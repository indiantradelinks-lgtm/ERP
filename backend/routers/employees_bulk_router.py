"""Employees bulk update — Excel export template + Excel import patch.

Workflow:
  1. GET  /api/employees/bulk-template      → xlsx with current employees + the
     allowed editable columns in a fixed order. Includes hidden `id` for matching.
  2. POST /api/employees/bulk-import        → multipart xlsx upload. Each row is
     matched by `id` (preferred) or `employee_id`, and only ALLOWED_FIELDS are
     patched. Returns per-row summary + audit log.

Audit:
  Every update writes one entry to `audit_logs` AND a snapshot to
  `employee_bulk_updates` so changes are recoverable.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/employees/bulk", tags=["employees-bulk"])


# Fields the user is allowed to bulk-edit. Anything else in the xlsx is ignored.
ALLOWED_FIELDS = [
    "name", "employee_id", "master_category", "department", "designation", "skill_name",
    "father_name",
    "phone", "email", "status", "role", "employment_type",
    "date_of_joining", "date_of_birth", "gender",
    "pan", "aadhaar", "aadhaar_number", "pf_uan", "esic_no",
    "bank_name", "bank_account", "bank_ifsc",
    "address", "city", "state", "pincode",
    "contractor_name", "contractor_license_no",
    "contract_start_date", "contract_end_date",
    "daily_wage", "working_days_per_month",
    "safety_induction", "medical_fitness", "medical_fitness_valid_till",
    "current_project_code", "current_site_code",
]

# Columns added for display only — we skip them when applying updates.
DISPLAY_ONLY = {"_status_hint", "_warning"}

# Accepted spellings for master_category → canonical value
_MASTER_ALIASES = {
    "employee": "employee", "employee master": "employee", "staff": "employee",
    "worker": "worker", "labour": "worker", "labor": "worker",
    "worker master": "worker", "worker/labour": "worker", "worker / labour": "worker",
    "worker-labour": "worker", "worker-labour master": "worker",
    "worker / labour master": "worker", "worker/labour master": "worker",
}


def _normalise_master_category(val) -> str:
    key = str(val).strip().lower()
    out = _MASTER_ALIASES.get(key)
    if not out:
        raise ValueError(f"invalid master_category '{val}' — use 'employee' or 'worker'")
    return out


@router.get("/template")
async def download_template(user: dict = Depends(require_permission("employees", "write"))):
    """Download current employees as an editable xlsx template."""
    rows = await db.employees.find({}, {"_id": 0}).sort("employee_id", 1).to_list(20000)
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"

    headers = ["id"] + ALLOWED_FIELDS
    ws.append(headers)
    for col_idx, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col_idx)
        c.font = c.font.copy(bold=True)
    for r in rows:
        vals = []
        for h in headers:
            if h == "master_category":
                vals.append(r.get("master_category") or "employee")
            else:
                vals.append(r.get(h, "") if r.get(h) is not None else "")
        ws.append(vals)

    # Instructions sheet
    inst = wb.create_sheet("INSTRUCTIONS")
    inst.append(["INDIAN TRADE LINKS ERP — Employee Bulk Update"])
    inst.append([])
    inst.append(["1. Do NOT modify the `id` column (column A). It is the match key."])
    inst.append(["2. Edit any of the allowed columns. Empty cell = leave existing value unchanged."])
    inst.append(["3. To explicitly clear a value, type the literal text:  __CLEAR__"])
    inst.append(["4. Adding NEW rows (blank id) will create new employees."])
    inst.append(["5. Save as .xlsx and re-upload via the Employees page → Bulk Update."])
    inst.append(["6. master_category: 'employee' (Employee Master) or 'worker' (Worker/Labour Master)."])
    inst.append(["   Changing it moves the record to the other master instantly — no data is lost."])
    inst.append([])
    inst.append(["Allowed columns:"])
    for f in ALLOWED_FIELDS:
        inst.append(["", f])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"employees-bulk-template-{datetime.now(timezone.utc).date()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/import")
async def import_bulk(file: UploadFile = File(...),
                      user: dict = Depends(require_permission("employees", "write"))):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Please upload a .xlsx file")
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Invalid xlsx file: {e}")
    if "Employees" in wb.sheetnames:
        ws = wb["Employees"]
    else:
        ws = wb.active
    if ws.max_row < 2:
        raise HTTPException(400, "Sheet is empty (need at least one data row)")

    # Read header row
    headers: List[str] = []
    for cell in ws[1]:
        headers.append((cell.value or "").strip())
    if "id" not in headers:
        raise HTTPException(400, "Missing `id` column in header row")

    summary = {
        "total_rows": 0, "updated": 0, "created": 0, "unchanged": 0,
        "already_updated": 0, "skipped": 0, "errors": [],
    }
    per_row = []
    snapshot_id = new_id()
    snapshot_rows = []

    for ri, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        summary["total_rows"] += 1
        row_dict = dict(zip(headers, row))
        emp_id = (row_dict.get("id") or "").strip() if isinstance(row_dict.get("id"), str) else row_dict.get("id")

        # Build a patch dict of only allowed fields
        patch: Dict[str, Any] = {}
        row_error = None
        for f in ALLOWED_FIELDS:
            if f not in row_dict:
                continue
            val = row_dict[f]
            if val is None or (isinstance(val, str) and val.strip() == ""):
                continue
            if isinstance(val, str) and val.strip() == "__CLEAR__":
                # master_category can never be blank — clearing resets to Employee Master
                patch[f] = "employee" if f == "master_category" else None
                continue
            if f == "master_category":
                try:
                    patch[f] = _normalise_master_category(val)
                except ValueError as ve:
                    row_error = str(ve)
                    break
                continue
            patch[f] = val

        if row_error:
            summary["skipped"] += 1
            summary["errors"].append({"row": ri, "id": emp_id, "error": row_error})
            per_row.append({"row": ri, "id": emp_id, "action": "skipped", "error": row_error})
            continue

        if not patch and emp_id:
            summary["unchanged"] += 1
            per_row.append({"row": ri, "id": emp_id, "action": "unchanged"})
            continue

        try:
            if emp_id:
                existing = await db.employees.find_one({"id": emp_id}, {"_id": 0})
                if not existing:
                    # Match by employee_id (code) as fallback
                    existing = await db.employees.find_one({"employee_id": emp_id}, {"_id": 0})
                if not existing:
                    summary["skipped"] += 1
                    summary["errors"].append({"row": ri, "id": emp_id, "error": "employee not found"})
                    per_row.append({"row": ri, "id": emp_id, "action": "skipped", "error": "not found"})
                    continue
                # Diff against existing — drop fields whose value already matches.
                # This avoids inflating "updated" counts and audit noise when the
                # user only edited one cell in a wide template row.
                diff_patch: Dict[str, Any] = {}
                for k, v in patch.items():
                    cur = existing.get(k)
                    # Normalize whitespace for string compares
                    cur_n = cur.strip() if isinstance(cur, str) else cur
                    v_n = v.strip() if isinstance(v, str) else v
                    if cur_n != v_n:
                        diff_patch[k] = v
                if not diff_patch:
                    summary["already_updated"] += 1
                    msg = f"Employee already updated — data for '{existing.get('name')}' already matches, no changes applied"
                    summary["errors"].append({"row": ri, "id": existing["id"], "error": msg})
                    per_row.append({"row": ri, "id": existing["id"], "action": "already_updated", "error": msg})
                    continue
                if existing.get("bulk_update_snapshot_id"):
                    prev = await db.employee_bulk_updates.find_one(
                        {"id": existing["bulk_update_snapshot_id"]}, {"_id": 0, "at": 1, "by_name": 1})
                    detail = ""
                    if prev:
                        when = (prev.get("at") or "")[:16].replace("T", " ")
                        detail = f" on {when} by {prev.get('by_name')}"
                    msg = (f"Employee already updated — '{existing.get('name')}' was modified by a previous bulk update{detail}. "
                           "Edit the record individually if a change is really needed.")
                    summary["already_updated"] += 1
                    summary["errors"].append({"row": ri, "id": existing["id"], "error": msg})
                    per_row.append({"row": ri, "id": existing["id"], "action": "already_updated", "error": msg})
                    continue
                # Apply update
                diff_patch["updated_at"] = now_iso()
                diff_patch["updated_by"] = user.get("name") or user.get("email")
                diff_patch["bulk_update_snapshot_id"] = snapshot_id
                await db.employees.update_one({"id": existing["id"]}, {"$set": diff_patch})
                snapshot_rows.append({"id": existing["id"], "before": existing, "patch": diff_patch})
                summary["updated"] += 1
                per_row.append({"row": ri, "id": existing["id"], "action": "updated",
                                "fields": list(k for k in diff_patch if k not in ("updated_at", "updated_by", "bulk_update_snapshot_id"))})
            else:
                # New employee — must at least have name
                if not patch.get("name"):
                    summary["skipped"] += 1
                    summary["errors"].append({"row": ri, "error": "blank id and blank name — row ignored"})
                    per_row.append({"row": ri, "action": "skipped", "error": "blank id+name"})
                    continue
                dup_q = []
                if patch.get("employee_id"):
                    dup_q.append({"employee_id": patch["employee_id"]})
                aad = patch.get("aadhaar_number") or patch.get("aadhaar")
                if aad:
                    dup_q.append({"$or": [{"aadhaar_number": aad}, {"aadhaar": aad}]})
                if patch.get("name") and patch.get("father_name"):
                    import re as _re
                    dup_q.append({"name": {"$regex": f"^{_re.escape(str(patch['name']).strip())}$", "$options": "i"},
                                  "father_name": {"$regex": f"^{_re.escape(str(patch['father_name']).strip())}$", "$options": "i"}})
                dup = await db.employees.find_one({"$or": dup_q}, {"_id": 0, "name": 1, "employee_id": 1}) if dup_q else None
                if dup:
                    msg = (f"Employee already updated — '{dup.get('name')}' (Emp ID {dup.get('employee_id') or '—'}) "
                           "already exists in the master; duplicate row not created")
                    summary["already_updated"] += 1
                    summary["errors"].append({"row": ri, "error": msg})
                    per_row.append({"row": ri, "action": "already_updated", "error": msg})
                    continue
                new_doc = {
                    "id": new_id(),
                    "status": "active",
                    "master_category": "employee",
                    "created_at": now_iso(),
                    "created_by": user.get("name") or user.get("email"),
                    "bulk_update_snapshot_id": snapshot_id,
                    **patch,
                }
                await db.employees.insert_one(new_doc)
                new_doc.pop("_id", None)
                summary["created"] += 1
                per_row.append({"row": ri, "id": new_doc["id"], "action": "created"})
        except Exception as e:
            summary["skipped"] += 1
            summary["errors"].append({"row": ri, "id": emp_id, "error": str(e)})
            per_row.append({"row": ri, "id": emp_id, "action": "error", "error": str(e)})

    # Persist a snapshot for rollback/audit
    await db.employee_bulk_updates.insert_one({
        "id": snapshot_id,
        "filename": file.filename,
        "at": now_iso(),
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "summary": summary,
        "rows": snapshot_rows[:2000],   # cap snapshot size
    })
    try:
        await audit(user=user, action="bulk_update", resource="employees",
                    record_id=snapshot_id, after=summary, ip="bulk")
    except Exception:
        pass

    return {"snapshot_id": snapshot_id, "summary": summary, "per_row": per_row[:500]}


@router.get("/history")
async def history(user: dict = Depends(require_permission("employees", "read"))):
    rows = await db.employee_bulk_updates.find(
        {}, {"_id": 0, "rows": 0}).sort("at", -1).limit(50).to_list(50)
    return rows
