"""P&O Phase 1 · Project Dashboard KPIs + workflow validators + status history.

EXTENDS the existing `projects` collection (NO duplication) by:
  • `/api/proj-masters/dashboard-kpis` — returns counts for all 20 dashboard cards
    in one round-trip, plus drill-down ids.
  • `/api/proj-masters/projects/{id}/status` — workflow-validated status change
    that writes to `project_status_history` and enforces:
      - draft → planned → approved → mobilization_pending → active → closure_pending → closed
      - status change requires project_manager + site location + work order ref
      - closed projects cannot be edited except by super_admin (reopen)
  • `/api/proj-masters/projects/{id}/approve` — approval workflow gate.
  • `/api/proj-masters/projects/{id}/status-history` — view audit trail per project.

The generic `/api/projects` PUT remains as a super-admin escape hatch.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, require_permission, get_current_user, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/proj-masters", tags=["projects-ops-phase1"])


# ───────────────────── Dashboard KPIs (20 cards) ─────────────────────
@router.get("/dashboard-kpis")
async def dashboard_kpis(user: dict = Depends(require_permission("projects", "read"))):
    """Returns counts + drill-down ids for the 20 Project Dashboard cards.

    PM-scoped users (project_manager, project_coordinator, 'Manager O P' or
    any custom role in 'Projects & Operations' department) see only KPIs
    computed over projects assigned to them.
    """
    from pm_scope import is_pm_scoped, pm_scope_clause
    today = datetime.now(timezone.utc).date().isoformat()
    out: Dict[str, Any] = {}

    # Build a base scope filter once; merged into every query below.
    scope: Dict[str, Any] = pm_scope_clause(user) if is_pm_scoped(user) else {}

    def _merge(q: Dict[str, Any]) -> Dict[str, Any]:
        if not scope:
            return q
        if not q:
            return dict(scope)
        return {"$and": [scope, q]}

    async def count_and_ids(q: Dict[str, Any], limit: int = 20):
        q = _merge(q)
        cnt = await db.projects.count_documents(q)
        ids = [r["id"] async for r in db.projects.find(q, {"_id": 0, "id": 1}).limit(limit)]
        return {"count": cnt, "ids": ids}

    out["total_projects"]                    = await count_and_ids({})
    out["active_projects"]                   = await count_and_ids({"status": "active"})
    out["planned_projects"]                  = await count_and_ids({"status": "planned"})
    out["mobilization_pending_projects"]     = await count_and_ids({"status": "mobilization_pending"})
    out["projects_on_hold"]                  = await count_and_ids({"status": "on_hold"})
    out["completed_projects"]                = await count_and_ids({"status": "completed"})
    out["closure_pending_projects"]          = await count_and_ids({"status": "closure_pending"})
    # Delayed: end_date in past AND status not in completed/closed
    out["delayed_projects"] = await count_and_ids({
        "end_date": {"$lt": today, "$ne": ""},
        "status": {"$nin": ["completed", "closed", "cancelled"]},
    })
    out["shutdown_projects"]                 = await count_and_ids({
        "$or": [{"priority": "shutdown"}, {"category": "shutdown"}, {"type": "shutdown"}],
    })
    out["projects_without_pm"] = await count_and_ids({
        "$and": [
            {"status": {"$nin": ["draft", "cancelled", "closed"]}},
            {"$or": [{"manager": {"$exists": False}}, {"manager": ""}, {"manager": None}]},
        ],
    })
    out["projects_without_site_incharge"] = await count_and_ids({
        "$and": [
            {"status": {"$nin": ["draft", "cancelled", "closed"]}},
            {"$or": [{"site_supervisor": {"$exists": False}}, {"site_supervisor": ""}, {"site_supervisor": None}]},
        ],
    })
    out["projects_pending_approval"] = await count_and_ids({
        "$or": [{"status": "planned"}, {"approval_status": "pending"}],
    })
    out["projects_requiring_manpower"] = await count_and_ids({
        "$or": [{"manpower_required": True}, {"manpower_status": "pending"},
                {"manpower_requirement": {"$exists": True, "$nin": [None, ""]}}],
    })
    out["projects_requiring_material"] = await count_and_ids({
        "$or": [{"material_required": True}, {"material_status": "pending"},
                {"material_requirement": {"$exists": True, "$nin": [None, ""]}}],
    })
    out["projects_requiring_safety_clearance"] = await count_and_ids({
        "$or": [{"safety_clearance_required": True}, {"safety_status": "pending"}],
    })
    out["projects_pending_billing"] = await count_and_ids({
        "$or": [{"billing_status": "pending"}, {"client_billing_pending": True}],
    })
    out["projects_with_pending_closure"] = await count_and_ids({"status": "closure_pending"})

    # Recent — last 10 by created_at
    recent_cur = db.projects.find(_merge({}), {"_id": 0, "id": 1, "code": 1, "name": 1, "client": 1, "status": 1, "created_at": 1}).sort("created_at", -1).limit(10)
    out["recent_projects"] = {"count": 0, "items": []}
    async for r in recent_cur:
        out["recent_projects"]["items"].append(r)
    out["recent_projects"]["count"] = len(out["recent_projects"]["items"])

    # High-value — contract_value > 10 lakh, top 10
    hv_cur = db.projects.find(_merge({"contract_value": {"$gt": 1000000}}),
        {"_id": 0, "id": 1, "code": 1, "name": 1, "client": 1, "contract_value": 1, "status": 1}
    ).sort("contract_value", -1).limit(10)
    out["high_value_projects"] = {"count": 0, "items": []}
    async for r in hv_cur:
        out["high_value_projects"]["items"].append(r)
    out["high_value_projects"]["count"] = len(out["high_value_projects"]["items"])

    # Status summary — counts grouped by status
    out["status_summary"] = {}
    pipeline = []
    if scope:
        pipeline.append({"$match": scope})
    pipeline.append({"$group": {"_id": "$status", "n": {"$sum": 1}}})
    async for r in db.projects.aggregate(pipeline):
        out["status_summary"][r["_id"] or "(unset)"] = r["n"]

    return out


# ───────────────────── Status Workflow with Validation ─────────────────────
ALLOWED_NEXT = {
    "draft":                  {"planned", "cancelled"},
    "planned":                {"approved", "cancelled", "draft"},
    "approved":               {"mobilization_pending", "cancelled"},
    "mobilization_pending":   {"active", "on_hold", "cancelled"},
    "active":                 {"on_hold", "closure_pending", "completed", "cancelled"},
    "on_hold":                {"active", "cancelled", "closure_pending"},
    "completed":              {"closure_pending", "closed"},
    "closure_pending":        {"closed"},
    "closed":                 set(),  # terminal — only super_admin can reopen
    "cancelled":              set(),
}


class StatusChange(BaseModel):
    new_status: str
    reason: Optional[str] = ""
    override: bool = False  # only honoured for super_admin


def _missing_required_for_approval(p: dict) -> List[str]:
    miss: List[str] = []
    if not (p.get("manager") or "").strip():
        miss.append("project_manager")
    if not (p.get("site") or p.get("site_address") or "").strip():
        miss.append("site_location")
    if not (p.get("work_order_number") or p.get("sales_quotation_ref") or "").strip():
        miss.append("work_order_reference")
    return miss


@router.put("/projects/{pid}/status")
async def change_project_status(pid: str, payload: StatusChange,
                                  user: dict = Depends(require_permission("projects", "write"))):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    cur = p.get("status") or "draft"
    nxt = payload.new_status
    is_admin = user.get("role") == "super_admin"

    # Closed → only super_admin can reopen
    if cur == "closed" and not is_admin:
        raise HTTPException(403, "Closed projects can only be reopened by Super Admin")

    # Validate transition
    if not payload.override and nxt not in ALLOWED_NEXT.get(cur, set()):
        if not (is_admin and payload.override):
            raise HTTPException(400,
                f"Cannot transition from '{cur}' to '{nxt}'. Allowed next: {sorted(ALLOWED_NEXT.get(cur, set())) or '— none —'}.")

    # Approval gate — must have PM, site location, WO ref
    if nxt in ("approved", "active") and not (is_admin and payload.override):
        missing = _missing_required_for_approval(p)
        if missing:
            raise HTTPException(400,
                f"Cannot move to '{nxt}' — missing required fields: {', '.join(missing)}. "
                "Either fill them in Project Master, or request Super Admin override.")

    # Write status + project_status_history entry
    history = list(p.get("project_status_history") or [])
    history.append({
        "id": new_id(),
        "at": now_iso(),
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "by_role": user.get("role"),
        "from_status": cur,
        "to_status": nxt,
        "reason": payload.reason or "",
        "override": bool(payload.override and is_admin),
    })
    patch = {
        "status": nxt,
        "project_status_history": history,
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }
    if nxt == "approved":
        patch["approved_by"] = user.get("name") or user.get("email")
        patch["approved_at"] = now_iso()
        patch["approval_status"] = "approved"
    if nxt == "completed":
        patch["actual_completion_date"] = patch.get("actual_completion_date") or now_iso()[:10]

    await db.projects.update_one({"id": pid}, {"$set": patch})
    # Audit log entry
    await audit(user=user, action=f"status:{nxt}", resource="projects",
                 record_id=pid, before={"status": cur}, after={"status": nxt}, ip="workflow")
    return await db.projects.find_one({"id": pid}, {"_id": 0})


@router.get("/projects/{pid}/status-history")
async def status_history(pid: str, user: dict = Depends(require_permission("projects", "read"))):
    p = await db.projects.find_one({"id": pid}, {"_id": 0, "project_status_history": 1})
    if not p:
        raise HTTPException(404, "Project not found")
    return p.get("project_status_history") or []


# ───────────────────── Approval shortcut (Owner/Project Head) ─────────────────────
class ApproveIn(BaseModel):
    note: Optional[str] = ""


@router.post("/projects/{pid}/approve")
async def approve_project(pid: str, payload: ApproveIn,
                            user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head"):
        raise HTTPException(403, "Only Owner / Project Head / Ops Head can approve a project")
    return await change_project_status(pid, StatusChange(new_status="approved", reason=payload.note), user)


# ───────────────────── Duplicate-code validation ─────────────────────
@router.get("/projects/check-code/{code}")
async def check_duplicate_code(code: str, exclude_id: Optional[str] = None,
                                 user: dict = Depends(require_permission("projects", "read"))):
    q = {"code": code.strip()}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    existing = await db.projects.find_one(q, {"_id": 0, "id": 1, "code": 1, "name": 1})
    return {"exists": bool(existing), "existing": existing}
