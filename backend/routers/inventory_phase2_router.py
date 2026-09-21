"""Store & Inventory Phase 2 — Procurement / Accounts / Finance integration.

This router is purely additive — it relies on the existing collections
(`purchase_requisitions`, `purchase_orders`, `grn`, `inventory`,
`inventory_transactions`, `vendor_bills`) and only adds cross-module
aggregation endpoints + one quick-create action.

NEW collections introduced: none.
"""
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from pagination import paginate_list
from audit import audit

router = APIRouter(prefix="/inv2", tags=["store-inventory-phase2"])


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


# ─────────────────────────────────────────────────────────────────────
# 1. Quick PR from Stock Shortage / Reorder
# ─────────────────────────────────────────────────────────────────────
class PRLineIn(BaseModel):
    item_id: str
    required_qty: float
    suggested_vendor: Optional[str] = None
    remarks: Optional[str] = None


class PRFromStockIn(BaseModel):
    store_id: Optional[str] = None
    project_code: Optional[str] = None
    priority: str = "normal"          # normal | urgent | emergency
    reason: str = "stock_below_reorder"  # stock_below_reorder | reorder_level | project_requirement | emergency | replacement
    required_date: Optional[str] = None
    lines: List[PRLineIn] = Field(..., min_length=1)
    remarks: Optional[str] = None


