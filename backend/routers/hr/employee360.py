"""HR · Employee 360 — unified profile aggregator + skill/cert CRUD."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from .common import ip_of

router = APIRouter(tags=["hr"])


@router.get("/employee-360/{employee_id}")
async def employee_360(employee_id: str,
                       user: dict = Depends(require_permission("hr_employee_360", "read"))):
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")

    skills = emp.get("skills") or []
    certifications = emp.get("certifications") or []
    today = datetime.now(timezone.utc).date()
    for c in certifications:
        try:
            exp = datetime.fromisoformat(str(c.get("expiry_date"))).date()
            days = (exp - today).days
            c["expires_in_days"] = days
            c["expiry_status"] = "expired" if days < 0 else ("expiring_soon" if days <= 30 else "valid")
        except Exception:
            c["expires_in_days"] = None
            c["expiry_status"] = "unknown"

    ppe = await db.ppe_issuance.find({"employee_id": employee_id}, {"_id": 0}) \
        .sort([("issue_date", -1)]).to_list(50)
    trainings = await db.safety_trainings.find({"trainee_id": employee_id}, {"_id": 0}) \
        .sort([("scheduled_date", -1)]).to_list(50)
    toolbox = await db.toolbox_talks.find({"attendees": {"$in": [employee_id, emp.get("name")]}}, {"_id": 0}) \
        .sort([("talk_date", -1)]).to_list(50)
    deployments = await db.deployments.find({"employee_id": employee_id}, {"_id": 0}) \
        .sort([("created_at", -1)]).to_list(50)

    thirty = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    att_rows = await db.attendance.find(
        {"employee_id": employee_id, "date": {"$gte": thirty}}, {"_id": 0}
    ).to_list(200)
    att_summary = {"present": 0, "absent": 0, "leave": 0, "total_hours": 0}
    for a in att_rows:
        s = a.get("status", "")
        if s in att_summary:
            att_summary[s] += 1
        att_summary["total_hours"] += float(a.get("hours") or 0)

    payroll = await db.payroll.find({"employee_id": employee_id}, {"_id": 0}) \
        .sort([("month", -1)]).limit(3).to_list(3)
    docs = await db.files.find(
        {"parent_type": "employees", "parent_id": employee_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    ).sort([("uploaded_at", -1)]).to_list(50)

    year = datetime.now(timezone.utc).year
    balances = await db.leave_balances.find(
        {"employee_id": employee_id, "year": year}, {"_id": 0}
    ).to_list(20)
    recent_leaves = await db.leave_applications.find(
        {"employee_id": employee_id}, {"_id": 0}
    ).sort([("from_date", -1)]).limit(10).to_list(10)

    return {
        "personal": emp, "skills": skills, "certifications": certifications,
        "ppe_history": ppe, "trainings": trainings + toolbox,
        "deployments": deployments,
        "attendance_30d": att_summary, "attendance_rows": att_rows,
        "payroll": payroll, "documents": docs,
        "leave_balances": balances, "recent_leaves": recent_leaves,
    }


class SkillIn(BaseModel):
    skill: str
    level: str = "intermediate"
    years: Optional[float] = None
    notes: Optional[str] = None


@router.post("/employees/{employee_id}/skills")
async def add_skill(employee_id: str, payload: SkillIn, request: Request,
                    user: dict = Depends(require_permission("hr_employee_360", "write"))):
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0, "id": 1})
    if not emp:
        raise HTTPException(404, "Employee not found")
    entry = {"id": new_id(), **payload.model_dump(), "added_at": now_iso()}
    await db.employees.update_one({"id": employee_id}, {"$push": {"skills": entry}})
    await audit(user=user, action="hr_skill_add", resource="employees",
                record_id=employee_id, after=entry, ip=ip_of(request))
    return entry


@router.delete("/employees/{employee_id}/skills/{skill_id}")
async def remove_skill(employee_id: str, skill_id: str, request: Request,
                       user: dict = Depends(require_permission("hr_employee_360", "write"))):
    r = await db.employees.update_one(
        {"id": employee_id}, {"$pull": {"skills": {"id": skill_id}}})
    if not r.modified_count:
        raise HTTPException(404, "Skill not found")
    await audit(user=user, action="hr_skill_delete", resource="employees",
                record_id=employee_id, after={"skill_id": skill_id}, ip=ip_of(request))
    return {"deleted": True}


class CertificationIn(BaseModel):
    name: str
    issuer: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    cert_no: Optional[str] = None
    notes: Optional[str] = None


@router.post("/employees/{employee_id}/certifications")
async def add_certification(employee_id: str, payload: CertificationIn, request: Request,
                            user: dict = Depends(require_permission("hr_employee_360", "write"))):
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0, "id": 1})
    if not emp:
        raise HTTPException(404, "Employee not found")
    entry = {"id": new_id(), **payload.model_dump(), "added_at": now_iso()}
    await db.employees.update_one({"id": employee_id}, {"$push": {"certifications": entry}})
    await audit(user=user, action="hr_cert_add", resource="employees",
                record_id=employee_id, after=entry, ip=ip_of(request))
    return entry


@router.delete("/employees/{employee_id}/certifications/{cert_id}")
async def remove_certification(employee_id: str, cert_id: str, request: Request,
                               user: dict = Depends(require_permission("hr_employee_360", "write"))):
    r = await db.employees.update_one(
        {"id": employee_id}, {"$pull": {"certifications": {"id": cert_id}}})
    if not r.modified_count:
        raise HTTPException(404, "Certification not found")
    await audit(user=user, action="hr_cert_delete", resource="employees",
                record_id=employee_id, after={"cert_id": cert_id}, ip=ip_of(request))
    return {"deleted": True}
