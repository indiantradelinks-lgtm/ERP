"""
Iter 131 — Safety Module · Phase 5 · Reports · Closure · Audit Trail · Final Dashboard
=======================================================================================

Consolidates the safety module into a shipping-grade closure/reporting layer:

  * `POST /api/safety/closure/{project_id}/check` — live 15-point checklist
  * `POST /api/safety/closure/{project_id}/submit` — commit closure record
  * `POST /api/safety/closure/{project_id}/override` — Safety Head / Owner override with reason
  * `GET  /api/safety/closure` — list all closure records
  * `GET  /api/safety/closure/{project_id}` — latest closure snapshot

  * `GET  /api/safety/reports/keys` — catalog of ~32 report keys
  * `GET  /api/safety/reports/{report_key}` — data for a report (with filters)
                                            format=json (default) | xlsx | pdf

  * `GET  /api/safety/dashboard-v2` — final 30-tile dashboard aggregating all phases

Extends the existing `safety_audit_log` collection with a Phase-5 closure trail.
Uses existing rbac keys; NEW rbac key `safety_closure` (added to rbac.py).
"""
from __future__ import annotations

import io
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission

router = APIRouter(prefix="/safety", tags=["safety-phase5"])

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _audit(kind: str, rid: str, action: str, user: dict, meta: Optional[Dict] = None):
    """Central audit trail writer (matches Phase 1-4 pattern)."""
    await db.safety_audit_log.insert_one({
        "id": new_id(),
        "record_kind": kind,
        "record_id": rid,
        "record_no": (meta or {}).get("record_no") or "",
        "action": action,
        "at": now_iso(),
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "by_role": user.get("role"),
        "meta": meta or {},
    })


def _is_safety_head_or_owner(user: dict) -> bool:
    role = user.get("role") or ""
    return role in {"super_admin", "director", "general_manager", "dept_head", "safety_officer"}


# ═══════════════════════════════════════════════════════════════════════════
# Project Safety Closure — 15-point checklist
# ═══════════════════════════════════════════════════════════════════════════

CLOSURE_ITEMS = [
    ("work_permits_closed",         "All work permits closed"),
    ("incidents_closed",            "All incidents closed"),
    ("near_misses_closed",          "All near misses closed"),
    ("observations_closed",         "All safety observations closed"),
    ("capa_closed",                 "All CAPA closed"),
    ("audit_findings_closed",       "All audit findings closed"),
    ("ppe_compliance_ok",           "PPE compliance closed"),
    ("training_up_to_date",         "Safety training records updated"),
    ("medical_fitness_ok",          "Medical fitness issues closed"),
    ("vendor_safety_cleared",       "Vendor safety compliance cleared"),
    ("client_docs_submitted",       "Client safety documents submitted"),
    ("safety_cost_recorded",        "Safety cost recorded"),
    ("final_report_uploaded",       "Final safety report uploaded"),
    ("safety_head_approved",        "Safety Head approval"),
    ("project_manager_approved",    "Project Manager approval"),
]


