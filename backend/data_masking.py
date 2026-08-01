"""Sensitive-field masking (Phase 9 — Role-Based Access & Security).

Strips or masks sensitive fields from a document based on the caller's role.
Used by endpoints that return employee, payroll, vendor or bank-account
details to non-finance / non-HR users.

Usage:
    from data_masking import mask_for, mask_list

    @router.get("/employees")
    async def list_emp(user = Depends(...)):
        rows = await db.employees.find(...).to_list(...)
        return mask_list(rows, "employees", user)
"""
from __future__ import annotations
from typing import Iterable, List

# Roles that always see everything (finance / hr / leadership)
PRIVILEGED_ROLES = {
    "super_admin", "director", "general_manager",
    "accounts_executive", "hr_executive", "billing_executive",
}

# Per-resource sensitive field config.
# action 'mask' replaces value with "****"; action 'strip' removes the key.
SENSITIVE_FIELDS: dict[str, dict[str, str]] = {
    "employees": {
        "salary": "strip", "ctc": "strip", "monthly_ctc": "strip",
        "basic": "strip", "hra": "strip", "pan": "mask", "aadhaar": "mask",
        "bank_account": "mask", "bank_ifsc": "mask", "bank_name": "mask",
        "pf_number": "mask", "esic_number": "mask", "uan": "mask",
    },
    "payroll": {
        "bank_account": "mask", "bank_ifsc": "mask",
    },
    "workers": {
        "aadhaar": "mask", "pan": "mask",
        "bank_account": "mask", "ifsc": "mask",
    },
    "vendors": {
        "bank_account": "mask", "bank_ifsc": "mask", "bank_name": "mask",
        "pan": "mask",
    },
    "clients": {
        "pan": "mask", "gstin_secret": "mask",
    },
}


def _mask_value(v):
    if v is None or v == "":
        return v
    s = str(v)
    if len(s) <= 4:
        return "****"
    return f"****{s[-4:]}"


def mask_for(doc: dict, resource: str, user: dict) -> dict:
    """Return a copy of `doc` with sensitive fields masked/stripped per role."""
    if not doc:
        return doc
    role = (user or {}).get("role")
    if role in PRIVILEGED_ROLES:
        return doc
    if doc.get("email") and doc.get("email") == (user or {}).get("email"):
        return doc  # self-view: users may see their own record
    rules = SENSITIVE_FIELDS.get(resource) or {}
    if not rules:
        return doc
    out = dict(doc)
    for field, action in rules.items():
        if field in out:
            if action == "strip":
                out.pop(field, None)
            else:
                out[field] = _mask_value(out.get(field))
    return out


def mask_list(rows: Iterable[dict], resource: str, user: dict) -> List[dict]:
    role = (user or {}).get("role")
    if role in PRIVILEGED_ROLES:
        return list(rows)
    rules = SENSITIVE_FIELDS.get(resource) or {}
    if not rules:
        return list(rows)
    return [mask_for(r, resource, user) for r in rows]


def masking_config() -> dict:
    """For Security Center display."""
    return {
        "privileged_roles": sorted(PRIVILEGED_ROLES),
        "rules": {res: dict(fields) for res, fields in SENSITIVE_FIELDS.items()},
    }
