"""Safety · Plans + Documents + Dashboard · Iter 127
====================================================

Three small resources under one router to keep the file count sane:

* Safety Plan Register — per-project safety plan doc (only one plan per
  project; upserts by project_id).
* Safety Document Register — arbitrary safety documents with expiry alerts
  (licenses, medical certificates, insurance, statutory approvals).
* Safety Dashboard — real KPI cards, all derived from actual DB counts.
"""
from __future__ import annotations
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission, get_current_user
from sequences import next_sequence

router = APIRouter(prefix="/safety", tags=["safety-plans-docs-dashboard"])


# ─── Safety Plan Register ─────────────────────────────────────────────────
class SafetyPlanIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    project_code: Optional[str] = None
    client_name: Optional[str] = None
    site_location: Optional[str] = None
    service_type: Optional[str] = None
    scope_summary: Optional[str] = ""
    key_hazards: Optional[str] = ""
    ppe_summary: Optional[str] = ""
    permits_summary: Optional[str] = ""
    manpower_competency: Optional[str] = ""
    emergency_plan: Optional[str] = ""
    prepared_by: Optional[str] = ""
    reviewed_by: Optional[str] = ""
    approved_by: Optional[str] = ""
    status: str = Field("draft", description="draft | active | closed")
    remarks: Optional[str] = ""


