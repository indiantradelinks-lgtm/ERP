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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from pydantic import BaseModel, Field

from core import db, require_permission, get_current_user, now_iso, new_id
from pagination import maybe_paged, paged_or_rows
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
    gst_pct: Optional[float] = None  # item-wise GST inherited from PO


class BillPaymentIn(BaseModel):
    """Advance / part payment recorded against ONE vendor bill (no new bill is created)."""
    amount: float
    payment_date: Optional[str] = None
    mode: str = "Bank"
    bank_account: Optional[str] = None
    utr: Optional[str] = None
    cheque_no: Optional[str] = None
    remarks: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


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
    advance_payment: Optional[BillPaymentIn] = None  # advance paid at bill entry (against GRN/invoice)


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
    if payload.lines and any(ln.gst_pct is not None for ln in payload.lines):
        gst = round(sum(
            (ln.taxable_value if ln.taxable_value is not None else ln.quantity * ln.rate)
            * float(ln.gst_pct if ln.gst_pct is not None else (payload.gst_rate or 0)) / 100
            for ln in payload.lines), 2)
    else:
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


APPROVED_LIKE = ("approved", "partially_paid", "paid")


def _payment_status(paid: float, net: float, bill_status: str, n_payments: int = 1) -> str:
    """Advance Paid → the first payment made before the bill cleared its approval chain.
    Partially Paid → part settled (approved bill, or a further instalment).
    Fully Paid → nothing outstanding."""
    if paid <= 0.01:
        return "unpaid"
    if round(net - paid, 2) <= 0.01:
        return "fully_paid"
    if bill_status in APPROVED_LIKE or n_payments > 1:
        return "partially_paid"
    return "advance_paid"


