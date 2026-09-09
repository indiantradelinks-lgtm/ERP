"""Executive dashboard aggregation."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core import db, get_current_user
from accounting_service import ar_aging

router = APIRouter(tags=["dashboard"])


async def _count(collection: str, query: dict | None = None) -> int:
    return await db[collection].count_documents(query or {})


async def _journal_totals() -> tuple[float, float]:
    pipeline = [{"$group": {"_id": "$type", "total": {"$sum": "$amount"}}}]
    sums = {d["_id"]: d["total"] async for d in db.journal_entries.aggregate(pipeline)}
    return float(sums.get("revenue", 0) or 0), float(sums.get("expense", 0) or 0)


async def _sum_field(cursor) -> float:
    total = 0.0
    async for r in cursor:
        total += float(r.get("total", 0) or 0)
    return total


def _six_months(now: datetime) -> list[str]:
    y, m = now.year, now.month
    months: list[str] = []
    for _ in range(6):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    return months


def _six_month_lower(now: datetime) -> str:
    return _six_months(now)[0] + "-01"


async def _monthly_chart(now: datetime) -> list[dict]:
    months = _six_months(now.replace(day=1))
    monthly = {mo: {"revenue": 0.0, "expense": 0.0} for mo in months}
    date_lower = months[0] + "-01"
    async for e in db.journal_entries.find(
        {"date": {"$gte": date_lower}, "type": {"$in": ["revenue", "expense"]}},
        {"_id": 0, "type": 1, "amount": 1, "date": 1},
    ):
        d = e.get("date") or ""
        m = d[:7] if isinstance(d, str) else ""
        if m in monthly:
            monthly[m][e["type"]] += float(e.get("amount") or 0)
    # Operational fallback per series: client invoices → revenue, vendor bills → expense
    ops = {mo: {"revenue": 0.0, "expense": 0.0} for mo in months}
    for coll, key in ((db.client_invoices, "revenue"), (db.vendor_bills, "expense")):
        async for r in coll.find(
            {"status": {"$nin": ["draft", "cancelled", "rejected"]}, "invoice_date": {"$gte": date_lower}},
            {"_id": 0, "invoice_date": 1, "amount": 1},
        ):
            m = (r.get("invoice_date") or "")[:7]
            if m in ops:
                ops[m][key] += float(r.get("amount") or 0)
    je_rev_total = sum(v["revenue"] for v in monthly.values())
    je_exp_total = sum(v["expense"] for v in monthly.values())
    for mo in months:
        if not je_rev_total:
            monthly[mo]["revenue"] = ops[mo]["revenue"]
        if not je_exp_total:
            monthly[mo]["expense"] = ops[mo]["expense"]
    return [
        {"month": mo, "revenue": round(v["revenue"], 2), "expense": round(v["expense"], 2)}
        for mo, v in monthly.items()
    ]


async def _group_count(collection: str, field: str, default_key: str = "unknown", key_alias: str | None = None) -> list[dict]:
    pipeline = [{"$group": {"_id": f"${field}", "count": {"$sum": 1}}}]
    out_key = key_alias or field
    return [
        {out_key: d["_id"] or default_key, "count": d["count"]}
        async for d in db[collection].aggregate(pipeline)
    ]


async def _attendance_today(now: datetime) -> tuple[int, int]:
    today = now.strftime("%Y-%m-%d")
    present = await db.attendance.count_documents({"date": today, "status": "present"})
    absent = await db.attendance.count_documents({"date": today, "status": "absent"})
    return present, absent


@router.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)

    clients = await _count("clients")
    vendors = await _count("vendors")
    employees = await _count("employees")
    projects_total = await _count("projects")
    projects_active = await _count("projects", {"status": "active"})
    inventory_items = await _count("inventory")
    low_stock = await _count("inventory", {"$expr": {"$lt": ["$quantity", "$min_stock"]}})
    pending_pos = await _count("purchase_orders", {"status": {"$in": ["pending", "draft"]}})
    open_quotations = await _count("quotations", {"status": {"$in": ["sent", "draft"]}})
    safety_open = await _count("safety_reports", {"status": {"$ne": "closed"}})
    pending_approvals = await _count("approvals", {"status": "pending"})

    revenue, expenses = await _journal_totals()
    if not revenue:
        # No legacy revenue journals — derive from client invoices (last 6 months)
        date_lower = _six_month_lower(now)
        agg = await db.client_invoices.aggregate([
            {"$match": {"status": {"$nin": ["draft", "cancelled", "rejected"]},
                        "invoice_date": {"$gte": date_lower}}},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$amount", 0]}}}},
        ]).to_list(1)
        revenue = float(agg[0]["total"]) if agg else 0.0
    profit = revenue - expenses

    ar = await ar_aging()
    receivables = float(ar.get("total_outstanding") or 0)
    payables = await _sum_field(
        db.purchase_orders.find(
            {"status": {"$in": ["approved", "received"]}, "paid": {"$ne": True}},
            {"_id": 0, "total": 1},
        )
    )

    chart_revenue_expense = await _monthly_chart(now)
    project_status = await _group_count("projects", "status", default_key="unknown", key_alias="status")
    safety_by_severity = await _group_count("safety_reports", "severity", default_key="low", key_alias="severity")
    present, absent = await _attendance_today(now)

    # Collections MTD
    mtd_start = now.replace(day=1).strftime("%Y-%m-%d")
    coll_agg = await db.client_receipts.aggregate([
        {"$match": {"receipt_date": {"$gte": mtd_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    collections_mtd = float(coll_agg[0]["total"]) if coll_agg else 0.0
    collections_count = int(coll_agg[0]["count"]) if coll_agg else 0

    return {
        "kpis": {
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "profit": round(profit, 2),
            "receivables": round(receivables, 2),
            "payables": round(payables, 2),
            "collections_mtd": round(collections_mtd, 2),
            "collections_count": collections_count,
            "active_projects": projects_active,
            "total_projects": projects_total,
            "employees": employees,
            "clients": clients,
            "vendors": vendors,
            "inventory_items": inventory_items,
            "low_stock_alerts": low_stock,
            "pending_purchase_orders": pending_pos,
            "open_quotations": open_quotations,
            "open_safety_incidents": safety_open,
            "pending_approvals": pending_approvals,
            "attendance_today_present": present,
            "attendance_today_absent": absent,
        },
        "chart_revenue_expense": chart_revenue_expense,
        "project_status": project_status,
        "safety_by_severity": safety_by_severity,
    }


@router.get("/dashboard/operations-pulse")
async def operations_pulse(user: dict = Depends(get_current_user)):
    """Live executive-level "heartbeat" counters spanning every operational module.
    Each entry has a `tone` hint for the UI to colour the card.

    All 7 counters are executed in parallel via asyncio.gather for sub-100ms response.
    """
    from datetime import timedelta as _td
    cutoff_30_iso = (datetime.now(timezone.utc).date() + _td(days=30)).isoformat()

    (
        pending_approvals,
        awaiting_material_issues,
        open_ptws,
        low_stock,
        ppe_due_soon,
        open_enquiries,
        open_safety,
    ) = await asyncio.gather(
        _count("approvals", {"status": {"$in": ["pending", "in_progress"]}}),
        _count("inventory_transactions", {"status": "awaiting_approval"}),
        _count("ptws", {"status": "open"}),
        _count("inventory", {"$expr": {"$lt": ["$quantity", "$min_stock"]}}),
        db.ppe_issuance.count_documents({"expiry_date": {"$ne": None, "$lte": cutoff_30_iso}}),
        _count("enquiries", {"status": {"$in": ["open", "under_review", "submitted", "negotiation"]}}),
        _count("safety_reports", {"status": {"$nin": ["closed", "resolved"]}}),
    )

    cards = [
        {"key": "pending_approvals", "label": "Pending Approvals", "value": pending_approvals, "tone": "warning" if pending_approvals else "neutral", "deeplink": "/app/approvals"},
        {"key": "material_issue_holds", "label": "Material Issues Held", "value": awaiting_material_issues, "tone": "warning" if awaiting_material_issues else "neutral", "deeplink": "/app/store-transactions"},
        {"key": "open_ptws", "label": "Open Permits", "value": open_ptws, "tone": "info" if open_ptws else "neutral", "deeplink": "/app/ptws"},
        {"key": "low_stock", "label": "Low Stock Items", "value": low_stock, "tone": "danger" if low_stock else "success", "deeplink": "/app/inventory"},
        {"key": "ppe_due", "label": "PPE Due ≤30d", "value": ppe_due_soon, "tone": "warning" if ppe_due_soon else "success", "deeplink": "/app/ppe"},
        {"key": "open_enquiries", "label": "Live Enquiries", "value": open_enquiries, "tone": "primary" if open_enquiries else "neutral", "deeplink": "/app/enquiries"},
        {"key": "open_safety", "label": "Safety Incidents", "value": open_safety, "tone": "danger" if open_safety else "success", "deeplink": "/app/safety"},
    ]
    return {"as_of": datetime.now(timezone.utc).isoformat(), "cards": cards}
