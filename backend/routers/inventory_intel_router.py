"""Procurement Phase C — Inventory Intelligence.

Endpoints:
  * POST /api/inventory/import.csv      — bulk Excel/CSV import (template + validation)
  * GET  /api/inventory/import-template — download the CSV template
  * GET  /api/inventory/valuation       — FIFO/LIFO layered valuation walk
  * GET  /api/inventory/reports/aging   — material aging buckets
  * GET  /api/inventory/reports/dead-stock — never-issued items past N days
  * GET  /api/inventory/reports/movers  — fast/slow movers (consumption over window)
  * GET  /api/inventory/reports/idle    — items with zero consumption but > 0 stock
  * GET  /api/inventory/reorder-alerts  — items at/below reorder_level

Existing collections used:  inventory, inventory_transactions, grn
"""
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse

from core import db, require_permission, now_iso, new_id

router = APIRouter(tags=["procurement-phase-c"])

IMPORT_TEMPLATE_COLUMNS = [
    "item_code", "name", "category", "unit", "opening_quantity", "rate",
    "store_location", "batch", "serial_no", "vendor_name", "asset_tag",
    "reorder_level", "min_stock", "max_stock",
]


# ──────────────────────────────────────────────────────────────────────────────
# Bulk import + template
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/inventory-intel/import-template")
async def import_template(user: dict = Depends(require_permission("inventory", "read"))):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(IMPORT_TEMPLATE_COLUMNS)
    w.writerow(["BOLT-001", "M12 Hex Bolt", "Consumable", "Nos", 500, 8.5, "Main Store", "B-2026-A", "", "VendorX", "", 100, 50, 2000])
    w.writerow(["DRILL-PR-7", "Power Drill Pro 7", "Tool", "Nos", 5, 12500, "Tool Crib", "", "SN-DPR7-001", "ToolsCo", "AT-001", 2, 1, 10])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventory_template.csv"'},
    )


@router.post("/inventory-intel/import.csv")
async def import_inventory(file: UploadFile = File(...),
                           user: dict = Depends(require_permission("inventory", "write"))):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    missing = [c for c in ("name", "unit", "opening_quantity") if c not in reader.fieldnames]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {missing}")

    created, updated, errors = [], [], []
    for line_no, row in enumerate(reader, start=2):
        name = (row.get("name") or "").strip()
        if not name:
            errors.append({"row": line_no, "error": "name is empty"})
            continue
        try:
            qty = float(row.get("opening_quantity") or 0)
        except ValueError:
            errors.append({"row": line_no, "error": "opening_quantity must be a number"})
            continue
        try:
            rate = float(row.get("rate") or 0)
        except ValueError:
            errors.append({"row": line_no, "error": "rate must be a number"})
            continue
        code = (row.get("item_code") or "").strip() or None
        # Duplicate detection — match by item_code or name
        query: dict = {}
        if code:
            query = {"$or": [{"item_code": code}, {"code": code}, {"name": name}]}
        else:
            query = {"name": name}
        existing = await db.inventory.find_one(query, {"_id": 0})
        record_payload = {
            "name": name,
            "item_code": code,
            "code": code,
            "category": (row.get("category") or "").strip() or None,
            "unit": (row.get("unit") or "Nos").strip(),
            "rate": rate,
            "store_location": (row.get("store_location") or "").strip() or None,
            "batch": (row.get("batch") or "").strip() or None,
            "serial_no": (row.get("serial_no") or "").strip() or None,
            "vendor_name": (row.get("vendor_name") or "").strip() or None,
            "asset_tag": (row.get("asset_tag") or "").strip() or None,
            "reorder_level": _as_float(row.get("reorder_level")),
            "min_stock": _as_float(row.get("min_stock")),
            "max_stock": _as_float(row.get("max_stock")),
            "updated_at": now_iso(),
            "updated_by": user["id"],
        }
        if existing:
            # Adjust existing — additive on quantity
            await db.inventory.update_one(
                {"id": existing["id"]},
                {"$set": record_payload, "$inc": {"quantity": qty}},
            )
            updated.append({"row": line_no, "id": existing["id"], "name": name})
        else:
            doc = {**record_payload, "id": new_id(), "quantity": qty,
                   "created_at": now_iso(), "created_by": user["id"]}
            await db.inventory.insert_one(doc)
            created.append({"row": line_no, "id": doc["id"], "name": name})
        # Audit row in inventory_transactions
        if qty > 0:
            target_id = existing["id"] if existing else doc["id"]
            await db.inventory_transactions.insert_one({
                "id": new_id(),
                "txn_type": "opening",
                "item_id": target_id,
                "item_name": name,
                "quantity": qty,
                "unit": record_payload["unit"],
                "rate": rate,
                "note": f"Bulk import row {line_no}",
                "ref_type": "bulk_import",
                "status": "posted",
                "created_by": user["id"],
                "created_at": now_iso(),
            })
    return {"summary": {"created": len(created), "updated": len(updated), "errors": len(errors)},
            "created": created, "updated": updated, "errors": errors}


