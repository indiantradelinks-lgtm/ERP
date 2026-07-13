"""Projects & Operations · Phase 5 — Final Consolidation.

Adds the closing artifacts on top of Phases 1-4:

  • **RA Billing Support** — derives a billing-ready payload from APPROVED
        measurement_lines + APPROVED extra_works minus what has already been
        invoiced. Status workflow: draft → submitted_to_accounts → invoiced.
        New collection `ra_billing_drafts`.
  • **Closure Checklist** — 18-point checklist per project, auto-evaluating
        each item against Phase 1-4 data. Override workflow integrates with
        Phase-4 `project_exceptions`. New collection `project_closure_checklists`.
  • **Client Handover + JCC** — formal handover document + JobCompletionCertificate.
        New collections `client_handovers`, `job_completion_certificates`.
  • **Reports Center** — single Excel exporter pivoted by `report_type` over
        existing data (no duplication; reads from projects, dprs, measurements,
        issues, work_progress, billing, etc.).
  • **Audit Trail viewer** — read-only view over existing `audit_logs`.

Endpoints under `/api/proj-phase5`:

  RA Billing
    GET    /ra-billing/{project_id}/computed       — live preview from MS + extras
    GET    /ra-billing                             — list drafts
    POST   /ra-billing                             — create draft from computed
    POST   /ra-billing/{id}/submit                 — submit to accounts
    POST   /ra-billing/{id}/mark-invoiced          — accounts marks invoice raised

  Profitability  (thin reuse — points to Phase 4)
    GET    /profitability/{project_id}             — adds status enum + reason field

  Closure
    GET    /closure/{project_id}/checklist          — live checklist (auto-evaluated)
    POST   /closure/{project_id}/mark-item          — manually override one item
    POST   /closure/{project_id}/complete           — final closure (calls Phase 4 transition)

  Client Handover + JCC
    GET/POST/PUT  /handovers/client[/{id}]
    GET/POST  /handovers/jcc[/{id}]
    POST   /handovers/jcc/{id}/issue

  Reports Center
    GET    /reports/{report_type}                  — Excel download
    GET    /reports                                — list of 30 supported types

  Audit Trail
    GET    /audit/{project_id}                     — chronological log
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/proj-phase5", tags=["projects-ops-phase5"])


async def _project(pid: str) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, f"Project '{pid}' not found")
    return p


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 · RA Billing Support
# ═══════════════════════════════════════════════════════════════════════════

class RABillingIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    billing_period_from: Optional[str] = ""
    billing_period_to: Optional[str] = ""
    retention_pct: float = 5.0
    tds_pct: float = 0.0
    gst_pct: float = 18.0
    remarks: Optional[str] = ""


async def _compute_ra_billing(project_id: str) -> dict:
    """Aggregate certified MS lines + approved extras minus already-invoiced."""
    project = await _project(project_id)
    ms_lines = await db.measurement_lines.find(
        {"project_id": project_id, "client_certification_status": {"$in": ["certified", "partial"]}},
        {"_id": 0},
    ).to_list(5000)
    rows: List[dict] = []
    for ln in ms_lines:
        rate = float(ln.get("rate") or 0)
        qty = float(ln.get("certified_quantity") or ln.get("quantity") or 0)
        amount = round(qty * rate, 2)
        rows.append({
            "source": "measurement", "ms_line_id": ln.get("id"),
            "boq_line_id": ln.get("boq_line_id"),
            "description": ln.get("description"),
            "uom": ln.get("uom"),
            "certified_quantity": qty, "rate": rate, "amount": amount,
        })
    extras = await db.extra_works.find(
        {"project_id": project_id, "approval_status": "approved", "billing_status": "pending"},
        {"_id": 0},
    ).to_list(2000)
    for ew in extras:
        rows.append({
            "source": "extra_work", "extra_work_id": ew.get("id"),
            "extra_work_no": ew.get("extra_work_no"),
            "description": ew.get("work_description"),
            "uom": ew.get("uom"),
            "certified_quantity": float(ew.get("quantity") or 0),
            "rate": float(ew.get("rate") or 0),
            "amount": float(ew.get("estimated_value") or 0),
        })

    # already-billed
    prior_invoiced = 0.0
    if "sales_invoices" in await db.list_collection_names():
        inv_rows = await db.sales_invoices.find({"project_id": project_id}, {"_id": 0}).to_list(500)
        prior_invoiced = round(sum(float(i.get("total") or i.get("grand_total") or 0) for i in inv_rows), 2)

    # WO value cap check
    wo_value = 0.0
    ho = await db.project_handovers.find_one(
        {"project_id": project_id},
        {"_id": 0, "wo_value": 1, "total_value": 1},
    )
    if ho:
        wo_value = float(ho.get("wo_value") or ho.get("total_value") or 0)
    if not wo_value:
        boqs = await db.project_boqs.find({"project_id": project_id, "status": "approved"},
                                          {"_id": 0, "total": 1}).to_list(20)
        wo_value = round(sum(float(b.get("total") or 0) for b in boqs), 2)

    subtotal = round(sum(r["amount"] for r in rows), 2)
    current_billing = round(max(subtotal - prior_invoiced, 0), 2)
    balance_after = round(max(wo_value - subtotal, 0), 2)
    over_wo = subtotal > wo_value and wo_value > 0

    return {
        "project": {"id": project_id, "code": project.get("code"),
                     "name": project.get("name"),
                     "client": project.get("client_name") or project.get("client")},
        "work_order_value": wo_value,
        "previous_billed": prior_invoiced,
        "certified_subtotal": subtotal,
        "current_billing": current_billing,
        "balance_after_billing": balance_after,
        "exceeds_wo_value": over_wo,
        "needs_variation_approval": over_wo,
        "rows": rows,
    }


@router.get("/ra-billing/{project_id}/computed")
async def ra_computed(project_id: str,
                      user: dict = Depends(require_permission("projects", "read"))):
    return await _compute_ra_billing(project_id)


@router.get("/ra-billing")
async def list_ra(project_id: Optional[str] = None,
                  status: Optional[str] = None,
                  user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    return await db.ra_billing_drafts.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/ra-billing")
async def create_ra(payload: RABillingIn,
                    user: dict = Depends(require_permission("projects", "write"))):
    computed = await _compute_ra_billing(payload.project_id)
    n = await db.ra_billing_drafts.count_documents({})
    retention = round(computed["current_billing"] * payload.retention_pct / 100, 2)
    gst = round((computed["current_billing"] - retention) * payload.gst_pct / 100, 2)
    tds = round(computed["current_billing"] * payload.tds_pct / 100, 2)
    net_payable = round(computed["current_billing"] - retention - tds + gst, 2)

    doc = {
        "id": new_id(),
        "ra_no": f"RA-{computed['project']['code']}-{n + 1:04d}",
        "project_id": payload.project_id,
        "project_code": computed["project"]["code"],
        "client_name": computed["project"]["client"],
        "billing_period_from": payload.billing_period_from,
        "billing_period_to": payload.billing_period_to,
        "retention_pct": payload.retention_pct,
        "retention_amount": retention,
        "gst_pct": payload.gst_pct, "gst_amount": gst,
        "tds_pct": payload.tds_pct, "tds_amount": tds,
        "work_order_value": computed["work_order_value"],
        "previous_billed": computed["previous_billed"],
        "certified_subtotal": computed["certified_subtotal"],
        "current_billing": computed["current_billing"],
        "net_payable": net_payable,
        "balance_after_billing": computed["balance_after_billing"],
        "exceeds_wo_value": computed["exceeds_wo_value"],
        "rows": computed["rows"],
        "remarks": payload.remarks,
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    if computed["exceeds_wo_value"]:
        # check approved variation
        var_ok = await db.project_exceptions.find_one(
            {"project_id": payload.project_id, "status": "approved",
             "kind": {"$in": ["accounts", "finance"]}},
            {"_id": 0, "id": 1},
        )
        if not var_ok:
            raise HTTPException(400, "RA billing exceeds work-order value. Approved variation/exception required first.")
    await db.ra_billing_drafts.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.post("/ra-billing/{ra_id}/submit")
async def submit_ra(ra_id: str,
                    user: dict = Depends(require_permission("projects", "write"))):
    r = await db.ra_billing_drafts.find_one({"id": ra_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "RA draft not found")
    patch = {"status": "submitted_to_accounts", "submitted_at": now_iso(),
              "submitted_by": user.get("name") or user.get("email")}
    await db.ra_billing_drafts.update_one({"id": ra_id}, {"$set": patch})
    return await db.ra_billing_drafts.find_one({"id": ra_id}, {"_id": 0})


@router.post("/ra-billing/{ra_id}/mark-invoiced")
async def invoiced_ra(ra_id: str, invoice_ref: str = Query(...),
                      user: dict = Depends(require_permission("projects", "write"))):
    draft = await db.ra_billing_drafts.find_one({"id": ra_id}, {"_id": 0})
    if not draft:
        raise HTTPException(404, "RA draft not found")
    patch = {"status": "invoiced", "invoice_ref": invoice_ref, "invoiced_at": now_iso()}
    await db.ra_billing_drafts.update_one({"id": ra_id}, {"$set": patch})
    # flip extras billing_status
    extra_ids = [row["extra_work_id"] for row in draft.get("rows", []) if row.get("source") == "extra_work"]
    if extra_ids:
        await db.extra_works.update_many({"id": {"$in": extra_ids}}, {"$set": {"billing_status": "billed"}})
    return await db.ra_billing_drafts.find_one({"id": ra_id}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 · Profitability (wraps Phase-4 with status enum)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/profitability/{project_id}")
async def profitability(project_id: str,
                        user: dict = Depends(require_permission("projects", "read"))):
    # Reuse Phase-4 by composing what we need
    from routers.projects_ops_phase4_router import _accounts_summary, _finance_summary
    project = await _project(project_id)
    accts = await _accounts_summary(project_id, project)
    fin = await _finance_summary(project_id, project)
    margin = accts["margin_pct"]
    if accts["profit_or_loss"] < 0:
        status = "loss"
    elif margin < 5:
        status = "at_risk"
    elif margin < 12:
        status = "low_margin"
    else:
        status = "profitable"
    return {
        "project_id": project_id,
        "project_code": project.get("code"),
        "revenue": {
            "work_order_value": accts["work_order_value"],
            "invoice_raised": accts["invoice_raised"],
            "collection": accts["collection"],
            "outstanding": accts["outstanding_receivable"],
            "pending_billing": accts["pending_billing"],
        },
        "cost": {
            "total": accts["total_cost"],
            "budget": fin["approved_budget"],
            "variance": fin["variance"],
        },
        "profitability": {
            "gross_profit": accts["profit_or_loss"],
            "margin_pct": margin,
            "status": status,
            "health": fin["finance_health"],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Section 3 · Closure Checklist (18 items, auto-evaluated)
# ═══════════════════════════════════════════════════════════════════════════

CHECKLIST_ITEMS = [
    "work_completed",
    "dpr_completed",
    "measurement_completed",
    "client_certification_received",
    "ra_final_billing_completed",
    "payment_status_reviewed",
    "material_return_completed",
    "tools_ppe_cleared",
    "manpower_demobilized",
    "logistics_return_completed",
    "safety_closure_completed",
    "vendor_bills_reviewed",
    "site_expenses_submitted",
    "accounts_cost_reviewed",
    "finance_review_completed",
    "jcc_uploaded",
    "client_handover_completed",
    "closure_approval_completed",
]


async def _evaluate_checklist(project_id: str) -> List[dict]:
    """Auto-evaluate each item against existing data; allow manual override."""
    from routers.projects_ops_phase4_router import (
        _manpower_summary, _material_summary, _safety_summary, _accounts_summary,
    )
    project = await _project(project_id)
    manpower = await _manpower_summary(project_id)
    material = await _material_summary(project_id)
    safety = await _safety_summary(project_id)
    accts = await _accounts_summary(project_id, project)
    approved_dpr_count = await db.dprs.count_documents(
        {"project_id": project_id, "status": "approved"}
    )

    # any manual overrides
    manual = await db.project_closure_checklists.find_one({"project_id": project_id}, {"_id": 0})
    manual_map = {it["key"]: it for it in (manual or {}).get("items", [])}

    def auto(key: str) -> dict:
        if key == "work_completed":
            return _row(key, project.get("status") in ("completed", "closure_pending", "closed"))
        if key == "dpr_completed":
            # at least one approved DPR exists
            return _row(key, approved_dpr_count > 0)
        if key == "measurement_completed":
            return _row(key, accts["pending_billing"] == 0)
        if key == "client_certification_received":
            return _row(key, accts["pending_billing"] == 0)
        if key == "ra_final_billing_completed":
            return _row(key, accts["pending_billing"] == 0)
        if key == "payment_status_reviewed":
            return _row(key, accts["outstanding_receivable"] == 0, "info-only")
        if key == "material_return_completed":
            return _row(key, material["pending_returnable"] == 0)
        if key == "tools_ppe_cleared":
            return _row(key, material["pending_returnable"] == 0, "info-only")
        if key == "manpower_demobilized":
            return _row(key, manpower["deployed_count"] == 0)
        if key == "logistics_return_completed":
            return _row(key, True, "info-only")
        if key == "safety_closure_completed":
            return _row(key, safety["critical_safety_open"] == 0)
        if key == "vendor_bills_reviewed":
            return _row(key, True, "info-only")
        if key == "site_expenses_submitted":
            return _row(key, True, "info-only")
        if key == "accounts_cost_reviewed":
            return _row(key, True, "info-only")
        if key == "finance_review_completed":
            return _row(key, True, "info-only")
        if key == "jcc_uploaded":
            return _row(key, False, "manual")
        if key == "client_handover_completed":
            return _row(key, False, "manual")
        if key == "closure_approval_completed":
            return _row(key, project.get("status") == "closed", "auto-locked")
        return _row(key, False)

    out = []
    for key in CHECKLIST_ITEMS:
        item = auto(key)
        if key in manual_map:
            item["manual_overridden"] = True
            item["complete"] = manual_map[key].get("complete", item["complete"])
            item["remarks"] = manual_map[key].get("remarks", "")
        out.append(item)
    return out


def _row(key: str, complete: bool, hint: str = "auto") -> dict:
    return {"key": key, "label": key.replace("_", " ").title(), "complete": bool(complete), "hint": hint}


@router.get("/closure/{project_id}/checklist")
async def closure_checklist(project_id: str,
                            user: dict = Depends(require_permission("projects", "read"))):
    items = await _evaluate_checklist(project_id)
    completion = round(sum(1 for it in items if it["complete"]) / len(items) * 100, 1)
    return {"project_id": project_id, "items": items, "completion_pct": completion,
            "total": len(items), "done": sum(1 for it in items if it["complete"])}


class ChecklistItemPatch(BaseModel):
    key: str
    complete: bool
    remarks: Optional[str] = ""


@router.post("/closure/{project_id}/mark-item")
async def mark_item(project_id: str, payload: ChecklistItemPatch,
                    user: dict = Depends(require_permission("projects", "write"))):
    if payload.key not in CHECKLIST_ITEMS:
        raise HTTPException(400, f"Unknown checklist key '{payload.key}'")
    await _project(project_id)
    existing = await db.project_closure_checklists.find_one({"project_id": project_id}, {"_id": 0})
    items = (existing or {}).get("items", [])
    found = next((i for i in items if i["key"] == payload.key), None)
    if found:
        found.update({"complete": payload.complete, "remarks": payload.remarks or "",
                       "updated_at": now_iso(),
                       "updated_by": user.get("name") or user.get("email")})
    else:
        items.append({"key": payload.key, "complete": payload.complete,
                       "remarks": payload.remarks or "",
                       "updated_at": now_iso(),
                       "updated_by": user.get("name") or user.get("email")})
    if existing:
        await db.project_closure_checklists.update_one(
            {"project_id": project_id},
            {"$set": {"items": items, "updated_at": now_iso()}},
        )
    else:
        await db.project_closure_checklists.insert_one({
            "id": new_id(), "project_id": project_id, "items": items,
            "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
        })
    return await closure_checklist(project_id, user)


@router.post("/closure/{project_id}/complete")
async def complete_closure(project_id: str,
                           override_reason: Optional[str] = Query(None),
                           user: dict = Depends(require_permission("projects", "write"))):
    """Final closure — delegates to Phase 4 transition with full blocker check."""
    from routers.projects_ops_phase4_router import _compute_blockers
    blockers = await _compute_blockers(project_id, "closed")
    unresolved = [b for b in blockers if not b.get("override_approved")]
    if unresolved and (not override_reason or user.get("role") not in ("super_admin", "director", "general_manager")):
        raise HTTPException(403, {
            "message": "Closure blocked",
            "blockers": unresolved,
            "hint": "Provide override_reason= and user must be GM/Director/Super Admin",
        })
    # Auto-record an approved exception for traceability when override was used
    if unresolved and override_reason:
        await db.project_exceptions.insert_one({
            "id": new_id(),
            "project_id": project_id,
            "kind": "closure_override",
            "applies_to_transition": "closed",
            "title": "Closure override",
            "reason": override_reason,
            "blockers_snapshot": unresolved,
            "status": "approved",
            "approved_by": user.get("name") or user.get("email"),
            "approved_role": user.get("role"),
            "approved_at": now_iso(),
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
        })
    before = await db.projects.find_one({"id": project_id}, {"_id": 0})
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"status": "closed", "closed_at": now_iso(),
                  "closed_by": user.get("name") or user.get("email"),
                  "closure_override_reason": override_reason or ""}},
    )
    await audit(user=user, action="close", resource="projects",
                record_id=project_id, before=before, after={"status": "closed"})
    return {"ok": True, "project_id": project_id, "status": "closed"}


# ═══════════════════════════════════════════════════════════════════════════
# Section 4 · Client Handover + Job Completion Certificate
# ═══════════════════════════════════════════════════════════════════════════

class ClientHandoverIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    handover_date: Optional[str] = ""
    work_completed: Optional[str] = ""
    pending_points: Optional[str] = ""
    client_representative: Optional[str] = ""
    itl_representative: Optional[str] = ""
    documents_submitted: Optional[str] = ""
    final_acceptance_status: str = "pending"   # pending | accepted | conditional | rejected
    remarks: Optional[str] = ""
    attachment_ids: List[str] = []


class JCCIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    jcc_date: Optional[str] = ""
    issued_to: Optional[str] = ""
    scope_summary: Optional[str] = ""
    completion_date: Optional[str] = ""
    defect_liability_period: Optional[str] = ""
    remarks: Optional[str] = ""
    attachment_ids: List[str] = []


async def _next_no(collection, project_code: str, prefix: str) -> str:
    n = await collection.count_documents({})
    return f"{prefix}-{project_code or 'GEN'}-{n + 1:05d}"


@router.get("/handovers/client")
async def list_handovers(project_id: Optional[str] = None,
                          user: dict = Depends(require_permission("projects", "read"))):
    q = {"project_id": project_id} if project_id else {}
    return await db.client_handovers.find(q, {"_id": 0}).sort("handover_date", -1).to_list(500)


@router.post("/handovers/client")
async def create_handover(payload: ClientHandoverIn,
                          user: dict = Depends(require_permission("projects", "write"))):
    p = await _project(payload.project_id)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "handover_no": await _next_no(db.client_handovers, p.get("code"), "HO"),
        "project_code": p.get("code"),
        "client_name": p.get("client_name") or p.get("client"),
        "handover_date": payload.handover_date or now_iso()[:10],
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.client_handovers.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/handovers/client/{ho_id}")
async def update_handover(ho_id: str, payload: ClientHandoverIn,
                          user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.client_handovers.find_one({"id": ho_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Handover not found")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    await db.client_handovers.update_one({"id": ho_id}, {"$set": patch})
    return await db.client_handovers.find_one({"id": ho_id}, {"_id": 0})


@router.get("/handovers/jcc")
async def list_jcc(project_id: Optional[str] = None,
                   user: dict = Depends(require_permission("projects", "read"))):
    q = {"project_id": project_id} if project_id else {}
    return await db.job_completion_certificates.find(q, {"_id": 0}).sort("jcc_date", -1).to_list(500)


@router.post("/handovers/jcc")
async def create_jcc(payload: JCCIn,
                     user: dict = Depends(require_permission("projects", "write"))):
    p = await _project(payload.project_id)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "jcc_no": await _next_no(db.job_completion_certificates, p.get("code"), "JCC"),
        "project_code": p.get("code"),
        "client_name": p.get("client_name") or p.get("client"),
        "jcc_date": payload.jcc_date or now_iso()[:10],
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.job_completion_certificates.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.post("/handovers/jcc/{jcc_id}/issue")
async def issue_jcc(jcc_id: str,
                    user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head", "project_manager"):
        raise HTTPException(403, "Only PM / Dept Head / GM / Director can issue JCC")
    existing = await db.job_completion_certificates.find_one({"id": jcc_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "JCC not found")
    patch = {"status": "issued", "issued_by": user.get("name") or user.get("email"),
              "issued_at": now_iso()}
    await db.job_completion_certificates.update_one({"id": jcc_id}, {"$set": patch})
    return await db.job_completion_certificates.find_one({"id": jcc_id}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Section 5 · Reports Center (single Excel exporter pivoted by report_type)
# ═══════════════════════════════════════════════════════════════════════════

REPORT_CATALOG = {
    "project_master":       {"collection": "projects", "label": "Project Master"},
    "active_projects":      {"collection": "projects", "filter": {"status": "active"}, "label": "Active Projects"},
    "delayed_projects":     {"collection": "work_progress", "filter": {"status": "delayed"}, "label": "Delayed Projects"},
    "boq":                  {"collection": "project_boqs", "label": "BOQ"},
    "activity_progress":    {"collection": "project_activities", "label": "Activity Progress"},
    "dpr":                  {"collection": "dprs", "label": "Daily Progress Reports"},
    "measurements":         {"collection": "measurement_sheets", "label": "Measurement Sheets"},
    "certified_qty":        {"collection": "measurement_lines", "filter": {"client_certification_status": {"$in": ["certified", "partial"]}}, "label": "Certified Quantities"},
    "ra_billing":           {"collection": "ra_billing_drafts", "label": "RA Billing Support"},
    "extra_work":           {"collection": "extra_works", "label": "Extra Work"},
    "site_issues":          {"collection": "site_issues", "label": "Site Issues"},
    "delays":               {"collection": "delay_records", "label": "Delay Register"},
    "project_resources":    {"collection": "project_resources", "label": "Resource Plan"},
    "permits":              {"collection": "work_permits", "label": "Work Permits"},
    "client_handovers":     {"collection": "client_handovers", "label": "Client Handovers"},
    "jcc":                  {"collection": "job_completion_certificates", "label": "Job Completion Certificates"},
    "closure_checklists":   {"collection": "project_closure_checklists", "label": "Closure Checklists"},
    "audit_logs":           {"collection": "audit_logs", "label": "Project Audit Trail"},
    "exceptions":           {"collection": "project_exceptions", "label": "Exceptions / Overrides"},
    "alerts":               {"collection": "project_alerts", "label": "Project Alerts"},
}


@router.get("/reports")
async def list_reports(user: dict = Depends(require_permission("projects", "read"))):
    return [{"report_type": k, "label": v["label"]} for k, v in REPORT_CATALOG.items()]


@router.get("/reports/{report_type}")
async def export_report(report_type: str,
                        project_id: Optional[str] = None,
                        from_date: Optional[str] = None,
                        to_date: Optional[str] = None,
                        user: dict = Depends(require_permission("projects", "read"))):
    cfg = REPORT_CATALOG.get(report_type)
    if not cfg:
        raise HTTPException(400, f"Unknown report '{report_type}'. See /reports for catalog.")

    q: Dict[str, Any] = dict(cfg.get("filter") or {})
    if project_id:
        q["project_id"] = project_id
    if from_date or to_date:
        date_field = "created_at"
        rng: Dict[str, Any] = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date
        q[date_field] = rng

    collection = getattr(db, cfg["collection"])
    rows = await collection.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)

    wb = Workbook()
    ws = wb.active
    ws.title = report_type[:30]
    ws.append([cfg["label"], f"Generated {now_iso()}"])
    ws.append([])
    if rows:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        ws.append(keys)
        for r in rows:
            ws.append([_stringify(r.get(k)) for k in keys])
    else:
        ws.append(["(no data)"])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{report_type}_{date.today().isoformat()}.xlsx"'},
    )


def _stringify(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        try:
            import json
            return json.dumps(v, default=str)[:32000]
        except Exception:
            return str(v)
    return v


# ═══════════════════════════════════════════════════════════════════════════
# Section 6 · Audit Trail viewer (read from existing audit_logs)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/audit/{project_id}")
async def audit_for_project(project_id: str,
                            user: dict = Depends(require_permission("projects", "read"))):
    """Return all audit_logs entries that reference this project (any resource)."""
    if "audit_logs" not in await db.list_collection_names():
        return {"project_id": project_id, "count": 0, "rows": []}
    q = {
        "$or": [
            {"record_id": project_id},
            {"before.project_id": project_id},
            {"after.project_id": project_id},
            {"before.id": project_id},
            {"after.id": project_id},
        ]
    }
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("ts", -1).to_list(2000)
    return {"project_id": project_id, "count": len(rows), "rows": rows}