async def _compute_closure_checklist(project_id: str) -> Dict[str, Any]:
    """Compute live 15-point closure checklist for a project."""
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")

    # 1. Work permits — any not-closed permit blocks
    open_permits = await db.safety_work_permits.count_documents({
        "project_id": project_id,
        "status": {"$nin": ["closed", "expired", "cancelled", "rejected"]},
    })

    # 2. Incidents — status != closed
    open_incidents = await db.safety_incidents.count_documents({
        "project_id": project_id,
        "status": {"$nin": ["closed"]},
        "incident_kind": {"$ne": "near_miss"},
    })

    # 3. Near misses (incident_kind='near_miss' — treat separately)
    open_near = await db.safety_incidents.count_documents({
        "project_id": project_id,
        "status": {"$nin": ["closed"]},
        "incident_kind": "near_miss",
    })

    # 4. Observations
    open_obs = await db.safety_observations_v2.count_documents({
        "project_id": project_id,
        "status": {"$nin": ["closed"]},
    })

    # 5. CAPA
    open_capa = await db.safety_capa.count_documents({
        "project_id": project_id,
        "status": {"$nin": ["closed"]},
    })

    # 6. Audit findings — a finding is 'closed' if audit is closed or finding.status == 'closed'
    open_findings = 0
    async for a in db.safety_audits.find(
        {"project_id": project_id, "status": {"$ne": "closed"}},
        {"_id": 0, "findings": 1},
    ):
        for f in a.get("findings") or []:
            if (f.get("status") or "open") != "closed":
                open_findings += 1

    # 7. PPE compliance — look for compliance issues (expired PPE for assigned workers)
    ppe_gaps = await db.safety_ppe_compliance.count_documents({
        "project_id": project_id,
        "compliance_state": {"$in": ["non_compliant", "partial"]},
    })

    # 8. Training — count trainings still 'expiring' or 'expired' for assigned scope
    training_gaps = await db.safety_trainings.count_documents({
        "project_id": project_id,
        "status": {"$in": ["expired"]},
    })

    # 9. Medical fitness — expired/pending on assigned workers
    medical_gaps = await db.safety_medical_fitness.count_documents({
        "project_id": project_id,
        "fitness_status": {"$in": ["unfit", "expired"]},
    })

    # 10. Vendor safety compliance
    vendor_gaps = await db.safety_vendor_compliance.count_documents({
        "project_id": project_id,
        "safety_approval_state": {"$ne": "approved"},
    })

    # 11. Client compliance — mandatory + not submitted
    client_gaps = await db.safety_client_compliance.count_documents({
        "project_id": project_id,
        "mandatory": True,
        "submitted_date": {"$in": [None, ""]},
    })

    # 12. Safety cost recorded — at least 1 entry
    cost_rows = await db.safety_costs.count_documents({"project_id": project_id})

    # Load latest closure record for approval / report state
    latest = await db.safety_project_closures.find_one(
        {"project_id": project_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    latest = latest or {}

    checks = {
        "work_permits_closed":       open_permits == 0,
        "incidents_closed":          open_incidents == 0,
        "near_misses_closed":        open_near == 0,
        "observations_closed":       open_obs == 0,
        "capa_closed":               open_capa == 0,
        "audit_findings_closed":     open_findings == 0,
        "ppe_compliance_ok":         ppe_gaps == 0,
        "training_up_to_date":       training_gaps == 0,
        "medical_fitness_ok":        medical_gaps == 0,
        "vendor_safety_cleared":     vendor_gaps == 0,
        "client_docs_submitted":     client_gaps == 0,
        "safety_cost_recorded":      cost_rows > 0,
        "final_report_uploaded":     bool(latest.get("final_report_url")),
        "safety_head_approved":      bool(latest.get("safety_head_approved_at")),
        "project_manager_approved":  bool(latest.get("project_manager_approved_at")),
    }
    counts = {
        "open_permits": open_permits,
        "open_incidents": open_incidents,
        "open_near_misses": open_near,
        "open_observations": open_obs,
        "open_capa": open_capa,
        "open_audit_findings": open_findings,
        "ppe_gaps": ppe_gaps,
        "training_gaps": training_gaps,
        "medical_gaps": medical_gaps,
        "vendor_gaps": vendor_gaps,
        "client_gaps": client_gaps,
        "cost_rows": cost_rows,
    }
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    can_close = all(checks.values()) or bool(latest.get("override_id"))
    return {
        "project_id": project_id,
        "project_code": p.get("code"),
        "project_name": p.get("name"),
        "project_status": p.get("status"),
        "checklist": [
            {"key": k, "label": label, "passed": checks[k]}
            for k, label in CLOSURE_ITEMS
        ],
        "counts": counts,
        "passed": passed,
        "total": total,
        "can_close": can_close,
        "override": {
            "id": latest.get("override_id"),
            "reason": latest.get("override_reason"),
            "by": latest.get("override_by_name"),
            "at": latest.get("override_at"),
        } if latest.get("override_id") else None,
        "closure_status": latest.get("status") or "not_started",
        "closure_id": latest.get("id"),
        "as_of": now_iso(),
    }


class ClosureSubmitIn(BaseModel):
    final_report_url: Optional[str] = None
    remarks: Optional[str] = None
    approve_as: Optional[str] = None  # "safety_head" | "project_manager" | None


class ClosureOverrideIn(BaseModel):
    reason: str = Field(..., min_length=10)


@router.post("/closure/{project_id}/check")
async def closure_check(
    project_id: str,
    user: dict = Depends(require_permission("safety_reports", "read")),
):
    return await _compute_closure_checklist(project_id)


@router.get("/closure/{project_id}")
async def closure_get(
    project_id: str,
    user: dict = Depends(require_permission("safety_reports", "read")),
):
    return await _compute_closure_checklist(project_id)


@router.get("/closure")
async def closure_list(
    user: dict = Depends(require_permission("safety_reports", "read")),
):
    rows = await db.safety_project_closures.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.post("/closure/{project_id}/submit")
async def closure_submit(
    project_id: str,
    payload: ClosureSubmitIn,
    user: dict = Depends(require_permission("safety_closure", "write")),
):
    snap = await _compute_closure_checklist(project_id)
    latest = await db.safety_project_closures.find_one(
        {"project_id": project_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    rec = dict(latest or {})
    if not rec.get("id"):
        rec.update({
            "id": new_id(),
            "project_id": project_id,
            "project_code": snap.get("project_code"),
            "project_name": snap.get("project_name"),
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
            "status": "pending",
        })
    # Attach payload fields
    if payload.final_report_url is not None:
        rec["final_report_url"] = payload.final_report_url
    if payload.remarks is not None:
        rec["remarks"] = payload.remarks

    # Approval stamp
    if payload.approve_as == "safety_head":
        if not _is_safety_head_or_owner(user):
            raise HTTPException(403, "Only Safety Head / Owner can stamp Safety Head approval")
        rec["safety_head_approved_at"] = now_iso()
        rec["safety_head_approved_by"] = user.get("name") or user.get("email")
    elif payload.approve_as == "project_manager":
        if user.get("role") not in {"super_admin", "director", "general_manager", "project_manager", "dept_head"}:
            raise HTTPException(403, "Only Project Manager / Owner can stamp PM approval")
        rec["project_manager_approved_at"] = now_iso()
        rec["project_manager_approved_by"] = user.get("name") or user.get("email")

    rec["updated_at"] = now_iso()
    rec["updated_by"] = user.get("name") or user.get("email")

    # Recompute status
    latest_snap = await _compute_closure_checklist(project_id)
    if latest_snap["can_close"] and rec.get("safety_head_approved_at") and rec.get("project_manager_approved_at"):
        rec["status"] = "closed"
        rec["closed_at"] = rec.get("closed_at") or now_iso()

    await db.safety_project_closures.update_one(
        {"id": rec["id"]}, {"$set": rec}, upsert=True
    )
    await _audit("project_closure", rec["id"], f"submit:{payload.approve_as or 'save'}", user,
                 {"project_id": project_id, "status": rec.get("status")})
    return await _compute_closure_checklist(project_id)


@router.post("/closure/{project_id}/override")
async def closure_override(
    project_id: str,
    payload: ClosureOverrideIn,
    user: dict = Depends(require_permission("safety_closure", "write")),
):
    if not _is_safety_head_or_owner(user):
        raise HTTPException(403, "Only Safety Head / Owner / Super Admin can override safety closure")
    latest = await db.safety_project_closures.find_one(
        {"project_id": project_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    p = await db.projects.find_one({"id": project_id}, {"_id": 0, "code": 1, "name": 1})
    if not p:
        raise HTTPException(404, "Project not found")
    rec = dict(latest or {})
    if not rec.get("id"):
        rec.update({
            "id": new_id(),
            "project_id": project_id,
            "project_code": p.get("code"),
            "project_name": p.get("name"),
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
            "status": "pending",
        })
    rec["override_id"] = new_id()
    rec["override_reason"] = payload.reason
    rec["override_by_id"] = user.get("id")
    rec["override_by_name"] = user.get("name") or user.get("email")
    rec["override_at"] = now_iso()
    rec["updated_at"] = now_iso()
    await db.safety_project_closures.update_one({"id": rec["id"]}, {"$set": rec}, upsert=True)
    await _audit("project_closure", rec["id"], "override", user,
                 {"project_id": project_id, "reason": payload.reason})
    return await _compute_closure_checklist(project_id)


# ═══════════════════════════════════════════════════════════════════════════
# Safety Reports Center
# ═══════════════════════════════════════════════════════════════════════════

# Each report_key maps to: (label, collection, columns, extra_filter_builder)
# Filters supported globally: from, to, project_id, site, client, risk, status, responsible

REPORT_CATALOG: Dict[str, Dict[str, Any]] = {
    "hira": {
        "label": "HIRA / Risk Assessment Report", "coll": "safety_hira",
        "columns": ["hira_no", "activity", "project_code", "site_location", "risk_level", "status", "created_at"],
        "date_field": "created_at",
    },
    "jsa": {
        "label": "JSA / Job Safety Analysis Report", "coll": "safety_jsa",
        "columns": ["jsa_no", "job_title", "project_code", "site_location", "status", "created_at"],
        "date_field": "created_at",
    },
    "work_permits": {
        "label": "Work Permits Report", "coll": "safety_work_permits",
        "columns": ["permit_no", "permit_type", "project_code", "site_location", "status", "valid_from", "valid_to"],
        "date_field": "valid_from",
    },
    "active_permits": {
        "label": "Active Permits", "coll": "safety_work_permits",
        "columns": ["permit_no", "permit_type", "project_code", "site_location", "valid_from", "valid_to"],
        "date_field": "valid_from",
        "extra": {"status": "approved"},
    },
    "expired_permits": {
        "label": "Expired Permits", "coll": "safety_work_permits",
        "columns": ["permit_no", "permit_type", "project_code", "valid_to"],
        "date_field": "valid_to",
        "extra": {"status": "expired"},
    },
    "permit_closure": {
        "label": "Permit Closure Report", "coll": "safety_work_permits",
        "columns": ["permit_no", "permit_type", "project_code", "closed_at", "closed_by"],
        "date_field": "closed_at",
        "extra": {"status": "closed"},
    },
    "safety_induction": {
        "label": "Safety Induction Report", "coll": "safety_trainings",
        "columns": ["training_no", "employee_name", "training_type", "date_conducted", "expiry_date"],
        "date_field": "date_conducted",
        "extra": {"training_type": "induction"},
    },
    "training": {
        "label": "Training Report", "coll": "safety_trainings",
        "columns": ["training_no", "employee_name", "training_type", "date_conducted", "expiry_date", "status"],
        "date_field": "date_conducted",
    },
    "training_expiry": {
        "label": "Training Expiry Report", "coll": "safety_trainings",
        "columns": ["training_no", "employee_name", "training_type", "expiry_date", "status"],
        "date_field": "expiry_date",
        "extra": {"status": {"$in": ["expiring", "expired"]}},
    },
    "medical_fitness_expiry": {
        "label": "Medical Fitness Expiry Report", "coll": "safety_medical_fitness",
        "columns": ["employee_name", "fitness_status", "valid_from", "valid_till"],
        "date_field": "valid_till",
        "extra": {"fitness_status": {"$in": ["expired", "unfit"]}},
    },
    "ppe_compliance": {
        "label": "PPE Compliance Report", "coll": "safety_ppe_compliance",
        "columns": ["employee_name", "ppe_item", "project_code", "compliance_state", "issued_date"],
        "date_field": "issued_date",
    },
    "ppe_shortage": {
        "label": "PPE Shortage Report", "coll": "safety_ppe_compliance",
        "columns": ["employee_name", "ppe_item", "project_code", "compliance_state"],
        "date_field": "issued_date",
        "extra": {"compliance_state": {"$in": ["non_compliant", "partial"]}},
    },
    "safety_inspection": {
        "label": "Safety Inspection Report", "coll": "safety_inspections",
        "columns": ["inspection_no", "inspection_date", "inspection_type", "project_code", "site_location", "status"],
        "date_field": "inspection_date",
    },
    "safety_observation": {
        "label": "Safety Observation Report", "coll": "safety_observations_v2",
        "columns": ["observation_no", "observation_date", "category", "project_code", "risk_level", "status"],
        "date_field": "observation_date",
    },
    "ofi": {
        "label": "OFI Report", "coll": "safety_observations_v2",
        "columns": ["observation_no", "observation_date", "category", "project_code", "risk_level", "status"],
        "date_field": "observation_date",
        "extra": {"category": "ofi"},
    },
    "near_miss": {
        "label": "Near Miss Report", "coll": "safety_incidents",
        "columns": ["incident_no", "incident_date", "project_code", "site_location", "severity", "status"],
        "date_field": "incident_date",
        "extra": {"incident_kind": "near_miss"},
    },
    "incident": {
        "label": "Incident Report", "coll": "safety_incidents",
        "columns": ["incident_no", "incident_date", "project_code", "site_location", "severity", "status"],
        "date_field": "incident_date",
        "extra": {"incident_kind": {"$ne": "near_miss"}},
    },
    "incident_investigation": {
        "label": "Incident Investigation Report", "coll": "safety_incidents",
        "columns": ["incident_no", "incident_date", "investigation_status", "root_cause", "status"],
        "date_field": "incident_date",
        "extra": {"investigation_status": {"$exists": True}},
    },
    "capa": {
        "label": "CAPA Report", "coll": "safety_capa",
        "columns": ["capa_no", "source_type", "project_code", "responsible", "target_date", "status"],
        "date_field": "created_at",
    },
    "capa_overdue": {
        "label": "Overdue CAPA Report", "coll": "safety_capa",
        "columns": ["capa_no", "source_type", "project_code", "responsible", "target_date", "status"],
        "date_field": "target_date",
        "extra": {"is_overdue": True, "status": {"$ne": "closed"}},
    },
    "safety_audit": {
        "label": "Safety Audit Report", "coll": "safety_audits",
        "columns": ["audit_no", "audit_date", "audit_type", "project_code", "auditor", "audit_score", "status"],
        "date_field": "audit_date",
    },
    "client_compliance": {
        "label": "Client Compliance Report", "coll": "safety_client_compliance",
        "columns": ["client_name", "project_code", "requirement", "requirement_type", "due_date", "submitted_date", "status"],
        "date_field": "due_date",
    },
    "vendor_safety_compliance": {
        "label": "Vendor Safety Compliance Report", "coll": "safety_vendor_compliance",
        "columns": ["vendor_name", "project_code", "safety_doc_valid_till", "insurance_valid_till", "safety_approval_state"],
        "date_field": "safety_doc_valid_till",
    },
    "monthly_review": {
        "label": "Monthly Safety Review Report", "coll": "safety_reviews",
        "columns": ["review_no", "month", "meeting_date", "project_code", "key_observations"],
        "date_field": "meeting_date",
    },
    "safety_cost": {
        "label": "Safety Cost Report", "coll": "safety_costs",
        "columns": ["cost_date", "cost_source", "project_code", "description", "amount", "is_recovery"],
        "date_field": "cost_date",
    },
    "safety_penalty": {
        "label": "Safety Penalty Report", "coll": "safety_costs",
        "columns": ["cost_date", "project_code", "description", "amount"],
        "date_field": "cost_date",
        "extra": {"cost_source": "penalty"},
    },
    "safety_recovery": {
        "label": "Safety Recovery Report", "coll": "safety_costs",
        "columns": ["cost_date", "project_code", "description", "amount"],
        "date_field": "cost_date",
        "extra": {"is_recovery": True},
    },
    "project_closure": {
        "label": "Project Safety Closure Report", "coll": "safety_project_closures",
        "columns": ["project_code", "project_name", "status", "safety_head_approved_at", "project_manager_approved_at", "closed_at"],
        "date_field": "created_at",
    },
    "audit_trail": {
        "label": "Safety Audit Trail Report", "coll": "safety_audit_log",
        "columns": ["at", "record_kind", "record_no", "action", "by_name", "by_role"],
        "date_field": "at",
    },
    "project_status": {
        "label": "Project-wise Safety Status", "coll": "_synthetic_project_status", "columns": [],
        "date_field": "",
    },
    "site_status": {
        "label": "Site-wise Safety Status", "coll": "_synthetic_site_status", "columns": [],
        "date_field": "",
    },
    "safety_dashboard": {
        "label": "Safety Dashboard Snapshot", "coll": "_synthetic_dashboard", "columns": [],
        "date_field": "",
    },
}


@router.get("/reports/keys")
async def report_keys(user: dict = Depends(require_permission("safety_reports", "read"))):
    return [{"key": k, "label": v["label"]} for k, v in REPORT_CATALOG.items()]


def _build_report_query(spec: Dict[str, Any], filters: Dict[str, Any]) -> Dict[str, Any]:
    q: Dict[str, Any] = dict(spec.get("extra") or {})
    df = spec.get("date_field")
    if df and (filters.get("from") or filters.get("to")):
        q[df] = {}
        if filters.get("from"):
            q[df]["$gte"] = filters["from"]
        if filters.get("to"):
            q[df]["$lte"] = filters["to"] + "T23:59:59"
    if filters.get("project_id"):
        q["project_id"] = filters["project_id"]
    if filters.get("site"):
        q["site_location"] = {"$regex": filters["site"], "$options": "i"}
    if filters.get("client"):
        q["client_name"] = {"$regex": filters["client"], "$options": "i"}
    if filters.get("risk"):
        q["risk_level"] = filters["risk"]
    if filters.get("status"):
        # Only apply if the collection typically has a status column
        q.setdefault("status", filters["status"])
    if filters.get("responsible"):
        q["responsible"] = {"$regex": filters["responsible"], "$options": "i"}
    return q


async def _synthesize_project_status() -> List[Dict[str, Any]]:
    """Rows: 1 per project with counts across safety collections."""
    projects = await db.projects.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1, "status": 1}).to_list(2000)
    out = []
    for p in projects:
        pid = p["id"]
        row = {
            "project_code": p.get("code"),
            "project_name": p.get("name"),
            "project_status": p.get("status"),
            "open_permits": await db.safety_work_permits.count_documents({"project_id": pid, "status": {"$nin": ["closed", "expired", "cancelled"]}}),
            "open_incidents": await db.safety_incidents.count_documents({"project_id": pid, "status": {"$ne": "closed"}}),
            "open_capa": await db.safety_capa.count_documents({"project_id": pid, "status": {"$ne": "closed"}}),
            "open_audits": await db.safety_audits.count_documents({"project_id": pid, "status": {"$ne": "closed"}}),
            "client_gaps": await db.safety_client_compliance.count_documents({"project_id": pid, "mandatory": True, "submitted_date": {"$in": [None, ""]}}),
        }
        out.append(row)
    return out


async def _synthesize_site_status() -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": {"site_location": {"$exists": True, "$ne": ""}}},
        {"$group": {"_id": "$site_location", "open_permits": {"$sum": 1}}},
    ]
    sites_data: Dict[str, Dict[str, Any]] = {}
    async for doc in db.safety_work_permits.aggregate(pipeline):
        site = doc["_id"]
        sites_data.setdefault(site, {"site_location": site})
        sites_data[site]["open_permits"] = doc["open_permits"]
    return list(sites_data.values())


@router.get("/reports/{report_key}")
async def get_report(
    report_key: str,
    format: str = Query("json", pattern="^(json|xlsx|pdf)$"),
    _from: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    project_id: Optional[str] = None,
    site: Optional[str] = None,
    client: Optional[str] = None,
    risk: Optional[str] = None,
    status: Optional[str] = None,
    responsible: Optional[str] = None,
    limit: int = 5000,
    user: dict = Depends(require_permission("safety_reports", "read")),
):
    spec = REPORT_CATALOG.get(report_key)
    if not spec:
        raise HTTPException(404, "Unknown report_key")

    filters = {"from": _from, "to": to, "project_id": project_id, "site": site,
               "client": client, "risk": risk, "status": status, "responsible": responsible}

    # Synthetic reports
    if report_key == "project_status":
        rows = await _synthesize_project_status()
        columns = ["project_code", "project_name", "project_status", "open_permits", "open_incidents", "open_capa", "open_audits", "client_gaps"]
    elif report_key == "site_status":
        rows = await _synthesize_site_status()
        columns = ["site_location", "open_permits"]
    elif report_key == "safety_dashboard":
        # Return dashboard-v2 as tabular snapshot
        dash = await _final_dashboard()
        rows = [{"metric": k, "value": v} for k, v in dash["kpis"].items()]
        columns = ["metric", "value"]
    else:
        q = _build_report_query(spec, filters)
        df = spec.get("date_field") or "created_at"
        try:
            rows = await db[spec["coll"]].find(q, {"_id": 0}).sort(df, -1).to_list(limit)
        except Exception:
            rows = await db[spec["coll"]].find(q, {"_id": 0}).to_list(limit)
        columns = spec["columns"]

    payload = {
        "report_key": report_key,
        "label": spec["label"],
        "filters": filters,
        "columns": columns,
        "rows": rows,
        "count": len(rows),
        "generated_at": now_iso(),
    }
    if format == "json":
        return payload
    if format == "xlsx":
        return _stream_xlsx(payload)
    return _stream_pdf(payload)


def _stream_xlsx(payload: Dict[str, Any]) -> StreamingResponse:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = payload["report_key"][:30]
    ws.append([payload["label"]])
    ws.append([f"Generated at: {payload['generated_at']}"])
    ws.append([])
    ws.append(payload["columns"])
    for r in payload["rows"]:
        ws.append([r.get(c, "") for c in payload["columns"]])
    # bold header
    for cell in ws[4]:
        cell.font = openpyxl.styles.Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"{payload['report_key']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _stream_pdf(payload: Dict[str, Any]) -> StreamingResponse:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=payload["label"])
    from pdf_watermark import attach_watermark
    attach_watermark(doc, width_mm=180.0)
    styles = getSampleStyleSheet()
    elems = [
        Paragraph(f"<b>{payload['label']}</b>", styles["Title"]),
        Paragraph(f"Generated: {payload['generated_at']} · Rows: {payload['count']}", styles["Normal"]),
        Spacer(1, 12),
    ]
    header = [c.replace("_", " ").title() for c in payload["columns"]]
    body = [[str(r.get(c, ""))[:80] for c in payload["columns"]] for r in payload["rows"][:2000]]
    data = [header] + body
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DC2626")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elems.append(tbl)
    doc.build(elems)
    buf.seek(0)
    fname = f"{payload['report_key']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Final Safety Dashboard (30 tiles)
# ═══════════════════════════════════════════════════════════════════════════

async def _final_dashboard() -> Dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    ninety_days_ago = (now_utc - timedelta(days=90)).isoformat()

    # Project counts
    total_projects = await db.projects.count_documents({})
    projects_active = await db.projects.count_documents({"status": {"$in": ["active", "approved"]}})

    # Safety-ready / safety-blocked from safety_readiness
    ready = await db.safety_readiness.count_documents({"readiness_state": "ready"})
    blocked = await db.safety_readiness.count_documents({"readiness_state": "blocked"})

    hira_pending = await db.safety_hira.count_documents({"status": {"$in": ["draft", "pending_approval"]}})
    jsa_pending = await db.safety_jsa.count_documents({"status": {"$in": ["draft", "pending_approval"]}})
    permits_active = await db.safety_work_permits.count_documents({"status": "approved"})
    permits_expired = await db.safety_work_permits.count_documents({"status": "expired"})
    permits_pending = await db.safety_work_permits.count_documents({"status": {"$in": ["pending_approval", "requested"]}})
    training_pending = await db.safety_trainings.count_documents({"status": {"$in": ["scheduled", "pending"]}})
    training_expiring = await db.safety_trainings.count_documents({"status": "expiring"})
    medical_expiring = await db.safety_medical_fitness.count_documents({"fitness_status": {"$in": ["expiring", "expired", "unfit"]}})
    ppe_pending = await db.safety_ppe_compliance.count_documents({"compliance_state": {"$in": ["non_compliant", "partial"]}})
    inspections_due = await db.safety_inspections.count_documents({"status": {"$in": ["scheduled", "due"]}})
    open_obs = await db.safety_observations_v2.count_documents({"status": {"$ne": "closed"}})
    open_ofi = await db.safety_observations_v2.count_documents({"category": "ofi", "status": {"$ne": "closed"}})
    open_incidents = await db.safety_incidents.count_documents({"status": {"$ne": "closed"}, "incident_kind": {"$ne": "near_miss"}})
    open_near_miss = await db.safety_incidents.count_documents({"status": {"$ne": "closed"}, "incident_kind": "near_miss"})
    open_capa = await db.safety_capa.count_documents({"status": {"$ne": "closed"}})
    overdue_capa = await db.safety_capa.count_documents({"status": {"$ne": "closed"}, "is_overdue": True})
    open_audit_findings = 0
    async for a in db.safety_audits.find({"status": {"$ne": "closed"}}, {"findings": 1, "_id": 0}):
        for f in a.get("findings") or []:
            if (f.get("status") or "open") != "closed":
                open_audit_findings += 1
    client_pending = await db.safety_client_compliance.count_documents({"mandatory": True, "submitted_date": {"$in": [None, ""]}})
    vendor_pending = await db.safety_vendor_compliance.count_documents({"safety_approval_state": {"$ne": "approved"}})
    projects_pending_closure = await db.projects.count_documents({"status": {"$in": ["active", "completed"]}}) \
        - await db.safety_project_closures.count_documents({"status": "closed"})
    if projects_pending_closure < 0:
        projects_pending_closure = 0

    cost_pipeline = [
        {"$match": {"cost_date": {"$gte": month_start[:10]}, "is_recovery": {"$ne": True}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    cost_this_month = 0
    async for doc in db.safety_costs.aggregate(cost_pipeline):
        cost_this_month = doc.get("total") or 0

    penalty_pending = await db.safety_costs.count_documents({"cost_source": "penalty", "approval_id": {"$exists": True, "$ne": None}})
    recovery_pending = await db.safety_costs.count_documents({"cost_source": "recovery", "is_recovery": True, "approval_id": {"$exists": True, "$ne": None}})
    high_risk_activities = await db.safety_hira.count_documents({"risk_level": {"$in": ["high", "critical"]}, "status": {"$ne": "closed"}})
    safety_approval_pending = await db.approvals.count_documents({"module": "safety", "status": "pending"}) \
        if await db.approvals.count_documents({"module": "safety"}) > 0 else 0

    recent_incidents = await db.safety_incidents.find(
        {"incident_date": {"$gte": ninety_days_ago[:10]}}, {"_id": 0, "incident_no": 1, "incident_date": 1, "severity": 1, "project_code": 1}
    ).sort("incident_date", -1).limit(5).to_list(5)
    recent_closures = await db.safety_project_closures.find(
        {"status": "closed"}, {"_id": 0, "project_code": 1, "closed_at": 1}
    ).sort("closed_at", -1).limit(5).to_list(5)

    kpis = {
        "total_projects_monitored":   total_projects,
        "projects_safety_ready":      ready,
        "projects_safety_blocked":    blocked,
        "hira_pending":               hira_pending,
        "jsa_pending":                jsa_pending,
        "work_permits_active":        permits_active,
        "work_permits_expired":       permits_expired,
        "work_permits_pending_closure": permits_pending,
        "training_pending":           training_pending,
        "training_expiring":          training_expiring,
        "medical_fitness_expiring":   medical_expiring,
        "ppe_compliance_pending":     ppe_pending,
        "safety_inspections_due":     inspections_due,
        "open_safety_observations":   open_obs,
        "open_ofis":                  open_ofi,
        "open_incidents":             open_incidents,
        "open_near_misses":           open_near_miss,
        "open_capa":                  open_capa,
        "overdue_capa":               overdue_capa,
        "open_audit_findings":        open_audit_findings,
        "client_compliance_pending":  client_pending,
        "vendor_safety_pending":      vendor_pending,
        "projects_pending_closure":   projects_pending_closure,
        "safety_cost_this_month":     cost_this_month,
        "safety_penalty_pending":     penalty_pending,
        "safety_recovery_pending":    recovery_pending,
        "high_risk_activities":       high_risk_activities,
        "safety_approval_pending":    safety_approval_pending,
        "projects_active":            projects_active,
    }
    return {
        "as_of": now_iso(),
        "kpis": kpis,
        "recent_incidents": recent_incidents,
        "recent_closures": recent_closures,
    }


@router.get("/dashboard-v2")
async def dashboard_v2(user: dict = Depends(require_permission("safety_reports", "read"))):
    return await _final_dashboard()


# ═══════════════════════════════════════════════════════════════════════════
# Audit Trail — richer read endpoint (Phase 5)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/audit-trail")
async def safety_audit_trail(
    record_kind: Optional[str] = None,
    record_id: Optional[str] = None,
    action: Optional[str] = None,
    by_id: Optional[str] = None,
    _from: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    limit: int = 500,
    user: dict = Depends(require_permission("safety_reports", "read")),
):
    if limit < 1 or limit > 5000:
        raise HTTPException(400, "limit must be 1..5000")
    q: Dict[str, Any] = {}
    if record_kind:
        q["record_kind"] = record_kind
    if record_id:
        q["record_id"] = record_id
    if action:
        q["action"] = {"$regex": action, "$options": "i"}
    if by_id:
        q["by_id"] = by_id
    if _from or to:
        q["at"] = {}
        if _from:
            q["at"]["$gte"] = _from
        if to:
            q["at"]["$lte"] = to + "T23:59:59"
    rows = await db.safety_audit_log.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return {"count": len(rows), "rows": rows}


@router.get("/audit-trail/kinds")
async def safety_audit_kinds(user: dict = Depends(require_permission("safety_reports", "read"))):
    """Distinct record kinds present in the audit trail."""
    kinds = await db.safety_audit_log.distinct("record_kind")
    return sorted([k for k in kinds if k])
