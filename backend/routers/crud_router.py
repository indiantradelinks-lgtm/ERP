"""Generic CRUD factory + module registration."""
import asyncio
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request

from core import db, require_permission, get_current_user, now_iso, new_id, logger
from approval_engine import build_chain, insert_approval, copy_approval_doc_fields
from audit import audit
from sequences import next_sequence
from scope import project_filter, department_filter
from india_compliance import validate_employee_compliance


# Auto-numbering map: collection → (prefix, field_name on the doc).
# Documents in these collections get a server-issued number on create if the
# client doesn't supply one. Each prefix yields e.g. "PTW-2026-0001".
AUTO_NUMBER = {
    "ptws": ("PTW", "ptw_no"),
    "safety_reports": ("INC", "incident_no"),
    "safety_trainings": ("TRN", "training_no"),
    "toolbox_talks": ("TBT", "talk_no"),
    "recruitment_requests": ("REQ", "req_no"),
    "candidates": ("CND", "candidate_no"),
    "deployments": ("DEP", "deployment_no"),
    "accommodations": ("ACC", "accom_no"),
    "overtime": ("OT", "ot_no"),
    "journal_entries": ("JV", "voucher_no"),
    "purchase_orders": ("PO", "po_no"),
    "departments": ("DPT", "code"),
    "employees": ("EMP", "employee_id"),
}


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# Collections that get project-scoped visibility for site-level roles.
PROJECT_SCOPED_COLLECTIONS = {
    "deployments", "safety_reports", "attendance", "ptws",
    "toolbox_talks", "ppe_issuance", "inventory_transactions", "projects",
    "purchase_orders", "assets",
    # Iter 47 — additional project-scoped collections
    "purchase_requisitions", "rfqs", "grns", "dprs", "measurements",
    "ra_bills", "vendor_invoices", "payments_in", "payments_out",
}

# Iter 47 — Department-scoped collections (dept_head + below see only own dept)
DEPT_SCOPED_COLLECTIONS = {"employees", "employee_advances", "hr_letters", "leave_requests", "overtime"}


async def _list_filter(collection: str, user: dict) -> dict:
    """Build a Mongo filter combining project/dept scope rules. Returns {} when
    the user has full visibility.
    """
    filt: dict = {}
    if collection in PROJECT_SCOPED_COLLECTIONS:
        proj_q = await project_filter(user)
        if proj_q is not None:
            if proj_q.get("_no_match_sentinel_"):
                return {"id": "__never_matches__"}
            filt.update(proj_q)
    if collection in DEPT_SCOPED_COLLECTIONS:
        dq = department_filter(user)
        if dq is not None:
            if dq.get("_no_match_sentinel_"):
                return {"id": "__never_matches__"}
            # Merge with $and to coexist with any existing filter
            existing = {**filt}
            filt = {"$and": [existing, dq]} if existing else dq
    return filt


router = APIRouter(tags=["crud"])

MODULES = [
    # ("clients", "clients"),  # Moved to dedicated clients_router with auto-code + hierarchy
    # ("vendors", "vendors"),  # Iter 55 — moved to dedicated vendors_router with status lifecycle + categories + addresses + bank + MSME + documents
    ("employees", "employees"),
    ("attendance", "attendance"),
    ("projects", "projects"),
    ("inventory", "inventory"),
    ("purchase-orders", "purchase_orders"),
    ("quotations", "quotations"),
    ("journal-entries", "journal_entries"),
    ("safety-reports", "safety_reports"),
    ("assets", "assets"),
    ("payroll", "payroll"),
    ("vehicles", "vehicles"),
    ("documents", "documents"),
    ("approvals", "approvals"),
    ("departments", "departments"),
    # Phase D — Safety pack
    ("ppe-issuance", "ppe_issuance"),
    ("ptws", "ptws"),
    ("safety-trainings", "safety_trainings"),
    ("toolbox-talks", "toolbox_talks"),
    # Phase E — HR pack
    ("recruitment-requests", "recruitment_requests"),
    ("candidates", "candidates"),
    ("deployments", "deployments"),
    ("accommodations", "accommodations"),
    ("overtime", "overtime"),
    # Phase F — Vendor evaluations (read via vendor_portal_router; CRUD for admins)
    ("vendor-evaluations", "vendor_evaluations"),
    ("vendor-invoices", "vendor_invoices"),
]


