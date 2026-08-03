"""Project Assignment Manager — assign/transfer PM & Coordinator with history.

Admin roles only. History stored on the project doc (assignment_history[]).
New assignees are notified; scoping updates instantly (evaluated live).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/ops/project-assignments", tags=["project-assignments"])

ADMIN_ROLES = {"super_admin", "director", "general_manager", "dept_head"}
ASSIGNEE_ROLES = ["project_manager", "project_coordinator", "site_engineer", "site_supervisor", "dept_head"]


def _require_admin(user: dict) -> None:
    if user.get("role") not in ADMIN_ROLES:
        raise HTTPException(403, "Only Project Head and above can manage assignments")


class AssignIn(BaseModel):
    project_manager_id: Optional[str] = None
    project_coordinator_id: Optional[str] = None
    remarks: Optional[str] = None


@router.get("")
async def list_assignments(user: dict = Depends(get_current_user)):
    _require_admin(user)
    projects = await db.projects.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1, "client": 1,
                                           "status": 1, "project_manager_id": 1, "project_manager_name": 1,
                                           "project_coordinator_id": 1, "project_coordinator_name": 1,
                                           "assignment_history": 1}).sort("code", 1).to_list(500)
    for p in projects:
        p["history_count"] = len(p.pop("assignment_history", []) or [])
    users = await db.users.find({"role": {"$in": ASSIGNEE_ROLES}, "active": {"$ne": False}},
                                {"_id": 0, "id": 1, "name": 1, "role": 1}).sort("name", 1).to_list(300)
    return {"projects": projects, "users": users}


@router.post("/{project_id}")
async def assign(project_id: str, p: AssignIn, request: Request,
                 user: dict = Depends(get_current_user)):
    _require_admin(user)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Project not found")

    async def _name(uid: Optional[str]) -> Optional[str]:
        if not uid:
            return None
        u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1})
        if not u:
            raise HTTPException(400, "Selected user not found")
        return u.get("name")

    patch: dict = {}
    events = []
    for field, name_field, label in (("project_manager_id", "project_manager_name", "Project Manager"),
                                     ("project_coordinator_id", "project_coordinator_name", "Project Coordinator")):
        new_id_val = getattr(p, field)
        if new_id_val is None or new_id_val == proj.get(field):
            continue
        new_name = await _name(new_id_val) if new_id_val else None
        patch[field] = new_id_val or None
        patch[name_field] = new_name
        events.append({"id": new_id(), "field": label,
                       "from_id": proj.get(field), "from_name": proj.get(name_field),
                       "to_id": new_id_val or None, "to_name": new_name,
                       "remarks": p.remarks, "by": user.get("name") or user.get("email"),
                       "at": now_iso()})
    if not patch:
        return {"ok": True, "changed": 0}
    patch["updated_at"] = now_iso()
    await db.projects.update_one({"id": project_id},
                                 {"$set": patch, "$push": {"assignment_history": {"$each": events}}})
    for ev in events:
        if ev["to_id"]:
            await db.notifications.insert_one({
                "id": new_id(), "user_id": ev["to_id"], "kind": "assignment",
                "title": f"You are now {ev['field']} — {proj.get('code')}",
                "message": f"{proj.get('code')} · {proj.get('name')} assigned to you by {ev['by']}."
                           + (f" Note: {p.remarks}" if p.remarks else ""),
                "link": "/app/ops/my-projects", "read": False, "at": now_iso()})
        if ev["from_id"] and ev["from_id"] != ev["to_id"]:
            await db.notifications.insert_one({
                "id": new_id(), "user_id": ev["from_id"], "kind": "assignment",
                "title": f"{ev['field']} transferred — {proj.get('code')}",
                "message": f"{proj.get('code')} · {proj.get('name')} is now handled by {ev['to_name'] or '—'}.",
                "link": "/app/ops/my-projects", "read": False, "at": now_iso()})
    await audit(user=user, action="project_assignment", resource="projects", record_id=project_id,
                after={"events": events}, ip=request.client.host if request.client else "")
    out = await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1, "code": 1,
                                                          "project_manager_id": 1, "project_manager_name": 1,
                                                          "project_coordinator_id": 1, "project_coordinator_name": 1})
    return {"ok": True, "changed": len(events), "project": out}


@router.get("/{project_id}/history")
async def history(project_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "code": 1, "name": 1, "assignment_history": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    rows = sorted(proj.get("assignment_history") or [], key=lambda e: e.get("at") or "", reverse=True)
    return {"project_code": proj.get("code"), "project_name": proj.get("name"), "history": rows}
