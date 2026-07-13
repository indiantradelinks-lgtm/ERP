"""Finance Phase 8 — Automation, Alerts & Follow-up (Iter 115).

Audit-first finding: alert *data* already exists scattered across
finance_phase4_5 (project alerts), finance_phase6 (compliance calendar),
finance_phase7 (dashboard summary), procurement_extras (notifications).
What's missing: a **follow-up workbench** and a **unified alerts feed**.

Endpoints:
  Receivable Follow-ups
    GET    /finance/followups
    GET    /finance/followups/inbox          (auto-identify due-soon/overdue invoices)
    POST   /finance/followups                (create/assign)
    POST   /finance/followups/{id}/update    (status / remarks / next date)

  Unified Alerts Feed
    GET    /finance/alerts/feed              (consolidates AR/AP/compliance/budget)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, new_id, now_iso
from audit import audit

router = APIRouter(prefix="/finance", tags=["finance-phase8"])

FOLLOWUP_STATUSES = ("pending", "committed", "disputed", "received", "escalated")
ESCALATION_DAYS_DEFAULT = 14


def _today():
    return datetime.now(timezone.utc).date()


# ═════════════════════════════════════════════════════════════════════════
# FOLLOW-UPS
# ═════════════════════════════════════════════════════════════════════════
class FollowupIn(BaseModel):
    invoice_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    assigned_to: Optional[str] = None
    next_followup_date: Optional[str] = None
    status: str = "pending"
    remarks: Optional[str] = None
    attachments: List[Dict[str, Any]] = []


class FollowupUpdate(BaseModel):
    status: Optional[str] = None
    remarks: Optional[str] = None
    next_followup_date: Optional[str] = None
    assigned_to: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


@router.get("/followups")
async def list_followups(status: Optional[str] = None,
                         assigned_to: Optional[str] = None,
                         user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if assigned_to:
        q["assigned_to"] = assigned_to
    rows = await db.receivable_followups.find(q, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return rows


@router.get("/followups/inbox")
async def followups_inbox(days_ahead: int = 7,
                          user: dict = Depends(require_permission("accounting", "read"))):
    """Auto-identifies invoices needing a follow-up.

    Categories:
      • overdue       past due_date, no follow-up yet
      • due_soon      due in next `days_ahead` days
      • partly_paid   payment_status=partial, no recent follow-up
      • tds_unrec     tds_amount > 0 and tds_reconciled != true
      • retention_due retention_amount > 0 and retention_status != released
    """
    today = _today()
    today_s = today.strftime("%Y-%m-%d")
    soon_s = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    existing_followup_invoice_ids = set()
    async for f in db.receivable_followups.find({"status": {"$ne": "received"}},
                                                 {"_id": 0, "invoice_id": 1}):
        existing_followup_invoice_ids.add(f.get("invoice_id"))

    out = []
    async for inv in db.client_invoices.find(
        {"status": {"$in": ["approved", "sent"]}},
        {"_id": 0, "id": 1, "invoice_number": 1, "client_id": 1, "client_name": 1,
         "due_date": 1, "amount": 1, "outstanding": 1, "total_amount": 1,
         "payment_status": 1, "tds_amount": 1, "tds_reconciled": 1,
         "retention_amount": 1, "retention_status": 1, "project_id": 1},
    ):
        amt = float(inv.get("outstanding") or inv.get("amount") or inv.get("total_amount") or 0)
        if amt <= 0 and inv.get("payment_status") != "partial":
            continue
        due = inv.get("due_date") or "9999-12-31"
        kind = None
        if due < today_s:
            kind = "overdue"
        elif due <= soon_s:
            kind = "due_soon"
        elif inv.get("payment_status") == "partial":
            kind = "partly_paid"
        elif float(inv.get("tds_amount") or 0) > 0 and not inv.get("tds_reconciled"):
            kind = "tds_unrec"
        elif float(inv.get("retention_amount") or 0) > 0 and (inv.get("retention_status") or "") != "released":
            kind = "retention_due"
        if not kind:
            continue
        out.append({
            "kind": kind,
            "invoice_id": inv["id"],
            "invoice_number": inv.get("invoice_number"),
            "client_id": inv.get("client_id"),
            "client_name": inv.get("client_name"),
            "project_id": inv.get("project_id"),
            "due_date": inv.get("due_date"),
            "amount_outstanding": round(amt, 2),
            "has_followup": inv["id"] in existing_followup_invoice_ids,
            "age_days": max((today - datetime.strptime(due[:10], "%Y-%m-%d").date()).days, 0) if due < today_s else None,
        })
    # sort: overdue oldest first, then due_soon
    out.sort(key=lambda r: (0 if r["kind"] == "overdue" else 1,
                            -(r.get("age_days") or 0),
                            r.get("due_date") or ""))
    return {"count": len(out), "rows": out}


@router.post("/followups")
async def create_followup(payload: FollowupIn, request: Request,
                          user: dict = Depends(require_permission("accounting", "write"))):
    if payload.status not in FOLLOWUP_STATUSES:
        raise HTTPException(400, f"status must be one of {FOLLOWUP_STATUSES}")
    inv = await db.client_invoices.find_one({"id": payload.invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["invoice_number"] = inv.get("invoice_number")
    doc["client_id"] = doc.get("client_id") or inv.get("client_id")
    doc["client_name"] = doc.get("client_name") or inv.get("client_name")
    doc["project_id"] = inv.get("project_id")
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    doc["updated_at"] = doc["created_at"]
    doc["updated_by"] = doc["created_by"]
    doc["history"] = [{
        "ts": doc["created_at"], "by": doc["created_by"],
        "status": doc["status"], "remarks": doc.get("remarks") or "",
    }]
    await db.receivable_followups.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="receivable_followups",
                record_id=doc["id"], after=doc,
                ip=request.client.host if request.client else "")
    return doc


@router.post("/followups/{fid}/update")
async def update_followup(fid: str, payload: FollowupUpdate, request: Request,
                          user: dict = Depends(require_permission("accounting", "write"))):
    fu = await db.receivable_followups.find_one({"id": fid}, {"_id": 0})
    if not fu:
        raise HTTPException(404, "Follow-up not found")
    if payload.status and payload.status not in FOLLOWUP_STATUSES:
        raise HTTPException(400, f"status must be one of {FOLLOWUP_STATUSES}")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "Nothing to update")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    history = fu.get("history") or []
    history.append({"ts": patch["updated_at"], "by": patch["updated_by"],
                    "status": patch.get("status") or fu.get("status"),
                    "remarks": patch.get("remarks") or ""})
    patch["history"] = history
    await db.receivable_followups.update_one({"id": fid}, {"$set": patch})
    await audit(user=user, action="update", resource="receivable_followups",
                record_id=fid, before={"status": fu.get("status")},
                after={"status": patch.get("status")},
                ip=request.client.host if request.client else "")
    return await db.receivable_followups.find_one({"id": fid}, {"_id": 0})


@router.post("/followups/escalate-stale")
async def escalate_stale(stale_days: int = ESCALATION_DAYS_DEFAULT,
                         request: Request = None,
                         user: dict = Depends(require_permission("accounting", "write"))):
    """Bulk-escalate follow-ups whose last update is older than `stale_days`."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat()
    q = {"status": {"$in": ["pending", "committed"]}, "updated_at": {"$lt": cutoff}}
    n = 0
    async for fu in db.receivable_followups.find(q, {"_id": 0, "id": 1, "history": 1}):
        history = fu.get("history") or []
        history.append({"ts": now_iso(), "by": "system",
                        "status": "escalated", "remarks": f"Auto-escalated after {stale_days} days inactivity"})
        await db.receivable_followups.update_one(
            {"id": fu["id"]},
            {"$set": {"status": "escalated", "updated_at": now_iso(),
                      "updated_by": "system", "history": history}},
        )
        n += 1
    return {"escalated": n, "stale_days": stale_days}


