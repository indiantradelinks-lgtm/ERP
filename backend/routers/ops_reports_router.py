"""Project Operations Reports (Iter 61, Phase 4).

Unified reporting endpoint with a `kind` selector — keeps the API small while
covering the 13 reports listed in the spec.

GET /ops/reports?kind=<report_id>&project_id=&client=&department=&pm=&pc=&start=&end=&status=

Available kinds (project-level rollups powered by ops_dashboard_router):
  • resources              · project-wise resource report
  • material_requests      · project-wise material request
  • purchase_requests      · project-wise PR
  • purchase_cost          · project-wise purchase cost (GRN value)
  • manpower               · project-wise manpower (deployments)
  • assets                 · project-wise asset allocation
  • pl                     · project-wise Profit & Loss
  • by_department          · department-wise project roll-up
  • by_pm                  · PM-wise project roll-up
  • pending_approvals      · pending approval across all projects
  • store_pending          · store: material requests still pending
  • loss_making            · projects running at a loss
  • outstanding_payments   · outstanding receivables by project
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core import db, require_permission
from .ops_dashboard_router import project_ops_dashboard

router = APIRouter(tags=["project-ops-reports"])

VALID_KINDS = {
    "resources", "material_requests", "purchase_requests", "purchase_cost",
    "manpower", "assets", "pl", "by_department", "by_pm",
    "pending_approvals", "store_pending", "loss_making", "outstanding_payments",
}


async def _gather_projects(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    return await db.projects.find(filters or {}, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.get("/ops/reports")
async def reports(
    kind: str = Query(..., description=f"One of {sorted(VALID_KINDS)}"),
    project_id: Optional[str] = None,
    client: Optional[str] = None,
    department: Optional[str] = None,
    pm: Optional[str] = None,
    pc: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    user: dict = Depends(require_permission("projects", "read")),
):
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(VALID_KINDS)}")

    proj_filter: Dict[str, Any] = {}
    if project_id:
        proj_filter["id"] = project_id
    if client:
        proj_filter["client_name"] = {"$regex": client, "$options": "i"}
    if department:
        proj_filter["department"] = department
    if pm:
        proj_filter["project_manager_id"] = pm
    if pc:
        proj_filter["project_coordinator_id"] = pc
    if status:
        proj_filter["status"] = status

    projects = await _gather_projects(proj_filter)

    # Apply role-based filter (PM/PC see only theirs)
    role = user.get("role")
    uid = user.get("id")
    if role in {"project_manager", "project_coordinator", "site_team"}:
        projects = [p for p in projects if uid in {p.get("project_manager_id"), p.get("project_coordinator_id"), p.get("reporting_manager_id")}]

    rows: List[Dict[str, Any]] = []

    # The simple kinds just pull from existing collections per project
    if kind == "resources":
        for p in projects:
            n_open = await db.resource_requests.count_documents({"project_id": p["id"], "status": {"$in": ["submitted", "pending_approval"]}})
            n_approved = await db.resource_requests.count_documents({"project_id": p["id"], "status": {"$in": ["approved", "in_progress", "completed"]}})
            rows.append({"project_id": p["id"], "project_name": p.get("name"), "client_name": p.get("client_name"),
                          "open": n_open, "approved": n_approved})
    elif kind == "material_requests":
        for p in projects:
            n = await db.inventory_transactions.count_documents({"project_id": p["id"], "txn_type": {"$in": ["outward", "issue"]}})
            rows.append({"project_id": p["id"], "project_name": p.get("name"), "material_transactions": n})
    elif kind == "purchase_requests":
        for p in projects:
            n_total = await db.purchase_requisitions.count_documents({"project_id": p["id"]})
            n_pending = await db.purchase_requisitions.count_documents({"project_id": p["id"], "status": {"$in": ["draft", "submitted", "pending_approval"]}})
            n_approved = await db.purchase_requisitions.count_documents({"project_id": p["id"], "status": "approved"})
            rows.append({"project_id": p["id"], "project_name": p.get("name"), "pr_total": n_total,
                          "pr_pending": n_pending, "pr_approved": n_approved})
    elif kind == "purchase_cost":
        for p in projects:
            grns = await db.grn.find({"project_id": p["id"]}, {"_id": 0, "total_value": 1}).to_list(2000)
            total = float(sum(float(g.get("total_value") or 0) for g in grns))
            rows.append({"project_id": p["id"], "project_name": p.get("name"), "purchase_cost": total, "grn_count": len(grns)})
    elif kind == "manpower":
        for p in projects:
            deps = await db.deployments.find({"project_id": p["id"]}, {"_id": 0, "status": 1, "employee_id": 1, "cost": 1, "daily_rate": 1, "days": 1}).to_list(5000)
            active = [d for d in deps if d.get("status") in {"approved", "active", "deployed"}]
            cost = float(sum(float(d.get("cost") or float(d.get("daily_rate") or 0) * float(d.get("days") or 0)) for d in deps))
            rows.append({"project_id": p["id"], "project_name": p.get("name"),
                          "manpower_total": len({d.get("employee_id") for d in active}),
                          "manpower_cost": cost})
    elif kind == "assets":
        for p in projects:
            n = await db.resource_requests.count_documents({"project_id": p["id"], "resource_type": "asset"})
            rows.append({"project_id": p["id"], "project_name": p.get("name"), "asset_requests": n})
    elif kind == "pl" or kind == "by_department" or kind == "by_pm" or kind == "loss_making" or kind == "outstanding_payments":
        # Dashboard powers these — gather full snapshot per project.
        for p in projects:
            try:
                d = await project_ops_dashboard(p["id"], user)
            except HTTPException:
                continue
            fin = d["financial"]
            entry = {
                "project_id": p["id"], "project_name": p.get("name"),
                "client_name": p.get("client_name"), "department": p.get("department"),
                "project_manager_id": p.get("project_manager_id"),
                "contract_value": fin["contract_value"],
                "billing_done": fin["billing_done"],
                "payment_received": fin["payment_received"],
                "outstanding": fin["outstanding"],
                "total_project_cost": fin["total_project_cost"],
                "gross_profit": fin["gross_profit"],
                "net_profit": fin["net_profit"],
                "profit_percentage": fin["profit_percentage"],
                "is_loss": fin["is_loss"],
                "over_budget": fin["over_budget"],
            }
            if kind == "loss_making" and not fin["is_loss"]:
                continue
            if kind == "outstanding_payments" and fin["outstanding"] <= 0:
                continue
            rows.append(entry)
        if kind == "by_department":
            agg: Dict[str, Dict[str, float]] = {}
            for r in rows:
                d = r.get("department") or "—"
                a = agg.setdefault(d, {"projects": 0, "billing_done": 0, "total_project_cost": 0, "net_profit": 0, "outstanding": 0})
                a["projects"] += 1
                a["billing_done"] += r["billing_done"]
                a["total_project_cost"] += r["total_project_cost"]
                a["net_profit"] += r["net_profit"]
                a["outstanding"] += r["outstanding"]
            rows = [{"department": k, **v} for k, v in agg.items()]
        elif kind == "by_pm":
            agg: Dict[str, Dict[str, float]] = {}
            for r in rows:
                pmid = r.get("project_manager_id") or "—"
                a = agg.setdefault(pmid, {"projects": 0, "billing_done": 0, "total_project_cost": 0, "net_profit": 0, "outstanding": 0})
                a["projects"] += 1
                a["billing_done"] += r["billing_done"]
                a["total_project_cost"] += r["total_project_cost"]
                a["net_profit"] += r["net_profit"]
                a["outstanding"] += r["outstanding"]
            # Hydrate PM names
            ids = [k for k in agg.keys() if k and k != "—"]
            users_by_id = {u["id"]: (u.get("name") or u.get("email")) for u in await db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(500)}
            rows = [{"project_manager_id": k, "project_manager_label": users_by_id.get(k, k), **v} for k, v in agg.items()]
    elif kind == "pending_approvals":
        q: Dict[str, Any] = {"status": "pending"}
        rows = await db.approvals.find(q, {"_id": 0, "id": 1, "type": 1, "title": 1, "requested_by": 1, "current_step": 1, "created_at": 1}).sort("created_at", -1).to_list(2000)
    elif kind == "store_pending":
        rows = await db.resource_requests.find(
            {"resource_type": {"$in": ["asset", "consumable", "ppe", "tool"]},
              "status": {"$in": ["submitted", "pending_approval", "approved"]}},
            {"_id": 0},
        ).sort("created_at", -1).to_list(2000)

    return {"kind": kind, "count": len(rows), "rows": rows, "filters": {
        "project_id": project_id, "client": client, "department": department,
        "pm": pm, "pc": pc, "status": status, "start": start, "end": end,
    }}
