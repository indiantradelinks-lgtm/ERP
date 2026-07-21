"""Projects & Operations · Phase 3 — Round 3B.

Measurement Sheet + Site Issues + Delay Records + Client Instructions +
Extra Work. Each is its own collection but they share a similar approval
pattern.

  • **MeasurementSheet** + **MeasurementLine** (`db.measurement_sheets`,
        `db.measurement_lines`) — BOQ/DPR-linked measurement with prepared/
        checked/approved roles. Certified qty visible to Accounts for RA
        billing; uncertified flagged as pending certification.

  • **SiteIssue**       (`db.site_issues`)
        Categorised issue tracking (manpower/material/safety/client/permit/
        logistics/equipment/weather/technical/billing/other) with impact
        (low/medium/high/critical) → critical triggers PM/owner notification
        via `db.notifications` (simple write-through).

  • **DelayRecord**     (`db.delay_records`)
        Delay impact tracking with days_delayed, root_cause, action,
        target_recovery. Linked to issues if applicable.

  • **ClientInstruction** (`db.client_instructions`)
        Verbal/written instructions from client with action_required +
        responsible + status.

  • **ExtraWork**       (`db.extra_works`)
        Extra/variation work record linked to a ClientInstruction reference
        and the project. PM-approval gate; billable extras feed Accounts
        when status=approved AND billing_status=pending.

Endpoints (all under `/api/proj-phase3`):

  Measurement
    GET/POST   /measurements                  — list / create header
    GET/PUT/DELETE  /measurements/{id}        — drill-down + edit + delete
    POST   /measurements/{id}/lines           — add line
    PUT/DELETE  /measurements/{id}/lines/{lid} — edit/delete line
    POST   /measurements/{id}/submit          — draft → submitted
    POST   /measurements/{id}/check           — submitted → checked
    POST   /measurements/{id}/approve         — checked → approved
    POST   /measurements/{id}/certify         — set client-certification per line
    GET    /measurements/{project_id}/pending-certification

  Issues / Delays / Client Instructions / Extra Work
    GET/POST   /issues                        — list / create
    PUT/DELETE /issues/{id}
    POST   /issues/{id}/close
    POST   /issues/{id}/escalate

    GET/POST/PUT/DELETE   /delays /delays/{id}
    GET/POST/PUT/DELETE   /client-instructions /client-instructions/{id}
    GET/POST/PUT/DELETE   /extra-works /extra-works/{id}
    POST   /extra-works/{id}/approve  POST   /extra-works/{id}/reject
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from scope import apply_project_scope
from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/proj-phase3", tags=["projects-ops-phase3-r2"])


# helpers
async def _resolve_project(pid: str) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, f"Project '{pid}' not found")
    return p


async def _notify(*, project_id: str, type: str, severity: str, title: str, detail: str,
                  recipients: List[str], record_ref: dict, user: dict):
    """Lightweight notification — writes to db.notifications for now (read by inbox UI later)."""
    await db.notifications.insert_one({
        "id": new_id(),
        "project_id": project_id,
        "type": type, "severity": severity,
        "title": title, "detail": detail,
        "recipients": recipients,
        "record_ref": record_ref,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "is_read": False,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 · Measurement Sheet
# ═══════════════════════════════════════════════════════════════════════════

MS_STATUS = ("draft", "submitted", "checked", "approved", "rejected")
CERT_STATUS = ("pending", "certified", "partial", "rejected", "held")


class MeasurementLineIn(BaseModel):
    sl_no: Optional[int] = None
    boq_line_id: Optional[str] = None
    activity_id: Optional[str] = None
    dpr_id: Optional[str] = None
    description: str = Field(..., min_length=1, max_length=500)
    location: Optional[str] = ""
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    quantity: float = 0.0
    uom: Optional[str] = ""
    rate: float = 0.0
    cumulative_qty: Optional[float] = None
    client_certification_status: str = "pending"
    certified_quantity: float = 0.0
    rejected_held_quantity: float = 0.0
    remarks: Optional[str] = ""


class MeasurementIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    site_id: Optional[str] = None
    measurement_no: Optional[str] = ""
    measurement_date: str = Field(..., min_length=1)
    period_from: Optional[str] = ""
    period_to: Optional[str] = ""
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = ""
    prepared_by: Optional[str] = ""
    checked_by: Optional[str] = ""
    approved_by: Optional[str] = ""
    attachment_ids: List[str] = []
    remarks: Optional[str] = ""


async def _next_ms_no(project_code: str) -> str:
    n = await db.measurement_sheets.count_documents({})
    return f"MS-{project_code or 'GEN'}-{n + 1:05d}"


def _line_amount(q: float, r: float) -> float:
    return round(float(q or 0) * float(r or 0), 2)


async def _ms_hydrate(ms_id: str) -> dict:
    ms = await db.measurement_sheets.find_one({"id": ms_id}, {"_id": 0})
    if not ms:
        raise HTTPException(404, "Measurement sheet not found")
    lines = await db.measurement_lines.find({"ms_id": ms_id}, {"_id": 0}).sort("sl_no", 1).to_list(2000)
    for ln in lines:
        ln["amount"] = _line_amount(ln.get("quantity"), ln.get("rate"))
    ms["lines"] = lines
    ms["total_quantity"] = round(sum(float(ln.get("quantity") or 0) for ln in lines), 4)
    ms["total_amount"] = round(sum(_line_amount(ln.get("quantity"), ln.get("rate")) for ln in lines), 2)
    ms["certified_amount"] = round(
        sum(_line_amount(ln.get("certified_quantity"), ln.get("rate")) for ln in lines), 2
    )
    return ms


@router.get("/measurements")
async def list_measurements(project_id: Optional[str] = None,
                            status: Optional[str] = None,
                            user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    q = await apply_project_scope(user, q)
    rows = await db.measurement_sheets.find(q, {"_id": 0}).sort("measurement_date", -1).to_list(2000)
    return rows


@router.post("/measurements")
async def create_measurement(payload: MeasurementIn,
                             user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "measurement_no": (payload.measurement_no or "").strip() or await _next_ms_no(p.get("code") or ""),
        "project_code": p.get("code"),
        "project_name": p.get("name"),
        "client_id": p.get("client_id"),
        "client_name": p.get("client_name") or p.get("client"),
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.measurement_sheets.insert_one(doc)
    return await _ms_hydrate(doc["id"])


@router.get("/measurements/{ms_id}")
async def get_measurement(ms_id: str,
                          user: dict = Depends(require_permission("projects", "read"))):
    return await _ms_hydrate(ms_id)


@router.put("/measurements/{ms_id}")
async def update_measurement(ms_id: str, payload: MeasurementIn,
                             user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.measurement_sheets.find_one({"id": ms_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Measurement sheet not found")
    if existing.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved measurement is locked.")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    await db.measurement_sheets.update_one({"id": ms_id}, {"$set": patch})
    return await _ms_hydrate(ms_id)


@router.delete("/measurements/{ms_id}")
async def delete_measurement(ms_id: str,
                             user: dict = Depends(require_permission("projects", "delete"))):
    existing = await db.measurement_sheets.find_one({"id": ms_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Measurement sheet not found")
    if existing.get("status") == "approved" and user.get("role") != "super_admin":
        raise HTTPException(403, "Approved measurement can only be deleted by Super Admin.")
    await db.measurement_lines.delete_many({"ms_id": ms_id})
    await db.measurement_sheets.delete_one({"id": ms_id})
    return {"ok": True}


# Measurement workflow
async def _ms_status_transition(ms_id: str, new_status: str, user: dict, extras: dict = None):
    ms = await db.measurement_sheets.find_one({"id": ms_id}, {"_id": 0})
    if not ms:
        raise HTTPException(404, "Measurement sheet not found")
    patch = {"status": new_status, "updated_at": now_iso(), **(extras or {})}
    await db.measurement_sheets.update_one({"id": ms_id}, {"$set": patch})
    await audit(user=user, action=new_status, resource="measurement_sheets",
                record_id=ms_id, before=ms, after=patch, ip="ms")
    return await _ms_hydrate(ms_id)


@router.post("/measurements/{ms_id}/submit")
async def ms_submit(ms_id: str, user: dict = Depends(require_permission("projects", "write"))):
    return await _ms_status_transition(ms_id, "submitted", user, {
        "submitted_by": user.get("name") or user.get("email"),
        "submitted_at": now_iso(),
    })


@router.post("/measurements/{ms_id}/check")
async def ms_check(ms_id: str, user: dict = Depends(require_permission("projects", "write"))):
    return await _ms_status_transition(ms_id, "checked", user, {
        "checked_by": user.get("name") or user.get("email"),
        "checked_at": now_iso(),
    })


@router.post("/measurements/{ms_id}/approve")
async def ms_approve(ms_id: str, user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head", "project_manager"):
        raise HTTPException(403, "Only PM / Dept Head / GM / Director can approve a measurement sheet")
    return await _ms_status_transition(ms_id, "approved", user, {
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
    })


@router.post("/measurements/{ms_id}/reject")
async def ms_reject(ms_id: str, reason: str = Query(...),
                    user: dict = Depends(require_permission("projects", "write"))):
    return await _ms_status_transition(ms_id, "rejected", user, {
        "rejected_by": user.get("name") or user.get("email"),
        "rejected_at": now_iso(),
        "rejection_reason": reason,
    })


# Lines
@router.post("/measurements/{ms_id}/lines")
async def ms_add_line(ms_id: str, payload: MeasurementLineIn,
                      user: dict = Depends(require_permission("projects", "write"))):
    ms = await db.measurement_sheets.find_one({"id": ms_id}, {"_id": 0})
    if not ms:
        raise HTTPException(404, "Measurement sheet not found")
    if ms.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved measurement sheet is locked.")

    sl = payload.sl_no
    if not sl:
        last = await db.measurement_lines.find({"ms_id": ms_id}).sort("sl_no", -1).limit(1).to_list(1)
        sl = ((last[0].get("sl_no") or 0) + 1) if last else 1

    ln = payload.model_dump()
    ln["sl_no"] = sl
    # auto-compute quantity from L×W×H if user left it at 0
    lwh = float(payload.length or 0) * float(payload.width or 0) * float(payload.height or 0)
    if (not payload.quantity) and lwh > 0:
        ln["quantity"] = round(lwh, 4)
    # cumulative_qty: prior sum on same boq_line_id within this project
    if payload.boq_line_id:
        pipeline = [
            {"$match": {"project_id": ms["project_id"]}},
            {"$lookup": {"from": "measurement_lines", "localField": "id", "foreignField": "ms_id", "as": "lines"}},
            {"$unwind": "$lines"},
            {"$match": {"lines.boq_line_id": payload.boq_line_id}},
            {"$group": {"_id": None, "total": {"$sum": "$lines.quantity"}}},
        ]
        prior = 0.0
        async for d in db.measurement_sheets.aggregate(pipeline):
            prior = float(d.get("total") or 0)
        ln["cumulative_qty"] = round(prior + float(ln["quantity"] or 0), 4)
    ln.update({
        "id": new_id(), "ms_id": ms_id, "project_id": ms["project_id"],
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
    })
    await db.measurement_lines.insert_one(ln)
    return await _ms_hydrate(ms_id)


@router.put("/measurements/{ms_id}/lines/{line_id}")
async def ms_update_line(ms_id: str, line_id: str, payload: MeasurementLineIn,
                         user: dict = Depends(require_permission("projects", "write"))):
    ms = await db.measurement_sheets.find_one({"id": ms_id}, {"_id": 0})
    if not ms:
        raise HTTPException(404, "Measurement sheet not found")
    if ms.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved measurement sheet is locked.")
    existing = await db.measurement_lines.find_one({"id": line_id, "ms_id": ms_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Line not found")
    patch = payload.model_dump()
    lwh = float(payload.length or 0) * float(payload.width or 0) * float(payload.height or 0)
    if (not payload.quantity) and lwh > 0:
        patch["quantity"] = round(lwh, 4)
    patch["updated_at"] = now_iso()
    await db.measurement_lines.update_one({"id": line_id, "ms_id": ms_id}, {"$set": patch})
    return await _ms_hydrate(ms_id)


@router.delete("/measurements/{ms_id}/lines/{line_id}")
async def ms_delete_line(ms_id: str, line_id: str,
                         user: dict = Depends(require_permission("projects", "write"))):
    r = await db.measurement_lines.delete_one({"id": line_id, "ms_id": ms_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Line not found")
    return await _ms_hydrate(ms_id)


class CertifyPayload(BaseModel):
    line_id: str
    certified_quantity: float
    client_certification_status: str = "certified"
    rejected_held_quantity: float = 0
    remarks: Optional[str] = ""


@router.post("/measurements/{ms_id}/certify")
async def ms_certify(ms_id: str, payload: CertifyPayload,
                     user: dict = Depends(require_permission("projects", "write"))):
    if payload.client_certification_status not in CERT_STATUS:
        raise HTTPException(400, f"Invalid certification status. Allowed: {CERT_STATUS}")
    r = await db.measurement_lines.update_one(
        {"id": payload.line_id, "ms_id": ms_id},
        {"$set": {
            "certified_quantity": payload.certified_quantity,
            "client_certification_status": payload.client_certification_status,
            "rejected_held_quantity": payload.rejected_held_quantity,
            "certified_at": now_iso(),
            "certified_by": user.get("name") or user.get("email"),
            "remarks": payload.remarks or "",
        }},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Line not found")
    return await _ms_hydrate(ms_id)


@router.get("/measurements/{project_id}/pending-certification")
async def ms_pending(project_id: str,
                     user: dict = Depends(require_permission("projects", "read"))):
    """Lines awaiting client certification — surfaced to Accounts/Sales."""
    sheets = await db.measurement_sheets.find(
        {"project_id": project_id, "status": {"$in": ["submitted", "checked", "approved"]}},
        {"_id": 0, "id": 1, "measurement_no": 1, "measurement_date": 1},
    ).to_list(500)
    ms_ids = [s["id"] for s in sheets]
    lines = await db.measurement_lines.find(
        {"ms_id": {"$in": ms_ids}, "client_certification_status": {"$in": ["pending", "partial", "held"]}},
        {"_id": 0},
    ).to_list(2000)
    return {"sheets": sheets, "pending_lines": lines, "pending_count": len(lines)}


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 · Site Issues
# ═══════════════════════════════════════════════════════════════════════════

ISSUE_CAT = ("manpower", "material", "safety", "client", "permit", "logistics",
              "equipment", "weather", "technical", "billing", "other")
ISSUE_IMPACT = ("low", "medium", "high", "critical")
ISSUE_STATUS = ("open", "in_progress", "closed", "escalated")


class SiteIssueIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    issue_date: Optional[str] = ""
    category: str = "other"
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = ""
    impact: str = "medium"
    delay_impact: bool = False
    cost_impact: bool = False
    responsible_department: Optional[str] = ""
    assigned_to: Optional[str] = ""
    target_closure_date: Optional[str] = ""
    corrective_action: Optional[str] = ""
    attachment_ids: List[str] = []
    site_id: Optional[str] = None


async def _next_issue_no(project_code: str) -> str:
    n = await db.site_issues.count_documents({})
    return f"ISS-{project_code or 'GEN'}-{n + 1:05d}"


@router.get("/issues")
async def list_issues(project_id: Optional[str] = None,
                      status: Optional[str] = None,
                      impact: Optional[str] = None,
                      user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    if impact:
        q["impact"] = impact
    return await db.site_issues.find(await apply_project_scope(user, q), {"_id": 0}).sort("issue_date", -1).to_list(2000)


@router.post("/issues")
async def create_issue(payload: SiteIssueIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    if payload.category not in ISSUE_CAT:
        raise HTTPException(400, f"Invalid category. Allowed: {ISSUE_CAT}")
    if payload.impact not in ISSUE_IMPACT:
        raise HTTPException(400, f"Invalid impact. Allowed: {ISSUE_IMPACT}")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "issue_no": await _next_issue_no(p.get("code") or ""),
        "issue_date": payload.issue_date or now_iso()[:10],
        "project_code": p.get("code"),
        "project_name": p.get("name"),
        "status": "open",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.site_issues.insert_one(doc)
    # critical → notify PM / Owner / Ops Head
    if payload.impact == "critical":
        await _notify(
            project_id=payload.project_id, type="site_issue", severity="critical",
            title=f"Critical site issue: {payload.title}",
            detail=payload.description or "",
            recipients=["project_manager", "general_manager", "director"],
            record_ref={"resource": "site_issues", "id": doc["id"]},
            user=user,
        )
    # cost impact → notify finance
    if payload.cost_impact:
        await _notify(
            project_id=payload.project_id, type="site_issue", severity="high",
            title=f"Cost-impact issue: {payload.title}", detail=payload.description or "",
            recipients=["accounts_officer", "general_manager"],
            record_ref={"resource": "site_issues", "id": doc["id"]},
            user=user,
        )
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/issues/{issue_id}")
async def update_issue(issue_id: str, payload: SiteIssueIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.site_issues.find_one({"id": issue_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Issue not found")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    await db.site_issues.update_one({"id": issue_id}, {"$set": patch})
    return await db.site_issues.find_one({"id": issue_id}, {"_id": 0})


@router.delete("/issues/{issue_id}")
async def delete_issue(issue_id: str,
                       user: dict = Depends(require_permission("projects", "delete"))):
    r = await db.site_issues.delete_one({"id": issue_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Issue not found")
    return {"ok": True}


@router.post("/issues/{issue_id}/close")
async def close_issue(issue_id: str, closure_note: str = Query(""),
                      user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.site_issues.find_one({"id": issue_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Issue not found")
    patch = {
        "status": "closed", "actual_closure_date": now_iso()[:10],
        "closed_by": user.get("name") or user.get("email"),
        "closure_note": closure_note, "updated_at": now_iso(),
    }
    await db.site_issues.update_one({"id": issue_id}, {"$set": patch})
    return await db.site_issues.find_one({"id": issue_id}, {"_id": 0})


@router.post("/issues/{issue_id}/escalate")
async def escalate_issue(issue_id: str,
                         user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.site_issues.find_one({"id": issue_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Issue not found")
    patch = {
        "status": "escalated", "escalation_status": "escalated",
        "escalated_at": now_iso(), "escalated_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    await db.site_issues.update_one({"id": issue_id}, {"$set": patch})
    await _notify(
        project_id=existing.get("project_id"), type="site_issue", severity="critical",
        title=f"Issue escalated: {existing.get('title')}", detail="Manual escalation",
        recipients=["general_manager", "director"],
        record_ref={"resource": "site_issues", "id": issue_id}, user=user,
    )
    return await db.site_issues.find_one({"id": issue_id}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Section 3 · Delay Records
# ═══════════════════════════════════════════════════════════════════════════

class DelayIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    delay_date: Optional[str] = ""
    activity_id: Optional[str] = None
    issue_id: Optional[str] = None
    days_delayed: int = 0
    root_cause: Optional[str] = ""
    impact_description: Optional[str] = ""
    action_taken: Optional[str] = ""
    target_recovery_date: Optional[str] = ""
    responsible: Optional[str] = ""
    status: str = "open"


@router.get("/delays")
async def list_delays(project_id: Optional[str] = None,
                      user: dict = Depends(require_permission("projects", "read"))):
    q = {"project_id": project_id} if project_id else {}
    return await db.delay_records.find(await apply_project_scope(user, q), {"_id": 0}).sort("delay_date", -1).to_list(2000)


@router.post("/delays")
async def create_delay(payload: DelayIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "project_code": p.get("code"),
        "delay_date": payload.delay_date or now_iso()[:10],
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
    })
    await db.delay_records.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/delays/{delay_id}")
async def update_delay(delay_id: str, payload: DelayIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.delay_records.find_one({"id": delay_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Delay record not found")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    await db.delay_records.update_one({"id": delay_id}, {"$set": patch})
    return await db.delay_records.find_one({"id": delay_id}, {"_id": 0})


@router.delete("/delays/{delay_id}")
async def delete_delay(delay_id: str,
                       user: dict = Depends(require_permission("projects", "delete"))):
    r = await db.delay_records.delete_one({"id": delay_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Delay record not found")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Section 4 · Client Instructions
# ═══════════════════════════════════════════════════════════════════════════

class ClientInstructionIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    instruction_date: Optional[str] = ""
    given_by: Optional[str] = ""
    mode: str = "verbal"               # verbal | written
    instruction_details: str = Field(..., min_length=2)
    action_required: Optional[str] = ""
    responsible_person: Optional[str] = ""
    target_date: Optional[str] = ""
    status: str = "open"               # open | in_progress | actioned | closed
    attachment_ids: List[str] = []


@router.get("/client-instructions")
async def list_cinst(project_id: Optional[str] = None,
                     status: Optional[str] = None,
                     user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    return await db.client_instructions.find(await apply_project_scope(user, q), {"_id": 0}).sort("instruction_date", -1).to_list(2000)


@router.post("/client-instructions")
async def create_cinst(payload: ClientInstructionIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    n = await db.client_instructions.count_documents({})
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "instruction_no": f"CI-{p.get('code') or 'GEN'}-{n + 1:05d}",
        "project_code": p.get("code"),
        "instruction_date": payload.instruction_date or now_iso()[:10],
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
    })
    await db.client_instructions.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/client-instructions/{cid}")
async def update_cinst(cid: str, payload: ClientInstructionIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.client_instructions.find_one({"id": cid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Client instruction not found")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    await db.client_instructions.update_one({"id": cid}, {"$set": patch})
    return await db.client_instructions.find_one({"id": cid}, {"_id": 0})


@router.delete("/client-instructions/{cid}")
async def delete_cinst(cid: str,
                       user: dict = Depends(require_permission("projects", "delete"))):
    r = await db.client_instructions.delete_one({"id": cid})
    if r.deleted_count == 0:
        raise HTTPException(404, "Client instruction not found")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Section 5 · Extra Work
# ═══════════════════════════════════════════════════════════════════════════

EW_APPROVAL = ("pending", "approved", "rejected")
EW_BILLING = ("pending", "billed", "received", "na")


class ExtraWorkIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    client_instruction_id: Optional[str] = None
    work_description: str = Field(..., min_length=2)
    quantity: float = 0.0
    uom: Optional[str] = ""
    rate: float = 0.0
    estimated_value: Optional[float] = None       # auto = qty*rate if omitted
    client_approval_status: str = "pending"        # pending | written | verbal | rejected
    attachment_ids: List[str] = []
    remarks: Optional[str] = ""


@router.get("/extra-works")
async def list_extra(project_id: Optional[str] = None,
                     approval_status: Optional[str] = None,
                     user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if approval_status:
        q["approval_status"] = approval_status
    return await db.extra_works.find(await apply_project_scope(user, q), {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/extra-works")
async def create_extra(payload: ExtraWorkIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    n = await db.extra_works.count_documents({})
    doc = payload.model_dump()
    est = payload.estimated_value if payload.estimated_value is not None else round(
        float(payload.quantity or 0) * float(payload.rate or 0), 2,
    )
    doc.update({
        "id": new_id(),
        "extra_work_no": f"EXW-{p.get('code') or 'GEN'}-{n + 1:05d}",
        "project_code": p.get("code"),
        "estimated_value": est,
        "approval_status": "pending",
        "billing_status": "pending",
        "is_risk": payload.client_approval_status not in ("written", "approved"),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.extra_works.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/extra-works/{ew_id}")
async def update_extra(ew_id: str, payload: ExtraWorkIn,
                       user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.extra_works.find_one({"id": ew_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Extra work not found")
    if existing.get("approval_status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved extra work cannot be edited.")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    est = payload.estimated_value if payload.estimated_value is not None else round(
        float(payload.quantity or 0) * float(payload.rate or 0), 2,
    )
    patch["estimated_value"] = est
    patch["is_risk"] = patch.get("client_approval_status") not in ("written", "approved")
    patch["updated_at"] = now_iso()
    await db.extra_works.update_one({"id": ew_id}, {"$set": patch})
    return await db.extra_works.find_one({"id": ew_id}, {"_id": 0})


@router.delete("/extra-works/{ew_id}")
async def delete_extra(ew_id: str,
                       user: dict = Depends(require_permission("projects", "delete"))):
    r = await db.extra_works.delete_one({"id": ew_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Extra work not found")
    return {"ok": True}


@router.post("/extra-works/{ew_id}/approve")
async def approve_extra(ew_id: str,
                        user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head", "project_manager"):
        raise HTTPException(403, "Only PM / Dept Head / GM / Director can approve extra work")
    existing = await db.extra_works.find_one({"id": ew_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Extra work not found")
    patch = {
        "approval_status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(), "updated_at": now_iso(),
    }
    await db.extra_works.update_one({"id": ew_id}, {"$set": patch})
    await audit(user=user, action="approve", resource="extra_works",
                record_id=ew_id, before=existing, after=patch, ip="extra")
    return await db.extra_works.find_one({"id": ew_id}, {"_id": 0})


@router.post("/extra-works/{ew_id}/reject")
async def reject_extra(ew_id: str, reason: str = Query(...),
                       user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.extra_works.find_one({"id": ew_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Extra work not found")
    patch = {
        "approval_status": "rejected",
        "rejection_reason": reason,
        "rejected_by": user.get("name") or user.get("email"),
        "rejected_at": now_iso(), "updated_at": now_iso(),
    }
    await db.extra_works.update_one({"id": ew_id}, {"$set": patch})
    return await db.extra_works.find_one({"id": ew_id}, {"_id": 0})


@router.get("/extra-works/{project_id}/billable")
async def billable_extra(project_id: str,
                         user: dict = Depends(require_permission("projects", "read"))):
    """Visible to Sales/Accounts: extras approved by PM AND pending billing."""
    rows = await db.extra_works.find(
        {"project_id": project_id, "approval_status": "approved", "billing_status": "pending"},
        {"_id": 0},
    ).to_list(500)
    total_value = round(sum(float(r.get("estimated_value") or 0) for r in rows), 2)
    return {"rows": rows, "total_value": total_value, "count": len(rows)}
