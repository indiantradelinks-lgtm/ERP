"""Admin → System Health: live snapshot, 30-day history, slow requests, thresholds, housekeeping."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user
import system_health as sh

router = APIRouter(prefix="/admin/system-health", tags=["system-health"])


def _admin(user: dict) -> None:
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")


class SettingsIn(BaseModel):
    mem_warn_pct: int | None = None
    mem_crit_pct: int | None = None
    disk_warn_pct: int | None = None
    disk_crit_pct: int | None = None
    db_warn_mb: int | None = None
    slow_ms: int | None = None
    alert_cooldown_hours: int | None = None
    alert_emails: list[str] | None = None
    retention_enabled: bool | None = None
    retention: dict | None = None


@router.get("")
async def current(user: dict = Depends(get_current_user)):
    _admin(user)
    snap = await sh.snapshot()
    snap["slow_requests"] = sh.slow_requests()[:20]
    snap["settings"] = await sh.get_settings()
    snap["last_housekeeping"] = await db.system_health_runs.find_one(
        {"kind": "housekeeping"}, {"_id": 0}, sort=[("at", -1)])
    snap["recent_alerts"] = await db.system_health_alerts.find(
        {}, {"_id": 0, "last_sent_dt": 0}).sort("last_sent", -1).to_list(10)
    return snap


@router.get("/history")
async def history(days: int = 7, user: dict = Depends(get_current_user)):
    _admin(user)
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 30)))
    rows = await db.system_health_samples.find({"at_dt": {"$gte": since}}, {"_id": 0, "at_dt": 0}) \
        .sort("at", 1).to_list(10000)
    return rows


@router.put("/settings")
async def update_settings(payload: SettingsIn, user: dict = Depends(get_current_user)):
    _admin(user)
    return await sh.save_settings(payload.model_dump(exclude_none=True))


@router.post("/housekeeping/run")
async def run_housekeeping(user: dict = Depends(get_current_user)):
    _admin(user)
    return await sh.housekeeping()


@router.post("/sample-now")
async def sample_now(user: dict = Depends(get_current_user)):
    _admin(user)
    return await sh.sample_and_alert()


@router.post("/trim-memory")
async def trim(user: dict = Depends(get_current_user)):
    _admin(user)
    before = sh.rss_mb()
    sh.trim_memory()
    return {"rss_before_mb": before, "rss_after_mb": sh.rss_mb()}
