"""APScheduler setup for nightly notifications."""
import asyncio
import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from routers.notifications_router import run_expiry_scan, run_invoice_reminders

logger = logging.getLogger("erp.scheduler")

_scheduler: AsyncIOScheduler | None = None
_last_results: dict = {"expiry_scan": None, "invoice_reminders": None, "shortage_scan": None, "email_retry": None, "onedrive_push": None, "onedrive_backup": None, "approval_reminders": None}


async def _expiry_job():
    try:
        result = await run_expiry_scan()
        _last_results["expiry_scan"] = {"at": datetime.utcnow().isoformat(), **result}
        logger.info(f"Nightly expiry-scan complete: {result}")
    except Exception as e:
        logger.exception(f"Nightly expiry-scan failed: {e}")


async def _invoice_job():
    try:
        result = await run_invoice_reminders()
        _last_results["invoice_reminders"] = {"at": datetime.utcnow().isoformat(), **result}
        logger.info(f"Weekly invoice-reminders complete: {result}")
    except Exception as e:
        logger.exception(f"Weekly invoice-reminders failed: {e}")


async def _shortage_job():
    """Daily manpower-shortage scan. Aggregates open requisitions vs active
    deployments and emails a digest to HR + Operations when shortfalls exist.
    """
    try:
        from routers.allocation_router import compute_manpower_shortages
        from notification_service import email_enabled, send_email
        from core import db
        rows = await compute_manpower_shortages()
        total = sum(r["shortfall"] for r in rows)
        _last_results["shortage_scan"] = {"at": datetime.utcnow().isoformat(), "total_shortfall": total, "rows": len(rows)}
        logger.info(f"Daily shortage scan: {len(rows)} flagged, total shortfall={total}")
        if rows and email_enabled():
            recipients = await db.users.find(
                {"role": {"$in": ["hr_executive", "general_manager", "director"]}},
                {"_id": 0, "email": 1, "name": 1},
            ).to_list(50)
            if recipients:
                summary_rows = "\n".join(
                    f" • {r['position']} ({r['department']}) — short by {r['shortfall']} (needed by {r.get('needed_by','—')})"
                    for r in rows[:10]
                )
                body = (
                    f"Daily manpower shortage scan flagged {len(rows)} requisition(s) "
                    f"with a combined shortfall of {total} headcount.\n\n{summary_rows}"
                )
                for u in recipients:
                    if u.get("email"):
                        await send_email(u["email"], "[ERP] Manpower shortage digest", body)
    except Exception as e:
        logger.exception(f"Daily shortage scan failed: {e}")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    tz = os.environ.get("SCHEDULER_TZ", "UTC")
    _scheduler = AsyncIOScheduler(timezone=tz)
    # Nightly expiry scan @ 09:00 UTC
    _scheduler.add_job(_expiry_job, CronTrigger(hour=9, minute=0), id="expiry_scan", replace_existing=True)
    # Weekly invoice reminders — Mondays @ 09:00 UTC
    _scheduler.add_job(_invoice_job, CronTrigger(day_of_week="mon", hour=9, minute=0), id="invoice_reminders", replace_existing=True)
    # Daily manpower shortage scan @ 07:30 UTC (1.5h before standup)
    _scheduler.add_job(_shortage_job, CronTrigger(hour=7, minute=30), id="shortage_scan", replace_existing=True)
    # Email outbox retry — every 10 minutes
    _scheduler.add_job(_email_retry_job, IntervalTrigger(minutes=10), id="email_retry", replace_existing=True)
    # OneDrive push queue worker — every 2 minutes
    _scheduler.add_job(_onedrive_push_job, IntervalTrigger(minutes=2), id="onedrive_push", replace_existing=True)
    # Nightly OneDrive DB backup @ 18:30 UTC (midnight IST)
    _scheduler.add_job(_onedrive_backup_job, CronTrigger(hour=18, minute=30), id="onedrive_backup", replace_existing=True)
    # Iter 51 — Approval reminders + escalation @ 08:00 UTC daily
    _scheduler.add_job(_approval_reminder_job, CronTrigger(hour=8, minute=0),
                       id="approval_reminders", replace_existing=True)
    _scheduler.start()
    logger.info(
        f"Scheduler started (tz={tz}). Jobs: expiry_scan@09:00, invoice_reminders@Mon 09:00, "
        f"shortage_scan@07:30, email_retry@every 10min"
    )


