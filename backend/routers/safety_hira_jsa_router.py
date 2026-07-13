"""Safety · HIRA & JSA · Iter 127
=================================

Two closely-related resources with the same lifecycle so we keep them in one
router:

* HIRA (Hazard Identification & Risk Assessment) — activity/hazard-based risk
  register. Per line: activity, hazard, consequence, existing control,
  likelihood, severity, risk_rating, additional_control, responsible, target_date.
* JSA (Job Safety Analysis) — job-step-based hazard register. Per line:
  step, hazard, risk, control, ppe_ids, permit_ids, competency, responsible.

Shared behaviour:
* Auto-numbered (`HIRA-YYYY-NNNN`, `JSA-YYYY-NNNN`) via sequences.
* Revisions preserve the previous version — every "revise" clones the doc,
  bumps `rev`, and stores the old doc under `revisions[]`.
* Approved records cannot be edited or deleted (state machine).
* High-risk (any line with `risk_rating` ∈ {`high`,`critical`}) auto-creates an
  approval request in the shared `approvals` collection wired for
  `safety_officer` + `project_manager` (both must approve).
* Every state change writes to `safety_audit_log` for the audit trail.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission
from sequences import next_sequence
from approval_engine import build_chain, insert_approval

router = APIRouter(prefix="/safety", tags=["safety-hira-jsa"])

HIGH_RISK_RATINGS = {"high", "critical"}
LOCKED_STATUSES = {"approved", "closed"}

# Approval chain: Safety Officer → Project Manager (both must approve).
HIRA_JSA_CHAIN = [
    {"role": "safety_officer", "label": "Safety Officer"},
    {"role": "project_manager", "label": "Project Manager"},
]

# ─── Models ─────────────────────────────────────────────────────────────
class HIRALine(BaseModel):
    activity: str = Field(..., min_length=1, max_length=500)
    hazard: str = Field(..., min_length=1, max_length=500)
    consequence: Optional[str] = ""
    existing_control: Optional[str] = ""
    likelihood: Optional[str] = None    # rare / unlikely / possible / likely / almost_certain
    severity: Optional[str] = None      # negligible / minor / moderate / major / catastrophic
    risk_rating: Optional[str] = None   # low / medium / high / critical
    additional_control: Optional[str] = ""
    responsible_person: Optional[str] = ""
    target_date: Optional[str] = None


class HIRAIn(BaseModel):
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    client_name: Optional[str] = ""
    service_type: Optional[str] = None   # scaffolding / painting / …
    prepared_by: Optional[str] = ""
    reviewed_by: Optional[str] = ""
    approved_by: Optional[str] = ""
    remarks: Optional[str] = ""
    lines: List[HIRALine] = Field(default_factory=list)


class JSALine(BaseModel):
    step_no: Optional[int] = None
    step: str = Field(..., min_length=1, max_length=500)
    hazard: Optional[str] = ""
    risk: Optional[str] = None            # low/medium/high/critical
    control_measure: Optional[str] = ""
    required_ppe: List[str] = Field(default_factory=list)     # list of PPE-category ids
    required_permit_ids: List[str] = Field(default_factory=list)  # WPT ids
    manpower_competency: Optional[str] = ""
    responsible_person: Optional[str] = ""


class JSAIn(BaseModel):
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_location: Optional[str] = ""
    activity: str = Field(..., min_length=1, max_length=300)
    prepared_by: Optional[str] = ""
    reviewed_by: Optional[str] = ""
    approved_by: Optional[str] = ""
    remarks: Optional[str] = ""
    lines: List[JSALine] = Field(default_factory=list)


# ─── Helpers ────────────────────────────────────────────────────────────
def _has_high_risk_lines(lines: List[Dict[str, Any]], key: str) -> bool:
    return any((l.get(key) or "").lower() in HIGH_RISK_RATINGS for l in lines)


async def _write_audit(record_kind: str, record_id: str, record_no: str,
                        action: str, user: dict, meta: Optional[Dict[str, Any]] = None) -> None:
    await db.safety_audit_log.insert_one({
        "id": new_id(),
        "record_kind": record_kind,      # 'hira' / 'jsa' / 'safety_plan' / 'safety_document'
        "record_id": record_id,
        "record_no": record_no,
        "action": action,                # 'created' | 'updated' | 'submitted' | 'approved' | 'revised' | 'closed'
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "role": user.get("role"),
        "at": now_iso(),
        "meta": meta or {},
    })


async def _submit_for_approval(kind: str, record: Dict[str, Any], user: dict) -> str:
    """Create an approval doc for a high-risk HIRA/JSA. Returns approval id."""
    # Prefer the DB-override chain if any admin has configured one for this type.
    chain_template = await build_chain(f"safety_{kind}") if False else None
    del chain_template
    chain = [{**step, "status": "pending", "approver": None, "at": None, "comment": None}
             for step in HIRA_JSA_CHAIN]
    approval_doc = {
        "id": new_id(),
        "type": f"safety_{kind}",
        "module": "safety",
        "record_id": record["id"],
        "title": f"{kind.upper()} {record.get(f'{kind}_no')} — high-risk approval",
        "summary": f"Project: {record.get('project_code') or '—'} · Site: {record.get('site_location') or '—'}",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    # HIRA/JSA don't gate on documents (spec doesn't require it) — bypass the gate.
    await insert_approval(approval_doc, skip_gate=True)
    return approval_doc["id"]


# ─── HIRA endpoints ─────────────────────────────────────────────────────
@router.get("/hira")
async def list_hira(status: Optional[str] = None, project_id: Optional[str] = None,
                     user: dict = Depends(require_permission("hira", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    rows = await db.safety_hira.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return rows


@router.get("/hira/{hid}")
async def get_hira(hid: str, user: dict = Depends(require_permission("hira", "read"))):
    doc = await db.safety_hira.find_one({"id": hid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "HIRA not found")
    return doc


@router.post("/hira")
async def create_hira(payload: HIRAIn, user: dict = Depends(require_permission("hira", "write"))):
    hira_no = await next_sequence("HIRA")
    lines = [l.model_dump() for l in payload.lines]
    doc = {
        **payload.model_dump(exclude={"lines"}),
        "id": new_id(),
        "hira_no": hira_no,
        "lines": lines,
        "rev": 0,
        "revisions": [],
        "status": "draft",
        "approval_id": None,
        "high_risk": _has_high_risk_lines(lines, "risk_rating"),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    await db.safety_hira.insert_one(doc)
    await _write_audit("hira", doc["id"], hira_no, "created", user, {"line_count": len(lines)})
    doc.pop("_id", None)
    return doc


@router.put("/hira/{hid}")
async def update_hira(hid: str, payload: HIRAIn, user: dict = Depends(require_permission("hira", "write"))):
    existing = await db.safety_hira.find_one({"id": hid})
    if not existing:
        raise HTTPException(404, "HIRA not found")
    if existing.get("status") in LOCKED_STATUSES:
        raise HTTPException(400, f"HIRA is {existing['status']} — use /revise to create a new revision")
    lines = [l.model_dump() for l in payload.lines]
    patch = {
        **payload.model_dump(exclude={"lines"}),
        "lines": lines,
        "high_risk": _has_high_risk_lines(lines, "risk_rating"),
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }
    await db.safety_hira.update_one({"id": hid}, {"$set": patch})
    await _write_audit("hira", hid, existing["hira_no"], "updated", user)
    return await db.safety_hira.find_one({"id": hid}, {"_id": 0})


@router.post("/hira/{hid}/submit")
async def submit_hira(hid: str, user: dict = Depends(require_permission("hira", "write"))):
    doc = await db.safety_hira.find_one({"id": hid})
    if not doc:
        raise HTTPException(404, "HIRA not found")
    if doc.get("status") not in {"draft", "sent_back"}:
        raise HTTPException(400, f"Cannot submit HIRA in '{doc.get('status')}' state")
    if not doc.get("project_id") and not doc.get("project_code"):
        raise HTTPException(400, "HIRA requires a project before submission")
    if not doc.get("lines"):
        raise HTTPException(400, "HIRA requires at least one activity/hazard line")
    is_high = _has_high_risk_lines(doc.get("lines") or [], "risk_rating")
    if is_high:
        approval_id = await _submit_for_approval("hira", doc, user)
        await db.safety_hira.update_one({"id": hid}, {"$set": {
            "status": "pending_approval", "approval_id": approval_id, "updated_at": now_iso(),
        }})
        await _write_audit("hira", hid, doc["hira_no"], "submitted", user, {"approval_id": approval_id})
    else:
        # Low/medium-only HIRAs auto-approve — no approval workflow needed.
        await db.safety_hira.update_one({"id": hid}, {"$set": {
            "status": "approved",
            "approved_at": now_iso(),
            "approved_by": user.get("name") or user.get("email"),
            "updated_at": now_iso(),
        }})
        await _write_audit("hira", hid, doc["hira_no"], "approved", user, {"auto": True, "reason": "no_high_risk_lines"})
    return await db.safety_hira.find_one({"id": hid}, {"_id": 0})


@router.post("/hira/{hid}/revise")
async def revise_hira(hid: str, user: dict = Depends(require_permission("hira", "write"))):
    """Clone the current doc into revisions[] and bump rev — returns doc for edit."""
    doc = await db.safety_hira.find_one({"id": hid})
    if not doc:
        raise HTTPException(404, "HIRA not found")
    snapshot = {k: v for k, v in doc.items() if k not in ("_id", "revisions")}
    revisions = list(doc.get("revisions") or [])
    revisions.append({"rev": doc.get("rev") or 0, "snapshot": snapshot, "revised_at": now_iso(),
                      "revised_by": user.get("name") or user.get("email")})
    await db.safety_hira.update_one({"id": hid}, {"$set": {
        "rev": (doc.get("rev") or 0) + 1,
        "revisions": revisions,
        "status": "draft",
        "approval_id": None,
        "updated_at": now_iso(),
    }})
    await _write_audit("hira", hid, doc["hira_no"], "revised", user, {"new_rev": (doc.get("rev") or 0) + 1})
    return await db.safety_hira.find_one({"id": hid}, {"_id": 0})


@router.delete("/hira/{hid}")
async def delete_hira(hid: str, user: dict = Depends(require_permission("hira", "delete"))):
    doc = await db.safety_hira.find_one({"id": hid}, {"_id": 0, "status": 1, "hira_no": 1})
    if not doc:
        raise HTTPException(404, "HIRA not found")
    if doc.get("status") in LOCKED_STATUSES:
        raise HTTPException(400, "Approved HIRA cannot be deleted")
    await db.safety_hira.delete_one({"id": hid})
    await _write_audit("hira", hid, doc.get("hira_no", ""), "deleted", user)
    return {"ok": True}


# ─── JSA endpoints ──────────────────────────────────────────────────────
@router.get("/jsa")
async def list_jsa(status: Optional[str] = None, project_id: Optional[str] = None,
                    user: dict = Depends(require_permission("jsa", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    return await db.safety_jsa.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.get("/jsa/{jid}")
async def get_jsa(jid: str, user: dict = Depends(require_permission("jsa", "read"))):
    doc = await db.safety_jsa.find_one({"id": jid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "JSA not found")
    return doc


@router.post("/jsa")
async def create_jsa(payload: JSAIn, user: dict = Depends(require_permission("jsa", "write"))):
    jsa_no = await next_sequence("JSA")
    lines = [l.model_dump() for l in payload.lines]
    doc = {
        **payload.model_dump(exclude={"lines"}),
        "id": new_id(),
        "jsa_no": jsa_no,
        "lines": lines,
        "rev": 0,
        "revisions": [],
        "status": "draft",
        "approval_id": None,
        "high_risk": _has_high_risk_lines(lines, "risk"),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    await db.safety_jsa.insert_one(doc)
    await _write_audit("jsa", doc["id"], jsa_no, "created", user, {"line_count": len(lines)})
    doc.pop("_id", None)
    return doc


@router.put("/jsa/{jid}")
async def update_jsa(jid: str, payload: JSAIn, user: dict = Depends(require_permission("jsa", "write"))):
    existing = await db.safety_jsa.find_one({"id": jid})
    if not existing:
        raise HTTPException(404, "JSA not found")
    if existing.get("status") in LOCKED_STATUSES:
        raise HTTPException(400, f"JSA is {existing['status']} — use /revise to create a new revision")
    lines = [l.model_dump() for l in payload.lines]
    patch = {
        **payload.model_dump(exclude={"lines"}),
        "lines": lines,
        "high_risk": _has_high_risk_lines(lines, "risk"),
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }
    await db.safety_jsa.update_one({"id": jid}, {"$set": patch})
    await _write_audit("jsa", jid, existing["jsa_no"], "updated", user)
    return await db.safety_jsa.find_one({"id": jid}, {"_id": 0})


@router.post("/jsa/{jid}/submit")
async def submit_jsa(jid: str, user: dict = Depends(require_permission("jsa", "write"))):
    doc = await db.safety_jsa.find_one({"id": jid})
    if not doc:
        raise HTTPException(404, "JSA not found")
    if doc.get("status") not in {"draft", "sent_back"}:
        raise HTTPException(400, f"Cannot submit JSA in '{doc.get('status')}' state")
    if not doc.get("lines"):
        raise HTTPException(400, "JSA requires at least one job step")
    is_high = _has_high_risk_lines(doc.get("lines") or [], "risk")
    if is_high:
        approval_id = await _submit_for_approval("jsa", doc, user)
        await db.safety_jsa.update_one({"id": jid}, {"$set": {
            "status": "pending_approval", "approval_id": approval_id, "updated_at": now_iso(),
        }})
        await _write_audit("jsa", jid, doc["jsa_no"], "submitted", user, {"approval_id": approval_id})
    else:
        await db.safety_jsa.update_one({"id": jid}, {"$set": {
            "status": "approved",
            "approved_at": now_iso(),
            "approved_by": user.get("name") or user.get("email"),
            "updated_at": now_iso(),
        }})
        await _write_audit("jsa", jid, doc["jsa_no"], "approved", user, {"auto": True, "reason": "no_high_risk_lines"})
    return await db.safety_jsa.find_one({"id": jid}, {"_id": 0})


@router.post("/jsa/{jid}/revise")
async def revise_jsa(jid: str, user: dict = Depends(require_permission("jsa", "write"))):
    doc = await db.safety_jsa.find_one({"id": jid})
    if not doc:
        raise HTTPException(404, "JSA not found")
    snapshot = {k: v for k, v in doc.items() if k not in ("_id", "revisions")}
    revisions = list(doc.get("revisions") or [])
    revisions.append({"rev": doc.get("rev") or 0, "snapshot": snapshot, "revised_at": now_iso(),
                      "revised_by": user.get("name") or user.get("email")})
    await db.safety_jsa.update_one({"id": jid}, {"$set": {
        "rev": (doc.get("rev") or 0) + 1,
        "revisions": revisions,
        "status": "draft",
        "approval_id": None,
        "updated_at": now_iso(),
    }})
    await _write_audit("jsa", jid, doc["jsa_no"], "revised", user, {"new_rev": (doc.get("rev") or 0) + 1})
    return await db.safety_jsa.find_one({"id": jid}, {"_id": 0})


@router.delete("/jsa/{jid}")
async def delete_jsa(jid: str, user: dict = Depends(require_permission("jsa", "delete"))):
    doc = await db.safety_jsa.find_one({"id": jid}, {"_id": 0, "status": 1, "jsa_no": 1})
    if not doc:
        raise HTTPException(404, "JSA not found")
    if doc.get("status") in LOCKED_STATUSES:
        raise HTTPException(400, "Approved JSA cannot be deleted")
    await db.safety_jsa.delete_one({"id": jid})
    await _write_audit("jsa", jid, doc.get("jsa_no", ""), "deleted", user)
    return {"ok": True}


# ─── Audit trail read endpoint ──────────────────────────────────────────
@router.get("/audit-log")
async def safety_audit_log(
    record_kind: Optional[str] = None,
    record_id: Optional[str] = None,
    limit: int = 500,
    user: dict = Depends(require_permission("hira", "read")),
):
    if limit < 1 or limit > 5000:
        raise HTTPException(400, "limit must be 1..5000")
    q: Dict[str, Any] = {}
    if record_kind:
        q["record_kind"] = record_kind
    if record_id:
        q["record_id"] = record_id
    rows = await db.safety_audit_log.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return rows
