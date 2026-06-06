"""Department-scoped dashboards. Each department gets a focused set of KPIs
returned through a single parameterised endpoint that runs the relevant counts
in parallel.

This is the back-end behind the /app/modules/<dept> workspaces — the "single
window per department" view requested by the master spec.
"""
import asyncio
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends

from core import db, get_current_user

router = APIRouter(tags=["dashboard"])


async def _count(coll: str, q: dict | None = None) -> int:
    return await db[coll].count_documents(q or {})


async def _sum(cursor, field: str = "total") -> float:
    total = 0.0
    async for row in cursor:
        try:
            total += float(row.get(field, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _kpi(label: str, value, tone: str = "neutral", deeplink: str | None = None, format_hint: str = "number") -> dict:
    return {"label": label, "value": value, "tone": tone, "deeplink": deeplink, "format": format_hint}


# Each builder returns {kpis: [...], links: [{label, to, description}]}
async def _sales() -> dict:
    open_states = ["open", "under_review", "submitted", "negotiation"]
    enq_total, enq_open, enq_won, enq_lost, quotes, orders = await asyncio.gather(
        _count("enquiries"),
        _count("enquiries", {"status": {"$in": open_states}}),
        _count("enquiries", {"status": "won"}),
        _count("enquiries", {"status": "lost"}),
        _count("quotations"),
        _count("orders"),
    )
    ord_value = await _sum(db.orders.find({}, {"_id": 0, "contract_value": 1}), "contract_value")
    conversion = round((enq_won / enq_total * 100), 1) if enq_total else 0
    return {
        "kpis": [
            _kpi("Live Enquiries", enq_open, "primary" if enq_open else "neutral", "/app/enquiries"),
            _kpi("Won", enq_won, "success", "/app/enquiries"),
            _kpi("Lost", enq_lost, "danger" if enq_lost else "neutral", "/app/enquiries"),
            _kpi("Quotations", quotes, "info", "/app/quotations"),
            _kpi("Sales Orders", orders, "primary", "/app/orders"),
            _kpi("Order Book", ord_value, "success", "/app/orders", format_hint="currency"),
            _kpi("Conversion %", conversion, "success" if conversion >= 30 else "warning", None, format_hint="percent"),
        ],
        "links": [
            {"label": "Enquiry Pipeline", "to": "/app/enquiries", "description": "Capture leads & track status through to Won/Lost"},
            {"label": "Quotations", "to": "/app/quotations", "description": "Issue quotes, manage revisions"},
            {"label": "Sales Orders", "to": "/app/orders", "description": "Confirmed orders linked to projects"},
            {"label": "Clients & Sites", "to": "/app/clients", "description": "Multi-location customer master with contact directory"},
            {"label": "Client Map", "to": "/app/client-map", "description": "All geo-tagged sites on a single interactive map"},
            {"label": "Client Reports", "to": "/app/client-reports", "description": "Revenue, outstanding, GST and contact analytics"},
            {"label": "Sales Reports", "to": "/app/sales-reports", "description": "Monthly trend, win-rate, deadline tracker, global search"},
        ],
    }


async def _projects() -> dict:
    total, active, planned, completed = await asyncio.gather(
        _count("projects"),
        _count("projects", {"status": "active"}),
        _count("projects", {"status": "planned"}),
        _count("projects", {"status": "completed"}),
    )
    budget = await _sum(db.projects.find({}, {"_id": 0, "budget": 1}), "budget")
    return {
        "kpis": [
            _kpi("Active Projects", active, "primary"),
            _kpi("Planned", planned, "info"),
            _kpi("Completed", completed, "success"),
            _kpi("Total Portfolio", total, "neutral"),
            _kpi("Total Budget", budget, "primary", format_hint="currency"),
        ],
        "links": [
            {"label": "Projects Register", "to": "/app/projects", "description": "All sites & their scope"},
            {"label": "Project Ops & Profitability", "to": "/app/project-ops", "description": "Snapshot · delay/extra-work register · PO expiry & utilisation"},
            {"label": "Daily Site Reports (DPR)", "to": "/app/dprs", "description": "End-of-day site state · digital PC approvals"},
            {"label": "Measurements & Certification", "to": "/app/measurements", "description": "Service-wise executed vs certified qty → RA bills"},
            {"label": "Deployments", "to": "/app/deployments", "description": "Manpower on each site"},
            {"label": "Allocation Reports", "to": "/app/allocation-reports", "description": "Manpower analytics & transfer history"},
            {"label": "Deployment Calendar", "to": "/app/deployment-calendar", "description": "Project × day timeline of all deployments"},
            {"label": "Assets", "to": "/app/assets", "description": "Equipment allocated to projects"},
            {"label": "Reports", "to": "/app/reports", "description": "Operations MIS"},
        ],
    }


async def _accounts() -> dict:
    # Sums
    revenue = await _sum(db.journal_entries.find({"type": "revenue"}, {"_id": 0, "amount": 1}), "amount")
    expense = await _sum(db.journal_entries.find({"type": "expense"}, {"_id": 0, "amount": 1}), "amount")
    receivables = await _sum(db.quotations.find({"status": "invoiced"}, {"_id": 0, "total": 1}), "total")
    invoices_in = await _count("vendor_invoices")
    payable_due = await _sum(db.purchase_orders.find({"status": {"$in": ["approved", "received"]}, "paid": {"$ne": True}}, {"_id": 0, "total": 1}), "total")
    return {
        "kpis": [
            _kpi("Revenue (cumulative)", revenue, "success", "/app/accounts", format_hint="currency"),
            _kpi("Expenses (cumulative)", expense, "warning", "/app/accounts", format_hint="currency"),
            _kpi("Net", revenue - expense, "success" if revenue >= expense else "danger", None, format_hint="currency"),
            _kpi("Receivables", receivables, "primary", "/app/quotations", format_hint="currency"),
            _kpi("Payables Due", payable_due, "danger" if payable_due else "neutral", "/app/purchase-orders", format_hint="currency"),
            _kpi("Vendor Invoices", invoices_in, "info", None),
        ],
        "links": [
            {"label": "Journal Entries", "to": "/app/accounts", "description": "Bookkeeping ledger"},
            {"label": "Running Bills (RA)", "to": "/app/ra-bills", "description": "Issue running / final / supplementary bills · retention · TDS · GST"},
            {"label": "Receivables & Cashflow", "to": "/app/receivables", "description": "Ageing · overdue alerts · client ledger · 30-day inflow"},
            {"label": "Measurements (Bill-ready)", "to": "/app/measurements", "description": "Client-certified quantities ready for RA billing"},
            {"label": "Quotations / Receivables", "to": "/app/quotations", "description": "Customer billing"},
            {"label": "Vendor Invoices", "to": "/app/purchase-orders", "description": "Payables management"},
            {"label": "Reports", "to": "/app/reports", "description": "Financial MIS"},
        ],
    }


async def _finance() -> dict:
    pending, approved, rejected = await asyncio.gather(
        _count("approvals", {"status": "pending"}),
        _count("approvals", {"status": "approved"}),
        _count("approvals", {"status": "rejected"}),
    )
    total_approved_value = await _sum(db.approvals.find({"status": "approved"}, {"_id": 0, "amount": 1}), "amount")
    return {
        "kpis": [
            _kpi("Pending Fund Approvals", pending, "warning" if pending else "neutral", "/app/approvals"),
            _kpi("Approved (lifetime)", approved, "success", "/app/approvals"),
            _kpi("Rejected", rejected, "danger" if rejected else "neutral", "/app/approvals"),
            _kpi("Approved Value", total_approved_value, "primary", "/app/approvals", format_hint="currency"),
        ],
        "links": [
            {"label": "Approvals Inbox", "to": "/app/approvals", "description": "Fund approvals & escalations"},
            {"label": "Cash Flow & MIS", "to": "/app/reports", "description": "Financial reports"},
            {"label": "Cost Centres", "to": "/app/projects", "description": "Project-wise spend"},
        ],
    }


async def _store() -> dict:
    items, low_stock, holds = await asyncio.gather(
        _count("inventory"),
        _count("inventory", {"$expr": {"$lt": ["$quantity", "$min_stock"]}}),
        _count("inventory_transactions", {"status": "awaiting_approval"}),
    )
    inward = await _count("inventory_transactions", {"txn_type": "inward", "status": "posted"})
    outward = await _count("inventory_transactions", {"txn_type": "outward", "status": "posted"})
    return {
        "kpis": [
            _kpi("Inventory Items", items, "neutral", "/app/inventory"),
            _kpi("Low Stock", low_stock, "danger" if low_stock else "success", "/app/inventory"),
            _kpi("Awaiting Approval", holds, "warning" if holds else "neutral", "/app/store-transactions"),
            _kpi("Inward (lifetime)", inward, "success", "/app/store-transactions"),
            _kpi("Outward (lifetime)", outward, "info", "/app/store-transactions"),
        ],
        "links": [
            {"label": "Inventory Register", "to": "/app/inventory", "description": "Master item list"},
            {"label": "Stock Movements", "to": "/app/store-transactions", "description": "Inward / Outward / Transfer / Return / Scrap"},
            {"label": "Inventory Intel", "to": "/app/inventory-intel", "description": "FIFO/LIFO · aging · dead stock · reorder alerts · bulk import"},
            {"label": "Material Allocations", "to": "/app/material-allocations", "description": "Issue/return materials to projects, sites, employees"},
            {"label": "Challans", "to": "/app/challans", "description": "Delivery / Return / Inter-site transfer + QR"},
            {"label": "Approvals (Material Issues)", "to": "/app/approvals", "description": "Outward issues held"},
        ],
    }


async def _safety() -> dict:
    today_30 = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    ptw_open, ptw_total, incidents_open, ppe_due, trainings, toolbox = await asyncio.gather(
        _count("ptws", {"status": "open"}),
        _count("ptws"),
        _count("safety_reports", {"status": {"$nin": ["closed", "resolved"]}}),
        db.ppe_issuance.count_documents({"expiry_date": {"$ne": None, "$lte": today_30}}),
        _count("safety_trainings"),
        _count("toolbox_talks"),
    )
    return {
        "kpis": [
            _kpi("Open Permits", ptw_open, "info" if ptw_open else "neutral", "/app/ptws"),
            _kpi("Open Incidents", incidents_open, "danger" if incidents_open else "success", "/app/safety"),
            _kpi("PPE Due ≤30d", ppe_due, "warning" if ppe_due else "success", "/app/ppe"),
            _kpi("Trainings", trainings, "primary", "/app/safety-trainings"),
            _kpi("Toolbox Talks", toolbox, "primary", "/app/toolbox-talks"),
            _kpi("Total PTW Issued", ptw_total, "neutral", "/app/ptws"),
        ],
        "links": [
            {"label": "Safety Incidents", "to": "/app/safety", "description": "Incident reports & investigations"},
            {"label": "Permits to Work", "to": "/app/ptws", "description": "Hot-work, confined-space, height etc."},
            {"label": "PPE Register", "to": "/app/ppe", "description": "PPE issuance & expiry"},
            {"label": "Safety Trainings", "to": "/app/safety-trainings", "description": "Mandatory training register"},
            {"label": "Toolbox Talks", "to": "/app/toolbox-talks", "description": "Daily site briefings"},
        ],
    }


async def _logistics() -> dict:
    vehicles_total, vehicles_active, accommodations, deployments = await asyncio.gather(
        _count("vehicles"),
        _count("vehicles", {"status": "active"}),
        _count("accommodations"),
        _count("deployments", {"status": "active"}),
    )
    return {
        "kpis": [
            _kpi("Fleet Strength", vehicles_total, "primary", "/app/logistics"),
            _kpi("Active Vehicles", vehicles_active, "success", "/app/logistics"),
            _kpi("Active Deployments", deployments, "info", "/app/deployments"),
            _kpi("Accommodations", accommodations, "primary", "/app/accommodations"),
        ],
        "links": [
            {"label": "Fleet Register", "to": "/app/logistics", "description": "Vehicles, drivers, fuel logs"},
            {"label": "Accommodations", "to": "/app/accommodations", "description": "Camp / room allocation"},
            {"label": "Site Deployments", "to": "/app/deployments", "description": "Active manpower per site"},
        ],
    }


async def _hr() -> dict:
    emps = await _count("employees")
    today = datetime.now(timezone.utc).date().isoformat()
    present, absent = await asyncio.gather(
        _count("attendance", {"date": today, "status": "present"}),
        _count("attendance", {"date": today, "status": "absent"}),
    )
    open_recruit = await _count("recruitment_requests", {"status": {"$nin": ["filled", "closed"]}})
    candidates = await _count("candidates")
    ot_pending = await _count("overtime", {"status": "pending"})
    adv_pending = await _count("employee_advances", {"status": {"$in": ["submitted", "under_approval"]}})
    adv_outstanding_rows = await db.employee_advances.aggregate([
        {"$match": {"outstanding": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$outstanding"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    adv_outstanding_count = adv_outstanding_rows[0]["count"] if adv_outstanding_rows else 0
    return {
        "kpis": [
            _kpi("Headcount", emps, "primary", "/app/employees"),
            _kpi("Present Today", present, "success", "/app/attendance"),
            _kpi("Absent Today", absent, "danger" if absent else "neutral", "/app/attendance"),
            _kpi("Open Vacancies", open_recruit, "warning" if open_recruit else "neutral", "/app/recruitment"),
            _kpi("Candidates", candidates, "info", "/app/candidates"),
            _kpi("OT Pending", ot_pending, "warning" if ot_pending else "neutral", "/app/overtime"),
            _kpi("Advance · Pending Approval", adv_pending, "warning" if adv_pending else "neutral", "/app/hr/advances"),
            _kpi("Advance · Outstanding", adv_outstanding_count, "info" if adv_outstanding_count else "neutral", "/app/hr/advance-recovery"),
        ],
        "links": [
            {"label": "Employees", "to": "/app/employees", "description": "HRMS master"},
            {"label": "Employee 360", "to": "/app/hr/employee-360", "description": "Lifecycle view per employee"},
            {"label": "Onboarding", "to": "/app/hr/onboarding", "description": "New-joiner workflow"},
            {"label": "Attendance", "to": "/app/attendance", "description": "Daily attendance"},
            {"label": "Leave Management", "to": "/app/hr/leave", "description": "Leave application & approvals"},
            {"label": "Payroll (Monthly Run)", "to": "/app/hr/payroll", "description": "Salary processing · attendance preflight · auto EMI deduction"},
            {"label": "Payroll (Legacy)", "to": "/app/payroll", "description": "Legacy payroll register"},
            {"label": "Advance Register", "to": "/app/hr/advances", "description": "Employee advances · request → approval → payment"},
            {"label": "Advance Recovery & Reports", "to": "/app/hr/advance-recovery", "description": "Monthly EMI run · outstanding · aging · bulk import"},
            {"label": "HR Letters & Templates", "to": "/app/hr/letters", "description": "Offer · appointment · confirmation · experience"},
            {"label": "Exit & FNF", "to": "/app/hr/exit", "description": "Resignation · clearance · final settlement"},
            {"label": "Recruitment", "to": "/app/recruitment", "description": "Hiring requisitions"},
            {"label": "Candidates", "to": "/app/candidates", "description": "Applicant pipeline"},
            {"label": "Deployments", "to": "/app/deployments", "description": "Site allocations"},
            {"label": "Accommodations", "to": "/app/accommodations", "description": "Camp management"},
            {"label": "Overtime", "to": "/app/overtime", "description": "OT requests"},
            {"label": "Allocation Reports", "to": "/app/allocation-reports", "description": "Dept-wise · project-wise · utilization · transfers"},
            {"label": "Allocation Board", "to": "/app/allocation-board", "description": "Drag-drop manpower planning"},
        ],
    }


async def _procurement() -> dict:
    vendors_total = await _count("vendors")
    vendors_active = await _count("vendors", {"status": "approved"})
    pos_total, pos_pending = await asyncio.gather(
        _count("purchase_orders"),
        _count("purchase_orders", {"status": {"$in": ["draft", "pending"]}}),
    )
    prs_pending = await _count("purchase_requisitions", {"status": "pending_approval"})
    rfqs_open = await _count("rfqs", {"status": {"$in": ["response_pending", "under_evaluation"]}})
    grn_total = await _count("grn")
    return {
        "kpis": [
            _kpi("Vendor Base", vendors_total, "primary", "/app/vendors"),
            _kpi("PR · Pending", prs_pending, "warning" if prs_pending else "neutral", "/app/purchase-requisitions"),
            _kpi("RFQ · Open", rfqs_open, "info" if rfqs_open else "neutral", "/app/rfqs"),
            _kpi("Pending POs", pos_pending, "warning" if pos_pending else "neutral", "/app/purchase-orders"),
            _kpi("GRN · Total", grn_total, "success", "/app/grn"),
            _kpi("Approved Vendors", vendors_active, "success", "/app/vendors"),
            _kpi("Total POs", pos_total, "neutral", "/app/purchase-orders"),
        ],
        "links": [
            {"label": "Procurement Dashboard", "to": "/app/procurement-dashboard", "description": "Cycle-time KPIs and quick-jumps"},
            {"label": "Purchase Requisitions", "to": "/app/purchase-requisitions", "description": "Multi-item PRs with 5-step approval"},
            {"label": "RFQs", "to": "/app/rfqs", "description": "Multi-vendor RFQ + comparative statement"},
            {"label": "Purchase Orders", "to": "/app/purchase-orders", "description": "RFQ → PO → GRN"},
            {"label": "GRN", "to": "/app/grn", "description": "Goods receipt + auto inventory inward"},
            {"label": "Material Allocations", "to": "/app/material-allocations", "description": "Issue/return materials & assets to projects, sites, employees"},
            {"label": "Asset Lifecycle", "to": "/app/asset-lifecycle", "description": "Depreciation · AMC · Calibration · Warranty"},
            {"label": "Challans", "to": "/app/challans", "description": "Delivery / Return / Inter-site / Vendor return + QR + e-sign"},
            {"label": "Inventory Intel", "to": "/app/inventory-intel", "description": "FIFO/LIFO valuation · aging · dead stock · reorder alerts · bulk import"},
            {"label": "Procurement Intel", "to": "/app/procurement-intel", "description": "Vendor performance · budgets · reservations · audit log"},
            {"label": "Vendor Master", "to": "/app/vendors", "description": "Supplier database"},
            {"label": "Approvals", "to": "/app/approvals", "description": "PR / PO authorisation chain"},
        ],
    }


META = {
    "sales": {"title": "Sales", "tagline": "Lead → Quote → Win → Order", "icon": "FileText", "color": "primary", "builder": _sales},
    "projects": {"title": "Projects & Operations", "tagline": "Plan, deploy, execute, monitor", "icon": "Briefcase", "color": "info", "builder": _projects},
    "accounts": {"title": "Accounts", "tagline": "Billing · Invoices · GST", "icon": "FileText", "color": "success", "builder": _accounts},
    "finance": {"title": "Finance", "tagline": "Budgets · Fund approvals · MIS", "icon": "Wallet", "color": "primary", "builder": _finance},
    "store": {"title": "Store & Inventory", "tagline": "Stock movements, GRN, alerts", "icon": "Boxes", "color": "warning", "builder": _store},
    "safety": {"title": "Safety", "tagline": "PTW, PPE, Incidents, Compliance", "icon": "ShieldAlert", "color": "danger", "builder": _safety},
    "logistics": {"title": "Logistics", "tagline": "Fleet, trips, accommodation", "icon": "Car", "color": "info", "builder": _logistics},
    "hr": {"title": "Human Resources", "tagline": "Attendance, Payroll, Recruitment", "icon": "HardHat", "color": "primary", "builder": _hr},
    "procurement": {"title": "Procurement & Vendors", "tagline": "Vendor registration · RFQ · PO", "icon": "Truck", "color": "info", "builder": _procurement},
}


@router.get("/dashboard/departments")
async def list_departments(user: dict = Depends(get_current_user)):
    """Lightweight list of all departments + a single headline counter each.
    Powers the department launcher tiles.

    Departments shown to the user are filtered by `settings.role_department_map`
    (manageable from /app/admin/role-department-map). super_admin always sees
    everything; an empty map (no entry for the role) also falls back to ALL.
    """
    visible = set(META.keys())
    role = user.get("role")
    if role and role != "super_admin":
        mapping = await _get_role_dept_map()
        depts_for_role = mapping.get(role)
        if depts_for_role:
            visible = set(depts_for_role) & set(META.keys())
        # else: no mapping yet — show all (fail-open during initial config)

    async def _badge(slug: str) -> dict:
        # Headline metric is intentionally aligned with each detail builder's
        # primary KPI so the tile value and the first card inside don't diverge.
        if slug == "sales":
            v = await _count("enquiries", {"status": {"$in": ["open", "under_review", "submitted", "negotiation"]}})
        elif slug == "projects":
            v = await _count("projects", {"status": "active"})
        elif slug == "accounts":
            # Align with the detail "Net" — show pending receivables count instead of total JEs.
            v = await _count("quotations", {"status": "invoiced"})
        elif slug == "finance":
            v = await _count("approvals", {"status": "pending"})
        elif slug == "store":
            v = await _count("inventory", {"$expr": {"$lt": ["$quantity", "$min_stock"]}})
        elif slug == "safety":
            v = await _count("safety_reports", {"status": {"$nin": ["closed", "resolved"]}})
        elif slug == "logistics":
            v = await _count("vehicles")
        elif slug == "hr":
            v = await _count("employees")
        elif slug == "procurement":
            v = await _count("purchase_orders", {"status": {"$in": ["draft", "pending"]}})
        else:
            v = 0
        return {"slug": slug, **META[slug], "headline": v, "builder": None}

    badges = await asyncio.gather(*[_badge(s) for s in META.keys() if s in visible])
    # Strip the un-serialisable builder
    for b in badges:
        b.pop("builder", None)
    return {"departments": badges}


# ---------- Role × Department Matrix (Phase admin) ----------
# Default mapping — used until super_admin customises via the UI.
DEFAULT_ROLE_DEPT_MAP = {
    "director":           list(META.keys()),
    "general_manager":    list(META.keys()),
    "hr_executive":       ["hr", "projects"],
    "dept_head":          ["projects", "safety", "store", "hr", "procurement", "finance"],
    "project_manager":    ["projects", "sales", "store", "safety", "hr"],
    "site_engineer":      ["projects", "safety"],
    "supervisor":         ["projects", "safety", "hr"],
    "store_incharge":     ["store", "procurement"],
    "accounts_executive": ["accounts", "finance"],
    "safety_officer":     ["safety", "projects"],
    "purchase_officer":   ["procurement", "store", "finance"],
    "sales_executive":    ["sales", "accounts"],
}


async def _get_role_dept_map() -> dict:
    doc = await db.settings.find_one({"_id": "role_department_map"})
    if doc and isinstance(doc.get("map"), dict):
        return doc["map"]
    return dict(DEFAULT_ROLE_DEPT_MAP)


@router.get("/admin/role-department-map")
async def get_role_dept_map(user: dict = Depends(get_current_user)):
    """Returns the current Role × Department mapping + the master role + dept lists."""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin only")
    mapping = await _get_role_dept_map()
    # Source the role list from the Role Catalog (iter 42) so that custom
    # roles automatically appear here. Falls back to the default static map
    # if the catalog isn't seeded yet. super_admin is excluded — it always
    # sees every department regardless of this map.
    catalog_rows = await db.role_catalog.find(
        {}, {"_id": 0, "key": 1, "sort_order": 1}
    ).sort("sort_order", 1).to_list(200)
    if catalog_rows:
        role_keys = [r["key"] for r in catalog_rows if r["key"] != "super_admin"]
    else:
        role_keys = list(DEFAULT_ROLE_DEPT_MAP.keys())
    return {
        "map": mapping,
        "roles": role_keys,
        "departments": [{"slug": s, "title": META[s]["title"]} for s in META.keys()],
    }


@router.put("/admin/role-department-map")
async def update_role_dept_map(payload: dict, user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin only")
    new_map = payload.get("map")
    if not isinstance(new_map, dict):
        raise HTTPException(status_code=400, detail="Body must be {map: {role: [dept,...]}}")
    valid_slugs = set(META.keys())
    cleaned: dict[str, list[str]] = {}
    for role, depts in new_map.items():
        if not isinstance(depts, list):
            continue
        cleaned[role] = [d for d in depts if d in valid_slugs]
    await db.settings.update_one(
        {"_id": "role_department_map"},
        {"$set": {"map": cleaned, "updated_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                  "updated_by": user.get("id")}},
        upsert=True,
    )
    return {"map": cleaned}


@router.get("/admin/role-preview/{role}")
async def role_preview(role: str, user: dict = Depends(get_current_user)):
    """Returns the exact Department Launcher tiles a user of `role` would see.
    Used by the Add User dialog to give super_admin a live preview before saving.
    """
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin only")
    mapping = await _get_role_dept_map()
    # A role is "known" if it's the root, has a default mapping, OR exists in
    # the runtime Role Catalog (iter 42). Custom roles without a department
    # mapping fall through to `fallback_all` and see every tile.
    catalog_row = await db.role_catalog.find_one({"key": role}, {"_id": 0, "key": 1})
    known_role = (
        role == "super_admin"
        or role in DEFAULT_ROLE_DEPT_MAP
        or catalog_row is not None
    )
    if role == "super_admin":
        # Note: order matches META insertion order (stable in Python 3.7+).
        visible_slugs = list(META.keys())
    else:
        depts_for_role = mapping.get(role)
        visible_slugs = list(depts_for_role) if depts_for_role else list(META.keys())
        # Keep only slugs that exist in META (drop any stale ones)
        visible_slugs = [s for s in visible_slugs if s in META]
    tiles = [{
        "slug": s,
        "title": META[s]["title"],
        "tagline": META[s]["tagline"],
        "icon": META[s]["icon"],
        "color": META[s]["color"],
    } for s in visible_slugs]
    fallback = role != "super_admin" and not mapping.get(role)
    return {"role": role, "known_role": known_role, "departments": tiles, "fallback_all": fallback}


@router.get("/dashboard/department/{dept}")
async def department_dashboard(dept: str, user: dict = Depends(get_current_user)):
    meta = META.get(dept)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Unknown department '{dept}'")
    payload = await meta["builder"]()
    return {
        "slug": dept,
        "title": meta["title"],
        "tagline": meta["tagline"],
        "icon": meta["icon"],
        "color": meta["color"],
        **payload,
    }
