"""Procurement Phase D — Intelligence layer.

Endpoints:
  * GET  /api/vendors/{id}/performance  — derived score from PO/GRN history
  * GET  /api/vendor-performance         — leaderboard across all vendors
  * GET  /api/procurement/budgets        — budget vs actual rollup (PR.budget_reference)
  * GET  /api/procurement/reservations   — inventory reservations from open PRs
  * GET  /api/audit/explorer             — filtered audit log search
  * GET  /api/admin/approval-matrix      — list configured override chains
  * PUT  /api/admin/approval-matrix/{type} — override chain for an approval type
  * POST /api/admin/approval-matrix/{type}/reset — drop override (back to defaults)
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query

from core import db, require_permission, get_current_user, now_iso
from approval_engine import APPROVAL_CHAINS

router = APIRouter(tags=["procurement-phase-d"])


# ──────────────────────────────────────────────────────────────────────────────
# Vendor performance rating
# ──────────────────────────────────────────────────────────────────────────────
async def _score_vendor(vendor_id: str, vendor_name: str | None) -> dict:
    """Compute a 0-100 score based on:
       * Total PO count and value
       * GRN quality (accepted vs rejected)
       * On-time delivery (received vs delivery_days)
       * RFQ response rate
    """
    pos = await db.purchase_orders.find({"vendor_id": vendor_id}, {"_id": 0}).to_list(500)
    po_count = len(pos)
    po_value = sum(float(p.get("amount") or 0) for p in pos)

    # GRN quality
    grns = await db.grn.find({"vendor_id": vendor_id}, {"_id": 0}).to_list(500)
    total_acc = sum(float(g.get("total_accepted") or 0) for g in grns)
    total_rej = sum(float(g.get("total_rejected") or 0) for g in grns)
    quality_pct = round((total_acc / (total_acc + total_rej) * 100), 1) if (total_acc + total_rej) else None

    # On-time delivery
    on_time = 0
    late = 0
    for g in grns:
        po = next((p for p in pos if p.get("id") == g.get("po_id")), None)
        if not po:
            continue
        try:
            po_created = datetime.fromisoformat(str(po.get("created_at") or "").replace("Z", "+00:00"))
            promised = po_created + timedelta(days=int(po.get("delivery_days") or 30))
            received = datetime.fromisoformat(str(g.get("created_at") or "").replace("Z", "+00:00"))
            (on_time if received <= promised else late).__iadd__ if False else None
            if received <= promised:
                on_time += 1
            else:
                late += 1
        except Exception:
            continue
    on_time_pct = round((on_time / (on_time + late) * 100), 1) if (on_time + late) else None

    # RFQ response rate
    rfqs = await db.rfqs.find({"vendors.vendor_id": vendor_id}, {"_id": 0}).to_list(500)
    invited = sent_resp = 0
    for r in rfqs:
        for v in r.get("vendors") or []:
            if v.get("vendor_id") != vendor_id:
                continue
            invited += 1
            if v.get("status") == "responded":
                sent_resp += 1
    response_pct = round((sent_resp / invited * 100), 1) if invited else None

    # Score: 40% quality + 30% on-time + 20% response rate + 10% scale (PO count log-norm)
    import math
    parts = []
    weights = []
    if quality_pct is not None:
        parts.append(quality_pct)
        weights.append(40)
    if on_time_pct is not None:
        parts.append(on_time_pct)
        weights.append(30)
    if response_pct is not None:
        parts.append(response_pct)
        weights.append(20)
    scale_score = min(100, math.log10(po_count + 1) * 50) if po_count else 0
    parts.append(scale_score)
    weights.append(10)
    score = round(sum(p * w for p, w in zip(parts, weights)) / sum(weights), 1) if weights else None
    grade = (
        "A+" if score and score >= 90 else
        "A" if score and score >= 80 else
        "B" if score and score >= 70 else
        "C" if score and score >= 50 else
        "D" if score and score >= 30 else
        "—"
    )
    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "score": score,
        "grade": grade,
        "po_count": po_count,
        "po_value": round(po_value, 2),
        "grn_count": len(grns),
        "quality_pct": quality_pct,
        "on_time_pct": on_time_pct,
        "response_pct": response_pct,
        "rfqs_invited": invited,
        "computed_at": now_iso(),
    }


@router.get("/vendors/{vendor_id}/performance")
async def vendor_performance(vendor_id: str,
                             user: dict = Depends(require_permission("vendors", "read"))):
    v = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return await _score_vendor(vendor_id, v.get("name"))


@router.get("/vendor-performance")
async def vendor_performance_leaderboard(user: dict = Depends(require_permission("vendors", "read"))):
    vendors = await db.vendors.find({}, {"_id": 0}).to_list(500)
    rows = []
    for v in vendors:
        rows.append(await _score_vendor(v["id"], v.get("name")))
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    return {"as_of": now_iso()[:10], "vendors": rows}


# ──────────────────────────────────────────────────────────────────────────────
# Budget vs Actual
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/procurement/budgets")
async def budgets_view(user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    """Group POs by their PR's `budget_reference`, surface PR count, PO value, GRN value."""
    pipeline = [
        {"$match": {"budget_reference": {"$ne": None, "$nin": [None, ""]}}},
        {"$group": {"_id": "$budget_reference",
                    "pr_count": {"$sum": 1},
                    "departments": {"$addToSet": "$department"}}},
        {"$sort": {"pr_count": -1}},
    ]
    budgets = await db.purchase_requisitions.aggregate(pipeline).to_list(500)
    out = []
    for b in budgets:
        ref = b["_id"]
        prs = await db.purchase_requisitions.find({"budget_reference": ref}, {"_id": 0, "id": 1, "status": 1, "po_id": 1, "department": 1}).to_list(500)
        po_ids = [p.get("po_id") for p in prs if p.get("po_id")]
        committed = 0.0
        grn_value = 0.0
        for po_id in po_ids:
            po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0, "amount": 1})
            if po:
                committed += float(po.get("amount") or 0)
            grns = await db.grn.find({"po_id": po_id}, {"_id": 0, "total_accepted": 1, "items": 1}).to_list(50)
            for g in grns:
                for it in g.get("items") or []:
                    grn_value += float(it.get("accepted_qty") or 0)
        out.append({
            "budget_reference": ref,
            "pr_count": b["pr_count"],
            "departments": [d for d in b.get("departments") or [] if d],
            "po_count": len(po_ids),
            "committed_value": round(committed, 2),
            "received_qty": round(grn_value, 2),
        })
    return {"as_of": now_iso()[:10], "budgets": out}


