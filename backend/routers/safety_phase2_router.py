"""Safety · PPE + Readiness + Overrides + Training-Expiry · Iter 128 (Phase 2)
==============================================================================

Four thin concerns bundled into one router because they share the same
readiness-checking domain:

* PPE Requirement master   — what PPE is required for a given (project /
                             service / activity / permit_type / hazard)
* PPE Compliance           — computed comparison of `ppe_issuance` vs.
                             requirements per (worker or project)
* Safety Readiness         — 11-factor aggregate per project (or per
                             worker) with a final `ready|conditional|
                             not_ready|blocked` classification
* Safety Override          — record + Safety-Head approval to proceed when
                             readiness is blocked
* Training Expiry Register — helper endpoint that buckets existing
                             `safety_trainings` by days-until-expiry
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission
from approval_engine import insert_approval

router = APIRouter(prefix="/safety", tags=["safety-phase2"])


# ─── PPE Requirement master ───────────────────────────────────────────────
class PpeRequirementIn(BaseModel):
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    service_type: Optional[str] = None
    activity: Optional[str] = ""
    permit_type_id: Optional[str] = None
    hazard_category_id: Optional[str] = None
    required_ppe_ids: List[str] = Field(..., min_length=1)      # references safety_ppe_categories
    notes: Optional[str] = ""
    active: bool = True


@router.get("/ppe-requirements")
async def list_ppe_reqs(project_id: Optional[str] = None,
                        user: dict = Depends(require_permission("safety_ppe_reqs", "read"))):
    q: Dict[str, Any] = {"active": True}
    if project_id:
        q["project_id"] = project_id
    return await db.safety_ppe_requirements.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/ppe-requirements")
async def create_ppe_req(payload: PpeRequirementIn,
                          user: dict = Depends(require_permission("safety_ppe_reqs", "write"))):
    doc = {
        **payload.model_dump(),
        "id": new_id(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    await db.safety_ppe_requirements.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/ppe-requirements/{rid}")
async def update_ppe_req(rid: str, payload: PpeRequirementIn,
                          user: dict = Depends(require_permission("safety_ppe_reqs", "write"))):
    existing = await db.safety_ppe_requirements.find_one({"id": rid}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(404, "PPE requirement not found")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.safety_ppe_requirements.update_one({"id": rid}, {"$set": patch})
    return await db.safety_ppe_requirements.find_one({"id": rid}, {"_id": 0})


@router.delete("/ppe-requirements/{rid}")
async def delete_ppe_req(rid: str,
                          user: dict = Depends(require_permission("safety_ppe_reqs", "delete"))):
    await db.safety_ppe_requirements.update_one({"id": rid}, {"$set": {
        "active": False, "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }})
    return {"ok": True, "soft_deleted": True}


# ─── PPE Compliance ────────────────────────────────────────────────────────
@router.get("/ppe-compliance")
async def ppe_compliance(project_id: Optional[str] = None,
                          worker_id: Optional[str] = None,
                          user: dict = Depends(require_permission("safety_ppe_reqs", "read"))):
    """Return, for the requested scope, {required, issued, missing, compliant}."""
    req_q: Dict[str, Any] = {"active": True}
    if project_id:
        req_q["project_id"] = project_id
    reqs = await db.safety_ppe_requirements.find(req_q, {"_id": 0}).to_list(500)
    required_ppe: set[str] = set()
    for r in reqs:
        for pid in (r.get("required_ppe_ids") or []):
            required_ppe.add(pid)

    iss_q: Dict[str, Any] = {}
    if project_id:
        iss_q["project"] = project_id
    if worker_id:
        iss_q["worker_id"] = worker_id
    issued = await db.ppe_issuance.find(iss_q, {"_id": 0}).to_list(2000)
    today = datetime.now(timezone.utc).date().isoformat()

    # An issuance counts as valid only when not expired and not marked damaged.
    valid_issued_ppe: set[str] = set()
    for i in issued:
        exp = i.get("expiry_date") or i.get("valid_till")
        if exp and exp < today:
            continue
        if (i.get("condition") or "").lower() in {"damaged", "unfit"}:
            continue
        pid = i.get("ppe_category_id") or i.get("ppe_id") or i.get("item")
        if pid:
            valid_issued_ppe.add(str(pid))

    missing = list(required_ppe - valid_issued_ppe)
    compliant = len(missing) == 0

    # Names for UI
    if required_ppe:
        cats = await db.safety_ppe_categories.find(
            {"id": {"$in": list(required_ppe)}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(500)
        name_by_id = {c["id"]: c["name"] for c in cats}
    else:
        name_by_id = {}

    return {
        "project_id": project_id,
        "worker_id": worker_id,
        "required_count": len(required_ppe),
        "issued_count": len(valid_issued_ppe),
        "missing_count": len(missing),
        "missing": [{"id": m, "name": name_by_id.get(m, m)} for m in missing],
        "compliant": compliant,
        "as_of": now_iso(),
    }


# ─── Safety Readiness (11-factor aggregate) ────────────────────────────────
class ReadinessQuery(BaseModel):
    project_id: str
    worker_id: Optional[str] = None
    activity: Optional[str] = None


def _classify(factors: List[Dict[str, Any]]) -> str:
    """Ready if all green; Blocked if any blocking factor is red; Not-Ready
    if any non-blocking red; Conditional if any yellow."""
    if any(f.get("state") == "red" and f.get("blocking") for f in factors):
        return "blocked"
    if any(f.get("state") == "red" for f in factors):
        return "not_ready"
    if any(f.get("state") == "yellow" for f in factors):
        return "conditional"
    return "ready"


@router.get("/readiness")
async def compute_readiness(project_id: str, worker_id: Optional[str] = None,
                             user: dict = Depends(require_permission("safety_readiness", "read"))):
    """Compute 11-factor readiness. Returns list of factors + overall classification."""
    if not project_id:
        raise HTTPException(400, "project_id is required")
    today = datetime.now(timezone.utc).date().isoformat()
    factors: List[Dict[str, Any]] = []

    # 1. HIRA approved
    hira_ok = await db.safety_hira.find_one(
        {"project_id": project_id, "status": {"$in": ["approved", "closed"]}}, {"_id": 0, "id": 1}
    )
    factors.append({"key": "hira", "label": "HIRA Approved",
                    "state": "green" if hira_ok else "red", "blocking": True,
                    "detail": None if hira_ok else "No approved HIRA on file for this project."})

    # 2. JSA approved
    jsa_ok = await db.safety_jsa.find_one(
        {"project_id": project_id, "status": {"$in": ["approved", "closed"]}}, {"_id": 0, "id": 1}
    )
    factors.append({"key": "jsa", "label": "JSA Approved",
                    "state": "green" if jsa_ok else "yellow", "blocking": False,
                    "detail": None if jsa_ok else "No approved JSA on file — consider adding one."})

    # 3. Work permit — is there an active one for this project?
    active_permit = await db.safety_work_permits.count_documents(
        {"project_id": project_id, "status": "active"}
    )
    factors.append({"key": "work_permit", "label": "Active Work Permit",
                    "state": "green" if active_permit else "yellow", "blocking": False,
                    "detail": f"{active_permit} active" if active_permit else "No active permits."})

    # 4-6. Worker-level factors (only when worker_id provided)
    if worker_id:
        # 4. Safety Induction — presence of an inducted-status training
        induction = await db.safety_trainings.find_one(
            {"employee_id": worker_id, "training_type": {"$regex": "induction", "$options": "i"},
             "status": {"$in": ["completed", "passed"]}},
            {"_id": 0, "id": 1, "expiry_date": 1},
        )
        induction_state = "red"
        induction_detail = "No completed safety induction on file."
        if induction:
            if induction.get("expiry_date") and induction["expiry_date"] < today:
                induction_state = "red"
                induction_detail = f"Induction expired on {induction['expiry_date']}."
            else:
                induction_state = "green"
                induction_detail = None
        factors.append({"key": "induction", "label": "Safety Induction",
                        "state": induction_state, "blocking": True, "detail": induction_detail})

        # 5. Training — any non-expired training
        trained = await db.safety_trainings.count_documents({
            "employee_id": worker_id,
            "status": {"$in": ["completed", "passed"]},
            "$or": [{"expiry_date": None}, {"expiry_date": {"$gte": today}}],
        })
        factors.append({"key": "training", "label": "Training Valid",
                        "state": "green" if trained else "yellow", "blocking": False,
                        "detail": f"{trained} valid training record(s)" if trained else "No valid training on file."})

        # 6. Medical Fitness — via HR
        med = None
        if "hr_medical_fitness" in await db.list_collection_names():
            med = await db.hr_medical_fitness.find_one(
                {"employee_id": worker_id}, {"_id": 0, "status": 1, "valid_till": 1, "restrictions": 1}
            )
        med_state = "red"
        med_detail = "No medical fitness record on file."
        if med:
            unfit = (med.get("status") or "").lower() in {"unfit", "not_fit"}
            expired = med.get("valid_till") and med["valid_till"] < today
            if unfit:
                med_detail = f"Marked unfit. {med.get('restrictions') or ''}"
                med_state = "red"
            elif expired:
                med_detail = f"Medical expired on {med['valid_till']}."
                med_state = "red"
            else:
                med_state = "green"
                med_detail = None
        factors.append({"key": "medical", "label": "Medical Fitness",
                        "state": med_state, "blocking": True, "detail": med_detail})

    # 7. PPE compliance for the project
    ppe = await ppe_compliance(project_id=project_id, worker_id=worker_id, user=user)  # type: ignore[arg-type]
    factors.append({"key": "ppe", "label": "PPE Compliance",
                    "state": "green" if ppe["compliant"] else "red", "blocking": True,
                    "detail": None if ppe["compliant"] else f"Missing PPE: {', '.join(m['name'] for m in ppe['missing'][:4])}"})

    # 8. Safety Plan
    plan = await db.safety_plans.find_one({"project_id": project_id, "status": "active"}, {"_id": 0, "id": 1})
    factors.append({"key": "safety_plan", "label": "Safety Plan Active",
                    "state": "green" if plan else "yellow", "blocking": False,
                    "detail": None if plan else "No active safety plan for this project."})

    # 9. Open Safety Observations
    open_obs = await db.safety_reports.count_documents(
        {"project": project_id, "type": "observation", "status": {"$in": ["open", "under_review"]}}
    )
    factors.append({"key": "observations", "label": "Open Observations",
                    "state": "yellow" if open_obs else "green", "blocking": False,
                    "detail": f"{open_obs} open" if open_obs else None})

    # 10. Open Incidents
    open_inc = await db.safety_reports.count_documents(
        {"project": project_id, "type": {"$in": ["incident", "near_miss"]},
         "status": {"$in": ["open", "under_review"]}}
    )
    factors.append({"key": "incidents", "label": "Open Incidents / Near Misses",
                    "state": "red" if open_inc else "green", "blocking": False,
                    "detail": f"{open_inc} open" if open_inc else None})

    # 11. Documents expiring
    in_30 = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    docs_alert = await db.safety_documents.count_documents({
        "project_id": project_id,
        "expires_on": {"$lt": in_30, "$ne": None},
    })
    factors.append({"key": "docs", "label": "Safety Documents",
                    "state": "yellow" if docs_alert else "green", "blocking": False,
                    "detail": f"{docs_alert} expiring/expired" if docs_alert else None})

    classification = _classify(factors)
    return {
        "project_id": project_id,
        "worker_id": worker_id,
        "factors": factors,
        "classification": classification,
        "as_of": now_iso(),
    }


# ─── Safety Override ───────────────────────────────────────────────────────
class SafetyOverrideIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    worker_id: Optional[str] = None
    activity: Optional[str] = ""
    blocked_factor: str = Field(..., min_length=1)   # e.g. "medical", "induction"
    reason: str = Field(..., min_length=10, max_length=1000)
    valid_until: Optional[str] = None


@router.get("/overrides")
async def list_overrides(project_id: Optional[str] = None,
                          status: Optional[str] = None,
                          user: dict = Depends(require_permission("safety_overrides", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    return await db.safety_overrides.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/overrides")
async def request_override(payload: SafetyOverrideIn,
                            user: dict = Depends(require_permission("safety_overrides", "write"))):
    """Records an override request + creates a Safety-Head approval doc."""
    ovr_id = new_id()
    doc = {
        **payload.model_dump(),
        "id": ovr_id,
        "status": "pending",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
    }
    # Approval chain: single Safety Head step (dept_head of safety dept).
    chain = [{"role": "dept_head", "label": "Safety Head", "status": "pending",
              "approver": None, "at": None, "comment": None}]
    approval_doc = {
        "id": new_id(),
        "type": "safety_override",
        "module": "safety",
        "record_id": ovr_id,
        "title": f"Safety Override — {payload.blocked_factor} for project {payload.project_id}",
        "summary": payload.reason[:200],
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await insert_approval(approval_doc, skip_gate=True)
    doc["approval_id"] = approval_doc["id"]
    await db.safety_overrides.insert_one(doc)
    await db.safety_audit_log.insert_one({
        "id": new_id(),
        "record_kind": "safety_override",
        "record_id": ovr_id,
        "record_no": ovr_id[:8],
        "action": "requested",
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "role": user.get("role"),
        "at": now_iso(),
        "meta": {"blocked_factor": payload.blocked_factor, "project_id": payload.project_id},
    })
    doc.pop("_id", None)
    return doc


# ─── Training Expiry Register ──────────────────────────────────────────────
@router.get("/training-expiry")
async def training_expiry(days: int = 90,
                           user: dict = Depends(require_permission("safety_trainings", "read"))):
    """Buckets existing safety_trainings by days-until-expiry: <=0 expired,
    <=30 expiring_soon, <=90 expiring_later, else valid.
    Uses the already-existing `safety_trainings` collection — no duplication."""
    if days < 1 or days > 365:
        raise HTTPException(400, "days must be 1..365")
    today = datetime.now(timezone.utc).date()
    horizon_iso = (today + timedelta(days=days)).isoformat()

    rows = await db.safety_trainings.find(
        {"expiry_date": {"$ne": None, "$lte": horizon_iso}},
        {"_id": 0},
    ).sort("expiry_date", 1).to_list(2000)

    today_iso = today.isoformat()
    in_30 = (today + timedelta(days=30)).isoformat()
    out = {"expired": [], "expiring_soon": [], "expiring_later": []}
    for r in rows:
        e = r.get("expiry_date")
        if not e:
            continue
        if e < today_iso:
            out["expired"].append(r)
        elif e <= in_30:
            out["expiring_soon"].append(r)
        else:
            out["expiring_later"].append(r)
    return {
        "as_of": now_iso(),
        "horizon_days": days,
        "expired": out["expired"],
        "expiring_soon": out["expiring_soon"],
        "expiring_later": out["expiring_later"],
        "counts": {k: len(v) for k, v in out.items()},
    }
