"""Running Account (RA) Bills, Final Bills, Debit/Credit Notes.

Workflow per bill:
  draft → submitted → approved → invoiced → paid | cancelled

Auto-numbering:
  RA-YYYY-#### for running/final/supplementary bills
  DN-YYYY-#### for debit notes
  CN-YYYY-#### for credit notes

Items can be sourced from `measurements` (status=approved_for_billing). When a
bill moves to `approved`, all linked measurements flip to `billed` and store the
ra_bill_id back-reference.

Money math (all on subtotal of THIS bill's lines, not cumulative PO value):
  gst_amount         = subtotal * gst_pct / 100
  gross_value        = subtotal + gst_amount
  retention_amount   = subtotal * retention_pct / 100
  tds_amount         = subtotal * tds_pct / 100        (deducted from gross)
  other_deductions   = sum of explicit line-items
  net_payable        = gross_value - retention_amount - tds_amount
                       - other_deductions_total - advance_recovery
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence, stamp_dept_doc
from approval_engine import build_chain, insert_approval
from scope import apply_project_scope

router = APIRouter(tags=["ra-bills"])

BILL_TYPES = ("running", "final", "supplementary", "debit_note", "credit_note")
BILL_STATUSES = ("draft", "submitted", "approved", "invoiced", "paid", "cancelled")
APPROVE_ROLES = {"super_admin", "director", "general_manager", "dept_head",
                 "accounts_executive", "billing_executive"}


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────
class RABillItem(BaseModel):
    measurement_id: Optional[str] = None
    measurement_no: Optional[str] = None
    service: Optional[str] = None
    activity: Optional[str] = None
    description: str
    quantity: float
    unit: str = "Nos"
    rate: float
    amount: Optional[float] = None      # computed server-side


class OtherDeduction(BaseModel):
    label: str
    amount: float


class RABillIn(BaseModel):
    bill_type: str = "running"
    bill_date: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_name: Optional[str] = None
    po_id: Optional[str] = None
    po_number: Optional[str] = None
    items: List[RABillItem]
    gst_pct: float = 18
    retention_pct: float = 0
    tds_pct: float = 0
    other_deductions: List[OtherDeduction] = Field(default_factory=list)
    advance_recovery: float = 0
    previous_bill_value: float = 0    # cumulative gross value billed earlier on the PO
    notes: Optional[str] = None
    quotation_no: Optional[str] = None  # offer this bill is formatted from
    bill_number: Optional[str] = None   # manual invoice number; auto next-sequence when blank
    submit: bool = False
    # Debit / Credit note linkage
    against_ra_bill_id: Optional[str] = None
    reason: Optional[str] = None       # required for DN/CN


def _compute_totals(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = payload.get("items") or []
    for it in items:
        rate = float(it.get("rate") or 0)
        qty = float(it.get("quantity") or 0)
        it["amount"] = round(rate * qty, 2)
    subtotal = round(sum(float(it.get("amount") or 0) for it in items), 2)
    gst_pct = float(payload.get("gst_pct") or 0)
    retention_pct = float(payload.get("retention_pct") or 0)
    tds_pct = float(payload.get("tds_pct") or 0)
    gst_amount = round(subtotal * gst_pct / 100.0, 2)
    gross_value = round(subtotal + gst_amount, 2)
    retention_amount = round(subtotal * retention_pct / 100.0, 2)
    tds_amount = round(subtotal * tds_pct / 100.0, 2)
    other_total = round(sum(float(d.get("amount") or 0) for d in (payload.get("other_deductions") or [])), 2)
    advance = float(payload.get("advance_recovery") or 0)
    net_payable = round(gross_value - retention_amount - tds_amount - other_total - advance, 2)
    # For RA / Final running bills, "current bill value" is the gross of THIS bill;
    # cumulative_value = previous_bill_value + gross_value
    previous_bill_value = float(payload.get("previous_bill_value") or 0)
    cumulative_value = round(previous_bill_value + gross_value, 2)
    return {
        "items": items,
        "subtotal": subtotal,
        "gst_amount": gst_amount,
        "gross_value": gross_value,
        "retention_amount": retention_amount,
        "tds_amount": tds_amount,
        "other_deductions_total": other_total,
        "advance_recovery": advance,
        "net_payable": net_payable,
        "current_bill_value": gross_value,
        "cumulative_value": cumulative_value,
    }


def _prefix(bill_type: str) -> str:
    return {"debit_note": "DN", "credit_note": "CN"}.get(bill_type, "RA")


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/ra-bills")
async def list_ra_bills(client_id: Optional[str] = None,
                        project_code: Optional[str] = None,
                        bill_type: Optional[str] = None,
                        status: Optional[str] = None,
                        po_id: Optional[str] = None,
                        user: dict = Depends(require_permission("ra_bills", "read"))):
    q: dict = {}
    if client_id:
        q["client_id"] = client_id
    if project_code:
        q["project_code"] = project_code
    if bill_type:
        q["bill_type"] = bill_type
    if status:
        q["status"] = status
    if po_id:
        q["po_id"] = po_id
    rows = await db.ra_bills.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.get("/ra-bills/dashboard")
async def ra_bills_dashboard(user: dict = Depends(require_permission("ra_bills", "read"))):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    total = await db.ra_bills.count_documents({})
    draft = await db.ra_bills.count_documents({"status": "draft"})
    submitted = await db.ra_bills.count_documents({"status": "submitted"})
    approved = await db.ra_bills.count_documents({"status": "approved"})
    invoiced = await db.ra_bills.count_documents({"status": "invoiced"})
    paid = await db.ra_bills.count_documents({"status": "paid"})
    pipeline = [
        {"$match": {"status": {"$in": ["approved", "invoiced", "paid"]}, "created_at": {"$gte": month_start}}},
        {"$group": {"_id": None,
                    "billed_this_month": {"$sum": "$gross_value"},
                    "retention_held": {"$sum": "$retention_amount"},
                    "tds_deducted": {"$sum": "$tds_amount"},
                    "net_due": {"$sum": {"$cond": [{"$ne": ["$status", "paid"]}, "$net_payable", 0]}}}},
    ]
    tots = await db.ra_bills.aggregate(pipeline).to_list(2)
    t = tots[0] if tots else {}
    return {
        "kpis": {
            "total_bills": total, "draft": draft, "submitted": submitted,
            "approved": approved, "invoiced": invoiced, "paid": paid,
            "billed_this_month": round(t.get("billed_this_month") or 0, 2),
            "retention_held": round(t.get("retention_held") or 0, 2),
            "tds_deducted": round(t.get("tds_deducted") or 0, 2),
            "net_due": round(t.get("net_due") or 0, 2),
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# Bill Generation Requests (Ops raise → multi-level approval → Accounts generate)
# ──────────────────────────────────────────────────────────────────────────────
class BillRequestIn(BaseModel):
    id: Optional[str] = None  # client may pre-generate to link attachments before submit
    project_code: str
    bill_type: str = "running"
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    expected_amount: float = 0
    items: List[Dict[str, Any]] = []
    remarks: Optional[str] = None
    client_name: Optional[str] = None
    quotation_no: Optional[str] = None
    po_number: Optional[str] = None


def _request_status(req: Dict[str, Any], approval: Optional[Dict[str, Any]]) -> str:
    if req.get("status") in ("bill_generated", "rejected"):
        return req["status"]
    if not approval:
        return req.get("status") or "pending_approval"
    return {"pending": "pending_approval", "approved": "approved",
            "rejected": "rejected"}.get(approval.get("status"), "pending_approval")


@router.post("/bill-requests")
async def create_bill_request(payload: BillRequestIn, request: Request,
                              user: dict = Depends(require_permission("bill_requests", "write"))):
    if payload.bill_type not in ("running", "final"):
        raise HTTPException(400, "bill_type must be running or final")
    scoped_q = await apply_project_scope(user, {"code": payload.project_code}, id_field="id", code_field="code")
    project = await db.projects.find_one(scoped_q, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found or outside your project scope")
    handover = await db.project_handovers.find_one(
        {"project_code": payload.project_code}, {"_id": 0}, sort=[("created_at", -1)])
    req_no = await next_sequence("BR")
    rid = payload.id or new_id()
    if await db.bill_requests.find_one({"id": rid}, {"_id": 0, "id": 1}):
        raise HTTPException(400, "Duplicate request id")
    items = []
    for it in payload.items:
        qty = float(it.get("quantity") or 0)
        rate = float(it.get("rate") or 0)
        items.append({"description": it.get("description") or "", "quantity": qty,
                      "unit": it.get("unit") or "", "rate": rate,
                      "amount": round(qty * rate, 2)})
    expected = round(sum(i["amount"] for i in items), 2) if items else payload.expected_amount
    attachments = await db.files.count_documents({"parent_type": "bill_requests", "parent_id": rid, "is_deleted": False})
    doc = {
        "id": rid,
        "request_no": req_no,
        "project_code": payload.project_code,
        "project_name": project.get("name") or "",
        "client_name": payload.client_name or (handover or {}).get("client_name") or project.get("client") or "",
        "quotation_no": payload.quotation_no or (handover or {}).get("quotation_no") or project.get("quotation_no") or "",
        "po_number": payload.po_number or (handover or {}).get("work_order_number") or "",
        "bill_type": payload.bill_type,
        "period_from": payload.period_from, "period_to": payload.period_to,
        "expected_amount": expected,
        "items": items,
        "attachment_count": attachments,
        "remarks": payload.remarks or "",
        "status": "pending_approval",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_role": user.get("role"),
        "bill_id": None, "bill_number": None,
        "created_at": now_iso(),
    }
    chain = await build_chain("bill_request")
    approval = {
        "id": new_id(),
        "title": f"Bill Request {req_no} — {doc['project_code']} · {doc['client_name']} ({payload.bill_type.upper()}, ₹{expected:,.0f}, {len(items)} line item(s), {attachments} document(s))",
        "type": "bill_request",
        "reference": doc["id"],
        "amount": expected,
        "requested_by": doc["requested_by"],
        "chain": chain, "current_step": 0, "history": [],
        "status": "pending", "created_at": now_iso(),
    }
    await insert_approval(approval, skip_gate=True)
    doc["approval_id"] = approval["id"]
    await db.bill_requests.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="bill_request_create", resource="bill_requests",
                record_id=doc["id"], after={"request_no": req_no}, ip=_ip(request))
    return doc


@router.get("/bill-requests")
async def list_bill_requests(status: Optional[str] = None,
                             user: dict = Depends(require_permission("bill_requests", "read"))):
    q: Dict[str, Any] = {}
    q = await apply_project_scope(user, q, id_field="project_id", code_field="project_code")
    rows = await db.bill_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    ids = [r["approval_id"] for r in rows if r.get("approval_id")]
    approvals = {a["id"]: a async for a in db.approvals.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "status": 1, "chain": 1, "current_step": 1})}
    out = []
    for r in rows:
        a = approvals.get(r.get("approval_id"))
        st = _request_status(r, a)
        if status and st != status:
            continue
        out.append({**r, "status": st,
                    "chain": (a or {}).get("chain") or [],
                    "current_step": (a or {}).get("current_step", 0)})
    return out


@router.get("/bill-requests/{rid}")
async def get_bill_request(rid: str,
                           user: dict = Depends(require_permission("bill_requests", "read"))):
    r = await db.bill_requests.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Bill request not found")
    a = await db.approvals.find_one({"id": r.get("approval_id")}, {"_id": 0, "status": 1, "chain": 1, "current_step": 1})
    return {**r, "status": _request_status(r, a), "chain": (a or {}).get("chain") or [],
            "current_step": (a or {}).get("current_step", 0)}


class MarkGeneratedIn(BaseModel):
    bill_id: str


@router.post("/bill-requests/{rid}/mark-generated")
async def mark_bill_generated(rid: str, payload: MarkGeneratedIn, request: Request,
                              user: dict = Depends(require_permission("ra_bills", "write"))):
    r = await db.bill_requests.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Bill request not found")
    a = await db.approvals.find_one({"id": r.get("approval_id")}, {"_id": 0, "status": 1})
    if _request_status(r, a) != "approved":
        raise HTTPException(400, "Bill request must be fully approved before generating the bill")
    bill = await db.ra_bills.find_one({"id": payload.bill_id}, {"_id": 0, "bill_number": 1})
    if not bill:
        raise HTTPException(404, "Bill not found")
    await db.bill_requests.update_one({"id": rid}, {"$set": {
        "status": "bill_generated", "bill_id": payload.bill_id,
        "bill_number": bill.get("bill_number"),
        "generated_by": user.get("name") or user.get("email"),
        "generated_at": now_iso(),
    }})
    await audit(user=user, action="bill_request_generated", resource="bill_requests",
                record_id=rid, after={"bill_id": payload.bill_id}, ip=_ip(request))
    return {"ok": True, "bill_number": bill.get("bill_number")}


class BillRejectIn(BaseModel):
    reason: str


@router.post("/bill-requests/{rid}/reject")
async def reject_bill_request(rid: str, payload: BillRejectIn, request: Request,
                              user: dict = Depends(require_permission("ra_bills", "write"))):
    """Accounts rejects a bill generation request with a mandatory reason —
    status + remarks stay visible to the Manager/Operations users who raised it."""
    if len((payload.reason or "").strip()) < 5:
        raise HTTPException(400, "Rejection reason / remarks are mandatory (min 5 characters)")
    r = await db.bill_requests.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Bill request not found")
    if r.get("status") == "bill_generated":
        raise HTTPException(400, "Bill already generated — cannot reject this request")
    if r.get("status") == "rejected":
        raise HTTPException(400, "Bill request is already rejected")
    await db.bill_requests.update_one({"id": rid}, {"$set": {
        "status": "rejected", "reject_reason": payload.reason.strip(),
        "rejected_by": user.get("name") or user.get("email"),
        "rejected_at": now_iso(), "updated_at": now_iso()}})
    await audit(user=user, action="bill_request_rejected", resource="bill_requests",
                record_id=rid, after={"reason": payload.reason}, ip=_ip(request))
    return {"ok": True, "status": "rejected"}


@router.get("/ra-bills/project-context/{project_code}")
async def ra_bill_project_context(project_code: str,
                                  user: dict = Depends(require_permission("bill_requests", "read"))):
    """Auto-fill context for a New RA Bill: client, site, customer PO and the
    line-item format of the offer (quotation) / received order for the project."""
    project = await db.projects.find_one({"code": project_code}, {"_id": 0})
    handover = await db.project_handovers.find_one(
        {"project_code": project_code}, {"_id": 0}, sort=[("created_at", -1)])

    client_name = (handover or {}).get("client_name") or (project or {}).get("client") or (project or {}).get("client_name") or ""
    client_id = (handover or {}).get("client_id") or (project or {}).get("client_id") or ""
    if not client_name and client_id:
        c = await db.clients.find_one({"id": client_id}, {"_id": 0, "name": 1})
        client_name = (c or {}).get("name") or ""
    if not client_id and client_name:
        c = await db.clients.find_one({"name": client_name}, {"_id": 0, "id": 1})
        client_id = (c or {}).get("id") or ""
    site_name = (handover or {}).get("site_location") or (project or {}).get("site") or ""

    # Customer PO: work order on the handover, else latest order for this client/project
    po_number = (handover or {}).get("work_order_number") or ""
    po_id = ""
    order = None
    if po_number:
        order = await db.orders.find_one({"order_no": po_number}, {"_id": 0})
    if not order:
        order = await db.orders.find_one({"$or": [{"project_code": project_code}, {"project_id": (project or {}).get("id") or ""}]},
                                         {"_id": 0}, sort=[("created_at", -1)])
    if not order and client_name:
        order = await db.orders.find_one({"customer": client_name}, {"_id": 0}, sort=[("created_at", -1)])
    if order:
        po_number = po_number or order.get("order_no") or ""
        po_id = order.get("id") or ""

    # Offer format: quotation linked on the handover, else from the project
    # itself (manually-created projects), else latest sectioned quote for client
    quotation_no = (handover or {}).get("quotation_no") or ""
    quote = None
    if quotation_no:
        quote = await db.quotations.find_one({"quote_number": quotation_no}, {"_id": 0})
    if not quote and project:
        if project.get("quotation_id"):
            quote = await db.quotations.find_one({"id": project["quotation_id"]}, {"_id": 0})
        for qn in (project.get("quotation_no"), project.get("sales_quotation_ref")):
            if quote:
                break
            if qn:
                quote = await db.quotations.find_one({"quote_number": qn}, {"_id": 0})
        if quote:
            quotation_no = quote.get("quote_number") or quotation_no
    if not quote and client_name:
        quote = await db.quotations.find_one(
            {"client": client_name, "sections.0": {"$exists": True}}, {"_id": 0},
            sort=[("created_at", -1)])
        quotation_no = (quote or {}).get("quote_number") or quotation_no

    items: List[Dict[str, Any]] = []
    gst_pct = None
    if quote:
        # Cumulative already-billed qty per line (all non-cancelled bills on this project,
        # credit notes excluded) keyed by normalized description
        billed: Dict[str, float] = {}
        async for b in db.ra_bills.find(
                {"project_code": project_code, "status": {"$ne": "cancelled"},
                 "bill_type": {"$ne": "credit_note"}}, {"_id": 0, "items": 1}):
            for it in b.get("items") or []:
                k = (it.get("description") or "").strip().lower()
                billed[k] = billed.get(k, 0) + float(it.get("quantity") or 0)

        for sec in quote.get("sections") or []:
            for it in sec.get("items") or []:
                offer_qty = float(it.get("quantity") or 0)
                billed_qty = billed.get((it.get("description") or "").strip().lower(), 0)
                items.append({
                    "description": it.get("description") or "",
                    "quantity": max(round(offer_qty - billed_qty, 3), 0),
                    "unit": it.get("unit") or "",
                    "rate": it.get("rate") or 0,
                    "offer_qty": offer_qty,
                    "billed_qty": round(billed_qty, 3),
                })
                if gst_pct is None and it.get("gst_pct") is not None:
                    gst_pct = it.get("gst_pct")
        if not items and quote.get("items"):
            items = [{"description": i.get("description") or "", "quantity": i.get("quantity") or 1,
                      "unit": i.get("unit") or "", "rate": i.get("rate") or 0}
                     for i in quote["items"]]

    if not items and order and (order.get("items") or []):
        # No offer/quote linked — fall back to the customer PO (order) line items
        items = [{"description": i.get("description") or i.get("name") or "", "quantity": i.get("quantity") or 1,
                  "unit": i.get("unit") or "", "rate": i.get("rate") or 0}
                 for i in order["items"]]

    return {
        "project_code": project_code,
        "project_name": (project or {}).get("name") or "",
        "client_id": client_id, "client_name": client_name,
        "site_name": site_name,
        "po_number": po_number, "po_id": po_id,
        "quotation_no": quotation_no,
        "gst_pct": gst_pct,
        "retention_pct": (order or {}).get("retention_pct"),
        "items": items,
    }


@router.get("/ra-bills/{bill_id}")
async def get_ra_bill(bill_id: str, user: dict = Depends(require_permission("ra_bills", "read"))):
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Bill not found")
    return row


@router.post("/ra-bills/from-measurements")
async def create_from_measurements(payload: dict, request: Request,
                                   user: dict = Depends(require_permission("ra_bills", "write"))):
    """Bulk-create a draft RA bill from `approved_for_billing` measurements."""
    measurement_ids = payload.get("measurement_ids") or []
    if not measurement_ids:
        raise HTTPException(status_code=400, detail="measurement_ids[] is required")
    rows = await db.measurements.find({"id": {"$in": measurement_ids}, "status": "approved_for_billing"}, {"_id": 0}).to_list(500)
    if not rows:
        raise HTTPException(status_code=400, detail="No measurements are approved_for_billing")
    items: List[Dict[str, Any]] = []
    project_code = rows[0].get("project_code")
    site_name = rows[0].get("site_name")
    for m in rows:
        for it in m.get("items") or []:
            qty = float(it.get("certified_qty") or 0)
            rate = float(it.get("rate") or 0)
            items.append({
                "measurement_id": m["id"], "measurement_no": m.get("measurement_no"),
                "service": it.get("service"), "activity": it.get("activity"),
                "description": (it.get("description")
                                or f"{(it.get('service') or '').replace('_', ' ').title()} – {it.get('activity', '')}"),
                "quantity": qty, "unit": it.get("unit") or "m²", "rate": rate,
                "amount": round(qty * rate, 2),
            })
    base = {
        "bill_type": payload.get("bill_type") or "running",
        "bill_date": payload.get("bill_date") or now_iso()[:10],
        "client_id": payload.get("client_id"),
        "client_name": payload.get("client_name"),
        "project_code": project_code,
        "site_name": site_name,
        "po_id": payload.get("po_id"),
        "po_number": payload.get("po_number"),
        "items": items,
        "gst_pct": float(payload.get("gst_pct") or 18),
        "retention_pct": float(payload.get("retention_pct") or 0),
        "tds_pct": float(payload.get("tds_pct") or 0),
        "other_deductions": payload.get("other_deductions") or [],
        "advance_recovery": float(payload.get("advance_recovery") or 0),
        "previous_bill_value": float(payload.get("previous_bill_value") or 0),
        "notes": payload.get("notes"),
    }
    base.update(_compute_totals(base))
    doc = {
        "id": new_id(),
        "bill_number": await next_sequence(_prefix(base["bill_type"])),
        **base,
        "status": "draft",
        "created_by": user["id"], "created_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
        "measurement_ids": list({i["measurement_id"] for i in items if i.get("measurement_id")}),
    }
    bill_dt = "credit_note" if base["bill_type"] == "credit_note" else ("debit_note" if base["bill_type"] == "debit_note" else "ra_bill")
    await stamp_dept_doc(doc, bill_dt)
    await db.ra_bills.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="ra_bills", record_id=doc["id"], after={"bill_number": doc["bill_number"], "net_payable": doc["net_payable"]}, ip=_ip(request))
    return doc


@router.post("/ra-bills")
async def create_ra_bill(payload: RABillIn, request: Request,
                         user: dict = Depends(require_permission("ra_bills", "write"))):
    if payload.bill_type not in BILL_TYPES:
        raise HTTPException(status_code=400, detail=f"bill_type must be one of {BILL_TYPES}")
    if payload.bill_type in ("debit_note", "credit_note"):
        if not payload.against_ra_bill_id:
            raise HTTPException(status_code=400, detail=f"{payload.bill_type} must reference against_ra_bill_id")
        if not payload.reason:
            raise HTTPException(status_code=400, detail=f"{payload.bill_type} requires a reason")
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one line item is required")
    base = payload.model_dump()
    base.pop("submit", None)
    manual_no = (base.pop("bill_number", None) or "").strip()
    if manual_no:
        if await db.ra_bills.find_one({"bill_number": manual_no}, {"_id": 0, "id": 1}):
            raise HTTPException(status_code=400, detail=f"Invoice number '{manual_no}' already exists")
        bill_number = manual_no
    else:
        bill_number = await next_sequence(_prefix(payload.bill_type))
    base.update(_compute_totals(base))
    doc = {
        "id": new_id(),
        "bill_number": bill_number,
        **base,
        "status": "submitted" if payload.submit else "draft",
        "created_by": user["id"], "created_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
        "measurement_ids": list({i["measurement_id"] for i in base["items"] if i.get("measurement_id")}),
    }
    bill_dt = "credit_note" if payload.bill_type == "credit_note" else ("debit_note" if payload.bill_type == "debit_note" else "ra_bill")
    await stamp_dept_doc(doc, bill_dt)
    await db.ra_bills.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="ra_bills", record_id=doc["id"], after={"bill_number": doc["bill_number"], "net_payable": doc["net_payable"]}, ip=_ip(request))
    return doc


@router.put("/ra-bills/{bill_id}")
async def update_ra_bill(bill_id: str, payload: dict, request: Request,
                         user: dict = Depends(require_permission("ra_bills", "write"))):
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Bill not found")
    if row.get("status") not in ("draft", "submitted"):
        raise HTTPException(status_code=400, detail=f"Bill in '{row.get('status')}' cannot be edited")
    for k in ("id", "bill_number", "status", "created_at", "created_by", "approved_by", "approved_at"):
        payload.pop(k, None)
    merged = {**row, **payload}
    # Only recompute totals when the relevant fields are touched
    if any(k in payload for k in ("items", "gst_pct", "retention_pct", "tds_pct", "other_deductions", "advance_recovery", "previous_bill_value")):
        merged.update(_compute_totals(merged))
        for k in ("items", "subtotal", "gst_amount", "gross_value", "retention_amount", "tds_amount", "other_deductions_total", "advance_recovery", "net_payable", "current_bill_value", "cumulative_value"):
            payload[k] = merged[k]
    payload["updated_at"] = now_iso()
    await db.ra_bills.update_one({"id": bill_id}, {"$set": payload})
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    await audit(user=user, action="update", resource="ra_bills", record_id=bill_id, after=row, ip=_ip(request))
    return row


@router.post("/ra-bills/{bill_id}/submit")
async def submit_ra_bill(bill_id: str, request: Request,
                         user: dict = Depends(require_permission("ra_bills", "write"))):
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Bill not found")
    if row.get("status") not in ("draft",):
        raise HTTPException(status_code=400, detail="Only draft bills can be submitted")
    await db.ra_bills.update_one({"id": bill_id}, {"$set": {"status": "submitted", "submitted_at": now_iso(), "updated_at": now_iso()}})
    return await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})


@router.post("/ra-bills/{bill_id}/approve")
async def approve_ra_bill(bill_id: str, request: Request,
                          user: dict = Depends(require_permission("ra_bills", "write"))):
    if user.get("role") not in APPROVE_ROLES:
        raise HTTPException(status_code=403, detail="Only Accounts/PC can approve RA bills")
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Bill not found")
    if row.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"Bill in '{row.get('status')}' cannot be approved")
    now = now_iso()
    await db.ra_bills.update_one({"id": bill_id}, {"$set": {
        "status": "approved", "approved_by": user.get("name") or user.get("email"),
        "approved_by_id": user["id"], "approved_at": now, "updated_at": now,
    }})
    # Flip linked measurements to `billed`
    if row.get("measurement_ids"):
        await db.measurements.update_many({"id": {"$in": row["measurement_ids"]}}, {"$set": {"status": "billed", "billed_at": now, "ra_bill_id": bill_id, "ra_bill_number": row.get("bill_number")}})
    await audit(user=user, action="approve", resource="ra_bills", record_id=bill_id, after={"status": "approved"}, ip=_ip(request))
    return await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})


@router.post("/ra-bills/{bill_id}/issue-invoice")
async def issue_invoice(bill_id: str, payload: dict | None = None, request: Request = None,
                        user: dict = Depends(require_permission("ra_bills", "write"))):
    """Mark approved bill as invoiced (PDF would be generated client-side or via a
    separate service). Optionally record the invoice number issued externally."""
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Bill not found")
    if row.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Only approved bills can be invoiced")
    invoice_no = (payload or {}).get("invoice_no") or row.get("bill_number")
    due_days = int((payload or {}).get("due_days") or 30)
    issue_date = (payload or {}).get("issue_date") or now_iso()[:10]
    due_date = (datetime.fromisoformat(issue_date) + timedelta(days=due_days)).date().isoformat()
    await db.ra_bills.update_one({"id": bill_id}, {"$set": {
        "status": "invoiced", "invoice_no": invoice_no, "issue_date": issue_date,
        "due_date": due_date, "due_days": due_days, "updated_at": now_iso(),
    }})
    updated = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    # Iter 71 — Auto-post sales-invoice JE
    try:
        from accounting_service import post_sales_invoice_issued
        await post_sales_invoice_issued({
            "id": updated["id"],
            "invoice_no": invoice_no,
            "invoice_date": issue_date,
            "amount": float(updated.get("net_payable") or updated.get("total_amount") or 0),
            "tax_amount": float(updated.get("tax_amount") or updated.get("gst_amount") or 0),
            "project_id": updated.get("project_id"),
            "client_name": updated.get("client_name"),
            "department": updated.get("department"),
            "type": "services",
        }, user)
    except Exception as ae:
        import logging
        logging.getLogger("erp").warning(f"[accounting] sales-invoice JE skipped: {ae}")
    return updated


@router.post("/ra-bills/{bill_id}/cancel")
async def cancel_ra_bill(bill_id: str, payload: dict, request: Request,
                         user: dict = Depends(require_permission("ra_bills", "write"))):
    if user.get("role") not in APPROVE_ROLES:
        raise HTTPException(status_code=403, detail="Only Accounts/PC can cancel RA bills")
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Bill not found")
    if row.get("status") == "paid":
        raise HTTPException(status_code=400, detail="Cannot cancel a paid bill — issue a credit note instead")
    reason = (payload or {}).get("reason") or "No reason given"
    await db.ra_bills.update_one({"id": bill_id}, {"$set": {"status": "cancelled", "cancel_reason": reason, "cancelled_at": now_iso(), "updated_at": now_iso()}})
    # Roll back linked measurements if they had been marked `billed`
    if row.get("measurement_ids"):
        await db.measurements.update_many({"id": {"$in": row["measurement_ids"]}, "status": "billed", "ra_bill_id": bill_id}, {"$set": {"status": "approved_for_billing"}, "$unset": {"ra_bill_id": "", "ra_bill_number": "", "billed_at": ""}})
    await audit(user=user, action="cancel", resource="ra_bills", record_id=bill_id, after={"status": "cancelled"}, ip=_ip(request))
    return await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})


@router.delete("/ra-bills/{bill_id}")
async def delete_ra_bill(bill_id: str, request: Request,
                         user: dict = Depends(require_permission("ra_bills", "delete"))):
    row = await db.ra_bills.find_one({"id": bill_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Bill not found")
    if row.get("status") not in ("draft", "cancelled"):
        raise HTTPException(status_code=400, detail="Only draft or cancelled bills can be deleted — use Cancel for issued bills")
    await db.ra_bills.delete_one({"id": bill_id})
    await audit(user=user, action="delete", resource="ra_bills", record_id=bill_id, before=row, ip=_ip(request))
    return {"ok": True}
