"""Projects & Operations · Work Orders + Project Settings (Iter 95).

Work Order = the customer PO / LOI document that authorizes execution against
a Project. One Project can have multiple WOs (phased releases). Each WO has
its own scope, value, validity, and status.

Routes:
    /api/work-orders            — full CRUD
    /api/work-orders/by-project/{project_id}
    /api/proj-settings          — single-document KV settings (ops defaults)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id

router = APIRouter(prefix="", tags=["projects-ops-workorders"])


class WorkOrderIn(BaseModel):
    wo_no: str = Field(..., min_length=1, max_length=60, description="Customer PO/LOI number")
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    wo_date: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    scope: Optional[str] = ""
    value: float = 0.0
    currency: str = "INR"
    service_type_id: Optional[str] = None
    status: str = Field("draft", description="draft|received|active|completed|cancelled|hold")
    remarks: Optional[str] = ""
    attachments: List[str] = []
    # ── Sales-linked fields (Iter 96) ──
    quotation_id: Optional[str] = None
    quotation_no: Optional[str] = None
    approved_quotation: Optional[bool] = None
    boq: Optional[str] = ""
    payment_terms: Optional[str] = ""
    retention_clause: Optional[str] = ""
    retention_percentage: Optional[float] = None
    tds_applicability: Optional[str] = None  # applicable / not_applicable
    gst_applicability: Optional[str] = None  # applicable / not_applicable / exempt
    project_start_condition: Optional[str] = ""
    billing_milestone: Optional[str] = ""
    contractual_completion_date: Optional[str] = None
    # ── Contract-Handover linkage (Iter 126) ──
    # When a WO is created from a Contract Handover, we remember the source so
    # the UI can show a "From HO-xxx" badge and future work can auto-sync
    # common fields (scope, value, payment terms, etc.).
    source_handover_id: Optional[str] = None
    source_handover_no: Optional[str] = None


# ─────────────────────────── Work Orders ───────────────────────────
@router.get("/work-orders")
async def list_work_orders(project_id: Optional[str] = None, status: Optional[str] = None,
                            user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    rows = await db.work_orders.find(q, {"_id": 0}).sort("wo_date", -1).to_list(2000)
    return rows


@router.post("/work-orders")
async def create_work_order(payload: WorkOrderIn,
                             user: dict = Depends(require_permission("projects", "write"))):
    clash = await db.work_orders.find_one({"wo_no": payload.wo_no.strip()})
    if clash:
        raise HTTPException(409, f"WO number '{payload.wo_no}' already exists")
    # Resolve project label fields if project_id was passed
    doc = payload.model_dump()
    doc["wo_no"] = doc["wo_no"].strip()
    if doc.get("project_id") and not doc.get("project_code"):
        p = await db.projects.find_one({"id": doc["project_id"]}, {"_id": 0, "code": 1, "client": 1, "site": 1})
        if p:
            doc["project_code"] = p.get("code")
            doc["client_name"] = doc["client_name"] or p.get("client")
            doc["site_name"] = doc["site_name"] or p.get("site")
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    await db.work_orders.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/work-orders/{wid}")
async def update_work_order(wid: str, payload: WorkOrderIn,
                             user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.work_orders.find_one({"id": wid})
    if not existing:
        raise HTTPException(404, "Work Order not found")
    patch = payload.model_dump()
    patch["wo_no"] = patch["wo_no"].strip()
    if patch["wo_no"] != existing.get("wo_no"):
        clash = await db.work_orders.find_one({"wo_no": patch["wo_no"], "id": {"$ne": wid}})
        if clash:
            raise HTTPException(409, f"WO number '{patch['wo_no']}' already in use")
    # Iter 96 — revision history on value change (also flow into project budget)
    if patch.get("value") is not None and float(patch["value"]) != float(existing.get("value") or 0):
        rev = {
            "at": now_iso(),
            "by_id": user.get("id"),
            "by_name": user.get("name") or user.get("email"),
            "from_value": existing.get("value") or 0,
            "to_value": patch["value"],
            "reason": patch.get("remarks") or "",
        }
        history = list(existing.get("revision_history") or [])
        history.append(rev)
        patch["revision_history"] = history
        # Cascade new value into the linked Project's contract_value / budget
        if existing.get("project_id"):
            await db.projects.update_one(
                {"id": existing["project_id"]},
                {"$set": {
                    "work_order_value": patch["value"],
                    "contract_value": patch["value"],
                    "updated_at": now_iso(),
                    "updated_by": user.get("name") or user.get("email"),
                }},
            )
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.work_orders.update_one({"id": wid}, {"$set": patch})
    return await db.work_orders.find_one({"id": wid}, {"_id": 0})


@router.delete("/work-orders/{wid}")
async def delete_work_order(wid: str,
                             user: dict = Depends(require_permission("projects", "delete"))):
    await db.work_orders.delete_one({"id": wid})
    return {"ok": True}


@router.get("/work-orders/stats")
async def wo_stats(user: dict = Depends(require_permission("projects", "read"))):
    """KPI roll-up across all WOs for the Project Dashboard."""
    total = await db.work_orders.count_documents({})
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}, "value": {"$sum": "$value"}}},
    ]
    by_status = []
    async for r in db.work_orders.aggregate(pipeline):
        by_status.append({"status": r["_id"], "count": r["count"], "value": r["value"]})
    tot_value = sum(s["value"] for s in by_status)
    return {"total": total, "total_value": tot_value, "by_status": by_status}


# ─────────────────────────── Project Settings ───────────────────────────
class ProjectSettingsIn(BaseModel):
    default_ra_bill_frequency: str = "monthly"  # weekly|fortnightly|monthly|milestone|completion
    default_currency: str = "INR"
    auto_create_wo_from_order: bool = True
    require_pm_approval_for_wo: bool = False
    require_safety_officer: bool = True
    default_billing_milestone_count: int = 4
    project_code_prefix: str = "PRJ"
    notification_emails: List[str] = []
    auto_alert_overdue_bills_days: int = 7
    notes: Optional[str] = ""


@router.get("/proj-settings")
async def get_project_settings(user: dict = Depends(require_permission("projects", "read"))):
    doc = await db.proj_settings.find_one({"id": "global"}, {"_id": 0})
    if not doc:
        # First-time defaults
        doc = ProjectSettingsIn().model_dump()
        doc["id"] = "global"
        doc["created_at"] = now_iso()
        await db.proj_settings.insert_one(doc)
        doc.pop("_id", None)
    return doc


@router.put("/proj-settings")
async def update_project_settings(payload: ProjectSettingsIn,
                                    user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head"):
        raise HTTPException(403, "Only management can change project settings")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.proj_settings.update_one({"id": "global"}, {"$set": patch}, upsert=True)
    return await db.proj_settings.find_one({"id": "global"}, {"_id": 0})


# ─────────────────────────── Project Audit Trail ───────────────────────────
@router.get("/project-audit")
async def project_audit(project_id: Optional[str] = None, limit: int = 200,
                          user: dict = Depends(require_permission("projects", "read"))):
    """Surface audit_logs entries that touch project-related resources."""
    q: Dict[str, Any] = {
        "resource": {"$in": ["projects", "project_handovers", "work_orders",
                              "orders", "enquiries", "quotations"]}
    }
    if project_id:
        q["record_id"] = project_id
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    return rows
