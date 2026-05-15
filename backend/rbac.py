"""Role-based access control: permission map + dependency factory."""
from typing import Set
from fastapi import HTTPException, Depends, Request
import jwt
import os

# Per-resource permission map. Action -> roles allowed.
# Special token "*" means any authenticated user.
PERMISSIONS = {
    "users": {
        "read": {"super_admin", "director", "general_manager", "hr_executive"},
        "write": {"super_admin"},
        "delete": {"super_admin"},
    },
    "clients": {
        "read": {"*"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "accounts_executive", "project_manager"},
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
        "write": {"super_admin", "director", "general_manager", "dept_head", "project_manager"},
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
        "read": {"super_admin", "director", "general_manager", "dept_head", "accounts_executive", "project_manager"},
        "write": {"super_admin", "director", "general_manager", "dept_head", "project_manager"},
        "delete": {"super_admin", "director"},
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
}


def can(role: str, resource: str, action: str) -> bool:
    if role == "super_admin":
        return True
    rules = PERMISSIONS.get(resource, {})
    allowed: Set[str] = rules.get(action, set())
    if "*" in allowed:
        return True
    return role in allowed


def permissions_for(role: str) -> dict:
    """Compact permission summary for the current user, sent to the frontend."""
    if role == "super_admin":
        return {res: {"read": True, "write": True, "delete": True} for res in PERMISSIONS}
    out = {}
    for res, rules in PERMISSIONS.items():
        out[res] = {act: ("*" in roles or role in roles) for act, roles in rules.items()}
    return out
