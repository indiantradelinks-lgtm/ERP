"""Projects & Operations Workflow router (Iter 60, Phase 1).

Implements the foundation of the post-sales hand-off workflow:

  Sales → Contract Handover  →  Project Head receives notification  →
  Project Head allocates to PM / Coordinator  →  Project row auto-created  →
  Existing PR/Material/PO/HR modules now operate against that project.

Endpoints (all under /api):
  POST   /ops/handovers                 Sales creates draft
  GET    /ops/handovers                 List (RBAC + dept-scoped)
  GET    /ops/handovers/{id}            Detail
  PUT    /ops/handovers/{id}            Update (only while draft / sent_back)
  DELETE /ops/handovers/{id}            Delete (draft only)
  POST   /ops/handovers/{id}/submit     Sales submits → notifies project heads
  POST   /ops/handovers/{id}/allocate   Project Head allocates PM/Coordinator
  POST   /ops/handovers/{id}/reassign   Project Head reassigns
  GET    /ops/my-projects               Assigned-to-me list (PM/Coordinator)
  GET    /ops/handovers/{id}/timeline   Activity timeline for one handover

Status flow:
  draft → submitted → under_review → allocated → active → on_hold | completed | closed
"""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, get_current_user, now_iso, new_id
from audit import audit
from sequences import next_sequence

logger = logging.getLogger("erp.ops")
router = APIRouter(tags=["projects-ops"])

ALLOWED_STATUSES = {
    "draft", "submitted", "under_review",
    "allocated", "active", "on_hold",
    "completed", "closed", "sent_back",
}
EDITABLE_STATUSES = {"draft", "sent_back"}



# ─── Iter 70 · Mirror handover files onto the project record ─────────────
async def _mirror_handover_files_to_project(handover_id: str, project_id: str, user: dict) -> int:
    """When a handover is allocated, clone every file row that points at the
    handover so it ALSO points at the new project record. This way the field
    team sees the contract / WO / drawings on the Project Dashboard without
    having to navigate back to Handovers.

    We deliberately create NEW `db.files` rows (not move) so:
      • The handover remains the source-of-truth audit copy
      • Project-side deletions don't orphan the handover
      • Storage paths/URLs are reused — no actual file copy on disk

    Idempotent: skips files already mirrored (tracked via the
    `mirrored_from_file_id` back-reference). Returns count of new rows.
    """
    existing = await db.files.find({
        "parent_type": "project_handovers",
        "parent_id": handover_id,
    }, {"_id": 0}).to_list(500)
    if not existing:
        return 0
    created = 0
    for f in existing:
        # Skip if a project-side copy already exists for this source file
        already = await db.files.find_one({
            "parent_type": "projects",
            "parent_id": project_id,
            "mirrored_from_file_id": f["id"],
        }, {"_id": 0, "id": 1})
        if already:
            continue
        clone = {**f}
        clone["id"] = new_id()
        clone["parent_type"] = "projects"
        clone["parent_id"] = project_id
        clone["mirrored_from_file_id"] = f["id"]
        clone["mirrored_from_parent_type"] = "project_handovers"
        clone["mirrored_from_parent_id"] = handover_id
        clone["mirrored_at"] = now_iso()
        clone["mirrored_by"] = user.get("name") or user.get("email")
        clone.pop("_id", None)
        await db.files.insert_one(clone)
        clone.pop("_id", None)
        created += 1
    return created


# ─────────────────────────────── MODELS ───────────────────────────────
class HandoverIn(BaseModel):
    project_name: str = Field(..., min_length=2, max_length=160)
    client_name: str = Field(..., min_length=2, max_length=160)
    client_id: Optional[str] = None
    site_location: Optional[str] = None
    work_order_number: Optional[str] = None
    contract_value: float = 0.0
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    scope_of_work: Optional[str] = None
    billing_terms: Optional[str] = None
    payment_terms: Optional[str] = None
    gst_details: Optional[str] = None
    customer_contact_person: Optional[str] = None
    customer_contact_number: Optional[str] = None
    customer_email: Optional[str] = None
    special_conditions: Optional[str] = None
    safety_requirements: Optional[str] = None
    manpower_requirements: Optional[str] = None
    material_requirements: Optional[str] = None
    asset_requirements: Optional[str] = None
    remarks: Optional[str] = None
    attachments: List[Dict[str, Any]] = []


