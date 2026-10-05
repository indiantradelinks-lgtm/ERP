"""HR · Payroll — Month-wise BULK SALARY BOOKING with project-wise allocation.

Flow
----
1. `GET  /api/payroll/bulk-booking/template?month=YYYY-MM`
   Downloads an xlsx in the client's own "Salary Export" format, pre-filled from
   Attendance (pay/present days + OT), Salary Breakup (payroll_master), active
   Advances and the employee's current project.
2. `POST /api/payroll/bulk-booking/preview`  (multipart: file, month)
   Parses the filled sheet, matches rows on **Emp ID** (employees.emp_code),
   resolves Project Name/Code against the project master, compares the sheet
   amounts against the system calculation (sheet wins — differences are shown as
   warnings) and stores a `salary_booking_batches` preview doc.
3. `POST /api/payroll/bulk-booking/{bid}/commit`
   Books the whole month in one shot: `payslips` (project-tagged),
   `salary_project_allocations`, `salary_bookings` header, `payroll_runs`
   (so the existing Finance Approval → Accounts posting chain keeps working)
   and advance-recovery rows. No journal entry is posted here — that stays with
   the existing `/api/hr4/payroll/finance-approve` → `/post-to-accounts` steps.
4. `POST /api/payroll/bulk-booking/payments`  — month-level and/or employee-wise
   payment recording; keeps booked / paid / pending balances per employee and
   per project.
5. `GET  /api/payroll/bulk-booking/summary` and `/project-report` — dashboards.

Existing Attendance and Salary Breakup functionality is untouched.
"""
from __future__ import annotations

import io
import logging
import re
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from pagination import maybe_paged
from hr_worker_rules import is_worker_master, paid_weights

logger = logging.getLogger("erp.salary_booking")
router = APIRouter(prefix="/payroll/bulk-booking", tags=["salary-booking"])

SHEET_NAME = "Salary Export"

# Exact column order of the client's Project-wise Salary Format
COLUMNS: List[tuple[str, str]] = [
    ("Emp ID", "emp_id"),
    ("Employee Name", "employee_name"),
    ("Month/ Year", "month_year"),
    ("Pay Days", "pay_days"),
    ("Present Days", "present_days"),
    ("BASIC", "basic"),
    ("FIX Rate", "fix_rate"),
    ("Other Allo", "other_allo"),
    ("DA", "da"),
    ("HRA", "hra"),
    ("CONV", "conv"),
    ("Att. Bonus", "att_bonus"),
    ("OT Amount", "ot_amount"),
    ("OT1 Unit", "ot1_unit"),
    ("Other ded", "other_ded"),
    ("Advance.", "advance"),
    ("LWF", "lwf"),
    ("PF", "pf"),
    ("ESI", "esi"),
    ("PT", "pt"),
    ("Total Earning", "total_earning"),
    ("Total Deduction", "total_deduction"),
    ("Net Amount", "net_amount"),
    ("BASIC (Rt)", "basic_rt"),
    ("FIX Rate (Rt)", "fix_rate_rt"),
    ("DA (Rt)", "da_rt"),
    ("OT RATE (Rt)", "ot_rate_rt"),
    ("EL AVAILED", "el_availed"),
    ("CL AVAILED", "cl_availed"),
    ("Remark", "remark"),
    ("Project Name", "project_name"),
    ("Project Code", "project_code"),
    ("Department", "department"),
    ("Designation", "designation"),
    ("Grade", "grade"),
    ("Father's Name", "father_name"),
    ("UAN No.", "uan_no"),
    ("E.S.I. No.", "esi_no"),
]

EARNING_KEYS = ["basic", "other_allo", "da", "hra", "conv", "att_bonus", "ot_amount"]
DEDUCTION_KEYS = ["other_ded", "advance", "lwf", "pf", "esi", "pt"]
NUMERIC_KEYS = set(EARNING_KEYS) | set(DEDUCTION_KEYS) | {
    "pay_days", "present_days", "fix_rate", "ot1_unit",
    "total_earning", "total_deduction", "net_amount",
    "basic_rt", "fix_rate_rt", "da_rt", "ot_rate_rt", "el_availed", "cl_availed",
}


def _canon(v: Any) -> str:
    return "".join(ch for ch in str(v or "").lower() if ch.isalnum())


HEADER_LOOKUP = {_canon(h): k for h, k in COLUMNS}


