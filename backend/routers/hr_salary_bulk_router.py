"""Salary Structure bulk upload — Excel template + bulk create/update.

Workflow (HR → Salary · Payroll → Salary Structures):
  1. GET  /api/hr4/salary-structures/bulk/template → xlsx pre-filled with every
     active employee and their CURRENT salary breakup (match key = employee_id code).
  2. POST /api/hr4/salary-structures/bulk/import   → multipart xlsx upload.
     Each row is matched on the Employee ID code. A NEW effective-dated structure
     version is created, the previous open version is end-dated ("superseded"),
     the new one is auto-approved and synced to `payroll_master`.

Bad rows (unknown employee, negative/garbage amounts, bad date) are skipped with
a reason — the rest of the file still imports. Every run is snapshotted in
`hr_salary_bulk_imports` and each structure keeps its own audit trail.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from core import db, require_permission, now_iso, new_id
from audit import audit
from routers.hr_phase4_router import sync_structure_to_payroll_master

router = APIRouter(prefix="/hr4/salary-structures/bulk", tags=["hr-salary-bulk"])

WAGE_TYPES = {"monthly", "daily", "hourly", "shift", "piece_rate"}

NUMERIC_FIELDS = ["basic", "hra", "da", "conveyance", "site_allowance", "food_allowance",
                  "other_allowance", "overtime_rate", "professional_tax",
                  "attendance_bonus_amount"]
BOOL_FIELDS = ["attendance_bonus_applicable", "pf_applicable", "esic_applicable", "tds_applicable"]

# Template column order (first two are the match/display keys)
COLUMNS: List[str] = ["employee_id", "employee_name", "wage_type"] + NUMERIC_FIELDS + \
                     BOOL_FIELDS + ["effective_from", "effective_to", "remarks"]

HEADER_ALIASES = {
    "employee id": "employee_id", "emp id": "employee_id", "emp_code": "employee_id",
    "employee code": "employee_id", "employee_code": "employee_id", "empid": "employee_id",
    "name": "employee_name", "employee name": "employee_name",
    "basic salary": "basic", "basic_salary": "basic",
    "dearness_allowance": "da", "dearness allowance": "da",
    "house rent allowance": "hra", "house_rent_allowance": "hra",
    "ot rate": "overtime_rate", "ot_rate": "overtime_rate", "overtime rate": "overtime_rate",
    "pt": "professional_tax", "professional tax": "professional_tax",
    "attendance bonus": "attendance_bonus_amount",
    "pf": "pf_applicable", "esic": "esic_applicable", "esi": "esic_applicable", "tds": "tds_applicable",
    "effective from": "effective_from", "effective to": "effective_to",
    "wage type": "wage_type",
}

TRUTHY = {"1", "y", "yes", "true", "t", "applicable", "on"}
FALSY = {"0", "n", "no", "false", "f", "na", "not applicable", "off", "-", ""}


def _canon(h) -> str:
    key = str(h or "").strip()
    return HEADER_ALIASES.get(key.lower(), key.lower().replace(" ", "_"))


def _num(val, field: str) -> float:
    if val is None or (isinstance(val, str) and not val.strip()):
        return 0.0
    try:
        n = float(str(val).replace(",", "").replace("₹", "").strip())
    except Exception:
        raise ValueError(f"{field}: '{val}' is not a number")
    if n < 0:
        raise ValueError(f"{field} cannot be negative ({n})")
    return round(n, 2)


def _bool(val, default: bool) -> bool:
    if val is None or (isinstance(val, str) and not val.strip()):
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in TRUTHY:
        return True
    if s in FALSY:
        return False
    raise ValueError(f"'{val}' is not a yes/no value")


def _date(val, field: str, default: Optional[str] = None) -> Optional[str]:
    if val is None or (isinstance(val, str) and not val.strip()):
        return default
    if isinstance(val, datetime):
        return val.date().isoformat()
    s = str(val).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"{field}: '{val}' is not a valid date (use YYYY-MM-DD)")


async def _seq(prefix: str = "SS-") -> str:
    doc = await db.counters.find_one_and_update(
        {"id": f"seq_{prefix.rstrip('-')}"},
        {"$inc": {"n": 1}, "$setOnInsert": {"id": f"seq_{prefix.rstrip('-')}"}},
        upsert=True, return_document=True,
    )
    return f"{prefix}{datetime.now(timezone.utc).year}-{(doc or {}).get('n', 1):04d}"


@router.get("/template")
async def download_template(user: dict = Depends(require_permission("hr_onboarding", "write"))):
    """xlsx pre-filled with every active employee + their latest salary breakup."""
    employees = await db.employees.find(
        {"status": {"$nin": ["exited", "terminated", "inactive"]}},
        {"_id": 0, "id": 1, "employee_id": 1, "emp_code": 1, "name": 1, "department": 1, "designation": 1},
    ).sort("employee_id", 1).to_list(20000)

    latest: Dict[str, Dict[str, Any]] = {}
    async for s in db.hr_salary_structures.find({}, {"_id": 0}).sort("effective_from", 1):
        latest[s.get("employee_id")] = s

    wb = Workbook()
    ws = wb.active
    ws.title = "SalaryStructures"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = c.font.copy(bold=True)
    for e in employees:
        cur = latest.get(e["id"]) or {}
        row = []
        for col in COLUMNS:
            if col == "employee_id":
                row.append(e.get("employee_id") or e.get("emp_code") or e["id"])
            elif col == "employee_name":
                row.append(e.get("name") or "")
            elif col == "wage_type":
                row.append(cur.get("wage_type") or "monthly")
            elif col in NUMERIC_FIELDS:
                row.append(float(cur.get(col) or 0))
            elif col in BOOL_FIELDS:
                default = True if col == "pf_applicable" else False
                row.append("YES" if cur.get(col, default) else "NO")
            elif col == "effective_from":
                row.append(datetime.now(timezone.utc).date().isoformat())
            else:
                row.append(cur.get(col) or "")
        ws.append(row)
    for col_idx, col in enumerate(COLUMNS, 1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max(14, len(col) + 2)

    inst = wb.create_sheet("INSTRUCTIONS")
    for line in [
        ["INDIAN TRADE LINKS ERP — Salary Structure Bulk Upload"],
        [],
        ["1. `employee_id` is the match key (the Employee ID code, e.g. EMPITL162). Do not blank it."],
        ["2. `employee_name` is for your reference only — it is never written back."],
        ["3. Edit the amount columns. Blank cell = 0."],
        ["4. wage_type: monthly | daily | hourly | shift | piece_rate (blank = monthly)."],
        ["5. YES/NO columns: attendance_bonus_applicable, pf_applicable, esic_applicable, tds_applicable."],
        ["6. effective_from: YYYY-MM-DD (blank = today). A NEW structure version is created and the"],
        ["   employee's previous open version is end-dated the day before, so history is preserved."],
        ["7. Uploaded structures are auto-approved and synced straight to the payroll master."],
        ["8. Rows with an unknown employee_id, a negative amount or a bad date are skipped —"],
        ["   the rest of the file still imports and the upload summary lists every failure."],
        ["9. Delete the rows of employees you do not want to touch."],
        [],
        ["Columns:"],
        *[["", c] for c in COLUMNS],
    ]:
        inst.append(line)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"salary-structure-bulk-template-{datetime.now(timezone.utc).date()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/import")
async def import_bulk(request: Request, file: UploadFile = File(...),
                      user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Please upload a .xlsx file (use the downloaded template)")
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Invalid xlsx file: {e}")
    ws = wb["SalaryStructures"] if "SalaryStructures" in wb.sheetnames else wb.active
    if ws.max_row < 2:
        raise HTTPException(400, "Sheet is empty (need at least one data row)")

    headers = [_canon(c.value) for c in ws[1]]
    if "employee_id" not in headers:
        raise HTTPException(400, "Missing `employee_id` column in the header row")

    batch_id = new_id()
    summary = {
        "batch_id": batch_id, "file_name": file.filename,
        "total_rows": 0, "created": 0, "superseded": 0, "skipped": 0,
        "errors": [], "rows": [],
    }

    for ri, raw in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        d = dict(zip(headers, raw))
        code = d.get("employee_id")
        code = str(code).strip() if code is not None else ""
        if isinstance(raw, tuple) and all(v in (None, "") for v in raw):
            continue
        summary["total_rows"] += 1

        def fail(msg: str):
            summary["skipped"] += 1
            summary["errors"].append({"row": ri, "employee_id": code, "error": msg})
            summary["rows"].append({"row": ri, "employee_id": code, "action": "skipped", "error": msg})

        if not code:
            fail("employee_id is blank")
            continue
        emp = await db.employees.find_one(
            {"$or": [{"employee_id": code}, {"emp_code": code}, {"id": code}]}, {"_id": 0})
        if not emp:
            fail(f"No employee found with Employee ID '{code}'")
            continue

        try:
            wage_type = str(d.get("wage_type") or "monthly").strip().lower() or "monthly"
            if wage_type not in WAGE_TYPES:
                raise ValueError(f"wage_type '{d.get('wage_type')}' is invalid (monthly | daily | hourly | shift | piece_rate)")
            vals = {f: _num(d.get(f), f) for f in NUMERIC_FIELDS}
            flags = {f: _bool(d.get(f), True if f == "pf_applicable" else False) for f in BOOL_FIELDS}
            eff_from = _date(d.get("effective_from"), "effective_from",
                             datetime.now(timezone.utc).date().isoformat())
            eff_to = _date(d.get("effective_to"), "effective_to", None)
            if eff_to and eff_to < eff_from:
                raise ValueError("effective_to is before effective_from")
            if wage_type == "monthly" and vals["basic"] <= 0:
                raise ValueError("basic must be greater than 0 for a monthly wage type")
        except ValueError as ve:
            fail(str(ve))
            continue

        # End-date the employee's previous open version → full history retained
        prev_cut = (datetime.fromisoformat(eff_from).date() - timedelta(days=1)).isoformat()
        prev = await db.hr_salary_structures.update_many(
            {"employee_id": emp["id"], "approval_status": {"$ne": "rejected"},
             "effective_from": {"$lt": eff_from},
             "$or": [{"effective_to": None}, {"effective_to": {"$exists": False}},
                     {"effective_to": {"$gte": eff_from}}]},
            {"$set": {"effective_to": prev_cut, "status": "superseded",
                      "superseded_at": now_iso(), "superseded_by_batch": batch_id}},
        )
        summary["superseded"] += prev.modified_count

        doc = {
            "id": new_id(),
            "structure_no": await _seq(),
            "employee_id": emp["id"],
            "employee_name": emp.get("name"),
            "employee_code": emp.get("employee_id") or emp.get("emp_code") or emp["id"],
            "department": (emp.get("departments") or [None])[0] or emp.get("department"),
            "wage_type": wage_type,
            **vals, **flags,
            "effective_from": eff_from,
            "effective_to": eff_to,
            "remarks": (str(d.get("remarks")).strip() if d.get("remarks") else None),
            "approval_status": "approved",
            "status": "active",
            "approved_by_id": user["id"],
            "approved_by_name": user.get("name") or user.get("email"),
            "approved_at": now_iso(),
            "approval_remarks": "Auto-approved via bulk Excel upload",
            "source": "bulk_import",
            "import_batch_id": batch_id,
            "created_at": now_iso(),
            "created_by": user["id"],
            "created_by_name": user.get("name") or user.get("email"),
        }
        await db.hr_salary_structures.insert_one(doc)
        doc.pop("_id", None)
        await db.hr_salary_structure_audit.insert_one({
            "id": new_id(), "structure_id": doc["id"], "action": "bulk_import_create",
            "before": None, "after": doc, "by_id": user["id"],
            "by_name": user.get("name") or user.get("email"),
            "ip": request.client.host if request and request.client else "",
            "at": now_iso(), "batch_id": batch_id,
        })
        await sync_structure_to_payroll_master(doc, doc["id"])

        summary["created"] += 1
        summary["rows"].append({
            "row": ri, "employee_id": code, "employee_name": emp.get("name"),
            "structure_no": doc["structure_no"], "action": "created",
            "basic": vals["basic"], "gross": round(sum(
                vals[f] for f in ("basic", "hra", "da", "conveyance", "site_allowance",
                                  "food_allowance", "other_allowance")), 2),
            "effective_from": eff_from,
        })

    await db.hr_salary_bulk_imports.insert_one({
        "id": batch_id, "file_name": file.filename, "at": now_iso(),
        "by_id": user["id"], "by_name": user.get("name") or user.get("email"),
        **{k: summary[k] for k in ("total_rows", "created", "superseded", "skipped")},
        "errors": summary["errors"], "rows": summary["rows"],
    })
    await audit(user=user, action="salary_structure_bulk_import", resource="hr_salary_structures",
                record_id=batch_id,
                after={k: summary[k] for k in ("file_name", "total_rows", "created", "superseded", "skipped")})
    return summary


@router.get("/history")
async def import_history(limit: int = 20,
                         user: dict = Depends(require_permission("hr_onboarding", "read"))):
    return await db.hr_salary_bulk_imports.find(
        {}, {"_id": 0, "rows": 0}).sort("at", -1).limit(limit).to_list(limit)
