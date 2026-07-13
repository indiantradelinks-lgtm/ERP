"""
Iter 132 — Logistics Module · Phase 1 · Foundation
====================================================

Extends the existing ERP with the Logistics foundation. Reuses the existing
`vehicles` collection (adds new optional fields — no destructive migration)
and adds:

  * `drivers`                        — Driver Master
  * `logistics_routes`               — Route Master
  * `logistics_loading_points`       — Loading / Unloading points
  * `logistics_dispatch_types`       — Dispatch type master
  * `logistics_dispatch_requests`    — Basic dispatch register (Phase 2 → full lifecycle)
  * `logistics_vendor_profiles`      — Overlay on existing `vendors` for transport-specific fields
  * `logistics_audit_log`            — Immutable audit trail for all logistics state changes

Endpoints:
  * `GET  /api/logistics/dashboard`                       — 20 real-time KPIs
  * `GET  /api/logistics/vehicles/availability`           — snapshot by status
  * `GET  /api/logistics/drivers/availability`            — snapshot by status
  *  CRUD /api/logistics/drivers
  *  CRUD /api/logistics/routes
  *  CRUD /api/logistics/loading-points
  *  CRUD /api/logistics/dispatch-types
  *  CRUD /api/logistics/dispatch-requests
  *  CRUD /api/logistics/vendor-profiles
  *  Extended Vehicle POST/PUT/GET (`/api/logistics/vehicles*`) with validation:
        - Blocks duplicate vehicle_number
        - Rejects assignment when driver's license expired (unless override)
  * `GET  /api/logistics/audit-log`                       — filterable

New RBAC keys added in rbac.py: `drivers`, `logistics_masters`, `dispatch_requests`,
`logistics_reports`, `logistics_audit`.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission

router = APIRouter(prefix="/logistics", tags=["logistics-phase1"])


async def _next_int(key: str) -> int:
    """Return next raw integer for a given sequence key (atomic upsert)."""
    doc = await db.sequences.find_one_and_update(
        {"_id": key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True,  # type: ignore[arg-type]
    )
    if not doc or "value" not in doc:
        doc = await db.sequences.find_one({"_id": key})
    return int((doc or {}).get("value", 1))

# ═══════════════════════════════════════════════════════════════════════════
# Audit trail helper
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# Drivers
# ═══════════════════════════════════════════════════════════════════════════

DRIVER_STATUSES = ["available", "assigned", "on_trip", "on_leave", "inactive"]


class DriverIn(BaseModel):
    driver_name: str
    mobile: Optional[str] = None
    alt_mobile: Optional[str] = None
    license_no: str
    license_type: Optional[str] = "LMV"
    license_expiry: Optional[str] = None
    id_proof: Optional[str] = None
    address: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    emergency_contact: Optional[str] = None
    status: str = "available"
    remarks: Optional[str] = None
    attachment_url: Optional[str] = None


@router.get("/drivers")
async def drivers_list(
    status: Optional[str] = None,
    q: Optional[str] = None,
    user: dict = Depends(require_permission("drivers", "read")),
):
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"driver_name": {"$regex": q, "$options": "i"}},
            {"license_no": {"$regex": q, "$options": "i"}},
            {"driver_code": {"$regex": q, "$options": "i"}},
        ]
    rows = await db.drivers.find(query, {"_id": 0}).sort("driver_name", 1).to_list(2000)
    return rows


@router.post("/drivers")
async def drivers_create(
    payload: DriverIn,
    user: dict = Depends(require_permission("drivers", "write")),
):
    if payload.status not in DRIVER_STATUSES:
        raise HTTPException(400, f"status must be one of {DRIVER_STATUSES}")
    exists = await db.drivers.find_one({"license_no": payload.license_no})
    if exists:
        raise HTTPException(400, f"Driver with license {payload.license_no} already exists")
    seq = await _next_int("drivers")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "driver_code": f"DRV-{seq:05d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    })
    await db.drivers.insert_one(doc)
    doc.pop("_id", None)
    await _audit("driver", doc["id"], "create", user, doc["driver_code"], {"status": doc["status"]})
    return doc


@router.put("/drivers/{driver_id}")
async def drivers_update(
    driver_id: str,
    payload: DriverIn,
    user: dict = Depends(require_permission("drivers", "write")),
):
    existing = await db.drivers.find_one({"id": driver_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Driver not found")
    if payload.status not in DRIVER_STATUSES:
        raise HTTPException(400, f"status must be one of {DRIVER_STATUSES}")
    updates = payload.model_dump(exclude_none=False)
    updates.update({
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    })
    await db.drivers.update_one({"id": driver_id}, {"$set": updates})
    action_meta = {"before": {"status": existing.get("status")}, "after": {"status": updates["status"]}}
    await _audit("driver", driver_id, "update", user, existing.get("driver_code", ""), action_meta)
    return {**existing, **updates}


@router.delete("/drivers/{driver_id}")
async def drivers_delete(
    driver_id: str,
    user: dict = Depends(require_permission("drivers", "delete")),
):
    existing = await db.drivers.find_one({"id": driver_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Driver not found")
    # No hard-delete if referenced by any dispatch or vehicle assignment (approved)
    assigned = await db.vehicles.find_one({"assigned_driver_id": driver_id})
    if assigned:
        raise HTTPException(400, "Driver assigned to a vehicle; deactivate instead")
    await db.drivers.delete_one({"id": driver_id})
    await _audit("driver", driver_id, "delete", user, existing.get("driver_code", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Vehicles — extend existing collection with logistics fields
# ═══════════════════════════════════════════════════════════════════════════

VEHICLE_TYPES = ["truck", "trailer", "pickup", "crane", "hydra", "forklift",
                 "tempo", "car", "bus", "two_wheeler", "other"]
OWNERSHIP_TYPES = ["own", "hired", "vendor"]
VEHICLE_STATUSES = ["available", "allocated", "in_transit", "maintenance", "inactive"]


class VehicleIn(BaseModel):
    vehicle_number: str
    vehicle_type: str = "truck"
    ownership_type: str = "own"
    capacity_mt: Optional[float] = None
    volume_cbm: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    fitness_no: Optional[str] = None
    fitness_expiry: Optional[str] = None
    insurance_no: Optional[str] = None
    insurance_expiry: Optional[str] = None
    pollution_expiry: Optional[str] = None
    permit_valid_till: Optional[str] = None
    gps_installed: bool = False
    status: str = "available"
    assigned_driver_id: Optional[str] = None
    assigned_driver_name: Optional[str] = None
    transport_vendor_id: Optional[str] = None
    transport_vendor_name: Optional[str] = None
    remarks: Optional[str] = None
    attachment_url: Optional[str] = None
    # Preserve legacy fields
    reg_number: Optional[str] = None
    type: Optional[str] = None
    capacity: Optional[str] = None
    driver: Optional[str] = None
    last_service: Optional[str] = None
    fuel_avg: Optional[float] = None


@router.get("/vehicles")
async def vehicles_list(
    status: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    q: Optional[str] = None,
    user: dict = Depends(require_permission("vehicles", "read")),
):
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if vehicle_type:
        query["vehicle_type"] = vehicle_type
    if q:
        query["$or"] = [
            {"vehicle_number": {"$regex": q, "$options": "i"}},
            {"reg_number": {"$regex": q, "$options": "i"}},
            {"vehicle_code": {"$regex": q, "$options": "i"}},
        ]
    rows = await db.vehicles.find(query, {"_id": 0}).sort("vehicle_number", 1).to_list(5000)
    return rows


@router.post("/vehicles")
async def vehicles_create(
    payload: VehicleIn,
    user: dict = Depends(require_permission("vehicles", "write")),
):
    if payload.vehicle_type not in VEHICLE_TYPES:
        raise HTTPException(400, f"vehicle_type must be one of {VEHICLE_TYPES}")
    if payload.ownership_type not in OWNERSHIP_TYPES:
        raise HTTPException(400, f"ownership_type must be one of {OWNERSHIP_TYPES}")
    if payload.status not in VEHICLE_STATUSES:
        raise HTTPException(400, f"status must be one of {VEHICLE_STATUSES}")

    dup = await db.vehicles.find_one({
        "$or": [
            {"vehicle_number": payload.vehicle_number},
            {"reg_number": payload.vehicle_number},
        ]
    })
    if dup:
        raise HTTPException(400, f"Vehicle number {payload.vehicle_number} already exists")

    # Driver assignment: block if driver license expired (unless authorised)
    if payload.assigned_driver_id:
        d = await db.drivers.find_one({"id": payload.assigned_driver_id})
        if not d:
            raise HTTPException(400, "Assigned driver not found")
        if _is_expired(d.get("license_expiry")) and user.get("role") not in {
            "super_admin", "director", "general_manager", "dept_head"
        }:
            raise HTTPException(400, "Driver license expired — assignment blocked (contact admin for override)")
        payload_dict_driver = d.get("driver_name", "")
    else:
        payload_dict_driver = None

    seq = await _next_int("vehicles")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "vehicle_code": f"VEH-{seq:05d}",
        "reg_number": payload.reg_number or payload.vehicle_number,  # legacy dual-write
        "assigned_driver_name": payload_dict_driver or payload.assigned_driver_name,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    })
    await db.vehicles.insert_one(doc)
    doc.pop("_id", None)
    await _audit("vehicle", doc["id"], "create", user, doc["vehicle_code"], {"status": doc["status"]})
    return doc


@router.put("/vehicles/{vehicle_id}")
async def vehicles_update(
    vehicle_id: str,
    payload: VehicleIn,
    user: dict = Depends(require_permission("vehicles", "write")),
):
    existing = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Vehicle not found")
    if payload.status == "maintenance" and existing.get("status") in {"allocated", "in_transit"}:
        raise HTTPException(400, "Cannot move a vehicle in-transit / allocated to maintenance directly")

    if payload.assigned_driver_id and payload.assigned_driver_id != existing.get("assigned_driver_id"):
        d = await db.drivers.find_one({"id": payload.assigned_driver_id})
        if not d:
            raise HTTPException(400, "Assigned driver not found")
        if _is_expired(d.get("license_expiry")) and user.get("role") not in {
            "super_admin", "director", "general_manager", "dept_head"
        }:
            raise HTTPException(400, "Driver license expired — assignment blocked")

    updates = payload.model_dump(exclude_none=False)
    updates.update({
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    })
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": updates})
    await _audit("vehicle", vehicle_id, "update", user, existing.get("vehicle_code", ""),
                 {"before": {"status": existing.get("status")}, "after": {"status": updates.get("status")}})
    return {**existing, **updates}


@router.delete("/vehicles/{vehicle_id}")
async def vehicles_delete(
    vehicle_id: str,
    user: dict = Depends(require_permission("vehicles", "delete")),
):
    existing = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Vehicle not found")
    if existing.get("status") in {"allocated", "in_transit"}:
        raise HTTPException(400, "Cannot delete a vehicle that is allocated/in-transit")
    await db.vehicles.delete_one({"id": vehicle_id})
    await _audit("vehicle", vehicle_id, "delete", user, existing.get("vehicle_code", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Route Master
# ═══════════════════════════════════════════════════════════════════════════

class RouteIn(BaseModel):
    name: str
    origin: str
    destination: str
    distance_km: Optional[float] = None
    est_hours: Optional[float] = None
    toll_estimate: Optional[float] = None
    remarks: Optional[str] = None
    active: bool = True


@router.get("/routes")
async def routes_list(user: dict = Depends(require_permission("logistics_masters", "read"))):
    return await db.logistics_routes.find({}, {"_id": 0}).sort("name", 1).to_list(2000)


@router.post("/routes")
async def routes_create(
    payload: RouteIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    seq = await _next_int("logistics_routes")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "route_code": f"RT-{seq:04d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_routes.insert_one(doc)
    doc.pop("_id", None)
    await _audit("route", doc["id"], "create", user, doc["route_code"])
    return doc


@router.put("/routes/{rid}")
async def routes_update(
    rid: str,
    payload: RouteIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    existing = await db.logistics_routes.find_one({"id": rid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Route not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user.get("name") or user.get("email")
    await db.logistics_routes.update_one({"id": rid}, {"$set": updates})
    await _audit("route", rid, "update", user, existing.get("route_code", ""))
    return {**existing, **updates}


@router.delete("/routes/{rid}")
async def routes_delete(
    rid: str,
    user: dict = Depends(require_permission("logistics_masters", "delete")),
):
    ex = await db.logistics_routes.find_one({"id": rid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Route not found")
    await db.logistics_routes.delete_one({"id": rid})
    await _audit("route", rid, "delete", user, ex.get("route_code", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Loading / Unloading Points
# ═══════════════════════════════════════════════════════════════════════════

POINT_KINDS = ["loading", "unloading", "both"]


class LoadingPointIn(BaseModel):
    name: str
    kind: str = "both"
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_no: Optional[str] = None
    project_id: Optional[str] = None
    site_location: Optional[str] = None
    remarks: Optional[str] = None
    active: bool = True


@router.get("/loading-points")
async def points_list(user: dict = Depends(require_permission("logistics_masters", "read"))):
    return await db.logistics_loading_points.find({}, {"_id": 0}).sort("name", 1).to_list(2000)


@router.post("/loading-points")
async def points_create(
    payload: LoadingPointIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    if payload.kind not in POINT_KINDS:
        raise HTTPException(400, f"kind must be one of {POINT_KINDS}")
    doc = payload.model_dump()
    doc.update({"id": new_id(), "created_at": now_iso(),
                "created_by": user.get("name") or user.get("email")})
    await db.logistics_loading_points.insert_one(doc)
    doc.pop("_id", None)
    await _audit("loading_point", doc["id"], "create", user, doc["name"])
    return doc


@router.put("/loading-points/{pid}")
async def points_update(
    pid: str,
    payload: LoadingPointIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    ex = await db.logistics_loading_points.find_one({"id": pid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Point not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_loading_points.update_one({"id": pid}, {"$set": updates})
    await _audit("loading_point", pid, "update", user, ex.get("name", ""))
    return {**ex, **updates}


@router.delete("/loading-points/{pid}")
async def points_delete(
    pid: str,
    user: dict = Depends(require_permission("logistics_masters", "delete")),
):
    ex = await db.logistics_loading_points.find_one({"id": pid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Point not found")
    await db.logistics_loading_points.delete_one({"id": pid})
    await _audit("loading_point", pid, "delete", user, ex.get("name", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Dispatch Types (small master)
# ═══════════════════════════════════════════════════════════════════════════

class DispatchTypeIn(BaseModel):
    name: str
    category: str = "material"  # material | manpower | equipment | return | other
    description: Optional[str] = None
    active: bool = True


@router.get("/dispatch-types")
async def dtypes_list(user: dict = Depends(require_permission("logistics_masters", "read"))):
    return await db.logistics_dispatch_types.find({}, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/dispatch-types")
async def dtypes_create(
    payload: DispatchTypeIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    doc = payload.model_dump()
    doc.update({"id": new_id(), "created_at": now_iso(),
                "created_by": user.get("name") or user.get("email")})
    await db.logistics_dispatch_types.insert_one(doc)
    doc.pop("_id", None)
    await _audit("dispatch_type", doc["id"], "create", user, doc["name"])
    return doc


@router.put("/dispatch-types/{tid}")
async def dtypes_update(
    tid: str,
    payload: DispatchTypeIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    ex = await db.logistics_dispatch_types.find_one({"id": tid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_dispatch_types.update_one({"id": tid}, {"$set": updates})
    return {**ex, **updates}


@router.delete("/dispatch-types/{tid}")
async def dtypes_delete(
    tid: str,
    user: dict = Depends(require_permission("logistics_masters", "delete")),
):
    ex = await db.logistics_dispatch_types.find_one({"id": tid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    await db.logistics_dispatch_types.delete_one({"id": tid})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Dispatch Requests — basic Phase 1 register
# ═══════════════════════════════════════════════════════════════════════════

DR_STATUSES = ["draft", "pending_approval", "approved", "allocated", "in_transit",
               "delivered", "closed", "cancelled", "rejected"]


class DispatchRequestIn(BaseModel):
    dispatch_type: str = "material"
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    from_point_id: Optional[str] = None
    from_point_name: Optional[str] = None
    to_point_id: Optional[str] = None
    to_point_name: Optional[str] = None
    route_id: Optional[str] = None
    required_date: Optional[str] = None
    material_summary: Optional[str] = None
    approx_weight_mt: Optional[float] = None
    approx_qty: Optional[str] = None
    vehicle_type_preferred: Optional[str] = None
    priority: str = "normal"  # low | normal | high | urgent
    requested_by: Optional[str] = None
    remarks: Optional[str] = None
    status: str = "draft"


@router.get("/dispatch-requests")
async def dr_list(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    return await db.logistics_dispatch_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/dispatch-requests")
async def dr_create(
    payload: DispatchRequestIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    if payload.status not in DR_STATUSES:
        raise HTTPException(400, f"status must be one of {DR_STATUSES}")
    seq = await _next_int("logistics_dispatch_requests")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "dr_no": f"DR-{datetime.now(timezone.utc).year}-{seq:04d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_dispatch_requests.insert_one(doc)
    doc.pop("_id", None)
    await _audit("dispatch_request", doc["id"], "create", user, doc["dr_no"],
                 {"status": doc["status"]})
    return doc


@router.put("/dispatch-requests/{drid}")
async def dr_update(
    drid: str,
    payload: DispatchRequestIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_dispatch_requests.find_one({"id": drid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Dispatch request not found")
    if ex.get("status") in {"approved", "allocated", "in_transit", "delivered", "closed"} \
            and payload.status == "draft":
        raise HTTPException(400, "Cannot revert an approved dispatch to draft")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user.get("name") or user.get("email")
    await db.logistics_dispatch_requests.update_one({"id": drid}, {"$set": updates})
    await _audit("dispatch_request", drid, "update", user, ex.get("dr_no", ""),
                 {"before": {"status": ex.get("status")}, "after": {"status": updates["status"]}})
    return {**ex, **updates}


@router.delete("/dispatch-requests/{drid}")
async def dr_delete(
    drid: str,
    user: dict = Depends(require_permission("dispatch_requests", "delete")),
):
    ex = await db.logistics_dispatch_requests.find_one({"id": drid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    if ex.get("status") in {"approved", "allocated", "in_transit", "delivered", "closed"}:
        raise HTTPException(400, "Cannot hard-delete approved dispatch — cancel instead")
    await db.logistics_dispatch_requests.delete_one({"id": drid})
    await _audit("dispatch_request", drid, "delete", user, ex.get("dr_no", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Transport Vendor Profile (overlay on existing vendors)
# ═══════════════════════════════════════════════════════════════════════════

VENDOR_KINDS = ["transporter", "crane_vendor", "loading_unloading", "equipment_rental"]


class VendorProfileIn(BaseModel):
    vendor_id: str
    vendor_kind: str = "transporter"
    service_areas: Optional[List[str]] = None
    vehicle_types_available: Optional[List[str]] = None
    rate_agreement_ref: Optional[str] = None
    rate_agreement_valid_till: Optional[str] = None
    insurance_valid_till: Optional[str] = None
    compliance_docs: Optional[List[str]] = None
    remarks: Optional[str] = None
    active: bool = True


@router.get("/vendor-profiles")
async def vp_list(user: dict = Depends(require_permission("logistics_masters", "read"))):
    rows = await db.logistics_vendor_profiles.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    # enrich with vendor name from vendors collection
    for r in rows:
        v = await db.vendors.find_one({"id": r.get("vendor_id")}, {"_id": 0, "name": 1, "vendor_code": 1})
        if v:
            r["vendor_name"] = v.get("name")
            r["vendor_code"] = v.get("vendor_code")
    return rows


@router.post("/vendor-profiles")
async def vp_create(
    payload: VendorProfileIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    if payload.vendor_kind not in VENDOR_KINDS:
        raise HTTPException(400, f"vendor_kind must be one of {VENDOR_KINDS}")
    v = await db.vendors.find_one({"id": payload.vendor_id})
    if not v:
        raise HTTPException(400, "Vendor not found in Procurement master")
    dup = await db.logistics_vendor_profiles.find_one({
        "vendor_id": payload.vendor_id, "vendor_kind": payload.vendor_kind
    })
    if dup:
        raise HTTPException(400, "Profile already exists for this vendor & kind")
    doc = payload.model_dump()
    doc.update({"id": new_id(), "created_at": now_iso(),
                "created_by": user.get("name") or user.get("email")})
    await db.logistics_vendor_profiles.insert_one(doc)
    doc.pop("_id", None)
    doc["vendor_name"] = v.get("name")
    await _audit("vendor_profile", doc["id"], "create", user, v.get("name", ""))
    return doc


@router.put("/vendor-profiles/{vpid}")
async def vp_update(
    vpid: str,
    payload: VendorProfileIn,
    user: dict = Depends(require_permission("logistics_masters", "write")),
):
    ex = await db.logistics_vendor_profiles.find_one({"id": vpid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_vendor_profiles.update_one({"id": vpid}, {"$set": updates})
    await _audit("vendor_profile", vpid, "update", user, ex.get("vendor_id", ""))
    return {**ex, **updates}


@router.delete("/vendor-profiles/{vpid}")
async def vp_delete(
    vpid: str,
    user: dict = Depends(require_permission("logistics_masters", "delete")),
):
    ex = await db.logistics_vendor_profiles.find_one({"id": vpid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    await db.logistics_vendor_profiles.delete_one({"id": vpid})
    await _audit("vendor_profile", vpid, "delete", user, ex.get("vendor_id", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Availability snapshots
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/vehicles/availability")
async def vehicles_availability(user: dict = Depends(require_permission("vehicles", "read"))):
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    counts: Dict[str, int] = {s: 0 for s in VEHICLE_STATUSES}
    async for doc in db.vehicles.aggregate(pipeline):
        counts[doc["_id"] or "available"] = doc["count"]
    # Expired doc counts
    today = _today()
    fitness_expired = await db.vehicles.count_documents({"fitness_expiry": {"$lt": today, "$ne": None}})
    insurance_expired = await db.vehicles.count_documents({"insurance_expiry": {"$lt": today, "$ne": None}})
    total = await db.vehicles.count_documents({})
    return {
        "total": total,
        "by_status": counts,
        "fitness_expired": fitness_expired,
        "insurance_expired": insurance_expired,
        "as_of": now_iso(),
    }


@router.get("/drivers/availability")
async def drivers_availability(user: dict = Depends(require_permission("drivers", "read"))):
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    counts: Dict[str, int] = {s: 0 for s in DRIVER_STATUSES}
    async for doc in db.drivers.aggregate(pipeline):
        counts[doc["_id"] or "available"] = doc["count"]
    today = _today()
    license_expired = await db.drivers.count_documents({"license_expiry": {"$lt": today, "$ne": None}})
    total = await db.drivers.count_documents({})
    return {
        "total": total,
        "by_status": counts,
        "license_expired": license_expired,
        "as_of": now_iso(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Logistics Dashboard — 20 real-time KPIs
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def dashboard(user: dict = Depends(require_permission("vehicles", "read"))):
    today = _today()

    total_vehicles = await db.vehicles.count_documents({})
    veh_available = await db.vehicles.count_documents({"status": "available"})
    veh_in_transit = await db.vehicles.count_documents({"status": "in_transit"})
    veh_maintenance = await db.vehicles.count_documents({"status": "maintenance"})

    total_drivers = await db.drivers.count_documents({})
    drv_available = await db.drivers.count_documents({"status": "available"})
    drv_on_trip = await db.drivers.count_documents({"status": "on_trip"})

    dr_pending = await db.logistics_dispatch_requests.count_documents({"status": {"$in": ["draft", "pending_approval"]}})
    dr_approved = await db.logistics_dispatch_requests.count_documents({"status": "approved"})
    dr_in_transit = await db.logistics_dispatch_requests.count_documents({"status": "in_transit"})
    dr_delivery_pending = await db.logistics_dispatch_requests.count_documents({"status": {"$in": ["approved", "allocated", "in_transit"]}})
    dr_return = await db.logistics_dispatch_requests.count_documents({"dispatch_type": "return", "status": {"$ne": "closed"}})
    dr_manpower = await db.logistics_dispatch_requests.count_documents({"dispatch_type": "manpower", "status": {"$ne": "closed"}})
    dr_material = await db.logistics_dispatch_requests.count_documents({"dispatch_type": "material", "status": {"$in": ["approved", "allocated", "in_transit"]}})
    dr_overdue = await db.logistics_dispatch_requests.count_documents({
        "required_date": {"$lt": today, "$ne": None},
        "status": {"$nin": ["delivered", "closed", "cancelled"]},
    })

    # Fitness/insurance/license alerts
    fitness_expired = await db.vehicles.count_documents({"fitness_expiry": {"$lt": today, "$ne": None}})
    insurance_expired = await db.vehicles.count_documents({"insurance_expiry": {"$lt": today, "$ne": None}})
    license_expired = await db.drivers.count_documents({"license_expiry": {"$lt": today, "$ne": None}})

    recent_dispatches = await db.logistics_dispatch_requests.find(
        {}, {"_id": 0, "dr_no": 1, "dispatch_type": 1, "status": 1, "project_code": 1, "created_at": 1}
    ).sort("created_at", -1).limit(5).to_list(5)

    return {
        "as_of": now_iso(),
        "kpis": {
            "total_vehicles":            total_vehicles,
            "vehicles_available":        veh_available,
            "vehicles_in_transit":       veh_in_transit,
            "vehicles_maintenance":      veh_maintenance,
            "drivers_available":         drv_available,
            "drivers_on_trip":           drv_on_trip,
            "total_drivers":             total_drivers,
            "dispatch_pending":          dr_pending,
            "dispatch_approved":         dr_approved,
            "dispatch_in_transit":       dr_in_transit,
            "delivery_pending":          dr_delivery_pending,
            "return_transport_pending":  dr_return,
            "manpower_mobilization":     dr_manpower,
            "material_movement":         dr_material,
            "overdue_deliveries":        dr_overdue,
            "fitness_expired":           fitness_expired,
            "insurance_expired":         insurance_expired,
            "driver_license_expired":    license_expired,
            "fuel_entries_this_month":   0,  # Phase 2
            "vehicle_expense_this_month": 0, # Phase 2
        },
        "recent_dispatches": recent_dispatches,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Audit Log
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/audit-log")
async def audit_log(
    record_kind: Optional[str] = None,
    action: Optional[str] = None,
    _from: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    limit: int = 500,
    user: dict = Depends(require_permission("logistics_audit", "read")),
):
    if limit < 1 or limit > 5000:
        raise HTTPException(400, "limit must be 1..5000")
    q: Dict[str, Any] = {}
    if record_kind:
        q["record_kind"] = record_kind
    if action:
        q["action"] = {"$regex": action, "$options": "i"}
    if _from or to:
        q["at"] = {}
        if _from:
            q["at"]["$gte"] = _from
        if to:
            q["at"]["$lte"] = to + "T23:59:59"
    rows = await db.logistics_audit_log.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return {"count": len(rows), "rows": rows}


@router.get("/audit-log/kinds")
async def audit_kinds(user: dict = Depends(require_permission("logistics_audit", "read"))):
    kinds = await db.logistics_audit_log.distinct("record_kind")
    return sorted([k for k in kinds if k])