def make_crud(resource: str, collection: str, perm_key: str | None = None) -> None:
    perm = perm_key or collection

    @router.get(f"/{resource}")
    async def list_items(user: dict = Depends(require_permission(perm, "read"))):
        q = await _list_filter(collection, user)
        rows = await db[collection].find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
        return rows

    @router.post(f"/{resource}")
    async def create_item(payload: Dict[str, Any], request: Request, user: dict = Depends(require_permission(perm, "write"))):
        doc = dict(payload)
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        doc["created_by"] = user["id"]
        # Normalise multi-dept: keep `departments[]` and mirror first into legacy `department`
        if collection == "employees":
            depts = doc.get("departments") or ([doc["department"]] if doc.get("department") else [])
            depts = [d for d in depts if d]
            if depts:
                doc["departments"] = depts
                doc["department"] = depts[0]
            if "allow_multi_dept" not in doc:
                doc["allow_multi_dept"] = False
            # Indian statutory ID + employment-type validation
            errs = validate_employee_compliance(doc)
            if errs:
                raise HTTPException(status_code=400, detail=" · ".join(errs))
        # Phase 3 — gate deployments behind approval for non-HR / non-Ops roles.
        deployment_needs_approval = (
            collection == "deployments"
            and user.get("role") not in {"super_admin", "hr_executive", "general_manager"}
        )
        if deployment_needs_approval:
            # Force the deployment into pending_approval state regardless of
            # what the requester submitted, so it can't go live early.
            doc["status"] = "pending_approval"
        # Auto-assign a department-scoped number if the collection has a prefix
        # and the client didn't supply one (or supplied an empty/null value).
        if collection in AUTO_NUMBER:
            prefix, field = AUTO_NUMBER[collection]
            if not doc.get(field):
                doc[field] = await next_sequence(prefix)
        if perm == "approvals" and not doc.get("chain"):
            doc["chain"] = await build_chain(doc.get("type") or "expense")
            doc["current_step"] = 0
            doc["history"] = []
            doc["status"] = doc.get("status") or "pending"
        # Route approval creates through the universal documents-gate insert.
        if collection == "approvals":
            copy_approval_doc_fields(doc, payload)
            await insert_approval(doc)
        else:
            await db[collection].insert_one(doc)
        doc.pop("_id", None)
        await audit(user=user, action="create", resource=perm, record_id=doc["id"], after=doc, ip=_ip(request))
        # If this deployment needs approval, create a companion approval doc;
        # only log deployment_start history when no approval is required.
        if collection == "deployments" and doc.get("employee_id") and not deployment_needs_approval:
            try:
                await db.employee_history.insert_one({
                    "id": new_id(),
                    "employee_id": doc.get("employee_id") or "",
                    "employee_name": doc.get("employee", ""),
                    "action": "deployment_start",
                    "from": None,
                    "to": {"project": doc.get("project"), "site_role": doc.get("site_role") or doc.get("role"),
                           "start_date": doc.get("start_date"), "shift": doc.get("shift")},
                    "project": doc.get("project"),
                    "actor_id": user.get("id"),
                    "actor_name": user.get("name"),
                    "note": "",
                    "at": now_iso(),
                })
            except Exception as e:
                logger.warning(f"deployment_start history failed: {e}")
        if deployment_needs_approval:
            try:
                chain = await build_chain("deployment")
                approval = {
                    "id": new_id(),
                    "title": f"Deployment — {doc.get('employee','')} → {doc.get('project','')}",
                    "type": "deployment",
                    "reference": doc.get("deployment_no") or doc["id"],
                    "record_id": doc["id"],
                    "module": "deployments",
                    "requested_by": user.get("name") or user.get("email"),
                    "requester_role": user.get("role"),
                    "chain": chain,
                    "current_step": 0,
                    "history": [],
                    "status": "pending",
                    "metadata": {
                        "employee_id": doc.get("employee_id"),
                        "project": doc.get("project"),
                        "site_role": doc.get("site_role") or doc.get("role"),
                        "shift": doc.get("shift"),
                    },
                    "created_at": now_iso(),
                    "created_by": user.get("id"),
                }
                # Deployment payload may include the 4 docs fields; otherwise fall
                # back to N/A (supporting docs typically live on the employee record).
                copy_approval_doc_fields(approval, payload)
                if not approval.get("documents") and not approval.get("documents_not_required"):
                    approval["documents_not_required"] = True
                    approval["documents_not_required_reason"] = "Supporting docs available on employee record"
                await insert_approval(approval)
                from routers.notifications_router import notify_approval_pending
                asyncio.create_task(notify_approval_pending(approval))
            except Exception as e:
                logger.warning(f"deployment approval creation failed: {e}")
        if perm == "approvals":
            # Lazy import to avoid circular import
            from routers.notifications_router import notify_approval_pending
            asyncio.create_task(notify_approval_pending(doc))
        return doc

    @router.get(f"/{resource}/{{item_id}}")
    async def get_item(item_id: str, user: dict = Depends(require_permission(perm, "read"))):
        row = await db[collection].find_one({"id": item_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return row

    @router.put(f"/{resource}/{{item_id}}")
    async def update_item(item_id: str, payload: Dict[str, Any], request: Request, user: dict = Depends(require_permission(perm, "write"))):
        payload.pop("id", None)
        payload["updated_at"] = now_iso()
        payload["updated_by"] = user["id"]
        if collection == "employees":
            # Keep departments[] and legacy `department` in sync, and respect
            # allow_multi_dept on writes.
            depts = payload.get("departments")
            if depts is not None:
                depts = [d for d in depts if d]
                if depts:
                    payload["departments"] = depts
                    payload["department"] = depts[0]
            # Indian statutory ID + employment-type validation (only on supplied fields)
            errs = validate_employee_compliance(payload)
            if errs:
                raise HTTPException(status_code=400, detail=" · ".join(errs))
        before = await db[collection].find_one({"id": item_id}, {"_id": 0})
        if collection == "employees" and before is not None:
            new_depts = payload.get("departments")
            if new_depts is not None and not (payload.get("allow_multi_dept", before.get("allow_multi_dept"))) and len(new_depts) > 1:
                raise HTTPException(status_code=400, detail="This employee is not approved for multi-department assignment")
        # Phase 3 guard: prevent non-HR/Ops roles from flipping a
        # pending_approval deployment to active via PUT, bypassing the
        # approval workflow.
        if collection == "deployments" and before is not None and before.get("status") == "pending_approval":
            new_status = payload.get("status")
            if new_status and new_status != "pending_approval" and user.get("role") not in {"super_admin", "hr_executive", "general_manager"}:
                raise HTTPException(status_code=403, detail="This deployment is pending approval and cannot be changed directly")
        result = await db[collection].update_one({"id": item_id}, {"$set": payload})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = await db[collection].find_one({"id": item_id}, {"_id": 0})
        await audit(user=user, action="update", resource=perm, record_id=item_id, before=before, after=row, ip=_ip(request))
        return row

    @router.delete(f"/{resource}/{{item_id}}")
    async def delete_item(item_id: str, request: Request, user: dict = Depends(require_permission(perm, "delete"))):
        before = await db[collection].find_one({"id": item_id}, {"_id": 0})
        result = await db[collection].delete_one({"id": item_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        await audit(user=user, action="delete", resource=perm, record_id=item_id, before=before, ip=_ip(request))
        return {"ok": True}


for _r, _c in MODULES:
    make_crud(_r, _c)
