"""Payroll module (Iter 49) — Indian-context monthly payroll.

Workflow
--------
1. **Payroll Master** (`db.payroll_master`) — one doc per employee with compensation structure
   (basic / hra / special / site_allowance / conveyance / medical / pf_applicable / esi_applicable
    / pt_state / fixed_other_earnings[] / fixed_other_deductions[] / pan / bank).
2. **Monthly Payroll Run** (`db.payroll_runs`) — preview→override→commit cycle:
   a) `/api/payroll/run/preview` calls the dept-gov attendance preflight FIRST.
      If `can_proceed=false`, returns blockers; HR fixes attendance, retries.
   b) Returns `payslips` array (one per employee) with computed earnings/deductions/net_pay.
   c) HR can `POST /api/payroll/run/override` to edit individual lines.
   d) `/api/payroll/run/commit` writes `db.payslips`, wires Advance EMI deductions
      into `db.advance_recoveries` (Iter 46 hook), updates `payroll_runs.status=committed`.

Statutory calculation (Indian rules):
- PF = 12% of Basic, capped at ₹1800 (basic ceiling ₹15k) when pf_applicable.
- ESI (Employee) = 0.75% of Gross when esi_applicable AND gross ≤ ₹21k.
- Professional Tax: pt_state-driven flat slab (₹200/mo for most states above ₹15k).
- TDS: simple `tds_override_pct` if set; full slab calc deferred to v2.
- LOP days reduce earnings proportionally (`paid_days / total_days`).
- Advance EMI auto-pulled from `db.employee_advances.emi` where status ∈ {paid, under_recovery}.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from core import db, get_current_user, now_iso, new_id

logger = logging.getLogger("erp.payroll")
router = APIRouter(prefix="/payroll", tags=["payroll"])

HR_ROLES = {"super_admin", "hr_executive", "general_manager", "director"}
FINANCE_ROLES = {"super_admin", "accounts_executive", "general_manager", "director"}

PT_SLAB_DEFAULT = 200  # ₹200/mo flat — applies to most Indian states above ₹15k salary
PF_BASIC_CEILING = 15000


# ════════════════════════════════════════════════════════════════════════
# 1) Payroll Master CRUD
# ════════════════════════════════════════════════════════════════════════
class PayrollMasterIn(BaseModel):
    employee_id: str
    basic: float = 0
    hra: float = 0
    special_allowance: float = 0
    site_allowance: float = 0
    conveyance: float = 0
    medical: float = 0
    pf_applicable: bool = True
    esi_applicable: bool = False
    pt_state: str = "GJ"   # Gujarat by default for ITL
    tds_override_pct: float = 0
    ot_rate_per_hour: float = 0   # 0 = auto (monthly fixed gross / (days × 8))
    ot_multiplier: float = 1.0
    fixed_other_earnings: list[dict] = Field(default_factory=list)
    fixed_other_deductions: list[dict] = Field(default_factory=list)
    pan: str = ""
    bank_name: str = ""
    bank_account: str = ""
    bank_ifsc: str = ""


@router.get("/master")
async def list_payroll_master(user: dict = Depends(get_current_user)):
    if user.get("role") not in HR_ROLES | FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    rows = await db.payroll_master.find({}, {"_id": 0}).limit(2000).to_list(2000)
    # Hydrate employee summary
    for r in rows:
        emp = await db.employees.find_one({"id": r["employee_id"]},
                                          {"_id": 0, "name": 1, "employee_id": 1, "emp_code": 1, "designation": 1, "departments": 1})
        if emp:
            r["employee_name"] = emp.get("name")
            r["employee_code"] = emp.get("employee_id") or emp.get("emp_code")
            r["designation"] = emp.get("designation")
            r["department"] = (emp.get("departments") or [None])[0]
    return rows


@router.get("/master/{employee_id}")
async def get_master(employee_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") not in HR_ROLES | FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    doc = await db.payroll_master.find_one({"employee_id": employee_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="master not found")
    return doc


@router.put("/master/{employee_id}")
async def upsert_master(employee_id: str, payload: PayrollMasterIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(status_code=403, detail="hr only")
    if payload.employee_id != employee_id:
        raise HTTPException(status_code=400, detail="employee_id mismatch")
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0, "id": 1})
    if not emp:
        raise HTTPException(status_code=404, detail="employee not found")
    update = {
        **payload.model_dump(),
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }
    existing = await db.payroll_master.find_one({"employee_id": employee_id}, {"_id": 0, "id": 1})
    if existing:
        await db.payroll_master.update_one({"employee_id": employee_id}, {"$set": update})
    else:
        update["id"] = new_id()
        update["created_at"] = now_iso()
        await db.payroll_master.insert_one(update)
    out = await db.payroll_master.find_one({"employee_id": employee_id}, {"_id": 0})
    return out


# ── Bulk upload: template + import ───────────────────────────────────────
MASTER_COLS = ["Employee Code", "Employee Name", "Basic", "HRA", "Special Allowance",
               "Site Allowance", "Conveyance", "Medical", "PF Applicable (Y/N)",
               "ESI Applicable (Y/N)", "PT State", "TDS Override %", "OT Rate/Hour",
               "OT Multiplier", "PAN", "Bank Name", "Bank Account", "Bank IFSC"]


@router.get("/master/bulk/template")
async def master_template(user: dict = Depends(get_current_user)):
    """Excel template: one row per active employee, existing master values prefilled."""
    if user.get("role") not in HR_ROLES:
        raise HTTPException(status_code=403, detail="hr only")
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from io import BytesIO
    wb = Workbook()
    ws = wb.active
    ws.title = "Payroll Master"
    ws.append(MASTER_COLS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F172A")
    masters = {m["employee_id"]: m async for m in db.payroll_master.find({}, {"_id": 0})}
    async for emp in db.employees.find({"active": {"$ne": False}},
                                       {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "emp_code": 1}).sort("name", 1):
        m = masters.get(emp["id"]) or {}
        ws.append([
            emp.get("employee_id") or emp.get("emp_code") or emp["id"][:8],
            emp.get("name") or "",
            m.get("basic") or 0, m.get("hra") or 0, m.get("special_allowance") or 0,
            m.get("site_allowance") or 0, m.get("conveyance") or 0, m.get("medical") or 0,
            "Y" if m.get("pf_applicable", True) else "N",
            "Y" if m.get("esi_applicable") else "N",
            m.get("pt_state") or "GJ", m.get("tds_override_pct") or 0,
            m.get("ot_rate_per_hour") or 0, m.get("ot_multiplier") or 1.0,
            m.get("pan") or "", m.get("bank_name") or "", m.get("bank_account") or "",
            m.get("bank_ifsc") or "",
        ])
    for i, w in enumerate([14, 26, 10, 10, 16, 14, 12, 10, 18, 18, 9, 14, 12, 12, 13, 18, 18, 13], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    notes = wb.create_sheet("Instructions")
    for line in [
        "Payroll Master Bulk Upload — Instructions",
        "1. Employee Code must match the code in Employee Master (column is pre-filled — do not edit).",
        "2. All amount columns are MONTHLY figures in ₹ (numbers only, no commas).",
        "3. PF/ESI Applicable: Y or N. PT State: 2-letter state code (GJ, MH, DL...).",
        "4. Rows already mapped are pre-filled with current values — edit and re-upload to update.",
        "5. Leave a row unchanged (all zeros, new employee) to skip it, or delete the row.",
    ]:
        notes.append([line])
    notes.column_dimensions["A"].width = 110
    buf = BytesIO()
    wb.save(buf)
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="payroll-master-template.xlsx"'})


def _yn(v) -> bool:
    return str(v or "").strip().lower() in {"y", "yes", "true", "1"}


def _num(v, field: str, row: int) -> float:
    if v is None or str(v).strip() == "":
        return 0.0
    try:
        n = float(str(v).replace(",", "").strip())
    except ValueError:
        raise ValueError(f"Row {row}: '{field}' must be a number (got '{v}')")
    if n < 0:
        raise ValueError(f"Row {row}: '{field}' cannot be negative")
    return n


@router.post("/master/bulk/import")
async def master_bulk_import(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upsert payroll_master rows from the uploaded template. Returns per-row results."""
    if user.get("role") not in HR_ROLES:
        raise HTTPException(status_code=403, detail="hr only")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload the .xlsx template file")
    from openpyxl import load_workbook
    from io import BytesIO
    try:
        wb = load_workbook(BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read the Excel file — is it a valid .xlsx?")
    ws = wb.worksheets[0]
    header = [str(c.value or "").strip() for c in ws[1]]
    if not header or header[0] != "Employee Code":
        raise HTTPException(status_code=400, detail="Unrecognized format — download the template and keep the header row")
    idx = {name: i for i, name in enumerate(header)}

    def cell(vals, col):
        i = idx.get(col)
        return vals[i] if i is not None and i < len(vals) else None

    emp_by_code: Dict[str, dict] = {}
    async for e in db.employees.find({}, {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "emp_code": 1}):
        for k in (e.get("employee_id"), e.get("emp_code"), e["id"][:8]):
            if k:
                emp_by_code[str(k).strip().lower()] = e

    created = updated = skipped = 0
    errors: List[Dict[str, Any]] = []
    for rno, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        code = str(cell(row, "Employee Code") or "").strip()
        if not code:
            continue
        emp = emp_by_code.get(code.lower())
        if not emp:
            errors.append({"row": rno, "employee": code, "error": "Employee code not found in Employee Master"})
            continue
        try:
            basic = _num(cell(row, "Basic"), "Basic", rno)
            hra = _num(cell(row, "HRA"), "HRA", rno)
            special = _num(cell(row, "Special Allowance"), "Special Allowance", rno)
            site = _num(cell(row, "Site Allowance"), "Site Allowance", rno)
            conv = _num(cell(row, "Conveyance"), "Conveyance", rno)
            med = _num(cell(row, "Medical"), "Medical", rno)
            tds = _num(cell(row, "TDS Override %"), "TDS Override %", rno)
            ot_rate = _num(cell(row, "OT Rate/Hour"), "OT Rate/Hour", rno)
            ot_mult = _num(cell(row, "OT Multiplier"), "OT Multiplier", rno) or 1.0
        except ValueError as e:
            errors.append({"row": rno, "employee": code, "error": str(e)})
            continue
        if tds > 100:
            errors.append({"row": rno, "employee": code, "error": f"Row {rno}: TDS Override % cannot exceed 100"})
            continue
        existing = await db.payroll_master.find_one({"employee_id": emp["id"]}, {"_id": 0, "id": 1})
        if basic + hra + special + site + conv + med <= 0 and not existing:
            skipped += 1
            continue
        pt_state = str(cell(row, "PT State") or "GJ").strip().upper()[:3] or "GJ"
        update = {
            "employee_id": emp["id"],
            "basic": basic, "hra": hra, "special_allowance": special,
            "site_allowance": site, "conveyance": conv, "medical": med,
            "pf_applicable": _yn(cell(row, "PF Applicable (Y/N)")),
            "esi_applicable": _yn(cell(row, "ESI Applicable (Y/N)")),
            "pt_state": pt_state,
            "tds_override_pct": tds,
            "ot_rate_per_hour": ot_rate, "ot_multiplier": ot_mult,
            "pan": str(cell(row, "PAN") or "").strip().upper(),
            "bank_name": str(cell(row, "Bank Name") or "").strip(),
            "bank_account": str(cell(row, "Bank Account") or "").strip(),
            "bank_ifsc": str(cell(row, "Bank IFSC") or "").strip().upper(),
            "updated_at": now_iso(),
            "updated_by": f"{user.get('name') or user.get('email')} (bulk upload)",
        }
        if existing:
            await db.payroll_master.update_one({"employee_id": emp["id"]}, {"$set": update})
            updated += 1
        else:
            update["id"] = new_id()
            update["created_at"] = now_iso()
            await db.payroll_master.insert_one(update)
            created += 1
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped,
            "error_count": len(errors), "errors": errors[:100]}


