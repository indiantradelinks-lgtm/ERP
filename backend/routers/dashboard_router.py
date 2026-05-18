"""Executive dashboard aggregation."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

from core import db, get_current_user

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    async def count(col):
        return await db[col].count_documents({})

    clients = await count("clients")
    vendors = await count("vendors")
    employees = await count("employees")
    projects_total = await count("projects")
    projects_active = await db.projects.count_documents({"status": "active"})
    inventory_items = await count("inventory")
    low_stock = await db.inventory.count_documents({"$expr": {"$lt": ["$quantity", "$min_stock"]}})
    pending_pos = await db.purchase_orders.count_documents({"status": {"$in": ["pending", "draft"]}})
    open_quotations = await db.quotations.count_documents({"status": {"$in": ["sent", "draft"]}})
    safety_open = await db.safety_reports.count_documents({"status": {"$ne": "closed"}})
    pending_approvals = await db.approvals.count_documents({"status": "pending"})

    pipeline = [{"$group": {"_id": "$type", "total": {"$sum": "$amount"}}}]
    sums = {d["_id"]: d["total"] async for d in db.journal_entries.aggregate(pipeline)}
    revenue = float(sums.get("revenue", 0) or 0)
    expenses = float(sums.get("expense", 0) or 0)
    profit = revenue - expenses

    receivables = 0.0
    async for r in db.quotations.find({"status": "invoiced"}, {"_id": 0, "total": 1}):
        receivables += float(r.get("total", 0) or 0)
    payables = 0.0
    async for p in db.purchase_orders.find({"status": {"$in": ["approved", "received"]}, "paid": {"$ne": True}}, {"_id": 0, "total": 1}):
        payables += float(p.get("total", 0) or 0)

    months = []
    now = datetime.now(timezone.utc)
    for i in range(5, -1, -1):
        m = (now.replace(day=1) - timedelta(days=30 * i))
        months.append(m.strftime("%Y-%m"))
    monthly = {m: {"revenue": 0.0, "expense": 0.0} for m in months}
    async for e in db.journal_entries.find({}, {"_id": 0, "type": 1, "amount": 1, "date": 1}):
        d = e.get("date") or ""
        m = d[:7] if isinstance(d, str) else ""
        if m in monthly and e.get("type") in ("revenue", "expense"):
            monthly[m][e["type"]] += float(e.get("amount") or 0)
    chart_revenue_expense = [
        {"month": m, "revenue": round(v["revenue"], 2), "expense": round(v["expense"], 2)}
        for m, v in monthly.items()
    ]

    proj_pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    project_status = [{"status": d["_id"] or "unknown", "count": d["count"]} async for d in db.projects.aggregate(proj_pipeline)]

    today = now.strftime("%Y-%m-%d")
    present = await db.attendance.count_documents({"date": today, "status": "present"})
    absent = await db.attendance.count_documents({"date": today, "status": "absent"})

    sev_pipeline = [{"$group": {"_id": "$severity", "count": {"$sum": 1}}}]
    safety_by_severity = [{"severity": d["_id"] or "low", "count": d["count"]} async for d in db.safety_reports.aggregate(sev_pipeline)]

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
