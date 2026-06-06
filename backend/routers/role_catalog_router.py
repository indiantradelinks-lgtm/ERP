"""Role Catalog — Super-Admin only management of system roles.

Drives all role dropdowns and the Role Register. On startup the catalog is
seeded with the 14 built-in roles (so existing PERMISSIONS_BASE keeps working).
Super-admin can then:
  • Add custom roles with starter permissions (writes into rbac_overrides)
  • Rename their label/description (key is immutable)
  • Delete a role — BLOCKED while any user holds that role.

Built-in roles can also be deleted (per user choice) but the same "no user
attached" guard applies. Note: built-in role *keys* still appear in the
hardcoded PERMISSIONS_BASE matrix of /app/backend/rbac.py — deleting a
built-in from the catalog only removes it from the assignable list and
the Role Register UI; permission checks against existing routes are
unaffected.

Endpoints (all RBAC-gated on 'role_register' write):
  GET    /api/admin/role-catalog
  POST   /api/admin/role-catalog
  PATCH  /api/admin/role-catalog/{key}
  DELETE /api/admin/role-catalog/{key}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, validator

from core import db, new_id, now_iso, require_permission
from audit import audit
from rbac import (
    PERMISSIONS_BASE,
    _resolved,  # noqa
    get_overrides_serializable,
    set_overrides,
)

logger = logging.getLogger("erp.role_catalog")
router = APIRouter(prefix="/admin", tags=["role-catalog"])


# ────────────────────────────────────────────────────────────────────────────
# Built-in role catalog seed (key, label, description, sort_order)
# ────────────────────────────────────────────────────────────────────────────
BUILTIN_ROLE_SEED = [
    ("super_admin", "Super Admin", "Root account — full access, unaffected by overrides.", 0),
    ("director", "Director", "Top-level executive. Strategic oversight across all departments.", 10),
    ("general_manager", "General Manager", "Cross-departmental head; approves high-value POs and quotations.", 20),
    ("dept_head", "Department Head", "Functional lead for one department (Procurement, HR, Site Ops, etc.).", 30),
    ("project_manager", "Project Manager", "Owns a project P&L; site mobilisation, manpower planning, billing.", 40),
    ("site_engineer", "Site Engineer", "On-site execution; DPRs, joint measurement, quality checks.", 50),
    ("supervisor", "Site Supervisor", "Crew lead; attendance entry, day-to-day work assignment.", 60),
    ("store_incharge", "Store In-charge", "Stores & inventory; GRN, issue notes, asset allocation.", 70),
    ("accounts_executive", "Accounts Executive", "Finance entries; RA Bills, retentions, TDS, vendor payments.", 80),
    ("hr_executive", "HR Executive", "Onboarding, leave, payroll, letters, FNF and compliance.", 90),
    ("safety_officer", "Safety Officer", "HIRA/JSA, PPE issuance, near-miss reports, compliance audits.", 100),
    ("purchase_officer", "Purchase Officer", "PR → RFQ → PO; vendor management and rate negotiation.", 110),
    ("sales_executive", "Sales Executive", "Client enquiries, quotations, sales orders.", 120),
    ("billing_executive", "Billing Executive", "Specialised billing role for RA Bills, retentions and invoicing.", 125),
    ("client_rep", "Client Representative", "External — limited read-only access to their own projects.", 130),
    ("vendor", "Vendor (External)", "External — limited read-only access to their RFQs and POs.", 140),
    # Iter 60 — Projects & Operations Workflow roles
    ("project_coordinator", "Project Coordinator", "Assists the Project Manager — raises resource/PR requests, coordinates site activity.", 45),
    ("admin_executive", "Admin Executive", "Handles accommodation, vehicles, drivers, admin/travel/site support requests.", 95),
    ("site_team", "Site Team", "On-ground site crew — updates daily activities, raises requirements to PM.", 55),
]


class CreateRoleIn(BaseModel):
    key: str = Field(..., min_length=2, max_length=40)
    label: str = Field(..., min_length=2, max_length=80)
    description: str = Field("", max_length=400)
    permissions: Optional[Dict[str, Dict[str, bool]]] = None
    # permissions = { resource: { read: bool, write: bool, delete: bool } }

    @validator("key")
    def _validate_key(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", v):
            raise ValueError("key must be lowercase letters/digits/underscore, start with letter, max 40 chars")
        if v == "*":
            raise ValueError("'*' is a reserved wildcard token")
        return v


class UpdateRoleIn(BaseModel):
    label: Optional[str] = Field(None, min_length=2, max_length=80)
    description: Optional[str] = Field(None, max_length=400)


# ────────────────────────────────────────────────────────────────────────────
# Seed + read helpers
# ────────────────────────────────────────────────────────────────────────────
async def ensure_role_catalog_seeded() -> int:
    """Idempotent — inserts only missing built-ins. Returns count inserted."""
    inserted = 0
    existing = {r["key"]: r async for r in db.role_catalog.find({}, {"_id": 0, "key": 1})}
    for key, label, desc, order in BUILTIN_ROLE_SEED:
        if key in existing:
            continue
        await db.role_catalog.insert_one({
            "id": new_id(),
            "key": key,
            "label": label,
            "description": desc,
            "is_builtin": True,
            "sort_order": order,
            "created_at": now_iso(),
            "created_by": "system",
        })
        inserted += 1
    return inserted


async def get_active_role_keys() -> List[str]:
    """All role keys currently in the catalog. Used by other endpoints that
    need to validate role tokens (e.g. /admin/role-register)."""
    rows = await db.role_catalog.find({}, {"_id": 0, "key": 1, "sort_order": 1}).sort("sort_order", 1).to_list(200)
    return [r["key"] for r in rows]


async def _user_count_per_role() -> Dict[str, int]:
    pipeline = [{"$group": {"_id": "$role", "count": {"$sum": 1}}}]
    out: Dict[str, int] = {}
    async for d in db.users.aggregate(pipeline):
        if d.get("_id"):
            out[d["_id"]] = int(d["count"])
    return out


def _resources_in_use() -> List[str]:
    return sorted(set(PERMISSIONS_BASE.keys()) | set(_resolved().keys()))


# ────────────────────────────────────────────────────────────────────────────
# GET — list catalog with user counts
# ────────────────────────────────────────────────────────────────────────────
@router.get("/role-catalog")
async def list_role_catalog(user: dict = Depends(require_permission("role_register", "read"))):
    rows = await db.role_catalog.find({}, {"_id": 0}).sort([("sort_order", 1), ("created_at", 1)]).to_list(200)
    counts = await _user_count_per_role()
    for r in rows:
        r["user_count"] = counts.get(r["key"], 0)
    return {
        "roles": rows,
        "resources": _resources_in_use(),
        "actions": ["read", "write", "delete"],
    }


# ────────────────────────────────────────────────────────────────────────────
# POST — create custom role
# ────────────────────────────────────────────────────────────────────────────
@router.post("/role-catalog", status_code=201)
async def create_custom_role(
    payload: CreateRoleIn,
    request: Request,
    user: dict = Depends(require_permission("role_register", "write")),
):
    existing = await db.role_catalog.find_one({"key": payload.key}, {"_id": 0, "key": 1})
    if existing:
        raise HTTPException(409, f"Role key '{payload.key}' already exists")

    # Determine sort_order = max + 10
    last = await db.role_catalog.find_one({}, {"_id": 0, "sort_order": 1}, sort=[("sort_order", -1)])
    next_order = (last.get("sort_order", 0) if last else 0) + 10

    doc = {
        "id": new_id(),
        "key": payload.key,
        "label": payload.label.strip(),
        "description": (payload.description or "").strip(),
        "is_builtin": False,
        "sort_order": next_order,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.role_catalog.insert_one(doc)
    doc.pop("_id", None)  # strip ObjectId added by pymongo

    # Seed permissions: for every (resource, action) marked true, ADD the new
    # role to the effective set and persist as an override.
    seeded_count = 0
    if payload.permissions:
        current = _resolved()
        # Start overrides from current persisted overrides (so we don't lose them)
        new_overrides_doc = await db.rbac_overrides.find_one({"id": "default"}, {"_id": 0}) or {}
        new_overrides: Dict[str, Dict[str, List[str]]] = dict(new_overrides_doc.get("overrides", {}))

        valid_resources = set(current.keys())
        for resource, action_map in payload.permissions.items():
            if resource not in valid_resources:
                continue
            for action in ("read", "write", "delete"):
                if not action_map.get(action):
                    continue
                # Take current effective and add our new role
                effective_set = set(current.get(resource, {}).get(action, set()))
                effective_set.add(payload.key)
                effective_set.add("super_admin")  # invariant
                new_overrides.setdefault(resource, {})[action] = sorted(effective_set)
                seeded_count += 1

        if seeded_count:
            await db.rbac_overrides.update_one(
                {"id": "default"},
                {"$set": {
                    "overrides": new_overrides,
                    "updated_at": now_iso(),
                    "updated_by": user.get("name") or user.get("email"),
                }, "$setOnInsert": {"id": "default"}},
                upsert=True,
            )
            set_overrides(new_overrides)

    await audit(
        user=user,
        action="create_role",
        resource="role_catalog",
        record_id=payload.key,
        after={"key": payload.key, "label": payload.label, "permissions_seeded": seeded_count},
        ip=_ip(request),
    )
    doc["user_count"] = 0
    return {"role": doc, "permissions_seeded": seeded_count}


# ────────────────────────────────────────────────────────────────────────────
# PATCH — rename label/description (key & is_builtin are immutable)
# ────────────────────────────────────────────────────────────────────────────
@router.patch("/role-catalog/{key}")
async def update_custom_role(
    key: str,
    payload: UpdateRoleIn,
    request: Request,
    user: dict = Depends(require_permission("role_register", "write")),
):
    existing = await db.role_catalog.find_one({"key": key}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Role not found")

    update: Dict[str, str] = {}
    if payload.label is not None:
        update["label"] = payload.label.strip()
    if payload.description is not None:
        update["description"] = payload.description.strip()
    if not update:
        return {"role": existing}
    update["updated_at"] = now_iso()
    await db.role_catalog.update_one({"key": key}, {"$set": update})

    await audit(
        user=user,
        action="update_role",
        resource="role_catalog",
        record_id=key,
        before={"label": existing.get("label"), "description": existing.get("description")},
        after=update,
        ip=_ip(request),
    )
    return {"role": {**existing, **update}}


# ────────────────────────────────────────────────────────────────────────────
# DELETE — block if any user holds the role; strip from overrides
# ────────────────────────────────────────────────────────────────────────────
@router.delete("/role-catalog/{key}")
async def delete_role(
    key: str,
    request: Request,
    user: dict = Depends(require_permission("role_register", "delete")),
):
    if key == "super_admin":
        raise HTTPException(400, "super_admin is the root role and cannot be deleted.")

    existing = await db.role_catalog.find_one({"key": key}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Role not found")

    user_count = await db.users.count_documents({"role": key})
    if user_count > 0:
        raise HTTPException(
            409,
            f"Cannot delete role '{key}' — {user_count} user(s) currently hold it. "
            f"Reassign those users to another role first."
        )

    # Strip the role from every override cell
    overrides_doc = await db.rbac_overrides.find_one({"id": "default"}, {"_id": 0}) or {}
    overrides: Dict[str, Dict[str, List[str]]] = dict(overrides_doc.get("overrides", {}))
    changed = False
    for resource, rules in list(overrides.items()):
        for action in ("read", "write", "delete"):
            if action in rules and key in rules[action]:
                rules[action] = [r for r in rules[action] if r != key]
                changed = True
    if changed:
        await db.rbac_overrides.update_one(
            {"id": "default"},
            {"$set": {"overrides": overrides, "updated_at": now_iso(),
                      "updated_by": user.get("name") or user.get("email")}},
        )
        set_overrides(overrides)

    await db.role_catalog.delete_one({"key": key})

    await audit(
        user=user,
        action="delete_role",
        resource="role_catalog",
        record_id=key,
        before={"key": key, "label": existing.get("label"), "is_builtin": existing.get("is_builtin")},
        ip=_ip(request),
    )
    return {"ok": True, "deleted_key": key, "permissions_stripped": changed}


def _ip(request: Request) -> str:
    return request.client.host if request and request.client else "unknown"