class HandoverUpdate(BaseModel):
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    client_id: Optional[str] = None
    site_location: Optional[str] = None
    work_order_number: Optional[str] = None
    contract_value: Optional[float] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    scope_of_work: Optional[str] = None
    billing_terms: Optional[str] = None
    payment_terms: Optional[str] = None
    gst_details: Optional[str] = None
    customer_contact_person: Optional[str] = None
    customer_contact_number: Optional[str] = None
    customer_email: Optional[str] = None
    special_conditions: Optional[str] = None
    safety_requirements: Optional[str] = None
    manpower_requirements: Optional[str] = None
    material_requirements: Optional[str] = None
    asset_requirements: Optional[str] = None
    remarks: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class AllocateIn(BaseModel):
    project_manager_id: Optional[str] = None
    project_coordinator_id: Optional[str] = None
    reporting_manager_id: Optional[str] = None
    department: Optional[str] = None
    priority: str = "medium"           # low/medium/high/critical
    expected_start_date: Optional[str] = None
    expected_completion_date: Optional[str] = None
    remarks: Optional[str] = None


# ─────────────────────────── HELPERS ───────────────────────────
def _ip(r: Request) -> str:
    return r.client.host if r.client else "unknown"


def _strip(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return d
    d.pop("_id", None)
    return d


async def _log_activity(handover_id: str, *, actor: dict, event: str, message: str,
                         meta: Optional[Dict[str, Any]] = None) -> None:
    await db.ops_activity.insert_one({
        "id": new_id(),
        "handover_id": handover_id,
        "event": event,
        "message": message,
        "by_id": actor.get("id"),
        "by_name": actor.get("name") or actor.get("email"),
        "by_role": actor.get("role"),
        "meta": meta or {},
        "at": now_iso(),
    })


async def _notify_role(role: str, *, kind: str, title: str, message: str,
                         link: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """In-app bell notification to every user with the given role."""
    users = await db.users.find({"role": role, "active": True}, {"_id": 0, "id": 1, "email": 1, "name": 1}).to_list(50)
    for u in users:
        if u.get("id"):
            await db.notifications.insert_one({
                "id": new_id(),
                "user_id": u["id"],
                "kind": kind,
                "title": title,
                "message": message,
                "link": link,
                "meta": meta or {},
                "read": False,
                "at": now_iso(),
            })


async def _notify_user(user_id: str, *, kind: str, title: str, message: str,
                         link: str, meta: Optional[Dict[str, Any]] = None) -> None:
    await db.notifications.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "kind": kind,
        "title": title,
        "message": message,
        "link": link,
        "meta": meta or {},
        "read": False,
        "at": now_iso(),
    })


async def _send_email_safe(to: str, subject: str, html: str) -> None:
    try:
        from notification_service import send_email, email_enabled
        if email_enabled():
            await send_email(to, subject, html)
    except Exception as e:  # pragma: no cover — fire-and-forget
        logger.warning("[ops] email send failed to=%s: %s", to, e)


def _scope_filter(user: dict) -> Dict[str, Any]:
    """Visibility:
      • super_admin / director / general_manager / dept_head → everything
      • sales_executive → only ones they submitted
      • project_manager / project_coordinator / 'Manager O P' / any custom
        role in 'Projects & Operations' department → only their assignments
      • everyone else → fall through (no filter)
    """
    from pm_scope import is_pm_scoped, pm_scope_clause
    role = user.get("role")
    if role in {"super_admin", "director", "general_manager", "dept_head", "accounts_executive"}:
        return {}
    uid = user.get("id")
    me = [uid, user.get("email"), user.get("name")]
    if role == "sales_executive":
        return {"$or": [
            {"submitted_by_id": uid},
            {"submitted_by": {"$in": me}},
            {"created_by_id": uid},
        ]}
    if is_pm_scoped(user):
        return pm_scope_clause(user)
    return {}