def _as_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# FIFO / LIFO valuation
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/inventory-intel/valuation")
async def inventory_valuation(method: str = "fifo",
                              user: dict = Depends(require_permission("inventory", "read"))):
    """Layered valuation walk using inventory_transactions ledger.
    method ∈ {fifo, lifo, weighted_avg}
    """
    if method not in ("fifo", "lifo", "weighted_avg"):
        raise HTTPException(status_code=400, detail="method must be fifo|lifo|weighted_avg")
    items = await db.inventory.find({}, {"_id": 0}).to_list(5000)
    rows = []
    grand_value = 0.0
    for item in items:
        # Inward layers — sort by created_at
        layers = await db.inventory_transactions.find(
            {"item_id": item["id"], "txn_type": {"$in": ["inward", "opening", "transfer_in"]}, "status": {"$ne": "voided"}},
            {"_id": 0, "quantity": 1, "rate": 1, "created_at": 1, "note": 1},
        ).sort("created_at", 1 if method == "fifo" else -1).to_list(1000)
        if not layers:
            # Fallback to item.rate × stock
            value = float(item.get("quantity") or 0) * float(item.get("rate") or 0)
            rows.append({"item_id": item["id"], "name": item.get("name"), "quantity": item.get("quantity"),
                         "unit": item.get("unit"), "method": method, "value": round(value, 2),
                         "layers": [], "weighted_rate": item.get("rate") or 0})
            grand_value += value
            continue
        # For weighted_avg — total_qty / total_value
        if method == "weighted_avg":
            total_qty = sum(float(la.get("quantity") or 0) for la in layers)
            total_value = sum(float(la.get("quantity") or 0) * float(la.get("rate") or 0) for la in layers)
            avg_rate = (total_value / total_qty) if total_qty else 0
            stock = float(item.get("quantity") or 0)
            value = stock * avg_rate
            rows.append({"item_id": item["id"], "name": item.get("name"), "quantity": stock,
                         "unit": item.get("unit"), "method": method, "value": round(value, 2),
                         "weighted_rate": round(avg_rate, 2), "layers": []})
            grand_value += value
            continue
        # FIFO / LIFO walk — consume `current stock` from oldest|newest layer first
        remaining = float(item.get("quantity") or 0)
        used_layers = []
        value = 0.0
        for layer in layers:
            if remaining <= 0:
                break
            take = min(remaining, float(layer.get("quantity") or 0))
            rate = float(layer.get("rate") or 0)
            value += take * rate
            used_layers.append({"qty": take, "rate": rate, "received_at": (layer.get("created_at") or "")[:10],
                                "note": layer.get("note")})
            remaining -= take
        rows.append({"item_id": item["id"], "name": item.get("name"), "quantity": float(item.get("quantity") or 0),
                     "unit": item.get("unit"), "method": method, "value": round(value, 2),
                     "weighted_rate": round(value / float(item.get("quantity") or 1), 2) if item.get("quantity") else 0,
                     "layers": used_layers})
        grand_value += value
    return {"method": method, "total_value": round(grand_value, 2), "items": sorted(rows, key=lambda r: -r["value"])}


# ──────────────────────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/inventory-intel/reports/aging")
async def aging_report(user: dict = Depends(require_permission("inventory", "read"))):
    """Bucket items by oldest-stock age (last inward date)."""
    today = datetime.now(timezone.utc)
    items = await db.inventory.find({"quantity": {"$gt": 0}}, {"_id": 0}).to_list(5000)
    buckets = {"0-30d": [], "30-90d": [], "90-180d": [], "180-365d": [], ">365d": [], "never_inward": []}
    for item in items:
        last = await db.inventory_transactions.find_one(
            {"item_id": item["id"], "txn_type": {"$in": ["inward", "opening"]}},
            {"_id": 0, "created_at": 1}, sort=[("created_at", -1)],
        )
        if not last:
            buckets["never_inward"].append(_aging_row(item, None))
            continue
        try:
            d = datetime.fromisoformat(str(last["created_at"]).replace("Z", "+00:00"))
            age_days = (today - d).days
        except Exception:
            age_days = None
        if age_days is None:
            buckets["never_inward"].append(_aging_row(item, None))
        elif age_days <= 30:
            buckets["0-30d"].append(_aging_row(item, age_days))
        elif age_days <= 90:
            buckets["30-90d"].append(_aging_row(item, age_days))
        elif age_days <= 180:
            buckets["90-180d"].append(_aging_row(item, age_days))
        elif age_days <= 365:
            buckets["180-365d"].append(_aging_row(item, age_days))
        else:
            buckets[">365d"].append(_aging_row(item, age_days))
    return {"as_of": now_iso()[:10], "buckets": buckets,
            "summary": {k: len(v) for k, v in buckets.items()}}


def _aging_row(item, age):
    return {
        "id": item["id"], "name": item.get("name"), "code": item.get("item_code") or item.get("code"),
        "quantity": item.get("quantity"), "unit": item.get("unit"),
        "value": round(float(item.get("quantity") or 0) * float(item.get("rate") or 0), 2),
        "age_days": age,
    }


