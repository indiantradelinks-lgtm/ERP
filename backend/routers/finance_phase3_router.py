"""Finance Phase 3 — Store / Inventory / Procurement integration (Iter 111).

Audit-first finding: the heavy lifting is ALREADY done.  All 7 auto-posting
hooks exist in `accounting_service.py` and are wired into their respective
module routers:
  • GRN finalize          → DR Inventory/Project-Cost · CR GRNI  (store_router.py)
  • Vendor Bill approve   → DR Expense + GST Input · CR AP + TDS  (vendor_billing_router.py)
  • Vendor Payment        → DR AP · CR Bank/Cash · CR Retention  (vendor_billing_router.py)
  • Sales Invoice issued  → DR AR · CR Revenue + GST Output      (billing_router.py)
  • Customer Receipt      → DR Bank · CR AR + TDS Receivable     (billing_router.py, receivables_router.py)
  • RA Bill issue         → DR AR · CR Revenue + GST Output      (ra_bills_router.py)
  • Material Issue        → DR Project-Cost · CR Inventory       (accounting_service.py)

Real gaps that this module fills (no duplication of existing work):

  1. **Budget availability check** — before approving a PR/PO, surface the
     project's budget vs already-committed (approved POs) vs already-spent
     (posted JEs) vs pending bills.  Endpoint: GET /finance/budget/check.

  2. **PO commitment report** — aggregated view of approved-not-fully-received
     POs (i.e. money the company is contractually committed to).
     Endpoint: GET /finance/reports/po-commitment.

  3. **GRN-not-billed report** — GRNs that have NOT yet been linked to a
     vendor bill.  Counter-balance to the existing "bill-without-GRN" guard.
     Endpoint: GET /finance/reports/grn-not-billed.

  4. **Bill-without-GRN report** — vendor bills posted without a matching GRN
     (these should mainly be services or expenses that don't need physical
     receipt — useful for audit).
     Endpoint: GET /finance/reports/bill-without-grn.

  5. **Material return → reverse JE hook** — when a `material_return` row
     is recorded, reverse the original consumption posting.
     Endpoint: POST /finance/material-return/{return_id}/post-reversal.

All read endpoints use existing collections; no new collections introduced.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from pagination import paginate_list
from audit import audit
from accounting_service import post_journal_entry

router = APIRouter(prefix="/finance", tags=["finance-phase3"])


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ═════════════════════════════════════════════════════════════════════════
# 1.  BUDGET AVAILABILITY CHECK
# ═════════════════════════════════════════════════════════════════════════
@router.get("/budget/check")
async def budget_check(
    project_id: str = Query(..., description="Project id"),
    amount: float = Query(0, description="Proposed new commitment amount"),
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Returns budget vs committed vs spent vs available for a project.

    • budget       = project.budget_value (or sum of WBS allocations if present)
    • committed    = sum(approved & not-fully-received PO amounts) +
                     sum(approved-not-paid SO amounts)
    • spent        = sum(approved vendor bills) + sum(approved site expenses)
    • pending_bills = vendor bills in pending_verification/pending_approval
    • available    = budget - committed - spent - pending_bills - amount
    """
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found")

    budget_value = float(project.get("budget_value") or project.get("total_value") or 0)
    # Try WBS-level rollup if budget_value is missing
    if budget_value <= 0:
        wbs_total = 0.0
        async for w in db.project_wbs.find({"project_id": project_id}, {"_id": 0, "budget": 1}):
            wbs_total += float(w.get("budget") or 0)
        budget_value = wbs_total

    # Committed = approved POs not fully received
    pos = await db.purchase_orders.find(
        {"project_id": project_id, "status": {"$in": ["approved", "partially_received"]}},
        {"_id": 0, "total": 1, "total_amount": 1, "received_value": 1, "amount": 1},
    ).to_list(500)
    committed = 0.0
    for p in pos:
        total = float(p.get("total") or p.get("total_amount") or p.get("amount") or 0)
        received = float(p.get("received_value") or 0)
        committed += max(total - received, 0)

    # Service orders committed too
    sos = await db.service_orders.find(
        {"project_id": project_id, "status": {"$in": ["approved", "in_progress", "partially_received"]}},
        {"_id": 0, "total_amount": 1, "received_value": 1},
    ).to_list(500)
    for so in sos:
        total = float(so.get("total_amount") or 0)
        received = float(so.get("received_value") or 0)
        committed += max(total - received, 0)

    # Spent = approved vendor bills + approved site expenses
    spent = 0.0
    async for vb in db.vendor_bills.find(
        {"project_id": project_id, "status": "approved"},
        {"_id": 0, "amount": 1, "total_amount": 1, "gross_amount": 1},
    ):
        spent += float(vb.get("amount") or vb.get("total_amount") or vb.get("gross_amount") or 0)
    async for se in db.site_expenses.find(
        {"project_id": project_id, "status": "approved"},
        {"_id": 0, "amount": 1, "total_amount": 1},
    ):
        spent += float(se.get("amount") or se.get("total_amount") or 0)

    # Pending bills
    pending_bills = 0.0
    async for vb in db.vendor_bills.find(
        {"project_id": project_id, "status": {"$in": ["pending_verification", "pending_approval", "submitted"]}},
        {"_id": 0, "amount": 1, "total_amount": 1, "gross_amount": 1},
    ):
        pending_bills += float(vb.get("amount") or vb.get("total_amount") or vb.get("gross_amount") or 0)

    available = budget_value - committed - spent - pending_bills
    after_request = available - float(amount or 0)

    return {
        "project_id": project_id,
        "project_code": project.get("code"),
        "project_name": project.get("name"),
        "budget_value": round(budget_value, 2),
        "committed_pos_sos": round(committed, 2),
        "spent_approved_bills": round(spent, 2),
        "pending_bills": round(pending_bills, 2),
        "available": round(available, 2),
        "requested_amount": float(amount or 0),
        "available_after_request": round(after_request, 2),
        "utilisation_pct": round((committed + spent) / budget_value * 100, 1) if budget_value > 0 else None,
        "within_budget": after_request >= 0 if budget_value > 0 else None,
    }