async def _hydrate_project_client_from_sales(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace each handover's `project_name` / `client_name` with the LIVE
    value from the linked quotation (preferred) or enquiry (fallback), so any
    edit done in Sales & Quotations is reflected instantly on the Contract
    Handovers page.

    The original snapshot is preserved in `project_name_original` and
    `client_name_original`. If neither a quote nor an enquiry is linked, the
    handover's stored values pass through untouched.
    """
    if not rows:
        return rows

    quote_ids = {r["quotation_id"] for r in rows if r.get("quotation_id")}
    enquiry_ids = {r["enquiry_id"] for r in rows if r.get("enquiry_id")}

    quotes_by_id: Dict[str, Dict[str, Any]] = {}
    if quote_ids:
        async for q in db.quotations.find(
            {"id": {"$in": list(quote_ids)}},
            {"_id": 0, "id": 1, "project": 1, "client": 1, "site_name": 1, "scope_of_work": 1},
        ):
            quotes_by_id[q["id"]] = q

    enquiries_by_id: Dict[str, Dict[str, Any]] = {}
    if enquiry_ids:
        async for e in db.enquiries.find(
            {"id": {"$in": list(enquiry_ids)}},
            {"_id": 0, "id": 1, "customer": 1, "scope_of_work": 1, "site_location": 1},
        ):
            enquiries_by_id[e["id"]] = e

    for r in rows:
        q = quotes_by_id.get(r.get("quotation_id") or "")
        e = enquiries_by_id.get(r.get("enquiry_id") or "")

        # PROJECT column → mirror Quotation Builder's "Site / project name" field
        # (`quote.site_name`). Fallback chain:
        #   quote.site_name  →  enquiry.site_location  →  quote.project (legacy) →
        #   enquiry.scope_of_work (truncated) → stored handover snapshot.
        live_project = None
        if q:
            live_project = (q.get("site_name") or "").strip() or None
        if not live_project and e:
            live_project = (e.get("site_location") or "").strip() or None
        if not live_project and q:
            live_project = (q.get("project") or "").strip() or None
        if not live_project and e:
            sow = (e.get("scope_of_work") or "").strip()
            live_project = sow[:160] or None

        live_client = None
        if q:
            live_client = (q.get("client") or "").strip() or None
        if not live_client and e:
            live_client = (e.get("customer") or "").strip() or None

        live_scope = None
        if q:
            live_scope = (q.get("scope_of_work") or "").strip() or None
        if not live_scope and e:
            live_scope = (e.get("scope_of_work") or "").strip() or None

        # Preserve original snapshot for traceability
        r["project_name_original"] = r.get("project_name")
        r["client_name_original"] = r.get("client_name")
        r["scope_of_work_original"] = r.get("scope_of_work")

        if live_project and live_project != r.get("project_name"):
            r["project_name"] = live_project
            # source priority: site_name(quote) > site_location(enquiry) > project(quote)
            if q and q.get("site_name"):
                r["project_name_source"] = "quotation"
            elif e and e.get("site_location"):
                r["project_name_source"] = "enquiry"
            elif q and q.get("project"):
                r["project_name_source"] = "quotation"
            else:
                r["project_name_source"] = "enquiry"
        if live_client and live_client != r.get("client_name"):
            r["client_name"] = live_client
            r["client_name_source"] = "quotation" if (q and q.get("client")) else "enquiry"
        if live_scope and live_scope != r.get("scope_of_work"):
            r["scope_of_work"] = live_scope
            r["scope_of_work_source"] = "quotation" if (q and q.get("scope_of_work")) else "enquiry"

    return rows


# ─────────────────────────── ENDPOINTS ───────────────────────────
@router.get("/ops/handovers")
async def list_handovers(status: Optional[str] = None,
                          user: dict = Depends(require_permission("project_handovers", "read"))):
    q: Dict[str, Any] = _scope_filter(user)
    if status:
        q["status"] = status
    rows = await db.project_handovers.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    rows = await _hydrate_project_client_from_sales(rows)
    return rows


@router.get("/ops/handovers/{hid}")
async def get_handover(hid: str, user: dict = Depends(require_permission("project_handovers", "read"))):
    row = await db.project_handovers.find_one({"id": hid}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Handover not found")
    # PM/Coordinator/'Manager O P' may only open their own assignments
    from pm_scope import can_view_handover
    if not can_view_handover(user, row):
        raise HTTPException(status_code=403, detail="You are not assigned to this handover")
    # Hydrate PM/coordinator/reporting manager names for the UI
    for fld in ("project_manager_id", "project_coordinator_id", "reporting_manager_id"):
        uid = row.get(fld)
        if uid:
            u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1, "email": 1, "role": 1})
            if u:
                row[fld.replace("_id", "") + "_label"] = u.get("name") or u.get("email")
    # Hydrate live project_name / client_name from Sales & Quotations
    await _hydrate_project_client_from_sales([row])
    return row


@router.post("/ops/handovers")
async def create_handover(payload: HandoverIn, request: Request,
                           user: dict = Depends(require_permission("project_handovers", "write"))):
    doc = payload.model_dump()
    doc["id"] = new_id()
    # Year-based handover number CHO-2026-0001
    doc["handover_no"] = await next_sequence("CHO")
    doc["status"] = "draft"
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    doc["created_by_id"] = user.get("id")
    if doc.get("work_order_number"):
        dup = await db.project_handovers.find_one({"work_order_number": doc["work_order_number"]})
        if dup:
            raise HTTPException(status_code=400, detail=f"Work order {doc['work_order_number']} already used in handover {dup.get('handover_no')}")
    await db.project_handovers.insert_one(doc)
    await _log_activity(doc["id"], actor=user, event="created",
                         message=f"Contract handover {doc['handover_no']} created (draft)")
    await audit(user=user, action="create", resource="project_handovers", record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.put("/ops/handovers/{hid}")
async def update_handover(hid: str, payload: HandoverUpdate, request: Request,
                           user: dict = Depends(require_permission("project_handovers", "write"))):
    existing = await db.project_handovers.find_one({"id": hid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Handover not found")
    if existing.get("status") not in EDITABLE_STATUSES and user.get("role") not in {"super_admin", "director"}:
        raise HTTPException(status_code=400, detail=f"Cannot edit handover in '{existing.get('status')}' state.")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.project_handovers.update_one({"id": hid}, {"$set": patch})
    await _log_activity(hid, actor=user, event="updated", message="Handover updated", meta={"keys": list(patch.keys())})
    await audit(user=user, action="update", resource="project_handovers", record_id=hid, after=patch, ip=_ip(request))
    fresh = await db.project_handovers.find_one({"id": hid}, {"_id": 0})
    return _strip(fresh)


@router.delete("/ops/handovers/{hid}")
async def delete_handover(hid: str, request: Request,
                           user: dict = Depends(require_permission("project_handovers", "delete"))):
    existing = await db.project_handovers.find_one({"id": hid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Handover not found")
    if existing.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Only draft handovers can be deleted")
    await db.project_handovers.delete_one({"id": hid})
    await audit(user=user, action="delete", resource="project_handovers", record_id=hid, before=existing, ip=_ip(request))
    return {"ok": True}


@router.post("/ops/handovers/{hid}/submit")
async def submit_handover(hid: str, request: Request,
                           user: dict = Depends(require_permission("project_handovers", "write"))):
    h = await db.project_handovers.find_one({"id": hid}, {"_id": 0})
    if not h:
        raise HTTPException(status_code=404, detail="Handover not found")
    if h.get("status") not in EDITABLE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Cannot submit handover in '{h.get('status')}' state.")
    missing = [f for f in ("project_name", "client_name", "contract_value") if not h.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")
    await db.project_handovers.update_one({"id": hid}, {"$set": {
        "status": "submitted",
        "submitted_at": now_iso(),
        "submitted_by": user.get("name") or user.get("email"),
        "submitted_by_id": user.get("id"),
        "updated_at": now_iso(),
    }})
    title = f"New contract handover {h['handover_no']}"
    msg = (f"New contract handover received from {user.get('name') or user.get('email')}. "
           f"Project: {h.get('project_name')} · Client: {h.get('client_name')} · "
           f"Contract Value: ₹{h.get('contract_value') or 0:,.2f}")
    link = f"/app/ops/handovers/{hid}"
    # Bell notifications to project heads
    for role in ("dept_head", "project_manager"):
        await _notify_role(role, kind="ops.handover.submitted", title=title, message=msg, link=link,
                            meta={"handover_id": hid, "handover_no": h["handover_no"]})
    # Email to dept_head users (first 5)
    heads = await db.users.find({"role": "dept_head", "active": True}, {"_id": 0, "email": 1, "name": 1}).to_list(20)
    for hd in heads:
        if hd.get("email"):
            await _send_email_safe(hd["email"], f"[ERP] {title}",
                f"<p>Dear {hd.get('name') or 'Project Head'},</p>"
                f"<p>{msg}</p>"
                f"<p><a href='{link}'>Open handover</a></p>")
    await _log_activity(hid, actor=user, event="submitted",
                         message="Submitted for Project Head review")
    await audit(user=user, action="submit", resource="project_handovers", record_id=hid, ip=_ip(request))
    return {"ok": True, "handover_id": hid, "notified_roles": ["dept_head", "project_manager"]}


@router.post("/ops/handovers/{hid}/allocate")
async def allocate_handover(hid: str, payload: AllocateIn, request: Request,
                              user: dict = Depends(require_permission("project_handovers", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager", "dept_head"}:
        raise HTTPException(status_code=403, detail="Only Project Heads / Department Heads can allocate handovers")
    h = await db.project_handovers.find_one({"id": hid}, {"_id": 0})
    if not h:
        raise HTTPException(status_code=404, detail="Handover not found")
    if h.get("status") not in {"submitted", "under_review", "allocated", "active"}:
        raise HTTPException(status_code=400, detail=f"Cannot allocate handover in '{h.get('status')}' state.")
    if not (payload.project_manager_id or payload.project_coordinator_id):
        raise HTTPException(status_code=400, detail="At least one of project_manager_id or project_coordinator_id is required")

    # Resolve user labels
    async def _label(uid: Optional[str]) -> Optional[str]:
        if not uid:
            return None
        u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1, "email": 1})
        return (u or {}).get("name") or (u or {}).get("email")

    pm_label = await _label(payload.project_manager_id)
    pc_label = await _label(payload.project_coordinator_id)
    rm_label = await _label(payload.reporting_manager_id)

    is_first_allocation = h.get("status") in {"submitted", "under_review"}

    # Bug fix — Projects must originate ONLY from the Enquiry→Order conversion
    # path. If the handover has no `project_id`, the operator must first convert
    # the underlying enquiry to an order. We DO NOT silently auto-create.
    project_id = h.get("project_id")

    # Iter 93 — Self-heal: an earlier code-path created the handover BEFORE the
    # enquiry was converted (the link was missed). Before erroring, look up the
    # current project via the source enquiry/quotation/order and back-fill it
    # on this handover. This unblocks allocation for any handover that lost
    # the link due to the conversion order-of-operations.
    if not project_id:
        proj = None
        if h.get("order_id"):
            o = await db.orders.find_one({"id": h["order_id"]}, {"_id": 0, "project_id": 1, "project_code": 1})
            if o and o.get("project_id"):
                proj = o
        if not proj and h.get("enquiry_id"):
            e = await db.enquiries.find_one({"id": h["enquiry_id"]}, {"_id": 0, "project_id": 1, "project_code": 1, "order_id": 1, "order_no": 1})
            if e and e.get("project_id"):
                proj = e
        if not proj and h.get("quotation_id"):
            p = await db.projects.find_one({"quotation_id": h["quotation_id"]}, {"_id": 0, "id": 1, "code": 1})
            if p:
                proj = {"project_id": p["id"], "project_code": p.get("code")}
        if proj and proj.get("project_id"):
            project_id = proj["project_id"]
            await db.project_handovers.update_one(
                {"id": hid},
                {"$set": {
                    "project_id": project_id,
                    "project_code": proj.get("project_code"),
                    "order_id": proj.get("order_id") or h.get("order_id"),
                    "order_no": proj.get("order_no") or h.get("order_no"),
                    "updated_at": now_iso(),
                }},
            )

    if is_first_allocation and not project_id:
        raise HTTPException(
            400,
            "Cannot allocate manpower — no Project linked to this Handover. "
            "Please convert the source Enquiry to an Order (Sales → Enquiries → "
            "Convert to Order). The Order conversion creates the Project, after "
            "which manpower allocation can proceed.",
        )

    set_doc = {
        "status": "active" if is_first_allocation else h.get("status"),
        "project_id": project_id,
        "project_manager_id": payload.project_manager_id,
        "project_coordinator_id": payload.project_coordinator_id,
        "reporting_manager_id": payload.reporting_manager_id,
        "department": payload.department,
        "priority": payload.priority,
        "expected_start_date": payload.expected_start_date,
        "expected_completion_date": payload.expected_completion_date,
        "allocation_remarks": payload.remarks,
        "allocated_at": now_iso(),
        "allocated_by": user.get("name") or user.get("email"),
        "allocated_by_id": user.get("id"),
        "updated_at": now_iso(),
    }
    await db.project_handovers.update_one({"id": hid}, {"$set": set_doc})

    # Iter 70 — Mirror handover-attached files onto the new project record so
    # the field team sees the contract / WO / drawings immediately in the
    # Project Dashboard without having to dig through Handovers. This only
    # runs on the FIRST allocation (when the project is just created).
    if is_first_allocation and project_id:
        try:
            mirrored = await _mirror_handover_files_to_project(hid, project_id, user)
            if mirrored:
                logger.info(f"Mirrored {mirrored} handover file(s) to project {project_id}")
        except Exception as e:
            logger.warning(f"Failed to mirror handover files: {e}")

    # If a project already exists, sync the assignment so MyProjects keeps working.
    if project_id and not is_first_allocation:
        await db.projects.update_one({"id": project_id}, {"$set": {
            "project_manager_id": payload.project_manager_id,
            "project_coordinator_id": payload.project_coordinator_id,
            "reporting_manager_id": payload.reporting_manager_id,
            "department": payload.department,
            "priority": payload.priority,
            "updated_at": now_iso(),
        }})

    # Notify assigned PM/Coordinator + Reporting Manager (bell + email)
    title = f"Project allocated: {h.get('project_name')}"
    msg = (f"You have been assigned to project {h.get('project_name')} (Client: {h.get('client_name')}, "
           f"Contract Value: ₹{h.get('contract_value') or 0:,.2f}). "
           f"Allocated by {user.get('name') or user.get('email')}.")
    link = "/app/ops/my-projects"
    for uid in [payload.project_manager_id, payload.project_coordinator_id, payload.reporting_manager_id]:
        if uid:
            await _notify_user(uid, kind="ops.project.allocated", title=title, message=msg, link=link,
                                 meta={"handover_id": hid, "project_id": project_id})
            u = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1, "name": 1})
            if u and u.get("email"):
                await _send_email_safe(u["email"], f"[ERP] {title}",
                    f"<p>Dear {u.get('name') or 'Manager'},</p><p>{msg}</p>"
                    f"<p><a href='{link}'>Open My Projects</a></p>")
    summary = ", ".join([x for x in [
        f"PM: {pm_label}" if pm_label else None,
        f"Coordinator: {pc_label}" if pc_label else None,
        f"Reporting Manager: {rm_label}" if rm_label else None,
    ] if x])
    await _log_activity(hid, actor=user, event="allocated" if is_first_allocation else "reassigned",
                         message=f"{'Allocated' if is_first_allocation else 'Re-assigned'} → {summary}",
                         meta={"project_id": project_id, **set_doc})
    await audit(user=user, action="allocate", resource="project_handovers", record_id=hid, after=set_doc, ip=_ip(request))
    return {"ok": True, "handover_id": hid, "project_id": project_id, "status": set_doc["status"]}


@router.post("/ops/handovers/{hid}/reassign")
async def reassign(hid: str, payload: AllocateIn, request: Request,
                    user: dict = Depends(require_permission("project_handovers", "write"))):
    """Alias for allocate — keeps backend contract clean when the UI uses Reassign button."""
    return await allocate_handover(hid, payload, request, user)


@router.get("/ops/my-projects")
async def my_projects(user: dict = Depends(get_current_user)):
    uid = user.get("id")
    role = user.get("role")
    # Management roles see everything (per business rule)
    MGMT = {"super_admin", "director", "general_manager", "dept_head"}
    if role in MGMT:
        q = {}
    elif not uid:
        # Defensive: never broadcast every handover if we can't identify the user
        q = {"id": "__never_matches__"}
    else:
        # Match against uid, email and name to be resilient to legacy data
        # where the label was stored instead of the id.
        aliases = [a for a in (uid, user.get("email"), user.get("name")) if a]
        q = {"$or": [
            {"project_manager_id": {"$in": aliases}},
            {"project_coordinator_id": {"$in": aliases}},
            {"reporting_manager_id": {"$in": aliases}},
        ]}
    rows = await db.project_handovers.find(q, {"_id": 0}).sort("allocated_at", -1).to_list(500)
    # Hydrate label fields for the UI
    for r in rows:
        for fld in ("project_manager_id", "project_coordinator_id", "reporting_manager_id"):
            v = r.get(fld)
            if v:
                u = await db.users.find_one({"id": v}, {"_id": 0, "name": 1, "email": 1})
                if u:
                    r[fld.replace("_id", "") + "_label"] = u.get("name") or u.get("email")
    # Hydrate live project_name / client_name from Sales & Quotations
    await _hydrate_project_client_from_sales(rows)
    return rows


@router.get("/ops/handovers/{hid}/timeline")
async def timeline(hid: str, user: dict = Depends(require_permission("project_handovers", "read"))):
    rows = await db.ops_activity.find({"handover_id": hid}, {"_id": 0}).sort("at", -1).to_list(500)
    return rows


@router.get("/ops/assignable-users")
async def assignable_users(user: dict = Depends(get_current_user)):
    """Returns the candidate options for PM / Coordinator / Reporting-Manager slots.

    Iter 90 — Per business rule:
      • Project Manager  → HRMS employees whose `designation` is "Projects & Operations"
      • Project Coordinator → HRMS employees whose `designation` is "Data Entry Operator"
      • Reporting Manager → existing pool (dept_head / GM / director / PM users)

    Each employee option is augmented with a `linked_user_id` (matched by name,
    case-insensitive) so that allocation can still drive notifications and the
    user-level "My Assigned Projects" filter. The option's `id` is the user id
    when a link is found, otherwise the employee id — keeping the existing
    `project_manager_id` / `project_coordinator_id` field semantics intact.
    """
    PM_DESIGNATION = "projects & operations"
    PC_DESIGNATION = "data entry operator"

    def _norm(s):
        return (s or "").strip().lower()

    async def _hrms_by_designation(designation: str):
        rows = await db.employees.find(
            {"status": {"$ne": "inactive"}},
            {"_id": 0, "id": 1, "name": 1, "designation": 1,
             "department": 1, "employee_id": 1, "phone": 1, "email": 1},
        ).sort("name", 1).to_list(1000)
        rows = [r for r in rows if _norm(r.get("designation")) == designation]
        # Bridge employee → user account by name (case-insensitive exact match)
        for r in rows:
            r["employee_record_id"] = r.get("id")
            r["linked_user_id"] = None
            nm = (r.get("name") or "").strip()
            if not nm:
                continue
            u = await db.users.find_one(
                {"name": {"$regex": f"^{re.escape(nm)}$", "$options": "i"}, "active": {"$ne": False}},
                {"_id": 0, "id": 1, "email": 1},
            )
            if u:
                r["linked_user_id"] = u["id"]
                r["linked_user_email"] = u.get("email")
                # Override `id` so downstream code stores the user id whenever possible
                r["id"] = u["id"]
        return rows

    pm = await _hrms_by_designation(PM_DESIGNATION)
    pc = await _hrms_by_designation(PC_DESIGNATION)

    rm = await db.users.find(
        {"role": {"$in": ["dept_head", "general_manager", "director", "project_manager"]},
         "active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "department": 1},
    ).sort("name", 1).to_list(200)

    return {
        "project_manager": pm,
        "project_coordinator": pc,
        "reporting_manager": rm,
    }