@router.get("/inventory-intel/reports/dead-stock")
async def dead_stock(days: int = 180, user: dict = Depends(require_permission("inventory", "read"))):
    """Items with stock > 0 but no outward activity in the last N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    items = await db.inventory.find({"quantity": {"$gt": 0}}, {"_id": 0}).to_list(5000)
    rows = []
    for item in items:
        recent = await db.inventory_transactions.find_one(
            {"item_id": item["id"], "txn_type": {"$in": ["outward", "transfer_out"]}, "created_at": {"$gte": cutoff}},
            {"_id": 0},
        )
        if not recent:
            rows.append({
                "id": item["id"], "name": item.get("name"), "code": item.get("item_code") or item.get("code"),
                "quantity": item.get("quantity"), "unit": item.get("unit"),
                "rate": item.get("rate"),
                "value": round(float(item.get("quantity") or 0) * float(item.get("rate") or 0), 2),
            })
    rows.sort(key=lambda r: -r["value"])
    total_value = sum(r["value"] for r in rows)
    return {"days_threshold": days, "as_of": now_iso()[:10],
            "count": len(rows), "total_value": round(total_value, 2), "items": rows}


@router.get("/inventory-intel/reports/movers")
async def movers(days: int = 90, top: int = 20,
                 user: dict = Depends(require_permission("inventory", "read"))):
    """Fast/slow movers based on cumulative outward over `days` window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"txn_type": {"$in": ["outward", "transfer_out"]}, "created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$item_id", "total_out": {"$sum": "$quantity"},
                    "txn_count": {"$sum": 1}, "name": {"$last": "$item_name"}, "unit": {"$last": "$unit"}}},
        {"$sort": {"total_out": -1}},
    ]
    rows = await db.inventory_transactions.aggregate(pipeline).to_list(5000)
    fast = []
    slow = []
    for r in rows:
        if not r.get("_id"):
            continue
        item = await db.inventory.find_one({"id": r["_id"]}, {"_id": 0, "quantity": 1, "rate": 1, "reorder_level": 1})
        fast.append({
            "item_id": r["_id"], "name": r.get("name"),
            "total_out": r["total_out"], "unit": r.get("unit"), "txn_count": r["txn_count"],
            "on_hand": (item or {}).get("quantity"), "reorder_level": (item or {}).get("reorder_level"),
        })
    # Items that are in inventory but had ZERO outward in the window are SLOW.
    inv_with_stock = await db.inventory.find({"quantity": {"$gt": 0}}, {"_id": 0}).to_list(5000)
    moved_ids = {r["_id"] for r in rows if r.get("_id")}
    for item in inv_with_stock:
        if item["id"] in moved_ids:
            continue
        slow.append({"item_id": item["id"], "name": item.get("name"), "total_out": 0,
                     "unit": item.get("unit"), "on_hand": item.get("quantity"),
                     "value": round(float(item.get("quantity") or 0) * float(item.get("rate") or 0), 2)})
    slow.sort(key=lambda r: -r["value"])
    return {"days_window": days, "fast_movers": fast[:top], "slow_movers": slow[:top]}


@router.get("/inventory-intel/reports/idle")
async def idle_inventory(days: int = 90, user: dict = Depends(require_permission("inventory", "read"))):
    """Items that have NOT moved (no inward OR outward) in the last N days but have stock."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    items = await db.inventory.find({"quantity": {"$gt": 0}}, {"_id": 0}).to_list(5000)
    rows = []
    for item in items:
        any_recent = await db.inventory_transactions.find_one(
            {"item_id": item["id"], "created_at": {"$gte": cutoff}}, {"_id": 0},
        )
        if not any_recent:
            rows.append({
                "id": item["id"], "name": item.get("name"),
                "quantity": item.get("quantity"), "unit": item.get("unit"),
                "value": round(float(item.get("quantity") or 0) * float(item.get("rate") or 0), 2),
            })
    rows.sort(key=lambda r: -r["value"])
    return {"days_window": days, "as_of": now_iso()[:10],
            "count": len(rows), "items": rows}


@router.get("/inventory-intel/reorder-alerts")
async def reorder_alerts(user: dict = Depends(require_permission("inventory", "read"))):
    """Items at or below their reorder_level."""
    items = await db.inventory.find(
        {"reorder_level": {"$gt": 0}}, {"_id": 0},
    ).to_list(5000)
    rows = []
    for item in items:
        rl = float(item.get("reorder_level") or 0)
        qty = float(item.get("quantity") or 0)
        if qty <= rl:
            rows.append({
                "id": item["id"], "name": item.get("name"),
                "code": item.get("item_code") or item.get("code"),
                "quantity": qty, "reorder_level": rl, "min_stock": item.get("min_stock"),
                "unit": item.get("unit"), "vendor_name": item.get("vendor_name"),
                "severity": "critical" if qty == 0 else ("high" if qty < rl * 0.5 else "warning"),
            })
    rows.sort(key=lambda r: (r["severity"] != "critical", r["severity"] != "high", -((r["reorder_level"] - r["quantity"]) / (r["reorder_level"] or 1))))
    return {"count": len(rows), "as_of": now_iso()[:10], "items": rows}
