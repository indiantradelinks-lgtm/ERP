"""User scope resolution.

Resolves what departments and projects an authenticated user "belongs" to.
Used by:
- /api/me/scope (returns scope to frontend so it can scope dashboards)
- list endpoint visibility filters (site-level roles only see records tied to
  their assigned projects; dept_head only sees their dept's records)

A user's scope is derived from two sources:
1) Their own user document — `department` (legacy single) and/or
   `departments[]` (new multi-dept array).
2) Their active deployments — any deployment row where `employee_id` matches
   their user id OR `employee_email`/`employee` matches, AND the deployment is
   not ended/withdrawn.

Roles that get global visibility (no filtering):
    super_admin, director, general_manager, hr_executive

Roles that get department-scoped visibility (employees + dept-tagged rows):
    dept_head

Roles that get project-scoped visibility (only see records for their assigned
projects):
    site_engineer, supervisor, safety_officer, store_incharge,
    purchase_officer (when not admin), project_manager (for site rows only)
"""
from typing import Dict, List
from datetime import datetime, timezone

from core import db


GLOBAL_ROLES = {"super_admin", "director", "general_manager", "hr_executive"}
DEPT_SCOPED_ROLES = {"dept_head"}
PROJECT_SCOPED_ROLES = {
    "site_engineer", "supervisor", "safety_officer", "store_incharge",
}


def _user_departments(user: dict) -> List[str]:
    """Return the union of single-dept (legacy) and multi-dept fields."""
    out: List[str] = []
    legacy = user.get("department")
    if legacy:
        out.append(legacy)
    for d in user.get("departments") or []:
        if d and d not in out:
            out.append(d)
    return out


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _active_projects_for(user: dict) -> List[str]:
    """All distinct project codes/names the user is actively deployed to.

    A deployment is considered active when:
      - status not in {completed, withdrawn}
      - end_date is missing OR end_date >= today
    """
    today = _today()
    # Match by user id or email. Name matching is intentionally avoided —
    # common names (e.g. multiple "Rajesh") would otherwise grant a user access
    # to projects assigned to a different person.
    or_filters = []
    if user.get("id"):
        or_filters.append({"employee_id": user["id"]})
    if user.get("email"):
        or_filters.append({"employee_email": user["email"]})
    if not or_filters:
        return []
    q = {
        "$and": [
            {"$or": or_filters},
            {"status": {"$nin": ["completed", "withdrawn"]}},
            {"$or": [{"end_date": {"$exists": False}}, {"end_date": None}, {"end_date": ""}, {"end_date": {"$gte": today}}]},
        ],
    }
    rows = await db.deployments.find(q, {"_id": 0, "project": 1}).to_list(500)
    out: List[str] = []
    for r in rows:
        p = r.get("project")
        if p and p not in out:
            out.append(p)
    return out


async def resolve_scope(user: dict) -> Dict[str, list]:
    """Return {role, global, departments, active_projects} for `user`."""
    role = user.get("role")
    is_global = role in GLOBAL_ROLES or role == "super_admin"
    return {
        "role": role,
        "global": is_global,
        "departments": _user_departments(user),
        "active_projects": await _active_projects_for(user),
    }


async def project_filter(user: dict, project_field: str = "project") -> dict | None:
    """Mongo filter clause restricting rows to the user's active projects.

    Returns:
        None  -> no filter (user has global visibility or is dept-scoped only)
        {}    -> match nothing (user is project-scoped but has zero projects)
        {project: {$in: [...]}}  -> the actual restriction
    """
    role = user.get("role")
    if role in GLOBAL_ROLES or role == "super_admin":
        return None
    if role not in PROJECT_SCOPED_ROLES:
        return None
    projects = await _active_projects_for(user)
    if not projects:
        return {"_no_match_sentinel_": True}  # forces empty result set
    return {project_field: {"$in": projects}}


def department_filter(user: dict, field: str = "departments") -> dict | None:
    """For dept_head users — restrict to rows whose `field` overlaps their dept.

    Returns None (no filter) for global roles. Returns a `{field: {$in: [..]}}`
    for dept_head, matched against either the array field or a legacy scalar.
    """
    role = user.get("role")
    if role in GLOBAL_ROLES or role == "super_admin":
        return None
    if role != "dept_head":
        return None
    depts = _user_departments(user)
    if not depts:
        return {"_no_match_sentinel_": True}
    # Match either the new array OR the legacy single-dept string.
    return {"$or": [{field: {"$in": depts}}, {"department": {"$in": depts}}]}