async def _record_bill_payment(bill: Dict[str, Any], p: BillPaymentIn, user: dict,
                               request: Optional[Request] = None) -> Dict[str, Any]:
    """Record one advance / part payment against a single bill and re-derive its
    paid, outstanding and payment status. Never creates another bill."""
    amount = round(float(p.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    if bill.get("status") in ("cancelled", "rejected"):
        raise HTTPException(status_code=400,
                            detail=f"Bill {bill['bill_no']} is {bill['status']} — payment cannot be recorded")
    if not bill.get("bank_verified"):
        raise HTTPException(status_code=400,
                            detail=f"Vendor bank details NOT verified for bill {bill['bill_no']} — cannot pay")
    net = round(float((bill.get("totals") or {}).get("net_payable") or bill.get("amount") or 0), 2)
    paid_before = round(float(bill.get("paid_amount") or 0), 2)
    outstanding_before = round(net - paid_before, 2)
    if amount > outstanding_before + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Payment ₹{amount:,.2f} exceeds the outstanding balance ₹{outstanding_before:,.2f} "
                   f"on {bill['bill_no']} — enter ₹{outstanding_before:,.2f} or less")

    paid_after = round(paid_before + amount, 2)
    outstanding_after = round(net - paid_after, 2)
    status_before = bill.get("status") or "draft"
    prior_payments = await db.vendor_payments.count_documents({"bill_ids": bill["id"]})
    pay_status = _payment_status(paid_after, net, status_before, prior_payments + 1)

    pay = {
        "id": new_id(),
        "payment_no": await next_sequence("VPAY"),
        "payment_date": p.payment_date or now_iso()[:10],
        "vendor_id": bill.get("vendor_id"), "vendor_name": bill.get("vendor_name"),
        "bill_ids": [bill["id"]], "bill_no": bill.get("bill_no"),
        "invoice_no": bill.get("invoice_no"), "grn_number": bill.get("grn_number"),
        "po_number": bill.get("po_number"),
        "mode": p.mode, "bank_account": p.bank_account,
        "utr": p.utr, "cheque_no": p.cheque_no, "reference": p.utr or p.cheque_no,
        "amount": amount, "retention_held": 0.0, "other_deduction": 0.0,
        "total_settled": amount,
        "payment_kind": "advance" if (status_before not in APPROVED_LIKE and prior_payments == 0) else "part",
        "bill_status_at_payment": status_before,
        "invoice_total": net,
        "outstanding_after": outstanding_after,
        "project_id": bill.get("project_id"), "project_code": bill.get("project_code"),
        "attachments": p.attachments or [],
        "remarks": p.remarks, "excess_reason": None,
        "status": "released",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.vendor_payments.insert_one(pay)
    pay.pop("_id", None)

    bill_set: Dict[str, Any] = {
        "paid_amount": paid_after,
        "outstanding": max(outstanding_after, 0.0),
        "payment_status": pay_status,
        "last_payment_at": pay["payment_date"],
    }
    # Only an approved bill moves its workflow status on payment — an advance paid
    # on a draft/under-approval bill must not short-circuit the approval chain.
    if status_before in APPROVED_LIKE:
        bill_set["status"] = "paid" if outstanding_after < 0.01 else "partially_paid"
    await db.vendor_bills.update_one({"id": bill["id"]}, {"$set": bill_set})

    try:
        je = await post_vendor_payment({
            "id": pay["id"], "payment_date": pay["payment_date"],
            "vendor_id": pay["vendor_id"], "vendor_name": pay["vendor_name"],
            "amount": amount, "retention_held": 0.0, "other_deduction": 0.0,
            "mode": p.mode, "reference": pay["reference"], "project_id": pay["project_id"],
        }, None, user)
        if je:
            await db.vendor_payments.update_one({"id": pay["id"]}, {"$set": {
                "je_id": je["id"], "je_voucher_number": je.get("voucher_number")}})
            pay["je_voucher_number"] = je.get("voucher_number")
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger("erp").warning(f"[payables] bill payment JE skipped: {e}")

    await audit(user=user, action="vendor_bill_payment", resource="vendor_bills",
                record_id=bill["id"],
                after={"payment_no": pay["payment_no"], "amount": amount, "kind": pay["payment_kind"],
                       "paid_amount": paid_after, "outstanding": outstanding_after,
                       "payment_status": pay_status},
                ip=request.client.host if request and request.client else "")
    return {**pay, "paid_amount": paid_after, "payment_status": pay_status}


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
        matched = None
        idx = it.get("po_item_index")
        if idx is not None and 0 <= int(idx) < len(po_items):
            matched = po_items[int(idx)]
            rate = float(matched.get("rate") or 0)
        if not rate and it.get("item_id"):
            for p_it in po_items:
                if p_it.get("item_id") == it.get("item_id"):
                    matched = p_it
                    rate = float(p_it.get("rate") or 0)
                    break
        if not rate and po and len(po_items) <= 1:
            matched = po_items[0] if po_items else None
            rate = float(po.get("rate") or 0)
        gst_pct = None
        if matched and matched.get("gst_pct") is not None:
            gst_pct = float(matched["gst_pct"])
        elif po and po.get("gst_pct") is not None:
            gst_pct = float(po["gst_pct"])
        lines.append({"description": it.get("item_name") or "", "quantity": acc,
                      "unit": it.get("unit") or "Nos", "rate": rate, "gst_pct": gst_pct})
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
        "payment_status": "unpaid",
        "attachments": payload.attachments or [],
        "notes": payload.notes,
        "match_flags": deps,
        "status": "draft",          # v3: draft → dept_approved → accounts_approved → admin_approved → approved → (due date) → payment queue
        "workflow_version": 3,
        "workflow_log": [],
        "payment_hold": False,
        "control_log": [],
        "verify_level": 0, "approve_level": 0,
        "verified_l1_by": None, "verified_l1_at": None,
        "approved_l1_by": None, "approved_l1_at": None,
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
    if payload.advance_payment and float(payload.advance_payment.amount or 0) > 0:
        pay = await _record_bill_payment(doc, payload.advance_payment, user, request)
        doc.update({"paid_amount": pay["paid_amount"], "payment_status": pay["payment_status"],
                    "outstanding": max(pay["outstanding_after"], 0.0),
                    "advance_payment_no": pay["payment_no"]})
    return doc


@router.post("/vendor-bills/{bill_id}/payments")
async def record_bill_payment(bill_id: str, payload: BillPaymentIn, request: Request,
                              user: dict = Depends(require_permission("accounting", "write"))):
    """Record an advance / part payment against an existing bill — the same invoice is
    settled over multiple payments instead of raising another bill."""
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    pay = await _record_bill_payment(b, payload, user, request)
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    return {"payment": pay, "bill": bill}


@router.get("/vendor-bills/{bill_id}/payments")
async def bill_payment_history(bill_id: str,
                               user: dict = Depends(require_permission("accounting", "read"))):
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    rows = await db.vendor_payments.find({"bill_ids": bill_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    net = round(float((b.get("totals") or {}).get("net_payable") or b.get("amount") or 0), 2)
    paid = round(sum(float(r.get("amount") or 0) + float(r.get("retention_held") or 0)
                     + float(r.get("other_deduction") or 0) for r in rows), 2)
    return {
        "bill_no": b.get("bill_no"), "invoice_no": b.get("invoice_no"),
        "vendor_name": b.get("vendor_name"), "grn_number": b.get("grn_number"),
        "invoice_total": net, "paid_amount": paid, "outstanding": round(net - paid, 2),
        "payment_status": b.get("payment_status") or _payment_status(paid, net, b.get("status") or "draft", len(rows)),
        "bill_status": b.get("status"),
        "payments": rows,
    }


@router.get("/vendor-bills")
async def list_vendor_bills(request: Request, status: Optional[str] = None,
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
    paged = await maybe_paged(request, "vendor_bills", q, "invoice_date",
                              ["bill_no", "invoice_no", "vendor_name", "po_number", "project_code", "project_name", "status", "grn_number"])
    if paged:
        return paged
    return await db.vendor_bills.find(q, {"_id": 0}).sort("invoice_date", -1).limit(limit).to_list(limit)


async def release_due_bills_to_queue() -> int:
    """Push v2/v3-workflow approved (not held) bills whose due date has arrived into the payment queue."""
    from datetime import date as _date
    today = _date.today().isoformat()
    n = 0
    async for b in db.vendor_bills.find(
            {"workflow_version": {"$in": [2, 3]}, "status": "approved", "outstanding": {"$gt": 0},
             "payment_hold": {"$ne": True}, "due_date": {"$lte": today}}, {"_id": 0}):
        await _push_bill_to_payment_queue(b, {"name": "system (due-date release)", "id": None})
        n += 1
    return n


@router.post("/vendor-bills/{bill_id}/reject")
async def reject_vendor_bill(bill_id: str, payload: dict, request: Request,
                             user: dict = Depends(require_permission("accounting", "write"))):
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    if b.get("status") not in ("draft", "verified_l1", "verified", "approved_l1",
                               "dept_approved", "accounts_approved", "admin_approved"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot reject bill in status {b.get('status')} — use Cancel for approved bills")
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": {
        "status": "rejected",
        "rejected_by": user.get("name") or user.get("email"),
        "rejected_at": now_iso(),
        "rejection_reason": (payload.get("reason") or "").strip() or None,
    }})
    await audit(user=user, action="vendor_bill_reject", resource="vendor_bills",
                record_id=bill_id, after={"bill_no": b["bill_no"], "reason": payload.get("reason")},
                ip=request.client.host if request.client else "")
    return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})


@router.put("/vendor-bills/{bill_id}")
async def update_vendor_bill(bill_id: str, payload: VendorBillIn, request: Request,
                             user: dict = Depends(require_permission("accounting", "write"))):
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    if b.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400,
                            detail=f"Only draft/rejected bills can be edited (current: {b.get('status')})")
    dup = await db.vendor_bills.find_one({
        "vendor_name": payload.vendor_name, "invoice_no": payload.invoice_no,
        "id": {"$ne": bill_id}, "status": {"$nin": ["cancelled", "rejected"]}}, {"_id": 0, "bill_no": 1})
    if dup:
        raise HTTPException(status_code=400,
                            detail=f"Duplicate: invoice {payload.invoice_no} for {payload.vendor_name} already exists ({dup['bill_no']})")
    totals = _compute_bill_totals(payload)
    paid_so_far = round(float(b.get("paid_amount") or 0), 2)
    if paid_so_far > totals["net_payable"] + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"₹{paid_so_far:,.2f} has already been paid against {b['bill_no']} — the revised "
                   f"net payable ₹{totals['net_payable']:,.2f} cannot be lower than that")
    due_date = (datetime.fromisoformat(payload.invoice_date) + timedelta(days=payload.due_days)).date().isoformat()
    upd = {
        "vendor_id": payload.vendor_id, "vendor_name": payload.vendor_name,
        "vendor_gstin": payload.vendor_gstin, "vendor_pan": payload.vendor_pan,
        "msme_status": payload.msme_status, "bank_verified": payload.bank_verified,
        "po_number": payload.po_number, "po_id": payload.po_id,
        "grn_number": payload.grn_number, "grn_id": payload.grn_id,
        "service_confirmation_no": payload.service_confirmation_no,
        "project_id": payload.project_id, "project_code": payload.project_code,
        "invoice_no": payload.invoice_no, "invoice_date": payload.invoice_date,
        "invoice_received_date": payload.invoice_received_date or b.get("invoice_received_date"),
        "due_date": due_date, "due_days": payload.due_days,
        "expense_category": payload.expense_category,
        "lines": [ln.model_dump() for ln in payload.lines],
        "gst_rate": payload.gst_rate, "is_intra_state": payload.is_intra_state,
        "tds_section": payload.tds_section, "tds_rate": payload.tds_rate,
        "advance_adjusted": payload.advance_adjusted,
        "retention_amount": payload.retention_amount,
        "payment_priority": payload.payment_priority,
        "totals": totals, "amount": totals["gross"], "tax_amount": totals["gst"],
        "tds_amount": totals["tds"],
        "outstanding": max(round(totals["net_payable"] - float(b.get("paid_amount") or 0), 2), 0.0),
        "payment_status": _payment_status(float(b.get("paid_amount") or 0), totals["net_payable"], "draft"),
        "notes": payload.notes,
        "status": "draft", "verify_level": 0, "approve_level": 0,
        "verified_l1_by": None, "verified_l1_at": None,
        "verified_by": None, "verified_at": None,
        "approved_l1_by": None, "approved_l1_at": None,
        "edited_by": user.get("name") or user.get("email"), "edited_at": now_iso(),
    }
    if payload.attachments:
        upd["attachments"] = payload.attachments
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": upd})
    await audit(user=user, action="vendor_bill_edit", resource="vendor_bills",
                record_id=bill_id, after={"bill_no": b["bill_no"], "invoice_no": payload.invoice_no,
                                          "gross": totals["gross"]},
                ip=request.client.host if request.client else "")
    return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})


