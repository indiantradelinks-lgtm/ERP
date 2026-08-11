"""Accounts · Payment Processing queue (prefix /accounts/payment-queue).

Flow: dept raises payment request → approval chain approves → request lands here →
Accounts verifies vendor/bank/GST/invoice details → verified requests are bundled
into a bank payment file (xlsx for direct bank upload) → after bank processes,
Accounts marks paid (UTR) which posts a Journal Entry (DR expense / CR bank).
Attachments live on parent_type 'payment_request' visible to all linked users.
"""
from io import BytesIO
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from accounting_service import post_journal_entry, ensure_coa_seeded

router = APIRouter(prefix="/accounts/payment-queue", tags=["payment-processing"])

QUEUE_STATUSES = ["with_dept", "pr_raised", "sourcing", "fulfilled"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _stage(v: Optional[dict]) -> str:
    return (v or {}).get("stage") or "pending_verification"


@router.get("")
async def payment_queue(stage: str = "", project_code: str = "",
                        user: dict = Depends(require_permission("accounting", "read"))):
    reqs = await db.project_requests.find(
        {"is_payment": True, "status": {"$in": QUEUE_STATUSES},
         **({"project_code": project_code} if project_code else {})},
        {"_id": 0}).sort("created_at", -1).to_list(1000)
    ver = {v["request_id"]: v async for v in db.payment_verifications.find(
        {"request_id": {"$in": [r["id"] for r in reqs]}}, {"_id": 0})}
    out = []
    for r in reqs:
        v = ver.get(r["id"])
        st = _stage(v)
        if stage and st != stage:
            continue
        out.append({**r, "verification": v, "pay_stage": st})
    return out


class VerifyIn(BaseModel):
    decision: str  # verified | rejected
    vendor_name: str = ""
    vendor_account_no: str = ""
    ifsc: str = ""
    bank_name: str = ""
    gst_applicable: bool = False
    gstin: str = ""
    gst_amount: float = 0.0
    invoice_type: str = "bill"  # bill | proforma
    invoice_no: str = ""
    invoice_date: str = ""
    verified_amount: float = 0.0
    tds_applicable: bool = False
    tds_pct: float = 0.0
    tds_amount: float = 0.0
    advance_adjusted: float = 0.0
    expense_account_code: str = "5150"
    remarks: str = ""


@router.post("/{rid}/verify")
async def verify_payment(rid: str, p: VerifyIn, request: Request,
                         user: dict = Depends(require_permission("accounting", "write"))):
    row = await db.project_requests.find_one({"id": rid, "is_payment": True}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Payment request not found")
    if row["status"] not in QUEUE_STATUSES:
        raise HTTPException(400, f"Request is not approved yet (status {row['status']})")
    if p.decision not in ("verified", "rejected"):
        raise HTTPException(400, "decision must be verified or rejected")
    if p.decision == "verified":
        missing = [f for f, val in [("vendor_name", p.vendor_name), ("vendor_account_no", p.vendor_account_no),
                                    ("ifsc", p.ifsc), ("invoice_no", p.invoice_no)] if not str(val).strip()]
        if missing:
            raise HTTPException(400, f"Required for verification: {', '.join(missing)}")
        if p.verified_amount <= 0:
            raise HTTPException(400, "verified_amount must be > 0")
        if p.gst_applicable and not p.gstin.strip():
            raise HTTPException(400, "GSTIN required when GST is applicable")
        if p.tds_amount < 0 or p.advance_adjusted < 0:
            raise HTTPException(400, "TDS / advance adjustment cannot be negative")
        if p.tds_applicable and p.tds_amount <= 0:
            raise HTTPException(400, "tds_amount must be > 0 when TDS is applicable")
    net_payable = round(p.verified_amount - p.tds_amount - p.advance_adjusted, 2)
    if p.decision == "verified" and net_payable < 0:
        raise HTTPException(400, "TDS + advance adjustment exceed the verified amount")
    existing = await db.payment_verifications.find_one({"request_id": rid}, {"_id": 0})
    if existing and existing.get("stage") in ("in_bank_file", "paid"):
        raise HTTPException(400, f"Already {existing['stage']} — cannot re-verify")
    doc = {**p.dict(), "net_payable": net_payable,
           "id": (existing or {}).get("id") or new_id(), "request_id": rid,
           "request_no": row.get("request_no"), "stage": p.decision,
           "verified_by": user.get("name") or user.get("email"), "verified_by_id": user["id"],
           "verified_at": now_iso()}
    await db.payment_verifications.update_one({"request_id": rid}, {"$set": doc}, upsert=True)
    await audit(user=user, action=f"payment_{p.decision}", resource="payment_queue",
                record_id=rid, after={"request_no": row.get("request_no"), "amount": p.verified_amount},
                ip=_ip(request))
    return doc


class BankFileIn(BaseModel):
    request_ids: List[str]
    bank_account_code: str = "1100"
    payment_mode: str = "NEFT"


def _bank_xlsx(f: dict) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "BANK_PAYMENT"
    ws.append(["Sr", "Beneficiary Name", "Account Number", "IFSC", "Amount (INR)", "Payment Mode", "Narration"])
    for i, r in enumerate(f["rows"], 1):
        ws.append([i, r["vendor_name"], r["vendor_account_no"], r["ifsc"],
                   r["amount"], f.get("payment_mode", "NEFT"), r["narration"]])
    ws.append([])
    ws.append(["", "TOTAL", "", "", f["total_amount"], "", f["file_no"]])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.post("/bank-file")
async def create_bank_file(p: BankFileIn, request: Request,
                           user: dict = Depends(require_permission("accounting", "write"))):
    if not p.request_ids:
        raise HTTPException(400, "Select at least one verified payment")
    vers = await db.payment_verifications.find(
        {"request_id": {"$in": p.request_ids}}, {"_id": 0}).to_list(500)
    vmap = {v["request_id"]: v for v in vers}
    rows, total = [], 0.0
    for rid in p.request_ids:
        v = vmap.get(rid)
        if not v or v.get("stage") != "verified":
            raise HTTPException(400, f"Request {rid} is not in 'verified' stage")
        amt = float(v.get("net_payable") if v.get("net_payable") is not None else v.get("verified_amount") or 0)
        if amt <= 0:
            raise HTTPException(400, f"Request {v.get('request_no')} has nothing payable to bank (net ₹0)")
        rows.append({"request_id": rid, "request_no": v.get("request_no"),
                     "vendor_name": v.get("vendor_name"), "vendor_account_no": v.get("vendor_account_no"),
                     "ifsc": v.get("ifsc"), "amount": amt,
                     "narration": f"{v.get('request_no')} {v.get('invoice_no') or ''}".strip()})
        total += amt
    file_doc = {"id": new_id(), "file_no": await next_sequence("BPF"),
                "rows": rows, "total_amount": round(total, 2),
                "bank_account_code": p.bank_account_code, "payment_mode": p.payment_mode,
                "created_by": user.get("name") or user.get("email"), "created_at": now_iso()}
    await db.bank_payment_files.insert_one(dict(file_doc))
    await db.payment_verifications.update_many(
        {"request_id": {"$in": p.request_ids}},
        {"$set": {"stage": "in_bank_file", "bank_file_id": file_doc["id"],
                  "bank_file_no": file_doc["file_no"]}})
    await audit(user=user, action="bank_file_created", resource="payment_queue",
                record_id=file_doc["id"], after={"file_no": file_doc["file_no"], "total": total,
                                                 "count": len(rows)}, ip=_ip(request))
    return StreamingResponse(BytesIO(_bank_xlsx(file_doc)), media_type=XLSX_MIME, headers={
        "Content-Disposition": f'attachment; filename="{file_doc["file_no"]}.xlsx"',
        "X-File-No": file_doc["file_no"]})


@router.get("/bank-files")
async def list_bank_files(user: dict = Depends(require_permission("accounting", "read"))):
    return await db.bank_payment_files.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/bank-files/{fid}/download")
async def download_bank_file(fid: str, user: dict = Depends(require_permission("accounting", "read"))):
    f = await db.bank_payment_files.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Bank file not found")
    return StreamingResponse(BytesIO(_bank_xlsx(f)), media_type=XLSX_MIME, headers={
        "Content-Disposition": f'attachment; filename="{f["file_no"]}.xlsx"'})


class MarkPaidIn(BaseModel):
    utr_no: str
    paid_date: str


@router.post("/{rid}/mark-paid")
async def mark_paid(rid: str, p: MarkPaidIn, request: Request,
                    user: dict = Depends(require_permission("accounting", "write"))):
    v = await db.payment_verifications.find_one({"request_id": rid}, {"_id": 0})
    if not v or v.get("stage") not in ("verified", "in_bank_file"):
        raise HTTPException(400, "Payment must be verified (and ideally in a bank file) first")
    if not p.utr_no.strip():
        raise HTTPException(400, "UTR number is required")
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    amt = float(v.get("verified_amount") or 0)
    tds = float(v.get("tds_amount") or 0)
    advance = float(v.get("advance_adjusted") or 0)
    net = round(amt - tds - advance, 2)
    lines = [{"account_code": v.get("expense_account_code") or "5150", "debit": amt, "credit": 0,
              "narration": row.get("description") or row.get("request_type_label")}]
    if net > 0:
        lines.append({"account_code": "1100", "debit": 0, "credit": net, "narration": f"UTR {p.utr_no}"})
    if tds > 0:
        lines.append({"account_code": "2400", "debit": 0, "credit": tds, "narration": "TDS deducted"})
    if advance > 0:
        lines.append({"account_code": "1510", "debit": 0, "credit": advance, "narration": "Vendor advance adjusted"})
    await ensure_coa_seeded()
    je = await post_journal_entry(
        date=p.paid_date, narration=f"Payment {v.get('request_no')} — {v.get('vendor_name')} (UTR {p.utr_no})",
        lines=lines,
        source_module="payment_queue", source_id=rid, source_event="paid",
        source_ref=v.get("request_no"), project_id=row.get("project_id"),
        department=row.get("owning_dept"), posted_by=user.get("name") or user.get("email"),
        voucher_type="PYV", party_type="vendor", party_name=v.get("vendor_name"))
    await db.payment_verifications.update_one({"request_id": rid}, {"$set": {
        "stage": "paid", "utr_no": p.utr_no, "paid_date": p.paid_date,
        "paid_by": user.get("name") or user.get("email"), "paid_at": now_iso(),
        "journal_entry_id": (je or {}).get("id"), "voucher_number": (je or {}).get("voucher_number")}})
    await db.project_requests.update_one({"id": rid}, {"$set": {
        "payment_status": "paid", "payment_utr": p.utr_no, "payment_date": p.paid_date}})
    await audit(user=user, action="payment_paid", resource="payment_queue", record_id=rid,
                after={"utr": p.utr_no, "amount": amt, "je": (je or {}).get("voucher_number")}, ip=_ip(request))
    return await db.payment_verifications.find_one({"request_id": rid}, {"_id": 0})
