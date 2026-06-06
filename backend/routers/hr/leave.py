"""HR · Leave management — types, balances, applications, calendar."""
from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from core import db, get_current_user, require_permission, now_iso, new_id
from audit import audit
from .common import ip_of, strip_id, days_between

router = APIRouter(tags=["hr"])

DEFAULT_LEAVE_TYPES = [
    {"code": "CL", "label": "Casual Leave", "annual_quota": 12, "active": True, "color": "#3b82f6"},
    {"code": "SL", "label": "Sick Leave", "annual_quota": 7, "active": True, "color": "#ef4444"},
    {"code": "EL", "label": "Earned Leave", "annual_quota": 15, "active": True, "color": "#10b981"},
    {"code": "PL", "label": "Paid Leave", "annual_quota": 10, "active": True, "color": "#f59e0b"},
]


async def seed_leave_types_if_empty() -> int:
    n = await db.leave_types.count_documents({})
    if n > 0:
        return 0
    docs = [{"id": new_id(), **lt, "created_at": now_iso()} for lt in DEFAULT_LEAVE_TYPES]
    await db.leave_types.insert_many(docs)
    return len(docs)


@router.get("/leave-types")
async def list_leave_types(user: dict = Depends(get_current_user)):
    return await db.leave_types.find({}, {"_id": 0}).sort([("code", 1)]).to_list(50)


class LeaveTypeIn(BaseModel):
    code: str
    label: str
    annual_quota: float = 0
    active: bool = True
    color: Optional[str] = "#3b82f6"


