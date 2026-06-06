"""Approval workflow endpoints — closed-loop revision cycle (Iter 50)."""
import asyncio
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, get_current_user, now_iso
from approval_engine import build_chain, apply_action, apply_resubmit, APPROVAL_CHAINS

router = APIRouter(tags=["approvals"])

# Statuses from which the originator can resubmit a revision.
RESUBMITTABLE = {"rejected_revision_required", "additional_info_required", "rejected"}


# ─── Department-scoped approval visibility (Iter 56) ────────────────────────
# Maps each approval `type` to the owning department (matches sequences.DEPT_DOC_MAP).
# When a user role isn't in GLOBAL_VISIBILITY, the GET /approvals + /approvals/lanes
# endpoints filter to approvals whose type belongs to one of the user's allowed depts
# OR where the user is currently the chain approver OR is the originator.
APPROVAL_TYPE_DEPT = {
    # HR
    "leave": "hr", "exit": "hr", "deployment": "hr", "overtime": "hr",
    "employee_advance": "hr", "department_move": "hr",
    "advance": "hr", "hr_letter": "hr", "onboarding": "hr",
    # Procurement
    "purchase_order": "procurement", "purchase_requisition": "procurement",
    "rfq": "procurement", "vendor": "procurement",
    # Store / Inventory
    "grn": "store", "material_outward": "store",
    "stock_adjustment": "store", "material_issue": "store",
    # Sales
    "enquiry": "sales", "quotation": "sales",
    "order": "sales", "sales_order": "sales", "client_onboarding": "sales",
    # Accounts / Finance
    "ra_bill": "accounts", "vendor_invoice": "accounts",
    "credit_note": "accounts", "debit_note": "accounts", "expense": "accounts",
    "payment_in": "finance", "payment_out": "finance",
    "journal_entry": "finance", "capex": "finance",
    # Operations / Projects
    "project": "operations", "dpr": "operations",
    "measurement": "operations", "joint_measurement": "operations",
    "project_handover": "operations", "resource_request": "operations",
    # Safety
    "safety_report": "safety", "incident": "safety", "ptw": "safety",
    "toolbox_talk": "safety",
    # Logistics
    "challan": "logistics", "vehicle_log": "logistics", "dispatch": "logistics",
}

GLOBAL_VISIBILITY_ROLES = {"super_admin", "director", "general_manager", "dept_head"}

ROLE_DEPT_SCOPE = {
    "hr_executive":       {"hr"},
    "purchase_officer":   {"procurement"},
    "store_incharge":     {"store", "procurement"},  # store handles inward from procurement
    "accounts_executive": {"accounts", "finance"},
    "sales_executive":    {"sales"},
    "safety_officer":     {"safety"},
    "project_manager":    {"operations", "hr"},      # project managers approve deployments (HR type)
    "project_coordinator":{"operations"},            # Iter 60
    "site_team":          {"operations"},            # Iter 60
    "admin_executive":    {"operations", "logistics"},  # Iter 60
    "supervisor":         {"operations"},
    "site_engineer":      {"operations"},
}


def _approval_visibility_filter(user: dict) -> Optional[dict]:
    """Return a Mongo filter dict for GET /approvals.
    Returns None when the user can see EVERYTHING (no filter).
    Returns {"id": "__never__"} when the role isn't recognised (defensive — sees nothing).
    Otherwise returns an $or that allows:
      • types belonging to one of the user's allowed departments
      • approvals where the user is the current chain approver (by role)
      • approvals they originated (created_by / requested_by matches their identity)
    """
    role = user.get("role")
    if role in GLOBAL_VISIBILITY_ROLES:
        return None  # see all
    allowed_depts = ROLE_DEPT_SCOPE.get(role)
    if not allowed_depts:
        return None  # unknown role → fall back to permission gate only (legacy behaviour)
    # Build the type filter from the dept set
    allowed_types = [t for t, d in APPROVAL_TYPE_DEPT.items() if d in allowed_depts]
    me_name = user.get("name") or ""
    me_email = user.get("email") or ""
    me_id = user.get("id") or ""
    return {"$or": [
        {"type": {"$in": allowed_types}},
        # Chain approver: any step in the chain has my role AND it's the current step.
        # We use a coarse-but-fast filter on chain.role + current_step using elemMatch w/
        # documented limitation: a full pipeline could pin index but $or here is fine for ≤2000 docs.
        {"chain.role": role},
        # Originator visibility
        {"created_by": {"$in": [me_id, me_name, me_email]}},
        {"requested_by": {"$in": [me_id, me_name, me_email]}},
        {"requested_by_id": me_id},
    ]}


