"""Accounts · Payment Processing queue (prefix /accounts/payment-queue).

Flow: dept raises payment request → approval chain approves → request lands here →
Accounts verifies vendor/bank/GST/invoice details → verified requests are bundled
into a bank payment file (xlsx for direct bank upload) → after bank processes,
Accounts marks paid (UTR) which posts a Journal Entry (DR expense / CR bank).
Attachments live on parent_type 'payment_request' visible to all linked users.
"""
import re
from io import BytesIO
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from accounting_service import post_journal_entry, ensure_coa_seeded

router = APIRouter(prefix="/accounts/payment-queue", tags=["payment-processing"])

QUEUE_STATUSES = ["with_dept", "pr_raised", "sourcing", "fulfilled"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DEFAULT_DEBIT_AC_NO = "169405500094"


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _stage(v: Optional[dict]) -> str:
    return (v or {}).get("stage") or "pending_verification"


@router.get("")
async def payment_queue(stage: str = "", project_code: str = "",
                        user: dict = Depends(require_permission("accounting", "read"))):
    try:
        from routers.vendor_billing_router import release_due_bills_to_queue
        await release_due_bills_to_queue()
    except Exception:
        pass
    reqs = await db.project_requests.find(
        {"is_payment": True, "status": {"$in": QUEUE_STATUSES},
         "split_into_children": {"$exists": False},
         **({"project_code": project_code} if project_code else {})},
        {"_id": 0}).sort("created_at", -1).to_list(1000)
    ver = {v["request_id"]: v async for v in db.payment_verifications.find(
        {"request_id": {"$in": [r["id"] for r in reqs]}}, {"_id": 0})}
    proj_ids = list({r.get("project_id") for r in reqs if r.get("project_id")})
    pmap = {p["id"]: p async for p in db.projects.find(
        {"id": {"$in": proj_ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1, "project_manager_name": 1, "manager": 1})}
    proj_codes = list({r.get("project_code") for r in reqs if r.get("project_code") and not r.get("project_id")})
    pcode_map = {p["code"]: p async for p in db.projects.find(
        {"code": {"$in": proj_codes}}, {"_id": 0, "id": 1, "name": 1, "code": 1, "project_manager_name": 1, "manager": 1})} if proj_codes else {}
    adv_ids = list({r.get("source_id") for r in reqs if r.get("source") == "advance" and r.get("source_id")})
    amap = {a["id"]: a async for a in db.employee_advances.find(
        {"id": {"$in": adv_ids}},
        {"_id": 0, "id": 1, "created_by": 1, "project_code": 1, "project_name": 1, "project_manager": 1})} if adv_ids else {}
    emp_ids = list({r.get("employee_id") for r in reqs if r.get("employee_id")})
    emap = {e["id"]: e async for e in db.employees.find(
        {"id": {"$in": emp_ids}},
        {"_id": 0, "id": 1, "name": 1, "bank_account_no": 1, "bank_account": 1, "bank_ifsc": 1, "bank_name": 1,
         "bank_branch": 1, "bank_beneficiary_name": 1})} if emp_ids else {}
    emp_codes = list({r.get("employee_code") for r in reqs if r.get("employee_code") and not r.get("employee_id")})
    ecmap: dict = {}
    if emp_codes:
        async for e in db.employees.find(
                {"$or": [{"emp_code": {"$in": emp_codes}}, {"employee_id": {"$in": emp_codes}}]},
                {"_id": 0, "id": 1, "emp_code": 1, "employee_id": 1, "name": 1, "bank_account_no": 1, "bank_account": 1,
                 "bank_ifsc": 1, "bank_name": 1, "bank_branch": 1, "bank_beneficiary_name": 1}):
            for k in (e.get("emp_code"), e.get("employee_id")):
                if k:
                    ecmap.setdefault(k, e)
    cc_ids = list({r.get("cost_center_id") for r in reqs if r.get("cost_center_id")})
    ccmap = {c["id"]: c async for c in db.cost_centers.find(
        {"id": {"$in": cc_ids}},
        {"_id": 0, "id": 1, "name": 1, "code": 1, "category_code": 1, "category_name": 1})} if cc_ids else {}
    out = []
    for r in reqs:
        v = ver.get(r["id"])
        st = _stage(v)
        if stage and st != stage:
            continue
        proj = pmap.get(r.get("project_id")) or pcode_map.get(r.get("project_code")) or {}
        adv = amap.get(r.get("source_id")) if r.get("source") == "advance" else None
        raised_by = r.get("created_by") or r.get("requested_by")
        if adv and (not raised_by or raised_by == "approval_engine"):
            raised_by = adv.get("created_by") or raised_by
        emp = emap.get(r.get("employee_id")) or ecmap.get(r.get("employee_code"))
        cc = ccmap.get(r.get("cost_center_id"))
        cc_name = r.get("cost_center_label") or (
            (f"{cc.get('category_code') or ''} · {cc.get('category_name') or ''}".strip(" ·") or cc.get("name"))
            if cc else None)
        out.append({**r, "verification": v, "pay_stage": st, "cost_center_name": cc_name,
                    "project_name": r.get("project_name") or proj.get("name") or (adv or {}).get("project_name"),
                    "project_code": r.get("project_code") or proj.get("code") or (adv or {}).get("project_code"),
                    "raised_by": raised_by,
                    "project_manager": r.get("project_manager") or proj.get("project_manager_name")
                                       or proj.get("manager") or (adv or {}).get("project_manager"),
                    "employee_bank": _employee_bank(emp),
                    "employee_record_id": (emp or {}).get("id")})
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
    vendor_email: str = ""
    verified_amount: float = 0.0
    tds_applicable: bool = False
    tds_pct: float = 0.0
    tds_amount: float = 0.0
    advance_adjusted: float = 0.0
    expense_account_code: str = "5150"
    remarks: str = ""


def _employee_bank(emp: Optional[dict]) -> Optional[dict]:
    if not emp:
        return None
    acct = emp.get("bank_account_no") or emp.get("bank_account")
    if not acct:
        return None
    return {"account_no": str(acct), "ifsc": (emp.get("bank_ifsc") or "").upper(),
            "bank_name": emp.get("bank_name"), "branch": emp.get("bank_branch"),
            "beneficiary_name": emp.get("bank_beneficiary_name") or emp.get("name")}


class BankDetailsIn(BaseModel):
    beneficiary_name: str = ""
    bank_name: str = ""
    account_no: str
    ifsc: str
    branch: str = ""


@router.post("/{rid}/save-bank-details")
async def save_bank_details(rid: str, p: BankDetailsIn, request: Request,
                            user: dict = Depends(require_permission("accounting", "write"))):
    """Save manually-entered bank details back to the Employee/Worker master
    so future payment verifications auto-fill them."""
    import re
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Payment queue row not found")
    emp = None
    if row.get("employee_id"):
        emp = await db.employees.find_one({"id": row["employee_id"]}, {"_id": 0, "id": 1, "emp_code": 1, "name": 1})
    if not emp and row.get("employee_code"):
        emp = await db.employees.find_one({"$or": [{"emp_code": row["employee_code"]}, {"employee_id": row["employee_code"]}]},
                                          {"_id": 0, "id": 1, "emp_code": 1, "name": 1})
    if not emp:
        raise HTTPException(400, "This payment is not linked to an employee/worker record")
    acct = (p.account_no or "").strip().replace(" ", "")
    ifsc = (p.ifsc or "").strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9]{6,20}", acct):
        raise HTTPException(400, "Account number must be 6–20 letters/digits")
    if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc):
        raise HTTPException(400, "IFSC must be 11 characters, e.g. HDFC0001234")
    upd = {"bank_account_no": acct, "bank_ifsc": ifsc,
           "bank_name": (p.bank_name or "").strip(),
           "bank_branch": (p.branch or "").strip(),
           "bank_beneficiary_name": (p.beneficiary_name or "").strip() or emp.get("name"),
           "bank_updated_by": user.get("name") or user.get("email"),
           "bank_updated_at": now_iso(), "updated_at": now_iso()}
    await db.employees.update_one({"id": emp["id"]}, {"$set": upd})
    await audit(user=user, action="employee_bank_update", resource="employees",
                record_id=emp["id"],
                after={"emp_code": emp.get("emp_code"), "account_no": acct, "ifsc": ifsc,
                       "via": f"payment_verification:{row.get('request_no')}"},
                ip=_ip(request))
    return {"ok": True, "employee_id": emp["id"], "emp_code": emp.get("emp_code"), **upd}