# ═════════════════════════════════════════════════════════════════════════
# 2.  PO COMMITMENT REPORT
# ═════════════════════════════════════════════════════════════════════════
@router.get("/reports/po-commitment")
async def po_commitment_report(
    request: Request,
    project_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Approved POs that still carry an open commitment (total > received)."""
    q: Dict[str, Any] = {"status": {"$in": ["approved", "partially_received"]}}
    if project_id:
        q["project_id"] = project_id
    if vendor_id:
        q["vendor_id"] = vendor_id
    rows = await db.purchase_orders.find(q, {
        "_id": 0, "id": 1, "po_number": 1, "po_date": 1, "vendor_id": 1, "vendor_name": 1,
        "vendor": 1, "project_id": 1, "project_code": 1, "status": 1,
        "total": 1, "total_amount": 1, "received_value": 1, "amount": 1,
    }).sort("po_date", -1).to_list(1000)

    out = []
    total_committed = 0.0
    for p in rows:
        total = float(p.get("total") or p.get("total_amount") or p.get("amount") or 0)
        received = float(p.get("received_value") or 0)
        open_commit = max(total - received, 0)
        if open_commit <= 0:
            continue
        total_committed += open_commit
        out.append({
            "id": p["id"], "po_number": p.get("po_number"),
            "po_date": p.get("po_date"),
            "vendor_id": p.get("vendor_id"),
            "vendor_name": p.get("vendor_name") or (p.get("vendor") or {}).get("name") if isinstance(p.get("vendor"), dict) else p.get("vendor"),
            "project_id": p.get("project_id"),
            "project_code": p.get("project_code"),
            "status": p.get("status"),
            "po_total": total,
            "received_value": received,
            "open_commitment": round(open_commit, 2),
        })

    paged = paginate_list(request, out, ["po_number", "vendor_name", "project_code", "status"], "po_date")
    return {"count": len(out), "total_open_commitment": round(total_committed, 2), **(paged or {"rows": out})}


# ═════════════════════════════════════════════════════════════════════════
# 3.  GRN-NOT-BILLED REPORT
# ═════════════════════════════════════════════════════════════════════════
@router.get("/reports/grn-not-billed")
async def grn_not_billed(
    request: Request,
    project_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    days_old: int = Query(0, description="Only GRNs older than this many days"),
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Goods Received Notes that have NOT yet been linked to a vendor bill.

    These are an accounts-payable provision risk — if a vendor bills late,
    the liability is unaccounted-for in the books.  Surfaces GRNI balance.
    """
    coll = db.goods_receipt_notes
    if (await db.grns.estimated_document_count()) > await coll.estimated_document_count():
        coll = db.grns  # fallback

    q: Dict[str, Any] = {"$or": [{"invoice_received": {"$ne": True}}, {"vendor_bill_id": None}]}
    if project_id:
        q["project_id"] = project_id
    if vendor_id:
        q["vendor_id"] = vendor_id
    if days_old > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_old)).strftime("%Y-%m-%d")
        q["grn_date"] = {"$lt": cutoff}

    rows = await coll.find(q, {
        "_id": 0, "id": 1, "grn_number": 1, "grn_date": 1, "vendor_id": 1, "vendor_name": 1,
        "project_id": 1, "project_code": 1, "po_id": 1, "po_number": 1,
        "total": 1, "total_amount": 1, "amount": 1, "invoice_received": 1,
    }).sort("grn_date", -1).to_list(1000)

    today = datetime.now(timezone.utc).date()
    out = []
    total_open = 0.0
    for r in rows:
        amt = float(r.get("total") or r.get("total_amount") or r.get("amount") or 0)
        gd = r.get("grn_date") or ""
        try:
            age = (today - datetime.strptime(gd[:10], "%Y-%m-%d").date()).days
        except Exception:
            age = None
        total_open += amt
        out.append({
            "id": r["id"], "grn_number": r.get("grn_number"),
            "grn_date": gd, "age_days": age,
            "vendor_id": r.get("vendor_id"), "vendor_name": r.get("vendor_name"),
            "project_id": r.get("project_id"), "project_code": r.get("project_code"),
            "po_id": r.get("po_id"), "po_number": r.get("po_number"),
            "grn_amount": round(amt, 2),
            "severity": ("critical" if (age or 0) > 60 else "warning" if (age or 0) > 30 else "info"),
        })
    paged = paginate_list(request, out, ["grn_number", "po_number", "vendor_name", "project_code", "status"], "grn_date")
    return {"count": len(out), "total_open_grni": round(total_open, 2), **(paged or {"rows": out})}


