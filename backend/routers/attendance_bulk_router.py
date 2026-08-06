"""Monthly Attendance bulk upload (per master):
  GET  /api/hr2/attendance/bulk/template?month=YYYY-MM&master=employee|worker
  POST /api/hr2/attendance/bulk/upload?month=...&master=...&project_code=...
Grid: one row per person, one column per day. Codes: P, A, HD, L, WO, H, OD.
OT: append +hours (e.g. P+2). Blank cells skipped. Entries land as approval_status=pending.
"""
from __future__ import annotations

import io
import re
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from scope import allowed_project_ids
from audit import audit

router = APIRouter(prefix="/hr2/attendance/bulk", tags=["attendance-bulk"])

CODE_MAP = {
    "P": "present", "A": "absent", "HD": "half_day", "L": "leave",
    "WO": "weekly_off", "H": "holiday", "OD": "on_duty",
}
MASTERS = {"employee", "worker"}
_CELL_RE = re.compile(r"^([A-Za-z]{1,2})(?:\+(\d+(?:\.\d+)?))?$")


def _parse_month(month: str) -> tuple[int, int, int]:
    try:
        y, m = int(month[:4]), int(month[5:7])
        return y, m, monthrange(y, m)[1]
    except Exception:
        raise HTTPException(400, "month must be YYYY-MM")


async def _people(master: str) -> List[dict]:
    if master not in MASTERS:
        raise HTTPException(400, "master must be 'employee' or 'worker'")
    q = {"status": {"$ne": "inactive"}}
    if master == "worker":
        q["master_category"] = "worker"
    else:
        q["$or"] = [{"master_category": {"$in": [None, "", "employee"]}}, {"master_category": {"$exists": False}}]
    return await db.employees.find(
        q, {"_id": 0, "id": 1, "employee_id": 1, "emp_code": 1, "name": 1, "department": 1,
             "designation": 1, "current_project_code": 1}).sort("name", 1).to_list(3000)


@router.get("/template")
async def bulk_template(month: str, master: str = "employee",
                          user: dict = Depends(require_permission("attendance", "read"))):
    _, _, ndays = _parse_month(month)
    people = await _people(master)
    wb = Workbook()
    ws = wb.active
    ws.title = "ATTENDANCE"
    ws.append(["id", "employee_code", "name", "department"] + [str(d) for d in range(1, ndays + 1)])
    for p in people:
        ws.append([p.get("id"), p.get("employee_id") or p.get("emp_code") or "", p.get("name") or "",
                   p.get("department") or ""] + [""] * ndays)
    inst = wb.create_sheet("INSTRUCTIONS")
    label = "Worker / Labour" if master == "worker" else "Employee"
    inst.append([f"INDIAN TRADE LINKS ERP — Monthly Attendance Upload ({label} Master) — {month}"])
    inst.append([])
    inst.append(["Fill one code per day column:"])
    inst.append(["  P = Present · A = Absent · HD = Half Day · L = Leave"])
    inst.append(["  WO = Weekly Off · H = Holiday · OD = On Duty"])
    inst.append(["  Overtime: append +hours, e.g. P+2 = Present with 2h OT"])
    inst.append(["  Blank cell = skipped (not marked)"])
    inst.append([])
    inst.append(["Rules:"])
    inst.append(["  • Do not edit the id / employee_code / name columns."])
    inst.append(["  • Uploaded entries land as PENDING APPROVAL — approve them from the Attendance register."])
    inst.append(["  • Existing entries for the same person+date are UPDATED (no duplicates)."])
    inst.append(["  • Months locked for a project are rejected per entry."])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="attendance_{master}_{month}.xlsx"'})


class DaySheetEntry(BaseModel):
    employee_id: str
    status: str
    overtime_hours: float = 0.0
    in_time: Optional[str] = None
    out_time: Optional[str] = None
    remarks: Optional[str] = None


class DaySheetIn(BaseModel):
    date: str
    project_code: str = "HEAD-OFFICE"
    master: str = "employee"
    entries: List[DaySheetEntry] = Field(..., min_length=1, max_length=2000)


async def _guard_project_access(user: dict, project_code: str):
    """Coordinators/PMs may only mark attendance for their own projects."""
    ids = await allowed_project_ids(user)
    if ids is None or project_code == "HEAD-OFFICE":
        if ids is not None and project_code == "HEAD-OFFICE" and user.get("role") in ("project_coordinator", "project_manager"):
            raise HTTPException(403, "Head Office attendance is managed by HR")
        return
    projs = await db.projects.find({"id": {"$in": ids}}, {"_id": 0, "code": 1, "name": 1}).to_list(500)
    tokens = {t for p in projs for t in (p.get("code"), p.get("name")) if t}
    if project_code not in tokens:
        raise HTTPException(403, "You can only mark attendance for your assigned projects")


