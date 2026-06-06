"""Procurement Master — Categories, Items, and Cost Centers.

This powers the PR creation dropdowns (department / project / site / category /
item name) and the admin control panels for managing the master data.

Collections used:
  • db.pr_categories       — { id, code, name, gst_pct, default_hsn, active, ... }
  • db.pr_items            — { id, code, name, category_id, category_code, unit,
                               hsn_sac, last_rate, default_vendor_id, active, ... }
  • db.cost_centers        — { id, project_id, project_code, category_id, category_code,
                               code, name, budget, committed, actual, active, ... }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, get_current_user, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/procurement/master", tags=["procurement-master"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _strip(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────── CATEGORIES ───────────────────────────
class CategoryIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = None
    gst_pct: Optional[float] = 18.0
    default_hsn: Optional[str] = None
    active: bool = True


class CategoryUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    gst_pct: Optional[float] = None
    default_hsn: Optional[str] = None
    active: Optional[bool] = None


@router.get("/categories")
async def list_categories(active_only: bool = False, user: dict = Depends(get_current_user)):
    """Any authenticated user can read — used by PR form dropdowns."""
    q: Dict[str, Any] = {}
    if active_only:
        q["active"] = True
    rows = await db.pr_categories.find(q, {"_id": 0}).sort([("name", 1)]).to_list(500)
    # Attach live item count
    code_counts: Dict[str, int] = {}
    pipeline = [{"$group": {"_id": "$category_code", "n": {"$sum": 1}}}]
    async for r in db.pr_items.aggregate(pipeline):
        code_counts[r["_id"] or ""] = r["n"]
    for r in rows:
        r["item_count"] = code_counts.get(r.get("code"), 0)
    return rows


@router.post("/categories")
async def create_category(payload: CategoryIn, request: Request,
                          user: dict = Depends(require_permission("procurement_master", "write"))):
    code = payload.code.strip().upper()
    if await db.pr_categories.find_one({"code": code}):
        raise HTTPException(status_code=400, detail=f"Category code '{code}' already exists")
    doc = payload.model_dump()
    doc["code"] = code
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    await db.pr_categories.insert_one(doc)
    await audit(user=user, action="create", resource="pr_categories", record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.put("/categories/{cid}")
async def update_category(cid: str, payload: CategoryUpdate, request: Request,
                          user: dict = Depends(require_permission("procurement_master", "write"))):
    existing = await db.pr_categories.find_one({"id": cid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Category not found")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "code" in patch:
        patch["code"] = patch["code"].strip().upper()
        if patch["code"] != existing.get("code"):
            if await db.pr_categories.find_one({"code": patch["code"], "id": {"$ne": cid}}):
                raise HTTPException(status_code=400, detail="Code already in use")
            # Cascade rename — keep linked items, cost centers, and any open PO/GRN line items in sync
            await db.pr_items.update_many({"category_id": cid}, {"$set": {"category_code": patch["code"]}})
            await db.cost_centers.update_many({"category_id": cid}, {"$set": {"category_code": patch["code"]}})
            await db.purchase_orders.update_many(
                {"items.category_id": cid},
                {"$set": {"items.$[el].category_code": patch["code"]}},
                array_filters=[{"el.category_id": cid}],
            )
            await db.grn.update_many(
                {"items.category_id": cid},
                {"$set": {"items.$[el].category_code": patch["code"]}},
                array_filters=[{"el.category_id": cid}],
            )
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.pr_categories.update_one({"id": cid}, {"$set": patch})
    row = await db.pr_categories.find_one({"id": cid}, {"_id": 0})
    await audit(user=user, action="update", resource="pr_categories", record_id=cid, after=patch, ip=_ip(request))
    return _strip(row)


@router.delete("/categories/{cid}")
async def delete_category(cid: str, request: Request,
                          user: dict = Depends(require_permission("procurement_master", "delete"))):
    item_links = await db.pr_items.count_documents({"category_id": cid})
    cc_links = await db.cost_centers.count_documents({"category_id": cid})
    if item_links or cc_links:
        raise HTTPException(status_code=400,
                            detail=f"Cannot delete — category has {item_links} item(s) and {cc_links} cost center(s) linked. Deactivate instead.")
    res = await db.pr_categories.delete_one({"id": cid})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Category not found")
    await audit(user=user, action="delete", resource="pr_categories", record_id=cid, after={}, ip=_ip(request))
    return {"ok": True}


# ────────────────────────────────────────── ITEMS ─────────────────────────────
class ItemIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=120)
    category_id: str
    description: Optional[str] = None
    unit: str = "Nos"
    hsn_sac: Optional[str] = None
    last_rate: Optional[float] = 0.0
    default_vendor_id: Optional[str] = None
    active: bool = True


class ItemUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    category_id: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    hsn_sac: Optional[str] = None
    last_rate: Optional[float] = None
    default_vendor_id: Optional[str] = None
    active: Optional[bool] = None


async def _resolve_category(category_id: str) -> Dict[str, Any]:
    cat = await db.pr_categories.find_one({"id": category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=400, detail=f"category_id '{category_id}' does not exist")
    return cat


@router.get("/items")
async def list_items(category_id: Optional[str] = None, active_only: bool = False,
                     user: dict = Depends(get_current_user)):
    q: Dict[str, Any] = {}
    if category_id:
        q["category_id"] = category_id
    if active_only:
        q["active"] = True
    rows = await db.pr_items.find(q, {"_id": 0}).sort([("category_code", 1), ("name", 1)]).to_list(2000)
    return rows


@router.post("/items")
async def create_item(payload: ItemIn, request: Request,
                      user: dict = Depends(require_permission("procurement_master", "write"))):
    cat = await _resolve_category(payload.category_id)
    code = payload.code.strip().upper()
    if await db.pr_items.find_one({"code": code}):
        raise HTTPException(status_code=400, detail=f"Item code '{code}' already exists")
    doc = payload.model_dump()
    doc["code"] = code
    doc["category_code"] = cat.get("code")
    doc["category_name"] = cat.get("name")
    if not doc.get("hsn_sac"):
        doc["hsn_sac"] = cat.get("default_hsn")
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    await db.pr_items.insert_one(doc)
    await audit(user=user, action="create", resource="pr_items", record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.put("/items/{iid}")
async def update_item(iid: str, payload: ItemUpdate, request: Request,
                      user: dict = Depends(require_permission("procurement_master", "write"))):
    existing = await db.pr_items.find_one({"id": iid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "code" in patch:
        patch["code"] = patch["code"].strip().upper()
        if patch["code"] != existing.get("code") and await db.pr_items.find_one({"code": patch["code"], "id": {"$ne": iid}}):
            raise HTTPException(status_code=400, detail="Code already in use")
    if "category_id" in patch:
        cat = await _resolve_category(patch["category_id"])
        patch["category_code"] = cat.get("code")
        patch["category_name"] = cat.get("name")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.pr_items.update_one({"id": iid}, {"$set": patch})
    row = await db.pr_items.find_one({"id": iid}, {"_id": 0})
    await audit(user=user, action="update", resource="pr_items", record_id=iid, after=patch, ip=_ip(request))
    return _strip(row)


@router.delete("/items/{iid}")
async def delete_item(iid: str, request: Request,
                      user: dict = Depends(require_permission("procurement_master", "delete"))):
    res = await db.pr_items.delete_one({"id": iid})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Item not found")
    await audit(user=user, action="delete", resource="pr_items", record_id=iid, after={}, ip=_ip(request))
    return {"ok": True}


# ──────────────────────────────────────── COST CENTERS ────────────────────────
class CostCenterIn(BaseModel):
    project_id: str
    category_id: str
    code: Optional[str] = None        # auto-generated if omitted
    name: Optional[str] = None
    budget: float = 0.0
    active: bool = True


class CostCenterUpdate(BaseModel):
    name: Optional[str] = None
    budget: Optional[float] = None
    active: Optional[bool] = None


async def _resolve_project(project_id: str) -> Dict[str, Any]:
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=400, detail=f"project_id '{project_id}' does not exist")
    return p


async def _cc_actuals(project_id: str, category_code: str) -> Dict[str, float]:
    """Roll up committed (PO) and actual (GRN) spend for the (project, category)."""
    link_or = []
    for k in ("project_id", "project_code", "project"):
        link_or.append({k: project_id})
    # We may not know the project_code at call time; the simpler approach is to
    # match by project_id (PO router stamps project_id on each PO), then filter
    # items by category_code below.
    po_rows = await db.purchase_orders.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    committed = 0.0
    for po in po_rows:
        for it in (po.get("items") or []):
            if (it.get("category_code") or it.get("category")) == category_code:
                committed += float(it.get("amount") or it.get("total") or (float(it.get("quantity") or 0) * float(it.get("rate") or 0)) or 0)
    grn_rows = await db.grn.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    actual = 0.0
    for g in grn_rows:
        for it in (g.get("items") or []):
            if (it.get("category_code") or it.get("category")) == category_code:
                actual += float(it.get("amount") or it.get("total") or 0)
    return {"committed": round(committed, 2), "actual": round(actual, 2)}


@router.get("/cost-centers")
async def list_cost_centers(project_id: Optional[str] = None,
                            user: dict = Depends(get_current_user)):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    rows = await db.cost_centers.find(q, {"_id": 0}).sort([("project_code", 1), ("category_code", 1)]).to_list(2000)
    # Live spend rollup (best-effort; doesn't persist)
    for r in rows:
        try:
            roll = await _cc_actuals(r.get("project_id"), r.get("category_code"))
            r["committed"] = roll["committed"]
            r["actual"] = roll["actual"]
            r["remaining"] = round(float(r.get("budget") or 0) - roll["committed"], 2)
        except Exception:
            pass
    return rows


@router.post("/cost-centers")
async def create_cost_center(payload: CostCenterIn, request: Request,
                             user: dict = Depends(require_permission("procurement_master", "write"))):
    proj = await _resolve_project(payload.project_id)
    cat = await _resolve_category(payload.category_id)
    existing = await db.cost_centers.find_one({"project_id": payload.project_id, "category_id": payload.category_id})
    if existing:
        raise HTTPException(status_code=400, detail="Cost center already exists for this project + category")
    code = payload.code or f"CC-{proj.get('code') or proj.get('id', '')[:6]}-{cat.get('code')}"
    doc = {
        "id": new_id(),
        "project_id": payload.project_id,
        "project_code": proj.get("code"),
        "project_name": proj.get("name"),
        "category_id": payload.category_id,
        "category_code": cat.get("code"),
        "category_name": cat.get("name"),
        "code": code,
        "name": payload.name or f"{proj.get('name')} · {cat.get('name')}",
        "budget": payload.budget,
        "committed": 0.0,
        "actual": 0.0,
        "active": payload.active,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.cost_centers.insert_one(doc)
    await audit(user=user, action="create", resource="cost_centers", record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.put("/cost-centers/{ccid}")
async def update_cost_center(ccid: str, payload: CostCenterUpdate, request: Request,
                             user: dict = Depends(require_permission("procurement_master", "write"))):
    existing = await db.cost_centers.find_one({"id": ccid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Cost center not found")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.cost_centers.update_one({"id": ccid}, {"$set": patch})
    row = await db.cost_centers.find_one({"id": ccid}, {"_id": 0})
    await audit(user=user, action="update", resource="cost_centers", record_id=ccid, after=patch, ip=_ip(request))
    return _strip(row)


@router.delete("/cost-centers/{ccid}")
async def delete_cost_center(ccid: str, request: Request,
                             user: dict = Depends(require_permission("procurement_master", "delete"))):
    res = await db.cost_centers.delete_one({"id": ccid})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Cost center not found")
    await audit(user=user, action="delete", resource="cost_centers", record_id=ccid, after={}, ip=_ip(request))
    return {"ok": True}


@router.post("/cost-centers/auto-provision/{project_id}")
async def auto_provision(project_id: str, request: Request,
                         user: dict = Depends(require_permission("procurement_master", "write"))):
    """Create a cost center for every active category that doesn't already have
    one for this project. Idempotent."""
    proj = await _resolve_project(project_id)
    cats = await db.pr_categories.find({"active": True}, {"_id": 0}).to_list(500)
    existing = {c["category_id"] async for c in db.cost_centers.find(
        {"project_id": project_id}, {"_id": 0, "category_id": 1})}
    created: List[Dict[str, Any]] = []
    for cat in cats:
        if cat["id"] in existing:
            continue
        doc = {
            "id": new_id(),
            "project_id": project_id,
            "project_code": proj.get("code"),
            "project_name": proj.get("name"),
            "category_id": cat["id"],
            "category_code": cat.get("code"),
            "category_name": cat.get("name"),
            "code": f"CC-{proj.get('code') or proj.get('id', '')[:6]}-{cat.get('code')}",
            "name": f"{proj.get('name')} · {cat.get('name')}",
            "budget": 0.0, "committed": 0.0, "actual": 0.0,
            "active": True,
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
            "created_via": "auto_provision",
        }
        await db.cost_centers.insert_one(doc)
        created.append(_strip(doc))
    await audit(user=user, action="auto_provision_cost_centers", resource="cost_centers",
                record_id=project_id, after={"created": len(created)}, ip=_ip(request))
    return {"created": len(created), "items": created}


# ────────────────────────────── PR-DROPDOWNS HELPER ───────────────────────────
@router.get("/pr-dropdowns")
async def pr_dropdowns(project_id: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    """One-shot helper used by the PR form. Returns departments, projects,
    sites (optionally filtered by selected project), categories, items grouped
    by category, and the cost centers for the project (if provided)."""
    # Iter 59 — Single source of truth: the canonical `departments` master.
    # Falls back to legacy dropdown_options + employee distinct so existing
    # installs don't get an empty list.
    dept_rows = await db.departments.find({}, {"_id": 0, "name": 1, "code": 1}).to_list(200)
    departments = sorted([d.get("name") or d.get("code") for d in dept_rows if d.get("name") or d.get("code")])
    if not departments:
        legacy = await db.dropdown_options.find({"category": "department", "active": True}, {"_id": 0}).to_list(200)
        departments = sorted([d.get("value") or d.get("label") for d in legacy if d.get("value") or d.get("label")])
    if not departments:
        emp_depts = await db.employees.distinct("department")
        departments = sorted([d for d in emp_depts if d])

    projects = await db.projects.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1, "client": 1}).sort([("code", 1)]).to_list(500)
    sites_q: Dict[str, Any] = {}
    if project_id:
        sites_q["$or"] = [{"project_id": project_id}]
    sites = await db.sites.find(sites_q, {"_id": 0, "id": 1, "code": 1, "name": 1, "project_id": 1, "project_code": 1}).sort([("code", 1)]).to_list(500)

    categories = await db.pr_categories.find({"active": True}, {"_id": 0}).sort([("name", 1)]).to_list(500)
    items_rows = await db.pr_items.find({"active": True}, {"_id": 0}).sort([("category_code", 1), ("name", 1)]).to_list(2000)
    items_by_category: Dict[str, List[Dict[str, Any]]] = {}
    for it in items_rows:
        items_by_category.setdefault(it.get("category_id") or "", []).append(it)

    cost_centers: List[Dict[str, Any]] = []
    if project_id:
        cost_centers = await db.cost_centers.find({"project_id": project_id, "active": True}, {"_id": 0}).to_list(500)

    return {
        "departments": departments,
        "projects": projects,
        "sites": sites,
        "categories": categories,
        "items_by_category": items_by_category,
        "cost_centers": cost_centers,
    }


# ──────────────────────────────────────── SEED HELPER ─────────────────────────
DEFAULT_CATEGORIES = [
    ("SCAFF", "Scaffolding Material", "Cuplock, tubular, accessories", 18, "7308"),
    ("PAINT", "Paints & Coatings", "Primers, finishes, thinners", 18, "3208"),
    ("CONSUM", "Consumables", "Brushes, rollers, abrasives", 18, "9603"),
    ("PPE", "PPE & Safety", "Helmets, harnesses, gloves, glasses", 18, "6506"),
    ("FAST", "Fasteners & Hardware", "Bolts, nuts, screws, anchors", 18, "7318"),
    ("INSUL", "Insulation Material", "Rock wool, glass wool, claddings", 18, "6806"),
    ("ROOF", "Roofing Material", "GI sheets, ridge, flashing", 18, "7210"),
    ("ROPE", "Rope Access Gear", "Ropes, descenders, ascenders, anchors", 18, "5607"),
    ("TOOL", "Tools & Tackles", "Power tools, hand tools, rigging gear", 18, "8205"),
    ("OFFICE", "Office & Stationery", "Printing, stationery, IT consumables", 18, "4820"),
]


async def seed_master_if_empty() -> int:
    n = await db.pr_categories.count_documents({})
    if n > 0:
        return 0
    docs = []
    for code, name, desc, gst, hsn in DEFAULT_CATEGORIES:
        docs.append({
            "id": new_id(),
            "code": code,
            "name": name,
            "description": desc,
            "gst_pct": gst,
            "default_hsn": hsn,
            "active": True,
            "created_at": now_iso(),
            "created_via": "seed",
        })
    if docs:
        await db.pr_categories.insert_many(docs)
    return len(docs)