@router.post("/leave-types")
async def create_leave_type(payload: LeaveTypeIn, request: Request,
                            user: dict = Depends(require_permission("hr_leave", "write"))):
    existing = await db.leave_types.find_one({"code": payload.code.upper()}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(400, f"Leave type '{payload.code}' already exists")
    doc = {"id": new_id(), **payload.model_dump(), "code": payload.code.upper(),
           "created_at": now_iso()}
    await db.leave_types.insert_one(doc)
    await audit(user=user, action="hr_leave_type_create", resource="leave_types",
                record_id=doc["id"], after=doc, ip=ip_of(request))
    return strip_id(doc)


@router.put("/leave-types/{tid}")
async def update_leave_type(tid: str, payload: Dict[str, Any], request: Request,
                            user: dict = Depends(require_permission("hr_leave", "write"))):
    payload.pop("id", None); payload.pop("code", None)
    r = await db.leave_types.update_one({"id": tid}, {"$set": payload})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return await db.leave_types.find_one({"id": tid}, {"_id": 0})


@router.get("/leave-balances/{employee_id}")
async def employee_leave_balances(employee_id: str, year: Optional[int] = None,
                                  user: dict = Depends(require_permission("hr_leave", "read"))):
    y = year or datetime.now(timezone.utc).year
    rows = await db.leave_balances.find(
        {"employee_id": employee_id, "year": y}, {"_id": 0}
    ).sort([("leave_type", 1)]).to_list(20)
    return {"year": y, "balances": rows}


class GrantBalanceIn(BaseModel):
    leave_type: str
    quantity: float
    year: Optional[int] = None
    employee_ids: Optional[List[str]] = None
    department: Optional[str] = None


@router.post("/leave-balances/grant")
async def grant_balances(payload: GrantBalanceIn, request: Request,
                         user: dict = Depends(require_permission("hr_leave", "write"))):
    lt = await db.leave_types.find_one({"code": payload.leave_type.upper()}, {"_id": 0})
    if not lt:
        raise HTTPException(400, f"Unknown leave_type '{payload.leave_type}'")
    year = payload.year or datetime.now(timezone.utc).year
    q: Dict[str, Any] = {"status": "active"}
    if payload.employee_ids:
        q["id"] = {"$in": payload.employee_ids}
    elif payload.department:
        q["department"] = payload.department
    emps = await db.employees.find(q, {"_id": 0, "id": 1, "name": 1}).to_list(2000)
    granted = 0
    for e in emps:
        existing = await db.leave_balances.find_one(
            {"employee_id": e["id"], "leave_type": lt["code"], "year": year}, {"_id": 0})
        if existing:
            new_g = (existing.get("granted") or 0) + payload.quantity
            new_b = (existing.get("balance") or 0) + payload.quantity
            await db.leave_balances.update_one(
                {"id": existing["id"]}, {"$set": {"granted": new_g, "balance": new_b}})
        else:
            await db.leave_balances.insert_one({
                "id": new_id(), "employee_id": e["id"], "employee_name": e["name"],
                "leave_type": lt["code"], "leave_type_label": lt["label"], "year": year,
                "granted": payload.quantity, "used": 0,
                "balance": payload.quantity, "created_at": now_iso()})
        granted += 1
    await audit(user=user, action="hr_balance_grant", resource="leave_balances",
                record_id=lt["code"],
                after={"granted_to": granted, "qty": payload.quantity, "year": year},
                ip=ip_of(request))
    return {"granted_to": granted, "leave_type": lt["code"], "year": year}


class LeaveApplyIn(BaseModel):
    employee_id: str
    leave_type: str
    from_date: str
    to_date: str
    half_day: bool = False
    reason: Optional[str] = None


@router.post("/leave-applications")
async def apply_leave(payload: LeaveApplyIn, request: Request,
                      user: dict = Depends(get_current_user)):
    self_emp = await db.employees.find_one({"email": user.get("email")},
                                           {"_id": 0, "id": 1, "name": 1, "department": 1})
    if payload.employee_id and self_emp and payload.employee_id != self_emp["id"]:
        if user.get("role") not in ("super_admin", "hr_executive", "general_manager", "director", "dept_head"):
            raise HTTPException(403, "Cannot apply leave for another employee")
    emp = await db.employees.find_one({"id": payload.employee_id},
                                      {"_id": 0, "id": 1, "name": 1, "department": 1, "email": 1})
    if not emp:
        raise HTTPException(404, "Employee not found")
    lt = await db.leave_types.find_one({"code": payload.leave_type.upper()}, {"_id": 0})
    if not lt:
        raise HTTPException(400, f"Unknown leave_type '{payload.leave_type}'")
    days = days_between(payload.from_date, payload.to_date, payload.half_day)
    year = datetime.fromisoformat(payload.from_date).year
    bal = await db.leave_balances.find_one(
        {"employee_id": emp["id"], "leave_type": lt["code"], "year": year}, {"_id": 0})
    available = (bal or {}).get("balance", 0)
    if days > available:
        raise HTTPException(400, f"Insufficient {lt['code']} balance: requested {days}, available {available}")
    doc = {
        "id": new_id(),
        "employee_id": emp["id"], "employee_name": emp["name"], "department": emp.get("department"),
        "leave_type": lt["code"], "leave_type_label": lt["label"],
        "from_date": payload.from_date, "to_date": payload.to_date,
        "days": days, "half_day": payload.half_day, "reason": payload.reason,
        "status": "pending", "applied_at": now_iso(),
        "applied_by": user.get("name") or user.get("email"),
        "approved_at": None, "approved_by": None, "remarks": None,
    }
    await db.leave_applications.insert_one(doc)
    await audit(user=user, action="hr_leave_apply", resource="leave_applications",
                record_id=doc["id"], after=doc, ip=ip_of(request))
    return strip_id(doc)


@router.get("/leave-applications")
async def list_leave_applications(status: Optional[str] = None,
                                  employee_id: Optional[str] = None,
                                  department: Optional[str] = None,
                                  user: dict = Depends(require_permission("hr_leave", "read"))):
    q: Dict[str, Any] = {}
    if status: q["status"] = status
    if employee_id: q["employee_id"] = employee_id
    if department: q["department"] = department
    return await db.leave_applications.find(q, {"_id": 0}).sort([("applied_at", -1)]).to_list(500)


@router.get("/leave-applications/mine")
async def my_leave_applications(user: dict = Depends(get_current_user)):
    self_emp = await db.employees.find_one({"email": user.get("email")}, {"_id": 0, "id": 1})
    if not self_emp:
        return []
    return await db.leave_applications.find({"employee_id": self_emp["id"]}, {"_id": 0}) \
        .sort([("applied_at", -1)]).to_list(200)


class LeaveDecisionIn(BaseModel):
    remarks: Optional[str] = None


@router.post("/leave-applications/{lid}/approve")
async def approve_leave(lid: str, payload: LeaveDecisionIn, request: Request,
                        user: dict = Depends(require_permission("hr_leave", "write"))):
    row = await db.leave_applications.find_one({"id": lid}, {"_id": 0})
    if not row: raise HTTPException(404, "Not found")
    if row["status"] != "pending": raise HTTPException(400, f"Already {row['status']}")
    year = datetime.fromisoformat(row["from_date"]).year
    bal = await db.leave_balances.find_one(
        {"employee_id": row["employee_id"], "leave_type": row["leave_type"], "year": year}, {"_id": 0})
    if not bal: raise HTTPException(400, "No balance row found — grant balance first")
    if row["days"] > bal["balance"]: raise HTTPException(400, "Insufficient balance at time of approval")
    new_used = (bal.get("used") or 0) + row["days"]
    new_bal = (bal.get("balance") or 0) - row["days"]
    await db.leave_balances.update_one({"id": bal["id"]}, {"$set": {"used": new_used, "balance": new_bal}})
    await db.leave_applications.update_one(
        {"id": lid},
        {"$set": {"status": "approved", "approved_at": now_iso(),
                  "approved_by": user.get("name") or user.get("email"),
                  "remarks": payload.remarks}})
    await audit(user=user, action="hr_leave_approve", resource="leave_applications",
                record_id=lid, after={"days": row["days"], "remarks": payload.remarks}, ip=ip_of(request))
    return await db.leave_applications.find_one({"id": lid}, {"_id": 0})


@router.post("/leave-applications/{lid}/reject")
async def reject_leave(lid: str, payload: LeaveDecisionIn, request: Request,
                       user: dict = Depends(require_permission("hr_leave", "write"))):
    row = await db.leave_applications.find_one({"id": lid}, {"_id": 0})
    if not row: raise HTTPException(404, "Not found")
    if row["status"] != "pending": raise HTTPException(400, f"Already {row['status']}")
    await db.leave_applications.update_one(
        {"id": lid},
        {"$set": {"status": "rejected", "approved_at": now_iso(),
                  "approved_by": user.get("name") or user.get("email"),
                  "remarks": payload.remarks}})
    await audit(user=user, action="hr_leave_reject", resource="leave_applications",
                record_id=lid, after={"remarks": payload.remarks}, ip=ip_of(request))
    return await db.leave_applications.find_one({"id": lid}, {"_id": 0})


@router.post("/leave-applications/{lid}/cancel")
async def cancel_leave(lid: str, request: Request,
                       user: dict = Depends(get_current_user)):
    row = await db.leave_applications.find_one({"id": lid}, {"_id": 0})
    if not row: raise HTTPException(404, "Not found")
    self_emp = await db.employees.find_one({"email": user.get("email")}, {"_id": 0, "id": 1})
    is_self = self_emp and self_emp["id"] == row["employee_id"]
    is_admin = user.get("role") in ("super_admin", "hr_executive", "general_manager", "director")
    if not (is_self or is_admin):
        raise HTTPException(403, "Cannot cancel another employee's leave")
    if row["status"] == "approved":
        year = datetime.fromisoformat(row["from_date"]).year
        bal = await db.leave_balances.find_one(
            {"employee_id": row["employee_id"], "leave_type": row["leave_type"], "year": year}, {"_id": 0})
        if bal:
            await db.leave_balances.update_one(
                {"id": bal["id"]},
                {"$set": {"used": max(0, (bal.get("used") or 0) - row["days"]),
                          "balance": (bal.get("balance") or 0) + row["days"]}})
    await db.leave_applications.update_one(
        {"id": lid}, {"$set": {"status": "cancelled", "approved_at": now_iso(),
                               "approved_by": user.get("name") or user.get("email")}})
    await audit(user=user, action="hr_leave_cancel", resource="leave_applications",
                record_id=lid, ip=ip_of(request))
    return {"cancelled": True}


@router.get("/leave-calendar")
async def leave_calendar(month: Optional[str] = Query(None, description="YYYY-MM, default current"),
                         user: dict = Depends(require_permission("hr_leave", "read"))):
    if month:
        try:
            y, m = month.split("-")
            start = date(int(y), int(m), 1)
        except Exception:
            raise HTTPException(400, "month must be YYYY-MM")
    else:
        today = datetime.now(timezone.utc).date()
        start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1)
    else:
        end = start.replace(month=start.month + 1, day=1)
    rows = await db.leave_applications.find(
        {"status": "approved",
         "$or": [
            {"from_date": {"$gte": start.isoformat(), "$lt": end.isoformat()}},
            {"to_date": {"$gte": start.isoformat(), "$lt": end.isoformat()}},
            {"from_date": {"$lt": start.isoformat()},
             "to_date": {"$gte": end.isoformat()}},
         ]}, {"_id": 0}
    ).to_list(500)
    return {"month": start.strftime("%Y-%m"), "rows": rows}