def _num(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("\u20b9", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    return str(v).strip()


def _seq_no(month: str, n: int) -> str:
    return f"HR/BSB/{month.replace('-', '/')}/{n:03d}"


# ──────────────────────────────────────────────────────────────────────────────
# Attendance + breakup derived pre-fill
# ──────────────────────────────────────────────────────────────────────────────
PAID_WEIGHTS = {"present": 1, "on_duty": 1, "leave": 1, "weekly_off": 1, "holiday": 1, "half_day": 0.5}


async def _att_stats(employee_id: str, month: str, total_days: int,
                     week_off_paid: bool = True) -> Dict[str, float]:
    rows = await db.attendance.find(
        {"employee_id": employee_id, "date": {"$regex": f"^{month}-"}},
        {"_id": 0, "status": 1, "overtime_hours": 1, "leave_type": 1},
    ).to_list(500)
    if not rows:
        return {"pay_days": float(total_days), "present_days": float(total_days),
                "ot_hours": 0.0, "el": 0.0, "cl": 0.0, "linked": False}
    pay = sum(PAID_WEIGHTS.get(r.get("status") or "", 0) for r in rows) if week_off_paid else \
        sum(paid_weights(False).get(r.get("status") or "", 0) for r in rows)
    present = sum(1 if (r.get("status") in {"present", "on_duty"}) else (0.5 if r.get("status") == "half_day" else 0)
                  for r in rows)
    ot = round(sum(_num(r.get("overtime_hours")) for r in rows), 2)
    el = sum(1 for r in rows if r.get("status") == "leave" and (r.get("leave_type") or "").upper().startswith("EL"))
    cl = sum(1 for r in rows if r.get("status") == "leave" and (r.get("leave_type") or "").upper().startswith("CL"))
    return {"pay_days": round(pay, 1), "present_days": round(present, 1),
            "ot_hours": ot, "el": float(el), "cl": float(cl), "linked": True}


async def _advance_due(employee_id: str, month: str) -> tuple[float, List[Dict[str, Any]]]:
    total = 0.0
    lines: List[Dict[str, Any]] = []
    async for adv in db.employee_advances.find(
        {"employee_id": employee_id, "status": {"$in": ["paid", "under_recovery"]}, "outstanding": {"$gt": 0}},
        {"_id": 0, "id": 1, "advance_no": 1, "dept_doc_no": 1, "emi": 1, "outstanding": 1,
         "repayment_start_month": 1, "recovered_amount": 1, "remaining_installments": 1},
    ):
        if (adv.get("repayment_start_month") or "") > month:
            continue
        if await db.advance_recoveries.find_one({"advance_id": adv["id"], "month": month}):
            continue
        emi = min(_num(adv.get("emi")), _num(adv.get("outstanding")))
        if emi > 0:
            total += emi
            lines.append({"advance_id": adv["id"],
                          "advance_no": adv.get("dept_doc_no") or adv.get("advance_no"),
                          "amount": round(emi, 2), "outstanding": _num(adv.get("outstanding"))})
    return round(total, 2), lines


async def _project_maps() -> tuple[Dict[str, str], Dict[str, str]]:
    """(code -> name, canon(name) -> code)"""
    by_code: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    async for p in db.projects.find({}, {"_id": 0, "code": 1, "name": 1}):
        code = (p.get("code") or "").strip()
        name = (p.get("name") or "").strip()
        if code:
            by_code[code.upper()] = name
            if name:
                by_name[_canon(name)] = code
    return by_code, by_name


async def _system_row(emp: dict, month: str, total_days: int,
                      master: dict, proj_by_code: Dict[str, str]) -> Dict[str, Any]:
    """System-calculated salary row for one employee (pre-fill + variance base)."""
    att = await _att_stats(emp["id"], month, total_days,
                           week_off_paid=not await is_worker_master(emp))
    pay_days = att["pay_days"]
    factor = max(0.0, min(1.0, pay_days / total_days)) if total_days else 0.0

    def m(k: str) -> float:
        return _num(master.get(k))

    fix_rate = (m("basic") + m("hra") + m("da") + m("special_allowance")
                + m("site_allowance") + m("conveyance") + m("medical")
                + sum(_num(r.get("amount")) for r in (master.get("fixed_other_earnings") or [])))
    basic = round(m("basic") * factor, 2)
    da = round(m("da") * factor, 2)
    hra = round(m("hra") * factor, 2)
    conv = round(m("conveyance") * factor, 2)
    other_allo = round((m("special_allowance") + m("site_allowance") + m("medical")
                        + sum(_num(r.get("amount")) for r in (master.get("fixed_other_earnings") or []))) * factor, 2)

    ot_rate = _num(master.get("ot_rate_per_hour"))
    if ot_rate <= 0 and fix_rate > 0 and total_days:
        ot_rate = round(fix_rate / (total_days * 8), 2)
    ot_amount = round(att["ot_hours"] * ot_rate * (_num(master.get("ot_multiplier")) or 1.0), 2)

    lop = max(0.0, total_days - pay_days)
    att_bonus = (round(_num(master.get("attendance_bonus_amount")), 2)
                 if master.get("attendance_bonus_applicable") and lop <= 0 else 0.0)

    gross = round(basic + da + hra + conv + other_allo + att_bonus + ot_amount, 2)
    pf = round(min(m("basic"), 15000) * 0.12, 2) if master.get("pf_applicable", True) else 0.0
    esi = round(gross * 0.0075, 2) if (master.get("esi_applicable") and gross <= 21000) else 0.0
    pt = 200.0 if gross > 15000 else 0.0
    other_ded = round(sum(_num(r.get("amount")) for r in (master.get("fixed_other_deductions") or [])), 2)
    advance, adv_lines = await _advance_due(emp["id"], month)

    total_ded = round(pf + esi + pt + other_ded + advance, 2)
    pcode = (emp.get("current_project_code") or "").strip()
    row = {
        "emp_id": emp.get("emp_code") or emp.get("employee_id") or "",
        "employee_name": emp.get("name") or "",
        "month_year": f"{month}-01",
        "pay_days": pay_days,
        "present_days": att["present_days"],
        "basic": basic, "fix_rate": round(fix_rate, 2), "other_allo": other_allo,
        "da": da, "hra": hra, "conv": conv, "att_bonus": att_bonus,
        "ot_amount": ot_amount, "ot1_unit": att["ot_hours"],
        "other_ded": other_ded, "advance": advance, "lwf": 0.0,
        "pf": pf, "esi": esi, "pt": pt,
        "total_earning": gross, "total_deduction": total_ded,
        "net_amount": round(gross - total_ded, 2),
        "basic_rt": round(basic / pay_days, 2) if pay_days else 0.0,
        "fix_rate_rt": round(fix_rate, 2),
        "da_rt": round(da / pay_days, 2) if pay_days else 0.0,
        "ot_rate_rt": ot_rate,
        "el_availed": att["el"], "cl_availed": att["cl"], "remark": "",
        "project_name": proj_by_code.get(pcode.upper(), ""),
        "project_code": pcode,
        "department": (emp.get("departments") or [None])[0] or emp.get("department") or "",
        "designation": emp.get("designation") or "",
        "grade": emp.get("grade") or "", "father_name": emp.get("father_name") or "",
        "uan_no": emp.get("uan_no") or "", "esi_no": emp.get("esi_no") or "",
        "_employee_id": emp["id"],
        "_attendance_linked": att["linked"],
        "_advance_lines": adv_lines,
    }
    return row


def _build_workbook(rows: List[Dict[str, Any]], month: str, *, notes: List[str]) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    ws.append([h for h, _ in COLUMNS])
    for c in ws[1]:
        c.font = c.font.copy(bold=True)
    for r in rows:
        ws.append([r.get(k, "") if k not in NUMERIC_KEYS else _num(r.get(k)) for _, k in COLUMNS])
    for idx, (h, _) in enumerate(COLUMNS, 1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = max(12, len(h) + 3)
    inst = wb.create_sheet("INSTRUCTIONS")
    for line in notes:
        inst.append([line])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ──────────────────────────────────────────────────────────────────────────────
# 1) Template
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/template")
async def download_template(month: str,
                            user: dict = Depends(require_permission("hr_payroll", "write"))):
    if len(month or "") != 7:
        raise HTTPException(400, "month must be YYYY-MM")
    total_days = monthrange(int(month[:4]), int(month[5:7]))[1]
    proj_by_code, _ = await _project_maps()
    emps = await db.employees.find(
        {"status": {"$nin": ["exited", "terminated", "inactive"]}, "active": {"$ne": False}},
        {"_id": 0},
    ).sort("emp_code", 1).to_list(20000)
    rows: List[Dict[str, Any]] = []
    for emp in emps:
        master = await db.payroll_master.find_one({"employee_id": emp["id"]}, {"_id": 0})
        if not master:
            continue
        rows.append(await _system_row(emp, month, total_days, master, proj_by_code))
    buf = _build_workbook(rows, month, notes=[
        f"INDIAN TRADE LINKS ERP — Project-wise Bulk Salary Booking · {month}",
        "",
        "1. 'Emp ID' is the match key (employee's Legacy Emp Code). Do not blank or edit it.",
        "2. Amounts are pre-filled from Attendance (Pay/Present Days + OT), Salary Breakup and open Advances.",
        "3. Edit any amount you want — the UPLOADED sheet is final. Differences vs the system",
        "   calculation are reported as warnings on the preview screen, they do not block booking.",
        "4. 'Project Code' (preferred) or 'Project Name' drives project-wise salary expense booking.",
        "   One project per employee per month. Unknown codes are flagged but still booked as a label.",
        "5. Total Earning / Total Deduction / Net Amount are recomputed on upload from the component",
        "   columns, so you only need to fix the components.",
        "6. Delete the rows of employees you do not want to book this month.",
        "7. Employees without a Salary Breakup are not exported and are reported if present in your sheet.",
    ])
    fname = f"salary-booking-{month}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2) Preview
# ──────────────────────────────────────────────────────────────────────────────
def _recompute(row: Dict[str, Any]) -> None:
    gross = round(sum(_num(row.get(k)) for k in EARNING_KEYS), 2)
    ded = round(sum(_num(row.get(k)) for k in DEDUCTION_KEYS), 2)
    row["total_earning"] = gross
    row["total_deduction"] = ded
    row["net_amount"] = round(gross - ded, 2)


@router.post("/preview")
async def preview_upload(month: str = Form(...), file: UploadFile = File(...),
                         user: dict = Depends(require_permission("hr_payroll", "write"))):
    if len(month or "") != 7:
        raise HTTPException(400, "month must be YYYY-MM")
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Please upload the .xlsx Project-wise Salary Format")
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception as exc:
        raise HTTPException(400, f"Invalid xlsx file: {exc}")
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.worksheets[0]
    if ws.max_row < 2:
        raise HTTPException(400, "Sheet has no data rows")

    headers = [_canon(c.value) for c in ws[1]]
    col_idx: Dict[str, int] = {}
    for i, h in enumerate(headers):
        key = HEADER_LOOKUP.get(h)
        if key and key not in col_idx:
            col_idx[key] = i
    if "emp_id" not in col_idx:
        raise HTTPException(400, "Column 'Emp ID' not found — upload the downloaded format")

    total_days = monthrange(int(month[:4]), int(month[5:7]))[1]
    proj_by_code, proj_by_name = await _project_maps()

    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for r in ws.iter_rows(min_row=2, values_only=True):
        if r is None or all(v in (None, "") for v in r):
            continue

        def cell(key: str) -> Any:
            i = col_idx.get(key)
            return r[i] if i is not None and i < len(r) else None

        emp_code = _txt(cell("emp_id"))
        if not emp_code:
            continue
        name_in_sheet = _txt(cell("employee_name"))
        if emp_code.upper() in seen:
            skipped.append({"emp_id": emp_code, "employee_name": name_in_sheet,
                            "reason": "Duplicate Emp ID in the sheet — only the first row is booked"})
            continue
        seen.add(emp_code.upper())

        emp = await db.employees.find_one(
            {"$or": [{"emp_code": {"$regex": f"^{re.escape(emp_code.strip())}$", "$options": "i"}},
                     {"employee_id": {"$regex": f"^{re.escape(emp_code.strip())}$", "$options": "i"}}]},
            {"_id": 0})
        if not emp:
            skipped.append({"emp_id": emp_code, "employee_name": name_in_sheet,
                            "reason": "Emp ID not found in HR employee master"})
            continue
        master = await db.payroll_master.find_one({"employee_id": emp["id"]}, {"_id": 0})
        if not master:
            skipped.append({"emp_id": emp_code, "employee_name": emp.get("name") or name_in_sheet,
                            "reason": "No Salary Breakup / Payroll Master configured"})
            continue

        sysrow = await _system_row(emp, month, total_days, master, proj_by_code)
        row = dict(sysrow)
        for _, key in COLUMNS:
            if key in ("emp_id", "employee_name", "month_year"):
                continue
            i = col_idx.get(key)
            if i is None:
                continue
            raw = r[i] if i < len(r) else None
            if raw in (None, ""):
                if key in NUMERIC_KEYS:
                    row[key] = 0.0
                continue
            row[key] = _num(raw) if key in NUMERIC_KEYS else _txt(raw)
        row["emp_id"] = emp.get("emp_code") or emp.get("employee_id") or emp_code
        row["employee_name"] = emp.get("name")
        row["month_year"] = f"{month}-01"
        _recompute(row)

        # Project resolution: code first, then name; unknown → keep as label
        pcode = _txt(row.get("project_code"))
        pname = _txt(row.get("project_name"))
        resolved = False
        if pcode and pcode.upper() in proj_by_code:
            row["project_name"] = proj_by_code[pcode.upper()] or pname
            resolved = True
        elif pname and _canon(pname) in proj_by_name:
            row["project_code"] = proj_by_name[_canon(pname)]
            resolved = True
        row["project_matched"] = resolved
        if not (pcode or pname):
            row["project_code"] = "_UNALLOCATED_"
            row["project_name"] = "Unallocated"
            warnings.append({"emp_id": row["emp_id"], "employee_name": row["employee_name"],
                             "type": "project", "message": "No project given — booked as Unallocated"})
        elif not resolved:
            row["project_code"] = pcode or pname
            row["project_name"] = pname or pcode
            warnings.append({"emp_id": row["emp_id"], "employee_name": row["employee_name"],
                             "type": "project",
                             "message": f"Project '{pname or pcode}' is not in the project master — booked as a label"})

        # Variance vs system calculation (sheet wins)
        for key, label in (("pay_days", "Pay Days"), ("total_earning", "Total Earning"),
                           ("total_deduction", "Total Deduction"), ("net_amount", "Net Amount")):
            sys_v = _num(sysrow.get(key)) if key != "net_amount" else _num(sysrow.get("net_amount"))
            sheet_v = _num(row.get(key))
            if abs(sheet_v - sys_v) > 1:
                warnings.append({"emp_id": row["emp_id"], "employee_name": row["employee_name"],
                                 "type": "variance", "field": label,
                                 "system_value": round(sys_v, 2), "sheet_value": round(sheet_v, 2),
                                 "message": f"{label}: sheet {sheet_v:,.2f} vs system {sys_v:,.2f}"})
        if not sysrow.get("_attendance_linked"):
            warnings.append({"emp_id": row["emp_id"], "employee_name": row["employee_name"],
                             "type": "attendance",
                             "message": "No attendance rows for this month — full-month days assumed by the system"})
        rows.append(row)

    if not rows:
        raise HTTPException(400, "No bookable rows found in the sheet — see the reported errors")

    by_project: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        agg = by_project.setdefault(row["project_code"], {
            "project_code": row["project_code"], "project_name": row["project_name"],
            "headcount": 0, "gross": 0.0, "deductions": 0.0, "net": 0.0,
            "matched": bool(row.get("project_matched")),
        })
        agg["headcount"] += 1
        agg["gross"] += _num(row["total_earning"])
        agg["deductions"] += _num(row["total_deduction"])
        agg["net"] += _num(row["net_amount"])
    for agg in by_project.values():
        for k in ("gross", "deductions", "net"):
            agg[k] = round(agg[k], 2)

    totals = {
        "count": len(rows),
        "gross": round(sum(_num(x["total_earning"]) for x in rows), 2),
        "deductions": round(sum(_num(x["total_deduction"]) for x in rows), 2),
        "net": round(sum(_num(x["net_amount"]) for x in rows), 2),
        "pf": round(sum(_num(x["pf"]) for x in rows), 2),
        "esi": round(sum(_num(x["esi"]) for x in rows), 2),
        "pt": round(sum(_num(x["pt"]) for x in rows), 2),
        "advance": round(sum(_num(x["advance"]) for x in rows), 2),
    }

    already = await db.salary_bookings.find_one({"month": month, "status": "booked"}, {"_id": 0, "booking_no": 1})
    run = await db.payroll_runs.find_one({"month": month, "status": "committed"}, {"_id": 0, "id": 1})

    batch = {
        "id": new_id(), "month": month, "filename": file.filename,
        "status": "preview", "rows": rows, "skipped": skipped, "warnings": warnings,
        "totals": totals, "by_project": sorted(by_project.values(), key=lambda x: -x["gross"]),
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
    }
    await db.salary_booking_batches.insert_one(dict(batch))
    batch.pop("_id", None)
    return {**batch, "already_booked": bool(already),
            "already_booked_no": (already or {}).get("booking_no"),
            "payroll_run_exists": bool(run)}


@router.get("/batch/{bid}")
async def get_batch(bid: str, user: dict = Depends(require_permission("hr_payroll", "read"))):
    doc = await db.salary_booking_batches.find_one({"id": bid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "batch not found")
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# 3) Commit — book the month
# ──────────────────────────────────────────────────────────────────────────────
class CommitIn(BaseModel):
    overwrite: bool = False
    remarks: str = ""


@router.post("/{bid}/commit")
async def commit_batch(bid: str, p: CommitIn,
                       user: dict = Depends(require_permission("hr_payroll", "write"))):
    batch = await db.salary_booking_batches.find_one({"id": bid}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "batch not found")
    if batch.get("status") == "committed":
        raise HTTPException(400, "This batch is already booked")
    month = batch["month"]

    existing = await db.salary_bookings.find_one({"month": month, "status": "booked"}, {"_id": 0})
    if existing and not p.overwrite:
        raise HTTPException(400, f"Salary for {month} is already booked ({existing['booking_no']}). "
                                 "Re-run with overwrite to replace it.")
    if existing and p.overwrite:
        await db.salary_bookings.update_one({"id": existing["id"]}, {"$set": {
            "status": "replaced", "replaced_at": now_iso(),
            "replaced_by": user.get("name") or user.get("email")}})
        await db.salary_project_allocations.delete_many({"month": month, "booking_id": existing["id"]})

    run = await db.payroll_runs.find_one({"month": month, "status": "committed"}, {"_id": 0})
    if run and run.get("source") != "bulk_booking" and not p.overwrite:
        raise HTTPException(400, f"A monthly payroll run for {month} is already committed. "
                                 "Use overwrite only if you intend to replace it.")

    by_user = user.get("name") or user.get("email")
    booking_id = new_id()
    seq = await db.salary_bookings.count_documents({}) + 1
    rows: List[Dict[str, Any]] = batch.get("rows") or []

    booked: List[Dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        gross = _num(row["total_earning"])
        ded = _num(row["total_deduction"])
        net = _num(row["net_amount"])
        earnings = {"basic": _num(row["basic"]), "hra": _num(row["hra"]), "da": _num(row["da"]),
                    "conveyance": _num(row["conv"]), "other_allowance": _num(row["other_allo"])}
        extra_earnings = []
        if _num(row["att_bonus"]):
            extra_earnings.append({"label": "Attendance Bonus", "amount": _num(row["att_bonus"])})
        if _num(row["ot_amount"]):
            extra_earnings.append({"label": f"Overtime ({_num(row['ot1_unit'])} hrs)", "amount": _num(row["ot_amount"])})
        extra_deductions = []
        if _num(row["other_ded"]):
            extra_deductions.append({"label": "Other Deduction", "amount": _num(row["other_ded"])})
        if _num(row["lwf"]):
            extra_deductions.append({"label": "LWF", "amount": _num(row["lwf"])})

        slip = {
            "id": new_id(),
            "dept_doc_no": _seq_no(month, i),
            "ownership_department": "hr",
            "employee_id": row["_employee_id"],
            "employee_name": row["employee_name"],
            "employee_code": row["emp_id"],
            "department": row.get("department") or "",
            "designation": row.get("designation") or "",
            "grade": row.get("grade") or "",
            "month": month,
            "total_days": monthrange(int(month[:4]), int(month[5:7]))[1],
            "paid_days": _num(row["pay_days"]),
            "present_days": _num(row["present_days"]),
            "lop_days": round(max(0.0, monthrange(int(month[:4]), int(month[5:7]))[1] - _num(row["pay_days"])), 1),
            "ot_hours": _num(row["ot1_unit"]),
            "attendance_linked": bool(row.get("_attendance_linked")),
            "earnings": earnings,
            "extra_earnings": extra_earnings,
            "statutory_deductions": {"pf": _num(row["pf"]), "esi": _num(row["esi"]),
                                     "professional_tax": _num(row["pt"]), "tds": 0.0},
            "advance_emi": _num(row["advance"]),
            "advance_lines": row.get("_advance_lines") or [],
            "extra_deductions": extra_deductions,
            "total_earnings": gross,
            "total_deductions": ded,
            "net_pay": net,
            "project_code": row["project_code"],
            "project_name": row["project_name"],
            "uan_no": row.get("uan_no") or "",
            "esi_no": row.get("esi_no") or "",
            "father_name": row.get("father_name") or "",
            "remark": row.get("remark") or "",
            "source": "bulk_booking",
            "booking_id": booking_id,
            "status": "committed",
            "paid_amount": 0.0,
            "payment_status": "unpaid",
            "committed_at": now_iso(),
            "committed_by": by_user,
        }
        await db.payslips.update_one({"month": month, "employee_id": slip["employee_id"]},
                                     {"$set": slip}, upsert=True)

        await db.salary_project_allocations.update_one(
            {"month": month, "employee_id": slip["employee_id"]},
            {"$set": {
                "id": new_id(), "booking_id": booking_id, "month": month,
                "employee_id": slip["employee_id"], "emp_code": slip["employee_code"],
                "employee_name": slip["employee_name"], "department": slip["department"],
                "designation": slip["designation"],
                "project_code": row["project_code"], "project_name": row["project_name"],
                "project_matched": bool(row.get("project_matched")),
                "gross": gross, "deductions": ded, "net": net,
                "pf": _num(row["pf"]), "esi": _num(row["esi"]), "pt": _num(row["pt"]),
                "advance": _num(row["advance"]),
                "paid_amount": 0.0, "pending_amount": net, "payment_status": "unpaid",
                "booked_at": now_iso(), "booked_by": by_user,
            }}, upsert=True)

        # Advance recovery wiring (same behaviour as the monthly run)
        pending = _num(row["advance"])
        for line in (row.get("_advance_lines") or []):
            if pending <= 0.009:
                break
            amt = min(_num(line.get("amount")), pending)
            pending = round(pending - amt, 2)
            if amt <= 0:
                continue
            if await db.advance_recoveries.find_one({"advance_id": line["advance_id"], "month": month}):
                continue
            await db.advance_recoveries.insert_one({
                "id": new_id(), "advance_id": line["advance_id"],
                "employee_id": slip["employee_id"], "month": month,
                "amount": amt, "type": "emi",
                "note": f"Auto EMI deduction from bulk salary booking {month}",
                "at": now_iso(), "by": by_user,
            })
            adv = await db.employee_advances.find_one({"id": line["advance_id"]}, {"_id": 0})
            if adv:
                new_out = max(0.0, _num(adv.get("outstanding")) - amt)
                await db.employee_advances.update_one({"id": adv["id"]}, {"$set": {
                    "recovered_amount": _num(adv.get("recovered_amount")) + amt,
                    "outstanding": new_out,
                    "remaining_installments": max(0, int(adv.get("remaining_installments") or 0) - 1),
                    "status": "closed" if new_out <= 0.01 else "under_recovery",
                    **({"closed_at": now_iso()} if new_out <= 0.01 else {}),
                }})
        booked.append({"employee_id": slip["employee_id"], "net_pay": net})

    totals = batch.get("totals") or {}
    booking = {
        "id": booking_id,
        "booking_no": f"BSB-{month}-{seq:03d}",
        "month": month, "status": "booked",
        "batch_id": bid, "filename": batch.get("filename"),
        "employee_count": len(booked),
        "totals": totals,
        "by_project": batch.get("by_project") or [],
        "booked_amount": totals.get("net", 0),
        "paid_amount": 0.0,
        "pending_amount": totals.get("net", 0),
        "payment_status": "unpaid",
        "skipped": batch.get("skipped") or [],
        "warning_count": len(batch.get("warnings") or []),
        "remarks": p.remarks,
        "created_at": now_iso(), "created_by": by_user,
    }
    await db.salary_bookings.insert_one(dict(booking))

    run_doc = {
        "month": month, "status": "committed", "source": "bulk_booking",
        "booking_id": booking_id, "booking_no": booking["booking_no"],
        "payslip_count": len(booked), "total_net": totals.get("net", 0),
        "committed_at": now_iso(), "committed_by": by_user,
    }
    if run:
        await db.payroll_runs.update_one({"id": run["id"]}, {"$set": run_doc})
    else:
        await db.payroll_runs.insert_one({"id": new_id(), **run_doc})

    await db.salary_booking_batches.update_one({"id": bid}, {"$set": {
        "status": "committed", "booking_id": booking_id,
        "committed_at": now_iso(), "committed_by": by_user}})

    return {"ok": True, "booking": booking, "booked_count": len(booked),
            "skipped_count": len(booking["skipped"])}


# ──────────────────────────────────────────────────────────────────────────────
# 4) Bookings list
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/bookings")
async def list_bookings(request: Request, month: str = "", status: str = "",
                        user: dict = Depends(require_permission("hr_payroll", "read"))):
    q: Dict[str, Any] = {}
    if month:
        q["month"] = month
    if status:
        q["status"] = status
    paged = await maybe_paged(request, "salary_bookings", q, "month",
                              ["booking_no", "month", "status", "created_by"])
    if paged:
        return paged
    return await db.salary_bookings.find(q, {"_id": 0, "rows": 0}).sort("month", -1).limit(200).to_list(200)


# ──────────────────────────────────────────────────────────────────────────────
# 5) Payments — month-level and employee-wise
# ──────────────────────────────────────────────────────────────────────────────
class PaymentIn(BaseModel):
    month: str
    employee_ids: List[str] = Field(default_factory=list)   # empty = every pending employee
    project_code: Optional[str] = None
    amount: float = 0                                       # 0 = clear full pending of the selection
    payment_date: str = ""
    mode: str = "bank"
    reference: str = ""
    note: str = ""


async def _refresh_booking_payment(month: str) -> Dict[str, Any]:
    allocs = await db.salary_project_allocations.find({"month": month}, {"_id": 0}).to_list(20000)
    booked = round(sum(_num(a.get("net")) for a in allocs), 2)
    paid = round(sum(_num(a.get("paid_amount")) for a in allocs), 2)
    pending = round(booked - paid, 2)
    status = "paid" if pending <= 0.01 and booked > 0 else ("partial" if paid > 0 else "unpaid")
    await db.salary_bookings.update_one({"month": month, "status": "booked"}, {"$set": {
        "booked_amount": booked, "paid_amount": paid,
        "pending_amount": pending, "payment_status": status}})
    return {"booked": booked, "paid": paid, "pending": pending, "payment_status": status}


@router.post("/payments")
async def record_payment(p: PaymentIn,
                         user: dict = Depends(require_permission("hr_payroll", "write"))):
    if len(p.month or "") != 7:
        raise HTTPException(400, "month must be YYYY-MM")
    booking = await db.salary_bookings.find_one({"month": p.month, "status": "booked"}, {"_id": 0})
    if not booking:
        raise HTTPException(404, f"No booked salary found for {p.month}")

    q: Dict[str, Any] = {"month": p.month}
    if p.employee_ids:
        q["employee_id"] = {"$in": p.employee_ids}
    if p.project_code:
        q["project_code"] = p.project_code
    allocs = await db.salary_project_allocations.find(q, {"_id": 0}).sort("employee_name", 1).to_list(20000)
    allocs = [a for a in allocs if _num(a.get("pending_amount")) > 0.009]
    if not allocs:
        raise HTTPException(400, "Nothing pending for the selected employees / project")

    budget = _num(p.amount)
    full = budget <= 0
    by_user = user.get("name") or user.get("email")
    pay_date = p.payment_date or now_iso()[:10]
    lines: List[Dict[str, Any]] = []

    for a in allocs:
        pending = round(_num(a.get("pending_amount")), 2)
        amt = pending if full else round(min(pending, budget), 2)
        if amt <= 0.009:
            continue
        if not full:
            budget = round(budget - amt, 2)
        new_paid = round(_num(a.get("paid_amount")) + amt, 2)
        new_pending = round(_num(a.get("net")) - new_paid, 2)
        status = "paid" if new_pending <= 0.01 else "partial"
        await db.salary_project_allocations.update_one(
            {"month": p.month, "employee_id": a["employee_id"]},
            {"$set": {"paid_amount": new_paid, "pending_amount": max(0.0, new_pending),
                      "payment_status": status, "last_paid_at": now_iso()}})
        await db.payslips.update_one({"month": p.month, "employee_id": a["employee_id"]},
                                     {"$set": {"paid_amount": new_paid, "payment_status": status}})
        pay = {
            "id": new_id(), "month": p.month, "booking_id": booking["id"],
            "employee_id": a["employee_id"], "emp_code": a.get("emp_code"),
            "employee_name": a.get("employee_name"),
            "project_code": a.get("project_code"), "project_name": a.get("project_name"),
            "amount": amt, "payment_date": pay_date, "mode": p.mode,
            "reference": p.reference, "note": p.note,
            "created_at": now_iso(), "created_by": by_user,
        }
        await db.salary_payments.insert_one(dict(pay))
        pay.pop("_id", None)
        lines.append(pay)
        if not full and budget <= 0.009:
            break

    summary = await _refresh_booking_payment(p.month)
    return {"ok": True, "paid_now": round(sum(_num(x["amount"]) for x in lines), 2),
            "employees_paid": len(lines), "lines": lines, **summary}


@router.get("/payments")
async def list_payments(month: str = "", employee_id: str = "", project_code: str = "",
                        user: dict = Depends(require_permission("hr_payroll", "read"))):
    q: Dict[str, Any] = {}
    if month:
        q["month"] = month
    if employee_id:
        q["employee_id"] = employee_id
    if project_code:
        q["project_code"] = project_code
    return await db.salary_payments.find(q, {"_id": 0}).sort("created_at", -1).limit(1000).to_list(1000)


# ──────────────────────────────────────────────────────────────────────────────
# 6) Dashboard + reports
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/summary")
async def summary(month: str = "", project_code: str = "", department: str = "",
                  payment_status: str = "", employee_q: str = "",
                  user: dict = Depends(require_permission("hr_payroll", "read"))):
    q: Dict[str, Any] = {}
    if month:
        q["month"] = month
    if project_code:
        q["project_code"] = project_code
    if department:
        q["department"] = department
    if payment_status:
        q["payment_status"] = payment_status
    if employee_q:
        q["$or"] = [{"employee_name": {"$regex": employee_q, "$options": "i"}},
                    {"emp_code": {"$regex": employee_q, "$options": "i"}}]
    rows = await db.salary_project_allocations.find(q, {"_id": 0}).sort("employee_name", 1).to_list(20000)

    booked = round(sum(_num(r.get("net")) for r in rows), 2)
    paid = round(sum(_num(r.get("paid_amount")) for r in rows), 2)
    gross = round(sum(_num(r.get("gross")) for r in rows), 2)

    by_project: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        pc = r.get("project_code") or "_UNALLOCATED_"
        agg = by_project.setdefault(pc, {"project_code": pc, "project_name": r.get("project_name") or pc,
                                         "headcount": 0, "gross": 0.0, "booked": 0.0,
                                         "paid": 0.0, "pending": 0.0})
        agg["headcount"] += 1
        agg["gross"] += _num(r.get("gross"))
        agg["booked"] += _num(r.get("net"))
        agg["paid"] += _num(r.get("paid_amount"))
        agg["pending"] += _num(r.get("pending_amount"))
    for agg in by_project.values():
        for k in ("gross", "booked", "paid", "pending"):
            agg[k] = round(agg[k], 2)

    booking = await db.salary_bookings.find_one({"month": month, "status": "booked"},
                                                {"_id": 0, "rows": 0}) if month else None
    run = await db.payroll_runs.find_one({"month": month}, {"_id": 0}) if month else None
    months = sorted({r.get("month") for r in await db.salary_project_allocations.find(
        {}, {"_id": 0, "month": 1}).to_list(20000)}, reverse=True)

    return {
        "month": month,
        "totals": {"headcount": len(rows), "gross": gross, "booked": booked,
                   "paid": paid, "pending": round(booked - paid, 2)},
        "by_project": sorted(by_project.values(), key=lambda x: -x["booked"]),
        "employees": rows,
        "booking": booking,
        "finance": {
            "finance_approval_status": (run or {}).get("finance_approval_status"),
            "accounts_posting_status": (run or {}).get("accounts_posting_status"),
            "accounts_je_number": (run or {}).get("accounts_je_number"),
        },
        "available_months": months,
    }


@router.get("/project-report")
async def project_report(month_from: str = "", month_to: str = "", project_code: str = "",
                         user: dict = Depends(require_permission("hr_payroll", "read"))):
    q: Dict[str, Any] = {}
    if month_from or month_to:
        rng: Dict[str, str] = {}
        if month_from:
            rng["$gte"] = month_from
        if month_to:
            rng["$lte"] = month_to
        q["month"] = rng
    if project_code:
        q["project_code"] = project_code
    rows = await db.salary_project_allocations.find(q, {"_id": 0}).to_list(50000)
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        key = (r.get("project_code") or "_UNALLOCATED_", r.get("month"))
        agg = by_key.setdefault(key, {"project_code": key[0], "project_name": r.get("project_name") or key[0],
                                      "month": key[1], "headcount": 0, "gross": 0.0,
                                      "booked": 0.0, "paid": 0.0, "pending": 0.0})
        agg["headcount"] += 1
        agg["gross"] += _num(r.get("gross"))
        agg["booked"] += _num(r.get("net"))
        agg["paid"] += _num(r.get("paid_amount"))
        agg["pending"] += _num(r.get("pending_amount"))
    out = []
    for agg in by_key.values():
        for k in ("gross", "booked", "paid", "pending"):
            agg[k] = round(agg[k], 2)
        out.append(agg)
    out.sort(key=lambda x: (x["project_code"], x["month"]))
    return {"rows": out, "totals": {
        "gross": round(sum(r["gross"] for r in out), 2),
        "booked": round(sum(r["booked"] for r in out), 2),
        "paid": round(sum(r["paid"] for r in out), 2),
        "pending": round(sum(r["pending"] for r in out), 2),
    }}


@router.get("/export")
async def export_booked(month: str,
                        user: dict = Depends(require_permission("hr_payroll", "read"))):
    """Re-export the booked month back into the client's Salary Export format."""
    slips = await db.payslips.find({"month": month}, {"_id": 0}).sort("employee_code", 1).to_list(20000)
    if not slips:
        raise HTTPException(404, f"No booked salary found for {month}")
    rows: List[Dict[str, Any]] = []
    for s in slips:
        e = s.get("earnings") or {}
        stat = s.get("statutory_deductions") or {}
        extra_e = {x.get("label", ""): _num(x.get("amount")) for x in (s.get("extra_earnings") or [])}
        ot = sum(v for k, v in extra_e.items() if k.lower().startswith("overtime"))
        bonus = sum(v for k, v in extra_e.items() if "bonus" in k.lower())
        extra_d = {x.get("label", ""): _num(x.get("amount")) for x in (s.get("extra_deductions") or [])}
        rows.append({
            "emp_id": s.get("employee_code") or "", "employee_name": s.get("employee_name") or "",
            "month_year": f"{month}-01",
            "pay_days": _num(s.get("paid_days")), "present_days": _num(s.get("present_days")),
            "basic": _num(e.get("basic")), "fix_rate": 0.0,
            "other_allo": _num(e.get("other_allowance")) + _num(e.get("special_allowance")) + _num(e.get("site_allowance")) + _num(e.get("medical")),
            "da": _num(e.get("da")), "hra": _num(e.get("hra")),
            "conv": _num(e.get("conveyance")), "att_bonus": bonus,
            "ot_amount": ot, "ot1_unit": _num(s.get("ot_hours")),
            "other_ded": extra_d.get("Other Deduction", 0.0), "advance": _num(s.get("advance_emi")),
            "lwf": extra_d.get("LWF", 0.0),
            "pf": _num(stat.get("pf")), "esi": _num(stat.get("esi")), "pt": _num(stat.get("professional_tax")),
            "total_earning": _num(s.get("total_earnings")), "total_deduction": _num(s.get("total_deductions")),
            "net_amount": _num(s.get("net_pay")),
            "basic_rt": 0.0, "fix_rate_rt": 0.0, "da_rt": 0.0, "ot_rate_rt": 0.0,
            "el_availed": 0.0, "cl_availed": 0.0, "remark": s.get("remark") or "",
            "project_name": s.get("project_name") or "", "project_code": s.get("project_code") or "",
            "department": s.get("department") or "", "designation": s.get("designation") or "",
            "grade": s.get("grade") or "", "father_name": s.get("father_name") or "",
            "uan_no": s.get("uan_no") or "", "esi_no": s.get("esi_no") or "",
        })
    buf = _build_workbook(rows, month, notes=[f"Booked salary export — {month}"])
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="salary-booked-{month}.xlsx"'},
    )
