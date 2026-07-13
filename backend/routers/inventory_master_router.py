"""Store & Inventory Phase 1 — master data + dashboard + opening stock.

This router is purely additive — it does NOT duplicate any of the existing
Item Master / Stock Ledger / Inventory Transaction / GRN / Material Allocation /
Challan / Inventory Intel functionality. It adds the missing **master tables**
and **dashboard aggregation** that Phase 1 demands.

New collections introduced (all suffixed `inv_*`):
  · inv_categories       — item categories (with sub-category dropdown values)
  · inv_units            — UOM master with optional conversion factors
  · inv_stores           — physical warehouses / main stores / scrap yards
  · inv_site_stores      — project-linked site stores
  · inv_bins             — bin/shelf locations within a store
  · inv_settings         — singleton document holding module-level settings
  · inv_opening_stock    — opening-stock declarations (links to inventory & inventory_transactions)

Endpoints prefixed with `/inv/...`.
"""
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/inv", tags=["store-inventory-phase1"])


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


# ─────────────────────────────────────────────────────────────────────
# 1. Item Category Master
# ─────────────────────────────────────────────────────────────────────
class CategoryIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str
    sub_categories: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    active: bool = True


@router.get("/categories")
async def list_categories(user: dict = Depends(require_permission("inventory", "read"))):
    rows = await db.inv_categories.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return rows


@router.post("/categories")
async def create_category(payload: CategoryIn, request: Request,
                          user: dict = Depends(require_permission("inventory", "write"))):
    if await db.inv_categories.find_one({"code": payload.code.upper()}, {"_id": 0}):
        raise HTTPException(status_code=409, detail=f"Category code '{payload.code}' already exists")
    doc = payload.model_dump()
    doc["code"] = doc["code"].upper()
    doc["id"] = new_id()
    doc["created_by"] = user["id"]
    doc["created_at"] = now_iso()
    await db.inv_categories.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="inv_categories", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/categories/{cat_id}")
