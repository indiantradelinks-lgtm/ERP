"""Sales Enquiry Follow-Up Tracker (Module 1) + Internal Project Review (Module 2).

ITER 120 — adds the two modules requested for INDIAN TRADE LINKS without
duplicating the existing `sales_router` (enquiry CRUD), `dprs`, `site_issues`,
`project_handovers`, approval_engine or audit infrastructure.

Module 1 endpoints:
  GET    /api/enquiry-followups/inbox            (today / upcoming / overdue / new / critical)
  POST   /api/enquiries/{enq_id}/followups       (append history entry, advance next date)
  GET    /api/enquiries/{enq_id}/followups       (full history)
  POST   /api/enquiries/{enq_id}/reminders       (set reminder)
  GET    /api/enquiry-followups/dashboard        (KPIs)

Module 2 endpoints:
  GET    /api/internal-reviews                   (list with filters)
  POST   /api/internal-reviews                   (create review with all 8 factor blocks)
  GET    /api/internal-reviews/{rid}             (single review with factors)
  PATCH  /api/internal-reviews/{rid}             (update overall status / summary)
  POST   /api/internal-reviews/{rid}/action-items (add)
  POST   /api/internal-reviews/{rid}/decisions   (add)
  POST   /api/internal-reviews/{rid}/critical-issues (add)
  PATCH  /api/action-items/{aid}                 (update status)
  GET    /api/internal-reviews/dashboard         (KPIs across all projects)
  GET    /api/action-items/inbox                 (my pending / overdue action items)
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, date as _date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io, csv

from core import db, require_permission, now_iso
from audit import audit

router = APIRouter(tags=["enquiry-followup-and-internal-review"])


def _csv_response(rows: List[Dict[str, Any]], headers: List[str], filename: str):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([r.get(h, "") for h in headers])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _xlsx_response(rows: List[Dict[str, Any]], headers: List[str], filename: str,
                    sheet_name: str = "Sheet1",
                    title: Optional[str] = None,
                    status_columns: Optional[List[str]] = None):
    """Iter 122 — true .xlsx with formatted header, frozen first row,
    auto-width and conditional status colouring."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    row_offset = 1
    if title:
        ws.cell(row=1, column=1, value=title).font = Font(bold=True, size=14)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        row_offset = 3
    # header row
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(border_style="thin", color="D1D5DB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=row_offset, column=col, value=h.replace("_", " ").title())
        c.fill = header_fill; c.font = header_font
        c.alignment = Alignment(horizontal="left", vertical="center")
        c.border = border
    ws.freeze_panes = ws.cell(row=row_offset + 1, column=1)

    STATUS_COLOURS = {
        "critical": "FECACA", "delayed": "FED7AA", "attention_required": "FEF3C7",
        "overdue": "FECACA", "today": "FEF3C7",
        "on_track": "D1FAE5", "completed": "D1FAE5", "won": "D1FAE5",
        "hold": "E9D5FF", "pending": "F3F4F6",
        "lost": "E5E7EB", "dropped": "E5E7EB",
    }
    status_cols = set(status_columns or [])
    for ri, r in enumerate(rows, row_offset + 1):
        for ci, h in enumerate(headers, 1):
            v = r.get(h, "")
            c = ws.cell(row=ri, column=ci, value=v if v is not None else "")
            c.border = border
            c.alignment = Alignment(vertical="center", wrap_text=True)
            if h in status_cols and isinstance(v, str):
                col = STATUS_COLOURS.get(v.lower())
                if col:
                    c.fill = PatternFill("solid", fgColor=col)
                    c.font = Font(bold=True)
            if isinstance(v, (int, float)):
                c.alignment = Alignment(horizontal="right")
    # auto-width (capped)
    for col_idx, h in enumerate(headers, 1):
        max_len = max([len(str(h))] + [len(str(r.get(h, ""))) for r in rows[:200]])
        ws.column_dimensions[ws.cell(row=row_offset, column=col_idx).column_letter].width = min(max(max_len + 2, 10), 40)

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 1 — SALES ENQUIRY FOLLOW-UP TRACKER
# ═══════════════════════════════════════════════════════════════════════════
class FollowUpIn(BaseModel):
    mode: str  # Call / Email / Meeting / WhatsApp / Client Visit / Tender Portal
    remarks: str = Field(..., min_length=3, max_length=2000)
    person_contacted: Optional[str] = None
    next_action: Optional[str] = None
    next_followup_date: Optional[str] = None  # ISO date
    next_followup_time: Optional[str] = None  # HH:MM
    action_owner: Optional[str] = None
    reminder_date: Optional[str] = None
    reminder_time: Optional[str] = None
    priority: Optional[str] = None
    documents: Optional[List[str]] = None


class ReminderIn(BaseModel):
    reminder_date: str
    reminder_time: Optional[str] = None
    owner: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/enquiries/{enq_id}/followups")
async def add_followup(enq_id: str, payload: FollowUpIn, request: Request,
                        user: dict = Depends(require_permission("quotations", "write"))):
    enq = await db.enquiries.find_one({"id": enq_id}, {"_id": 0})
    if not enq:
        raise HTTPException(404, "Enquiry not found")
    now = now_iso()
    fu = {
        "id": str(uuid.uuid4()),
        "enquiry_id": enq_id,
        "client_name": enq.get("client_name"),
        "mode": payload.mode,
        "remarks": payload.remarks,
        "person_contacted": payload.person_contacted,
        "next_action": payload.next_action,
        "next_followup_date": payload.next_followup_date,
        "next_followup_time": payload.next_followup_time,
        "action_owner": payload.action_owner,
        "priority": payload.priority,
        "documents": payload.documents or [],
        "done_by_id": user.get("id"),
        "done_by": user.get("name") or user.get("email"),
        "done_at": now,
    }
    await db.enquiry_followups.insert_one(dict(fu))
    fu.pop("_id", None)

    # Bump rollup fields on the enquiry itself
    upd: Dict[str, Any] = {
        "last_followup_date": now[:10],
        "last_followup_remarks": payload.remarks,
        "last_followup_mode": payload.mode,
        "last_followup_by": user.get("name") or user.get("email"),
        "updated_at": now,
    }
    if payload.next_followup_date:
        upd["next_followup_date"] = payload.next_followup_date
        upd["next_followup_time"] = payload.next_followup_time
    if payload.priority:
        upd["priority"] = payload.priority
    if payload.action_owner:
        upd["action_owner"] = payload.action_owner

    # Optional reminder
    if payload.reminder_date:
        rem = {
            "id": str(uuid.uuid4()), "enquiry_id": enq_id,
            "reminder_date": payload.reminder_date,
            "reminder_time": payload.reminder_time,
            "owner": payload.action_owner or (user.get("name") or user.get("email")),
            "remarks": payload.next_action or payload.remarks,
            "status": "pending",
            "created_at": now,
        }
        await db.enquiry_reminders.insert_one(dict(rem))

    await db.enquiries.update_one({"id": enq_id}, {"$set": upd})
    await audit(user=user, action="add_followup", resource="enquiries",
                record_id=enq_id, after={"mode": payload.mode, "next": payload.next_followup_date},
                ip=request.client.host if request.client else "")
    return fu


@router.get("/enquiries/{enq_id}/followups")
async def list_followups(enq_id: str,
                          user: dict = Depends(require_permission("quotations", "read"))):
    rows = await db.enquiry_followups.find({"enquiry_id": enq_id}, {"_id": 0})\
        .sort("done_at", -1).to_list(500)
    return rows


@router.post("/enquiries/{enq_id}/reminders")
async def add_reminder(enq_id: str, payload: ReminderIn,
                        user: dict = Depends(require_permission("quotations", "write"))):
    enq = await db.enquiries.find_one({"id": enq_id}, {"_id": 0, "id": 1})
    if not enq:
        raise HTTPException(404, "Enquiry not found")
    rec = {
        "id": str(uuid.uuid4()), "enquiry_id": enq_id,
        "reminder_date": payload.reminder_date,
        "reminder_time": payload.reminder_time,
        "owner": payload.owner or user.get("name") or user.get("email"),
        "remarks": payload.remarks,
        "status": "pending",
        "created_at": now_iso(),
    }
    await db.enquiry_reminders.insert_one(dict(rec))
    rec.pop("_id", None)
    return rec


@router.get("/enquiry-followups/inbox")
async def enquiry_followup_inbox(
        view: str = Query("all", regex="^(today|upcoming|overdue|new|critical|all)$"),
        user: dict = Depends(require_permission("quotations", "read"))):
    """Returns enquiries grouped by their next-followup status."""
    today = _date.today().isoformat()
    open_statuses = {"new", "under_review", "quotation_pending", "quotation_submitted",
                      "technical_clarification_pending", "commercial_negotiation",
                      "client_approval_pending", "po_awaited", "on_hold"}

    q: Dict[str, Any] = {"status": {"$nin": ["won", "lost", "dropped"]}}
    if view == "today":
        q["next_followup_date"] = today
    elif view == "upcoming":
        q["next_followup_date"] = {"$gt": today}
    elif view == "overdue":
        q["next_followup_date"] = {"$lt": today, "$ne": None}
    elif view == "new":
        cutoff = (_date.today() - timedelta(days=7)).isoformat()
        q["created_at"] = {"$gte": cutoff}
        q["$or"] = [{"last_followup_date": {"$in": [None, ""]}}, {"last_followup_date": {"$exists": False}}]
    elif view == "critical":
        q["priority"] = {"$in": ["high", "critical", "High", "Critical"]}

    rows = await db.enquiries.find(q, {"_id": 0}).sort("next_followup_date", 1).to_list(1000)

    # Classification helper for the "all" view
    def classify(r):
        nd = r.get("next_followup_date")
        if not nd:
            return "no_date"
        if nd < today:
            return "overdue"
        if nd == today:
            return "today"
        return "upcoming"

    return {
        "view": view,
        "count": len(rows),
        "rows": [{**r, "_bucket": classify(r)} for r in rows],
    }


@router.get("/enquiry-followups/dashboard")
async def enquiry_followup_dashboard(
        user: dict = Depends(require_permission("quotations", "read"))):
    today = _date.today().isoformat()
    cutoff_7d = (_date.today() - timedelta(days=7)).isoformat()
    open_q = {"status": {"$nin": ["won", "lost", "dropped"]}}

    async def n(q):
        return await db.enquiries.count_documents(q)

    total_open = await n(open_q)
    new_recent = await n({"created_at": {"$gte": cutoff_7d}})
    quot_pending = await n({"status": "quotation_pending"})
    quot_submitted = await n({"status": "quotation_submitted"})
    due_today = await n({**open_q, "next_followup_date": today})
    overdue = await n({**open_q, "next_followup_date": {"$lt": today, "$ne": None}})
    high_priority = await n({**open_q, "priority": {"$in": ["high", "critical", "High", "Critical"]}})
    won = await n({"status": "won"})
    lost = await n({"status": "lost"})

    # Pipeline value
    pipeline_val = 0.0
    async for r in db.enquiries.aggregate([
        {"$match": open_q},
        {"$group": {"_id": None, "v": {"$sum": "$estimated_value"}}},
    ]):
        pipeline_val = float(r.get("v") or 0)

    # Salesperson breakdown
    sales_breakdown = []
    async for r in db.enquiries.aggregate([
        {"$match": open_q},
        {"$group": {"_id": "$assigned_to", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]):
        sales_breakdown.append({"salesperson": r.get("_id") or "(unassigned)", "count": r.get("count", 0)})

    # Client breakdown
    client_breakdown = []
    async for r in db.enquiries.aggregate([
        {"$match": open_q},
        {"$group": {"_id": "$client_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]):
        client_breakdown.append({"client": r.get("_id") or "(unknown)", "count": r.get("count", 0)})

    return {
        "open": total_open,
        "new_7d": new_recent,
        "quotations_pending": quot_pending,
        "quotations_submitted": quot_submitted,
        "due_today": due_today,
        "overdue": overdue,
        "high_priority": high_priority,
        "won": won,
        "lost": lost,
        "pipeline_value": round(pipeline_val, 2),
        "by_salesperson": sales_breakdown,
        "by_client": client_breakdown,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 2 — INTERNAL PROJECT REVIEW
# ═══════════════════════════════════════════════════════════════════════════
FACTOR_KEYS = ["manpower", "material", "planning", "hr_compliance",
               "safety_compliance", "billing", "payment"]
OVERALL_STATUSES = {"on_track", "attention_required", "delayed", "critical", "hold", "completed"}


class FactorBlockIn(BaseModel):
    """A single factor card (one of 7)."""
    status: str  # on_track / attention_required / delayed / critical / hold / completed / pending
    summary: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None   # arbitrary k/v (required vs available, dates, qty, etc)
    responsible: Optional[str] = None
    remarks: Optional[str] = None


class ReviewIn(BaseModel):
    project_id: str
    review_type: str = "daily"  # daily / weekly / management / site / billing / payment / safety / emergency
    review_date: Optional[str] = None
    conducted_by: Optional[str] = None
    participants: Optional[List[str]] = None
    overall_status: str = "on_track"
    summary: Optional[str] = None
    key_decisions: Optional[str] = None
    next_review_date: Optional[str] = None
    factors: Dict[str, FactorBlockIn] = Field(default_factory=dict)


class ActionItemIn(BaseModel):
    title: str = Field(..., min_length=3)
    related_factor: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"
    remarks: Optional[str] = None


class DecisionIn(BaseModel):
    decision: str = Field(..., min_length=3)
    taken_by: Optional[str] = None
    approved_by: Optional[str] = None
    related_factor: Optional[str] = None
    impact: str = "medium"
    followup_required: bool = False
    followup_date: Optional[str] = None
    remarks: Optional[str] = None


class CriticalIssueIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: str  # manpower / material / planning / hr / safety / billing / payment / client / site / commercial / other
    impact: str = "medium"
    responsible: Optional[str] = None
    target_resolution_date: Optional[str] = None
    escalation_required: bool = False
    escalated_to: Optional[str] = None


def _auto_overall(overall: str, factors: Dict[str, Any]) -> str:
    """If any factor is critical, escalate overall_status to 'critical'."""
    if not factors:
        return overall
    for f in factors.values():
        if isinstance(f, dict) and (f.get("status") or "").lower() == "critical":
            return "critical"
    return overall


@router.post("/internal-reviews")
async def create_review(payload: ReviewIn, request: Request,
                         user: dict = Depends(require_permission("projects", "write"))):
    if payload.overall_status not in OVERALL_STATUSES | {"pending"}:
        raise HTTPException(400, f"Invalid overall_status: {payload.overall_status}")
    factors = {k: v.dict() for k, v in (payload.factors or {}).items() if k in FACTOR_KEYS}
    now = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "project_id": payload.project_id,
        "review_type": payload.review_type,
        "review_date": payload.review_date or now[:10],
        "conducted_by": payload.conducted_by or user.get("name"),
        "conducted_by_id": user.get("id"),
        "participants": payload.participants or [],
        "overall_status": _auto_overall(payload.overall_status, factors),
        "summary": payload.summary,
        "key_decisions": payload.key_decisions,
        "next_review_date": payload.next_review_date,
        "factors": factors,
        "action_items": [],
        "decisions": [],
        "critical_issues": [],
        "created_at": now,
        "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
        "updated_at": now,
    }
    await db.project_reviews.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit(user=user, action="create_review", resource="project_reviews",
                record_id=doc["id"], after={"project_id": payload.project_id, "type": payload.review_type},
                ip=request.client.host if request.client else "")
    return doc


@router.get("/internal-reviews")
async def list_reviews(project_id: Optional[str] = None,
                        overall_status: Optional[str] = None,
                        review_type: Optional[str] = None,
                        limit: int = 200,
                        user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if overall_status:
        q["overall_status"] = overall_status
    if review_type:
        q["review_type"] = review_type
    rows = await db.project_reviews.find(q, {"_id": 0}).sort("review_date", -1).to_list(min(limit, 1000))
    return rows


@router.get("/internal-reviews/dashboard")
async def internal_reviews_dashboard(
        user: dict = Depends(require_permission("projects", "read"))):
    """KPIs across all active projects for the Internal Review dashboard."""
    today = _date.today().isoformat()
    # Aggregate latest review per project
    latest_status_count: Dict[str, int] = {}
    seen_projects: set[str] = set()
    async for r in db.project_reviews.find({}, {"_id": 0, "project_id": 1, "overall_status": 1, "review_date": 1}).sort("review_date", -1):
        pid = r.get("project_id")
        if pid in seen_projects:
            continue
        seen_projects.add(pid)
        st = r.get("overall_status") or "pending"
        latest_status_count[st] = latest_status_count.get(st, 0) + 1

    open_issues = await db.project_critical_issues.count_documents({"status": {"$ne": "closed"}})
    overdue_actions = await db.project_action_items.count_documents({
        "status": {"$in": ["pending", "in_progress"]},
        "due_date": {"$lt": today, "$ne": None},
    })
    pending_actions = await db.project_action_items.count_documents({
        "status": {"$in": ["pending", "in_progress"]},
    })
    reviews_due_today = await db.project_reviews.count_documents({"next_review_date": today})

    return {
        "by_overall_status": latest_status_count,
        "open_critical_issues": open_issues,
        "overdue_action_items": overdue_actions,
        "pending_action_items": pending_actions,
        "reviews_due_today": reviews_due_today,
    }


@router.get("/internal-reviews/export.csv")
async def export_reviews_csv(project_id: Optional[str] = None,
                              user: dict = Depends(require_permission("projects", "read"))):
    """Iter 121 — CSV export of internal reviews, flattens factor statuses."""
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    rows = await db.project_reviews.find(q, {"_id": 0}).sort("review_date", -1).to_list(5000)
    flat_rows = _flatten_reviews(rows)
    headers = ["review_date", "review_type", "project_id", "conducted_by",
                "overall_status", "manpower_status", "material_status",
                "planning_status", "hr_status", "safety_status", "billing_status",
                "payment_status", "summary", "next_review_date"]
    return _csv_response(flat_rows, headers, "internal-reviews.csv")


@router.get("/internal-reviews/export.xlsx")
async def export_reviews_xlsx(project_id: Optional[str] = None,
                                user: dict = Depends(require_permission("projects", "read"))):
    """Iter 122 — true Excel with status colour-coding on the 7 factor columns."""
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    rows = await db.project_reviews.find(q, {"_id": 0}).sort("review_date", -1).to_list(5000)
    flat_rows = _flatten_reviews(rows)
    headers = ["review_date", "review_type", "project_id", "conducted_by",
                "overall_status", "manpower_status", "material_status",
                "planning_status", "hr_status", "safety_status", "billing_status",
                "payment_status", "summary", "next_review_date"]
    status_cols = ["overall_status", "manpower_status", "material_status",
                    "planning_status", "hr_status", "safety_status",
                    "billing_status", "payment_status"]
    return _xlsx_response(flat_rows, headers, "internal-reviews.xlsx",
                           sheet_name="Internal Reviews",
                           title="Internal Project Reviews",
                           status_columns=status_cols)


def _flatten_reviews(rows):
    """Helper used by both CSV and XLSX exporters."""
    flat = []
    for r in rows:
        f = r.get("factors") or {}
        flat.append({
            **r,
            "manpower_status": (f.get("manpower") or {}).get("status"),
            "material_status": (f.get("material") or {}).get("status"),
            "planning_status": (f.get("planning") or {}).get("status"),
            "hr_status": (f.get("hr_compliance") or {}).get("status"),
            "safety_status": (f.get("safety_compliance") or {}).get("status"),
            "billing_status": (f.get("billing") or {}).get("status"),
            "payment_status": (f.get("payment") or {}).get("status"),
        })
    return flat


@router.get("/internal-reviews/{rid}")
async def get_review(rid: str, user: dict = Depends(require_permission("projects", "read"))):
    row = await db.project_reviews.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Review not found")
    return row


class ReviewPatch(BaseModel):
    overall_status: Optional[str] = None
    summary: Optional[str] = None
    key_decisions: Optional[str] = None
    next_review_date: Optional[str] = None
    factors: Optional[Dict[str, FactorBlockIn]] = None


@router.patch("/internal-reviews/{rid}")
async def patch_review(rid: str, payload: ReviewPatch, request: Request,
                        user: dict = Depends(require_permission("projects", "write"))):
    row = await db.project_reviews.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Review not found")
    upd = {"updated_at": now_iso(),
           "updated_by": user.get("name") or user.get("email")}
    if payload.overall_status:
        if payload.overall_status not in OVERALL_STATUSES | {"pending"}:
            raise HTTPException(400, f"Invalid overall_status: {payload.overall_status}")
        upd["overall_status"] = payload.overall_status
    if payload.summary is not None:
        upd["summary"] = payload.summary
    if payload.key_decisions is not None:
        upd["key_decisions"] = payload.key_decisions
    if payload.next_review_date:
        upd["next_review_date"] = payload.next_review_date
    if payload.factors:
        merged = dict(row.get("factors") or {})
        for k, v in payload.factors.items():
            if k in FACTOR_KEYS:
                merged[k] = v.dict()
        upd["factors"] = merged
        if payload.overall_status is None:
            upd["overall_status"] = _auto_overall(row.get("overall_status") or "on_track", merged)
    await db.project_reviews.update_one({"id": rid}, {"$set": upd})
    await audit(user=user, action="update_review", resource="project_reviews",
                record_id=rid, after=upd,
                ip=request.client.host if request.client else "")
    return {**row, **upd}


@router.post("/internal-reviews/{rid}/action-items")
async def add_action_item(rid: str, payload: ActionItemIn, request: Request,
                           user: dict = Depends(require_permission("projects", "write"))):
    row = await db.project_reviews.find_one({"id": rid}, {"_id": 0, "id": 1, "project_id": 1})
    if not row:
        raise HTTPException(404, "Review not found")
    ai = {
        "id": str(uuid.uuid4()),
        "review_id": rid,
        "project_id": row["project_id"],
        "title": payload.title,
        "related_factor": payload.related_factor,
        "assigned_to": payload.assigned_to,
        "assigned_to_id": payload.assigned_to_id,
        "due_date": payload.due_date,
        "priority": payload.priority,
        "remarks": payload.remarks,
        "status": "pending",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.project_action_items.insert_one(dict(ai))
    ai.pop("_id", None)
    await db.project_reviews.update_one({"id": rid},
                                          {"$push": {"action_items": ai["id"]},
                                           "$set": {"updated_at": now_iso()}})
    return ai


@router.post("/internal-reviews/{rid}/decisions")
async def add_decision(rid: str, payload: DecisionIn,
                        user: dict = Depends(require_permission("projects", "write"))):
    row = await db.project_reviews.find_one({"id": rid}, {"_id": 0, "id": 1, "project_id": 1})
    if not row:
        raise HTTPException(404, "Review not found")
    dec = {
        "id": str(uuid.uuid4()),
        "review_id": rid,
        "project_id": row["project_id"],
        **payload.dict(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.project_decision_log.insert_one(dict(dec))
    dec.pop("_id", None)
    await db.project_reviews.update_one({"id": rid},
                                          {"$push": {"decisions": dec["id"]},
                                           "$set": {"updated_at": now_iso()}})
    return dec


@router.post("/internal-reviews/{rid}/critical-issues")
async def add_critical_issue(rid: str, payload: CriticalIssueIn,
                              user: dict = Depends(require_permission("projects", "write"))):
    row = await db.project_reviews.find_one({"id": rid}, {"_id": 0, "id": 1, "project_id": 1})
    if not row:
        raise HTTPException(404, "Review not found")
    ci = {
        "id": str(uuid.uuid4()),
        "review_id": rid,
        "project_id": row["project_id"],
        **payload.dict(),
        "status": "open",
        "raised_by": user.get("name") or user.get("email"),
        "raised_at": now_iso(),
    }
    await db.project_critical_issues.insert_one(dict(ci))
    ci.pop("_id", None)
    # If a critical issue is added, escalate review status
    if payload.impact.lower() in ("high", "critical"):
        await db.project_reviews.update_one({"id": rid},
                                              {"$push": {"critical_issues": ci["id"]},
                                               "$set": {"overall_status": "critical",
                                                        "updated_at": now_iso()}})
    else:
        await db.project_reviews.update_one({"id": rid},
                                              {"$push": {"critical_issues": ci["id"]},
                                               "$set": {"updated_at": now_iso()}})
    return ci


class ActionItemPatch(BaseModel):
    status: Optional[str] = None  # pending / in_progress / completed / overdue / deferred
    remarks: Optional[str] = None
    completed_at: Optional[str] = None


@router.patch("/action-items/{aid}")
async def update_action_item(aid: str, payload: ActionItemPatch,
                              user: dict = Depends(require_permission("projects", "write"))):
    row = await db.project_action_items.find_one({"id": aid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Action item not found")
    upd = {"updated_at": now_iso(), "updated_by": user.get("name") or user.get("email")}
    if payload.status:
        if payload.status not in {"pending", "in_progress", "completed", "overdue", "deferred"}:
            raise HTTPException(400, "Invalid status")
        upd["status"] = payload.status
        if payload.status == "completed":
            upd["completed_at"] = payload.completed_at or now_iso()
    if payload.remarks is not None:
        upd["remarks"] = payload.remarks
    await db.project_action_items.update_one({"id": aid}, {"$set": upd})
    return {**row, **upd}


@router.get("/action-items/inbox")
async def my_action_items(view: str = Query("pending", regex="^(pending|overdue|completed|all|mine)$"),
                            user: dict = Depends(require_permission("projects", "read"))):
    today = _date.today().isoformat()
    q: Dict[str, Any] = {}
    if view == "pending":
        q["status"] = {"$in": ["pending", "in_progress"]}
    elif view == "overdue":
        q["status"] = {"$in": ["pending", "in_progress"]}
        q["due_date"] = {"$lt": today, "$ne": None}
    elif view == "completed":
        q["status"] = "completed"
    elif view == "mine":
        q["assigned_to_id"] = user.get("id")
    rows = await db.project_action_items.find(q, {"_id": 0}).sort("due_date", 1).to_list(500)
    # mark overdue
    for r in rows:
        dd = r.get("due_date")
        if dd and dd < today and r.get("status") in ("pending", "in_progress"):
            r["_overdue"] = True
    return {"view": view, "count": len(rows), "rows": rows}


# ═════════════════════════════════════════════════════════════════════════
# Iter 121 — Excel/CSV exports + manual reminder trigger + home dashboard
# ═════════════════════════════════════════════════════════════════════════
@router.get("/enquiry-followups/export.csv")
async def export_followups_csv(view: str = "all",
                                user: dict = Depends(require_permission("quotations", "read"))):
    """Excel/CSV export of the current inbox view, honouring same filter."""
    today = _date.today().isoformat()
    q: Dict[str, Any] = {"status": {"$nin": ["won", "lost", "dropped"]}}
    if view == "today":
        q["next_followup_date"] = today
    elif view == "upcoming":
        q["next_followup_date"] = {"$gt": today}
    elif view == "overdue":
        q["next_followup_date"] = {"$lt": today, "$ne": None}
    elif view == "critical":
        q["priority"] = {"$in": ["high", "critical", "High", "Critical"]}
    rows = await db.enquiries.find(q, {"_id": 0}).sort("next_followup_date", 1).to_list(5000)
    headers = ["enquiry_number", "client_name", "service_type", "estimated_value",
                "status", "priority", "next_followup_date", "last_followup_date",
                "action_owner", "assigned_to", "source", "created_at"]
    return _csv_response(rows, headers, f"enquiry-followups-{view}.csv")


@router.get("/enquiry-followups/export.xlsx")
async def export_followups_xlsx(view: str = "all",
                                 user: dict = Depends(require_permission("quotations", "read"))):
    """Iter 122 — Excel with status/priority colour-coding."""
    today = _date.today().isoformat()
    q: Dict[str, Any] = {"status": {"$nin": ["won", "lost", "dropped"]}}
    if view == "today":
        q["next_followup_date"] = today
    elif view == "upcoming":
        q["next_followup_date"] = {"$gt": today}
    elif view == "overdue":
        q["next_followup_date"] = {"$lt": today, "$ne": None}
    elif view == "critical":
        q["priority"] = {"$in": ["high", "critical", "High", "Critical"]}
    rows = await db.enquiries.find(q, {"_id": 0}).sort("next_followup_date", 1).to_list(5000)
    headers = ["enquiry_number", "client_name", "service_type", "estimated_value",
                "status", "priority", "next_followup_date", "last_followup_date",
                "action_owner", "assigned_to", "source", "created_at"]
    return _xlsx_response(rows, headers, f"enquiry-followups-{view}.xlsx",
                           sheet_name=f"Followups {view}",
                           title=f"Enquiry Follow-Ups — {view.title()} View",
                           status_columns=["status", "priority"])


@router.get("/action-items/export.csv")
async def export_action_items_csv(view: str = "all",
                                    user: dict = Depends(require_permission("projects", "read"))):
    today = _date.today().isoformat()
    q: Dict[str, Any] = {}
    if view == "pending":
        q["status"] = {"$in": ["pending", "in_progress"]}
    elif view == "overdue":
        q["status"] = {"$in": ["pending", "in_progress"]}
        q["due_date"] = {"$lt": today, "$ne": None}
    elif view == "completed":
        q["status"] = "completed"
    rows = await db.project_action_items.find(q, {"_id": 0}).sort("due_date", 1).to_list(5000)
    headers = ["title", "project_id", "related_factor", "assigned_to",
                "priority", "due_date", "status", "created_at", "completed_at"]
    return _csv_response(rows, headers, f"action-items-{view}.csv")


@router.get("/action-items/export.xlsx")
async def export_action_items_xlsx(view: str = "all",
                                     user: dict = Depends(require_permission("projects", "read"))):
    """Iter 122 — Excel with status/priority colour-coding."""
    today = _date.today().isoformat()
    q: Dict[str, Any] = {}
    if view == "pending":
        q["status"] = {"$in": ["pending", "in_progress"]}
    elif view == "overdue":
        q["status"] = {"$in": ["pending", "in_progress"]}
        q["due_date"] = {"$lt": today, "$ne": None}
    elif view == "completed":
        q["status"] = "completed"
    rows = await db.project_action_items.find(q, {"_id": 0}).sort("due_date", 1).to_list(5000)
    headers = ["title", "project_id", "related_factor", "assigned_to",
                "priority", "due_date", "status", "created_at", "completed_at"]
    return _xlsx_response(rows, headers, f"action-items-{view}.xlsx",
                           sheet_name=f"Action Items {view}",
                           title=f"Project Action Items — {view.title()}",
                           status_columns=["status", "priority"])


@router.post("/scheduler/run-enquiry-reminders")
async def trigger_enquiry_reminders(user: dict = Depends(require_permission("quotations", "write"))):
    """Manual trigger for the enquiry-reminder cron — useful for testing or
    catching up after downtime."""
    from scheduler import _enquiry_reminder_job
    await _enquiry_reminder_job()
    return {"ok": True, "ts": now_iso()}


@router.get("/me/action-items/summary")
async def my_action_items_summary(user: dict = Depends(require_permission("projects", "read"))):
    """Iter 121 — count of action items assigned to the current user, for the
    home-dashboard widget. Counts by status + 3 most-urgent rows."""
    uid = user.get("id")
    name = user.get("name") or user.get("email")
    today = _date.today().isoformat()
    me_q = {"$or": [{"assigned_to_id": uid}, {"assigned_to": name}]}

    async def _n(extra: Dict[str, Any]) -> int:
        return await db.project_action_items.count_documents({**me_q, **extra})

    pending = await _n({"status": {"$in": ["pending", "in_progress"]}})
    overdue = await _n({"status": {"$in": ["pending", "in_progress"]},
                        "due_date": {"$lt": today, "$ne": None}})
    completed_7d = await _n({"status": "completed",
                              "completed_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}})
    top = await db.project_action_items.find(
        {**me_q, "status": {"$in": ["pending", "in_progress"]}},
        {"_id": 0, "id": 1, "title": 1, "due_date": 1, "priority": 1, "related_factor": 1},
    ).sort("due_date", 1).limit(5).to_list(5)
    return {"pending": pending, "overdue": overdue, "completed_7d": completed_7d, "top": top}
