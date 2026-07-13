"""Ops project dashboard + P&L engine (Iter 61, Phase 3).

Composes a single dashboard snapshot per project by aggregating from existing tables:
  • Purchase Requests + POs + GRNs   → purchase / material cost
  • Store transactions                → material issued / pending
  • Resource Requests                 → open / approved / serviced by type
  • Payroll / deployments             → manpower cost
  • RA bills                          → billing + payment received

P&L formula:
    total_project_cost = Σ(purchase + material + consumable + ppe + manpower
                            + accommodation + vehicle + admin + driver + asset + other)
    gross_profit       = billing_done - total_project_cost
    net_profit         = payment_received - total_project_cost
    outstanding        = billing_done - payment_received
    profit_pct         = 0 if billing_done == 0 else net_profit / billing_done * 100
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from core import db, require_permission

logger = logging.getLogger("erp.ops_dashboard")
router = APIRouter(tags=["project-ops-dashboard"])


def _sum(rows: List[Dict[str, Any]], key: str) -> float:
    return float(sum((float(r.get(key) or 0) for r in rows)))


def _safe_pct(num: float, den: float) -> float:
    if not den:
        return 0.0
    return round(num / den * 100, 2)


async def _project(project_id: str) -> Dict[str, Any]:
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.get("/ops/projects/{project_id}/dashboard")
async def project_ops_dashboard(project_id: str, user: dict = Depends(require_permission("projects", "read"))):
    p = await _project(project_id)
    role = user.get("role")
    uid = user.get("id")
    if role in {"project_manager", "project_coordinator", "site_team"}:
        allowed = {p.get("project_manager_id"), p.get("project_coordinator_id"), p.get("reporting_manager_id")}
        if uid not in allowed:
            raise HTTPException(status_code=403, detail="You can only view projects assigned to you")

    contract_value = float(p.get("contract_value") or 0)
    prs = await db.purchase_requisitions.find({"project_id": project_id}, {"_id": 0, "status": 1, "items": 1, "total_value": 1}).to_list(2000)
    pending_prs = [r for r in prs if r.get("status") in {"draft", "pending_approval", "submitted"}]
    approved_prs = [r for r in prs if r.get("status") == "approved"]
    pos = await db.purchase_orders.find({"project_id": project_id}, {"_id": 0, "status": 1, "amount": 1, "total_amount": 1}).to_list(2000)
    po_total = _sum(pos, "total_amount") or _sum(pos, "amount")
    grns = await db.grn.find({"project_id": project_id}, {"_id": 0, "total_value": 1}).to_list(2000)
    purchase_cost = _sum(grns, "total_value")
    issued = await db.inventory_transactions.find(
        {"project_id": project_id, "txn_type": {"$in": ["outward", "issue"]}},
        {"_id": 0, "total_value": 1, "value_at_txn": 1}
    ).to_list(5000)
    material_cost = _sum(issued, "total_value") or _sum(issued, "value_at_txn")
    material_requests = await db.inventory_transactions.count_documents({"project_id": project_id, "txn_type": {"$in": ["outward", "issue"]}})

    rrs = await db.resource_requests.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    def _rr_cost(rtype):
        return float(sum((float(r.get("actual_cost") or 0) for r in rrs if r.get("resource_type") == rtype and r.get("status") in {"approved", "in_progress", "completed"})))
    cost_consumable = _rr_cost("consumable")
    cost_ppe = _rr_cost("ppe")
    cost_accommodation = _rr_cost("accommodation")
    cost_vehicle = _rr_cost("vehicle")
    cost_driver = _rr_cost("driver")
    cost_admin = _rr_cost("admin")
    cost_asset = _rr_cost("asset")
    cost_tool = _rr_cost("tool")
    cost_other = _rr_cost("other")
    open_rrs = [r for r in rrs if r.get("status") in {"draft", "submitted", "pending_approval"}]
    approved_rrs = [r for r in rrs if r.get("status") in {"approved", "in_progress", "completed"}]

    deps = await db.deployments.find({"project_id": project_id}, {"_id": 0, "status": 1, "cost": 1, "daily_rate": 1, "days": 1, "employee_id": 1}).to_list(5000)
    manpower_active = [d for d in deps if d.get("status") in {"approved", "active", "deployed"}]
    manpower_count = len({d.get("employee_id") for d in manpower_active})
    manpower_cost = float(sum((float(d.get("cost") or (float(d.get("daily_rate") or 0) * float(d.get("days") or 0))) for d in deps)))

    invs = await db.ra_bills.find({"project_id": project_id}, {"_id": 0, "amount": 1, "paid_amount": 1, "total": 1}).to_list(2000)
    billing_done = _sum(invs, "total") or _sum(invs, "amount")
    payment_received = _sum(invs, "paid_amount")

    total_project_cost = sum([purchase_cost, material_cost, cost_consumable, cost_ppe, manpower_cost,
                                 cost_accommodation, cost_vehicle, cost_driver, cost_admin, cost_asset,
                                 cost_tool, cost_other])
    gross_profit = billing_done - total_project_cost
    net_profit = payment_received - total_project_cost
    outstanding = billing_done - payment_received
    profit_pct = _safe_pct(net_profit, billing_done)
    is_loss = total_project_cost > billing_done > 0
    over_budget = total_project_cost > contract_value if contract_value else False

    alerts: List[Dict[str, Any]] = []
    if open_rrs:
        alerts.append({"level": "info", "type": "open_rr", "message": f"{len(open_rrs)} pending resource request(s)"})
    if pending_prs:
        alerts.append({"level": "info", "type": "pending_pr", "message": f"{len(pending_prs)} pending PR(s)"})
    if is_loss:
        alerts.append({"level": "danger", "type": "loss_making", "message": f"Project running at a loss: ₹{abs(net_profit):,.2f} loss against ₹{billing_done:,.2f} billing"})
    if over_budget:
        alerts.append({"level": "warning", "type": "over_budget", "message": f"Total cost ₹{total_project_cost:,.2f} exceeds contract value ₹{contract_value:,.2f}"})
    if outstanding > 0 and billing_done > 0:
        alerts.append({"level": "warning", "type": "outstanding", "message": f"Outstanding receivables: ₹{outstanding:,.2f}"})

    return {
        "project": {
            "id": p["id"], "code": p.get("code"), "name": p.get("name"),
            "client_name": p.get("client_name"), "site_location": p.get("site_location"),
            "contract_value": contract_value,
            "contract_start_date": p.get("contract_start_date"),
            "contract_end_date": p.get("contract_end_date"),
            "status": p.get("status"), "priority": p.get("priority"),
            "project_manager_id": p.get("project_manager_id"),
            "project_coordinator_id": p.get("project_coordinator_id"),
            "reporting_manager_id": p.get("reporting_manager_id"),
            "department": p.get("department"),
        },
        "operations": {"open_tasks": 0, "pending_approvals": len(pending_prs) + len(open_rrs)},
        "resources": {
            "manpower_deployed": manpower_count, "manpower_active": len(manpower_active),
            "assets_deployed": int(sum(1 for r in approved_rrs if r.get("resource_type") == "asset")),
            "vehicles_deployed": int(sum(1 for r in approved_rrs if r.get("resource_type") == "vehicle")),
            "accommodation_units": int(sum(1 for r in approved_rrs if r.get("resource_type") == "accommodation")),
            "open_resource_requests": len(open_rrs),
            "approved_resource_requests": len(approved_rrs),
            "by_type": {t: int(sum(1 for r in rrs if r.get("resource_type") == t)) for t in {"asset","consumable","ppe","manpower","accommodation","vehicle","admin","driver","tool","other"}},
        },
        "material": {
            "material_requested": material_requests, "material_issued": material_requests,
            "material_pending": int(sum(1 for r in rrs if r.get("resource_type") in {"asset","consumable","ppe","tool"} and r.get("status") in {"submitted","pending_approval","approved"})),
        },
        "purchase": {
            "pr_raised": len(prs), "pr_pending": len(pending_prs), "pr_approved": len(approved_prs),
            "po_created": len(pos), "po_value": po_total, "material_received_value": purchase_cost,
        },
        "financial": {
            "contract_value": contract_value, "billing_done": billing_done,
            "payment_received": payment_received, "outstanding": outstanding,
            "purchase_cost": purchase_cost, "material_cost": material_cost,
            "consumable_cost": cost_consumable, "ppe_cost": cost_ppe,
            "manpower_cost": manpower_cost, "accommodation_cost": cost_accommodation,
            "vehicle_cost": cost_vehicle, "admin_cost": cost_admin, "driver_cost": cost_driver,
            "asset_cost": cost_asset, "tool_cost": cost_tool, "other_cost": cost_other,
            "total_project_cost": total_project_cost,
            "gross_profit": gross_profit, "net_profit": net_profit,
            "profit_percentage": profit_pct, "is_loss": is_loss, "over_budget": over_budget,
        },
        "alerts": alerts,
    }


@router.get("/ops/projects/{project_id}/pl")
async def project_pl(project_id: str, user: dict = Depends(require_permission("projects", "read"))):
    d = await project_ops_dashboard(project_id, user)
    return d["financial"]


@router.get("/ops/projects/{project_id}/closure-check")
async def closure_check(project_id: str, user: dict = Depends(require_permission("projects", "read"))):
    d = await project_ops_dashboard(project_id, user)
    blockers: List[str] = []
    if d["purchase"]["pr_pending"]:
        blockers.append(f"{d['purchase']['pr_pending']} pending purchase request(s)")
    if d["resources"]["open_resource_requests"]:
        blockers.append(f"{d['resources']['open_resource_requests']} pending resource request(s)")
    if d["financial"]["outstanding"] > 0:
        blockers.append(f"Outstanding payment ₹{d['financial']['outstanding']:,.2f}")
    if d["financial"]["billing_done"] == 0:
        blockers.append("No billing raised yet")
    return {"ok": not blockers, "blockers": blockers, "financial_snapshot": d["financial"]}