@router.get("/vendor-bills/report/pdf")
async def vendor_bills_report_pdf(status: Optional[str] = None, payment_priority: Optional[str] = None,
                                  user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if payment_priority:
        q["payment_priority"] = payment_priority
    rows = [r async for r in db.vendor_bills.find(q, {"_id": 0}).sort("created_at", -1).limit(500)]
    from pdf_generator import render_vendor_bills_report
    pdf = render_vendor_bills_report(rows, status_label=(status or "All Statuses"))
    from fastapi import Response
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="vendor-bills-report.pdf"'})


PAYMENT_CONTROL_ROLES = {"accounts_executive", "general_manager", "director", "super_admin"}


@router.post("/vendor-bills/{bill_id}/payment-control")
async def vendor_bill_payment_control(bill_id: str, payload: dict, request: Request,
                                      user: dict = Depends(get_current_user)):
    """Authorized: hold/release payment or change due days AFTER approval. Fully audited."""
    if user.get("role") not in PAYMENT_CONTROL_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Payment control requires one of: {', '.join(sorted(PAYMENT_CONTROL_ROLES))}")
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    if b.get("status") not in ("approved", "partially_paid"):
        raise HTTPException(status_code=400, detail=f"Payment control only for approved bills (current: {b.get('status')})")
    action = payload.get("action")
    remarks = (payload.get("remarks") or "").strip()
    actor = user.get("name") or user.get("email")
    entry = {"action": action, "by": actor, "role": user.get("role"), "at": now_iso(), "remarks": remarks or None}
    upd: Dict[str, Any] = {}
    if action == "hold":
        upd = {"payment_hold": True, "hold_reason": remarks or None}
        # pull unprocessed queue row back (only if Accounts hasn't started verification)
        qrow = await db.project_requests.find_one({"source": "accounts_vendor_bill", "source_id": bill_id}, {"_id": 0, "id": 1})
        if qrow and not await db.payment_verifications.find_one({"request_id": qrow["id"]}, {"_id": 0, "id": 1}):
            await db.project_requests.delete_one({"id": qrow["id"]})
            entry["queue_row_removed"] = True
    elif action == "release":
        upd = {"payment_hold": False, "hold_reason": None}
    elif action == "set_due_days":
        try:
            dd = int(payload.get("due_days"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="due_days must be a number")
        if not 0 <= dd <= 365:
            raise HTTPException(status_code=400, detail="due_days must be between 0 and 365")
        base = (b.get("approved_at") or now_iso())[:10]
        new_due = (datetime.fromisoformat(base) + timedelta(days=dd)).date().isoformat()
        entry["from_due"] = b.get("due_date")
        entry["to_due"] = new_due
        upd = {"due_days": dd, "due_date": new_due, "payment_release_date": new_due}
    else:
        raise HTTPException(status_code=400, detail="action must be hold | release | set_due_days")
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": upd, "$push": {"control_log": entry}})
    await audit(user=user, action=f"vendor_bill_payment_{action}", resource="vendor_bills",
                record_id=bill_id, after={"bill_no": b["bill_no"], **entry},
                ip=request.client.host if request.client else "")
    if action == "release":
        await release_due_bills_to_queue()
    return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})


