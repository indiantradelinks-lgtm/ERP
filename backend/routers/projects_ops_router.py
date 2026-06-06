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
      • project_manager / project_coordinator → ones allocated to them
      • everyone else → fall through (no filter)
    """
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
    if role in {"project_manager", "project_coordinator"}:
        return {"$or": [
            {"project_manager_id": uid},
            {"project_coordinator_id": uid},
            {"reporting_manager_id": uid},
        ]}
    return {}


# ─────────────────────────── ENDPOINTS ───────────────────────────
@router.get("/ops/handovers")
async def list_handovers(status: Optional[str] = None,
                          user: dict = Depends(require_permission("project_handovers", "read"))):
    q: Dict[str, Any] = _scope_filter(user)
    if status:
        q["status"] = status
    rows = await db.project_handovers.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return rows


@router.get("/ops/handovers/{hid}")
async def get_handover(hid: str, user: dict = Depends(require_permission("project_handovers", "read"))):
    row = await db.project_handovers.find_one({"id": hid}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Handover not found")
    # Hydrate PM/coordinator/reporting manager names for the UI
    for fld in ("project_manager_id", "project_coordinator_id", "reporting_manager_id"):
        uid = row.get(fld)
        if uid:
            u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1, "email": 1, "role": 1})
            if u:
                row[fld.replace("_id", "") + "_label"] = u.get("name") or u.get("email")
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

    # Auto-create a Project row on first allocation, so existing modules
    # (PR / Stores / HR / DPR) immediately work against this project.
    project_id = h.get("project_id")
    if is_first_allocation and not project_id:
        from sequences import next_sequence as _seq
        project_id = new_id()
        proj_code = await _seq("PRJ")
        await db.projects.insert_one({
            "id": project_id,
            "code": proj_code,
            "name": h.get("project_name"),
            "client_id": h.get("client_id"),
            "client_name": h.get("client_name"),
            "site_location": h.get("site_location"),
            "work_order_number": h.get("work_order_number"),
            "contract_value": h.get("contract_value") or 0,
            "contract_start_date": h.get("contract_start_date"),
            "contract_end_date": h.get("contract_end_date"),
            "status": "active",
            "project_manager_id": payload.project_manager_id,
            "project_coordinator_id": payload.project_coordinator_id,
            "reporting_manager_id": payload.reporting_manager_id,
            "department": payload.department,
            "priority": payload.priority,
            "handover_id": hid,
            "handover_no": h.get("handover_no"),
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
        })

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
    q = {"$or": [
        {"project_manager_id": uid},
        {"project_coordinator_id": uid},
        {"reporting_manager_id": uid},
    ]}
    # Super-admin/director/GM see all
    if user.get("role") in {"super_admin", "director", "general_manager", "dept_head"}:
        q = {}
    rows = await db.project_handovers.find(q, {"_id": 0}).sort("allocated_at", -1).to_list(500)
    # Hydrate label fields for the UI
    for r in rows:
        for fld in ("project_manager_id", "project_coordinator_id", "reporting_manager_id"):
            v = r.get(fld)
            if v:
                u = await db.users.find_one({"id": v}, {"_id": 0, "name": 1, "email": 1})
                if u:
                    r[fld.replace("_id", "") + "_label"] = u.get("name") or u.get("email")
    return rows


@router.get("/ops/handovers/{hid}/timeline")
async def timeline(hid: str, user: dict = Depends(require_permission("project_handovers", "read"))):
    rows = await db.ops_activity.find({"handover_id": hid}, {"_id": 0}).sort("at", -1).to_list(500)
    return rows


@router.get("/ops/assignable-users")
async def assignable_users(user: dict = Depends(get_current_user)):
    """Returns the candidate users for PM / Coordinator / Reporting-Manager slots."""
    roles = {
        "project_manager": ["project_manager", "dept_head"],
        "project_coordinator": ["project_coordinator", "project_manager"],
        "reporting_manager": ["dept_head", "general_manager", "director", "project_manager"],
    }
    out = {}
    for slot, role_list in roles.items():
        users = await db.users.find(
            {"role": {"$in": role_list}, "active": True},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "department": 1},
        ).sort("name", 1).to_list(200)
        out[slot] = users
    return out
