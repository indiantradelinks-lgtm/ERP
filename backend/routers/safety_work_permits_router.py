"""Safety · Work Permit Management · Iter 128 (Phase 2)
========================================================

Rich permit lifecycle sitting alongside the existing `work_permits` / `ptws`
CRUD (which the crud_router still serves for backwards compat). This router
adds:

* HIRA / JSA linkage with pre-approval validation
* LOTO / Gas / Rescue-plan flags
* Explicit request → approve → activate → close state machine
* High-risk permits auto-route to a Safety Officer → Safety Head approval
* Auto-expire background hook (`_check_expiries`) callable on-demand
* Closure creates an audit entry in `safety_audit_log`

Route shape (all live under `/api/safety/work-permits`):
    GET    /                              list, filter by status/project
    GET    /{pid}                         detail with linked HIRA/JSA snapshot
    POST   /                              create draft
    PUT    /{pid}                         update draft/requested/sent_back
    POST   /{pid}/request                 draft → requested (submits approval)
    POST   /{pid}/approve                 approver marks permit approved
    POST   /{pid}/activate                approved → active
    POST   /{pid}/close                   active → closed (with completion notes)
    POST   /{pid}/cancel                  any → cancelled (with reason)
    DELETE /{pid}                         draft only
    POST   /-/tick-expiries               marks active permits past valid_to as expired
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Request, APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission
from pagination import maybe_paged, paged_or_rows
from sequences import next_sequence
from approval_engine import insert_approval

router = APIRouter(prefix="/safety/work-permits", tags=["safety-work-permits"])

STATUSES = {"draft", "requested", "approved", "active", "expired", "closed", "cancelled", "sent_back"}
EDITABLE = {"draft", "sent_back"}
HIGH_RISK_PERMIT_SEVERITY = {"high", "critical"}

# Fixed 2-step chain: Safety Officer → Safety Head. `general_manager` acts as
# fallback for Safety Head in orgs where that role isn't seeded (we take the
# first user with role `dept_head` in the safety department, else GM).
PERMIT_APPROVAL_CHAIN = [
    {"role": "safety_officer", "label": "Safety Officer"},
    {"role": "dept_head", "label": "Safety Head"},
]


class WorkPermitIn(BaseModel):
    permit_type_id: Optional[str] = None
    permit_type_name: Optional[str] = None   # denormalised for UI
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    client_name: Optional[str] = None
    site_location: Optional[str] = None
    activity: Optional[str] = ""
    work_area: Optional[str] = ""
    permit_date: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    requested_by: Optional[str] = ""
    permit_issuer: Optional[str] = ""
    required_ppe_ids: List[str] = Field(default_factory=list)
    required_competency: Optional[str] = ""
    related_hira_id: Optional[str] = None
    related_jsa_id: Optional[str] = None
    isolation_loto_required: bool = False
    gas_testing_required: bool = False
    rescue_plan_required: bool = False
    emergency_contact: Optional[str] = ""
    attachments: List[str] = Field(default_factory=list)
    remarks: Optional[str] = ""


class ClosureIn(BaseModel):
    completion_notes: str = Field(..., min_length=3, max_length=2000)
    incidents_reported: bool = False


class CancelIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


# ─── Helpers ────────────────────────────────────────────────────────────
async def _write_audit(pid: str, permit_no: str, action: str, user: dict,
                        meta: Optional[Dict[str, Any]] = None) -> None:
    await db.safety_audit_log.insert_one({
        "id": new_id(),
        "record_kind": "work_permit",
        "record_id": pid,
        "record_no": permit_no,
        "action": action,
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "role": user.get("role"),
        "at": now_iso(),
        "meta": meta or {},
    })


async def _validate_linkage(permit: dict) -> None:
    """Enforce spec rule: permit cannot be approved if mandatory HIRA/JSA is pending."""
    if permit.get("related_hira_id"):
        h = await db.safety_hira.find_one({"id": permit["related_hira_id"]}, {"_id": 0, "status": 1, "hira_no": 1})
        if not h:
            raise HTTPException(400, "Linked HIRA no longer exists")
        if h.get("status") not in {"approved", "closed"}:
            raise HTTPException(400, f"Linked HIRA {h.get('hira_no')} is '{h.get('status')}' — must be approved first")
    if permit.get("related_jsa_id"):
        j = await db.safety_jsa.find_one({"id": permit["related_jsa_id"]}, {"_id": 0, "status": 1, "jsa_no": 1})
        if not j:
            raise HTTPException(400, "Linked JSA no longer exists")
        if j.get("status") not in {"approved", "closed"}:
            raise HTTPException(400, f"Linked JSA {j.get('jsa_no')} is '{j.get('status')}' — must be approved first")


async def _is_high_risk(permit: dict) -> bool:
    """A permit is 'high-risk' when its permit-type master row has severity
    high/critical, or when the linked HIRA is high_risk."""
    if permit.get("permit_type_id"):
        pt = await db.safety_work_permit_types.find_one({"id": permit["permit_type_id"]}, {"_id": 0, "severity": 1})
        if pt and (pt.get("severity") or "").lower() in HIGH_RISK_PERMIT_SEVERITY:
            return True
    if permit.get("related_hira_id"):
        h = await db.safety_hira.find_one({"id": permit["related_hira_id"]}, {"_id": 0, "high_risk": 1})
        if h and h.get("high_risk"):
            return True
    return False


async def _create_approval_doc(permit: dict, user: dict) -> str:
    chain = [{**step, "status": "pending", "approver": None, "at": None, "comment": None}
             for step in PERMIT_APPROVAL_CHAIN]
    approval_doc = {
        "id": new_id(),
        "type": "safety_work_permit",
        "module": "safety",
        "record_id": permit["id"],
        "title": f"Work Permit {permit['permit_no']} — {permit.get('permit_type_name') or 'permit'} approval",
        "summary": f"Project: {permit.get('project_code') or '—'} · Site: {permit.get('site_location') or '—'} · Activity: {permit.get('activity') or '—'}",
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
    return approval_doc["id"]


# ─── Endpoints ──────────────────────────────────────────────────────────
@router.get("")
async def list_permits(request: Request, status: Optional[str] = None, project_id: Optional[str] = None,
                        user: dict = Depends(require_permission("ptws", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    paged = await maybe_paged(request, "safety_work_permits", q, "created_at",
                              ["permit_no", "permit_type", "work_description", "project_name", "project_code", "location", "status", "issued_to", "contractor"])
    if paged:
        return paged
    return await db.safety_work_permits.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.get("/{pid}")
async def get_permit(pid: str, user: dict = Depends(require_permission("ptws", "read"))):
    doc = await db.safety_work_permits.find_one({"id": pid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Work Permit not found")
    return doc


@router.post("")
async def create_permit(payload: WorkPermitIn, user: dict = Depends(require_permission("ptws", "write"))):
    permit_no = await next_sequence("WP")
    doc = {
        **payload.model_dump(),
        "id": new_id(),
        "permit_no": permit_no,
        "status": "draft",
        "approval_id": None,
        "high_risk": await _is_high_risk(payload.model_dump()),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(),
    }
    await db.safety_work_permits.insert_one(doc)
    await _write_audit(doc["id"], permit_no, "created", user)
    doc.pop("_id", None)
    return doc


@router.put("/{pid}")
async def update_permit(pid: str, payload: WorkPermitIn, user: dict = Depends(require_permission("ptws", "write"))):
    existing = await db.safety_work_permits.find_one({"id": pid})
    if not existing:
        raise HTTPException(404, "Work Permit not found")
    if existing.get("status") not in EDITABLE:
        raise HTTPException(400, f"Cannot edit permit in '{existing.get('status')}' state")
    patch = payload.model_dump()
    patch["high_risk"] = await _is_high_risk({**existing, **patch})
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.safety_work_permits.update_one({"id": pid}, {"$set": patch})
    await _write_audit(pid, existing["permit_no"], "updated", user)
    return await db.safety_work_permits.find_one({"id": pid}, {"_id": 0})


@router.post("/{pid}/request")
async def request_permit(pid: str, user: dict = Depends(require_permission("ptws", "write"))):
    """Draft → Requested. Creates an approval doc via the shared engine."""
    doc = await db.safety_work_permits.find_one({"id": pid})
    if not doc:
        raise HTTPException(404, "Work Permit not found")
    if doc.get("status") not in EDITABLE:
        raise HTTPException(400, f"Cannot request permit in '{doc.get('status')}' state")
    if not doc.get("project_id") and not doc.get("project_code"):
        raise HTTPException(400, "Permit requires a project before it can be requested")
    if not doc.get("activity"):
        raise HTTPException(400, "Permit requires an activity before it can be requested")
    await _validate_linkage(doc)   # 400 if HIRA/JSA pending
    approval_id = await _create_approval_doc(doc, user)
    await db.safety_work_permits.update_one({"id": pid}, {"$set": {
        "status": "requested", "approval_id": approval_id, "updated_at": now_iso(),
    }})
    await _write_audit(pid, doc["permit_no"], "requested", user, {"approval_id": approval_id})
    return await db.safety_work_permits.find_one({"id": pid}, {"_id": 0})


@router.post("/{pid}/approve")
async def approve_permit(pid: str, user: dict = Depends(require_permission("ptws", "write"))):
    """Approver marks the permit approved. In prod flow this is normally
    triggered from `MyApprovalsInbox`; we expose it here for testability and
    for the safety-officer direct-approval path when no full chain is needed."""
    doc = await db.safety_work_permits.find_one({"id": pid})
    if not doc:
        raise HTTPException(404, "Work Permit not found")
    if doc.get("status") != "requested":
        raise HTTPException(400, f"Cannot approve permit in '{doc.get('status')}' state")
    await _validate_linkage(doc)   # Re-check at approval time
    await db.safety_work_permits.update_one({"id": pid}, {"$set": {
        "status": "approved",
        "approved_at": now_iso(),
        "approved_by": user.get("name") or user.get("email"),
        "approved_by_id": user.get("id"),
        "updated_at": now_iso(),
    }})
    await _write_audit(pid, doc["permit_no"], "approved", user)
    return await db.safety_work_permits.find_one({"id": pid}, {"_id": 0})


@router.post("/{pid}/activate")
async def activate_permit(pid: str, user: dict = Depends(require_permission("ptws", "write"))):
    doc = await db.safety_work_permits.find_one({"id": pid})
    if not doc:
        raise HTTPException(404, "Work Permit not found")
    if doc.get("status") != "approved":
        raise HTTPException(400, f"Cannot activate permit in '{doc.get('status')}' state")
    await db.safety_work_permits.update_one({"id": pid}, {"$set": {
        "status": "active",
        "activated_at": now_iso(),
        "updated_at": now_iso(),
    }})
    await _write_audit(pid, doc["permit_no"], "activated", user)
    return await db.safety_work_permits.find_one({"id": pid}, {"_id": 0})


@router.post("/{pid}/close")
async def close_permit(pid: str, payload: ClosureIn,
                        user: dict = Depends(require_permission("ptws", "write"))):
    doc = await db.safety_work_permits.find_one({"id": pid})
    if not doc:
        raise HTTPException(404, "Work Permit not found")
    if doc.get("status") not in {"active", "expired"}:
        raise HTTPException(400, f"Cannot close permit in '{doc.get('status')}' state")
    await db.safety_work_permits.update_one({"id": pid}, {"$set": {
        "status": "closed",
        "closed_at": now_iso(),
        "closed_by": user.get("name") or user.get("email"),
        "closure_notes": payload.completion_notes,
        "incidents_reported_at_closure": payload.incidents_reported,
        "updated_at": now_iso(),
    }})
    await _write_audit(pid, doc["permit_no"], "closed", user, {
        "incidents_reported": payload.incidents_reported,
        "notes": payload.completion_notes[:120],
    })
    return await db.safety_work_permits.find_one({"id": pid}, {"_id": 0})


@router.post("/{pid}/cancel")
async def cancel_permit(pid: str, payload: CancelIn,
                         user: dict = Depends(require_permission("ptws", "write"))):
    doc = await db.safety_work_permits.find_one({"id": pid})
    if not doc:
        raise HTTPException(404, "Work Permit not found")
    if doc.get("status") in {"closed", "cancelled"}:
        raise HTTPException(400, f"Permit already in '{doc.get('status')}' state")
    await db.safety_work_permits.update_one({"id": pid}, {"$set": {
        "status": "cancelled",
        "cancelled_at": now_iso(),
        "cancelled_by": user.get("name") or user.get("email"),
        "cancellation_reason": payload.reason,
        "updated_at": now_iso(),
    }})
    await _write_audit(pid, doc["permit_no"], "cancelled", user, {"reason": payload.reason})
    return await db.safety_work_permits.find_one({"id": pid}, {"_id": 0})


@router.delete("/{pid}")
async def delete_permit(pid: str, user: dict = Depends(require_permission("ptws", "delete"))):
    doc = await db.safety_work_permits.find_one({"id": pid}, {"_id": 0, "status": 1, "permit_no": 1})
    if not doc:
        raise HTTPException(404, "Work Permit not found")
    if doc.get("status") != "draft":
        raise HTTPException(400, "Only draft permits can be deleted; use /cancel instead")
    await db.safety_work_permits.delete_one({"id": pid})
    await _write_audit(pid, doc.get("permit_no", ""), "deleted", user)
    return {"ok": True}


@router.post("/-/tick-expiries")
async def tick_expiries(user: dict = Depends(require_permission("ptws", "write"))):
    """Marks any `active` permit whose `valid_to` has passed as `expired`.
    Safe to call on-demand; scheduler can call it daily."""
    today = datetime.now(timezone.utc).date().isoformat()
    cursor = db.safety_work_permits.find(
        {"status": "active", "valid_to": {"$lt": today, "$ne": None}},
        {"_id": 0, "id": 1, "permit_no": 1},
    )
    count = 0
    async for r in cursor:
        await db.safety_work_permits.update_one({"id": r["id"]}, {"$set": {
            "status": "expired",
            "expired_at": now_iso(),
            "updated_at": now_iso(),
        }})
        await _write_audit(r["id"], r.get("permit_no", ""), "auto_expired",
                            {"id": None, "name": "system", "role": "system"})
        count += 1
    return {"expired_now": count, "as_of": now_iso()}
