"""Attendance Plus — Summary dashboard/exports, row-based bulk update, AI punch-machine import.

Endpoints (prefix /hr2/attendance-plus):
  GET  /summary                       month-wise aggregated summary (employee/date/dept/project/shift)
  GET  /summary/export?fmt=xlsx|csv|pdf
  GET  /bulk-rows/template            row-based Excel template (code/date/shift/status/in/out/ot/remarks)
  POST /bulk-rows/upload              validated row-based Excel import with error report
  POST /punch-import/preview          AI-mapped biometric file preview (xlsx/csv/txt/dat)
  POST /punch-import/{bid}/commit     write attendance (overwrite duplicates by default)
  POST /punch-import/{bid}/rollback   undo a committed batch
  GET  /punch-imports                 import history
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta, time as dtime
from typing import Any, Dict, List, Optional

from fastapi import Request, APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openpyxl import Workbook, load_workbook

from core import db, require_permission, get_current_user, now_iso, new_id
from pagination import maybe_paged, paged_or_rows
from audit import audit
from hr_worker_rules import worker_key_set, is_worker_row

logger = logging.getLogger("erp.attendance_plus")
router = APIRouter(prefix="/hr2/attendance-plus", tags=["attendance-plus"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

STATUS_CODES = {"present": "P", "absent": "A", "half_day": "HD", "leave": "L",
                "weekly_off": "WO", "holiday": "H", "on_duty": "OD"}
CODE_TO_STATUS = {v: k for k, v in STATUS_CODES.items()}
HR_ROLES = {"super_admin", "hr_executive", "general_manager", "director"}


def _hhmm(s) -> Optional[dtime]:
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"^(\d{1,2})[:.](\d{2})", s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return dtime(h, mi)


def _hours_between(t_in: Optional[dtime], t_out: Optional[dtime], break_min: float = 0.0) -> float:
    if not t_in or not t_out:
        return 0.0
    d = datetime(2000, 1, 1, t_in.hour, t_in.minute)
    o = datetime(2000, 1, 1, t_out.hour, t_out.minute)
    if o <= d:
        o += timedelta(days=1)
    return max(0.0, round((o - d).total_seconds() / 3600.0 - break_min / 60.0, 2))


async def _shift_map() -> Dict[str, dict]:
    rows = await db.hr_shifts.find({}, {"_id": 0, "code": 1, "start_time": 1, "end_time": 1,
                                        "break_minutes": 1, "standard_hours": 1, "overtime_after": 1}).to_list(200)
    return {r["code"]: r for r in rows}


def _late_early(row: dict, shifts: Dict[str, dict]) -> tuple:
    """(late_minutes, early_minutes) vs the row's shift (default GEN / 09:00-18:00)."""
    sh = shifts.get(row.get("shift_code") or "GEN") or {"start_time": "09:00", "end_time": "18:00"}
    st, et = _hhmm(sh.get("start_time")), _hhmm(sh.get("end_time"))
    ti, to = _hhmm(row.get("in_time")), _hhmm(row.get("out_time"))
    late = early = 0
    if st and ti:
        late = max(0, (ti.hour * 60 + ti.minute) - (st.hour * 60 + st.minute))
    if et and to and to > (st or dtime(0, 0)):
        early = max(0, (et.hour * 60 + et.minute) - (to.hour * 60 + to.minute))
    return late, early


# ──────────────────────────── SUMMARY ────────────────────────────
async def _summary_data(month: str, project_code: Optional[str], department: Optional[str],
                        shift_code: Optional[str], q: Optional[str], employee_id: Optional[str],
                        user: dict) -> dict:
    try:
        datetime.strptime(month, "%Y-%m")
    except Exception:
        raise HTTPException(400, "month must be YYYY-MM")
    from scope import apply_project_scope
    match: Dict[str, Any] = {"date": {"$regex": f"^{month}-"}}
    if project_code:
        if project_code == "HEAD-OFFICE":
            match["project_code"] = {"$in": [None, "", "HEAD-OFFICE"]}
        else:
            match["project_code"] = project_code
    if department:
        match["department"] = department
    if shift_code:
        match["shift_code"] = shift_code
    if employee_id:
        match["employee_id"] = employee_id
    match = await apply_project_scope(user, match, id_field="project_id", code_field="project_code")
    rows = await db.attendance.find(match, {"_id": 0}).to_list(20000)
    inactive_ids = set()
    all_ids = list({r.get("employee_id") for r in rows if r.get("employee_id")})
    if all_ids:
        async for e in db.employees.find({"id": {"$in": all_ids}, "status": "inactive"}, {"_id": 0, "id": 1}):
            inactive_ids.add(e["id"])
    rows = [r for r in rows if r.get("employee_id") not in inactive_ids]
    if q:
        s = q.lower()
        rows = [r for r in rows if s in (r.get("employee_name") or "").lower()
                or s in (r.get("employee_code") or "").lower()]

    shifts = await _shift_map()
    year = int(month[:4])
    emp_ids = list({r.get("employee_id") for r in rows if r.get("employee_id")})
    lb: Dict[str, float] = {}
    async for b in db.leave_balances.find({"employee_id": {"$in": emp_ids}, "year": year},
                                          {"_id": 0, "employee_id": 1, "balance": 1}):
        lb[b["employee_id"]] = lb.get(b["employee_id"], 0) + float(b.get("balance") or 0)

    def _blank():
        return {"P": 0, "A": 0, "HD": 0, "L": 0, "WO": 0, "H": 0, "OD": 0,
                "late_count": 0, "early_count": 0, "ot_hours": 0.0, "total_hours": 0.0, "days": 0}

    emps: Dict[str, dict] = {}
    by_date: Dict[str, dict] = {}
    by_dept: Dict[str, dict] = {}
    by_proj: Dict[str, dict] = {}
    by_shift: Dict[str, dict] = {}

    def bump(bucket: dict, key: str, code: str, r: dict, late: int, early: int):
        b = bucket.setdefault(key, _blank())
        b[code] = b.get(code, 0) + 1
        b["days"] += 1
        b["ot_hours"] = round(b["ot_hours"] + float(r.get("overtime_hours") or 0), 2)
        b["total_hours"] = round(b["total_hours"] + float(r.get("total_hours") or r.get("hours") or 0), 2)
        if late > 0:
            b["late_count"] += 1
        if early > 0:
            b["early_count"] += 1

    for r in rows:
        code = STATUS_CODES.get(r.get("status") or "", None)
        if not code:
            continue
        late, early = _late_early(r, shifts) if r.get("in_time") or r.get("out_time") else (0, 0)
        eid = r.get("employee_id") or "?"
        e = emps.setdefault(eid, {**_blank(), "employee_id": eid,
                                  "employee_code": r.get("employee_code") or r.get("emp_code") or "",
                                  "employee_name": r.get("employee_name") or "",
                                  "department": r.get("department") or "",
                                  "projects": set(), "shifts": set()})
        e[code] += 1
        e["days"] += 1
        e["ot_hours"] = round(e["ot_hours"] + float(r.get("overtime_hours") or 0), 2)
        e["total_hours"] = round(e["total_hours"] + float(r.get("total_hours") or r.get("hours") or 0), 2)
        if late > 0:
            e["late_count"] += 1
        if early > 0:
            e["early_count"] += 1
        if r.get("project_code"):
            e["projects"].add(r["project_code"])
        if r.get("shift_code"):
            e["shifts"].add(r["shift_code"])
        bump(by_date, r.get("date") or "?", code, r, late, early)
        bump(by_dept, r.get("department") or "—", code, r, late, early)
        bump(by_proj, r.get("project_code") or "HEAD-OFFICE", code, r, late, early)
        bump(by_shift, r.get("shift_code") or "—", code, r, late, early)

    emp_rows = []
    worker_keys = await worker_key_set()
    for eid, e in emps.items():
        present_days = e["P"] + e["OD"] + 0.5 * e["HD"]
        # Worker / Labour Master: weekly off is NOT a paid day (staff unchanged)
        is_worker = is_worker_row({"id": eid, "emp_code": e.get("employee_code"),
                                   "employee_id": e.get("employee_code")}, worker_keys)
        paid_days = round(e["P"] + 0.5 * e["HD"] + e["L"] + e["H"] + e["OD"]
                          + (0 if is_worker else e["WO"]), 1)
        emp_rows.append({
            **{k: v for k, v in e.items() if k not in ("projects", "shifts")},
            "projects": sorted(e["projects"]), "shift_codes": sorted(e["shifts"]),
            "is_worker_master": is_worker, "week_off_paid": not is_worker,
            "working_days": e["days"], "paid_days": paid_days,
            "present_days": round(present_days, 1),
            "leave_balance": round(lb.get(eid, 0), 1),
        })
    emp_rows.sort(key=lambda x: x["employee_name"])

    def flat(bucket: dict, key_name: str):
        return [{key_name: k, **v} for k, v in sorted(bucket.items())]

    totals = _blank()
    for e in emp_rows:
        for k in ("P", "A", "HD", "L", "WO", "H", "OD", "late_count", "early_count", "days"):
            totals[k] += e[k]
        totals["ot_hours"] = round(totals["ot_hours"] + e["ot_hours"], 2)
        totals["total_hours"] = round(totals["total_hours"] + e["total_hours"], 2)
    totals["employees"] = len(emp_rows)
    totals["present_days"] = round(sum(e["present_days"] for e in emp_rows), 1)
    totals["paid_days"] = round(sum(e["paid_days"] for e in emp_rows), 1)

    return {"month": month, "totals": totals, "employees": emp_rows,
            "by_date": flat(by_date, "date"), "by_department": flat(by_dept, "department"),
            "by_project": flat(by_proj, "project_code"), "by_shift": flat(by_shift, "shift_code")}


