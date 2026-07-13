"""Centralized project-manager visibility scope.

Used by:
  • Contract Handovers list (`/api/ops/handovers`)
  • Project list (`/api/dashboard/projects`)
  • Project dashboard KPIs (`/api/dashboard-kpis`)
  • Project detail visibility gate

A user is "PM-scoped" — i.e. sees ONLY projects assigned to them — when any of
the following holds (and they aren't in a privileged leadership role):

  1. Their role slug is one of the canonical PM roles
     ('project_manager', 'project_coordinator')
  2. Their role slug/label is 'Manager O P' / 'manager_o_p' (any case/space)
  3. Their department is 'Projects & Operations' AND their role-label contains
     manager / coordinator / engineer (covers custom roles created via Role
     Catalog with department = 'Projects & Operations')

Leadership roles (super_admin, director, general_manager, dept_head,
accounts_executive) bypass scoping.
"""
from __future__ import annotations
import re
from typing import Any, Dict

PM_SCOPED_ROLES = {
    "project_manager",
    "project_coordinator",
    "manager_o_p",
    "manager_op",
}

PM_SCOPED_DEPARTMENTS = {
    "projects & operations",
    "projects and operations",
    "operations",
    "projects",
}

PRIVILEGED_ROLES = {
    "super_admin", "director", "general_manager",
    "dept_head", "accounts_executive",
}

_PM_LABEL_HINTS = ("manager", "coordinator", "engineer", "supervisor", "incharge")


def _norm(s) -> str:
    return re.sub(r"\s+", "_", (s or "").strip().lower())


def is_pm_scoped(user: dict) -> bool:
    """Return True when the user must only see projects assigned to them."""
    role_raw = user.get("role") or ""
    role = _norm(role_raw)
    if role in PRIVILEGED_ROLES:
        return False
    if role in PM_SCOPED_ROLES:
        return True
    # Department-based fallback for custom roles like 'Manager O P'
    dept = (user.get("department") or "").strip().lower()
    if dept in PM_SCOPED_DEPARTMENTS:
        label = (user.get("role_label") or role_raw or "").lower()
        if any(h in label for h in _PM_LABEL_HINTS):
            return True
    return False


def pm_scope_clause(user: dict) -> Dict[str, Any]:
    """Mongo $or clause limiting to documents assigned to this user.

    Empty dict means 'no filter' (privileged).
    Returns the clause for collections that carry `project_manager_id` /
    `project_coordinator_id` / `reporting_manager_id` fields. Falls back to
    name/email matches for legacy rows that pre-date the *_id columns.
    """
    if not is_pm_scoped(user):
        return {}
    uid = user.get("id")
    name = user.get("name")
    email = user.get("email")
    aliases = [v for v in (uid, name, email) if v]
    return {"$or": [
        {"project_manager_id": uid},
        {"project_coordinator_id": uid},
        {"reporting_manager_id": uid},
        {"project_manager": {"$in": aliases}},
        {"project_coordinator": {"$in": aliases}},
        {"manager": {"$in": aliases}},
    ]}


def can_view_handover(user: dict, doc: dict) -> bool:
    """In-memory check used by single-record fetches (detail page)."""
    if not is_pm_scoped(user):
        return True
    uid = user.get("id")
    name = user.get("name")
    email = user.get("email")
    aliases = {uid, name, email}
    return any(doc.get(k) in aliases for k in (
        "project_manager_id", "project_coordinator_id", "reporting_manager_id",
        "project_manager", "project_coordinator", "manager",
    ))
