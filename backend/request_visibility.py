"""Row-level visibility rules for Project Request Center rows.

Two product rules on top of the normal project scope:

1. Manager Log users only ever see Fuel Payment and Service Invoice (SR Workflow)
   requests — every other type stays hidden (list, summary, inbox and exports).
2. A self-raised employee advance is visible only to the person who raised it,
   the employee it belongs to, their project manager and the roles that must
   process it (HR, Accounts, GM, Director, Super Admin).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core import db

MANAGER_LOG_ROLES = {"manager_log", "manager_l_o_g"}
MANAGER_LOG_TYPES = ["fuel", "service_invoice"]
ADVANCE_PRIVILEGED_ROLES = {"super_admin", "director", "general_manager",
                            "hr_executive", "accounts_executive"}


def manager_log_clause() -> Dict[str, Any]:
    return {"$or": [{"request_type": {"$in": MANAGER_LOG_TYPES}},
                    {"source": "service_invoice"}]}


async def _my_employee_keys(user: dict) -> List[str]:
    keys = [k for k in (user.get("employee_id"), user.get("employee_code")) if k]
    ors: List[dict] = [{"user_id": user.get("id")}]
    if user.get("email"):
        ors.append({"email": user["email"]})
    async for e in db.employees.find({"$or": ors}, {"_id": 0, "id": 1, "emp_code": 1, "employee_id": 1}):
        keys += [v for v in (e.get("id"), e.get("emp_code"), e.get("employee_id")) if v]
    return list({str(k) for k in keys})


async def _self_advance_clause(user: dict) -> Dict[str, Any]:
    """Hide other people's SELF-raised advances. On-behalf advances are unaffected."""
    allowed: List[dict] = [
        {"source": {"$ne": "advance"}},          # not an advance row at all
        {"self_raised": {"$ne": True}},          # raised on behalf → old visibility
        {"advance_created_by_id": user.get("id")},
        {"created_by_id": user.get("id")},
    ]
    keys = await _my_employee_keys(user)
    if keys:
        allowed.append({"employee_id": {"$in": keys}})
        allowed.append({"employee_code": {"$in": keys}})
    from pm_scope import is_pm_scoped
    if is_pm_scoped(user) or user.get("role") in {"project_manager", "project_coordinator", "dept_head"}:
        from scope import assigned_projects_for
        tokens = [p.get("code") for p in await assigned_projects_for(user) if p.get("code")]
        if tokens:
            allowed.append({"project_code": {"$in": tokens}})
    return {"$or": allowed}


async def own_rows_clauses(user: dict) -> List[Dict[str, Any]]:
    """Rows a user must always see regardless of project scope: raised by them,
    or where they are the beneficiary (self expense / self advance)."""
    ors: List[Dict[str, Any]] = [{"created_by_id": user.get("id")},
                                 {"advance_created_by_id": user.get("id")}]
    keys = await _my_employee_keys(user)
    if keys:
        ors.append({"employee_id": {"$in": keys}})
        ors.append({"employee_code": {"$in": keys}})
    return ors


async def request_visibility_clauses(user: dict) -> List[Dict[str, Any]]:
    """Extra `$and` clauses to apply to any project_requests query."""
    clauses: List[Dict[str, Any]] = []
    if user.get("role") in MANAGER_LOG_ROLES:
        clauses.append(manager_log_clause())
    if user.get("role") not in ADVANCE_PRIVILEGED_ROLES:
        clauses.append(await _self_advance_clause(user))
    return clauses


async def apply_request_visibility(user: dict, q: Dict[str, Any]) -> Dict[str, Any]:
    clauses = await request_visibility_clauses(user)
    if not clauses:
        return q
    return {"$and": [q, *clauses]} if q else ({"$and": clauses} if len(clauses) > 1 else clauses[0])


def can_view_request(user: dict, row: Optional[dict]) -> bool:
    """Same rules for a single row (detail view)."""
    if not row:
        return False
    role = user.get("role")
    if role in MANAGER_LOG_ROLES:
        if row.get("request_type") not in MANAGER_LOG_TYPES and row.get("source") != "service_invoice":
            return False
    return True
