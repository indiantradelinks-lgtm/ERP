"""HR Phase 3 — Manpower Planning · Deployment · Mobilization · Demobilization
· Replacement Requests · Project/Site rollups.

Extends Phase 1 (hr_workers, employees) + Phase 2 (compliance helpers, audit)
without replacing them. Reuses the existing `deployments` collection so the
existing CRUD UI continues to function.

All endpoints prefixed `/api/hr3`.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core import db, get_current_user, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/hr3", tags=["hr-phase3"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
SERVICE_TYPES = {"scaffolding", "painting", "roof_sheeting", "rope_access",
                 "manpower", "other"}
DEPLOY_STATUSES = {"planned", "approved", "mobilized", "active",
                   "demobilized", "returned", "closed", "pending_approval", "rejected"}
URGENCY = {"low", "medium", "high", "critical"}


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def _seq(prefix: str) -> str:
    doc = await db.counters.find_one_and_update(
        {"id": f"seq_{prefix.rstrip('-')}"},
        {"$inc": {"n": 1}, "$setOnInsert": {"id": f"seq_{prefix.rstrip('-')}"}},
        upsert=True, return_document=True,
    )
    n = (doc or {}).get("n", 1)
    return f"{prefix}{datetime.now(timezone.utc).year}-{n:04d}"


async def _audit_deployment(dep_id: str, action: str, before: dict | None,
                            after: dict | None, user: dict, ip: str,
                            note: Optional[str] = None):
    await db.hr_deployment_audit.insert_one({
        "id": new_id(), "deployment_id": dep_id, "action": action,
        "before": before, "after": after,
        "by_id": user.get("id"), "by_name": user.get("name") or user.get("email"),
        "by_role": user.get("role"), "ip": ip,
        "note": note, "at": now_iso(),
    })


async def _resolve_person(person_type: str, person_id: Optional[str],
                          employee_code: Optional[str] = None) -> dict:
    if person_type == "worker":
        if person_id:
            row = await db.hr_workers.find_one({"id": person_id}, {"_id": 0})
        else:
            row = None
        if row and row.get("active") is False:
            raise HTTPException(400, "Worker is INACTIVE — deployment blocked")
        return row or {}
    # default employee
    if person_id:
        row = await db.employees.find_one({"id": person_id}, {"_id": 0})
    elif employee_code:
        row = await db.employees.find_one(
            {"$or": [{"emp_code": employee_code}, {"employee_id": employee_code}]},
            {"_id": 0})
    else:
        row = None
    if row and str(row.get("status", "active")).lower() == "inactive":
        raise HTTPException(400, "Employee is INACTIVE — deployment blocked")
    return row or {}


async def _compliance_status(person: dict) -> Dict[str, Any]:
    """Returns flags + blocking-reasons for one person."""
    reasons: list[str] = []
    today_s = _today()
    today_d = datetime.now(timezone.utc).date()

    # Documents
    doc_ok = bool(person.get("documents_verified", True))
    # Medical fitness
    med_ok = bool(person.get("medical_fitness"))
    med_valid = person.get("medical_fitness_valid_till")
    if med_ok and med_valid and str(med_valid) < today_s:
        med_ok = False
        reasons.append("Medical fitness EXPIRED")
    elif not med_ok:
        reasons.append("Medical fitness PENDING")

    # Safety induction
    safety_ok = bool(person.get("safety_induction"))
    if not safety_ok:
        reasons.append("Safety induction PENDING")

    # Certification — only for hazardous trades
    skill = (person.get("skill_name") or person.get("designation") or "").lower()
    needs_cert = any(k in skill for k in ("rope", "scaffold", "rigger", "welder"))
    cert_ok = True
    if needs_cert:
        cert_ok = False
        for c in (person.get("certifications") or []):
            try:
                exp = datetime.fromisoformat(str(c.get("expiry_date"))).date()
                if exp >= today_d:
                    cert_ok = True
                    break
            except Exception:
                pass
        if not cert_ok:
            reasons.append("Required trade certification missing/expired")

    return {
        "documents_ok": doc_ok, "medical_ok": med_ok,
        "safety_induction_ok": safety_ok, "certification_ok": cert_ok,
        "blocking_reasons": reasons,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1.  MANPOWER REQUIREMENT
# ──────────────────────────────────────────────────────────────────────────────
class ManpowerLine(BaseModel):
    skill: str
    required_headcount: int
    qualification: Optional[str] = None
    shift_code: Optional[str] = None
    required_date: Optional[str] = None
    duration_days: Optional[int] = None
    medical_required: bool = True
    safety_induction_required: bool = True
    ppe_required: bool = True


class ManpowerRequirementIn(BaseModel):
    project_code: str
    client: Optional[str] = None
    site_location: Optional[str] = None
    service_type: str = "manpower"
    work_order_no: Optional[str] = None
    requirement_date: Optional[str] = None
    expected_start_date: Optional[str] = None
    expected_duration_days: Optional[int] = None
    priority: str = "medium"
    billing_basis: Optional[str] = None  # day/month/team/shift/qty/lumpsum
    lines: List[ManpowerLine]
    remarks: Optional[str] = None


@router.post("/manpower-requirements")
async def create_manpower_requirement(p: ManpowerRequirementIn, request: Request,
                                      user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if not p.project_code.strip():
        raise HTTPException(400, "project_code is required")
    if p.service_type not in SERVICE_TYPES:
        raise HTTPException(400, f"service_type must be one of {sorted(SERVICE_TYPES)}")
    if not p.lines:
        raise HTTPException(400, "At least one manpower line is required")
    if p.priority not in URGENCY:
        raise HTTPException(400, f"priority must be one of {sorted(URGENCY)}")
    req_no = await _seq("MR-")
    lines_with_id = []
    for line in p.lines:
        ld = line.model_dump()
        ld["id"] = new_id()
        ld["available_count"] = 0
        ld["shortage"] = ld["required_headcount"]
        ld["fulfilled"] = 0
        lines_with_id.append(ld)
    doc = {
        "id": new_id(), "requirement_no": req_no,
        **p.model_dump(exclude={"lines"}),
        "lines": lines_with_id,
        "requested_by_id": user["id"],
        "requested_by_name": user.get("name") or user.get("email"),
        "approval_status": "pending",
        "approved_by_id": None, "approved_by_name": None, "approved_at": None,
        "status": "open",
        "created_at": now_iso(),
    }
    await db.hr_manpower_requirements.insert_one(doc)
    doc.pop("_id", None)
    # Compute availability eagerly so the UI can show shortage immediately
    await _recompute_requirement_availability(doc["id"])
    return await db.hr_manpower_requirements.find_one({"id": doc["id"]}, {"_id": 0})


async def _recompute_requirement_availability(req_id: str):
    req = await db.hr_manpower_requirements.find_one({"id": req_id}, {"_id": 0})
    if not req:
        return
    updated_lines = []
    total_required, total_available, total_shortage = 0, 0, 0
    for line in req.get("lines", []):
        skill = (line.get("skill") or "").strip().lower()
        # Count active workers/employees with matching skill not currently
        # actively deployed (deployment status in active/mobilized).
        wq = {"active": True, "$or": [
            {"skill_name": {"$regex": f"^{skill}$", "$options": "i"}},
            {"designation": {"$regex": f"^{skill}$", "$options": "i"}},
        ]}
        worker_pool = await db.hr_workers.find(wq, {"_id": 0, "id": 1}).to_list(5000)
        worker_ids = [w["id"] for w in worker_pool]
        eq = {"status": {"$ne": "inactive"}, "$or": [
            {"skill_name": {"$regex": f"^{skill}$", "$options": "i"}},
            {"designation": {"$regex": f"^{skill}$", "$options": "i"}},
        ]}
        emp_pool = await db.employees.find(eq, {"_id": 0, "id": 1}).to_list(5000)
        emp_ids = [e["id"] for e in emp_pool]
        all_ids = worker_ids + emp_ids
        # subtract those actively deployed
        deployed_ids = set()
        if all_ids:
            cur = db.deployments.find(
                {"employee_id": {"$in": all_ids},
                 "status": {"$in": ["active", "mobilized", "approved"]}},
                {"_id": 0, "employee_id": 1},
            )
            async for d in cur:
                deployed_ids.add(d["employee_id"])
        available = len([i for i in all_ids if i not in deployed_ids])
        line["available_count"] = available
        line["total_pool"] = len(all_ids)
        required = int(line.get("required_headcount") or 0)
        line["shortage"] = max(0, required - available)
        line["recruitment_required"] = line["shortage"] > 0
        total_required += required
        total_available += available
        total_shortage += line["shortage"]
        updated_lines.append(line)
    await db.hr_manpower_requirements.update_one(
        {"id": req_id},
        {"$set": {
            "lines": updated_lines,
            "total_required": total_required,
            "total_available": total_available,
            "total_shortage": total_shortage,
            "recalc_at": now_iso(),
        }})


@router.get("/manpower-requirements")
async def list_manpower_requirements(project_code: Optional[str] = None,
                                     status: Optional[str] = None,
                                     approval_status: Optional[str] = None,
                                     limit: int = 200,
                                     user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    if approval_status:
        q["approval_status"] = approval_status
    return await db.hr_manpower_requirements.find(q, {"_id": 0}) \
        .sort("created_at", -1).limit(limit).to_list(limit)


@router.get("/manpower-requirements/{rid}")
async def get_manpower_requirement(rid: str,
                                   user: dict = Depends(require_permission("hr_onboarding", "read"))):
    row = await db.hr_manpower_requirements.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Manpower requirement not found")
    return row


@router.post("/manpower-requirements/{rid}/refresh")
async def refresh_availability(rid: str,
                               user: dict = Depends(require_permission("hr_onboarding", "read"))):
    await _recompute_requirement_availability(rid)
    return await db.hr_manpower_requirements.find_one({"id": rid}, {"_id": 0})


class ApprovalIn(BaseModel):
    decision: str = "approve"   # approve | reject
    remarks: Optional[str] = None


@router.post("/manpower-requirements/{rid}/approve")
async def approve_manpower_requirement(rid: str, p: ApprovalIn, request: Request,
                                       user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager",
                                "dept_head", "hr_executive", "project_manager"}:
        raise HTTPException(403, "Only Manager+ can approve manpower requirement")
    if p.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve | reject")
    upd = {
        "approval_status": "approved" if p.decision == "approve" else "rejected",
        "approved_by_id": user["id"],
        "approved_by_name": user.get("name") or user.get("email"),
        "approved_at": now_iso(), "approval_remarks": p.remarks,
        "status": "approved" if p.decision == "approve" else "rejected",
    }
    await db.hr_manpower_requirements.update_one({"id": rid}, {"$set": upd})
    return await db.hr_manpower_requirements.find_one({"id": rid}, {"_id": 0})


# ──────────────────────────────────────────────────────────────────────────────
# 2.  AVAILABILITY (skill-wise)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/availability")
async def availability_by_skill(skill: Optional[str] = None,
                                project_code: Optional[str] = None,
                                user: dict = Depends(require_permission("hr_onboarding", "read"))):
    """Return per-skill totals: active / deployed / available / blocked-by-* / shortage."""
    # 1. Build skill list
    if skill:
        skills = [skill.strip().lower()]
    else:
        a = await db.hr_workers.distinct("skill_name", {"active": True})
        b = await db.employees.distinct("skill_name", {"status": {"$ne": "inactive"}})
        skills = sorted({(s or "").strip().lower() for s in (a + b) if s})

    # 2. Pre-load deployed employee_ids
    deployed_q = {"status": {"$in": ["active", "mobilized", "approved"]}}
    if project_code:
        deployed_q["$or"] = [{"project_code": project_code}, {"project": project_code}]
    deployed_ids = set()
    async for d in db.deployments.find(deployed_q, {"_id": 0, "employee_id": 1}):
        if d.get("employee_id"):
            deployed_ids.add(d["employee_id"])

    rows: list[dict] = []
    for sk in skills:
        # workers + employees pool
        pool = await db.hr_workers.find(
            {"active": True, "$or": [
                {"skill_name": {"$regex": f"^{sk}$", "$options": "i"}},
                {"designation": {"$regex": f"^{sk}$", "$options": "i"}},
            ]}, {"_id": 0}).to_list(5000)
        pool += await db.employees.find(
            {"status": {"$ne": "inactive"}, "$or": [
                {"skill_name": {"$regex": f"^{sk}$", "$options": "i"}},
                {"designation": {"$regex": f"^{sk}$", "$options": "i"}},
            ]}, {"_id": 0}).to_list(5000)
        total = len(pool)
        currently_deployed = sum(1 for p in pool if p.get("id") in deployed_ids)

        blocked_doc, blocked_med, blocked_safety = 0, 0, 0
        deployable_ids = []
        for p in pool:
            if p.get("id") in deployed_ids:
                continue
            cs = await _compliance_status(p)
            if not cs["medical_ok"]:
                blocked_med += 1
                continue
            if not cs["safety_induction_ok"]:
                blocked_safety += 1
                continue
            if not cs["documents_ok"]:
                blocked_doc += 1
                continue
            deployable_ids.append({"id": p.get("id"), "name": p.get("name"),
                                   "kind": "worker" if p in pool[:len(pool)//2] else "employee"})
        available = len(deployable_ids)
        rows.append({
            "skill": sk,
            "total_active": total,
            "currently_deployed": currently_deployed,
            "available": available,
            "blocked_documents": blocked_doc,
            "blocked_medical": blocked_med,
            "blocked_safety": blocked_safety,
            "suggested_list": deployable_ids[:25],
        })
    return {"as_of": now_iso(), "rows": rows}


# ──────────────────────────────────────────────────────────────────────────────
# 3.  PROJECT / SITE DEPLOYMENT  (smart wrapper around `deployments`)
# ──────────────────────────────────────────────────────────────────────────────
class DeploymentIn(BaseModel):
    person_type: str = "employee"   # employee | worker
    person_id: str
    employee_code: Optional[str] = None
    project_code: str
    client: Optional[str] = None
    site_location: Optional[str] = None
    service_type: str = "manpower"
    skill: Optional[str] = None
    deployment_start_date: str
    expected_end_date: Optional[str] = None
    reporting_person: Optional[str] = None
    accommodation_required: bool = False
    travel_required: bool = False
    ppe_required: bool = True
    tool_required: bool = False
    allow_multi_site: bool = False
    requirement_id: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/deployments")
async def create_deployment(p: DeploymentIn, request: Request,
                            user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if not p.project_code.strip():
        raise HTTPException(400, "project_code is required")
    if p.service_type not in SERVICE_TYPES:
        raise HTTPException(400, f"service_type must be in {sorted(SERVICE_TYPES)}")
    person = await _resolve_person(p.person_type, p.person_id, p.employee_code)
    if not person:
        raise HTTPException(404, "Employee/Worker not found")

    # Active deployment guard
    existing = await db.deployments.find_one(
        {"employee_id": p.person_id,
         "status": {"$in": ["planned", "approved", "mobilized", "active"]}},
        {"_id": 0})
    if existing and not p.allow_multi_site:
        raise HTTPException(
            400,
            f"Already deployed on '{existing.get('project') or existing.get('project_code')}'. "
            f"Set allow_multi_site=true to override.")

    # Compliance guard
    cs = await _compliance_status(person)
    if cs["blocking_reasons"]:
        raise HTTPException(
            400, f"Compliance blocked: {'; '.join(cs['blocking_reasons'])}")

    dep_no = await _seq("DEP-")
    doc = {
        "id": new_id(), "deployment_no": dep_no,
        "employee_id": p.person_id,
        "employee": person.get("name"),
        "employee_code": p.employee_code or person.get("emp_code"),
        "person_type": p.person_type,
        # back-compat fields used by existing UI
        "project": p.project_code,
        "project_code": p.project_code,
        "client": p.client,
        "site": p.site_location, "site_location": p.site_location,
        "site_role": p.skill or person.get("designation") or person.get("skill_name"),
        "service_type": p.service_type,
        "skill": p.skill or person.get("skill_name"),
        "start_date": p.deployment_start_date,
        "deployment_start_date": p.deployment_start_date,
        "end_date": p.expected_end_date,
        "expected_end_date": p.expected_end_date,
        "actual_end_date": None,
        "reporting_to": p.reporting_person,
        "reporting_person": p.reporting_person,
        "accommodation_required": p.accommodation_required,
        "travel_required": p.travel_required,
        "ppe_required": p.ppe_required,
        "tool_required": p.tool_required,
        "safety_induction_status": "ok" if cs["safety_induction_ok"] else "pending",
        "medical_fitness_status": "ok" if cs["medical_ok"] else "pending",
        "document_status": "ok" if cs["documents_ok"] else "pending",
        "requirement_id": p.requirement_id,
        "status": "planned",
        "source": "hr3",
        "remarks": p.remarks,
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    }
    await db.deployments.insert_one(doc)
    doc.pop("_id", None)
    await _audit_deployment(doc["id"], "create", None, doc, user, _ip(request))
    # Mark worker as deployed for availability
    if p.person_type == "worker":
        await db.hr_workers.update_one({"id": p.person_id},
                                       {"$set": {"current_project_code": p.project_code,
                                                 "current_status": "deployed"}})
    # Update parent requirement fulfilled count
    if p.requirement_id:
        await db.hr_manpower_requirements.update_one(
            {"id": p.requirement_id, "lines.skill": p.skill},
            {"$inc": {"lines.$.fulfilled": 1}})
        await _recompute_requirement_availability(p.requirement_id)
    return doc


class DeploymentStatusIn(BaseModel):
    status: str
    remarks: Optional[str] = None


@router.post("/deployments/{dep_id}/status")
async def change_deployment_status(dep_id: str, p: DeploymentStatusIn, request: Request,
                                   user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if p.status not in DEPLOY_STATUSES:
        raise HTTPException(400, f"status must be in {sorted(DEPLOY_STATUSES)}")
    row = await db.deployments.find_one({"id": dep_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Deployment not found")
    upd = {"status": p.status, "status_remarks": p.remarks,
           "status_changed_at": now_iso(),
           "status_changed_by": user.get("name") or user.get("email")}
    if p.status == "active":
        upd["mobilized_at"] = now_iso()
    if p.status in ("demobilized", "returned", "closed"):
        upd["actual_end_date"] = _today()
    await db.deployments.update_one({"id": dep_id}, {"$set": upd})
    after = await db.deployments.find_one({"id": dep_id}, {"_id": 0})
    await _audit_deployment(dep_id, f"status_{p.status}", row, after, user,
                            _ip(request), note=p.remarks)
    # Worker availability auto-update on close
    if p.status in ("returned", "closed") and row.get("person_type") == "worker":
        await db.hr_workers.update_one({"id": row["employee_id"]},
                                       {"$set": {"current_status": "available"}})
    return after


@router.get("/deployments/{dep_id}/audit")
async def deployment_audit(dep_id: str,
                           user: dict = Depends(require_permission("hr_onboarding", "read"))):
    return await db.hr_deployment_audit.find(
        {"deployment_id": dep_id}, {"_id": 0}).sort("at", -1).to_list(200)


# ──────────────────────────────────────────────────────────────────────────────
# 4.  MOBILIZATION
# ──────────────────────────────────────────────────────────────────────────────
class MobilizationIn(BaseModel):
    deployment_id: str
    travel_date: Optional[str] = None
    reporting_date: Optional[str] = None
    travel_required: bool = False
    accommodation_required: bool = False
    ppe_required: bool = True
    tool_required: bool = False
    remarks: Optional[str] = None


@router.post("/mobilizations")
async def create_mobilization(p: MobilizationIn, request: Request,
                              user: dict = Depends(require_permission("hr_onboarding", "write"))):
    dep = await db.deployments.find_one({"id": p.deployment_id}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Deployment not found")
    mob_no = await _seq("MOB-")
    doc = {
        "id": new_id(), "mobilization_no": mob_no,
        "deployment_id": p.deployment_id,
        "deployment_no": dep.get("deployment_no"),
        "employee_id": dep.get("employee_id"),
        "employee_name": dep.get("employee"),
        "project_code": dep.get("project_code") or dep.get("project"),
        "site_location": dep.get("site_location") or dep.get("site"),
        "travel_date": p.travel_date,
        "reporting_date": p.reporting_date,
        "travel_required": p.travel_required,
        "accommodation_required": p.accommodation_required,
        "ppe_required": p.ppe_required,
        "tool_required": p.tool_required,
        # Sub-system statuses (Logistics / Store / Safety updates these)
        "logistics_status": "pending" if (p.travel_required or p.accommodation_required) else "not_required",
        "store_status": "pending" if (p.ppe_required or p.tool_required) else "not_required",
        "safety_status": "pending" if dep.get("safety_induction_status") != "ok" else "ok",
        "status": "open",
        "remarks": p.remarks,
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    }
    await db.hr_mobilizations.insert_one(doc)
    doc.pop("_id", None)
    return doc


class MobStatusIn(BaseModel):
    section: str   # logistics | store | safety
    status: str    # pending | in_progress | ok | failed
    remarks: Optional[str] = None


@router.post("/mobilizations/{mid}/section")
async def update_mob_section(mid: str, p: MobStatusIn,
                             user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if p.section not in {"logistics", "store", "safety"}:
        raise HTTPException(400, "section must be logistics | store | safety")
    if p.status not in {"pending", "in_progress", "ok", "failed", "not_required"}:
        raise HTTPException(400, "invalid status")
    field = f"{p.section}_status"
    await db.hr_mobilizations.update_one(
        {"id": mid},
        {"$set": {field: p.status, f"{p.section}_remarks": p.remarks,
                  f"{p.section}_updated_at": now_iso(),
                  f"{p.section}_updated_by": user.get("name") or user.get("email")}})
    return await db.hr_mobilizations.find_one({"id": mid}, {"_id": 0})


@router.post("/mobilizations/{mid}/close")
async def close_mobilization(mid: str,
                             user: dict = Depends(require_permission("hr_onboarding", "write"))):
    row = await db.hr_mobilizations.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Mobilization not found")
    # Block close if any required section still pending
    pending: list[str] = []
    for sec in ("logistics", "store", "safety"):
        st = row.get(f"{sec}_status")
        if st in (None, "pending", "in_progress", "failed"):
            pending.append(f"{sec}={st or 'pending'}")
    if pending:
        raise HTTPException(400, f"Cannot close — pending sections: {', '.join(pending)}")
    await db.hr_mobilizations.update_one(
        {"id": mid}, {"$set": {"status": "closed", "closed_at": now_iso(),
                               "closed_by": user.get("name") or user.get("email")}})
    # Promote deployment status to mobilized → active
    await db.deployments.update_one(
        {"id": row["deployment_id"]},
        {"$set": {"status": "active", "mobilized_at": now_iso()}})
    return await db.hr_mobilizations.find_one({"id": mid}, {"_id": 0})


@router.get("/mobilizations")
async def list_mobilizations(project_code: Optional[str] = None,
                             status: Optional[str] = None,
                             user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    return await db.hr_mobilizations.find(q, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)


# ──────────────────────────────────────────────────────────────────────────────
# 5.  DEMOBILIZATION
# ──────────────────────────────────────────────────────────────────────────────
class DemobilizationIn(BaseModel):
    deployment_id: str
    demobilization_date: Optional[str] = None
    reason: str
    return_travel_required: bool = False
    ppe_return_required: bool = True
    tool_return_required: bool = False
    remarks: Optional[str] = None


@router.post("/demobilizations")
async def create_demobilization(p: DemobilizationIn, request: Request,
                                user: dict = Depends(require_permission("hr_onboarding", "write"))):
    dep = await db.deployments.find_one({"id": p.deployment_id}, {"_id": 0})
    if not dep:
        raise HTTPException(404, "Deployment not found")
    demob_no = await _seq("DMB-")
    doc = {
        "id": new_id(), "demobilization_no": demob_no,
        "deployment_id": p.deployment_id,
        "deployment_no": dep.get("deployment_no"),
        "employee_id": dep.get("employee_id"),
        "employee_name": dep.get("employee"),
        "project_code": dep.get("project_code") or dep.get("project"),
        "site_location": dep.get("site_location") or dep.get("site"),
        "demobilization_date": p.demobilization_date or _today(),
        "reason": p.reason,
        "return_travel_required": p.return_travel_required,
        "ppe_return_required": p.ppe_return_required,
        "tool_return_required": p.tool_return_required,
        "store_clearance": "pending" if (p.ppe_return_required or p.tool_return_required) else "not_required",
        "safety_clearance": "pending",
        "project_clearance": "pending",
        "hr_clearance": "pending",
        "logistics_status": "pending" if p.return_travel_required else "not_required",
        "status": "open",
        "remarks": p.remarks,
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    }
    await db.hr_demobilizations.insert_one(doc)
    doc.pop("_id", None)
    # Mark deployment demobilized (but worker not yet available until clearance)
    await db.deployments.update_one(
        {"id": p.deployment_id},
        {"$set": {"status": "demobilized",
                  "demobilization_initiated_at": now_iso()}})
    return doc


class ClearanceIn(BaseModel):
    section: str  # store | safety | project | hr | logistics
    status: str   # pending | in_progress | ok | failed | not_required
    remarks: Optional[str] = None


@router.post("/demobilizations/{did}/clearance")
async def update_clearance(did: str, p: ClearanceIn,
                           user: dict = Depends(require_permission("hr_onboarding", "write"))):
    sec_map = {"store": "store_clearance", "safety": "safety_clearance",
               "project": "project_clearance", "hr": "hr_clearance",
               "logistics": "logistics_status"}
    if p.section not in sec_map:
        raise HTTPException(400, f"section must be {list(sec_map)}")
    if p.status not in {"pending", "in_progress", "ok", "failed", "not_required"}:
        raise HTTPException(400, "invalid status")
    field = sec_map[p.section]
    await db.hr_demobilizations.update_one(
        {"id": did},
        {"$set": {field: p.status,
                  f"{p.section}_remarks": p.remarks,
                  f"{p.section}_updated_at": now_iso(),
                  f"{p.section}_updated_by": user.get("name") or user.get("email")}})
    return await db.hr_demobilizations.find_one({"id": did}, {"_id": 0})


@router.post("/demobilizations/{did}/close")
async def close_demobilization(did: str,
                               user: dict = Depends(require_permission("hr_onboarding", "write"))):
    row = await db.hr_demobilizations.find_one({"id": did}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Demobilization not found")
    pending = []
    for fld in ("store_clearance", "safety_clearance", "project_clearance",
                "hr_clearance", "logistics_status"):
        st = row.get(fld)
        if st in (None, "pending", "in_progress", "failed"):
            pending.append(f"{fld}={st or 'pending'}")
    if pending:
        raise HTTPException(400, f"Cannot close — pending clearances: {', '.join(pending)}")
    await db.hr_demobilizations.update_one(
        {"id": did}, {"$set": {"status": "closed", "closed_at": now_iso(),
                               "final_status": "completed"}})
    # Close the deployment
    await db.deployments.update_one(
        {"id": row["deployment_id"]},
        {"$set": {"status": "closed", "actual_end_date": _today(),
                  "demobilization_completed_at": now_iso()}})
    # Mark worker available again
    dep = await db.deployments.find_one({"id": row["deployment_id"]}, {"_id": 0})
    if dep and dep.get("person_type") == "worker":
        await db.hr_workers.update_one(
            {"id": dep["employee_id"]},
            {"$set": {"current_project_code": None, "current_status": "available"}})
    return await db.hr_demobilizations.find_one({"id": did}, {"_id": 0})


@router.get("/demobilizations")
async def list_demobilizations(project_code: Optional[str] = None,
                               status: Optional[str] = None,
                               user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    return await db.hr_demobilizations.find(q, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)


# ──────────────────────────────────────────────────────────────────────────────
# 6.  REPLACEMENT REQUEST
# ──────────────────────────────────────────────────────────────────────────────
class ReplacementIn(BaseModel):
    project_code: str
    site_location: Optional[str] = None
    existing_employee_id: str
    existing_deployment_id: Optional[str] = None
    reason: str
    required_skill: str
    required_date: Optional[str] = None
    urgency: str = "medium"
    suggested_replacement_id: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/replacements")
async def create_replacement(p: ReplacementIn, request: Request,
                             user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if p.urgency not in URGENCY:
        raise HTTPException(400, f"urgency must be {sorted(URGENCY)}")
    if not p.reason.strip():
        raise HTTPException(400, "reason is required")
    rep_no = await _seq("REP-")
    doc = {
        "id": new_id(), "replacement_no": rep_no,
        **p.model_dump(),
        "approval_status": "pending",
        "approved_by_id": None, "approved_by_name": None, "approved_at": None,
        "deployment_id": None,
        "status": "open",
        "created_at": now_iso(),
        "requested_by_id": user["id"],
        "requested_by_name": user.get("name") or user.get("email"),
    }
    await db.hr_replacement_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/replacements/{rid}/approve")
async def approve_replacement(rid: str, p: ApprovalIn,
                              user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager",
                                "dept_head", "hr_executive", "project_manager"}:
        raise HTTPException(403, "Only Manager+ can approve replacement requests")
    row = await db.hr_replacement_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Replacement request not found")
    upd = {
        "approval_status": "approved" if p.decision == "approve" else "rejected",
        "approved_by_id": user["id"],
        "approved_by_name": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "approval_remarks": p.remarks,
        "status": "approved" if p.decision == "approve" else "rejected",
    }
    await db.hr_replacement_requests.update_one({"id": rid}, {"$set": upd})
    return await db.hr_replacement_requests.find_one({"id": rid}, {"_id": 0})


@router.get("/replacements")
async def list_replacements(project_code: Optional[str] = None,
                            status: Optional[str] = None,
                            user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    return await db.hr_replacement_requests.find(q, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)


# ──────────────────────────────────────────────────────────────────────────────
# 7.  ROLLUPS — Project / Site / Calendar
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/project-manpower")
async def project_manpower(project_code: Optional[str] = None,
                           user: dict = Depends(require_permission("hr_onboarding", "read"))):
    match: Dict[str, Any] = {"status": {"$in": ["active", "mobilized", "approved", "planned"]}}
    if project_code:
        match["$or"] = [{"project_code": project_code}, {"project": project_code}]
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"project": {"$ifNull": ["$project_code", "$project"]},
                    "skill": {"$ifNull": ["$skill", "$site_role"]}},
            "count": {"$sum": 1},
            "active": {"$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}},
            "planned": {"$sum": {"$cond": [{"$eq": ["$status", "planned"]}, 1, 0]}},
            "mobilized": {"$sum": {"$cond": [{"$eq": ["$status", "mobilized"]}, 1, 0]}},
        }},
        {"$sort": {"_id.project": 1, "_id.skill": 1}},
    ]
    rows = await db.deployments.aggregate(pipeline).to_list(1000)
    return [{
        "project_code": r["_id"]["project"],
        "skill": r["_id"]["skill"],
        "total": r["count"], "active": r["active"],
        "planned": r["planned"], "mobilized": r["mobilized"],
    } for r in rows]


@router.get("/site-manpower")
async def site_manpower(site_location: Optional[str] = None,
                        user: dict = Depends(require_permission("hr_onboarding", "read"))):
    match: Dict[str, Any] = {"status": {"$in": ["active", "mobilized", "approved"]}}
    if site_location:
        match["$or"] = [{"site_location": site_location}, {"site": site_location}]
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"site": {"$ifNull": ["$site_location", "$site"]},
                    "project": {"$ifNull": ["$project_code", "$project"]}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    rows = await db.deployments.aggregate(pipeline).to_list(1000)
    return [{"site_location": r["_id"]["site"],
             "project_code": r["_id"]["project"],
             "headcount": r["count"]} for r in rows]


@router.get("/deployment-calendar")
async def deployment_calendar(from_date: str = Query(...),
                              to_date: str = Query(...),
                              project_code: Optional[str] = None,
                              user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {
        "$or": [
            {"deployment_start_date": {"$gte": from_date, "$lte": to_date}},
            {"start_date": {"$gte": from_date, "$lte": to_date}},
        ]
    }
    if project_code:
        q = {"$and": [q, {"$or": [{"project_code": project_code}, {"project": project_code}]}]}
    rows = await db.deployments.find(q, {"_id": 0}) \
        .sort("deployment_start_date", 1).to_list(2000)
    return [{
        "deployment_no": r.get("deployment_no"),
        "employee": r.get("employee"),
        "project_code": r.get("project_code") or r.get("project"),
        "site_location": r.get("site_location") or r.get("site"),
        "skill": r.get("skill") or r.get("site_role"),
        "start": r.get("deployment_start_date") or r.get("start_date"),
        "end": r.get("expected_end_date") or r.get("end_date"),
        "status": r.get("status"),
    } for r in rows]


@router.get("/shortage-report")
async def shortage_report(user: dict = Depends(require_permission("hr_onboarding", "read"))):
    rows = await db.hr_manpower_requirements.find(
        {"approval_status": "approved", "total_shortage": {"$gt": 0}},
        {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# 8.  Phase-3 Dashboard
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def hr3_dashboard(user: dict = Depends(require_permission("hr_onboarding", "read"))):
    active_deployments = await db.deployments.count_documents({"status": "active"})
    planned = await db.deployments.count_documents({"status": "planned"})
    mobilizations_open = await db.hr_mobilizations.count_documents({"status": "open"})
    demob_open = await db.hr_demobilizations.count_documents({"status": "open"})
    open_requirements = await db.hr_manpower_requirements.count_documents(
        {"status": {"$in": ["open", "approved"]}})
    shortage_docs = await db.hr_manpower_requirements.find(
        {"total_shortage": {"$gt": 0}}, {"_id": 0, "total_shortage": 1}).to_list(500)
    total_shortage = sum(d.get("total_shortage", 0) for d in shortage_docs)
    replacements_open = await db.hr_replacement_requests.count_documents({"status": "open"})
    return {
        "as_of": now_iso(),
        "open_requirements": open_requirements,
        "total_shortage": total_shortage,
        "active_deployments": active_deployments,
        "planned_deployments": planned,
        "mobilizations_open": mobilizations_open,
        "demobilizations_open": demob_open,
        "replacements_open": replacements_open,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 9.  Sales → HR sync
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/sales-requirements")
async def sales_requirements(user: dict = Depends(require_permission("hr_onboarding", "read"))):
    """Pull won-quotation / order rows that mention manpower for HR planning."""
    rows = await db.enquiries.find(
        {"$or": [
            {"manpower_requirements": {"$exists": True, "$nin": [None, ""]}},
            {"service_categories": {"$in": ["manpower", "scaffolding", "painting",
                                            "roof_sheeting", "rope_access"]}},
        ]}, {"_id": 0}).sort("enquiry_date", -1).limit(200).to_list(200)
    out = []
    for r in rows:
        out.append({
            "enquiry_id": r.get("id"),
            "client": r.get("customer") or r.get("client_name"),
            "site_location": r.get("site_location"),
            "service_type": r.get("service_type"),
            "service_categories": r.get("service_categories"),
            "manpower_requirements": r.get("manpower_requirements"),
            "expected_value": r.get("expected_value"),
            "submission_deadline": r.get("submission_deadline"),
            "enquiry_date": r.get("enquiry_date"),
            "status": r.get("status"),
        })
    return out
