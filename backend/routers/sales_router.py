"""Sales pipeline:
  Enquiry → Quotation (with revisions) → Order → Project

Auto-numbering: ENQ-YYYY-####, QTN-YYYY-####, ORD-YYYY-####, PRJ-YYYY-####.
Status transitions are enforced; "Won" enquiry can be converted to an Order
(and optionally a Project) in a single transactional call.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, require_permission, get_current_user, now_iso, new_id, logger
from audit import audit
from sequences import next_sequence, stamp_dept_doc

router = APIRouter(tags=["sales"])

ENQUIRY_STATUSES = ["open", "under_review", "submitted", "negotiation", "hold", "lost", "won"]
ALLOWED_TRANSITIONS = {
    "open": {"under_review", "submitted", "hold", "lost"},
    "under_review": {"submitted", "hold", "lost"},
    "submitted": {"negotiation", "won", "lost", "hold"},
    "negotiation": {"won", "lost", "hold"},
    "hold": {"open", "under_review", "submitted", "negotiation", "lost"},
    "lost": set(),
    "won": set(),  # Won is terminal at the enquiry level — convert to Order to progress
}

SERVICE_TYPES = ["sales", "services", "sales_services"]
RFQ_TYPES = ["supply", "service", "supply_service"]
SERVICE_CATEGORIES = ["scaffolding", "painting", "roof_sheeting", "insulation", "rope_access"]
PRIORITIES = ["high", "medium", "low"]
QUOTATION_STATUSES = ["draft", "under_review", "costing_pending", "submitted", "revised", "won", "lost", "cancelled"]


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _snapshot_from_site(site_id: str) -> dict:
    """Pull a denormalised snapshot from a customer site so the enquiry survives
    later edits to the master.
    """
    if not site_id:
        return {}
    site = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not site:
        return {}
    client = await db.clients.find_one({"id": site.get("client_id")}, {"_id": 0}) or {}
    primary_contact = await db.client_contacts.find_one({"site_id": site_id}, {"_id": 0}, sort=[("created_at", 1)]) or {}
    return {
        "client_id": site.get("client_id"),
        "client_code": client.get("customer_code"),
        "customer": client.get("name"),
        "site_code": site.get("site_code"),
        "site_name": site.get("name"),
        "site_location": site.get("city") or site.get("state"),
        "gst": site.get("gst"),
        "billing_address": site.get("billing_address"),
        "contact_person": primary_contact.get("name"),
        "contact_email": primary_contact.get("email"),
        "contact_phone": primary_contact.get("mobile"),
    }


# ---------- Enquiry ----------
class EnquiryIn(BaseModel):
    # Master-linked
    site_id: Optional[str] = None
    client_id: Optional[str] = None
    # Free-text fallbacks
    customer: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    site_location: Optional[str] = None
    department: Optional[str] = None
    # Customer's own reference
    customer_enquiry_no: Optional[str] = None
    enquiry_date: Optional[str] = None
    # RFQ + service categories — multi-select
    rfq_type: list[str] = []
    service_categories: list[str] = []
    # Legacy single field — kept for back-compat with existing rows/screens
    service_type: str = "sales"
    # Deadlines & priority
    submission_deadline: Optional[str] = None
    bid_closing_date: Optional[str] = None
    deadline: Optional[str] = None  # legacy alias
    priority: Optional[str] = None
    # Rich scope sections
    scope_of_work: Optional[str] = None
    technical_requirements: Optional[str] = None
    material_requirements: Optional[str] = None
    site_conditions: Optional[str] = None
    special_instructions: Optional[str] = None
    commercial_notes: Optional[str] = None
    # Legacy combined scope
    scope: Optional[str] = None
    expected_value: Optional[float] = 0.0
    notes: Optional[str] = None


class StatusChange(BaseModel):
    status: str
    note: Optional[str] = None


class ConvertIn(BaseModel):
    customer_po: Optional[str] = None
    contract_value: Optional[float] = None
    payment_terms: Optional[str] = None
    create_project: bool = True


@router.get("/enquiries")
async def list_enquiries(user: dict = Depends(require_permission("quotations", "read"))):
    rows = await db.enquiries.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.post("/enquiries")
async def create_enquiry(payload: EnquiryIn, request: Request, user: dict = Depends(require_permission("quotations", "write"))):
    if payload.service_type not in SERVICE_TYPES:
        raise HTTPException(status_code=400, detail=f"service_type must be one of {SERVICE_TYPES}")
    # Validate multi-selects against masters
    bad = [t for t in (payload.rfq_type or []) if t not in RFQ_TYPES]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown rfq_type {bad}. Allowed: {RFQ_TYPES}")
    if payload.priority and payload.priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {PRIORITIES}")
    doc = payload.model_dump()
    # Mandatory: site_id (and by extension a client through the site snapshot).
    # User policy (Iter 62): Client + Site are both required at creation time.
    if not doc.get("site_id"):
        raise HTTPException(status_code=400, detail="Client Site is required. Please pick a site from the master.")
    # Snapshot master data into the enquiry so it survives edits to clients/sites
    snap = await _snapshot_from_site(doc["site_id"])
    if not snap:
        raise HTTPException(status_code=400, detail="Selected site not found in master")
    for k, v in snap.items():
        if v and not doc.get(k):
            doc[k] = v
    if not doc.get("client_id"):
        raise HTTPException(status_code=400, detail="Client is required. Please pick a client from the master.")
    if not doc.get("customer"):
        raise HTTPException(status_code=400, detail="Customer name could not be resolved from the selected client")
    # Duplicate detection — same site_id + customer_enquiry_no can't happen twice
    if doc.get("site_id") and doc.get("customer_enquiry_no"):
        dup = await db.enquiries.find_one(
            {"site_id": doc["site_id"], "customer_enquiry_no": doc["customer_enquiry_no"]},
            {"_id": 0, "enquiry_no": 1},
        )
        if dup:
            raise HTTPException(
                status_code=400,
                detail=f"This customer enquiry no '{doc['customer_enquiry_no']}' is already registered as {dup['enquiry_no']}",
            )
    doc["id"] = new_id()
    doc["enquiry_no"] = await next_sequence("ENQ")
    await stamp_dept_doc(doc, "enquiry")
    doc["status"] = "open"
    doc["status_history"] = [{"status": "open", "by": user.get("name") or user.get("email"), "at": now_iso(), "note": None}]
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    await db.enquiries.insert_one(doc)
    doc.pop("_id", None)

    # Phase C — auto-create a draft quotation linked back to this enquiry
    try:
        quote_no = await next_sequence("QTN")
        quote_doc = {
            "id": new_id(),
            "quote_number": quote_no,
            "enquiry_id": doc["id"],
            "enquiry_no": doc["enquiry_no"],
            "client_id": doc.get("client_id"),
            "site_id": doc.get("site_id"),
            "client": doc.get("customer"),
            "project": doc.get("scope_of_work") or doc.get("scope") or "",
            # Iter 67 — "Customer Site" picked on the enquiry feeds the Quotation
            # Builder's "Site / Project Name". Priority: enquiry's snapshotted
            # site_name (from the master site picker) → site_location → scope.
            "site_name": doc.get("site_name") or doc.get("site_location") or doc.get("scope_of_work") or doc.get("project") or "",
            "site_location": doc.get("site_location") or "",
            "service_categories": doc.get("service_categories") or [],
            "rfq_type": doc.get("rfq_type") or [],
            "submission_deadline": doc.get("submission_deadline") or doc.get("deadline"),
            "scope_of_work": doc.get("scope_of_work"),
            "technical_requirements": doc.get("technical_requirements"),
            "material_requirements": doc.get("material_requirements"),
            "commercial_notes": doc.get("commercial_notes"),
            "contact_person": doc.get("contact_person"),
            "contact_email": doc.get("contact_email"),
            "contact_phone": doc.get("contact_phone"),
            "amount": doc.get("expected_value") or 0,
            "date": doc.get("enquiry_date") or now_iso()[:10],
            "status": "draft",
            "created_at": now_iso(),
            "created_by": user["id"],
            "created_via": "auto_from_enquiry",
        }
        await stamp_dept_doc(quote_doc, "quotation")
        await db.quotations.insert_one(quote_doc)
        quote_doc.pop("_id", None)
        await db.enquiries.update_one({"id": doc["id"]},
                                      {"$set": {"quotation_id": quote_doc["id"], "quotation_no": quote_no}})
        doc["quotation_id"] = quote_doc["id"]
        doc["quotation_no"] = quote_no
    except Exception as e:
        logger.warning(f"Auto-quotation creation failed for enquiry {doc['id']}: {e}")

    await audit(user=user, action="create", resource="enquiries", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/enquiries/{enq_id}")
async def get_enquiry(enq_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    row = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.put("/enquiries/{enq_id}")
async def update_enquiry(enq_id: str, payload: dict, request: Request, user: dict = Depends(require_permission("quotations", "write"))):
    payload.pop("id", None)
    payload.pop("enquiry_no", None)
    payload.pop("status", None)
    payload.pop("status_history", None)
    payload["updated_at"] = now_iso()
    payload["updated_by"] = user["id"]
    before = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Not found")
    await db.enquiries.update_one({"id": enq_id}, {"$set": payload})
    after = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    await audit(user=user, action="update", resource="enquiries", record_id=enq_id, before=before, after=after, ip=_ip(request))
    return after


@router.post("/enquiries/{enq_id}/status")
async def change_status(enq_id: str, payload: StatusChange, request: Request, user: dict = Depends(require_permission("quotations", "write"))):
    if payload.status not in ENQUIRY_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {ENQUIRY_STATUSES}")
    enq = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    if not enq:
        raise HTTPException(status_code=404, detail="Not found")
    current = enq.get("status", "open")
    if payload.status != current and payload.status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=400, detail=f"Cannot transition from {current} to {payload.status}")
    history = list(enq.get("status_history") or [])
    history.append({
        "status": payload.status,
        "by": user.get("name") or user.get("email"),
        "at": now_iso(),
        "note": payload.note,
    })
    await db.enquiries.update_one(
        {"id": enq_id},
        {"$set": {"status": payload.status, "status_history": history, "updated_at": now_iso(), "updated_by": user["id"]}},
    )
    after = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    await audit(user=user, action="status_change", resource="enquiries", record_id=enq_id, before={"status": current}, after={"status": payload.status, "note": payload.note}, ip=_ip(request))
    return after


@router.delete("/enquiries/{enq_id}")
async def delete_enquiry(enq_id: str, request: Request, user: dict = Depends(require_permission("quotations", "delete"))):
    before = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    res = await db.enquiries.delete_one({"id": enq_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await audit(user=user, action="delete", resource="enquiries", record_id=enq_id, before=before, ip=_ip(request))
    return {"ok": True}


# ---------- Won → Order → Project ----------
@router.post("/enquiries/{enq_id}/convert")
async def convert_to_order(enq_id: str, payload: ConvertIn, request: Request, user: dict = Depends(require_permission("quotations", "write"))):
    enq = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    if not enq:
        raise HTTPException(status_code=404, detail="Not found")
    if enq.get("status") != "won":
        raise HTTPException(status_code=400, detail="Only Won enquiries can be converted")
    if enq.get("order_id"):
        raise HTTPException(status_code=409, detail=f"Already converted to order {enq.get('order_no')}")

    order_no = await next_sequence("ORD")
    order_doc = {
        "id": new_id(),
        "order_no": order_no,
        "enquiry_id": enq_id,
        "enquiry_no": enq.get("enquiry_no"),
        "customer": enq.get("customer"),
        "contact_person": enq.get("contact_person"),
        "site_location": enq.get("site_location"),
        "service_type": enq.get("service_type"),
        "scope": enq.get("scope"),
        "customer_po": payload.customer_po,
        "contract_value": payload.contract_value or enq.get("expected_value") or 0.0,
        "payment_terms": payload.payment_terms,
        "status": "active",
        "created_at": now_iso(),
        "created_by": user["id"],
    }
    project_doc = None
    if payload.create_project:
        proj_no = await next_sequence("PRJ")
        project_doc = {
            "id": new_id(),
            "code": proj_no,
            "name": f"{enq.get('customer')} — {enq.get('scope') or 'Project'}"[:140],
            "client": enq.get("customer"),
            "type": enq.get("service_type"),
            "site": enq.get("site_location"),
            "budget": order_doc["contract_value"],
            "status": "planned",
            "progress": 0,
            "manager": None,
            "order_id": order_doc["id"],
            "enquiry_id": enq_id,
            "created_at": now_iso(),
            "created_by": user["id"],
        }
        order_doc["project_id"] = project_doc["id"]
        order_doc["project_code"] = proj_no
        await db.projects.insert_one(project_doc)
        project_doc.pop("_id", None)
        await audit(user=user, action="create", resource="projects", record_id=project_doc["id"], after=project_doc, ip=_ip(request))

    await stamp_dept_doc(order_doc, "order")
    await db.orders.insert_one(order_doc)
    order_doc.pop("_id", None)
    await audit(user=user, action="create", resource="orders", record_id=order_doc["id"], after=order_doc, ip=_ip(request))

    await db.enquiries.update_one(
        {"id": enq_id},
        {"$set": {
            "order_id": order_doc["id"],
            "order_no": order_no,
            "project_id": order_doc.get("project_id"),
            "project_code": order_doc.get("project_code"),
            "updated_at": now_iso(),
        }},
    )
    return {"order": order_doc, "project": project_doc, "enquiry_id": enq_id}


# ---------- Orders ----------
@router.get("/orders")
async def list_orders(user: dict = Depends(require_permission("quotations", "read"))):
    rows = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.get("/orders/{order_id}")
async def get_order(order_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    row = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.put("/orders/{order_id}")
async def update_order(order_id: str, payload: dict, request: Request, user: dict = Depends(require_permission("quotations", "write"))):
    payload.pop("id", None)
    payload.pop("order_no", None)
    payload["updated_at"] = now_iso()
    payload["updated_by"] = user["id"]
    before = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Not found")
    await db.orders.update_one({"id": order_id}, {"$set": payload})
    after = await db.orders.find_one({"id": order_id}, {"_id": 0})
    await audit(user=user, action="update", resource="orders", record_id=order_id, before=before, after=after, ip=_ip(request))
    return after


@router.delete("/orders/{order_id}")
async def delete_order(order_id: str, request: Request, user: dict = Depends(require_permission("quotations", "delete"))):
    before = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Not found")
    await db.orders.delete_one({"id": order_id})
    await audit(user=user, action="delete", resource="orders", record_id=order_id, before=before, ip=_ip(request))
    return {"ok": True, "deleted_id": order_id}


# ---------- Quotation revision ----------
@router.post("/quotations/{q_id}/revise")
async def revise_quotation(q_id: str, request: Request, user: dict = Depends(require_permission("quotations", "write"))):
    parent = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not parent:
        raise HTTPException(status_code=404, detail="Not found")
    # find the latest revision in the chain
    root_id = parent.get("root_id") or parent["id"]
    last = await db.quotations.find({"$or": [{"id": root_id}, {"root_id": root_id}]}, {"_id": 0}).sort("revision_no", -1).to_list(1)
    last_rev = (last[0].get("revision_no") if last else 0) or 0

    new_doc = {**parent}
    new_doc.pop("_id", None)
    new_doc["id"] = new_id()
    new_doc["parent_id"] = parent["id"]
    new_doc["root_id"] = root_id
    new_doc["revision_no"] = last_rev + 1
    base_qno = (parent.get("quote_number") or await next_sequence("QTN")).split(" Rev")[0]
    new_doc["quote_number"] = f"{base_qno} Rev{new_doc['revision_no']}"
    new_doc["status"] = "draft"
    new_doc["date"] = now_iso()[:10]
    new_doc["created_at"] = now_iso()
    new_doc["created_by"] = user["id"]
    await db.quotations.insert_one(new_doc)
    new_doc.pop("_id", None)
    await audit(user=user, action="revise", resource="quotations", record_id=new_doc["id"], before=parent, after=new_doc, ip=_ip(request))
    return new_doc


@router.get("/quotations/{q_id}/revisions")
async def list_revisions(q_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    base = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not base:
        raise HTTPException(status_code=404, detail="Not found")
    root_id = base.get("root_id") or base["id"]
    rows = await db.quotations.find({"$or": [{"id": root_id}, {"root_id": root_id}]}, {"_id": 0}).sort("revision_no", 1).to_list(50)
    return rows


# ---------- Quotation create/update/status overrides (Iter 62) ----------
# These overrides MUST be registered BEFORE crud_router (see server.py).
# Policy: quotations are auto-created from enquiries only. Direct creation is blocked.

QUOTATION_STATUS_TRANSITIONS = {
    "draft": {"under_review", "costing_pending", "submitted", "cancelled"},
    "under_review": {"costing_pending", "submitted", "draft", "cancelled"},
    "costing_pending": {"under_review", "submitted", "draft", "cancelled"},
    "submitted": {"revised", "won", "lost", "cancelled"},
    "revised": {"submitted", "won", "lost", "cancelled"},
    "won": set(),
    "lost": set(),
    "cancelled": set(),
}

# Map quotation final-state status onto the enquiry's status (one-way sync)
QUOTE_TO_ENQUIRY_STATUS = {
    "submitted": "submitted",
    "won": "won",
    "lost": "lost",
    "cancelled": "lost",
}


class QuotationStatusIn(BaseModel):
    status: str
    note: Optional[str] = None


@router.post("/quotations")
async def block_direct_quotation_create(payload: dict, user: dict = Depends(require_permission("quotations", "write"))):
    """Sales policy (Iter 62): quotations are auto-generated from enquiries only."""
    raise HTTPException(
        status_code=400,
        detail="Quotations cannot be created directly. Register an Enquiry first; a draft quotation will be auto-generated and linked.",
    )


@router.put("/quotations/{q_id}")
async def update_quotation(q_id: str, payload: dict, request: Request, user: dict = Depends(require_permission("quotations", "write"))):
    """Edit a quotation. Status changes MUST go through /quotations/{id}/status
    so the enquiry-link, approval gate, and history are enforced."""
    payload.pop("id", None)
    payload.pop("quote_number", None)
    # Strip server-managed fields
    for k in ("status", "status_history", "approval_id", "approval_status", "approval_decided_at",
              "enquiry_id", "enquiry_no", "root_id", "parent_id", "revision_no",
              "created_at", "created_by", "created_via"):
        payload.pop(k, None)
    payload["updated_at"] = now_iso()
    payload["updated_by"] = user["id"]
    before = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Quotation not found")
    await db.quotations.update_one({"id": q_id}, {"$set": payload})
    after = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    await audit(user=user, action="update", resource="quotations", record_id=q_id, before=before, after=after, ip=_ip(request))
    return after


@router.post("/quotations/{q_id}/send-for-approval")
async def send_quotation_for_approval(q_id: str, request: Request, body: Optional[dict] = None,
                                       user: dict = Depends(require_permission("quotations", "write"))):
    """Create (or refresh) the internal approval row for a quotation.
    Uses the 'quotation' approval chain (admin-editable in Approval Matrix).

    Body (optional, all 4 fields used to satisfy the universal approval-docs gate):
      documents: list[str|dict]            — newly uploaded file_ids
      linked_attachments: list[str]        — existing file_ids on the quote
      documents_not_required: bool         — toggle for 'no docs needed'
      documents_not_required_reason: str   — required when toggle is true
    """
    from approval_engine import build_chain, insert_approval, copy_approval_doc_fields
    quote = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quote.get("status") not in {"draft", "under_review", "costing_pending"}:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send for approval — quote is already in '{quote.get('status')}' state.",
        )
    # Block duplicate ACTIVE approvals only (allow re-send after rejection/info_required so the
    # requester can correct & restart the chain). A new approval row replaces the old approval_id
    # on the quote; chain auto-restarts from step 0.
    existing = await db.approvals.find_one(
        {"type": "quotation", "record_id": q_id,
         "status": {"$in": ["pending", "in_progress"]}},
        {"_id": 0, "id": 1, "status": 1},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This quote already has an active approval ({existing['id']}, status={existing['status']}).",
        )

    chain = await build_chain("quotation")
    first_step = chain[0] if chain else {}
    approval_doc = {
        "id": new_id(),
        "type": "quotation",
        "title": f"{quote.get('quote_number')} — {quote.get('client') or ''}".strip(" —"),
        "reference": quote.get("quote_number"),
        "record_id": q_id,
        "module": "sales",
        "amount": float(quote.get("total") or quote.get("amount") or 0),
        "department": quote.get("department"),
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "chain": chain,
        "current_step": 0,
        "history": [],
        "status": "pending",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "payload": {
            "quote_number": quote.get("quote_number"),
            "client": quote.get("client"),
            "project": quote.get("project"),
            "total": quote.get("total") or quote.get("amount") or 0,
            "enquiry_no": quote.get("enquiry_no"),
        },
    }
    copy_approval_doc_fields(approval_doc, body)
    await insert_approval(approval_doc)
    await db.quotations.update_one(
        {"id": q_id},
        {"$set": {
            "approval_id": approval_doc["id"],
            "approval_status": "pending",
            "approval_sent_at": now_iso(),
            "approval_current_step_role": first_step.get("role"),
            "approval_current_step_label": first_step.get("label") or first_step.get("role"),
            "approval_current_step_index": 0,
            "approval_total_steps": len(chain),
            "approval_reject_reason": None,
            "status": "under_review",
            "updated_at": now_iso(),
            "updated_by": user["id"],
        }},
    )
    # In-app notify first-step approver
    try:
        from routers.notifications_router import notify_approval_pending
        await notify_approval_pending(approval_doc)
    except Exception:
        pass
    await audit(user=user, action="send_for_approval", resource="quotations",
                record_id=q_id, after={"approval_id": approval_doc["id"]}, ip=_ip(request))
    return {"approval": approval_doc, "quotation_id": q_id}


@router.post("/quotations/{q_id}/status")
async def change_quotation_status(q_id: str, payload: QuotationStatusIn, request: Request,
                                  user: dict = Depends(require_permission("quotations", "write"))):
    """Validated status transition with approval gate + enquiry sync.

    Rule: cannot go to 'submitted' until approval_status == 'approved'.
    On submitted/won/lost/cancelled, mirror the new status onto the linked enquiry.
    """
    if payload.status not in QUOTATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {QUOTATION_STATUSES}")
    quote = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quotation not found")
    current = quote.get("status") or "draft"
    if payload.status != current and payload.status not in QUOTATION_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=400, detail=f"Cannot transition quotation from {current} to {payload.status}")
    # Approval gate
    if payload.status == "submitted" and quote.get("approval_status") != "approved":
        raise HTTPException(
            status_code=400,
            detail="Internal approval is required before submitting the quotation. Click 'Send for Approval' and wait for all approvers.",
        )

    history = list(quote.get("status_history") or [])
    history.append({
        "status": payload.status,
        "by": user.get("name") or user.get("email"),
        "at": now_iso(),
        "note": payload.note,
    })
    await db.quotations.update_one(
        {"id": q_id},
        {"$set": {"status": payload.status, "status_history": history,
                  "updated_at": now_iso(), "updated_by": user["id"]}},
    )
    after = await db.quotations.find_one({"id": q_id}, {"_id": 0})

    # Mirror onto enquiry (best-effort one-way sync)
    enquiry_id = quote.get("enquiry_id")
    mirror = QUOTE_TO_ENQUIRY_STATUS.get(payload.status)
    if enquiry_id and mirror:
        enq = await db.enquiries.find_one({"id": enquiry_id}, {"_id": 0})
        if enq and enq.get("status") != mirror and mirror in ENQUIRY_STATUSES:
            enq_history = list(enq.get("status_history") or [])
            enq_history.append({
                "status": mirror, "by": user.get("name") or user.get("email"),
                "at": now_iso(), "note": f"Synced from quote {quote.get('quote_number')} → {payload.status}",
            })
            await db.enquiries.update_one(
                {"id": enquiry_id},
                {"$set": {"status": mirror, "status_history": enq_history,
                          "updated_at": now_iso(), "updated_by": user["id"]}},
            )

    await audit(user=user, action="status_change", resource="quotations", record_id=q_id,
                before={"status": current}, after={"status": payload.status, "note": payload.note}, ip=_ip(request))

    # Iter 64 — Auto-create a draft Contract Handover when the quote is WON.
    # One handover per quote (we de-dupe on quotation_id).
    auto_handover = None
    if payload.status == "won":
        try:
            auto_handover = await _auto_create_handover_from_quote(after, user)
        except Exception as e:
            logger.warning(f"auto-handover creation failed for quote {q_id}: {e}")

    if auto_handover:
        after["auto_handover"] = {
            "id": auto_handover["id"],
            "handover_no": auto_handover["handover_no"],
            "project_code": auto_handover.get("project_code"),
            "project_id": auto_handover.get("project_id"),
        }
    return after


async def _auto_create_handover_from_quote(quote: dict, user: dict) -> Optional[dict]:
    """Create a draft project_handover record from a WON quotation.
    Pre-fills every available field from the quote + linked enquiry + client master.
    No-op if a handover already exists for this quote (idempotent).
    """
    # Idempotency guard — one handover per won quote
    existing = await db.project_handovers.find_one({"quotation_id": quote["id"]}, {"_id": 0, "id": 1, "handover_no": 1})
    if existing:
        return existing

    enquiry = None
    if quote.get("enquiry_id"):
        enquiry = await db.enquiries.find_one({"id": quote["enquiry_id"]}, {"_id": 0})

    # Resolve client master (for GST + contact details) when we have an id
    client_master = None
    client_id = quote.get("client_id") or (enquiry or {}).get("client_id")
    if client_id:
        client_master = await db.clients.find_one({"id": client_id}, {"_id": 0})

    handover_no = await next_sequence("CHO")
    now = now_iso()

    # ---- Field mapping ----
    project_name = (
        quote.get("project")
        or (enquiry or {}).get("scope_of_work", "")[:80]
        or quote.get("quote_number")
    )[:160] or "Untitled Project"
    client_name = quote.get("client") or (enquiry or {}).get("customer") or (client_master or {}).get("name") or "—"
    site_location = quote.get("site_location") or (enquiry or {}).get("site_location") or ""
    scope_of_work = (
        quote.get("scope_of_work")
        or (enquiry or {}).get("scope_of_work")
        or quote.get("project")
        or ""
    )
    contract_value = float(quote.get("total") or quote.get("amount") or (enquiry or {}).get("expected_value") or 0)

    # Iter 65 — Also spawn the Project record (PRJ-YYYY-####) so Sales doesn't have
    # to do a second convert step. Idempotent on quotation_id.
    project_doc = await db.projects.find_one({"quotation_id": quote["id"]}, {"_id": 0})
    if not project_doc:
        proj_no = await next_sequence("PRJ")
        project_doc = {
            "id": new_id(),
            "code": proj_no,
            "name": project_name,
            "client": client_name,
            "client_id": client_id,
            "type": (enquiry or {}).get("service_type"),
            "site": site_location,
            "site_id": quote.get("site_id") or (enquiry or {}).get("site_id"),
            "budget": contract_value,
            "status": "planned",
            "progress": 0,
            "manager": None,
            "quotation_id": quote["id"],
            "quotation_no": quote.get("quote_number"),
            "enquiry_id": quote.get("enquiry_id"),
            "enquiry_no": quote.get("enquiry_no") or (enquiry or {}).get("enquiry_no"),
            "department": quote.get("department") or (enquiry or {}).get("department"),
            "source": "auto_from_quote",
            "created_at": now,
            "created_by": user.get("name") or user.get("email"),
            "created_by_id": user.get("id"),
        }
        await db.projects.insert_one(project_doc)
        project_doc.pop("_id", None)
        try:
            await audit(user=user, action="auto_create_from_quote", resource="projects",
                        record_id=project_doc["id"], after={"quote_id": quote["id"]}, ip="system")
        except Exception:
            pass

    handover = {
        "id": new_id(),
        "handover_no": handover_no,
        "project_name": project_name,
        "client_name": client_name,
        "client_id": client_id,
        "site_id": quote.get("site_id") or (enquiry or {}).get("site_id"),
        "site_location": site_location,
        "work_order_number": quote.get("customer_po") or quote.get("customer_enquiry_no") or (enquiry or {}).get("customer_enquiry_no") or "",
        "contract_value": contract_value,
        "contract_start_date": quote.get("contract_start_date") or quote.get("date"),
        "contract_end_date": quote.get("valid_until"),
        "scope_of_work": scope_of_work,
        "billing_terms": quote.get("billing_terms") or "",
        "payment_terms": quote.get("payment_terms") or (client_master or {}).get("payment_terms") or "Net 30",
        "gst_details": quote.get("gst") or (client_master or {}).get("gst") or "",
        "customer_contact_person": quote.get("contact_person") or (enquiry or {}).get("contact_person") or "",
        "customer_contact_number": quote.get("contact_phone") or (enquiry or {}).get("contact_phone") or "",
        "customer_email": quote.get("contact_email") or (enquiry or {}).get("contact_email") or "",
        "special_conditions": quote.get("special_instructions") or (enquiry or {}).get("special_instructions") or "",
        "safety_requirements": (enquiry or {}).get("safety_requirements") or "",
        "manpower_requirements": (enquiry or {}).get("manpower_requirements") or "",
        "material_requirements": (enquiry or {}).get("material_requirements") or "",
        "asset_requirements": (enquiry or {}).get("asset_requirements") or "",
        "remarks": f"Auto-created from won quotation {quote.get('quote_number')}",
        "attachments": [],
        "department": quote.get("department") or (enquiry or {}).get("department"),
        # Provenance / lineage
        "quotation_id": quote["id"],
        "quotation_no": quote.get("quote_number"),
        "enquiry_id": quote.get("enquiry_id"),
        "enquiry_no": quote.get("enquiry_no") or (enquiry or {}).get("enquiry_no"),
        "project_id": project_doc["id"],
        "project_code": project_doc["code"],
        "source": "auto_from_quote",
        # Workflow status
        "status": "draft",
        "status_history": [{
            "status": "draft", "by": user.get("name") or user.get("email"),
            "at": now, "note": f"Auto-generated when quote {quote.get('quote_number')} was marked won",
        }],
        "created_at": now,
        "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
        "updated_at": now,
    }
    await db.project_handovers.insert_one(handover)
    handover.pop("_id", None)
    # Activity feed entry (best-effort)
    try:
        await db.handover_activity.insert_one({
            "id": new_id(),
            "handover_id": handover["id"],
            "actor_id": user.get("id"),
            "actor_name": user.get("name") or user.get("email"),
            "event": "auto_created",
            "message": f"Contract handover {handover_no} auto-created from won quote {quote.get('quote_number')}",
            "at": now,
        })
    except Exception:
        pass
    # Audit
    try:
        await audit(user=user, action="auto_create_from_quote", resource="project_handovers",
                    record_id=handover["id"], after={"quote_id": quote["id"]}, ip="system")
    except Exception:
        pass
    return handover


@router.get("/quotations/{q_id}/approval")
async def get_quotation_approval(q_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    """Return the latest approval doc for this quote (or null)."""
    quote = await db.quotations.find_one({"id": q_id}, {"_id": 0, "approval_id": 1})
    if not quote:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if not quote.get("approval_id"):
        return None
    appr = await db.approvals.find_one({"id": quote["approval_id"]}, {"_id": 0})
    return appr




# ---------- Sales enquiry pulse dashboard ----------
@router.get("/sales/enquiry-pulse")
async def enquiry_pulse(user: dict = Depends(require_permission("quotations", "read"))):
    from datetime import date, timedelta
    today = date.today()
    in_7 = (today + timedelta(days=7)).isoformat()
    total = await db.enquiries.count_documents({})
    open_count = await db.enquiries.count_documents({"status": {"$in": ["open", "under_review", "submitted", "negotiation"]}})
    won = await db.enquiries.count_documents({"status": "won"})
    lost = await db.enquiries.count_documents({"status": "lost"})
    pending_quotes = await db.quotations.count_documents({"status": {"$in": ["draft", "under_review", "costing_pending"]}})
    approaching = await db.enquiries.count_documents({
        "submission_deadline": {"$gte": today.isoformat(), "$lte": in_7},
        "status": {"$nin": ["won", "lost"]},
    })
    # by service
    pipeline = [
        {"$unwind": {"path": "$service_categories", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$service_categories", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_service = await db.enquiries.aggregate(pipeline).to_list(20)
    # by RFQ type
    rfq_pipeline = [
        {"$unwind": {"path": "$rfq_type", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$rfq_type", "count": {"$sum": 1}}},
    ]
    by_rfq = await db.enquiries.aggregate(rfq_pipeline).to_list(20)
    ratio = round((won / (won + lost) * 100), 1) if (won + lost) else None
    return {
        "kpis": {
            "total": total,
            "open": open_count,
            "won": won,
            "lost": lost,
            "win_ratio_pct": ratio,
            "pending_quotations": pending_quotes,
            "deadline_approaching": approaching,
        },
        "by_service": [{"category": r["_id"], "count": r["count"]} for r in by_service],
        "by_rfq_type": [{"rfq_type": r["_id"], "count": r["count"]} for r in by_rfq],
    }


# ---------- Phase D · Sales Reports & Global Search ----------
@router.get("/sales/reports/monthly")
async def report_monthly(user: dict = Depends(require_permission("sales_reports", "read"))):
    """Enquiries created per calendar month with won/lost split and pipeline value."""
    pipeline = [
        {"$project": {
            "ym": {"$substr": ["$created_at", 0, 7]},
            "status": 1,
            "expected_value": {"$ifNull": ["$expected_value", 0]},
        }},
        {"$group": {
            "_id": "$ym",
            "total": {"$sum": 1},
            "won": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, 1, 0]}},
            "lost": {"$sum": {"$cond": [{"$eq": ["$status", "lost"]}, 1, 0]}},
            "pipeline_value": {"$sum": "$expected_value"},
            "won_value": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, "$expected_value", 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = await db.enquiries.aggregate(pipeline).to_list(60)
    return [{"month": r["_id"], "total": r["total"], "won": r["won"], "lost": r["lost"],
             "pipeline_value": round(r.get("pipeline_value", 0) or 0, 2),
             "won_value": round(r.get("won_value", 0) or 0, 2)} for r in rows]


@router.get("/sales/reports/by-client")
async def report_by_client(user: dict = Depends(require_permission("sales_reports", "read"))):
    """Aggregate enquiries / win-rate / pipeline value by client."""
    pipeline = [
        {"$group": {
            "_id": {"client_id": "$client_id", "customer": "$customer"},
            "total": {"$sum": 1},
            "won": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, 1, 0]}},
            "lost": {"$sum": {"$cond": [{"$eq": ["$status", "lost"]}, 1, 0]}},
            "pipeline_value": {"$sum": {"$ifNull": ["$expected_value", 0]}},
            "won_value": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, {"$ifNull": ["$expected_value", 0]}, 0]}},
        }},
        {"$sort": {"total": -1}},
    ]
    rows = await db.enquiries.aggregate(pipeline).to_list(500)
    out = []
    for r in rows:
        key = r["_id"] or {}
        won = r.get("won", 0)
        lost = r.get("lost", 0)
        out.append({
            "client_id": key.get("client_id"),
            "customer": key.get("customer") or "—",
            "total": r["total"],
            "won": won, "lost": lost,
            "win_ratio_pct": round((won / (won + lost) * 100), 1) if (won + lost) else None,
            "pipeline_value": round(r.get("pipeline_value", 0) or 0, 2),
            "won_value": round(r.get("won_value", 0) or 0, 2),
        })
    return out


@router.get("/sales/reports/by-service")
async def report_by_service(user: dict = Depends(require_permission("sales_reports", "read"))):
    """Aggregate by service_categories (unwound) with win-rate."""
    pipeline = [
        {"$unwind": {"path": "$service_categories", "preserveNullAndEmptyArrays": False}},
        {"$group": {
            "_id": "$service_categories",
            "total": {"$sum": 1},
            "won": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, 1, 0]}},
            "lost": {"$sum": {"$cond": [{"$eq": ["$status", "lost"]}, 1, 0]}},
            "pipeline_value": {"$sum": {"$ifNull": ["$expected_value", 0]}},
            "won_value": {"$sum": {"$cond": [{"$eq": ["$status", "won"]}, {"$ifNull": ["$expected_value", 0]}, 0]}},
        }},
        {"$sort": {"total": -1}},
    ]
    rows = await db.enquiries.aggregate(pipeline).to_list(50)
    return [{
        "service": r["_id"],
        "total": r["total"],
        "won": r["won"],
        "lost": r["lost"],
        "win_ratio_pct": round((r["won"] / (r["won"] + r["lost"]) * 100), 1) if (r["won"] + r["lost"]) else None,
        "pipeline_value": round(r.get("pipeline_value", 0) or 0, 2),
        "won_value": round(r.get("won_value", 0) or 0, 2),
    } for r in rows]


@router.get("/sales/reports/won-lost")
async def report_won_lost(user: dict = Depends(require_permission("sales_reports", "read"))):
    """High-level win/loss ratio plus monthly trend (last 12 months)."""
    from datetime import date
    today = date.today()
    total_won = await db.enquiries.count_documents({"status": "won"})
    total_lost = await db.enquiries.count_documents({"status": "lost"})
    win_pct = round((total_won / (total_won + total_lost) * 100), 1) if (total_won + total_lost) else None
    # average cycle time on won enquiries
    won_rows = await db.enquiries.find({"status": "won"}, {"_id": 0, "created_at": 1, "status_history": 1}).to_list(500)
    cycles = []
    for w in won_rows:
        try:
            created = w.get("created_at", "")[:10]
            won_at = ""
            for h in w.get("status_history", []) or []:
                if h.get("status") == "won":
                    won_at = (h.get("at") or "")[:10]
            if created and won_at:
                from datetime import datetime as _dt
                d1 = _dt.fromisoformat(created)
                d2 = _dt.fromisoformat(won_at)
                cycles.append((d2 - d1).days)
        except Exception:
            continue
    avg_cycle_days = round(sum(cycles) / len(cycles), 1) if cycles else None
    return {
        "won": total_won,
        "lost": total_lost,
        "win_ratio_pct": win_pct,
        "avg_cycle_days": avg_cycle_days,
        "as_of": today.isoformat(),
    }


@router.get("/sales/reports/deadline-tracker")
async def report_deadline_tracker(user: dict = Depends(require_permission("sales_reports", "read"))):
    """Open enquiries sorted by submission_deadline; flags overdue & due-soon."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    in_7 = (date.today() + timedelta(days=7)).isoformat()
    rows = await db.enquiries.find(
        {"status": {"$nin": ["won", "lost"]}, "submission_deadline": {"$nin": [None, ""]}},
        {"_id": 0},
    ).sort("submission_deadline", 1).to_list(500)
    out = []
    for r in rows:
        dl = r.get("submission_deadline") or r.get("deadline") or ""
        if not dl:
            continue
        if dl < today:
            bucket = "overdue"
        elif dl <= in_7:
            bucket = "due_soon"
        else:
            bucket = "upcoming"
        out.append({
            "id": r.get("id"),
            "enquiry_no": r.get("enquiry_no"),
            "customer": r.get("customer"),
            "site_code": r.get("site_code"),
            "site_location": r.get("site_location"),
            "submission_deadline": dl,
            "priority": r.get("priority"),
            "status": r.get("status"),
            "service_categories": r.get("service_categories") or [],
            "expected_value": r.get("expected_value") or 0,
            "bucket": bucket,
        })
    return out


@router.get("/sales/search")
async def sales_global_search(q: str, user: dict = Depends(require_permission("sales_reports", "read"))):
    """Cross-search enquiries / quotations / orders by code, customer, site, scope."""
    import re
    if not q or len(q.strip()) < 1:
        return {"enquiries": [], "quotations": [], "orders": []}
    pat = re.compile(re.escape(q.strip()), re.IGNORECASE)
    enq = await db.enquiries.find(
        {"$or": [{"enquiry_no": pat}, {"customer_enquiry_no": pat}, {"customer": pat},
                 {"site_code": pat}, {"site_location": pat}, {"scope_of_work": pat}, {"scope": pat}]},
        {"_id": 0},
    ).limit(40).to_list(40)
    qts = await db.quotations.find(
        {"$or": [{"quote_number": pat}, {"client": pat}, {"project": pat}, {"enquiry_no": pat}]},
        {"_id": 0},
    ).limit(40).to_list(40)
    ord_rows = await db.orders.find(
        {"$or": [{"order_no": pat}, {"customer": pat}, {"customer_po": pat}, {"enquiry_no": pat}]},
        {"_id": 0},
    ).limit(40).to_list(40)
    return {"enquiries": enq, "quotations": qts, "orders": ord_rows}
