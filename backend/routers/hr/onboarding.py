"""HR · Onboarding workflow.

6-stage joiner checklist with `complete` auto-triggers: creates employee
record, login user, PPE issuance, safety induction training and seeds default
leave balances for all active leave types.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from core import db, get_current_user, require_permission, now_iso, new_id, hash_password
from audit import audit
from .common import ip_of, strip_id, next_emp_code, seq

router = APIRouter(tags=["hr"])

ONBOARDING_STAGES = [
    {"key": "offer_accepted", "label": "Offer Accepted"},
    {"key": "docs_uploaded", "label": "Documents Uploaded"},
    {"key": "id_card_issued", "label": "ID Card Issued"},
    {"key": "ppe_issued", "label": "PPE Issued"},
    {"key": "induction_done", "label": "Safety Induction Done"},
    {"key": "site_assigned", "label": "Site Assigned"},
]


class OnboardingIn(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: str = "supervisor"
    department: Optional[str] = None
    joining_date: Optional[str] = None
    designation: Optional[str] = None
    salary: Optional[float] = None
    candidate_id: Optional[str] = None
    site_id: Optional[str] = None
    project_id: Optional[str] = None
    notes: Optional[str] = None


def _fresh_stages() -> List[Dict[str, Any]]:
    return [{"key": s["key"], "label": s["label"], "done": False,
             "done_at": None, "done_by": None, "notes": None}
            for s in ONBOARDING_STAGES]


@router.get("/onboardings/stages")
async def onboarding_stages(user: dict = Depends(get_current_user)):
    return ONBOARDING_STAGES


@router.get("/onboardings")
async def list_onboardings(status: Optional[str] = None,
                           user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    return await db.onboardings.find(q, {"_id": 0}).sort([("created_at", -1)]).to_list(500)


@router.get("/onboardings/employee-status")
async def onboarding_employee_status(master: str = "employee",
                                     user: dict = Depends(require_permission("hr_onboarding", "read"))):
    """All active employees from Employee Master joined with their onboarding state."""
    q: Dict[str, Any] = {"status": {"$ne": "inactive"}}
    if master == "worker":
        q["master_category"] = "worker"
    else:
        q["$or"] = [{"master_category": {"$in": [None, "", "employee"]}}, {"master_category": {"$exists": False}}]
    emps = await db.employees.find(q, {"_id": 0, "id": 1, "emp_code": 1, "employee_id": 1, "name": 1,
                                        "email": 1, "department": 1, "designation": 1,
                                        "joining_date": 1}).sort("name", 1).to_list(3000)
    obs = await db.onboardings.find({}, {"_id": 0, "id": 1, "employee_id": 1, "email": 1,
                                          "status": 1, "stages": 1}).to_list(3000)
    by_emp = {o["employee_id"]: o for o in obs if o.get("employee_id")}
    by_email = {o["email"].lower(): o for o in obs if o.get("email")}
    rows: List[Dict[str, Any]] = []
    counts = {"completed": 0, "in_progress": 0, "not_started": 0}
    for e in emps:
        o = by_emp.get(e["id"]) or by_email.get((e.get("email") or "").lower())
        if o:
            stages = o.get("stages") or []
            done = sum(1 for s in stages if s.get("done"))
            status = "completed" if o.get("status") == "completed" else "in_progress"
            pct = 100 if status == "completed" else (round(done / len(stages) * 100) if stages else 0)
        else:
            status, pct, done, stages = "not_started", 0, 0, []
        counts[status] += 1
        rows.append({
            "employee_id": e["id"],
            "emp_code": e.get("employee_id") or e.get("emp_code") or "",
            "name": e.get("name"), "department": e.get("department"),
            "designation": e.get("designation"), "joining_date": e.get("joining_date"),
            "onboarding_id": o.get("id") if o else None,
            "status": status, "progress_pct": pct,
            "stages_done": done, "stages_total": len(stages) or len(ONBOARDING_STAGES),
        })
    return {"total": len(rows), **counts, "rows": rows}


class StartForEmployeeIn(BaseModel):
    employee_id: str


@router.post("/onboardings/start-for-employee")
async def start_for_employee(payload: StartForEmployeeIn, request: Request,
                             user: dict = Depends(require_permission("hr_onboarding", "write"))):
    """Start an onboarding checklist for an employee who already exists in Employee Master.
    Completing it will NOT create a duplicate employee — only the remaining triggers fire."""
    emp = await db.employees.find_one({"id": payload.employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found in Employee Master")
    existing = await db.onboardings.find_one({"employee_id": payload.employee_id}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(400, "An onboarding checklist already exists for this employee")
    doc = {
        "id": new_id(),
        "name": emp.get("name"), "email": emp.get("email"), "phone": emp.get("phone"),
        "role": emp.get("role") or "supervisor", "department": emp.get("department"),
        "joining_date": emp.get("joining_date"), "designation": emp.get("designation"),
        "salary": emp.get("salary"), "candidate_id": None,
        "site_id": emp.get("site_id"), "project_id": emp.get("project_id"),
        "notes": "Checklist started for existing Employee Master record",
        "for_existing_employee": True,
        "stages": _fresh_stages(),
        "status": "in_progress",
        "completed_at": None, "employee_id": emp["id"], "user_id": None,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.onboardings.insert_one(doc)
    await audit(user=user, action="hr_onboarding_start_existing", resource="onboardings",
                record_id=doc["id"], after={"employee_id": emp["id"], "name": emp.get("name")},
                ip=ip_of(request))
    return strip_id(doc)


@router.get("/onboardings/{oid}")
async def get_onboarding(oid: str, user: dict = Depends(require_permission("hr_onboarding", "read"))):
    row = await db.onboardings.find_one({"id": oid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.post("/onboardings")
async def create_onboarding(payload: OnboardingIn, request: Request,
                            user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if not payload.name.strip():
        raise HTTPException(400, "Name is required")
    doc = {
        "id": new_id(),
        **payload.model_dump(),
        "stages": _fresh_stages(),
        "status": "in_progress",
        "completed_at": None, "employee_id": None, "user_id": None,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.onboardings.insert_one(doc)
    await audit(user=user, action="hr_onboarding_create", resource="onboardings",
                record_id=doc["id"], after=doc, ip=ip_of(request))
    return strip_id(doc)


@router.post("/onboardings/{oid}/advance")
async def advance_onboarding(oid: str, request: Request,
                             payload: Dict[str, Any] = None,
                             user: dict = Depends(require_permission("hr_onboarding", "write"))):
    payload = payload or {}
    stage_key = payload.get("stage_key")
    if not stage_key:
        raise HTTPException(400, "stage_key required")
    row = await db.onboardings.find_one({"id": oid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    stages = row.get("stages") or _fresh_stages()
    found = False
    for s in stages:
        if s["key"] == stage_key:
            s["done"] = True
            s["done_at"] = now_iso()
            s["done_by"] = user.get("name") or user.get("email")
            if payload.get("notes"):
                s["notes"] = payload.get("notes")
            found = True
            break
    if not found:
        raise HTTPException(400, f"Unknown stage_key '{stage_key}'")
    await db.onboardings.update_one({"id": oid}, {"$set": {"stages": stages}})
    await audit(user=user, action="hr_onboarding_advance", resource="onboardings",
                record_id=oid, after={"stage_key": stage_key, "notes": payload.get("notes")}, ip=ip_of(request))
    return await get_onboarding(oid, user=user)


class CompleteIn(BaseModel):
    create_login: bool = True
    default_password: Optional[str] = None
    issue_ppe_kit: bool = True
    schedule_induction: bool = True


@router.post("/onboardings/{oid}/complete")
async def complete_onboarding(oid: str, payload: CompleteIn, request: Request,
                              user: dict = Depends(require_permission("hr_onboarding", "write"))):
    row = await db.onboardings.find_one({"id": oid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row.get("status") == "completed":
        raise HTTPException(400, "Already completed")
    name, email = row["name"], row.get("email")
    department, role = row.get("department"), row.get("role") or "supervisor"
    triggers: Dict[str, Any] = {}

    employee = None
    if row.get("employee_id"):
        employee = await db.employees.find_one({"id": row["employee_id"]}, {"_id": 0})
    if employee:
        name = employee.get("name") or name
        email = email or employee.get("email")
        emp_code = employee.get("employee_id") or employee.get("emp_code") or ""
        await db.employees.update_one({"id": employee["id"]}, {"$set": {"onboarding_id": oid}})
        triggers["employee_reused"] = True
    else:
        emp_code = await next_emp_code()
        employee = {
            "id": new_id(), "emp_code": emp_code,
            "name": name, "email": email, "phone": row.get("phone"),
            "role": role, "department": department,
            "departments": [department] if department else [],
            "designation": row.get("designation"),
            "joining_date": row.get("joining_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "salary": row.get("salary") or 0, "status": "active",
            "onboarding_id": oid, "site_id": row.get("site_id"), "project_id": row.get("project_id"),
            "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
        }
        await db.employees.insert_one(employee)
    triggers["employee_id"] = employee["id"]
    triggers["emp_code"] = emp_code

    user_id = None
    if payload.create_login and email:
        existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
        if existing:
            user_id = existing["id"]
            triggers["user_login"] = "existing"
        else:
            pwd = payload.default_password or "Welcome@123"
            u = {"id": new_id(), "email": email, "name": name, "role": role,
                 "department": department, "phone": row.get("phone") or "",
                 "password_hash": hash_password(pwd), "active": True, "created_at": now_iso()}
            await db.users.insert_one(u)
            user_id = u["id"]
            triggers["user_login"] = "created"
            triggers["default_password"] = pwd

    if payload.issue_ppe_kit:
        ppe = {"id": new_id(), "issue_no": await seq("PPE-"),
               "employee_id": employee["id"], "employee_name": name,
               "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
               "items": [{"item": "Safety Helmet", "qty": 1}, {"item": "Safety Shoes", "qty": 1},
                         {"item": "Hi-Vis Vest", "qty": 1}, {"item": "Safety Goggles", "qty": 1},
                         {"item": "Gloves", "qty": 1}],
               "status": "issued", "remarks": "Auto-issued during onboarding",
               "created_at": now_iso(), "created_by": user.get("name") or user.get("email")}
        await db.ppe_issuance.insert_one(ppe)
        triggers["ppe_issuance_id"] = ppe["id"]

    if payload.schedule_induction:
        trn = {"id": new_id(), "training_no": await seq("TRN-"),
               "type": "safety_induction", "title": "Safety Induction (New Joiner)",
               "trainee_id": employee["id"], "trainee_name": name,
               "scheduled_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
               "status": "scheduled", "created_at": now_iso(),
               "created_by": user.get("name") or user.get("email")}
        await db.safety_trainings.insert_one(trn)
        triggers["safety_training_id"] = trn["id"]

    year = datetime.now(timezone.utc).year
    types = await db.leave_types.find({"active": True}, {"_id": 0}).to_list(20)
    for lt in types:
        await db.leave_balances.update_one(
            {"employee_id": employee["id"], "leave_type": lt["code"], "year": year},
            {"$setOnInsert": {
                "id": new_id(), "employee_id": employee["id"], "employee_name": name,
                "leave_type": lt["code"], "leave_type_label": lt["label"], "year": year,
                "granted": lt.get("annual_quota") or 0, "used": 0,
                "balance": lt.get("annual_quota") or 0, "created_at": now_iso()}},
            upsert=True)
    triggers["leave_balances_granted"] = len(types)

    await db.onboardings.update_one(
        {"id": oid},
        {"$set": {"status": "completed", "completed_at": now_iso(),
                  "employee_id": employee["id"], "user_id": user_id, "triggers": triggers}})
    await audit(user=user, action="hr_onboarding_complete", resource="onboardings",
                record_id=oid, after=triggers, ip=ip_of(request))
    return {"ok": True, "triggers": triggers, "employee_id": employee["id"]}


@router.delete("/onboardings/{oid}")
async def delete_onboarding(oid: str, request: Request,
                            user: dict = Depends(require_permission("hr_onboarding", "delete"))):
    row = await db.onboardings.find_one({"id": oid}, {"_id": 0, "status": 1})
    if not row:
        raise HTTPException(404, "Not found")
    if row.get("status") == "completed":
        raise HTTPException(400, "Cannot delete a completed onboarding")
    await db.onboardings.delete_one({"id": oid})
    await audit(user=user, action="hr_onboarding_delete", resource="onboardings",
                record_id=oid, ip=ip_of(request))
    return {"deleted": True}