@router.get("/vendor-bills/{bill_id}/pdf")
async def vendor_bill_pdf(bill_id: str,
                          user: dict = Depends(require_permission("accounting", "read"))):
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    from pdf_generator import render_vendor_bill_pdf
    pdf = render_vendor_bill_pdf(b)
    from fastapi import Response
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{b.get("bill_no") or bill_id}.pdf"'})


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
    actor = user.get("name") or user.get("email")
    if b.get("workflow_version") == 2:
        st = b.get("status")
        if st == "draft":
            upd = {"status": "verified_l1", "verify_level": 1,
                   "verified_l1_by": actor, "verified_l1_at": now_iso()}
            action = "vendor_bill_verify_l1"
        elif st == "verified_l1":
            upd = {"status": "verified", "verify_level": 2,
                   "verified_by": actor, "verified_at": now_iso()}
            action = "vendor_bill_verify_l2"
        else:
            raise HTTPException(status_code=400, detail=f"Cannot verify bill in status {st}")
        await db.vendor_bills.update_one({"id": bill_id}, {"$set": upd})
        await audit(user=user, action=action, resource="vendor_bills",
                    record_id=bill_id, after={"bill_no": b["bill_no"]},
                    ip=request.client.host if request.client else "")
        return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if b.get("status") != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot verify bill in status {b.get('status')}")
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": {
        "status": "verified",
        "verified_by": actor,
        "verified_at": now_iso(),
    }})
    await audit(user=user, action="vendor_bill_verify", resource="vendor_bills",
                record_id=bill_id, after={"bill_no": b["bill_no"]},
                ip=request.client.host if request.client else "")
    return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})