@router.post("/pr-from-stock")
async def create_pr_from_stock(payload: PRFromStockIn, request: Request,
                               user: dict = Depends(require_permission("purchase_requisitions", "write"))):
    """Create a Purchase Requisition triggered by a stock shortage.
    Reuses the existing `purchase_requisitions` collection — no duplication."""
    if payload.priority not in ("normal", "urgent", "emergency"):
        raise HTTPException(status_code=400, detail="priority must be normal | urgent | emergency")

    # Resolve items, compute available stock & short qty
    pr_lines = []
    for ln in payload.lines:
        if ln.required_qty <= 0:
            raise HTTPException(status_code=400, detail=f"required_qty must be > 0 (item {ln.item_id})")
        item = await db.inventory.find_one({"id": ln.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {ln.item_id} not found")
        available = float(item.get("quantity") or 0)
        short = max(0.0, float(ln.required_qty) - available)
        pr_lines.append({
            "item_id": ln.item_id,
            "item_code": item.get("code"),
            "item_name": item.get("name"),
            "uom": item.get("unit") or item.get("uom") or "Nos",
            "category": item.get("category"),
            "required_qty": float(ln.required_qty),
            "available_stock": available,
            "short_qty": short,
            "rate": float(item.get("rate") or item.get("last_purchase_rate") or 0),
            "suggested_vendor": ln.suggested_vendor or item.get("vendor_name"),
            "min_stock": float(item.get("min_stock") or 0),
            "reorder_level": float(item.get("reorder_level") or 0),
            "remarks": ln.remarks,
        })

    # Auto-bump priority if any line is critically below min_stock
    auto_priority = payload.priority
    if any(ln["available_stock"] <= ln["min_stock"] for ln in pr_lines):
        auto_priority = "urgent" if payload.priority == "normal" else payload.priority

    # Numbering
    pr_count = await db.purchase_requisitions.count_documents({})
    pr_number = f"PR-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(pr_count + 1).zfill(5)}"

    doc = {
        "id": new_id(),
        "pr_number": pr_number,
        "pr_date": now_iso()[:10],
        "requested_by": user["id"],
        "requested_by_name": user.get("name") or user.get("email"),
        "store_id": payload.store_id,
        "project_code": payload.project_code,
        "priority": auto_priority,
        "reason": payload.reason,
        "required_date": payload.required_date,
        "items": pr_lines,
        "lines": pr_lines,                       # alias for legacy consumers
        "remarks": payload.remarks,
        "total_value": round(sum(ln["short_qty"] * ln["rate"] for ln in pr_lines), 2),
        "status": "submitted",                   # auto-submit when triggered from stock
        "source": "stock_shortage",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.purchase_requisitions.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create_from_stock", resource="purchase_requisitions",
                record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/stock-shortage-suggestions")
async def stock_shortage_suggestions(user: dict = Depends(require_permission("inventory", "read"))):
    """Suggest items that should be added to a stock-shortage PR right now —
    items where qty <= reorder_level OR qty <= min_stock."""
    items = await db.inventory.find({}, {"_id": 0}).to_list(10000)
    suggestions = []
    for it in items:
        qty = float(it.get("quantity") or 0)
        min_s = float(it.get("min_stock") or 0)
        reorder = float(it.get("reorder_level") or 0)
        if (min_s > 0 and qty <= min_s) or (reorder > 0 and qty <= reorder):
            suggestions.append({
                "item_id": it["id"],
                "item_code": it.get("code"),
                "item_name": it.get("name"),
                "category": it.get("category"),
                "available_qty": qty,
                "min_stock": min_s,
                "reorder_level": reorder,
                "suggested_qty": max(reorder, min_s) - qty if (min_s or reorder) else 0,
                "rate": float(it.get("rate") or it.get("last_purchase_rate") or 0),
                "vendor_name": it.get("vendor_name"),
                "trigger": "below_min" if (min_s > 0 and qty <= min_s) else "below_reorder",
            })
    suggestions.sort(key=lambda r: (r["trigger"] == "below_min", -r["suggested_qty"]), reverse=True)
    return {"count": len(suggestions), "rows": suggestions}


# ─────────────────────────────────────────────────────────────────────
# 2. Pending POs for GRN
# ─────────────────────────────────────────────────────────────────────
@router.get("/pending-pos-for-grn")
async def pending_pos_for_grn(user: dict = Depends(require_permission("grn", "read"))):
    """List approved / partially-received POs that still have pending qty to be
    received. Used by the Store to know what to inward next."""
    pos = await db.purchase_orders.find(
        {"status": {"$in": ["approved", "sent_to_vendor", "partially_received"]}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(1000)

    out = []
    for po in pos:
        items = po.get("items") or []
        if not items:
            continue
        # cumulative accepted per line index across all GRNs of this PO
        cum: dict = {}
        grns = await db.grn.find({"po_id": po["id"]}, {"_id": 0, "items": 1, "grn_number": 1}).to_list(500)
        for g in grns:
            for it in g.get("items") or []:
                idx = int(it.get("po_item_index") or 0)
                cum[idx] = cum.get(idx, 0.0) + float(it.get("accepted_qty") or 0)
        line_rows = []
        total_pending = 0.0
        total_value_pending = 0.0
        for i, it in enumerate(items):
            ordered = float(it.get("quantity") or 0)
            received = cum.get(i, 0.0)
            pending = max(0.0, ordered - received)
            if pending > 1e-6:
                rate = float(it.get("rate") or po.get("rate") or 0)
                total_pending += pending
                total_value_pending += pending * rate
                line_rows.append({
                    "po_item_index": i,
                    "item_id": it.get("item_id"),
                    "item_name": it.get("name") or it.get("item_name"),
                    "unit": it.get("unit") or "Nos",
                    "ordered_qty": ordered,
                    "received_qty": received,
                    "pending_qty": pending,
                    "rate": rate,
                    "pending_value": round(pending * rate, 2),
                })
        if line_rows:
            out.append({
                "po_id": po["id"],
                "po_number": po.get("po_number"),
                "po_date": po.get("created_at", "")[:10],
                "vendor_id": po.get("vendor_id"),
                "vendor_name": po.get("vendor"),
                "project": po.get("project"),
                "site": po.get("site"),
                "status": po.get("status"),
                "ordered_total": float(po.get("amount") or 0),
                "delivery_days": po.get("delivery_days"),
                "payment_terms": po.get("payment_terms"),
                "grn_count": len(grns),
                "lines": line_rows,
                "pending_lines": len(line_rows),
                "pending_qty_total": round(total_pending, 2),
                "pending_value_total": round(total_value_pending, 2),
            })
    out.sort(key=lambda r: -r["pending_value_total"])
    return {"count": len(out), "total_pending_value": round(sum(r["pending_value_total"] for r in out), 2), "rows": out}


# ─────────────────────────────────────────────────────────────────────
# 3. Stock Inward Report
# ─────────────────────────────────────────────────────────────────────
@router.get("/stock-inward-report")
async def stock_inward_report(request: Request, date_from: Optional[str] = None, date_to: Optional[str] = None,
                              store_id: Optional[str] = None, vendor_id: Optional[str] = None,
                              user: dict = Depends(require_permission("inventory", "read"))):
    """Inward transactions (GRN-driven + opening stock + manual inward) within
    a date range. Pulls from existing `inventory_transactions` collection."""
    q: dict = {"txn_type": {"$in": ["inward", "opening", "transfer_in", "return_inward"]}, "status": "posted"}
    if date_from:
        q.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        q.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59Z"
    if store_id:
        q["store_id"] = store_id
    rows = await db.inventory_transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)

    # Enrich each row with vendor + PO refs by joining with GRN where available
    grn_cache: dict = {}
    for r in rows:
        if r.get("ref_type") == "grn" and r.get("ref_id"):
            grn = grn_cache.get(r["ref_id"])
            if grn is None:
                grn = await db.grn.find_one({"id": r["ref_id"]}, {"_id": 0, "vendor_name": 1, "vendor_id": 1, "po_number": 1, "po_id": 1, "received_by": 1})
                grn_cache[r["ref_id"]] = grn or {}
            r["vendor_name"] = (grn or {}).get("vendor_name")
            r["vendor_id"] = (grn or {}).get("vendor_id")
            r["po_number"] = (grn or {}).get("po_number")
            r["received_by"] = (grn or {}).get("received_by")
    if vendor_id:
        rows = [r for r in rows if r.get("vendor_id") == vendor_id]

    total_value = round(sum(float(r.get("quantity") or 0) * float(r.get("rate") or 0) for r in rows), 2)
    by_type = {}
    for r in rows:
        by_type[r.get("txn_type")] = by_type.get(r.get("txn_type"), 0) + 1
    return {
        "count": len(rows),
        "total_value": total_value,
        "by_type": by_type,
        **(paginate_list(request, rows, ["txn_no", "item_name", "item_code", "vendor_name", "po_number", "store_name", "txn_type"], "created_at")
           or {"rows": rows[:1500]}),   # legacy cap
    }


# ─────────────────────────────────────────────────────────────────────
# 4. GRN Pending Invoice Report (Accounts visibility)
# ─────────────────────────────────────────────────────────────────────
@router.get("/grn-pending-invoice")
async def grn_pending_invoice(user: dict = Depends(require_permission("vendor_bills", "read"))):
    """List approved GRNs that have NO matching vendor bill yet. Pre-built for
    the Accounts team to chase invoices and complete 3-way match."""
    grns = await db.grn.find(
        {"inspection_status": {"$in": ["approved", "partial_accepted"]}, "status": {"$ne": "deleted"}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(2000)

    out = []
    matched = 0
    for g in grns:
        # vendor_bills can link via grn_id (array) or via po_id
        bill = await db.vendor_bills.find_one(
            {"$or": [
                {"grn_ids": g["id"]},
                {"grn_id": g["id"]},
                {"po_id": g.get("po_id"), "vendor_id": g.get("vendor_id")},
            ]},
            {"_id": 0, "bill_number": 1, "bill_date": 1, "total_amount": 1, "status": 1},
        )
        if bill:
            matched += 1
            continue
        gross = round(sum(float(it.get("accepted_qty") or 0) * float(it.get("rate") or 0) for it in (g.get("items") or [])), 2)
        out.append({
            "grn_id": g["id"],
            "grn_number": g.get("grn_number"),
            "grn_date": g.get("received_at"),
            "po_number": g.get("po_number"),
            "vendor_id": g.get("vendor_id"),
            "vendor_name": g.get("vendor_name"),
            "total_accepted": g.get("total_accepted"),
            "total_rejected": g.get("total_rejected"),
            "estimated_value": gross,
            "line_count": len(g.get("items") or []),
            "vendor_invoice_no": g.get("vendor_invoice_no"),
            "vendor_invoice_date": g.get("vendor_invoice_date"),
            "days_pending": (datetime.now(timezone.utc) - datetime.fromisoformat((g.get("created_at") or now_iso()).replace("Z", "+00:00"))).days,
        })
    out.sort(key=lambda r: -r["days_pending"])
    return {
        "count": len(out),
        "matched_count": matched,
        "total_count": len(grns),
        "total_estimated_value": round(sum(r["estimated_value"] for r in out), 2),
        "rows": out,
    }


# ─────────────────────────────────────────────────────────────────────
# 5. Accounts GRN Visibility — Three-way match feed
# ─────────────────────────────────────────────────────────────────────
@router.get("/accounts-grn-visibility")
async def accounts_grn_visibility(vendor_id: Optional[str] = None, po_number: Optional[str] = None,
                                  user: dict = Depends(require_permission("vendor_bills", "read"))):
    """Single source of truth for Accounts to verify a vendor's invoice:
    returns PO + GRN + matched vendor bill (if any) all in one shot."""
    q: dict = {"status": {"$ne": "deleted"}}
    if vendor_id:
        q["vendor_id"] = vendor_id
    if po_number:
        q["po_number"] = po_number
    grns = await db.grn.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)

    out = []
    for g in grns:
        gross = sum(float(it.get("accepted_qty") or 0) * float(it.get("rate") or 0) for it in (g.get("items") or []))
        po = await db.purchase_orders.find_one({"id": g.get("po_id")}, {"_id": 0, "amount": 1, "items": 1, "payment_terms": 1, "project": 1})
        bill = await db.vendor_bills.find_one(
            {"$or": [{"grn_ids": g["id"]}, {"grn_id": g["id"]}, {"po_id": g.get("po_id"), "vendor_id": g.get("vendor_id")}]},
            {"_id": 0, "bill_number": 1, "bill_date": 1, "total_amount": 1, "status": 1, "id": 1},
        )
        out.append({
            "grn_id": g["id"],
            "grn_number": g.get("grn_number"),
            "grn_date": g.get("received_at"),
            "po_id": g.get("po_id"),
            "po_number": g.get("po_number"),
            "po_value": (po or {}).get("amount"),
            "po_project": (po or {}).get("project"),
            "payment_terms": (po or {}).get("payment_terms"),
            "vendor_id": g.get("vendor_id"),
            "vendor_name": g.get("vendor_name"),
            "vendor_invoice_no": g.get("vendor_invoice_no"),
            "vendor_invoice_date": g.get("vendor_invoice_date"),
            "vendor_invoice_value": g.get("vendor_invoice_value"),
            "total_accepted": g.get("total_accepted"),
            "total_rejected": g.get("total_rejected"),
            "estimated_grn_value": round(gross, 2),
            "items": g.get("items") or [],
            "bill_id": (bill or {}).get("id"),
            "bill_number": (bill or {}).get("bill_number"),
            "bill_status": (bill or {}).get("status"),
            "bill_amount": (bill or {}).get("total_amount"),
            "three_way_match": bool(bill) and abs(float((bill or {}).get("total_amount") or 0) - gross) < 1.0,
        })
    return {"count": len(out), "rows": out}


# ─────────────────────────────────────────────────────────────────────
# 6. Inspection Hold Stock
# ─────────────────────────────────────────────────────────────────────
@router.get("/inspection-hold")
async def inspection_hold(user: dict = Depends(require_permission("inventory", "read"))):
    """GRN lines with inspection_status in (pending, hold, partial_accepted) — i.e.
    material physically received but not yet released into available stock."""
    rows = []
    total_held_value = 0.0
    grns = await db.grn.find(
        {"inspection_status": {"$in": ["pending", "hold", "partial_accepted"]}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(1000)
    for g in grns:
        for line in (g.get("items") or []):
            held = float(line.get("hold_qty") or 0)
            if line.get("inspection_status") in ("pending", "hold") and held == 0:
                held = float(line.get("received_qty") or 0) - float(line.get("accepted_qty") or 0) - float(line.get("rejected_qty") or 0)
            if held <= 0 and line.get("inspection_status") not in ("pending", "hold"):
                continue
            rate = float(line.get("rate") or 0)
            total_held_value += held * rate
            rows.append({
                "grn_id": g["id"],
                "grn_number": g.get("grn_number"),
                "grn_date": g.get("received_at"),
                "po_number": g.get("po_number"),
                "vendor_name": g.get("vendor_name"),
                "item_id": line.get("item_id"),
                "item_name": line.get("item_name"),
                "unit": line.get("unit"),
                "received_qty": float(line.get("received_qty") or 0),
                "accepted_qty": float(line.get("accepted_qty") or 0),
                "rejected_qty": float(line.get("rejected_qty") or 0),
                "hold_qty": held,
                "rate": rate,
                "hold_value": round(held * rate, 2),
                "inspection_status": line.get("inspection_status"),
                "damage_notes": line.get("damage_notes"),
            })
    return {"count": len(rows), "rows": rows, "total_held_value": round(total_held_value, 2)}


# ─────────────────────────────────────────────────────────────────────
# 7. Finance / Executive view: Procurement Pipeline value
# ─────────────────────────────────────────────────────────────────────
@router.get("/procurement-pipeline")
async def procurement_pipeline(user: dict = Depends(require_permission("inventory", "read"))):
    """Single tile-friendly response with the value of every stage in the
    procurement pipeline — what Finance wants to see at a glance."""
    pr_pending = await db.purchase_requisitions.find(
        {"status": {"$in": ["submitted", "approved", "rfq_generated"]}}, {"_id": 0, "total_value": 1, "items": 1},
    ).to_list(2000)
    po_pending = await db.purchase_orders.find(
        {"status": {"$in": ["approved", "sent_to_vendor", "partially_received"]}}, {"_id": 0, "amount": 1, "status": 1},
    ).to_list(2000)
    grns_30d = await db.grn.find(
        {"created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()}},
        {"_id": 0, "items": 1, "total_accepted": 1},
    ).to_list(2000)
    grns_value_30d = 0.0
    for g in grns_30d:
        grns_value_30d += sum(float(it.get("accepted_qty") or 0) * float(it.get("rate") or 0) for it in (g.get("items") or []))

    emergency_prs = await db.purchase_requisitions.count_documents({"priority": "emergency", "status": {"$nin": ["closed", "rejected"]}})

    return {
        "pr_pending_count": len(pr_pending),
        "pr_pending_value": round(sum(float(r.get("total_value") or 0) for r in pr_pending), 2),
        "po_pending_count": len(po_pending),
        "po_pending_value": round(sum(float(r.get("amount") or 0) for r in po_pending), 2),
        "grn_30d_count": len(grns_30d),
        "grn_30d_value": round(grns_value_30d, 2),
        "emergency_pr_count": emergency_prs,
        "as_of": now_iso(),
    }