async def update_category(cat_id: str, payload: CategoryIn, request: Request,
                          user: dict = Depends(require_permission("inventory", "write"))):
    existing = await db.inv_categories.find_one({"id": cat_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Category not found")
    upd = payload.model_dump()
    upd["code"] = upd["code"].upper()
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]
    await db.inv_categories.update_one({"id": cat_id}, {"$set": upd})
    row = await db.inv_categories.find_one({"id": cat_id}, {"_id": 0})
    await audit(user=user, action="update", resource="inv_categories", record_id=cat_id, before=existing, after=row, ip=_ip(request))
    return row


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: str, request: Request,
                          user: dict = Depends(require_permission("inventory", "delete"))):
    existing = await db.inv_categories.find_one({"id": cat_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Category not found")
    used = await db.inventory.count_documents({"category_id": cat_id})
    if used:
        raise HTTPException(status_code=400, detail=f"Cannot delete — {used} items are using this category")
    await db.inv_categories.delete_one({"id": cat_id})
    await audit(user=user, action="delete", resource="inv_categories", record_id=cat_id, before=existing, ip=_ip(request))
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────
# 2. Unit Master (UOM)
# ─────────────────────────────────────────────────────────────────────
class UnitIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=15)
    name: str
    type: str = "count"          # count | length | weight | volume | area | time
    base_unit: Optional[str] = None  # if convertible (e.g. cm → m)
    conversion_factor: Optional[float] = None  # multiplier to base unit
    active: bool = True


@router.get("/units")
async def list_units(user: dict = Depends(require_permission("inventory", "read"))):
    return await db.inv_units.find({}, {"_id": 0}).sort("name", 1).to_list(200)


@router.post("/units")
async def create_unit(payload: UnitIn, request: Request,
                      user: dict = Depends(require_permission("inventory", "write"))):
    code = payload.code.upper()
    if await db.inv_units.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(status_code=409, detail=f"Unit '{code}' already exists")
    doc = payload.model_dump()
    doc["code"] = code
    doc["id"] = new_id()
    doc["created_by"] = user["id"]
    doc["created_at"] = now_iso()
    await db.inv_units.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="inv_units", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/units/{unit_id}")
async def update_unit(unit_id: str, payload: UnitIn, request: Request,
                      user: dict = Depends(require_permission("inventory", "write"))):
    existing = await db.inv_units.find_one({"id": unit_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Unit not found")
    upd = payload.model_dump()
    upd["code"] = upd["code"].upper()
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]
    await db.inv_units.update_one({"id": unit_id}, {"$set": upd})
    row = await db.inv_units.find_one({"id": unit_id}, {"_id": 0})
    await audit(user=user, action="update", resource="inv_units", record_id=unit_id, before=existing, after=row, ip=_ip(request))
    return row


@router.delete("/units/{unit_id}")
async def delete_unit(unit_id: str, request: Request,
                      user: dict = Depends(require_permission("inventory", "delete"))):
    existing = await db.inv_units.find_one({"id": unit_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Unit not found")
    await db.inv_units.delete_one({"id": unit_id})
    await audit(user=user, action="delete", resource="inv_units", record_id=unit_id, before=existing, ip=_ip(request))
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────
# 3. Store / Warehouse Master
# ─────────────────────────────────────────────────────────────────────
STORE_TYPES = ("main_store", "site_store", "project_store", "scrap_yard", "damaged_stock")


class StoreIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str
    type: str = "main_store"
    address: Optional[str] = None
    incharge_id: Optional[str] = None
    incharge_name: Optional[str] = None
    contact_phone: Optional[str] = None
    active: bool = True
    remarks: Optional[str] = None


@router.get("/stores")
async def list_stores(type: Optional[str] = None,
                       user: dict = Depends(require_permission("inventory", "read"))):
    q = {"type": type} if type else {}
    return await db.inv_stores.find(q, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/stores")
async def create_store(payload: StoreIn, request: Request,
                       user: dict = Depends(require_permission("inventory", "write"))):
    if payload.type not in STORE_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {STORE_TYPES}")
    code = payload.code.upper()
    if await db.inv_stores.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(status_code=409, detail=f"Store code '{code}' already exists")
    doc = payload.model_dump()
    doc["code"] = code
    doc["id"] = new_id()
    doc["created_by"] = user["id"]
    doc["created_at"] = now_iso()
    await db.inv_stores.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="inv_stores", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/stores/{store_id}")
async def update_store(store_id: str, payload: StoreIn, request: Request,
                       user: dict = Depends(require_permission("inventory", "write"))):
    if payload.type not in STORE_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {STORE_TYPES}")
    existing = await db.inv_stores.find_one({"id": store_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Store not found")
    upd = payload.model_dump()
    upd["code"] = upd["code"].upper()
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]
    await db.inv_stores.update_one({"id": store_id}, {"$set": upd})
    row = await db.inv_stores.find_one({"id": store_id}, {"_id": 0})
    await audit(user=user, action="update", resource="inv_stores", record_id=store_id, before=existing, after=row, ip=_ip(request))
    return row


@router.delete("/stores/{store_id}")
async def delete_store(store_id: str, request: Request,
                       user: dict = Depends(require_permission("inventory", "delete"))):
    existing = await db.inv_stores.find_one({"id": store_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Store not found")
    used = await db.inventory.count_documents({"store_id": store_id})
    if used:
        raise HTTPException(status_code=400, detail=f"Cannot delete — {used} items reference this store")
    await db.inv_stores.delete_one({"id": store_id})
    await audit(user=user, action="delete", resource="inv_stores", record_id=store_id, before=existing, ip=_ip(request))
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────
# 4. Site Store Master
# ─────────────────────────────────────────────────────────────────────
class SiteStoreIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=25)
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    client_name: Optional[str] = None
    site_location: str
    site_incharge_id: Optional[str] = None
    site_incharge_name: Optional[str] = None
    storekeeper_id: Optional[str] = None
    storekeeper_name: Optional[str] = None
    start_date: Optional[str] = None
    closing_date: Optional[str] = None
    active: bool = True
    remarks: Optional[str] = None


@router.get("/site-stores")
async def list_site_stores(project_id: Optional[str] = None,
                           user: dict = Depends(require_permission("inventory", "read"))):
    q = {"project_id": project_id} if project_id else {}
    return await db.inv_site_stores.find(q, {"_id": 0}).sort("code", 1).to_list(500)


@router.post("/site-stores")
async def create_site_store(payload: SiteStoreIn, request: Request,
                            user: dict = Depends(require_permission("inventory", "write"))):
    code = payload.code.upper()
    if await db.inv_site_stores.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(status_code=409, detail=f"Site store '{code}' already exists")
    doc = payload.model_dump()
    doc["code"] = code
    doc["id"] = new_id()
    doc["created_by"] = user["id"]
    doc["created_at"] = now_iso()
    await db.inv_site_stores.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="inv_site_stores", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/site-stores/{store_id}")
async def update_site_store(store_id: str, payload: SiteStoreIn, request: Request,
                            user: dict = Depends(require_permission("inventory", "write"))):
    existing = await db.inv_site_stores.find_one({"id": store_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Site store not found")
    upd = payload.model_dump()
    upd["code"] = upd["code"].upper()
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]
    await db.inv_site_stores.update_one({"id": store_id}, {"$set": upd})
    row = await db.inv_site_stores.find_one({"id": store_id}, {"_id": 0})
    await audit(user=user, action="update", resource="inv_site_stores", record_id=store_id, before=existing, after=row, ip=_ip(request))
    return row


@router.delete("/site-stores/{store_id}")
async def delete_site_store(store_id: str, request: Request,
                            user: dict = Depends(require_permission("inventory", "delete"))):
    existing = await db.inv_site_stores.find_one({"id": store_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Site store not found")
    await db.inv_site_stores.delete_one({"id": store_id})
    await audit(user=user, action="delete", resource="inv_site_stores", record_id=store_id, before=existing, ip=_ip(request))
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────
# 5. Bin / Shelf Location Master
# ─────────────────────────────────────────────────────────────────────
class BinIn(BaseModel):
    code: str
    store_id: str
    aisle: Optional[str] = None
    rack: Optional[str] = None
    shelf: Optional[str] = None
    description: Optional[str] = None
    active: bool = True


@router.get("/bins")
async def list_bins(store_id: Optional[str] = None,
                    user: dict = Depends(require_permission("inventory", "read"))):
    q = {"store_id": store_id} if store_id else {}
    return await db.inv_bins.find(q, {"_id": 0}).sort("code", 1).to_list(2000)


@router.post("/bins")
async def create_bin(payload: BinIn, request: Request,
                     user: dict = Depends(require_permission("inventory", "write"))):
    code = payload.code.upper()
    if not await db.inv_stores.find_one({"id": payload.store_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Store not found")
    if await db.inv_bins.find_one({"code": code, "store_id": payload.store_id}, {"_id": 0}):
        raise HTTPException(status_code=409, detail=f"Bin '{code}' already exists in this store")
    doc = payload.model_dump()
    doc["code"] = code
    doc["id"] = new_id()
    doc["created_by"] = user["id"]
    doc["created_at"] = now_iso()
    await db.inv_bins.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="inv_bins", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/bins/{bin_id}")
async def update_bin(bin_id: str, payload: BinIn, request: Request,
                     user: dict = Depends(require_permission("inventory", "write"))):
    existing = await db.inv_bins.find_one({"id": bin_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Bin not found")
    upd = payload.model_dump()
    upd["code"] = upd["code"].upper()
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]
    await db.inv_bins.update_one({"id": bin_id}, {"$set": upd})
    row = await db.inv_bins.find_one({"id": bin_id}, {"_id": 0})
    await audit(user=user, action="update", resource="inv_bins", record_id=bin_id, before=existing, after=row, ip=_ip(request))
    return row


@router.delete("/bins/{bin_id}")
async def delete_bin(bin_id: str, request: Request,
                     user: dict = Depends(require_permission("inventory", "delete"))):
    existing = await db.inv_bins.find_one({"id": bin_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Bin not found")
    await db.inv_bins.delete_one({"id": bin_id})
    await audit(user=user, action="delete", resource="inv_bins", record_id=bin_id, before=existing, ip=_ip(request))
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────
# 6. Inventory Settings (singleton)
# ─────────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "id": "singleton",
    "issue_threshold_default": 50,
    "opening_stock_approval_value": 100000,
    "default_category_id": None,
    "default_unit_id": None,
    "default_store_id": None,
    "block_negative_stock": True,
    "require_batch_on_receipt": False,
    "auto_create_bins_per_store": True,
    "ppe_inspection_days": 30,
    "tool_calibration_warning_days": 30,
    "low_stock_email_to": None,
}


@router.get("/settings")
async def get_settings(user: dict = Depends(require_permission("inventory", "read"))):
    row = await db.inv_settings.find_one({"id": "singleton"}, {"_id": 0})
    if not row:
        return DEFAULT_SETTINGS
    return {**DEFAULT_SETTINGS, **row}


@router.put("/settings")
async def update_settings(payload: dict, request: Request,
                          user: dict = Depends(require_permission("inventory", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager", "store_incharge"}:
        raise HTTPException(status_code=403, detail="Only Admin / Director / GM / Store Incharge can edit inventory settings")
    # Drop non-whitelisted keys
    safe = {k: payload[k] for k in payload if k in DEFAULT_SETTINGS and k != "id"}
    safe["updated_at"] = now_iso()
    safe["updated_by"] = user["id"]
    await db.inv_settings.update_one({"id": "singleton"}, {"$set": safe}, upsert=True)
    row = await db.inv_settings.find_one({"id": "singleton"}, {"_id": 0})
    await audit(user=user, action="update", resource="inv_settings", record_id="singleton", after=row, ip=_ip(request))
    return {**DEFAULT_SETTINGS, **row}


# ─────────────────────────────────────────────────────────────────────
# 7. Opening Stock workflow
# ─────────────────────────────────────────────────────────────────────
OS_STATUSES = ("draft", "pending_approval", "approved", "rejected", "cancelled")
OS_CONDITIONS = ("new", "good", "used", "damaged", "scrap")


class OpeningStockLine(BaseModel):
    item_id: str
    quantity: float
    rate: float
    condition: str = "new"
    batch: Optional[str] = None
    serial_no: Optional[str] = None
    bin_id: Optional[str] = None


class OpeningStockIn(BaseModel):
    date: str
    store_id: str
    remarks: Optional[str] = None
    lines: List[OpeningStockLine]


@router.get("/opening-stock")
async def list_opening_stock(status: Optional[str] = None, store_id: Optional[str] = None,
                              user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    if store_id:
        q["store_id"] = store_id
    return await db.inv_opening_stock.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/opening-stock")
async def create_opening_stock(payload: OpeningStockIn, request: Request,
                                user: dict = Depends(require_permission("inventory", "write"))):
    """Create an opening-stock declaration. If total_value > approval_threshold,
    status defaults to `pending_approval`, otherwise `approved` (auto-posts ledger).
    Validations:
      - quantity > 0, rate >= 0 per line
      - duplicate (date, store_id, item_id) flagged
      - store must exist
    """
    if not payload.lines:
        raise HTTPException(status_code=400, detail="At least one line is required")
    if not await db.inv_stores.find_one({"id": payload.store_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Store not found")
    for ln in payload.lines:
        if ln.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity must be > 0 (item {ln.item_id})")
        if ln.rate < 0:
            raise HTTPException(status_code=400, detail=f"Rate cannot be negative (item {ln.item_id})")
        if ln.condition not in OS_CONDITIONS:
            raise HTTPException(status_code=400, detail=f"condition must be one of {OS_CONDITIONS}")
        # Duplicate guard
        dup = await db.inv_opening_stock.find_one({
            "date": payload.date, "store_id": payload.store_id,
            "lines.item_id": ln.item_id,
            "status": {"$in": ["pending_approval", "approved"]},
        }, {"_id": 0, "os_number": 1})
        if dup:
            raise HTTPException(status_code=409,
                                detail=f"Duplicate opening stock detected for item {ln.item_id} on {payload.date} (existing: {dup.get('os_number')})")
        if not await db.inventory.find_one({"id": ln.item_id}, {"_id": 0}):
            raise HTTPException(status_code=404, detail=f"Item {ln.item_id} not found")

    total_value = sum(ln.quantity * ln.rate for ln in payload.lines)
    settings = await db.inv_settings.find_one({"id": "singleton"}, {"_id": 0}) or {}
    approval_threshold = float(settings.get("opening_stock_approval_value") or DEFAULT_SETTINGS["opening_stock_approval_value"])

    os_number = f"OS-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(await db.inv_opening_stock.count_documents({})).zfill(5)}"
    needs_approval = total_value >= approval_threshold
    doc = {
        "id": new_id(),
        "os_number": os_number,
        "date": payload.date,
        "store_id": payload.store_id,
        "remarks": payload.remarks,
        "lines": [ln.model_dump() for ln in payload.lines],
        "total_value": round(total_value, 2),
        "line_count": len(payload.lines),
        "status": "pending_approval" if needs_approval else "approved",
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }

    if not needs_approval:
        # Auto-post to inventory + ledger
        doc["approved_by"] = user["id"]
        doc["approved_by_name"] = user.get("name") or user.get("email")
        doc["approved_at"] = now_iso()
        await _post_opening_stock(doc, user)

    await db.inv_opening_stock.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="inv_opening_stock", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


async def _post_opening_stock(doc: dict, user: dict):
    """Atomically increment inventory and write ledger rows of type=opening."""
    for ln in doc["lines"]:
        await db.inventory.update_one(
            {"id": ln["item_id"]},
            {"$inc": {"quantity": ln["quantity"]},
             "$set": {"updated_at": now_iso(), "last_purchase_rate": ln["rate"]}},
        )
        item = await db.inventory.find_one({"id": ln["item_id"]}, {"_id": 0}) or {}
        await db.inventory_transactions.insert_one({
            "id": new_id(),
            "txn_type": "opening",
            "item_id": ln["item_id"],
            "item_name": item.get("name"),
            "quantity": ln["quantity"],
            "delta": ln["quantity"],
            "balance_after": float(item.get("quantity") or 0),
            "unit": item.get("unit") or item.get("uom"),
            "rate": ln["rate"],
            "store_id": doc["store_id"],
            "bin_id": ln.get("bin_id"),
            "batch": ln.get("batch"),
            "serial_no": ln.get("serial_no"),
            "condition": ln["condition"],
            "ref_type": "opening_stock",
            "ref_id": doc["id"],
            "ref_no": doc["os_number"],
            "note": doc.get("remarks") or f"Opening stock {doc['os_number']}",
            "status": "posted",
            "created_by": user["id"],
            "created_at": now_iso(),
        })


@router.post("/opening-stock/{os_id}/approve")
async def approve_opening_stock(os_id: str, request: Request,
                                 user: dict = Depends(require_permission("inventory", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager", "store_incharge", "accounts_executive"}:
        raise HTTPException(status_code=403, detail="Insufficient role to approve opening stock")
    os_doc = await db.inv_opening_stock.find_one({"id": os_id}, {"_id": 0})
    if not os_doc:
        raise HTTPException(status_code=404, detail="Opening stock not found")
    if os_doc.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Cannot approve — current status: {os_doc.get('status')}")
    if os_doc.get("created_by") == user["id"]:
        raise HTTPException(status_code=403, detail="Cannot approve your own opening-stock declaration")
    await _post_opening_stock(os_doc, user)
    await db.inv_opening_stock.update_one(
        {"id": os_id},
        {"$set": {
            "status": "approved",
            "approved_by": user["id"],
            "approved_by_name": user.get("name") or user.get("email"),
            "approved_at": now_iso(),
        }},
    )
    row = await db.inv_opening_stock.find_one({"id": os_id}, {"_id": 0})
    await audit(user=user, action="approve", resource="inv_opening_stock", record_id=os_id, after=row, ip=_ip(request))
    return row


@router.post("/opening-stock/{os_id}/reject")
async def reject_opening_stock(os_id: str, payload: dict, request: Request,
                                user: dict = Depends(require_permission("inventory", "write"))):
    os_doc = await db.inv_opening_stock.find_one({"id": os_id}, {"_id": 0})
    if not os_doc:
        raise HTTPException(status_code=404, detail="Opening stock not found")
    if os_doc.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Cannot reject — current status: {os_doc.get('status')}")
    await db.inv_opening_stock.update_one(
        {"id": os_id},
        {"$set": {
            "status": "rejected",
            "rejected_by": user["id"],
            "rejected_at": now_iso(),
            "reject_reason": payload.get("reason"),
        }},
    )
    row = await db.inv_opening_stock.find_one({"id": os_id}, {"_id": 0})
    await audit(user=user, action="reject", resource="inv_opening_stock", record_id=os_id, after=row, ip=_ip(request))
    return row


# ─────────────────────────────────────────────────────────────────────
# 8. Inventory Dashboard
# ─────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def inventory_dashboard(user: dict = Depends(require_permission("inventory", "read"))):
    """Real-time tiles for the Inventory Dashboard. All values come from MongoDB
    (no static mocks). Driven by the `inventory` and `inventory_transactions`
    collections plus the new master tables."""
    items = await db.inventory.find({}, {"_id": 0}).to_list(10000)

    total_items = len(items)
    total_value = 0.0
    low_stock = []
    reorder = []
    out_of_stock = []
    damaged_value = 0.0
    scrap_value = 0.0
    needs_inspection = []

    # Per-category aggregations for ITL service lines
    cat_values: dict = {}

    for it in items:
        qty = float(it.get("quantity") or 0)
        rate = float(it.get("rate") or it.get("average_rate") or it.get("last_purchase_rate") or 0)
        value = qty * rate
        total_value += value

        cat = (it.get("category") or "uncategorised").lower()
        cat_values[cat] = cat_values.get(cat, 0) + value

        min_s = float(it.get("min_stock") or 0)
        reorder_lvl = float(it.get("reorder_level") or 0)
        if qty == 0:
            out_of_stock.append({"id": it["id"], "name": it.get("name"), "code": it.get("code")})
        elif min_s > 0 and qty < min_s:
            low_stock.append({"id": it["id"], "name": it.get("name"), "code": it.get("code"),
                              "quantity": qty, "min_stock": min_s})
        if reorder_lvl > 0 and qty <= reorder_lvl:
            reorder.append({"id": it["id"], "name": it.get("name"), "code": it.get("code"),
                            "quantity": qty, "reorder_level": reorder_lvl})
        if it.get("condition") == "damaged":
            damaged_value += value
        if it.get("condition") == "scrap" or cat == "scrap_material":
            scrap_value += value
        if it.get("inspection_required") and not it.get("last_inspection_date"):
            needs_inspection.append({"id": it["id"], "name": it.get("name")})

    pending_approvals = await db.inv_opening_stock.count_documents({"status": "pending_approval"})
    stores_count = await db.inv_stores.count_documents({"active": True})
    site_stores_count = await db.inv_site_stores.count_documents({"active": True})

    # Recent transactions (last 10)
    recent_txns = await db.inventory_transactions.find(
        {}, {"_id": 0, "id": 1, "txn_no": 1, "txn_type": 1, "item_name": 1,
              "quantity": 1, "created_at": 1, "created_by_name": 1}
    ).sort("created_at", -1).to_list(10)

    # Top consumed items in last 90 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    top_pipeline = [
        {"$match": {"txn_type": {"$in": ["outward", "transfer_out"]}, "created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$item_id", "total_out": {"$sum": "$quantity"},
                    "name": {"$last": "$item_name"}}},
        {"$sort": {"total_out": -1}}, {"$limit": 10},
    ]
    top_consumed = await db.inventory_transactions.aggregate(top_pipeline).to_list(10)

    # Slow movers (items with stock but zero outward in last 90 days) — top 10 by value
    moved_ids = {r["_id"] for r in top_consumed if r.get("_id")}
    slow_movers = []
    for it in items:
        if it["id"] in moved_ids or float(it.get("quantity") or 0) == 0:
            continue
        v = float(it.get("quantity") or 0) * float(it.get("rate") or 0)
        slow_movers.append({"id": it["id"], "name": it.get("name"), "value": round(v, 2),
                            "quantity": it.get("quantity")})
    slow_movers.sort(key=lambda r: -r["value"])
    slow_movers = slow_movers[:10]

    def _cat_value(prefix: str) -> float:
        return round(sum(v for k, v in cat_values.items() if prefix in k), 2)

    return {
        "as_of": now_iso(),
        # 20 cards — all real DB values
        "total_stock_value": round(total_value, 2),
        "total_items": total_items,
        "low_stock_count": len(low_stock),
        "reorder_count": len(reorder),
        "out_of_stock_count": len(out_of_stock),
        "pending_approvals": pending_approvals,
        "stores_count": stores_count,
        "site_stores_count": site_stores_count,
        "scaffolding_value": _cat_value("scaffold"),
        "painting_value": _cat_value("paint"),
        "roof_sheeting_value": _cat_value("roof") + _cat_value("sheeting"),
        "rope_access_value": _cat_value("rope"),
        "ppe_value": _cat_value("ppe") + _cat_value("safety"),
        "tools_value": _cat_value("tool"),
        "damaged_value": round(damaged_value, 2),
        "scrap_value": round(scrap_value, 2),
        "recent_transactions": recent_txns,
        "top_consumed": top_consumed,
        "slow_movers": slow_movers,
        "items_needing_inspection": needs_inspection[:20],
        # Drill-down friendly lists
        "low_stock_items": low_stock[:50],
        "reorder_items": reorder[:50],
        "out_of_stock_items": out_of_stock[:50],
        "category_breakdown": [{"category": k, "value": round(v, 2)} for k, v in
                                sorted(cat_values.items(), key=lambda kv: -kv[1])],
    }


# ─────────────────────────────────────────────────────────────────────
# 9. Stock Balance & Audit-log convenience endpoints
# ─────────────────────────────────────────────────────────────────────
@router.get("/stock-balance")
async def stock_balance(store_id: Optional[str] = None,
                         category: Optional[str] = None,
                         only_in_stock: bool = False,
                         user: dict = Depends(require_permission("inventory", "read"))):
    """Tabular stock balance derived from the existing `inventory` collection.
    Adds in-transit / reserved / damaged / scrap aggregation per item by querying
    the `inventory_transactions` ledger so it stays in sync with movements."""
    q: dict = {}
    if store_id:
        q["store_id"] = store_id
    if category:
        q["category"] = category
    if only_in_stock:
        q["quantity"] = {"$gt": 0}

    items = await db.inventory.find(q, {"_id": 0}).sort("name", 1).to_list(5000)
    out = []
    for it in items:
        # In-transit: transfer_out without matching transfer_in for same ref
        in_transit = await db.inventory_transactions.count_documents({
            "item_id": it["id"], "txn_type": "transfer_out", "status": "posted",
        })
        recd_back = await db.inventory_transactions.count_documents({
            "item_id": it["id"], "txn_type": "transfer_in", "status": "posted",
        })
        # Latest movement
        last = await db.inventory_transactions.find_one(
            {"item_id": it["id"]}, {"_id": 0, "created_at": 1, "txn_type": 1},
            sort=[("created_at", -1)],
        )
        rate = float(it.get("rate") or it.get("average_rate") or it.get("last_purchase_rate") or 0)
        qty = float(it.get("quantity") or 0)
        out.append({
            "item_id": it["id"],
            "item_code": it.get("code") or it.get("item_code"),
            "item_name": it.get("name"),
            "category": it.get("category"),
            "store_id": it.get("store_id"),
            "store_name": it.get("location") or it.get("store_name"),
            "unit": it.get("unit") or it.get("uom"),
            "available_qty": qty,
            "in_transit_qty": max(0, in_transit - recd_back),
            "damaged_qty": float(it.get("damaged_qty") or 0),
            "scrap_qty": float(it.get("scrap_qty") or 0),
            "reserved_qty": float(it.get("reserved_qty") or 0),
            "average_rate": rate,
            "stock_value": round(qty * rate, 2),
            "last_txn_date": (last or {}).get("created_at"),
            "last_txn_type": (last or {}).get("txn_type"),
        })
    return {"count": len(out), "rows": out,
            "totals": {"stock_value": round(sum(r["stock_value"] for r in out), 2)}}


# ─────────────────────────────────────────────────────────────────────
# 10. Seed defaults — Indian Trade Links specifics
# ─────────────────────────────────────────────────────────────────────
ITL_CATEGORIES = [
    {"code": "SCAFFOLD",  "name": "Scaffolding Material",
     "sub_categories": ["Pipe", "Cuplock Vertical", "Cuplock Horizontal", "Base Jack", "U Jack",
                         "Joint Pin", "Walkway Plank", "Clamp", "Coupler", "Ladder"]},
    {"code": "PAINT",     "name": "Painting Material",
     "sub_categories": ["Paint", "Primer", "Thinner", "Brush", "Roller", "Sandpaper", "Grinding Wheel", "Cutting Disc"]},
    {"code": "ROOF",      "name": "Roof Sheeting Material",
     "sub_categories": ["Roof Sheet", "Screw", "Fastener", "Sealant", "Flashing", "Ridge Cap"]},
    {"code": "ROPE",      "name": "Rope Access Equipment",
     "sub_categories": ["Rope", "Harness", "Descender", "Ascender", "Helmet", "Carabiner", "Lifeline", "Anchor Sling"]},
    {"code": "TOOLS",     "name": "Tools and Tackles", "sub_categories": []},
    {"code": "PPE",       "name": "PPE and Safety Items",
     "sub_categories": ["Helmet", "Safety Shoes", "Gloves", "Safety Harness", "Goggles", "Reflective Jacket",
                         "Face Shield", "Ear Plug", "Fire Extinguisher", "First Aid Item"]},
    {"code": "CONSUM",    "name": "Consumables", "sub_categories": []},
    {"code": "MACHINE",   "name": "Machinery and Equipment", "sub_categories": []},
    {"code": "VEHICLE",   "name": "Vehicle/Logistics Items", "sub_categories": []},
    {"code": "OFFICE",    "name": "Office/Administrative Items", "sub_categories": []},
    {"code": "SCRAP",     "name": "Scrap Material", "sub_categories": []},
    {"code": "MISC",      "name": "Miscellaneous", "sub_categories": []},
]

ITL_UNITS = [
    {"code": "NOS",  "name": "Numbers",      "type": "count"},
    {"code": "PCS",  "name": "Pieces",       "type": "count"},
    {"code": "KG",   "name": "Kilogram",     "type": "weight"},
    {"code": "G",    "name": "Gram",         "type": "weight", "base_unit": "KG", "conversion_factor": 0.001},
    {"code": "MT",   "name": "Metric Tonne", "type": "weight", "base_unit": "KG", "conversion_factor": 1000},
    {"code": "M",    "name": "Meter",        "type": "length"},
    {"code": "CM",   "name": "Centimeter",   "type": "length", "base_unit": "M", "conversion_factor": 0.01},
    {"code": "FT",   "name": "Foot",         "type": "length", "base_unit": "M", "conversion_factor": 0.3048},
    {"code": "L",    "name": "Litre",        "type": "volume"},
    {"code": "ML",   "name": "Millilitre",   "type": "volume", "base_unit": "L", "conversion_factor": 0.001},
    {"code": "SQM",  "name": "Square Meter", "type": "area"},
    {"code": "SQFT", "name": "Square Foot",  "type": "area",   "base_unit": "SQM", "conversion_factor": 0.0929},
    {"code": "BAG",  "name": "Bag",          "type": "count"},
    {"code": "BOX",  "name": "Box",          "type": "count"},
    {"code": "ROLL", "name": "Roll",         "type": "count"},
    {"code": "SET",  "name": "Set",          "type": "count"},
    {"code": "PAIR", "name": "Pair",         "type": "count"},
]


@router.post("/seed-defaults")
async def seed_defaults(user: dict = Depends(require_permission("inventory", "write"))):
    """Idempotent: creates ITL-specific categories, UOMs and a default Main Store
    if they do not already exist. Safe to call multiple times."""
    if user.get("role") not in {"super_admin", "director", "general_manager", "store_incharge"}:
        raise HTTPException(status_code=403, detail="Only Admin / Director / GM / Store Incharge can seed defaults")
    cat_added = 0
    for c in ITL_CATEGORIES:
        if not await db.inv_categories.find_one({"code": c["code"]}, {"_id": 0}):
            await db.inv_categories.insert_one({
                **c, "id": new_id(), "active": True, "created_by": user["id"], "created_at": now_iso(),
            })
            cat_added += 1
    unit_added = 0
    for u in ITL_UNITS:
        if not await db.inv_units.find_one({"code": u["code"]}, {"_id": 0}):
            await db.inv_units.insert_one({
                **u, "id": new_id(), "active": True, "created_by": user["id"], "created_at": now_iso(),
            })
            unit_added += 1
    store_added = 0
    if not await db.inv_stores.find_one({"code": "MAIN"}, {"_id": 0}):
        await db.inv_stores.insert_one({
            "id": new_id(), "code": "MAIN", "name": "Main Store", "type": "main_store",
            "address": "HQ - Indian Trade Links", "active": True,
            "created_by": user["id"], "created_at": now_iso(),
        })
        store_added = 1
    settings_seeded = False
    if not await db.inv_settings.find_one({"id": "singleton"}, {"_id": 0}):
        await db.inv_settings.insert_one({**DEFAULT_SETTINGS, "created_at": now_iso(), "created_by": user["id"]})
        settings_seeded = True
    return {
        "categories_added": cat_added, "units_added": unit_added,
        "stores_added": store_added, "settings_seeded": settings_seeded,
        "total_categories": await db.inv_categories.count_documents({}),
        "total_units": await db.inv_units.count_documents({}),
        "total_stores": await db.inv_stores.count_documents({}),
    }
