"""HR Phase 1 — Worker / Designation / Skill / Category masters + Medical & Police
Verification registers + consolidated HR Dashboard. Purely additive.
"""
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/hr1", tags=["hr-phase1"])


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


# 1. Designation Master
class DesignationIn(BaseModel):
    code: str
    name: str
    department_id: Optional[str] = None
    level: Optional[str] = None
    active: bool = True


@router.get("/designations")
async def list_designations(user: dict = Depends(require_permission("employees", "read"))):
    return await db.hr_designations.find({}, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/designations")
async def create_designation(p: DesignationIn, request: Request,
                             user: dict = Depends(require_permission("employees", "write"))):
    code = p.code.upper()
    if await db.hr_designations.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(409, f"Designation '{code}' already exists")
    doc = {**p.model_dump(), "code": code, "id": new_id(),
            "created_by": user["id"], "created_at": now_iso()}
    await db.hr_designations.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="hr_designations", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/designations/{did}")
async def update_designation(did: str, p: DesignationIn, request: Request,
                              user: dict = Depends(require_permission("employees", "write"))):
    if not await db.hr_designations.find_one({"id": did}, {"_id": 0}):
        raise HTTPException(404, "Not found")
    upd = {**p.model_dump(), "code": p.code.upper(), "updated_at": now_iso(), "updated_by": user["id"]}
    await db.hr_designations.update_one({"id": did}, {"$set": upd})
    return await db.hr_designations.find_one({"id": did}, {"_id": 0})


@router.delete("/designations/{did}")
async def delete_designation(did: str, request: Request,
                              user: dict = Depends(require_permission("employees", "delete"))):
    if await db.employees.count_documents({"designation_id": did}):
        raise HTTPException(400, "Cannot delete — employees reference this designation")
    await db.hr_designations.delete_one({"id": did})
    return {"ok": True}


# 2. Skill / Trade Master
class SkillIn(BaseModel):
    code: str
    name: str
    category: Optional[str] = None
    certification_required: bool = False
    safety_training_required: bool = False
    medical_fitness_required: bool = False
    active: bool = True


@router.get("/skills")
async def list_skills(user: dict = Depends(require_permission("employees", "read"))):
    return await db.hr_skills.find({}, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/skills")
async def create_skill(p: SkillIn, request: Request,
                       user: dict = Depends(require_permission("employees", "write"))):
    code = p.code.upper()
    if await db.hr_skills.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(409, f"Skill '{code}' already exists")
    doc = {**p.model_dump(), "code": code, "id": new_id(),
            "created_by": user["id"], "created_at": now_iso()}
    await db.hr_skills.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="hr_skills", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/skills/{sid}")
async def update_skill(sid: str, p: SkillIn, request: Request,
                       user: dict = Depends(require_permission("employees", "write"))):
    if not await db.hr_skills.find_one({"id": sid}, {"_id": 0}):
        raise HTTPException(404, "Not found")
    upd = {**p.model_dump(), "code": p.code.upper(), "updated_at": now_iso(), "updated_by": user["id"]}
    await db.hr_skills.update_one({"id": sid}, {"$set": upd})
    return await db.hr_skills.find_one({"id": sid}, {"_id": 0})


@router.delete("/skills/{sid}")
async def delete_skill(sid: str, user: dict = Depends(require_permission("employees", "delete"))):
    await db.hr_skills.delete_one({"id": sid})
    return {"ok": True}


# 3. Employee Category Master
class CategoryIn(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    active: bool = True


@router.get("/employee-categories")
async def list_categories(user: dict = Depends(require_permission("employees", "read"))):
    return await db.hr_employee_categories.find({}, {"_id": 0}).sort("name", 1).to_list(200)


@router.post("/employee-categories")
async def create_category(p: CategoryIn, user: dict = Depends(require_permission("employees", "write"))):
    code = p.code.upper()
    if await db.hr_employee_categories.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(409, "Category already exists")
    doc = {**p.model_dump(), "code": code, "id": new_id(),
            "created_by": user["id"], "created_at": now_iso()}
    await db.hr_employee_categories.insert_one(doc); doc.pop("_id", None)
    return doc


@router.delete("/employee-categories/{cid}")
async def delete_category(cid: str, user: dict = Depends(require_permission("employees", "delete"))):
    await db.hr_employee_categories.delete_one({"id": cid})
    return {"ok": True}


# 4. Worker / Labour Master (separate from employees)
WORKER_TYPES = ("skilled", "semi_skilled", "unskilled", "helper", "supervisor",
                "technician", "rope_access", "painter", "scaffolder",
                "fitter", "welder", "other")
WAGE_TYPES = ("daily", "monthly", "shift", "hourly", "piece_rate")


class WorkerIn(BaseModel):
    code: str
    name: str
    mobile: str
    aadhaar: Optional[str] = None
    pan: Optional[str] = None
    bank_account: Optional[str] = None
    ifsc: Optional[str] = None
    skill_id: Optional[str] = None
    skill_name: Optional[str] = None
    service_category: Optional[str] = None
    worker_type: str = "skilled"
    wage_type: str = "daily"
    wage_amount: float = 0.0
    contractor_name: Optional[str] = None
    medical_fitness: bool = False
    safety_induction: bool = False
    document_status: str = "pending"     # pending | verified | rejected
    current_project_code: Optional[str] = None
    current_site_code: Optional[str] = None
    availability: str = "available"      # available | deployed | leave | exited
    photo_url: Optional[str] = None
    remarks: Optional[str] = None
    active: bool = True


@router.get("/workers")
async def list_workers(skill_id: Optional[str] = None, availability: Optional[str] = None,
                       project_code: Optional[str] = None, active: Optional[bool] = None,
                       user: dict = Depends(require_permission("employees", "read"))):
    q: dict = {}
    if skill_id:
        q["skill_id"] = skill_id
    if availability:
        q["availability"] = availability
    if project_code:
        q["current_project_code"] = project_code
    if active is not None:
        q["active"] = active
    return await db.hr_workers.find(q, {"_id": 0}).sort("name", 1).to_list(2000)


@router.post("/workers")
async def create_worker(p: WorkerIn, request: Request,
                        user: dict = Depends(require_permission("employees", "write"))):
    if p.worker_type not in WORKER_TYPES:
        raise HTTPException(400, f"worker_type must be in {WORKER_TYPES}")
    if p.wage_type not in WAGE_TYPES:
        raise HTTPException(400, f"wage_type must be in {WAGE_TYPES}")
    if not p.name.strip():
        raise HTTPException(400, "name is mandatory")
    if not p.mobile.strip():
        raise HTTPException(400, "mobile is mandatory")
    code = p.code.upper()
    if await db.hr_workers.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(409, f"Worker code '{code}' already exists")
    if p.aadhaar:
        if await db.hr_workers.find_one({"aadhaar": p.aadhaar}, {"_id": 0}):
            raise HTTPException(409, "Aadhaar already exists for another worker")
    doc = {**p.model_dump(), "code": code, "id": new_id(),
            "created_by": user["id"], "created_at": now_iso(), "updated_at": now_iso()}
    await db.hr_workers.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="hr_workers", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/workers/{wid}")
async def update_worker(wid: str, p: WorkerIn, request: Request,
                        user: dict = Depends(require_permission("employees", "write"))):
    existing = await db.hr_workers.find_one({"id": wid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Worker not found")
    upd = {**p.model_dump(), "code": p.code.upper(), "updated_at": now_iso(), "updated_by": user["id"]}
    await db.hr_workers.update_one({"id": wid}, {"$set": upd})
    row = await db.hr_workers.find_one({"id": wid}, {"_id": 0})
    await audit(user=user, action="update", resource="hr_workers", record_id=wid, before=existing, after=row, ip=_ip(request))
    return row


@router.delete("/workers/{wid}")
async def delete_worker(wid: str, request: Request,
                        user: dict = Depends(require_permission("employees", "delete"))):
    existing = await db.hr_workers.find_one({"id": wid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Worker not found")
    # Soft-delete: mark inactive instead of hard-delete (rule 10)
    await db.hr_workers.update_one({"id": wid}, {"$set": {"active": False, "availability": "exited", "exited_at": now_iso()}})
    await audit(user=user, action="soft_delete", resource="hr_workers", record_id=wid, before=existing, ip=_ip(request))
    return {"ok": True}


# 5. Medical Fitness & Police Verification Registers
class FitnessIn(BaseModel):
    person_type: str           # employee | worker
    person_id: str
    person_name: Optional[str] = None
    test_date: str
    fitness_status: str        # fit | unfit | fit_with_restrictions
    issued_by: Optional[str] = None
    valid_till: Optional[str] = None
    restrictions: Optional[str] = None
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None


@router.get("/medical-fitness")
async def list_fitness(person_id: Optional[str] = None,
                        user: dict = Depends(require_permission("employees", "read"))):
    q: dict = {"person_id": person_id} if person_id else {}
    return await db.hr_medical_fitness.find(q, {"_id": 0}).sort("test_date", -1).to_list(2000)


@router.post("/medical-fitness")
async def create_fitness(p: FitnessIn, request: Request,
                          user: dict = Depends(require_permission("employees", "write"))):
    if p.fitness_status not in ("fit", "unfit", "fit_with_restrictions"):
        raise HTTPException(400, "fitness_status must be fit | unfit | fit_with_restrictions")
    doc = {**p.model_dump(), "id": new_id(),
            "created_by": user["id"], "created_at": now_iso()}
    await db.hr_medical_fitness.insert_one(doc); doc.pop("_id", None)
    # Mirror onto the person record
    coll = "employees" if p.person_type == "employee" else "hr_workers"
    await db[coll].update_one({"id": p.person_id}, {"$set": {
        "medical_fitness": p.fitness_status == "fit",
        "medical_fitness_valid_till": p.valid_till,
    }})
    await audit(user=user, action="create", resource="hr_medical_fitness", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


class PoliceIn(BaseModel):
    person_type: str
    person_id: str
    person_name: Optional[str] = None
    verification_date: str
    status: str                  # clear | pending | rejected | not_required
    verifying_agency: Optional[str] = None
    reference_no: Optional[str] = None
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None


@router.get("/police-verification")
async def list_police(person_id: Optional[str] = None,
                       user: dict = Depends(require_permission("employees", "read"))):
    q: dict = {"person_id": person_id} if person_id else {}
    return await db.hr_police_verification.find(q, {"_id": 0}).sort("verification_date", -1).to_list(2000)


@router.post("/police-verification")
async def create_police(p: PoliceIn, request: Request,
                         user: dict = Depends(require_permission("employees", "write"))):
    if p.status not in ("clear", "pending", "rejected", "not_required"):
        raise HTTPException(400, "Invalid status")
    doc = {**p.model_dump(), "id": new_id(),
            "created_by": user["id"], "created_at": now_iso()}
    await db.hr_police_verification.insert_one(doc); doc.pop("_id", None)
    coll = "employees" if p.person_type == "employee" else "hr_workers"
    await db[coll].update_one({"id": p.person_id}, {"$set": {"police_verification_status": p.status}})
    await audit(user=user, action="create", resource="hr_police_verification", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


# 6. HR Dashboard (20 tiles)
@router.get("/dashboard")
async def hr_dashboard(user: dict = Depends(require_permission("employees", "read"))):
    today = datetime.now(timezone.utc).date().isoformat()
    horizon = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

    active_employees = await db.employees.count_documents({"status": {"$ne": "inactive"}})
    active_workers = await db.hr_workers.count_documents({"active": True})
    office_staff = await db.employees.count_documents({"employee_type": "office_staff", "status": {"$ne": "inactive"}})
    site_staff = await db.employees.count_documents({"employee_type": "site_staff", "status": {"$ne": "inactive"}})
    skilled = await db.hr_workers.count_documents({"worker_type": "skilled", "active": True})
    available = await db.hr_workers.count_documents({"availability": "available", "active": True})
    deployed = await db.hr_workers.count_documents({"availability": "deployed", "active": True})

    pending_docs = await db.hr_documents.count_documents({"verification_status": "pending"}) \
        if "hr_documents" in await db.list_collection_names() else 0
    expiring_docs = await db.hr_documents.count_documents({
        "expiry_date": {"$ne": None, "$gte": today, "$lte": horizon},
    }) if "hr_documents" in await db.list_collection_names() else 0

    medical_expiring = await db.hr_medical_fitness.count_documents({
        "valid_till": {"$ne": None, "$gte": today, "$lte": horizon},
    })
    police_pending = await db.hr_police_verification.count_documents({"status": "pending"})

    # Recent joinings / exits (30d)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent_joining = await db.employees.count_documents({"created_at": {"$gte": cutoff}})
    recent_exit = await db.employees.count_documents({"exit_date": {"$gte": cutoff[:10]}}) \
        if await db.employees.count_documents({"exit_date": {"$ne": None}}) else 0

    pending_approvals = await db.approvals.count_documents({
        "status": "pending", "module": {"$regex": "hr|leave|onboard", "$options": "i"},
    }) if "approvals" in await db.list_collection_names() else 0

    inactive_count = await db.employees.count_documents({"status": "inactive"})

    # Skill-wise manpower
    by_skill = await db.hr_workers.aggregate([
        {"$match": {"active": True}},
        {"$group": {"_id": "$skill_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 10},
    ]).to_list(10)

    # Project-wise deployed
    by_project = await db.hr_workers.aggregate([
        {"$match": {"active": True, "availability": "deployed", "current_project_code": {"$ne": None}}},
        {"$group": {"_id": "$current_project_code", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 10},
    ]).to_list(10)

    return {
        "as_of": now_iso(),
        "active_employees": active_employees,
        "active_workers": active_workers,
        "office_staff": office_staff,
        "site_staff": site_staff,
        "skilled_workers": skilled,
        "available_manpower": available,
        "deployed_manpower": deployed,
        "pending_documents": pending_docs,
        "expiring_documents_30d": expiring_docs,
        "medical_expiring_30d": medical_expiring,
        "police_verification_pending": police_pending,
        "recent_joinings_30d": recent_joining,
        "recent_exits_30d": recent_exit,
        "hr_pending_approvals": pending_approvals,
        "inactive_employees": inactive_count,
        "by_skill": by_skill,
        "by_project": by_project,
    }


# 7. Seed defaults — ITL trades
ITL_SKILLS = [
    ("SCAFFOLDER", "Scaffolder", True, True, True),
    ("PAINTER", "Painter", True, True, True),
    ("ROPE", "Rope Access Technician", True, True, True),
    ("ROOF", "Roof Sheeting Technician", True, True, True),
    ("FITTER", "Fitter", True, True, True),
    ("WELDER", "Welder", True, True, True),
    ("HELPER", "Helper", False, True, False),
    ("SUPERVISOR", "Supervisor", False, True, False),
    ("SAFETY", "Safety Steward", True, True, False),
    ("STORE", "Store Helper", False, False, False),
    ("DRIVER", "Driver", True, True, True),
    ("OPERATOR", "Machine Operator", True, True, True),
    ("RIGGER", "Rigger", True, True, True),
    ("FABRICATOR", "Fabricator", True, True, True),
    ("GENERAL", "General Worker", False, True, False),
]

ITL_CATEGORIES = [
    ("OFFICE_STAFF", "Office Staff"),
    ("SITE_STAFF", "Site Staff"),
    ("SKILLED_WORKER", "Skilled Worker"),
    ("SEMI_SKILLED_WORKER", "Semi-Skilled Worker"),
    ("UNSKILLED_WORKER", "Unskilled Worker"),
    ("CONTRACT_WORKER", "Contract Worker"),
    ("LABOUR_CONTRACTOR_WORKER", "Labour Contractor Worker"),
]


@router.post("/seed-defaults")
async def seed_defaults(user: dict = Depends(require_permission("employees", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager", "hr_executive"}:
        raise HTTPException(403, "Only Admin / Director / GM / HR can seed HR defaults")
    s_added = 0
    for code, name, cert, safety, med in ITL_SKILLS:
        if not await db.hr_skills.find_one({"code": code}, {"_id": 0}):
            await db.hr_skills.insert_one({
                "id": new_id(), "code": code, "name": name, "category": "trade",
                "certification_required": cert, "safety_training_required": safety,
                "medical_fitness_required": med, "active": True,
                "created_by": user["id"], "created_at": now_iso(),
            })
            s_added += 1
    c_added = 0
    for code, name in ITL_CATEGORIES:
        if not await db.hr_employee_categories.find_one({"code": code}, {"_id": 0}):
            await db.hr_employee_categories.insert_one({
                "id": new_id(), "code": code, "name": name, "active": True,
                "created_by": user["id"], "created_at": now_iso(),
            })
            c_added += 1
    return {"skills_added": s_added, "categories_added": c_added,
            "total_skills": await db.hr_skills.count_documents({}),
            "total_categories": await db.hr_employee_categories.count_documents({})}
