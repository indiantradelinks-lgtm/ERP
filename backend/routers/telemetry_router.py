"""User telemetry — currently just page-visit logging to power the
personalised Quick Actions on each Department Workspace.

Storage
-------
Collection: `module_visits`
    { user_id, path, dept, ts }

Aggregation
-----------
Top-N most-visited paths per (user, dept) in the last 30 days.

We keep everything intentionally cheap:
    * A single tiny document per navigation
    * A TTL index on `ts` so 60-day-old visits are auto-purged by Mongo
    * A compound index on (user_id, dept, ts) for fast group-by queries
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user


router = APIRouter(tags=["telemetry"])


# ─── Index bootstrap (idempotent) ──────────────────────────────────────────
_indexes_ready = False


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    # 60-day TTL — keeps the collection tiny.
    await db.module_visits.create_index("ts", expireAfterSeconds=60 * 24 * 3600)
    await db.module_visits.create_index([("user_id", 1), ("dept", 1), ("ts", -1)])
    _indexes_ready = True


# ─── Models ────────────────────────────────────────────────────────────────
class VisitIn(BaseModel):
    path: str = Field(..., min_length=1, max_length=200)
    dept: Optional[str] = Field(None, max_length=40)


# ─── Endpoints ─────────────────────────────────────────────────────────────
@router.post("/telemetry/module-visit")
async def record_visit(payload: VisitIn, user: dict = Depends(get_current_user)):
    await _ensure_indexes()
    # We only care about /app/* module routes — the client already filters
    # but we double-guard here.
    path = payload.path.strip()
    if not path.startswith("/app/") or path in {"/app", "/app/", "/app/modules"}:
        return {"ok": True, "skipped": True}
    if path.startswith("/app/modules/"):
        # Landing pages themselves aren't shortcuts — skip.
        return {"ok": True, "skipped": True}
    await db.module_visits.insert_one({
        "user_id": user["id"],
        "path": path,
        "dept": (payload.dept or "").strip() or None,
        "ts": datetime.now(timezone.utc),
    })
    return {"ok": True}


@router.get("/telemetry/top-shortcuts/{dept}")
async def top_shortcuts(
    dept: str,
    limit: int = 6,
    days: int = 30,
    user: dict = Depends(get_current_user),
):
    """Return the user's top-N visited paths in a department over `days` days."""
    if limit < 1 or limit > 20:
        raise HTTPException(status_code=400, detail="limit must be 1..20")
    if days < 1 or days > 180:
        raise HTTPException(status_code=400, detail="days must be 1..180")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"user_id": user["id"], "dept": dept, "ts": {"$gte": since}}},
        {"$group": {"_id": "$path", "count": {"$sum": 1}, "last": {"$max": "$ts"}}},
        {"$sort": {"count": -1, "last": -1}},
        {"$limit": limit},
    ]
    rows = [
        {"path": r["_id"], "count": r["count"], "last": r["last"].isoformat() if r.get("last") else None}
        async for r in db.module_visits.aggregate(pipeline)
    ]
    return {"dept": dept, "days": days, "items": rows, "total_visits": sum(r["count"] for r in rows)}
