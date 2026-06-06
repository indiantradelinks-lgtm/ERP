"""Role-based access control: permission map + dependency factory.

The map is split into:
  • PERMISSIONS_BASE — the immutable, code-defined defaults below.
  • _overrides       — DB-backed overrides loaded from `db.rbac_overrides`
                       (a singleton doc with id="default"). Empty by default.
  • _resolved()      — merge of base + overrides; this is what every gate uses.

Overrides COMPLETELY REPLACE the role-set for that (resource, action) pair.
The Role Register control panel writes to this collection; super_admin is always
allowed irrespective of overrides (an emergency safety net).
"""
from typing import Set, Dict, List
from fastapi import HTTPException, Depends, Request
import jwt
import os

# Per-resource permission map. Action -> roles allowed.
# Special token "*" means any authenticated user.
PERMISSIONS_BASE = {
    "users": {
        "read": {"super_admin", "director", "general_manager", "hr_executive"},
        "write": {"super_admin"},
        "delete": {"super_admin"},
    },
    "clients": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "accounts_executive", "project_manager", "sales_executive"},
        "delete": {"super_admin", "director"},
    },
    "vendors": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "purchase_officer", "accounts_executive"},
        "delete": {"super_admin", "director"},
    },
    "employees": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "hr_executive", "project_manager", "accounts_executive"},
        "write": {"super_admin", "director", "general_manager", "hr_executive"},
        "delete": {"super_admin", "hr_executive"},
    },
    "attendance": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "hr_executive", "supervisor", "project_manager"},
        "write": {"super_admin", "hr_executive", "supervisor", "project_manager"},
        "delete": {"super_admin", "hr_executive"},
    },
    "projects": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "project_manager", "project_coordinator"},
        "delete": {"super_admin", "director"},
    },
    "project_handovers": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "sales_executive", "project_manager", "project_coordinator", "accounts_executive"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "sales_executive"},
        "delete": {"super_admin", "director"},
    },
    "inventory": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "store_incharge", "purchase_officer"},
        "delete": {"super_admin", "store_incharge"},
    },
    "purchase_orders": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "purchase_officer", "accounts_executive", "project_manager", "store_incharge"},
        "write": {"super_admin", "director", "dept_head", "purchase_officer", "project_manager"},
        "delete": {"super_admin", "director", "purchase_officer"},
    },
    "quotations": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "accounts_executive", "project_manager", "sales_executive"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "project_manager", "sales_executive"},
        "delete": {"super_admin", "director"},
    },
    "sales_reports": {
        # Pipeline analytics — restricted to sales/leadership roles, NOT project_manager
        "read": {"super_admin", "director", "general_manager", "dept_head", "sales_executive", "accounts_executive"},
        "write": {"super_admin"},
        "delete": {"super_admin"},
    },
    "journal_entries": {
        "read": {"super_admin", "director", "general_manager", "accounts_executive"},
        "write": {"super_admin", "director", "accounts_executive"},
        "delete": {"super_admin", "accounts_executive"},
    },
    "safety_reports": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "safety_officer", "supervisor", "project_manager", "site_engineer"},
        "delete": {"super_admin", "safety_officer"},
    },
    "assets": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "store_incharge"},
        "delete": {"super_admin", "director"},
    },
    "payroll": {
        "read": {"super_admin", "director", "general_manager", "hr_executive", "accounts_executive"},
        "write": {"super_admin", "hr_executive", "accounts_executive"},
        "delete": {"super_admin", "accounts_executive"},
    },
    "vehicles": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head"},
        "delete": {"super_admin", "director"},
    },
    "documents": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "project_manager", "safety_officer", "hr_executive", "accounts_executive"},
        "delete": {"super_admin", "director"},
    },
    "approvals": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "project_manager", "purchase_officer", "accounts_executive", "hr_executive", "store_incharge", "supervisor"},
        "delete": {"super_admin"},
    },
    "departments": {
        "read": {"*"},
        "write": {"super_admin"},
        "delete": {"super_admin"},
    },
    # Phase D — Safety pack
    "ppe_issuance": {
        "read": {"*"},
        "write": {"super_admin", "safety_officer", "hr_executive", "store_incharge"},
        "delete": {"super_admin", "safety_officer"},
    },
    "ptws": {
        "read": {"*"},
        "write": {"super_admin", "safety_officer", "supervisor", "project_manager", "site_engineer", "dept_head"},
        "delete": {"super_admin", "safety_officer"},
    },
    "safety_trainings": {
        "read": {"*"},
        "write": {"super_admin", "safety_officer", "hr_executive"},
        "delete": {"super_admin", "safety_officer"},
    },
    "toolbox_talks": {
        "read": {"*"},
        "write": {"super_admin", "safety_officer", "supervisor", "site_engineer", "project_manager"},
        "delete": {"super_admin", "safety_officer"},
    },
    # Phase E — HR pack
    "recruitment_requests": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "hr_executive", "project_manager"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "hr_executive", "project_manager"},
        "delete": {"super_admin", "hr_executive"},
    },
    "candidates": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "hr_executive"},
        "write": {"super_admin", "hr_executive"},
        "delete": {"super_admin", "hr_executive"},
    },
    "deployments": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "hr_executive", "project_manager"},
        "delete": {"super_admin", "hr_executive"},
    },
    "accommodations": {
        "read": {"*"},
        "write": {"super_admin", "hr_executive", "dept_head"},
        "delete": {"super_admin", "hr_executive"},
    },
    "overtime": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "hr_executive", "supervisor", "project_manager", "accounts_executive"},
        "write": {"super_admin", "hr_executive", "supervisor", "project_manager", "dept_head"},
        "delete": {"super_admin", "hr_executive"},
    },
    # Phase F
    "vendor_evaluations": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "purchase_officer"},
        "write": {"super_admin", "director", "general_manager", "purchase_officer"},
        "delete": {"super_admin"},
    },
    "vendor_invoices": {
        "read": {"super_admin", "director", "general_manager", "accounts_executive", "purchase_officer"},
        "write": {"super_admin", "accounts_executive", "purchase_officer"},
        "delete": {"super_admin"},
    },
    # Procurement Phase A
    "purchase_requisitions": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "project_manager",
                  "site_engineer", "supervisor", "store_incharge", "purchase_officer", "safety_officer", "hr_executive"},
        "delete": {"super_admin", "director", "purchase_officer"},
    },
    "rfqs": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "purchase_officer", "accounts_executive", "project_manager"},
        "write": {"super_admin", "director", "purchase_officer"},
        "delete": {"super_admin", "director", "purchase_officer"},
    },
    "grn": {
        "read": {"*"},
        "write": {"super_admin", "store_incharge", "purchase_officer", "dept_head", "project_manager"},
        "delete": {"super_admin", "store_incharge"},
    },
    # Procurement Phase B
    "material_allocations": {
        "read": {"*"},
        "write": {"super_admin", "store_incharge", "supervisor", "site_engineer", "project_manager", "dept_head"},
        "delete": {"super_admin", "store_incharge"},
    },
    "asset_lifecycle": {
        "read": {"*"},
        "write": {"super_admin", "store_incharge", "dept_head", "project_manager", "purchase_officer", "accounts_executive"},
        "delete": {"super_admin"},
    },
    "challans": {
        "read": {"*"},
        "write": {"super_admin", "store_incharge", "supervisor", "project_manager", "dept_head", "purchase_officer"},
        "delete": {"super_admin", "store_incharge"},
    },
    # Phase C — Store transactions handled by store_router; expose read-only here as well
    "inventory_transactions": {
        "read": {"*"},
        "write": {"super_admin", "store_incharge", "purchase_officer"},
        "delete": {"super_admin", "store_incharge"},
    },
    # Site execution — Daily Site Reports + Measurement / Work Certification
    "dprs": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head",
                  "project_manager", "site_engineer", "supervisor", "safety_officer"},
        "delete": {"super_admin", "project_manager"},
    },
    "measurements": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head",
                  "project_manager", "site_engineer", "supervisor", "accounts_executive"},
        "delete": {"super_admin", "project_manager"},
    },
    # Iteration 28 — Running Bills + Receivables + Project Ops + Service rate master
    "ra_bills": {
        "read": {"super_admin", "director", "general_manager", "dept_head",
                 "accounts_executive", "project_manager", "billing_executive"},
        "write": {"super_admin", "director", "accounts_executive", "billing_executive",
                  "project_manager"},
        "delete": {"super_admin", "accounts_executive"},
    },
    "receivables": {
        "read": {"super_admin", "director", "general_manager", "accounts_executive",
                 "billing_executive", "dept_head"},
        "write": {"super_admin", "accounts_executive", "billing_executive"},
        "delete": {"super_admin", "accounts_executive"},
    },
    "payments_in": {
        "read": {"super_admin", "director", "general_manager", "accounts_executive",
                 "billing_executive"},
        "write": {"super_admin", "accounts_executive", "billing_executive"},
        "delete": {"super_admin", "accounts_executive"},
    },
    "project_ops": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head",
                  "project_manager", "site_engineer", "supervisor"},
        "delete": {"super_admin", "project_manager"},
    },
    "service_rates": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "accounts_executive",
                  "sales_executive"},
        "delete": {"super_admin", "director"},
    },
    # Iteration 29 — AI Quotation Builder (rich quotation + AI RFQ extraction)
    # Reuses 'quotations' permission. Builder-specific extras (company profile,
    # condition library) check 'quotations' write for create/edit.
    "company_profile": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager"},
        "delete": {"super_admin"},
    },
    "condition_library": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "sales_executive"},
        "delete": {"super_admin", "director"},
    },
    # Iteration 30 — User Management + Role Register control panels
    "role_register": {
        "read": {"super_admin", "director", "general_manager"},
        "write": {"super_admin"},
        "delete": {"super_admin"},
    },
    # Iteration 32 — Procurement Master (categories, items, cost centers)
    "procurement_master": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "purchase_officer", "accounts_executive"},
        "delete": {"super_admin", "director", "general_manager"},
    },
    # Iteration 33 — Data Cleanup (super_admin-only by default)
    "data_cleanup": {
        "read": {"super_admin", "director"},
        "write": {"super_admin"},   # restore from archive
        "delete": {"super_admin"},  # hard delete & purge
    },
    # Iteration 34 — Human Resources (Onboarding · Employee 360 · Leave)
    "hr_onboarding": {
        "read": {"super_admin", "director", "general_manager", "hr_executive", "dept_head"},
        "write": {"super_admin", "hr_executive", "general_manager"},
        "delete": {"super_admin", "hr_executive"},
    },
    "hr_employee_360": {
        "read": {"super_admin", "director", "general_manager", "hr_executive", "dept_head", "project_manager", "accounts_executive"},
        "write": {"super_admin", "hr_executive", "general_manager"},
        "delete": {"super_admin", "hr_executive"},
    },
    "hr_leave": {
        "read": {"*"},
        "write": {"super_admin", "hr_executive", "general_manager", "director", "dept_head", "project_manager"},
        "delete": {"super_admin", "hr_executive"},
    },
    # Iteration 35 — HR Letters & Exit/FNF
    "hr_letters": {
        "read": {"super_admin", "director", "general_manager", "hr_executive", "dept_head"},
        "write": {"super_admin", "hr_executive", "general_manager"},
        "delete": {"super_admin", "hr_executive"},
    },
    "hr_exit": {
        "read": {"super_admin", "director", "general_manager", "hr_executive", "dept_head", "accounts_executive"},
        "write": {"super_admin", "hr_executive", "general_manager", "director", "store_incharge", "dept_head", "accounts_executive"},
        "delete": {"super_admin", "hr_executive"},
    },
    # Iteration 45 — Employee Advance Register
    "hr_advances": {
        "read": {"*"},
        "write": {"super_admin", "hr_executive", "general_manager", "director",
                  "project_manager", "dept_head", "accounts_executive"},
        "delete": {"super_admin", "hr_executive"},
    },
    # Iteration 49 — Real Payroll Module (Monthly run + EMI auto-deduction)
    "hr_payroll": {
        "read": {"super_admin", "director", "general_manager", "hr_executive",
                 "accounts_executive", "dept_head"},
        "write": {"super_admin", "hr_executive"},
        "delete": {"super_admin"},
    },
    # Iteration 40 — Microsoft 365 SMTP Email + Outbox
    "email_outbox": {
        "read": {"super_admin", "director", "general_manager", "dept_head", "hr_executive",
                 "accounts_executive", "purchase_officer", "project_manager", "sales_executive",
                 "billing_executive"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "hr_executive",
                  "accounts_executive", "purchase_officer", "project_manager", "sales_executive",
                  "billing_executive"},
        "delete": {"super_admin"},
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Override layer (DB-backed, editable via /api/admin/role-register).
# ──────────────────────────────────────────────────────────────────────────────
_overrides: Dict[str, Dict[str, Set[str]]] = {}
_resolved_cache: Dict[str, Dict[str, Set[str]]] | None = None


def _build_resolved() -> Dict[str, Dict[str, Set[str]]]:
    merged: Dict[str, Dict[str, Set[str]]] = {}
    # Start with a deep copy of the base map
    for res, rules in PERMISSIONS_BASE.items():
        merged[res] = {
            "read": set(rules.get("read", set())),
            "write": set(rules.get("write", set())),
            "delete": set(rules.get("delete", set())),
        }
    # Layer overrides on top: explicit action lists replace the base set
    for res, rules in _overrides.items():
        merged.setdefault(res, {"read": set(), "write": set(), "delete": set()})
        for action in ("read", "write", "delete"):
            if action in rules:
                merged[res][action] = set(rules[action] or [])
    return merged


def _resolved() -> Dict[str, Dict[str, Set[str]]]:
    global _resolved_cache
    if _resolved_cache is None:
        _resolved_cache = _build_resolved()
    return _resolved_cache


def _invalidate_cache() -> None:
    global _resolved_cache
    _resolved_cache = None


def set_overrides(overrides: Dict[str, Dict[str, List[str]]]) -> None:
    """Replace the in-memory override map. Called by the admin router after a
    successful DB write. Keeps cache consistent without re-querying mongo."""
    global _overrides
    out: Dict[str, Dict[str, Set[str]]] = {}
    for res, rules in (overrides or {}).items():
        out[res] = {}
        for action, roles in (rules or {}).items():
            if action not in ("read", "write", "delete"):
                continue
            out[res][action] = set(roles or [])
    _overrides = out
    _invalidate_cache()


def get_overrides_serializable() -> Dict[str, Dict[str, List[str]]]:
    return {
        res: {action: sorted(list(roles)) for action, roles in rules.items()}
        for res, rules in _overrides.items()
    }


# ──────────────────────────────────────────────────────────────────────────────
# Backwards-compatible alias — some test files still import `PERMISSIONS`.
# Points at the merged map; do NOT mutate.
# ──────────────────────────────────────────────────────────────────────────────
class _PermissionsProxy:
    def __getitem__(self, k):
        return _resolved()[k]
    def get(self, k, default=None):
        return _resolved().get(k, default)
    def __contains__(self, k):
        return k in _resolved()
    def __iter__(self):
        return iter(_resolved())
    def keys(self):
        return _resolved().keys()
    def items(self):
        return _resolved().items()
    def values(self):
        return _resolved().values()


PERMISSIONS = _PermissionsProxy()


def can(role: str, resource: str, action: str) -> bool:
    if role == "super_admin":
        return True
    rules = _resolved().get(resource, {})
    allowed: Set[str] = rules.get(action, set())
    if "*" in allowed:
        return True
    return role in allowed


def permissions_for(role: str) -> dict:
    """Compact permission summary for the current user, sent to the frontend."""
    resolved = _resolved()
    if role == "super_admin":
        return {res: {"read": True, "write": True, "delete": True} for res in resolved}
    out = {}
    for res, rules in resolved.items():
        out[res] = {act: ("*" in roles or role in roles) for act, roles in rules.items()}
    return out


def has_permission(role: str | None, resource: str, action: str) -> bool:
    """Pure boolean check — no FastAPI dependency. Used by importer's
    per-collection re-check (it gates on 'clients' write but we still want to
    enforce the real target collection's permission inside the handler).
    """
    if role == "super_admin":
        return True
    rules = _resolved().get(resource, {})
    roles = rules.get(action, set())
    return "*" in roles or (role is not None and role in roles)
