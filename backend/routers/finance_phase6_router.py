"""Finance Phase 6 — Compliance dashboard, calendar, and challan tracker (Iter 113).

Audit-first finding: the building blocks are all already in place —
  • GST Sales Register     billing_router /reports/gst-sales-register
  • GST Purchase Register  vendor_billing_router /reports/gst-purchase-register
  • TDS Receivable         billing_router /reports/tds-receivable
  • TDS Payable            vendor_billing_router /reports/tds-payable
  • GSTR-1 / GSTR-3B       statutory_router /gst/gstr-1, /gst/gstr-3b
  • TDS 26AS               statutory_router /tds/26as/upload, /match
  • Statutory Summary      finance_phase4_5_router /statutory-summary

What was missing (this iteration fills):
  1. Compliance Dashboard      — single consolidated KPI payload
  2. Compliance Calendar       — Indian tax due dates auto-computed per period
                                 (GSTR-1 → 11th, GSTR-3B → 20th, TDS → 7th,
                                 PF → 15th, ESIC → 15th, Adv Tax → 15th of
                                 Jun/Sep/Dec/Mar, ITR → 31 Jul / 31 Oct)
  3. Compliance Items / Challans CRUD — track each filing / payment with
                                 due_date, paid_date, challan_number, status
"""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, new_id, now_iso
from audit import audit

router = APIRouter(prefix="/finance/compliance", tags=["finance-phase6"])


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _ym(d: date) -> str:
    return d.strftime("%Y-%m")


def _last_month_ym() -> str:
    t = _today().replace(day=1) - timedelta(days=1)
    return _ym(t)


