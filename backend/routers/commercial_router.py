"""Commercial & Operations bundle — Modules E, F, G.

E. Sales-Order (Client PO/WO) commercial enhancements:
   retention clause, security deposit, penalty clause, validity / expiry date,
   balance PO value tracking (from RA bills), expiring-soon alerts.

F. Project Operations augmentation:
   daily progress %, delay-event register, extra-work register, profitability
   snapshot (RA-billed − material/labour cost approximation).

G. Service-rate master:
   per-service × activity × unit × effective_from rate card consumable by
   Quotations and Measurement / RA-bill flows.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(tags=["commercial-ops"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _days_between(a: str, b: str) -> int:
    try:
        da = datetime.fromisoformat(a).date()
        db_ = datetime.fromisoformat(b).date()
        return (db_ - da).days
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# E. Sales-Order (Client PO) commercials
# ──────────────────────────────────────────────────────────────────────────────
class POCommercials(BaseModel):
    contract_value: Optional[float] = None
    retention_pct: Optional[float] = None
    security_deposit_amount: Optional[float] = None
    security_deposit_status: Optional[str] = None       # held | released | partial
    penalty_clause: Optional[str] = None
    validity_date: Optional[str] = None                  # ISO YYYY-MM-DD; PO expiry
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    payment_terms: Optional[str] = None
    billing_terms: Optional[str] = None
    material_supply_terms: Optional[str] = None
    manpower_supply_terms: Optional[str] = None
    po_attachment_id: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/orders/{order_id}/commercials")
async def update_order_commercials(order_id: str, payload: POCommercials, request: Request,
                                   user: dict = Depends(require_permission("quotations", "write"))):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    patch["updated_at"] = now_iso()
    await db.orders.update_one({"id": order_id}, {"$set": patch})
    row = await db.orders.find_one({"id": order_id}, {"_id": 0})
    await audit(user=user, action="update", resource="orders", record_id=order_id, after=patch, ip=_ip(request))
    return row


@router.get("/orders/{order_id}/utilization")
async def order_utilization(order_id: str,
                            user: dict = Depends(require_permission("quotations", "read"))):
    """Compute billed vs paid vs balance against the contract value."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    contract_value = float(order.get("contract_value") or 0)
    # Join via po_number OR order id reference on RA bills
    q = {"$or": [{"po_id": order_id}, {"po_number": order.get("order_no")}]}
    bills = await db.ra_bills.find(q, {"_id": 0}).to_list(500)
    billed_gross = round(sum(float(b.get("gross_value") or 0) for b in bills if b.get("status") not in ("draft", "cancelled")), 2)
    paid = round(sum(float(b.get("paid_amount") or 0) for b in bills), 2)
    retained = round(sum(float(b.get("retention_amount") or 0) for b in bills if b.get("status") not in ("draft", "cancelled")), 2)
    balance_po = round(contract_value - billed_gross, 2)
    return {
        "order_id": order_id, "order_no": order.get("order_no"),
        "contract_value": contract_value,
        "billed_gross": billed_gross,
        "paid_received": paid,
        "balance_po_value": balance_po,
        "retention_held": retained,
        "validity_date": order.get("validity_date"),
        "days_to_expiry": _days_between(_today(), order["validity_date"]) if order.get("validity_date") else None,
        "bill_count": sum(1 for b in bills if b.get("status") not in ("draft", "cancelled")),
        "utilisation_pct": round((billed_gross / contract_value * 100) if contract_value else 0, 1),
    }


@router.get("/orders/expiring-soon")
async def orders_expiring_soon(days: int = 30,
                               user: dict = Depends(require_permission("quotations", "read"))):
    """List orders whose validity_date falls within `days` from today."""
    today = datetime.now(timezone.utc).date()
    horizon = (today + timedelta(days=days)).isoformat()
    rows = await db.orders.find(
        {"validity_date": {"$gte": today.isoformat(), "$lte": horizon}, "status": {"$ne": "closed"}},
        {"_id": 0},
    ).to_list(500)
    rows.sort(key=lambda r: r.get("validity_date") or "")
    return {"as_of": today.isoformat(), "horizon_days": days, "count": len(rows), "rows": rows}


# ──────────────────────────────────────────────────────────────────────────────
# F. Project Operations
# ──────────────────────────────────────────────────────────────────────────────
class DelayEvent(BaseModel):
    date: Optional[str] = None
    hours: float = 0
    category: str = "other"                # weather | client_hold | manpower | material | safety | other
    reason: str


class ExtraWorkEvent(BaseModel):
    date: Optional[str] = None
    description: str
    estimated_value: Optional[float] = None
    client_approved: bool = False
    approval_note: Optional[str] = None


