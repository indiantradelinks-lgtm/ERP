"""Executive dashboard aggregation."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core import db, get_current_user

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


async def _monthly_chart(now: datetime) -> list[dict]:
    # Build the last 6 calendar months (inclusive of current) at the YYYY-MM granularity.
    base = now.replace(day=1)
    months: list[str] = []
    y, m = base.year, base.month
    for _ in range(6):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    monthly = {mo: {"revenue": 0.0, "expense": 0.0} for mo in months}
    async for e in db.journal_entries.find({}, {"_id": 0, "type": 1, "amount": 1, "date": 1}):
        d = e.get("date") or ""
        m = d[:7] if isinstance(d, str) else ""
        if m in monthly and e.get("type") in ("revenue", "expense"):
            monthly[m][e["type"]] += float(e.get("amount") or 0)
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
    profit = revenue - expenses

    receivables = await _sum_field(db.quotations.find({"status": "invoiced"}, {"_id": 0, "total": 1}))
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

    return {
        "kpis": {
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "profit": round(profit, 2),
            "receivables": round(receivables, 2),
            "payables": round(payables, 2),
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
