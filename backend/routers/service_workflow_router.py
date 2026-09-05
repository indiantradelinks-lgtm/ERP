"""Service Request → Payment Management workflow.

Chain: Service Request → Approval → RFQ → Vendor Quotations → Comparison →
Vendor Selection → PO → Service Execution → SRN → Vendor Invoice →
3-Way Match → Invoice Approval → Payment (via Accounts Payment Processing) → Closed.

Collections: svc_requests, svc_rfqs, svc_pos, svc_srns, svc_invoices.
Approved invoices land in the unified Accounts Payment Processing queue
(project_requests shadow row, source='service_invoice'); mark-paid there calls
on_service_invoice_paid() to cascade Paid → PO → SR closure.
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from core import db, get_current_user, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from approval_engine import build_chain

router = APIRouter(prefix="/service-workflow", tags=["service-workflow"])

SR_APPROVERS = {"super_admin", "director", "general_manager", "dept_head", "project_manager"}
PROC_ROLES = {"super_admin", "purchase_officer", "manager_log", "director", "general_manager"}
SRN_ROLES = PROC_ROLES | {"project_manager", "site_engineer", "supervisor", "dept_head"}
ACCOUNTS_ROLES = {"super_admin", "accounts_executive", "director"}
VIEW_ALL_ROLES = SR_APPROVERS | PROC_ROLES | ACCOUNTS_ROLES | {"hr_executive"}

SR_STATUSES = ["draft", "submitted", "under_review", "approved", "rejected", "sent_back",
               "rfq_created", "po_created", "service_in_progress", "srn_created",
               "invoice_received", "payment_pending", "paid", "closed"]

SERVICE_CATEGORIES = ["Manpower Services", "Equipment Hire", "Transportation", "Scaffolding Services",
                      "Painting Services", "Insulation Services", "Civil Works", "Electrical Works",
                      "Mechanical Works", "IT & Software", "Housekeeping", "Security Services",
                      "Calibration & Testing", "AMC / Maintenance", "Consultancy", "Other"]

AMOUNT_TOL = 1.0  # ₹ tolerance in 3-way matching


def _cat_key(label: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_")[:40]


def _is_transport(category: str) -> bool:
    c = (category or "").lower()
    return "transport" in c or "vehicle" in c


async def get_service_categories(active_only: bool = False) -> dict:
    """Built-in SERVICE_CATEGORIES merged with the Service Category Master overrides."""
    merged = {_cat_key(c): {"label": c, "active": True, "builtin": True} for c in SERVICE_CATEGORIES}
    async for o in db.svc_category_options.find({}, {"_id": 0}):
        k = o.get("key")
        if not k:
            continue
        base = merged.get(k, {"label": o.get("label") or k, "builtin": False})
        if o.get("label"):
            base["label"] = o["label"]
        base["active"] = o.get("active", True)
        merged[k] = base
    if active_only:
        return {k: v for k, v in merged.items() if v.get("active", True)}
    return merged


async def _fresh_sr_chain() -> list:
    """Approval chain for Service Requests, resolved from the Super Admin Approval Matrix."""
    return await build_chain("service_request")


def _validate_submit(d: dict):
    if not (d.get("service_category") and (d.get("service_description") or "").strip()):
        raise HTTPException(400, "Service Category and Description are required to submit")
    if _is_transport(d.get("service_category")) and not (
            (d.get("from_location") or "").strip() and (d.get("to_location") or "").strip()):
        raise HTTPException(400, "From Location and To Location are required for Vehicle/Transport service requests")


def _ip(request: Request | None) -> str:
    try:
        return request.client.host if request and request.client else ""
    except Exception:
        return ""


def _uname(user: dict) -> str:
    return user.get("name") or user.get("email") or ""


def _hist(user: dict, action: str, remarks: str = "", frm: str = "", to: str = "") -> dict:
    return {"at": now_iso(), "by": _uname(user), "by_id": user.get("id"), "role": user.get("role"),
            "action": action, "from": frm, "to": to, "remarks": remarks}


def _require_role(user: dict, roles: set, what: str):
    if user.get("role") not in roles:
        raise HTTPException(403, f"Your role '{user.get('role')}' cannot {what}")


async def _sr(sr_id: str) -> dict:
    r = await db.svc_requests.find_one({"id": sr_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Service Request not found")
    return r


async def _set_sr_status(sr_id: str, status: str, user: dict, action: str, remarks: str = "",
                         extra: Optional[dict] = None):
    sr = await db.svc_requests.find_one({"id": sr_id}, {"_id": 0, "status": 1})
    await db.svc_requests.update_one({"id": sr_id}, {
        "$set": {"status": status, "updated_at": now_iso(), **(extra or {})},
        "$push": {"history": _hist(user, action, remarks, (sr or {}).get("status", ""), status)}})


# ══════════════════════════════ META ══════════════════════════════
@router.get("/meta")
async def workflow_meta(user: dict = Depends(get_current_user)):
    dept_rows = await db.departments.find({}, {"_id": 0, "name": 1, "code": 1}).to_list(300)
    departments = sorted({d.get("name") or d.get("code") for d in dept_rows if d.get("name") or d.get("code")})
    vendors = await db.vendors.find({"status": {"$nin": ["inactive", "blacklisted"]}},
                                    {"_id": 0, "id": 1, "name": 1, "email": 1, "gstin": 1}).sort("name", 1).to_list(2000)
    extra_cats = sorted({v["label"] for v in (await get_service_categories(True)).values()})
    ccs = await db.cost_centers.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1,
                                          "category_name": 1}).sort("code", 1).to_list(1000)
    return {"departments": departments, "vendors": vendors,
            "service_categories": extra_cats,
            "cost_centers": ccs, "priorities": ["Low", "Medium", "High", "Urgent"],
            "sr_statuses": SR_STATUSES,
            "role_caps": {"sr_approver": user.get("role") in SR_APPROVERS,
                          "procurement": user.get("role") in PROC_ROLES,
                          "srn": user.get("role") in SRN_ROLES,
                          "accounts": user.get("role") in ACCOUNTS_ROLES}}


# ══════════════════════════════ SERVICE REQUESTS ══════════════════════════════
class SRIn(BaseModel):
    department: str = ""
    project_code: str = ""
    project_name: str = ""
    site_location: str = ""
    service_category: str = ""
    service_type: str = ""
    service_description: str = ""
    scope_of_work: str = ""
    required_date: str = ""
    priority: str = "Medium"
    estimated_budget: float = 0.0
    cost_center_id: str = ""
    cost_center_label: str = ""
    from_location: str = ""
    to_location: str = ""
    remarks: str = ""
    submit: bool = False


@router.post("/requests")
async def create_request(p: SRIn, request: Request,
                         user: dict = Depends(require_permission("service_workflow", "write"))):
    if p.submit:
        _validate_submit(p.dict())
    status = "submitted" if p.submit else "draft"
    chain = await _fresh_sr_chain() if p.submit else []
    doc = {**p.dict(exclude={"submit"}), "id": new_id(),
           "sr_no": await next_sequence("SVC"),
           "request_date": now_iso()[:10], "status": status,
           "approval_chain": chain, "approval_step": 0,
           "requester_id": user.get("id"), "requester_name": _uname(user), "requester_role": user.get("role"),
           "current_owner": (chain[0]["label"] if chain else "Approver") if p.submit else _uname(user),
           "rfq_id": None, "po_ids": [],
           "history": [_hist(user, "created" if not p.submit else "created_and_submitted", "", "", status)],
           "created_by": _uname(user), "created_by_id": user.get("id"),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_requests.insert_one(dict(doc))
    await audit(user=user, action="svc_request_create", resource="service_workflow",
                record_id=doc["id"], after={"sr_no": doc["sr_no"], "status": status}, ip=_ip(request))
    return doc


@router.get("/requests")
async def list_requests(status: str = "", department: str = "", site: str = "", category: str = "",
                        requester: str = "", project: str = "", q: str = "",
                        date_from: str = "", date_to: str = "",
                        user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if user.get("role") not in VIEW_ALL_ROLES:
        fl["requester_id"] = user.get("id")
    if status:
        fl["status"] = status
    if department:
        fl["department"] = department
    if site:
        fl["site_location"] = site
    if category:
        fl["service_category"] = category
    if requester:
        fl["requester_name"] = {"$regex": requester, "$options": "i"}
    if project:
        fl["project_code"] = project
    if date_from or date_to:
        fl["request_date"] = {**({"$gte": date_from} if date_from else {}),
                              **({"$lte": date_to} if date_to else {})}
    if q:
        fl["$or"] = [{"sr_no": {"$regex": q, "$options": "i"}},
                     {"service_description": {"$regex": q, "$options": "i"}},
                     {"service_type": {"$regex": q, "$options": "i"}}]
    return await db.svc_requests.find(fl, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(1000)


@router.get("/requests/{sr_id}")
async def request_detail(sr_id: str, user: dict = Depends(require_permission("service_workflow", "read"))):
    sr = await _sr(sr_id)
    if user.get("role") not in VIEW_ALL_ROLES and sr.get("requester_id") != user.get("id"):
        raise HTTPException(403, "You can only view your own Service Requests")
    rfq = await db.svc_rfqs.find_one({"sr_id": sr_id}, {"_id": 0})
    pos = await db.svc_pos.find({"sr_id": sr_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    srns = await db.svc_srns.find({"sr_id": sr_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    invoices = await db.svc_invoices.find({"sr_id": sr_id}, {"_id": 0}).sort("created_at", 1).to_list(100)
    inv_ids = [i["id"] for i in invoices]
    stages = {}
    if inv_ids:
        async for pr in db.project_requests.find({"source": "service_invoice", "source_id": {"$in": inv_ids}},
                                                 {"_id": 0, "source_id": 1, "id": 1}):
            v = await db.payment_verifications.find_one({"request_id": pr["id"]}, {"_id": 0, "stage": 1, "utr_no": 1, "paid_date": 1})
            stages[pr["source_id"]] = v or {"stage": "pending_verification"}
    for i in invoices:
        i["payment_stage"] = stages.get(i["id"])
    timeline = []
    for src, docs in [("Service Request", [sr]), ("RFQ", [rfq] if rfq else []), ("PO", pos),
                      ("SRN", srns), ("Invoice", invoices)]:
        for d in docs:
            ref = d.get("sr_no") or d.get("rfq_no") or d.get("po_no") or d.get("srn_no") or d.get("inv_no")
            for h in d.get("history") or []:
                timeline.append({**h, "doc": src, "ref": ref})
    timeline.sort(key=lambda x: x.get("at") or "")
    return {"request": sr, "rfq": rfq, "pos": pos, "srns": srns, "invoices": invoices, "timeline": timeline}


@router.put("/requests/{sr_id}")
async def update_request(sr_id: str, p: SRIn, request: Request,
                         user: dict = Depends(require_permission("service_workflow", "write"))):
    sr = await _sr(sr_id)
    if sr["status"] not in ("draft", "sent_back", "rejected"):
        raise HTTPException(400, f"Cannot edit a request in status '{sr['status']}'")
    if sr.get("requester_id") != user.get("id") and user.get("role") != "super_admin":
        raise HTTPException(403, "Only the requester can edit this request")
    status = "submitted" if p.submit else sr["status"]
    if p.submit:
        _validate_submit(p.dict())
    upd = {**p.dict(exclude={"submit"}), "status": status, "updated_at": now_iso()}
    if p.submit:
        chain = await _fresh_sr_chain()
        upd.update({"approval_chain": chain, "approval_step": 0,
                    "current_owner": chain[0]["label"] if chain else "Approver"})
    await db.svc_requests.update_one({"id": sr_id}, {
        "$set": upd,
        "$push": {"history": _hist(user, "resubmitted" if p.submit else "updated", "", sr["status"], status)}})
    await audit(user=user, action="svc_request_update", resource="service_workflow",
                record_id=sr_id, after={"status": status}, ip=_ip(request))
    return await _sr(sr_id)


@router.post("/requests/{sr_id}/submit")
async def submit_request(sr_id: str, request: Request,
                         user: dict = Depends(require_permission("service_workflow", "write"))):
    sr = await _sr(sr_id)
    if sr["status"] not in ("draft", "sent_back", "rejected"):
        raise HTTPException(400, f"Cannot submit from status '{sr['status']}'")
    _validate_submit(sr)
    chain = await _fresh_sr_chain()
    await _set_sr_status(sr_id, "submitted", user, "submitted",
                         extra={"approval_chain": chain, "approval_step": 0,
                                "current_owner": chain[0]["label"] if chain else "Approver"})
    await audit(user=user, action="svc_request_submit", resource="service_workflow",
                record_id=sr_id, after={"sr_no": sr["sr_no"]}, ip=_ip(request))
    return await _sr(sr_id)


class ActionIn(BaseModel):
    action: str  # approve | reject | send_back
    remarks: str = ""


@router.post("/requests/{sr_id}/action")
async def approve_request(sr_id: str, p: ActionIn, request: Request,
                          user: dict = Depends(get_current_user)):
    sr = await _sr(sr_id)
    if sr["status"] not in ("submitted", "under_review"):
        raise HTTPException(400, f"Request is not awaiting approval (status '{sr['status']}')")
    if p.action not in ("approve", "reject", "send_back"):
        raise HTTPException(400, "action must be approve | reject | send_back")
    if p.action in ("reject", "send_back") and not p.remarks.strip():
        raise HTTPException(400, "Remarks are required when rejecting or sending back")
    if sr.get("requester_id") == user.get("id") and user.get("role") != "super_admin":
        raise HTTPException(403, "You cannot approve your own service request — it is routed via the Approval Matrix")
    # Chain resolved from the Super Admin Approval Matrix (type 'service_request')
    chain = sr.get("approval_chain") or await _fresh_sr_chain()
    idx = int(sr.get("approval_step") or 0)
    if idx >= len(chain):
        idx = max(len(chain) - 1, 0)
    step = chain[idx]
    if user.get("role") not in (step.get("role"), "super_admin"):
        raise HTTPException(403, f"This request is awaiting '{step.get('label')}' ({step.get('role')}) "
                                 f"per the Approval Matrix — your role '{user.get('role')}' cannot act on this step")
    step.update({"status": {"approve": "approved", "reject": "rejected", "send_back": "sent_back"}[p.action],
                 "approver": _uname(user), "approver_role": user.get("role"),
                 "at": now_iso(), "comment": p.remarks})
    chain[idx] = step
    if p.action == "approve":
        idx += 1
        if idx >= len(chain):
            to, owner = "approved", "Logistics / Procurement"
        else:
            to, owner = "under_review", chain[idx].get("label") or chain[idx].get("role")
    else:
        to = "rejected" if p.action == "reject" else "sent_back"
        owner = sr.get("requester_name")
    extra = {"approval_chain": chain, "approval_step": idx, "current_owner": owner}
    if to == "approved":
        extra["approval"] = {"action": "approve", "by": _uname(user), "role": user.get("role"),
                             "at": now_iso(), "remarks": p.remarks}
    action_label = (f"sr_step_{idx}_approved" if (p.action == "approve" and to == "under_review")
                    else f"sr_{p.action}")
    remarks = p.remarks if p.remarks else (f"Step '{step.get('label')}' cleared" if p.action == "approve" else "")
    await _set_sr_status(sr_id, to, user, action_label, remarks, extra)
    await audit(user=user, action=f"svc_request_{p.action}", resource="service_workflow",
                record_id=sr_id, after={"sr_no": sr["sr_no"], "step": step.get("label"),
                                        "remarks": p.remarks}, ip=_ip(request))
    return await _sr(sr_id)


class InboxActionIn(BaseModel):
    remarks: Optional[str] = ""


@router.post("/requests/{sr_id}/inbox-approve")
async def inbox_approve(sr_id: str, p: InboxActionIn, request: Request,
                        user: dict = Depends(get_current_user)):
    """Approve wrapper for the unified My Pending Approvals inbox."""
    return await approve_request(sr_id, ActionIn(action="approve", remarks=p.remarks or ""), request, user)


@router.post("/requests/{sr_id}/inbox-reject")
async def inbox_reject(sr_id: str, p: InboxActionIn, request: Request,
                       user: dict = Depends(get_current_user)):
    if not (p.remarks or "").strip():
        raise HTTPException(400, "Rejection reason is required")
    return await approve_request(sr_id, ActionIn(action="reject", remarks=p.remarks or ""), request, user)


@router.post("/requests/{sr_id}/close")
async def close_request(sr_id: str, p: ActionIn, request: Request,
                        user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES | ACCOUNTS_ROLES, "close service requests")
    sr = await _sr(sr_id)
    if sr["status"] == "closed":
        raise HTTPException(400, "Already closed")
    open_inv = await db.svc_invoices.count_documents(
        {"sr_id": sr_id, "status": {"$nin": ["paid", "rejected"]}})
    if open_inv and user.get("role") != "super_admin":
        raise HTTPException(400, f"{open_inv} invoice(s) still unpaid — only Super Admin can force-close")
    await _set_sr_status(sr_id, "closed", user, "closed", p.remarks, {"closed_at": now_iso()})
    await audit(user=user, action="svc_request_close", resource="service_workflow",
                record_id=sr_id, after={"sr_no": sr["sr_no"]}, ip=_ip(request))
    return await _sr(sr_id)


# ══════════════════════════════ RFQ ══════════════════════════════
class RfqIn(BaseModel):
    vendor_ids: List[str]
    scope_of_work: str = ""
    service_requirements: str = ""
    required_completion_date: str = ""
    commercial_terms: str = ""
    technical_terms: str = ""
    taxes_notes: str = ""


@router.post("/requests/{sr_id}/rfq")
async def create_rfq(sr_id: str, p: RfqIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "create RFQs")
    sr = await _sr(sr_id)
    if sr["status"] != "approved":
        raise HTTPException(400, f"RFQ can only be created from an APPROVED request (status '{sr['status']}')")
    if not p.vendor_ids:
        raise HTTPException(400, "Select at least one vendor")
    vendors = await db.vendors.find({"id": {"$in": p.vendor_ids}},
                                    {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(100)
    if len(vendors) != len(set(p.vendor_ids)):
        raise HTTPException(400, "One or more vendors not found")
    doc = {"id": new_id(), "rfq_no": await next_sequence("SRFQ"), "rfq_date": now_iso()[:10],
           "sr_id": sr_id, "sr_no": sr["sr_no"],
           "service_category": sr.get("service_category"), "service_type": sr.get("service_type"),
           "project_code": sr.get("project_code"), "project_name": sr.get("project_name"),
           "site_location": sr.get("site_location"), "department": sr.get("department"),
           "scope_of_work": p.scope_of_work or sr.get("scope_of_work") or "",
           "service_requirements": p.service_requirements,
           "required_completion_date": p.required_completion_date or sr.get("required_date") or "",
           "commercial_terms": p.commercial_terms, "technical_terms": p.technical_terms,
           "taxes_notes": p.taxes_notes,
           "vendors": [{"vendor_id": v["id"], "vendor_name": v["name"], "vendor_email": v.get("email"),
                        "issued_at": None, "quotation": None} for v in vendors],
           "status": "draft", "recommended_vendor_id": None, "recommendation_remarks": "",
           "history": [_hist(user, "rfq_created", "", "", "draft")],
           "created_by": _uname(user), "created_by_id": user.get("id"),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_rfqs.insert_one(dict(doc))
    await _set_sr_status(sr_id, "rfq_created", user, "rfq_created", f"RFQ {doc['rfq_no']}",
                         {"rfq_id": doc["id"], "current_owner": "Procurement"})
    await audit(user=user, action="svc_rfq_create", resource="service_workflow",
                record_id=doc["id"], after={"rfq_no": doc["rfq_no"], "sr_no": sr["sr_no"]}, ip=_ip(request))
    return doc


@router.get("/rfqs")
async def list_rfqs(status: str = "", q: str = "",
                    user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if status:
        fl["status"] = status
    if q:
        fl["$or"] = [{"rfq_no": {"$regex": q, "$options": "i"}}, {"sr_no": {"$regex": q, "$options": "i"}}]
    return await db.svc_rfqs.find(fl, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)


async def _rfq(rfq_id: str) -> dict:
    r = await db.svc_rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "RFQ not found")
    return r


@router.post("/rfqs/{rfq_id}/issue")
async def issue_rfq(rfq_id: str, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "issue RFQs")
    rfq = await _rfq(rfq_id)
    if rfq["status"] not in ("draft", "issued"):
        raise HTTPException(400, f"RFQ already {rfq['status']}")
    ts = now_iso()
    vendors = [{**v, "issued_at": v.get("issued_at") or ts} for v in rfq["vendors"]]
    await db.svc_rfqs.update_one({"id": rfq_id}, {
        "$set": {"vendors": vendors, "status": "issued", "updated_at": ts},
        "$push": {"history": _hist(user, "rfq_issued", f"Issued to {len(vendors)} vendor(s)", rfq["status"], "issued")}})
    await audit(user=user, action="svc_rfq_issue", resource="service_workflow",
                record_id=rfq_id, after={"rfq_no": rfq["rfq_no"]}, ip=_ip(request))
    return await _rfq(rfq_id)


class QuoteIn(BaseModel):
    vendor_id: str
    amount: float
    tax_pct: float = 18.0
    other_charges: float = 0.0
    timeline_days: Optional[int] = None
    validity_date: str = ""
    payment_terms: str = ""
    commercial_terms: str = ""
    technical_compliance: str = "compliant"  # compliant | partial | non_compliant
    remarks: str = ""


@router.post("/rfqs/{rfq_id}/quotation")
async def record_quotation(rfq_id: str, p: QuoteIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "record vendor quotations")
    rfq = await _rfq(rfq_id)
    if rfq["status"] in ("selection_approved", "po_created", "rejected"):
        raise HTTPException(400, f"RFQ is {rfq['status']} — quotations locked")
    if p.amount <= 0:
        raise HTTPException(400, "Quotation amount must be > 0")
    tax_amount = round(p.amount * p.tax_pct / 100, 2)
    total = round(p.amount + tax_amount + p.other_charges, 2)
    found = False
    vendors = []
    for v in rfq["vendors"]:
        if v["vendor_id"] == p.vendor_id:
            found = True
            v = {**v, "quotation": {**p.dict(exclude={"vendor_id"}), "tax_amount": tax_amount,
                                    "total": total, "submitted_at": now_iso(), "recorded_by": _uname(user)}}
        vendors.append(v)
    if not found:
        raise HTTPException(400, "Vendor is not part of this RFQ")
    quoted = sum(1 for v in vendors if v.get("quotation"))
    status = "quotations_received" if quoted else rfq["status"]
    await db.svc_rfqs.update_one({"id": rfq_id}, {
        "$set": {"vendors": vendors, "status": status, "updated_at": now_iso()},
        "$push": {"history": _hist(user, "quotation_recorded",
                                   f"{next(v['vendor_name'] for v in vendors if v['vendor_id'] == p.vendor_id)} — ₹{total:,.2f}")}})
    await audit(user=user, action="svc_rfq_quotation", resource="service_workflow",
                record_id=rfq_id, after={"vendor_id": p.vendor_id, "total": total}, ip=_ip(request))
    return await _rfq(rfq_id)


@router.get("/rfqs/{rfq_id}/comparison")
async def rfq_comparison(rfq_id: str, user: dict = Depends(require_permission("service_workflow", "read"))):
    rfq = await _rfq(rfq_id)
    rows = []
    for v in rfq["vendors"]:
        q = v.get("quotation")
        rows.append({"vendor_id": v["vendor_id"], "vendor_name": v["vendor_name"],
                     "issued_at": v.get("issued_at"), "has_quote": bool(q), **(q or {})})
    quoted = sorted([r for r in rows if r["has_quote"]], key=lambda x: x.get("total") or 0)
    lowest = quoted[0]["vendor_id"] if quoted else None
    return {"rfq": {k: rfq[k] for k in ("id", "rfq_no", "sr_no", "status", "scope_of_work",
                                        "recommended_vendor_id", "recommendation_remarks")},
            "rows": quoted + [r for r in rows if not r["has_quote"]], "lowest_vendor_id": lowest}


class RecommendIn(BaseModel):
    vendor_id: str
    remarks: str = ""


@router.post("/rfqs/{rfq_id}/recommend")
async def recommend_vendor(rfq_id: str, p: RecommendIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "recommend vendors")
    rfq = await _rfq(rfq_id)
    v = next((x for x in rfq["vendors"] if x["vendor_id"] == p.vendor_id), None)
    if not v or not v.get("quotation"):
        raise HTTPException(400, "Selected vendor has no recorded quotation")
    if rfq["status"] in ("selection_approved", "po_created"):
        raise HTTPException(400, "Vendor selection already finalised")
    await db.svc_rfqs.update_one({"id": rfq_id}, {
        "$set": {"status": "recommended", "recommended_vendor_id": p.vendor_id,
                 "recommendation_remarks": p.remarks, "updated_at": now_iso()},
        "$push": {"history": _hist(user, "vendor_recommended", f"{v['vendor_name']} · {p.remarks}")}})
    await audit(user=user, action="svc_rfq_recommend", resource="service_workflow",
                record_id=rfq_id, after={"vendor": v["vendor_name"]}, ip=_ip(request))
    return await _rfq(rfq_id)


@router.post("/rfqs/{rfq_id}/selection-action")
async def selection_action(rfq_id: str, p: ActionIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, SR_APPROVERS, "approve vendor selection")
    rfq = await _rfq(rfq_id)
    if rfq["status"] != "recommended":
        raise HTTPException(400, "No vendor recommendation pending approval")
    if p.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve | reject")
    to = "selection_approved" if p.action == "approve" else "quotations_received"
    upd = {"status": to, "updated_at": now_iso(),
           "selection_approval": {"action": p.action, "by": _uname(user), "role": user.get("role"),
                                  "at": now_iso(), "remarks": p.remarks}}
    if p.action == "reject":
        upd["recommended_vendor_id"] = None
    await db.svc_rfqs.update_one({"id": rfq_id}, {
        "$set": upd, "$push": {"history": _hist(user, f"selection_{p.action}", p.remarks, rfq["status"], to)}})
    await audit(user=user, action=f"svc_rfq_selection_{p.action}", resource="service_workflow",
                record_id=rfq_id, after={"rfq_no": rfq["rfq_no"]}, ip=_ip(request))
    return await _rfq(rfq_id)


# ══════════════════════════════ PO ══════════════════════════════
class PoIn(BaseModel):
    rate: float = 0.0
    quantity: float = 1.0
    unit: str = "Lot"
    tax_pct: float = 18.0
    other_charges: float = 0.0
    service_period_from: str = ""
    service_period_to: str = ""
    completion_date: str = ""
    payment_terms: str = ""
    terms_conditions: str = ""
    terms_id: str = ""
    exception_override: bool = False
    exception_note: str = ""


@router.post("/rfqs/{rfq_id}/po")
async def create_po(rfq_id: str, p: PoIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "create Service POs")
    rfq = await _rfq(rfq_id)
    if rfq["status"] == "po_created":
        raise HTTPException(400, "PO already created for this RFQ")
    if rfq["status"] != "selection_approved":
        if not (p.exception_override and user.get("role") in ("super_admin", "director")):
            raise HTTPException(400, "PO requires an approved vendor selection "
                                     "(exception override available to Super Admin / Director only)")
        if not p.exception_note.strip():
            raise HTTPException(400, "Exception note is required for override")
    vid = rfq.get("recommended_vendor_id")
    v = next((x for x in rfq["vendors"] if x["vendor_id"] == vid), None)
    if not v:
        raise HTTPException(400, "No selected vendor on this RFQ")
    q = v.get("quotation") or {}
    rate = p.rate or float(q.get("amount") or 0)
    subtotal = round(rate * p.quantity, 2) if p.rate else round(float(q.get("amount") or 0), 2)
    tax_pct = p.tax_pct if p.rate else float(q.get("tax_pct") or p.tax_pct)
    tax_amount = round(subtotal * tax_pct / 100, 2)
    other = p.other_charges if p.rate else float(q.get("other_charges") or 0)
    total = round(subtotal + tax_amount + other, 2)
    sr = await _sr(rfq["sr_id"])
    terms_text = p.terms_conditions
    terms_title = ""
    if p.terms_id:
        t = await db.svc_terms_master.find_one({"id": p.terms_id}, {"_id": 0})
        if not t:
            raise HTTPException(400, "Selected Terms & Conditions template not found")
        terms_title = t.get("title") or ""
        if not terms_text.strip():
            terms_text = t.get("body") or ""
    doc = {"id": new_id(), "po_no": await next_sequence("SPO"), "po_date": now_iso()[:10],
           "rfq_id": rfq_id, "rfq_no": rfq["rfq_no"], "sr_id": rfq["sr_id"], "sr_no": rfq["sr_no"],
           "vendor_id": vid, "vendor_name": v["vendor_name"],
           "project_code": rfq.get("project_code"), "project_name": rfq.get("project_name"),
           "site_location": rfq.get("site_location"), "department": rfq.get("department"),
           "scope_of_work": rfq.get("scope_of_work"), "service_details": sr.get("service_description"),
           "rate": rate, "quantity": p.quantity, "unit": p.unit,
           "subtotal": subtotal, "tax_pct": tax_pct, "tax_amount": tax_amount,
           "other_charges": other, "total_value": total,
           "service_period_from": p.service_period_from, "service_period_to": p.service_period_to,
           "completion_date": p.completion_date or rfq.get("required_completion_date") or "",
           "payment_terms": p.payment_terms or q.get("payment_terms") or "",
           "terms_conditions": terms_text, "terms_id": p.terms_id, "terms_title": terms_title,
           "exception_note": p.exception_note if rfq["status"] != "selection_approved" else "",
           "status": "draft", "accepted_pct_total": 0.0, "invoiced_total": 0.0,
           "paid_amount": 0.0, "payment_status": "unpaid",
           "history": [_hist(user, "po_created", "", "", "draft")],
           "created_by": _uname(user), "created_by_id": user.get("id"),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_pos.insert_one(dict(doc))
    await db.svc_rfqs.update_one({"id": rfq_id}, {
        "$set": {"status": "po_created", "po_id": doc["id"], "po_no": doc["po_no"], "updated_at": now_iso()},
        "$push": {"history": _hist(user, "po_created", doc["po_no"])}})
    await _set_sr_status(rfq["sr_id"], "po_created", user, "po_created", doc["po_no"],
                         {"current_owner": "Procurement"})
    await db.svc_requests.update_one({"id": rfq["sr_id"]}, {"$push": {"po_ids": doc["id"]}})
    await audit(user=user, action="svc_po_create", resource="service_workflow",
                record_id=doc["id"], after={"po_no": doc["po_no"], "total": total}, ip=_ip(request))
    return doc


@router.get("/pos")
async def list_pos(status: str = "", vendor: str = "", q: str = "",
                   user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if status:
        fl["status"] = status
    if vendor:
        fl["vendor_name"] = {"$regex": vendor, "$options": "i"}
    if q:
        fl["$or"] = [{"po_no": {"$regex": q, "$options": "i"}}, {"sr_no": {"$regex": q, "$options": "i"}},
                     {"vendor_name": {"$regex": q, "$options": "i"}}]
    return await db.svc_pos.find(fl, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)


async def _po(po_id: str) -> dict:
    r = await db.svc_pos.find_one({"id": po_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Service PO not found")
    return r


@router.post("/pos/{po_id}/submit")
async def submit_po(po_id: str, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "submit POs")
    po = await _po(po_id)
    if po["status"] != "draft":
        raise HTTPException(400, f"Only draft POs can be submitted (status '{po['status']}')")
    await db.svc_pos.update_one({"id": po_id}, {
        "$set": {"status": "pending_approval", "updated_at": now_iso()},
        "$push": {"history": _hist(user, "po_submitted", "", "draft", "pending_approval")}})
    return await _po(po_id)


@router.post("/pos/{po_id}/action")
async def po_action(po_id: str, p: ActionIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, SR_APPROVERS, "approve POs")
    po = await _po(po_id)
    if po["status"] != "pending_approval":
        raise HTTPException(400, "PO is not pending approval")
    if p.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve | reject")
    to = "approved" if p.action == "approve" else "draft"
    await db.svc_pos.update_one({"id": po_id}, {
        "$set": {"status": to, "updated_at": now_iso(),
                 "po_approval": {"action": p.action, "by": _uname(user), "role": user.get("role"),
                                 "at": now_iso(), "remarks": p.remarks}},
        "$push": {"history": _hist(user, f"po_{p.action}", p.remarks, "pending_approval", to)}})
    await audit(user=user, action=f"svc_po_{p.action}", resource="service_workflow",
                record_id=po_id, after={"po_no": po["po_no"]}, ip=_ip(request))
    return await _po(po_id)


@router.post("/pos/{po_id}/issue")
async def issue_po(po_id: str, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "issue POs")
    po = await _po(po_id)
    if po["status"] != "approved":
        raise HTTPException(400, f"Only approved POs can be issued (status '{po['status']}')")
    await db.svc_pos.update_one({"id": po_id}, {
        "$set": {"status": "issued", "issued_at": now_iso(), "updated_at": now_iso()},
        "$push": {"history": _hist(user, "po_issued", "", "approved", "issued")}})
    await _set_sr_status(po["sr_id"], "service_in_progress", user, "service_started",
                         f"PO {po['po_no']} issued to {po['vendor_name']}",
                         {"current_owner": "Site / Service Team"})
    await audit(user=user, action="svc_po_issue", resource="service_workflow",
                record_id=po_id, after={"po_no": po["po_no"]}, ip=_ip(request))
    return await _po(po_id)


# ══════════════════════════════ TERMS & CONDITIONS MASTER ══════════════════════════════
class TermIn(BaseModel):
    title: str
    body: str
    active: bool = True


@router.get("/terms")
async def list_terms(active: bool = False,
                     user: dict = Depends(require_permission("service_workflow", "read"))):
    fl = {"active": True} if active else {}
    return await db.svc_terms_master.find(fl, {"_id": 0}).sort("title", 1).to_list(200)


@router.post("/terms")
async def create_term(p: TermIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "manage the Terms & Conditions master")
    if not p.title.strip() or not p.body.strip():
        raise HTTPException(400, "Title and Terms body are required")
    doc = {"id": new_id(), "title": p.title.strip(), "body": p.body.strip(), "active": p.active,
           "created_by": _uname(user), "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_terms_master.insert_one(dict(doc))
    await audit(user=user, action="svc_terms_create", resource="service_workflow",
                record_id=doc["id"], after={"title": doc["title"]}, ip=_ip(request))
    return doc


@router.put("/terms/{tid}")
async def update_term(tid: str, p: TermIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "manage the Terms & Conditions master")
    if not p.title.strip() or not p.body.strip():
        raise HTTPException(400, "Title and Terms body are required")
    r = await db.svc_terms_master.update_one({"id": tid}, {"$set": {
        "title": p.title.strip(), "body": p.body.strip(), "active": p.active,
        "updated_by": _uname(user), "updated_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, "Terms template not found")
    await audit(user=user, action="svc_terms_update", resource="service_workflow",
                record_id=tid, after={"title": p.title}, ip=_ip(request))
    return await db.svc_terms_master.find_one({"id": tid}, {"_id": 0})


@router.delete("/terms/{tid}")
async def delete_term(tid: str, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, PROC_ROLES, "manage the Terms & Conditions master")
    r = await db.svc_terms_master.delete_one({"id": tid})
    if not r.deleted_count:
        raise HTTPException(404, "Terms template not found")
    await audit(user=user, action="svc_terms_delete", resource="service_workflow",
                record_id=tid, ip=_ip(request))
    return {"ok": True}


@router.get("/pos/{po_id}/pdf")
async def service_po_pdf(po_id: str,
                         user: dict = Depends(require_permission("service_workflow", "read"))):
    po = await _po(po_id)
    vendor = await db.vendors.find_one({"id": po.get("vendor_id")}, {"_id": 0})
    sr = await db.svc_requests.find_one({"id": po.get("sr_id")}, {"_id": 0})
    from pdf_generator import render_service_po_pdf
    pdf = render_service_po_pdf(po, vendor, sr)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{po["po_no"]}.pdf"'})


# ══════════════════════════════ SRN ══════════════════════════════
class SrnIn(BaseModel):
    receipt_date: str = ""
    service_details: str = ""
    completed_pct: float = 0.0
    accepted_pct: float = 0.0
    receipt_type: str = "partial"  # partial | full
    quality_status: str = "accepted"  # accepted | accepted_with_remarks | rejected
    remarks: str = ""
    submit: bool = True


@router.post("/pos/{po_id}/srn")
async def create_srn(po_id: str, p: SrnIn, request: Request, user: dict = Depends(get_current_user)):
    po = await _po(po_id)
    sr = await _sr(po["sr_id"])
    allowed = user.get("role") in SRN_ROLES or user.get("id") == sr.get("requester_id")
    if not allowed:
        raise HTTPException(403, "Only site/service team, procurement or the requester can create SRNs")
    if po["status"] not in ("issued", "in_progress"):
        raise HTTPException(400, f"SRN requires an issued PO (status '{po['status']}')")
    if not (0 < p.accepted_pct <= 100) or not (0 < p.completed_pct <= 100):
        raise HTTPException(400, "Completed/Accepted % must be between 0 and 100")
    if p.accepted_pct > p.completed_pct:
        raise HTTPException(400, "Accepted % cannot exceed Completed %")
    remaining = 100.0 - float(po.get("accepted_pct_total") or 0)
    if p.accepted_pct > remaining + 0.001:
        raise HTTPException(400, f"Only {remaining:.1f}% of this PO remains un-received")
    status = "submitted" if p.submit else "draft"
    doc = {**p.dict(exclude={"submit"}), "id": new_id(), "srn_no": await next_sequence("SSRN"),
           "receipt_date": p.receipt_date or now_iso()[:10],
           "po_id": po_id, "po_no": po["po_no"], "sr_id": po["sr_id"], "sr_no": po["sr_no"],
           "rfq_no": po.get("rfq_no"), "vendor_id": po.get("vendor_id"), "vendor_name": po["vendor_name"],
           "project_code": po.get("project_code"), "site_location": po.get("site_location"),
           "status": status, "history": [_hist(user, "srn_created", "", "", status)],
           "created_by": _uname(user), "created_by_id": user.get("id"),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_srns.insert_one(dict(doc))
    if po["status"] == "issued":
        await db.svc_pos.update_one({"id": po_id}, {"$set": {"status": "in_progress", "updated_at": now_iso()},
                                                    "$push": {"history": _hist(user, "service_in_progress")}})
    await audit(user=user, action="svc_srn_create", resource="service_workflow",
                record_id=doc["id"], after={"srn_no": doc["srn_no"], "accepted_pct": p.accepted_pct}, ip=_ip(request))
    return doc


@router.get("/srns")
async def list_srns(status: str = "", q: str = "",
                    user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if status:
        fl["status"] = status
    if q:
        fl["$or"] = [{"srn_no": {"$regex": q, "$options": "i"}}, {"po_no": {"$regex": q, "$options": "i"}},
                     {"sr_no": {"$regex": q, "$options": "i"}}]
    return await db.svc_srns.find(fl, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)


async def _srn(srn_id: str) -> dict:
    r = await db.svc_srns.find_one({"id": srn_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "SRN not found")
    return r


@router.post("/srns/{srn_id}/submit")
async def submit_srn(srn_id: str, request: Request, user: dict = Depends(get_current_user)):
    srn = await _srn(srn_id)
    if srn["status"] != "draft":
        raise HTTPException(400, "Only draft SRNs can be submitted")
    await db.svc_srns.update_one({"id": srn_id}, {
        "$set": {"status": "submitted", "updated_at": now_iso()},
        "$push": {"history": _hist(user, "srn_submitted", "", "draft", "submitted")}})
    return await _srn(srn_id)


@router.post("/srns/{srn_id}/action")
async def srn_action(srn_id: str, p: ActionIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, SR_APPROVERS | PROC_ROLES, "verify SRNs")
    srn = await _srn(srn_id)
    if srn["status"] != "submitted":
        raise HTTPException(400, f"SRN is not awaiting verification (status '{srn['status']}')")
    if p.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve | reject")
    if p.action == "reject" and not p.remarks.strip():
        raise HTTPException(400, "Remarks required to reject an SRN")
    to = "approved" if p.action == "approve" else "rejected"
    await db.svc_srns.update_one({"id": srn_id}, {
        "$set": {"status": to, "updated_at": now_iso(),
                 "verification": {"action": p.action, "by": _uname(user), "role": user.get("role"),
                                  "at": now_iso(), "remarks": p.remarks}},
        "$push": {"history": _hist(user, f"srn_{p.action}", p.remarks, "submitted", to)}})
    if to == "approved":
        agg = db.svc_srns.aggregate([{"$match": {"po_id": srn["po_id"], "status": "approved"}},
                                     {"$group": {"_id": None, "t": {"$sum": "$accepted_pct"}}}])
        total = 0.0
        async for a in agg:
            total = float(a.get("t") or 0)
        po_upd = {"accepted_pct_total": min(total, 100.0), "updated_at": now_iso()}
        if total >= 99.999:
            po_upd["status"] = "completed"
        await db.svc_pos.update_one({"id": srn["po_id"]}, {"$set": po_upd})
        sr = await _sr(srn["sr_id"])
        if sr["status"] in ("service_in_progress", "po_created"):
            await _set_sr_status(srn["sr_id"], "srn_created", user, "srn_approved", srn["srn_no"])
    await audit(user=user, action=f"svc_srn_{p.action}", resource="service_workflow",
                record_id=srn_id, after={"srn_no": srn["srn_no"]}, ip=_ip(request))
    return await _srn(srn_id)


# ══════════════════════════════ INVOICE + 3-WAY MATCH ══════════════════════════════
class InvoiceIn(BaseModel):
    po_id: str
    srn_id: str
    vendor_invoice_no: str
    invoice_date: str = ""
    invoice_amount: float = 0.0
    tax_amount: float = 0.0
    other_charges: float = 0.0
    tds_amount: float = 0.0
    due_date: str = ""
    remarks: str = ""


def _three_way_match(po: dict, srn: dict, p: InvoiceIn) -> dict:
    mismatches = []
    if po["status"] not in ("issued", "in_progress", "completed"):
        mismatches.append(f"PO {po['po_no']} is not issued/active (status {po['status']})")
    if srn["status"] != "approved":
        mismatches.append(f"SRN {srn['srn_no']} is not approved (status {srn['status']})")
    if srn.get("po_id") != po["id"]:
        mismatches.append("SRN does not belong to the referenced PO")
    if srn.get("vendor_id") and po.get("vendor_id") and srn["vendor_id"] != po["vendor_id"]:
        mismatches.append("Vendor mismatch between PO and SRN")
    gross = round(p.invoice_amount + p.tax_amount + p.other_charges, 2)
    entitled = round(float(po.get("total_value") or 0) * float(po.get("accepted_pct_total") or 0) / 100
                     - float(po.get("invoiced_total") or 0), 2)
    if gross > entitled + AMOUNT_TOL:
        mismatches.append(f"Invoice gross ₹{gross:,.2f} exceeds un-invoiced accepted value ₹{max(entitled, 0):,.2f}")
    expected_tax = round(p.invoice_amount * float(po.get("tax_pct") or 0) / 100, 2)
    if abs(p.tax_amount - expected_tax) > max(AMOUNT_TOL, expected_tax * 0.02):
        mismatches.append(f"Tax ₹{p.tax_amount:,.2f} deviates from PO tax rate ({po.get('tax_pct')}% → ₹{expected_tax:,.2f})")
    return {"ok": not mismatches, "mismatches": mismatches, "checked_at": now_iso(),
            "gross": gross, "entitled": max(entitled, 0)}


@router.post("/invoices")
async def create_invoice(p: InvoiceIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, ACCOUNTS_ROLES | PROC_ROLES, "record vendor invoices")
    po = await _po(p.po_id)
    srn = await _srn(p.srn_id)
    if not p.vendor_invoice_no.strip():
        raise HTTPException(400, "Vendor invoice number is required")
    if p.invoice_amount <= 0:
        raise HTTPException(400, "Invoice amount must be > 0")
    if p.tds_amount < 0 or p.tax_amount < 0 or p.other_charges < 0:
        raise HTTPException(400, "Amounts cannot be negative")
    dup = await db.svc_invoices.find_one({"po_id": p.po_id, "vendor_invoice_no": p.vendor_invoice_no.strip(),
                                          "status": {"$ne": "rejected"}}, {"_id": 0, "id": 1})
    if dup:
        raise HTTPException(400, "This vendor invoice number already exists against the PO")
    match = _three_way_match(po, srn, p)
    net = round(p.invoice_amount + p.tax_amount + p.other_charges - p.tds_amount, 2)
    if net <= 0:
        raise HTTPException(400, "Net payable must be > 0")
    status = "pending_approval" if match["ok"] else "exception_review"
    doc = {**p.dict(), "vendor_invoice_no": p.vendor_invoice_no.strip(),
           "id": new_id(), "inv_no": await next_sequence("SVI"),
           "invoice_date": p.invoice_date or now_iso()[:10],
           "po_no": po["po_no"], "srn_no": srn["srn_no"], "sr_id": po["sr_id"], "sr_no": po["sr_no"],
           "rfq_no": po.get("rfq_no"), "vendor_id": po.get("vendor_id"), "vendor_name": po["vendor_name"],
           "project_code": po.get("project_code"), "project_name": po.get("project_name"),
           "net_payable": net, "match": match, "status": status, "reserved": match["ok"],
           "history": [_hist(user, "invoice_received",
                             "3-way match OK" if match["ok"] else f"{len(match['mismatches'])} mismatch(es) → exception review",
                             "", status)],
           "created_by": _uname(user), "created_by_id": user.get("id"),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_invoices.insert_one(dict(doc))
    if match["ok"]:  # exception invoices don't reserve PO value until resolved
        await db.svc_pos.update_one({"id": p.po_id}, {"$inc": {"invoiced_total": match["gross"]},
                                                      "$set": {"updated_at": now_iso()}})
    sr = await _sr(po["sr_id"])
    if sr["status"] in ("service_in_progress", "srn_created", "po_created"):
        await _set_sr_status(po["sr_id"], "invoice_received", user, "invoice_received", doc["inv_no"],
                             {"current_owner": "Accounts"})
    await audit(user=user, action="svc_invoice_create", resource="service_workflow",
                record_id=doc["id"], after={"inv_no": doc["inv_no"], "net": net, "match_ok": match["ok"]},
                ip=_ip(request))
    return doc


@router.get("/invoices")
async def list_invoices(status: str = "", vendor: str = "", q: str = "",
                        user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if status:
        fl["status"] = status
    if vendor:
        fl["vendor_name"] = {"$regex": vendor, "$options": "i"}
    if q:
        fl["$or"] = [{"inv_no": {"$regex": q, "$options": "i"}},
                     {"vendor_invoice_no": {"$regex": q, "$options": "i"}},
                     {"po_no": {"$regex": q, "$options": "i"}}, {"sr_no": {"$regex": q, "$options": "i"}}]
    return await db.svc_invoices.find(fl, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)


async def _inv(inv_id: str) -> dict:
    r = await db.svc_invoices.find_one({"id": inv_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Invoice not found")
    return r


@router.post("/invoices/{inv_id}/resolve-exception")
async def resolve_exception(inv_id: str, p: ActionIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, ACCOUNTS_ROLES, "resolve invoice exceptions")
    inv = await _inv(inv_id)
    if inv["status"] != "exception_review":
        raise HTTPException(400, "Invoice is not in exception review")
    if not p.remarks.strip():
        raise HTTPException(400, "Resolution remarks are required")
    await db.svc_invoices.update_one({"id": inv_id}, {
        "$set": {"status": "pending_approval", "reserved": True, "updated_at": now_iso(),
                 "exception_resolution": {"by": _uname(user), "at": now_iso(), "remarks": p.remarks}},
        "$push": {"history": _hist(user, "exception_resolved", p.remarks, "exception_review", "pending_approval")}})
    if not inv.get("reserved"):
        await db.svc_pos.update_one({"id": inv["po_id"]},
                                    {"$inc": {"invoiced_total": float((inv.get("match") or {}).get("gross") or 0)}})
    await audit(user=user, action="svc_invoice_exception_resolved", resource="service_workflow",
                record_id=inv_id, after={"inv_no": inv["inv_no"]}, ip=_ip(request))
    return await _inv(inv_id)


async def _push_invoice_to_payment_queue(inv: dict, user: dict):
    if await db.project_requests.find_one({"source": "service_invoice", "source_id": inv["id"]},
                                          {"_id": 0, "id": 1}):
        return
    await db.project_requests.insert_one({
        "id": new_id(), "request_no": inv["inv_no"],
        "request_type": "service_invoice", "request_type_label": "Service Invoice (SR Workflow)",
        "is_payment": True, "is_stockable": False, "owning_dept": "procurement",
        "status": "with_dept", "payment_status": "payment_pending",
        "source": "service_invoice", "source_id": inv["id"],
        "project_code": inv.get("project_code"), "project_name": inv.get("project_name"),
        "vendor": inv.get("vendor_name"), "vendor_name": inv.get("vendor_name"),
        "invoice_no": inv.get("vendor_invoice_no"), "invoice_date": inv.get("invoice_date"),
        "due_date": inv.get("due_date"),
        "est_value": float(inv.get("net_payable") or 0), "amount": float(inv.get("net_payable") or 0),
        "pay_debit_account_code": "5150",
        "description": (f"Service invoice {inv.get('vendor_invoice_no')} — {inv.get('vendor_name')} "
                        f"(PO {inv.get('po_no')} / SRN {inv.get('srn_no')} / SR {inv.get('sr_no')})"),
        "items": [], "chain": [], "current_step": None,
        "created_by": _uname(user), "created_by_id": user.get("id"), "created_at": now_iso()})


@router.post("/invoices/{inv_id}/action")
async def invoice_action(inv_id: str, p: ActionIn, request: Request, user: dict = Depends(get_current_user)):
    _require_role(user, ACCOUNTS_ROLES, "approve invoices")
    inv = await _inv(inv_id)
    if inv["status"] not in ("pending_approval", "exception_review"):
        raise HTTPException(400, f"Invoice is not awaiting approval (status '{inv['status']}')")
    if p.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve | reject")
    if inv["status"] == "exception_review" and p.action == "approve":
        raise HTTPException(400, "Resolve the exception first, then approve")
    if p.action == "reject" and not p.remarks.strip():
        raise HTTPException(400, "Remarks required to reject an invoice")
    to = "payment_pending" if p.action == "approve" else "rejected"
    await db.svc_invoices.update_one({"id": inv_id}, {
        "$set": {"status": to, "updated_at": now_iso(),
                 "invoice_approval": {"action": p.action, "by": _uname(user), "role": user.get("role"),
                                      "at": now_iso(), "remarks": p.remarks}},
        "$push": {"history": _hist(user, f"invoice_{p.action}", p.remarks, inv["status"], to)}})
    if p.action == "approve":
        inv = await _inv(inv_id)
        await _push_invoice_to_payment_queue(inv, user)
        await _set_sr_status(inv["sr_id"], "payment_pending", user, "invoice_approved",
                             inv["inv_no"], {"current_owner": "Accounts (Payment)"})
    else:
        if inv.get("reserved"):
            await db.svc_pos.update_one({"id": inv["po_id"]},
                                        {"$inc": {"invoiced_total": -float((inv.get("match") or {}).get("gross") or 0)}})
    await audit(user=user, action=f"svc_invoice_{p.action}", resource="service_workflow",
                record_id=inv_id, after={"inv_no": inv["inv_no"]}, ip=_ip(request))
    return await _inv(inv_id)


@router.get("/payments")
async def payments_view(user: dict = Depends(require_permission("service_workflow", "read"))):
    invs = await db.svc_invoices.find({"status": {"$in": ["payment_pending", "paid"]}},
                                      {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)
    prs = {r["source_id"]: r async for r in db.project_requests.find(
        {"source": "service_invoice", "source_id": {"$in": [i["id"] for i in invs]}}, {"_id": 0})}
    vers = {}
    pr_ids = [r["id"] for r in prs.values()]
    if pr_ids:
        async for v in db.payment_verifications.find({"request_id": {"$in": pr_ids}}, {"_id": 0}):
            vers[v["request_id"]] = v
    out = []
    for i in invs:
        pr = prs.get(i["id"])
        v = vers.get((pr or {}).get("id")) if pr else None
        out.append({**i, "queue_stage": (v or {}).get("stage") or ("pending_verification" if pr else None),
                    "utr_no": (v or {}).get("utr_no") or (i.get("payment") or {}).get("utr_no"),
                    "paid_date": (v or {}).get("paid_date") or (i.get("payment") or {}).get("paid_date")})
    return out


# ══════════════════════════════ PAID CALLBACK (from Payment Processing) ══════════════════════════════
async def on_service_invoice_paid(inv_id: str, utr_no: str, paid_date: str, user: dict):
    inv = await db.svc_invoices.find_one({"id": inv_id}, {"_id": 0})
    if not inv or inv.get("status") == "paid":
        return
    await db.svc_invoices.update_one({"id": inv_id}, {
        "$set": {"status": "paid", "updated_at": now_iso(),
                 "payment": {"utr_no": utr_no, "paid_date": paid_date,
                             "paid_by": _uname(user), "paid_at": now_iso()}},
        "$push": {"history": _hist(user, "invoice_paid", f"UTR {utr_no}", "payment_pending", "paid")}})
    net = float(inv.get("net_payable") or 0)
    tds = float(inv.get("tds_amount") or 0)
    po = await db.svc_pos.find_one({"id": inv["po_id"]}, {"_id": 0})
    if po:
        paid = round(float(po.get("paid_amount") or 0) + net, 2)
        settled = round(float(po.get("settled_amount") or 0) + net + tds, 2)
        pay_status = "payment_completed" if settled >= float(po.get("total_value") or 0) - AMOUNT_TOL else "partially_paid"
        po_set = {"paid_amount": paid, "settled_amount": settled, "payment_status": pay_status, "updated_at": now_iso()}
        if pay_status == "payment_completed" and po.get("status") == "completed":
            po_set["status"] = "closed"
        await db.svc_pos.update_one({"id": inv["po_id"]}, {
            "$set": po_set, "$push": {"history": _hist(user, "payment_recorded", f"₹{net:,.2f} · UTR {utr_no}")}})
    unpaid = await db.svc_invoices.count_documents(
        {"sr_id": inv["sr_id"], "status": {"$nin": ["paid", "rejected"]}})
    if unpaid == 0:
        po2 = await db.svc_pos.find_one({"id": inv["po_id"]}, {"_id": 0, "payment_status": 1, "status": 1})
        if po2 and po2.get("payment_status") == "payment_completed":
            await _set_sr_status(inv["sr_id"], "closed", user, "auto_closed",
                                 "All services delivered & payments completed", {"closed_at": now_iso()})
        else:
            await _set_sr_status(inv["sr_id"], "paid", user, "payment_recorded", f"UTR {utr_no}")


# ══════════════════════════════ DASHBOARD ══════════════════════════════
@router.get("/dashboard")
async def dashboard(date_from: str = "", date_to: str = "", department: str = "", site: str = "",
                    vendor: str = "", category: str = "", requester: str = "", project: str = "",
                    user: dict = Depends(require_permission("service_workflow", "read"))):
    base: dict = {}
    if user.get("role") not in VIEW_ALL_ROLES:
        base["requester_id"] = user.get("id")
    if department:
        base["department"] = department
    if site:
        base["site_location"] = site
    if category:
        base["service_category"] = category
    if requester:
        base["requester_name"] = {"$regex": requester, "$options": "i"}
    if project:
        base["project_code"] = project
    if date_from or date_to:
        base["request_date"] = {**({"$gte": date_from} if date_from else {}),
                                **({"$lte": date_to} if date_to else {})}
    sr_ids = [r["id"] async for r in db.svc_requests.find(base, {"_id": 0, "id": 1})] if base else None
    link = ({"sr_id": {"$in": sr_ids}} if sr_ids is not None else {})
    vlink = {**link, **({"vendor_name": {"$regex": vendor, "$options": "i"}} if vendor else {})}
    today = datetime.now(timezone.utc).date().isoformat()

    async def c(coll, q):
        return await db[coll].count_documents(q)

    cards = {
        "total_requests": await c("svc_requests", base),
        "pending_approvals": await c("svc_requests", {**base, "status": {"$in": ["submitted", "under_review"]}}),
        "approved_requests": await c("svc_requests", {**base, "status": "approved"}),
        "rejected_requests": await c("svc_requests", {**base, "status": "rejected"}),
        "rfqs_pending": await c("svc_rfqs", {**link, "status": {"$in": ["draft", "issued"]}}),
        "quotations_pending": await c("svc_rfqs", {**link, "status": {"$in": ["issued", "quotations_received", "recommended"]}}),
        "pos_pending": await c("svc_pos", {**vlink, "status": {"$in": ["draft", "pending_approval", "approved"]}}),
        "services_in_progress": await c("svc_pos", {**vlink, "status": {"$in": ["issued", "in_progress"]}}),
        "srn_pending": await c("svc_srns", {**vlink, "status": {"$in": ["draft", "submitted"]}}),
        "invoices_pending": await c("svc_invoices", {**vlink, "status": {"$in": ["received", "matching", "exception_review", "pending_approval"]}}),
        "payment_pending": await c("svc_invoices", {**vlink, "status": "payment_pending"}),
        "overdue_payments": await c("svc_invoices", {**vlink, "status": "payment_pending",
                                                     "due_date": {"$gt": "", "$lt": today}}),
        "exceptions": await c("svc_invoices", {**vlink, "status": "exception_review"}),
        "completed": await c("svc_requests", {**base, "status": {"$in": ["paid", "closed"]}}),
    }
    recent = await db.svc_requests.find(base, {"_id": 0, "history": 0}).sort("updated_at", -1).to_list(8)
    by_status = {}
    async for g in db.svc_requests.aggregate([{"$match": base}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[g["_id"]] = g["n"]
    return {"cards": cards, "recent": recent, "by_status": by_status, "as_of": now_iso()}
