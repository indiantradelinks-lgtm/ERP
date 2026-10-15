"""Platform cron endpoints (.emergent/crons.yml calls these)."""
import hmac
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from core import db, now_iso

router = APIRouter(prefix="/cron", tags=["cron"])
logger = logging.getLogger("erp")


def _authorise(authorization: str | None):
    secret = os.environ.get("WEBHOOK_CRON_SECRET")
    if not secret:
        raise HTTPException(401, "Cron secret not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    if not hmac.compare_digest(authorization.split(" ", 1)[1].strip(), secret):
        raise HTTPException(401, "Invalid cron token")


async def _run_monthly_service_drafts(run_id: str):
    from routers.service_recurring_router import auto_draft_current_month
    try:
        result = await auto_draft_current_month()
        await db.cron_runs.update_one({"run_id": run_id},
                                      {"$set": {"status": "done", "result": result,
                                                "finished_at": now_iso()}})
        logger.info("[cron] monthly service drafts: %s", result)
    except Exception as e:
        await db.cron_runs.update_one({"run_id": run_id},
                                      {"$set": {"status": "failed", "error": str(e),
                                                "finished_at": now_iso()}})
        logger.exception("[cron] monthly service drafts failed")


@router.post("/monthly-service-payments")
async def monthly_service_payments(request: Request, background: BackgroundTasks,
                                   authorization: str | None = Header(default=None),
                                   x_webhook_id: str | None = Header(default=None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _authorise(authorization)
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    run_id = x_webhook_id or body.get("run_id") or now_iso()
    existing = await db.cron_runs.find_one({"run_id": run_id}, {"_id": 0, "status": 1})
    if existing:
        return {"ok": True, "duplicate": True, "run_id": run_id}
    await db.cron_runs.insert_one({"run_id": run_id, "job": "monthly-service-payments",
                                   "status": "queued", "started_at": now_iso()})
    background.add_task(_run_monthly_service_drafts, run_id)
    return {"ok": True, "queued": True, "run_id": run_id}