@router.get("/summary")
async def attendance_summary(month: str = Query(...), project_code: Optional[str] = None,
                             department: Optional[str] = None, shift_code: Optional[str] = None,
                             q: Optional[str] = None, employee_id: Optional[str] = None,
                             user: dict = Depends(require_permission("attendance", "read"))):
    return await _summary_data(month, project_code, department, shift_code, q, employee_id, user)


_EXPORT_HEADERS = ["Code", "Name", "Department", "Projects", "P", "A", "HD", "L", "WO", "H", "OD",
                   "Late", "Early Exit", "Paid Days", "Present Days", "OT Hours", "Total Hours", "Leave Balance"]


def _export_rows(data: dict) -> List[list]:
    out = []
    for e in data["employees"]:
        out.append([e["employee_code"], e["employee_name"], e["department"], ", ".join(e["projects"]),
                    e["P"], e["A"], e["HD"], e["L"], e["WO"], e["H"], e["OD"],
                    e["late_count"], e["early_count"], e["paid_days"], e["present_days"],
                    e["ot_hours"], e["total_hours"], e["leave_balance"]])
    return out


@router.get("/summary/export")
async def export_summary(fmt: str = Query(..., pattern="^(xlsx|csv|pdf)$"), month: str = Query(...),
                         project_code: Optional[str] = None, department: Optional[str] = None,
                         shift_code: Optional[str] = None, q: Optional[str] = None,
                         user: dict = Depends(require_permission("attendance", "read"))):
    data = await _summary_data(month, project_code, department, shift_code, q, None, user)
    rows = _export_rows(data)
    fname = f"attendance_summary_{month}"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(_EXPORT_HEADERS)
        w.writerows(rows)
        return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8-sig")), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'})
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "SUMMARY"
        ws.append([f"INDIAN TRADE LINKS — Attendance Summary — {month}"])
        ws.append(_EXPORT_HEADERS)
        for r in rows:
            ws.append(r)
        t = data["totals"]
        ws.append([])
        ws.append(["TOTALS", f"{t['employees']} employees", "", "", t["P"], t["A"], t["HD"], t["L"],
                   t["WO"], t["H"], t["OD"], t["late_count"], t["early_count"], t.get("paid_days", 0),
                   t["present_days"], t["ot_hours"], t["total_hours"], ""])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})
    # pdf
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"INDIAN TRADE LINKS — Attendance Summary — {month}", styles["Title"]), Spacer(1, 4)]
    table_data = [_EXPORT_HEADERS] + [[str(c) for c in r] for r in rows]
    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    story.append(tbl)
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})