# ─── Department-scoped GET /approvals (overrides crud_router generic) ──────
@router.get("/approvals")
async def list_approvals_scoped(user: dict = Depends(get_current_user)):
    """Return approvals the user can see. Department-scoped:
      • Global roles (super_admin/director/GM/dept_head) → all approvals
      • Other roles → only types in their department PLUS items they are
        a chain approver for OR originated.
    """
    filt = _approval_visibility_filter(user) or {}
    rows = await db.approvals.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows



class ApprovalAction(BaseModel):
    action: str  # approve | reject | request_info | comment
    comment: Optional[str] = None
    required_documents: Optional[List[str]] = None
    deadline: Optional[str] = None


class ResubmitIn(BaseModel):
    comment: Optional[str] = None
    file_ids: Optional[List[str]] = None
    payload_patch: Optional[dict] = None   # optional in-place edits to approval.payload


@router.post("/approvals/{approval_id}/action")
async def approval_action(approval_id: str, payload: ApprovalAction, user: dict = Depends(get_current_user)):
    approval = await db.approvals.find_one({"id": approval_id}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Not found")
    if not approval.get("chain"):
        approval["chain"] = await build_chain(approval.get("type") or "expense")
        approval["current_step"] = 0
        approval["history"] = []
    try:
        updated = apply_action(
            approval, payload.action, user, payload.comment,
            required_documents=payload.required_documents,
            deadline=payload.deadline,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    set_doc = {
        "chain": updated["chain"],
        "current_step": updated["current_step"],
        "history": updated["history"],
        "status": updated["status"],
        "updated_at": updated["updated_at"],
    }
    # Carry over the new bounce-back fields so dashboard widgets can filter on them.
    for k in ("rejected_at_step", "last_reject_reason", "last_reject_by", "last_reject_at",
              "info_required_at_step", "last_info_request"):
        if k in updated:
            set_doc[k] = updated[k]
    await db.approvals.update_one({"id": approval_id}, {"$set": set_doc})

    # Iter 62.1 — Quotation: keep the denormalised "pending at <step>" mirror
    # in sync on every action (approve-but-still-in-progress, reject, info_request).
    if updated.get("type") == "quotation" and updated.get("record_id"):
        chain = updated.get("chain") or []
        cidx = updated.get("current_step") or 0
        astatus = updated.get("status")
        q_set = {"updated_at": now_iso()}
        if astatus in {"rejected_revision_required", "rejected"}:
            rejected_idx = updated.get("rejected_at_step", cidx)
            try:
                rejected_step = chain[rejected_idx] if 0 <= rejected_idx < len(chain) else None
            except Exception:
                rejected_step = None
            q_set["approval_current_step_role"] = rejected_step.get("role") if rejected_step else None
            q_set["approval_current_step_label"] = f"Rejected at {rejected_step.get('label')}" if rejected_step else "Rejected"
            q_set["approval_current_step_index"] = rejected_idx
            q_set["approval_reject_reason"] = updated.get("last_reject_reason") or payload.comment
        elif astatus == "additional_info_required":
            try:
                cur = chain[cidx] if 0 <= cidx < len(chain) else None
            except Exception:
                cur = None
            q_set["approval_current_step_label"] = f"Info needed at {cur.get('label')}" if cur else "Info needed"
            q_set["approval_current_step_role"] = cur.get("role") if cur else None
            q_set["approval_current_step_index"] = cidx
        elif astatus in {"in_progress", "pending"}:
            try:
                cur = chain[cidx] if 0 <= cidx < len(chain) else None
            except Exception:
                cur = None
            q_set["approval_current_step_role"] = cur.get("role") if cur else None
            q_set["approval_current_step_label"] = cur.get("label") if cur else None
            q_set["approval_current_step_index"] = cidx
            q_set["approval_total_steps"] = len(chain)
        if len(q_set) > 1:
            await db.quotations.update_one({"id": updated["record_id"]}, {"$set": q_set})

    from routers.notifications_router import notify_approval_pending, notify_approval_decided
    from notification_service import notify_revision_required, notify_info_requested, notify_resubmitted
    from allocation_workflow import apply_department_move, apply_deployment, reject_deployment
    from routers.advance_router import on_advance_approval_action
    if updated.get("type") == "employee_advance":
        await on_advance_approval_action(updated)
    by = user.get("name") or user.get("email", "")

    if payload.action == "approve":
        if updated["status"] == "approved":
            if updated.get("type") == "material_issue" and updated.get("module") == "inventory" and updated.get("record_id"):
                await _post_outward_after_approval(updated["record_id"])
            if updated.get("type") == "department_move":
                await apply_department_move(updated)
            elif updated.get("type") == "deployment":
                await apply_deployment(updated)
            elif updated.get("type") == "client_onboarding" and updated.get("record_id"):
                await db.clients.update_one(
                    {"id": updated["record_id"]},
                    {"$set": {"status": "active", "approved_at": now_iso(),
                              "approval_id": updated["id"], "updated_at": now_iso()}},
                )
            elif updated.get("type") == "purchase_requisition" and updated.get("record_id"):
                await db.purchase_requisitions.update_one(
                    {"id": updated["record_id"]},
                    {"$set": {"status": "approved", "approved_at": now_iso(), "updated_at": now_iso()}},
                )
            elif updated.get("type") == "rfq" and updated.get("record_id"):
                await db.rfqs.update_one(
                    {"id": updated["record_id"]},
                    {"$set": {"status": "approved", "approved_at": now_iso(), "updated_at": now_iso()}},
                )
            elif updated.get("type") == "grn" and updated.get("record_id"):
                await db.grn.update_one(
                    {"id": updated["record_id"]},
                    {"$set": {"status": "approved", "approved_at": now_iso(), "updated_at": now_iso()}},
                )
            elif updated.get("type") == "vendor" and updated.get("record_id"):
                await db.vendors.update_one(
                    {"id": updated["record_id"]},
                    {"$set": {"status": "approved", "approved_at": now_iso(),
                              "approval_id": updated["id"], "reject_reason": None,
                              "updated_at": now_iso()}},
                )
            elif updated.get("type") == "resource_request" and updated.get("record_id"):
                await db.resource_requests.update_one(
                    {"id": updated["record_id"]},
                    {"$set": {"status": "approved", "approved_at": now_iso(),
                              "updated_at": now_iso()}},
                )
            elif updated.get("type") == "quotation" and updated.get("record_id"):
                await db.quotations.update_one(
                    {"id": updated["record_id"]},
                    {"$set": {"approval_status": "approved",
                              "approval_decided_at": now_iso(),
                              "approval_current_step_role": None,
                              "approval_current_step_label": "Approved",
                              "approval_current_step_index": len(updated.get("chain") or []),
                              "updated_at": now_iso()}},
                )
            asyncio.create_task(notify_approval_decided(updated, "approve", by))
        else:
            asyncio.create_task(notify_approval_pending(updated))
    elif payload.action == "reject":
        # Iter 50: rejection is NOT terminal — bounce the originating record back to
        # ``pending_revision`` so the originator can revise & resubmit. We still
        # invoke the legacy type-specific side-effects (e.g. reject_deployment writes
        # a withdrawn history entry; client_onboarding now goes pending_revision via
        # _mirror_downstream_record so we skip the duplicate update here).
        if updated.get("type") == "deployment":
            await reject_deployment(updated)
        await _mirror_downstream_record(updated, status="pending_revision",
                                       reason=payload.comment)
        await _push_inapp_to_originator(updated, {
            "type": "approval_rejected",
            "title": f"Revision required: {updated.get('title')}",
            "body": (payload.comment or "")[:120],
            "link": f"/app/approvals/my-revisions",
        })
        asyncio.create_task(notify_revision_required(updated, by, payload.comment or ""))
    elif payload.action == "request_info":
        await _mirror_downstream_record(updated, status="info_required",
                                       reason=payload.comment)
        await _push_inapp_to_originator(updated, {
            "type": "approval_info_requested",
            "title": f"Info needed: {updated.get('title')}",
            "body": (payload.comment or "")[:120],
            "link": f"/app/approvals/my-revisions",
        })
        asyncio.create_task(notify_info_requested(updated, by,
            payload.comment or "", payload.required_documents or [], payload.deadline))
    return updated


@router.post("/approvals/{approval_id}/resubmit")
async def approval_resubmit(approval_id: str, body: ResubmitIn, user: dict = Depends(get_current_user)):
    """Originator (or super_admin / hr_executive) resubmits a bounced approval."""
    approval = await db.approvals.find_one({"id": approval_id}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Not found")
    if approval.get("status") not in RESUBMITTABLE:
        raise HTTPException(status_code=400,
            detail=f"Cannot resubmit — current status is {approval.get('status')}")

    # Originator gate
    role = user.get("role")
    originator = (approval.get("created_by") or approval.get("requested_by") or "")
    is_creator = (originator == (user.get("name") or user.get("email")) or
                  originator == user.get("id") or originator == user.get("email"))
    if role not in {"super_admin", "hr_executive"} and not is_creator:
        raise HTTPException(status_code=403,
            detail="Only the originator can resubmit this approval")

    updated = await apply_resubmit(approval, user, body.comment, body.file_ids)

    # Optional payload patch (originator-driven corrections)
    if body.payload_patch:
        new_payload = {**(approval.get("payload") or {}), **body.payload_patch}
        updated["payload"] = new_payload

    set_doc = {
        "chain": updated["chain"],
        "current_step": updated["current_step"],
        "history": updated["history"],
        "status": updated["status"],
        "version": updated["version"],
        "resubmitted_at": updated["resubmitted_at"],
        "resubmitted_by": updated["resubmitted_by"],
        "resubmit_count": updated["resubmit_count"],
        "updated_at": updated["updated_at"],
    }
    if "payload" in updated:
        set_doc["payload"] = updated["payload"]
    if "attachments" in updated:
        set_doc["attachments"] = updated["attachments"]
    await db.approvals.update_one({"id": approval_id}, {"$set": set_doc})

    # Snapshot the new version for compare/audit (Phase 2 will surface this in UI)
    await db.approval_versions.insert_one({
        "approval_id": approval_id,
        "version": updated["version"],
        "snapshot": {k: v for k, v in updated.items() if k != "_id"},
        "saved_at": updated["updated_at"],
        "saved_by": user.get("name") or user.get("email"),
    })

    # Reset downstream record status back to "submitted" so it's re-evaluated.
    await _mirror_downstream_record(updated, status="submitted", reason=None)

    # Notify the next approver (in-app)
    chain = updated.get("chain") or []
    cidx = updated.get("current_step") or 0
    next_role = chain[cidx].get("role") if 0 <= cidx < len(chain) else None
    if next_role:
        await _push_inapp_for_role(next_role, {
            "type": "approval_resubmitted",
            "title": f"Resubmitted v{updated.get('version')}: {updated.get('title')}",
            "body": (body.comment or "")[:120],
            "link": f"/app/approvals?id={approval_id}",
        })

    from notification_service import notify_resubmitted
    by = user.get("name") or user.get("email", "")
    asyncio.create_task(notify_resubmitted(updated, by))
    updated.pop("_id", None)
    return updated


@router.get("/approvals/my-revisions")
async def my_revisions(user: dict = Depends(get_current_user)):
    """Approvals bounced back to ME (the originator) needing revision or extra info."""
    me_name = user.get("name") or ""
    me_email = user.get("email") or ""
    me_id = user.get("id") or ""
    q = {
        "status": {"$in": list(RESUBMITTABLE)},
        "$or": [
            {"created_by": me_name}, {"created_by": me_email}, {"created_by": me_id},
            {"requested_by": me_name}, {"requested_by": me_email}, {"requested_by": me_id},
        ],
    }
    if user.get("role") == "super_admin":
        q = {"status": {"$in": list(RESUBMITTABLE)}}
    rows = await db.approvals.find(q, {"_id": 0}).sort("updated_at", -1).limit(200).to_list(200)
    return rows


@router.get("/approvals/{approval_id}/versions")
async def list_versions(approval_id: str, user: dict = Depends(get_current_user)):
    rows = await db.approval_versions.find(
        {"approval_id": approval_id}, {"_id": 0}
    ).sort("saved_at", -1).to_list(50)
    return rows


@router.get("/approvals/{approval_id}/versions/compare")
async def compare_versions(approval_id: str, v1: str, v2: str,
                            user: dict = Depends(get_current_user)):
    """Return a flat diff between two saved versions. Each diff line:
    {key, v1, v2, changed: bool}. Useful for the side-by-side compare UI."""
    snap1 = await db.approval_versions.find_one(
        {"approval_id": approval_id, "version": v1}, {"_id": 0})
    snap2 = await db.approval_versions.find_one(
        {"approval_id": approval_id, "version": v2}, {"_id": 0})
    if not snap1 or not snap2:
        raise HTTPException(status_code=404, detail="version not found")

    DIFF_KEYS = {
        "status", "current_step", "version", "payload", "amount", "title",
        "resubmit_count", "last_reject_reason", "last_reject_by",
    }
    rows: list[dict] = []
    a = snap1.get("snapshot", {})
    b = snap2.get("snapshot", {})
    for k in sorted(DIFF_KEYS | set(a) | set(b)):
        if k.startswith("_") or k in {"chain", "history"}:
            continue
        va, vb = a.get(k), b.get(k)
        if va == vb and k not in DIFF_KEYS:
            continue
        rows.append({"key": k, "v1": va, "v2": vb, "changed": va != vb})
    # History tail diff (last 4 entries each)
    history_diff = {
        "v1_tail": (a.get("history") or [])[-4:],
        "v2_tail": (b.get("history") or [])[-4:],
    }
    return {
        "approval_id": approval_id,
        "v1": {"version": v1, "saved_at": snap1.get("saved_at"), "saved_by": snap1.get("saved_by")},
        "v2": {"version": v2, "saved_at": snap2.get("saved_at"), "saved_by": snap2.get("saved_by")},
        "rows": rows,
        "history_diff": history_diff,
    }


async def _push_inapp_to_originator(approval: dict, payload: dict) -> None:
    """Insert a notification doc keyed by the originator's user id."""
    from core import new_id
    cb = approval.get("created_by") or approval.get("requested_by") or ""
    # Look up the originator's user id (cb may be name/email/id)
    user_doc = await db.users.find_one(
        {"$or": [{"id": cb}, {"email": cb}, {"name": cb}]},
        {"_id": 0, "id": 1},
    )
    if not user_doc:
        return
    await db.notifications.insert_one({
        "id": new_id(),
        "user_id": user_doc["id"],
        **payload,
        "approval_id": approval.get("id"),
        "read": False,
        "at": now_iso(),
    })


async def _push_inapp_for_role(role: str, payload: dict) -> None:
    """Fan-out a notification to every user with the given role."""
    if not role:
        return
    from core import new_id
    users = await db.users.find({"role": role}, {"_id": 0, "id": 1}).to_list(50)
    for u in users:
        if u.get("id"):
            await db.notifications.insert_one({
                "id": new_id(),
                "user_id": u["id"],
                **payload,
                "read": False,
                "at": now_iso(),
            })


async def _mirror_downstream_record(approval: dict, *, status: str, reason: Optional[str]) -> None:
    """Push the new approval status to the originating record (PR, PO, client, etc.)
    so the requester sees an actionable badge on the record itself.

    NOTE: Types that already have a dedicated downstream hook
    (e.g. employee_advance via on_advance_approval_action, deployment via reject_deployment)
    are skipped here so the hook's specific status mapping wins.
    """
    record_id = approval.get("record_id") or approval.get("reference")
    atype = approval.get("type")
    if not record_id or not atype:
        return
    # Skip — handled by their own hooks
    if atype in {"employee_advance", "deployment", "department_move"}:
        return
    type_to_coll = {
        "purchase_requisition": "purchase_requisitions",
        "rfq": "rfqs",
        "grn": "grn",
        "client_onboarding": "clients",
        "material_issue": "inventory_transactions",
        "purchase_order": "purchase_orders",
        "expense": "journal_entries",
        "capex": "assets",
        "quotation": "quotations",
        "vendor": "vendors",
        "leave": "leave_requests",
    }
    coll = type_to_coll.get(atype)
    if not coll:
        return
    set_doc = {"status": status, "updated_at": now_iso()}
    if reason is not None:
        if status == "pending_revision":
            set_doc["reject_reason"] = reason
        elif status == "info_required":
            set_doc["info_request_reason"] = reason
    # Quotation special-case (Iter 62): we never want to overwrite the sales
    # pipeline status (draft/submitted/won/lost). Track the approval result on
    # the dedicated `approval_status` field instead.
    if atype == "quotation":
        approval_map = {"pending_revision": "rejected", "info_required": "info_required", "submitted": "pending"}
        set_doc = {
            "approval_status": approval_map.get(status, status),
            "approval_decided_at": now_iso(),
            "updated_at": now_iso(),
        }
        if reason is not None:
            set_doc["approval_reject_reason"] = reason
    await db[coll].update_one({"id": record_id}, {"$set": set_doc})


async def _post_outward_after_approval(txn_id: str) -> None:
    """Apply the held outward issue to inventory.quantity once it is fully approved."""
    txn = await db.inventory_transactions.find_one({"id": txn_id}, {"_id": 0})
    if not txn or txn.get("status") != "awaiting_approval":
        return
    item = await db.inventory.find_one({"id": txn["item_id"]}, {"_id": 0})
    if not item:
        return
    new_qty = float(item.get("quantity", 0) or 0) + float(txn.get("delta", 0) or 0)
    if new_qty < 0:
        await db.inventory_transactions.update_one(
            {"id": txn_id},
            {"$set": {"status": "failed_insufficient_stock", "updated_at": now_iso()}},
        )
        return
    await db.inventory.update_one({"id": txn["item_id"]}, {"$set": {"quantity": new_qty, "updated_at": now_iso()}})
    await db.inventory_transactions.update_one(
        {"id": txn_id},
        {"$set": {"status": "posted", "balance_after": new_qty, "posted_at": now_iso()}},
    )


@router.get("/approvals-config/chains")
async def approval_chains(user: dict = Depends(get_current_user)):
    return APPROVAL_CHAINS


# ─── Admin: approval-workflow settings ───────────────────────────────────
class ApprovalWorkflowConfig(BaseModel):
    restart_on_resubmit: bool = True
    mandatory_attachment_types: List[str] = []
    reject_remark_min_chars: int = 5
    # Phase 2 — escalation / reminder schedule
    escalation_days: int = 3                 # auto-escalate steps stuck > N days
    reminder_days: int = 1                   # daily reminder if no action > N days
    auto_reminders_enabled: bool = True


@router.get("/admin/approval-workflow-config")
async def get_approval_workflow_config(user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "director", "general_manager"}:
        raise HTTPException(status_code=403, detail="not allowed")
    doc = await db.settings.find_one({"_id": "approval_workflow"}, {"_id": 0})
    return doc or {
        "restart_on_resubmit": True, "mandatory_attachment_types": [],
        "reject_remark_min_chars": 5, "escalation_days": 3,
        "reminder_days": 1, "auto_reminders_enabled": True,
    }


@router.put("/admin/approval-workflow-config")
async def put_approval_workflow_config(payload: ApprovalWorkflowConfig,
                                        user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")
    doc = payload.model_dump()
    doc["updated_at"] = now_iso()
    doc["updated_by"] = user.get("name") or user.get("email")
    await db.settings.update_one({"_id": "approval_workflow"},
                                 {"$set": doc}, upsert=True)
    return {"ok": True, **doc}


# ─── Phase 2: mandatory-attachment enforcement helper ───────────────────
async def assert_attachments_for_type(approval_type: str, file_ids: List[str]) -> None:
    """Called by upstream routers (PR submit, client onboarding, etc.) right before
    creating an approval. Raises 400 when the type is on the mandatory-attachment
    list and no file_ids are supplied."""
    cfg = await db.settings.find_one({"_id": "approval_workflow"}, {"_id": 0}) or {}
    mandatory = set(cfg.get("mandatory_attachment_types", []))
    if approval_type in mandatory and not file_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Approval type '{approval_type}' requires at least one attachment "
                   f"(mandated by Admin → Approval Workflow Settings).",
        )


# ─── Phase 3: 5-lane My-Approvals dashboard ─────────────────────────────
@router.get("/approvals/lanes")
async def approval_lanes(user: dict = Depends(get_current_user)):
    """Buckets every approval the current user can see into 5 lanes for the
    Phase-3 dashboard. Super_admin sees all; everyone else sees only their
    role's pending step OR their own bounced-back items."""
    role = user.get("role")
    me_name = user.get("name") or ""
    me_email = user.get("email") or ""
    me_id = user.get("id") or ""

    # Pull all "open-ish" approvals (max 500 each lane — capped for speed)
    # Iter 56 — apply dept-scope filter so module dashboards only show relevant data
    base_filter = _approval_visibility_filter(user) or {}
    rows = await db.approvals.find(
        base_filter, {"_id": 0, "history": {"$slice": -3}}
    ).sort("updated_at", -1).limit(2000).to_list(2000)

    def mine_as_creator(r: dict) -> bool:
        cb = r.get("created_by") or r.get("requested_by") or ""
        return cb in {me_name, me_email, me_id}

    def mine_as_approver(r: dict) -> bool:
        chain = r.get("chain") or []
        idx = r.get("current_step") or 0
        step = chain[idx] if 0 <= idx < len(chain) else None
        return bool(step) and step.get("role") == role

    lanes: dict[str, list[dict]] = {
        "pending": [], "rejected": [], "revision_required": [],
        "additional_info": [], "resubmitted": [],
    }
    for r in rows:
        status = r.get("status")
        is_creator = mine_as_creator(r)
        is_approver = mine_as_approver(r)
        admin = role == "super_admin"

        # Pending lane → waiting on me (or any role for super_admin)
        if status in ("pending", "in_progress") and (admin or is_approver):
            lanes["pending"].append(r)

        # Bounce-back lanes → only the creator (or super_admin)
        if (admin or is_creator) and status == "rejected_revision_required":
            lanes["revision_required"].append(r)
        if (admin or is_creator) and status == "additional_info_required":
            lanes["additional_info"].append(r)
        if (admin or is_creator) and status == "rejected":   # legacy terminal rejects
            lanes["rejected"].append(r)

        # Resubmitted lane → freshly resubmitted, now pending again
        if r.get("resubmit_count", 0) > 0 and status in ("pending", "in_progress"):
            lanes["resubmitted"].append(r)

    return {
        "totals": {k: len(v) for k, v in lanes.items()},
        "lanes": lanes,
    }


# ─── Phase 3: Cycle-time + bottleneck analytics ─────────────────────────
@router.get("/approvals/analytics")
async def approval_analytics(days: int = 90, user: dict = Depends(get_current_user)):
    """Aggregate cycle-time and bottleneck stats across all approvals over the
    last `days` window."""
    if user.get("role") not in {"super_admin", "director", "general_manager",
                                  "hr_executive", "accounts_executive"}:
        raise HTTPException(status_code=403, detail="not allowed")
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    cursor = db.approvals.find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "type": 1, "status": 1, "created_at": 1,
         "updated_at": 1, "chain": 1, "history": 1, "resubmit_count": 1},
    )
    rows = await cursor.to_list(5000)

    def parse(s: str | None):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    by_type: dict[str, dict] = {}
    by_step_role: dict[str, dict] = {}
    cycle_days: list[float] = []
    rejection_count = 0
    info_request_count = 0
    resubmits = 0

    for r in rows:
        t = r.get("type") or "unknown"
        by_type.setdefault(t, {"total": 0, "approved": 0, "rejected": 0,
                                "open": 0, "avg_days": 0.0, "_durations": []})
        by_type[t]["total"] += 1
        if r.get("status") == "approved":
            by_type[t]["approved"] += 1
        elif r.get("status") in ("rejected", "rejected_revision_required"):
            by_type[t]["rejected"] += 1
        else:
            by_type[t]["open"] += 1

        ca = parse(r.get("created_at"))
        ua = parse(r.get("updated_at"))
        if ca and ua and r.get("status") == "approved":
            secs = (ua - ca).total_seconds()
            d = round(secs / 86400, 2)
            cycle_days.append(d)
            by_type[t]["_durations"].append(d)

        if r.get("resubmit_count", 0) > 0:
            resubmits += r.get("resubmit_count", 0)

        # Step-role bottleneck — time spent at each step from history
        hist = r.get("history") or []
        prev_at = parse(r.get("created_at"))
        for h in hist:
            at = parse(h.get("at"))
            role_ = h.get("step_role") or "unknown"
            if at and prev_at:
                spent = (at - prev_at).total_seconds() / 86400
                by_step_role.setdefault(role_, {"actions": 0, "total_days": 0.0})
                by_step_role[role_]["actions"] += 1
                by_step_role[role_]["total_days"] += spent
            prev_at = at
            action = h.get("action")
            if action == "reject":
                rejection_count += 1
            elif action == "request_info":
                info_request_count += 1

    # Compute averages + sort
    for t, data in by_type.items():
        durs = data.pop("_durations")
        data["avg_days"] = round(sum(durs) / len(durs), 2) if durs else 0.0

    for role_, data in by_step_role.items():
        data["avg_days_at_step"] = round(data["total_days"] / data["actions"], 2) \
            if data["actions"] else 0.0

    avg_cycle = round(sum(cycle_days) / len(cycle_days), 2) if cycle_days else 0.0
    cycle_days.sort()
    p50 = cycle_days[len(cycle_days) // 2] if cycle_days else 0
    p95 = cycle_days[int(len(cycle_days) * 0.95)] if cycle_days else 0

    bottleneck_roles = sorted(
        [{"role": k, **v} for k, v in by_step_role.items()],
        key=lambda x: x["avg_days_at_step"], reverse=True,
    )[:8]

    return {
        "window_days": days,
        "totals": {
            "approvals": len(rows),
            "avg_cycle_days": avg_cycle,
            "p50_cycle_days": p50,
            "p95_cycle_days": p95,
            "rejections": rejection_count,
            "info_requests": info_request_count,
            "resubmits": resubmits,
        },
        "by_type": [{"type": k, **v} for k, v in sorted(by_type.items())],
        "bottleneck_roles": bottleneck_roles,
    }


# ─── Phase 2/3: in-app notifications inbox (persistent) ─────────────────
@router.get("/notifications/mine")
async def my_notifications(unread_only: bool = False, limit: int = 50,
                            user: dict = Depends(get_current_user)):
    q: dict = {"user_id": user.get("id")}
    if unread_only:
        q["read"] = False
    rows = await db.notifications.find(q, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    unread = await db.notifications.count_documents({"user_id": user.get("id"), "read": False})
    return {"unread": unread, "items": rows}


@router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one(
        {"id": notif_id, "user_id": user.get("id")},
        {"$set": {"read": True, "read_at": now_iso()}},
    )
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    r = await db.notifications.update_many(
        {"user_id": user.get("id"), "read": False},
        {"$set": {"read": True, "read_at": now_iso()}},
    )
    return {"ok": True, "marked": r.modified_count}


@router.get("/approvals/inbox/mine")
async def my_inbox(user: dict = Depends(get_current_user)):
    """Approvals currently waiting on the logged-in user's role (super_admin sees all)."""
    role = user.get("role")
    rows = await db.approvals.find(
        {"status": {"$in": ["pending", "in_progress", None]}}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    out = []
    for r in rows:
        chain = r.get("chain") or []
        idx = r.get("current_step") or 0
        step = chain[idx] if 0 <= idx < len(chain) else None
        if not step:
            continue
        if role == "super_admin" or step.get("role") == role:
            r["_my_step"] = step
            out.append(r)
    return out


# ─── Approval record preview (Iter 57) ──────────────────────────────────────
RECORD_COLLECTION_MAP = {
    "vendor": "vendors",
    "purchase_requisition": "purchase_requisitions",
    "rfq": "rfqs",
    "purchase_order": "purchase_orders",
    "grn": "grn",
    "quotation": "quotations",
    "enquiry": "enquiries",
    "sales_order": "sales_orders",
    "client_onboarding": "clients",
    "leave": "leaves",
    "deployment": "deployments",
    "employee_advance": "employee_advances",
    "advance": "advances",
    "exit": "exits",
    "expense": "expenses",
    "vendor_invoice": "vendor_invoices",
    "ra_bill": "ra_bills",
    "credit_note": "credit_notes",
    "debit_note": "debit_notes",
    "incident": "safety_incidents",
    "ptw": "permits_to_work",
}

# Maps record_type → (parent_type used by files_router uploads, list of typed-doc array keys to flatten)
RECORD_FILE_HINTS = {
    "vendor": ("vendors", ["documents"]),
    "client_onboarding": ("clients", ["documents"]),
    "purchase_requisition": ("purchase_requisitions", ["attachments"]),
    "rfq": ("rfqs", ["attachments"]),
    "purchase_order": ("purchase_orders", ["attachments"]),
    "grn": ("grns", ["attachments"]),
    "quotation": ("quotations", ["attachments"]),
    "incident": ("safety", ["attachments"]),
}


@router.get("/approvals/{approval_id}/record-preview")
async def record_preview(approval_id: str, user: dict = Depends(get_current_user)):
    """Return underlying record snapshot + uploaded documents for approver review.

    Returns:
      { record: {...},
        documents: [ { id, name, type, file_id, expiry, uploaded_at, content_type, size, source } ],
        pdf_url: "/api/procurement/prs/{id}/pdf" | None
      }
    """
    approval = await db.approvals.find_one({"id": approval_id}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    rtype = approval.get("type")
    rec_id = approval.get("record_id")
    coll = RECORD_COLLECTION_MAP.get(rtype)
    record: Dict[str, Any] = {}
    if coll and rec_id:
        record = await db[coll].find_one({"id": rec_id}, {"_id": 0}) or {}

    documents: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    parent_type, typed_keys = RECORD_FILE_HINTS.get(rtype, (None, []))

    # 1) Typed doc arrays embedded in the record (e.g., vendor.documents)
    for key in typed_keys:
        for d in record.get(key) or []:
            fid = d.get("file_id")
            if not fid or fid in seen_ids:
                continue
            seen_ids.add(fid)
            file_row = await db.files.find_one({"id": fid, "is_deleted": False},
                                                {"_id": 0, "content_type": 1, "size": 1, "original_filename": 1})
            documents.append({
                "id": fid,
                "file_id": fid,
                "name": d.get("name") or (file_row or {}).get("original_filename"),
                "type": d.get("type"),
                "expiry": d.get("expiry"),
                "uploaded_at": d.get("uploaded_at"),
                "content_type": (file_row or {}).get("content_type"),
                "size": (file_row or {}).get("size"),
                "source": "typed",
            })

    # 2) All files uploaded to parent_type=<parent>, parent_id=<rec_id> (orphans + linked)
    if parent_type and rec_id:
        async for f in db.files.find(
            {"parent_type": parent_type, "parent_id": rec_id, "is_deleted": False},
            {"_id": 0, "id": 1, "original_filename": 1, "content_type": 1, "size": 1, "created_at": 1, "category": 1, "title": 1},
        ):
            if f["id"] in seen_ids:
                continue
            seen_ids.add(f["id"])
            documents.append({
                "id": f["id"], "file_id": f["id"],
                "name": f.get("title") or f.get("original_filename"),
                "type": f.get("category") or "Attachment",
                "expiry": None,
                "uploaded_at": f.get("created_at"),
                "content_type": f.get("content_type"),
                "size": f.get("size"),
                "source": "upload",
            })

    # 3) Resubmission attachments stored on the approval doc itself
    for att in approval.get("attachments") or []:
        fid = att.get("file_id") or att.get("id")
        if not fid or fid in seen_ids:
            continue
        seen_ids.add(fid)
        documents.append({
            "id": fid, "file_id": fid,
            "name": att.get("name") or att.get("filename"),
            "type": "Resubmission",
            "uploaded_at": att.get("uploaded_at"),
            "source": "resubmission",
        })

    # 4) Composed-record PDF URL for one-click full-document preview
    pdf_url = None
    pdf_map = {
        "purchase_requisition": f"/api/procurement/prs/{rec_id}/pdf",
        "rfq": f"/api/procurement/rfqs/{rec_id}/pdf",
        "purchase_order": f"/api/procurement/pos/{rec_id}/pdf",
        "grn": f"/api/procurement/grns/{rec_id}/pdf",
    }
    if rtype in pdf_map and rec_id:
        pdf_url = pdf_map[rtype]

    return {
        "type": rtype,
        "record_id": rec_id,
        "record": record,
        "documents": documents,
        "pdf_url": pdf_url,
    }



async def migrate_approvals_chain():
    """Backfill chain/history/current_step/version on legacy approval docs."""
    async for doc in db.approvals.find({"chain": {"$exists": False}}, {"_id": 0, "id": 1, "type": 1}):
        chain = await build_chain(doc.get("type") or "expense")
        await db.approvals.update_one(
            {"id": doc["id"]},
            {"$set": {"chain": chain, "current_step": 0, "history": [], "version": "1.0"}},
        )
    await db.approvals.update_many({"version": {"$exists": False}}, {"$set": {"version": "1.0"}})