# ═════════════════════════════════════════════════════════════════════════
# 4.  BILL-WITHOUT-GRN REPORT (services + expenses + audit)
# ═════════════════════════════════════════════════════════════════════════
@router.get("/reports/bill-without-grn")
async def bill_without_grn(
    request: Request,
    project_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Vendor bills that don't have a linked GRN.

    Expected (informational only): services, AMC, transport, manpower.
    Audit risk: material purchases that bypassed the GRN flow.
    """
    q: Dict[str, Any] = {
        "$or": [
            {"grn_id": None},
            {"grn_id": {"$exists": False}},
            {"grn_number": None},
        ],
        "status": {"$in": ["approved", "pending_approval", "pending_verification"]},
    }
    if project_id:
        q["project_id"] = project_id
    if vendor_id:
        q["vendor_id"] = vendor_id
    rows = await db.vendor_bills.find(q, {
        "_id": 0, "id": 1, "invoice_no": 1, "bill_number": 1, "invoice_date": 1, "bill_date": 1,
        "vendor_id": 1, "vendor_name": 1, "project_id": 1, "project_code": 1,
        "amount": 1, "total_amount": 1, "gross_amount": 1, "status": 1,
        "po_id": 1, "po_number": 1, "is_service": 1, "expense_category": 1,
    }).sort("invoice_date", -1).to_list(1000)

    out = []
    for r in rows:
        amt = float(r.get("amount") or r.get("total_amount") or r.get("gross_amount") or 0)
        out.append({
            "id": r["id"],
            "bill_number": r.get("invoice_no") or r.get("bill_number"),
            "bill_date": r.get("invoice_date") or r.get("bill_date"),
            "vendor_id": r.get("vendor_id"), "vendor_name": r.get("vendor_name"),
            "project_id": r.get("project_id"), "project_code": r.get("project_code"),
            "po_number": r.get("po_number"),
            "amount": round(amt, 2),
            "status": r.get("status"),
            "is_service": bool(r.get("is_service") or (r.get("expense_category") in ("service", "labour", "transport", "consultancy"))),
        })
    audit_risk = [x for x in out if not x["is_service"] and not x.get("po_number")]
    paged = paginate_list(request, out, ["bill_no", "invoice_no", "vendor_name", "po_number", "project_code", "status", "expense_category"], "invoice_date")
    return {"count": len(out), "audit_risk_count": len(audit_risk), **(paged or {"rows": out})}


# ═════════════════════════════════════════════════════════════════════════
# 5.  MATERIAL RETURN → reverse-JE auto-post
# ═════════════════════════════════════════════════════════════════════════
class MaterialReturnPostIn(BaseModel):
    project_id: str
    return_id: Optional[str] = None
    amount: float
    item_name: Optional[str] = None
    return_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/material-return/post-reversal")
async def post_material_return_reversal(payload: MaterialReturnPostIn, request: Request,
                                        user: dict = Depends(require_permission("accounting", "write"))):
    """Reverse the original consumption JE for a returned material.
       DR Inventory   1300
       CR Project Cost — Materials   5100
    Idempotent — using `source_event=return` makes re-runs safe.
    """
    if payload.amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    rid = payload.return_id or new_id()
    je = await post_journal_entry(
        source_module="material_return",
        source_id=rid,
        source_event="return",
        date=payload.return_date or _today(),
        narration=f"Material return — {payload.item_name or 'consumables'} (project {payload.project_id})",
        lines=[
            {"account_code": "1300", "debit":  payload.amount, "credit": 0, "project_id": payload.project_id},
            {"account_code": "5100", "debit": 0, "credit": payload.amount, "project_id": payload.project_id},
        ],
        project_id=payload.project_id,
        voucher_type="JV",
        posted_by=user.get("name") or user.get("email"),
        status="posted",
    )
    await audit(user=user, action="post_reversal", resource="material_return",
                record_id=rid, after={"amount": payload.amount, "je": (je or {}).get("je_number")},
                ip=request.client.host if request.client else "")
    return {"ok": True, "return_id": rid, "je_id": (je or {}).get("id"),
            "je_number": (je or {}).get("je_number"), "amount": payload.amount}


# ═════════════════════════════════════════════════════════════════════════
# 6.  PROJECT-WISE PROCUREMENT COST ROLL-UP (read-only convenience)
# ═════════════════════════════════════════════════════════════════════════
@router.get("/reports/project-procurement-cost")
async def project_procurement_cost(
    project_id: Optional[str] = None,
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Single payload: per-project committed-PO + GRN + approved-bills + paid +
    pending-bills + GRNI.  Drives the integration dashboard."""
    pids: List[str]
    if project_id:
        pids = [project_id]
    else:
        pids = [p["id"] async for p in db.projects.find({"status": {"$ne": "closed"}}, {"_id": 0, "id": 1}).limit(50)]

    out = []
    for pid in pids:
        proj = await db.projects.find_one({"id": pid}, {"_id": 0, "code": 1, "name": 1, "budget_value": 1})
        committed = 0.0
        async for p in db.purchase_orders.find(
            {"project_id": pid, "status": {"$in": ["approved", "partially_received"]}},
            {"_id": 0, "total": 1, "total_amount": 1, "received_value": 1, "amount": 1},
        ):
            total = float(p.get("total") or p.get("total_amount") or p.get("amount") or 0)
            received = float(p.get("received_value") or 0)
            committed += max(total - received, 0)
        approved_bills = 0.0
        pending_bills = 0.0
        async for vb in db.vendor_bills.find({"project_id": pid}, {"_id": 0, "amount": 1, "total_amount": 1, "gross_amount": 1, "status": 1}):
            amt = float(vb.get("amount") or vb.get("total_amount") or vb.get("gross_amount") or 0)
            if vb.get("status") == "approved":
                approved_bills += amt
            elif vb.get("status") in ("pending_verification", "pending_approval", "submitted"):
                pending_bills += amt
        grn_value = 0.0
        async for g in db.goods_receipt_notes.find({"project_id": pid}, {"_id": 0, "total": 1, "total_amount": 1, "amount": 1}):
            grn_value += float(g.get("total") or g.get("total_amount") or g.get("amount") or 0)
        out.append({
            "project_id": pid,
            "project_code": (proj or {}).get("code"),
            "project_name": (proj or {}).get("name"),
            "budget": float((proj or {}).get("budget_value") or 0),
            "po_committed_open": round(committed, 2),
            "grn_received_value": round(grn_value, 2),
            "approved_bills": round(approved_bills, 2),
            "pending_bills": round(pending_bills, 2),
        })
    # sort by spend descending
    out.sort(key=lambda r: r["approved_bills"], reverse=True)
    return {"count": len(out), "rows": out}