@router.get("/export/{fmt}")
async def export_payment_queue(fmt: str, stage: str = "pending", search: str = "",
                               user: dict = Depends(require_permission("accounting", "read"))):
    """Excel/PDF export of a Payment Processing tab (pending | verified | bank | paid)."""
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "fmt must be xlsx or pdf")
    rows = await payment_queue(stage="", project_code="", user=user)
    def tab_of(r):
        s = r.get("pay_stage")
        if s == "verified":
            return "verified"
        if s == "in_bank_file":
            return "bank"
        if s == "paid":
            return "paid"
        return "pending"
    rows = [r for r in rows if tab_of(r) == stage]
    if search:
        s = search.lower()
        rows = [r for r in rows if s in " ".join(str(r.get(k) or "") for k in
                ("request_no", "employee_name", "vendor_name", "project_code", "project_name",
                 "description", "request_type")).lower()]
    data = []
    for i, r in enumerate(rows, start=1):
        v = r.get("verification") or {}
        data.append({
            "s_no": i,
            "request_no": r.get("request_no"),
            "date": str(r.get("created_at") or "")[:10],
            "source": (r.get("source") or r.get("request_type") or "").replace("_", " "),
            "project": " ".join(x for x in [r.get("project_code"), r.get("project_name")] if x),
            "payee": r.get("employee_name") or r.get("vendor_name") or v.get("vendor_name") or "",
            "description": r.get("description") or "",
            "amount": r.get("amount") or r.get("est_value") or 0,
            "verified_amount": v.get("verified_amount") or "",
            "net_payable": v.get("net_payable") or "",
            "stage": (r.get("pay_stage") or "").replace("_", " "),
            "utr_no": v.get("utr_no") or r.get("utr_no") or "",
            "paid_date": v.get("paid_date") or r.get("paid_date") or "",
            "raised_by": r.get("raised_by") or r.get("created_by") or "",
        })
    from exports import to_excel, to_pdf
    label = {"pending": "Pending-Verification", "verified": "Verified", "bank": "Bank-Files", "paid": "Paid-History"}.get(stage, stage)
    if fmt == "xlsx":
        content = to_excel("payment_queue", data)
        mt = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = to_pdf("payment_queue", data)
        mt = "application/pdf"
    return Response(content=content, media_type=mt,
                    headers={"Content-Disposition": f'attachment; filename="Payment-{label}.{fmt}"'})


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
    payment_mode: str = "N"
    debit_ac_no: str = DEFAULT_DEBIT_AC_NO