@router.get("/summary/breakdown/export")
async def export_breakdown(fmt: str = Query(..., pattern="^(xlsx|pdf)$"), month: str = Query(...),
                           project_code: Optional[str] = None, department: Optional[str] = None,
                           shift_code: Optional[str] = None, q: Optional[str] = None,
                           user: dict = Depends(require_permission("attendance", "read"))):
    """Employee-wise date-wise attendance matrix (rows: employees, cols: each day of month)."""
    data = await _summary_data(month, project_code, department, shift_code, q, None, user)
    from calendar import monthrange
    year, mon = map(int, month.split("-"))
    ndays = monthrange(year, mon)[1]
    # rebuild per-cell codes from raw rows (need employee×date)
    from scope import apply_project_scope
    match: Dict[str, Any] = {"date": {"$regex": f"^{month}-"}}
    if project_code:
        match["project_code"] = {"$in": [None, "", "HEAD-OFFICE"]} if project_code == "HEAD-OFFICE" else project_code
    if department:
        match["department"] = department
    if shift_code:
        match["shift_code"] = shift_code
    match = await apply_project_scope(user, match, id_field="project_id", code_field="project_code")
    raw = await db.attendance.find(match, {"_id": 0, "employee_id": 1, "date": 1, "status": 1,
                                           "in_time": 1, "out_time": 1, "total_hours": 1,
                                           "overtime_hours": 1, "remarks": 1}).to_list(20000)
    cell = {(r["employee_id"], r["date"]): STATUS_CODES.get(r.get("status") or "", "") for r in raw}
    by_emp_date = {(r["employee_id"], r["date"]): r for r in raw}
    day_headers = [f"{d:02d}" for d in range(1, ndays + 1)]
    headers = ["Code", "Name", "Dept"] + day_headers + ["P", "A", "HD", "L", "WO", "H", "OD", "OT Hrs"]
    body = []
    detail_headers = ["Code", "Name", "Dept", "Date", "Status", "In Time", "Out Time", "Working Hrs", "OT Hrs"]
    detail = []
    for e in data["employees"]:
        row = [e["employee_code"], e["employee_name"], e["department"]]
        row += [cell.get((e["employee_id"], f"{month}-{d:02d}"), "") for d in range(1, ndays + 1)]
        row += [e["P"], e["A"], e["HD"], e["L"], e["WO"], e["H"], e["OD"], e["ot_hours"]]
        body.append(row)
        for d in range(1, ndays + 1):
            r = by_emp_date.get((e["employee_id"], f"{month}-{d:02d}"))
            if not r:
                continue
            detail.append([e["employee_code"], e["employee_name"], e["department"], r["date"],
                           STATUS_CODES.get(r.get("status") or "", ""), r.get("in_time") or "—",
                           r.get("out_time") or "—", r.get("total_hours") or 0, r.get("overtime_hours") or 0])
    fname = f"attendance_breakdown_{month}"
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "DATE-WISE DETAIL"
        ws.append([f"INDIAN TRADE LINKS — Employee Date-wise Attendance — {month}"])
        ws.append(detail_headers)
        for r in detail:
            ws.append(r)
        ws2 = wb.create_sheet("MONTH MATRIX")
        ws2.append([f"INDIAN TRADE LINKS — Employee × Date Attendance Matrix — {month}"])
        ws2.append(headers)
        for r in body:
            ws2.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=6 * mm, rightMargin=6 * mm,
                            topMargin=8 * mm, bottomMargin=8 * mm)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"INDIAN TRADE LINKS — Employee Date-wise Attendance — {month}", styles["Title"]), Spacer(1, 3)]
    detail_data = [detail_headers] + [[str(c) for c in r] for r in detail]
    dt = Table(detail_data, repeatRows=1,
               colWidths=[22 * mm, 48 * mm, 30 * mm, 24 * mm, 16 * mm, 20 * mm, 20 * mm, 24 * mm, 20 * mm])
    dt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (4, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    story.append(dt)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Month Matrix — {month}", styles["Heading2"]))
    table_data = [headers] + [[str(c) for c in r] for r in body]
    name_w = 34 * mm
    day_w = (282 * mm - 18 * mm - name_w - 16 * mm - 8 * 7 * mm) / ndays
    widths = [18 * mm, name_w, 16 * mm] + [day_w] * ndays + [7 * mm] * 8
    tbl = Table(table_data, repeatRows=1, colWidths=widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 4.6),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (3, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    story.append(tbl)
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{fname}.pdf"'})


# ──────────────────────────── PERSONAL (SELF-ONLY) ATTENDANCE ────────────────────────────
@router.get("/my/monthly")
async def my_monthly_attendance(month: str = Query(...), user: dict = Depends(get_current_user)):
    """Personal attendance dashboard — strictly scoped to the logged-in user's own records. View-only."""
    try:
        datetime.strptime(month + "-01", "%Y-%m-%d")
    except Exception:
        raise HTTPException(400, "month must be YYYY-MM")
    ors = []
    if user.get("id"):
        ors.append({"user_id": user["id"]})
    if user.get("email"):
        ors.append({"email": {"$regex": f"^{re.escape(user['email'])}$", "$options": "i"}})
    emp = await db.employees.find_one(
        {"$or": ors}, {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "emp_code": 1,
                       "master_category": 1, "is_worker": 1, "employee_category": 1,
                       "department": 1, "designation": 1, "current_project_code": 1}) if ors else None
    if not emp:
        return {"linked": False, "month": month, "employee": None, "rows": [], "summary": None}
    rows = await db.attendance.find(
        {"employee_id": emp["id"], "date": {"$gte": f"{month}-01", "$lte": f"{month}-31"}},
        {"_id": 0, "date": 1, "status": 1, "in_time": 1, "out_time": 1,
         "total_hours": 1, "overtime_hours": 1, "remarks": 1, "approval_status": 1}).sort("date", 1).to_list(62)
    counts = {c: 0 for c in STATUS_CODES.values()}
    ot = th = 0.0
    for r in rows:
        code = STATUS_CODES.get(r.get("status") or "")
        r["code"] = code
        if code:
            counts[code] += 1
        ot += float(r.get("overtime_hours") or 0)
        th += float(r.get("total_hours") or 0)
    is_worker = is_worker_row(emp, await worker_key_set())
    paid = (counts["P"] + counts["L"] + counts["H"] + counts["OD"] + 0.5 * counts["HD"]
            + (0 if is_worker else counts["WO"]))
    return {"linked": True, "month": month,
            "employee": {"name": emp.get("name"), "code": emp.get("employee_id") or emp.get("emp_code"),
                         "department": emp.get("department"), "designation": emp.get("designation"),
                         "project_code": emp.get("current_project_code"),
                         "is_worker_master": is_worker, "week_off_paid": not is_worker},
            "rows": rows,
            "summary": {**counts, "paid_days": round(paid, 1), "ot_hours": round(ot, 1),
                        "total_hours": round(th, 1), "marked_days": len(rows)}}


# ──────────────────────────── AUTO ATTENDANCE (WO / P-HD / Absent) ────────────────────────────
WEEKDAY_IDX = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
               "friday": 4, "saturday": 5, "sunday": 6}
DEFAULT_AUTO_SETTINGS = {"full_in_by": "09:10", "full_out_after": "17:00", "mid_time": "13:00"}


async def _auto_settings() -> dict:
    doc = await db.hr_attendance_settings.find_one({"id": "auto"}, {"_id": 0}) or {}
    return {"full_in_by": doc.get("full_in_by") or "09:10",
            "full_out_after": doc.get("full_out_after") or "17:00",
            "mid_time": doc.get("mid_time") or "13:00"}


def _derive_status(t_in: Optional[dtime], t_out: Optional[dtime], settings: dict) -> Optional[str]:
    """Time-window rule — P: in ≤ full_in_by AND out ≥ full_out_after.
    HD: covers either half (in ≤ full_in_by & out ≥ mid, or in ≤ mid & out ≥ full_out_after). Else absent."""
    if not t_in or not t_out:
        return None
    fi = _hhmm(settings.get("full_in_by")) or dtime(9, 10)
    fo = _hhmm(settings.get("full_out_after")) or dtime(17, 0)
    mid = _hhmm(settings.get("mid_time")) or dtime(13, 0)
    if t_in <= fi and t_out >= fo:
        return "present"
    if (t_in <= fi and t_out >= mid) or (t_in <= mid and t_out >= fo):
        return "half_day"
    return "absent"


@router.get("/auto-settings")
async def get_auto_settings(user: dict = Depends(require_permission("attendance", "read"))):
    return await _auto_settings()


class AutoSettingsIn(BaseModel):
    full_in_by: str = "09:10"
    full_out_after: str = "17:00"
    mid_time: str = "13:00"


@router.put("/auto-settings")
async def put_auto_settings(p: AutoSettingsIn,
                            user: dict = Depends(require_permission("attendance", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Only HR / Admin can change attendance settings")
    fi, fo, mid = _hhmm(p.full_in_by), _hhmm(p.full_out_after), _hhmm(p.mid_time)
    if not (fi and fo and mid) or not (fi < mid < fo):
        raise HTTPException(400, "Invalid time windows — need full-in < mid < full-out (HH:MM)")
    await db.hr_attendance_settings.update_one(
        {"id": "auto"}, {"$set": {"full_in_by": p.full_in_by, "full_out_after": p.full_out_after,
                                  "mid_time": p.mid_time,
                                  "updated_by": user.get("name"), "updated_at": now_iso()}}, upsert=True)
    return await _auto_settings()


class AutoRunIn(BaseModel):
    month: str
    project_code: Optional[str] = None
    do_weekly_off: bool = True
    do_absent: bool = True


def _auto_row(e: dict, date: str, status: str, source: str, user: dict) -> dict:
    return {
        "id": new_id(), "employee_id": e["id"], "employee_name": e.get("name"),
        "employee_code": e.get("employee_id") or e.get("emp_code"),
        "person_type": "employee", "date": date, "status": status,
        "in_time": None, "out_time": None, "check_in": None, "check_out": None,
        "total_hours": 0.0, "hours": 0.0, "overtime_hours": 0.0,
        "late_minutes": 0, "early_exit_minutes": 0,
        "project_code": e.get("current_project_code"),
        "department": e.get("department"), "designation": e.get("designation"),
        "site_location": None, "skill": None, "attachment_url": None, "shift_code": None,
        "remarks": "Auto-marked", "source": source, "approval_status": "pending",
        "approved_by_id": None, "approved_by_name": None, "approved_at": None,
        "marked_by_id": user["id"], "marked_by_name": "Auto Attendance",
        "locked": False, "lock_id": None, "created_at": now_iso(),
    }


@router.post("/auto/run")
async def auto_run(p: AutoRunIn, user: dict = Depends(require_permission("attendance", "write"))):
    """Generate WO from each employee's weekly_off + auto-Absent for empty past working days."""
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Only HR / Admin can run auto attendance")
    try:
        year, mon = map(int, p.month.split("-"))
        datetime(year, mon, 1)
    except Exception:
        raise HTTPException(400, "month must be YYYY-MM")
    from calendar import monthrange
    ndays = monthrange(year, mon)[1]
    today = datetime.now(timezone.utc).date().isoformat()
    q: Dict[str, Any] = {"status": {"$ne": "inactive"}}
    if p.project_code and p.project_code != "ALL":
        q["current_project_code"] = None if p.project_code == "HEAD-OFFICE" else p.project_code
        if p.project_code == "HEAD-OFFICE":
            q["current_project_code"] = {"$in": [None, "", "HEAD-OFFICE"]}
    emps = await db.employees.find(q, {"_id": 0, "id": 1, "employee_id": 1, "emp_code": 1, "name": 1,
                                       "department": 1, "designation": 1, "current_project_code": 1,
                                       "weekly_off": 1}).to_list(10000)
    ids = [e["id"] for e in emps]
    existing = set()
    async for r in db.attendance.find({"employee_id": {"$in": ids}, "date": {"$regex": f"^{p.month}-"}},
                                      {"_id": 0, "employee_id": 1, "date": 1}):
        existing.add((r["employee_id"], r["date"]))
    inserts: List[dict] = []
    wo_created = absent_created = 0
    for e in emps:
        wo_idx = WEEKDAY_IDX.get(str(e.get("weekly_off") or "sunday").strip().lower(), 6)
        for d in range(1, ndays + 1):
            date = f"{p.month}-{d:02d}"
            if (e["id"], date) in existing:
                continue
            wd = datetime(year, mon, d).weekday()
            if wd == wo_idx:
                if p.do_weekly_off:
                    inserts.append(_auto_row(e, date, "weekly_off", "auto_wo", user))
                    wo_created += 1
            elif p.do_absent and date < today:
                inserts.append(_auto_row(e, date, "absent", "auto_absent", user))
                absent_created += 1
    if inserts:
        await db.attendance.insert_many(inserts)
    await audit(user=user, action="auto_attendance_run", resource="attendance", record_id=p.month,
                after={"weekly_off_created": wo_created, "absent_created": absent_created,
                       "employees": len(emps), "project": p.project_code}, ip="attendance-plus")
    return {"ok": True, "weekly_off_created": wo_created, "absent_created": absent_created,
            "employees_scanned": len(emps), "skipped_existing": len(existing)}


# ──────────────────────────── ROW-BASED BULK UPDATE ────────────────────────────
_ROW_HEADERS = ["Employee Code", "Employee Name", "Date (YYYY-MM-DD)", "Shift",
                "Status (P/A/HD/L/WO/OD/H)", "In Time (HH:MM)", "Out Time (HH:MM)",
                "Overtime Hours", "Remarks"]


@router.get("/bulk-rows/template")
async def bulk_rows_template(user: dict = Depends(require_permission("attendance", "read"))):
    wb = Workbook()
    ws = wb.active
    ws.title = "ATTENDANCE_ROWS"
    ws.append(_ROW_HEADERS)
    ws.append(["EMP-0001", "Sample Name", datetime.now(timezone.utc).date().isoformat(), "GEN", "P", "09:00", "18:30", "0.5", "Optional note"])
    inst = wb.create_sheet("INSTRUCTIONS")
    for line in ["Row-based Attendance Bulk Update", "",
                 "• One row per employee per date.",
                 "• Status codes: P, A, HD, L, WO, OD, H.",
                 "• In/Out Time optional (HH:MM 24h). Working hours & OT auto-calculated from shift when provided.",
                 "• Existing entries for the same employee+date are UPDATED.",
                 "• Invalid rows are reported back — nothing partial is silently skipped."]:
        inst.append([line])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="attendance_bulk_rows_template.xlsx"'})


def _norm_code(v) -> str:
    s = str(v if v is not None else "").strip().upper()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return re.sub(r"\s+", "", s)


def _norm_name(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip().upper())


async def _employee_lookup() -> Dict[str, dict]:
    """Keys: LEGACY::<emp_code> (punch-machine ID), ID::<employee_id>, NAME::<name>.
    Active employees win when two records share a key."""
    out: Dict[str, dict] = {}

    def put(key: str, p: dict):
        cur = out.get(key)
        if cur is None or (cur.get("status") not in ("active", None) and p.get("status") == "active"):
            out[key] = p

    async for p in db.employees.find({}, {"_id": 0, "id": 1, "employee_id": 1, "emp_code": 1, "name": 1,
                                          "status": 1, "department": 1, "designation": 1, "current_project_code": 1}):
        if p.get("emp_code"):
            put("LEGACY::" + _norm_code(p["emp_code"]), p)
        if p.get("employee_id"):
            put("ID::" + _norm_code(p["employee_id"]), p)
        if p.get("name"):
            put("NAME::" + _norm_name(p["name"]), p)
    return out


def _match_employee(lookup: Dict[str, dict], code: str, name: str) -> tuple:
    """Legacy Emp Code (punch-machine ID) first, then Employee ID, then exact name."""
    c = _norm_code(code)
    if c:
        if "LEGACY::" + c in lookup:
            return lookup["LEGACY::" + c], "legacy_emp_code"
        if "ID::" + c in lookup:
            return lookup["ID::" + c], "employee_id"
    n = _norm_name(name)
    if n and "NAME::" + n in lookup:
        return lookup["NAME::" + n], "name"
    return None, None


async def _write_attendance(person: dict, date: str, status: str, in_time: Optional[str],
                            out_time: Optional[str], ot: Optional[float], remarks: Optional[str],
                            shift_code: Optional[str], source: str, user: dict,
                            shifts: Dict[str, dict], overwrite: bool = True,
                            settings: Optional[dict] = None) -> tuple:
    """Upsert one attendance row. Returns (action, attendance_id, prev_doc|None)."""
    sh = shifts.get(shift_code or "GEN") or {}
    ti, to = _hhmm(in_time), _hhmm(out_time)
    total = _hours_between(ti, to, float(sh.get("break_minutes") or 0))
    if ti and to and status in (None, "", "present", "half_day"):
        derived = _derive_status(ti, to, settings or DEFAULT_AUTO_SETTINGS)
        if derived:
            status = derived
    if status == "absent":
        total = 0.0
    if total == 0.0:
        total = 8.0 if status in ("present", "on_duty") else (4.0 if status == "half_day" else 0.0)
    ot_after = float(sh.get("overtime_after") or sh.get("standard_hours") or 8.0)
    ot_val = ot if ot is not None else max(0.0, round(total - ot_after, 2))
    late, early = _late_early({"shift_code": shift_code, "in_time": in_time, "out_time": out_time}, shifts)
    base = {
        "status": status, "in_time": in_time or None, "out_time": out_time or None,
        "check_in": in_time or None, "check_out": out_time or None,
        "total_hours": total, "hours": total, "overtime_hours": ot_val,
        "late_minutes": late, "early_exit_minutes": early,
        "shift_code": shift_code or None, "remarks": remarks or None,
        "source": source, "approval_status": "pending",
        "approved_by_id": None, "approved_by_name": None, "approved_at": None,
        "marked_by_id": user["id"], "marked_by_name": user.get("name") or user.get("email"),
    }
    existing = await db.attendance.find_one({"employee_id": person["id"], "date": date}, {"_id": 0})
    if existing and existing.get("status_manual"):
        # Manually set statuses are never overwritten by auto derivation (uploads / punch imports)
        base["status"] = existing.get("status") or base["status"]
        base["status_manual"] = True
        if base["status"] == "absent":
            base["total_hours"] = base["hours"] = 0.0
    if existing:
        if existing.get("locked"):
            raise ValueError("Entry locked")
        if not overwrite:
            return "skipped", existing["id"], None
        await db.attendance.update_one({"id": existing["id"]}, {"$set": base})
        return "updated", existing["id"], existing
    doc = {
        "id": new_id(), "employee_id": person["id"], "employee_name": person.get("name"),
        "employee_code": person.get("employee_id") or person.get("emp_code"),
        "person_type": "employee", "date": date,
        "project_code": person.get("current_project_code"),
        "department": person.get("department"), "designation": person.get("designation"),
        "site_location": None, "skill": None, "attachment_url": None,
        "locked": False, "lock_id": None, "created_at": now_iso(), **base,
    }
    await db.attendance.insert_one(doc)
    return "created", doc["id"], None


@router.post("/bulk-rows/upload")
async def bulk_rows_upload(file: UploadFile = File(...),
                           user: dict = Depends(require_permission("attendance", "write"))):
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(400, "Could not read the file — upload a valid .xlsx")
    ws = wb["ATTENDANCE_ROWS"] if "ATTENDANCE_ROWS" in wb.sheetnames else wb.active
    lookup = await _employee_lookup()
    shifts = await _shift_map()
    settings = await _auto_settings()
    today = datetime.now(timezone.utc).date()
    created = updated = 0
    errors: List[dict] = []
    for rn, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        vals = list(row) + [None] * 9
        code, name, date_v, shift, status_raw, tin, tout, ot_raw, remarks = vals[:9]
        person, _ = _match_employee(lookup, str(code or ""), str(name or ""))
        if not person:
            errors.append({"row": rn, "error": f"Unknown employee '{code or name}'"})
            continue
        if isinstance(date_v, datetime):
            date = date_v.date().isoformat()
        else:
            date = str(date_v or "").strip()[:10]
        try:
            d = datetime.fromisoformat(date).date()
        except Exception:
            errors.append({"row": rn, "error": f"Invalid date '{date_v}'"})
            continue
        if d > today:
            errors.append({"row": rn, "error": f"Future date {date} skipped"})
            continue
        sc = str(status_raw or "").strip().upper()
        status = CODE_TO_STATUS.get(sc)
        if not status:
            errors.append({"row": rn, "error": f"Invalid status '{status_raw}' (use P/A/HD/L/WO/OD/H)"})
            continue
        tin_s = str(tin).strip()[:5] if tin not in (None, "") else None
        tout_s = str(tout).strip()[:5] if tout not in (None, "") else None
        if isinstance(tin, datetime):
            tin_s = tin.strftime("%H:%M")
        if isinstance(tout, datetime):
            tout_s = tout.strftime("%H:%M")
        if isinstance(tin, dtime):
            tin_s = tin.strftime("%H:%M")
        if isinstance(tout, dtime):
            tout_s = tout.strftime("%H:%M")
        try:
            ot = float(ot_raw) if ot_raw not in (None, "") else None
        except Exception:
            errors.append({"row": rn, "error": f"Invalid OT '{ot_raw}'"})
            continue
        if await db.hr_attendance_locks.find_one({"month": date[:7], "locked": True,
                                                  "project_code": person.get("current_project_code") or "HEAD-OFFICE"},
                                                 {"_id": 0, "id": 1}):
            errors.append({"row": rn, "error": f"{date[:7]} locked for {person.get('current_project_code')}"})
            continue
        try:
            action, _, _ = await _write_attendance(person, date, status, tin_s, tout_s, ot,
                                                   str(remarks or "").strip() or None,
                                                   str(shift or "").strip() or None,
                                                   "upload", user, shifts, settings=settings)
        except ValueError as ve:
            errors.append({"row": rn, "error": str(ve)})
            continue
        if action == "created":
            created += 1
        else:
            updated += 1
    await audit(user=user, action="bulk_rows_upload", resource="attendance", record_id=file.filename,
                after={"created": created, "updated": updated, "errors": len(errors)}, ip="attendance-plus")
    return {"ok": True, "created": created, "updated": updated,
            "errors": errors[:200], "error_count": len(errors)}


# ──────────────────────────── AI PUNCH-MACHINE IMPORT ────────────────────────────
PUNCH_MAP_SYSTEM = (
    "You are a biometric attendance file analyst. You will receive raw sample lines from a punch "
    "machine / biometric device export (could be CSV, TXT, DAT, tab/space/pipe delimited, or an Excel "
    "sheet rendered as CSV). Identify the structure and return a SINGLE JSON object only — no prose:\n"
    "{\n"
    '  "delimiter": str,              // e.g. ",", "\\t", "|", " " (whitespace) — best guess\n'
    '  "has_header": bool,\n'
    '  "employee_code_col": int|null, // 0-based column index of employee code/ID\n'
    '  "employee_name_col": int|null,\n'
    '  "date_col": int|null,          // column containing the date (may be combined with time)\n'
    '  "time_col": int|null,          // column containing punch time (null if combined with date)\n'
    '  "datetime_combined": bool,     // true when one column holds both date and time\n'
    '  "in_col": int|null,            // when the file has explicit IN and OUT columns per row\n'
    '  "out_col": int|null,\n'
    '  "direction_col": int|null,     // column indicating IN/OUT direction token, if any\n'
    '  "in_tokens": [str],            // tokens meaning check-in, e.g. ["IN","0","I","C/In"]\n'
    '  "date_format": str,            // python strptime, e.g. "%d/%m/%Y" or "%Y-%m-%d %H:%M:%S"\n'
    '  "time_format": str|null,       // strptime for the time column when separate\n'
    '  "notes": str\n'
    "}"
)


def _file_to_lines(filename: str, content: bytes) -> List[str]:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext in (".xlsx", ".xls"):
        try:
            wb = load_workbook(io.BytesIO(content), data_only=True)
        except Exception:
            raise HTTPException(400, "Could not read the Excel file")
        ws = wb.active
        lines = []
        for row in ws.iter_rows(values_only=True):
            if row is None:
                continue
            cells = ["" if v is None else (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else str(v)) for v in row]
            if any(c.strip() for c in cells):
                lines.append(",".join(cells))
        return lines
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        raise HTTPException(400, "Could not decode the file")
    return [ln for ln in text.splitlines() if ln.strip()]


async def _ai_map(lines: List[str]) -> dict:
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "EMERGENT_LLM_KEY not configured")
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    sample = "\n".join(lines[:40])
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"punch-map-{new_id()}",
                   system_message=PUNCH_MAP_SYSTEM).with_model("gemini", "gemini-2.5-flash")
    try:
        resp = await chat.send_message(UserMessage(text=f"Sample lines from the punch machine file:\n\n{sample}\n\nReturn the JSON mapping only."))
    except Exception as e:
        logger.exception("AI mapping failed")
        raise HTTPException(502, f"AI format detection failed: {e}")
    s = (resp or "").strip()
    if s.startswith("```"):
        s = "\n".join(ln for ln in s.splitlines() if not ln.startswith("```"))
    try:
        start, end = s.find("{"), s.rfind("}")
        return json.loads(s[start:end + 1])
    except Exception:
        raise HTTPException(502, f"AI returned unparseable mapping (snippet: {s[:150]})")


def _split_line(line: str, delim: str) -> List[str]:
    if delim in (" ", "whitespace", "\\s"):
        return re.split(r"\s+", line.strip())
    if delim == "\\t":
        delim = "\t"
    return [c.strip() for c in line.split(delim)]


def _parse_dt(value: str, fmt: Optional[str]):
    value = (value or "").strip()
    fmts = [fmt] if fmt else []
    fmts += ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
             "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
             "%m/%d/%Y %H:%M", "%H:%M:%S", "%H:%M"]
    for f in fmts:
        if not f:
            continue
        try:
            return datetime.strptime(value, f)
        except Exception:
            continue
    return None


def _hhmm_or_none(v) -> Optional[str]:
    s = str(v or "").strip()
    return s[:5] if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", s) else None


_MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def _parse_block_report(content: bytes) -> Optional[dict]:
    """Deterministic parser for per-employee 'block' biometric reports (e.g. MyOfficeGuardian):
    a header line with the report range, then per employee: <name> / 'Emp_code:' <id> / day rows
    '(Tue) 01' Shift In Out Late Early Hours OT Status. Returns None if the sheet isn't this format."""
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return None
    rows = [list(r) for r in wb.active.iter_rows(values_only=True) if r]
    if not any(str(r[0] or "").strip().lower().startswith("emp_code") for r in rows if r):
        return None
    year = month = None
    for r in rows[:15]:
        m = re.search(r"(\d{1,2})[/-]([A-Za-z]{3})[/-](\d{4})", " ".join(str(c) for c in r if c is not None))
        if m:
            month, year = _MONTHS.get(m.group(2).upper()), int(m.group(3))
            break
    if not (year and month):
        return None
    records: List[dict] = []
    cur: Optional[dict] = None
    for i, r in enumerate(rows):
        c0 = str(r[0] or "").strip()
        if c0.lower().startswith("emp_code"):
            name = str(rows[i - 1][0] or "").strip() if i > 0 else ""
            cur = {"code": _norm_code(r[1] if len(r) > 1 else ""), "name": name}
            continue
        dm = re.match(r"^\((\w{3})\)\s*(\d{1,2})$", c0)
        if not dm or cur is None:
            continue
        day = int(dm.group(2))
        try:
            date = datetime(year, month, day).date().isoformat()
        except ValueError:
            continue
        r = r + [None] * 9
        records.append({"code": cur["code"], "name": cur["name"], "date": date, "weekday": dm.group(1).upper(),
                        "shift": str(r[1] or "").strip() or None, "in": _hhmm_or_none(r[2]), "out": _hhmm_or_none(r[3]),
                        "machine_status": str(r[8] or "").strip().upper()})
    if not records:
        return None
    return {"format": "block_report", "year": year, "month": month, "records": records,
            "employees": len({(x["code"], x["name"]) for x in records})}


@router.post("/punch-import/preview")
async def punch_preview(file: UploadFile = File(...),
                        user: dict = Depends(require_permission("attendance", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Only HR / Admin can import punch-machine data")
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10 MB)")
    lookup = await _employee_lookup()
    shifts = await _shift_map()
    auto_settings = await _auto_settings()

    # Collect punches per (employee_key, date)
    punches: Dict[tuple, dict] = {}
    parse_errors: List[dict] = []
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    block = _parse_block_report(content) if ext in ("xlsx", "xls") else None
    if block:
        mapping = {"format": "block_report", "year": block["year"], "month": block["month"],
                   "employees": block["employees"], "notes": "Per-employee block report parsed deterministically (no AI)."}
        for rec in block["records"]:
            key = ("LEGACY::" + rec["code"]) if rec["code"] else ("NAME::" + _norm_name(rec["name"]))
            if not rec["in"] and not rec["out"]:
                if rec["machine_status"] != "A" or rec["weekday"] == "SUN":
                    continue
            punches[(key, rec["date"])] = {"code": rec["code"], "name": rec["name"], "times": [],
                                           "in": rec["in"], "out": rec["out"], "shift": rec["shift"],
                                           "machine_absent": not rec["in"] and not rec["out"]}
        delim, start_idx = ",", 0
        lines = []
    else:
        lines = _file_to_lines(file.filename or "punches.txt", content)
        if not lines:
            raise HTTPException(400, "No data lines found in the file")
        mapping = await _ai_map(lines)
        delim = mapping.get("delimiter") or ","
        start_idx = 1 if mapping.get("has_header") else 0

    def col(row: List[str], idx) -> Optional[str]:
        if idx is None:
            return None
        try:
            return row[int(idx)]
        except Exception:
            return None

    in_tokens = {str(t).strip().upper() for t in (mapping.get("in_tokens") or ["IN", "0", "I"])}
    for ln_no, line in enumerate(lines[start_idx:], start=start_idx + 1):
        cells = _split_line(line, delim)
        code = (col(cells, mapping.get("employee_code_col")) or "").strip()
        name = (col(cells, mapping.get("employee_name_col")) or "").strip()
        if not code and not name:
            parse_errors.append({"line": ln_no, "error": "No employee identifier"})
            continue
        key = ("CODE::" + _norm_code(code)) if code else ("NAME::" + _norm_name(name))
        if mapping.get("in_col") is not None or mapping.get("out_col") is not None:
            d = _parse_dt(col(cells, mapping.get("date_col")) or "", mapping.get("date_format"))
            if not d:
                parse_errors.append({"line": ln_no, "error": "Unparseable date"})
                continue
            date = d.date().isoformat()
            rec = punches.setdefault((key, date), {"code": code, "name": name, "times": [], "in": None, "out": None})
            ti = _parse_dt(col(cells, mapping.get("in_col")) or "", mapping.get("time_format"))
            to = _parse_dt(col(cells, mapping.get("out_col")) or "", mapping.get("time_format"))
            if ti:
                rec["in"] = ti.strftime("%H:%M")
            if to:
                rec["out"] = to.strftime("%H:%M")
        else:
            if mapping.get("datetime_combined"):
                dt = _parse_dt(col(cells, mapping.get("date_col")) or "", mapping.get("date_format"))
            else:
                d = _parse_dt(col(cells, mapping.get("date_col")) or "", mapping.get("date_format"))
                t = _parse_dt(col(cells, mapping.get("time_col")) or "", mapping.get("time_format"))
                dt = datetime.combine(d.date(), t.time()) if d and t else None
            if not dt:
                parse_errors.append({"line": ln_no, "error": "Unparseable date/time"})
                continue
            date = dt.date().isoformat()
            rec = punches.setdefault((key, date), {"code": code, "name": name, "times": [], "in": None, "out": None})
            direction = (col(cells, mapping.get("direction_col")) or "").strip().upper()
            rec["times"].append((dt, direction))

    today = datetime.now(timezone.utc).date().isoformat()
    preview_rows: List[dict] = []
    exceptions: List[dict] = []
    unmatched_seen: set = set()
    seen_dates = set()
    for (key, date), rec in sorted(punches.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        person, matched_by = _match_employee(lookup, rec["code"], rec["name"])
        row: dict = {"employee_code": rec["code"], "employee_name": rec["name"], "date": date, "flags": [],
                     "shift_code": rec.get("shift") if rec.get("shift") in shifts else "GEN"}
        if not person:
            row["flags"].append("unmatched_employee")
            who = f"{rec['name']} [{rec['code']}]".strip() if rec["code"] else rec["name"]
            if who not in unmatched_seen:
                unmatched_seen.add(who)
                exceptions.append({"date": date, "who": who, "issue": "No employee with this Legacy Emp Code / name in Employee Master"})
            preview_rows.append(row)
            continue
        row["employee_id"] = person["id"]
        row["employee_name"] = person.get("name")
        row["employee_code"] = person.get("emp_code") or person.get("employee_id")
        row["matched_by"] = matched_by
        if rec.get("machine_absent"):
            row.update({"in_time": None, "out_time": None, "working_hours": 0.0, "overtime_hours": 0.0,
                        "late_minutes": 0, "early_exit_minutes": 0, "status": "absent"})
            row["flags"].append("machine_absent")
            if date > today:
                row["flags"].append("future_date")
            existing = await db.attendance.find_one({"employee_id": person["id"], "date": date}, {"_id": 0, "status": 1, "locked": 1})
            if existing:
                row["flags"].append("locked" if existing.get("locked") else "existing_kept")
                row["status"] = existing.get("status") or "absent"
            seen_dates.add(date)
            preview_rows.append(row)
            continue
        if rec["times"]:
            ins = [t for t, d in rec["times"] if d in in_tokens] or [t for t, _ in rec["times"]]
            outs = [t for t, d in rec["times"] if d and d not in in_tokens] or [t for t, _ in rec["times"]]
            t_in, t_out = min(ins), max(outs)
            rec["in"] = t_in.strftime("%H:%M")
            rec["out"] = t_out.strftime("%H:%M") if t_out > t_in else None
        row["in_time"], row["out_time"] = rec["in"], rec["out"]
        if not rec["in"] and not rec["out"]:
            row["flags"].append("no_punch_time")
        elif not rec["out"] or rec["in"] == rec["out"]:
            row["out_time"] = None if rec["in"] == rec["out"] else rec["out"]
            row["flags"].append("missing_punch")
            exceptions.append({"date": date, "who": row["employee_name"], "issue": "Single punch — missing IN or OUT"})
        if date > today:
            row["flags"].append("future_date")
            exceptions.append({"date": date, "who": row["employee_name"], "issue": "Future date — will be skipped"})
        sh_code = rec.get("shift") if rec.get("shift") in shifts else "GEN"
        row["shift_code"] = sh_code
        sh = shifts.get(sh_code) or {}
        total = _hours_between(_hhmm(row.get("in_time")), _hhmm(row.get("out_time")),
                               float(sh.get("break_minutes") or 0))
        row["working_hours"] = total
        if row.get("in_time") and row.get("out_time"):
            row["status"] = _derive_status(_hhmm(row["in_time"]), _hhmm(row["out_time"]), auto_settings) or "present"
        else:
            row["status"] = "present"
        ot_after = float(sh.get("overtime_after") or 8.0)
        row["overtime_hours"] = max(0.0, round(total - ot_after, 2))
        late, early = _late_early({"shift_code": sh_code, "in_time": row.get("in_time"), "out_time": row.get("out_time")}, shifts)
        row["late_minutes"], row["early_exit_minutes"] = late, early
        existing = await db.attendance.find_one({"employee_id": person["id"], "date": date}, {"_id": 0, "id": 1, "status": 1, "locked": 1})
        if existing:
            row["flags"].append("locked" if existing.get("locked") else "duplicate")
            if existing.get("locked"):
                exceptions.append({"date": date, "who": row["employee_name"], "issue": "Existing entry is LOCKED — will be skipped"})
        seen_dates.add(date)
        preview_rows.append(row)

    batch = {
        "id": new_id(), "file_name": file.filename, "uploaded_by_id": user["id"],
        "uploaded_by": user.get("name") or user.get("email"), "at": now_iso(),
        "mapping": mapping, "rows": preview_rows, "parse_errors": parse_errors[:200],
        "exceptions": exceptions[:500], "dates": sorted(seen_dates), "status": "preview",
        "created_ids": [], "prev_docs": [],
    }
    await db.punch_import_batches.insert_one({**batch})
    batch.pop("_id", None)
    skip_flags = {"unmatched_employee", "locked", "future_date", "existing_kept"}
    importable = len([r for r in preview_rows if not skip_flags & set(r["flags"])])
    unmatched = sorted({f"{r['employee_name']} [{r['employee_code']}]" for r in preview_rows if "unmatched_employee" in r["flags"]})
    return {"ok": True, "batch_id": batch["id"], "mapping": mapping,
            "rows": preview_rows, "exceptions": exceptions, "parse_errors": parse_errors[:50],
            "total_rows": len(preview_rows), "importable": importable,
            "matched_employees": len({r["employee_id"] for r in preview_rows if r.get("employee_id")}),
            "unmatched_employees": unmatched,
            "duplicates": len([r for r in preview_rows if "duplicate" in r["flags"]])}


class CommitIn(BaseModel):
    overwrite: bool = True


@router.post("/punch-import/{batch_id}/commit")
async def punch_commit(batch_id: str, p: CommitIn,
                       user: dict = Depends(require_permission("attendance", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Only HR / Admin can import punch-machine data")
    batch = await db.punch_import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Import batch not found")
    if batch.get("status") != "preview":
        raise HTTPException(400, f"Batch already {batch.get('status')}")
    shifts = await _shift_map()
    settings = await _auto_settings()
    today = datetime.now(timezone.utc).date().isoformat()
    created_ids: List[str] = []
    prev_docs: List[dict] = []
    created = updated = skipped = 0
    for row in batch.get("rows") or []:
        flags = row.get("flags") or []
        if ({"unmatched_employee", "locked", "future_date", "existing_kept"} & set(flags)) or row.get("date") > today:
            skipped += 1
            continue
        person = await db.employees.find_one({"id": row["employee_id"]}, {"_id": 0})
        if not person:
            skipped += 1
            continue
        try:
            action, aid, prev = await _write_attendance(
                person, row["date"], row.get("status") or "present",
                row.get("in_time"), row.get("out_time"), row.get("overtime_hours"),
                "Punch machine import", row.get("shift_code") if row.get("shift_code") in shifts else None,
                "biometric", user, shifts,
                overwrite=p.overwrite, settings=settings)
        except ValueError:
            skipped += 1
            continue
        if action == "created":
            created += 1
            created_ids.append(aid)
        elif action == "updated":
            updated += 1
            if prev:
                prev_docs.append(prev)
        else:
            skipped += 1
    await db.punch_import_batches.update_one({"id": batch_id}, {"$set": {
        "status": "committed", "committed_at": now_iso(), "committed_by": user.get("name"),
        "created_ids": created_ids, "prev_docs": prev_docs,
        "result": {"created": created, "updated": updated, "skipped": skipped}}})
    await audit(user=user, action="punch_import_commit", resource="attendance", record_id=batch_id,
                after={"created": created, "updated": updated, "skipped": skipped}, ip="attendance-plus")
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped}


@router.post("/punch-import/{batch_id}/rollback")
async def punch_rollback(batch_id: str,
                         user: dict = Depends(require_permission("attendance", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Only HR / Admin can rollback imports")
    batch = await db.punch_import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Import batch not found")
    if batch.get("status") != "committed":
        raise HTTPException(400, f"Only committed batches can be rolled back (status: {batch.get('status')})")
    removed = restored = 0
    if batch.get("created_ids"):
        res = await db.attendance.delete_many({"id": {"$in": batch["created_ids"]}})
        removed = res.deleted_count
    for prev in batch.get("prev_docs") or []:
        prev.pop("_id", None)
        await db.attendance.replace_one({"id": prev["id"]}, prev, upsert=True)
        restored += 1
    await db.punch_import_batches.update_one({"id": batch_id}, {"$set": {
        "status": "rolled_back", "rolled_back_at": now_iso(), "rolled_back_by": user.get("name")}})
    await audit(user=user, action="punch_import_rollback", resource="attendance", record_id=batch_id,
                after={"removed": removed, "restored": restored}, ip="attendance-plus")
    return {"ok": True, "removed": removed, "restored": restored}


@router.get("/punch-imports")
async def punch_history(request: Request, user: dict = Depends(require_permission("attendance", "read"))):
    proj = {"_id": 0, "rows": 0, "prev_docs": 0, "created_ids": 0, "mapping": 0}
    paged = await maybe_paged(request, "punch_import_batches", {}, "at", ["filename", "file_name", "uploaded_by", "status", "month", "source"])
    if paged:
        ids = [r["id"] for r in paged["rows"] if r.get("id")]
        paged["rows"] = await db.punch_import_batches.find({"id": {"$in": ids}}, proj).sort("at", -1).to_list(len(ids) or 1)
        return paged
    rows = await db.punch_import_batches.find({}, proj).sort("at", -1).to_list(100)
    return rows
