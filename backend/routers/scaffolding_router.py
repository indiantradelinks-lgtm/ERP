"""Scaffolding Stock & Challan Center.

Location-wise scaffolding inventory (stores + running project sites) with
approval-gated inter-company movements and delivery challans.

Flow: Transfer request (from → to, item lines) → Store Manager approval →
one or more Delivery Challans (each = one vehicle trip) → dispatch deducts
source stock (in-transit) → Receive at destination lands stock there.
Supports single vehicle/single challan and multiple deliveries/challans
against one approved transfer.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from exports import to_excel, to_pdf
from pdf_generator import _wrap, _render, _esc

router = APIRouter(tags=["scaffolding"])
logger = logging.getLogger("erp")

APPROVE_ROLES = {"super_admin", "store_manager", "inventory_manager", "dept_head",
                 "general_manager", "director"}


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


# ─── Locations = stores + active projects ────────────────────────────────
async def _locations() -> List[Dict[str, Any]]:
    locs = []
    for s in await db.inv_stores.find({"active": {"$ne": False}}, {"_id": 0}).to_list(500):
        locs.append({"id": s["id"], "name": s["name"], "code": s.get("code"), "type": "store"})
    for p in await db.projects.find({"status": {"$nin": ["closed", "completed", "cancelled"]}},
                                    {"_id": 0, "id": 1, "code": 1, "name": 1}).to_list(500):
        locs.append({"id": p["id"], "name": f"{p.get('code')} · {p.get('name')}"[:80], "code": p.get("code"), "type": "project"})
    return locs


@router.get("/scaffolding/locations")
async def locations(user: dict = Depends(require_permission("scaffolding", "read"))):
    return await _locations()


async def _adjust(item: dict, location: dict, delta: float) -> float:
    row = await db.scaf_stock.find_one({"item_id": item["id"], "location_id": location["id"]}, {"_id": 0})
    new_qty = round(float((row or {}).get("quantity") or 0) + delta, 3)
    if row:
        await db.scaf_stock.update_one({"id": row["id"]}, {"$set": {"quantity": new_qty, "updated_at": now_iso()}})
    else:
        await db.scaf_stock.insert_one({
            "id": new_id(), "item_id": item["id"], "item_code": item.get("code"),
            "item_name": item.get("name"), "unit": item.get("unit") or item.get("uom") or "Nos",
            "size": item.get("size"), "spec": item.get("spec"),
            "location_id": location["id"], "location_name": location["name"], "location_type": location["type"],
            "quantity": new_qty, "updated_at": now_iso()})
    return new_qty


async def _loc(location_id: str) -> Optional[Dict[str, Any]]:
    return next((l for l in await _locations() if l["id"] == location_id), None)


async def _company() -> Dict[str, Any]:
    return await db.settings.find_one({"_id": "company"}) or await db.settings.find_one({"id": "company"}) or {}


async def _location_details(location_id: str) -> Dict[str, Any]:
    comp = await _company()
    base = {"company": comp.get("name") or "INDIAN TRADE LINKS", "gstin": comp.get("gstin") or "",
            "address": ", ".join(x for x in [comp.get("address"), comp.get("city"), comp.get("state"), comp.get("pincode")] if x)}
    store = await db.inv_stores.find_one({"id": location_id}, {"_id": 0})
    if store:
        return {**base, "id": location_id, "name": store["name"], "type": "store",
                "address": store.get("address") or base["address"]}
    proj = await db.projects.find_one({"id": location_id}, {"_id": 0})
    if proj:
        return {**base, "id": location_id, "name": f"{proj.get('code')} · {proj.get('name')}", "type": "project",
                "address": proj.get("site") or base["address"], "client": proj.get("client")}
    return {**base, "id": location_id, "name": "", "type": "unknown"}


@router.get("/scaffolding/location-details/{location_id}")
async def location_details(location_id: str,
                           user: dict = Depends(require_permission("scaffolding", "read"))):
    return await _location_details(location_id)


# ─── Items & stock ───────────────────────────────────────────────────────
class ItemIn(BaseModel):
    name: str
    code: Optional[str] = None
    size: Optional[str] = None
    spec: Optional[str] = None
    unit: str = "Nos"
    rate: float = 0
    min_stock: float = 0
    unit_weight_kg: float = 0


@router.post("/scaffolding/items")
async def create_item(p: ItemIn, request: Request,
                      user: dict = Depends(require_permission("scaffolding", "write"))):
    code = (p.code or "").strip().upper() or f"SCF-{(await next_sequence('SCF'))[-4:]}"
    if await db.inventory.find_one({"code": code}, {"_id": 0, "id": 1}):
        raise HTTPException(409, f"Item code {code} already exists")
    doc = {"id": new_id(), "code": code, "name": p.name.strip(), "size": p.size, "spec": p.spec,
           "unit": p.unit, "uom": p.unit, "quantity": 0, "category": "scaffolding",
           "rate": p.rate, "min_stock": p.min_stock, "unit_weight_kg": p.unit_weight_kg,
           "created_at": now_iso(), "created_by": user.get("id")}
    await db.inventory.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="scaffolding_items", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/scaffolding/items")
async def list_items(q: Optional[str] = None,
                     user: dict = Depends(require_permission("scaffolding", "read"))):
    query: Dict[str, Any] = {}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"code": {"$regex": q, "$options": "i"}}]
    return await db.inventory.find(query, {"_id": 0}).sort("name", 1).to_list(2000)


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    size: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    rate: Optional[float] = None
    min_stock: Optional[float] = None
    unit_weight_kg: Optional[float] = None


@router.put("/scaffolding/items/{item_id}")
async def update_item(item_id: str, p: ItemUpdate, request: Request,
                      user: dict = Depends(require_permission("scaffolding", "write"))):
    item = await db.inventory.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item not found")
    patch: Dict[str, Any] = {k: v for k, v in p.model_dump().items() if v is not None}
    if "code" in patch:
        patch["code"] = patch["code"].strip().upper()
        dup = await db.inventory.find_one({"code": patch["code"], "id": {"$ne": item_id}}, {"_id": 0, "id": 1})
        if dup:
            raise HTTPException(409, f"Item code {patch['code']} already exists")
    if "name" in patch:
        patch["name"] = patch["name"].strip()
    if "unit" in patch:
        patch["uom"] = patch["unit"]
    if not patch:
        return item
    patch["updated_at"] = now_iso()
    await db.inventory.update_one({"id": item_id}, {"$set": patch})
    # keep denormalised scaf_stock rows in sync
    stock_patch = {k: patch[k] for k in ("name", "code", "unit", "size", "spec") if k in patch}
    if stock_patch:
        mapped = {}
        if "name" in stock_patch: mapped["item_name"] = stock_patch["name"]
        if "code" in stock_patch: mapped["item_code"] = stock_patch["code"]
        if "unit" in stock_patch: mapped["unit"] = stock_patch["unit"]
        if "size" in stock_patch: mapped["size"] = stock_patch["size"]
        if "spec" in stock_patch: mapped["spec"] = stock_patch["spec"]
        await db.scaf_stock.update_many({"item_id": item_id}, {"$set": mapped})
    await audit(user=user, action="update", resource="scaffolding_items", record_id=item_id,
                before=item, after=patch, ip=_ip(request))
    return await db.inventory.find_one({"id": item_id}, {"_id": 0})


@router.delete("/scaffolding/items/{item_id}")
async def delete_item(item_id: str, request: Request,
                      user: dict = Depends(require_permission("scaffolding", "write"))):
    item = await db.inventory.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item not found")
    stock = await db.scaf_stock.find_one({"item_id": item_id, "quantity": {"$gt": 0}}, {"_id": 0, "id": 1})
    if stock:
        raise HTTPException(400, "Cannot delete — item has stock at one or more locations")
    open_tr = await db.scaf_transfers.find_one(
        {"lines.item_id": item_id, "status": {"$in": ["pending_approval", "approved", "partially_dispatched", "dispatched", "partially_received"]}},
        {"_id": 0, "transfer_no": 1})
    if open_tr:
        raise HTTPException(400, f"Cannot delete — item is on open transfer {open_tr['transfer_no']}")
    await db.inventory.delete_one({"id": item_id})
    await db.scaf_stock.delete_many({"item_id": item_id})
    await audit(user=user, action="delete", resource="scaffolding_items", record_id=item_id, before=item, ip=_ip(request))
    return {"deleted": True}


@router.get("/scaffolding/stock")
async def stock(location_id: Optional[str] = None, q: Optional[str] = None,
                user: dict = Depends(require_permission("scaffolding", "read"))):
    query: Dict[str, Any] = {}
    if location_id:
        query["location_id"] = location_id
    if q:
        query["$or"] = [{"item_name": {"$regex": q, "$options": "i"}}, {"item_code": {"$regex": q, "$options": "i"}}]
    return await db.scaf_stock.find(query, {"_id": 0}).sort("item_name", 1).to_list(5000)


@router.get("/scaffolding/stock-matrix")
async def stock_matrix(location_id: Optional[str] = None, q: Optional[str] = None,
                       user: dict = Depends(require_permission("scaffolding", "read"))):
    rows = await db.scaf_stock.find({}, {"_id": 0}).to_list(10000)
    locs = await _locations()
    weights = {i["id"]: float(i.get("unit_weight_kg") or 0)
               async for i in db.inventory.find({}, {"_id": 0, "id": 1, "unit_weight_kg": 1})}
    used_ids = {r["location_id"] for r in rows}
    cols = [l for l in locs if l["id"] in used_ids]
    if location_id:
        rows = [r for r in rows if r["location_id"] == location_id]
        cols = [c for c in cols if c["id"] == location_id]
    if q:
        rx = re.compile(re.escape(q), re.I)
        rows = [r for r in rows if rx.search(r.get("item_name") or "") or rx.search(r.get("item_code") or "")]
    items: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        it = items.setdefault(r["item_id"], {"item_id": r["item_id"], "item_code": r.get("item_code"),
                                             "item_name": r["item_name"], "unit": r.get("unit"),
                                             "size": r.get("size"), "spec": r.get("spec"),
                                             "unit_weight_kg": weights.get(r["item_id"], 0),
                                             "by_location": {}, "total": 0})
        it["by_location"][r["location_id"]] = r["quantity"]
        it["total"] = round(it["total"] + float(r["quantity"] or 0), 3)
    in_transit = await db.scaf_challans.aggregate([
        {"$match": {"status": "dispatched"}}, {"$unwind": "$lines"},
        {"$group": {"_id": "$lines.item_id", "qty": {"$sum": "$lines.quantity"}}}]).to_list(1000)
    transit_map = {t["_id"]: t["qty"] for t in in_transit}
    out = sorted(items.values(), key=lambda x: x["item_name"] or "")
    total_weight = 0.0
    for it in out:
        it["in_transit"] = transit_map.get(it["item_id"], 0)
        it["total_weight_kg"] = round(it["total"] * it["unit_weight_kg"], 2)
        it["total_tonnage"] = round(it["total_weight_kg"] / 1000, 3)
        total_weight += it["total_weight_kg"]
    return {"locations": cols, "items": out,
            "grand_total_qty": round(sum(i["total"] for i in out), 3),
            "grand_total_weight_kg": round(total_weight, 2),
            "grand_total_tonnage": round(total_weight / 1000, 3)}


class OpeningIn(BaseModel):
    item_id: str
    location_id: str
    quantity: float


@router.post("/scaffolding/opening-stock")
async def opening_stock(p: OpeningIn, request: Request,
                        user: dict = Depends(require_permission("scaffolding", "write"))):
    item = await db.inventory.find_one({"id": p.item_id}, {"_id": 0})
    loc = await _loc(p.location_id)
    if not item or not loc:
        raise HTTPException(400, "Invalid item or location")
    row = await db.scaf_stock.find_one({"item_id": p.item_id, "location_id": p.location_id}, {"_id": 0})
    delta = p.quantity - float((row or {}).get("quantity") or 0)
    new_qty = await _adjust(item, loc, delta)
    await audit(user=user, action="opening_stock", resource="scaf_stock", record_id=p.item_id,
                after={"location": loc["name"], "quantity": p.quantity}, ip=_ip(request))
    return {"item": item["name"], "location": loc["name"], "quantity": new_qty}


@router.post("/scaffolding/migrate-main-store")
async def migrate_main_store(request: Request,
                             user: dict = Depends(require_permission("scaffolding", "write"))):
    """One-time: seed each catalog item's current global quantity into Main Store."""
    if user.get("role") not in APPROVE_ROLES:
        raise HTTPException(403, "Store Manager / management only")
    main = await db.inv_stores.find_one({"code": "MAIN"}, {"_id": 0}) or await db.inv_stores.find_one({}, {"_id": 0})
    if not main:
        raise HTTPException(400, "No store found — create the Main Store first")
    loc = {"id": main["id"], "name": main["name"], "type": "store"}
    migrated = skipped = 0
    async for item in db.inventory.find({}, {"_id": 0}):
        if await db.scaf_stock.find_one({"item_id": item["id"]}, {"_id": 0, "id": 1}):
            skipped += 1; continue
        qty = float(item.get("quantity") or 0)
        if qty <= 0:
            skipped += 1; continue
        await _adjust(item, loc, qty)
        migrated += 1
    await audit(user=user, action="migrate_main_store", resource="scaf_stock", record_id=main["id"],
                after={"migrated": migrated, "skipped": skipped}, ip=_ip(request))
    return {"migrated": migrated, "skipped": skipped, "store": main["name"]}