# ════════════════════════════════════════════════════════════════════════
# 2) Payroll calculation engine
# ════════════════════════════════════════════════════════════════════════
def _statutory(gross: float, basic: float, *, pf: bool, esi: bool, pt_state: str,
               tds_pct: float) -> dict:
    pf_amt = round(min(basic, PF_BASIC_CEILING) * 0.12, 2) if pf else 0
    esi_amt = round(gross * 0.0075, 2) if (esi and gross <= 21000) else 0
    pt_amt = PT_SLAB_DEFAULT if (gross > 15000) else 0
    tds_amt = round(gross * (tds_pct / 100), 2) if tds_pct else 0
    return {"pf": pf_amt, "esi": esi_amt, "professional_tax": pt_amt, "tds": tds_amt}


async def _compute_payslip(month: str, emp: dict, master: dict) -> dict:
    """Compute a single payslip from a payroll_master + attendance + active advances."""
    year, mm = int(month[:4]), int(month[5:7])
    total_days = monthrange(year, mm)[1]
    # ── Attendance link: derive Paid Days + OT hours from per-day attendance rows
    # Paid Days = P + 0.5×HD + L + WO + H + OD  (same formula as Attendance Summary)
    att_rows = await db.attendance.find(
        {"employee_id": emp["id"], "date": {"$regex": f"^{month}-"}},
        {"_id": 0, "status": 1, "overtime_hours": 1},
    ).to_list(400)
    ot_hours = 0.0
    if att_rows:
        w = {"present": 1, "on_duty": 1, "leave": 1, "weekly_off": 1, "holiday": 1, "half_day": 0.5}
        paid_days = sum(w.get(r.get("status") or "", 0) for r in att_rows)
        ot_hours = round(sum(float(r.get("overtime_hours") or 0) for r in att_rows), 2)
        lop_days = max(0.0, total_days - paid_days)
    else:
        # Legacy fallback (aggregated doc) → full month when no attendance exists
        att = await db.attendance.find_one({"employee_id": emp["id"], "month": month}, {"_id": 0}) or {}
        paid_days = float(att.get("paid_days", total_days))
        lop_days = float(att.get("lop_days", max(0, total_days - paid_days)))
    factor = max(0.0, min(1.0, paid_days / total_days))

    def _m(k: str) -> float:
        return float(master.get(k) or 0)

    base_earn = {
        "basic": round(_m("basic") * factor, 2),
        "hra": round(_m("hra") * factor, 2),
        "special_allowance": round(_m("special_allowance") * factor, 2),
        "site_allowance": round(_m("site_allowance") * factor, 2),
        "conveyance": round(_m("conveyance") * factor, 2),
        "medical": round(_m("medical") * factor, 2),
    }
    extra_earnings = []
    for r in master.get("fixed_other_earnings", []):
        extra_earnings.append({"label": r.get("label", "Other"), "amount": round(float(r.get("amount", 0)) * factor, 2)})

    # Overtime: hours from attendance × rate (master.ot_rate_per_hour, else auto
    # hourly = monthly fixed gross / (total_days × 8), scaled by ot_multiplier)
    ot_amount = 0.0
    if ot_hours > 0:
        rate = float(master.get("ot_rate_per_hour") or 0)
        if rate <= 0:
            monthly_fixed = (_m("basic") + _m("hra") + _m("special_allowance")
                             + _m("site_allowance") + _m("conveyance") + _m("medical"))
            rate = monthly_fixed / (total_days * 8) if monthly_fixed > 0 else 0
        ot_amount = round(ot_hours * rate * float(master.get("ot_multiplier") or 1.0), 2)
    else:
        # Legacy aggregated fallback
        ot_amount = float((await db.attendance.find_one({"employee_id": emp["id"], "month": month},
                                                        {"_id": 0, "ot_amount": 1}) or {}).get("ot_amount", 0)) if not att_rows else 0.0
    if ot_amount > 0:
        extra_earnings.append({"label": f"Overtime ({ot_hours} hrs)" if ot_hours else "Overtime", "amount": ot_amount})

    total_earnings = sum(base_earn.values()) + sum(e["amount"] for e in extra_earnings)

    stat = _statutory(
        gross=total_earnings, basic=base_earn["basic"],
        pf=master.get("pf_applicable", True),
        esi=master.get("esi_applicable", False),
        pt_state=master.get("pt_state", "GJ"),
        tds_pct=master.get("tds_override_pct", 0),
    )

    # Advance EMI from active advances (Iter 46 hook)
    advance_emi = 0
    advance_lines: list[dict] = []
    async for adv in db.employee_advances.find(
        {"employee_id": emp["id"], "status": {"$in": ["paid", "under_recovery"]}, "outstanding": {"$gt": 0}},
        {"_id": 0, "id": 1, "advance_no": 1, "dept_doc_no": 1, "emi": 1, "outstanding": 1, "repayment_start_month": 1},
    ):
        if (adv.get("repayment_start_month") or "") > month:
            continue
        already = await db.advance_recoveries.find_one({"advance_id": adv["id"], "month": month})
        if already:
            continue
        emi_amt = min(float(adv.get("emi", 0)), float(adv["outstanding"]))
        if emi_amt > 0:
            advance_emi += emi_amt
            advance_lines.append({"advance_id": adv["id"], "advance_no": adv.get("dept_doc_no") or adv["advance_no"], "amount": emi_amt})

    extra_deductions = []
    for r in master.get("fixed_other_deductions", []):
        extra_deductions.append({"label": r.get("label", "Other"), "amount": round(float(r.get("amount", 0)), 2)})

    total_deductions = sum(stat.values()) + advance_emi + sum(d["amount"] for d in extra_deductions)
    net_pay = round(total_earnings - total_deductions, 2)

    return {
        "employee_id": emp["id"],
        "employee_name": emp.get("name"),
        "employee_code": emp.get("employee_id") or emp.get("emp_code"),
        "department": (emp.get("departments") or [None])[0] or emp.get("department"),
        "designation": emp.get("designation"),
        "month": month,
        "total_days": total_days,
        "paid_days": round(paid_days, 1),
        "lop_days": round(lop_days, 1),
        "ot_hours": ot_hours,
        "attendance_linked": bool(att_rows),
        "earnings": base_earn,
        "extra_earnings": extra_earnings,
        "statutory_deductions": stat,
        "advance_emi": advance_emi,
        "advance_lines": advance_lines,
        "extra_deductions": extra_deductions,
        "total_earnings": round(total_earnings, 2),
        "total_deductions": round(total_deductions, 2),
        "net_pay": net_pay,
        "bank": {"name": master.get("bank_name"), "account": master.get("bank_account"), "ifsc": master.get("bank_ifsc")},
    }