@router.get("/day-sheet")
async def day_sheet(date: str, master: str = "employee", project_code: str = "HEAD-OFFICE",
                     designation: str | None = None, q: str | None = None,
                     only_project_people: bool = False,
                     user: dict = Depends(require_permission("attendance", "read"))):
    await _guard_project_access(user, project_code)
    people = await _people(master)
    if designation:
        people = [p for p in people if (p.get("designation") or "") == designation]
    if only_project_people and project_code != "HEAD-OFFICE":
        people = [p for p in people if p.get("current_project_code") == project_code]
    if q:
        s = q.lower()
        people = [p for p in people if s in (p.get("name") or "").lower() or s in (p.get("employee_id") or p.get("emp_code") or "").lower()]
    existing = {a["employee_id"]: a for a in await db.attendance.find(
        {"date": date, "employee_id": {"$in": [p["id"] for p in people]}},
        {"_id": 0, "employee_id": 1, "status": 1, "overtime_hours": 1, "approval_status": 1, "locked": 1,
         "project_code": 1, "in_time": 1, "out_time": 1, "remarks": 1, "total_hours": 1}).to_list(3000)}
    locked = bool(await db.hr_attendance_locks.find_one({"month": date[:7], "project_code": project_code, "locked": True}, {"_id": 0, "id": 1}))
    rows = []
    for p in people:
        a = existing.get(p["id"], {})
        rows.append({
            "employee_id": p["id"],
            "code": p.get("employee_id") or p.get("emp_code") or "",
            "name": p.get("name"),
            "designation": p.get("designation") or "",
            "status": a.get("status"),
            "overtime_hours": a.get("overtime_hours") or 0,
            "in_time": a.get("in_time"),
            "out_time": a.get("out_time"),
            "remarks": a.get("remarks"),
            "total_hours": a.get("total_hours"),
            "approval_status": a.get("approval_status"),
            "entry_locked": bool(a.get("locked")),
        })
    designations = sorted({p.get("designation") for p in await _people(master) if p.get("designation")})
    return {"date": date, "project_code": project_code, "month_locked": locked,
            "designations": designations, "rows": rows}


@router.post("/day-sheet")
async def save_day_sheet(payload: DaySheetIn,
                           user: dict = Depends(require_permission("attendance", "write"))):
    if payload.master not in MASTERS:
        raise HTTPException(400, "master must be 'employee' or 'worker'")
    await _guard_project_access(user, payload.project_code)
    if datetime.fromisoformat(payload.date).date() > datetime.now(timezone.utc).date():
        raise HTTPException(400, "Cannot mark attendance for a future date")
    if await db.hr_attendance_locks.find_one({"month": payload.date[:7], "project_code": payload.project_code, "locked": True}, {"_id": 0, "id": 1}):
        raise HTTPException(400, f"{payload.date[:7]} is locked for {payload.project_code}")
    people = {p["id"]: p for p in await _people(payload.master)}
    from routers.attendance_plus_router import _hhmm, _hours_between, _derive_status, _auto_settings
    auto_cfg = await _auto_settings()
    created = updated = 0
    errors: List[Dict[str, Any]] = []
    for e in payload.entries:
        person = people.get(e.employee_id)
        if not person:
            errors.append({"employee_id": e.employee_id, "error": "Unknown or inactive person"})
            continue
        if e.status not in set(CODE_MAP.values()):
            errors.append({"employee_id": e.employee_id, "error": f"Invalid status '{e.status}'"})
            continue
        base = {
            "status": e.status, "overtime_hours": e.overtime_hours or 0.0,
            "total_hours": 8.0 if e.status in ("present", "on_duty") else (4.0 if e.status == "half_day" else 0.0),
            "hours": 8.0 if e.status in ("present", "on_duty") else (4.0 if e.status == "half_day" else 0.0),
            "project_code": payload.project_code,
            "source": "day_sheet",
            "approval_status": "pending",
            "approved_by_id": None, "approved_by_name": None, "approved_at": None,
            "marked_by_id": user["id"], "marked_by_name": user.get("name") or user.get("email"),
        }
        if e.in_time or e.out_time:
            computed = _hours_between(_hhmm(e.in_time), _hhmm(e.out_time))
            base.update({"in_time": e.in_time or None, "out_time": e.out_time or None,
                         "check_in": e.in_time or None, "check_out": e.out_time or None})
            if e.in_time and e.out_time and e.status in ("present", "half_day"):
                derived = _derive_status(_hhmm(e.in_time), _hhmm(e.out_time), auto_cfg)
                if derived:
                    base["status"] = derived
            if computed > 0:
                base["total_hours"] = computed
                base["hours"] = computed
                if not e.overtime_hours:
                    base["overtime_hours"] = max(0.0, round(computed - 8.0, 2))
        if e.remarks is not None:
            base["remarks"] = e.remarks or None
        existing = await db.attendance.find_one({"employee_id": e.employee_id, "date": payload.date}, {"_id": 0, "id": 1, "locked": 1})
        if existing:
            if existing.get("locked"):
                errors.append({"employee_id": e.employee_id, "error": "Entry locked"})
                continue
            await db.attendance.update_one({"id": existing["id"]}, {"$set": base})
            updated += 1
        else:
            await db.attendance.insert_one({
                "id": new_id(), "employee_id": e.employee_id,
                "employee_name": person.get("name"),
                "employee_code": person.get("employee_id") or person.get("emp_code"),
                "person_type": "worker" if payload.master == "worker" else "employee",
                "date": payload.date, "site_location": None,
                "department": person.get("department"), "designation": person.get("designation"),
                "skill": None, "shift_code": None,
                "in_time": None, "out_time": None, "check_in": None, "check_out": None,
                "remarks": None, "attachment_url": None,
                "locked": False, "lock_id": None,
                "created_at": now_iso(), **base,
            })
            created += 1
    await audit(user=user, action="day_sheet", resource="attendance",
                record_id=f"{payload.project_code}:{payload.date}",
                after={"created": created, "updated": updated, "errors": len(errors)}, ip="attendance-bulk")
    return {"ok": True, "created": created, "updated": updated, "errors": errors}