@router.post("/projects/{code}/ops/delay-events")
async def add_delay_event(code: str, payload: DelayEvent, request: Request,
                          user: dict = Depends(require_permission("project_ops", "write"))):
    if not await db.projects.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Project not found")
    doc = {
        "id": new_id(), "project_code": code, **payload.model_dump(),
        "logged_by": user.get("name") or user.get("email"), "logged_by_id": user["id"],
        "created_at": now_iso(),
    }
    doc["date"] = doc.get("date") or _today()
    await db.project_delay_events.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="add_delay", resource="projects", record_id=code, after=doc, ip=_ip(request))
    return doc


@router.delete("/projects/{code}/ops/delay-events/{event_id}")
async def delete_delay_event(code: str, event_id: str, request: Request,
                             user: dict = Depends(require_permission("project_ops", "write"))):
    res = await db.project_delay_events.delete_one({"id": event_id, "project_code": code})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Delay event not found")
    return {"ok": True}


@router.post("/projects/{code}/ops/extra-works")
async def add_extra_work(code: str, payload: ExtraWorkEvent, request: Request,
                         user: dict = Depends(require_permission("project_ops", "write"))):
    if not await db.projects.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Project not found")
    doc = {
        "id": new_id(), "project_code": code, **payload.model_dump(),
        "logged_by": user.get("name") or user.get("email"), "logged_by_id": user["id"],
        "created_at": now_iso(),
    }
    doc["date"] = doc.get("date") or _today()
    await db.project_extra_works.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="add_extra_work", resource="projects", record_id=code, after=doc, ip=_ip(request))
    return doc


@router.delete("/projects/{code}/ops/extra-works/{event_id}")
async def delete_extra_work(code: str, event_id: str, request: Request,
                            user: dict = Depends(require_permission("project_ops", "write"))):
    res = await db.project_extra_works.delete_one({"id": event_id, "project_code": code})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Extra-work event not found")
    return {"ok": True}


