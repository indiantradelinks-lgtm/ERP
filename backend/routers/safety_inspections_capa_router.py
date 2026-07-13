"""Safety · Inspections + Observations + CAPA + Escalations · Iter 129 (Phase 3)
================================================================================

Four related registers sharing the same closure/audit conventions. Kept in
one file because CAPA references all three source registers (inspection/
observation/incident/audit) and the escalation dashboard queries all four.

Highlights
----------
* Safety Inspection — with `lines[]` (checklist responses), risk-tinted cells
* Safety Observation — extends legacy `safety_observations` with lifecycle
  (open/in_progress/closed/overdue/escalated). **High-risk observations
  auto-create a draft CAPA** (Q2 confirmed).
* CAPA — linked to source, requires evidence on close (or override reason)
* Escalation — dashboard rolling up overdue CAPA + critical incidents (which
  are created by the sibling `safety_incidents_router.py`)
* `POST /-/tick-overdue` — nightly-callable sweep flipping past-due CAPAs
  to `overdue` and creating an escalation row (Q3 confirmed).

Every state transition writes to `safety_audit_log` (from Iter 127).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission
from sequences import next_sequence

router = APIRouter(prefix="/safety", tags=["safety-phase3"])

HIGH_RISK = {"high", "critical"}


async def _audit(kind: str, rid: str, rno: str, action: str, user: dict, meta: Optional[Dict] = None) -> None:
    await db.safety_audit_log.insert_one({
        "id": new_id(),
        "record_kind": kind,
        "record_id": rid,
        "record_no": rno,
        "action": action,
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "role": user.get("role"),
        "at": now_iso(),
        "meta": meta or {},
    })


async def _create_escalation(kind: str, ref_id: str, ref_no: str, project_id: Optional[str],
                              reason: str, level: str = "high") -> str:
    esc_id = new_id()
    await db.safety_escalations.insert_one({
        "id": esc_id,
        "kind": kind,                    # overdue_capa / critical_incident / high_risk_observation
        "ref_id": ref_id,
        "ref_no": ref_no,
        "project_id": project_id,
        "level": level,                  # medium / high / critical
        "reason": reason,
        "status": "open",
        "created_at": now_iso(),
    })
    return esc_id


# ═══════════════════ Safety Inspections ═══════════════════
class InspectionLine(BaseModel):
    checklist_item: str = Field(..., min_length=1, max_length=300)
    compliant: Optional[bool] = None      # True/False/None (n-a)
    observation: Optional[str] = ""
    risk_level: Optional[str] = None       # low/medium/high/critical
    corrective_action_required: bool = False


class InspectionIn(BaseModel):
    inspection_date: str = Field(..., description="YYYY-MM-DD")
    inspection_type: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    inspector: Optional[str] = ""
    checklist_id: Optional[str] = None
    area_inspected: Optional[str] = ""
    compliance_status: Optional[str] = None    # compliant / non_compliant / partial
    risk_level: Optional[str] = None
    photo_ids: List[str] = Field(default_factory=list)
    corrective_action_required: bool = False
    responsible_person: Optional[str] = ""
    target_closure_date: Optional[str] = None
    remarks: Optional[str] = ""
    lines: List[InspectionLine] = Field(default_factory=list)


@router.get("/inspections")
async def list_inspections(status: Optional[str] = None, project_id: Optional[str] = None,
                            user: dict = Depends(require_permission("safety_inspections", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    return await db.safety_inspections.find(q, {"_id": 0}).sort("inspection_date", -1).to_list(2000)


@router.post("/inspections")
async def create_inspection(payload: InspectionIn,
                             user: dict = Depends(require_permission("safety_inspections", "write"))):
    ino = await next_sequence("INSP")
    lines = [l.model_dump() for l in payload.lines]
    doc = {
        **payload.model_dump(exclude={"lines"}),
        "id": new_id(),
        "inspection_no": ino,
        "lines": lines,
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_inspections.insert_one(doc)
    await _audit("safety_inspection", doc["id"], ino, "created", user, {"line_count": len(lines)})
    doc.pop("_id", None)
    return doc


@router.put("/inspections/{iid}")
async def update_inspection(iid: str, payload: InspectionIn,
                             user: dict = Depends(require_permission("safety_inspections", "write"))):
    existing = await db.safety_inspections.find_one({"id": iid})
    if not existing:
        raise HTTPException(404, "Inspection not found")
    if existing.get("status") == "closed":
        raise HTTPException(400, "Closed inspection cannot be edited")
    lines = [l.model_dump() for l in payload.lines]
    patch = {**payload.model_dump(exclude={"lines"}), "lines": lines, "updated_at": now_iso(),
             "updated_by": user.get("name") or user.get("email")}
    await db.safety_inspections.update_one({"id": iid}, {"$set": patch})
    await _audit("safety_inspection", iid, existing["inspection_no"], "updated", user)
    return await db.safety_inspections.find_one({"id": iid}, {"_id": 0})


@router.post("/inspections/{iid}/close")
async def close_inspection(iid: str,
                            user: dict = Depends(require_permission("safety_inspections", "write"))):
    doc = await db.safety_inspections.find_one({"id": iid})
    if not doc:
        raise HTTPException(404, "Inspection not found")
    await db.safety_inspections.update_one({"id": iid}, {"$set": {
        "status": "closed",
        "closed_at": now_iso(),
        "closed_by": user.get("name") or user.get("email"),
    }})
    await _audit("safety_inspection", iid, doc["inspection_no"], "closed", user)
    return await db.safety_inspections.find_one({"id": iid}, {"_id": 0})


# ═══════════════════ Safety Observations / OFI ═══════════════════
class ObservationIn(BaseModel):
    observation_date: str
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    category_id: Optional[str] = None
    kind: str = Field("unsafe_act", description="unsafe_act | unsafe_condition | ofi")
    description: str = Field(..., min_length=3, max_length=2000)
    risk_level: Optional[str] = None
    immediate_action_taken: Optional[str] = ""
    corrective_action_required: bool = False
    responsible_person: Optional[str] = ""
    target_date: Optional[str] = None
    reported_by: Optional[str] = ""


@router.get("/observations-v2")
async def list_observations(status: Optional[str] = None, project_id: Optional[str] = None,
                             user: dict = Depends(require_permission("safety_reports", "read"))):
    """Iter 129 observations register — richer than the legacy `safety_observations`.
    Uses collection `safety_observations_v2` to avoid data mixing with the older
    unstructured `safety_observations` collection (which stays intact)."""
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    return await db.safety_observations_v2.find(q, {"_id": 0}).sort("observation_date", -1).to_list(2000)


@router.post("/observations-v2")
async def create_observation(payload: ObservationIn,
                              user: dict = Depends(require_permission("safety_reports", "write"))):
    ono = await next_sequence("OBS")
    doc = {
        **payload.model_dump(),
        "id": new_id(),
        "observation_no": ono,
        "status": "open",
        "capa_id": None,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    # High-risk observations auto-create a draft CAPA (Q2)
    capa_id: Optional[str] = None
    if (payload.risk_level or "").lower() in HIGH_RISK:
        capa_id = await _auto_create_capa(
            source_type="observation",
            source_id=doc["id"],
            source_no=ono,
            project_id=payload.project_id,
            project_code=payload.project_code,
            corrective_action=f"Address observation: {payload.description[:120]}",
            responsible_person=payload.responsible_person,
            target_date=payload.target_date,
            user=user,
        )
        doc["capa_id"] = capa_id
        # And create a high-risk escalation
        await _create_escalation("high_risk_observation", doc["id"], ono, payload.project_id,
                                  reason=f"High-risk observation reported: {payload.description[:120]}",
                                  level="high")
    await db.safety_observations_v2.insert_one(doc)
    await _audit("safety_observation", doc["id"], ono, "created", user,
                  {"auto_capa": capa_id, "risk_level": payload.risk_level})
    doc.pop("_id", None)
    return doc


@router.post("/observations-v2/{oid}/close")
async def close_observation(oid: str,
                             user: dict = Depends(require_permission("safety_reports", "write"))):
    doc = await db.safety_observations_v2.find_one({"id": oid})
    if not doc:
        raise HTTPException(404, "Observation not found")
    await db.safety_observations_v2.update_one({"id": oid}, {"$set": {
        "status": "closed",
        "closed_at": now_iso(),
        "closed_by": user.get("name") or user.get("email"),
    }})
    await _audit("safety_observation", oid, doc["observation_no"], "closed", user)
    return await db.safety_observations_v2.find_one({"id": oid}, {"_id": 0})


# ═══════════════════ CAPA ═══════════════════
class CapaIn(BaseModel):
    source_type: str = Field(..., description="inspection | observation | incident | audit | client_feedback")
    source_id: Optional[str] = None
    source_no: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    corrective_action: str = Field(..., min_length=3, max_length=2000)
    preventive_action: Optional[str] = ""
    responsible_department: Optional[str] = ""
    responsible_person: Optional[str] = ""
    target_date: Optional[str] = None
    remarks: Optional[str] = ""


class CapaCloseIn(BaseModel):
    evidence_ids: List[str] = Field(default_factory=list)
    override_reason: Optional[str] = None       # Required when evidence_ids is empty
    completion_notes: Optional[str] = ""


async def _auto_create_capa(*, source_type: str, source_id: str, source_no: str,
                             project_id: Optional[str], project_code: Optional[str],
                             corrective_action: str, responsible_person: Optional[str],
                             target_date: Optional[str], user: dict) -> str:
    """Internal helper — creates a draft CAPA when an observation/incident is
    flagged high-risk. Returns CAPA id."""
    capa_no = await next_sequence("CAPA")
    doc = {
        "id": new_id(),
        "capa_no": capa_no,
        "source_type": source_type,
        "source_id": source_id,
        "source_no": source_no,
        "project_id": project_id,
        "project_code": project_code,
        "corrective_action": corrective_action,
        "preventive_action": "",
        "responsible_department": "",
        "responsible_person": responsible_person or "",
        "target_date": target_date,
        "completion_date": None,
        "evidence_ids": [],
        "verified_by_safety": False,
        "status": "open",
        "closure_notes": "",
        "auto_created": True,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_capa.insert_one(doc)
    await _audit("safety_capa", doc["id"], capa_no, "auto_created", user, {"source": source_type})
    return doc["id"]


@router.get("/capa")
async def list_capa(status: Optional[str] = None, source_type: Optional[str] = None,
                     project_id: Optional[str] = None,
                     user: dict = Depends(require_permission("safety_capa", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if source_type:
        q["source_type"] = source_type
    if project_id:
        q["project_id"] = project_id
    return await db.safety_capa.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/capa")
async def create_capa(payload: CapaIn,
                       user: dict = Depends(require_permission("safety_capa", "write"))):
    capa_no = await next_sequence("CAPA")
    doc = {
        **payload.model_dump(),
        "id": new_id(),
        "capa_no": capa_no,
        "completion_date": None,
        "evidence_ids": [],
        "verified_by_safety": False,
        "status": "open",
        "closure_notes": "",
        "auto_created": False,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_capa.insert_one(doc)
    await _audit("safety_capa", doc["id"], capa_no, "created", user)
    doc.pop("_id", None)
    return doc


@router.put("/capa/{cid}")
async def update_capa(cid: str, payload: CapaIn,
                       user: dict = Depends(require_permission("safety_capa", "write"))):
    existing = await db.safety_capa.find_one({"id": cid})
    if not existing:
        raise HTTPException(404, "CAPA not found")
    if existing.get("status") == "closed":
        raise HTTPException(400, "Closed CAPA cannot be edited")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.safety_capa.update_one({"id": cid}, {"$set": patch})
    await _audit("safety_capa", cid, existing["capa_no"], "updated", user)
    return await db.safety_capa.find_one({"id": cid}, {"_id": 0})


@router.post("/capa/{cid}/close")
async def close_capa(cid: str, payload: CapaCloseIn,
                      user: dict = Depends(require_permission("safety_capa", "write"))):
    doc = await db.safety_capa.find_one({"id": cid})
    if not doc:
        raise HTTPException(404, "CAPA not found")
    if doc.get("status") == "closed":
        raise HTTPException(400, "CAPA already closed")
    # Enforce spec rule: CAPA cannot close without evidence unless override
    if not payload.evidence_ids and not (payload.override_reason and len(payload.override_reason) >= 10):
        raise HTTPException(400, "CAPA closure requires evidence, or an override_reason ≥10 chars")
    await db.safety_capa.update_one({"id": cid}, {"$set": {
        "status": "closed",
        "completion_date": now_iso()[:10],
        "closed_at": now_iso(),
        "closed_by": user.get("name") or user.get("email"),
        "evidence_ids": payload.evidence_ids,
        "closure_notes": payload.completion_notes or "",
        "override_reason": payload.override_reason,
        "verified_by_safety": True if payload.evidence_ids else False,
    }})
    await _audit("safety_capa", cid, doc["capa_no"], "closed", user, {
        "evidence_count": len(payload.evidence_ids),
        "override": bool(payload.override_reason),
    })
    return await db.safety_capa.find_one({"id": cid}, {"_id": 0})


@router.post("/capa/-/tick-overdue")
async def tick_capa_overdue(user: dict = Depends(require_permission("safety_capa", "write"))):
    """Flip past-`target_date` open CAPAs to `overdue` and create an escalation row.
    Safe to call daily; runs idempotently."""
    today = datetime.now(timezone.utc).date().isoformat()
    cursor = db.safety_capa.find(
        {"status": {"$in": ["open", "in_progress"]}, "target_date": {"$lt": today, "$ne": None}},
        {"_id": 0, "id": 1, "capa_no": 1, "project_id": 1},
    )
    count = 0
    async for r in cursor:
        # Skip if already escalated for this CAPA in the last 24h
        existing = await db.safety_escalations.find_one({
            "kind": "overdue_capa", "ref_id": r["id"], "status": "open",
        })
        await db.safety_capa.update_one({"id": r["id"]}, {"$set": {"status": "overdue", "updated_at": now_iso()}})
        if not existing:
            await _create_escalation("overdue_capa", r["id"], r.get("capa_no", ""),
                                      r.get("project_id"),
                                      reason=f"CAPA {r.get('capa_no', '')} target date passed",
                                      level="medium")
        count += 1
    return {"flagged_overdue": count, "as_of": now_iso()}


# ═══════════════════ Escalation Dashboard ═══════════════════
@router.get("/escalations")
async def list_escalations(status: Optional[str] = "open",
                            user: dict = Depends(require_permission("safety_escalations", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    return await db.safety_escalations.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/escalations/{eid}/close")
async def close_escalation(eid: str,
                            user: dict = Depends(require_permission("safety_escalations", "write"))):
    doc = await db.safety_escalations.find_one({"id": eid})
    if not doc:
        raise HTTPException(404, "Escalation not found")
    await db.safety_escalations.update_one({"id": eid}, {"$set": {
        "status": "closed",
        "closed_at": now_iso(),
        "closed_by": user.get("name") or user.get("email"),
    }})
    return await db.safety_escalations.find_one({"id": eid}, {"_id": 0})
