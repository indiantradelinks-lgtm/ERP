"""
Iter 134 — Logistics Module · Phase 3 · Manpower Mobilization
==============================================================

Manpower mobilization / demobilization / travel / accommodation / site reporting.

Collections:
  * logistics_mobilizations         — request with workers[] sub-list
  * logistics_travel                — travel arrangements
  * logistics_accommodations        — hotel / camp / hotel bookings
  * logistics_local_conveyance      — daily / trip conveyance
  * logistics_site_reporting        — site check-in confirmation
  * logistics_demobilizations       — return-side logistics

Endpoints (all under /api/logistics):
  * CRUD /mobilizations
  * CRUD /travel
  * CRUD /accommodations
  * CRUD /local-conveyance
  * CRUD /site-reporting
  * CRUD /demobilizations
  * GET  /mobilization-dashboard     (aggregates for quick KPIs)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Request, APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core import db, now_iso, new_id, require_permission
from pagination import maybe_paged, paged_or_rows

router = APIRouter(prefix="/logistics", tags=["logistics-phase3"])

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _next_int(key: str) -> int:
    doc = await db.sequences.find_one_and_update(
        {"_id": key}, {"$inc": {"value": 1}}, upsert=True, return_document=True
    )
    return int(doc["value"])


async def _audit(kind: str, rid: str, action: str, user: dict, record_no: str = "",
                 meta: Optional[Dict] = None):
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


def _yr() -> int:
    return datetime.now(timezone.utc).year


# ═══════════════════════════════════════════════════════════════════════════
# Manpower Mobilization Request
# ═══════════════════════════════════════════════════════════════════════════

MOB_STATUSES = ["draft", "pending_approval", "approved", "in_progress",
                "reported", "completed", "cancelled"]


class WorkerLine(BaseModel):
    employee_id: Optional[str] = None
    name: str
    trade: Optional[str] = None
    skill: Optional[str] = None
    contact: Optional[str] = None


class MobilizationIn(BaseModel):
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    client: Optional[str] = None
    site_location: Optional[str] = None
    deployment_ref: Optional[str] = None
    reporting_date: Optional[str] = None
    reporting_person: Optional[str] = None
    travel_required: bool = False
    accommodation_required: bool = False
    conveyance_required: bool = False
    ppe_tools_status: Optional[str] = None
    safety_ready: bool = False
    priority: str = "normal"
    workers: List[WorkerLine] = []
    remarks: Optional[str] = None
    status: str = "draft"


@router.get("/mobilizations")
async def mobs_list(
    request: Request,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    paged = await maybe_paged(request, "logistics_mobilizations", q, "created_at", ['mob_no', 'project_name', 'project_code', 'from_location', 'to_location', 'status', 'mob_type', 'remarks'])
    if paged:
        return paged
    return await db.logistics_mobilizations.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/mobilizations")
async def mobs_create(
    payload: MobilizationIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    if payload.status not in MOB_STATUSES:
        raise HTTPException(400, f"status must be one of {MOB_STATUSES}")
    seq = await _next_int("logistics_mobilizations")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "mob_no": f"MOB-{_yr()}-{seq:04d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_mobilizations.insert_one(doc)
    doc.pop("_id", None)
    await _audit("mobilization", doc["id"], "create", user, doc["mob_no"],
                 {"workers": len(payload.workers)})
    return doc


@router.put("/mobilizations/{mid}")
async def mobs_update(
    mid: str,
    payload: MobilizationIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_mobilizations.find_one({"id": mid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Mobilization not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user.get("name") or user.get("email")
    await db.logistics_mobilizations.update_one({"id": mid}, {"$set": updates})
    await _audit("mobilization", mid, f"update:{updates['status']}", user, ex.get("mob_no", ""))
    return {**ex, **updates}


@router.delete("/mobilizations/{mid}")
async def mobs_delete(
    mid: str,
    user: dict = Depends(require_permission("dispatch_requests", "delete")),
):
    ex = await db.logistics_mobilizations.find_one({"id": mid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    if ex.get("status") in {"approved", "in_progress", "reported", "completed"}:
        raise HTTPException(400, "Cannot hard-delete an approved mobilization — cancel instead")
    await db.logistics_mobilizations.delete_one({"id": mid})
    await _audit("mobilization", mid, "delete", user, ex.get("mob_no", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Travel Arrangement
# ═══════════════════════════════════════════════════════════════════════════

TRAVEL_MODES = ["bus", "train", "flight", "company_vehicle", "vendor_vehicle", "own"]


class TravelIn(BaseModel):
    mob_id: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    travel_mode: str = "bus"
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    travel_date: Optional[str] = None
    ticket_ref: Optional[str] = None
    cost: Optional[float] = None
    paid_by: Optional[str] = None
    attachment_url: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    status: str = "planned"
    remarks: Optional[str] = None


@router.get("/travel")
async def travel_list(
    request: Request,
    mob_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if mob_id:
        q["mob_id"] = mob_id
    paged = await maybe_paged(request, "logistics_travel", q, "created_at", ['mob_no', 'employee_name', 'traveller_name', 'mode', 'from_location', 'to_location', 'status', 'pnr', 'ticket_no'])
    if paged:
        return paged
    return await db.logistics_travel.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/travel")
async def travel_create(
    payload: TravelIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    if payload.travel_mode not in TRAVEL_MODES:
        raise HTTPException(400, f"travel_mode must be one of {TRAVEL_MODES}")
    if payload.mob_id:
        mob = await db.logistics_mobilizations.find_one({"id": payload.mob_id})
        if not mob:
            raise HTTPException(400, "Mobilization not found")
        if mob.get("status") in {"draft", "pending_approval"}:
            raise HTTPException(400, "Travel cannot be confirmed — deployment not approved")
    if not payload.project_code and payload.status == "confirmed":
        raise HTTPException(400, "Confirmed travel requires a project code")
    seq = await _next_int("logistics_travel")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "travel_no": f"TRV-{_yr()}-{seq:04d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_travel.insert_one(doc)
    doc.pop("_id", None)
    await _audit("travel", doc["id"], "create", user, doc["travel_no"], {"cost": doc.get("cost")})
    return doc


@router.put("/travel/{tid}")
async def travel_update(
    tid: str,
    payload: TravelIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_travel.find_one({"id": tid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_travel.update_one({"id": tid}, {"$set": updates})
    await _audit("travel", tid, "update", user, ex.get("travel_no", ""))
    return {**ex, **updates}


# ═══════════════════════════════════════════════════════════════════════════
# Accommodation
# ═══════════════════════════════════════════════════════════════════════════

ACC_TYPES = ["company", "client", "vendor", "hotel", "labour_camp", "other"]


class AccommodationIn(BaseModel):
    mob_id: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    acc_type: str = "hotel"
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    vendor_name: Optional[str] = None
    cost: Optional[float] = None
    attachment_url: Optional[str] = None
    status: str = "planned"
    remarks: Optional[str] = None


@router.get("/accommodations")
async def acc_list(
    mob_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if mob_id:
        q["mob_id"] = mob_id
    return await db.logistics_accommodations.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/accommodations")
async def acc_create(
    payload: AccommodationIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    if payload.acc_type not in ACC_TYPES:
        raise HTTPException(400, f"acc_type must be one of {ACC_TYPES}")
    seq = await _next_int("logistics_accommodations")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "acc_no": f"ACC-{_yr()}-{seq:04d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_accommodations.insert_one(doc)
    doc.pop("_id", None)
    await _audit("accommodation", doc["id"], "create", user, doc["acc_no"])
    return doc


@router.put("/accommodations/{aid}")
async def acc_update(
    aid: str,
    payload: AccommodationIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_accommodations.find_one({"id": aid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    if payload.status == "closed" and not payload.check_out:
        raise HTTPException(400, "Cannot close accommodation without a check_out date")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_accommodations.update_one({"id": aid}, {"$set": updates})
    await _audit("accommodation", aid, "update", user, ex.get("acc_no", ""))
    return {**ex, **updates}


# ═══════════════════════════════════════════════════════════════════════════
# Local Conveyance
# ═══════════════════════════════════════════════════════════════════════════

class ConveyanceIn(BaseModel):
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    conveyance_date: Optional[str] = None
    mode: Optional[str] = None
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    amount: Optional[float] = None
    bill_ref: Optional[str] = None
    status: str = "submitted"
    remarks: Optional[str] = None


@router.get("/local-conveyance")
async def conv_list(user: dict = Depends(require_permission("dispatch_requests", "read"))):
    return await db.logistics_local_conveyance.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/local-conveyance")
async def conv_create(
    payload: ConveyanceIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    seq = await _next_int("logistics_local_conveyance")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "conv_no": f"CNV-{_yr()}-{seq:04d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_local_conveyance.insert_one(doc)
    doc.pop("_id", None)
    await _audit("conveyance", doc["id"], "create", user, doc["conv_no"])
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# Site Reporting Confirmation
# ═══════════════════════════════════════════════════════════════════════════

class SiteReportingIn(BaseModel):
    mob_id: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    reporting_at: Optional[str] = None
    reported_to: Optional[str] = None
    attendance_start: Optional[str] = None
    safety_induction_done: bool = False
    accommodation_confirmed: bool = False
    remarks: Optional[str] = None
    status: str = "reported"


@router.get("/site-reporting")
async def sr_list(
    mob_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if mob_id:
        q["mob_id"] = mob_id
    return await db.logistics_site_reporting.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/site-reporting")
async def sr_create(
    payload: SiteReportingIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    seq = await _next_int("logistics_site_reporting")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "sr_no": f"SR-{_yr()}-{seq:04d}",
        "reporting_at": payload.reporting_at or now_iso(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_site_reporting.insert_one(doc)
    doc.pop("_id", None)

    # Optionally advance mobilization status to 'reported'
    if payload.mob_id:
        await db.logistics_mobilizations.update_one(
            {"id": payload.mob_id, "status": {"$in": ["approved", "in_progress"]}},
            {"$set": {"status": "reported", "updated_at": now_iso()}},
        )

    await _audit("site_reporting", doc["id"], "create", user, doc["sr_no"],
                 {"safety_induction_done": doc.get("safety_induction_done")})
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# Demobilization
# ═══════════════════════════════════════════════════════════════════════════

class DemobilizationIn(BaseModel):
    mob_id: Optional[str] = None
    demob_ref: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    demob_date: Optional[str] = None
    return_travel_required: bool = False
    return_destination: Optional[str] = None
    ppe_return_done: bool = False
    store_clearance_done: bool = False
    travel_id: Optional[str] = None
    acc_closure_done: bool = False
    remarks: Optional[str] = None
    status: str = "in_progress"


@router.get("/demobilizations")
async def demob_list(user: dict = Depends(require_permission("dispatch_requests", "read"))):
    return await db.logistics_demobilizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/demobilizations")
async def demob_create(
    payload: DemobilizationIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    seq = await _next_int("logistics_demobilizations")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "demob_no": f"DMB-{_yr()}-{seq:04d}",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_demobilizations.insert_one(doc)
    doc.pop("_id", None)
    await _audit("demobilization", doc["id"], "create", user, doc["demob_no"])
    return doc


@router.put("/demobilizations/{did}")
async def demob_update(
    did: str,
    payload: DemobilizationIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_demobilizations.find_one({"id": did}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    if payload.status == "closed":
        if payload.return_travel_required and not payload.travel_id:
            raise HTTPException(400, "Return travel is required but no travel_id recorded")
        if not payload.store_clearance_done:
            raise HTTPException(400, "Store clearance must be completed before closing")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_demobilizations.update_one({"id": did}, {"$set": updates})
    await _audit("demobilization", did, f"update:{updates['status']}", user, ex.get("demob_no", ""))
    return {**ex, **updates}


# ═══════════════════════════════════════════════════════════════════════════
# Mobilization Dashboard
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/mobilization-dashboard")
async def mob_dashboard(user: dict = Depends(require_permission("dispatch_requests", "read"))):
    total_mobs = await db.logistics_mobilizations.count_documents({})
    mobs_pending = await db.logistics_mobilizations.count_documents({"status": {"$in": ["draft", "pending_approval"]}})
    mobs_approved = await db.logistics_mobilizations.count_documents({"status": "approved"})
    mobs_in_progress = await db.logistics_mobilizations.count_documents({"status": "in_progress"})
    mobs_reported = await db.logistics_mobilizations.count_documents({"status": "reported"})
    travel_planned = await db.logistics_travel.count_documents({"status": "planned"})
    travel_confirmed = await db.logistics_travel.count_documents({"status": "confirmed"})
    acc_active = await db.logistics_accommodations.count_documents({"status": {"$in": ["confirmed", "active"]}})
    demob_pending = await db.logistics_demobilizations.count_documents({"status": {"$in": ["in_progress"]}})
    site_reports_today = await db.logistics_site_reporting.count_documents({
        "reporting_at": {"$gte": datetime.now(timezone.utc).date().isoformat()},
    })
    # sum workers across active mobs
    active_workers = 0
    async for m in db.logistics_mobilizations.find(
        {"status": {"$in": ["approved", "in_progress", "reported"]}}, {"workers": 1, "_id": 0}
    ):
        active_workers += len(m.get("workers") or [])
    return {
        "as_of": now_iso(),
        "kpis": {
            "total_mobilizations": total_mobs,
            "mobs_pending": mobs_pending,
            "mobs_approved": mobs_approved,
            "mobs_in_progress": mobs_in_progress,
            "mobs_reported": mobs_reported,
            "active_workers": active_workers,
            "travel_planned": travel_planned,
            "travel_confirmed": travel_confirmed,
            "accommodations_active": acc_active,
            "site_reports_today": site_reports_today,
            "demob_pending": demob_pending,
        },
    }