# ──────────────────────────────────────────────────────────────────────────────
# Material reservations (soft-hold against open PRs)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/procurement/reservations")
async def reservations_view(user: dict = Depends(require_permission("inventory", "read"))):
    """Open PRs (pending_approval / approved / rfq_initiated) reserve their requested qty against inventory."""
    open_prs = await db.purchase_requisitions.find(
        {"status": {"$in": ["pending_approval", "approved", "rfq_initiated"]}}, {"_id": 0},
    ).to_list(500)
    reserved_by_item_name: Dict[str, float] = {}
    for pr in open_prs:
        for it in pr.get("items") or []:
            if not it.get("name"):
                continue
            key = (it.get("name") or "").strip().lower()
            reserved_by_item_name[key] = reserved_by_item_name.get(key, 0.0) + float(it.get("quantity") or 0)
    items = await db.inventory.find({}, {"_id": 0}).to_list(5000)
    rows = []
    for item in items:
        reserved = reserved_by_item_name.get((item.get("name") or "").strip().lower(), 0.0)
        if reserved <= 0:
            continue
        on_hand = float(item.get("quantity") or 0)
        rows.append({
            "id": item["id"], "name": item.get("name"), "unit": item.get("unit"),
            "on_hand": on_hand, "reserved": round(reserved, 2),
            "available": round(on_hand - reserved, 2),
            "shortfall": round(reserved - on_hand, 2) if reserved > on_hand else 0,
        })
    rows.sort(key=lambda r: -r["reserved"])
    return {"as_of": now_iso()[:10], "open_pr_count": len(open_prs), "items": rows}


# ──────────────────────────────────────────────────────────────────────────────
# Audit explorer
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/audit/explorer")
async def audit_explorer(resource: Optional[str] = None,
                         action: Optional[str] = None,
                         user_id: Optional[str] = None,
                         from_date: Optional[str] = None,
                         to_date: Optional[str] = None,
                         limit: int = Query(default=200, le=2000),
                         user: dict = Depends(get_current_user)):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head"):
        raise HTTPException(status_code=403, detail="Restricted to leadership / super admin")
    q: dict = {}
    if resource:
        q["resource"] = resource
    if action:
        q["action"] = action
    if user_id:
        q["user_id"] = user_id
    if from_date or to_date:
        rng: dict = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date + "T23:59:59"
        q["created_at"] = rng
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    # Distinct dimensions for filter dropdowns
    resources = await db.audit_logs.distinct("resource")
    actions = await db.audit_logs.distinct("action")
    return {"count": len(rows), "rows": rows, "resources": resources, "actions": actions}


# ──────────────────────────────────────────────────────────────────────────────
# Approval matrix override — handled by /api/admin/approval-matrix in
# `admin_router.py`; the approval_engine already reads from
# `db.approval_chains` so PR/RFQ/GRN auto-pick up the override.
# ──────────────────────────────────────────────────────────────────────────────
