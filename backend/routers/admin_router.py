"""Super-Admin power-tool endpoints:
- Dropdown Master (categories -> options)
- Approval Matrix (db override of approval_engine.APPROVAL_CHAINS)
- Audit Trail viewer
- Login Activity (session monitor)

All endpoints require super_admin via require_super_admin.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id, ROLES, logger, hash_password, require_permission
from approval_engine import APPROVAL_CHAINS
from rbac import (
    PERMISSIONS_BASE, _resolved, set_overrides,
    get_overrides_serializable, _invalidate_cache,
)
from audit import audit
import re
from pydantic import EmailStr, Field

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin only")
    return user


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- Dropdown Master ----------
class DropdownOption(BaseModel):
    category: str
    label: str
    value: str
    order: int = 0
    active: bool = True


@router.get("/dropdowns")
async def list_dropdowns(category: Optional[str] = None, user: dict = Depends(require_super_admin)):
    q: Dict[str, Any] = {}
    if category:
        q["category"] = category
    rows = await db.dropdown_options.find(q, {"_id": 0}).sort([("category", 1), ("order", 1)]).to_list(2000)
    return rows


@router.get("/dropdowns/categories")
async def dropdown_categories(user: dict = Depends(get_current_user)):
    """Any authenticated user can READ category list (UI selects need this)."""
    cats = await db.dropdown_options.distinct("category")
    return sorted(cats)


@router.get("/dropdowns/by-category/{category}")
async def dropdown_by_category(category: str, user: dict = Depends(get_current_user)):
    """Public read of a single category — used by module forms to populate selects."""
    rows = await db.dropdown_options.find({"category": category, "active": True}, {"_id": 0}).sort("order", 1).to_list(500)
    return rows


@router.post("/dropdowns")
async def create_dropdown(payload: DropdownOption, request: Request, user: dict = Depends(require_super_admin)):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    await db.dropdown_options.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="dropdown_options", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/dropdowns/{opt_id}")
async def update_dropdown(opt_id: str, payload: Dict[str, Any], request: Request, user: dict = Depends(require_super_admin)):
    before = await db.dropdown_options.find_one({"id": opt_id}, {"_id": 0})
    payload.pop("id", None)
    payload["updated_at"] = now_iso()
    result = await db.dropdown_options.update_one({"id": opt_id}, {"$set": payload})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    after = await db.dropdown_options.find_one({"id": opt_id}, {"_id": 0})
    await audit(user=user, action="update", resource="dropdown_options", record_id=opt_id, before=before, after=after, ip=_ip(request))
    return after


@router.delete("/dropdowns/{opt_id}")
async def delete_dropdown(opt_id: str, request: Request, user: dict = Depends(require_super_admin)):
    before = await db.dropdown_options.find_one({"id": opt_id}, {"_id": 0})
    result = await db.dropdown_options.delete_one({"id": opt_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await audit(user=user, action="delete", resource="dropdown_options", record_id=opt_id, before=before, ip=_ip(request))
    return {"ok": True}


# ---------- Approval Matrix ----------
class ChainStep(BaseModel):
    role: str
    label: str


class ApprovalChainIn(BaseModel):
    type: str
    steps: List[ChainStep]


@router.get("/approval-matrix")
async def list_matrix(user: dict = Depends(require_super_admin)):
    """Return the merged matrix: every default type plus any DB overrides."""
    db_rows = {r["type"]: r async for r in db.approval_chains.find({}, {"_id": 0})}
    out: List[Dict[str, Any]] = []
    seen = set()
    for atype, steps in APPROVAL_CHAINS.items():
        seen.add(atype)
        override = db_rows.get(atype)
        out.append({
            "type": atype,
            "steps": override["steps"] if override else steps,
            "source": "custom" if override else "default",
            "id": override.get("id") if override else None,
            "updated_at": override.get("updated_at") if override else None,
        })
    for atype, row in db_rows.items():
        if atype in seen:
            continue
        out.append({
            "type": atype,
            "steps": row["steps"],
            "source": "custom",
            "id": row.get("id"),
            "updated_at": row.get("updated_at"),
        })
    return out


@router.get("/approval-matrix/roles")
async def matrix_roles(user: dict = Depends(get_current_user)):
    from routers.role_catalog_router import get_active_role_keys
    keys = await get_active_role_keys()
    return keys or ROLES


async def _allowed_role_keys() -> set:
    """Union of catalog keys + static ROLES (defensive)."""
    from routers.role_catalog_router import get_active_role_keys
    return set(await get_active_role_keys()) | set(ROLES)


@router.put("/approval-matrix/{atype}")
async def upsert_matrix(atype: str, payload: ApprovalChainIn, request: Request, user: dict = Depends(require_super_admin)):
    if not payload.steps:
        raise HTTPException(status_code=400, detail="At least one step is required")
    allowed = await _allowed_role_keys()
    for s in payload.steps:
        if s.role not in allowed:
            raise HTTPException(status_code=400, detail=f"Unknown role: {s.role}")
    before = await db.approval_chains.find_one({"type": atype}, {"_id": 0})
    doc = {
        "type": atype,
        "steps": [s.model_dump() for s in payload.steps],
        "updated_at": now_iso(),
        "updated_by": user["id"],
    }
    if before:
        await db.approval_chains.update_one({"type": atype}, {"$set": doc})
    else:
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        await db.approval_chains.insert_one(doc)
    after = await db.approval_chains.find_one({"type": atype}, {"_id": 0})
    await audit(user=user, action="upsert", resource="approval_chains", record_id=atype, before=before, after=after, ip=_ip(request))
    return after


@router.delete("/approval-matrix/{atype}")
async def reset_matrix(atype: str, request: Request, user: dict = Depends(require_super_admin)):
    """Reset a chain back to its built-in default by removing the DB override."""
    before = await db.approval_chains.find_one({"type": atype}, {"_id": 0})
    res = await db.approval_chains.delete_one({"type": atype})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No custom override to reset")
    await audit(user=user, action="reset", resource="approval_chains", record_id=atype, before=before, ip=_ip(request))
    return {"ok": True}


# ---------- Audit Trail viewer ----------
@router.get("/audit-logs")
async def list_audit_logs(
    resource: Optional[str] = None,
    actor_id: Optional[str] = None,
    record_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 200,
    user: dict = Depends(require_super_admin),
):
    q: Dict[str, Any] = {}
    if resource:
        q["resource"] = resource
    if actor_id:
        q["actor_id"] = actor_id
    if record_id:
        q["record_id"] = record_id
    if action:
        q["action"] = action
    limit = max(1, min(limit, 1000))
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("ts", -1).to_list(limit)
    return rows


# ---------- Login Activity (Session Monitor) ----------


# ============================================================================
# USER MANAGEMENT
# ============================================================================
class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=2, max_length=80)
    role: str
    department: Optional[str] = None
    phone: Optional[str] = None
    active: bool = True
    must_change_password: bool = False


class UserUpdateIn(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    active: Optional[bool] = None
    email: Optional[EmailStr] = None


class PasswordResetIn(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)
    must_change_password: bool = False


_STRONG_PW = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")


def _check_password_strength(pw: str) -> None:
    if not _STRONG_PW.match(pw):
        raise HTTPException(
            status_code=400,
            detail="Password must be 8-128 chars and contain at least one letter and one digit.",
        )


def _safe_user(doc: dict) -> dict:
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    doc.setdefault("active", True)
    doc.setdefault("must_change_password", False)
    return doc


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/users")
async def admin_list_users(user: dict = Depends(require_permission("users", "read"))):
    rows = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort([("created_at", 1)]).to_list(2000)
    return [_safe_user(r) for r in rows]


@router.post("/users")
async def admin_create_user(payload: UserCreateIn, request: Request,
                            user: dict = Depends(require_permission("users", "write"))):
    allowed = await _allowed_role_keys()
    if payload.role not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid role '{payload.role}'. Use /api/admin/role-catalog to see assignable roles.")
    _check_password_strength(payload.password)
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {
        "id": new_id(),
        "email": email,
        "name": payload.name.strip(),
        "role": payload.role,
        "department": payload.department,
        "phone": payload.phone,
        "active": payload.active,
        "must_change_password": payload.must_change_password,
        "password_hash": hash_password(payload.password),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.users.insert_one(doc)
    safe = _safe_user(dict(doc))
    await audit(user=user, action="create_user", resource="users", record_id=doc["id"],
                after={"email": email, "role": payload.role, "active": payload.active}, ip=_ip(request))
    return safe


@router.put("/users/{user_id}")
async def admin_update_user(user_id: str, payload: UserUpdateIn, request: Request,
                            user: dict = Depends(require_permission("users", "write"))):
    existing = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    patch: Dict[str, Any] = {}
    if payload.name is not None: patch["name"] = payload.name.strip()
    if payload.role is not None:
        allowed = await _allowed_role_keys()
        if payload.role not in allowed:
            raise HTTPException(status_code=400, detail=f"Invalid role '{payload.role}'.")
        if existing.get("role") == "super_admin" and payload.role != "super_admin":
            count = await db.users.count_documents({"role": "super_admin"})
            if count <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the only super_admin user.")
        patch["role"] = payload.role
    if payload.department is not None: patch["department"] = payload.department
    if payload.phone is not None: patch["phone"] = payload.phone
    if payload.active is not None:
        if existing.get("role") == "super_admin" and not payload.active:
            count = await db.users.count_documents({"role": "super_admin", "active": {"$ne": False}})
            if count <= 1:
                raise HTTPException(status_code=400, detail="Cannot deactivate the only super_admin user.")
        patch["active"] = payload.active
    if payload.email is not None:
        new_email = payload.email.lower().strip()
        if new_email != existing.get("email"):
            if await db.users.find_one({"email": new_email, "id": {"$ne": user_id}}):
                raise HTTPException(status_code=400, detail="Email already in use")
            patch["email"] = new_email
    if not patch:
        return _safe_user(existing)
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.users.update_one({"id": user_id}, {"$set": patch})
    row = await db.users.find_one({"id": user_id}, {"_id": 0})
    await audit(user=user, action="update_user", resource="users", record_id=user_id,
                after=patch, ip=_ip(request))
    return _safe_user(row or {})


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, payload: PasswordResetIn, request: Request,
                               user: dict = Depends(require_permission("users", "write"))):
    existing = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    _check_password_strength(payload.password)
    patch = {
        "password_hash": hash_password(payload.password),
        "must_change_password": payload.must_change_password,
        "password_reset_at": now_iso(),
        "password_reset_by": user.get("name") or user.get("email"),
    }
    await db.users.update_one({"id": user_id}, {"$set": patch})
    await db.login_attempts.delete_many({"identifier": {"$regex": f":{existing.get('email')}$"}})
    await audit(user=user, action="reset_password", resource="users", record_id=user_id,
                after={"must_change_password": payload.must_change_password}, ip=_ip(request))
    return {"ok": True, "user_id": user_id, "email": existing.get("email")}


@router.post("/users/{user_id}/toggle-active")
async def admin_toggle_active(user_id: str, request: Request,
                              user: dict = Depends(require_permission("users", "write"))):
    existing = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    new_active = not bool(existing.get("active", True))
    if not new_active and existing.get("role") == "super_admin":
        count = await db.users.count_documents({"role": "super_admin", "active": {"$ne": False}})
        if count <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the only super_admin user.")
    await db.users.update_one({"id": user_id}, {"$set": {"active": new_active, "updated_at": now_iso(),
                                                          "updated_by": user.get("name") or user.get("email")}})
    await audit(user=user, action="toggle_active", resource="users", record_id=user_id,
                after={"active": new_active}, ip=_ip(request))
    return {"ok": True, "active": new_active}


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request,
                            user: dict = Depends(require_permission("users", "delete"))):
    existing = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    if existing.get("role") == "super_admin":
        count = await db.users.count_documents({"role": "super_admin"})
        if count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only super_admin user.")
    if existing.get("id") == user.get("id"):
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    await db.users.delete_one({"id": user_id})
    await audit(user=user, action="delete_user", resource="users", record_id=user_id,
                after={"email": existing.get("email")}, ip=_ip(request))
    return {"ok": True, "deleted_id": user_id}


# ============================================================================
# ROLE REGISTER — permission matrix override layer
# ============================================================================
def _serialize_map(m: Dict[str, Dict[str, set]]) -> Dict[str, Dict[str, list]]:
    return {res: {act: sorted(list(roles)) for act, roles in rules.items()} for res, rules in m.items()}


@router.get("/role-register")
async def get_role_register(user: dict = Depends(require_permission("role_register", "read"))):
    from routers.role_catalog_router import get_active_role_keys
    base = _serialize_map({res: rules for res, rules in PERMISSIONS_BASE.items()})
    overrides = get_overrides_serializable()
    effective = _serialize_map(_resolved())
    catalog_roles = await get_active_role_keys()
    # Use catalog as the source of truth; if catalog is somehow empty, fall back to ROLES
    return {
        "roles": catalog_roles or ROLES,
        "actions": ["read", "write", "delete"],
        "resources": sorted(list(_resolved().keys())),
        "base": base,
        "overrides": overrides,
        "effective": effective,
    }


class RoleRegisterUpdateIn(BaseModel):
    overrides: Dict[str, Dict[str, List[str]]]


@router.put("/role-register")
async def update_role_register(payload: RoleRegisterUpdateIn, request: Request,
                               user: dict = Depends(require_permission("role_register", "write"))):
    from routers.role_catalog_router import get_active_role_keys
    catalog_keys = set(await get_active_role_keys())
    allowed_tokens = catalog_keys | set(ROLES) | {"*"}
    cleaned: Dict[str, Dict[str, List[str]]] = {}
    for res, rules in (payload.overrides or {}).items():
        if res not in _resolved() and res not in PERMISSIONS_BASE:
            raise HTTPException(status_code=400, detail=f"Unknown resource '{res}'")
        cleaned[res] = {}
        for action, roles in (rules or {}).items():
            if action not in ("read", "write", "delete"):
                raise HTTPException(status_code=400, detail=f"Unknown action '{action}'")
            bad = [r for r in (roles or []) if r not in allowed_tokens]
            if bad:
                raise HTTPException(status_code=400, detail=f"Unknown roles {bad} for {res}.{action}")
            role_set = sorted(set(roles or []) | {"super_admin"})
            cleaned[res][action] = role_set
    await db.rbac_overrides.update_one(
        {"id": "default"},
        {"$set": {
            "overrides": cleaned,
            "updated_at": now_iso(),
            "updated_by": user.get("name") or user.get("email"),
        }, "$setOnInsert": {"id": "default"}},
        upsert=True,
    )
    set_overrides(cleaned)
    await audit(user=user, action="update_role_register", resource="role_register",
                record_id="default", after={"resource_count": len(cleaned)}, ip=_ip(request))
    return await get_role_register(user)


@router.post("/role-register/reset")
async def reset_role_register(request: Request,
                              user: dict = Depends(require_permission("role_register", "delete"))):
    await db.rbac_overrides.delete_many({"id": "default"})
    set_overrides({})
    await audit(user=user, action="reset_role_register", resource="role_register",
                record_id="default", after={}, ip=_ip(request))
    return await get_role_register(user)


# ============================================================================
# Startup loader
# ============================================================================
async def load_rbac_overrides_on_startup() -> int:
    """Load DB overrides into the in-memory rbac cache. Returns the count of
    resource entries loaded. Safe to call multiple times."""
    try:
        row = await db.rbac_overrides.find_one({"id": "default"}, {"_id": 0})
        overrides = (row or {}).get("overrides") or {}
        set_overrides(overrides)
        return len(overrides)
    except Exception as e:
        logger.warning(f"RBAC override load skipped: {e}")
        _invalidate_cache()
        return 0

@router.get("/login-activity")
async def login_activity(limit: int = 100, user: dict = Depends(require_super_admin)):
    limit = max(1, min(limit, 500))
    rows = await db.login_activity.find({}, {"_id": 0}).sort("at", -1).to_list(limit)
    return rows


# ─────────────────────────────────────────────────────────────────────
# Iter 52 — Sequence counter reset utility
# ─────────────────────────────────────────────────────────────────────
# After test data is deleted, document counters (HR/ADV/2026 = 43 etc.)
# stay high and new clients/POs/PRs start from inflated numbers.
# This admin tool re-syncs every counter — either to the MAX value
# actually present in the corresponding collection (safe / "auto") or
# to ZERO (next allocation = 1, hard reset / "force").
# ─────────────────────────────────────────────────────────────────────

SEQUENCE_DATA_MAP: dict[str, tuple[str, str]] = {
    "EMP":   ("employees", "employee_id"),
    "AD":    ("employee_advances", "advance_no"),
    "ALC":   ("material_allocations", "code"),
    "CH":    ("delivery_challans", "challan_no"),
    "DEP":   ("deployments", "code"),
    "DPR":   ("dpr", "dpr_no"),
    "ENQ":   ("enquiries", "enquiry_no"),
    "GRN":   ("grn", "grn_no"),
    "INC":   ("safety_incidents", "incident_no"),
    "INV":   ("invoices", "invoice_no"),
    "JV":    ("journal_entries", "voucher_no"),
    "MEAS":  ("measurements", "code"),
    "ORD":   ("sales_orders", "order_no"),
    "OT":    ("overtime", "code"),
    "PAY":   ("payments", "payment_no"),
    "PO":    ("purchase_orders", "po_number"),
    "PR":    ("purchase_requisitions", "pr_no"),
    "PRJ":   ("projects", "code"),
    "PTW":   ("permits_to_work", "ptw_no"),
    "QTN":   ("quotations", "quotation_no"),
    "RA":    ("ra_bills", "bill_no"),
    "REQ":   ("material_requisitions", "code"),
    "RFQ":   ("rfqs", "rfq_no"),
    "TBT":   ("toolbox_talks", "code"),
    "TRN":   ("trainings", "code"),
}


def _parse_seq_key(key: str) -> tuple[str, int | None]:
    if "/" in key:
        parts = key.split("/")
        if len(parts) == 3 and parts[2].isdigit():
            return ("/".join(parts[:2]), int(parts[2]))
        return (key, None)
    if "-" in key:
        prefix, _, year = key.rpartition("-")
        if year.isdigit():
            return (prefix, int(year))
    return (key, None)


def _extract_n(doc_no: str, key: str) -> int | None:
    if not doc_no:
        return None
    parts = str(doc_no).replace("/", "-").split("-")
    if not parts:
        return None
    try:
        return int(parts[-1])
    except ValueError:
        return None


async def _max_existing_for_key(key: str) -> int:
    prefix, year = _parse_seq_key(key)
    if "/" in prefix:
        candidate_collections = [
            "employee_advances", "purchase_requisitions", "purchase_orders", "rfqs",
            "vendors", "grn", "inventory_transactions", "enquiries", "quotations",
            "sales_orders", "ra_bills", "vendor_invoices", "credit_notes",
            "debit_notes", "payments", "journal_entries", "projects", "dpr",
            "measurements", "safety_reports", "incidents", "permits_to_work",
            "delivery_challans", "vehicle_logs", "dispatches", "clients",
            "deployments", "employees", "leave_requests", "exit_clearances",
            "overtime", "onboarding_records", "payslips",
        ]
        like = f"{key}/" if year else f"{prefix}/"
        max_n = 0
        for coll in candidate_collections:
            try:
                cursor = db[coll].find(
                    {"dept_doc_no": {"$regex": f"^{like}", "$options": ""}},
                    {"_id": 0, "dept_doc_no": 1},
                ).limit(2000)
                async for d in cursor:
                    n = _extract_n(d.get("dept_doc_no"), key)
                    if n and n > max_n:
                        max_n = n
            except Exception:
                continue
        return max_n
    coll_field = SEQUENCE_DATA_MAP.get(prefix)
    if not coll_field:
        return 0
    coll, field = coll_field
    like = f"{prefix}-{year}-" if year else f"{prefix}-"
    cursor = db[coll].find(
        {field: {"$regex": f"^{like}", "$options": ""}},
        {"_id": 0, field: 1},
    ).limit(5000)
    max_n = 0
    async for d in cursor:
        n = _extract_n(d.get(field), prefix)
        if n and n > max_n:
            max_n = n
    return max_n


@router.get("/sequences")
async def list_sequences(user: dict = Depends(require_super_admin)):
    """Return every sequence counter with current value + max-in-data."""
    rows = []
    async for d in db.sequences.find({}, {"_id": 1, "value": 1}).sort("_id", 1):
        key = d["_id"]
        current = int(d.get("value") or 0)
        max_in_data = await _max_existing_for_key(key)
        rows.append({
            "key": key,
            "current_value": current,
            "max_in_data": max_in_data,
            "drift": current - max_in_data,
            "can_safely_reset_to_zero": max_in_data == 0,
        })
    return rows


class SequenceResetIn(BaseModel):
    mode: str = "auto"
    keys: Optional[List[str]] = None


@router.post("/sequences/reset")
async def reset_sequences(payload: SequenceResetIn, request: Request,
                           user: dict = Depends(require_super_admin)):
    """Bulk reset (auto = max-in-data) or hard zero (force)."""
    if payload.mode not in ("auto", "force"):
        raise HTTPException(status_code=400, detail="mode must be 'auto' or 'force'")
    q: dict = {}
    if payload.keys:
        q["_id"] = {"$in": payload.keys}
    changes = []
    async for d in db.sequences.find(q, {"_id": 1, "value": 1}):
        key = d["_id"]
        old = int(d.get("value") or 0)
        new_val = (await _max_existing_for_key(key)) if payload.mode == "auto" else 0
        if new_val != old:
            await db.sequences.update_one({"_id": key}, {"$set": {"value": new_val}})
        changes.append({"key": key, "old": old, "new": new_val,
                         "next_allocation": new_val + 1})
    await db.audit_log.insert_one({
        "id": new_id(), "actor_id": user.get("id"),
        "actor": user.get("name") or user.get("email"),
        "action": "sequences.reset",
        "details": {"mode": payload.mode, "key_count": len(changes),
                     "keys": payload.keys},
        "at": now_iso(), "ip": _ip(request),
    })
    return {"ok": True, "mode": payload.mode, "reset_count": len(changes), "changes": changes}


@router.delete("/sequences/{key}")
async def delete_sequence_key(key: str, request: Request,
                               user: dict = Depends(require_super_admin)):
    """Delete a sequence counter. Next access re-creates it from 1."""
    r = await db.sequences.delete_one({"_id": key})
    await db.audit_log.insert_one({
        "id": new_id(), "actor_id": user.get("id"),
        "actor": user.get("name") or user.get("email"),
        "action": "sequences.delete",
        "details": {"key": key, "deleted": r.deleted_count},
        "at": now_iso(), "ip": _ip(request),
    })
    return {"ok": True, "deleted": r.deleted_count}
