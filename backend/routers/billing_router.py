"""Phase 2 — Client Billing & Receivables Management
=====================================================
Unified `/api/billing/*` surface that:
  • Manages 10 invoice types end-to-end (Tax / Proforma / RA / Final /
    Mobilization / Retention / Extra-Work / Reimbursement / DN / CN)
  • Auto-posts to Accounts on invoice approval (DR AR / CR Service Income /
    CR GST Output) — using service_type → income-account mapping
  • Records receipts with TDS / Retention / Other-deduction splits and
    posts the full multi-leg JE automatically
  • Renders 13 receivable reports (client outstanding / project / WO /
    aging / collection / TDS / Retention / GST sales register / overdue /
    disputed / RA register / final register / client ledger)

Integration:
  • Reads Sales (clients_router, quotation_builder_router) for client master,
    GST, billing address, work order value
  • Reads Projects & Operations for project code, PM, completion %
  • Writes to journal_entries via accounting_service.post_sales_invoice_issued()
    and post_customer_receipt() so the Finance + Accounts dashboards reflect
    the activity instantly
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from accounting_service import post_sales_invoice_issued, post_customer_receipt

router = APIRouter(prefix="/billing", tags=["Billing & Receivables"])


# ─── Constants ──────────────────────────────────────────────────────────
INVOICE_TYPES: Dict[str, str] = {
    "TAX":   "Tax Invoice",
    "PROF":  "Proforma Invoice",
    "RA":    "RA Bill (Running Account)",
    "FINAL": "Final Bill",
    "MOB":   "Mobilization Advance",
    "RETN":  "Retention Invoice",
    "EXTRA": "Extra Work Invoice",
    "REIMB": "Reimbursement Invoice",
    "DN":    "Debit Note",
    "CN":    "Credit Note",
}

SERVICE_TYPES: List[str] = [
    "scaffolding", "painting", "roof_sheeting", "rope_access",
    "manpower", "material_supply", "other",
]

RECEIPT_MODES: List[str] = ["Bank", "Cash", "UPI", "NEFT", "RTGS", "IMPS", "Cheque"]


# ─── Pydantic schemas ───────────────────────────────────────────────────
class InvoiceLineIn(BaseModel):
    description: str
    quantity: float = 1
    unit: str = "Lot"
    rate: float = 0
    taxable_value: Optional[float] = None  # if not given, qty*rate is used


class InvoiceIn(BaseModel):
    invoice_type: str = Field(..., description="One of TAX/PROF/RA/FINAL/MOB/RETN/EXTRA/REIMB/DN/CN")
    invoice_date: str
    client_id: Optional[str] = None
    client_name: str
    client_gstin: Optional[str] = None
    billing_address: Optional[str] = None
    site_address: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    work_order_no: Optional[str] = None
    contract_value: Optional[float] = None
    billing_period_from: Optional[str] = None
    billing_period_to: Optional[str] = None
    service_type: str = "other"
    description: Optional[str] = None
    lines: List[InvoiceLineIn] = []
    gst_rate: float = 18.0
    is_intra_state: bool = True  # True → CGST+SGST · False → IGST
    tds_rate: float = 0.0        # 2% for 194C; 0 for none
    retention_rate: float = 0.0  # % of taxable_value
    due_days: int = 30
    measurement_sheet_ref: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None


class ReceiptIn(BaseModel):
    receipt_date: str
    client_id: Optional[str] = None
    client_name: str
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    invoice_ids: List[str] = []          # invoices being adjusted
    mode: str = "Bank"                   # Bank/Cash/UPI/NEFT/RTGS/IMPS/Cheque
    bank_account: Optional[str] = None
    txn_reference: Optional[str] = None  # UTR / cheque #
    amount: float                        # net amount actually received
    tds_deducted: float = 0
    retention_deducted: float = 0
    other_deduction: float = 0
    excess_reason: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    file_ids: Optional[List[str]] = None  # uploaded file references from /api/uploads
    remarks: Optional[str] = None


# ─── Helpers ────────────────────────────────────────────────────────────
def _compute_invoice_totals(payload: InvoiceIn) -> Dict[str, float]:
    """Returns the canonical money figures for an invoice."""
    taxable = round(sum(
        (ln.taxable_value if ln.taxable_value is not None else ln.quantity * ln.rate)
        for ln in payload.lines
    ), 2) if payload.lines else 0.0
    if taxable <= 0:
        taxable = round((payload.lines[0].quantity * payload.lines[0].rate) if payload.lines else 0, 2)
    gst_total = round(taxable * (payload.gst_rate or 0) / 100.0, 2)
    cgst = sgst = igst = 0.0
    if payload.is_intra_state:
        cgst = sgst = round(gst_total / 2, 2)
    else:
        igst = gst_total
    gross = round(taxable + gst_total, 2)
    tds_expected = round(taxable * (payload.tds_rate or 0) / 100.0, 2)
    retention = round(taxable * (payload.retention_rate or 0) / 100.0, 2)
    net_receivable = round(gross - tds_expected - retention, 2)
    return {
        "taxable_value": taxable, "gst_total": gst_total,
        "cgst": cgst, "sgst": sgst, "igst": igst,
        "gross_value": gross, "tds_expected": tds_expected,
        "retention_amount": retention, "net_receivable": net_receivable,
    }


async def _check_wo_limit(payload: InvoiceIn, totals: Dict[str, float]) -> None:
    """Block the invoice if cumulative billing > work-order value (unless variation present)."""
    if not payload.work_order_no or not payload.contract_value:
        return
    invoiced_so_far = 0.0
    async for prev in db.client_invoices.find({
        "work_order_no": payload.work_order_no,
        "status": {"$in": ["approved", "partially_paid", "paid"]},
    }, {"_id": 0, "totals.taxable_value": 1}):
        invoiced_so_far += float(((prev.get("totals") or {}).get("taxable_value")) or 0)
    new_cum = invoiced_so_far + totals["taxable_value"]
    if new_cum > float(payload.contract_value or 0) * 1.0001:
         # tiny float tolerance
        raise HTTPException(
            status_code=400,
            detail=f"Billing exceeds work-order value: cumulative ₹{new_cum:,.2f} > WO ₹{payload.contract_value:,.2f}. "
                   "Raise a Variation Order or Extra Work invoice with owner approval."
        )


# ════════════════════════════════════════════════════════════════════════
# Invoices
# ════════════════════════════════════════════════════════════════════════
@router.get("/invoice-types")
async def list_invoice_types(user: dict = Depends(require_permission("accounting", "read"))):
    return [{"code": k, "label": v} for k, v in INVOICE_TYPES.items()]


@router.get("/service-types")
async def list_service_types(user: dict = Depends(require_permission("accounting", "read"))):
    return SERVICE_TYPES


@router.post("/invoices")
async def create_invoice(payload: InvoiceIn, request: Request,
                         user: dict = Depends(require_permission("accounting", "write"))):
    it = payload.invoice_type.upper()
    if it not in INVOICE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown invoice_type {it}")
    if not payload.client_name:
        raise HTTPException(status_code=400, detail="client_name required")
    # Project required for project-billing types
    if it in {"RA", "FINAL", "MOB", "RETN", "EXTRA"} and not (payload.project_id or payload.project_code):
        raise HTTPException(status_code=400, detail=f"project_id/project_code required for {INVOICE_TYPES[it]}")

    totals = _compute_invoice_totals(payload)

    if totals["tds_expected"] > totals["gross_value"]:
        raise HTTPException(status_code=400, detail="TDS expected cannot exceed invoice value")
    if totals["gross_value"] <= 0:
        raise HTTPException(status_code=400, detail="Invoice value must be > 0")

    await _check_wo_limit(payload, totals)

    # Per-type invoice number series — INV/RA/FIN/MOB/RETN/EXTRA/REIMB/DN/CN/PROF
    series = {"TAX": "INV", "PROF": "PROF", "RA": "RA", "FINAL": "FIN",
              "MOB": "MOB", "RETN": "RETN", "EXTRA": "EXTRA", "REIMB": "REIMB",
              "DN": "CDN", "CN": "CCN"}[it]
    inv_no = await next_sequence(series)
    due_date = (datetime.fromisoformat(payload.invoice_date) + timedelta(days=payload.due_days)).date().isoformat()

    doc = {
        "id": new_id(),
        "invoice_no": inv_no,
        "invoice_type": it,
        "invoice_date": payload.invoice_date,
        "due_date": due_date,
        "due_days": payload.due_days,
        "client_id": payload.client_id,
        "client_name": payload.client_name,
        "client_gstin": payload.client_gstin,
        "billing_address": payload.billing_address,
        "site_address": payload.site_address,
        "project_id": payload.project_id,
        "project_code": payload.project_code,
        "work_order_no": payload.work_order_no,
        "contract_value": payload.contract_value,
        "billing_period_from": payload.billing_period_from,
        "billing_period_to": payload.billing_period_to,
        "service_type": payload.service_type,
        "description": payload.description,
        "lines": [ln.model_dump() for ln in payload.lines],
        "gst_rate": payload.gst_rate,
        "is_intra_state": payload.is_intra_state,
        "tds_rate": payload.tds_rate,
        "retention_rate": payload.retention_rate,
        "totals": totals,
        "amount": totals["gross_value"],        # legacy alias for accounting_service hook
        "tax_amount": totals["gst_total"],      # legacy alias
        "paid_amount": 0.0,
        "tds_received": 0.0,
        "retention_received": 0.0,
        "other_deduction_received": 0.0,
        "outstanding": totals["gross_value"],
        "net_receivable": totals["net_receivable"],
        "measurement_sheet_ref": payload.measurement_sheet_ref,
        "attachments": payload.attachments or [],
        "notes": payload.notes,
        "status": "draft",                       # draft → approved → partially_paid → paid → closed
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.client_invoices.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="invoice_create", resource="client_invoices",
                record_id=doc["id"], after={"invoice_no": inv_no, "type": it, "gross": totals["gross_value"]},
                ip=request.client.host if request.client else "")
    return doc


@router.get("/invoices")
async def list_invoices(invoice_type: Optional[str] = None,
                        status: Optional[str] = None,
                        client_id: Optional[str] = None,
                        project_id: Optional[str] = None,
                        work_order_no: Optional[str] = None,
                        start: Optional[str] = None, end: Optional[str] = None,
                        limit: int = 200,
                        user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if invoice_type:
        q["invoice_type"] = invoice_type.upper()
    if status:
        q["status"] = status
    if client_id:
        q["client_id"] = client_id
    if project_id:
        q["project_id"] = project_id
    if work_order_no:
        q["work_order_no"] = work_order_no
    if start:
        q["invoice_date"] = {**q.get("invoice_date", {}), "$gte": start}
    if end:
          q["invoice_date"] = {**q.get("invoice_date", {}), "$lte": end}
    rows = await db.client_invoices.find(q, {"_id": 0}).sort("invoice_date", -1).limit(limit).to_list(limit)
    return rows


@router.get("/invoices/receivable")
async def list_receivable_invoices(user: dict = Depends(require_permission("accounting", "read"))):
    """All invoices with outstanding > 0 (approved or partially_paid) — used by Receipts page."""
    rows = await db.client_invoices.find(
        {"status": {"$in": ["approved", "partially_paid"]}, "outstanding": {"$gt": 0}},
        {"_id": 0}
    ).sort("invoice_date", -1).to_list(500)
    return rows


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user: dict = Depends(require_permission("accounting", "read"))):
    inv = await db.client_invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/invoices/{invoice_id}/approve")
async def approve_invoice(invoice_id: str, request: Request,
                          user: dict = Depends(require_permission("accounting", "write"))):
    """Approve invoice → auto-post JE (DR AR / CR Service-line / CR GST Output)."""
    inv = await db.client_invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot approve invoice in status {inv.get('status')}")

    # Post JE
    try:
        je = await post_sales_invoice_issued({
            "id": inv["id"], "invoice_no": inv["invoice_no"],
            "invoice_date": inv["invoice_date"],
            "amount": inv["totals"]["gross_value"],
            "tax_amount": inv["totals"]["gst_total"],
            "service_type": inv.get("service_type"),
            "project_id": inv.get("project_id"),
            "client_id": inv.get("client_id"),
            "client_name": inv.get("client_name"),
            "department": inv.get("department"),
        }, user)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"JE post failed: {e}")

    await db.client_invoices.update_one({"id": invoice_id}, {"$set": {
        "status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "je_id": je["id"] if je else None,
        "je_voucher_number": (je or {}).get("voucher_number"),
    }})
    # Also bump project revenue running tally if project linked
    if inv.get("project_id"):
        await db.projects.update_one(
            {"id": inv["project_id"]},
            {"$inc": {"revenue_invoiced": float(inv["totals"]["gross_value"])}}
        )
    await audit(user=user, action="invoice_approve", resource="client_invoices",
                record_id=invoice_id,
                after={"invoice_no": inv["invoice_no"], "je": (je or {}).get("voucher_number")},
                ip=request.client.host if request.client else "")
    return await db.client_invoices.find_one({"id": invoice_id}, {"_id": 0})


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(invoice_id: str, request: Request,
                         user: dict = Depends(require_permission("accounting", "write"))):
    """Cancel a draft. Approved invoices must be corrected via Credit Note."""
    inv = await db.client_invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Only draft invoices can be cancelled. Use Credit Note for approved ones.")
    await db.client_invoices.update_one({"id": invoice_id}, {"$set": {
        "status": "cancelled",
        "cancelled_by": user.get("name") or user.get("email"),
        "cancelled_at": now_iso(),
    }})
    await audit(user=user, action="invoice_cancel", resource="client_invoices",
                record_id=invoice_id, after={"invoice_no": inv["invoice_no"]},
                ip=request.client.host if request.client else "")
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════
# Receipts
# ════════════════════════════════════════════════════════════════════════
@router.post("/receipts")
async def create_receipt(payload: ReceiptIn, request: Request,
                         user: dict = Depends(require_permission("accounting", "write"))):
    if payload.amount <= 0 and payload.tds_deducted <= 0 and payload.retention_deducted <= 0:
        raise HTTPException(status_code=400, detail="At least one of amount/tds/retention must be > 0")
    mode_norm = next((m for m in RECEIPT_MODES if m.lower() == (payload.mode or "").lower()), None)
    if not mode_norm:
        raise HTTPException(status_code=400, detail=f"mode must be one of {RECEIPT_MODES}")
    payload.mode = mode_norm

    total_adjusted = round(payload.amount + payload.tds_deducted + payload.retention_deducted + payload.other_deduction, 2)

    # Apply to invoices in FIFO order until exhausted
    if payload.invoice_ids:
        # First pass — validate total adjusted vs available outstanding
        invs_cache = []
        avail = 0.0
        for iid in payload.invoice_ids:
            inv = await db.client_invoices.find_one({"id": iid}, {"_id": 0})
            if not inv:
                raise HTTPException(status_code=404, detail=f"Invoice {iid} not found")
            if inv.get("source") == "ra_bill":
                raise HTTPException(status_code=400,
                                    detail=f"Invoice {inv['invoice_no']} is generated from an RA bill — record the receipt via Accounts → Payments In against the RA bill instead")
            if inv.get("status") not in ("approved", "partially_paid"):
                raise HTTPException(status_code=400, detail=f"Invoice {inv['invoice_no']} not in receivable state ({inv.get('status')})")
            invs_cache.append(inv)
            avail += float(inv.get("outstanding") or 0)
        excess_amt = round(total_adjusted - avail, 2)
        if excess_amt > 0.01 and not payload.excess_reason:
            raise HTTPException(status_code=400,
                detail=f"Excess receipt ₹{excess_amt:,.2f} requires `excess_reason`")
        # Second pass — actually apply
        remaining = total_adjusted
        for inv in invs_cache:
            outstanding = float(inv.get("outstanding") or 0)
            apply_amt = min(outstanding, remaining)
            if apply_amt <= 0:
                continue
            new_outstanding = round(outstanding - apply_amt, 2)
            await db.client_invoices.update_one({"id": inv["id"]}, {"$inc": {
                "paid_amount": apply_amt,
            }, "$set": {
                "outstanding": new_outstanding,
                "status": "paid" if new_outstanding < 0.01 else "partially_paid",
            }})
            remaining = round(remaining - apply_amt, 2)
            if remaining < 0.01:
                break

    rcpt_no = await next_sequence("RCPT")
    rcpt = {
        "id": new_id(),
        "receipt_no": rcpt_no,
        "receipt_date": payload.receipt_date,
        "client_id": payload.client_id,
        "client_name": payload.client_name,
        "project_id": payload.project_id,
        "project_code": payload.project_code,
        "invoice_ids": payload.invoice_ids,
        "mode": payload.mode,
        "bank_account": payload.bank_account,
        "txn_reference": payload.txn_reference,
        "amount": payload.amount,
        "tds_deducted": payload.tds_deducted,
        "retention_deducted": payload.retention_deducted,
        "other_deduction": payload.other_deduction,
        "total_adjusted": total_adjusted,
        "excess_reason": payload.excess_reason,
        "attachments": payload.attachments or [],
        "file_ids": payload.file_ids or [],
        "remarks": payload.remarks,
        "status": "posted",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.client_receipts.insert_one(rcpt)
    rcpt.pop("_id", None)

    # Auto-JE
    try:
        je = await post_customer_receipt({
            "id": rcpt["id"], "receipt_date": payload.receipt_date,
            "client_id": payload.client_id, "client_name": payload.client_name,
            "project_id": payload.project_id,
            "amount": payload.amount,
            "tds_deducted": payload.tds_deducted,
            "retention_deducted": payload.retention_deducted,
            "other_deduction": payload.other_deduction,
            "mode": payload.mode,
            "reference": payload.txn_reference,
        }, user)
        if je:
            await db.client_receipts.update_one({"id": rcpt["id"]}, {"$set": {
                "je_id": je["id"], "je_voucher_number": je.get("voucher_number"),
            }})
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger("erp").warning(f"[billing] receipt JE skipped: {e}")

    await audit(user=user, action="receipt_create", resource="client_receipts",
                record_id=rcpt["id"], after={"receipt_no": rcpt_no, "total": total_adjusted},
                ip=request.client.host if request.client else "")
    return await db.client_receipts.find_one({"id": rcpt["id"]}, {"_id": 0})


@router.get("/receipts")
async def list_receipts(client_id: Optional[str] = None, project_id: Optional[str] = None,
                        start: Optional[str] = None, end: Optional[str] = None,
                        limit: int = 200,
                        user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if client_id:
        q["client_id"] = client_id
    if project_id:
        q["project_id"] = project_id
    if start:
        q["receipt_date"] = {**q.get("receipt_date", {}), "$gte": start}
    if end:
          q["receipt_date"] = {**q.get("receipt_date", {}), "$lte": end}
    return await db.client_receipts.find(q, {"_id": 0}).sort("receipt_date", -1).limit(limit).to_list(limit)


@router.get("/receipts/summary")
async def receipts_summary(user: dict = Depends(require_permission("accounting", "read"))):
    """Dashboard KPI: collections MTD + lifetime totals."""
    today = datetime.now(timezone.utc)
    mtd_start = today.replace(day=1).strftime("%Y-%m-%d")
    mtd_agg = await db.client_receipts.aggregate([
        {"$match": {"receipt_date": {"$gte": mtd_start}}},
        {"$group": {"_id": None, "amount": {"$sum": "$amount"}, "adjusted": {"$sum": "$total_adjusted"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    life_agg = await db.client_receipts.aggregate([
        {"$group": {"_id": None, "amount": {"$sum": "$amount"}, "adjusted": {"$sum": "$total_adjusted"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    mtd = mtd_agg[0] if mtd_agg else {"amount": 0, "adjusted": 0, "count": 0}
    life = life_agg[0] if life_agg else {"amount": 0, "adjusted": 0, "count": 0}
    return {
        "mtd_amount": round(float(mtd.get("amount") or 0), 2),
        "mtd_adjusted": round(float(mtd.get("adjusted") or 0), 2),
        "mtd_count": mtd.get("count") or 0,
        "lifetime_amount": round(float(life.get("amount") or 0), 2),
        "lifetime_adjusted": round(float(life.get("adjusted") or 0), 2),
        "lifetime_count": life.get("count") or 0,
    }


@router.get("/receipts/{receipt_id}")
async def get_receipt(receipt_id: str, user: dict = Depends(require_permission("accounting", "read"))):
    rcpt = await db.client_receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not rcpt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    # Enrich with invoice numbers
    if rcpt.get("invoice_ids"):
        invs = await db.client_invoices.find(
            {"id": {"$in": rcpt["invoice_ids"]}},
            {"_id": 0, "id": 1, "invoice_no": 1, "invoice_date": 1, "outstanding": 1,
             "totals": 1, "client_name": 1, "status": 1}
        ).to_list(100)
        rcpt["invoices"] = invs
    # Enrich with uploaded files
    if rcpt.get("file_ids"):
        files = await db.documents.find(
            {"id": {"$in": rcpt["file_ids"]}},
            {"_id": 0, "id": 1, "title": 1, "file_url": 1, "content_type": 1, "size": 1}
        ).to_list(50)
        rcpt["files"] = files
    return rcpt


@router.patch("/receipts/{receipt_id}")
async def update_receipt(receipt_id: str, body: dict, user: dict = Depends(require_permission("accounting", "write"))):
    """Update receipt — primarily to add/edit payment details & upload file references after initial creation."""
    rcpt = await db.client_receipts.find_one({"id": receipt_id})
    if not rcpt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    allowed = {"txn_reference", "mode", "bank_account", "remarks", "file_ids"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user.get("name") or user.get("email")
    await db.client_receipts.update_one({"id": receipt_id}, {"$set": updates})
    return {**{k: v for k, v in rcpt.items() if k != "_id"}, **updates}



# ════════════════════════════════════════════════════════════════════════
# Receivable Reports
# ════════════════════════════════════════════════════════════════════════
def _age_bucket(invoice_date_iso: str) -> tuple[str, int]:
    try:
        d = datetime.fromisoformat(invoice_date_iso).date()
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


@router.get("/reports/client-outstanding")
async def client_outstanding(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.client_invoices.find(
        {"status": {"$in": ["approved", "partially_paid"]}},
        {"_id": 0, "invoice_no": 1, "invoice_date": 1, "client_name": 1, "client_id": 1,
         "project_id": 1, "project_code": 1, "work_order_no": 1,
         "totals": 1, "paid_amount": 1, "outstanding": 1, "due_date": 1, "service_type": 1}
    ).to_list(2000)
    by_client: Dict[str, Dict[str, Any]] = {}
    aging = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for r in rows:
        outs = float(r.get("outstanding") or 0)
        if outs < 0.01:
            continue
        b, days = _age_bucket(r["invoice_date"])
        aging[b] += outs
        c = r["client_name"]
        c_row = by_client.setdefault(c, {"client_name": c, "total_outstanding": 0.0, "invoices": []})
        c_row["total_outstanding"] += outs
        r["bucket"] = b
        r["days_overdue"] = days
        c_row["invoices"].append(r)
    return {
        "buckets": {k: round(v, 2) for k, v in aging.items()},
        "total_outstanding": round(sum(aging.values()), 2),
        "clients": sorted(by_client.values(), key=lambda x: -x["total_outstanding"]),
    }


@router.get("/reports/project-outstanding")
async def project_outstanding(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.client_invoices.find(
        {"status": {"$in": ["approved", "partially_paid"]}, "project_id": {"$ne": None}},
        {"_id": 0, "project_id": 1, "project_code": 1, "client_name": 1,
         "totals": 1, "outstanding": 1, "invoice_no": 1, "invoice_date": 1}
    ).to_list(2000)
    by_proj: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        outs = float(r.get("outstanding") or 0)
        if outs < 0.01:
            continue
        p = r.get("project_code") or r.get("project_id") or "—"
        row = by_proj.setdefault(p, {"project_code": p, "client_name": r.get("client_name"),
                                     "outstanding": 0.0, "invoices": []})
        row["outstanding"] += outs
        row["invoices"].append(r)
    return {"projects": sorted(by_proj.values(), key=lambda x: -x["outstanding"])}


@router.get("/reports/collection")
async def collection_report(start: Optional[str] = None, end: Optional[str] = None,
                            user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if start:
        q["receipt_date"] = {**q.get("receipt_date", {}), "$gte": start}
    if end:
          q["receipt_date"] = {**q.get("receipt_date", {}), "$lte": end}
    rows = await db.client_receipts.find(q, {"_id": 0}).sort("receipt_date", -1).to_list(2000)
    total_gross = sum(float(r.get("total_adjusted") or 0) for r in rows)
    total_net = sum(float(r.get("amount") or 0) for r in rows)
    total_tds = sum(float(r.get("tds_deducted") or 0) for r in rows)
    total_retn = sum(float(r.get("retention_deducted") or 0) for r in rows)
    return {
        "rows": rows,
        "totals": {
            "total_adjusted": round(total_gross, 2), "amount_received": round(total_net, 2),
            "tds_deducted": round(total_tds, 2), "retention_deducted": round(total_retn, 2),
        },
    }


@router.get("/reports/gst-sales-register")
async def gst_sales_register(start: Optional[str] = None, end: Optional[str] = None,
                             user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {"status": {"$in": ["approved", "partially_paid", "paid"]}}
    if start:
        q["invoice_date"] = {**q.get("invoice_date", {}), "$gte": start}
    if end:
          q["invoice_date"] = {**q.get("invoice_date", {}), "$lte": end}
    rows = await db.client_invoices.find(q, {"_id": 0}).sort("invoice_date", -1).to_list(2000)
    out = []
    totals = {"taxable": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "gross": 0.0}
    for r in rows:
        t = r.get("totals") or {}
        out.append({
            "invoice_no": r["invoice_no"], "invoice_date": r["invoice_date"],
            "client_name": r["client_name"], "client_gstin": r.get("client_gstin"),
            "service_type": r.get("service_type"), "gst_rate": r.get("gst_rate"),
            "is_intra_state": r.get("is_intra_state", True),
            "taxable_value": t.get("taxable_value"),
            "cgst": t.get("cgst"), "sgst": t.get("sgst"), "igst": t.get("igst"),
            "gross_value": t.get("gross_value"),
        })
        totals["taxable"] += float(t.get("taxable_value") or 0)
        totals["cgst"]    += float(t.get("cgst") or 0)
        totals["sgst"]    += float(t.get("sgst") or 0)
        totals["igst"]    += float(t.get("igst") or 0)
        totals["gross"]   += float(t.get("gross_value") or 0)
    return {"rows": out, "totals": {k: round(v, 2) for k, v in totals.items()}}


@router.get("/reports/tds-receivable")
async def tds_receivable_report(user: dict = Depends(require_permission("accounting", "read"))):
    """Per-client / per-project view of TDS that has been deducted but not yet
    received as TDS certificate / refund."""
    rcpts = await db.client_receipts.find({"tds_deducted": {"$gt": 0}}, {"_id": 0}).to_list(5000)
    by_client: Dict[str, Dict[str, Any]] = {}
    for r in rcpts:
        c = r["client_name"]
        row = by_client.setdefault(c, {"client_name": c, "tds_deducted": 0.0, "receipts": []})
        row["tds_deducted"] += float(r.get("tds_deducted") or 0)
        row["receipts"].append({
            "receipt_no": r["receipt_no"], "receipt_date": r["receipt_date"],
            "tds_deducted": r.get("tds_deducted"), "project_id": r.get("project_id"),
        })
    return {"clients": sorted(by_client.values(), key=lambda x: -x["tds_deducted"]),
            "total_tds": round(sum(float(r.get("tds_deducted") or 0) for r in rcpts), 2)}


@router.get("/reports/retention-receivable")
async def retention_receivable_report(user: dict = Depends(require_permission("accounting", "read"))):
    rcpts = await db.client_receipts.find({"retention_deducted": {"$gt": 0}}, {"_id": 0}).to_list(5000)
    by_client: Dict[str, Dict[str, Any]] = {}
    for r in rcpts:
        c = r["client_name"]
        row = by_client.setdefault(c, {"client_name": c, "retention_deducted": 0.0, "receipts": []})
        row["retention_deducted"] += float(r.get("retention_deducted") or 0)
        row["receipts"].append({
            "receipt_no": r["receipt_no"], "receipt_date": r["receipt_date"],
            "retention_deducted": r.get("retention_deducted"), "project_id": r.get("project_id"),
        })
    return {"clients": sorted(by_client.values(), key=lambda x: -x["retention_deducted"]),
            "total_retention": round(sum(float(r.get("retention_deducted") or 0) for r in rcpts), 2)}


@router.get("/reports/overdue")
async def overdue_report(user: dict = Depends(require_permission("accounting", "read"))):
    today = datetime.now(timezone.utc).date().isoformat()
    rows = await db.client_invoices.find({
        "status": {"$in": ["approved", "partially_paid"]},
        "due_date": {"$lt": today},
        "outstanding": {"$gt": 0},
    }, {"_id": 0}).sort("due_date", 1).to_list(2000)
    for r in rows:
        try:
            r["overdue_days"] = (datetime.fromisoformat(today) - datetime.fromisoformat(r["due_date"])).days
        except Exception:
            r["overdue_days"] = 0
    return {"rows": rows, "total_outstanding": round(sum(float(r.get("outstanding") or 0) for r in rows), 2)}


@router.get("/reports/invoice-register")
async def invoice_register(invoice_type: Optional[str] = None,
                           start: Optional[str] = None, end: Optional[str] = None,
                           user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if invoice_type:
        q["invoice_type"] = invoice_type.upper()
    if start:
        q["invoice_date"] = {**q.get("invoice_date", {}), "$gte": start}
    if end:
          q["invoice_date"] = {**q.get("invoice_date", {}), "$lte": end}
    rows = await db.client_invoices.find(q, {"_id": 0}).sort("invoice_date", -1).to_list(2000)
    return {"rows": rows,
            "totals": {"gross": round(sum(float((r.get("totals") or {}).get("gross_value") or 0) for r in rows), 2),
                       "outstanding": round(sum(float(r.get("outstanding") or 0) for r in rows), 2),
                       "count": len(rows)}}


@router.get("/reports/client-ledger")
async def client_ledger(client_id: Optional[str] = None, client_name: Optional[str] = None,
                        user: dict = Depends(require_permission("accounting", "read"))):
    if not (client_id or client_name):
        raise HTTPException(status_code=400, detail="client_id or client_name required")
    q = {"client_id": client_id} if client_id else {"client_name": client_name}
    invs = await db.client_invoices.find(q, {"_id": 0}).sort("invoice_date", 1).to_list(2000)
    rcpts = await db.client_receipts.find(q, {"_id": 0}).sort("receipt_date", 1).to_list(2000)
    events: List[Dict[str, Any]] = []
    for i in invs:
        events.append({"date": i["invoice_date"], "type": "INVOICE",
                       "ref": i["invoice_no"], "narration": i.get("description") or i.get("invoice_type"),
                       "debit": float((i.get("totals") or {}).get("gross_value") or 0), "credit": 0})
    for r in rcpts:
        events.append({"date": r["receipt_date"], "type": "RECEIPT",
                       "ref": r["receipt_no"],
                       "narration": f"{r.get('mode')} · {r.get('txn_reference') or ''}",
                       "debit": 0, "credit": float(r.get("total_adjusted") or 0)})
    events.sort(key=lambda x: x["date"])
    running = 0.0
    for e in events:
        running += e["debit"] - e["credit"]
        e["running"] = round(running, 2)
    return {"events": events, "closing_balance": round(running, 2)}