CMS_HEADERS = ["Debit Ac No", "Beneficiary Ac No", "Beneficiary Name", "Amt", "Pay Mod", "Date",
               "IFSC", "Payable Location", "Print Location", "Bene Mobile No.", "Bene Email ID",
               "Bene add1", "Bene add2", "Bene add3", "Bene add4",
               "Add Details 1", "Add Details 2", "Add Details 3", "Add Details 4", "Add Details 5",
               "Remarks"]


def _cms_date(iso: str) -> str:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso[:10]).strftime("%d-%b-%Y").upper()
    except Exception:
        return iso[:10]


def _bank_xlsx(f: dict) -> bytes:
    """CMS bank-upload format (matches customer-provided template)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "BANK_PAYMENT"
    ws.append(CMS_HEADERS)
    debit_ac = f.get("debit_ac_no") or DEFAULT_DEBIT_AC_NO
    pay_mode = f.get("payment_mode") or "N"
    if len(pay_mode) > 2:  # legacy files stored 'NEFT'
        pay_mode = "N"
    file_date = _cms_date(f.get("created_at") or now_iso())
    for r in f["rows"]:
        ifsc = (r.get("ifsc") or "").upper()
        pay_mod = "" if ifsc.startswith("ICIC") else pay_mode
        ws.append([debit_ac, r["vendor_account_no"], r["vendor_name"], r["amount"], pay_mod,
                   file_date, ifsc, "", "", "", "", "", "", "", "", "", "", "", "", "",
                   r["narration"]])
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
                     "narration": (v.get("remarks") or "").strip() or f"{v.get('request_no')} {v.get('invoice_no') or ''}".strip()})
        total += amt
    if not str(p.debit_ac_no).strip():
        raise HTTPException(400, "Debit A/c No is required")
    file_doc = {"id": new_id(), "file_no": await next_sequence("BPF"),
                "rows": rows, "total_amount": round(total, 2),
                "bank_account_code": p.bank_account_code, "payment_mode": p.payment_mode,
                "debit_ac_no": str(p.debit_ac_no).strip(),
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


async def _resolve_vendor_email(v: dict) -> str:
    if (v.get("vendor_email") or "").strip():
        return v["vendor_email"].strip()
    name = (v.get("vendor_name") or "").strip()
    if name:
        import re
        vd = await db.vendors.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0, "email": 1})
        if vd and (vd.get("email") or "").strip():
            return vd["email"].strip()
    return ""


async def _send_payment_advice(v: dict, row: dict, utr: str, paid_date: str, user: dict) -> dict:
    """Best-effort branded payment advice to the vendor. Never raises."""
    try:
        to = await _resolve_vendor_email(v)
        if not to:
            return {"advice_status": "no_email"}
        from notification_service import tmpl_payment_advice, send_email as resend_send, email_enabled
        t = tmpl_payment_advice(v, row, utr, paid_date)
        from routers.email_router import _queue_outbox, _send_and_log
        from m365_email import shared_mailbox_configured, SHARED_USERNAME, SHARED_DISPLAY_NAME
        if shared_mailbox_configured():
            outbox_id = await _queue_outbox(
                sender_type="shared", sender_user_id=user["id"], sender_email=SHARED_USERNAME,
                sender_display_name=SHARED_DISPLAY_NAME, to=[to], cc=[], bcc=[],
                subject=t["subject"], body_text=f"Payment advice — UTR {utr}", body_html=t["html"],
                reply_to=None, attachments_inline=[], file_ids=[],
                related={"entity_type": "payment_queue", "entity_id": v.get("request_id"),
                         "entity_ref": v.get("request_no"), "vendor_name": v.get("vendor_name")},
                queued_by=user["id"])
            import asyncio
            asyncio.create_task(_send_and_log(outbox_id))
            return {"advice_status": "queued", "advice_to": to, "advice_outbox_id": outbox_id}
        if email_enabled():
            ok = await resend_send(to, t["subject"], t["html"])
            return {"advice_status": "sent" if ok else "failed", "advice_to": to}
        return {"advice_status": "email_disabled", "advice_to": to}
    except Exception as e:
        import logging
        logging.getLogger("erp").warning(f"Payment advice email failed for {v.get('request_no')}: {e}")
        return {"advice_status": "failed"}


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
    lines = [{"account_code": row.get("pay_debit_account_code") or v.get("expense_account_code") or "5150",
              "debit": amt, "credit": 0,
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
    advice = await _send_payment_advice(v, row, p.utr_no, p.paid_date, user)
    await db.payment_verifications.update_one({"request_id": rid}, {"$set": advice})
    await db.project_requests.update_one({"id": rid}, {"$set": {
        "payment_status": "paid", "payment_utr": p.utr_no, "payment_date": p.paid_date}})
    if row.get("source") == "vendor_bill" and row.get("source_id"):
        await db.logistics_vendor_bills.update_one({"id": row["source_id"]}, {"$set": {
            "status": "paid", "utr_no": p.utr_no, "paid_date": p.paid_date, "updated_at": now_iso()}})
        lvb = await db.logistics_vendor_bills.find_one({"id": row["source_id"]}, {"_id": 0})
        if lvb:
            from routers.logistics_phase4_router import _mirror_bill_to_vendor_bills
            await _mirror_bill_to_vendor_bills(lvb)
    if row.get("source") == "accounts_vendor_bill" and row.get("source_id"):
        paid_amt = float(v.get("net_payable") if v.get("net_payable") is not None else net)
        bill = await db.vendor_bills.find_one({"id": row["source_id"]},
                                              {"_id": 0, "paid_amount": 1, "outstanding": 1})
        if bill:
            new_paid = round(float(bill.get("paid_amount") or 0) + paid_amt, 2)
            new_out = max(round(float(bill.get("outstanding") or 0) - paid_amt, 2), 0.0)
            await db.vendor_bills.update_one({"id": row["source_id"]}, {"$set": {
                "paid_amount": new_paid, "outstanding": new_out,
                "status": "paid" if new_out <= 0 else "partially_paid",
                "last_payment_utr": p.utr_no, "last_payment_date": p.paid_date,
                "updated_at": now_iso()}})
            await db.alerts.delete_one({"id": f"vpd-{row['source_id']}"})
    if row.get("source") == "service_invoice" and row.get("source_id"):
        from routers.service_workflow_router import on_service_invoice_paid
        await on_service_invoice_paid(row["source_id"], p.utr_no, p.paid_date, user)
    if row.get("source") == "advance" and row.get("source_id"):
        adv = await db.employee_advances.find_one({"id": row["source_id"]}, {"_id": 0})
        if adv and adv.get("status") == "approved":
            paid_amt = float(v.get("net_payable") if v.get("net_payable") is not None else v.get("verified_amount") or 0)
            await db.employee_advances.update_one({"id": row["source_id"]}, {"$set": {
                "status": "paid",
                "payment": {"mode": "Bank (Accounts Payment Queue)", "paid_amount": paid_amt,
                            "payment_date": p.paid_date, "txn_no": p.utr_no,
                            "voucher_no": (je or {}).get("voucher_number"),
                            "paid_by": user.get("name") or user.get("email"), "paid_at": now_iso()},
                "paid_amount": paid_amt, "outstanding": paid_amt, "paid_at": now_iso()},
                "$push": {"status_history": {"at": now_iso(), "by": user.get("name") or user.get("email"),
                                             "by_role": user.get("role"), "from": "approved", "to": "paid",
                                             "comment": f"Paid via Accounts Payment Queue · UTR {p.utr_no}"}}})
    await audit(user=user, action="payment_paid", resource="payment_queue", record_id=rid,
                after={"utr": p.utr_no, "amount": amt, "je": (je or {}).get("voucher_number")}, ip=_ip(request))
    return await db.payment_verifications.find_one({"request_id": rid}, {"_id": 0})


# ─── Bulk UTR upload / bulk Mark Paid ─────────────────────────────────────────
BULK_HEADERS = ["Request No", "UTR No", "Paid Date (YYYY-MM-DD)", "Vendor", "Net Payable", "Stage"]


@router.get("/bulk-utr/template")
async def bulk_utr_template(stage: str = "", user: dict = Depends(require_permission("accounting", "read"))):
    """Excel template pre-filled with every payment awaiting UTR (verified / in bank file)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    q: Dict[str, Any] = {"stage": {"$in": ["verified", "in_bank_file"]}}
    if stage in ("verified", "in_bank_file"):
        q["stage"] = stage
    rows = await db.payment_verifications.find(q, {"_id": 0, "request_no": 1, "vendor_name": 1, "net_payable": 1,
                                                   "verified_amount": 1, "stage": 1}).sort("request_no", 1).to_list(5000)
    wb = Workbook()
    ws = wb.active
    ws.title = "Bulk UTR"
    ws.append(BULK_HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F2937")
    today = now_iso()[:10]
    for r in rows:
        ws.append([r.get("request_no"), "", today, r.get("vendor_name"),
                   r.get("net_payable") if r.get("net_payable") is not None else r.get("verified_amount"), r.get("stage")])
    for col, w in zip("ABCDEF", (18, 24, 22, 32, 14, 14)):
        ws.column_dimensions[col].width = w
    ws2 = wb.create_sheet("Instructions")
    for line in ["Fill column B (UTR No) for each Request No you have paid.",
                 "Column C (Paid Date) is optional — defaults to today when blank.",
                 "Leave a row's UTR blank to skip it. Do not rename or reorder columns A–C.",
                 "Only payments in stage 'verified' or 'in_bank_file' can be marked paid."]:
        ws2.append([line])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="bulk_utr_template_{today}.xlsx"'})


def _parse_bulk_rows(content: bytes) -> List[Dict[str, Any]]:
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if i == 1:
            continue  # header
        if not row or all(v in (None, "") for v in row[:3]):
            continue
        req = str(row[0] or "").strip()
        utr = str(row[1] or "").strip() if len(row) > 1 else ""
        pd = row[2] if len(row) > 2 else None
        if hasattr(pd, "strftime"):
            pd = pd.strftime("%Y-%m-%d")
        out.append({"row": i, "request_no": req, "utr_no": utr, "paid_date": str(pd or "").strip()[:10]})
    return out


async def _validate_bulk(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = now_iso()[:10]
    valid, errors = [], []
    seen_req, seen_utr = set(), {}
    nos = [r["request_no"] for r in rows if r["request_no"]]
    vmap = {v["request_no"]: v async for v in db.payment_verifications.find({"request_no": {"$in": nos}}, {"_id": 0})}
    used = {u["utr_no"]: u["request_no"] async for u in db.payment_verifications.find(
        {"stage": "paid", "utr_no": {"$in": [r["utr_no"] for r in rows if r["utr_no"]]}}, {"_id": 0, "utr_no": 1, "request_no": 1})}
    for r in rows:
        err = None
        if not r["request_no"]:
            err = "Request No is blank"
        elif not r["utr_no"]:
            continue  # intentionally skipped row
        elif r["request_no"] in seen_req:
            err = "Duplicate Request No in file"
        elif r["request_no"] not in vmap:
            err = "Request No not found in payment queue"
        elif vmap[r["request_no"]].get("stage") == "paid":
            err = f"Already paid (UTR {vmap[r['request_no']].get('utr_no') or '—'})"
        elif vmap[r["request_no"]].get("stage") not in ("verified", "in_bank_file"):
            err = f"Not ready — stage is '{vmap[r['request_no']].get('stage')}' (must be verified / in bank file)"
        elif r["utr_no"] in used:
            err = f"UTR already used on {used[r['utr_no']]}"
        elif r["utr_no"] in seen_utr:
            err = f"Duplicate UTR in file (also on {seen_utr[r['utr_no']]})"
        elif r["paid_date"] and not re.match(r"^\d{4}-\d{2}-\d{2}$", r["paid_date"]):
            err = "Paid Date must be YYYY-MM-DD"
        if err:
            errors.append({**r, "error": err})
            continue
        seen_req.add(r["request_no"])
        seen_utr[r["utr_no"]] = r["request_no"]
        v = vmap[r["request_no"]]
        valid.append({**r, "paid_date": r["paid_date"] or today, "request_id": v["request_id"],
                      "vendor_name": v.get("vendor_name"), "stage": v.get("stage"),
                      "net_payable": v.get("net_payable") if v.get("net_payable") is not None else v.get("verified_amount")})
    return {"valid": valid, "errors": errors, "skipped": len([r for r in rows if r["request_no"] and not r["utr_no"]])}


@router.post("/bulk-utr/validate")
async def bulk_utr_validate(file: UploadFile = File(...), user: dict = Depends(require_permission("accounting", "write"))):
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Upload the .xlsx template")
    try:
        rows = _parse_bulk_rows(await file.read())
    except Exception as e:
        raise HTTPException(400, f"Could not read Excel: {e}")
    res = await _validate_bulk(rows)
    return {**res, "total_rows": len(rows)}


@router.post("/bulk-utr/apply")
async def bulk_utr_apply(file: UploadFile = File(...), request: Request = None,
                         user: dict = Depends(require_permission("accounting", "write"))):
    """Re-validates the uploaded file and marks every valid row paid (same logic as single Mark Paid)."""
    rows = _parse_bulk_rows(await file.read())
    res = await _validate_bulk(rows)
    done, failed = [], []
    for r in res["valid"]:
        try:
            await mark_paid(r["request_id"], MarkPaidIn(utr_no=r["utr_no"], paid_date=r["paid_date"]), request, user)
            done.append({"request_no": r["request_no"], "utr_no": r["utr_no"], "paid_date": r["paid_date"], "vendor_name": r.get("vendor_name")})
        except HTTPException as e:
            failed.append({**r, "error": str(e.detail)})
        except Exception as e:  # noqa: BLE001
            failed.append({**r, "error": str(e)[:200]})
    await audit(user=user, action="payment_bulk_paid", resource="payment_queue", record_id="bulk",
                after={"paid": len(done), "errors": len(res["errors"]) + len(failed)}, ip=_ip(request))
    return {"paid": done, "failed": failed, "errors": res["errors"], "skipped": res["skipped"], "total_rows": len(rows)}