@router.get("/projects/{code}/ops/snapshot")
async def project_ops_snapshot(code: str,
                               user: dict = Depends(require_permission("project_ops", "read"))):
    project = await db.projects.find_one({"code": code}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # DPRs
    dpr_total = await db.dprs.count_documents({"project_code": code})
    dpr_approved = await db.dprs.count_documents({"project_code": code, "status": "approved"})
    last_dpr = await db.dprs.find({"project_code": code}, {"_id": 0}).sort("date", -1).to_list(1)
    last_dpr_date = last_dpr[0].get("date") if last_dpr else None
    # Measurement billable
    meas_aggr = await db.measurements.aggregate([
        {"$match": {"project_code": code, "status": {"$in": ["approved_for_billing", "billed"]}}},
        {"$group": {"_id": None, "billable_value": {"$sum": "$billable_value"}}},
    ]).to_list(2)
    billable = round((meas_aggr[0]["billable_value"] if meas_aggr else 0), 2)
    # Delay & extras
    delays = await db.project_delay_events.find({"project_code": code}, {"_id": 0}).sort("date", -1).to_list(500)
    extras = await db.project_extra_works.find({"project_code": code}, {"_id": 0}).sort("date", -1).to_list(500)
    delay_hours = round(sum(float(d.get("hours") or 0) for d in delays), 1)
    extras_value = round(sum(float(e.get("estimated_value") or 0) for e in extras), 2)
    # Progress %: 70% weight on completed DPR ratio + 30% weight on billable vs budget
    budget = float(project.get("budget") or 0)
    progress_pct = 0.0
    if dpr_total:
        progress_pct = (dpr_approved / dpr_total) * 70
    if budget:
        progress_pct += min((billable / budget) * 30, 30)
    return {
        "project": {"code": project["code"], "name": project.get("name"), "status": project.get("status"), "budget": budget},
        "dpr": {"total": dpr_total, "approved": dpr_approved, "last_dpr_date": last_dpr_date},
        "measurement_billable_value": billable,
        "progress_pct": round(progress_pct, 1),
        "delay_events": delays,
        "delay_hours": delay_hours,
        "extra_works": extras,
        "extras_value": extras_value,
    }


@router.get("/projects/{code}/ops/profitability")
async def project_profitability(code: str,
                                user: dict = Depends(require_permission("project_ops", "read"))):
    """Indicative profitability snapshot — revenue (RA-billed) minus cost
    approximations (issued material valuation + payroll allocated to project).
    """
    project = await db.projects.find_one({"code": code}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Revenue: gross_value of non-draft / non-cancelled RA bills tagged to project
    rev_aggr = await db.ra_bills.aggregate([
        {"$match": {"project_code": code, "status": {"$nin": ["draft", "cancelled"]}}},
        {"$group": {"_id": None, "v": {"$sum": "$gross_value"}, "net": {"$sum": "$net_payable"}, "c": {"$sum": 1}}},
    ]).to_list(2)
    revenue_gross = round((rev_aggr[0]["v"] if rev_aggr else 0), 2)
    revenue_net = round((rev_aggr[0]["net"] if rev_aggr else 0), 2)
    bill_count = (rev_aggr[0]["c"] if rev_aggr else 0)
    # Cost — material allocations (issued) valued at item rate
    mat_aggr = await db.material_allocations.aggregate([
        {"$match": {"project_code": code, "status": {"$in": ["issued", "partial_return", "returned"]}}},
        {"$unwind": "$items"},
        {"$group": {"_id": None, "v": {"$sum": {"$multiply": [{"$ifNull": ["$items.rate", 0]}, {"$ifNull": ["$items.issued_quantity", 0]}]}}}},
    ]).to_list(2)
    material_cost = round((mat_aggr[0]["v"] if mat_aggr else 0), 2)
    # Labour cost — sum payroll.net_pay for employees deployed to this project (lightweight join)
    deps = await db.deployments.find({"project": code, "status": {"$nin": ["completed", "withdrawn"]}}, {"_id": 0, "employee_id": 1}).to_list(500)
    emp_ids = [d.get("employee_id") for d in deps if d.get("employee_id")]
    labour_cost = 0.0
    if emp_ids:
        pay_aggr = await db.payroll.aggregate([
            {"$match": {"employee_id": {"$in": emp_ids}}},
            {"$group": {"_id": None, "v": {"$sum": {"$ifNull": ["$net_pay", "$net_amount"]}}}},
        ]).to_list(2)
        labour_cost = round((pay_aggr[0]["v"] if pay_aggr else 0), 2)
    total_cost = round(material_cost + labour_cost, 2)
    gross_margin = round(revenue_gross - total_cost, 2)
    margin_pct = round((gross_margin / revenue_gross * 100) if revenue_gross else 0, 1)
    return {
        "project_code": code,
        "revenue": {"gross": revenue_gross, "net": revenue_net, "bill_count": bill_count},
        "cost": {"material": material_cost, "labour": labour_cost, "total": total_cost},
        "gross_margin": gross_margin,
        "margin_pct": margin_pct,
    }


# ──────────────────────────────────────────────────────────────────────────────
# G. Service-rate master
# ──────────────────────────────────────────────────────────────────────────────
class ServiceRate(BaseModel):
    service: str                          # scaffolding | painting | rope_access | insulation | roof_sheeting | other
    activity: str
    unit: str = "m²"
    standard_rate: float
    description: Optional[str] = None
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    notes: Optional[str] = None


@router.get("/service-rates")
async def list_service_rates(service: Optional[str] = None,
                             active_only: bool = False,
                             user: dict = Depends(require_permission("service_rates", "read"))):
    q: dict = {}
    if service:
        q["service"] = service
    if active_only:
        today = _today()
        q["$and"] = [
            {"$or": [{"effective_from": {"$exists": False}}, {"effective_from": {"$lte": today}}]},
            {"$or": [{"effective_until": {"$exists": False}}, {"effective_until": {"$gte": today}}, {"effective_until": None}]},
        ]
    return await db.service_rates.find(q, {"_id": 0}).sort([("service", 1), ("activity", 1)]).to_list(1000)


@router.get("/service-rates/lookup")
async def lookup_rate(service: str, activity: str, unit: Optional[str] = None,
                      user: dict = Depends(require_permission("service_rates", "read"))):
    today = _today()
    q: dict = {"service": service, "activity": activity}
    if unit:
        q["unit"] = unit
    q["$and"] = [
        {"$or": [{"effective_from": {"$exists": False}}, {"effective_from": {"$lte": today}}]},
        {"$or": [{"effective_until": {"$exists": False}}, {"effective_until": {"$gte": today}}, {"effective_until": None}]},
    ]
    row = await db.service_rates.find_one(q, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="No active rate found")
    return row


@router.post("/service-rates")
async def create_service_rate(payload: ServiceRate, request: Request,
                              user: dict = Depends(require_permission("service_rates", "write"))):
    doc = {"id": new_id(), **payload.model_dump(),
           "created_at": now_iso(), "created_by": user["id"]}
    await db.service_rates.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="service_rates", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/service-rates/{rate_id}")
async def update_service_rate(rate_id: str, payload: dict, request: Request,
                              user: dict = Depends(require_permission("service_rates", "write"))):
    row = await db.service_rates.find_one({"id": rate_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Rate not found")
    for k in ("id", "created_at", "created_by"):
        payload.pop(k, None)
    payload["updated_at"] = now_iso()
    await db.service_rates.update_one({"id": rate_id}, {"$set": payload})
    return await db.service_rates.find_one({"id": rate_id}, {"_id": 0})


@router.delete("/service-rates/{rate_id}")
async def delete_service_rate(rate_id: str, request: Request,
                              user: dict = Depends(require_permission("service_rates", "delete"))):
    res = await db.service_rates.delete_one({"id": rate_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rate not found")
    await audit(user=user, action="delete", resource="service_rates", record_id=rate_id, ip=_ip(request))
    return {"ok": True}