# ════════════════════════════════════════════════════════════════════════
# 3) Monthly run — preview → override → commit
# ════════════════════════════════════════════════════════════════════════
class PayrollRunIn(BaseModel):
    month: str
    employee_ids: list[str] = Field(default_factory=list)
    skip_attendance_check: bool = False


@router.post("/run/preview")
async def preview_run(payload: PayrollRunIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(status_code=403, detail="hr only")
    if not payload.month or len(payload.month) != 7:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    # Iter 48 hook — payroll preflight (attendance approval check)
    if not payload.skip_attendance_check:
        from routers.dept_governance_router import payroll_attendance_check, PayrollPreflightIn
        check = await payroll_attendance_check(PayrollPreflightIn(month=payload.month), user)
        if not check["can_proceed"]:
            return {"preflight_failed": True, **check, "payslips": []}

    emp_q: dict = {"active": {"$ne": False}}
    if payload.employee_ids:
        emp_q["id"] = {"$in": payload.employee_ids}
    emps = await db.employees.find(emp_q, {"_id": 0}).to_list(5000)

    slips: list[dict] = []
    missing_master: list[dict] = []
    for emp in emps:
        master = await db.payroll_master.find_one({"employee_id": emp["id"]}, {"_id": 0})
        if not master:
            missing_master.append({"employee_id": emp["id"], "name": emp.get("name"), "code": emp.get("employee_id")})
            continue
        slip = await _compute_payslip(payload.month, emp, master)
        slips.append(slip)
    total_net = sum(s["net_pay"] for s in slips)
    total_earn = sum(s["total_earnings"] for s in slips)
    total_ded = sum(s["total_deductions"] for s in slips)
    return {
        "preflight_failed": False, "month": payload.month,
        "payslips": slips, "missing_master": missing_master,
        "totals": {"count": len(slips), "earnings": total_earn,
                   "deductions": total_ded, "net_pay": total_net},
    }


class PayslipOverrideIn(BaseModel):
    month: str
    employee_id: str
    earnings: Optional[dict] = None
    extra_earnings: Optional[list[dict]] = None
    extra_deductions: Optional[list[dict]] = None
    advance_emi: Optional[float] = None
    note: str = ""


@router.post("/run/override")
async def override_line(payload: PayslipOverrideIn, user: dict = Depends(get_current_user)):
    """Persist override for one employee for a given month (consumed by /commit)."""
    if user.get("role") not in HR_ROLES:
        raise HTTPException(status_code=403, detail="hr only")
    doc = {
        "month": payload.month, "employee_id": payload.employee_id,
        **{k: v for k, v in payload.model_dump().items() if v is not None and k not in {"month", "employee_id"}},
        "at": now_iso(), "by": user.get("name") or user.get("email"),
    }
    await db.payroll_overrides.update_one(
        {"month": payload.month, "employee_id": payload.employee_id},
        {"$set": doc}, upsert=True,
    )
    return {"ok": True}


class CommitIn(BaseModel):
    month: str
    skip_attendance_check: bool = False


@router.post("/run/commit")
async def commit_run(payload: CommitIn, user: dict = Depends(get_current_user)):
    """Generate persistent payslips, write advance_recoveries, mark run committed.
    Idempotent — running commit on the same month is a no-op for already-paid slips."""
    if user.get("role") not in HR_ROLES:
        raise HTTPException(status_code=403, detail="hr only")
    existing_run = await db.payroll_runs.find_one({"month": payload.month, "status": "committed"})
    if existing_run:
        raise HTTPException(status_code=400, detail=f"payroll for {payload.month} is already committed")

    preview = await preview_run(
        PayrollRunIn(month=payload.month, skip_attendance_check=payload.skip_attendance_check),
        user,
    )
    if preview.get("preflight_failed"):
        raise HTTPException(status_code=400, detail="attendance preflight not cleared")
    slips = preview["payslips"]

    # Apply overrides
    overrides = {o["employee_id"]: o async for o in db.payroll_overrides.find({"month": payload.month}, {"_id": 0})}
    for slip in slips:
        ov = overrides.get(slip["employee_id"])
        if not ov:
            continue
        if ov.get("earnings"):
            slip["earnings"].update(ov["earnings"])
        if ov.get("extra_earnings") is not None:
            slip["extra_earnings"] = ov["extra_earnings"]
        if ov.get("extra_deductions") is not None:
            slip["extra_deductions"] = ov["extra_deductions"]
        if ov.get("advance_emi") is not None:
            new_emi = float(ov["advance_emi"])
            old_emi = float(slip.get("advance_emi", 0))
            slip["advance_emi"] = new_emi
            # Sync advance_lines so the persisted recovery rows match the override.
            # Zero → clear all recovery side-effects. Non-zero → scale proportionally.
            if new_emi <= 0:
                slip["advance_lines"] = []
            elif old_emi > 0 and slip.get("advance_lines"):
                scale = new_emi / old_emi
                slip["advance_lines"] = [
                    {**ln, "amount": round(float(ln["amount"]) * scale, 2)}
                    for ln in slip["advance_lines"]
                ]
        # Recompute totals
        te = sum(slip["earnings"].values()) + sum(e["amount"] for e in slip["extra_earnings"])
        td = sum(slip["statutory_deductions"].values()) + slip["advance_emi"] + sum(d["amount"] for d in slip["extra_deductions"])
        slip["total_earnings"] = round(te, 2)
        slip["total_deductions"] = round(td, 2)
        slip["net_pay"] = round(te - td, 2)

    # Persist payslips
    committed: list[dict] = []
    for slip in slips:
        doc = {
            "id": new_id(), "dept_doc_no": f"HR/SAL/{payload.month.replace('-', '/')}/{slip['employee_code'] or slip['employee_id'][:6]}",
            "ownership_department": "hr",
            **slip,
            "status": "committed",
            "committed_at": now_iso(),
            "committed_by": user.get("name") or user.get("email"),
        }
        await db.payslips.update_one(
            {"month": slip["month"], "employee_id": slip["employee_id"]},
            {"$set": doc}, upsert=True,
        )
        committed.append({"employee_id": slip["employee_id"], "net_pay": slip["net_pay"]})

        # Wire advance recovery
        for line in slip.get("advance_lines", []):
            already = await db.advance_recoveries.find_one({"advance_id": line["advance_id"], "month": payload.month})
            if already:
                continue
            await db.advance_recoveries.insert_one({
                "id": new_id(), "advance_id": line["advance_id"],
                "employee_id": slip["employee_id"], "month": payload.month,
                "amount": line["amount"], "type": "emi",
                "note": f"Auto EMI deduction from payroll {payload.month}",
                "at": now_iso(), "by": user.get("name") or user.get("email"),
            })
            adv = await db.employee_advances.find_one({"id": line["advance_id"]}, {"_id": 0})
            if adv:
                new_recovered = float(adv.get("recovered_amount", 0)) + line["amount"]
                new_outstanding = max(0.0, float(adv["outstanding"]) - line["amount"])
                new_remaining = max(0, int(adv.get("remaining_installments", 0)) - 1)
                new_status = "closed" if new_outstanding <= 0.01 else "under_recovery"
                set_doc = {"recovered_amount": new_recovered, "outstanding": new_outstanding,
                           "remaining_installments": new_remaining, "status": new_status}
                if new_status == "closed":
                    set_doc["closed_at"] = now_iso()
                await db.employee_advances.update_one({"id": adv["id"]}, {"$set": set_doc})

    run_doc = {
        "id": new_id(), "month": payload.month, "status": "committed",
        "payslip_count": len(committed), "total_net": sum(s["net_pay"] for s in committed),
        "committed_at": now_iso(), "committed_by": user.get("name") or user.get("email"),
    }
    await db.payroll_runs.insert_one(run_doc)
    run_doc.pop("_id", None)
    return {"ok": True, "run": run_doc, "committed_count": len(committed)}


# ════════════════════════════════════════════════════════════════════════
# 4) Payslip queries
# ════════════════════════════════════════════════════════════════════════
@router.get("/payslips")
async def list_payslips(month: str = "", employee_id: str = "", user: dict = Depends(get_current_user)):
    q: dict = {}
    role = user.get("role")
    if role not in HR_ROLES | FINANCE_ROLES:
        # Employee can only see their own
        emp = await db.employees.find_one({"email": user.get("email")}, {"_id": 0, "id": 1})
        if not emp:
            return []
        q["employee_id"] = emp["id"]
    if month:
        q["month"] = month
    if employee_id and role in HR_ROLES | FINANCE_ROLES:
        q["employee_id"] = employee_id
    rows = await db.payslips.find(q, {"_id": 0}).sort("month", -1).limit(500).to_list(500)
    return rows


@router.get("/payslips/bulk-pdf")
async def payslips_bulk_pdf(month: str, user: dict = Depends(get_current_user)):
    """All committed payslips for a month as one PDF (HR/Finance only)."""
    if user.get("role") not in HR_ROLES | FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    slips = await db.payslips.find({"month": month}, {"_id": 0}).sort("employee_name", 1).to_list(1000)
    if not slips:
        raise HTTPException(status_code=404, detail=f"no payslips found for {month}")
    from pdf_generator import render_payslips_bundle_pdf
    emp_ids = [s["employee_id"] for s in slips]
    pans = {m["employee_id"]: m.get("pan") or "" async for m in db.payroll_master.find(
        {"employee_id": {"$in": emp_ids}}, {"_id": 0, "employee_id": 1, "pan": 1})}
    data = render_payslips_bundle_pdf(slips, month, pans=pans)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="Payslips-{month}.pdf"'})


async def _payslip_with_access(employee_id: str, month: str, user: dict) -> dict:
    doc = await db.payslips.find_one({"employee_id": employee_id, "month": month}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="payslip not found")
    if user.get("role") not in HR_ROLES | FINANCE_ROLES:
        emp = await db.employees.find_one({"email": user.get("email")}, {"_id": 0, "id": 1})
        if not emp or emp["id"] != employee_id:
            raise HTTPException(status_code=403, detail="not allowed")
    return doc


@router.get("/payslips/{employee_id}/{month}")
async def get_payslip(employee_id: str, month: str, user: dict = Depends(get_current_user)):
    return await _payslip_with_access(employee_id, month, user)


@router.get("/payslips/{employee_id}/{month}/pdf")
async def payslip_pdf(employee_id: str, month: str, user: dict = Depends(get_current_user)):
    doc = await _payslip_with_access(employee_id, month, user)
    from pdf_generator import render_payslip_pdf
    master = await db.payroll_master.find_one({"employee_id": employee_id}, {"_id": 0, "pan": 1}) or {}
    data = render_payslip_pdf(doc, pan=master.get("pan") or "")
    fname = f"Payslip-{doc.get('employee_code') or employee_id[:6]}-{month}.pdf"
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{fname}"'})


@router.get("/runs")
async def list_runs(user: dict = Depends(get_current_user)):
    if user.get("role") not in HR_ROLES | FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    rows = await db.payroll_runs.find({}, {"_id": 0}).sort("month", -1).limit(60).to_list(60)
    return rows


@router.get("/me")
async def my_payslips(user: dict = Depends(get_current_user)):
    """Employee self-service: my latest payslips."""
    emp = await db.employees.find_one({"email": user.get("email")}, {"_id": 0, "id": 1, "name": 1}) if user.get("email") else None
    if not emp:
        return {"linked": False, "payslips": []}
    rows = await db.payslips.find({"employee_id": emp["id"]}, {"_id": 0}).sort("month", -1).limit(12).to_list(12)
    return {"linked": True, "employee": emp, "payslips": rows}
