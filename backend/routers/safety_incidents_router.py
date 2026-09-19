"""Safety · Incident Reporting & Investigation · Iter 129 (Phase 3)
====================================================================

Handles both Near-Miss and Incident registration in a single collection
(`safety_incidents`) with the `incident_type` field partitioning them.

Highlights
----------
* Critical incident types → auto-create escalation to Owner/Ops Head/Safety
  Head (Q1: LTI, Fatality, Fire, Environmental, Property Damage-High)
* Incident cost (>₹50k configurable via `SafetySetting`) auto-routes to
  Finance Head approval (Q2)
* Medical / injury details on `people_involved[]` are stored under a
  restricted field group that only `safety_incidents_medical` readers see
* Investigation adds root_cause + corrective + preventive actions and
  auto-creates a CAPA on close-investigation

All state transitions write to `safety_audit_log` (Iter 127).
Integrations:
    * Projects & Ops → mirrors a lightweight row into `project_issues`
    * HR             → optional employee_id on `people_involved[]`
    * Store          → optional `damaged_ppe_ids[]` flags issued PPE as damaged
    * Accounts / Fin → cost fields readable by finance dashboards; over-threshold auto-approval
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import Request, APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission, get_current_user
from pagination import maybe_paged, paged_or_rows
from sequences import next_sequence
from approval_engine import insert_approval

router = APIRouter(prefix="/safety/incidents", tags=["safety-incidents"])

# Incident types that auto-escalate to Owner / Ops Head / Safety Head (Q1-a).
CRITICAL_INCIDENT_TYPES = {
    "lost_time_injury", "fatality", "fire", "environmental_incident", "property_damage",
}
# Types considered near-miss (still tracked, no auto-escalation).
NEAR_MISS_TYPES = {"near_miss", "unsafe_condition"}

# Cost threshold above which incident cost auto-creates a Finance Head approval (Q2-a).
DEFAULT_COST_APPROVAL_THRESHOLD = 50_000


async def _get_cost_threshold() -> float:
    """Reads override from `safety_settings` collection (single doc, key `incident_cost_threshold`)."""
    setting = await db.safety_settings.find_one({"key": "incident_cost_threshold"}, {"_id": 0, "value": 1})
    if setting and isinstance(setting.get("value"), (int, float)):
        return float(setting["value"])
    return float(DEFAULT_COST_APPROVAL_THRESHOLD)


class PersonInvolved(BaseModel):
    employee_id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    injury_type: Optional[str] = None       # restricted (medical)
    injury_body_part: Optional[str] = None  # restricted
    treatment_given: Optional[str] = None   # restricted
    medical_notes: Optional[str] = None     # restricted
    days_lost: Optional[int] = 0


class IncidentIn(BaseModel):
    incident_datetime: str = Field(..., description="ISO-8601 datetime")
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    incident_type: str = Field(..., min_length=1)
    description: str = Field(..., min_length=10, max_length=5000)
    location_area: Optional[str] = ""
    people_involved: List[PersonInvolved] = Field(default_factory=list)
    immediate_action_taken: Optional[str] = ""
    root_cause: Optional[str] = ""
    corrective_action: Optional[str] = ""
    preventive_action: Optional[str] = ""
    responsible_person: Optional[str] = ""
    target_closure_date: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)
    damaged_ppe_ids: List[str] = Field(default_factory=list)
    medical_cost: float = 0.0
    penalty_cost: float = 0.0
    recovery_amount: float = 0.0
    reported_by: Optional[str] = ""


# ─── Helpers ────────────────────────────────────────────────────────────
async def _write_audit(iid: str, ino: str, action: str, user: dict,
                        meta: Optional[Dict[str, Any]] = None) -> None:
    await db.safety_audit_log.insert_one({
        "id": new_id(), "record_kind": "safety_incident", "record_id": iid, "record_no": ino,
        "action": action,
        "by_id": user.get("id"), "by_name": user.get("name") or user.get("email"),
        "role": user.get("role"), "at": now_iso(), "meta": meta or {},
    })


async def _mirror_to_project_issues(incident: dict) -> None:
    """Integrate with Projects & Ops: create a lightweight linked issue row.
    Never mutates existing issue records — pure append with source pointer."""
    if not incident.get("project_id"):
        return
    await db.project_issues.insert_one({
        "id": new_id(),
        "project_id": incident["project_id"],
        "issue_type": "safety",
        "severity": "critical" if incident["incident_type"] in CRITICAL_INCIDENT_TYPES else "medium",
        "title": f"Safety incident {incident['incident_no']} — {(incident['incident_type'] or '').replace('_', ' ')}",
        "description": (incident.get("description") or "")[:400],
        "source_module": "safety",
        "source_type": "safety_incident",
        "source_id": incident["id"],
        "source_no": incident["incident_no"],
        "status": "open",
        "created_at": now_iso(),
    })


async def _flag_damaged_ppe(damaged_ppe_ids: List[str], incident_no: str) -> None:
    """Integrate with Store: flag issued PPE rows as damaged."""
    if not damaged_ppe_ids:
        return
    await db.ppe_issuance.update_many(
        {"id": {"$in": damaged_ppe_ids}},
        {"$set": {"condition": "damaged", "damaged_reason": f"Incident {incident_no}",
                  "flagged_at": now_iso()}},
    )


async def _create_critical_escalation(incident: dict) -> str:
    esc_id = new_id()
    await db.safety_escalations.insert_one({
        "id": esc_id,
        "kind": "critical_incident",
        "ref_id": incident["id"],
        "ref_no": incident["incident_no"],
        "project_id": incident.get("project_id"),
        "level": "critical",
        "reason": f"{incident['incident_type']} at {incident.get('site_location') or 'site'}",
        "status": "open",
        "notify_roles": ["director", "general_manager", "dept_head"],
        "created_at": now_iso(),
    })
    return esc_id


async def _create_cost_approval(incident: dict, total_cost: float) -> str:
    """Route high-value incident cost to Finance Head approval."""
    approval_doc = {
        "id": new_id(),
        "type": "safety_incident_cost",
        "module": "safety",
        "record_id": incident["id"],
        "title": f"Incident {incident['incident_no']} — cost approval ₹{total_cost:,.0f}",
        "summary": f"{incident['incident_type']} · Project {incident.get('project_code') or '—'}",
        "requested_by": incident.get("reported_by") or "system",
        "status": "pending",
        "current_step": 0,
        "chain": [{"role": "finance_head", "label": "Finance Head",
                   "status": "pending", "approver": None, "at": None, "comment": None}],
        "history": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await insert_approval(approval_doc, skip_gate=True)
    return approval_doc["id"]


def _strip_medical(row: dict, allowed: bool) -> dict:
    """Redact medical / injury fields on `people_involved[]` when user lacks
    `safety_incidents_medical` read permission."""
    if allowed:
        return row
    people = row.get("people_involved") or []
    redacted = []
    for p in people:
        redacted.append({
            "employee_id": p.get("employee_id"),
            "name": p.get("name"),
            "role": p.get("role"),
            "days_lost": p.get("days_lost"),
            # medical/injury fields hidden
            "medical_details_hidden": True,
        })
    return {**row, "people_involved": redacted}


def _has_medical_perm(user: dict) -> bool:
    from rbac import PERMISSIONS
    allowed_roles = PERMISSIONS.get("safety_incidents_medical", {}).get("read", set())
    return (user.get("role") in allowed_roles) or ("*" in allowed_roles)


# ─── Endpoints ──────────────────────────────────────────────────────────
@router.get("")
async def list_incidents(
    request: Request,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    incident_type: Optional[str] = None,
    user: dict = Depends(require_permission("safety_incidents", "read")),
):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    if incident_type:
        q["incident_type"] = incident_type
    paged = await maybe_paged(request, "safety_incidents", q, "incident_datetime",
                              ["incident_no", "title", "incident_type", "severity", "project_name", "project_code", "location", "status", "reported_by"])
    rows = paged["rows"] if paged else await db.safety_incidents.find(q, {"_id": 0}).sort("incident_datetime", -1).to_list(2000)
    med_ok = _has_medical_perm(user)
    return paged_or_rows(paged, [_strip_medical(r, med_ok) for r in rows])


@router.get("/{iid}")
async def get_incident(iid: str, user: dict = Depends(require_permission("safety_incidents", "read"))):
    doc = await db.safety_incidents.find_one({"id": iid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Incident not found")
    return _strip_medical(doc, _has_medical_perm(user))


@router.post("")
async def create_incident(payload: IncidentIn,
                           user: dict = Depends(require_permission("safety_incidents", "write"))):
    ino = await next_sequence("INC")
    is_near_miss = payload.incident_type in NEAR_MISS_TYPES
    is_critical = payload.incident_type in CRITICAL_INCIDENT_TYPES
    doc = {
        **payload.model_dump(),
        "id": new_id(),
        "incident_no": ino,
        "is_near_miss": is_near_miss,
        "is_critical": is_critical,
        "escalation_id": None,
        "cost_approval_id": None,
        "capa_ids": [],
        "investigation_status": "pending",
        "status": "reported",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_incidents.insert_one(doc)
    await _write_audit(doc["id"], ino, "reported", user, {"critical": is_critical, "near_miss": is_near_miss})

    # Auto-integrations
    await _mirror_to_project_issues(doc)
    await _flag_damaged_ppe(payload.damaged_ppe_ids, ino)

    updates: Dict[str, Any] = {}
    if is_critical:
        esc_id = await _create_critical_escalation(doc)
        updates["escalation_id"] = esc_id
        await _write_audit(doc["id"], ino, "auto_escalated", user, {"escalation_id": esc_id})

    total_cost = float(payload.medical_cost or 0) + float(payload.penalty_cost or 0)
    threshold = await _get_cost_threshold()
    if total_cost >= threshold:
        appr_id = await _create_cost_approval(doc, total_cost)
        updates["cost_approval_id"] = appr_id
        await _write_audit(doc["id"], ino, "cost_approval_requested", user,
                           {"approval_id": appr_id, "total_cost": total_cost, "threshold": threshold})

    if updates:
        await db.safety_incidents.update_one({"id": doc["id"]}, {"$set": updates})
        doc.update(updates)
    doc.pop("_id", None)
    return _strip_medical(doc, _has_medical_perm(user))


@router.put("/{iid}")
async def update_incident(iid: str, payload: IncidentIn,
                           user: dict = Depends(require_permission("safety_incidents", "write"))):
    existing = await db.safety_incidents.find_one({"id": iid})
    if not existing:
        raise HTTPException(404, "Incident not found")
    if existing.get("status") == "closed":
        raise HTTPException(400, "Closed incident cannot be edited without reopening approval")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.safety_incidents.update_one({"id": iid}, {"$set": patch})
    await _write_audit(iid, existing["incident_no"], "updated", user)
    fresh = await db.safety_incidents.find_one({"id": iid}, {"_id": 0})
    return _strip_medical(fresh, _has_medical_perm(user))


@router.post("/{iid}/close-investigation")
async def close_investigation(iid: str,
                               user: dict = Depends(require_permission("safety_incidents", "write"))):
    """Marks investigation complete and auto-creates a CAPA linked to this
    incident (using the corrective_action & preventive_action fields)."""
    doc = await db.safety_incidents.find_one({"id": iid})
    if not doc:
        raise HTTPException(404, "Incident not found")
    if not doc.get("root_cause"):
        raise HTTPException(400, "root_cause is required before closing investigation")

    capa_no = await next_sequence("CAPA")
    capa_doc = {
        "id": new_id(),
        "capa_no": capa_no,
        "source_type": "incident",
        "source_id": iid,
        "source_no": doc["incident_no"],
        "project_id": doc.get("project_id"),
        "project_code": doc.get("project_code"),
        "corrective_action": doc.get("corrective_action") or "See incident investigation",
        "preventive_action": doc.get("preventive_action") or "",
        "responsible_person": doc.get("responsible_person") or "",
        "target_date": doc.get("target_closure_date"),
        "evidence_ids": [],
        "verified_by_safety": False,
        "status": "open",
        "auto_created": True,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_capa.insert_one(capa_doc)
    await db.safety_incidents.update_one({"id": iid}, {"$set": {
        "investigation_status": "closed",
        "investigation_closed_at": now_iso(),
        "investigation_closed_by": user.get("name") or user.get("email"),
    }, "$push": {"capa_ids": capa_doc["id"]}})
    await _write_audit(iid, doc["incident_no"], "investigation_closed", user, {"auto_capa": capa_doc["id"]})
    return {"ok": True, "capa_id": capa_doc["id"], "capa_no": capa_no}


@router.post("/{iid}/close")
async def close_incident(iid: str,
                          user: dict = Depends(require_permission("safety_incidents", "write"))):
    doc = await db.safety_incidents.find_one({"id": iid})
    if not doc:
        raise HTTPException(404, "Incident not found")
    if doc.get("investigation_status") != "closed":
        raise HTTPException(400, "Investigation must be closed before closing the incident")
    await db.safety_incidents.update_one({"id": iid}, {"$set": {
        "status": "closed",
        "closed_at": now_iso(),
        "closed_by": user.get("name") or user.get("email"),
    }})
    await _write_audit(iid, doc["incident_no"], "closed", user)
    return await db.safety_incidents.find_one({"id": iid}, {"_id": 0})
