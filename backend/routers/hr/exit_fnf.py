"""HR · Exit & FNF (Full & Final settlement).

Workflow:
  draft → clearance_in_progress → fnf_computed → finalised
Each clearance item (laptop / ID card / keys / PPE / IT access / knowledge
transfer / library / accommodation) must be marked approved by the relevant
department before FNF is computed. Once finalised the employee `status` flips
to `exited` and a relieving letter is auto-generated if a 'relieving'
template exists.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from .common import ip_of, strip_id

logger = logging.getLogger("erp.hr.exit")
router = APIRouter(tags=["hr"])

CLEARANCE_ITEMS = [
    {"key": "laptop", "label": "Laptop / Devices", "approver_role": "store_incharge"},
    {"key": "id_card", "label": "ID Card & Access Cards", "approver_role": "hr_executive"},
    {"key": "keys", "label": "Keys & Locker", "approver_role": "store_incharge"},
    {"key": "ppe", "label": "PPE Returned", "approver_role": "store_incharge"},
    {"key": "it_access", "label": "IT Accounts / Email", "approver_role": "super_admin"},
    {"key": "knowledge_transfer", "label": "Knowledge Transfer", "approver_role": "dept_head"},
    {"key": "library", "label": "Library / Documents", "approver_role": "hr_executive"},
    {"key": "accounts", "label": "Travel & Reimbursements", "approver_role": "accounts_executive"},
]


def _fresh_clearance() -> List[Dict[str, Any]]:
    return [{"key": c["key"], "label": c["label"], "approver_role": c["approver_role"],
             "status": "pending", "approved_at": None, "approved_by": None, "remarks": None}
            for c in CLEARANCE_ITEMS]


class ExitIn(BaseModel):
    employee_id: str
    resignation_date: str          # YYYY-MM-DD
    last_working_day: str          # YYYY-MM-DD
    reason: Optional[str] = None
    notice_period_days: int = 30
    advances: float = 0
    bonus_accrual: float = 0
    notes: Optional[str] = None


@router.get("/clearance-items")
async def clearance_items(user: dict = Depends(require_permission("hr_exit", "read"))):
    return CLEARANCE_ITEMS


@router.get("/exits")
async def list_exits(status: Optional[str] = None,
                     user: dict = Depends(require_permission("hr_exit", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    return await db.hr_exits.find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(500)


@router.get("/exits/{eid}")
async def get_exit(eid: str, user: dict = Depends(require_permission("hr_exit", "read"))):
    row = await db.hr_exits.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.post("/exits")
async def create_exit(payload: ExitIn, request: Request,
                      user: dict = Depends(require_permission("hr_exit", "write"))):
    emp = await db.employees.find_one({"id": payload.employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.get("status") == "exited":
        raise HTTPException(400, "Employee already exited")
    existing_open = await db.hr_exits.find_one(
        {"employee_id": emp["id"], "status": {"$in": ["draft", "clearance_in_progress", "fnf_computed"]}},
        {"_id": 0, "id": 1})
    if existing_open:
        raise HTTPException(400, f"An open exit already exists (id={existing_open['id']})")

    doc = {
        "id": new_id(),
        "employee_id": emp["id"],
        "employee_name": emp.get("name"),
        "emp_code": emp.get("emp_code"),
        "department": emp.get("department"),
        "designation": emp.get("designation") or emp.get("role"),
        "monthly_salary": float(emp.get("salary") or 0),
        "joining_date": emp.get("joining_date"),
        "resignation_date": payload.resignation_date,
        "last_working_day": payload.last_working_day,
        "reason": payload.reason,
        "notice_period_days": payload.notice_period_days,
        "advances": float(payload.advances or 0),
        "bonus_accrual": float(payload.bonus_accrual or 0),
        "notes": payload.notes,
        "clearance": _fresh_clearance(),
        "fnf": None,
        "status": "clearance_in_progress",
        "finalised_at": None,
        "finalised_by": None,
        "relieving_letter_id": None,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.hr_exits.insert_one(doc)
    await audit(user=user, action="hr_exit_create", resource="hr_exits",
                record_id=doc["id"], after=doc, ip=ip_of(request))
    return strip_id(doc)


class ClearanceActionIn(BaseModel):
    remarks: Optional[str] = None


@router.post("/exits/{eid}/clearance/{item_key}/approve")
async def approve_clearance(eid: str, item_key: str, payload: ClearanceActionIn, request: Request,
                            user: dict = Depends(require_permission("hr_exit", "write"))):
    row = await db.hr_exits.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    items = row.get("clearance") or []
    target = next((c for c in items if c["key"] == item_key), None)
    if not target:
        raise HTTPException(400, f"Unknown clearance item '{item_key}'")
    # Only the required approver role OR super_admin / hr_executive can sign off
    if user.get("role") not in (target.get("approver_role"), "super_admin", "hr_executive"):
        raise HTTPException(403, f"Only {target['approver_role']} (or super_admin / HR) can approve this item")
    target["status"] = "approved"
    target["approved_at"] = now_iso()
    target["approved_by"] = user.get("name") or user.get("email")
    target["remarks"] = payload.remarks
    await db.hr_exits.update_one({"id": eid}, {"$set": {"clearance": items}})
    await audit(user=user, action="hr_exit_clearance_approve", resource="hr_exits",
                record_id=eid, after={"item": item_key, "remarks": payload.remarks}, ip=ip_of(request))
    return await db.hr_exits.find_one({"id": eid}, {"_id": 0})


@router.post("/exits/{eid}/clearance/{item_key}/reject")
async def reject_clearance(eid: str, item_key: str, payload: ClearanceActionIn, request: Request,
                           user: dict = Depends(require_permission("hr_exit", "write"))):
    row = await db.hr_exits.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    items = row.get("clearance") or []
    target = next((c for c in items if c["key"] == item_key), None)
    if not target:
        raise HTTPException(400, f"Unknown clearance item '{item_key}'")
    target["status"] = "rejected"
    target["approved_at"] = now_iso()
    target["approved_by"] = user.get("name") or user.get("email")
    target["remarks"] = payload.remarks
    await db.hr_exits.update_one({"id": eid}, {"$set": {"clearance": items}})
    await audit(user=user, action="hr_exit_clearance_reject", resource="hr_exits",
                record_id=eid, after={"item": item_key, "remarks": payload.remarks}, ip=ip_of(request))
    return await db.hr_exits.find_one({"id": eid}, {"_id": 0})


def _completed_years(start_iso: Optional[str], end_iso: str) -> int:
    """Return whole completed years between start and end (Indian Gratuity Act
    style — 5 full calendar years means eligible, regardless of float rounding
    from days/365.25)."""
    if not start_iso:
        return 0
    try:
        s = datetime.fromisoformat(str(start_iso)).date()
        e = datetime.fromisoformat(str(end_iso)).date()
    except Exception:
        return 0
    if e < s:
        return 0
    years = e.year - s.year
    # Anniversary not yet reached this year? Subtract one.
    if (e.month, e.day) < (s.month, s.day):
        years -= 1
    return max(0, years)


def _years_between(start_iso: Optional[str], end_iso: str) -> float:
    if not start_iso:
        return 0.0
    try:
        s = datetime.fromisoformat(str(start_iso)).date()
        e = datetime.fromisoformat(str(end_iso)).date()
    except Exception:
        return 0.0
    return max(0.0, (e - s).days / 365.25)


def _days_between(a: str, b: str) -> int:
    try:
        d1 = datetime.fromisoformat(a).date()
        d2 = datetime.fromisoformat(b).date()
        return max(0, (d2 - d1).days + 1)
    except Exception:
        return 0


@router.post("/exits/{eid}/compute-fnf")
async def compute_fnf(eid: str, request: Request,
                      user: dict = Depends(require_permission("hr_exit", "write"))):
    row = await db.hr_exits.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] == "finalised":
        raise HTTPException(400, "Already finalised")

    monthly = float(row.get("monthly_salary") or 0)
    per_day = round(monthly / 30, 2) if monthly else 0

    # Pending salary: days between last payroll and last_working_day. Simple model: assume from
    # the 1st of the LWD month to the LWD itself.
    lwd = row["last_working_day"]
    pending_days = 0
    try:
        d_lwd = datetime.fromisoformat(lwd).date()
        pending_days = d_lwd.day  # day-of-month → days worked this month
    except Exception:
        pending_days = 0
    pending_salary = round(per_day * pending_days, 2)

    # Leave encashment — EL + PL balances only
    year = datetime.now(timezone.utc).year
    encashable = await db.leave_balances.find(
        {"employee_id": row["employee_id"], "year": year,
         "leave_type": {"$in": ["EL", "PL"]}},
        {"_id": 0},
    ).to_list(20)
    encash_days = sum(float(b.get("balance") or 0) for b in encashable)
    leave_encashment = round(per_day * encash_days, 2)

    # Gratuity — only if completed years ≥ 5 (Indian Gratuity Act).
    # Use whole completed-years arithmetic to avoid float drift on 1826/365.25.
    tenure_years = _years_between(row.get("joining_date"), lwd)
    completed_years = _completed_years(row.get("joining_date"), lwd)
    gratuity = 0.0
    if completed_years >= 5:
        # 15 days basic per completed year. Approximating basic = monthly_salary.
        gratuity = round((monthly * 15 / 26) * completed_years, 2)

    # Notice period recovery — if notice served less than required
    actual_notice = _days_between(row["resignation_date"], lwd)
    short_notice_days = max(0, (row.get("notice_period_days") or 0) - actual_notice)
    notice_recovery = round(per_day * short_notice_days, 2)

    advances = float(row.get("advances") or 0)
    bonus = float(row.get("bonus_accrual") or 0)

    net = round(pending_salary + leave_encashment + gratuity + bonus - advances - notice_recovery, 2)

    fnf = {
        "per_day_rate": per_day,
        "pending_days": pending_days,
        "pending_salary": pending_salary,
        "encashable_days": encash_days,
        "leave_encashment": leave_encashment,
        "tenure_years": round(tenure_years, 2),
        "completed_years": completed_years,
        "gratuity": gratuity,
        "bonus_accrual": bonus,
        "advances": advances,
        "short_notice_days": short_notice_days,
        "notice_recovery": notice_recovery,
        "net_payable": net,
        "computed_at": now_iso(),
        "computed_by": user.get("name") or user.get("email"),
    }
    await db.hr_exits.update_one(
        {"id": eid}, {"$set": {"fnf": fnf, "status": "fnf_computed"}})
    await audit(user=user, action="hr_exit_compute_fnf", resource="hr_exits",
                record_id=eid, after=fnf, ip=ip_of(request))
    return await db.hr_exits.find_one({"id": eid}, {"_id": 0})


class FnfOverrideIn(BaseModel):
    overrides: Dict[str, float]


@router.put("/exits/{eid}/fnf")
async def override_fnf(eid: str, payload: FnfOverrideIn, request: Request,
                       user: dict = Depends(require_permission("hr_exit", "write"))):
    """Override any computed FNF field (HR may want to manually edit gratuity etc.).
    Re-computes net_payable from the updated dict."""
    row = await db.hr_exits.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] == "finalised":
        raise HTTPException(400, "Already finalised")
    fnf = row.get("fnf") or {}
    if not fnf:
        raise HTTPException(400, "Run compute-fnf first")
    for k, v in payload.overrides.items():
        fnf[k] = float(v)
    fnf["net_payable"] = round(
        float(fnf.get("pending_salary", 0))
        + float(fnf.get("leave_encashment", 0))
        + float(fnf.get("gratuity", 0))
        + float(fnf.get("bonus_accrual", 0))
        - float(fnf.get("advances", 0))
        - float(fnf.get("notice_recovery", 0)), 2)
    fnf["overridden_at"] = now_iso()
    fnf["overridden_by"] = user.get("name") or user.get("email")
    await db.hr_exits.update_one({"id": eid}, {"$set": {"fnf": fnf}})
    await audit(user=user, action="hr_exit_fnf_override", resource="hr_exits",
                record_id=eid, after=payload.overrides, ip=ip_of(request))
    return await db.hr_exits.find_one({"id": eid}, {"_id": 0})


@router.post("/exits/{eid}/finalise")
async def finalise_exit(eid: str, request: Request,
                        user: dict = Depends(require_permission("hr_exit", "write"))):
    row = await db.hr_exits.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] == "finalised":
        raise HTTPException(400, "Already finalised")
    items = row.get("clearance") or []
    pending = [c for c in items if c["status"] != "approved"]
    if pending:
        raise HTTPException(400,
            f"Cannot finalise — {len(pending)} clearance item(s) not approved: "
            + ", ".join(c["label"] for c in pending))
    if not row.get("fnf"):
        raise HTTPException(400, "FNF not computed — run /compute-fnf first")

    # Flip employee status
    await db.employees.update_one(
        {"id": row["employee_id"]},
        {"$set": {"status": "exited",
                  "exit_date": row["last_working_day"],
                  "exit_id": row["id"]}})

    # Best-effort relieving letter if a relieving template exists
    letter_id = None
    tpl = await db.letter_templates.find_one(
        {"kind": "relieving", "active": True}, {"_id": 0, "id": 1})
    if tpl:
        try:
            from .letters import render_letter, RenderIn  # type: ignore
            letter_resp = await render_letter(
                tpl["id"],
                RenderIn(employee_id=row["employee_id"],
                         variables={"last_working_day": row["last_working_day"]}),
                request, user=user)
            letter_id = letter_resp.headers.get("X-Letter-Id")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Relieving letter auto-render failed: %s", exc)

    await db.hr_exits.update_one(
        {"id": eid},
        {"$set": {"status": "finalised", "finalised_at": now_iso(),
                  "finalised_by": user.get("name") or user.get("email"),
                  "relieving_letter_id": letter_id}})
    await audit(user=user, action="hr_exit_finalise", resource="hr_exits",
                record_id=eid, after={"relieving_letter_id": letter_id}, ip=ip_of(request))
    return await db.hr_exits.find_one({"id": eid}, {"_id": 0})


@router.delete("/exits/{eid}")
async def delete_exit(eid: str, request: Request,
                      user: dict = Depends(require_permission("hr_exit", "delete"))):
    row = await db.hr_exits.find_one({"id": eid}, {"_id": 0, "status": 1})
    if not row:
        raise HTTPException(404, "Not found")
    if row.get("status") == "finalised":
        raise HTTPException(400, "Cannot delete a finalised exit")
    await db.hr_exits.delete_one({"id": eid})
    await audit(user=user, action="hr_exit_delete", resource="hr_exits",
                record_id=eid, ip=ip_of(request))
    return {"deleted": True}