# ═════════════════════════════════════════════════════════════════════════
# UNIFIED ALERTS FEED
# ═════════════════════════════════════════════════════════════════════════
@router.get("/alerts/feed")
async def alerts_feed(user: dict = Depends(require_permission("accounting", "read"))):
    """Consolidated alerts across AR / AP / Compliance / Approvals / Budget."""
    today = _today()
    today_s = today.strftime("%Y-%m-%d")
    plus7 = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    alerts: List[Dict[str, Any]] = []

    # AR overdue
    n = await db.client_invoices.count_documents({
        "status": {"$in": ["approved", "sent"]},
        "payment_status": {"$ne": "paid"},
        "due_date": {"$lt": today_s},
    })
    if n:
        alerts.append({"kind": "ar_overdue", "severity": "critical",
                       "title": f"{n} client invoice(s) overdue", "count": n,
                       "link": "/app/accounts/dashboard"})

    # AP due within 7 days
    n = await db.vendor_bills.count_documents({
        "status": "approved", "payment_status": {"$ne": "paid"},
        "due_date": {"$gte": today_s, "$lte": plus7},
    })
    if n:
        alerts.append({"kind": "ap_due_soon", "severity": "warning",
                       "title": f"{n} vendor payment(s) due in 7 days", "count": n,
                       "link": "/app/vendor-bills"})

    # AP overdue
    n = await db.vendor_bills.count_documents({
        "status": "approved", "payment_status": {"$ne": "paid"},
        "due_date": {"$lt": today_s},
    })
    if n:
        alerts.append({"kind": "ap_overdue", "severity": "critical",
                       "title": f"{n} vendor payment(s) overdue", "count": n,
                       "link": "/app/vendor-bills"})

    # Compliance overdue
    n = await db.compliance_items.count_documents({
        "status": {"$ne": "paid"}, "due_date": {"$lt": today_s},
    })
    if n:
        alerts.append({"kind": "compliance_overdue", "severity": "critical",
                       "title": f"{n} compliance item(s) overdue", "count": n,
                       "link": "/app/accounts/compliance"})

    # Pending approvals
    pa = (
        await db.client_invoices.count_documents({"status": "pending_approval"})
        + await db.vendor_bills.count_documents({"status": {"$in": ["pending_verification", "pending_approval"]}})
        + await db.journal_entries.count_documents({"status": "pending_approval"})
        + await db.finance_notes.count_documents({"status": "pending_approval"})
    )
    if pa:
        alerts.append({"kind": "approvals_pending", "severity": "warning",
                       "title": f"{pa} item(s) pending finance approval", "count": pa,
                       "link": "/app/accounts/dashboard"})

    # Follow-ups: escalated
    n = await db.receivable_followups.count_documents({"status": "escalated"})
    if n:
        alerts.append({"kind": "followup_escalated", "severity": "critical",
                       "title": f"{n} follow-up(s) escalated", "count": n,
                       "link": "/app/accounts/followups"})

    # Follow-ups: pending inbox count
    inbox = await followups_inbox(days_ahead=7, user=user)
    needs_attention = sum(1 for r in inbox["rows"] if not r["has_followup"])
    if needs_attention:
        alerts.append({"kind": "followup_needed", "severity": "warning",
                       "title": f"{needs_attention} invoice(s) need follow-up assignment", "count": needs_attention,
                       "link": "/app/accounts/followups"})

    return {
        "total": sum(a["count"] for a in alerts),
        "critical": sum(a["count"] for a in alerts if a["severity"] == "critical"),
        "alerts": alerts,
    }
