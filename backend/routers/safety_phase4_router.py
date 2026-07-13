"""Safety · Phase 4 (Audits · Client Compliance · Reviews · Vendor · Cost) · Iter 130
======================================================================================

One consolidated router covering the six Phase-4 domains. Every domain shares
the same audit/approval conventions from Phases 1-3 (writes to `safety_audit_log`,
routes high-value items through the shared `approvals` engine).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission, get_current_user
from sequences import next_sequence
from approval_engine import insert_approval

router = APIRouter(prefix="/safety", tags=["safety-phase4"])

DEFAULT_COST_APPROVAL_THRESHOLD = 50_000


async def _get_threshold(key: str, default: float) -> float:
    s = await db.safety_settings.find_one({"key": key}, {"_id": 0, "value": 1})
    if s and isinstance(s.get("value"), (int, float)):
        return float(s["value"])
    return float(default)


async def _audit(kind: str, rid: str, rno: str, action: str, user: dict, meta: Optional[Dict] = None):
    await db.safety_audit_log.insert_one({
        "id": new_id(), "record_kind": kind, "record_id": rid, "record_no": rno,
        "action": action, "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "role": user.get("role"), "at": now_iso(), "meta": meta or {},
    })


# ═══════════════════ 1. Safety Audits ═══════════════════
AUDIT_TYPES = {"internal", "client", "third_party", "site", "contractor", "ppe", "scaffold", "work_permit"}


class AuditFinding(BaseModel):
    finding: str = Field(..., min_length=3, max_length=1000)
    non_compliance: Optional[str] = ""
    risk_level: Optional[str] = None      # low/medium/high/critical
    corrective_action: Optional[str] = ""
    responsible_person: Optional[str] = ""
    target_date: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    capa_id: Optional[str] = None
    status: str = "open"


class SafetyAuditIn(BaseModel):
    audit_date: str
    audit_type: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    auditor: Optional[str] = ""
    checklist_id: Optional[str] = None
    audit_score: Optional[float] = None
    attachments: List[str] = Field(default_factory=list)
    remarks: Optional[str] = ""
    findings: List[AuditFinding] = Field(default_factory=list)


async def _auto_capa_from_finding(audit: dict, idx: int, finding: dict, user: dict) -> str:
    capa_no = await next_sequence("CAPA")
    doc = {
        "id": new_id(), "capa_no": capa_no,
        "source_type": "audit", "source_id": audit["id"], "source_no": audit["audit_no"],
        "project_id": audit.get("project_id"), "project_code": audit.get("project_code"),
        "corrective_action": finding.get("corrective_action") or f"Address: {finding['finding'][:120]}",
        "preventive_action": "", "responsible_person": finding.get("responsible_person") or "",
        "target_date": finding.get("target_date"),
        "evidence_ids": [], "verified_by_safety": False, "status": "open",
        "auto_created": True, "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "audit_finding_index": idx,
    }
    await db.safety_capa.insert_one(doc)
    return doc["id"]


@router.get("/audits")
async def list_audits(status: Optional[str] = None,
                      user: dict = Depends(require_permission("safety_audits", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    return await db.safety_audits.find(q, {"_id": 0}).sort("audit_date", -1).to_list(2000)


@router.post("/audits")
async def create_audit(payload: SafetyAuditIn,
                       user: dict = Depends(require_permission("safety_audits", "write"))):
    if payload.audit_type not in AUDIT_TYPES:
        raise HTTPException(400, f"audit_type must be one of {sorted(AUDIT_TYPES)}")
    ano = await next_sequence("AUD")
    findings = [f.model_dump() for f in payload.findings]
    doc = {
        **payload.model_dump(exclude={"findings"}),
        "id": new_id(), "audit_no": ano, "findings": findings,
        "status": "open", "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_audits.insert_one(doc)
    # Auto-CAPA on high-risk findings
    capa_ids: List[str] = []
    for i, f in enumerate(findings):
        if (f.get("risk_level") or "").lower() in {"high", "critical"}:
            cid = await _auto_capa_from_finding(doc, i, f, user)
            findings[i]["capa_id"] = cid
            capa_ids.append(cid)
    if capa_ids:
        await db.safety_audits.update_one({"id": doc["id"]}, {"$set": {"findings": findings}})
    await _audit("safety_audit", doc["id"], ano, "created", user, {"auto_capa_count": len(capa_ids)})
    doc["findings"] = findings
    doc.pop("_id", None)
    return doc


@router.post("/audits/{aid}/close")
async def close_audit(aid: str, user: dict = Depends(require_permission("safety_audits", "write"))):
    doc = await db.safety_audits.find_one({"id": aid})
    if not doc:
        raise HTTPException(404, "Audit not found")
    await db.safety_audits.update_one({"id": aid}, {"$set": {
        "status": "closed", "closed_at": now_iso(),
        "closed_by": user.get("name") or user.get("email"),
    }})
    await _audit("safety_audit", aid, doc["audit_no"], "closed", user)
    return await db.safety_audits.find_one({"id": aid}, {"_id": 0})


# ═══════════════════ 2. Client Compliance ═══════════════════
class ClientComplianceIn(BaseModel):
    client_name: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    requirement: str = Field(..., min_length=1, max_length=300)
    requirement_type: str = Field(..., description="safety_document | training | ppe | permit | inspection | scaffold_standard | medical_fitness | hr_clearance | site_clearance | job_completion | other")
    due_date: Optional[str] = None
    submitted_date: Optional[str] = None
    responsible_person: Optional[str] = ""
    attachments: List[str] = Field(default_factory=list)
    mandatory: bool = False
    remarks: Optional[str] = ""


def _compliance_status(row: dict, today: str) -> str:
    if row.get("submitted_date"):
        return "submitted"
    if row.get("due_date") and row["due_date"] < today:
        return "overdue"
    return "pending"


@router.get("/client-compliance")
async def list_client_compliance(project_id: Optional[str] = None,
                                   user: dict = Depends(require_permission("safety_client_compliance", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    rows = await db.safety_client_compliance.find(q, {"_id": 0}).sort("due_date", 1).to_list(2000)
    today = datetime.now(timezone.utc).date().isoformat()
    for r in rows:
        r["status"] = _compliance_status(r, today)
    return rows


@router.post("/client-compliance")
async def create_client_compliance(payload: ClientComplianceIn,
                                     user: dict = Depends(require_permission("safety_client_compliance", "write"))):
    doc = {
        **payload.model_dump(), "id": new_id(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_client_compliance.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/client-compliance/{cid}")
async def update_client_compliance(cid: str, payload: ClientComplianceIn,
                                     user: dict = Depends(require_permission("safety_client_compliance", "write"))):
    existing = await db.safety_client_compliance.find_one({"id": cid}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(404, "Not found")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.safety_client_compliance.update_one({"id": cid}, {"$set": patch})
    return await db.safety_client_compliance.find_one({"id": cid}, {"_id": 0})


@router.get("/client-compliance/blocking/{project_id}")
async def blocking_client_compliance(project_id: str,
                                       user: dict = Depends(require_permission("safety_client_compliance", "read"))):
    """Returns pending mandatory client compliance rows for a project — used
    by Projects & Ops to block project closure per spec rule 2."""
    today = datetime.now(timezone.utc).date().isoformat()
    rows = await db.safety_client_compliance.find(
        {"project_id": project_id, "mandatory": True, "submitted_date": None}, {"_id": 0}
    ).to_list(500)
    for r in rows:
        r["status"] = _compliance_status(r, today)
    return {"blocks_closure": len(rows) > 0, "pending_mandatory": rows}


# ═══════════════════ 3. Monthly Safety Review ═══════════════════
class ReviewActionItem(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    responsible_person: Optional[str] = ""
    target_date: Optional[str] = None
    status: str = "open"
    evidence_ids: List[str] = Field(default_factory=list)
    capa_id: Optional[str] = None


class SafetyReviewIn(BaseModel):
    month: str = Field(..., description="YYYY-MM")
    meeting_date: str
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    attendees: List[str] = Field(default_factory=list)
    key_observations: Optional[str] = ""
    ofis: Optional[str] = ""
    incident_review: Optional[str] = ""
    capa_status_summary: Optional[str] = ""
    training_status: Optional[str] = ""
    ppe_compliance_status: Optional[str] = ""
    client_observations: Optional[str] = ""
    attachments: List[str] = Field(default_factory=list)
    action_items: List[ReviewActionItem] = Field(default_factory=list)


@router.get("/reviews")
async def list_reviews(project_id: Optional[str] = None,
                        user: dict = Depends(require_permission("safety_reviews", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    return await db.safety_reviews.find(q, {"_id": 0}).sort("meeting_date", -1).to_list(500)


@router.post("/reviews")
async def create_review(payload: SafetyReviewIn,
                         user: dict = Depends(require_permission("safety_reviews", "write"))):
    rno = await next_sequence("REV")
    items = [i.model_dump() for i in payload.action_items]
    # Each action item auto-creates a CAPA (spec rule 1)
    for i, item in enumerate(items):
        capa_no = await next_sequence("CAPA")
        capa_doc = {
            "id": new_id(), "capa_no": capa_no,
            "source_type": "review", "source_no": rno,
            "project_id": payload.project_id, "project_code": payload.project_code,
            "corrective_action": item["description"],
            "responsible_person": item.get("responsible_person") or "",
            "target_date": item.get("target_date"),
            "evidence_ids": [], "status": "open", "auto_created": True,
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
        }
        await db.safety_capa.insert_one(capa_doc)
        items[i]["capa_id"] = capa_doc["id"]
    doc = {
        **payload.model_dump(exclude={"action_items"}),
        "id": new_id(), "review_no": rno, "action_items": items,
        "status": "held", "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_reviews.insert_one(doc)
    await _audit("safety_review", doc["id"], rno, "created", user, {"action_item_count": len(items)})
    doc.pop("_id", None)
    return doc


# ═══════════════════ 4. Vendor Safety Compliance ═══════════════════
class VendorSafetyIn(BaseModel):
    vendor_id: str = Field(..., min_length=1)
    vendor_name: Optional[str] = ""
    vendor_type: Optional[str] = ""
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    safety_doc_valid_till: Optional[str] = None
    labour_licence_valid_till: Optional[str] = None
    pf_esic_valid: bool = False
    insurance_valid_till: Optional[str] = None
    training_ok: bool = False
    ppe_ok: bool = False
    work_permit_ok: bool = False
    mandatory_docs_present: bool = False
    remarks: Optional[str] = ""


def _vendor_approval_state(row: dict, today: str) -> str:
    """Vendor cannot be safety-approved if mandatory docs are missing or expired."""
    if not row.get("mandatory_docs_present"):
        return "not_approved"
    for k in ("safety_doc_valid_till", "labour_licence_valid_till", "insurance_valid_till"):
        v = row.get(k)
        if v and v < today:
            return "not_approved"
    return "approved"


@router.get("/vendor-compliance")
async def list_vendor_compliance(project_id: Optional[str] = None,
                                   user: dict = Depends(require_permission("safety_vendor_compliance", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    rows = await db.safety_vendor_compliance.find(q, {"_id": 0}).sort("vendor_name", 1).to_list(2000)
    today = datetime.now(timezone.utc).date().isoformat()
    for r in rows:
        r["safety_approval_state"] = _vendor_approval_state(r, today)
    return rows


@router.post("/vendor-compliance")
async def create_vendor_compliance(payload: VendorSafetyIn,
                                     user: dict = Depends(require_permission("safety_vendor_compliance", "write"))):
    # Auto-fill vendor_name from Procurement master if not provided
    vendor_name = payload.vendor_name
    if not vendor_name:
        v = await db.vendors.find_one({"id": payload.vendor_id}, {"_id": 0, "name": 1})
        if v:
            vendor_name = v.get("name") or ""
    doc = {
        **payload.model_dump(),
        "vendor_name": vendor_name,
        "id": new_id(), "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.safety_vendor_compliance.insert_one(doc)
    doc.pop("_id", None)
    today = datetime.now(timezone.utc).date().isoformat()
    doc["safety_approval_state"] = _vendor_approval_state(doc, today)
    return doc


# ═══════════════════ 5. Safety Costs (+ Penalty + Recovery) ═══════════════════
COST_SOURCES = {"ppe_purchase", "training", "medical", "incident", "audit", "equipment",
                 "compliance", "corrective_action", "vendor_safety", "penalty", "recovery"}


class SafetyCostIn(BaseModel):
    cost_source: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_bill_ref: Optional[str] = None
    incident_id: Optional[str] = None
    audit_id: Optional[str] = None
    amount: float = Field(..., gt=0)
    is_recovery: bool = False
    cost_date: str
    description: Optional[str] = ""


@router.get("/costs")
async def list_costs(project_id: Optional[str] = None, cost_source: Optional[str] = None,
                     user: dict = Depends(require_permission("safety_costs", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if cost_source:
        q["cost_source"] = cost_source
    return await db.safety_costs.find(q, {"_id": 0}).sort("cost_date", -1).to_list(2000)


@router.post("/costs")
async def create_cost(payload: SafetyCostIn,
                       user: dict = Depends(require_permission("safety_costs", "write"))):
    if payload.cost_source not in COST_SOURCES:
        raise HTTPException(400, f"cost_source must be one of {sorted(COST_SOURCES)}")
    doc = {
        **payload.model_dump(), "id": new_id(),
        "approval_id": None, "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    # Auto-route high-value costs to Finance Head approval
    threshold = await _get_threshold("cost_approval_threshold", DEFAULT_COST_APPROVAL_THRESHOLD)
    if payload.amount >= threshold:
        approval_doc = {
            "id": new_id(),
            "type": "safety_cost", "module": "safety",
            "record_id": doc["id"],
            "title": f"Safety cost ₹{payload.amount:,.0f} — {payload.cost_source}",
            "summary": f"Project {payload.project_code or '—'} · Source: {payload.cost_source}",
            "requested_by": user.get("name") or user.get("email"),
            "status": "pending", "current_step": 0,
            "chain": [{"role": "finance_head", "label": "Finance Head",
                       "status": "pending", "approver": None, "at": None, "comment": None}],
            "history": [], "created_at": now_iso(), "updated_at": now_iso(),
        }
        await insert_approval(approval_doc, skip_gate=True)
        doc["approval_id"] = approval_doc["id"]
    await db.safety_costs.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ═══════════════════ 6. Management Review Dashboard ═══════════════════
@router.get("/management-review")
async def management_review(user: dict = Depends(get_current_user)):
    """Aggregate rollup for the Safety Management Review dashboard."""
    today = datetime.now(timezone.utc).date().isoformat()
    total_costs = 0.0
    penalty_cost = 0.0
    recovery_amount = 0.0
    async for c in db.safety_costs.find({}, {"_id": 0, "amount": 1, "cost_source": 1, "is_recovery": 1}):
        amt = float(c.get("amount") or 0)
        if c.get("is_recovery"):
            recovery_amount += amt
        else:
            total_costs += amt
            if c.get("cost_source") == "penalty":
                penalty_cost += amt

    open_capas = await db.safety_capa.count_documents({"status": {"$in": ["open", "in_progress", "overdue"]}})
    overdue_capas = await db.safety_capa.count_documents({"status": "overdue"})
    critical_incidents = await db.safety_incidents.count_documents({"is_critical": True, "status": {"$ne": "closed"}})
    open_audits = await db.safety_audits.count_documents({"status": "open"})
    pending_client_compliance = await db.safety_client_compliance.count_documents({
        "submitted_date": None, "mandatory": True,
    })
    vendor_not_approved = 0
    async for v in db.safety_vendor_compliance.find({}, {"_id": 0}):
        if _vendor_approval_state(v, today) == "not_approved":
            vendor_not_approved += 1
    reviews_this_year = await db.safety_reviews.count_documents({"month": {"$gte": today[:4] + "-01"}})

    return {
        "as_of": now_iso(),
        "kpis": {
            "total_safety_cost": round(total_costs, 2),
            "penalty_cost": round(penalty_cost, 2),
            "recovery_amount": round(recovery_amount, 2),
            "open_capas": open_capas,
            "overdue_capas": overdue_capas,
            "open_critical_incidents": critical_incidents,
            "open_audits": open_audits,
            "pending_mandatory_client_compliance": pending_client_compliance,
            "vendors_not_safety_approved": vendor_not_approved,
            "reviews_held_this_year": reviews_this_year,
        },
    }
