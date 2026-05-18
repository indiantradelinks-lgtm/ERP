"""APScheduler setup for nightly notifications."""
import asyncio
import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from routers.notifications_router import run_expiry_scan, run_invoice_reminders

logger = logging.getLogger("erp.scheduler")

_scheduler: AsyncIOScheduler | None = None
_last_results: dict = {"expiry_scan": None, "invoice_reminders": None}


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
    _scheduler.start()
    logger.info(f"Scheduler started (tz={tz}). Jobs: expiry_scan@09:00 daily, invoice_reminders@Mon 09:00")


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
