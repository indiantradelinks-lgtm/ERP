"""Employee Advance Register & Recovery (Phase A + B).

Phase A: Request creation (self + on-behalf), approval workflow, attachments, audit.
Phase B: Finance payment entry + ledger auto-creation + outstanding tracking.
Phase C (deferred): EMI auto-recovery during payroll run.

Endpoints under /api/advances and /api/advance-types.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, now_iso, new_id
from rbac import can
from approval_engine import build_chain, apply_action, current_step, insert_approval, copy_approval_doc_fields
from sequences import next_sequence, next_dept_doc

logger = logging.getLogger("erp.advances")
router = APIRouter(tags=["advances"])

# ────────────────────────────────────────────────────────────────────────
# Defaults: 7 advance types seeded on startup if collection is empty
# ────────────────────────────────────────────────────────────────────────
DEFAULT_ADVANCE_TYPES = [
    {"code": "SAL", "name": "Salary Advance", "max_amount": 100000, "max_installments": 12},
    {"code": "EMG", "name": "Emergency Advance", "max_amount": 50000, "max_installments": 6},
    {"code": "MED", "name": "Medical Advance", "max_amount": 200000, "max_installments": 24},
    {"code": "SITE", "name": "Site Advance", "max_amount": 25000, "max_installments": 3},
    {"code": "FEST", "name": "Festival Advance", "max_amount": 50000, "max_installments": 12},
    {"code": "TRVL", "name": "Travel Advance", "max_amount": 30000, "max_installments": 3},
    {"code": "OTH", "name": "Other", "max_amount": 0, "max_installments": 0},
]


async def seed_advance_types_if_empty() -> int:
    """Idempotent seed at startup."""
    cnt = await db.advance_types.count_documents({})
    if cnt > 0:
        return 0
    docs = [
        {"id": new_id(), **t, "description": "", "active": True, "created_at": now_iso()}
        for t in DEFAULT_ADVANCE_TYPES
    ]
    await db.advance_types.insert_many(docs)
    return len(docs)


# ────────────────────────────────────────────────────────────────────────
# Advance Types CRUD (admin / hr)
# ────────────────────────────────────────────────────────────────────────
class AdvanceTypeIn(BaseModel):
    code: str
    name: str
    description: str = ""
    max_amount: float = 0
    max_installments: int = 0
    active: bool = True


@router.get("/advance-types")
async def list_advance_types(active_only: bool = False, user: dict = Depends(get_current_user)):
    q = {"active": True} if active_only else {}
    rows = await db.advance_types.find(q, {"_id": 0}).sort("name", 1).to_list(100)
    return rows


@router.post("/advance-types")
async def create_advance_type(payload: AdvanceTypeIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "hr_executive", "general_manager", "director"}:
        raise HTTPException(status_code=403, detail="not allowed")
    if not payload.code.strip() or not payload.name.strip():
        raise HTTPException(status_code=400, detail="code and name required")
    existing = await db.advance_types.find_one({"code": payload.code.strip().upper()})
    if existing:
        raise HTTPException(status_code=409, detail="advance type code already exists")
    doc = {"id": new_id(), **payload.model_dump(), "code": payload.code.strip().upper(),
           "created_by": user.get("name") or user.get("email"), "created_at": now_iso()}
    await db.advance_types.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/advance-types/{type_id}")
async def update_advance_type(type_id: str, payload: AdvanceTypeIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "hr_executive", "general_manager", "director"}:
        raise HTTPException(status_code=403, detail="not allowed")
    update = {**payload.model_dump(), "code": payload.code.strip().upper(), "updated_at": now_iso()}
    res = await db.advance_types.update_one({"id": type_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.delete("/advance-types/{type_id}")
async def delete_advance_type(type_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "hr_executive"}:
        raise HTTPException(status_code=403, detail="not allowed")
    res = await db.advance_types.delete_one({"id": type_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────
# Advance Requests
# ────────────────────────────────────────────────────────────────────────
class AdvanceCreateIn(BaseModel):
    employee_id: str
    advance_type: str   # name OR code
    requested_amount: float = Field(gt=0)
    reason: str
    emergency: bool = False
    site: str = ""
    project: str = ""
    repayment_start_month: str = ""   # "YYYY-MM"
    installments: int = Field(ge=1, default=1)
    remarks: str = ""
    attachments: list[str] = []   # file ids
    submit: bool = True            # if False saves as draft


class AdvancePaymentIn(BaseModel):
    mode: str          # bank_transfer | cash | cheque | upi
    paid_amount: float = Field(gt=0)
    payment_date: str  # YYYY-MM-DD
    bank_name: str = ""
    voucher_no: str = ""
    txn_no: str = ""
    remarks: str = ""


CREATE_ON_BEHALF_ROLES = {
    "super_admin", "hr_executive", "general_manager", "director",
    "project_manager", "dept_head", "accounts_executive",
}

PAYMENT_ROLES = {"super_admin", "accounts_executive", "general_manager", "director"}


async def _fetch_employee(emp_id: str) -> dict:
    emp = await db.employees.find_one({"id": emp_id}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="employee not found")
    return emp


def _is_self_request(user: dict, employee: dict) -> bool:
    if user.get("id") == employee.get("user_id"):
        return True
    user_email = (user.get("email") or "").lower()
    emp_email = (employee.get("email") or "").lower()
    return bool(user_email) and user_email == emp_email


async def _approval_pending_step(advance_id: str) -> Optional[dict]:
    a = await db.approvals.find_one(
        {"reference": advance_id, "type": "employee_advance", "status": {"$in": ["pending", "in_progress"]}},
        {"_id": 0},
    )
    if not a:
        return None
    return current_step(a)


@router.post("/advances")
async def create_advance(payload: AdvanceCreateIn, user: dict = Depends(get_current_user)):
    emp = await _fetch_employee(payload.employee_id)
    on_behalf = not _is_self_request(user, emp)
    if on_behalf and user.get("role") not in CREATE_ON_BEHALF_ROLES:
        raise HTTPException(status_code=403, detail="not allowed to create on behalf of another employee")

    # Resolve advance type
    atype = await db.advance_types.find_one(
        {"$or": [{"code": payload.advance_type.upper()}, {"name": payload.advance_type}], "active": True},
        {"_id": 0},
    )
    if not atype:
        raise HTTPException(status_code=400, detail=f"unknown advance type '{payload.advance_type}'")
    if atype.get("max_amount") and payload.requested_amount > atype["max_amount"]:
        raise HTTPException(status_code=400, detail=f"requested amount exceeds cap (₹{atype['max_amount']:,.0f}) for {atype['name']}")
    if atype.get("max_installments") and payload.installments > atype["max_installments"]:
        raise HTTPException(status_code=400, detail=f"installments exceed cap ({atype['max_installments']}) for {atype['name']}")

    adv_no = await next_sequence("AD")  # → AD-YYYY-####
    dept_no = await next_dept_doc("advance")
    emi = round(payload.requested_amount / payload.installments, 2) if payload.installments else 0

    doc = {
        "id": new_id(),
        "advance_no": adv_no,
        "dept_doc_no": dept_no["dept_doc_no"],
        "ownership_department": dept_no["owner_dept"],
        "employee_id": emp["id"],
        "employee_code": emp.get("employee_id") or emp.get("emp_code"),
        "employee_name": emp.get("name"),
        "department": (emp.get("departments") or [None])[0] or emp.get("department"),
        "designation": emp.get("designation"),
        "site": payload.site or emp.get("site"),
        "project": payload.project,
        "reporting_manager": emp.get("reporting_manager"),
        "salary": emp.get("salary"),
        "joining_date": emp.get("joining_date"),
        "advance_type": atype["name"],
        "advance_type_code": atype["code"],
        "request_date": now_iso()[:10],
        "requested_amount": payload.requested_amount,
        "approved_amount": 0,
        "paid_amount": 0,
        "recovered_amount": 0,
        "outstanding": 0,
        "reason": payload.reason,
        "emergency": payload.emergency,
        "remarks": payload.remarks,
        "repayment_start_month": payload.repayment_start_month,
        "installments": payload.installments,
        "remaining_installments": payload.installments,
        "emi": emi,
        "attachments": payload.attachments or [],
        "status": "draft",
        "on_behalf_of": on_behalf,
        "created_by_role": user.get("role"),
        "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
        "created_at": now_iso(),
        "status_history": [{"at": now_iso(), "by": user.get("name") or user.get("email"),
                            "by_role": user.get("role"), "from": None, "to": "draft", "comment": "Created"}],
    }
    await db.employee_advances.insert_one(doc)

    if payload.submit:
        return await _submit_advance(doc["id"], user, payload.model_dump(exclude_none=True))

    doc.pop("_id", None)
    return doc


async def _submit_advance(advance_id: str, user: dict, docs_payload: Optional[dict] = None) -> dict:
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if adv["status"] not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail=f"cannot submit from status '{adv['status']}'")

    chain = await build_chain("employee_advance")
    approval = {
        "id": new_id(),
        "title": f"Advance {adv['advance_no']} — {adv['employee_name']} (₹{adv['requested_amount']:,.0f})",
        "type": "employee_advance",
        "reference": adv["id"],
        "amount": adv["requested_amount"],
        "requested_by": adv["created_by"],
        "chain": chain,
        "current_step": 0,
        "history": [],
        "status": "pending",
        "created_at": now_iso(),
    }
    copy_approval_doc_fields(approval, docs_payload)
    await insert_approval(approval)
    await db.employee_advances.update_one(
        {"id": advance_id},
        {"$set": {"status": "submitted", "approval_id": approval["id"], "submitted_at": now_iso()},
         "$push": {"status_history": {"at": now_iso(), "by": user.get("name") or user.get("email"),
                                       "by_role": user.get("role"), "from": adv["status"], "to": "submitted",
                                       "comment": "Submitted for approval"}}},
    )
    out = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    return out


@router.post("/advances/{advance_id}/submit")
async def submit_advance(advance_id: str, body: Optional[dict] = None, user: dict = Depends(get_current_user)):
    return await _submit_advance(advance_id, user, body)


@router.get("/advances")
async def list_advances(
    status: str = "",
    employee_id: str = "",
    site: str = "",
    department: str = "",
    advance_type: str = "",
    user: dict = Depends(get_current_user),
):
    q: dict = {}
    # Visibility scope:
    # - Privileged roles see everything
    # - Other roles see only their own + (PM/dept_head can see their team)
    role = user.get("role")
    privileged = {"super_admin", "director", "general_manager", "hr_executive", "accounts_executive"}
    if role not in privileged:
        # Self-or-creator scope (also covers project_manager who created on behalf)
        q["$or"] = [
            {"employee_id": user.get("id")},
            {"created_by_id": user.get("id")},
            {"employee_code": user.get("employee_code")},
        ]
        # Also match by email (employee.email == user.email)
        if user.get("email"):
            emp = await db.employees.find_one({"email": user["email"]}, {"_id": 0, "id": 1})
            if emp:
                q["$or"].append({"employee_id": emp["id"]})
    if status:
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    if site:
        q["site"] = site
    if department:
        q["department"] = department
    if advance_type:
        q["advance_type"] = advance_type

    rows = await db.employee_advances.find(q, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    # Attach the pending approval step (if any) so the UI can show "Awaiting: HR"
    for r in rows:
        if r["status"] in {"submitted", "under_approval"} and r.get("approval_id"):
            step = await _approval_pending_step(r["id"])
            r["awaiting_role"] = step.get("role") if step else None
            r["awaiting_label"] = step.get("label") if step else None
    return rows


@router.get("/advances/{advance_id}")
async def get_advance(advance_id: str, user: dict = Depends(get_current_user)):
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    # Attach approval doc for timeline display
    if adv.get("approval_id"):
        appr = await db.approvals.find_one({"id": adv["approval_id"]}, {"_id": 0})
        adv["approval"] = appr
    # Attach recovery history (Phase C-ready)
    recoveries = await db.advance_recoveries.find({"advance_id": advance_id}, {"_id": 0}).sort("month", 1).to_list(60)
    adv["recoveries"] = recoveries
    return adv


@router.put("/advances/{advance_id}")
async def update_advance(advance_id: str, payload: AdvanceCreateIn, user: dict = Depends(get_current_user)):
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if adv["status"] not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail="only draft/rejected advances are editable")
    if user.get("id") != adv.get("created_by_id") and user.get("role") not in {"super_admin", "hr_executive"}:
        raise HTTPException(status_code=403, detail="not allowed")
    emi = round(payload.requested_amount / payload.installments, 2) if payload.installments else 0
    update = {
        "requested_amount": payload.requested_amount,
        "advance_type": payload.advance_type,
        "reason": payload.reason,
        "emergency": payload.emergency,
        "site": payload.site,
        "project": payload.project,
        "repayment_start_month": payload.repayment_start_month,
        "installments": payload.installments,
        "remaining_installments": payload.installments,
        "emi": emi,
        "remarks": payload.remarks,
        "attachments": payload.attachments or [],
        "updated_at": now_iso(),
    }
    await db.employee_advances.update_one({"id": advance_id}, {"$set": update})
    return {"ok": True}


@router.delete("/advances/{advance_id}")
async def delete_advance(advance_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "hr_executive"}:
        raise HTTPException(status_code=403, detail="not allowed")
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if adv["status"] in {"paid", "under_recovery", "closed"}:
        raise HTTPException(status_code=400, detail="cannot delete a paid/under-recovery/closed advance")
    await db.employee_advances.delete_one({"id": advance_id})
    if adv.get("approval_id"):
        await db.approvals.update_one({"id": adv["approval_id"]}, {"$set": {"status": "superseded"}})
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────
# Approval finalisation hook (called from approvals_router on each action)
# ────────────────────────────────────────────────────────────────────────
async def on_advance_approval_action(approval: dict) -> None:
    """Called by approvals_router.approval_action after apply_action persists.
    Updates the linked advance based on the new approval status."""
    if approval.get("type") != "employee_advance":
        return
    advance_id = approval.get("reference")
    if not advance_id:
        return
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        return
    new_status: Optional[str] = None  # noqa: F841 - placeholder for future emit hooks
    history_entry = {"at": now_iso(), "by_role": "approval_engine"}
    if approval.get("status") == "approved":
        # Approved amount defaults to requested unless approver modified it (via comment metadata)
        approved_amount = adv.get("approved_amount") or adv.get("requested_amount") or 0
        emi = round(approved_amount / adv["installments"], 2) if adv.get("installments") else 0
        await db.employee_advances.update_one(
            {"id": advance_id},
            {"$set": {
                "status": "approved",
                "approved_amount": approved_amount,
                "outstanding": approved_amount,
                "emi": emi,
                "approved_at": now_iso(),
            },
             "$push": {"status_history": {**history_entry, "from": adv["status"], "to": "approved",
                                           "comment": "All chain steps approved"}}},
        )
    elif approval.get("status") in ("rejected", "rejected_revision_required"):
        last = (approval.get("history") or [])[-1] if approval.get("history") else {}
        # Iter 50: advance bounces back to draft so the originator can resubmit
        # (kept as the legacy 'rejected' value too for back-compat consumers).
        await db.employee_advances.update_one(
            {"id": advance_id},
            {"$set": {"status": "rejected", "rejected_at": now_iso(),
                      "reject_reason": last.get("comment")},
             "$push": {"status_history": {**history_entry, "from": adv["status"], "to": "rejected",
                                           "comment": last.get("comment") or "Rejected"}}},
        )
    elif approval.get("status") == "in_progress":
        if adv["status"] not in {"under_approval"}:
            await db.employee_advances.update_one(
                {"id": advance_id},
                {"$set": {"status": "under_approval"},
                 "$push": {"status_history": {**history_entry, "from": adv["status"], "to": "under_approval",
                                               "comment": "Approval in progress"}}},
            )
    return None


# Allow approvers to modify the approved amount when they hit Approve
class ApprovalAmendIn(BaseModel):
    approved_amount: float = Field(gt=0)
    installments: int = Field(ge=1)


@router.post("/advances/{advance_id}/amend")
async def amend_advance_terms(advance_id: str, payload: ApprovalAmendIn, user: dict = Depends(get_current_user)):
    """Approver can modify approved amount & installments BEFORE final approval."""
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if adv["status"] not in {"submitted", "under_approval"}:
        raise HTTPException(status_code=400, detail="can only amend during approval")
    # Check user is in the chain
    appr = await db.approvals.find_one({"id": adv.get("approval_id")}, {"_id": 0})
    if not appr:
        raise HTTPException(status_code=404, detail="approval not found")
    step = current_step(appr) or {}
    if user.get("role") != step.get("role") and user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="only current step approver can amend")
    emi = round(payload.approved_amount / payload.installments, 2)
    await db.employee_advances.update_one(
        {"id": advance_id},
        {"$set": {"approved_amount": payload.approved_amount, "installments": payload.installments,
                  "remaining_installments": payload.installments, "emi": emi, "updated_at": now_iso()},
         "$push": {"status_history": {"at": now_iso(), "by": user.get("name") or user.get("email"),
                                       "by_role": user.get("role"),
                                       "from": adv["status"], "to": adv["status"],
                                       "comment": f"Terms amended → ₹{payload.approved_amount:,.0f} × {payload.installments}"}}},
    )
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────
# Phase B — Payment processing
# ────────────────────────────────────────────────────────────────────────
@router.post("/advances/{advance_id}/payment")
async def record_payment(advance_id: str, payload: AdvancePaymentIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in PAYMENT_ROLES:
        raise HTTPException(status_code=403, detail="payment processing restricted")
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if adv["status"] != "approved":
        raise HTTPException(status_code=400, detail=f"cannot pay from status '{adv['status']}' — must be 'approved'")
    if payload.paid_amount > adv["approved_amount"]:
        raise HTTPException(status_code=400, detail="paid amount exceeds approved amount")
    payment_doc = {
        "mode": payload.mode,
        "paid_amount": payload.paid_amount,
        "payment_date": payload.payment_date,
        "bank_name": payload.bank_name,
        "voucher_no": payload.voucher_no,
        "txn_no": payload.txn_no,
        "remarks": payload.remarks,
        "paid_by": user.get("name") or user.get("email"),
        "paid_by_id": user.get("id"),
        "paid_at": now_iso(),
    }
    new_status = "paid" if payload.paid_amount >= adv["approved_amount"] else "payment_pending"
    # After payment, employee owes us back what they received → outstanding = paid_amount
    outstanding = payload.paid_amount
    await db.employee_advances.update_one(
        {"id": advance_id},
        {"$set": {"status": new_status, "payment": payment_doc, "paid_amount": payload.paid_amount,
                  "outstanding": outstanding, "paid_at": now_iso()},
         "$push": {"status_history": {"at": now_iso(), "by": user.get("name") or user.get("email"),
                                       "by_role": user.get("role"), "from": adv["status"], "to": new_status,
                                       "comment": f"Paid ₹{payload.paid_amount:,.0f} via {payload.mode}"}}},
    )
    # Write a Journal Voucher row so it shows on the Accounts ledger
    je = {
        "id": new_id(),
        "je_number": payload.voucher_no or f"ADV-{adv['advance_no']}",
        "date": payload.payment_date,
        "type": "expense",
        "account": f"Employee Advance — {adv['employee_name']}",
        "amount": payload.paid_amount,
        "narration": f"Advance {adv['advance_no']} paid via {payload.mode} (Txn {payload.txn_no})",
        "cost_centre": adv.get("department") or "HR",
        "ref_advance_id": adv["id"],
        "ref_employee_id": adv["employee_id"],
        "created_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.journal_entries.insert_one(je)
    return {"ok": True, "status": new_status, "outstanding": outstanding, "voucher_no": je["je_number"]}


# ────────────────────────────────────────────────────────────────────────
# Dashboard summary (Phase A glance + drives Phase D widgets later)
# ────────────────────────────────────────────────────────────────────────
@router.get("/advances/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "director", "general_manager", "hr_executive",
                                "accounts_executive", "dept_head"}:
        raise HTTPException(status_code=403, detail="not allowed")
    pipeline_status = [{"$group": {"_id": "$status", "count": {"$sum": 1},
                                    "total_requested": {"$sum": "$requested_amount"},
                                    "total_approved": {"$sum": "$approved_amount"},
                                    "total_paid": {"$sum": "$paid_amount"},
                                    "total_outstanding": {"$sum": "$outstanding"}}}]
    by_status = await db.employee_advances.aggregate(pipeline_status).to_list(20)
    by_dept = await db.employee_advances.aggregate([
        {"$group": {"_id": "$department", "outstanding": {"$sum": "$outstanding"}, "count": {"$sum": 1}}},
        {"$sort": {"outstanding": -1}},
        {"$limit": 10},
    ]).to_list(10)
    totals = {
        "outstanding": sum((b.get("total_outstanding") or 0) for b in by_status),
        "requested": sum((b.get("total_requested") or 0) for b in by_status),
        "approved": sum((b.get("total_approved") or 0) for b in by_status),
        "paid": sum((b.get("total_paid") or 0) for b in by_status),
        "pending_approval": next((b["count"] for b in by_status if b["_id"] in {"submitted", "under_approval"}), 0),
    }
    return {
        "totals": totals,
        "by_status": [{"status": b["_id"], **{k: v for k, v in b.items() if k != "_id"}} for b in by_status],
        "by_department": [{"department": b["_id"], "outstanding": b["outstanding"], "count": b["count"]} for b in by_dept],
        "generated_at": now_iso(),
    }



# ════════════════════════════════════════════════════════════════════════
# Phase C — Recovery (skip / foreclose / settle + monthly run)
# ════════════════════════════════════════════════════════════════════════
HR_FINANCE_ROLES = {"super_admin", "hr_executive", "accounts_executive", "general_manager", "director"}


def _is_recoverable(adv: dict) -> bool:
    return adv["status"] in {"paid", "under_recovery"} and float(adv.get("outstanding", 0)) > 0


class RecoveryAdjustIn(BaseModel):
    amount: float = Field(gt=0)
    month: str        # YYYY-MM
    note: str = ""


@router.post("/advances/{advance_id}/recovery/skip")
async def skip_emi(advance_id: str, payload: RecoveryAdjustIn, user: dict = Depends(get_current_user)):
    """Mark this month's EMI as skipped — outstanding/remaining_installments unchanged
    but a 'skipped' row is written for audit."""
    if user.get("role") not in HR_FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if not _is_recoverable(adv):
        raise HTTPException(status_code=400, detail="advance is not in a recoverable state")
    rec = {
        "id": new_id(),
        "advance_id": advance_id,
        "employee_id": adv["employee_id"],
        "month": payload.month,
        "amount": 0,
        "type": "skipped",
        "note": payload.note or "Skipped by HR",
        "at": now_iso(),
        "by": user.get("name") or user.get("email"),
    }
    await db.advance_recoveries.insert_one(rec)
    rec.pop("_id", None)
    return rec


@router.post("/advances/{advance_id}/recovery/foreclose")
async def foreclose(advance_id: str, payload: RecoveryAdjustIn, user: dict = Depends(get_current_user)):
    """Employee pays the remaining outstanding in one shot. amount must equal outstanding."""
    if user.get("role") not in HR_FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if not _is_recoverable(adv):
        raise HTTPException(status_code=400, detail="advance is not in a recoverable state")
    if abs(payload.amount - float(adv["outstanding"])) > 0.01:
        raise HTTPException(status_code=400, detail=f"foreclose amount must equal outstanding (₹{adv['outstanding']:,.2f})")
    rec = {
        "id": new_id(),
        "advance_id": advance_id,
        "employee_id": adv["employee_id"],
        "month": payload.month,
        "amount": payload.amount,
        "type": "foreclosure",
        "note": payload.note or "Foreclosed by employee",
        "at": now_iso(),
        "by": user.get("name") or user.get("email"),
    }
    await db.advance_recoveries.insert_one(rec)
    new_recovered = float(adv.get("recovered_amount", 0)) + payload.amount
    await db.employee_advances.update_one(
        {"id": advance_id},
        {"$set": {"recovered_amount": new_recovered, "outstanding": 0,
                  "remaining_installments": 0, "status": "closed",
                  "closed_at": now_iso()},
         "$push": {"status_history": {"at": now_iso(), "by": user.get("name") or user.get("email"),
                                       "by_role": user.get("role"), "from": adv["status"], "to": "closed",
                                       "comment": f"Foreclosed ₹{payload.amount:,.0f}"}}},
    )
    rec.pop("_id", None)
    return rec


class SettleIn(BaseModel):
    waived_amount: float = Field(ge=0)
    month: str
    note: str = ""


@router.post("/advances/{advance_id}/recovery/settle")
async def settle(advance_id: str, payload: SettleIn, user: dict = Depends(get_current_user)):
    """One-time settlement — write off (waive) the remaining outstanding (GM/Director only)."""
    if user.get("role") not in {"super_admin", "general_manager", "director"}:
        raise HTTPException(status_code=403, detail="settlement requires GM/Director")
    adv = await db.employee_advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if not _is_recoverable(adv):
        raise HTTPException(status_code=400, detail="advance is not in a recoverable state")
    waived = min(payload.waived_amount, float(adv["outstanding"]))
    rec = {
        "id": new_id(),
        "advance_id": advance_id,
        "employee_id": adv["employee_id"],
        "month": payload.month,
        "amount": waived,
        "type": "settlement",
        "note": payload.note or "Written off",
        "at": now_iso(),
        "by": user.get("name") or user.get("email"),
    }
    await db.advance_recoveries.insert_one(rec)
    await db.employee_advances.update_one(
        {"id": advance_id},
        {"$set": {"outstanding": 0, "remaining_installments": 0, "status": "closed",
                  "closed_at": now_iso(), "settlement_waived": waived},
         "$push": {"status_history": {"at": now_iso(), "by": user.get("name") or user.get("email"),
                                       "by_role": user.get("role"), "from": adv["status"], "to": "closed",
                                       "comment": f"Settled — waived ₹{waived:,.0f}"}}},
    )
    rec.pop("_id", None)
    return rec


class RecoveryRunIn(BaseModel):
    month: str
    employee_ids: list[str] = []
    dry_run: bool = True


def _eligible_for_month(adv: dict, month: str) -> bool:
    if not _is_recoverable(adv):
        return False
    rs = (adv.get("repayment_start_month") or "")
    if rs and rs > month:
        return False
    return True


@router.post("/advances/recovery/run")
async def run_monthly_recovery(payload: RecoveryRunIn, user: dict = Depends(get_current_user)):
    """Compute proposed EMI deductions for a month.
    dry_run=True → proposals only; dry_run=False → commits and updates balances.
    Already-processed months are auto-skipped."""
    if user.get("role") not in HR_FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    if not payload.month or len(payload.month) != 7:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    query: dict = {"status": {"$in": ["paid", "under_recovery"]}, "outstanding": {"$gt": 0}}
    if payload.employee_ids:
        query["employee_id"] = {"$in": payload.employee_ids}

    proposals: list[dict] = []
    skipped: list[dict] = []
    async for adv in db.employee_advances.find(query, {"_id": 0}):
        if not _eligible_for_month(adv, payload.month):
            skipped.append({"advance_no": adv["advance_no"], "reason": "repayment not started"})
            continue
        already = await db.advance_recoveries.find_one(
            {"advance_id": adv["id"], "month": payload.month,
             "type": {"$in": ["emi", "skipped", "foreclosure", "settlement", "manual"]}}
        )
        if already:
            skipped.append({"advance_no": adv["advance_no"], "reason": f"already processed ({already.get('type')})"})
            continue
        emi = min(float(adv.get("emi", 0)), float(adv["outstanding"]))
        if emi <= 0:
            continue
        proposals.append({
            "advance_id": adv["id"],
            "advance_no": adv["advance_no"],
            "employee_id": adv["employee_id"],
            "employee_name": adv["employee_name"],
            "department": adv.get("department"),
            "outstanding_before": float(adv["outstanding"]),
            "emi": emi,
            "outstanding_after": float(adv["outstanding"]) - emi,
            "remaining_installments_after": max(0, int(adv.get("remaining_installments", 0)) - 1),
        })

    if payload.dry_run:
        return {"dry_run": True, "month": payload.month, "proposals": proposals,
                "skipped": skipped, "total_emi": sum(p["emi"] for p in proposals)}

    committed = 0
    for p in proposals:
        rec = {
            "id": new_id(), "advance_id": p["advance_id"], "employee_id": p["employee_id"],
            "month": payload.month, "amount": p["emi"], "type": "emi",
            "note": f"Auto EMI deduction for {payload.month}", "at": now_iso(),
            "by": user.get("name") or user.get("email"),
        }
        await db.advance_recoveries.insert_one(rec)
        adv = await db.employee_advances.find_one({"id": p["advance_id"]}, {"_id": 0})
        new_recovered = float(adv.get("recovered_amount", 0)) + p["emi"]
        new_outstanding = p["outstanding_after"]
        new_remaining = p["remaining_installments_after"]
        new_status = "closed" if new_outstanding <= 0.01 else "under_recovery"
        set_doc = {"recovered_amount": new_recovered, "outstanding": new_outstanding,
                   "remaining_installments": new_remaining, "status": new_status}
        if new_status == "closed":
            set_doc["closed_at"] = now_iso()
        await db.employee_advances.update_one(
            {"id": p["advance_id"]},
            {"$set": set_doc,
             "$push": {"status_history": {"at": now_iso(), "by": user.get("name") or user.get("email"),
                                           "by_role": user.get("role"), "from": adv["status"],
                                           "to": new_status, "comment": f"EMI ₹{p['emi']:,.0f} for {payload.month}"}}},
        )
        committed += 1
    return {"dry_run": False, "month": payload.month, "committed": committed,
            "skipped": skipped, "total_emi": sum(p["emi"] for p in proposals)}


class RecoveryOverrideIn(BaseModel):
    advance_id: str
    month: str
    amount: float = Field(ge=0)
    note: str = ""


@router.post("/advances/recovery/override")
async def override_recovery(payload: RecoveryOverrideIn, user: dict = Depends(get_current_user)):
    """Manual override of a single EMI deduction value."""
    if user.get("role") not in HR_FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    adv = await db.employee_advances.find_one({"id": payload.advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="advance not found")
    if payload.amount > float(adv["outstanding"]) + float(adv.get("recovered_amount", 0)) + 0.01:
        raise HTTPException(status_code=400, detail="override amount exceeds approved amount")
    existing = await db.advance_recoveries.find_one({"advance_id": payload.advance_id, "month": payload.month})
    delta_back = float(existing["amount"]) if existing and existing.get("type") in {"emi", "manual"} else 0
    if existing:
        await db.advance_recoveries.delete_one({"id": existing["id"]})
    rec = {
        "id": new_id(), "advance_id": payload.advance_id, "employee_id": adv["employee_id"],
        "month": payload.month, "amount": payload.amount, "type": "manual",
        "note": payload.note or "Manual override", "at": now_iso(),
        "by": user.get("name") or user.get("email"),
    }
    await db.advance_recoveries.insert_one(rec)
    new_recovered = float(adv.get("recovered_amount", 0)) - delta_back + payload.amount
    new_outstanding = float(adv["approved_amount"]) - new_recovered
    new_status = "closed" if new_outstanding <= 0.01 else "under_recovery"
    set_doc = {"recovered_amount": new_recovered, "outstanding": new_outstanding, "status": new_status}
    if new_status == "closed":
        set_doc["closed_at"] = now_iso()
    await db.employee_advances.update_one({"id": payload.advance_id}, {"$set": set_doc})
    rec.pop("_id", None)
    return rec


# ════════════════════════════════════════════════════════════════════════
# Phase D — Reports + Self-service
# ════════════════════════════════════════════════════════════════════════
@router.get("/advances/me/summary")
async def employee_self_summary(user: dict = Depends(get_current_user)):
    """Compact dashboard widget data for the logged-in employee."""
    emp = await db.employees.find_one({"email": user.get("email")}, {"_id": 0}) if user.get("email") else None
    if not emp:
        return {"linked": False, "active_advances": [], "outstanding_total": 0, "next_emi": None}
    advs = await db.employee_advances.find(
        {"employee_id": emp["id"], "status": {"$in": ["approved", "paid", "under_recovery", "payment_pending"]}},
        {"_id": 0},
    ).to_list(20)
    history = await db.employee_advances.find(
        {"employee_id": emp["id"]},
        {"_id": 0, "advance_no": 1, "advance_type": 1, "status": 1,
         "requested_amount": 1, "approved_amount": 1, "outstanding": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)
    outstanding_total = sum(float(a.get("outstanding", 0)) for a in advs)
    next_emi = None
    for a in advs:
        if a.get("emi") and float(a.get("outstanding", 0)) > 0:
            next_emi = {"advance_no": a["advance_no"], "emi": a["emi"], "month": a.get("repayment_start_month")}
            break
    return {
        "linked": True,
        "employee": {"id": emp["id"], "name": emp.get("name"), "code": emp.get("employee_id"),
                     "department": (emp.get("departments") or [None])[0]},
        "active_advances": advs, "history": history,
        "outstanding_total": outstanding_total, "next_emi": next_emi,
    }


@router.get("/advances/reports/outstanding")
async def report_outstanding(department: str = "", site: str = "", user: dict = Depends(get_current_user)):
    """Outstanding report (Finance)."""
    if user.get("role") not in HR_FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    q: dict = {"outstanding": {"$gt": 0}}
    if department:
        q["department"] = department
    if site:
        q["site"] = site
    rows = await db.employee_advances.find(q, {
        "_id": 0, "advance_no": 1, "employee_name": 1, "employee_code": 1, "department": 1, "site": 1,
        "advance_type": 1, "approved_amount": 1, "recovered_amount": 1, "outstanding": 1,
        "emi": 1, "remaining_installments": 1, "status": 1,
    }).sort("outstanding", -1).to_list(2000)
    return {"rows": rows, "total_outstanding": sum(r.get("outstanding", 0) for r in rows)}


@router.get("/advances/reports/monthly-recovery")
async def report_monthly_recovery(month: str, user: dict = Depends(get_current_user)):
    """Monthly recovery report by employee for a given YYYY-MM."""
    if user.get("role") not in HR_FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    rows = await db.advance_recoveries.aggregate([
        {"$match": {"month": month}},
        {"$group": {"_id": {"emp": "$employee_id", "adv": "$advance_id"},
                    "amount": {"$sum": "$amount"}, "types": {"$addToSet": "$type"}}},
        {"$sort": {"amount": -1}},
    ]).to_list(2000)
    out = []
    for r in rows:
        adv = await db.employee_advances.find_one({"id": r["_id"]["adv"]}, {"_id": 0})
        if adv:
            out.append({"advance_no": adv["advance_no"], "employee_name": adv["employee_name"],
                        "employee_code": adv.get("employee_code"), "department": adv.get("department"),
                        "amount": r["amount"], "types": r["types"]})
    return {"month": month, "rows": out, "total_recovered": sum(r["amount"] for r in out)}


@router.get("/advances/reports/aging")
async def report_aging(user: dict = Depends(get_current_user)):
    """Aging buckets for outstanding advances (0-30, 30-60, 60-90, 90+ days)."""
    if user.get("role") not in HR_FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="not allowed")
    from datetime import datetime
    now = datetime.now()
    buckets = {"0-30": 0, "30-60": 0, "60-90": 0, "90+": 0}
    async for a in db.employee_advances.find({"outstanding": {"$gt": 0}}, {"_id": 0}):
        ts = a.get("paid_at") or a.get("approved_at") or a.get("created_at")
        try:
            d = datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if ts else now
            d = d.replace(tzinfo=None)
        except Exception:
            d = now
        days = (now - d).days
        bk = "0-30" if days <= 30 else ("30-60" if days <= 60 else ("60-90" if days <= 90 else "90+"))
        buckets[bk] += float(a["outstanding"])
    return {"buckets": buckets, "total": sum(buckets.values())}


# ════════════════════════════════════════════════════════════════════════
# Phase E — Bulk historical import (CSV)
# ════════════════════════════════════════════════════════════════════════
import csv
import io
from fastapi import UploadFile, File


@router.post("/advances/bulk-import")
async def bulk_import(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """CSV import of historical advances. Required columns: employee_code, advance_type,
    approved_amount, recovered_amount (optional), installments, emi (optional),
    repayment_start_month. Imported rows bypass approval (they are real pre-existing balances)."""
    if user.get("role") not in {"super_admin", "hr_executive"}:
        raise HTTPException(status_code=403, detail="not allowed")
    raw = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    created: list[dict] = []
    errors: list[dict] = []
    for line_no, row in enumerate(reader, start=2):
        try:
            code = (row.get("employee_code") or "").strip()
            if not code:
                raise ValueError("missing employee_code")
            emp = await db.employees.find_one(
                {"$or": [{"employee_id": code}, {"emp_code": code}, {"email": code}]},
                {"_id": 0},
            )
            if not emp:
                raise ValueError(f"employee not found: {code}")
            approved = float(row.get("approved_amount") or 0)
            paid = float(row.get("paid_amount") or approved)
            recovered = float(row.get("recovered_amount") or 0)
            outstanding = float(row.get("outstanding") or max(0, paid - recovered))
            installments = int(row.get("installments") or 1)
            emi = float(row.get("emi") or (paid / installments if installments else 0))
            status = "closed" if outstanding <= 0.01 else "under_recovery"
            adv_no = await next_sequence("AD")
            dept_no = await next_dept_doc("advance")
            doc = {
                "id": new_id(), "advance_no": adv_no,
                "dept_doc_no": dept_no["dept_doc_no"],
                "ownership_department": dept_no["owner_dept"], "employee_id": emp["id"],
                "employee_code": emp.get("employee_id") or emp.get("emp_code"),
                "employee_name": emp.get("name"),
                "department": (emp.get("departments") or [None])[0] or emp.get("department"),
                "designation": emp.get("designation"), "site": emp.get("site"),
                "salary": emp.get("salary"), "joining_date": emp.get("joining_date"),
                "advance_type": (row.get("advance_type") or "Other").strip(),
                "advance_type_code": "OTH",
                "request_date": (row.get("request_date") or now_iso()[:10]),
                "requested_amount": approved, "approved_amount": approved, "paid_amount": paid,
                "recovered_amount": recovered, "outstanding": outstanding,
                "reason": row.get("reason") or "Migrated historical advance",
                "emergency": False, "remarks": row.get("remarks") or "Bulk import",
                "repayment_start_month": (row.get("repayment_start_month") or "").strip(),
                "installments": installments,
                "remaining_installments": max(0, installments - int(recovered / emi)) if emi > 0 else 0,
                "emi": emi, "attachments": [], "status": status, "on_behalf_of": True,
                "created_by_role": user.get("role"),
                "created_by": user.get("name") or user.get("email"),
                "created_by_id": user.get("id"), "created_at": now_iso(),
                "imported": True,
                "status_history": [{"at": now_iso(), "by": user.get("name") or user.get("email"),
                                     "by_role": user.get("role"), "from": None, "to": status,
                                     "comment": "Bulk-imported historical record"}],
            }
            await db.employee_advances.insert_one(doc)
            created.append({"advance_no": adv_no, "employee": emp["name"]})
        except Exception as e:
            errors.append({"line": line_no, "error": str(e)})
    return {"created": len(created), "errors": errors, "samples": created[:10]}
