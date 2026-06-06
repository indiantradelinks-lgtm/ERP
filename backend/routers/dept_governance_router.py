"""Department Governance (Iter 48) — Phase 2 of dept-based restructure.

Bundles three deliverables:
  D — Cross-department dependency enforcement
      • Endpoint: POST /dept-gov/invoices/{id}/verify  (Accounts verifies a vendor invoice)
      • Endpoint: POST /dept-gov/payments-out          (Finance pays a verified invoice; rejects unverified)
      • Endpoint: POST /dept-gov/payroll/check-attendance (preflight before payroll run)
      (Material outward ↔ approved PR enforcement is implemented directly in store_router.)
  E — Inter-department delay / performance reports
      • GET /dept-gov/reports/handoff-delays  — avg approval / handoff turnaround per doc-type
      • GET /dept-gov/reports/dept-performance — count + amount of records owned by each dept
      • GET /dept-gov/reports/dept-manpower    — active deployments per dept
  F — Department audit trail viewer
      • GET /dept-gov/audit/by-dept?dept=&date_from=&date_to= — filter audit_logs by ownership_department
      • GET /dept-gov/audit/record/{collection}/{record_id}    — full chain (created → approved → modified)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, now_iso, new_id
from sequences import next_dept_doc

logger = logging.getLogger("erp.dept_gov")
router = APIRouter(prefix="/dept-gov", tags=["department-governance"])


# ════════════════════════════════════════════════════════════════════════
# D — Cross-Department Dependency Enforcement
# ════════════════════════════════════════════════════════════════════════
ACCOUNTS_ROLES = {"super_admin", "accounts_executive", "general_manager", "director"}
FINANCE_ROLES = {"super_admin", "accounts_executive", "general_manager", "director"}
HR_ROLES = {"super_admin", "hr_executive", "general_manager", "director"}


class InvoiceVerifyIn(BaseModel):
    verified: bool = True
    note: str = ""


@router.post("/invoices/{invoice_id}/verify")
async def verify_vendor_invoice(invoice_id: str, payload: InvoiceVerifyIn, user: dict = Depends(get_current_user)):
    """Accounts verifies a vendor invoice. Without this step, Finance cannot pay it."""
    if user.get("role") not in ACCOUNTS_ROLES:
        raise HTTPException(status_code=403, detail="accounts/finance only")
    inv = await db.vendor_invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="vendor invoice not found")
    new_status = "verified" if payload.verified else "rejected"
    update = {
        "status": new_status,
        "verified_at": now_iso() if payload.verified else None,
        "verified_by": (user.get("name") or user.get("email")) if payload.verified else None,
        "verified_by_id": user.get("id") if payload.verified else None,
        "verification_note": payload.note,
    }
    await db.vendor_invoices.update_one({"id": invoice_id}, {"$set": update})
    return {"ok": True, "status": new_status, "invoice_no": inv.get("invoice_no") or inv.get("submission_no")}


class PaymentOutIn(BaseModel):
    invoice_id: str
    amount: float = Field(gt=0)
    mode: str           # bank_transfer | cheque | upi | cash
    payment_date: str   # YYYY-MM-DD
    bank_name: str = ""
    voucher_no: str = ""
    txn_no: str = ""
    remarks: str = ""


@router.post("/payments-out")
async def make_payment_out(payload: PaymentOutIn, user: dict = Depends(get_current_user)):
    """Finance pays a verified vendor invoice. **Refuses to pay an unverified invoice**
    — this is the cross-department dependency rule between Accounts and Finance."""
    if user.get("role") not in FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="finance only")
    inv = await db.vendor_invoices.find_one({"id": payload.invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="vendor invoice not found")
    if inv.get("status") != "verified":
        raise HTTPException(
            status_code=400,
            detail=f"cannot pay an unverified invoice (current status: {inv.get('status', 'unknown')}). "
                   "Accounts must verify first via POST /dept-gov/invoices/{id}/verify.",
        )
    total_paid_rows = await db.payments_out.aggregate([
        {"$match": {"invoice_id": payload.invoice_id, "status": {"$ne": "voided"}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    already_paid = total_paid_rows[0]["total"] if total_paid_rows else 0
    if already_paid + payload.amount > float(inv.get("amount", 0)) + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"payment exceeds invoice amount (invoice {inv.get('amount', 0)}, already paid {already_paid})",
        )
    dept_no = await next_dept_doc("payment_out")
    doc = {
        "id": new_id(),
        "dept_doc_no": dept_no["dept_doc_no"],
        "ownership_department": dept_no["owner_dept"],
        **payload.model_dump(),
        "vendor_id": inv.get("vendor_id"),
        "vendor_name": inv.get("vendor_name"),
        "invoice_no": inv.get("invoice_no") or inv.get("submission_no"),
        "status": "paid",
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
    }
    await db.payments_out.insert_one(doc)
    # Flip invoice to "paid" if fully settled
    if already_paid + payload.amount >= float(inv.get("amount", 0)) - 0.01:
        await db.vendor_invoices.update_one({"id": payload.invoice_id},
                                            {"$set": {"status": "paid", "paid_at": now_iso()}})
    doc.pop("_id", None)
    return doc


@router.get("/payments-out")
async def list_payments_out(user: dict = Depends(get_current_user)):
    if user.get("role") not in FINANCE_ROLES | {"director"}:
        raise HTTPException(status_code=403, detail="not allowed")
    rows = await db.payments_out.find({}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return rows


class PayrollPreflightIn(BaseModel):
    month: str   # YYYY-MM


@router.post("/payroll/check-attendance")
async def payroll_attendance_check(payload: PayrollPreflightIn, user: dict = Depends(get_current_user)):
    """HR/Finance preflight: before running payroll for a month, every active employee
    must have an APPROVED attendance row for that month. Returns blockers if any."""
    if user.get("role") not in HR_ROLES:
        raise HTTPException(status_code=403, detail="hr only")
    if not payload.month or len(payload.month) != 7:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    emps = await db.employees.find(
        {"active": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "departments": 1}
    ).to_list(5000)
    blockers: list[dict] = []
    ok_count = 0
    for e in emps:
        att = await db.attendance.find_one(
            {"employee_id": e["id"], "month": payload.month, "status": "approved"},
            {"_id": 0, "id": 1},
        )
        if att:
            ok_count += 1
        else:
            blockers.append({
                "employee_id": e["id"], "name": e.get("name"),
                "code": e.get("employee_id"),
                "department": (e.get("departments") or [None])[0],
            })
    return {
        "month": payload.month,
        "total_employees": len(emps),
        "approved_attendance_count": ok_count,
        "blocker_count": len(blockers),
        "blockers": blockers[:200],
        "can_proceed": len(blockers) == 0,
    }


# ════════════════════════════════════════════════════════════════════════
# E — Inter-Department Delay / Performance Reports
# ════════════════════════════════════════════════════════════════════════
@router.get("/reports/handoff-delays")
async def report_handoff_delays(days: int = 90, user: dict = Depends(get_current_user)):
    """Average turnaround between approval-chain steps for every doc-type, last N days.
    Calculated from `db.approvals.history[*].at` timestamps."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    apprs = await db.approvals.find(
        {"created_at": {"$gte": cutoff}, "history.0": {"$exists": True}},
        {"_id": 0, "type": 1, "history": 1, "created_at": 1, "status": 1},
    ).to_list(5000)
    by_type: dict[str, dict] = {}
    for a in apprs:
        t = a.get("type") or "unknown"
        bucket = by_type.setdefault(t, {"type": t, "samples": 0, "total_minutes": 0.0,
                                         "longest_step_minutes": 0.0, "approved": 0, "rejected": 0})
        if a.get("status") == "approved":
            bucket["approved"] += 1
        elif a.get("status") == "rejected":
            bucket["rejected"] += 1
        try:
            start = datetime.fromisoformat(str(a["created_at"]).replace("Z", "+00:00"))
        except Exception:
            continue
        prev = start
        for h in a.get("history", []):
            try:
                cur = datetime.fromisoformat(str(h["at"]).replace("Z", "+00:00"))
            except Exception:
                continue
            mins = (cur - prev).total_seconds() / 60
            if mins >= 0:
                bucket["total_minutes"] += mins
                bucket["longest_step_minutes"] = max(bucket["longest_step_minutes"], mins)
                bucket["samples"] += 1
            prev = cur
    out = []
    for b in by_type.values():
        avg = b["total_minutes"] / b["samples"] if b["samples"] else 0
        out.append({**b, "avg_minutes_per_step": round(avg, 1), "avg_hours_per_step": round(avg / 60, 2)})
    out.sort(key=lambda x: -x["avg_minutes_per_step"])
    return {"days": days, "rows": out, "generated_at": now_iso()}


