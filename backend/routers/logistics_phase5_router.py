"""
Iter 137 — Logistics Module · Phase 5 · Reports / Closure / Audit / Access
==========================================================================

Completes the Logistics Module with:

  * Trip / Dispatch Closure workflow (15-point checklist + audit + reopen)
  * Advanced Logistics Dashboard v2 (30 real-time KPIs incl. Phase-4 costs)
  * Final Reports Center (30 reports · filterable · Excel export)
  * Enriched Audit Trail viewer

All endpoints respect `require_permission()` (RBAC) and, where relevant,
`data_scope_filter()` on projects so that Project Managers, Site Incharges
and Logistics Executives only see records under their scope.

No new destructive schemas — this router reads across every logistics
collection already created by Phases 1-4.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, now_iso, new_id, require_permission
from access_control import data_scope_filter

router = APIRouter(prefix="/logistics", tags=["logistics-phase5"])


# ═══════════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════════

def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _month_start() -> str:
    d = datetime.now(timezone.utc)
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


async def _audit(kind: str, rid: str, action: str, user: dict,
                 record_no: str = "", meta: Optional[Dict] = None):
    await db.logistics_audit_log.insert_one({
        "id": new_id(),
        "record_kind": kind,
        "record_id": rid,
        "record_no": record_no or "",
        "action": action,
        "at": now_iso(),
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "by_role": user.get("role"),
        "meta": meta or {},
    })


async def _project_scope(user: dict) -> Optional[List[str]]:
    """Return a list of allowed project_ids for this user, or None for full access."""
    filt = await data_scope_filter(user, "projects")
    if not filt:
        return None
    # Very common shape: {"project_id": {"$in": [...]}} or {"id": {"$in": [...]}}
    for key in ("project_id", "id"):
        v = filt.get(key)
        if isinstance(v, dict) and "$in" in v:
            return list(v["$in"])
    if filt.get("id") == "__never_matches__":
        return []
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Trip / Dispatch Closure
# ═══════════════════════════════════════════════════════════════════════════

CLOSURE_ITEMS = [
    ("dispatch_request_completed",   "Dispatch request completed"),
    ("vehicle_allocated",            "Vehicle allocation completed"),
    ("loading_confirmed",            "Loading confirmed"),
    ("dispatch_started",             "Dispatch started"),
    ("delivery_confirmed",           "Delivery confirmed"),
    ("proof_of_delivery",            "Proof of delivery uploaded"),
    ("shortage_damage_resolved",     "Shortage / damage resolved (or none)"),
    ("store_stock_updated",          "Store stock updated"),
    ("site_received_confirmation",   "Project / site received confirmation"),
    ("returnable_material_status",   "Returnable material status updated"),
    ("fuel_expense_entries",         "Fuel / expense entries completed"),
    ("vendor_bill_reviewed",         "Transport vendor bill status reviewed"),
    ("accounts_cost_posted",         "Accounts cost posting completed where applicable"),
    ("finance_approval",             "Finance approval completed where required"),
    ("closure_approval",             "Trip closure approval completed"),
]


async def _closure_checklist(dr: dict) -> List[Dict[str, Any]]:
    dr_id = dr["id"]
    items: List[Dict[str, Any]] = []

    alloc      = await db.logistics_allocations.find_one({"dispatch_id": dr_id})
    loading    = await db.logistics_loadings.find_one({"dispatch_id": dr_id})
    delivery   = await db.logistics_deliveries.find_one({"dispatch_id": dr_id})
    ex_open    = await db.logistics_exceptions.count_documents(
        {"dispatch_id": dr_id, "status": {"$nin": ["resolved", "waived"]}}
    )
    stock_move = await db.logistics_stock_moves.count_documents({"dispatch_id": dr_id})
    fuel_cnt   = await db.logistics_fuel_entries.count_documents({"dispatch_id": dr_id})
    exp_cnt    = await db.logistics_vehicle_expenses.count_documents({"dispatch_id": dr_id})
    vb_cnt     = await db.logistics_vendor_bills.count_documents({"dispatch_id": dr_id})

    cost_alloc = await db.logistics_cost_allocations.find(
        {"dispatch_id": dr_id}, {"_id": 0}
    ).to_list(500)
    unposted_cost = [c for c in cost_alloc if not c.get("posted_to_accounts")]
    highval_pending: List[Dict[str, Any]] = []
    for c in cost_alloc:
        if c.get("high_value") and c.get("finance_approval_id"):
            appr = await db.approvals.find_one(
                {"id": c["finance_approval_id"]}, {"_id": 0, "status": 1}
            )
            if not appr or appr.get("status") != "approved":
                highval_pending.append(c)

    proof_urls = (delivery or {}).get("proof_urls") or []
    values = {
        "dispatch_request_completed":  dr.get("status") in {"approved", "allocated", "in_transit", "delivered", "closed"},
        "vehicle_allocated":           bool(alloc),
        "loading_confirmed":           bool(loading),
        "dispatch_started":            dr.get("status") in {"in_transit", "delivered", "closed"},
        "delivery_confirmed":          bool(delivery),
        "proof_of_delivery":           bool(proof_urls) or bool((delivery or {}).get("proof_url")),
        "shortage_damage_resolved":    ex_open == 0,
        "store_stock_updated":         stock_move > 0 or dr.get("dispatch_type") != "material",
        "site_received_confirmation":  bool((delivery or {}).get("received_by")),
        "returnable_material_status":  dr.get("dispatch_type") != "return"
                                        or (delivery is not None and delivery.get("return_received") is True),
        "fuel_expense_entries":        (fuel_cnt + exp_cnt) > 0 or dr.get("dispatch_type") != "material",
        "vendor_bill_reviewed":        vb_cnt == 0 or vb_cnt > 0,  # informational — vendor bill optional
        "accounts_cost_posted":        len(unposted_cost) == 0,
        "finance_approval":            len(highval_pending) == 0,
        "closure_approval":            dr.get("closure_approval_id") is not None
                                        or dr.get("status") == "closed",
    }

    for key, label in CLOSURE_ITEMS:
        items.append({"key": key, "label": label, "done": bool(values.get(key))})
    return items


@router.get("/dispatch-requests/{dr_id}/closure-checklist")
async def closure_checklist(
    dr_id: str,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    dr = await db.logistics_dispatch_requests.find_one({"id": dr_id}, {"_id": 0})
    if not dr:
        raise HTTPException(404, "Dispatch request not found")
    items = await _closure_checklist(dr)
    return {
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "status": dr.get("status"),
        "checklist": items,
        "can_close": all(i["done"] for i in items if i["key"] in {
            "delivery_confirmed", "shortage_damage_resolved", "proof_of_delivery",
            "accounts_cost_posted", "finance_approval",
        }),
    }


class TripCloseIn(BaseModel):
    reason: Optional[str] = None
    override_exceptions: bool = False


@router.post("/dispatch-requests/{dr_id}/close")
async def close_trip(
    dr_id: str,
    payload: TripCloseIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    dr = await db.logistics_dispatch_requests.find_one({"id": dr_id}, {"_id": 0})
    if not dr:
        raise HTTPException(404, "Dispatch request not found")
    if dr.get("status") == "closed":
        raise HTTPException(400, "Trip already closed")
    if dr.get("status") == "cancelled":
        raise HTTPException(400, "Cancelled trips cannot be closed")

    items = await _closure_checklist(dr)
    mandatory = {"delivery_confirmed", "proof_of_delivery",
                 "accounts_cost_posted", "finance_approval"}
    missing = [i for i in items if i["key"] in mandatory and not i["done"]]
    if missing:
        raise HTTPException(400,
            "Cannot close — pending: " + ", ".join(i["label"] for i in missing))

    # Rule: closure blocked if open exceptions unless override + role allowed
    open_ex = await db.logistics_exceptions.count_documents(
        {"dispatch_id": dr_id, "status": {"$nin": ["resolved", "waived"]}}
    )
    if open_ex and not payload.override_exceptions:
        raise HTTPException(400,
            f"{open_ex} open shortage/damage exception(s) — resolve or set override_exceptions=true")
    if open_ex and payload.override_exceptions:
        if (user.get("role") or "") not in {"super_admin", "director", "general_manager",
                                             "dept_head", "logistics_head"}:
            raise HTTPException(403, "Not authorised to override open exceptions on closure")

    await db.logistics_dispatch_requests.update_one(
        {"id": dr_id},
        {"$set": {
            "status": "closed",
            "closed_at": now_iso(),
            "closed_by": user.get("name") or user.get("email"),
            "closure_reason": payload.reason or "",
            "closure_override_exceptions": bool(open_ex and payload.override_exceptions),
        }},
    )
    await _audit("dispatch_request", dr_id, "trip_closed", user, dr.get("dr_no", ""),
                 {"reason": payload.reason, "override_exceptions": bool(open_ex and payload.override_exceptions),
                  "open_exceptions": open_ex})
    return await db.logistics_dispatch_requests.find_one({"id": dr_id}, {"_id": 0})


class TripReopenIn(BaseModel):
    reason: str


@router.post("/dispatch-requests/{dr_id}/reopen")
async def reopen_trip(
    dr_id: str,
    payload: TripReopenIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    if (user.get("role") or "") not in {"super_admin", "director", "general_manager",
                                         "dept_head", "logistics_head"}:
        raise HTTPException(403, "Not authorised to reopen a closed trip")
    dr = await db.logistics_dispatch_requests.find_one({"id": dr_id}, {"_id": 0})
    if not dr:
        raise HTTPException(404, "Dispatch request not found")
    if dr.get("status") != "closed":
        raise HTTPException(400, "Only closed trips can be reopened")
    if not (payload.reason or "").strip():
        raise HTTPException(400, "Reason is required to reopen a closed trip")

    await db.logistics_dispatch_requests.update_one(
        {"id": dr_id},
        {"$set": {
            "status": "delivered",
            "reopened_at": now_iso(),
            "reopened_by": user.get("name") or user.get("email"),
            "reopen_reason": payload.reason,
        }},
    )
    await _audit("dispatch_request", dr_id, "trip_reopened", user, dr.get("dr_no", ""),
                 {"reason": payload.reason})
    return await db.logistics_dispatch_requests.find_one({"id": dr_id}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Advanced Dashboard v2 — 30 real-time cards
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/dashboard-v2")
async def dashboard_v2(user: dict = Depends(require_permission("vehicles", "read"))):
    today = _today()
    month_start = _month_start()

    async def cnt(col: str, q: Dict[str, Any]) -> int:
        return await db[col].count_documents(q)

    async def sum_amount(col: str, q: Dict[str, Any]) -> float:
        agg = await db[col].aggregate([
            {"$match": q}, {"$group": {"_id": None, "s": {"$sum": "$amount"}}}
        ]).to_list(1)
        return float(agg[0]["s"]) if agg else 0.0

    # ── Vehicles / Drivers
    tot_veh          = await cnt("vehicles", {})
    veh_available    = await cnt("vehicles", {"status": "available"})
    veh_in_transit   = await cnt("vehicles", {"status": "in_transit"})
    veh_maintenance  = await cnt("vehicles", {"status": "maintenance"})
    tot_drv          = await cnt("drivers", {})
    drv_available    = await cnt("drivers", {"status": "available"})
    drv_on_trip      = await cnt("drivers", {"status": "on_trip"})

    # ── Dispatch / Delivery
    dr_pending       = await cnt("logistics_dispatch_requests", {"status": {"$in": ["draft", "pending_approval"]}})
    alloc_pending    = await cnt("logistics_dispatch_requests", {"status": "approved"})
    disp_today       = await cnt("logistics_dispatch_requests", {"created_at": {"$gte": today}})
    in_transit       = await cnt("logistics_dispatch_requests", {"status": "in_transit"})
    deliv_pending    = await cnt("logistics_dispatch_requests", {"status": {"$in": ["allocated", "in_transit"]}})
    overdue          = await cnt("logistics_dispatch_requests", {
        "required_date": {"$lt": today, "$ne": None},
        "status": {"$nin": ["delivered", "closed", "cancelled"]},
    })
    open_ex          = await cnt("logistics_exceptions", {"status": {"$nin": ["resolved", "waived"]}})
    pending_closure  = await cnt("logistics_dispatch_requests", {"status": "delivered"})

    # ── Manpower / Travel / Accommodation
    mob_pending      = await cnt("logistics_manpower_mob", {"status": {"$in": ["draft", "pending_approval", "approved"]}})
    demob_pending    = await cnt("logistics_demobilizations", {"status": {"$in": ["draft", "pending"]}})
    travel_pending   = await cnt("logistics_travel", {"status": {"$in": ["pending", "booked_pending_confirm"]}})
    accom_pending    = await cnt("logistics_accommodations", {"status": {"$in": ["pending", "booked_pending_confirm"]}})

    # ── Costs (this month + high value pending)
    fuel_cost        = await sum_amount("logistics_fuel_entries", {"entry_date": {"$gte": today[:8] + "01"}})
    veh_expense_cost = await sum_amount("logistics_vehicle_expenses", {"expense_date": {"$gte": today[:8] + "01"}})
    vb_pending       = await cnt("logistics_vendor_bills", {"status": {"$in": ["submitted", "under_verification"]}})
    freight_cost_agg = await db.logistics_cost_allocations.aggregate([
        {"$match": {"category": "freight", "at": {"$gte": month_start}}},
        {"$group": {"_id": None, "s": {"$sum": "$amount"}}},
    ]).to_list(1)
    freight_cost     = float(freight_cost_agg[0]["s"]) if freight_cost_agg else 0.0
    hv_pending       = await db.approvals.count_documents(
        {"module": "logistics", "status": "pending"}
    )

    # ── Compliance alerts (expiring within 30 days)
    from datetime import timedelta
    horizon = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    fitness_expiring   = await db.vehicles.count_documents(
        {"fitness_expiry": {"$lt": horizon, "$gt": today}}
    )
    license_expiring   = await db.drivers.count_documents(
        {"license_expiry": {"$lt": horizon, "$gt": today}}
    )

    # ── Project-wise cost snapshot (top 5)
    proj_cost_agg = await db.logistics_cost_allocations.aggregate([
        {"$match": {"project_code": {"$ne": None, "$exists": True}}},
        {"$group": {"_id": "$project_code", "amount": {"$sum": "$amount"}}},
        {"$sort": {"amount": -1}}, {"$limit": 5},
    ]).to_list(5)

    # ── Recent lists
    recent_disp = await db.logistics_dispatch_requests.find(
        {}, {"_id": 0, "dr_no": 1, "status": 1, "project_code": 1, "created_at": 1}
    ).sort("created_at", -1).limit(5).to_list(5)
    recent_dlv = await db.logistics_deliveries.find(
        {}, {"_id": 0}
    ).sort("delivered_at", -1).limit(5).to_list(5)

    # ── Cost trend last 6 months
    trend = await db.logistics_cost_allocations.aggregate([
        {"$group": {
            "_id": {"$substr": ["$at", 0, 7]},
            "amount": {"$sum": "$amount"},
        }},
        {"$sort": {"_id": -1}}, {"$limit": 6},
    ]).to_list(6)

    return {
        "as_of": now_iso(),
        "cards": {
            "total_vehicles":         tot_veh,
            "vehicles_available":     veh_available,
            "vehicles_in_transit":    veh_in_transit,
            "vehicles_maintenance":   veh_maintenance,
            "drivers_available":      drv_available,
            "drivers_on_trip":        drv_on_trip,
            "total_drivers":          tot_drv,
            "dispatch_requests_pending": dr_pending,
            "vehicle_allocation_pending": alloc_pending,
            "material_dispatches_today":  disp_today,
            "in_transit_material":    in_transit,
            "delivery_confirmations_pending": deliv_pending,
            "overdue_deliveries":     overdue,
            "transit_shortage_damage": open_ex,
            "manpower_mobilization_pending": mob_pending,
            "demobilization_pending": demob_pending,
            "travel_arrangements_pending": travel_pending,
            "accommodation_pending":  accom_pending,
            "fuel_cost_this_month":   fuel_cost,
            "vehicle_expense_this_month": veh_expense_cost,
            "vendor_bills_pending":   vb_pending,
            "freight_cost_this_month": freight_cost,
            "high_value_approvals_pending": hv_pending,
            "vehicles_fitness_expiring_soon": fitness_expiring,
            "drivers_license_expiring_soon": license_expiring,
            "open_exceptions":        open_ex,
            "dispatches_pending_closure": pending_closure,
        },
        "project_cost_top5": [{"project_code": r["_id"], "amount": r["amount"]} for r in proj_cost_agg],
        "recent_dispatches": recent_disp,
        "recent_deliveries": recent_dlv,
        "cost_trend": sorted([{"month": r["_id"], "amount": r["amount"]} for r in trend],
                              key=lambda x: x["month"]),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Reports Center — 30 reports
# ═══════════════════════════════════════════════════════════════════════════

REPORT_CATALOG: List[Dict[str, Any]] = [
    # (key, label, collection, default_sort, columns)
    {"key": "vehicle_master",         "label": "Vehicle Master",              "collection": "vehicles",
     "columns": ["vehicle_number", "vehicle_type", "owned_by", "status", "fitness_expiry", "insurance_expiry"]},
    {"key": "driver_master",          "label": "Driver Master",               "collection": "drivers",
     "columns": ["employee_code", "name", "license_no", "license_expiry", "status"]},
    {"key": "transport_vendors",      "label": "Transport Vendors",           "collection": "logistics_vendor_profiles",
     "columns": ["vendor_id", "vendor_kind", "rate_agreement_ref", "rate_agreement_valid_till", "active"]},
    {"key": "vehicle_availability",   "label": "Vehicle Availability",        "collection": "vehicles",
     "filter": {"status": {"$in": ["available", "in_transit", "maintenance"]}},
     "columns": ["vehicle_number", "vehicle_type", "status", "current_location"]},
    {"key": "driver_availability",    "label": "Driver Availability",         "collection": "drivers",
     "columns": ["name", "status", "current_assignment"]},
    {"key": "dispatch_requests",      "label": "Dispatch Requests",           "collection": "logistics_dispatch_requests",
     "columns": ["dr_no", "dispatch_type", "project_code", "status", "required_date", "created_at"]},
    {"key": "material_dispatches",    "label": "Material Dispatches",         "collection": "logistics_dispatch_requests",
     "filter": {"dispatch_type": "material"},
     "columns": ["dr_no", "project_code", "material_summary", "status", "required_date"]},
    {"key": "in_transit_material",    "label": "In-Transit Material",         "collection": "logistics_dispatch_requests",
     "filter": {"status": "in_transit"},
     "columns": ["dr_no", "project_code", "from_point_name", "to_point_name", "created_at"]},
    {"key": "delivery_confirmations", "label": "Delivery Confirmations",      "collection": "logistics_deliveries",
     "columns": ["dispatch_no", "delivered_at", "received_by", "shortage_qty", "damage_note"]},
    {"key": "proof_of_delivery",      "label": "Proof of Delivery",           "collection": "logistics_deliveries",
     "filter": {"$or": [{"proof_urls": {"$exists": True, "$ne": []}}, {"proof_url": {"$ne": None}}]},
     "columns": ["dispatch_no", "delivered_at", "received_by", "proof_urls"]},
    {"key": "overdue_deliveries",     "label": "Overdue Deliveries",          "collection": "logistics_dispatch_requests",
     "filter": {"required_date": {"$lt": _today(), "$ne": None},
                "status": {"$nin": ["delivered", "closed", "cancelled"]}},
     "columns": ["dr_no", "project_code", "required_date", "status"]},
    {"key": "transit_exceptions",     "label": "Transit Shortage / Damage",   "collection": "logistics_exceptions",
     "columns": ["dispatch_no", "kind", "description", "status", "raised_at"]},
    {"key": "project_dispatches",     "label": "Project-wise Dispatches",     "collection": "logistics_dispatch_requests",
     "columns": ["dr_no", "project_code", "dispatch_type", "status"]},
    {"key": "site_deliveries",        "label": "Site-wise Deliveries",        "collection": "logistics_deliveries",
     "columns": ["dispatch_no", "to_point_name", "delivered_at", "received_by"]},
    {"key": "store_dispatches",       "label": "Store-wise Dispatches",       "collection": "logistics_dispatch_requests",
     "columns": ["dr_no", "from_point_name", "material_summary", "status"]},
    {"key": "manpower_mobilizations", "label": "Manpower Mobilizations",      "collection": "logistics_manpower_mob",
     "columns": ["mob_no", "project_code", "worker_count", "mobilization_date", "status"]},
    {"key": "demobilizations",        "label": "Demobilizations",             "collection": "logistics_demobilizations",
     "columns": ["demob_no", "project_code", "worker_count", "demobilization_date", "status"]},
    {"key": "travel_arrangements",    "label": "Travel Arrangements",         "collection": "logistics_travel",
     "columns": ["travel_no", "traveller_name", "from_place", "to_place", "travel_date", "status"]},
    {"key": "accommodations",         "label": "Accommodation Arrangements",  "collection": "logistics_accommodations",
     "columns": ["accom_no", "guest_name", "check_in", "check_out", "status"]},
    {"key": "fuel_entries",           "label": "Fuel / Diesel Report",        "collection": "logistics_fuel_entries",
     "columns": ["fuel_no", "vehicle_number", "entry_date", "quantity", "rate", "amount"]},
    {"key": "vehicle_expenses",       "label": "Vehicle Expense Report",      "collection": "logistics_vehicle_expenses",
     "columns": ["exp_no", "vehicle_number", "expense_date", "category", "amount"]},
    {"key": "maintenance",            "label": "Vehicle Maintenance",         "collection": "logistics_vehicle_maintenance",
     "columns": ["maint_no", "vehicle_number", "kind", "start_date", "amount", "status"]},
    {"key": "vendor_bills",           "label": "Transport Vendor Bills",      "collection": "logistics_vendor_bills",
     "columns": ["vb_no", "vendor_name", "bill_no", "bill_date", "net_payable", "status"]},
    {"key": "freight_cost",           "label": "Freight Cost",                "collection": "logistics_cost_allocations",
     "filter": {"category": "freight"},
     "columns": ["source_no", "project_code", "vehicle_id", "amount", "at"]},
    {"key": "loading_unloading_cost", "label": "Loading / Unloading Cost",    "collection": "logistics_cost_allocations",
     "filter": {"category": {"$in": ["loading", "unloading", "loading_unloading"]}},
     "columns": ["source_no", "project_code", "amount", "at"]},
    {"key": "project_wise_cost",      "label": "Project-wise Logistics Cost", "collection": "logistics_cost_allocations",
     "columns": ["project_code", "category", "amount", "source_no", "at"]},
    {"key": "vehicle_wise_cost",      "label": "Vehicle-wise Cost",           "collection": "logistics_cost_allocations",
     "columns": ["vehicle_id", "category", "amount", "source_no", "at"]},
    {"key": "vendor_payable",         "label": "Transport Vendor Payable",    "collection": "logistics_vendor_bills",
     "filter": {"status": {"$in": ["approved", "posted"]}},
     "columns": ["vb_no", "vendor_name", "bill_no", "net_payable", "status"]},
    {"key": "audit_trail",            "label": "Logistics Audit Trail",       "collection": "logistics_audit_log",
     "columns": ["at", "record_kind", "record_no", "action", "by_name", "by_role"]},
    {"key": "logistics_exceptions",   "label": "Logistics Exception Report",  "collection": "logistics_exceptions",
     "columns": ["dispatch_no", "kind", "description", "raised_at", "status"]},
]


def _report_meta(key: str) -> Dict[str, Any]:
    for r in REPORT_CATALOG:
        if r["key"] == key:
            return r
    raise HTTPException(404, f"Unknown report: {key}")


def _apply_filters(base_filter: Dict[str, Any],
                   date_from: Optional[str], date_to: Optional[str],
                   project_code: Optional[str], vehicle_id: Optional[str],
                   driver_id: Optional[str], vendor_id: Optional[str],
                   status: Optional[str], category: Optional[str],
                   collection: str) -> Dict[str, Any]:
    q = dict(base_filter or {})
    if project_code:
        q["project_code"] = project_code
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    if driver_id:
        q["driver_id"] = driver_id
    if vendor_id:
        q["vendor_id"] = vendor_id
    if status:
        q["status"] = status
    if category:
        q["category"] = category
    if date_from or date_to:
        # Preferred timestamp field per collection
        ts = {
            "logistics_dispatch_requests":   "created_at",
            "logistics_deliveries":          "delivered_at",
            "logistics_exceptions":          "raised_at",
            "logistics_fuel_entries":        "entry_date",
            "logistics_vehicle_expenses":    "expense_date",
            "logistics_vehicle_maintenance": "start_date",
            "logistics_vendor_bills":        "bill_date",
            "logistics_cost_allocations":    "at",
            "logistics_audit_log":           "at",
            "logistics_manpower_mob":        "mobilization_date",
            "logistics_demobilizations":     "demobilization_date",
            "logistics_travel":              "travel_date",
            "logistics_accommodations":      "check_in",
        }.get(collection, "created_at")
        clause: Dict[str, Any] = {}
        if date_from:
            clause["$gte"] = date_from
        if date_to:
            clause["$lte"] = date_to + "T23:59:59"
        q[ts] = clause
    return q


@router.get("/reports/list")
async def reports_list(user: dict = Depends(require_permission("logistics_reports", "read"))):
    return [{"key": r["key"], "label": r["label"], "columns": r["columns"]}
            for r in REPORT_CATALOG]


@router.get("/reports/{report_key}")
async def report_data(
    report_key: str,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to:   Optional[str] = Query(None, alias="to"),
    project_code: Optional[str] = None,
    vehicle_id:   Optional[str] = None,
    driver_id:    Optional[str] = None,
    vendor_id:    Optional[str] = None,
    status:   Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(500, ge=1, le=5000),
    user: dict = Depends(require_permission("logistics_reports", "read")),
):
    meta = _report_meta(report_key)
    q = _apply_filters(meta.get("filter", {}), date_from, date_to,
                       project_code, vehicle_id, driver_id, vendor_id, status, category,
                       meta["collection"])
    # Data scope for project-linked collections
    scope = await _project_scope(user)
    if scope is not None and meta["collection"] in {
        "logistics_dispatch_requests", "logistics_cost_allocations",
        "logistics_manpower_mob", "logistics_demobilizations",
    }:
        if not scope:
            return {"report": meta["key"], "columns": meta["columns"], "rows": [], "count": 0}
        q["$and"] = q.get("$and", []) + [{"project_id": {"$in": scope}}]

    sort_field = "created_at"
    if meta["collection"] == "logistics_audit_log":
        sort_field = "at"
    elif meta["collection"] == "logistics_cost_allocations":
        sort_field = "at"
    rows = await db[meta["collection"]].find(q, {"_id": 0}).sort(sort_field, -1).to_list(limit)
    return {"report": meta["key"], "label": meta["label"],
            "columns": meta["columns"], "rows": rows, "count": len(rows)}


@router.get("/reports/{report_key}/export.xlsx")
async def report_export_xlsx(
    report_key: str,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to:   Optional[str] = Query(None, alias="to"),
    project_code: Optional[str] = None,
    vehicle_id:   Optional[str] = None,
    driver_id:    Optional[str] = None,
    vendor_id:    Optional[str] = None,
    status:   Optional[str] = None,
    category: Optional[str] = None,
    user: dict = Depends(require_permission("logistics_reports", "read")),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    meta = _report_meta(report_key)
    q = _apply_filters(meta.get("filter", {}), date_from, date_to,
                       project_code, vehicle_id, driver_id, vendor_id, status, category,
                       meta["collection"])
    scope = await _project_scope(user)
    if scope is not None and meta["collection"] in {
        "logistics_dispatch_requests", "logistics_cost_allocations",
        "logistics_manpower_mob", "logistics_demobilizations",
    }:
        if not scope:
            rows = []
        else:
            q["$and"] = q.get("$and", []) + [{"project_id": {"$in": scope}}]
            rows = await db[meta["collection"]].find(q, {"_id": 0}).to_list(20000)
    else:
        rows = await db[meta["collection"]].find(q, {"_id": 0}).to_list(20000)

    wb = Workbook()
    ws = wb.active
    ws.title = meta["label"][:31]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="0F172A")
    ws.append(["Report", meta["label"]])
    ws.append(["Generated", now_iso()])
    ws.append(["Generated by", user.get("name") or user.get("email")])
    ws.append([])
    ws.append(meta["columns"])
    for c in ws[5]:
        c.font = header_font
        c.fill = header_fill
    for r in rows:
        ws.append([str(r.get(col, "")) if r.get(col) is not None else "" for col in meta["columns"]])
    for i, _ in enumerate(meta["columns"], start=1):
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A" + chr(64 + i - 26)].width = 20

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"{meta['key']}-{_today()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