async def _email_retry_job():
    try:
        from routers.email_actions_router import retry_pending_outbox
        result = await retry_pending_outbox()
        _last_results["email_retry"] = {"at": datetime.utcnow().isoformat(), **result}
        if result.get("retried", 0):
            logger.info(f"Email outbox retry: {result}")
    except Exception as e:
        logger.exception(f"Email retry job failed: {e}")


async def _onedrive_push_job():
    try:
        from routers.onedrive_router import run_push_queue
        result = await run_push_queue(limit=25)
        _last_results["onedrive_push"] = {"at": datetime.utcnow().isoformat(), **result}
        if result.get("pushed", 0) or result.get("failed", 0):
            logger.info(f"OneDrive push queue: {result}")
    except Exception as e:
        logger.exception(f"OneDrive push job failed: {e}")


async def _onedrive_backup_job():
    try:
        from routers.onedrive_router import run_db_backup
        result = await run_db_backup()
        _last_results["onedrive_backup"] = {"at": datetime.utcnow().isoformat(), **result}
        logger.info(f"OneDrive nightly backup: {result}")
    except Exception as e:
        logger.exception(f"OneDrive backup job failed: {e}")



async def _approval_reminder_job():
    """Daily reminder + escalation pass.

    Iter 51 (Phase 2):
    - Reminder: if an approval has been sitting on the same step for > reminder_days
      and no email has been sent in the last 24h, email the assigned approver(s).
    - Escalation: if stuck > escalation_days, append an `escalation` history entry
      and notify one rung up (general_manager → director, dept_head → general_manager).
    """
    try:
        from core import db, new_id, now_iso
        from notification_service import send_email, email_enabled, APP_URL
        from datetime import datetime, timezone, timedelta

        cfg = await db.settings.find_one({"_id": "approval_workflow"}, {"_id": 0}) or {}
        if not cfg.get("auto_reminders_enabled", True):
            _last_results["approval_reminders"] = {"at": datetime.utcnow().isoformat(), "skipped": "disabled"}
            return
        reminder_days = int(cfg.get("reminder_days", 1))
        escalation_days = int(cfg.get("escalation_days", 3))
        now = datetime.now(timezone.utc)
        reminder_cutoff = now - timedelta(days=reminder_days)
        escalation_cutoff = now - timedelta(days=escalation_days)

        sent = 0
        escalated = 0
        async for appr in db.approvals.find(
            {"status": {"$in": ["pending", "in_progress"]}}, {"_id": 0}
        ):
            chain = appr.get("chain") or []
            idx = appr.get("current_step") or 0
            if not (0 <= idx < len(chain)):
                continue
            step = chain[idx]
            updated_at = appr.get("updated_at") or appr.get("created_at")
            try:
                ua = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            except Exception:
                continue

            # Skip if recently nudged
            last_nudge = appr.get("last_reminder_at")
            if last_nudge:
                try:
                    ln = datetime.fromisoformat(str(last_nudge).replace("Z", "+00:00"))
                    if (now - ln).total_seconds() < 22 * 3600:
                        continue
                except Exception:
                    pass

            # Escalation path
            if ua < escalation_cutoff and not step.get("escalated"):
                escalation_role = {
                    "supervisor": "dept_head",
                    "dept_head": "general_manager",
                    "purchase_officer": "general_manager",
                    "accounts_executive": "general_manager",
                    "project_manager": "dept_head",
                    "general_manager": "director",
                }.get(step.get("role"))
                step["escalated"] = True
                step["escalated_at"] = now_iso()
                step["escalated_to"] = escalation_role
                chain[idx] = step
                hist = list(appr.get("history") or [])
                hist.append({
                    "action": "escalate",
                    "by": "system", "by_role": "scheduler",
                    "step_index": idx, "step_role": step.get("role"),
                    "comment": f"Auto-escalated to {escalation_role} after "
                               f"{escalation_days}d of inactivity.",
                    "at": now_iso(),
                })
                await db.approvals.update_one(
                    {"id": appr["id"]},
                    {"$set": {"chain": chain, "history": hist,
                              "last_reminder_at": now_iso()}},
                )
                if escalation_role and email_enabled():
                    recipients = await db.users.find(
                        {"role": escalation_role}, {"_id": 0, "email": 1, "name": 1}
                    ).to_list(20)
                    for u in recipients:
                        if u.get("email"):
                            await send_email(
                                u["email"],
                                f"[Escalation] {appr.get('title') or 'Approval'} "
                                f"pending {escalation_days}d+",
                                f"<p>Approval <strong>{appr.get('title')}</strong> has been "
                                f"sitting on step <strong>{step.get('label')}</strong> "
                                f"for more than {escalation_days} days. Please review.</p>"
                                f"<p><a href='{APP_URL}/app/approvals'>Open Approvals</a></p>",
                            )
                # In-app notification
                await _push_inapp_for_role(escalation_role, {
                    "type": "approval_escalation",
                    "title": f"Escalated: {appr.get('title')}",
                    "body": f"Pending {escalation_days}d on {step.get('label')}",
                    "link": f"/app/approvals?id={appr['id']}",
                })
                escalated += 1
                continue   # don't also send reminder

            # Reminder
            if ua < reminder_cutoff:
                if email_enabled():
                    recipients = await db.users.find(
                        {"role": step.get("role")}, {"_id": 0, "email": 1, "name": 1}
                    ).to_list(20)
                    for u in recipients:
                        if u.get("email"):
                            await send_email(
                                u["email"],
                                f"[Reminder] Approval pending: {appr.get('title')}",
                                f"<p>Approval <strong>{appr.get('title')}</strong> is awaiting your "
                                f"decision at step <strong>{step.get('label')}</strong>. "
                                f"Please review.</p>"
                                f"<p><a href='{APP_URL}/app/approvals'>Open Approvals</a></p>",
                            )
                await _push_inapp_for_role(step.get("role"), {
                    "type": "approval_reminder",
                    "title": f"Reminder: {appr.get('title')}",
                    "body": f"Pending at {step.get('label')}",
                    "link": f"/app/approvals?id={appr['id']}",
                })
                await db.approvals.update_one(
                    {"id": appr["id"]}, {"$set": {"last_reminder_at": now_iso()}},
                )
                sent += 1

        _last_results["approval_reminders"] = {
            "at": datetime.utcnow().isoformat(),
            "reminders_sent": sent, "escalated": escalated,
        }
        logger.info(f"Approval reminders: sent={sent}, escalated={escalated}")
    except Exception as e:
        logger.exception(f"Approval reminder job failed: {e}")


async def _push_inapp_for_role(role: str, payload: dict) -> None:
    """Fan-out an in-app notification to every user with the given role."""
    if not role:
        return
    from core import db, new_id, now_iso
    users = await db.users.find({"role": role}, {"_id": 0, "id": 1}).to_list(50)
    for u in users:
        if u.get("id"):
            await db.notifications.insert_one({
                "id": new_id(),
                "user_id": u["id"],
                **payload,
                "read": False,
                "at": now_iso(),
            })


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_status() -> dict:
    if not _scheduler:
        return {"running": False}
    jobs = [
        {"id": j.id, "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None, "trigger": str(j.trigger)}
        for j in _scheduler.get_jobs()
    ]
    return {"running": True, "jobs": jobs, "last_results": _last_results}