# ═════════════════════════════════════════════════════════════════════════
# 1. COMPLIANCE DASHBOARD
# ═════════════════════════════════════════════════════════════════════════
@router.get("/dashboard")
async def compliance_dashboard(
    period: Optional[str] = None,  # YYYY-MM, defaults to last month
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Single payload aggregating GST / TDS / PF / ESIC for management."""
    period = period or _last_month_ym()
    start = f"{period}-01"
    # period end = last day of month
    y, m = period.split("-")
    next_m = int(m) % 12 + 1
    next_y = int(y) + (1 if next_m == 1 else 0)
    end = (date(next_y, next_m, 1) - timedelta(days=1)).strftime("%Y-%m-%d")

    STATUTORY_CODES = {
        "2220": "PF Payable",
        "2230": "ESIC Payable",
        "2400": "TDS Payable",
        "2300": "GST Output",
        "1700": "GST Input",
    }

    # Sum across journal_entries
    sums: Dict[str, Dict[str, float]] = {c: {"accrued": 0.0, "paid": 0.0} for c in STATUTORY_CODES}
    async for je in db.journal_entries.find(
        {"date": {"$gte": start, "$lte": end}, "lines.account_code": {"$in": list(STATUTORY_CODES.keys())}},
        {"_id": 0, "lines": 1},
    ):
        for ln in je.get("lines") or []:
            code = ln.get("account_code")
            if code in STATUTORY_CODES:
                sums[code]["accrued"] += float(ln.get("credit") or 0)
                sums[code]["paid"] += float(ln.get("debit") or 0)

    gst_output = sums["2300"]
    gst_input = sums["1700"]
    gst_net_payable = round(gst_output["accrued"] - gst_input["accrued"], 2)

    # TDS receivable (= TDS deducted by clients on receipts)
    tds_rec_due = 0.0
    async for inv in db.client_invoices.find(
        {"status": "approved", "tds_amount": {"$gt": 0}},
        {"_id": 0, "tds_amount": 1, "tds_reconciled": 1},
    ):
        if not inv.get("tds_reconciled"):
            tds_rec_due += float(inv.get("tds_amount") or 0)

    # Compliance items for this period
    items = await db.compliance_items.find(
        {"period": period}, {"_id": 0}
    ).sort("due_date", 1).to_list(50)
    paid_count = sum(1 for i in items if i.get("status") == "paid")
    pending_count = sum(1 for i in items if i.get("status") in ("pending", "overdue"))
    overdue_count = sum(1 for i in items if i.get("status") == "overdue")

    return {
        "period": period,
        "period_start": start,
        "period_end": end,
        "gst": {
            "output_accrued": round(gst_output["accrued"], 2),
            "input_credit": round(gst_input["accrued"], 2),
            "net_payable": gst_net_payable,
            "paid": round(gst_output["paid"] - gst_input["paid"], 2),
        },
        "tds": {
            "payable_accrued": round(sums["2400"]["accrued"], 2),
            "payable_paid": round(sums["2400"]["paid"], 2),
            "payable_balance": round(sums["2400"]["accrued"] - sums["2400"]["paid"], 2),
            "receivable_due": round(tds_rec_due, 2),
        },
        "pf": {
            "accrued": round(sums["2220"]["accrued"], 2),
            "paid": round(sums["2220"]["paid"], 2),
            "balance": round(sums["2220"]["accrued"] - sums["2220"]["paid"], 2),
        },
        "esic": {
            "accrued": round(sums["2230"]["accrued"], 2),
            "paid": round(sums["2230"]["paid"], 2),
            "balance": round(sums["2230"]["accrued"] - sums["2230"]["paid"], 2),
        },
        "items_summary": {
            "total": len(items),
            "paid": paid_count,
            "pending": pending_count - overdue_count,
            "overdue": overdue_count,
        },
    }


# ═════════════════════════════════════════════════════════════════════════
# 2. COMPLIANCE CALENDAR — Indian tax due dates
# ═════════════════════════════════════════════════════════════════════════
def _compute_calendar(period: str) -> List[Dict[str, Any]]:
    """Indian statutory due dates for a YYYY-MM period."""
    y, m = period.split("-")
    y, m = int(y), int(m)
    # Filings are for THIS period, but due dates fall in NEXT month
    nxt_m = m % 12 + 1
    nxt_y = y + (1 if nxt_m == 1 else 0)

    def fmt(yy, mm, dd):
        return f"{yy:04d}-{mm:02d}-{dd:02d}"

    items = [
        {"kind": "tds_payment",  "label": f"TDS Payment ({period})",      "due_date": fmt(nxt_y, nxt_m, 7),
         "section": "TDS · monthly challan (Form 281)", "frequency": "monthly"},
        {"kind": "gstr_1",       "label": f"GSTR-1 filing ({period})",    "due_date": fmt(nxt_y, nxt_m, 11),
         "section": "GST Returns", "frequency": "monthly"},
        {"kind": "pf_payment",   "label": f"PF Challan ({period})",       "due_date": fmt(nxt_y, nxt_m, 15),
         "section": "EPFO ECR", "frequency": "monthly"},
        {"kind": "esic_payment", "label": f"ESIC Challan ({period})",     "due_date": fmt(nxt_y, nxt_m, 15),
         "section": "ESIC Portal", "frequency": "monthly"},
        {"kind": "gstr_3b",      "label": f"GSTR-3B filing ({period})",   "due_date": fmt(nxt_y, nxt_m, 20),
         "section": "GST Returns", "frequency": "monthly"},
        {"kind": "professional_tax", "label": f"Professional Tax ({period})", "due_date": fmt(nxt_y, nxt_m, 21),
         "section": "State PT", "frequency": "monthly"},
    ]
    # Quarterly advance tax
    if m in (3, 6, 9, 12):
        items.append({"kind": "advance_tax", "label": f"Advance Tax ({period})",
                      "due_date": fmt(y, m, 15), "section": "Income Tax · 234B", "frequency": "quarterly"})
    # Annual ITR (filing for the previous FY happens in Jul of the next FY)
    if (m, 1) == (7, 1):
        items.append({"kind": "itr", "label": "Income Tax Return (non-audit)",
                      "due_date": fmt(y, 7, 31), "section": "IT Department", "frequency": "annual"})
    if (m, 1) == (10, 1):
        items.append({"kind": "itr_audit", "label": "Income Tax Return (audit)",
                      "due_date": fmt(y, 10, 31), "section": "IT Department", "frequency": "annual"})
    return items


@router.get("/calendar")
async def compliance_calendar(
    period: Optional[str] = None,
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Auto-computed Indian compliance calendar for a YYYY-MM period.

    Cross-references db.compliance_items to mark filings as paid where the
    user has already recorded the challan.
    """
    period = period or _last_month_ym()
    items = _compute_calendar(period)
    paid_map: Dict[str, Dict[str, Any]] = {}
    async for r in db.compliance_items.find({"period": period}, {"_id": 0}):
        paid_map[r.get("kind")] = r

    today = _today().strftime("%Y-%m-%d")
    for it in items:
        existing = paid_map.get(it["kind"])
        if existing:
            it["status"] = existing.get("status") or "pending"
            it["paid_date"] = existing.get("paid_date")
            it["challan_number"] = existing.get("challan_number")
            it["amount"] = existing.get("amount")
            it["item_id"] = existing.get("id")
        else:
            it["status"] = "overdue" if it["due_date"] < today else "pending"
            it["item_id"] = None
    return {"period": period, "today": today, "items": items}


# ═════════════════════════════════════════════════════════════════════════
# 3. COMPLIANCE ITEMS — challan / filing tracker
# ═════════════════════════════════════════════════════════════════════════
class ComplianceItemIn(BaseModel):
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    kind: str  # tds_payment | gstr_1 | gstr_3b | pf_payment | esic_payment | advance_tax | itr | professional_tax | other
    label: Optional[str] = None
    due_date: str
    amount: Optional[float] = None
    challan_number: Optional[str] = None
    paid_date: Optional[str] = None
    paid_through: Optional[str] = None
    attachments: List[Dict[str, Any]] = []
    notes: Optional[str] = None


@router.get("/items")
async def list_items(period: Optional[str] = None, status: Optional[str] = None,
                     user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if period:
        q["period"] = period
    if status:
        q["status"] = status
    rows = await db.compliance_items.find(q, {"_id": 0}).sort("due_date", -1).to_list(500)
    return rows


@router.post("/items")
async def upsert_item(payload: ComplianceItemIn, request: Request,
                      user: dict = Depends(require_permission("accounting", "write"))):
    """Create or update a compliance item — idempotent on (period, kind)."""
    today = _today().strftime("%Y-%m-%d")
    paid = bool(payload.paid_date and payload.challan_number)
    status = "paid" if paid else ("overdue" if payload.due_date < today else "pending")

    existing = await db.compliance_items.find_one({"period": payload.period, "kind": payload.kind}, {"_id": 0})
    doc = payload.model_dump()
    doc["status"] = status
    doc["updated_at"] = now_iso()
    doc["updated_by"] = user.get("name") or user.get("email")

    if existing:
        await db.compliance_items.update_one(
            {"id": existing["id"]},
            {"$set": doc},
        )
        doc["id"] = existing["id"]
        action = "update"
    else:
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        doc["created_by"] = user.get("name") or user.get("email")
        await db.compliance_items.insert_one(doc)
        action = "create"
    doc.pop("_id", None)

    await audit(user=user, action=action, resource="compliance_items",
                record_id=doc["id"], after=doc,
                ip=request.client.host if request.client else "")
    return doc


@router.post("/items/{item_id}/mark-paid")
async def mark_paid(item_id: str, challan_number: str, paid_date: str,
                    amount: Optional[float] = None,
                    request: Request = None,
                    user: dict = Depends(require_permission("accounting", "write"))):
    item = await db.compliance_items.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Compliance item not found")
    patch: Dict[str, Any] = {
        "status": "paid",
        "challan_number": challan_number,
        "paid_date": paid_date,
        "paid_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    if amount is not None:
        patch["amount"] = float(amount)
    await db.compliance_items.update_one({"id": item_id}, {"$set": patch})
    await audit(user=user, action="mark_paid", resource="compliance_items",
                record_id=item_id, after=patch,
                ip=request.client.host if request and request.client else "")
    return {"ok": True, "item_id": item_id, "status": "paid"}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, request: Request,
                      user: dict = Depends(require_permission("accounting", "write"))):
    if user.get("role") not in ("super_admin", "director", "accounts_manager"):
        raise HTTPException(403, "Insufficient role")
    res = await db.compliance_items.delete_one({"id": item_id})
    if not res.deleted_count:
        raise HTTPException(404, "Compliance item not found")
    await audit(user=user, action="delete", resource="compliance_items",
                record_id=item_id, ip=request.client.host if request.client else "")
    return {"ok": True}
