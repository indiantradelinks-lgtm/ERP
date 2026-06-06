"""Phase-3 deferred mutations triggered by approval completion.

When an approval document of type `department_move` or `deployment` reaches
fully-approved status, the `apply_*` functions below execute the original
mutation (updating the underlying record and writing employee_history).

Called from routers/approvals_router.approval_action.
"""
from typing import Optional

from core import db, now_iso, new_id, logger


async def _log_history(*, employee_id: str, employee_name: str, action: str,
                       from_value, to_value, project: Optional[str],
                       actor_id: Optional[str], actor_name: Optional[str], note: str = "") -> None:
    await db.employee_history.insert_one({
        "id": new_id(),
        "employee_id": employee_id,
        "employee_name": employee_name,
        "action": action,
        "from": from_value,
        "to": to_value,
        "project": project,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "note": note,
        "at": now_iso(),
    })


async def apply_department_move(approval: dict) -> None:
    """Apply a pending department_move approval.
    Expects approval.metadata = {employee_id, target_departments, note}.
    """
    meta = approval.get("metadata") or {}
    emp_id = meta.get("employee_id")
    target = [d for d in (meta.get("target_departments") or []) if d]
    if not emp_id or not target:
        logger.warning(f"department_move apply skipped — missing metadata on approval {approval.get('id')}")
        return
    emp = await db.employees.find_one({"id": emp_id}, {"_id": 0})
    if not emp:
        logger.warning(f"department_move apply skipped — employee {emp_id} not found")
        return
    before_depts = emp.get("departments") or ([emp.get("department")] if emp.get("department") else [])
    await db.employees.update_one(
        {"id": emp_id},
        {"$set": {"departments": target, "department": target[0], "updated_at": now_iso()}},
    )
    history = approval.get("history") or []
    actor = history[-1] if history else {}
    await _log_history(
        employee_id=emp_id, employee_name=emp.get("name", ""),
        action="department_move", from_value=before_depts, to_value=target,
        project=None,
        actor_id=actor.get("by_id"), actor_name=actor.get("by"),
        note=meta.get("note") or "via approval",
    )


async def apply_deployment(approval: dict) -> None:
    """Activate a pending deployment when its approval is fully approved."""
    dep_id = approval.get("record_id")
    if not dep_id:
        return
    dep = await db.deployments.find_one({"id": dep_id}, {"_id": 0})
    if not dep:
        return
    if dep.get("status") != "pending_approval":
        return
    await db.deployments.update_one(
        {"id": dep_id},
        {"$set": {"status": "active", "updated_at": now_iso()}},
    )
    history = approval.get("history") or []
    actor = history[-1] if history else {}
    if dep.get("employee_id"):
        await _log_history(
            employee_id=dep["employee_id"], employee_name=dep.get("employee", ""),
            action="deployment_start",
            from_value=None,
            to_value={"project": dep.get("project"), "site_role": dep.get("site_role") or dep.get("role"),
                      "start_date": dep.get("start_date"), "shift": dep.get("shift")},
            project=dep.get("project"),
            actor_id=actor.get("by_id"), actor_name=actor.get("by"),
            note="via approval",
        )


async def reject_deployment(approval: dict) -> None:
    """Mark a deployment doc as withdrawn when its approval is rejected."""
    dep_id = approval.get("record_id")
    if not dep_id:
        return
    dep = await db.deployments.find_one({"id": dep_id}, {"_id": 0})
    if not dep or dep.get("status") != "pending_approval":
        return
    await db.deployments.update_one(
        {"id": dep_id},
        {"$set": {"status": "withdrawn", "updated_at": now_iso()}},
    )
