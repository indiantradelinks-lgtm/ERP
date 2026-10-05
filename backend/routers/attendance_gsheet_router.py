"""HR · Attendance Center — Google Sheets attendance & OT automation.

The client maintains monthly attendance in Google Sheets (one sheet per site/month).
Layout handled (fully dynamic — no per-month code change):

    row 1  : title cell e.g. "Attendance Sheet 18_10_MYSORE_Sep'26"  → base month/year
    row n  : header row containing "E-Code"; date columns are "1-Sep", "2-Sep" … "1-Oct"
    pairs  : every employee occupies TWO rows —
               • row A (has E-Code) → day-wise status  (P / WO / A / HD / CL / EL / H / OD)
               • row B (blank E-Code) → day-wise OT hours

Employees are matched on **E-Code → employees.emp_code / employee_id**, and the
attendance row is stamped with the employee's project from the ERP master, so
project-wise attendance follows the mapping automatically.

Only HR-authorised users (`attendance:write`) can configure or sync. Approved or
locked attendance rows are never overwritten — they are reported as skipped.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from audit import audit
from core import db, logger, new_id, now_iso, require_permission

router = APIRouter(prefix="/hr2/attendance-gsheet", tags=["attendance-gsheet"])

CONFIG_ID = "default"
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# Sheet token → (ERP attendance status, leave_type)
STATUS_MAP: Dict[str, tuple[str, Optional[str]]] = {
    "P": ("present", None), "PR": ("present", None), "PP": ("present", None),
    "WO": ("weekly_off", None), "W/O": ("weekly_off", None), "WOFF": ("weekly_off", None),
    "A": ("absent", None), "AB": ("absent", None), "ABS": ("absent", None),
    "H": ("holiday", None), "HO": ("holiday", None), "PH": ("holiday", None),
    "HD": ("half_day", None), "H/D": ("half_day", None), "HF": ("half_day", None),
    "CL": ("leave", "CL"), "EL": ("leave", "EL"), "SL": ("leave", "SL"),
    "PL": ("leave", "PL"), "L": ("leave", None), "LWP": ("absent", "LWP"),
    "OD": ("on_duty", None), "OT": ("present", None), "T": ("on_duty", None),
}
DATE_COL_RE = re.compile(r"^\s*(\d{1,2})[-/\s]([A-Za-z]{3,})\.?\s*$")
TITLE_MONTH_RE = re.compile(r"([A-Za-z]{3,})[\s'`_-]*(\d{2,4})")


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
class ConfigIn(BaseModel):
    sheet_url: str
    gid: Optional[str] = None
    enabled: bool = True
    auto_sync: bool = True
    sync_hour_ist: int = 7          # daily auto-sync time (IST)
    sync_minute_ist: int = 0
    label: str = ""


def _parse_sheet_url(url: str) -> tuple[str, str]:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url or "")
    if not m:
        raise HTTPException(400, "That does not look like a Google Sheets link")
    gid = ""
    g = re.search(r"[#&?]gid=(\d+)", url)
    if g:
        gid = g.group(1)
    return m.group(1), gid


@router.get("/config")
async def get_config(user: dict = Depends(require_permission("attendance", "read"))):
    cfg = await db.gsheet_attendance_config.find_one({"id": CONFIG_ID}, {"_id": 0})
    last = await db.gsheet_attendance_runs.find_one({}, {"_id": 0}, sort=[("started_at", -1)])
    return {"config": cfg, "last_run": last}


@router.put("/config")
async def save_config(p: ConfigIn, request: Request,
                      user: dict = Depends(require_permission("attendance", "write"))):
    sheet_id, url_gid = _parse_sheet_url(p.sheet_url)
    gid = (p.gid or url_gid or "0").strip()
    doc = {
        "id": CONFIG_ID, "sheet_url": p.sheet_url.strip(), "sheet_id": sheet_id, "gid": gid,
        "enabled": p.enabled, "auto_sync": p.auto_sync,
        "sync_hour_ist": max(0, min(23, p.sync_hour_ist)),
        "sync_minute_ist": max(0, min(59, p.sync_minute_ist)),
        "label": p.label.strip(), "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }
    await db.gsheet_attendance_config.update_one({"id": CONFIG_ID}, {"$set": doc}, upsert=True)
    await audit(user=user, action="gsheet_attendance_config", resource="attendance",
                record_id=CONFIG_ID, after=doc,
                ip=request.headers.get("x-forwarded-for", "unknown"))
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# Fetch + parse
# ──────────────────────────────────────────────────────────────────────────────
async def _fetch_csv(sheet_id: str, gid: str) -> List[List[str]]:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid or '0'}"
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as cx:
        r = await cx.get(url)
    if r.status_code != 200 or "<html" in r.text[:200].lower():
        raise HTTPException(400, "Could not read the sheet. Open it in Google Sheets → Share → "
                                 "General access → 'Anyone with the link' (Viewer), then sync again.")
    return list(csv.reader(io.StringIO(r.text)))


def _base_month(rows: List[List[str]]) -> tuple[int, int]:
    """Month/year from the sheet title (e.g. ...Sep'26) — falls back to today."""
    for row in rows[:3]:
        for cell in row[:6]:
            for m in TITLE_MONTH_RE.finditer(cell or ""):
                if m.group(1).lower()[:3] in MONTHS:
                    yr = int(m.group(2))
                    return MONTHS[m.group(1).lower()[:3]], (2000 + yr if yr < 100 else yr)
    now = datetime.now(timezone.utc)
    return now.month, now.year


def _parse_sheet(rows: List[List[str]]) -> Dict[str, Any]:
    hdr_idx = next((i for i, r in enumerate(rows[:25])
                    if any("e-code" in (c or "").strip().lower() for c in r)), None)
    if hdr_idx is None:
        raise HTTPException(400, "Could not find the header row — the sheet must have an 'E-Code' column")
    header = rows[hdr_idx]
    code_col = next(i for i, c in enumerate(header) if "e-code" in (c or "").strip().lower())
    name_col = next((i for i, c in enumerate(header) if "employee name" in (c or "").strip().lower()), None)

    base_month, base_year = _base_month(rows)
    date_cols: List[tuple[int, str]] = []
    month, year, prev = base_month, base_year, base_month
    for i, c in enumerate(header):
        m = DATE_COL_RE.match(c or "")
        if not m:
            continue
        mon = MONTHS.get(m.group(2).lower()[:3])
        if not mon:
            continue
        if mon != prev:
            if mon < prev:
                year += 1
            prev = mon
        day = int(m.group(1))
        try:
            date_cols.append((i, datetime(year, mon, day).date().isoformat()))
        except ValueError:
            continue
    if not date_cols:
        raise HTTPException(400, "No date columns (like '1-Sep') found in the header row")

    employees: List[Dict[str, Any]] = []
    i = hdr_idx + 1
    while i < len(rows):
        row = rows[i]
        code = (row[code_col] if code_col < len(row) else "").strip()
        if not code:
            i += 1
            continue
        ot_row = rows[i + 1] if i + 1 < len(rows) else []
        ot_has_code = bool((ot_row[code_col] if code_col < len(ot_row) else "").strip())
        employees.append({
            "emp_code": code,
            "name": (row[name_col] if name_col is not None and name_col < len(row) else "").strip(),
            "days": [{"date": d,
                      "status_raw": (row[ci] if ci < len(row) else "").strip(),
                      "ot_raw": "" if ot_has_code else (ot_row[ci] if ci < len(ot_row) else "").strip()}
                     for ci, d in date_cols],
        })
        i += 1 if ot_has_code else 2
    return {"month": f"{base_year}-{base_month:02d}", "date_count": len(date_cols),
            "employees": employees,
            "date_from": date_cols[0][1], "date_to": date_cols[-1][1]}


def _num(v: str) -> float:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Sync
# ──────────────────────────────────────────────────────────────────────────────
class SyncIn(BaseModel):
    dry_run: bool = False


async def _run_sync(*, actor: str, trigger: str, dry_run: bool = False) -> Dict[str, Any]:
    cfg = await db.gsheet_attendance_config.find_one({"id": CONFIG_ID}, {"_id": 0})
    if not cfg:
        raise HTTPException(400, "Connect the Google attendance sheet first")
    if not cfg.get("enabled") and trigger != "manual":
        return {"skipped": "connection disabled"}

    started = now_iso()
    rows = await _fetch_csv(cfg["sheet_id"], cfg.get("gid") or "0")
    parsed = _parse_sheet(rows)

    emps = await db.employees.find(
        {}, {"_id": 0, "id": 1, "name": 1, "emp_code": 1, "employee_id": 1,
             "current_project_code": 1, "current_project_name": 1, "departments": 1,
             "department": 1, "designation": 1}).to_list(20000)
    by_code: Dict[str, dict] = {}
    for e in emps:
        for key in (e.get("emp_code"), e.get("employee_id")):
            if key:
                by_code.setdefault(str(key).strip().upper(), e)
    proj_names = {p["code"]: p.get("name") async for p in
                  db.projects.find({}, {"_id": 0, "code": 1, "name": 1})}

    imported = updated = skipped_locked = unchanged = failed = 0
    unmatched: Dict[str, str] = {}
    errors: List[Dict[str, str]] = []
    matched_employees = 0

    for emp_row in parsed["employees"]:
        emp = by_code.get(emp_row["emp_code"].upper())
        if not emp:
            unmatched[emp_row["emp_code"]] = emp_row["name"]
            failed += sum(1 for d in emp_row["days"] if d["status_raw"])
            continue
        matched_employees += 1
        pcode = (emp.get("current_project_code") or "").strip()
        base = {
            "employee_id": emp["id"], "employee_name": emp.get("name"),
            "emp_code": emp.get("emp_code") or emp.get("employee_id"),
            "department": (emp.get("departments") or [None])[0] or emp.get("department") or "",
            "designation": emp.get("designation") or "",
            "project_code": pcode or None,
            "project_name": emp.get("current_project_name") or proj_names.get(pcode),
            "source": "google_sheet", "source_sheet_id": cfg["sheet_id"],
        }
        for d in emp_row["days"]:
            raw = (d["status_raw"] or "").strip()
            ot = _num(d["ot_raw"])
            if not raw and ot <= 0:
                continue
            token = raw.upper().replace(" ", "")
            mapped = STATUS_MAP.get(token)
            if raw and not mapped:
                failed += 1
                if len(errors) < 200:
                    errors.append({"emp_code": emp_row["emp_code"], "employee_name": emp.get("name"),
                                   "date": d["date"],
                                   "error": f"Unknown attendance code '{raw}' — add it to the sheet legend"})
                continue
            status, leave_type = mapped if mapped else ("present", None)

            existing = await db.attendance.find_one(
                {"employee_id": emp["id"], "date": d["date"]}, {"_id": 0})
            if existing and (existing.get("approved") or existing.get("locked")
                             or existing.get("status_locked")
                             or existing.get("approval_status") == "approved"
                             or existing.get("payroll_locked")):
                skipped_locked += 1
                continue
            doc = {**base, "date": d["date"], "status": status,
                   "leave_type": leave_type, "overtime_hours": ot,
                   "synced_at": now_iso(), "synced_by": actor, "sync_trigger": trigger}
            if existing:
                same = (existing.get("status") == status
                        and _num(existing.get("overtime_hours")) == ot
                        and (existing.get("project_code") or None) == base["project_code"])
                if same:
                    unchanged += 1
                    continue
                if not dry_run:
                    await db.attendance.update_one({"id": existing["id"]}, {"$set": doc})
                updated += 1
            else:
                if not dry_run:
                    await db.attendance.insert_one({"id": new_id(), **doc,
                                                    "created_at": now_iso(), "created_by": actor})
                imported += 1

    for code, name in list(unmatched.items())[:200]:
        errors.append({"emp_code": code, "employee_name": name, "date": "",
                       "error": "E-Code not found in ERP Employee Master (add the employee or fix the Legacy Emp Code)"})

    run = {
        "id": new_id(), "started_at": started, "finished_at": now_iso(),
        "trigger": trigger, "dry_run": dry_run, "by": actor,
        "sheet_id": cfg["sheet_id"], "gid": cfg.get("gid"), "sheet_url": cfg.get("sheet_url"),
        "month": parsed["month"], "date_from": parsed["date_from"], "date_to": parsed["date_to"],
        "sheet_employees": len(parsed["employees"]), "matched_employees": matched_employees,
        "unmatched_employees": len(unmatched),
        "imported": imported, "updated": updated, "unchanged": unchanged,
        "skipped_locked": skipped_locked, "failed": failed,
        "errors": errors[:300], "status": "success" if not failed else "partial",
    }
    await db.gsheet_attendance_runs.insert_one(dict(run))
    if not dry_run:
        await db.gsheet_attendance_config.update_one({"id": CONFIG_ID}, {"$set": {
            "last_sync_at": run["finished_at"], "last_sync_by": actor,
            "last_sync_trigger": trigger, "last_sync_status": run["status"],
            "last_sync_counts": {k: run[k] for k in
                                 ("imported", "updated", "unchanged", "skipped_locked", "failed")}}})
    run.pop("_id", None)
    return run


@router.post("/sync")
async def manual_sync(p: SyncIn, request: Request,
                      user: dict = Depends(require_permission("attendance", "write"))):
    actor = user.get("name") or user.get("email")
    run = await _run_sync(actor=actor, trigger="manual", dry_run=p.dry_run)
    await audit(user=user, action="gsheet_attendance_sync", resource="attendance",
                record_id=run.get("id"),
                after={k: run.get(k) for k in ("month", "imported", "updated", "failed", "dry_run")},
                ip=request.headers.get("x-forwarded-for", "unknown"))
    return run


@router.get("/runs")
async def list_runs(limit: int = 20,
                    user: dict = Depends(require_permission("attendance", "read"))):
    return await db.gsheet_attendance_runs.find({}, {"_id": 0}).sort("started_at", -1).to_list(min(limit, 100))


@router.get("/preview")
async def preview_sheet(user: dict = Depends(require_permission("attendance", "read"))):
    """Show what the connector can see — used to validate the sheet before syncing."""
    cfg = await db.gsheet_attendance_config.find_one({"id": CONFIG_ID}, {"_id": 0})
    if not cfg:
        raise HTTPException(400, "Connect the Google attendance sheet first")
    parsed = _parse_sheet(await _fetch_csv(cfg["sheet_id"], cfg.get("gid") or "0"))
    emps = await db.employees.find({}, {"_id": 0, "emp_code": 1, "employee_id": 1}).to_list(20000)
    known = {str(e.get(k)).strip().upper() for e in emps for k in ("emp_code", "employee_id") if e.get(k)}
    sample = []
    for e in parsed["employees"][:25]:
        days = [d for d in e["days"] if d["status_raw"]]
        sample.append({"emp_code": e["emp_code"], "name": e["name"],
                       "matched": e["emp_code"].upper() in known,
                       "days_with_status": len(days),
                       "total_ot": round(sum(_num(d["ot_raw"]) for d in e["days"]), 2),
                       "first_days": days[:5]})
    return {"month": parsed["month"], "date_from": parsed["date_from"], "date_to": parsed["date_to"],
            "date_count": parsed["date_count"], "employees_in_sheet": len(parsed["employees"]),
            "matched": sum(1 for e in parsed["employees"] if e["emp_code"].upper() in known),
            "sample": sample}


async def scheduled_gsheet_attendance_sync() -> None:
    """APScheduler entry point — runs only when auto-sync is switched on."""
    try:
        cfg = await db.gsheet_attendance_config.find_one({"id": CONFIG_ID}, {"_id": 0})
        if not cfg or not cfg.get("enabled") or not cfg.get("auto_sync"):
            return
        ist_now = datetime.now(timezone.utc).timestamp() + 19800
        hh = int(datetime.fromtimestamp(ist_now, tz=timezone.utc).strftime("%H"))
        mm = int(datetime.fromtimestamp(ist_now, tz=timezone.utc).strftime("%M"))
        if hh != int(cfg.get("sync_hour_ist", 7)) or not (0 <= mm - int(cfg.get("sync_minute_ist", 0)) < 15):
            return
        run = await _run_sync(actor="System (scheduled)", trigger="scheduled")
        logger.info("gsheet attendance auto-sync: %s", {k: run.get(k) for k in
                                                        ("imported", "updated", "failed")})
    except Exception as exc:  # noqa: BLE001
        logger.warning("gsheet attendance auto-sync failed: %s", exc)
        await db.gsheet_attendance_runs.insert_one({
            "id": new_id(), "started_at": now_iso(), "finished_at": now_iso(),
            "trigger": "scheduled", "status": "failed", "by": "System (scheduled)",
            "imported": 0, "updated": 0, "unchanged": 0, "skipped_locked": 0, "failed": 0,
            "errors": [{"error": str(exc)[:500]}]})
