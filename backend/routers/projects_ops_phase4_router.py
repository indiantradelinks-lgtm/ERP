"""Projects & Operations · Phase 4 — Cross-Module Integration Hub.

This phase does NOT introduce new business data; it aggregates what other
modules already store and surfaces it through a unified Project Control
Center. Collections referenced (read-only unless noted):

  Existing               Used for
  ─────────              ─────────────────────────────────────────────
  projects               base
  project_handovers      Sales → Ops handover values
  project_boqs/_lines    BOQ value (planned revenue base)
  project_resources      planned manpower/material/tools/subcontract
  project_planning       readiness + approval state
  dprs, dpr_lines        execution log
  work_progress          actual progress
  measurement_sheets/_lines  certified qty + RA-billing feed
  site_issues            open / critical issues
  work_permits           safety clearance state
  extra_works            client-billable extras (Sales feed)
  manpower_allocations   HR deployment
  attendance             HR daily presence
  material_issues        Store issuance (graceful empty if absent)
  material_returns       Store return (graceful empty if absent)
  purchase_orders        Procurement spend commitment
  grn                    Actual material receipt
  vendor_bills           Procurement payables
  cost_centers           Category-wise budget commitments
  sales_invoices         Revenue raised
  customer_payments      Revenue collected

  New collections (introduced here, all lazy-created)
  ────────────────────────────────────────────────────
  project_exceptions     Manual exceptions / authorised overrides
  project_blockers       Computed snapshot of why a project cannot move state
  project_alerts         Inbox-style alerts (cost overrun, safety, finance)

Endpoints under `/api/proj-phase4`:

  Control Center
    GET    /control-center                          — portfolio-wide KPI grid
    GET    /control-center/{project_id}             — one project, all dimensions
    GET    /summary/{project_id}/{dimension}        — granular per-module summary
                                                       dimension ∈
                                                       manpower | material | safety |
                                                       logistics | procurement |
                                                       accounts | finance

  Exceptions / Blockers / Alerts
    GET    /exceptions                              — list (filters)
    POST   /exceptions                              — raise (authorised override)
    PUT    /exceptions/{id}                         — update
    POST   /exceptions/{id}/approve|reject

    GET    /blockers/{project_id}                   — current blockers (live)
    GET    /alerts                                  — list
    POST   /alerts/{id}/ack                         — acknowledge

  Status transition guards
    GET    /transition-check/{project_id}?to=active|completed|closure_pending|closed
    POST   /transition/{project_id}?to=…            — apply (passes through
                                                       to Phase 1 status update
                                                       if no blockers OR override)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/proj-phase4", tags=["projects-ops-phase4"])


# ─── helpers ──────────────────────────────────────────────────────────
async def _project(pid: str) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, f"Project '{pid}' not found")
    return p


def _today() -> str:
    return date.today().isoformat()


async def _coll_exists(name: str) -> bool:
    try:
        return name in await db.list_collection_names()
    except Exception:
        return True   # be permissive on driver shape


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 · Per-module Summaries (the "Project shows" lists from the spec)
# ═══════════════════════════════════════════════════════════════════════════

async def _manpower_summary(project_id: str) -> dict:
    today = _today()
    # planned: from project_resources where type=manpower
    res_rows = await db.project_resources.find(
        {"project_id": project_id, "resource_type": "manpower"}, {"_id": 0}
    ).to_list(500)
    planned_count = int(sum(float(r.get("count_required") or 0) for r in res_rows))
    planned_cost = round(sum(float(r.get("total_cost") or 0) for r in res_rows), 2)

    # deployed: manpower_allocations
    deployed: List[dict] = []
    deployed_present = absent = overtime_count = demobilised = 0
    pending_replacements = 0
    try:
        deployed = await db.manpower_allocations.find(
            {"project_id": project_id}, {"_id": 0}
        ).to_list(2000)
    except Exception:
        deployed = []
    active = [d for d in deployed if (not d.get("end_date")) or d.get("end_date", "") >= today]
    demobilised = len([d for d in deployed if d.get("status") in ("demobilized", "released")])
    pending_replacements = len([d for d in deployed if d.get("status") == "replacement_pending"])

    # attendance for today
    emp_ids = [d["employee_id"] for d in active if d.get("employee_id")]
    if emp_ids:
        try:
            present_rows = await db.attendance.find(
                {"employee_id": {"$in": emp_ids}, "date": today}, {"_id": 0}
            ).to_list(1000)
            deployed_present = sum(1 for r in present_rows
                                   if str(r.get("status", "")).lower().startswith("p"))
            absent = len(active) - deployed_present
            overtime_count = sum(1 for r in present_rows if float(r.get("ot_hours") or 0) > 0)
        except Exception:
            pass

    # skill-wise deployed (designation)
    skill_breakdown: Dict[str, int] = {}
    for d in active:
        k = d.get("designation") or d.get("role") or "Unspecified"
        skill_breakdown[k] = skill_breakdown.get(k, 0) + 1

    shortage = max(planned_count - len(active), 0)

    return {
        "planned_count": planned_count,
        "planned_cost": planned_cost,
        "deployed_count": len(active),
        "deployed_present_today": deployed_present,
        "absent_today": absent,
        "overtime_today": overtime_count,
        "demobilised_count": demobilised,
        "pending_replacement_count": pending_replacements,
        "shortage_count": shortage,
        "skill_breakdown": skill_breakdown,
    }


async def _material_summary(project_id: str) -> dict:
    # planned: project_resources where type=material
    res_rows = await db.project_resources.find(
        {"project_id": project_id, "resource_type": "material"}, {"_id": 0}
    ).to_list(2000)
    planned_qty = sum(float(r.get("quantity") or 0) for r in res_rows)
    planned_cost = round(sum(float(r.get("total_cost") or 0) for r in res_rows), 2)

    issued_count = consumed_count = returned_count = damaged_count = 0
    pending_returnable = 0
    material_cost = 0.0

    if await _coll_exists("material_issues"):
        issued = await db.material_issues.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
        issued_count = len(issued)
        material_cost += sum(float(x.get("total_value") or 0) for x in issued)
    if await _coll_exists("material_consumption"):
        consumed = await db.material_consumption.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
        consumed_count = len(consumed)
    if await _coll_exists("material_returns"):
        returns = await db.material_returns.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
        returned_count = len(returns)
        damaged_count = sum(1 for r in returns if r.get("damage_qty") or r.get("damaged"))
        pending_returnable = sum(1 for r in returns if r.get("status") in ("pending", "in_transit"))

    # purchase committed via cost_centers if present
    po_committed = 0.0
    try:
        po_rows = await db.purchase_orders.find({"project_id": project_id}, {"_id": 0}).to_list(1000)
        po_committed = round(sum(float(po.get("total") or 0) for po in po_rows), 2)
    except Exception:
        pass

    return {
        "planned_qty": round(planned_qty, 4),
        "planned_cost": planned_cost,
        "requested_count": 0,   # placeholder until MR module exists
        "issued_count": issued_count,
        "consumed_count": consumed_count,
        "returned_count": returned_count,
        "damaged_count": damaged_count,
        "pending_returnable": pending_returnable,
        "po_committed": po_committed,
        "material_cost": round(material_cost, 2),
    }


async def _safety_summary(project_id: str) -> dict:
    today = _today()
    horizon = (date.today() + timedelta(days=7)).isoformat()

    permits = await db.work_permits.find({"project_id": project_id}, {"_id": 0}).to_list(500) \
        if await _coll_exists("work_permits") else []
    permits_active = sum(1 for p in permits
                         if (not p.get("valid_to") or p["valid_to"] >= today) and p.get("status") != "revoked")
    permits_expired = sum(1 for p in permits if p.get("valid_to") and p["valid_to"] < today)
    permits_expiring = sum(1 for p in permits
                            if p.get("valid_to") and today <= p["valid_to"] <= horizon)

    safety_issues_open = await db.site_issues.count_documents(
        {"project_id": project_id, "category": "safety", "status": {"$in": ["open", "in_progress"]}}
    ) if await _coll_exists("site_issues") else 0
    critical_safety = await db.site_issues.count_documents(
        {"project_id": project_id, "category": "safety", "impact": "critical", "status": {"$ne": "closed"}}
    ) if await _coll_exists("site_issues") else 0

    obs_count = 0
    if await _coll_exists("safety_observations"):
        obs_count = await db.safety_observations.count_documents({"project_id": project_id})

    safety_cost = 0.0   # placeholder — would consume safety module collection

    return {
        "permits_active": permits_active,
        "permits_expiring_in_7d": permits_expiring,
        "permits_expired": permits_expired,
        "safety_issues_open": safety_issues_open,
        "critical_safety_open": critical_safety,
        "observations_logged": obs_count,
        "readiness": (
            "ready" if permits_active > 0 and permits_expired == 0 and critical_safety == 0
            else "not_ready"
        ),
        "safety_cost": safety_cost,
    }


async def _logistics_summary(project_id: str) -> dict:
    if not await _coll_exists("logistics_movements"):
        return {"pending_dispatches": 0, "in_transit": 0, "delivered": 0, "transit_damage": 0,
                "logistics_cost": 0.0}
    rows = await db.logistics_movements.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    pending = sum(1 for r in rows if r.get("status") in ("pending", "scheduled"))
    in_transit = sum(1 for r in rows if r.get("status") == "in_transit")
    delivered = sum(1 for r in rows if r.get("status") in ("delivered", "received"))
    damage = sum(1 for r in rows if (r.get("transit_damage") or r.get("damage_qty")))
    cost = round(sum(float(r.get("freight_cost") or 0) for r in rows), 2)
    return {"pending_dispatches": pending, "in_transit": in_transit, "delivered": delivered,
            "transit_damage": damage, "logistics_cost": cost}


async def _procurement_summary(project_id: str) -> dict:
    po_pending = po_total_value = 0
    po_count = 0
    if await _coll_exists("purchase_orders"):
        po_rows = await db.purchase_orders.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
        po_count = len(po_rows)
        po_pending = sum(1 for r in po_rows if r.get("status") in ("draft", "submitted", "approved"))
        po_total_value = round(sum(float(r.get("total") or 0) for r in po_rows), 2)

    bills = []
    if await _coll_exists("vendor_bills"):
        bills = await db.vendor_bills.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    vendor_cost = round(sum(float(b.get("total") or b.get("amount") or 0) for b in bills
                            if b.get("status") not in ("draft", "rejected", "cancelled")), 2)
    bills_pending = sum(1 for b in bills if b.get("status") in ("draft", "verified", "approved"))

    # subcontractor — resources of type=subcontract
    subcon_rows = await db.project_resources.find(
        {"project_id": project_id, "resource_type": "subcontract"}, {"_id": 0}
    ).to_list(500)
    subcon_value = round(sum(float(r.get("total_cost") or r.get("value") or 0) for r in subcon_rows), 2)

    return {
        "purchase_orders_count": po_count,
        "purchase_orders_pending": po_pending,
        "purchase_orders_value": po_total_value,
        "vendor_bills_count": len(bills),
        "vendor_bills_pending": bills_pending,
        "vendor_cost": vendor_cost,
        "subcontract_count": len(subcon_rows),
        "subcontract_value": subcon_value,
    }


async def _accounts_summary(project_id: str, project: dict) -> dict:
    # Work-Order value (from handovers / sales)
    wo_value = 0.0
    try:
        ho = await db.project_handovers.find_one(
            {"project_id": project_id}, {"_id": 0, "wo_value": 1, "total_value": 1},
        )
        if ho:
            wo_value = float(ho.get("wo_value") or ho.get("total_value") or 0)
    except Exception:
        pass
    if not wo_value:
        boqs = await db.project_boqs.find({"project_id": project_id, "status": "approved"},
                                            {"_id": 0, "total": 1}).to_list(50)
        wo_value = round(sum(float(b.get("total") or 0) for b in boqs), 2)

    invoices = []
    if await _coll_exists("sales_invoices"):
        invoices = await db.sales_invoices.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    invoice_raised = round(sum(float(i.get("total") or i.get("grand_total") or 0) for i in invoices), 2)

    payments = []
    if await _coll_exists("customer_payments"):
        payments = await db.customer_payments.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    collection = round(sum(float(p.get("amount") or 0) for p in payments), 2)
    outstanding = round(max(invoice_raised - collection, 0), 2)

    # pending billing — certified measurements not yet invoiced (best-effort)
    ms_lines = await db.measurement_lines.find(
        {"project_id": project_id, "client_certification_status": "certified"},
        {"_id": 0, "certified_quantity": 1, "rate": 1},
    ).to_list(2000) if await _coll_exists("measurement_lines") else []
    certified_value = round(sum(float(line.get("certified_quantity") or 0) * float(line.get("rate") or 0) for line in ms_lines), 2)
    pending_billing = round(max(certified_value - invoice_raised, 0), 2)

    # Cost roll-up across modules
    manpower = await _manpower_summary(project_id)
    material = await _material_summary(project_id)
    logistics = await _logistics_summary(project_id)
    procurement = await _procurement_summary(project_id)
    safety = await _safety_summary(project_id)
    total_cost = round(
        manpower["planned_cost"] + material["material_cost"]
        + logistics["logistics_cost"] + procurement["vendor_cost"]
        + procurement["subcontract_value"] + safety["safety_cost"], 2
    )
    profit = round(invoice_raised - total_cost, 2)

    return {
        "work_order_value": wo_value,
        "invoice_raised": invoice_raised,
        "collection": collection,
        "outstanding_receivable": outstanding,
        "pending_billing": pending_billing,
        "total_cost": total_cost,
        "profit_or_loss": profit,
        "margin_pct": round((profit / invoice_raised * 100), 2) if invoice_raised else 0.0,
    }


async def _finance_summary(project_id: str, project: dict) -> dict:
    # budget — try project_budgets, else use BOQ approved total
    approved_budget = 0.0
    try:
        bud = await db.project_budgets.find_one({"project_id": project_id}, {"_id": 0})
        if bud:
            approved_budget = float(bud.get("total_budget") or 0)
    except Exception:
        pass
    if not approved_budget:
        approved_budget = float(project.get("budget_amount") or 0)

    accounts = await _accounts_summary(project_id, project)
    actual_cost = accounts["total_cost"]
    variance = round(approved_budget - actual_cost, 2)
    variance_pct = round((variance / approved_budget * 100), 2) if approved_budget else 0.0

    finance_health = "healthy"
    if approved_budget and actual_cost > approved_budget:
        finance_health = "over_budget"
    elif approved_budget and actual_cost > approved_budget * 0.9:
        finance_health = "approaching_limit"

    pending_fin_approvals = await db.project_exceptions.count_documents(
        {"project_id": project_id, "kind": "finance", "status": "pending"}
    )

    return {
        "approved_budget": approved_budget,
        "actual_cost": actual_cost,
        "variance": variance,
        "variance_pct": variance_pct,
        "cash_flow_requirement": max(actual_cost - accounts["collection"], 0),
        "pending_financial_approvals": pending_fin_approvals,
        "finance_health": finance_health,
    }


DIMENSIONS = {
    "manpower": _manpower_summary, "material": _material_summary,
    "safety": _safety_summary, "logistics": _logistics_summary,
    "procurement": _procurement_summary,
    # accounts/finance need project doc
}


@router.get("/summary/{project_id}/{dimension}")
async def per_module_summary(project_id: str, dimension: str,
                             user: dict = Depends(require_permission("projects", "read"))):
    project = await _project(project_id)
    if dimension == "accounts":
        return await _accounts_summary(project_id, project)
    if dimension == "finance":
        return await _finance_summary(project_id, project)
    fn = DIMENSIONS.get(dimension)
    if not fn:
        raise HTTPException(400, "Unknown dimension. Allowed: manpower|material|safety|logistics|procurement|accounts|finance")
    return await fn(project_id)


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 · Blockers (computed live) + Exceptions (manual overrides)
# ═══════════════════════════════════════════════════════════════════════════

ExceptionKind = Literal["manpower", "material", "safety", "logistics", "procurement", "accounts", "finance", "other"]
ExceptionStatus = Literal["pending", "approved", "rejected", "expired"]


class ExceptionIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    kind: ExceptionKind = "other"
    title: str = Field(..., min_length=2, max_length=200)
    reason: str = Field(..., min_length=2)
    applies_to_transition: Optional[str] = ""    # active|completed|closure_pending|closed
    valid_until: Optional[str] = ""


@router.get("/exceptions")
async def list_exceptions(project_id: Optional[str] = None,
                          status: Optional[str] = None,
                          kind: Optional[str] = None,
                          user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    if kind:
        q["kind"] = kind
    return await db.project_exceptions.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/exceptions")
async def create_exception(payload: ExceptionIn,
                           user: dict = Depends(require_permission("projects", "write"))):
    await _project(payload.project_id)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "status": "pending",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.project_exceptions.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/exceptions/{ex_id}")
async def update_exception(ex_id: str, payload: ExceptionIn,
                           user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.project_exceptions.find_one({"id": ex_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Exception not found")
    patch = payload.model_dump()
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    await db.project_exceptions.update_one({"id": ex_id}, {"$set": patch})
    return await db.project_exceptions.find_one({"id": ex_id}, {"_id": 0})


@router.post("/exceptions/{ex_id}/approve")
async def approve_exception(ex_id: str,
                            user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager"):
        raise HTTPException(403, "Only GM / Director / Super Admin can approve an exception override")
    ex = await db.project_exceptions.find_one({"id": ex_id}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Exception not found")
    patch = {"status": "approved", "approved_by": user.get("name") or user.get("email"), "approved_at": now_iso(), "updated_at": now_iso()}
    await db.project_exceptions.update_one({"id": ex_id}, {"$set": patch})
    await audit(user=user, action="approve", resource="project_exceptions", record_id=ex_id, before=ex, after=patch, ip="phase4")
    return await db.project_exceptions.find_one({"id": ex_id}, {"_id": 0})


@router.post("/exceptions/{ex_id}/reject")
async def reject_exception(ex_id: str, reason: str = Query(...),
                           user: dict = Depends(require_permission("projects", "write"))):
    ex = await db.project_exceptions.find_one({"id": ex_id}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Exception not found")
    patch = {"status": "rejected", "rejection_reason": reason, "rejected_by": user.get("name") or user.get("email"), "updated_at": now_iso()}
    await db.project_exceptions.update_one({"id": ex_id}, {"$set": patch})
    return await db.project_exceptions.find_one({"id": ex_id}, {"_id": 0})


async def _has_active_override(project_id: str, transition: str) -> bool:
    today = _today()
    q = {
        "project_id": project_id,
        "status": "approved",
        "$or": [
            {"applies_to_transition": transition},
            {"applies_to_transition": ""},
            {"applies_to_transition": None},
        ],
        "$and": [{"$or": [{"valid_until": ""}, {"valid_until": {"$gte": today}}, {"valid_until": None}]}],
    }
    return bool(await db.project_exceptions.find_one(q, {"_id": 0, "id": 1}))


async def _compute_blockers(project_id: str, transition: str) -> List[dict]:
    """Compute live blocker list for a target transition. Returns [] when clear."""
    project = await _project(project_id)
    blockers: List[dict] = []

    if transition == "active":
        man = await _manpower_summary(project_id)
        if man["planned_count"] > 0 and man["deployed_count"] == 0:
            blockers.append({"kind": "manpower", "severity": "critical",
                              "message": f"Project requires {man['planned_count']} resources but 0 deployed."})
        safety = await _safety_summary(project_id)
        if safety["permits_active"] == 0 and safety.get("permits_expired", 0) == 0:
            blockers.append({"kind": "safety", "severity": "high",
                              "message": "No active work permit on file."})
        if safety["critical_safety_open"] > 0:
            blockers.append({"kind": "safety", "severity": "critical",
                              "message": f"{safety['critical_safety_open']} critical safety issue(s) open."})

    elif transition == "completed":
        # require DPR + progress data
        dpr_count = await db.dprs.count_documents({"project_id": project_id, "status": "approved"})
        if dpr_count == 0:
            blockers.append({"kind": "other", "severity": "high",
                              "message": "No approved DPR exists — execution data is incomplete."})
        wp_rows = await db.work_progress.find({"project_id": project_id}, {"_id": 0}).to_list(500)
        delayed = [r for r in wp_rows if r.get("status") == "delayed"]
        if delayed:
            blockers.append({"kind": "other", "severity": "medium",
                              "message": f"{len(delayed)} work-progress item(s) flagged delayed."})

    elif transition == "closure_pending":
        material = await _material_summary(project_id)
        if material["pending_returnable"] > 0:
            blockers.append({"kind": "material", "severity": "high",
                              "message": f"{material['pending_returnable']} pending returnable material item(s)."})

    elif transition == "closed":
        man = await _manpower_summary(project_id)
        if man["deployed_count"] > 0:
            blockers.append({"kind": "manpower", "severity": "high",
                              "message": f"{man['deployed_count']} resource(s) still deployed; demobilise before closure."})

        accounts = await _accounts_summary(project_id, project)
        if accounts["pending_billing"] > 0 and not project.get("non_billable"):
            blockers.append({"kind": "accounts", "severity": "high",
                              "message": f"Pending billing of ₹{accounts['pending_billing']:.2f}."})

        safety_critical = await db.site_issues.count_documents(
            {"project_id": project_id, "impact": "critical", "status": {"$ne": "closed"}}
        )
        if safety_critical > 0:
            blockers.append({"kind": "safety", "severity": "critical",
                              "message": f"{safety_critical} critical issue(s) open — cannot close until resolved."})

    # Filter out blockers covered by an approved override
    if blockers:
        if await _has_active_override(project_id, transition):
            for b in blockers:
                b["override_approved"] = True

    return blockers


@router.get("/blockers/{project_id}")
async def list_blockers(project_id: str,
                        transition: str = Query("active"),
                        user: dict = Depends(require_permission("projects", "read"))):
    blockers = await _compute_blockers(project_id, transition)
    return {"project_id": project_id, "transition": transition, "blockers": blockers,
            "blocked": any(not b.get("override_approved") for b in blockers)}


# ═══════════════════════════════════════════════════════════════════════════
# Section 3 · Alerts (cost overrun + safety + finance)
# ═══════════════════════════════════════════════════════════════════════════

class AlertAck(BaseModel):
    note: Optional[str] = ""


async def _generate_alerts(project_id: str, project: dict):
    """Idempotently generate/refresh alerts based on current state."""
    fin = await _finance_summary(project_id, project)
    safety = await _safety_summary(project_id)
    accounts = await _accounts_summary(project_id, project)

    candidates: List[dict] = []
    if fin["finance_health"] == "over_budget":
        candidates.append({"kind": "finance", "severity": "critical",
                            "title": "Project over budget",
                            "detail": f"Actual ₹{fin['actual_cost']:.2f} > budget ₹{fin['approved_budget']:.2f}"})
    elif fin["finance_health"] == "approaching_limit":
        candidates.append({"kind": "finance", "severity": "high",
                            "title": "Approaching budget limit",
                            "detail": f"Actual ₹{fin['actual_cost']:.2f} > 90% of budget."})
    if safety["critical_safety_open"] > 0:
        candidates.append({"kind": "safety", "severity": "critical",
                            "title": f"{safety['critical_safety_open']} critical safety issue(s) open",
                            "detail": "Resolve before closure / continued work."})
    if safety["permits_expired"] > 0:
        candidates.append({"kind": "safety", "severity": "high",
                            "title": f"{safety['permits_expired']} permit(s) expired",
                            "detail": "Renew permits before resuming work."})
    if accounts["outstanding_receivable"] > 0:
        candidates.append({"kind": "accounts", "severity": "medium",
                            "title": f"Outstanding ₹{accounts['outstanding_receivable']:.2f}",
                            "detail": "Follow up on collection."})

    for c in candidates:
        signature = f"{project_id}|{c['kind']}|{c['title']}"
        exists = await db.project_alerts.find_one(
            {"signature": signature, "ack_at": None}, {"_id": 0, "id": 1}
        )
        if not exists:
            await db.project_alerts.insert_one({
                "id": new_id(),
                "project_id": project_id,
                "project_code": project.get("code"),
                "signature": signature,
                "kind": c["kind"], "severity": c["severity"],
                "title": c["title"], "detail": c["detail"],
                "ack_at": None, "ack_by": None,
                "created_at": now_iso(),
            })


@router.get("/alerts")
async def list_alerts(project_id: Optional[str] = None,
                      severity: Optional[str] = None,
                      acknowledged: Optional[bool] = None,
                      user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if severity:
        q["severity"] = severity
    if acknowledged is True:
        q["ack_at"] = {"$ne": None}
    elif acknowledged is False:
        q["ack_at"] = None
    return await db.project_alerts.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, payload: AlertAck,
                    user: dict = Depends(require_permission("projects", "write"))):
    a = await db.project_alerts.find_one({"id": alert_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Alert not found")
    patch = {
        "ack_at": now_iso(),
        "ack_by": user.get("name") or user.get("email"),
        "ack_note": payload.note or "",
    }
    await db.project_alerts.update_one({"id": alert_id}, {"$set": patch})
    return await db.project_alerts.find_one({"id": alert_id}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Section 4 · Status transition with blocker enforcement
# ═══════════════════════════════════════════════════════════════════════════

ALLOWED_TRANSITIONS = ("active", "on_hold", "completed", "closure_pending", "closed")


@router.get("/transition-check/{project_id}")
async def transition_check(project_id: str, to: str = Query(...),
                           user: dict = Depends(require_permission("projects", "read"))):
    if to not in ALLOWED_TRANSITIONS:
        raise HTTPException(400, f"Unsupported transition '{to}'")
    blockers = await _compute_blockers(project_id, to)
    blocked = any(not b.get("override_approved") for b in blockers)
    return {"project_id": project_id, "to": to, "blockers": blockers,
            "blocked": blocked, "can_transition": not blocked}


@router.post("/transition/{project_id}")
async def apply_transition(project_id: str, to: str = Query(...),
                           override_reason: Optional[str] = Query(None),
                           user: dict = Depends(require_permission("projects", "write"))):
    if to not in ALLOWED_TRANSITIONS:
        raise HTTPException(400, f"Unsupported transition '{to}'")
    project = await _project(project_id)
    blockers = await _compute_blockers(project_id, to)
    unresolved = [b for b in blockers if not b.get("override_approved")]
    if unresolved:
        if not override_reason or user.get("role") not in ("super_admin", "director", "general_manager"):
            raise HTTPException(403, {
                "message": "Transition blocked",
                "blockers": unresolved,
                "hint": "Provide override_reason= AND user must be GM/Director/Super Admin",
            })
        # auto-create an approved exception
        await db.project_exceptions.insert_one({
            "id": new_id(),
            "project_id": project_id,
            "kind": "other",
            "title": f"Override for transition→{to}",
            "reason": override_reason,
            "applies_to_transition": to,
            "valid_until": "",
            "status": "approved",
            "approved_by": user.get("name") or user.get("email"),
            "approved_at": now_iso(),
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
        })

    # apply state change
    before_status = project.get("status")
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"status": to, "status_updated_at": now_iso(),
                  "status_updated_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action=f"transition→{to}", resource="projects",
                record_id=project_id, before={"status": before_status}, after={"status": to}, ip="phase4")

    # generate alerts after transition
    await _generate_alerts(project_id, await _project(project_id))

    return {"project_id": project_id, "from": before_status, "to": to,
            "override_used": bool(unresolved)}


# ═══════════════════════════════════════════════════════════════════════════
# Section 5 · Control Center — portfolio + one-project unified payload
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/control-center/{project_id}")
async def one_project_control(project_id: str,
                              user: dict = Depends(require_permission("projects", "read"))):
    project = await _project(project_id)
    manpower = await _manpower_summary(project_id)
    material = await _material_summary(project_id)
    safety = await _safety_summary(project_id)
    logistics = await _logistics_summary(project_id)
    procurement = await _procurement_summary(project_id)
    accounts = await _accounts_summary(project_id, project)
    finance = await _finance_summary(project_id, project)
    blockers = await _compute_blockers(project_id, "active")
    closure_blockers = await _compute_blockers(project_id, "closed")
    alerts = await db.project_alerts.find(
        {"project_id": project_id, "ack_at": None}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    # auto-refresh alerts
    await _generate_alerts(project_id, project)
    return {
        "project": {"id": project["id"], "code": project.get("code"), "name": project.get("name"),
                     "status": project.get("status"), "client": project.get("client_name") or project.get("client")},
        "manpower": manpower, "material": material, "safety": safety,
        "logistics": logistics, "procurement": procurement,
        "accounts": accounts, "finance": finance,
        "blockers_active": blockers, "blockers_closure": closure_blockers,
        "unack_alerts": alerts, "alerts_count": len(alerts),
    }


@router.get("/control-center")
async def portfolio_control_center(user: dict = Depends(require_permission("projects", "read"))):
    """Portfolio-wide KPI grid."""
    projects = await db.projects.find({}, {"_id": 0}).to_list(1000)

    counters = {
        "projects_active": 0, "projects_delayed": 0,
        "projects_with_manpower_shortage": 0,
        "projects_with_material_shortage": 0,
        "projects_with_safety_pending": 0,
        "projects_with_logistics_pending": 0,
        "projects_over_budget": 0,
        "projects_pending_billing": 0,
        "projects_pending_collection": 0,
        "projects_with_open_issues": 0,
        "projects_with_pending_client_measurement": 0,
        "projects_ready_for_closure": 0,
        "projects_blocked_material_return": 0,
        "projects_blocked_safety": 0,
        "projects_blocked_manpower": 0,
    }
    cards: List[dict] = []

    for p in projects:
        pid = p["id"]
        status = p.get("status") or "active"
        if status == "active":
            counters["projects_active"] += 1

        m = await _manpower_summary(pid)
        if m["shortage_count"] > 0:
            counters["projects_with_manpower_shortage"] += 1
        mat = await _material_summary(pid)
        if mat["pending_returnable"] > 0:
            counters["projects_blocked_material_return"] += 1
        sa = await _safety_summary(pid)
        if sa["safety_issues_open"] > 0 or sa["permits_expired"] > 0:
            counters["projects_with_safety_pending"] += 1
        if sa["critical_safety_open"] > 0:
            counters["projects_blocked_safety"] += 1
        lg = await _logistics_summary(pid)
        if lg["pending_dispatches"] > 0 or lg["in_transit"] > 0:
            counters["projects_with_logistics_pending"] += 1

        fin = await _finance_summary(pid, p)
        if fin["finance_health"] == "over_budget":
            counters["projects_over_budget"] += 1

        ac = await _accounts_summary(pid, p)
        if ac["pending_billing"] > 0:
            counters["projects_pending_billing"] += 1
        if ac["outstanding_receivable"] > 0:
            counters["projects_pending_collection"] += 1

        # open issues
        issues_open = await db.site_issues.count_documents(
            {"project_id": pid, "status": {"$in": ["open", "in_progress"]}}
        ) if await _coll_exists("site_issues") else 0
        if issues_open > 0:
            counters["projects_with_open_issues"] += 1

        # pending client cert
        pcl = await db.measurement_lines.count_documents(
            {"project_id": pid, "client_certification_status": {"$in": ["pending", "partial", "held"]}}
        ) if await _coll_exists("measurement_lines") else 0
        if pcl > 0:
            counters["projects_with_pending_client_measurement"] += 1

        # delayed
        delayed_wp = await db.work_progress.count_documents(
            {"project_id": pid, "status": "delayed"}
        ) if await _coll_exists("work_progress") else 0
        if delayed_wp > 0:
            counters["projects_delayed"] += 1

        # manpower-blocker?
        blk = await _compute_blockers(pid, "active")
        if any(b["kind"] == "manpower" and not b.get("override_approved") for b in blk):
            counters["projects_blocked_manpower"] += 1

        # closure readiness
        closure_blk = await _compute_blockers(pid, "closed")
        ready_for_closure = (
            status in ("completed", "closure_pending")
            and not any(not b.get("override_approved") for b in closure_blk)
        )
        if ready_for_closure:
            counters["projects_ready_for_closure"] += 1

        # mini card per project
        cards.append({
            "project_id": pid, "project_code": p.get("code"), "name": p.get("name"),
            "status": status, "client": p.get("client_name") or p.get("client"),
            "manpower_shortage": m["shortage_count"],
            "material_pending_return": mat["pending_returnable"],
            "safety_critical": sa["critical_safety_open"],
            "permits_expired": sa["permits_expired"],
            "logistics_pending": lg["pending_dispatches"] + lg["in_transit"],
            "open_issues": issues_open,
            "pending_billing": ac["pending_billing"],
            "outstanding": ac["outstanding_receivable"],
            "budget_health": fin["finance_health"],
            "variance_pct": fin["variance_pct"],
            "actual_pct": (await _accounts_summary(pid, p))["margin_pct"],
        })

    return {"as_of": _today(), "counters": counters, "projects": cards}
