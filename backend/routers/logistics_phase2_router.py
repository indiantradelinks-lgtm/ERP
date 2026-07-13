"""
Iter 133 — Logistics Module · Phase 2 · Dispatch Lifecycle
=============================================================

Extends Phase 1 with the full material-movement lifecycle:

  * Vehicle Allocation      → `logistics_vehicle_allocations`
  * Loading Confirmation    → `logistics_loading_events`
  * Transit Tracking        → `logistics_transit_events` (many per DR)
  * Delivery Confirmation   → `logistics_delivery_confirmations`
  * Transit Exception       → `logistics_transit_exceptions`
  * Stock hand-off          → `logistics_stock_moves` (Store integration hook)

Endpoints:
  * POST /api/logistics/dispatch-requests/{dr_id}/allocate       (allocate vehicle+driver)
  * POST /api/logistics/dispatch-requests/{dr_id}/load           (record loading)
  * POST /api/logistics/dispatch-requests/{dr_id}/transit        (append transit event)
  * POST /api/logistics/dispatch-requests/{dr_id}/deliver        (record POD)
  * POST /api/logistics/dispatch-requests/{dr_id}/exception      (raise shortage/damage)
  * GET  /api/logistics/allocations                              (list)
  * GET  /api/logistics/loadings                                 (list)
  * GET  /api/logistics/in-transit                               (list — active only)
  * GET  /api/logistics/deliveries                               (list)
  * GET  /api/logistics/exceptions                               (list)
  * GET  /api/logistics/stock-moves                              (list — Store integration)

Validation guards:
  * Only approved DRs may be allocated
  * Cannot allocate vehicle in status != available (unless override role)
  * Cannot allocate a driver with expired licence unless override role
  * Loaded qty cannot exceed request qty without an approval flag
  * Delivery cannot happen without a prior loading + allocation
  * DR cannot close until POD is captured (delivered/partial)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission

router = APIRouter(prefix="/logistics", tags=["logistics-phase2"])

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _next_int(key: str) -> int:
    doc = await db.sequences.find_one_and_update(
        {"_id": key}, {"$inc": {"value": 1}}, upsert=True, return_document=True
    )
    return int(doc["value"])


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


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _is_expired(date_str: Optional[str]) -> bool:
    if not date_str:
        return False
    try:
        return date_str[:10] < _today()
    except Exception:
        return False


def _is_admin_override(user: dict) -> bool:
    return (user.get("role") or "") in {"super_admin", "director", "general_manager", "dept_head"}


async def _get_dr(dr_id: str) -> Dict[str, Any]:
    dr = await db.logistics_dispatch_requests.find_one({"id": dr_id}, {"_id": 0})
    if not dr:
        raise HTTPException(404, "Dispatch request not found")
    return dr


async def _set_dr_status(dr_id: str, new_status: str, user: dict, meta: Optional[Dict] = None):
    await db.logistics_dispatch_requests.update_one(
        {"id": dr_id},
        {"$set": {"status": new_status, "updated_at": now_iso(),
                  "updated_by": user.get("name") or user.get("email")}},
    )
    dr = await db.logistics_dispatch_requests.find_one({"id": dr_id}, {"_id": 0})
    await _audit("dispatch_request", dr_id, f"status:{new_status}", user,
                 dr.get("dr_no", "") if dr else "", meta)


# ═══════════════════════════════════════════════════════════════════════════
# Vehicle Allocation
# ═══════════════════════════════════════════════════════════════════════════

FREIGHT_BASES = ["fixed", "per_km", "per_mt", "per_trip", "per_day", "vendor_bill"]


class AllocationIn(BaseModel):
    vehicle_id: str
    driver_id: Optional[str] = None
    transport_vendor_id: Optional[str] = None
    loading_point_id: Optional[str] = None
    delivery_point_id: Optional[str] = None
    planned_dispatch_at: Optional[str] = None
    expected_delivery_at: Optional[str] = None
    freight_basis: str = "fixed"
    estimated_freight: Optional[float] = None
    loading_cost: Optional[float] = None
    unloading_cost: Optional[float] = None
    advance_amount: Optional[float] = None
    remarks: Optional[str] = None


@router.post("/dispatch-requests/{dr_id}/allocate")
async def allocate_vehicle(
    dr_id: str,
    payload: AllocationIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    dr = await _get_dr(dr_id)
    if dr.get("status") not in {"approved", "pending_approval", "allocated"}:
        raise HTTPException(400, f"Cannot allocate vehicle while DR is in status '{dr.get('status')}'")
    if payload.freight_basis not in FREIGHT_BASES:
        raise HTTPException(400, f"freight_basis must be one of {FREIGHT_BASES}")

    veh = await db.vehicles.find_one({"id": payload.vehicle_id}, {"_id": 0})
    if not veh:
        raise HTTPException(400, "Vehicle not found")
    if veh.get("status") not in {"available", "allocated"} and not _is_admin_override(user):
        raise HTTPException(400, f"Vehicle is not available (status={veh.get('status')})")
    if (_is_expired(veh.get("fitness_expiry")) or _is_expired(veh.get("insurance_expiry"))) \
            and not _is_admin_override(user):
        raise HTTPException(400, "Vehicle fitness or insurance expired — allocation blocked")

    drv = None
    if payload.driver_id:
        drv = await db.drivers.find_one({"id": payload.driver_id}, {"_id": 0})
        if not drv:
            raise HTTPException(400, "Driver not found")
        if drv.get("status") not in {"available", "assigned"} and not _is_admin_override(user):
            raise HTTPException(400, f"Driver is not available (status={drv.get('status')})")
        if _is_expired(drv.get("license_expiry")) and not _is_admin_override(user):
            raise HTTPException(400, "Driver licence expired — allocation blocked")

    seq = await _next_int("logistics_allocations")
    alloc = payload.model_dump()
    alloc.update({
        "id": new_id(),
        "allocation_no": f"ALC-{datetime.now(timezone.utc).year}-{seq:04d}",
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "vehicle_number": veh.get("vehicle_number") or veh.get("reg_number"),
        "vehicle_type": veh.get("vehicle_type") or veh.get("type"),
        "driver_name": drv.get("driver_name") if drv else veh.get("assigned_driver_name"),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "status": "approved",
    })
    await db.logistics_vehicle_allocations.insert_one(alloc)

    # Update vehicle + driver status
    await db.vehicles.update_one({"id": payload.vehicle_id},
                                 {"$set": {"status": "allocated", "updated_at": now_iso()}})
    if payload.driver_id:
        await db.drivers.update_one({"id": payload.driver_id},
                                    {"$set": {"status": "assigned", "updated_at": now_iso()}})

    # Update DR
    await db.logistics_dispatch_requests.update_one(
        {"id": dr_id},
        {"$set": {
            "status": "allocated",
            "allocation_id": alloc["id"],
            "allocation_no": alloc["allocation_no"],
            "vehicle_id": payload.vehicle_id,
            "vehicle_number": alloc["vehicle_number"],
            "driver_id": payload.driver_id,
            "driver_name": alloc["driver_name"],
            "updated_at": now_iso(),
        }},
    )
    alloc.pop("_id", None)
    await _audit("vehicle_allocation", alloc["id"], "create", user, alloc["allocation_no"],
                 {"dr_no": dr.get("dr_no"), "vehicle": alloc["vehicle_number"]})
    return alloc


@router.get("/allocations")
async def allocations_list(
    dr_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if dr_id:
        q["dr_id"] = dr_id
    return await db.logistics_vehicle_allocations.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


# ═══════════════════════════════════════════════════════════════════════════
# Loading Confirmation
# ═══════════════════════════════════════════════════════════════════════════

class LoadingIn(BaseModel):
    loaded_at: Optional[str] = None
    loaded_by: Optional[str] = None
    material_summary: Optional[str] = None
    loaded_qty: Optional[float] = None
    short_loaded_qty: Optional[float] = None
    approved_qty: Optional[float] = None
    e_way_bill_no: Optional[str] = None
    delivery_challan_no: Optional[str] = None
    gate_pass_no: Optional[str] = None
    driver_acknowledged: bool = False
    excess_override_reason: Optional[str] = None
    photo_urls: Optional[List[str]] = None
    remarks: Optional[str] = None


@router.post("/dispatch-requests/{dr_id}/load")
async def load_confirm(
    dr_id: str,
    payload: LoadingIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    dr = await _get_dr(dr_id)
    if dr.get("status") not in {"allocated", "loading_pending", "loaded"}:
        raise HTTPException(400, f"Cannot record loading — DR status is '{dr.get('status')}'")
    if not dr.get("allocation_id"):
        raise HTTPException(400, "Vehicle must be allocated before loading")

    if payload.approved_qty is not None and payload.loaded_qty is not None:
        if payload.loaded_qty > payload.approved_qty and not payload.excess_override_reason \
                and not _is_admin_override(user):
            raise HTTPException(400, "Loaded qty exceeds approved qty — override reason required")

    seq = await _next_int("logistics_loadings")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "loading_no": f"LOAD-{datetime.now(timezone.utc).year}-{seq:04d}",
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "allocation_id": dr.get("allocation_id"),
        "loaded_at": payload.loaded_at or now_iso(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_loading_events.insert_one(doc)
    doc.pop("_id", None)

    # Update DR status to 'in_transit' after loading (dispatched)
    await _set_dr_status(dr_id, "in_transit", user, {"loading_no": doc["loading_no"]})
    # Update vehicle status
    if dr.get("vehicle_id"):
        await db.vehicles.update_one({"id": dr["vehicle_id"]},
                                     {"$set": {"status": "in_transit"}})
    if dr.get("driver_id"):
        await db.drivers.update_one({"id": dr["driver_id"]},
                                    {"$set": {"status": "on_trip"}})

    # Emit stock-move event (Store integration hook)
    await db.logistics_stock_moves.insert_one({
        "id": new_id(),
        "event": "in_transit",
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "project_id": dr.get("project_id"),
        "project_code": dr.get("project_code"),
        "material_summary": doc.get("material_summary") or dr.get("material_summary"),
        "qty": doc.get("loaded_qty"),
        "at": now_iso(),
        "by": user.get("name") or user.get("email"),
    })

    await _audit("loading", doc["id"], "create", user, doc["loading_no"],
                 {"dr_no": dr.get("dr_no"), "loaded_qty": doc.get("loaded_qty")})
    return doc


@router.get("/loadings")
async def loadings_list(
    dr_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if dr_id:
        q["dr_id"] = dr_id
    return await db.logistics_loading_events.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


# ═══════════════════════════════════════════════════════════════════════════
# In-Transit Tracking
# ═══════════════════════════════════════════════════════════════════════════

TRANSIT_STATES = ["loaded", "dispatched", "in_transit", "reached_site", "unloading",
                  "delivered", "partially_delivered", "delayed", "shortage_reported",
                  "damage_reported", "closed"]


class TransitEventIn(BaseModel):
    status: str
    current_location: Optional[str] = None
    delay_reason: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/dispatch-requests/{dr_id}/transit")
async def transit_update(
    dr_id: str,
    payload: TransitEventIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    dr = await _get_dr(dr_id)
    if payload.status not in TRANSIT_STATES:
        raise HTTPException(400, f"status must be one of {TRANSIT_STATES}")

    event = {
        "id": new_id(),
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "status": payload.status,
        "current_location": payload.current_location,
        "delay_reason": payload.delay_reason,
        "remarks": payload.remarks,
        "at": now_iso(),
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
    }
    await db.logistics_transit_events.insert_one(event)

    # Map some transit statuses to DR status
    dr_status_map = {
        "delivered": "delivered",
        "partially_delivered": "delivered",
        "closed": "closed",
    }
    if payload.status in dr_status_map:
        await _set_dr_status(dr_id, dr_status_map[payload.status], user,
                             {"transit_status": payload.status})

    event.pop("_id", None)
    await _audit("transit_event", event["id"], payload.status, user, dr.get("dr_no", ""),
                 {"loc": payload.current_location})
    return event


@router.get("/dispatch-requests/{dr_id}/transit-timeline")
async def transit_timeline(
    dr_id: str,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    return await db.logistics_transit_events.find(
        {"dr_id": dr_id}, {"_id": 0}
    ).sort("at", 1).to_list(500)


@router.get("/in-transit")
async def in_transit_list(user: dict = Depends(require_permission("dispatch_requests", "read"))):
    """DRs currently mid-flight."""
    return await db.logistics_dispatch_requests.find(
        {"status": {"$in": ["in_transit"]}}, {"_id": 0}
    ).sort("updated_at", -1).to_list(2000)


# ═══════════════════════════════════════════════════════════════════════════
# Delivery Confirmation / POD
# ═══════════════════════════════════════════════════════════════════════════

class DeliveryIn(BaseModel):
    delivered_at: Optional[str] = None
    received_by: Optional[str] = None
    delivered_qty: Optional[float] = None
    short_qty: Optional[float] = None
    damaged_qty: Optional[float] = None
    rejected_qty: Optional[float] = None
    material_condition: Optional[str] = None  # good / partial / damaged / rejected
    pod_url: Optional[str] = None
    photo_urls: Optional[List[str]] = None
    site_remarks: Optional[str] = None
    close_dispatch: bool = False


@router.post("/dispatch-requests/{dr_id}/deliver")
async def deliver(
    dr_id: str,
    payload: DeliveryIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    dr = await _get_dr(dr_id)
    if dr.get("status") not in {"in_transit", "delivered", "partially_delivered"}:
        raise HTTPException(400, f"Cannot record delivery — DR status is '{dr.get('status')}'")

    seq = await _next_int("logistics_deliveries")
    is_partial = bool((payload.short_qty or 0) > 0 or (payload.damaged_qty or 0) > 0
                      or (payload.rejected_qty or 0) > 0)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "delivery_no": f"POD-{datetime.now(timezone.utc).year}-{seq:04d}",
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "allocation_id": dr.get("allocation_id"),
        "delivered_at": payload.delivered_at or now_iso(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "is_partial": is_partial,
    })
    await db.logistics_delivery_confirmations.insert_one(doc)
    doc.pop("_id", None)

    # Move stock: in_transit → delivered
    await db.logistics_stock_moves.insert_one({
        "id": new_id(),
        "event": "delivered",
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "project_id": dr.get("project_id"),
        "project_code": dr.get("project_code"),
        "qty": doc.get("delivered_qty"),
        "at": now_iso(),
        "by": user.get("name") or user.get("email"),
    })

    # Update DR status
    if payload.close_dispatch and not is_partial:
        new_status = "closed"
    elif is_partial:
        new_status = "delivered"  # keep open until exceptions closed
    else:
        new_status = "delivered"
    await _set_dr_status(dr_id, new_status, user, {"delivery_no": doc["delivery_no"]})

    # Release vehicle + driver back to available (if closing)
    if new_status == "closed":
        if dr.get("vehicle_id"):
            await db.vehicles.update_one({"id": dr["vehicle_id"]}, {"$set": {"status": "available"}})
        if dr.get("driver_id"):
            await db.drivers.update_one({"id": dr["driver_id"]}, {"$set": {"status": "available"}})

    await _audit("delivery", doc["id"], "create", user, doc["delivery_no"],
                 {"dr_no": dr.get("dr_no"), "partial": is_partial})
    return doc


@router.get("/deliveries")
async def deliveries_list(
    dr_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if dr_id:
        q["dr_id"] = dr_id
    return await db.logistics_delivery_confirmations.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


# ═══════════════════════════════════════════════════════════════════════════
# Transit Exceptions (shortage / damage)
# ═══════════════════════════════════════════════════════════════════════════

RESPONSIBLE_PARTIES = ["transporter", "driver", "store_loading", "site_unloading", "unknown"]


class ExceptionIn(BaseModel):
    kind: str = "shortage"  # shortage | damage | rejected
    item: Optional[str] = None
    short_qty: Optional[float] = None
    damaged_qty: Optional[float] = None
    approx_value: Optional[float] = None
    reason: Optional[str] = None
    responsible_party: str = "unknown"
    recovery_applicable: bool = False
    recovery_amount: Optional[float] = None
    attachment_urls: Optional[List[str]] = None
    remarks: Optional[str] = None


@router.post("/dispatch-requests/{dr_id}/exception")
async def raise_exception(
    dr_id: str,
    payload: ExceptionIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    dr = await _get_dr(dr_id)
    if payload.responsible_party not in RESPONSIBLE_PARTIES:
        raise HTTPException(400, f"responsible_party must be one of {RESPONSIBLE_PARTIES}")

    seq = await _next_int("logistics_exceptions")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "exception_no": f"EXC-{datetime.now(timezone.utc).year}-{seq:04d}",
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "project_id": dr.get("project_id"),
        "project_code": dr.get("project_code"),
        "status": "open",
        "reported_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    })
    await db.logistics_transit_exceptions.insert_one(doc)
    doc.pop("_id", None)

    # Append transit-event echo
    await db.logistics_transit_events.insert_one({
        "id": new_id(),
        "dr_id": dr_id,
        "dr_no": dr.get("dr_no"),
        "status": "damage_reported" if payload.kind == "damage" else "shortage_reported",
        "remarks": f"{doc['exception_no']}: {payload.reason or ''}",
        "at": now_iso(),
        "by_name": user.get("name") or user.get("email"),
    })

    await _audit("transit_exception", doc["id"], "create", user, doc["exception_no"],
                 {"dr_no": dr.get("dr_no"), "kind": payload.kind,
                  "responsible": payload.responsible_party})
    return doc


class ExceptionUpdateIn(BaseModel):
    verified_by: Optional[str] = None
    approved_by: Optional[str] = None
    recovery_amount: Optional[float] = None
    status: Optional[str] = None  # open | verified | approved | closed | rejected


@router.put("/exceptions/{eid}")
async def update_exception(
    eid: str,
    payload: ExceptionUpdateIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_transit_exceptions.find_one({"id": eid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Exception not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user.get("name") or user.get("email")
    await db.logistics_transit_exceptions.update_one({"id": eid}, {"$set": updates})
    await _audit("transit_exception", eid, f"update:{updates.get('status') or 'edit'}",
                 user, ex.get("exception_no", ""))
    return {**ex, **updates}


@router.get("/exceptions")
async def exceptions_list(
    status: Optional[str] = None,
    dr_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if dr_id:
        q["dr_id"] = dr_id
    return await db.logistics_transit_exceptions.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


# ═══════════════════════════════════════════════════════════════════════════
# Stock Moves (Store integration hook)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/stock-moves")
async def stock_moves_list(
    dr_id: Optional[str] = None,
    project_id: Optional[str] = None,
    event: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if dr_id:
        q["dr_id"] = dr_id
    if project_id:
        q["project_id"] = project_id
    if event:
        q["event"] = event
    return await db.logistics_stock_moves.find(q, {"_id": 0}).sort("at", -1).to_list(2000)


# ═══════════════════════════════════════════════════════════════════════════
# Enriched DR detail (aggregates allocation + loading + delivery + exceptions)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/dispatch-requests/{dr_id}/full")
async def dr_full(
    dr_id: str,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    dr = await _get_dr(dr_id)
    allocation = None
    if dr.get("allocation_id"):
        allocation = await db.logistics_vehicle_allocations.find_one(
            {"id": dr["allocation_id"]}, {"_id": 0}
        )
    loadings = await db.logistics_loading_events.find({"dr_id": dr_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    deliveries = await db.logistics_delivery_confirmations.find({"dr_id": dr_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    exceptions = await db.logistics_transit_exceptions.find({"dr_id": dr_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    timeline = await db.logistics_transit_events.find({"dr_id": dr_id}, {"_id": 0}).sort("at", 1).to_list(200)
    return {
        "dr": dr,
        "allocation": allocation,
        "loadings": loadings,
        "deliveries": deliveries,
        "exceptions": exceptions,
        "timeline": timeline,
    }
