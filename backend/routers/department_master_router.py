"""Department Master CRUD (Iter 47).

Stores configurable department definitions plus sub-departments / branches / business_units
in `db.department_master`. The 9 primary departments are seeded on startup.

Note: this is the ADMIN master — display labels & metadata. The existing
`departments_router.py` (workspace KPIs) and `role_department_map` (RBAC) remain as-is.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, now_iso, new_id

router = APIRouter(prefix="/admin/department-master", tags=["department-master"])


DEFAULT_DEPARTMENTS = [
    {"slug": "sales",       "code": "SAL", "name": "Sales",                 "color": "info"},
    {"slug": "projects",    "code": "OPS", "name": "Projects / Operations", "color": "primary"},
    {"slug": "accounts",    "code": "ACC", "name": "Accounts",              "color": "success"},
    {"slug": "finance",     "code": "FIN", "name": "Finance",               "color": "success"},
    {"slug": "store",       "code": "STO", "name": "Store / Inventory",     "color": "warning"},
    {"slug": "safety",      "code": "SAF", "name": "Safety",                "color": "danger"},
    {"slug": "logistics",   "code": "LOG", "name": "Logistics",             "color": "info"},
    {"slug": "hr",          "code": "HR",  "name": "Human Resources",       "color": "primary"},
    {"slug": "procurement", "code": "PRO", "name": "Vendors / Procurement", "color": "warning"},
]


async def seed_department_master_if_empty() -> int:
    if await db.department_master.count_documents({}) > 0:
        return 0
    docs = [
        {"id": new_id(), **d, "sub_departments": [], "branches": [], "business_units": [],
         "active": True, "created_at": now_iso()}
        for d in DEFAULT_DEPARTMENTS
    ]
    await db.department_master.insert_many(docs)
    return len(docs)


def _require_admin(user: dict) -> None:
    if user.get("role") not in {"super_admin", "director", "general_manager"}:
        raise HTTPException(status_code=403, detail="admin only")


class DepartmentIn(BaseModel):
    slug: str
    code: str
    name: str
    color: str = "neutral"
    sub_departments: list[str] = Field(default_factory=list)
    branches: list[str] = Field(default_factory=list)
    business_units: list[str] = Field(default_factory=list)
    active: bool = True


@router.get("")
async def list_departments(user: dict = Depends(get_current_user)):
    rows = await db.department_master.find({}, {"_id": 0}).sort("name", 1).to_list(50)
    return rows


@router.post("")
async def add_department(payload: DepartmentIn, user: dict = Depends(get_current_user)):
    _require_admin(user)
    slug = payload.slug.strip().lower()
    if not slug or not payload.code or not payload.name:
        raise HTTPException(status_code=400, detail="slug, code and name required")
    if await db.department_master.find_one({"slug": slug}):
        raise HTTPException(status_code=409, detail="slug already exists")
    doc = {"id": new_id(), **payload.model_dump(), "slug": slug,
           "code": payload.code.upper(), "created_at": now_iso(),
           "created_by": user.get("name") or user.get("email")}
    await db.department_master.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{dept_id}")
async def update_department(dept_id: str, payload: DepartmentIn, user: dict = Depends(get_current_user)):
    _require_admin(user)
    update = {**payload.model_dump(), "slug": payload.slug.strip().lower(),
              "code": payload.code.upper(), "updated_at": now_iso()}
    res = await db.department_master.update_one({"id": dept_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.delete("/{dept_id}")
async def delete_department(dept_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    doc = await db.department_master.find_one({"id": dept_id})
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    if doc.get("slug") in {d["slug"] for d in DEFAULT_DEPARTMENTS}:
        raise HTTPException(status_code=400, detail="cannot delete a built-in department")
    await db.department_master.delete_one({"id": dept_id})
    return {"ok": True}


class SubItemIn(BaseModel):
    kind: str   # "sub_departments" | "branches" | "business_units"
    value: str


@router.post("/{dept_id}/items")
async def add_sub_item(dept_id: str, payload: SubItemIn, user: dict = Depends(get_current_user)):
    _require_admin(user)
    if payload.kind not in {"sub_departments", "branches", "business_units"}:
        raise HTTPException(status_code=400, detail="invalid kind")
    if not payload.value.strip():
        raise HTTPException(status_code=400, detail="value required")
    res = await db.department_master.update_one(
        {"id": dept_id},
        {"$addToSet": {payload.kind: payload.value.strip()},
         "$set": {"updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.delete("/{dept_id}/items")
async def remove_sub_item(dept_id: str, kind: str, value: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    if kind not in {"sub_departments", "branches", "business_units"}:
        raise HTTPException(status_code=400, detail="invalid kind")
    res = await db.department_master.update_one(
        {"id": dept_id},
        {"$pull": {kind: value}, "$set": {"updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}