@router.get("/plans")
async def list_safety_plans(status: Optional[str] = None, project_id: Optional[str] = None,
                             user: dict = Depends(require_permission("safety_plans", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    return await db.safety_plans.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/plans")
async def create_safety_plan(payload: SafetyPlanIn,
                              user: dict = Depends(require_permission("safety_plans", "write"))):
    existing = await db.safety_plans.find_one({"project_id": payload.project_id})
    if existing:
        raise HTTPException(409, f"A Safety Plan already exists for this project ({existing.get('plan_no')})")
    plan_no = await next_sequence("SP")
    doc = {
        **payload.model_dump(),
        "id": new_id(),
        "plan_no": plan_no,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    await db.safety_plans.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/plans/{pid}")
async def update_safety_plan(pid: str, payload: SafetyPlanIn,
                              user: dict = Depends(require_permission("safety_plans", "write"))):
    existing = await db.safety_plans.find_one({"id": pid}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(404, "Safety Plan not found")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.safety_plans.update_one({"id": pid}, {"$set": patch})
    return await db.safety_plans.find_one({"id": pid}, {"_id": 0})


@router.delete("/plans/{pid}")
async def delete_safety_plan(pid: str,
                              user: dict = Depends(require_permission("safety_plans", "delete"))):
    await db.safety_plans.delete_one({"id": pid})
    return {"ok": True}


# ─── Safety Document Register ─────────────────────────────────────────────
class SafetyDocIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    doc_type: str = Field(..., max_length=60)      # license / certificate / insurance / statutory / policy / plan / other
    reference_no: Optional[str] = ""
    issued_by: Optional[str] = ""
    issued_on: Optional[str] = None                # YYYY-MM-DD
    expires_on: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    remarks: Optional[str] = ""
    file_ids: List[str] = Field(default_factory=list)


def _expiry_status(expires_on: Optional[str], today: date) -> str:
    if not expires_on:
        return "no_expiry"
    try:
        exp = datetime.strptime(expires_on, "%Y-%m-%d").date()
    except ValueError:
        return "no_expiry"
    days_left = (exp - today).days
    if days_left < 0:
        return "expired"
    if days_left <= 30:
        return "expiring_soon"
    return "valid"


@router.get("/documents")
async def list_safety_documents(status: Optional[str] = None, doc_type: Optional[str] = None,
                                 user: dict = Depends(require_permission("safety_documents", "read"))):
    q: Dict[str, Any] = {}
    if doc_type:
        q["doc_type"] = doc_type
    rows = await db.safety_documents.find(q, {"_id": 0}).sort("expires_on", 1).to_list(2000)
    today = datetime.now(timezone.utc).date()
    for r in rows:
        r["expiry_status"] = _expiry_status(r.get("expires_on"), today)
    if status:
        rows = [r for r in rows if r["expiry_status"] == status]
    return rows


@router.post("/documents")
async def create_safety_document(payload: SafetyDocIn,
                                  user: dict = Depends(require_permission("safety_documents", "write"))):
    doc = {
        **payload.model_dump(),
        "id": new_id(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    await db.safety_documents.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/documents/{did}")
async def update_safety_document(did: str, payload: SafetyDocIn,
                                  user: dict = Depends(require_permission("safety_documents", "write"))):
    existing = await db.safety_documents.find_one({"id": did}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(404, "Safety Document not found")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.safety_documents.update_one({"id": did}, {"$set": patch})
    return await db.safety_documents.find_one({"id": did}, {"_id": 0})


@router.delete("/documents/{did}")
async def delete_safety_document(did: str,
                                  user: dict = Depends(require_permission("safety_documents", "delete"))):
    await db.safety_documents.delete_one({"id": did})
    return {"ok": True}


# ─── Safety Dashboard (20 real cards) ─────────────────────────────────────
@router.get("/dashboard")
async def safety_dashboard(user: dict = Depends(get_current_user)):
    """Return 20 real KPI cards for the Safety dashboard. Each card carries a
    numeric `value` and an optional `deeplink` for drill-down."""
    today = datetime.now(timezone.utc).date()
    today_iso = today.isoformat()
    in_30d = (today + timedelta(days=30)).isoformat()

    # Parallel-ish counters (motor pipelines are lightweight)
    active_projects = await db.projects.count_documents({
        "status": {"$in": ["active", "in_progress", "planning"]},
    })
    project_ids_with_plans = await db.safety_plans.distinct("project_id", {"status": {"$in": ["active", "draft"]}})
    projects_with_plan = len([p for p in project_ids_with_plans if p])
    projects_missing_plan = max(active_projects - projects_with_plan, 0)

    hira_pending = await db.safety_hira.count_documents({"status": {"$in": ["pending_approval", "under_review"]}})
    jsa_pending  = await db.safety_jsa.count_documents({"status": {"$in": ["pending_approval", "under_review"]}})

    permits_pending = await db.work_permits.count_documents({"status": {"$in": ["pending", "draft", "submitted", "under_review"]}})
    permits_active  = await db.work_permits.count_documents({"status": "active"})
    permits_expired = await db.work_permits.count_documents({"$or": [
        {"status": "expired"},
        {"valid_until": {"$lt": today_iso}, "status": {"$in": ["active", "approved"]}},
    ]})

    # Safety observations & inspections
    inspections_due = await db.safety_inspections.count_documents({"status": "due"}) if "safety_inspections" in await db.list_collection_names() else 0
    open_observations = await db.safety_observations.count_documents({"status": {"$in": ["open", "under_review"]}}) \
        if "safety_observations" in await db.list_collection_names() else 0
    open_corrective = await db.safety_reports.count_documents({"type": "corrective_action", "status": {"$in": ["open", "under_review"]}})

    incidents = await db.safety_reports.count_documents({"type": "incident"})
    near_misses = await db.safety_reports.count_documents({"type": "near_miss"})

    ppe_pending = await db.ppe_issuance.count_documents({"status": {"$in": ["pending", "requested"]}}) \
        if "ppe_issuance" in await db.list_collection_names() else 0

    trainings_pending = await db.safety_trainings.count_documents({"status": {"$in": ["scheduled", "pending"]}}) \
        if "safety_trainings" in await db.list_collection_names() else 0

    # Medical fitness — HR letters typed 'medical_fitness' with status pending
    med_pending = await db.hr_letters.count_documents({"letter_type": "medical_fitness", "status": {"$ne": "issued"}}) \
        if "hr_letters" in await db.list_collection_names() else 0

    # Client safety audits — safety_reports with type='client_audit'
    client_audits_pending = await db.safety_reports.count_documents({"type": "client_audit", "status": {"$ne": "closed"}})

    # Safety documents expiring in the next 30 days
    docs_expiring = await db.safety_documents.count_documents({
        "expires_on": {"$gte": today_iso, "$lte": in_30d},
    })
    docs_expired = await db.safety_documents.count_documents({
        "expires_on": {"$lt": today_iso, "$ne": None},
    })
    docs_expiry_alert = docs_expiring + docs_expired

    # High-risk activities today — any HIRA/JSA line with target_date today
    hr_today = await db.safety_hira.count_documents({
        "high_risk": True,
        "status": "approved",
        "lines.target_date": today_iso,
    })

    # Safety approval inbox for the current user's role
    role = user.get("role")
    pending_approvals_for_me = 0
    if role in ("safety_officer", "project_manager", "super_admin"):
        pending_approvals_for_me = await db.approvals.count_documents({
            "type": {"$in": ["safety_hira", "safety_jsa"]},
            "status": "pending",
        })

    cards = [
        {"key": "active_projects",     "label": "Active Projects",             "value": active_projects,       "deeplink": "/app/projects"},
        {"key": "projects_with_plan",  "label": "Projects · Plan Approved",    "value": projects_with_plan,    "deeplink": "/app/safety/plans"},
        {"key": "projects_missing_plan","label":"Projects · Plan Missing",     "value": projects_missing_plan, "deeplink": "/app/safety/plans"},
        {"key": "hira_pending",        "label": "HIRA · Pending Approval",     "value": hira_pending,          "deeplink": "/app/safety/hira?status=pending_approval"},
        {"key": "jsa_pending",         "label": "JSA · Pending Approval",      "value": jsa_pending,           "deeplink": "/app/safety/jsa?status=pending_approval"},
        {"key": "permits_pending",     "label": "Permits · Pending",           "value": permits_pending,       "deeplink": "/app/ptws"},
        {"key": "permits_active",      "label": "Permits · Active",            "value": permits_active,        "deeplink": "/app/ptws"},
        {"key": "permits_expired",     "label": "Permits · Expired",           "value": permits_expired,       "deeplink": "/app/ptws"},
        {"key": "inspections_due",     "label": "Inspections Due",             "value": inspections_due,       "deeplink": "/app/safety"},
        {"key": "open_observations",   "label": "Open Observations",           "value": open_observations,     "deeplink": "/app/safety"},
        {"key": "open_corrective",     "label": "Open Corrective Actions",     "value": open_corrective,       "deeplink": "/app/safety"},
        {"key": "incidents_reported",  "label": "Incidents Reported",          "value": incidents,             "deeplink": "/app/safety"},
        {"key": "near_misses",         "label": "Near Misses Reported",        "value": near_misses,           "deeplink": "/app/safety"},
        {"key": "ppe_pending",         "label": "PPE Compliance · Pending",    "value": ppe_pending,           "deeplink": "/app/ppe"},
        {"key": "trainings_pending",   "label": "Safety Training · Pending",   "value": trainings_pending,     "deeplink": "/app/safety-trainings"},
        {"key": "medical_pending",     "label": "Medical Fitness · Pending",   "value": med_pending,           "deeplink": "/app/hr/letters"},
        {"key": "client_audits",       "label": "Client Audits · Pending",     "value": client_audits_pending, "deeplink": "/app/safety"},
        {"key": "docs_expiring",       "label": "Documents Expiring / Expired","value": docs_expiry_alert,     "deeplink": "/app/safety/documents"},
        {"key": "high_risk_today",     "label": "High-risk Activities Today",  "value": hr_today,              "deeplink": "/app/safety/hira"},
        {"key": "pending_approvals",   "label": "Safety Approvals · For You",  "value": pending_approvals_for_me,"deeplink": "/app/approvals"},
    ]
    return {"as_of": now_iso(), "cards": cards}