@router.get("/reports/dept-performance")
async def report_dept_performance(days: int = 30, user: dict = Depends(get_current_user)):
    """Counts + amounts per `ownership_department` across all transaction collections."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    collections_with_amount = [
        ("purchase_orders", "total"),
        ("ra_bills", "gross"),
        ("payments_in", "amount"),
        ("payments_out", "amount"),
        ("quotations", "total"),
        ("employee_advances", "approved_amount"),
        ("vendor_invoices", "amount"),
    ]
    summary: dict[str, dict] = {}
    for coll, amt_field in collections_with_amount:
        try:
            rows = await db[coll].aggregate([
                {"$match": {"created_at": {"$gte": cutoff}}},
                {"$group": {"_id": "$ownership_department", "count": {"$sum": 1},
                            "amount": {"$sum": {"$ifNull": [f"${amt_field}", 0]}}}},
            ]).to_list(20)
        except Exception:
            rows = []
        for r in rows:
            dept = r["_id"] or "—"
            bucket = summary.setdefault(dept, {"department": dept, "count": 0, "amount": 0.0, "by_doctype": []})
            bucket["count"] += r["count"]
            bucket["amount"] += float(r.get("amount") or 0)
            bucket["by_doctype"].append({"doc_type": coll, "count": r["count"], "amount": r.get("amount", 0)})
    out = sorted(summary.values(), key=lambda x: -x["count"])
    return {"days": days, "rows": out, "generated_at": now_iso()}


@router.get("/reports/dept-manpower")
async def report_dept_manpower(user: dict = Depends(get_current_user)):
    """Active deployments + headcount per department."""
    pipeline = [
        {"$unwind": {"path": "$departments", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": "$departments", "headcount": {"$sum": 1}}},
        {"$sort": {"headcount": -1}},
    ]
    rows = await db.employees.aggregate(pipeline).to_list(50)
    deployed = await db.deployments.aggregate([
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$department", "deployed": {"$sum": 1}}},
    ]).to_list(50)
    dep_map = {r["_id"]: r["deployed"] for r in deployed}
    out = [{"department": r["_id"] or "—", "headcount": r["headcount"], "deployed": dep_map.get(r["_id"], 0),
            "available": r["headcount"] - dep_map.get(r["_id"], 0)} for r in rows]
    return {"rows": out, "generated_at": now_iso()}


# ════════════════════════════════════════════════════════════════════════
# F — Department Audit Trail Viewer
# ════════════════════════════════════════════════════════════════════════
@router.get("/audit/by-dept")
async def audit_by_dept(
    dept: str = "",
    date_from: str = "",
    date_to: str = "",
    action: str = "",
    resource: str = "",
    limit: int = 200,
    user: dict = Depends(get_current_user),
):
    """Filter audit_logs by ownership department of the record, action, resource, date range."""
    if user.get("role") not in {"super_admin", "director", "general_manager", "accounts_executive"}:
        raise HTTPException(status_code=403, detail="not allowed")
    q: dict = {}
    if date_from:
        q.setdefault("at", {})["$gte"] = date_from
    if date_to:
        q.setdefault("at", {})["$lte"] = date_to
    if action:
        q["action"] = action
    if resource:
        q["resource"] = resource
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("at", -1).limit(max(50, min(limit, 1000))).to_list(1000)
    if dept:
        # Filter to logs whose record's ownership_department matches the requested dept
        filtered = []
        for r in rows:
            coll, rid = r.get("resource"), r.get("record_id")
            if not coll or not rid:
                continue
            try:
                rec = await db[coll].find_one({"id": rid}, {"_id": 0, "ownership_department": 1})
            except Exception:
                rec = None
            if rec and rec.get("ownership_department") == dept:
                filtered.append(r)
        rows = filtered
    return {"rows": rows, "count": len(rows), "generated_at": now_iso()}


@router.get("/audit/record/{collection}/{record_id}")
async def audit_record_trail(collection: str, record_id: str, user: dict = Depends(get_current_user)):
    """Full department trail for one record: who in which dept created/approved/modified it."""
    if user.get("role") not in {"super_admin", "director", "general_manager",
                                  "hr_executive", "accounts_executive", "purchase_officer"}:
        raise HTTPException(status_code=403, detail="not allowed")
    try:
        rec = await db[collection].find_one({"id": record_id}, {"_id": 0})
    except Exception:
        raise HTTPException(status_code=400, detail=f"invalid collection: {collection}")
    if not rec:
        raise HTTPException(status_code=404, detail="record not found")
    logs = await db.audit_logs.find(
        {"resource": collection, "record_id": record_id}, {"_id": 0}
    ).sort("at", 1).to_list(500)
    approval = None
    if rec.get("approval_id"):
        approval = await db.approvals.find_one({"id": rec["approval_id"]}, {"_id": 0})
    # Synthesise a unified timeline
    timeline = []
    timeline.append({
        "phase": "created",
        "at": rec.get("created_at"),
        "by": rec.get("created_by"),
        "by_role": rec.get("created_by_role"),
        "department": rec.get("ownership_department"),
    })
    if approval and approval.get("history"):
        for h in approval["history"]:
            timeline.append({"phase": "approval", "at": h.get("at"), "by": h.get("approver"),
                              "by_role": h.get("role"), "department": h.get("dept"),
                              "action": h.get("action"), "comment": h.get("comment")})
    for log in logs:
        if log.get("action") in {"update", "delete"}:
            timeline.append({"phase": log["action"], "at": log.get("at"),
                              "by": log.get("user_name") or log.get("user_id"),
                              "by_role": log.get("user_role"), "ip": log.get("ip")})
    return {
        "record": {"id": record_id, "collection": collection,
                    "ownership_department": rec.get("ownership_department"),
                    "dept_doc_no": rec.get("dept_doc_no")},
        "timeline": sorted(timeline, key=lambda x: x.get("at") or ""),
        "approval": approval,
        "audit_log_count": len(logs),
    }
