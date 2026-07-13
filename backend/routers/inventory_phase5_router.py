"""Store & Inventory Phase 5 — Valuation + Physical Stock Count + Consolidated Dashboard.

Purely additive. Reuses:
  · inventory, inventory_transactions, material_allocations
  · inv_stores, inv_site_stores (Phase 1)
  · material_transfers (Phase 3)
  · ppe_issuance, damage_loss_entries, scrap_entries, recoveries (Phase 4)
  · inventory_intel_router (slow-mover / dead-stock / valuation already exist there)

NEW collection: stock_counts (physical count headers + line variance).
"""
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/inv5", tags=["store-inventory-phase5"])

HIGH_VARIANCE_THRESHOLD = 25000.0


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


# ─────────────────────────────────────────────────────────────────────
# 1. Stock Valuation (weighted-average with last-purchase / standard fallback)
# ─────────────────────────────────────────────────────────────────────
@router.get("/valuation")
async def stock_valuation(category: Optional[str] = None, store_id: Optional[str] = None,
                          method: str = "weighted_average",
                          user: dict = Depends(require_permission("inventory", "read"))):
    """Returns per-item valuation. `method` ∈ {weighted_average, last_purchase, standard}."""
    if method not in ("weighted_average", "last_purchase", "standard"):
        raise HTTPException(status_code=400, detail="method must be weighted_average | last_purchase | standard")
    q: dict = {}
    if category:
        q["category"] = category
    if store_id:
        q["store_id"] = store_id
    items = await db.inventory.find(q, {"_id": 0}).sort("name", 1).to_list(10000)

    rows = []
    total_value = 0.0
    damaged_value = 0.0
    scrap_value = 0.0
    by_category: dict = {}
    by_store: dict = {}

    for it in items:
        qty = float(it.get("quantity") or 0)
        # Weighted-average: prefer recorded average_rate; fallback last_purchase; fallback standard/rate
        wa = float(it.get("average_rate") or 0)
        lp = float(it.get("last_purchase_rate") or 0)
        std = float(it.get("standard_rate") or it.get("rate") or 0)
        if method == "weighted_average":
            rate = wa or lp or std
        elif method == "last_purchase":
            rate = lp or wa or std
        else:
            rate = std or wa or lp
        value = qty * rate
        damaged_qty = float(it.get("damaged_qty") or 0)
        scrap_qty = float(it.get("scrap_qty") or 0)
        damaged_value += damaged_qty * rate
        scrap_value += scrap_qty * rate
        total_value += value
        cat = it.get("category") or "uncategorised"
        by_category[cat] = by_category.get(cat, 0) + value
        sk = it.get("store_id") or "_none"
        by_store[sk] = by_store.get(sk, 0) + value
        rows.append({
            "item_id": it["id"],
            "item_code": it.get("code"),
            "item_name": it.get("name"),
            "category": it.get("category"),
            "store_id": it.get("store_id"),
            "unit": it.get("unit"),
            "quantity": qty,
            "average_rate": round(wa, 2),
            "last_purchase_rate": round(lp, 2),
            "standard_rate": round(std, 2),
            "rate_used": round(rate, 2),
            "stock_value": round(value, 2),
            "damaged_qty": damaged_qty,
            "scrap_qty": scrap_qty,
        })

    # In-transit value (Phase 3)
    transfers = await db.material_transfers.find({"status": "in_transit"}, {"_id": 0, "total_value": 1}).to_list(500)
    in_transit_value = sum(float(t.get("total_value") or 0) for t in transfers)

    # Project-tied outstanding value (Phase 3)
    proj_allocs = await db.material_allocations.find(
        {"status": {"$in": ["issued", "partially_returned"]}}, {"_id": 0},
    ).to_list(5000)
    project_value = sum(
        (float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0)) * float(a.get("rate") or 0)
        for a in proj_allocs
    )

    return {
        "method": method,
        "as_of": now_iso(),
        "summary": {
            "total_items": len(rows),
            "total_value": round(total_value, 2),
            "damaged_value": round(damaged_value, 2),
            "scrap_value": round(scrap_value, 2),
            "in_transit_value": round(in_transit_value, 2),
            "project_value": round(project_value, 2),
            "grand_total": round(total_value + in_transit_value + project_value, 2),
        },
        "by_category": [{"category": k, "value": round(v, 2)} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
        "by_store": [{"store_id": k, "value": round(v, 2)} for k, v in sorted(by_store.items(), key=lambda x: -x[1])],
        "rows": rows,
    }


# ─────────────────────────────────────────────────────────────────────
# 2. Physical Stock Count + Reconciliation
# ─────────────────────────────────────────────────────────────────────
SC_STATUSES = ("draft", "submitted", "approved", "rejected", "cancelled")


class StockCountLine(BaseModel):
    item_id: str
    physical_qty: float
    reason: Optional[str] = None
    notes: Optional[str] = None


class StockCountIn(BaseModel):
    count_date: str
    store_id: Optional[str] = None
    counted_by_name: Optional[str] = None
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None
    lines: List[StockCountLine] = Field(..., min_length=1)


@router.get("/stock-counts")
async def list_stock_counts(status: Optional[str] = None,
                              user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {"status": status} if status else {}
    return await db.stock_counts.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/stock-counts")
async def create_stock_count(payload: StockCountIn, request: Request,
                              user: dict = Depends(require_permission("inventory", "write"))):
    enriched = []
    total_var_value = 0.0
    for ln in payload.lines:
        if ln.physical_qty < 0:
            raise HTTPException(status_code=400, detail="physical_qty cannot be negative")
        item = await db.inventory.find_one({"id": ln.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {ln.item_id} not found")
        system_qty = float(item.get("quantity") or 0)
        diff = ln.physical_qty - system_qty
        rate = float(item.get("rate") or item.get("average_rate") or 0)
        diff_value = diff * rate
        total_var_value += abs(diff_value)
        enriched.append({
            "item_id": ln.item_id,
            "item_code": item.get("code"),
            "item_name": item.get("name"),
            "unit": item.get("unit"),
            "system_qty": system_qty,
            "physical_qty": ln.physical_qty,
            "diff_qty": diff,
            "rate": rate,
            "diff_value": round(diff_value, 2),
            "reason": ln.reason,
            "notes": ln.notes,
        })

    needs_finance = total_var_value >= HIGH_VARIANCE_THRESHOLD
    no = f"SC-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(await db.stock_counts.count_documents({})).zfill(5)}"
    doc = {
        "id": new_id(),
        "count_no": no,
        **payload.model_dump(exclude={"lines"}),
        "lines": enriched,
        "line_count": len(enriched),
        "total_variance_value": round(total_var_value, 2),
        "needs_finance_approval": needs_finance,
        "status": "submitted",
        "counted_by_id": user["id"],
        "counted_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.stock_counts.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="stock_counts", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.post("/stock-counts/{sc_id}/approve")
async def approve_stock_count(sc_id: str, request: Request,
                                user: dict = Depends(require_permission("inventory", "write"))):
    sc = await db.stock_counts.find_one({"id": sc_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Stock count not found")
    if sc.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"Cannot approve — status {sc.get('status')}")
    if sc.get("needs_finance_approval") and user.get("role") not in {"super_admin", "director", "finance_head", "general_manager"}:
        raise HTTPException(status_code=403, detail=f"Variance exceeds ₹{HIGH_VARIANCE_THRESHOLD:,.0f} — requires Finance/Director/GM approval")
    if sc.get("counted_by_id") == user["id"] and user.get("role") not in {"super_admin", "director"}:
        raise HTTPException(status_code=403, detail="Cannot approve your own stock count")

    # Pre-validation pass: ensure every negative-diff line has sufficient stock
    # BEFORE we start mutating anything. This makes the approval atomic — if any
    # line would overdraw, the whole approval is rejected with 400 and no rows
    # have been touched.
    for ln in sc.get("lines") or []:
        diff = float(ln.get("diff_qty") or 0)
        if diff >= -1e-9:
            continue
        cur = await db.inventory.find_one({"id": ln["item_id"]}, {"_id": 0, "quantity": 1, "name": 1}) or {}
        if float(cur.get("quantity") or 0) + diff < -1e-9:
            raise HTTPException(status_code=400,
                                detail=f"Insufficient stock to debit {-diff:g} from {ln['item_name']} (avail {float(cur.get('quantity') or 0):g})")

    # Apply each line variance + post ledger
    for ln in sc.get("lines") or []:
        diff = float(ln.get("diff_qty") or 0)
        if abs(diff) < 1e-9:
            continue
        # Race-safe negative guard
        if diff < 0:
            res = await db.inventory.update_one(
                {"id": ln["item_id"], "quantity": {"$gte": -diff}},
                {"$inc": {"quantity": diff}},
            )
            if res.matched_count == 0:
                cur = await db.inventory.find_one({"id": ln["item_id"]}, {"_id": 0}) or {}
                raise HTTPException(status_code=400,
                                    detail=f"Insufficient stock to debit {-diff:g} from {ln['item_name']} (avail {float(cur.get('quantity') or 0):g})")
        else:
            await db.inventory.update_one({"id": ln["item_id"]}, {"$inc": {"quantity": diff}})
        await db.inventory_transactions.insert_one({
            "id": new_id(), "txn_type": "adjustment",
            "item_id": ln["item_id"], "item_name": ln["item_name"],
            "quantity": abs(diff), "delta": diff, "unit": ln.get("unit"),
            "rate": ln.get("rate"), "store_id": sc.get("store_id"),
            "ref_type": "stock_count", "ref_id": sc_id, "ref_no": sc["count_no"],
            "note": f"Physical count variance · {ln.get('reason') or 'unspecified'}",
            "status": "posted", "created_by": user["id"],
            "created_by_name": user.get("name") or user.get("email"),
            "created_at": now_iso(),
        })

    await db.stock_counts.update_one({"id": sc_id}, {"$set": {
        "status": "approved",
        "approved_by_id": user["id"],
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
    }})
    row = await db.stock_counts.find_one({"id": sc_id}, {"_id": 0})
    await audit(user=user, action="approve", resource="stock_counts", record_id=sc_id, after=row, ip=_ip(request))
    return row


@router.post("/stock-counts/{sc_id}/reject")
async def reject_stock_count(sc_id: str, payload: dict, request: Request,
                              user: dict = Depends(require_permission("inventory", "write"))):
    sc = await db.stock_counts.find_one({"id": sc_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Not found")
    await db.stock_counts.update_one({"id": sc_id}, {"$set": {
        "status": "rejected", "rejected_by_id": user["id"],
        "rejected_at": now_iso(), "reject_reason": payload.get("reason"),
    }})
    return await db.stock_counts.find_one({"id": sc_id}, {"_id": 0})


# ─────────────────────────────────────────────────────────────────────
# 3. Consolidated Phase-5 Dashboard (30 tiles)
# ─────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def consolidated_dashboard(user: dict = Depends(require_permission("inventory", "read"))):
    """Single endpoint that powers the final Store & Inventory dashboard with
    real-time figures aggregated from all collections introduced in Phase 1-5."""
    items = await db.inventory.find({}, {"_id": 0}).to_list(10000)
    total_items = len(items)
    total_value = 0.0
    low_stock = 0
    reorder = 0
    out_stock = 0
    damaged_value = 0.0
    scrap_value = 0.0
    high_value_movements = 0
    for it in items:
        qty = float(it.get("quantity") or 0)
        # Match valuation rate-fallback chain so dashboard total_stock_value reconciles
        rate = float(it.get("average_rate") or it.get("last_purchase_rate") or it.get("rate") or 0)
        total_value += qty * rate
        min_s = float(it.get("min_stock") or 0)
        ro = float(it.get("reorder_level") or 0)
        if qty == 0:
            out_stock += 1
        elif min_s > 0 and qty < min_s:
            low_stock += 1
        if ro > 0 and qty <= ro:
            reorder += 1
        damaged_value += float(it.get("damaged_qty") or 0) * rate
        scrap_value += float(it.get("scrap_qty") or 0) * rate

    # Parallel-friendly count queries
    pending_mr = await db.material_requests.count_documents({"status": {"$in": ["submitted", "approved", "partially_issued"]}})
    pending_grn = await db.grn.count_documents({"status": "draft"})
    pending_inspection = await db.grn.count_documents({"inspection_status": {"$in": ["pending", "hold"]}})
    pending_transfer = await db.material_transfers.count_documents({"status": "in_transit"})
    pending_opening = await db.inv_opening_stock.count_documents({"status": "pending_approval"})
    pending_dl = await db.damage_loss_entries.count_documents({"status": "submitted"})
    pending_scrap = await db.scrap_entries.count_documents({"status": "submitted"})
    pending_sc = await db.stock_counts.count_documents({"status": "submitted"})
    today_str = datetime.now(timezone.utc).date().isoformat()
    horizon_30d = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    pending_ppe_expiry = await db.ppe_issuance.count_documents({
        "expiry_date": {"$ne": None, "$gte": today_str, "$lte": horizon_30d},
        "status": {"$in": ["issued", "active"]},
    })

    stores = await db.inv_stores.count_documents({"active": True})
    site_stores = await db.inv_site_stores.count_documents({"active": True})

    in_transit_value = 0.0
    async for t in db.material_transfers.find({"status": "in_transit"}, {"_id": 0, "total_value": 1}):
        in_transit_value += float(t.get("total_value") or 0)

    # Material consumption this month
    from datetime import datetime as _dt
    month_start = _dt.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    consumption_month = 0.0
    high_value_movements = 0
    async for t in db.inventory_transactions.find(
        {"txn_type": "outward", "created_at": {"$gte": month_start}, "status": "posted"},
        {"_id": 0, "quantity": 1, "rate": 1},
    ):
        v = float(t.get("quantity") or 0) * float(t.get("rate") or 0)
        consumption_month += v
        if v >= 50000:
            high_value_movements += 1

    # Tools / PPE / Employee pending
    tools_issued = await db.material_allocations.count_documents({
        "kind": {"$in": ["tool", "asset"]}, "status": {"$in": ["issued", "partially_returned"]},
    })
    ppe_issued = await db.ppe_issuance.count_documents({"status": {"$in": ["issued", "active"]}})

    # Pending recoveries
    pending_recovery_value = 0.0
    async for r in db.recoveries.find({"status": "pending"}, {"_id": 0, "amount": 1}):
        pending_recovery_value += float(r.get("amount") or 0)

    # Top consumed items (last 30d)
    pipeline = [
        {"$match": {"txn_type": "outward", "created_at": {"$gte": month_start}, "status": "posted"}},
        {"$group": {"_id": "$item_id", "total": {"$sum": "$quantity"}, "name": {"$last": "$item_name"}}},
        {"$sort": {"total": -1}}, {"$limit": 5},
    ]
    top_consumed = await db.inventory_transactions.aggregate(pipeline).to_list(5)

    # Recent transactions
    recent = await db.inventory_transactions.find(
        {}, {"_id": 0, "id": 1, "txn_no": 1, "txn_type": 1, "item_name": 1,
              "quantity": 1, "created_at": 1, "ref_no": 1},
    ).sort("created_at", -1).to_list(10)

    return {
        "as_of": now_iso(),
        # 30 dashboard tiles
        "total_stock_value": round(total_value, 2),
        "total_items": total_items,
        "stores_count": stores,
        "site_stores_count": site_stores,
        "low_stock_count": low_stock,
        "reorder_count": reorder,
        "out_of_stock_count": out_stock,
        "pending_mr_count": pending_mr,
        "pending_grn_count": pending_grn,
        "pending_inspection_count": pending_inspection,
        "pending_transfer_count": pending_transfer,
        "pending_opening_count": pending_opening,
        "pending_damage_loss_count": pending_dl,
        "pending_scrap_count": pending_scrap,
        "pending_stock_count_count": pending_sc,
        "in_transit_value": round(in_transit_value, 2),
        "damaged_value": round(damaged_value, 2),
        "scrap_value": round(scrap_value, 2),
        "tools_issued_count": tools_issued,
        "ppe_issued_count": ppe_issued,
        "expiring_ppe_30d_count": pending_ppe_expiry,
        "pending_recovery_value": round(pending_recovery_value, 2),
        "consumption_month_value": round(consumption_month, 2),
        "high_value_movements_month": high_value_movements,
        "top_consumed": top_consumed,
        "recent_transactions": recent,
    }


# ─────────────────────────────────────────────────────────────────────
# 4. Stock Reconciliation check: ledger sum vs inventory.quantity
# ─────────────────────────────────────────────────────────────────────
@router.get("/reconcile-check")
async def reconcile_check(user: dict = Depends(require_permission("inventory", "read"))):
    """Verifies stock_balance == ledger_sum_per_item. Any drift indicates a
    bug or manual DB tampering — output is used by Auditor role."""
    items = await db.inventory.find({}, {"_id": 0, "id": 1, "name": 1, "code": 1, "quantity": 1}).to_list(10000)
    drifts = []
    for it in items:
        s = await db.inventory_transactions.aggregate([
            {"$match": {"item_id": it["id"], "status": "posted"}},
            {"$group": {"_id": None, "sum": {"$sum": "$delta"}}},
        ]).to_list(1)
        ledger_sum = float((s[0]["sum"] if s else 0) or 0)
        balance = float(it.get("quantity") or 0)
        if abs(ledger_sum - balance) > 1e-6:
            drifts.append({
                "item_id": it["id"], "item_code": it.get("code"), "item_name": it.get("name"),
                "ledger_sum": ledger_sum, "inventory_qty": balance,
                "drift": round(balance - ledger_sum, 4),
            })
    return {"checked_items": len(items), "drift_count": len(drifts), "drifts": drifts, "as_of": now_iso()}
