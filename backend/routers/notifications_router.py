"""Email notifications: status + ad-hoc scans + helpers used by approvals & scheduler."""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from core import db, get_current_user, logger
from notification_service import (
    send_email, email_enabled,
    tmpl_approval_pending, tmpl_approval_decided,
    tmpl_invoice_reminder, tmpl_doc_expiry, tmpl_ppe_expiry,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def app_url() -> str:
    return os.environ.get("FRONTEND_URL", "")


async def emails_for_role(role: str) -> list[str]:
    rows = await db.users.find({"role": role}, {"_id": 0, "email": 1}).to_list(100)
    return [r["email"] for r in rows if r.get("email")]


async def notify_approval_pending(approval: dict) -> None:
    chain = approval.get("chain") or []
    idx = approval.get("current_step") or 0
    if idx >= len(chain):
        return
    step = chain[idx]
    recipients = await emails_for_role(step.get("role"))
    if not recipients:
        return
    msg = tmpl_approval_pending(approval, step, app_url())
    for r in recipients:
        await send_email(r, msg["subject"], msg["html"])


async def notify_approval_decided(approval: dict, action: str, by: str) -> None:
    recipients: set[str] = set()
    requester = approval.get("requested_by") or ""
    if "@" in requester:
        recipients.add(requester)
    admins = await emails_for_role("super_admin")
    recipients.update(admins)
    msg = tmpl_approval_decided(approval, action, by, app_url())
    for r in recipients:
        await send_email(r, msg["subject"], msg["html"])


async def run_expiry_scan() -> dict:
    """Scan documents AND PPE issuance records that expire in the next 30 days
    and email super_admins + safety_officers."""
    today = datetime.now(timezone.utc).date()
    admins = await emails_for_role("super_admin")
    safety = await emails_for_role("safety_officer")
    recipients = list({*admins, *safety})

    # Documents
    docs = await db.documents.find({"is_deleted": {"$ne": True}, "expiry": {"$ne": None}}, {"_id": 0}).to_list(500)
    docs_sent = 0
    for d in docs:
        exp = d.get("expiry")
        if not exp:
            continue
        try:
            exp_date = datetime.fromisoformat(str(exp)).date()
        except Exception:
            continue
        days_left = (exp_date - today).days
        if days_left <= 30:
            msg = tmpl_doc_expiry(d, days_left, app_url())
            for r in recipients:
                await send_email(r, msg["subject"], msg["html"])
                docs_sent += 1

    # PPE Issuance
    ppe = await db.ppe_issuance.find({"expiry_date": {"$ne": None}}, {"_id": 0}).to_list(2000)
    ppe_sent = 0
    ppe_due = 0
    for p in ppe:
        exp = p.get("expiry_date")
        if not exp:
            continue
        try:
            exp_date = datetime.fromisoformat(str(exp)).date()
        except Exception:
            continue
        days_left = (exp_date - today).days
        if days_left <= 30:
            ppe_due += 1
            msg = tmpl_ppe_expiry(p, days_left, app_url())
            for r in recipients:
                await send_email(r, msg["subject"], msg["html"])
                ppe_sent += 1

    return {
        "documents": {"scanned": len(docs), "sent": docs_sent},
        "ppe": {"scanned": len(ppe), "due": ppe_due, "sent": ppe_sent},
        "email_enabled": email_enabled(),
    }


async def run_invoice_reminders() -> dict:
    """Email super_admins about outstanding invoices (quotations with status=invoiced)."""
    rows = await db.quotations.find({"status": "invoiced"}, {"_id": 0}).to_list(500)
    admins = await emails_for_role("super_admin")
    sent = 0
    for q in rows:
        msg = tmpl_invoice_reminder(q, app_url())
        for r in admins:
            await send_email(r, msg["subject"], msg["html"])
            sent += 1
    return {"scanned": len(rows), "sent": sent, "email_enabled": email_enabled()}


# ---------- HTTP endpoints ----------
@router.get("/email-status")
async def email_status(user: dict = Depends(get_current_user)):
    return {"enabled": email_enabled()}


@router.post("/expiry-scan")
async def expiry_scan(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("super_admin", "director", "general_manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return await run_expiry_scan()


@router.post("/invoice-reminders")
async def invoice_reminders(user: dict = Depends(get_current_user)):
    if user.get("role") not in ("super_admin", "director", "general_manager", "accounts_executive"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return await run_invoice_reminders()
