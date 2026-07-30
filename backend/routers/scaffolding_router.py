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

import io
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
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


# ─── Items & stock ───────────────────────────────────────────────────────
class ItemIn(BaseModel):
    name: str
    code: Optional[str] = None
    size: Optional[str] = None
    spec: Optional[str] = None
    unit: str = "Nos"
    rate: float = 0
    min_stock: float = 0


@router.post("/scaffolding/items")
async def create_item(p: ItemIn, request: Request,
                      user: dict = Depends(require_permission("scaffolding", "write"))):
    code = (p.code or "").strip().upper() or f"SCF-{(await next_sequence('SCF'))[-4:]}"
    if await db.inventory.find_one({"code": code}, {"_id": 0, "id": 1}):
        raise HTTPException(409, f"Item code {code} already exists")
    doc = {"id": new_id(), "code": code, "name": p.name.strip(), "size": p.size, "spec": p.spec,
           "unit": p.unit, "uom": p.unit, "quantity": 0, "category": "scaffolding",
           "rate": p.rate, "min_stock": p.min_stock, "created_at": now_iso(), "created_by": user.get("id")}
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
async def stock_matrix(user: dict = Depends(require_permission("scaffolding", "read"))):
    rows = await db.scaf_stock.find({}, {"_id": 0}).to_list(10000)
    locs = await _locations()
    used_ids = {r["location_id"] for r in rows}
    cols = [l for l in locs if l["id"] in used_ids]
    items: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        it = items.setdefault(r["item_id"], {"item_id": r["item_id"], "item_code": r.get("item_code"),
                                             "item_name": r["item_name"], "unit": r.get("unit"),
                                             "size": r.get("size"), "spec": r.get("spec"),
                                             "by_location": {}, "total": 0})
        it["by_location"][r["location_id"]] = r["quantity"]
        it["total"] = round(it["total"] + float(r["quantity"] or 0), 3)
    in_transit = await db.scaf_challans.aggregate([
        {"$match": {"status": "dispatched"}}, {"$unwind": "$lines"},
        {"$group": {"_id": "$lines.item_id", "qty": {"$sum": "$lines.quantity"}}}]).to_list(1000)
    transit_map = {t["_id"]: t["qty"] for t in in_transit}
    out = sorted(items.values(), key=lambda x: x["item_name"] or "")
    for it in out:
        it["in_transit"] = transit_map.get(it["item_id"], 0)
    return {"locations": cols, "items": out}


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
class ChallanIn(BaseModel):
    vehicle_no: str
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    transporter: Optional[str] = None
    eway_bill_no: Optional[str] = None
    lines: List[TLine]
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
        ch_lines.append({"item_id": l.item_id, "item_code": item.get("code"), "item_name": item["name"],
                         "unit": item.get("unit") or item.get("uom") or "Nos", "quantity": l.quantity})
    # deduct source stock
    for l in ch_lines:
        item = await db.inventory.find_one({"id": l["item_id"]}, {"_id": 0})
        await _adjust(item, src, -l["quantity"])
        tmap[l["item_id"]]["dispatched"] = round(float(tmap[l["item_id"]].get("dispatched") or 0) + l["quantity"], 3)
    ch = {"id": new_id(), "challan_no": await next_sequence("DC"),
          "transfer_id": tid, "transfer_no": tr["transfer_no"],
          "from_location_id": tr["from_location_id"], "from_location": tr["from_location"],
          "to_location_id": tr["to_location_id"], "to_location": tr["to_location"],
          "vehicle_no": p.vehicle_no, "driver_name": p.driver_name, "driver_phone": p.driver_phone,
          "transporter": p.transporter, "eway_bill_no": p.eway_bill_no,
          "lines": ch_lines, "remarks": p.remarks, "status": "dispatched",
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
    await db.scaf_challans.update_one({"id": cid}, {"$set": {
        "status": "received", "received_at": now_iso(),
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


@router.get("/scaffolding/challans/{cid}/pdf")
async def challan_pdf(cid: str, user: dict = Depends(require_permission("scaffolding", "read"))):
    ch = await db.scaf_challans.find_one({"id": cid}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Not found")
    rows = "".join(
        f"<tr><td>{i+1}</td><td>{_esc(l['item_name'])}</td><td>{_esc(l.get('item_code'))}</td>"
        f"<td style='text-align:right'>{l['quantity']}</td><td>{_esc(l.get('unit'))}</td></tr>"
        for i, l in enumerate(ch["lines"]))
    body = f"""
    <table class="kv"><tr>
      <td><b>Challan No:</b> {_esc(ch['challan_no'])}</td><td><b>Date:</b> {_esc((ch.get('dispatched_at') or '')[:10])}</td>
      <td><b>Against Transfer:</b> {_esc(ch['transfer_no'])}</td></tr><tr>
      <td><b>From:</b> {_esc(ch['from_location'])}</td><td colspan="2"><b>To:</b> {_esc(ch['to_location'])}</td></tr><tr>
      <td><b>Vehicle:</b> {_esc(ch.get('vehicle_no'))}</td><td><b>Driver:</b> {_esc(ch.get('driver_name'))} {_esc(ch.get('driver_phone') or '')}</td>
      <td><b>Transporter:</b> {_esc(ch.get('transporter') or '—')} {('· E-Way: ' + _esc(ch['eway_bill_no'])) if ch.get('eway_bill_no') else ''}</td>
    </tr></table>
    <table><thead><tr><th>#</th><th>Material Description</th><th>Code</th><th>Qty</th><th>Unit</th></tr></thead>
    <tbody>{rows}</tbody></table>
    <p><b>Remarks:</b> {_esc(ch.get('remarks') or '—')}</p>
    <br/><br/>
    <table class="kv"><tr>
      <td style="text-align:center">______________________<br/>Dispatched By<br/>{_esc(ch.get('dispatched_by'))}</td>
      <td style="text-align:center">______________________<br/>Driver Signature</td>
      <td style="text-align:center">______________________<br/>Received By<br/>{_esc(ch.get('receiver_name') or '')}</td>
    </tr></table>
    <p style="font-size:9px;color:#666">Status: {_esc(ch['status'].upper())} · This is a material movement challan, not an invoice.</p>
    """
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


@router.get("/scaffolding/export.{fmt}")
async def export_stock(fmt: str, kind: str = "stock",
                       user: dict = Depends(require_permission("scaffolding", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "Format must be xlsx or pdf")
    if kind == "challans":
        rows = await db.scaf_challans.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
        for r in rows:
            r["items_summary"] = "; ".join(f"{l['item_name']} x{l['quantity']}" for l in r.get("lines") or [])
        res = "scaf_challans"
    else:
        rows = await db.scaf_stock.find({}, {"_id": 0}).sort([("location_name", 1), ("item_name", 1)]).to_list(10000)
        res = "scaf_stock"
    data = to_excel(res, rows) if fmt == "xlsx" else to_pdf(res, rows)
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt == "xlsx" else "application/pdf")
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="scaffolding_{kind}.{fmt}"'})
