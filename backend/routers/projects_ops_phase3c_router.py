"""Projects & Operations · Phase 3 — Round 3C.

Work Permits + Site Photos + Execution Dashboard.

  • **WorkPermit** (`db.work_permits`)
        permit_no (auto), project_id, permit_type (hot_work / confined_space /
        height / electrical / excavation / general), valid_from, valid_to,
        issued_by, activity_covered, safety_clearance_status (pending/cleared/
        rejected), attachment_ids, status (active|expired|revoked).
        Auto-detects expired permits via `valid_to < today`.

  • **SitePhoto** (`db.site_photos`)
        Thin metadata pointing to existing `db.files` (uploaded via the
        existing `/api/uploads` endpoint with folder=projects parent_type=
        site_photo parent_id=<project_id>). Adds caption + taken_at +
        location + tags.

  • **Execution Dashboard** — aggregate KPIs across phase-3 collections:
        DPRs (pending/approved/today), Issues (open/critical), Permits
        (active/expiring), Measurements (pending certification), Extra
        work (pending approval, total billable value).

  • **DPR Reports** — single endpoint that returns a tabular report of
        DPRs grouped by project, status, or date.

Endpoints (all under `/api/proj-phase3`):

  Permits
    GET    /permits                            — list (filterable + ?expiring_in_days=)
    POST   /permits                            — create
    GET    /permits/{id}                       — fetch
    PUT    /permits/{id}                       — update
    DELETE /permits/{id}
    GET    /permits/{project_id}/expiring      — soft-alerts list

  Site photos
    GET    /photos/{project_id}                — list
    POST   /photos/{project_id}                — create metadata after upload
    DELETE /photos/{photo_id}

  Execution Dashboard
    GET    /execution/{project_id}/dashboard
    GET    /reports/dpr                        — flexible report
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id


router = APIRouter(prefix="/proj-phase3", tags=["projects-ops-phase3-r3"])


async def _resolve_project(pid: str) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, f"Project '{pid}' not found")
    return p


def _today() -> str:
    return date.today().isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 · Work Permits
# ═══════════════════════════════════════════════════════════════════════════

PERMIT_TYPES = ("hot_work", "confined_space", "height", "electrical",
                 "excavation", "lifting", "general")
PERMIT_STATUS = ("active", "expired", "revoked", "pending_clearance")
CLEARANCE_STATUS = ("pending", "cleared", "rejected")


class WorkPermitIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    permit_no: Optional[str] = ""
    permit_type: str = "general"
    permit_date: Optional[str] = ""
    valid_from: Optional[str] = ""
    valid_to: Optional[str] = ""
    issued_by: Optional[str] = ""               # client/site rep
    activity_covered: Optional[str] = ""
    safety_clearance_status: str = "pending"
    attachment_ids: List[str] = []
    remarks: Optional[str] = ""


async def _next_permit_no(project_code: str) -> str:
    n = await db.work_permits.count_documents({})
    return f"WP-{project_code or 'GEN'}-{n + 1:05d}"


def _derive_permit_status(valid_to: str, current_status: Optional[str] = None) -> str:
    if current_status == "revoked":
        return current_status
    # if past valid_to → expired regardless of clearance
    if valid_to:
        try:
            if datetime.fromisoformat(valid_to).date() < date.today():
                return "expired"
        except Exception:
            pass
    if current_status == "pending_clearance":
        return "pending_clearance"
    return current_status or "active"


@router.get("/permits")
async def list_permits(project_id: Optional[str] = None,
                       status: Optional[str] = None,
                       expiring_in_days: Optional[int] = None,
                       user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    rows = await db.work_permits.find(q, {"_id": 0}).sort("valid_to", 1).to_list(2000)
    # auto-tag expired
    for r in rows:
        r["status"] = _derive_permit_status(r.get("valid_to") or "", r.get("status"))
    if expiring_in_days is not None:
        threshold = (date.today() + timedelta(days=expiring_in_days)).isoformat()
        rows = [r for r in rows
                if r.get("status") == "active" and (r.get("valid_to") or "9999") <= threshold]
    return rows


@router.post("/permits")
async def create_permit(payload: WorkPermitIn,
                        user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    if payload.permit_type not in PERMIT_TYPES:
        raise HTTPException(400, f"Invalid permit_type. Allowed: {PERMIT_TYPES}")
    if payload.safety_clearance_status not in CLEARANCE_STATUS:
        raise HTTPException(400, f"Invalid clearance status. Allowed: {CLEARANCE_STATUS}")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "permit_no": (payload.permit_no or "").strip() or await _next_permit_no(p.get("code") or ""),
        "permit_date": payload.permit_date or now_iso()[:10],
        "project_code": p.get("code"),
        "project_name": p.get("name"),
        "status": _derive_permit_status(payload.valid_to or "", "active" if payload.safety_clearance_status == "cleared" else "pending_clearance"),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.work_permits.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/permits/{permit_id}")
async def get_permit(permit_id: str,
                     user: dict = Depends(require_permission("projects", "read"))):
    p = await db.work_permits.find_one({"id": permit_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Permit not found")
    p["status"] = _derive_permit_status(p.get("valid_to") or "", p.get("status"))
    return p


@router.put("/permits/{permit_id}")
async def update_permit(permit_id: str, payload: WorkPermitIn,
                        user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.work_permits.find_one({"id": permit_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Permit not found")
    if payload.permit_type not in PERMIT_TYPES:
        raise HTTPException(400, f"Invalid permit_type. Allowed: {PERMIT_TYPES}")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    patch["status"] = _derive_permit_status(payload.valid_to or "", existing.get("status"))
    patch["updated_at"] = now_iso()
    await db.work_permits.update_one({"id": permit_id}, {"$set": patch})
    return await db.work_permits.find_one({"id": permit_id}, {"_id": 0})


@router.delete("/permits/{permit_id}")
async def delete_permit(permit_id: str,
                        user: dict = Depends(require_permission("projects", "delete"))):
    r = await db.work_permits.delete_one({"id": permit_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Permit not found")
    return {"ok": True}


@router.get("/permits/{project_id}/expiring")
async def permits_expiring(project_id: str, days: int = 7,
                           user: dict = Depends(require_permission("projects", "read"))):
    """Permits whose valid_to falls within the next `days` days OR already expired."""
    await _resolve_project(project_id)
    threshold = (date.today() + timedelta(days=days)).isoformat()
    rows = await db.work_permits.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    expiring = []
    today_str = _today()
    for r in rows:
        r["status"] = _derive_permit_status(r.get("valid_to") or "", r.get("status"))
        if r.get("status") == "expired":
            r["alert"] = "expired"
            expiring.append(r)
        elif r.get("status") == "active" and r.get("valid_to") and r["valid_to"] <= threshold:
            r["alert"] = "expiring_soon"
            r["days_to_expiry"] = (datetime.fromisoformat(r["valid_to"]).date() - date.today()).days
            expiring.append(r)
        elif r.get("status") == "pending_clearance":
            r["alert"] = "pending_clearance"
            expiring.append(r)
    return {"today": today_str, "horizon_days": days, "rows": expiring, "count": len(expiring)}


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 · Site Photos
# ═══════════════════════════════════════════════════════════════════════════

class SitePhotoIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    file_id: str = Field(..., min_length=1)         # existing /api/uploads response.id
    caption: Optional[str] = ""
    taken_at: Optional[str] = ""
    location: Optional[str] = ""
    activity_id: Optional[str] = None
    dpr_id: Optional[str] = None
    site_id: Optional[str] = None
    tags: List[str] = []


@router.get("/photos/{project_id}")
async def list_photos(project_id: str,
                      user: dict = Depends(require_permission("projects", "read"))):
    rows = await db.site_photos.find({"project_id": project_id}, {"_id": 0}).sort("taken_at", -1).to_list(500)
    if rows:
        file_ids = [r["file_id"] for r in rows if r.get("file_id")]
        files = await db.files.find(
            {"id": {"$in": file_ids}}, {"_id": 0, "id": 1, "original_filename": 1, "title": 1, "content_type": 1}
        ).to_list(500)
        by_id = {f["id"]: f for f in files}
        for r in rows:
            r["file"] = by_id.get(r.get("file_id"))
    return rows


@router.post("/photos/{project_id}")
async def create_photo(project_id: str, payload: SitePhotoIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    await _resolve_project(project_id)
    # ensure file exists
    f = await db.files.find_one({"id": payload.file_id, "is_deleted": False}, {"_id": 0, "id": 1})
    if not f:
        raise HTTPException(404, "Underlying file not found")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "project_id": project_id,
        "taken_at": payload.taken_at or now_iso(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.site_photos.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str,
                       user: dict = Depends(require_permission("projects", "delete"))):
    r = await db.site_photos.delete_one({"id": photo_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Photo not found")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Section 3 · Execution Dashboard
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/execution/{project_id}/dashboard")
async def execution_dashboard(project_id: str,
                              user: dict = Depends(require_permission("projects", "read"))):
    await _resolve_project(project_id)
    today = _today()

    # DPRs
    dpr_total      = await db.dprs.count_documents({"project_id": project_id})
    dpr_pending    = await db.dprs.count_documents({"project_id": project_id, "status": "submitted"})
    dpr_approved   = await db.dprs.count_documents({"project_id": project_id, "status": "approved"})
    dpr_today      = await db.dprs.count_documents({"project_id": project_id, "dpr_date": today})

    # Issues
    issues_open    = await db.site_issues.count_documents({"project_id": project_id, "status": {"$in": ["open", "in_progress"]}})
    issues_critical = await db.site_issues.count_documents({"project_id": project_id, "impact": "critical", "status": {"$ne": "closed"}})
    issues_escalated = await db.site_issues.count_documents({"project_id": project_id, "status": "escalated"})

    # Delays
    delays_open = await db.delay_records.count_documents({"project_id": project_id, "status": {"$ne": "closed"}})

    # Permits
    permits_active = 0
    permits_expiring = 0
    permits_expired = 0
    permit_rows = await db.work_permits.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    horizon = (date.today() + timedelta(days=7)).isoformat()
    for p in permit_rows:
        st = _derive_permit_status(p.get("valid_to") or "", p.get("status"))
        if st == "expired":
            permits_expired += 1
        elif st == "active":
            permits_active += 1
            if p.get("valid_to") and p["valid_to"] <= horizon:
                permits_expiring += 1

    # Measurements
    ms_pending = await db.measurement_sheets.count_documents(
        {"project_id": project_id, "status": {"$in": ["submitted", "checked"]}}
    )
    pending_cert_lines = await db.measurement_lines.count_documents(
        {"project_id": project_id, "client_certification_status": {"$in": ["pending", "partial", "held"]}}
    )

    # Extra Work
    ew_pending = await db.extra_works.count_documents(
        {"project_id": project_id, "approval_status": "pending"}
    )
    ew_billable_rows = await db.extra_works.find(
        {"project_id": project_id, "approval_status": "approved", "billing_status": "pending"},
        {"_id": 0, "estimated_value": 1},
    ).to_list(500)
    ew_billable_value = round(sum(float(r.get("estimated_value") or 0) for r in ew_billable_rows), 2)

    # Progress avg
    wp_rows = await db.work_progress.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    avg_actual = round(sum(float(r.get("actual_progress_pct") or 0) for r in wp_rows) / len(wp_rows), 2) if wp_rows else 0.0
    delayed_progress = len([r for r in wp_rows if r.get("status") == "delayed"])

    return {
        "as_of": today,
        "dpr": {"total": dpr_total, "pending_approval": dpr_pending,
                "approved": dpr_approved, "today": dpr_today},
        "issues": {"open": issues_open, "critical_open": issues_critical, "escalated": issues_escalated},
        "delays": {"open": delays_open},
        "permits": {"active": permits_active, "expiring_in_7d": permits_expiring, "expired": permits_expired},
        "measurements": {"pending_approval": ms_pending, "pending_certification_lines": pending_cert_lines},
        "extra_work": {"pending_approval": ew_pending, "billable_value": ew_billable_value, "billable_count": len(ew_billable_rows)},
        "progress": {"avg_actual_pct": avg_actual, "delayed_items": delayed_progress, "total_items": len(wp_rows)},
    }


@router.get("/reports/dpr")
async def report_dpr(project_id: Optional[str] = None,
                     status: Optional[str] = None,
                     from_date: Optional[str] = None,
                     to_date: Optional[str] = None,
                     user: dict = Depends(require_permission("projects", "read"))):
    """Flexible DPR report. Returns rows + small aggregate."""
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    if from_date or to_date:
        q["dpr_date"] = {}
        if from_date:
            q["dpr_date"]["$gte"] = from_date
        if to_date:
            q["dpr_date"]["$lte"] = to_date
    rows = await db.dprs.find(q, {"_id": 0}).sort("dpr_date", -1).to_list(5000)
    summary = {
        "total": len(rows),
        "approved": sum(1 for r in rows if r.get("status") == "approved"),
        "submitted": sum(1 for r in rows if r.get("status") == "submitted"),
        "rejected": sum(1 for r in rows if r.get("status") == "rejected"),
        "total_manpower_present": sum(int(r.get("manpower_present") or 0) for r in rows),
        "total_overtime_hours": round(sum(float(r.get("overtime_hours") or 0) for r in rows), 2),
    }
    return {"rows": rows, "summary": summary}
