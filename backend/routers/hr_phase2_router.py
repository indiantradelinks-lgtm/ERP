"""HR Phase 2 — Shifts, Attendance workflow (approval+lock+audit), Overtime workflow,
Compliance Alerts, Safety Readiness. Extends (does NOT replace) Phase 1 + the existing
/api/hr/* leave module.

Endpoints prefixed with /api/hr2.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, date, time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core import db, get_current_user, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/hr2", tags=["hr-phase2"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _strip(d):
    if d is None:
        return None
    d.pop("_id", None)
    return d


def _parse_hhmm(s: Optional[str]) -> Optional[time]:
    if not s:
        return None
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except Exception:
        return None


def _compute_hours(in_time: Optional[str], out_time: Optional[str],
                   break_min: float = 0.0) -> float:
    """Returns total worked hours.  Supports night shift (out < in → next day)."""
    t_in = _parse_hhmm(in_time)
    t_out = _parse_hhmm(out_time)
    if not t_in or not t_out:
        return 0.0
    today = date.today()
    dt_in = datetime.combine(today, t_in)
    dt_out = datetime.combine(today, t_out)
    if dt_out <= dt_in:
        dt_out += timedelta(days=1)  # night shift
    hours = (dt_out - dt_in).total_seconds() / 3600.0 - (break_min / 60.0)
    return max(0.0, round(hours, 2))


async def _seq(prefix: str) -> str:
    doc = await db.counters.find_one_and_update(
        {"id": f"seq_{prefix.rstrip('-')}"},
        {"$inc": {"n": 1}, "$setOnInsert": {"id": f"seq_{prefix.rstrip('-')}"}},
        upsert=True, return_document=True,
    )
    n = (doc or {}).get("n", 1)
    return f"{prefix}{datetime.now(timezone.utc).year}-{n:04d}"


async def _log_attendance_audit(rid: str, action: str, before: dict | None,
                                after: dict | None, user: dict, ip: str):
    await db.hr_attendance_audit.insert_one({
        "id": new_id(), "attendance_id": rid, "action": action,
        "before": before, "after": after,
        "by_id": user.get("id"), "by_name": user.get("name") or user.get("email"),
        "by_role": user.get("role"), "ip": ip, "at": now_iso(),
    })


# ──────────────────────────────────────────────────────────────────────────────
# 1.  SHIFT MASTER
# ──────────────────────────────────────────────────────────────────────────────
class ShiftIn(BaseModel):
    code: str
    name: str
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    break_minutes: float = 0.0
    standard_hours: float = 8.0
    overtime_after: float = 8.0
    project_code: Optional[str] = None
    employee_type: Optional[str] = None  # all | office_staff | site_staff | worker
    night_shift: bool = False
    active: bool = True
    remarks: Optional[str] = None


@router.get("/shifts")
async def list_shifts(active_only: bool = False, project_code: Optional[str] = None,
                      user: dict = Depends(require_permission("hr_shifts", "read"))):
    q: Dict[str, Any] = {}
    if active_only:
        q["active"] = True
    if project_code:
        q["$or"] = [{"project_code": project_code}, {"project_code": None}, {"project_code": ""}]
    return await db.hr_shifts.find(q, {"_id": 0}).sort("code", 1).to_list(200)


@router.post("/shifts")
async def create_shift(p: ShiftIn, request: Request,
                       user: dict = Depends(require_permission("hr_shifts", "write"))):
    code = p.code.strip().upper()
    if not code:
        raise HTTPException(400, "code is required")
    if await db.hr_shifts.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(409, f"Shift '{code}' already exists")
    if not _parse_hhmm(p.start_time) or not _parse_hhmm(p.end_time):
        raise HTTPException(400, "start_time / end_time must be HH:MM")
    doc = {**p.model_dump(), "code": code, "id": new_id(),
           "created_by": user["id"], "created_at": now_iso()}
    await db.hr_shifts.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="hr_shifts",
                record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/shifts/{sid}")
async def update_shift(sid: str, p: ShiftIn, request: Request,
                       user: dict = Depends(require_permission("hr_shifts", "write"))):
    existing = await db.hr_shifts.find_one({"id": sid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Shift not found")
    upd = {**p.model_dump(), "code": p.code.upper(), "updated_at": now_iso(),
           "updated_by": user["id"]}
    await db.hr_shifts.update_one({"id": sid}, {"$set": upd})
    row = await db.hr_shifts.find_one({"id": sid}, {"_id": 0})
    await audit(user=user, action="update", resource="hr_shifts",
                record_id=sid, before=existing, after=row, ip=_ip(request))
    return row


@router.delete("/shifts/{sid}")
async def delete_shift(sid: str, user: dict = Depends(require_permission("hr_shifts", "delete"))):
    existing = await db.hr_shifts.find_one({"id": sid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Shift not found")
    if await db.attendance.count_documents({"shift_code": existing["code"]}):
        # Soft delete — keep history intact
        await db.hr_shifts.update_one({"id": sid}, {"$set": {"active": False}})
        return {"ok": True, "soft_deleted": True}
    await db.hr_shifts.delete_one({"id": sid})
    return {"ok": True}


@router.post("/shifts/seed-defaults")
async def seed_default_shifts(user: dict = Depends(require_permission("hr_shifts", "write"))):
    defaults = [
        ("GEN", "General Shift",          "09:00", "18:00", 60, 8, 8, False),
        ("DAY", "Day Shift",              "07:00", "16:00", 30, 8, 8, False),
        ("EVE", "Evening Shift",          "14:00", "23:00", 30, 8, 8, False),
        ("NIGHT", "Night Shift",          "22:00", "06:00", 30, 8, 8, True),
        ("HALF", "Half Day Shift",        "09:00", "13:00", 0,  4, 4, False),
    ]
    added = 0
    for code, name, st, et, bm, sh, ota, night in defaults:
        if not await db.hr_shifts.find_one({"code": code}, {"_id": 0}):
            await db.hr_shifts.insert_one({
                "id": new_id(), "code": code, "name": name,
                "start_time": st, "end_time": et, "break_minutes": bm,
                "standard_hours": sh, "overtime_after": ota,
                "night_shift": night, "active": True,
                "employee_type": "all",
                "created_at": now_iso(), "created_by": user["id"],
            })
            added += 1
    return {"added": added, "total": await db.hr_shifts.count_documents({})}


# ──────────────────────────────────────────────────────────────────────────────
# 2.  ATTENDANCE WORKFLOW  (extends existing `attendance` collection)
# ──────────────────────────────────────────────────────────────────────────────
ATT_STATUSES = {"present", "absent", "half_day", "leave", "weekly_off", "holiday", "on_duty"}
ATT_SOURCES = {"manual", "mobile", "biometric", "upload", "site_entry"}


class AttendanceIn(BaseModel):
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    person_type: str = "employee"          # employee | worker
    date: str                              # YYYY-MM-DD
    project_code: Optional[str] = None
    site_location: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    skill: Optional[str] = None
    shift_code: Optional[str] = None
    in_time: Optional[str] = None          # HH:MM
    out_time: Optional[str] = None
    total_hours: Optional[float] = None    # auto if missing
    overtime_hours: Optional[float] = None # auto if missing
    status: str = "present"
    source: str = "manual"
    remarks: Optional[str] = None
    attachment_url: Optional[str] = None
    allow_future: bool = False             # explicit override


async def _resolve_person(att: AttendanceIn) -> dict:
    """Fetch the underlying employee/worker — block inactive."""
    if att.person_type == "worker":
        if not att.employee_id:
            return {}
        row = await db.hr_workers.find_one({"id": att.employee_id}, {"_id": 0})
        if row and row.get("active") is False:
            raise HTTPException(400, f"Worker '{row.get('name')}' is INACTIVE — attendance blocked")
        return row or {}
    if att.employee_id:
        row = await db.employees.find_one({"id": att.employee_id}, {"_id": 0})
    elif att.employee_code:
        row = await db.employees.find_one(
            {"$or": [{"emp_code": att.employee_code}, {"employee_id": att.employee_code}]},
            {"_id": 0},
        )
    else:
        row = None
    if row and str(row.get("status", "active")).lower() == "inactive":
        raise HTTPException(400, f"Employee '{row.get('name')}' is INACTIVE — attendance blocked")
    return row or {}


@router.post("/attendance")
async def mark_attendance(p: AttendanceIn, request: Request,
                          user: dict = Depends(require_permission("attendance", "write"))):
    # 1. Validations
    if p.status not in ATT_STATUSES:
        raise HTTPException(400, f"status must be in {sorted(ATT_STATUSES)}")
    if p.source not in ATT_SOURCES:
        raise HTTPException(400, f"source must be in {sorted(ATT_SOURCES)}")
    try:
        d = datetime.fromisoformat(p.date).date()
    except Exception:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    if d > datetime.now(timezone.utc).date() and not p.allow_future:
        raise HTTPException(400, "Cannot mark attendance for future date")

    person = await _resolve_person(p)

    # 2. Lock-period guard
    if await db.hr_attendance_locks.find_one(
        {"project_code": p.project_code, "month": d.strftime("%Y-%m"), "locked": True},
        {"_id": 0},
    ):
        raise HTTPException(400, f"Attendance for {d.strftime('%Y-%m')} is LOCKED for this project")

    # 3. Duplicate guard
    dup_q: Dict[str, Any] = {"date": p.date}
    if p.employee_id:
        dup_q["employee_id"] = p.employee_id
    elif p.employee_name:
        dup_q["employee_name"] = p.employee_name
    if p.project_code:
        dup_q["project_code"] = p.project_code
    if await db.attendance.find_one(dup_q, {"_id": 0, "id": 1}):
        raise HTTPException(409, "Duplicate attendance — already marked for this employee/date/project")

    # 4. Shift + hours calc
    shift = None
    if p.shift_code:
        shift = await db.hr_shifts.find_one({"code": p.shift_code.upper()}, {"_id": 0})
    break_min = (shift or {}).get("break_minutes", 0) or 0
    std_hours = (shift or {}).get("standard_hours", 8.0) or 8.0
    ot_after = (shift or {}).get("overtime_after", std_hours)

    total = p.total_hours if p.total_hours is not None else _compute_hours(
        p.in_time, p.out_time, break_min)
    ot = p.overtime_hours if p.overtime_hours is not None else max(0.0, round(total - ot_after, 2))

    doc = {
        "id": new_id(),
        "employee_id": p.employee_id or person.get("id"),
        "employee_name": p.employee_name or person.get("name"),
        "employee_code": p.employee_code or person.get("emp_code") or person.get("code"),
        "person_type": p.person_type,
        "date": p.date,
        "project_code": p.project_code or person.get("current_project_code"),
        "site_location": p.site_location or person.get("current_site_code"),
        "department": p.department or person.get("department"),
        "designation": p.designation or person.get("designation"),
        "skill": p.skill or person.get("skill_name"),
        "shift_code": (p.shift_code or "").upper() or None,
        "in_time": p.in_time, "out_time": p.out_time,
        "check_in": p.in_time, "check_out": p.out_time,   # back-compat
        "hours": total,                                    # back-compat with payroll
        "total_hours": total, "overtime_hours": ot,
        "status": p.status, "source": p.source,
        "remarks": p.remarks, "attachment_url": p.attachment_url,
        "marked_by_id": user["id"],
        "marked_by_name": user.get("name") or user.get("email"),
        "approval_status": "pending",
        "approved_by_id": None, "approved_by_name": None, "approved_at": None,
        "locked": False, "lock_id": None,
        "created_at": now_iso(),
    }
    await db.attendance.insert_one(doc)
    doc.pop("_id", None)
    await _log_attendance_audit(doc["id"], "create", None, doc, user, _ip(request))
    return doc


class AttendanceEdit(BaseModel):
    in_time: Optional[str] = None
    out_time: Optional[str] = None
    total_hours: Optional[float] = None
    overtime_hours: Optional[float] = None
    status: Optional[str] = None
    remarks: Optional[str] = None
    shift_code: Optional[str] = None


@router.put("/attendance/{aid}")
async def edit_attendance(aid: str, p: AttendanceEdit, request: Request,
                          user: dict = Depends(require_permission("attendance", "write"))):
    row = await db.attendance.find_one({"id": aid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Attendance not found")
    if row.get("locked"):
        if user.get("role") not in {"super_admin", "hr_executive", "general_manager"}:
            raise HTTPException(403, "Attendance is LOCKED — only HR Manager / Admin can edit")
    upd = {k: v for k, v in p.model_dump().items() if v is not None}
    # Recompute total / OT when times change
    if "in_time" in upd or "out_time" in upd:
        shift = None
        sc = upd.get("shift_code") or row.get("shift_code")
        if sc:
            shift = await db.hr_shifts.find_one({"code": sc.upper()}, {"_id": 0})
        break_min = (shift or {}).get("break_minutes", 0) or 0
        ot_after = (shift or {}).get("overtime_after", 8.0) or 8.0
        new_total = _compute_hours(upd.get("in_time", row.get("in_time")),
                                   upd.get("out_time", row.get("out_time")), break_min)
        upd["total_hours"] = new_total
        upd["hours"] = new_total
        upd["overtime_hours"] = max(0.0, round(new_total - ot_after, 2))
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]
    await db.attendance.update_one({"id": aid}, {"$set": upd})
    after = await db.attendance.find_one({"id": aid}, {"_id": 0})
    await _log_attendance_audit(aid, "update", row, after, user, _ip(request))
    return after


class AttApprovalIn(BaseModel):
    ids: List[str]
    decision: str = "approve"   # approve | reject
    remarks: Optional[str] = None


@router.post("/attendance/approve")
async def bulk_approve_attendance(p: AttApprovalIn, request: Request,
                                  user: dict = Depends(require_permission("attendance", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager",
                                "dept_head", "hr_executive", "project_manager"}:
        raise HTTPException(403, "Only Manager+ can approve attendance")
    if p.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve | reject")
    status = "approved" if p.decision == "approve" else "rejected"
    upd = {"approval_status": status, "approved_at": now_iso(),
           "approved_by_id": user["id"],
           "approved_by_name": user.get("name") or user.get("email"),
           "approval_remarks": p.remarks}
    result = await db.attendance.update_many(
        {"id": {"$in": p.ids}, "approval_status": "pending"}, {"$set": upd}
    )
    for aid in p.ids:
        await _log_attendance_audit(aid, f"approval_{status}", None, upd, user, _ip(request))
    return {"updated": result.modified_count, "decision": status}


class LockIn(BaseModel):
    project_code: Optional[str] = None
    month: str                      # YYYY-MM
    reason: Optional[str] = None


@router.post("/attendance/lock")
async def lock_attendance(p: LockIn, request: Request,
                          user: dict = Depends(require_permission("attendance", "write"))):
    if user.get("role") not in {"super_admin", "hr_executive", "general_manager"}:
        raise HTTPException(403, "Only HR Manager / Admin / GM can lock attendance")
    try:
        datetime.strptime(p.month, "%Y-%m")
    except Exception:
        raise HTTPException(400, "month must be YYYY-MM")
    lid = new_id()
    doc = {"id": lid, "project_code": p.project_code, "month": p.month,
           "locked": True, "locked_by": user["id"],
           "locked_by_name": user.get("name") or user.get("email"),
           "locked_at": now_iso(), "reason": p.reason}
    await db.hr_attendance_locks.update_one(
        {"project_code": p.project_code, "month": p.month},
        {"$set": doc}, upsert=True)
    # Stamp all attendance rows in scope
    q: Dict[str, Any] = {"date": {"$regex": f"^{p.month}-"}}
    if p.project_code:
        q["project_code"] = p.project_code
    await db.attendance.update_many(q, {"$set": {"locked": True, "lock_id": lid}})
    return {"locked": True, "month": p.month, "project_code": p.project_code}


@router.post("/attendance/unlock")
async def unlock_attendance(p: LockIn, request: Request,
                            user: dict = Depends(require_permission("attendance", "write"))):
    if user.get("role") not in {"super_admin", "hr_executive"}:
        raise HTTPException(403, "Only Admin / HR Manager can unlock attendance")
    await db.hr_attendance_locks.update_one(
        {"project_code": p.project_code, "month": p.month},
        {"$set": {"locked": False, "unlocked_by": user["id"],
                  "unlocked_at": now_iso()}})
    q: Dict[str, Any] = {"date": {"$regex": f"^{p.month}-"}}
    if p.project_code:
        q["project_code"] = p.project_code
    await db.attendance.update_many(q, {"$set": {"locked": False}})
    return {"unlocked": True, "month": p.month, "project_code": p.project_code}


@router.get("/attendance/locks")
async def list_locks(user: dict = Depends(require_permission("attendance", "read"))):
    return await db.hr_attendance_locks.find({"locked": True}, {"_id": 0}) \
        .sort("locked_at", -1).to_list(200)


@router.get("/attendance/register")
async def attendance_register(from_date: Optional[str] = None, to_date: Optional[str] = None,
                              project_code: Optional[str] = None,
                              employee_id: Optional[str] = None,
                              designation: Optional[str] = None,
                              status: Optional[str] = None,
                              approval_status: Optional[str] = None,
                              limit: int = 500,
                              user: dict = Depends(require_permission("attendance", "read"))):
    q: Dict[str, Any] = {}
    if from_date and to_date:
        q["date"] = {"$gte": from_date, "$lte": to_date}
    elif from_date:
        q["date"] = {"$gte": from_date}
    elif to_date:
        q["date"] = {"$lte": to_date}
    if project_code:
        q["project_code"] = project_code
    if employee_id:
        q["employee_id"] = employee_id
    if designation:
        q["designation"] = designation
    if status:
        q["status"] = status
    if approval_status:
        q["approval_status"] = approval_status
    rows = await db.attendance.find(q, {"_id": 0}).sort([("date", -1)]).limit(limit).to_list(limit)
    return rows


@router.get("/attendance/monthly-summary")
async def monthly_summary(month: str = Query(..., description="YYYY-MM"),
                          project_code: Optional[str] = None,
                          user: dict = Depends(require_permission("attendance", "read"))):
    try:
        datetime.strptime(month, "%Y-%m")
    except Exception:
        raise HTTPException(400, "month must be YYYY-MM")
    match: Dict[str, Any] = {"date": {"$regex": f"^{month}-"}}
    if project_code:
        match["project_code"] = project_code
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"emp_id": "$employee_id", "emp_name": "$employee_name"},
            "present": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}},
            "absent":  {"$sum": {"$cond": [{"$eq": ["$status", "absent"]},  1, 0]}},
            "leave":   {"$sum": {"$cond": [{"$eq": ["$status", "leave"]},   1, 0]}},
            "half_day":{"$sum": {"$cond": [{"$eq": ["$status", "half_day"]},1, 0]}},
            "weekly_off":{"$sum": {"$cond": [{"$eq": ["$status", "weekly_off"]},1, 0]}},
            "holiday": {"$sum": {"$cond": [{"$eq": ["$status", "holiday"]}, 1, 0]}},
            "on_duty": {"$sum": {"$cond": [{"$eq": ["$status", "on_duty"]}, 1, 0]}},
            "total_hours": {"$sum": "$total_hours"},
            "overtime_hours": {"$sum": "$overtime_hours"},
        }},
        {"$sort": {"_id.emp_name": 1}},
    ]
    rows = await db.attendance.aggregate(pipeline).to_list(2000)
    return {"month": month, "project_code": project_code,
            "rows": [{
                "employee_id": r["_id"]["emp_id"],
                "employee_name": r["_id"]["emp_name"],
                **{k: v for k, v in r.items() if k != "_id"}
            } for r in rows]}


@router.get("/attendance/{aid}/audit")
async def attendance_audit(aid: str, user: dict = Depends(require_permission("attendance", "read"))):
    return await db.hr_attendance_audit.find({"attendance_id": aid}, {"_id": 0}) \
        .sort("at", -1).to_list(200)


# ──────────────────────────────────────────────────────────────────────────────
# 3.  OVERTIME WORKFLOW   (extends existing `overtime` collection)
# ──────────────────────────────────────────────────────────────────────────────
class OvertimeIn(BaseModel):
    employee_id: Optional[str] = None
    employee_name: str
    employee_code: Optional[str] = None
    person_type: str = "employee"
    project_code: Optional[str] = None
    site_location: Optional[str] = None
    overtime_date: str                # YYYY-MM-DD
    normal_hours: float = 8.0
    overtime_hours: float
    reason: str
    overtime_rate: float = 0.0


@router.post("/overtime")
async def create_overtime(p: OvertimeIn, request: Request,
                          user: dict = Depends(require_permission("overtime", "write"))):
    if p.overtime_hours <= 0:
        raise HTTPException(400, "overtime_hours must be > 0")
    if not p.reason.strip():
        raise HTTPException(400, "reason is required")
    try:
        datetime.fromisoformat(p.overtime_date)
    except Exception:
        raise HTTPException(400, "overtime_date must be YYYY-MM-DD")
    request_no = await _seq("OT-")
    amount = round(p.overtime_hours * p.overtime_rate, 2)
    doc = {
        "id": new_id(), "request_no": request_no,
        **p.model_dump(),
        # back-compat with legacy `overtime` CRUD fields
        "date": p.overtime_date,
        "employee": p.employee_name,
        "hours": p.overtime_hours,
        "rate": p.overtime_rate,
        "project": p.project_code,
        "approver": None,
        "overtime_amount": amount,
        "pm_status": "pending", "pm_approved_by": None, "pm_approved_at": None,
        "hr_status": "pending", "hr_approved_by": None, "hr_approved_at": None,
        "status": "pending",
        "payroll_status": "not_processed",
        "requested_by_id": user["id"],
        "requested_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.overtime.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="overtime",
                record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


class OtDecision(BaseModel):
    remarks: Optional[str] = None


@router.post("/overtime/{oid}/approve-pm")
async def approve_overtime_pm(oid: str, p: OtDecision, request: Request,
                              user: dict = Depends(require_permission("overtime", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager",
                                "dept_head", "project_manager"}:
        raise HTTPException(403, "Only Project Manager / Dept Head+ can approve OT (Step 1)")
    row = await db.overtime.find_one({"id": oid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "OT not found")
    if row.get("pm_status") == "approved":
        raise HTTPException(400, "Already approved by PM")
    upd = {"pm_status": "approved", "pm_approved_by": user.get("name") or user.get("email"),
           "pm_approved_at": now_iso(),
           "status": "hr_pending" if row.get("hr_status") == "pending" else "approved",
           "approver": user.get("name") or user.get("email"),
           "pm_remarks": p.remarks}
    await db.overtime.update_one({"id": oid}, {"$set": upd})
    await audit(user=user, action="approve_pm", resource="overtime",
                record_id=oid, after=upd, ip=_ip(request))
    return await db.overtime.find_one({"id": oid}, {"_id": 0})


@router.post("/overtime/{oid}/approve-hr")
async def approve_overtime_hr(oid: str, p: OtDecision, request: Request,
                              user: dict = Depends(require_permission("overtime", "write"))):
    if user.get("role") not in {"super_admin", "hr_executive", "general_manager"}:
        raise HTTPException(403, "Only HR / GM / Admin can approve OT (Step 2)")
    row = await db.overtime.find_one({"id": oid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "OT not found")
    if row.get("pm_status") != "approved":
        raise HTTPException(400, "PM approval required first")
    upd = {"hr_status": "approved", "hr_approved_by": user.get("name") or user.get("email"),
           "hr_approved_at": now_iso(),
           "status": "approved", "hr_remarks": p.remarks}
    await db.overtime.update_one({"id": oid}, {"$set": upd})
    await audit(user=user, action="approve_hr", resource="overtime",
                record_id=oid, after=upd, ip=_ip(request))
    return await db.overtime.find_one({"id": oid}, {"_id": 0})


@router.post("/overtime/{oid}/reject")
async def reject_overtime(oid: str, p: OtDecision, request: Request,
                          user: dict = Depends(require_permission("overtime", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager",
                                "dept_head", "hr_executive", "project_manager"}:
        raise HTTPException(403, "Only Manager+ can reject OT")
    row = await db.overtime.find_one({"id": oid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "OT not found")
    upd = {"status": "rejected", "rejected_by": user.get("name") or user.get("email"),
           "rejected_at": now_iso(), "reject_reason": p.remarks,
           "pm_status": row.get("pm_status") if row.get("pm_status") == "approved" else "rejected",
           "hr_status": row.get("hr_status") if row.get("hr_status") == "approved" else "rejected"}
    await db.overtime.update_one({"id": oid}, {"$set": upd})
    return await db.overtime.find_one({"id": oid}, {"_id": 0})


@router.get("/overtime/register")
async def overtime_register(status: Optional[str] = None,
                            project_code: Optional[str] = None,
                            employee_id: Optional[str] = None,
                            user: dict = Depends(require_permission("overtime", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_code:
        q["project_code"] = project_code
    if employee_id:
        q["employee_id"] = employee_id
    return await db.overtime.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/overtime/project-cost")
async def overtime_project_cost(project_code: str,
                                user: dict = Depends(require_permission("overtime", "read"))):
    pipeline = [
        {"$match": {"project_code": project_code, "status": "approved"}},
        {"$group": {"_id": None,
                    "total_hours": {"$sum": {"$ifNull": ["$overtime_hours", "$hours"]}},
                    "total_amount": {"$sum": {"$ifNull": ["$overtime_amount", 0]}},
                    "count": {"$sum": 1}}}
    ]
    rows = await db.overtime.aggregate(pipeline).to_list(1)
    if not rows:
        return {"project_code": project_code, "total_hours": 0, "total_amount": 0, "count": 0}
    r = rows[0]
    r.pop("_id", None)
    return {"project_code": project_code, **r}


# ──────────────────────────────────────────────────────────────────────────────
# 4.  COMPLIANCE ALERTS
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/compliance-alerts")
async def compliance_alerts(days: int = 30,
                            user: dict = Depends(require_permission("attendance", "read"))):
    today = datetime.now(timezone.utc).date()
    horizon = (today + timedelta(days=days)).isoformat()
    today_s = today.isoformat()
    collections = await db.list_collection_names()

    # 1. Missing mandatory fields on active employees
    emp_q = {"status": {"$ne": "inactive"}}
    pf_missing = await db.employees.count_documents({**emp_q,
        "$or": [{"pf_uan": {"$exists": False}}, {"pf_uan": None}, {"pf_uan": ""}]})
    esic_missing = await db.employees.count_documents({**emp_q, "esic_applicable": True,
        "$or": [{"esic_no": {"$exists": False}}, {"esic_no": None}, {"esic_no": ""}]})
    bank_missing = await db.employees.count_documents({**emp_q,
        "$or": [{"bank_account": {"$exists": False}}, {"bank_account": None}, {"bank_account": ""}]})
    pan_missing = await db.employees.count_documents({**emp_q,
        "$or": [{"pan": {"$exists": False}}, {"pan": None}, {"pan": ""}]})

    # 2. Document expiry
    expiring_docs, missing_docs = 0, 0
    if "hr_documents" in collections:
        expiring_docs = await db.hr_documents.count_documents({
            "expiry_date": {"$gte": today_s, "$lte": horizon}})
        missing_docs = await db.hr_documents.count_documents({"verification_status": "pending"})

    # 3. Medical fitness
    medical_expiring = await db.hr_medical_fitness.count_documents({
        "valid_till": {"$gte": today_s, "$lte": horizon}}) \
        if "hr_medical_fitness" in collections else 0
    medical_expired = await db.hr_medical_fitness.count_documents({
        "valid_till": {"$lt": today_s, "$ne": None}}) \
        if "hr_medical_fitness" in collections else 0

    # 4. Safety / Training expiry (cert.expiry_date on employees)
    train_expiring, rope_expiring = 0, 0
    emps_with_certs = await db.employees.find(
        {"certifications": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "name": 1, "certifications": 1}).to_list(2000)
    for e in emps_with_certs:
        for c in (e.get("certifications") or []):
            try:
                exp = datetime.fromisoformat(str(c.get("expiry_date"))).date()
                if today <= exp <= today + timedelta(days=days):
                    train_expiring += 1
                    if "rope" in str(c.get("name", "")).lower():
                        rope_expiring += 1
            except Exception:
                pass

    # 5. Police verification pending
    police_pending = await db.hr_police_verification.count_documents({"status": "pending"}) \
        if "hr_police_verification" in collections else 0

    # 6. Inactive but deployed
    deployed_inactive = await db.deployments.count_documents({
        "status": "active", "employee_status": "inactive"}) \
        if "deployments" in collections else 0

    # 7. Pending approvals
    att_pending = await db.attendance.count_documents({"approval_status": "pending"})
    ot_pending = await db.overtime.count_documents({"status": {"$in": ["pending", "hr_pending"]}})
    leave_pending = await db.leave_applications.count_documents({"status": "pending"}) \
        if "leave_applications" in collections else 0

    cards: List[Dict[str, Any]] = []
    def add(key, label, count, severity, link=None):
        cards.append({"key": key, "label": label, "count": int(count),
                      "severity": severity, "link": link})

    add("missing_documents", "Missing / Pending Documents", missing_docs, "high" if missing_docs else "low")
    add("expiring_documents", f"Documents Expiring ≤ {days}d", expiring_docs, "medium" if expiring_docs else "low")
    add("medical_expired", "Medical Fitness EXPIRED", medical_expired, "high" if medical_expired else "low")
    add("medical_expiring", f"Medical Fitness Expiring ≤ {days}d", medical_expiring, "medium" if medical_expiring else "low")
    add("training_expiring", f"Safety Training Expiring ≤ {days}d", train_expiring, "medium" if train_expiring else "low")
    add("rope_expiring", f"Rope Access Cert Expiring ≤ {days}d", rope_expiring, "high" if rope_expiring else "low")
    add("police_pending", "Police Verification Pending", police_pending, "medium" if police_pending else "low")
    add("pf_missing", "PF/UAN Missing", pf_missing, "medium" if pf_missing else "low")
    add("esic_missing", "ESIC No. Missing (where applicable)", esic_missing, "medium" if esic_missing else "low")
    add("bank_missing", "Bank Details Missing", bank_missing, "high" if bank_missing else "low")
    add("pan_missing", "PAN Missing", pan_missing, "medium" if pan_missing else "low")
    add("inactive_deployed", "Inactive Employees Still Deployed", deployed_inactive, "high" if deployed_inactive else "low")
    add("att_pending", "Attendance Approvals Pending", att_pending, "medium" if att_pending else "low")
    add("ot_pending", "Overtime Approvals Pending", ot_pending, "medium" if ot_pending else "low")
    add("leave_pending", "Leave Approvals Pending", leave_pending, "medium" if leave_pending else "low")

    total_open = sum(c["count"] for c in cards if c["severity"] in ("high", "medium"))
    return {"as_of": now_iso(), "horizon_days": days, "total_open": total_open, "cards": cards}


@router.get("/medical-fitness-expiry")
async def medical_fitness_expiry(days: int = 30,
                                 user: dict = Depends(require_permission("employees", "read"))):
    today_s = _today()
    horizon = (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()
    rows = await db.hr_medical_fitness.find(
        {"valid_till": {"$ne": None}}, {"_id": 0},
    ).sort("valid_till", 1).to_list(2000)
    expired, expiring = [], []
    for r in rows:
        vt = r.get("valid_till")
        if not vt:
            continue
        if vt < today_s:
            expired.append(r)
        elif today_s <= vt <= horizon:
            expiring.append(r)
    return {"expired": expired, "expiring": expiring}


@router.get("/training-expiry")
async def training_expiry(days: int = 30,
                          user: dict = Depends(require_permission("employees", "read"))):
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=days)
    rows = await db.employees.find(
        {"certifications": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "name": 1, "department": 1,
         "current_project_code": 1, "certifications": 1},
    ).to_list(2000)
    expired, expiring = [], []
    for e in rows:
        for c in (e.get("certifications") or []):
            try:
                exp = datetime.fromisoformat(str(c.get("expiry_date"))).date()
                base = {"employee_id": e["id"], "employee_name": e["name"],
                        "department": e.get("department"),
                        "project_code": e.get("current_project_code"),
                        "certification": c.get("name"),
                        "expiry_date": c.get("expiry_date")}
                if exp < today:
                    expired.append(base)
                elif exp <= horizon:
                    base["days_left"] = (exp - today).days
                    expiring.append(base)
            except Exception:
                pass
    expiring.sort(key=lambda x: x.get("days_left", 0))
    return {"expired": expired, "expiring": expiring}


# ──────────────────────────────────────────────────────────────────────────────
# 5.  SAFETY READINESS  (Inbound from Safety module)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/safety-readiness")
async def safety_readiness(project_code: Optional[str] = None,
                           user: dict = Depends(require_permission("employees", "read"))):
    """Combines safety induction + medical fitness + active certifications +
    PPE issued to determine deployment readiness."""
    today_s = _today()
    today = datetime.now(timezone.utc).date()

    # 1. Pull employees + workers
    emp_q: Dict[str, Any] = {"status": {"$ne": "inactive"}}
    if project_code:
        emp_q["current_project_code"] = project_code
    employees = await db.employees.find(emp_q, {"_id": 0}).to_list(5000)

    wrk_q: Dict[str, Any] = {"active": True}
    if project_code:
        wrk_q["current_project_code"] = project_code
    workers = await db.hr_workers.find(wrk_q, {"_id": 0}).to_list(5000)

    # 2. PPE map
    ppe_active: Dict[str, int] = {}
    if "ppe_issuance" in await db.list_collection_names():
        for p in await db.ppe_issuance.find({}, {"_id": 0}).to_list(5000):
            eid = p.get("employee_id")
            if not eid:
                continue
            ppe_active[eid] = ppe_active.get(eid, 0) + 1

    def _classify(person: dict, kind: str) -> Dict[str, Any]:
        reasons = []
        safety_ok = bool(person.get("safety_induction"))
        med_ok = False
        med_valid = person.get("medical_fitness_valid_till")
        if person.get("medical_fitness"):
            med_ok = True
            if med_valid and str(med_valid) < today_s:
                med_ok = False
                reasons.append("Medical fitness EXPIRED")
        if not safety_ok:
            reasons.append("Safety induction PENDING")
        # Cert check for skilled / rope-access
        skill = (person.get("skill_name") or person.get("designation") or "").lower()
        needs_cert = any(k in skill for k in ("rope", "scaffold", "rigger", "welder"))
        cert_ok = True
        if needs_cert:
            cert_ok = False
            for c in (person.get("certifications") or []):
                try:
                    exp = datetime.fromisoformat(str(c.get("expiry_date"))).date()
                    if exp >= today:
                        cert_ok = True
                        break
                except Exception:
                    pass
            if not cert_ok:
                reasons.append("Required trade certification missing/expired")
        ppe_ok = ppe_active.get(person.get("id"), 0) > 0
        ready = safety_ok and med_ok and cert_ok
        return {
            "kind": kind, "person_id": person.get("id"),
            "person_name": person.get("name"),
            "department": person.get("department"),
            "project_code": person.get("current_project_code"),
            "designation": person.get("designation") or person.get("skill_name"),
            "safety_induction": safety_ok,
            "medical_fitness": med_ok,
            "medical_valid_till": med_valid,
            "certification_ok": cert_ok,
            "ppe_issued": ppe_ok,
            "ready": ready, "blocking_reasons": reasons,
        }

    rows = [_classify(e, "employee") for e in employees] + \
           [_classify(w, "worker") for w in workers]
    ready = [r for r in rows if r["ready"]]
    blocked = [r for r in rows if not r["ready"]]
    return {"as_of": now_iso(), "project_code": project_code,
            "ready_count": len(ready), "blocked_count": len(blocked),
            "ready": ready[:500], "blocked": blocked[:500]}


# ──────────────────────────────────────────────────────────────────────────────
# 6.  Phase-2 Dashboard
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def hr_phase2_dashboard(user: dict = Depends(require_permission("attendance", "read"))):
    today_s = _today()
    month = today_s[:7]
    active_shifts = await db.hr_shifts.count_documents({"active": True})
    att_today = await db.attendance.count_documents({"date": today_s})
    att_pending = await db.attendance.count_documents({"approval_status": "pending"})
    att_locked = await db.hr_attendance_locks.count_documents({"locked": True})
    ot_pending = await db.overtime.count_documents({"status": {"$in": ["pending", "hr_pending"]}})
    ot_approved_month = await db.overtime.count_documents({"status": "approved",
                                                            "overtime_date": {"$regex": f"^{month}"}})
    leave_pending = await db.leave_applications.count_documents({"status": "pending"}) \
        if "leave_applications" in await db.list_collection_names() else 0
    return {
        "as_of": now_iso(), "month": month,
        "active_shifts": active_shifts,
        "attendance_today": att_today,
        "attendance_pending_approval": att_pending,
        "attendance_locked_periods": att_locked,
        "overtime_pending": ot_pending,
        "overtime_approved_month": ot_approved_month,
        "leave_pending": leave_pending,
    }