@router.get("/dashboard")
async def hr_dashboard(user: dict = Depends(require_permission("hr_onboarding", "read"))):
    total_emps = await db.employees.count_documents({"status": "active"})
    onb_in_progress = await db.onboardings.count_documents({"status": "in_progress"})
    onb_completed = await db.onboardings.count_documents({"status": "completed"})
    pending_leaves = await db.leave_applications.count_documents({"status": "pending"})
    approved_today = await db.leave_applications.count_documents({
        "status": "approved",
        "approved_at": {"$gte": datetime.now(timezone.utc).strftime("%Y-%m-%d")}})
    emps = await db.employees.find({"certifications": {"$exists": True, "$ne": []}},
                                    {"_id": 0, "id": 1, "name": 1, "certifications": 1}).to_list(500)
    today = datetime.now(timezone.utc).date()
    expiring = []
    for e in emps:
        for c in (e.get("certifications") or []):
            try:
                exp = datetime.fromisoformat(str(c.get("expiry_date"))).date()
                days = (exp - today).days
                if 0 <= days <= 30:
                    expiring.append({"employee_id": e["id"], "employee_name": e["name"],
                                     "cert": c.get("name"), "expires_in_days": days,
                                     "expiry_date": c.get("expiry_date")})
            except Exception:
                pass
    expiring.sort(key=lambda x: x["expires_in_days"])
    return {
        "active_employees": total_emps,
        "onboarding_in_progress": onb_in_progress,
        "onboarding_completed_total": onb_completed,
        "pending_leaves": pending_leaves,
        "leaves_approved_today": approved_today,
        "expiring_certifications": expiring[:20],
        "expiring_total": len(expiring),
    }
