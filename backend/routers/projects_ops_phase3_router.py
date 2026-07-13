"""Projects & Operations · Phase 3 — Round 3A.

Daily Site Execution Control · DPR + Work Progress

  • **DailyProgressReport** (`db.dprs`) — header with site context, weather,
    deployment summary, status flow (draft → submitted → approved/rejected/revised).
  • **DPRLine** (`db.dpr_lines`) — per-activity / BOQ-line work logged today.
  • **WorkProgress** (`db.work_progress`) — one row per (project, boq_line_id OR
    activity_id), auto-upserted from APPROVED DPRs only. Holds planned vs
    actual qty, cumulative qty, % progress, status (on_track/delayed/ahead/on_hold),
    delay reason, corrective action, target recovery date.

  Validation rules (per spec):
    1. DPR cannot be submitted without project_code
    2. DPR date must lie within project_start_date .. project_end_date
       (unless caller has approve override)
    3. line.completed_qty cannot be negative
    4. cumulative_qty cannot exceed BOQ qty (unless `extra_work=true` flagged
       on the line OR the BOQ line has `revised` allowance)
    5. approved DPR cannot be deleted (super_admin allowed for emergency)
    6. any revision (after approval) writes a snapshot to
       `db.dpr_revisions` for audit trail
    7. WorkProgress only updated on APPROVED status — submission alone is not
       enough.

Endpoints (all under `/api/proj-phase3`):

  DPR
    GET    /dprs                              — list (filterable)
    POST   /dprs                              — create draft (header + lines)
    GET    /dprs/{id}                         — header + lines
    PUT    /dprs/{id}                         — update (draft / rejected only)
    DELETE /dprs/{id}                         — delete (draft only; admin override)
    POST   /dprs/{id}/submit                  — draft → submitted
    POST   /dprs/{id}/approve                 — submitted → approved (cascades to work_progress)
    POST   /dprs/{id}/reject                  — submitted → rejected (with reason)
    POST   /dprs/{id}/revise                  — approved → revised (snapshots prior state)
    POST   /dprs/{id}/lines                   — add line to existing DPR
    PUT    /dprs/{id}/lines/{line_id}         — update line
    DELETE /dprs/{id}/lines/{line_id}         — delete line

  Work Progress
    GET    /work-progress/{project_id}        — list rows
    PUT    /work-progress/{row_id}            — patch planned_qty / variance fields
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/proj-phase3", tags=["projects-ops-phase3"])


# ─── helpers ──────────────────────────────────────────────────────────
async def _resolve_project(pid: str) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, f"Project '{pid}' not found")
    return p


def _within_period(dpr_date: str, project: dict) -> bool:
    """Returns True if `dpr_date` ∈ [project.start_date, project.end_date].
    Empty bounds → permissive."""
    if not dpr_date:
        return True
    try:
        d = datetime.fromisoformat(dpr_date).date()
    except Exception:
        return True
    s = project.get("start_date") or ""
    e = project.get("end_date") or ""
    try:
        if s and d < datetime.fromisoformat(s).date():
            return False
    except Exception:
        pass
    try:
        if e and d > datetime.fromisoformat(e).date():
            return False
    except Exception:
        pass
    return True


async def _next_dpr_no(project_code: str) -> str:
    n = await db.dprs.count_documents({})
    return f"DPR-{project_code or 'GEN'}-{n + 1:05d}"


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 · DPR models
# ═══════════════════════════════════════════════════════════════════════════

DPR_STATUS = ("draft", "submitted", "approved", "rejected", "revised")


class DPRLineIn(BaseModel):
    """One row of work captured in a DPR."""
    activity_id: Optional[str] = None       # link to project_activities
    boq_line_id: Optional[str] = None       # link to project_boq_lines
    boq_id: Optional[str] = None
    description: str = Field(..., min_length=1, max_length=500)
    uom: Optional[str] = ""
    qty_completed_today: float = 0.0
    cumulative_qty_completed: Optional[float] = None   # auto-computed if omitted
    balance_qty: Optional[float] = None                 # auto-computed if omitted
    boq_qty: Optional[float] = None                    # snapshot at time of submission
    extra_work: bool = False
    remarks: Optional[str] = ""


class DPRIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    dpr_no: Optional[str] = ""
    dpr_date: str = Field(..., min_length=1)
    site_id: Optional[str] = None
    site_location: Optional[str] = ""
    service_type: Optional[str] = ""
    site_incharge: Optional[str] = ""
    project_manager: Optional[str] = ""
    weather_condition: Optional[str] = ""
    work_performed: Optional[str] = ""

    # deployment summary
    manpower_deployed: int = 0
    manpower_present: int = 0
    overtime_hours: float = 0
    material_used_summary: Optional[str] = ""
    tools_used_summary: Optional[str] = ""
    logistics_support_summary: Optional[str] = ""

    # operational
    safety_observations: Optional[str] = ""
    work_permit_status: Optional[str] = ""
    issues_faced: Optional[str] = ""
    delay_reason: Optional[str] = ""
    client_instruction: Optional[str] = ""
    extra_work_identified: bool = False

    lines: List[DPRLineIn] = []
    attachment_ids: List[str] = []      # files.id references
    remarks: Optional[str] = ""


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 · DPR endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/dprs")
async def list_dprs(project_id: Optional[str] = None,
                    status: Optional[str] = None,
                    from_date: Optional[str] = None,
                    to_date: Optional[str] = None,
                    user: dict = Depends(require_permission("projects", "read"))):
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
    rows = await db.dprs.find(q, {"_id": 0}).sort("dpr_date", -1).to_list(2000)
    return rows


async def _compute_line_aggregates(line: dict, project_id: str) -> dict:
    """Backfill cumulative_qty and balance_qty from prior approved DPRs + BOQ line."""
    out = {**line}
    qty_today = float(line.get("qty_completed_today") or 0)
    if qty_today < 0:
        raise HTTPException(400, "Completed quantity cannot be negative")

    # prior approved cumulative for same boq_line_id / activity_id
    key_field = None
    key_value = None
    if line.get("boq_line_id"):
        key_field = "boq_line_id"
        key_value = line["boq_line_id"]
    elif line.get("activity_id"):
        key_field = "activity_id"
        key_value = line["activity_id"]

    prior_cum = 0.0
    if key_field:
        pipeline = [
            {"$match": {"project_id": project_id, "status": "approved"}},
            {"$lookup": {"from": "dpr_lines", "localField": "id", "foreignField": "dpr_id", "as": "lines"}},
            {"$unwind": "$lines"},
            {"$match": {f"lines.{key_field}": key_value}},
            {"$group": {"_id": None, "total": {"$sum": "$lines.qty_completed_today"}}},
        ]
        cur = db.dprs.aggregate(pipeline)
        async for d in cur:
            prior_cum = float(d.get("total") or 0)

    out["cumulative_qty_completed"] = round(prior_cum + qty_today, 4)

    boq_qty = float(line.get("boq_qty") or 0)
    if not boq_qty and line.get("boq_line_id"):
        bq = await db.project_boq_lines.find_one({"id": line["boq_line_id"]}, {"_id": 0, "quantity": 1})
        boq_qty = float((bq or {}).get("quantity") or 0)
        out["boq_qty"] = boq_qty

    if boq_qty:
        out["balance_qty"] = round(max(boq_qty - out["cumulative_qty_completed"], 0), 4)
        # rule 4: cumulative cannot exceed BOQ unless extra_work=True
        if out["cumulative_qty_completed"] > boq_qty + 1e-6 and not line.get("extra_work"):
            raise HTTPException(
                400,
                f"Cumulative {out['cumulative_qty_completed']} would exceed BOQ qty {boq_qty}. "
                f"Mark line as 'extra_work=true' to proceed.",
            )
    else:
        out["balance_qty"] = line.get("balance_qty") or 0
    return out


@router.post("/dprs")
async def create_dpr(payload: DPRIn,
                     user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    if not payload.dpr_date:
        raise HTTPException(400, "DPR date is required")
    if not _within_period(payload.dpr_date, p):
        raise HTTPException(
            400,
            f"DPR date {payload.dpr_date} is outside project period "
            f"{p.get('start_date')} .. {p.get('end_date')}",
        )
    if payload.site_id and not await db.sites.find_one({"id": payload.site_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Site not found")

    header_id = new_id()
    doc = payload.model_dump(exclude={"lines"})
    doc.update({
        "id": header_id,
        "dpr_no": (payload.dpr_no or "").strip() or await _next_dpr_no(p.get("code") or ""),
        "project_code": p.get("code"),
        "project_name": p.get("name"),
        "client_id": p.get("client_id"),
        "client_name": p.get("client_name") or p.get("client"),
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "submitted_by": None,
        "submitted_at": None,
        "approved_by": None,
        "approved_at": None,
    })
    await db.dprs.insert_one(doc)

    # lines
    line_docs: List[dict] = []
    for ln in payload.lines:
        ln_dict = ln.model_dump()
        ln_dict = await _compute_line_aggregates(ln_dict, payload.project_id)
        ln_dict.update({
            "id": new_id(),
            "dpr_id": header_id,
            "project_id": payload.project_id,
            "created_at": now_iso(),
        })
        line_docs.append(ln_dict)
    if line_docs:
        await db.dpr_lines.insert_many(line_docs)

    await audit(user=user, action="create", resource="dprs",
                record_id=header_id, before={}, after=doc, ip="dpr")
    return await _hydrate_dpr(header_id)


@router.get("/dprs/{dpr_id}")
async def get_dpr(dpr_id: str,
                  user: dict = Depends(require_permission("projects", "read"))):
    return await _hydrate_dpr(dpr_id)


async def _hydrate_dpr(dpr_id: str) -> dict:
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    lines = await db.dpr_lines.find({"dpr_id": dpr_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    # attachment metadata
    atts = []
    if d.get("attachment_ids"):
        atts = await db.files.find(
            {"id": {"$in": d["attachment_ids"]}, "is_deleted": False},
            {"_id": 0, "id": 1, "title": 1, "original_filename": 1, "content_type": 1, "size": 1},
        ).to_list(50)
    return {**d, "lines": lines, "attachments": atts}


@router.put("/dprs/{dpr_id}")
async def update_dpr(dpr_id: str, payload: DPRIn,
                     user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "DPR not found")
    if existing.get("status") not in ("draft", "rejected"):
        raise HTTPException(403, f"DPR in '{existing['status']}' state cannot be edited. Use /revise.")

    patch = payload.model_dump(exclude={"lines"})
    # project_id is immutable
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.dprs.update_one({"id": dpr_id}, {"$set": patch})

    # replace lines wholesale
    await db.dpr_lines.delete_many({"dpr_id": dpr_id})
    new_lines: List[dict] = []
    for ln in payload.lines:
        ln_dict = ln.model_dump()
        ln_dict = await _compute_line_aggregates(ln_dict, existing["project_id"])
        ln_dict.update({
            "id": new_id(),
            "dpr_id": dpr_id,
            "project_id": existing["project_id"],
            "created_at": now_iso(),
        })
        new_lines.append(ln_dict)
    if new_lines:
        await db.dpr_lines.insert_many(new_lines)

    await audit(user=user, action="update", resource="dprs",
                record_id=dpr_id, before=existing, after=patch, ip="dpr")
    return await _hydrate_dpr(dpr_id)


@router.delete("/dprs/{dpr_id}")
async def delete_dpr(dpr_id: str,
                     user: dict = Depends(require_permission("projects", "delete"))):
    existing = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "DPR not found")
    if existing.get("status") == "approved" and user.get("role") != "super_admin":
        raise HTTPException(403, "Approved DPR cannot be deleted (Super Admin override only).")
    await db.dpr_lines.delete_many({"dpr_id": dpr_id})
    await db.dprs.delete_one({"id": dpr_id})
    await audit(user=user, action="delete", resource="dprs",
                record_id=dpr_id, before=existing, after={}, ip="dpr")
    return {"ok": True}


# ─── status workflow ──────────────────────────────────────────────────
@router.post("/dprs/{dpr_id}/submit")
async def submit_dpr(dpr_id: str,
                     user: dict = Depends(require_permission("projects", "write"))):
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    if not d.get("project_id"):
        raise HTTPException(400, "Project code is missing")
    if d.get("status") not in ("draft", "rejected"):
        raise HTTPException(403, f"Cannot submit a DPR in '{d['status']}' state")
    patch = {
        "status": "submitted",
        "submitted_by": user.get("name") or user.get("email"),
        "submitted_at": now_iso(),
    }
    await db.dprs.update_one({"id": dpr_id}, {"$set": patch})
    await audit(user=user, action="submit", resource="dprs", record_id=dpr_id, before=d, after=patch, ip="dpr")
    return await _hydrate_dpr(dpr_id)


@router.post("/dprs/{dpr_id}/approve")
async def approve_dpr(dpr_id: str,
                      user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head", "project_manager"):
        raise HTTPException(403, "Only Project Manager / Dept Head / GM / Director / Super Admin can approve a DPR")
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    if d.get("status") not in ("submitted", "revised"):
        raise HTTPException(403, f"Cannot approve DPR in '{d['status']}' state")
    patch = {
        "status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
    }
    await db.dprs.update_one({"id": dpr_id}, {"$set": patch})
    # cascade → work_progress upsert
    await _cascade_work_progress(dpr_id, user)
    await audit(user=user, action="approve", resource="dprs", record_id=dpr_id, before=d, after=patch, ip="dpr")
    return await _hydrate_dpr(dpr_id)


@router.post("/dprs/{dpr_id}/reject")
async def reject_dpr(dpr_id: str, reason: str = Query(...),
                     user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head", "project_manager"):
        raise HTTPException(403, "Only PM / Dept Head / GM / Director can reject")
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    if d.get("status") not in ("submitted", "revised"):
        raise HTTPException(403, f"Cannot reject DPR in '{d['status']}' state")
    patch = {
        "status": "rejected",
        "rejected_by": user.get("name") or user.get("email"),
        "rejected_at": now_iso(),
        "rejection_reason": reason,
    }
    await db.dprs.update_one({"id": dpr_id}, {"$set": patch})
    await audit(user=user, action="reject", resource="dprs", record_id=dpr_id, before=d, after=patch, ip="dpr")
    return await _hydrate_dpr(dpr_id)


@router.post("/dprs/{dpr_id}/revise")
async def revise_dpr(dpr_id: str,
                     user: dict = Depends(require_permission("projects", "write"))):
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    if d.get("status") != "approved":
        raise HTTPException(403, "Only approved DPRs can be revised. Use /reject if still in review.")
    # snapshot to dpr_revisions for audit trail
    lines = await db.dpr_lines.find({"dpr_id": dpr_id}, {"_id": 0}).to_list(2000)
    snapshot = {
        "id": new_id(),
        "dpr_id": dpr_id,
        "snapshot_at": now_iso(),
        "snapshot_by": user.get("name") or user.get("email"),
        "header": copy.deepcopy(d),
        "lines": copy.deepcopy(lines),
    }
    await db.dpr_revisions.insert_one(snapshot)
    patch = {
        "status": "revised",
        "revised_by": user.get("name") or user.get("email"),
        "revised_at": now_iso(),
    }
    await db.dprs.update_one({"id": dpr_id}, {"$set": patch})
    await audit(user=user, action="revise", resource="dprs", record_id=dpr_id, before=d, after=patch, ip="dpr")
    return await _hydrate_dpr(dpr_id)


# ─── DPR lines: incremental CRUD on an existing DPR ───────────────────
@router.post("/dprs/{dpr_id}/lines")
async def add_line(dpr_id: str, payload: DPRLineIn,
                   user: dict = Depends(require_permission("projects", "write"))):
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    if d.get("status") not in ("draft", "rejected"):
        raise HTTPException(403, f"Cannot add lines to a DPR in '{d['status']}' state")
    ln_dict = await _compute_line_aggregates(payload.model_dump(), d["project_id"])
    ln_dict.update({
        "id": new_id(),
        "dpr_id": dpr_id,
        "project_id": d["project_id"],
        "created_at": now_iso(),
    })
    await db.dpr_lines.insert_one(ln_dict)
    return {k: v for k, v in ln_dict.items() if k != "_id"}


@router.put("/dprs/{dpr_id}/lines/{line_id}")
async def update_line(dpr_id: str, line_id: str, payload: DPRLineIn,
                      user: dict = Depends(require_permission("projects", "write"))):
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    if d.get("status") not in ("draft", "rejected"):
        raise HTTPException(403, f"Cannot edit lines of a DPR in '{d['status']}' state")
    existing = await db.dpr_lines.find_one({"id": line_id, "dpr_id": dpr_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Line not found")
    patch = await _compute_line_aggregates(payload.model_dump(), d["project_id"])
    patch["updated_at"] = now_iso()
    await db.dpr_lines.update_one({"id": line_id, "dpr_id": dpr_id}, {"$set": patch})
    return await db.dpr_lines.find_one({"id": line_id}, {"_id": 0})


@router.delete("/dprs/{dpr_id}/lines/{line_id}")
async def delete_line(dpr_id: str, line_id: str,
                      user: dict = Depends(require_permission("projects", "write"))):
    d = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "DPR not found")
    if d.get("status") not in ("draft", "rejected"):
        raise HTTPException(403, f"Cannot edit lines of a DPR in '{d['status']}' state")
    r = await db.dpr_lines.delete_one({"id": line_id, "dpr_id": dpr_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Line not found")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Section 3 · Work Progress (auto-cascade from approved DPR)
# ═══════════════════════════════════════════════════════════════════════════

PROGRESS_STATUS = ("on_track", "delayed", "ahead", "on_hold")


class WorkProgressPatch(BaseModel):
    planned_qty: Optional[float] = None
    planned_progress_pct: Optional[float] = None
    status: Optional[str] = None
    delay_reason: Optional[str] = ""
    corrective_action: Optional[str] = ""
    responsible_person: Optional[str] = ""
    target_recovery_date: Optional[str] = ""


def _progress_status(planned_pct: float, actual_pct: float) -> str:
    if actual_pct >= planned_pct + 5:
        return "ahead"
    if actual_pct < planned_pct - 5:
        return "delayed"
    return "on_track"


async def _cascade_work_progress(dpr_id: str, user: dict):
    """When a DPR is approved, upsert work_progress rows per
    (boq_line_id OR activity_id) using cumulative qty from all approved DPRs."""
    dpr = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not dpr:
        return
    lines = await db.dpr_lines.find({"dpr_id": dpr_id}, {"_id": 0}).to_list(2000)
    project_id = dpr["project_id"]
    for ln in lines:
        key_field = None
        key_value = None
        if ln.get("boq_line_id"):
            key_field, key_value = "boq_line_id", ln["boq_line_id"]
        elif ln.get("activity_id"):
            key_field, key_value = "activity_id", ln["activity_id"]
        else:
            continue

        # planned qty: from BOQ line if available, else 0
        planned_qty = 0.0
        boq_line = None
        if key_field == "boq_line_id":
            boq_line = await db.project_boq_lines.find_one({"id": key_value}, {"_id": 0})
            planned_qty = float((boq_line or {}).get("quantity") or 0)
        elif key_field == "activity_id":
            # no native qty on activity — leave 0
            planned_qty = 0.0

        # cumulative = ln.cumulative_qty_completed (already computed at insert)
        cum = float(ln.get("cumulative_qty_completed") or 0)
        actual_pct = round((cum / planned_qty * 100), 2) if planned_qty else 0.0
        # planned pct preserved if existing
        existing = await db.work_progress.find_one(
            {"project_id": project_id, key_field: key_value}, {"_id": 0}
        )
        planned_pct = float((existing or {}).get("planned_progress_pct") or 0.0)
        status = _progress_status(planned_pct, actual_pct) if planned_pct else "on_track"
        if (existing or {}).get("status") == "on_hold":
            status = "on_hold"

        body = {
            "project_id": project_id,
            "project_code": dpr.get("project_code"),
            key_field: key_value,
            "description": ln.get("description") or (boq_line or {}).get("description") or "",
            "uom": ln.get("uom") or (boq_line or {}).get("uom") or "",
            "planned_qty": planned_qty or (existing or {}).get("planned_qty") or 0,
            "completed_qty_today": float(ln.get("qty_completed_today") or 0),
            "cumulative_completed_qty": cum,
            "balance_qty": max((planned_qty or 0) - cum, 0) if planned_qty else (existing or {}).get("balance_qty", 0),
            "planned_progress_pct": planned_pct,
            "actual_progress_pct": actual_pct,
            "variance_pct": round(actual_pct - planned_pct, 2),
            "status": status,
            "last_dpr_id": dpr_id,
            "last_dpr_date": dpr.get("dpr_date"),
            "updated_at": now_iso(),
        }
        if not existing:
            body.update({
                "id": new_id(),
                "delay_reason": "",
                "corrective_action": "",
                "responsible_person": dpr.get("project_manager") or "",
                "target_recovery_date": "",
                "created_at": now_iso(),
            })
            await db.work_progress.insert_one(body)
        else:
            body["id"] = existing["id"]
            await db.work_progress.update_one(
                {"id": existing["id"]}, {"$set": body}
            )


@router.get("/work-progress/{project_id}")
async def list_progress(project_id: str,
                        user: dict = Depends(require_permission("projects", "read"))):
    await _resolve_project(project_id)
    rows = await db.work_progress.find({"project_id": project_id}, {"_id": 0}).sort("updated_at", -1).to_list(5000)
    return rows


@router.put("/work-progress/{row_id}")
async def patch_progress(row_id: str, payload: WorkProgressPatch,
                         user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.work_progress.find_one({"id": row_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Progress row not found")
    if payload.status and payload.status not in PROGRESS_STATUS:
        raise HTTPException(400, f"Invalid status. Allowed: {PROGRESS_STATUS}")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "planned_qty" in patch and existing.get("cumulative_completed_qty"):
        new_planned = float(patch["planned_qty"] or 0)
        cum = float(existing["cumulative_completed_qty"])
        actual_pct = round((cum / new_planned * 100), 2) if new_planned else 0.0
        patch["actual_progress_pct"] = actual_pct
        patch["balance_qty"] = max(new_planned - cum, 0)
        planned_pct = float(patch.get("planned_progress_pct") or existing.get("planned_progress_pct") or 0)
        patch["variance_pct"] = round(actual_pct - planned_pct, 2)
        if existing.get("status") != "on_hold":
            patch["status"] = patch.get("status") or _progress_status(planned_pct, actual_pct)
    patch["updated_at"] = now_iso()
    await db.work_progress.update_one({"id": row_id}, {"$set": patch})
    return await db.work_progress.find_one({"id": row_id}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Section 4 · Integration READ endpoints (HR / Store / Safety / Logistics)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/integrations/{project_id}/manpower")
async def integration_manpower(project_id: str, on_date: Optional[str] = None,
                                user: dict = Depends(require_permission("projects", "read"))):
    """Pull deployed manpower from existing manpower_allocations + attendance."""
    today = on_date or now_iso()[:10]
    allocs = await db.manpower_allocations.find(
        {"project_id": project_id}, {"_id": 0, "employee_id": 1, "designation": 1, "designation_id": 1, "from_date": 1, "to_date": 1}
    ).to_list(500)
    present_count = 0
    if allocs:
        emp_ids = [a["employee_id"] for a in allocs if a.get("employee_id")]
        if emp_ids:
            present_count = await db.attendance.count_documents(
                {"employee_id": {"$in": emp_ids}, "date": today, "status": {"$in": ["P", "Present", "present"]}}
            )
    return {
        "date": today, "deployed_count": len(allocs), "present_count": present_count,
        "allocations": allocs,
    }


@router.get("/integrations/{project_id}/material")
async def integration_material(project_id: str,
                                user: dict = Depends(require_permission("projects", "read"))):
    """Material issued + consumed snapshot from store."""
    issued = await db.material_issues.find({"project_id": project_id}, {"_id": 0}).sort("date", -1).to_list(500) \
        if "material_issues" in await db.list_collection_names() else []
    return {"issued_count": len(issued), "recent": issued[:20]}


@router.get("/integrations/{project_id}/safety")
async def integration_safety(project_id: str,
                              user: dict = Depends(require_permission("projects", "read"))):
    """Safety observations + permit status. Pulls from safety collections if present."""
    collections = await db.list_collection_names()
    obs = await db.safety_observations.find({"project_id": project_id}, {"_id": 0}).sort("date", -1).to_list(50) \
        if "safety_observations" in collections else []
    permits = await db.work_permits.find({"project_id": project_id}, {"_id": 0}).to_list(50) \
        if "work_permits" in collections else []
    return {"observations": obs, "permits": permits}


@router.get("/integrations/{project_id}/logistics")
async def integration_logistics(project_id: str,
                                 user: dict = Depends(require_permission("projects", "read"))):
    """Dispatch / delivery snapshot."""
    collections = await db.list_collection_names()
    if "logistics_movements" not in collections:
        return {"movements": []}
    moves = await db.logistics_movements.find({"project_id": project_id}, {"_id": 0}).sort("date", -1).to_list(50)
    return {"movements": moves}
