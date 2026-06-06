"""Receivables & Cashflow — Module D.

Combines invoiced RA bills + payments_in to expose:
  * Ageing buckets (0-30 / 31-60 / 61-90 / 91-180 / >180)
  * Client ledger (invoices + payments + running balance)
  * Overdue alerts
  * 30-day cashflow forecast
  * Payment recording with auto-allocation
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence, stamp_dept_doc

router = APIRouter(tags=["receivables"])

AGEING_BUCKETS = [(0, 30, "0-30d"), (31, 60, "31-60d"), (61, 90, "61-90d"),
                  (91, 180, "91-180d"), (181, 10_000, ">180d")]


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
# Payments
# ──────────────────────────────────────────────────────────────────────────────
class PaymentInAlloc(BaseModel):
    ra_bill_id: str
    amount: float


class PaymentIn(BaseModel):
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    payment_date: Optional[str] = None
    amount: float
    mode: str = "bank_transfer"   # bank_transfer | cheque | cash | upi | rtgs | neft
    reference_no: Optional[str] = None
    notes: Optional[str] = None
    allocations: List[PaymentInAlloc] = Field(default_factory=list)


@router.post("/payments-in")
async def record_payment(payload: PaymentIn, request: Request,
                         user: dict = Depends(require_permission("payments_in", "write"))):
    """Record an inbound payment and (optionally) allocate it across one or more
    invoiced RA bills. When allocations sum to the payment amount and cover the
    full net_payable of each bill, those bills flip to `paid`.
    """
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be > 0")
    alloc_total = sum(float(a.amount) for a in payload.allocations or [])
    if alloc_total > payload.amount + 1e-6:
        raise HTTPException(status_code=400, detail=f"Allocations ({alloc_total}) exceed payment amount ({payload.amount})")

    # Resolve / validate bills first so we can fail fast before insert
    bill_lookup: Dict[str, Dict[str, Any]] = {}
    for a in payload.allocations or []:
        bill = await db.ra_bills.find_one({"id": a.ra_bill_id}, {"_id": 0})
        if not bill:
            raise HTTPException(status_code=404, detail=f"RA bill {a.ra_bill_id} not found")
        if bill.get("status") not in ("invoiced", "approved"):
            raise HTTPException(status_code=400, detail=f"RA bill {bill.get('bill_number')} is in '{bill.get('status')}' — cannot apply payment")
        bill_lookup[a.ra_bill_id] = bill

    doc = {
        "id": new_id(),
        "payment_no": await next_sequence("PAY"),
        "client_id": payload.client_id, "client_name": payload.client_name,
        "payment_date": payload.payment_date or _today(),
        "amount": round(float(payload.amount), 2),
        "mode": payload.mode, "reference_no": payload.reference_no, "notes": payload.notes,
        "allocations": [a.model_dump() for a in payload.allocations or []],
        "unallocated": round(float(payload.amount) - alloc_total, 2),
        "created_by": user["id"], "created_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await stamp_dept_doc(doc, "payment_in")
    await db.payments_in.insert_one(doc)
    # Update each linked bill: append paid_amounts + flip to paid when fully covered
    for a in payload.allocations or []:
        bill = bill_lookup[a.ra_bill_id]
        prev_paid = float(bill.get("paid_amount") or 0)
        new_paid = round(prev_paid + float(a.amount), 2)
        net = float(bill.get("net_payable") or 0)
        new_status = "paid" if new_paid + 1e-6 >= net else bill.get("status")
        await db.ra_bills.update_one({"id": a.ra_bill_id}, {
            "$set": {"paid_amount": new_paid, "balance_due": round(net - new_paid, 2), "status": new_status, "updated_at": now_iso()},
            "$push": {"payments": {"payment_id": doc["id"], "payment_no": doc["payment_no"], "date": doc["payment_date"], "amount": float(a.amount), "mode": payload.mode}}
        })
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="payments_in", record_id=doc["id"], after={"payment_no": doc["payment_no"], "amount": doc["amount"]}, ip=_ip(request))
    return doc


@router.get("/payments-in")
async def list_payments(client_id: Optional[str] = None,
                        user: dict = Depends(require_permission("payments_in", "read"))):
    q: dict = {}
    if client_id:
        q["client_id"] = client_id
    return await db.payments_in.find(q, {"_id": 0}).sort("payment_date", -1).to_list(1000)


# ──────────────────────────────────────────────────────────────────────────────
# Receivables analytics
# ──────────────────────────────────────────────────────────────────────────────
async def _open_bills(filter_extra: Optional[dict] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"status": {"$in": ["invoiced", "approved"]}, "bill_type": {"$nin": ["credit_note"]}}
    if filter_extra:
        q.update(filter_extra)
    return await db.ra_bills.find(q, {"_id": 0}).to_list(2000)


@router.get("/receivables/ageing")
async def receivables_ageing(client_id: Optional[str] = None,
                             user: dict = Depends(require_permission("receivables", "read"))):
    """Bucket all open invoices by days past due."""
    today = _today()
    bills = await _open_bills({"client_id": client_id} if client_id else None)
    buckets: Dict[str, Dict[str, Any]] = {label: {"label": label, "count": 0, "amount": 0.0, "bills": []} for _, _, label in AGEING_BUCKETS}
    not_due = {"label": "Not due", "count": 0, "amount": 0.0, "bills": []}
    total = 0.0
    for b in bills:
        net = float(b.get("net_payable") or 0)
        paid = float(b.get("paid_amount") or 0)
        balance = round(net - paid, 2)
        if balance <= 0:
            continue
        due_date = b.get("due_date") or b.get("issue_date") or b.get("bill_date") or today
        days_past = _days_between(due_date, today)
        bucket_row = {
            "id": b["id"], "bill_number": b.get("bill_number"), "client_name": b.get("client_name"),
            "project_code": b.get("project_code"), "due_date": due_date,
            "days_past_due": days_past, "balance": balance,
        }
        total += balance
        if days_past <= 0:
            not_due["count"] += 1
            not_due["amount"] += balance
            not_due["bills"].append(bucket_row)
            continue
        for lo, hi, label in AGEING_BUCKETS:
            if lo <= days_past <= hi:
                buckets[label]["count"] += 1
                buckets[label]["amount"] += balance
                buckets[label]["bills"].append(bucket_row)
                break
    return {
        "as_of": today,
        "not_due": not_due,
        "buckets": list(buckets.values()),
        "total_outstanding": round(total, 2),
    }


@router.get("/receivables/client-ledger")
async def client_ledger(client_id: str,
                        user: dict = Depends(require_permission("receivables", "read"))):
    bills = await db.ra_bills.find({"client_id": client_id, "bill_type": {"$nin": ["credit_note"]}}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    payments = await db.payments_in.find({"client_id": client_id}, {"_id": 0}).sort("payment_date", 1).to_list(1000)
    txns: List[Dict[str, Any]] = []
    for b in bills:
        if b.get("status") in ("approved", "invoiced", "paid"):
            txns.append({"date": b.get("issue_date") or b.get("bill_date"), "type": "invoice",
                         "ref": b.get("bill_number"), "debit": float(b.get("net_payable") or 0), "credit": 0,
                         "ra_bill_id": b["id"], "status": b.get("status")})
    for p in payments:
        txns.append({"date": p.get("payment_date"), "type": "payment", "ref": p.get("payment_no"),
                     "debit": 0, "credit": float(p.get("amount") or 0),
                     "mode": p.get("mode"), "payment_id": p["id"]})
    txns.sort(key=lambda t: (t["date"] or "", t["type"] != "invoice"))
    running = 0.0
    for t in txns:
        running += t["debit"] - t["credit"]
        t["balance"] = round(running, 2)
    return {
        "client_id": client_id,
        "transactions": txns,
        "summary": {
            "invoiced": round(sum(t["debit"] for t in txns), 2),
            "received": round(sum(t["credit"] for t in txns), 2),
            "balance": round(running, 2),
            "count_invoices": sum(1 for t in txns if t["type"] == "invoice"),
            "count_payments": sum(1 for t in txns if t["type"] == "payment"),
        },
    }


@router.get("/receivables/overdue")
async def overdue(user: dict = Depends(require_permission("receivables", "read"))):
    today = _today()
    bills = await _open_bills()
    rows = []
    for b in bills:
        net = float(b.get("net_payable") or 0)
        paid = float(b.get("paid_amount") or 0)
        balance = round(net - paid, 2)
        if balance <= 0:
            continue
        due_date = b.get("due_date") or b.get("issue_date") or b.get("bill_date") or today
        days_past = _days_between(due_date, today)
        if days_past <= 0:
            continue
        rows.append({
            "id": b["id"], "bill_number": b.get("bill_number"),
            "client_id": b.get("client_id"), "client_name": b.get("client_name"),
            "project_code": b.get("project_code"), "po_number": b.get("po_number"),
            "issue_date": b.get("issue_date"), "due_date": due_date,
            "days_past_due": days_past, "balance": balance,
            "severity": "high" if days_past >= 91 else "medium" if days_past >= 31 else "low",
        })
    rows.sort(key=lambda r: r["days_past_due"], reverse=True)
    return {"as_of": today, "count": len(rows), "rows": rows, "total_overdue": round(sum(r["balance"] for r in rows), 2)}


@router.get("/receivables/cashflow")
async def cashflow_forecast(days: int = 30,
                            user: dict = Depends(require_permission("receivables", "read"))):
    """Project expected inflows across the next N days based on invoice due_dates."""
    today = datetime.now(timezone.utc).date()
    horizon = (today + timedelta(days=days)).isoformat()
    bills = await _open_bills()
    weeks: Dict[str, float] = {}
    overdue_amount = 0.0
    upcoming_amount = 0.0
    horizon_amount = 0.0
    for b in bills:
        net = float(b.get("net_payable") or 0)
        paid = float(b.get("paid_amount") or 0)
        balance = round(net - paid, 2)
        if balance <= 0:
            continue
        due = b.get("due_date") or b.get("issue_date") or b.get("bill_date") or today.isoformat()
        try:
            due_date = datetime.fromisoformat(due).date()
        except Exception:
            due_date = today
        if due_date < today:
            overdue_amount += balance
        elif due_date <= datetime.fromisoformat(horizon).date():
            upcoming_amount += balance
            horizon_amount += balance
            # Bucket by ISO week label
            wk = due_date.strftime("%G-W%V")
            weeks[wk] = round(weeks.get(wk, 0) + balance, 2)
        else:
            horizon_amount += 0
    return {
        "as_of": today.isoformat(),
        "horizon_days": days,
        "overdue_amount": round(overdue_amount, 2),
        "upcoming_within_horizon": round(upcoming_amount, 2),
        "weekly_inflow": [{"week": w, "amount": amt} for w, amt in sorted(weeks.items())],
    }


@router.get("/receivables/dashboard")
async def receivables_dashboard(user: dict = Depends(require_permission("receivables", "read"))):
    """Single-shot summary for the Receivables dashboard."""
    ageing = await receivables_ageing(user=user)        # type: ignore[arg-type]
    overdue_data = await overdue(user=user)             # type: ignore[arg-type]
    today = _today()
    bills = await _open_bills()
    invoiced_lifetime = await db.ra_bills.aggregate([
        {"$match": {"status": {"$in": ["invoiced", "paid"]}, "bill_type": {"$nin": ["credit_note"]}}},
        {"$group": {"_id": None, "v": {"$sum": "$gross_value"}}},
    ]).to_list(2)
    received_lifetime = await db.payments_in.aggregate([{"$group": {"_id": None, "v": {"$sum": "$amount"}}}]).to_list(2)
    return {
        "kpis": {
            "outstanding_total": ageing["total_outstanding"],
            "overdue_total": overdue_data["total_overdue"],
            "overdue_count": overdue_data["count"],
            "open_bills": len(bills),
            "invoiced_lifetime": round((invoiced_lifetime[0]["v"] if invoiced_lifetime else 0), 2),
            "received_lifetime": round((received_lifetime[0]["v"] if received_lifetime else 0), 2),
            "as_of": today,
        },
        "ageing": ageing,
        "overdue_preview": overdue_data["rows"][:5],
    }