# ─── Transfers (approval before dispatch) ────────────────────────────────
class TLine(BaseModel):
    item_id: str
    quantity: float


class TransferIn(BaseModel):
    from_location_id: str
    to_location_id: str
    lines: List[TLine]
    need_by: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/scaffolding/transfers")
async def create_transfer(p: TransferIn, request: Request,
                          user: dict = Depends(require_permission("scaffolding", "write"))):
    if p.from_location_id == p.to_location_id:
        raise HTTPException(400, "From and To locations must differ")
    src, dst = await _loc(p.from_location_id), await _loc(p.to_location_id)
    if not src or not dst:
        raise HTTPException(400, "Invalid location(s)")
    if not p.lines:
        raise HTTPException(400, "Add at least one item line")
    lines = []
    for l in p.lines:
        if l.quantity <= 0:
            raise HTTPException(400, "Quantities must be positive")
        item = await db.inventory.find_one({"id": l.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(400, f"Unknown item {l.item_id}")
        srow = await db.scaf_stock.find_one({"item_id": l.item_id, "location_id": src["id"]}, {"_id": 0, "quantity": 1})
        on_hand = float((srow or {}).get("quantity") or 0)
        if l.quantity > on_hand:
            raise HTTPException(400, f"Insufficient stock of {item['name']} at {src['name']} (have {on_hand}, need {l.quantity})")
        lines.append({"item_id": item["id"], "item_code": item.get("code"), "item_name": item["name"],
                      "unit": item.get("unit") or item.get("uom") or "Nos", "size": item.get("size"),
                      "quantity": l.quantity, "dispatched": 0, "received": 0})
    doc = {"id": new_id(), "transfer_no": await next_sequence("MTN"),
           "from_location_id": src["id"], "from_location": src["name"], "from_type": src["type"],
           "to_location_id": dst["id"], "to_location": dst["name"], "to_type": dst["type"],
           "lines": lines, "need_by": p.need_by, "remarks": p.remarks,
           "status": "pending_approval", "challan_count": 0,
           "created_at": now_iso(), "created_by": user.get("name") or user.get("email")}
    await db.scaf_transfers.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="scaf_transfers", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/scaffolding/transfers")
async def list_transfers(status: Optional[str] = None, location_id: Optional[str] = None,
                         user: dict = Depends(require_permission("scaffolding", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if location_id:
        q["$or"] = [{"from_location_id": location_id}, {"to_location_id": location_id}]
    return await db.scaf_transfers.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


class ActionIn(BaseModel):
    remarks: Optional[str] = None


@router.post("/scaffolding/transfers/{tid}/approve")
async def approve_transfer(tid: str, p: ActionIn, request: Request,
                           user: dict = Depends(require_permission("scaffolding", "write"))):
    if user.get("role") not in APPROVE_ROLES:
        raise HTTPException(403, "Only the Store Manager / management can approve dispatches")
    row = await db.scaf_transfers.find_one({"id": tid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] != "pending_approval":
        raise HTTPException(400, f"Cannot approve in status {row['status']}")
    await db.scaf_transfers.update_one({"id": tid}, {"$set": {
        "status": "approved", "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(), "approve_remarks": p.remarks}})
    await audit(user=user, action="approve", resource="scaf_transfers", record_id=tid, ip=_ip(request))
    return await db.scaf_transfers.find_one({"id": tid}, {"_id": 0})


@router.post("/scaffolding/transfers/{tid}/reject")
async def reject_transfer(tid: str, p: ActionIn, request: Request,
                          user: dict = Depends(require_permission("scaffolding", "write"))):
    if user.get("role") not in APPROVE_ROLES:
        raise HTTPException(403, "Only the Store Manager / management can reject")
    row = await db.scaf_transfers.find_one({"id": tid}, {"_id": 0, "status": 1})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] != "pending_approval":
        raise HTTPException(400, f"Cannot reject in status {row['status']}")
    await db.scaf_transfers.update_one({"id": tid}, {"$set": {
        "status": "rejected", "rejected_reason": p.remarks, "rejected_by": user.get("name") or user.get("email")}})
    return await db.scaf_transfers.find_one({"id": tid}, {"_id": 0})


# ─── Challans (one or many per approved transfer) ────────────────────────
class CLine(BaseModel):
    item_id: str
    quantity: float
    unit_rate: Optional[float] = None


class ChallanIn(BaseModel):
    vehicle_no: str
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    transporter: Optional[str] = None
    eway_bill_no: Optional[str] = None
    customer_wo_no: Optional[str] = None
    purpose: str = "returnable_service"   # returnable_service | sale
    origin_address: Optional[str] = None
    origin_gstin: Optional[str] = None
    destination_address: Optional[str] = None
    destination_gstin: Optional[str] = None
    lines: List[CLine]
    remarks: Optional[str] = None


@router.post("/scaffolding/transfers/{tid}/challans")
async def create_challan(tid: str, p: ChallanIn, request: Request,
                         user: dict = Depends(require_permission("scaffolding", "write"))):
    """Create + dispatch a challan in one step: deducts source stock (in-transit)."""
    tr = await db.scaf_transfers.find_one({"id": tid}, {"_id": 0})
    if not tr:
        raise HTTPException(404, "Transfer not found")
    if tr["status"] not in ("approved", "partially_dispatched", "partially_received"):
        raise HTTPException(400, f"Transfer must be approved first (status: {tr['status']})")
    if not p.lines:
        raise HTTPException(400, "Add at least one item line")
    src = await _loc(tr["from_location_id"])
    tmap = {l["item_id"]: l for l in tr["lines"]}
    ch_lines = []
    for l in p.lines:
        tl = tmap.get(l.item_id)
        if not tl:
            raise HTTPException(400, "Item not part of the approved transfer")
        remaining = float(tl["quantity"]) - float(tl.get("dispatched") or 0)
        if l.quantity <= 0 or l.quantity > remaining:
            raise HTTPException(400, f"{tl['item_name']}: challan qty {l.quantity} exceeds remaining approved {remaining}")
        item = await db.inventory.find_one({"id": l.item_id}, {"_id": 0})
        srow = await db.scaf_stock.find_one({"item_id": l.item_id, "location_id": src["id"]}, {"_id": 0, "quantity": 1})
        if l.quantity > float((srow or {}).get("quantity") or 0):
            raise HTTPException(400, f"Insufficient stock of {tl['item_name']} at {src['name']}")
        unit_wt = float(item.get("unit_weight_kg") or 0)
        unit_rate = float(l.unit_rate if l.unit_rate is not None else (item.get("rate") or 0))
        ch_lines.append({"item_id": l.item_id, "item_code": item.get("code"), "item_name": item["name"],
                         "unit": item.get("unit") or item.get("uom") or "Nos", "quantity": l.quantity,
                         "unit_weight_kg": unit_wt, "line_weight_kg": round(l.quantity * unit_wt, 2),
                         "unit_rate": unit_rate, "line_value": round(l.quantity * unit_rate, 2)})
    # deduct source stock
    for l in ch_lines:
        item = await db.inventory.find_one({"id": l["item_id"]}, {"_id": 0})
        await _adjust(item, src, -l["quantity"])
        tmap[l["item_id"]]["dispatched"] = round(float(tmap[l["item_id"]].get("dispatched") or 0) + l["quantity"], 3)
    origin = await _location_details(tr["from_location_id"])
    dest = await _location_details(tr["to_location_id"])
    ch = {"id": new_id(), "challan_no": await next_sequence("DC"),
          "transfer_id": tid, "transfer_no": tr["transfer_no"],
          "from_location_id": tr["from_location_id"], "from_location": tr["from_location"],
          "to_location_id": tr["to_location_id"], "to_location": tr["to_location"],
          "origin_address": p.origin_address or origin.get("address"),
          "origin_gstin": p.origin_gstin or origin.get("gstin"),
          "destination_address": p.destination_address or dest.get("address"),
          "destination_gstin": p.destination_gstin or dest.get("gstin"),
          "customer_wo_no": p.customer_wo_no,
          "purpose": p.purpose if p.purpose in ("sale", "returnable_service") else "returnable_service",
          "vehicle_no": p.vehicle_no, "driver_name": p.driver_name, "driver_phone": p.driver_phone,
          "transporter": p.transporter, "eway_bill_no": p.eway_bill_no,
          "lines": ch_lines, "remarks": p.remarks, "status": "dispatched",
          "total_qty": round(sum(l["quantity"] for l in ch_lines), 3),
          "total_weight_kg": round(sum(l["line_weight_kg"] for l in ch_lines), 2),
          "total_value": round(sum(l["line_value"] for l in ch_lines), 2),
          "in_challan_no": None,
          "dispatched_at": now_iso(), "dispatched_by": user.get("name") or user.get("email"),
          "received_at": None, "received_by": None, "receiver_name": None,
          "created_at": now_iso()}
    await db.scaf_challans.insert_one(ch); ch.pop("_id", None)
    all_dispatched = all(float(l.get("dispatched") or 0) >= float(l["quantity"]) for l in tr["lines"])
    await db.scaf_transfers.update_one({"id": tid}, {"$set": {
        "lines": tr["lines"], "challan_count": int(tr.get("challan_count") or 0) + 1,
        "status": "dispatched" if all_dispatched else "partially_dispatched"}})
    await audit(user=user, action="dispatch", resource="scaf_challans", record_id=ch["id"], after=ch, ip=_ip(request))
    return ch


@router.get("/scaffolding/challans")
async def list_challans(status: Optional[str] = None, transfer_id: Optional[str] = None,
                        location_id: Optional[str] = None,
                        user: dict = Depends(require_permission("scaffolding", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if transfer_id:
        q["transfer_id"] = transfer_id
    if location_id:
        q["$or"] = [{"from_location_id": location_id}, {"to_location_id": location_id}]
    return await db.scaf_challans.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


class ReceiveIn(BaseModel):
    receiver_name: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/scaffolding/challans/{cid}/receive")
async def receive_challan(cid: str, p: ReceiveIn, request: Request,
                          user: dict = Depends(require_permission("scaffolding", "write"))):
    ch = await db.scaf_challans.find_one({"id": cid}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Not found")
    if ch["status"] != "dispatched":
        raise HTTPException(400, f"Challan is {ch['status']}")
    dst = await _loc(ch["to_location_id"])
    if not dst:
        raise HTTPException(400, "Destination location no longer exists")
    for l in ch["lines"]:
        item = await db.inventory.find_one({"id": l["item_id"]}, {"_id": 0})
        await _adjust(item, dst, float(l["quantity"]))
    in_no = await next_sequence("IC")
    await db.scaf_challans.update_one({"id": cid}, {"$set": {
        "status": "received", "received_at": now_iso(), "in_challan_no": in_no,
        "received_by": user.get("name") or user.get("email"),
        "receiver_name": p.receiver_name, "received_remarks": p.remarks}})
    tr = await db.scaf_transfers.find_one({"id": ch["transfer_id"]}, {"_id": 0})
    if tr:
        for l in ch["lines"]:
            tl = next((x for x in tr["lines"] if x["item_id"] == l["item_id"]), None)
            if tl:
                tl["received"] = round(float(tl.get("received") or 0) + float(l["quantity"]), 3)
        all_recv = all(float(l.get("received") or 0) >= float(l["quantity"]) for l in tr["lines"])
        await db.scaf_transfers.update_one({"id": tr["id"]}, {"$set": {
            "lines": tr["lines"], "status": "completed" if all_recv else "partially_received"}})
    await audit(user=user, action="receive", resource="scaf_challans", record_id=cid, ip=_ip(request))
    return await db.scaf_challans.find_one({"id": cid}, {"_id": 0})


@router.get("/scaffolding/location-statement")
async def location_statement(location_id: str,
                             user: dict = Depends(require_permission("scaffolding", "read"))):
    """Per-item material summary at a location, derived from challans (In/Out) + live stock."""
    loc = await _loc(location_id)
    if not loc:
        raise HTTPException(400, "Invalid location")
    items: Dict[str, Dict[str, Any]] = {}

    def bucket(l: dict) -> Dict[str, Any]:
        return items.setdefault(l["item_id"], {
            "item_id": l["item_id"], "item_code": l.get("item_code"), "item_name": l["item_name"],
            "unit": l.get("unit"), "unit_weight_kg": float(l.get("unit_weight_kg") or 0),
            "in_qty": 0, "out_qty": 0, "in_challans": 0, "out_challans": 0, "current_stock": 0})

    async for ch in db.scaf_challans.find(
            {"$or": [{"from_location_id": location_id}, {"to_location_id": location_id}]}, {"_id": 0}):
        is_out = ch["from_location_id"] == location_id
        is_in = ch["to_location_id"] == location_id and ch["status"] == "received"
        for l in ch["lines"]:
            b = bucket(l)
            if is_out:
                b["out_qty"] = round(b["out_qty"] + float(l["quantity"]), 3)
                b["out_challans"] += 1
            if is_in:
                b["in_qty"] = round(b["in_qty"] + float(l["quantity"]), 3)
                b["in_challans"] += 1
    async for s in db.scaf_stock.find({"location_id": location_id}, {"_id": 0}):
        b = bucket({"item_id": s["item_id"], "item_code": s.get("item_code"), "item_name": s["item_name"],
                    "unit": s.get("unit"), "unit_weight_kg": 0})
        b["current_stock"] = float(s.get("quantity") or 0)
    weights = {i["id"]: float(i.get("unit_weight_kg") or 0)
               async for i in db.inventory.find({"id": {"$in": list(items.keys())}}, {"_id": 0, "id": 1, "unit_weight_kg": 1})}
    out = sorted(items.values(), key=lambda x: x["item_name"] or "")
    for b in out:
        b["unit_weight_kg"] = weights.get(b["item_id"], b["unit_weight_kg"])
        b["stock_weight_kg"] = round(b["current_stock"] * b["unit_weight_kg"], 2)
    return {"location": loc, "items": out,
            "totals": {"in_qty": round(sum(b["in_qty"] for b in out), 3),
                       "out_qty": round(sum(b["out_qty"] for b in out), 3),
                       "current_stock": round(sum(b["current_stock"] for b in out), 3),
                       "stock_weight_kg": round(sum(b["stock_weight_kg"] for b in out), 2)}}


@router.get("/scaffolding/item-ledger")
async def item_ledger(item_id: str, location_id: Optional[str] = None,
                      user: dict = Depends(require_permission("scaffolding", "read"))):
    """Challan-wise In / Out movement history for one item (component)."""
    item = await db.inventory.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item not found")
    q: Dict[str, Any] = {"lines.item_id": item_id}
    if location_id:
        q["$or"] = [{"from_location_id": location_id}, {"to_location_id": location_id}]
    rows = []
    async for ch in db.scaf_challans.find(q, {"_id": 0}).sort("dispatched_at", -1):
        line = next((l for l in ch["lines"] if l["item_id"] == item_id), None)
        if not line:
            continue
        direction = None
        if location_id:
            direction = "out" if ch["from_location_id"] == location_id else ("in" if ch["status"] == "received" else "in_transit")
        rows.append({
            "date": (ch.get("dispatched_at") or "")[:10], "challan_no": ch["challan_no"],
            "in_challan_no": ch.get("in_challan_no"), "transfer_no": ch.get("transfer_no"),
            "from_location": ch["from_location"], "to_location": ch["to_location"],
            "quantity": line["quantity"], "unit": line.get("unit"), "status": ch["status"],
            "direction": direction, "vehicle_no": ch.get("vehicle_no"),
            "received_at": (ch.get("received_at") or "")[:10] or None})
    total_moved = round(sum(float(r["quantity"]) for r in rows), 3)
    return {"item": {"id": item["id"], "code": item.get("code"), "name": item["name"],
                     "unit": item.get("unit") or item.get("uom")},
            "rows": rows, "total_moved": total_moved}


@router.get("/scaffolding/challans/{cid}/pdf")
async def challan_pdf(cid: str, user: dict = Depends(require_permission("scaffolding", "read"))):
    ch = await db.scaf_challans.find_one({"id": cid}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Not found")
    comp = await _company()
    purpose_txt = ("FOR SALE" if ch.get("purpose") == "sale"
                   else "NOT FOR SALE — Issued to render services, on returnable basis")
    inr = lambda v: f"₹ {float(v or 0):,.2f}"
    rows = "".join(
        f"<tr><td>{i+1}</td><td>{_esc(l['item_name'])}</td><td>{_esc(l.get('item_code'))}</td>"
        f"<td style='text-align:right'>{l['quantity']}</td><td>{_esc(l.get('unit'))}</td>"
        f"<td style='text-align:right'>{l.get('unit_weight_kg') or '—'}</td>"
        f"<td style='text-align:right'>{l.get('line_weight_kg') or '—'}</td>"
        f"<td style='text-align:right'>{inr(l.get('unit_rate'))}</td>"
        f"<td style='text-align:right'>{inr(l.get('line_value'))}</td></tr>"
        for i, l in enumerate(ch["lines"]))
    totals_row = (f"<tr style='font-weight:bold;background:#f1f5f9'><td colspan='3'>TOTAL</td>"
                  f"<td style='text-align:right'>{ch.get('total_qty') or sum(l['quantity'] for l in ch['lines'])}</td><td></td><td></td>"
                  f"<td style='text-align:right'>{ch.get('total_weight_kg') or '—'} kg</td><td></td>"
                  f"<td style='text-align:right'>{inr(ch.get('total_value'))}</td></tr>")

    def copy_html(label: str, last: bool) -> str:
        return f"""
    <div style="{'page-break-after:always;' if not last else ''}">
    <table class="kv"><tr>
      <td colspan="2" style="text-align:center;font-weight:bold;background:#f1f5f9">
        DELIVERY CHALLAN — {_esc(ch['challan_no'])} &nbsp;·&nbsp; <span style="color:#1d4ed8">{label}</span></td></tr><tr>
      <td style="width:50%;vertical-align:top"><b>CONSIGNOR (Origin)</b><br/>
        {_esc(comp.get('name') or 'INDIAN TRADE LINKS')} — {_esc(ch['from_location'])}<br/>
        {_esc(ch.get('origin_address') or '—')}<br/>
        <b>GSTIN:</b> {_esc(ch.get('origin_gstin') or '—')}</td>
      <td style="width:50%;vertical-align:top"><b>CONSIGNEE (Destination)</b><br/>
        {_esc(comp.get('name') or 'INDIAN TRADE LINKS')} — {_esc(ch['to_location'])}<br/>
        {_esc(ch.get('destination_address') or '—')}<br/>
        <b>GSTIN:</b> {_esc(ch.get('destination_gstin') or '—')}</td>
    </tr></table>
    <table class="kv"><tr>
      <td><b>Out Challan No:</b> {_esc(ch['challan_no'])}</td>
      <td><b>In Challan No:</b> {_esc(ch.get('in_challan_no') or '—')}</td>
      <td><b>Date:</b> {_esc((ch.get('dispatched_at') or '')[:10])}</td>
      <td><b>Against Transfer:</b> {_esc(ch['transfer_no'])}</td></tr><tr>
      <td><b>Vehicle:</b> {_esc(ch.get('vehicle_no'))}</td>
      <td><b>Driver:</b> {_esc(ch.get('driver_name') or '—')} {_esc(ch.get('driver_phone') or '')}</td>
      <td><b>Transporter:</b> {_esc(ch.get('transporter') or '—')}</td>
      <td><b>E-Way Bill:</b> {_esc(ch.get('eway_bill_no') or '—')}</td></tr><tr>
      <td colspan="2"><b>Customer Work Order:</b> {_esc(ch.get('customer_wo_no') or 'N/A')}</td>
      <td colspan="2"><b>Purpose:</b> {_esc(purpose_txt)}</td>
    </tr></table>
    <table><thead><tr><th>#</th><th>Material Description</th><th>Code</th><th>Qty</th><th>Unit</th>
      <th>Unit Wt (kg)</th><th>Total Wt (kg)</th><th>Unit Price</th><th>Value</th></tr></thead>
    <tbody>{rows}{totals_row}</tbody></table>
    <p style="font-size:10px"><b>Remarks:</b> {_esc(ch.get('remarks') or '—')} ·
      <b>Declaration:</b> {_esc(purpose_txt)}. Value declared for transit/insurance purposes only{'' if ch.get('purpose') == 'sale' else ' — no supply/sale is involved'}.</p>
    <br/>
    <table class="kv"><tr>
      <td style="text-align:center">______________________<br/>Dispatched By<br/>{_esc(ch.get('dispatched_by'))}</td>
      <td style="text-align:center">______________________<br/>Driver Signature</td>
      <td style="text-align:center">______________________<br/>Received By<br/>{_esc(ch.get('receiver_name') or '')}</td>
    </tr></table>
    <p style="font-size:9px;color:#666">Status: {_esc(ch['status'].upper())} · This is a material movement challan{'' if ch.get('purpose') == 'sale' else ', not a tax invoice'}.</p>
    </div>"""

    copies = ["ORIGINAL FOR CONSIGNEE", "DUPLICATE FOR TRANSPORTER", "TRIPLICATE FOR CONSIGNOR"]
    body = "".join(copy_html(label, i == len(copies) - 1) for i, label in enumerate(copies))
    pdf = _render(_wrap(f"DELIVERY CHALLAN — {ch['challan_no']}", body))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{ch["challan_no"]}.pdf"'})


@router.get("/scaffolding/summary")
async def scaf_summary(user: dict = Depends(require_permission("scaffolding", "read"))):
    stock_rows = await db.scaf_stock.find({}, {"_id": 0, "quantity": 1, "location_id": 1, "item_id": 1}).to_list(10000)
    return {
        "items_tracked": len({r["item_id"] for r in stock_rows}),
        "locations": len({r["location_id"] for r in stock_rows}),
        "total_qty": round(sum(float(r["quantity"] or 0) for r in stock_rows), 1),
        "pending_approvals": await db.scaf_transfers.count_documents({"status": "pending_approval"}),
        "in_transit_challans": await db.scaf_challans.count_documents({"status": "dispatched"}),
        "open_transfers": await db.scaf_transfers.count_documents({"status": {"$in": ["approved", "partially_dispatched", "dispatched", "partially_received"]}}),
    }


TEMPLATE_HEADERS = ["code", "name", "size", "spec", "unit", "rate", "min_stock",
                    "unit_weight_kg", "location", "opening_quantity"]


@router.get("/scaffolding/import-template")
async def import_template(user: dict = Depends(require_permission("scaffolding", "read"))):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEADERS)
    w.writerow(["SCF-0101", "Vertical Standard 3m", "3.0m", "48.3mm OD", "Nos", "450", "50", "17.1", "Main Store", "100"])
    w.writerow(["SCF-0102", "Ledger 2m", "2.0m", "", "Nos", "300", "50", "9.8", "", ""])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="scaffolding_import_template.csv"'})


@router.post("/scaffolding/import.csv")
async def import_csv(request: Request, file: UploadFile = File(...),
                     user: dict = Depends(require_permission("scaffolding", "write"))):
    """Bulk create/update items (incl. unit weights) with optional opening stock per location."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    if "name" not in headers and "code" not in headers:
        raise HTTPException(400, f"CSV must contain at least a 'name' or 'code' column. Expected: {', '.join(TEMPLATE_HEADERS)}")
    locs = await _locations()

    def find_loc(v: str):
        v = (v or "").strip().lower()
        if not v:
            return None
        return next((l for l in locs if (l.get("code") or "").lower() == v
                     or l["name"].lower() == v or v in l["name"].lower()), None)

    created = updated = stocked = 0
    errors: List[dict] = []
    for i, r in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        name, code = row.get("name") or "", (row.get("code") or "").upper()
        if not name and not code:
            continue
        try:
            oq = row.get("opening_quantity")
            loc = None
            if oq:
                loc = find_loc(row.get("location"))
                if not loc:
                    raise ValueError(f"unknown location '{row.get('location')}'")
            item = await db.inventory.find_one({"code": code}, {"_id": 0}) if code else None
            if not item and name:
                item = await db.inventory.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0})
            patch: Dict[str, Any] = {}
            for f, cast in (("size", str), ("spec", str), ("unit", str),
                            ("rate", float), ("min_stock", float), ("unit_weight_kg", float)):
                v = row.get(f)
                if v:
                    patch[f] = cast(v)
            if "unit" in patch:
                patch["uom"] = patch["unit"]
            if item:
                if name:
                    patch["name"] = name
                if patch:
                    patch["updated_at"] = now_iso()
                    await db.inventory.update_one({"id": item["id"]}, {"$set": patch})
                    sync = {}
                    if "name" in patch: sync["item_name"] = patch["name"]
                    if "unit" in patch: sync["unit"] = patch["unit"]
                    if "size" in patch: sync["size"] = patch["size"]
                    if sync:
                        await db.scaf_stock.update_many({"item_id": item["id"]}, {"$set": sync})
                    item = {**item, **patch}
                updated += 1
            else:
                if not name:
                    raise ValueError("name required for a new item")
                new_code = code or f"SCF-{(await next_sequence('SCF'))[-4:]}"
                item = {"id": new_id(), "code": new_code, "name": name, "quantity": 0,
                        "category": "scaffolding", "unit": patch.get("unit") or "Nos",
                        "uom": patch.get("unit") or "Nos", "size": patch.get("size"),
                        "spec": patch.get("spec"), "rate": patch.get("rate") or 0,
                        "min_stock": patch.get("min_stock") or 0,
                        "unit_weight_kg": patch.get("unit_weight_kg") or 0,
                        "created_at": now_iso(), "created_by": user.get("id")}
                await db.inventory.insert_one(dict(item))
                created += 1
            if oq:
                srow = await db.scaf_stock.find_one({"item_id": item["id"], "location_id": loc["id"]}, {"_id": 0})
                delta = float(oq) - float((srow or {}).get("quantity") or 0)
                await _adjust(item, loc, delta)
                stocked += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)})
    await audit(user=user, action="bulk_import", resource="scaffolding_items", record_id="csv",
                after={"created": created, "updated": updated, "opening_stock_set": stocked, "errors": len(errors)},
                ip=_ip(request))
    return {"created": created, "updated": updated, "opening_stock_set": stocked, "errors": errors}


@router.get("/scaffolding/export.{fmt}")
async def export_stock(fmt: str, kind: str = "stock", location_id: Optional[str] = None,
                       q: Optional[str] = None, item_ids: Optional[str] = None,
                       user: dict = Depends(require_permission("scaffolding", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "Format must be xlsx or pdf")
    if kind == "challans":
        rows = await db.scaf_challans.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
        for r in rows:
            r["items_summary"] = "; ".join(f"{l['item_name']} x{l['quantity']}" for l in r.get("lines") or [])
        res = "scaf_challans"
    else:
        query: Dict[str, Any] = {}
        if location_id:
            query["location_id"] = location_id
        if item_ids:
            query["item_id"] = {"$in": [x for x in item_ids.split(",") if x]}
        if q:
            query["$or"] = [{"item_name": {"$regex": q, "$options": "i"}}, {"item_code": {"$regex": q, "$options": "i"}}]
        rows = await db.scaf_stock.find(query, {"_id": 0}).sort([("location_name", 1), ("item_name", 1)]).to_list(10000)
        weights = {i["id"]: float(i.get("unit_weight_kg") or 0)
                   async for i in db.inventory.find({}, {"_id": 0, "id": 1, "unit_weight_kg": 1})}
        for r in rows:
            w = weights.get(r["item_id"], 0)
            r["unit_weight_kg"] = w
            r["weight_kg"] = round(float(r.get("quantity") or 0) * w, 2)
            r["tonnage_mt"] = round(r["weight_kg"] / 1000, 3)
        res = "scaf_stock"
    data = to_excel(res, rows) if fmt == "xlsx" else to_pdf(res, rows)
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt == "xlsx" else "application/pdf")
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="scaffolding_{kind}.{fmt}"'})