# v3 workflow stage map: current status → (next status, stage label, allowed roles)
WF3_STAGES = {
    "draft": ("dept_approved", "Department Approval",
              {"purchase_officer", "project_manager", "dept_head", "manager_pnv", "manager_o_p",
               "manager_log", "general_manager", "super_admin"}),
    "dept_approved": ("accounts_approved", "Accounts Approval",
                      {"accounts_executive", "super_admin"}),
    "accounts_approved": ("admin_approved", "Admin Approval",
                          {"general_manager", "director", "super_admin"}),
    "admin_approved": ("approved", "Final Approval",
                       {"director", "super_admin"}),
}


@router.post("/vendor-bills/{bill_id}/approve")
async def approve_vendor_bill(bill_id: str, request: Request,
                              user: dict = Depends(get_current_user)):
    """Approve → auto-post JE (DR Expense + DR GST Input / CR AP + CR TDS Payable + CR Vendor Advance)."""
    b = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    actor = user.get("name") or user.get("email")
    role = user.get("role")
    wf3 = b.get("workflow_version") == 3
    wf2 = b.get("workflow_version") == 2

    if wf3:
        st = b.get("status")
        if st not in WF3_STAGES:
            raise HTTPException(status_code=400, detail=f"Cannot approve bill in status {st}")
        next_status, stage_label, roles = WF3_STAGES[st]
        if role not in roles:
            raise HTTPException(status_code=403,
                                detail=f"{stage_label} requires one of: {', '.join(sorted(roles))} (you are {role})")
        log_entry = {"stage": stage_label, "from": st, "to": next_status,
                     "by": actor, "role": role, "at": now_iso()}
        if next_status != "approved":
            await db.vendor_bills.update_one({"id": bill_id}, {
                "$set": {"status": next_status},
                "$push": {"workflow_log": log_entry}})
            await audit(user=user, action=f"vendor_bill_{next_status}", resource="vendor_bills",
                        record_id=bill_id, after={"bill_no": b["bill_no"], "stage": stage_label},
                        ip=request.client.host if request.client else "")
            return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
        # Final approval falls through to JE posting below
        await db.vendor_bills.update_one({"id": bill_id}, {"$push": {"workflow_log": log_entry}})
    elif wf2:
        if b.get("status") not in ("verified", "approved_l1"):
            raise HTTPException(status_code=400,
                                detail=f"Cannot approve bill in status {b.get('status')} — complete 2-level verification first")
        if role not in ("accounts_executive", "general_manager", "director", "super_admin"):
            raise HTTPException(status_code=403, detail="Approval requires accounts/admin role")
        if b.get("status") == "verified":
            # Approval Level 1 — no JE yet
            await db.vendor_bills.update_one({"id": bill_id}, {"$set": {
                "status": "approved_l1", "approve_level": 1,
                "approved_l1_by": actor, "approved_l1_at": now_iso()}})
            await audit(user=user, action="vendor_bill_approve_l1", resource="vendor_bills",
                        record_id=bill_id, after={"bill_no": b["bill_no"]},
                        ip=request.client.host if request.client else "")
            return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    else:
        if b.get("status") not in ("draft", "verified"):
            raise HTTPException(status_code=400, detail=f"Cannot approve bill in status {b.get('status')}")
        if role not in ("accounts_executive", "general_manager", "director", "super_admin"):
            raise HTTPException(status_code=403, detail="Approval requires accounts/admin role")

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

    upd = {
        "status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "je_id": je["id"] if je else None,
        "je_voucher_number": (je or {}).get("voucher_number"),
    }
    if wf2 or wf3:
        # Due days count from FINAL APPROVAL date; bill becomes payment-eligible only on/after due date
        dd = int(b.get("due_days") or 30)
        release = (datetime.now(timezone.utc).date() + timedelta(days=dd)).isoformat()
        upd.update({"approve_level": 2, "due_date": release, "payment_release_date": release})
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": upd})
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
    if not (wf2 or wf3):
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
        net_b = round(float((b.get("totals") or {}).get("net_payable") or b.get("amount") or 0), 2)
        await db.vendor_bills.update_one({"id": b["id"]}, {"$inc": {
            "paid_amount": apply_amt,
        }, "$set": {
            "outstanding": new_outs,
            "status": "paid" if new_outs < 0.01 else "partially_paid",
            "payment_status": _payment_status(round(float(b.get("paid_amount") or 0) + apply_amt, 2),
                                              net_b, b.get("status") or "approved"),
            "last_payment_at": payload.payment_date,
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
async def list_vendor_payments(request: Request, vendor_id: Optional[str] = None,
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
    paged = await maybe_paged(request, "vendor_payments", q, "payment_date",
                              ["payment_no", "vendor_name", "utr_no", "reference", "mode", "status", "bill_no"])
    if paged:
        return paged
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


# ═══════════════════════════════════════════════════════════════════════════
# Direct Cost Booking — historical / pre-ERP expenses (PO & GRN done outside ERP)
# ═══════════════════════════════════════════════════════════════════════════
DIRECT_CATEGORIES = ("material", "labour", "transport", "subcontract", "service", "other")


class DirectBookingIn(BaseModel):
    vendor_name: str
    invoice_no: str
    invoice_date: str                       # actual (past) bill date YYYY-MM-DD
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    expense_category: str = "other"
    taxable_value: float
    gst_amount: float = 0.0
    tds_amount: float = 0.0
    remarks: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


async def _resolve_direct_project(project_id: Optional[str], project_code: Optional[str]) -> Dict[str, Any]:
    q = {"$or": [{"id": project_id or ""}, {"code": project_code or ""},
                 {"project_code": project_code or ""}]}
    proj = await db.projects.find_one(q, {"_id": 0, "id": 1, "code": 1, "project_code": 1, "name": 1})
    if not proj:
        raise HTTPException(status_code=400,
                            detail=f"Project '{project_code or project_id}' not found — project is mandatory for direct cost booking")
    return proj


async def _insert_direct_booking(data: DirectBookingIn, user: dict) -> Dict[str, Any]:
    if not (data.vendor_name or "").strip():
        raise HTTPException(status_code=400, detail="Vendor name is required")
    if not (data.invoice_no or "").strip():
        raise HTTPException(status_code=400, detail="Bill/invoice number is required")
    if float(data.taxable_value or 0) <= 0:
        raise HTTPException(status_code=400, detail="Basic amount must be greater than zero")
    if data.expense_category not in DIRECT_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"expense_category must be one of {DIRECT_CATEGORIES}")
    try:
        datetime.fromisoformat(data.invoice_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid bill date '{data.invoice_date}' — use YYYY-MM-DD")
    proj = await _resolve_direct_project(data.project_id, data.project_code)
    dup = await db.vendor_bills.find_one({"vendor_name": data.vendor_name.strip(), "invoice_no": data.invoice_no.strip(),
                                          "status": {"$nin": ["cancelled", "rejected"]}}, {"_id": 0, "bill_no": 1})
    if dup:
        raise HTTPException(status_code=400,
                            detail=f"Duplicate: invoice {data.invoice_no} for {data.vendor_name} already booked ({dup['bill_no']})")
    basic = round(float(data.taxable_value), 2)
    gst = round(float(data.gst_amount or 0), 2)
    tds = round(float(data.tds_amount or 0), 2)
    gross = round(basic + gst, 2)
    net = round(gross - tds, 2)
    doc = {
        "id": new_id(),
        "bill_no": await next_sequence("DCB"),
        "bill_type": "direct_booking", "is_historical": True, "workflow_version": "direct",
        "vendor_name": data.vendor_name.strip(),
        "invoice_no": data.invoice_no.strip(), "invoice_date": data.invoice_date,
        "project_id": proj["id"], "project_code": proj.get("code") or proj.get("project_code"),
        "project_name": proj.get("name"),
        "expense_category": data.expense_category,
        "taxable_value": basic, "amount": gross, "total": gross,
        "tax_amount": gst, "gst_amount": gst, "tds_amount": tds,
        "totals": {"taxable": basic, "gst": gst, "tds": tds, "gross": gross, "net_payable": net},
        "paid_amount": gross, "outstanding": 0.0,   # historical bills were already settled pre-ERP
        "status": "posted",
        "notes": data.remarks or "Direct cost booking — PO/GRN completed before ERP implementation",
        "attachments": data.attachments or [],
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
    }
    await db.vendor_bills.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/vendor-bills/direct")
async def create_direct_booking(payload: DirectBookingIn, request: Request,
                                user: dict = Depends(require_permission("accounting", "write"))):
    doc = await _insert_direct_booking(payload, user)
    await audit(user=user, action="direct_cost_booking", resource="vendor_bills", record_id=doc["id"],
                after={"bill_no": doc["bill_no"], "vendor": doc["vendor_name"], "project": doc["project_code"],
                       "gross": doc["amount"]}, ip=request.client.host if request.client else None)
    return doc


_DIRECT_HEADERS = ["Vendor Name", "Bill Number", "Bill Date (YYYY-MM-DD)", "Project Code",
                   "Expense Category (material/labour/transport/subcontract/service/other)",
                   "Basic Amount", "GST Amount", "TDS Amount", "Remarks"]


@router.get("/vendor-bills/direct/template")
async def direct_booking_template(user: dict = Depends(require_permission("accounting", "read"))):
    from openpyxl import Workbook
    from io import BytesIO
    from fastapi import Response
    wb = Workbook()
    ws = wb.active
    ws.title = "Direct Bookings"
    ws.append(_DIRECT_HEADERS)
    ws.append(["ABC Transport Co", "INV-1041", "2025-11-14", "PRJ-2026-0049", "transport", 50000, 9000, 1000,
               "Opening cost booking — pre-ERP"])
    for col in "ABCDEFGHI":
        ws.column_dimensions[col].width = 24
    buf = BytesIO()
    wb.save(buf)
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=direct_cost_booking_template.xlsx"})


@router.post("/vendor-bills/direct/import")
async def import_direct_bookings(request: Request, file: UploadFile = File(...),
                                 user: dict = Depends(require_permission("accounting", "write"))):
    from openpyxl import load_workbook
    from io import BytesIO
    try:
        wb = load_workbook(BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read file — upload the .xlsx template")
    ws = wb.active
    inserted, errors = [], []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or all(c in (None, "") for c in row):
            continue
        vals = list(row) + [None] * (9 - len(row))

        def _s(x):
            return str(x).strip() if x is not None else ""
        bill_date = vals[2]
        if hasattr(bill_date, "date"):
            bill_date = bill_date.date().isoformat()
        try:
            data = DirectBookingIn(
                vendor_name=_s(vals[0]), invoice_no=_s(vals[1]), invoice_date=_s(bill_date),
                project_code=_s(vals[3]), expense_category=_s(vals[4]).lower() or "other",
                taxable_value=float(vals[5] or 0), gst_amount=float(vals[6] or 0),
                tds_amount=float(vals[7] or 0), remarks=_s(vals[8]) or None)
            doc = await _insert_direct_booking(data, user)
            inserted.append(doc["bill_no"])
        except HTTPException as e:
            errors.append({"row": i, "error": e.detail})
        except Exception as e:
            errors.append({"row": i, "error": str(e)})
    await audit(user=user, action="direct_cost_booking_import", resource="vendor_bills", record_id="bulk",
                after={"inserted": len(inserted), "errors": len(errors)},
                ip=request.client.host if request.client else None)
    return {"inserted": len(inserted), "bill_nos": inserted, "errors": errors}
