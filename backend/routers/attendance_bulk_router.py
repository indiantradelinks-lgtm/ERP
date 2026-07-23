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
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from core import db, require_permission, now_iso, new_id
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
