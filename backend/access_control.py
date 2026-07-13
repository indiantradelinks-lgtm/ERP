"""Central Access Control Orchestrator.

This module is the single entry point that high-level code can use instead of
calling the lower-level helpers directly. It composes the building blocks that
already exist in the codebase:

  • rbac.py             — role × resource × action matrix + DB overrides
  • pm_scope.py         — PM/Coordinator/Manager OP scope
  • department_scope.py — department-based scope
  • scope.py            — project_filter / department_filter (used by crud_router)
  • data_masking.py     — sensitive field masking
  • finance_guards.py   — voucher / ledger / payment write-time guards
  • audit.py            — audit logger

Public surface (used by callers):

  has_module_access(user, module_key)        -> bool
  has_page_access(user, perm_key)            -> bool   (alias for read perm)
  has_action_access(user, perm_key, action)  -> bool
  data_scope_filter(user, collection)        -> dict   (Mongo $-clause)
  mask(user, resource, doc_or_list)          -> dict/list
  log_access_denied(user, path, reason)      -> coroutine
"""
from __future__ import annotations
from typing import Any, Iterable, Optional

from rbac import can as _rbac_can
from rbac import _resolved as _rbac_resolved
from scope import project_filter as _proj_filter, department_filter as _dept_filter
from pm_scope import is_pm_scoped, pm_scope_clause
from data_masking import mask_for, mask_list, masking_config
from core import db, now_iso

# Collections from crud_router (kept in sync — adding here only for explicitness).
PROJECT_SCOPED = {
    "deployments", "safety_reports", "attendance", "ptws", "toolbox_talks",
    "ppe_issuance", "inventory_transactions", "projects", "purchase_orders",
    "assets", "purchase_requisitions", "rfqs", "grns", "dprs", "measurements",
    "ra_bills", "vendor_invoices", "payments_in", "payments_out",
}
DEPT_SCOPED = {
    "employees", "employee_advances", "hr_letters", "leave_requests", "overtime",
}
PM_SCOPED_COLLECTIONS = {
    "project_handovers", "projects",
}

# Permission read-aliases for module/page checks. Modules to representative perm.
MODULE_PERMS = {
    "dashboard": "dashboards",
    "sales": "quotations",
    "ops": "projects",
    "hr": "employees",
    "store": "inventory",
    "procurement": "vendors",
    "accounts": "accounting",
    "finance": "accounting",
    "safety": "safety_reports",
    "logistics": "vehicles",
    "admin": "role_register",
}


# ─── Action checks ────────────────────────────────────────────────────────
def has_action_access(user: dict, perm: str, action: str = "read") -> bool:
    """Return True if user has the given permission/action."""
    role = (user or {}).get("role")
    if not role:
        return False
    return _rbac_can(role, perm, action)


def has_page_access(user: dict, perm: str) -> bool:
    """Alias — page access == read access on its permission key."""
    return has_action_access(user, perm, "read")


def has_module_access(user: dict, module_key: str) -> bool:
    perm = MODULE_PERMS.get(module_key)
    if not perm:
        # Module without an explicit perm — assume visible to all authed users.
        return bool((user or {}).get("role"))
    return has_action_access(user, perm, "read")


# ─── Data scope ───────────────────────────────────────────────────────────
async def data_scope_filter(user: dict, collection: str) -> dict:
    """Return the Mongo filter clause that limits visibility for this user.

    Returns `{}` for full access. Returns `{"id": "__never_matches__"}` when
    the user has zero scope (no projects, no dept) so callers can short-circuit.
    """
    filt: dict = {}
    if collection in PROJECT_SCOPED:
        pq = await _proj_filter(user)
        if pq is not None:
            if pq.get("_no_match_sentinel_"):
                return {"id": "__never_matches__"}
            filt.update(pq)
    if collection in DEPT_SCOPED:
        dq = _dept_filter(user)
        if dq is not None:
            if dq.get("_no_match_sentinel_"):
                return {"id": "__never_matches__"}
            if filt:
                filt = {"$and": [dict(filt), dq]}
            else:
                filt = dq
    if collection in PM_SCOPED_COLLECTIONS and is_pm_scoped(user):
        pm_q = pm_scope_clause(user)
        if pm_q:
            filt = {"$and": [dict(filt), pm_q]} if filt else pm_q
    return filt


# ─── Masking helpers (passthrough for discoverability) ────────────────────
def mask(user: dict, resource: str, value):
    """Mask a single doc OR a list. Detects automatically."""
    if isinstance(value, list):
        return mask_list(value, resource, user)
    if isinstance(value, dict):
        return mask_for(value, resource, user)
    return value


def get_masking_config() -> dict:
    return masking_config()


# ─── Access-denied audit ──────────────────────────────────────────────────
async def log_access_denied(user: dict, path: str, reason: str, ip: str = "") -> None:
    """Persist a denied-access event to the security event log."""
    await db.access_denied_logs.insert_one({
        "ts": now_iso(),
        "actor_id": (user or {}).get("id"),
        "actor_email": (user or {}).get("email"),
        "actor_role": (user or {}).get("role"),
        "path": path,
        "reason": reason,
        "ip": ip,
    })


# ─── Context snapshot for the frontend ────────────────────────────────────
def get_access_context(user: dict) -> dict:
    """Returns the full access-control snapshot for a user, for the frontend
    AuthContext to render menus, guards and KPIs correctly."""
    role = (user or {}).get("role")
    if not role:
        return {"role": None, "permissions": {}, "modules": [], "pm_scoped": False}
    resolved = _rbac_resolved()
    perms = {}
    for resource, actions in resolved.items():
        perms[resource] = {a: role in roles or "*" in roles
                          for a, roles in actions.items()}
    modules = [m for m in MODULE_PERMS.keys() if has_module_access(user, m)]
    return {
        "role": role,
        "department": (user or {}).get("department"),
        "permissions": perms,
        "modules": modules,
        "pm_scoped": is_pm_scoped(user),
    }