@router.post("/upload")
async def bulk_upload(month: str, master: str = "employee", project_code: str | None = None,
                        file: UploadFile = File(...),
                        user: dict = Depends(require_permission("attendance", "write"))):
    y, m, ndays = _parse_month(month)
    if master not in MASTERS:
        raise HTTPException(400, "master must be 'employee' or 'worker'")
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(400, "Could not read the file — upload a valid .xlsx")
    ws = wb["ATTENDANCE"] if "ATTENDANCE" in wb.sheetnames else wb.active
    header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    if "id" not in header or "1" not in header:
        raise HTTPException(400, "Wrong template — download the monthly template and fill it")
    col = {h: i for i, h in enumerate(header)}
    people = {p["id"]: p for p in await _people(master)}
    locks = {l.get("project_code") for l in await db.hr_attendance_locks.find(
        {"month": month, "locked": True}, {"_id": 0, "project_code": 1}).to_list(200)}
    today = datetime.now(timezone.utc).date()

    created = updated = skipped_blank = 0
    errors: List[Dict[str, Any]] = []

    for rn, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        pid = str(row[col["id"]] or "").strip()
        person = people.get(pid)
        if not person:
            errors.append({"row": rn, "error": f"Unknown or inactive {master} (id '{pid[:12]}…')"})
            continue
        proj = project_code or person.get("current_project_code")
        for d in range(1, ndays + 1):
            idx = col.get(str(d))
            raw = row[idx] if idx is not None and idx < len(row) else None
            token = str(raw).strip() if raw is not None else ""
            if not token:
                skipped_blank += 1
                continue
            mm = _CELL_RE.match(token)
            code = mm.group(1).upper() if mm else None
            if not mm or code not in CODE_MAP:
                errors.append({"row": rn, "error": f"Day {d}: invalid code '{token}'"})
                continue
            ot = float(mm.group(2)) if mm.group(2) else 0.0
            date = f"{y:04d}-{m:02d}-{d:02d}"
            if datetime.fromisoformat(date).date() > today:
                errors.append({"row": rn, "error": f"Day {d}: future date skipped"})
                continue
            if proj in locks:
                errors.append({"row": rn, "error": f"Day {d}: {month} is LOCKED for project {proj}"})
                continue
            status = CODE_MAP[code]
            existing = await db.attendance.find_one({"employee_id": pid, "date": date}, {"_id": 0, "id": 1, "locked": 1})
            base = {
                "status": status, "overtime_hours": ot,
                "total_hours": 8.0 if status in ("present", "on_duty") else (4.0 if status == "half_day" else 0.0),
                "hours": 8.0 if status in ("present", "on_duty") else (4.0 if status == "half_day" else 0.0),
                "source": "upload",
                "approval_status": "pending",
                "approved_by_id": None, "approved_by_name": None, "approved_at": None,
                "marked_by_id": user["id"], "marked_by_name": user.get("name") or user.get("email"),
            }
            if existing:
                if existing.get("locked"):
                    errors.append({"row": rn, "error": f"Day {d}: entry locked"})
                    continue
                await db.attendance.update_one({"id": existing["id"]}, {"$set": base})
                updated += 1
            else:
                doc = {
                    "id": new_id(),
                    "employee_id": pid,
                    "employee_name": person.get("name"),
                    "employee_code": person.get("employee_id") or person.get("emp_code"),
                    "person_type": "worker" if master == "worker" else "employee",
                    "date": date,
                    "project_code": proj,
                    "site_location": None,
                    "department": person.get("department"),
                    "designation": person.get("designation"),
                    "skill": None, "shift_code": None,
                    "in_time": None, "out_time": None, "check_in": None, "check_out": None,
                    "remarks": None, "attachment_url": None,
                    "locked": False, "lock_id": None,
                    "created_at": now_iso(),
                    **base,
                }
                await db.attendance.insert_one(doc)
                created += 1

    await audit(user=user, action="bulk_upload", resource="attendance", record_id=f"{master}:{month}",
                after={"created": created, "updated": updated, "skipped_blank": skipped_blank,
                        "errors": len(errors)}, ip="attendance-bulk")
    return {"ok": True, "created": created, "updated": updated,
            "skipped_blank": skipped_blank, "errors": errors[:100], "error_count": len(errors)}
