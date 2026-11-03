"""Monthly Recurring Service Payments (fixed transportation and similar).

A Service PO can be flagged as a **monthly recurring service**: the Service
Request / RFQ / PO are raised once for the whole project duration, and from then
on Logistics only raises the monthly payment. Each month lands directly in the
existing Accounts payment queue (verify → bank file → paid) — no SRN and no
3-way match — while the cumulative value is still capped by the PO value.

Validity defaults to the Project Master Start / Target Completion dates and can
be extended when the project is extended, without touching the procurement chain.
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from audit import audit
from core import db, get_current_user, new_id, now_iso, require_permission

router = APIRouter(prefix="/service-recurring", tags=["service-recurring"])

RAISE_ROLES = {"super_admin", "manager_log", "manager_l_o_g", "logistics_executive",
               "logistics_manager", "purchase_officer", "procurement_executive",
               "manager_pnv", "manager_p_n_v",
               "director", "general_manager"}
CLOSED_PROJECT_STATUSES = {"closed", "cancelled"}
PO_ELIGIBLE_STATUSES = {"approved", "issued", "in_progress", "completed"}


def _ip(request: Optional[Request]) -> str:
    return request.client.host if request and request.client else ""


def _uname(user: dict) -> str:
    return user.get("name") or user.get("email") or "User"


def _require_raise_role(user: dict):
    if user.get("role") not in RAISE_ROLES:
        raise HTTPException(403, "Only Logistics / Procurement can raise monthly service payments")


def _month_key(d: str) -> str:
    return (d or "")[:7]


def _month_label(m: str) -> str:
    try:
        return datetime.strptime(m, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return m


def _months_between(start: str, end: str) -> List[str]:
    """Inclusive list of YYYY-MM keys between two ISO dates."""
    if not start or not end or end < start:
        return []
    y, m = int(start[0:4]), int(start[5:7])
    ey, em = int(end[0:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em) and len(out) < 240:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


async def _project_for(code: str) -> dict:
    if not code:
        return {}
    return await db.projects.find_one({"code": code}, {"_id": 0, "code": 1, "name": 1, "status": 1,
                                                       "start_date": 1, "end_date": 1,
                                                       "actual_completion_date": 1}) or {}


async def _contract(cid: str) -> dict:
    row = await db.svc_recurring.find_one({"id": cid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Recurring service contract not found")
    return row


async def _po(po_id: str) -> dict:
    row = await db.svc_pos.find_one({"id": po_id}, {"_id": 0, "history": 0})
    if not row:
        raise HTTPException(404, "Service PO not found")
    return row


async def _paid_summary(cid: str) -> Dict[str, dict]:
    rows = await db.svc_recurring_payments.find(
        {"recurring_id": cid, "status": {"$ne": "rejected"}}, {"_id": 0}).to_list(500)
    return {r["month"]: r for r in rows}


def _committed(payments: Dict[str, dict]) -> float:
    return round(sum(float(p.get("gross") or 0) for p in payments.values()), 2)


async def _enrich(c: dict) -> dict:
    project = await _project_for(c.get("project_code"))
    payments = await _paid_summary(c["id"])
    po = await db.svc_pos.find_one({"id": c["po_id"]}, {"_id": 0, "total_value": 1, "status": 1}) or {}
    po_value = float(po.get("total_value") or 0)
    committed = _committed(payments)
    today = date.today().isoformat()
    effective_to = min(x for x in [c.get("validity_to"), project.get("end_date") or c.get("validity_to")] if x)
    months = _months_between(c.get("validity_from"), c.get("validity_to"))
    raised = len(payments)
    this_month = today[:7]
    due_now = (c.get("status") == "active"
               and project.get("status") not in CLOSED_PROJECT_STATUSES
               and this_month in months and this_month not in payments)
    return {**c,
            "project_status": project.get("status"), "project_end_date": project.get("end_date"),
            "project_name": project.get("name") or c.get("project_name"),
            "po_status": po.get("status"), "po_value": po_value,
            "committed_value": committed, "remaining_value": round(po_value - committed, 2),
            "effective_to": effective_to,
            "months_total": len(months), "months_raised": raised,
            "months_pending": max(len(months) - raised, 0),
            "paid_count": len([p for p in payments.values() if p.get("status") == "paid"]),
            "due_this_month": due_now,
            "project_closed": project.get("status") in CLOSED_PROJECT_STATUSES}


# ─── Enable / list / extend ────────────────────────────────────────────────
class EnableIn(BaseModel):
    monthly_amount: float = 0
    validity_from: str = ""
    validity_to: str = ""
    service_label: str = ""
    remarks: str = ""


@router.post("/pos/{po_id}/enable")
async def enable_recurring(po_id: str, p: EnableIn, request: Request,
                           user: dict = Depends(require_permission("service_workflow", "write"))):
    _require_raise_role(user)
    po = await _po(po_id)
    if po.get("status") not in PO_ELIGIBLE_STATUSES:
        raise HTTPException(400, f"PO must be approved/issued first (status '{po.get('status')}')")
    if await db.svc_recurring.find_one({"po_id": po_id, "status": {"$ne": "closed"}}, {"_id": 0, "id": 1}):
        raise HTTPException(400, "This PO already runs as a monthly recurring service")
    project = await _project_for(po.get("project_code"))
    v_from = p.validity_from or po.get("service_period_from") or project.get("start_date") or now_iso()[:10]
    v_to = p.validity_to or po.get("service_period_to") or project.get("end_date") or po.get("completion_date")
    if not v_to:
        raise HTTPException(400, "Set a Project Target Completion Date (Project Master) or a validity end date")
    if v_to < v_from:
        raise HTTPException(400, "Validity end date cannot be before the start date")
    if project.get("end_date") and v_to > project["end_date"]:
        raise HTTPException(400, f"Validity cannot go beyond the project end date ({project['end_date']}) — "
                                 f"extend the project first, then extend the service validity")
    amount = round(float(p.monthly_amount or 0), 2)
    if amount <= 0:
        raise HTTPException(400, "Monthly amount must be greater than zero")
    doc = {"id": new_id(), "po_id": po_id, "po_no": po.get("po_no"),
           "sr_id": po.get("sr_id"), "sr_no": po.get("sr_no"), "rfq_no": po.get("rfq_no"),
           "vendor_id": po.get("vendor_id"), "vendor_name": po.get("vendor_name"),
           "project_code": po.get("project_code"), "project_name": po.get("project_name") or project.get("name"),
           "service_label": p.service_label or po.get("scope_of_work") or "Fixed monthly transportation",
           "monthly_amount": amount, "tax_pct": float(po.get("tax_pct") or 0),
           "validity_from": v_from, "validity_to": v_to,
           "status": "active", "remarks": p.remarks,
           "history": [{"action": "enabled", "by": _uname(user), "at": now_iso(),
                        "remarks": f"Monthly ₹{amount:,.2f} · {v_from} → {v_to}"}],
           "created_by": _uname(user), "created_by_id": user.get("id"),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.svc_recurring.insert_one(dict(doc))
    await db.svc_pos.update_one({"id": po_id}, {"$set": {"recurring": True, "recurring_id": doc["id"],
                                                         "updated_at": now_iso()}})
    await audit(user=user, action="svc_recurring_enable", resource="service_recurring",
                record_id=doc["id"], after={"po_no": po.get("po_no"), "monthly": amount,
                                            "validity": f"{v_from}→{v_to}"}, ip=_ip(request))
    return await _enrich(doc)


@router.get("")
async def list_recurring(status: str = "", project_code: str = "", q: str = "",
                         user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if status:
        fl["status"] = status
    if project_code:
        fl["project_code"] = project_code
    if q:
        fl["$or"] = [{"po_no": {"$regex": q, "$options": "i"}},
                     {"vendor_name": {"$regex": q, "$options": "i"}},
                     {"project_code": {"$regex": q, "$options": "i"}},
                     {"service_label": {"$regex": q, "$options": "i"}}]
    rows = await db.svc_recurring.find(fl, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)
    return [await _enrich(r) for r in rows]


@router.get("/dashboard")
async def recurring_dashboard(user: dict = Depends(require_permission("service_workflow", "read"))):
    rows = [await _enrich(r) for r in await db.svc_recurring.find({}, {"_id": 0, "history": 0}).to_list(500)]
    active = [r for r in rows if r["status"] == "active" and not r["project_closed"]]
    return {"active": len(active), "due_this_month": len([r for r in active if r["due_this_month"]]),
            "monthly_commitment": round(sum(float(r["monthly_amount"]) for r in active), 2),
            "expiring_soon": len([r for r in active
                                  if r.get("validity_to", "") <= _month_key(now_iso()) + "-31"])}


@router.get("/{cid}")
async def get_recurring(cid: str, user: dict = Depends(require_permission("service_workflow", "read"))):
    c = await _contract(cid)
    out = await _enrich(c)
    out["history"] = c.get("history") or []
    return out


@router.get("/{cid}/months")
async def recurring_months(cid: str, user: dict = Depends(require_permission("service_workflow", "read"))):
    c = await _contract(cid)
    project = await _project_for(c.get("project_code"))
    payments = await _paid_summary(cid)
    today = date.today()
    this_month = today.isoformat()[:7]
    closed = project.get("status") in CLOSED_PROJECT_STATUSES
    out = []
    for m in _months_between(c.get("validity_from"), c.get("validity_to")):
        pay = payments.get(m)
        blocked = None
        if pay:
            blocked = "Already raised for this month"
        elif closed:
            blocked = f"Project is {project.get('status')} — monthly payments stopped"
        elif c.get("status") != "active":
            blocked = f"Contract is {c.get('status')}"
        elif m > this_month:
            blocked = "Future month — available from the 1st of that month"
        out.append({"month": m, "label": _month_label(m),
                    "amount": float(c.get("monthly_amount") or 0),
                    "status": (pay or {}).get("status") or "not_raised",
                    "payment": pay, "can_raise": blocked is None, "blocked_reason": blocked})
    return {"contract": await _enrich(c), "months": out}


class ExtendIn(BaseModel):
    validity_to: str
    remarks: str = ""


@router.post("/{cid}/extend")
async def extend_validity(cid: str, p: ExtendIn, request: Request,
                          user: dict = Depends(require_permission("service_workflow", "write"))):
    _require_raise_role(user)
    c = await _contract(cid)
    if not p.validity_to:
        raise HTTPException(400, "New validity end date is required")
    if p.validity_to <= c["validity_to"]:
        raise HTTPException(400, f"New end date must be after the current validity ({c['validity_to']})")
    project = await _project_for(c.get("project_code"))
    if project.get("end_date") and p.validity_to > project["end_date"]:
        raise HTTPException(400, f"Project end date is {project['end_date']} — extend the project in "
                                 f"Project Master first, then extend this service validity")
    if project.get("status") in CLOSED_PROJECT_STATUSES:
        raise HTTPException(400, f"Project is {project.get('status')} — validity cannot be extended")
    await db.svc_recurring.update_one({"id": cid}, {
        "$set": {"validity_to": p.validity_to, "status": "active", "updated_at": now_iso()},
        "$push": {"history": {"action": "validity_extended", "by": _uname(user), "at": now_iso(),
                              "remarks": f"{c['validity_to']} → {p.validity_to}. {p.remarks}".strip()}}})
    await db.svc_pos.update_one({"id": c["po_id"]}, {"$set": {"service_period_to": p.validity_to,
                                                              "updated_at": now_iso()}})
    await audit(user=user, action="svc_recurring_extend", resource="service_recurring", record_id=cid,
                after={"from": c["validity_to"], "to": p.validity_to}, ip=_ip(request))
    return await _enrich(await _contract(cid))


class StatusIn(BaseModel):
    status: str
    remarks: str = ""


@router.post("/{cid}/status")
async def set_status(cid: str, p: StatusIn, request: Request,
                     user: dict = Depends(require_permission("service_workflow", "write"))):
    _require_raise_role(user)
    if p.status not in ("active", "paused", "closed"):
        raise HTTPException(400, "status must be active | paused | closed")
    c = await _contract(cid)
    await db.svc_recurring.update_one({"id": cid}, {
        "$set": {"status": p.status, "updated_at": now_iso()},
        "$push": {"history": {"action": f"contract_{p.status}", "by": _uname(user),
                              "at": now_iso(), "remarks": p.remarks}}})
    if p.status == "closed":
        await db.svc_pos.update_one({"id": c["po_id"]}, {"$set": {"recurring": False, "updated_at": now_iso()}})
    await audit(user=user, action="svc_recurring_status", resource="service_recurring", record_id=cid,
                after={"status": p.status}, ip=_ip(request))
    return await _enrich(await _contract(cid))


# ─── Monthly payment ───────────────────────────────────────────────────────
class MonthlyPayIn(BaseModel):
    amount: float = 0
    vendor_invoice_no: str = ""
    invoice_date: str = ""
    remarks: str = ""


async def _raise_month(c: dict, month: str, p: MonthlyPayIn, user: dict, auto: bool = False) -> dict:
    project = await _project_for(c.get("project_code"))
    if c.get("status") != "active":
        raise HTTPException(400, f"Contract is {c.get('status')} — monthly payments are not available")
    if project.get("status") in CLOSED_PROJECT_STATUSES:
        raise HTTPException(400, f"Project is {project.get('status')} — monthly payments have stopped")
    if month not in _months_between(c.get("validity_from"), c.get("validity_to")):
        raise HTTPException(400, f"{_month_label(month)} is outside the service validity "
                                 f"({c.get('validity_from')} → {c.get('validity_to')}). Extend the validity first.")
    if month > date.today().isoformat()[:7]:
        raise HTTPException(400, "A future month cannot be raised yet")
    if await db.svc_recurring_payments.find_one({"recurring_id": c["id"], "month": month,
                                                 "status": {"$ne": "rejected"}}, {"_id": 0, "id": 1}):
        raise HTTPException(400, f"A payment for {_month_label(month)} already exists for this contract")
    amount = round(float(p.amount or c.get("monthly_amount") or 0), 2)
    if amount <= 0:
        raise HTTPException(400, "Amount must be greater than zero")
    tax = round(amount * float(c.get("tax_pct") or 0) / 100, 2)
    gross = round(amount + tax, 2)
    po = await _po(c["po_id"])
    po_value = float(po.get("total_value") or 0)
    committed = _committed(await _paid_summary(c["id"]))
    if po_value and round(committed + gross, 2) > po_value + 0.5:
        raise HTTPException(400, f"PO value exhausted — ₹{committed:,.2f} of ₹{po_value:,.2f} already committed; "
                                 f"this month needs ₹{gross:,.2f}. Revise the PO value or close the contract.")
    doc = {"id": new_id(), "recurring_id": c["id"], "po_id": c["po_id"], "po_no": c.get("po_no"),
           "sr_no": c.get("sr_no"), "month": month, "month_label": _month_label(month),
           "vendor_id": c.get("vendor_id"), "vendor_name": c.get("vendor_name"),
           "project_code": c.get("project_code"), "project_name": c.get("project_name"),
           "amount": amount, "tax_pct": float(c.get("tax_pct") or 0), "tax_amount": tax, "gross": gross,
           "vendor_invoice_no": p.vendor_invoice_no.strip(), "invoice_date": p.invoice_date or now_iso()[:10],
           "remarks": p.remarks, "status": "payment_pending", "auto_drafted": auto,
           "created_by": _uname(user), "created_by_id": user.get("id"), "created_at": now_iso()}
    pr_id = new_id()
    doc["request_id"] = pr_id
    await db.svc_recurring_payments.insert_one(dict(doc))
    description = (f"Monthly service payment — {c.get('service_label')} · {_month_label(month)} · "
                   f"{c.get('vendor_name')} (PO {c.get('po_no')} / SR {c.get('sr_no')})"
                   + (f". {p.remarks}" if p.remarks else ""))
    await db.project_requests.insert_one({
        "id": pr_id, "request_no": f"{c.get('po_no')}-{month}",
        "request_type": "service_recurring",
        "request_type_label": "Monthly Service Payment (Fixed Transport)",
        "is_payment": True, "is_stockable": False, "owning_dept": "logistics",
        "status": "with_dept", "payment_status": "payment_pending",
        "source": "service_recurring", "source_id": doc["id"],
        "project_code": c.get("project_code"), "project_name": c.get("project_name"),
        "vendor": c.get("vendor_name"), "vendor_name": c.get("vendor_name"), "vendor_id": c.get("vendor_id"),
        "invoice_no": doc["vendor_invoice_no"], "invoice_date": doc["invoice_date"],
        "est_value": gross, "amount": gross, "pay_debit_account_code": "5150",
        "description": description, "service_month": month,
        "items": [], "chain": [], "current_step": None,
        "created_by": _uname(user), "created_by_id": user.get("id"), "created_at": now_iso()})
    await db.svc_recurring.update_one({"id": c["id"]}, {
        "$push": {"history": {"action": "month_raised", "by": _uname(user), "at": now_iso(),
                              "remarks": f"{_month_label(month)} · ₹{gross:,.2f}"
                                         + (" (auto-drafted)" if auto else "")}},
        "$set": {"updated_at": now_iso()}})
    return doc


@router.post("/{cid}/months/{month}/raise")
async def raise_month(cid: str, month: str, p: MonthlyPayIn, request: Request,
                      user: dict = Depends(require_permission("service_workflow", "write"))):
    _require_raise_role(user)
    c = await _contract(cid)
    doc = await _raise_month(c, month, p, user)
    await audit(user=user, action="svc_recurring_month_raise", resource="service_recurring",
                record_id=doc["id"], after={"po_no": c.get("po_no"), "month": month,
                                            "gross": doc["gross"]}, ip=_ip(request))
    return doc


@router.get("/payments/all")
async def list_monthly_payments(month: str = "", project_code: str = "", vendor: str = "",
                                user: dict = Depends(require_permission("service_workflow", "read"))):
    fl: dict = {}
    if month:
        fl["month"] = month
    if project_code:
        fl["project_code"] = project_code
    if vendor:
        fl["vendor_name"] = {"$regex": vendor, "$options": "i"}
    rows = await db.svc_recurring_payments.find(fl, {"_id": 0}).sort("month", -1).to_list(2000)
    prs = {r["source_id"]: r async for r in db.project_requests.find(
        {"source": "service_recurring", "source_id": {"$in": [r["id"] for r in rows]}},
        {"_id": 0, "source_id": 1, "payment_status": 1, "id": 1})}
    vers = {v["request_id"]: v async for v in db.payment_verifications.find(
        {"request_id": {"$in": [p["id"] for p in prs.values()]}},
        {"_id": 0, "request_id": 1, "stage": 1, "utr_no": 1, "paid_date": 1, "net_payable": 1})}
    out = []
    for r in rows:
        pr = prs.get(r["id"]) or {}
        v = vers.get(pr.get("id")) or {}
        out.append({**r, "payment_stage": v.get("stage") or "pending_verification",
                    "utr_no": v.get("utr_no"), "paid_date": v.get("paid_date")})
    return out


async def sync_payment_states() -> int:
    """Reflect the Accounts payment stage back on the monthly rows."""
    rows = await db.svc_recurring_payments.find({"status": {"$ne": "paid"}}, {"_id": 0, "id": 1, "request_id": 1}).to_list(2000)
    n = 0
    for r in rows:
        v = await db.payment_verifications.find_one({"request_id": r.get("request_id")},
                                                    {"_id": 0, "stage": 1})
        stage = (v or {}).get("stage")
        if stage in ("paid", "rejected"):
            await db.svc_recurring_payments.update_one(
                {"id": r["id"]}, {"$set": {"status": stage, "updated_at": now_iso()}})
            n += 1
    return n


async def auto_draft_current_month() -> dict:
    """Create the current month's payment request for every active contract.

    Called by the platform cron on the 1st of each month so Logistics only has to
    approve/pay; duplicates are impossible because of the month uniqueness check.
    """
    await sync_payment_states()
    month = date.today().isoformat()[:7]
    created, skipped = [], 0
    system = {"id": "system", "name": "System (monthly auto-draft)", "role": "super_admin"}
    for c in await db.svc_recurring.find({"status": "active"}, {"_id": 0}).to_list(500):
        try:
            doc = await _raise_month(c, month, MonthlyPayIn(remarks="Auto-drafted for the month"),
                                      system, auto=True)
            created.append(doc["request_id"])
        except HTTPException:
            skipped += 1
        except Exception:
            skipped += 1
    return {"month": month, "created": len(created), "skipped": skipped,
            "at": datetime.now(timezone.utc).isoformat()}
