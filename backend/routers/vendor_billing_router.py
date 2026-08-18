"""Phase 3 — Vendor Bill Processing, Payables, GST Input, TDS Payable & Payment Control
=========================================================================================
Endpoints under `/api/payables/*` — mirror of Phase 2 on the AP side.

Integration:
  • Reads Procurement (`purchase_orders`) for PO #, vendor master, payment terms
  • Reads Store & Inventory (`grn`) for GRN# / accepted qty / accepted value
  • Reads Vendors (`vendors`) for PAN/GST/MSME/bank-verification
  • Writes JE via accounting_service.post_vendor_invoice_verify / post_vendor_payment
    — flows directly into Trial Balance / AP Aging / Accounts Dashboard
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from accounting_service import post_vendor_invoice_verify, post_vendor_payment

router = APIRouter(prefix="/payables", tags=["Vendor Billing & Payables"])


EXPENSE_CATEGORY_MAP: Dict[str, str] = {
    "material":         "5105",
    "labour":           "5111",
    "subcontract":      "5121",
    "tools":            "5135",
    "fuel":             "5141",
    "vehicle":          "5142",
    "loading":          "5143",
    "site":             "5150",
    "accommodation":    "5151",
    "safety":           "5300",
    "office":           "5400",
    "rent":             "5410",
    "professional":     "5420",
    "bank_charges":     "5430",
    "repair":           "5440",
    "misc":             "5900",
    "inventory":        "1300",     # to stores
    "project_material": "5100",     # to project cost
}


class VendorBillLineIn(BaseModel):
    description: str
    quantity: float = 1
    unit: str = "Nos"
    rate: float = 0
    taxable_value: Optional[float] = None


class VendorBillIn(BaseModel):
    vendor_id: Optional[str] = None
    vendor_name: str
    vendor_category: Optional[str] = None
    vendor_gstin: Optional[str] = None
    vendor_pan: Optional[str] = None
    msme_status: Optional[str] = None         # 'micro' | 'small' | 'medium' | None
    bank_verified: bool = False               # source-of-truth from vendor master
    po_number: Optional[str] = None
    po_id: Optional[str] = None
    grn_number: Optional[str] = None
    grn_id: Optional[str] = None
    service_confirmation_no: Optional[str] = None  # for service bills (no GRN)
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    invoice_no: str                            # vendor's invoice number (used for dup check)
    invoice_date: str
    invoice_received_date: Optional[str] = None
    expense_category: str = "material"         # key in EXPENSE_CATEGORY_MAP
    is_inventory: bool = False                 # if true → DR Inventory(1300) instead
    lines: List[VendorBillLineIn] = []
    gst_rate: float = 18.0
    is_intra_state: bool = True
    tds_section: Optional[str] = None          # '194C' / '194J' etc.
    tds_rate: float = 0.0
    advance_adjusted: float = 0.0
    retention_amount: float = 0.0              # absolute ₹ withheld at bill stage
    payment_terms: Optional[str] = None
    due_days: int = 30
    payment_priority: str = "normal"           # 'high' / 'normal' / 'low' / 'hold'
    attachments: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    force_no_po: bool = False                  # if true, allow bills without PO (needs admin)
    force_no_grn: bool = False                 # if true, allow bills without GRN (services)
    po_terms: Optional[List[Dict[str, Any]]] = None  # snapshot of PO T&C at bill entry


class VendorPaymentIn(BaseModel):
    payment_date: str
    vendor_id: Optional[str] = None
    vendor_name: str
    bill_ids: List[str] = []
    mode: str = "Bank"
    bank_account: Optional[str] = None
    utr: Optional[str] = None
    cheque_no: Optional[str] = None
    amount: float                              # net cash actually being paid
    retention_held: float = 0.0
    other_deduction: float = 0.0
    project_id: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    remarks: Optional[str] = None
    excess_reason: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────
def _compute_bill_totals(payload: VendorBillIn) -> Dict[str, float]:
    taxable = round(sum(
        (ln.taxable_value if ln.taxable_value is not None else ln.quantity * ln.rate)
        for ln in payload.lines
    ), 2) if payload.lines else 0.0
    gst = round(taxable * (payload.gst_rate or 0) / 100, 2)
    cgst = sgst = igst = 0.0
    if payload.is_intra_state:
        cgst = sgst = round(gst / 2, 2)
    else:
        igst = gst
    gross = round(taxable + gst, 2)
    tds = round(taxable * (payload.tds_rate or 0) / 100, 2)
    net_payable = round(gross - tds - payload.advance_adjusted - payload.retention_amount, 2)
    return {"taxable": taxable, "gst": gst, "cgst": cgst, "sgst": sgst, "igst": igst,
            "gross": gross, "tds": tds, "net_payable": net_payable}


async def _validate_bill_dependencies(payload: VendorBillIn) -> Dict[str, Any]:
    """Returns dict of warnings/flags. Raises 400 for hard-blocks."""
    flags: Dict[str, Any] = {"warnings": [], "matched": {}}

    # Dup invoice check (same vendor + invoice_no)
    if payload.vendor_id or payload.vendor_name:
        q = {"invoice_no": payload.invoice_no,
             "status": {"$ne": "cancelled"}}
        q["vendor_id" if payload.vendor_id else "vendor_name"] = payload.vendor_id or payload.vendor_name
        dup = await db.vendor_bills.find_one(q, {"_id": 0, "id": 1, "invoice_no": 1})
        if dup:
            raise HTTPException(status_code=409,
                detail=f"Duplicate invoice {payload.invoice_no} already exists for this vendor (bill {dup['id']})")

    # PO match
    if payload.po_number:
        po = await db.purchase_orders.find_one(
            {"po_number": payload.po_number}, {"_id": 0, "id": 1, "po_number": 1, "vendor": 1, "amount": 1, "status": 1}
        )
        if not po:
            if not payload.force_no_po:
                raise HTTPException(status_code=400, detail=f"PO {payload.po_number} not found")
            flags["warnings"].append("PO not found — override accepted")
        else:
            flags["matched"]["po"] = po
    elif not payload.force_no_po and not payload.service_confirmation_no:
        raise HTTPException(status_code=400, detail="PO number required — set force_no_po=true to override (needs special permission)")

    # GRN match
    if payload.grn_number:
        grn = await db.grn.find_one({"grn_number": payload.grn_number},
                                     {"_id": 0, "id": 1, "grn_number": 1, "po_number": 1, "total_accepted": 1, "status": 1})
        if not grn:
            if not payload.force_no_grn:
                raise HTTPException(status_code=400, detail=f"GRN {payload.grn_number} not found")
            flags["warnings"].append("GRN not found — override accepted")
        else:
            flags["matched"]["grn"] = grn
            # PO-GRN cross-check
            if payload.po_number and grn.get("po_number") and grn["po_number"] != payload.po_number:
                raise HTTPException(status_code=400,
                    detail=f"GRN {payload.grn_number} belongs to PO {grn['po_number']}, not {payload.po_number}")
    elif not payload.service_confirmation_no and not payload.force_no_grn:
        raise HTTPException(status_code=400, detail="GRN or service_confirmation_no required — set force_no_grn=true to override")
    return flags


# ════════════════════════════════════════════════════════════════════════
# Vendor Bills
# ════════════════════════════════════════════════════════════════════════
@router.get("/expense-categories")
async def list_expense_categories(user: dict = Depends(require_permission("accounting", "read"))):
    return [{"key": k, "account_code": v} for k, v in EXPENSE_CATEGORY_MAP.items()]


@router.get("/grn-prefill")
async def grn_prefill(grn_number: str = Query(...),
                      user: dict = Depends(require_permission("accounting", "read"))):
    """Auto-fetch vendor, PO rates, GST/PAN/MSME/bank, project & PO terms from an accepted GRN."""
    grn = await db.grn.find_one({"grn_number": grn_number}, {"_id": 0})
    if not grn:
        raise HTTPException(404, f"GRN '{grn_number}' not found")
    po = await db.purchase_orders.find_one({"po_number": grn.get("po_number")}, {"_id": 0}) if grn.get("po_number") else None
    vendor = None
    if grn.get("vendor_id"):
        vendor = await db.vendors.find_one({"id": grn["vendor_id"]}, {"_id": 0})
    if not vendor:
        vname = grn.get("vendor_name") or (po or {}).get("vendor")
        if vname:
            vendor = await db.vendors.find_one({"name": vname}, {"_id": 0})
    po_items = (po or {}).get("items") or []
    lines = []
    for it in grn.get("items") or []:
        acc = float(it.get("accepted_qty") or 0)
        if acc <= 0:
            continue
        rate = 0.0
        idx = it.get("po_item_index")
        if idx is not None and 0 <= int(idx) < len(po_items):
            rate = float(po_items[int(idx)].get("rate") or 0)
        if not rate and it.get("item_id"):
            for p_it in po_items:
                if p_it.get("item_id") == it.get("item_id"):
                    rate = float(p_it.get("rate") or 0)
                    break
        if not rate and po and len(po_items) <= 1:
            rate = float(po.get("rate") or 0)
        lines.append({"description": it.get("item_name") or "", "quantity": acc,
                      "unit": it.get("unit") or "Nos", "rate": rate})
    bank = None
    for acct in (vendor or {}).get("bank_accounts") or []:
        if acct.get("is_default"):
            bank = acct
            break
    if bank is None and (vendor or {}).get("bank_accounts"):
        bank = vendor["bank_accounts"][0]
    msme = (vendor or {}).get("msme") or {}
    due_days = 30
    pt = str((po or {}).get("payment_terms") or "").strip()
    m = re.search(r"\b(\d{1,3})\b", pt)
    if m and 1 <= int(m.group(1)) <= 120:
        due_days = int(m.group(1))
    project_code = grn.get("project_code") or (po or {}).get("project")
    proj = await db.projects.find_one({"code": project_code}, {"_id": 0, "id": 1}) if project_code else None
    return {
        "vendor_id": (vendor or {}).get("id"),
        "vendor_name": (vendor or {}).get("name") or grn.get("vendor_name"),
        "vendor_gstin": (vendor or {}).get("gst") or "",
        "vendor_pan": (vendor or {}).get("pan") or "",
        "msme_status": msme.get("status"),
        "bank_verified": bool(bank and bank.get("account_no") and bank.get("ifsc")),
        "bank": bank,
        "po_number": grn.get("po_number"), "po_id": (po or {}).get("id"),
        "grn_number": grn_number, "grn_id": grn.get("id"),
        "project_code": project_code, "project_id": (proj or {}).get("id"),
        "lines": lines,
        "due_days": due_days,
        "payment_terms": pt or None,
        "delivery_days": (po or {}).get("delivery_days"),
        "po_terms_text": (po or {}).get("terms"),
        "po_terms": (po or {}).get("terms_structured") or [],
    }


@router.post("/vendor-bills")
async def create_vendor_bill(payload: VendorBillIn, request: Request,
                             user: dict = Depends(require_permission("accounting", "write"))):
    if not payload.vendor_name:
        raise HTTPException(status_code=400, detail="vendor_name required")
    if not payload.invoice_no:
        raise HTTPException(status_code=400, detail="invoice_no required")

    deps = await _validate_bill_dependencies(payload)
    totals = _compute_bill_totals(payload)
    if totals["gross"] <= 0:
        raise HTTPException(status_code=400, detail="Invoice value must be > 0")
    if totals["tds"] > totals["gross"]:
        raise HTTPException(status_code=400, detail="TDS amount cannot exceed gross invoice value")

    expense_code = EXPENSE_CATEGORY_MAP.get(payload.expense_category, "5400")
    if payload.is_inventory:
        expense_code = "1300"
    elif payload.project_id and payload.expense_category in {"material", "labour", "subcontract"}:
        expense_code = "5100" if payload.expense_category == "material" else expense_code

    bill_no = await next_sequence("VB")  # internal bill # — distinct from vendor's invoice_no
    due_date = (datetime.fromisoformat(payload.invoice_date) + timedelta(days=payload.due_days)).date().isoformat()

    doc = {
        "id": new_id(),
        "bill_no": bill_no,
        "vendor_id": payload.vendor_id,
        "vendor_name": payload.vendor_name,
        "vendor_category": payload.vendor_category,
        "vendor_gstin": payload.vendor_gstin,
        "vendor_pan": payload.vendor_pan,
        "msme_status": payload.msme_status,
        "bank_verified": payload.bank_verified,
        "po_number": payload.po_number, "po_id": payload.po_id,
        "grn_number": payload.grn_number, "grn_id": payload.grn_id,
        "service_confirmation_no": payload.service_confirmation_no,
        "project_id": payload.project_id, "project_code": payload.project_code,
        "invoice_no": payload.invoice_no,
        "invoice_date": payload.invoice_date,
        "invoice_received_date": payload.invoice_received_date or now_iso()[:10],
        "due_date": due_date, "due_days": payload.due_days,
        "expense_category": payload.expense_category,
        "expense_code": expense_code,
        "is_inventory": payload.is_inventory,
        "lines": [ln.model_dump() for ln in payload.lines],
        "gst_rate": payload.gst_rate, "is_intra_state": payload.is_intra_state,
        "tds_section": payload.tds_section, "tds_rate": payload.tds_rate,
        "advance_adjusted": payload.advance_adjusted,
        "retention_amount": payload.retention_amount,
        "payment_terms": payload.payment_terms,
        "po_terms": payload.po_terms,
        "payment_priority": payload.payment_priority,
        "totals": totals,
        "amount": totals["gross"],
        "tax_amount": totals["gst"],
        "tds_amount": totals["tds"],
        "paid_amount": 0.0,
        "outstanding": totals["net_payable"],
        "attachments": payload.attachments or [],
        "notes": payload.notes,
        "match_flags": deps,
        "status": "draft",          # draft → verified → approved → partially_paid → paid → cancelled
        "verified_by": None, "verified_at": None,
        "approved_by": None, "approved_at": None,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.vendor_bills.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="vendor_bill_create", resource="vendor_bills",
                record_id=doc["id"], after={"bill_no": bill_no, "vendor": payload.vendor_name,
                                            "invoice_no": payload.invoice_no, "gross": totals["gross"]},
                ip=request.client.host if request.client else "")
    return doc


@router.get("/vendor-bills")
async def list_vendor_bills(status: Optional[str] = None,
                            vendor_id: Optional[str] = None, project_id: Optional[str] = None,
                            po_number: Optional[str] = None, payment_priority: Optional[str] = None,
                            start: Optional[str] = None, end: Optional[str] = None,
                            limit: int = 200,
                            user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if vendor_id:
        q["vendor_id"] = vendor_id
    if project_id:
        q["project_id"] = project_id
    if po_number:
        q["po_number"] = po_number
    if payment_priority:
        q["payment_priority"] = payment_priority
    if start:
        q["invoice_date"] = {**q.get("invoice_date", {}), "$gte": start}
    if end:
        q["invoice_date"] = {**q.get("invoice_date", {}), "$lte": end}
    return await db.vendor_bills.find(q, {"_id": 0}).sort("invoice_date", -1).limit(limit).to_list(limit)


@router.get("/vendor-bills/{bill_id}")
async def get_vendor_bill(bill_id: str, user: dict = Depends(require_permission("accounting", "read"))):
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    return b


@router.post("/vendor-bills/{bill_id}/verify")
async def verify_vendor_bill(bill_id: str, request: Request,
                             user: dict = Depends(require_permission("accounting", "write"))):
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    if b.get("status") != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot verify bill in status {b.get('status')}")
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": {
        "status": "verified",
        "verified_by": user.get("name") or user.get("email"),
        "verified_at": now_iso(),
    }})
    await audit(user=user, action="vendor_bill_verify", resource="vendor_bills",
                record_id=bill_id, after={"bill_no": b["bill_no"]},
                ip=request.client.host if request.client else "")
    return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})


@router.post("/vendor-bills/{bill_id}/approve")
async def approve_vendor_bill(bill_id: str, request: Request,
                              user: dict = Depends(require_permission("accounting", "write"))):
    """Approve → auto-post JE (DR Expense + DR GST Input / CR AP + CR TDS Payable + CR Vendor Advance)."""
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    if b.get("status") not in ("draft", "verified"):
        raise HTTPException(status_code=400, detail=f"Cannot approve bill in status {b.get('status')}")

    # Validation: attachments required for expenses without PO/GRN
    if not b.get("attachments") and not (b.get("po_number") or b.get("grn_number")):
        raise HTTPException(status_code=400,
            detail="Attachments required for invoices without PO/GRN reference")

    try:
        je = await post_vendor_invoice_verify({
            "id": b["id"], "invoice_no": b["invoice_no"], "invoice_date": b["invoice_date"],
            "vendor_id": b.get("vendor_id"), "vendor_name": b.get("vendor_name"),
            "amount": b["totals"]["gross"], "tax_amount": b["totals"]["gst"],
            "tds_amount": b["totals"]["tds"],
            "advance_adjusted": b.get("advance_adjusted") or 0,
            "retention_amount": b.get("retention_amount") or 0,
            "expense_code": b.get("expense_code"),
            "is_inventory": b.get("is_inventory") or False,
            "project_id": b.get("project_id"),
            "department": b.get("department"),
        }, user)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"JE post failed: {e}")

    await db.vendor_bills.update_one({"id": bill_id}, {"$set": {
        "status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "je_id": je["id"] if je else None,
        "je_voucher_number": (je or {}).get("voucher_number"),
    }})
    # Bump project cost if linked
    if b.get("project_id"):
        await db.projects.update_one(
            {"id": b["project_id"]},
            {"$inc": {"cost_incurred": float(b["totals"]["gross"])}}
        )
    await audit(user=user, action="vendor_bill_approve", resource="vendor_bills",
                record_id=bill_id,
                after={"bill_no": b["bill_no"], "je": (je or {}).get("voucher_number")},
                ip=request.client.host if request.client else "")
    updated = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    await _push_bill_to_payment_queue(updated, user)
    return updated


async def _push_bill_to_payment_queue(b: dict, user: dict) -> None:
    """Approved vendor bill → shadow row in the unified Accounts Payment Processing
    queue (same flow as logistics vendor bills & employee advances). Payment JE
    debits Accounts Payable (2100) since expense was booked at approval."""
    if await db.project_requests.find_one(
            {"source": "accounts_vendor_bill", "source_id": b["id"]}, {"_id": 0, "id": 1}):
        return
    proj = await db.projects.find_one({"id": b.get("project_id")}, {"_id": 0, "name": 1}) if b.get("project_id") else None
    is_service = bool(b.get("service_confirmation_no")) and not b.get("grn_number")
    await db.project_requests.insert_one({
        "id": new_id(),
        "request_no": b.get("bill_no"),
        "request_type": "service_vendor_bill" if is_service else "material_vendor_bill",
        "request_type_label": "Service Vendor Bill (SRN)" if is_service else "Material Vendor Bill (PO/GRN)",
        "is_payment": True, "is_stockable": False,
        "owning_dept": "accounts",
        "expense_type": b.get("expense_category"),
        "status": "with_dept",
        "payment_status": "payment_pending",
        "source": "accounts_vendor_bill", "source_id": b["id"],
        "project_id": b.get("project_id"), "project_code": b.get("project_code"),
        "project_name": (proj or {}).get("name"),
        "vendor": b.get("vendor_name"),
        "invoice_no": b.get("invoice_no"), "invoice_date": b.get("invoice_date"),
        "due_date": b.get("due_date"),
        "est_value": float(b.get("outstanding") or 0),
        "pay_debit_account_code": "2100",
        "description": (f"Vendor bill {b.get('bill_no')} · Inv {b.get('invoice_no')} — {b.get('vendor_name')} "
                        f"(PO {b.get('po_number') or '—'} / {'SC ' + b.get('service_confirmation_no') if is_service else 'GRN ' + (b.get('grn_number') or '—')})"),
        "items": [], "chain": [], "current_step": None,
        "created_by": user.get("name") or user.get("email"), "created_by_id": user.get("id"),
        "created_at": now_iso(),
    })


@router.post("/vendor-bills/{bill_id}/cancel")
async def cancel_vendor_bill(bill_id: str, request: Request,
                             user: dict = Depends(require_permission("accounting", "write"))):
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    if b.get("status") not in ("draft", "verified"):
        raise HTTPException(status_code=400, detail="Approved bill must be corrected via Debit/Credit Note")
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": {
        "status": "cancelled",
        "cancelled_by": user.get("name") or user.get("email"),
        "cancelled_at": now_iso(),
    }})
    await audit(user=user, action="vendor_bill_cancel", resource="vendor_bills",
                record_id=bill_id, after={"bill_no": b["bill_no"]},
                ip=request.client.host if request.client else "")
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════
# Vendor Payments
# ════════════════════════════════════════════════════════════════════════
@router.post("/vendor-payments")
async def create_vendor_payment(payload: VendorPaymentIn, request: Request,
                                user: dict = Depends(require_permission("accounting", "write"))):
    if payload.amount <= 0 and payload.retention_held <= 0:
        raise HTTPException(status_code=400, detail="amount or retention_held required > 0")
    total_settled = round(payload.amount + payload.retention_held + payload.other_deduction, 2)

    # Validate bank_verified on every approved bill being paid
    bills_cache = []
    avail = 0.0
    for bid in payload.bill_ids:
        b = await db.vendor_bills.find_one({"id": bid}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=404, detail=f"Bill {bid} not found")
        if b.get("status") not in ("approved", "partially_paid"):
            raise HTTPException(status_code=400, detail=f"Bill {b['bill_no']} status {b.get('status')} — must be approved")
        if not b.get("bank_verified"):
            raise HTTPException(status_code=400,
                detail=f"Vendor bank details NOT verified for bill {b['bill_no']} — cannot pay")
        bills_cache.append(b)
        avail += float(b.get("outstanding") or 0)

    excess = round(total_settled - avail, 2)
    if excess > 0.01 and not payload.excess_reason:
        raise HTTPException(status_code=400,
            detail=f"Excess payment ₹{excess:,.2f} requires `excess_reason`")

    # Apply FIFO
    remaining = total_settled
    for b in bills_cache:
        outs = float(b.get("outstanding") or 0)
        apply_amt = min(outs, remaining)
        if apply_amt <= 0:
            continue
        new_outs = round(outs - apply_amt, 2)
        await db.vendor_bills.update_one({"id": b["id"]}, {"$inc": {
            "paid_amount": apply_amt,
        }, "$set": {
            "outstanding": new_outs,
            "status": "paid" if new_outs < 0.01 else "partially_paid",
        }})
        remaining = round(remaining - apply_amt, 2)
        if remaining < 0.01:
            break

    pay_no = await next_sequence("VPAY")
    pay = {
        "id": new_id(),
        "payment_no": pay_no,
        "payment_date": payload.payment_date,
        "vendor_id": payload.vendor_id, "vendor_name": payload.vendor_name,
        "bill_ids": payload.bill_ids,
        "mode": payload.mode, "bank_account": payload.bank_account,
        "utr": payload.utr, "cheque_no": payload.cheque_no, "reference": payload.utr or payload.cheque_no,
        "amount": payload.amount,
        "retention_held": payload.retention_held,
        "other_deduction": payload.other_deduction,
        "total_settled": total_settled,
        "project_id": payload.project_id,
        "attachments": payload.attachments or [],
        "remarks": payload.remarks, "excess_reason": payload.excess_reason,
        "status": "released",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.vendor_payments.insert_one(pay)
    pay.pop("_id", None)

    # Auto-JE
    try:
        je = await post_vendor_payment({
            "id": pay["id"], "payment_date": payload.payment_date,
            "vendor_id": payload.vendor_id, "vendor_name": payload.vendor_name,
            "amount": payload.amount, "retention_held": payload.retention_held,
            "other_deduction": payload.other_deduction,
            "mode": payload.mode, "reference": payload.utr or payload.cheque_no,
            "project_id": payload.project_id,
        }, None, user)
        if je:
            await db.vendor_payments.update_one({"id": pay["id"]}, {"$set": {
                "je_id": je["id"], "je_voucher_number": je.get("voucher_number"),
            }})
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger("erp").warning(f"[payables] payment JE skipped: {e}")

    await audit(user=user, action="vendor_payment_create", resource="vendor_payments",
                record_id=pay["id"], after={"payment_no": pay_no, "total": total_settled},
                ip=request.client.host if request.client else "")
    return await db.vendor_payments.find_one({"id": pay["id"]}, {"_id": 0})


@router.get("/vendor-payments")
async def list_vendor_payments(vendor_id: Optional[str] = None,
                               start: Optional[str] = None, end: Optional[str] = None,
                               limit: int = 200,
                               user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if vendor_id:
        q["vendor_id"] = vendor_id
    if start:
        q["payment_date"] = {**q.get("payment_date", {}), "$gte": start}
    if end:
        q["payment_date"] = {**q.get("payment_date", {}), "$lte": end}
    return await db.vendor_payments.find(q, {"_id": 0}).sort("payment_date", -1).limit(limit).to_list(limit)


# ════════════════════════════════════════════════════════════════════════
# Payable Reports
# ════════════════════════════════════════════════════════════════════════
def _age_bucket(date_iso: str) -> tuple[str, int]:
    try:
        d = datetime.fromisoformat(date_iso).date()
        days = (datetime.now(timezone.utc).date() - d).days
    except Exception:
        days = 0
    if days <= 30:
        return ("0-30", days)
    if days <= 60:
        return ("31-60", days)
    if days <= 90:
        return ("61-90", days)
    return ("90+", days)


@router.get("/reports/vendor-outstanding")
async def vendor_outstanding(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.vendor_bills.find(
        {"status": {"$in": ["approved", "partially_paid"]}, "outstanding": {"$gt": 0}},
        {"_id": 0}
    ).to_list(2000)
    by_vendor: Dict[str, Dict[str, Any]] = {}
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for r in rows:
        outs = float(r.get("outstanding") or 0)
        b, days = _age_bucket(r["invoice_date"])
        buckets[b] += outs
        v = r["vendor_name"]
        row = by_vendor.setdefault(v, {"vendor_name": v, "total_outstanding": 0.0, "bills": []})
        row["total_outstanding"] += outs
        r["bucket"] = b
        r["days_overdue"] = days
        row["bills"].append(r)
    return {"buckets": {k: round(v, 2) for k, v in buckets.items()},
            "total_outstanding": round(sum(buckets.values()), 2),
            "vendors": sorted(by_vendor.values(), key=lambda x: -x["total_outstanding"])}


@router.get("/reports/payable-aging")
async def payable_aging(user: dict = Depends(require_permission("accounting", "read"))):
    return await vendor_outstanding(user)  # aging buckets already in vendor_outstanding


@router.get("/reports/payment-due")
async def payment_due(days_ahead: int = 7,
                      user: dict = Depends(require_permission("accounting", "read"))):
    today = datetime.now(timezone.utc).date()
    limit_date = (today + timedelta(days=days_ahead)).isoformat()
    rows = await db.vendor_bills.find({
        "status": {"$in": ["approved", "partially_paid"]},
        "due_date": {"$lte": limit_date},
        "outstanding": {"$gt": 0},
    }, {"_id": 0}).sort("due_date", 1).to_list(500)
    for r in rows:
        try:
            r["overdue_days"] = (today - datetime.fromisoformat(r["due_date"]).date()).days
        except Exception:
            r["overdue_days"] = 0
    return {"rows": rows, "total_due": round(sum(float(r.get("outstanding") or 0) for r in rows), 2)}


@router.get("/reports/vendor-advance")
async def vendor_advance_report(user: dict = Depends(require_permission("accounting", "read"))):
    """Vendor advances paid not yet adjusted. Reads from journal_entries on account 1510."""
    rows = await db.journal_entries.find(
        {"lines.account_code": "1510", "status": "posted"},
        {"_id": 0, "voucher_number": 1, "date": 1, "narration": 1, "party_name": 1, "lines": 1}
    ).sort("date", -1).limit(500).to_list(500)
    by_vendor: Dict[str, float] = {}
    for r in rows:
        for ln in (r.get("lines") or []):
            if ln.get("account_code") == "1510":
                v = r.get("party_name") or r.get("narration") or "—"
                by_vendor[v] = by_vendor.get(v, 0) + float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
    return {"vendors": [{"vendor_name": k, "balance": round(v, 2)} for k, v in by_vendor.items() if abs(v) > 0.01]}


@router.get("/reports/retention-payable")
async def retention_payable_report(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.vendor_payments.find({"retention_held": {"$gt": 0}}, {"_id": 0}).to_list(2000)
    by_vendor: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        v = r["vendor_name"]
        row = by_vendor.setdefault(v, {"vendor_name": v, "retention_held": 0.0, "payments": []})
        row["retention_held"] += float(r.get("retention_held") or 0)
        row["payments"].append({"payment_no": r["payment_no"], "payment_date": r["payment_date"],
                                "retention_held": r.get("retention_held")})
    return {"vendors": sorted(by_vendor.values(), key=lambda x: -x["retention_held"]),
            "total_retention": round(sum(float(r.get("retention_held") or 0) for r in rows), 2)}


@router.get("/reports/tds-payable")
async def tds_payable_report(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.vendor_bills.find(
        {"tds_amount": {"$gt": 0}, "status": {"$in": ["approved", "partially_paid", "paid"]}},
        {"_id": 0, "bill_no": 1, "invoice_no": 1, "vendor_name": 1, "tds_section": 1,
         "tds_amount": 1, "tds_rate": 1, "invoice_date": 1, "project_id": 1}
    ).sort("invoice_date", -1).to_list(2000)
    total = sum(float(r.get("tds_amount") or 0) for r in rows)
    by_section: Dict[str, float] = {}
    for r in rows:
        s = r.get("tds_section") or "—"
        by_section[s] = by_section.get(s, 0) + float(r.get("tds_amount") or 0)
    return {"rows": rows, "total_tds": round(total, 2),
            "by_section": [{"section": k, "amount": round(v, 2)} for k, v in by_section.items()]}


@router.get("/reports/gst-purchase-register")
async def gst_purchase_register(start: Optional[str] = None, end: Optional[str] = None,
                                user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {"status": {"$in": ["approved", "partially_paid", "paid"]}}
    if start:
        q["invoice_date"] = {**q.get("invoice_date", {}), "$gte": start}
    if end:
        q["invoice_date"] = {**q.get("invoice_date", {}), "$lte": end}
    rows = await db.vendor_bills.find(q, {"_id": 0}).sort("invoice_date", -1).to_list(2000)
    out: List[Dict[str, Any]] = []
    totals = {"taxable": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "gross": 0.0}
    for r in rows:
        t = r.get("totals") or {}
        out.append({"bill_no": r["bill_no"], "invoice_no": r.get("invoice_no"),
                    "invoice_date": r["invoice_date"], "vendor_name": r["vendor_name"],
                    "vendor_gstin": r.get("vendor_gstin"), "expense_category": r.get("expense_category"),
                    "gst_rate": r.get("gst_rate"), "is_intra_state": r.get("is_intra_state"),
                    "taxable": t.get("taxable"), "cgst": t.get("cgst"), "sgst": t.get("sgst"),
                    "igst": t.get("igst"), "gross": t.get("gross")})
        totals["taxable"] += float(t.get("taxable") or 0)
        totals["cgst"] += float(t.get("cgst") or 0)
        totals["sgst"] += float(t.get("sgst") or 0)
        totals["igst"] += float(t.get("igst") or 0)
        totals["gross"] += float(t.get("gross") or 0)
    return {"rows": out, "totals": {k: round(v, 2) for k, v in totals.items()}}


@router.get("/reports/project-vendor-cost")
async def project_vendor_cost(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.vendor_bills.find(
        {"status": {"$in": ["approved", "partially_paid", "paid"]}, "project_id": {"$ne": None}},
        {"_id": 0, "project_id": 1, "project_code": 1, "vendor_name": 1, "totals": 1, "expense_category": 1}
    ).to_list(2000)
    by_proj: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        p = r.get("project_code") or r.get("project_id") or "—"
        row = by_proj.setdefault(p, {"project_code": p, "total_cost": 0.0, "by_vendor": {}, "by_category": {}})
        amt = float((r.get("totals") or {}).get("gross") or 0)
        row["total_cost"] += amt
        v = r.get("vendor_name") or "—"
        row["by_vendor"][v] = row["by_vendor"].get(v, 0) + amt
        cat = r.get("expense_category") or "—"
        row["by_category"][cat] = row["by_category"].get(cat, 0) + amt
    return {"projects": sorted(by_proj.values(), key=lambda x: -x["total_cost"])}


@router.get("/reports/grn-pending-invoice")
async def grn_pending_invoice(user: dict = Depends(require_permission("accounting", "read"))):
    """GRNs finalized but no vendor bill received yet (matched by GRN number)."""
    grns = await db.grn.find({"status": {"$in": ["finalized", "approved", "received"]}},
                             {"_id": 0, "id": 1, "grn_number": 1, "po_number": 1,
                              "vendor_name": 1, "received_at": 1, "total_accepted": 1}).to_list(500)
    billed_grns = set()
    async for b in db.vendor_bills.find({"grn_number": {"$ne": None}}, {"_id": 0, "grn_number": 1}):
        billed_grns.add(b["grn_number"])
    pending = [g for g in grns if g["grn_number"] not in billed_grns]
    return {"rows": pending, "count": len(pending),
            "total_value": round(sum(float(g.get("total_accepted") or 0) for g in pending), 2)}


@router.get("/reports/duplicate-invoice-check")
async def duplicate_invoice_check(user: dict = Depends(require_permission("accounting", "read"))):
    """Returns bills with same (vendor + invoice_no) — should be empty after enforcement."""
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$group": {"_id": {"vendor_id": "$vendor_id", "vendor_name": "$vendor_name", "invoice_no": "$invoice_no"},
                    "count": {"$sum": 1}, "bills": {"$push": {"bill_no": "$bill_no", "id": "$id", "invoice_date": "$invoice_date"}}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 100},
    ]
    return [row async for row in db.vendor_bills.aggregate(pipeline)]


@router.get("/reports/vendor-ledger")
async def vendor_ledger(vendor_id: Optional[str] = None, vendor_name: Optional[str] = None,
                        user: dict = Depends(require_permission("accounting", "read"))):
    if not (vendor_id or vendor_name):
        raise HTTPException(status_code=400, detail="vendor_id or vendor_name required")
    q = {"vendor_id": vendor_id} if vendor_id else {"vendor_name": vendor_name}
    bills = await db.vendor_bills.find(q, {"_id": 0}).sort("invoice_date", 1).to_list(2000)
    payments = await db.vendor_payments.find(q, {"_id": 0}).sort("payment_date", 1).to_list(2000)
    events: List[Dict[str, Any]] = []
    for b in bills:
        events.append({"date": b["invoice_date"], "type": "BILL", "ref": b["bill_no"],
                       "narration": b.get("invoice_no"),
                       "debit": 0,
                       "credit": float((b.get("totals") or {}).get("gross") or 0)})
    for p in payments:
        events.append({"date": p["payment_date"], "type": "PAYMENT", "ref": p["payment_no"],
                       "narration": f"{p.get('mode')} · {p.get('reference') or ''}",
                       "debit": float(p.get("total_settled") or 0), "credit": 0})
    events.sort(key=lambda x: x["date"])
    running = 0.0
    for e in events:
        running += e["debit"] - e["credit"]
        e["running"] = round(running, 2)
    return {"events": events, "closing_balance": round(running, 2)}


@router.get("/reports/po-payable")
async def po_wise_payable(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.vendor_bills.find(
        {"status": {"$in": ["approved", "partially_paid"]}, "po_number": {"$ne": None}, "outstanding": {"$gt": 0}},
        {"_id": 0, "po_number": 1, "vendor_name": 1, "totals": 1, "outstanding": 1, "bill_no": 1, "invoice_date": 1}
    ).to_list(2000)
    by_po: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        po = r["po_number"]
        row = by_po.setdefault(po, {"po_number": po, "vendor_name": r["vendor_name"], "outstanding": 0.0, "bills": []})
        row["outstanding"] += float(r.get("outstanding") or 0)
        row["bills"].append(r)
    return {"pos": sorted(by_po.values(), key=lambda x: -x["outstanding"])}
