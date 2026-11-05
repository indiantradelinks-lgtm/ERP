"""Permanent performance monitoring + automated housekeeping.

Collects process RSS/CPU, event-loop lag, disk, Mongo size and per-request
timings (slow requests kept for the dashboard), samples them every 5 minutes
(leader replica only, 30-day history) and raises in-app + email alerts when a
configurable threshold is crossed. Housekeeping removes only technical debris
(temp files, expired queue rows, stale technical logs) — never business data.
"""
from __future__ import annotations

import asyncio
import collections
import ctypes
import gc
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone

from starlette.middleware.base import BaseHTTPMiddleware

from core import db, now_iso, new_id

logger = logging.getLogger("erp.health")

DEFAULT_SETTINGS = {
    "mem_warn_pct": 75, "mem_crit_pct": 90,
    "disk_warn_pct": 75, "disk_crit_pct": 90,
    "db_warn_mb": 2048,
    "slow_ms": 1500,
    "alert_cooldown_hours": 6,
    "alert_emails": [],
    "retention_enabled": True,
    "retention": {
        "temp_file_hours": 2,
        "login_activity_days": 180,
        "notifications_read_days": 90,
        "email_outbox_body_days": 180,
        "health_samples_days": 30,
    },
}

_slow: collections.deque = collections.deque(maxlen=100)
_durations: collections.deque = collections.deque(maxlen=2000)
_counters = {"requests": 0, "errors_5xx": 0, "started_at": time.time()}
_loop_lag = {"max_ms": 0.0, "ewma_ms": 0.0}
_last_cpu = {"t": time.time(), "ticks": 0.0}
_settings_cache: dict | None = None
_libc = None


# ── memory tuning ───────────────────────────────────────────────────────
def tune_malloc() -> None:
    """Fewer glibc arenas + eager trim: long-lived Python servers otherwise keep
    freed heap pages resident for hours after a heavy export."""
    global _libc
    try:
        _libc = ctypes.CDLL("libc.so.6")
        _libc.mallopt(-8, 2)        # M_ARENA_MAX = 2
        _libc.mallopt(-1, 128 * 1024)  # M_TRIM_THRESHOLD = 128 KB
    except Exception as e:  # noqa: BLE001 — non-glibc platform
        logger.info(f"malloc tuning unavailable: {e}")


def trim_memory() -> None:
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:  # noqa: BLE001
            pass


# ── raw probes ──────────────────────────────────────────────────────────
def _read(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def rss_mb() -> float:
    for line in _read("/proc/self/status").splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return 0.0


def mem_limit_mb() -> float:
    raw = _read("/sys/fs/cgroup/memory.max") or _read("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if raw.isdigit() and int(raw) < 1 << 50:
        return round(int(raw) / 1024 / 1024, 1)
    for line in _read("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            return round(int(line.split()[1]) / 1024, 1)
    return 0.0


def cpu_quota_cores() -> float:
    raw = _read("/sys/fs/cgroup/cpu.max")
    if raw and not raw.startswith("max"):
        q, p = raw.split()[:2]
        return round(int(q) / int(p), 2)
    return float(os.cpu_count() or 1)


def cpu_pct() -> float:
    """Process CPU since the previous call, as % of the container's CPU quota."""
    parts = _read("/proc/self/stat").split(")")[-1].split()
    ticks = (int(parts[11]) + int(parts[12])) / os.sysconf("SC_CLK_TCK")
    now = time.time()
    dt = now - _last_cpu["t"]
    used = ticks - _last_cpu["ticks"]
    _last_cpu.update(t=now, ticks=ticks)
    if dt <= 0:
        return 0.0
    return round(100 * used / dt / cpu_quota_cores(), 1)


def disk_usage(path: str) -> dict:
    try:
        u = shutil.disk_usage(path)
        return {"path": path, "total_gb": round(u.total / 1e9, 2), "used_gb": round(u.used / 1e9, 2),
                "pct": round(100 * u.used / u.total, 1) if u.total else 0}
    except OSError:
        return {"path": path, "total_gb": 0, "used_gb": 0, "pct": 0}


async def db_stats() -> dict:
    out = {"data_mb": 0, "index_mb": 0, "storage_mb": 0, "collections": 0, "connections": None}
    try:
        st = await db.command("dbStats")
        out.update(data_mb=round(st["dataSize"] / 1e6, 1), index_mb=round(st["indexSize"] / 1e6, 1),
                   storage_mb=round(st["storageSize"] / 1e6, 1), collections=st["collections"], indexes=st["indexes"])
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:120]
    try:
        ss = await db.command("serverStatus")
        out["connections"] = (ss.get("connections") or {}).get("current")
    except Exception:  # noqa: BLE001
        pass
    return out


def _pct(values, q):
    if not values:
        return 0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * len(s)))], 0)


def request_stats() -> dict:
    d = list(_durations)
    return {"count": _counters["requests"], "errors_5xx": _counters["errors_5xx"],
            "since": datetime.fromtimestamp(_counters["started_at"], tz=timezone.utc).isoformat(),
            "window": len(d), "avg_ms": round(sum(d) / len(d), 0) if d else 0,
            "p50_ms": _pct(d, 0.5), "p95_ms": _pct(d, 0.95), "max_ms": max(d) if d else 0}


# ── settings ────────────────────────────────────────────────────────────
async def get_settings() -> dict:
    global _settings_cache
    if _settings_cache is None:
        doc = await db.settings.find_one({"_id": "system_health"}, {"_id": 0}) or {}
        merged = {**DEFAULT_SETTINGS, **doc}
        merged["retention"] = {**DEFAULT_SETTINGS["retention"], **(doc.get("retention") or {})}
        _settings_cache = merged
    return dict(_settings_cache)


async def save_settings(payload: dict) -> dict:
    global _settings_cache
    clean = {k: payload[k] for k in DEFAULT_SETTINGS if k in payload}
    if "retention" in clean:
        clean["retention"] = {k: int(v) for k, v in clean["retention"].items() if k in DEFAULT_SETTINGS["retention"]}
    clean["updated_at"] = now_iso()
    await db.settings.update_one({"_id": "system_health"}, {"$set": clean}, upsert=True)
    _settings_cache = None
    return await get_settings()


# ── middleware + loop lag ──────────────────────────────────────────────
class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            ms = (time.perf_counter() - started) * 1000
            path = request.url.path
            if path.startswith("/api/"):
                _counters["requests"] += 1
                if status >= 500:
                    _counters["errors_5xx"] += 1
                _durations.append(ms)
                slow_ms = (_settings_cache or DEFAULT_SETTINGS)["slow_ms"]
                if ms >= slow_ms:
                    route = request.scope.get("route")
                    _slow.appendleft({"at": now_iso(), "method": request.method, "path": path,
                                      "route": getattr(route, "path", None), "ms": round(ms), "status": status})
                    logger.warning(f"[slow-request] {request.method} {path} {ms:.0f} ms → {status}")


async def _loop_lag_task():
    while True:
        t = time.perf_counter()
        await asyncio.sleep(1.0)
        lag = max(0.0, (time.perf_counter() - t - 1.0) * 1000)
        _loop_lag["ewma_ms"] = round(0.8 * _loop_lag["ewma_ms"] + 0.2 * lag, 1)
        _loop_lag["max_ms"] = round(max(_loop_lag["max_ms"], lag), 1)


def install(app) -> None:
    app.add_middleware(RequestTimingMiddleware)


async def start_background() -> None:
    cpu_pct()  # prime the delta
    asyncio.get_running_loop().create_task(_loop_lag_task())
    await db.system_health_samples.create_index("at_dt", expireAfterSeconds=30 * 86400)
    await db.system_health_alerts.create_index("key", unique=True)


# ── snapshot + alerting ────────────────────────────────────────────────
async def snapshot() -> dict:
    from scheduler import scheduler_status
    limit = mem_limit_mb()
    rss = rss_mb()
    tmpdir = tempfile.gettempdir()
    snap = {
        "at": now_iso(),
        "process": {"rss_mb": rss, "mem_limit_mb": limit,
                    "mem_pct": round(100 * rss / limit, 1) if limit else None,
                    "cpu_pct_of_quota": cpu_pct(), "cpu_quota_cores": cpu_quota_cores(),
                    "loop_lag_ewma_ms": _loop_lag["ewma_ms"], "loop_lag_max_ms": _loop_lag["max_ms"],
                    "uptime_min": round((time.time() - _counters["started_at"]) / 60),
                    "litellm_loaded": "litellm" in __import__("sys").modules},
        "disk": {"app": disk_usage("/app"), "tmp": disk_usage(tmpdir)},
        "db": await db_stats(),
        "requests": request_stats(),
        "scheduler": {"leader": bool(scheduler_status().get("running"))},
    }
    _loop_lag["max_ms"] = 0.0
    return snap


async def _alert(key: str, level: str, title: str, message: str, settings: dict) -> bool:
    cooldown = timedelta(hours=float(settings.get("alert_cooldown_hours") or 6))
    now = datetime.now(timezone.utc)
    prev = await db.system_health_alerts.find_one({"key": key})
    if prev and prev.get("last_sent_dt") and now - prev["last_sent_dt"].replace(tzinfo=timezone.utc) < cooldown:
        return False
    await db.system_health_alerts.update_one(
        {"key": key}, {"$set": {"level": level, "title": title, "message": message,
                                "last_sent_dt": now, "last_sent": now_iso()}, "$inc": {"count": 1}}, upsert=True)
    admins = await db.users.find({"role": "super_admin", "is_active": {"$ne": False}},
                                 {"_id": 0, "id": 1, "email": 1}).to_list(50)
    for a in admins:
        await db.notifications.insert_one({"id": new_id(), "user_id": a["id"], "kind": "system_health",
                                           "title": title, "message": message, "link": "/app/admin/system-health",
                                           "meta": {"level": level, "key": key}, "read": False, "at": now_iso()})
    emails = set(settings.get("alert_emails") or []) | {a["email"] for a in admins if a.get("email")}
    try:
        from notification_service import send_email
        for to in emails:
            await send_email(to, f"[ERP {level.upper()}] {title}", f"<p>{message}</p><p>Open Admin → System Health for details.</p>")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"health alert email skipped: {e}")
    logger.warning(f"[health-alert] {level}: {title} — {message}")
    return True


async def sample_and_alert() -> dict:
    settings = await get_settings()
    snap = await snapshot()
    row = {"at": snap["at"], "at_dt": datetime.now(timezone.utc),
           "rss_mb": snap["process"]["rss_mb"], "mem_pct": snap["process"]["mem_pct"],
           "cpu_pct": snap["process"]["cpu_pct_of_quota"], "loop_lag_ms": snap["process"]["loop_lag_ewma_ms"],
           "disk_pct": snap["disk"]["app"]["pct"], "db_mb": snap["db"]["data_mb"] + snap["db"]["index_mb"],
           "req_count": snap["requests"]["count"], "p95_ms": snap["requests"]["p95_ms"],
           "slow_count": len(_slow)}
    await db.system_health_samples.insert_one(row)
    fired = []
    mp, dp, dbm = row["mem_pct"] or 0, row["disk_pct"], row["db_mb"]
    if mp >= settings["mem_crit_pct"]:
        fired.append(await _alert("mem", "critical", "Backend memory critical",
                                  f"RSS {row['rss_mb']} MB = {mp}% of the {snap['process']['mem_limit_mb']} MB limit.", settings))
    elif mp >= settings["mem_warn_pct"]:
        fired.append(await _alert("mem", "warning", "Backend memory high",
                                  f"RSS {row['rss_mb']} MB = {mp}% of the {snap['process']['mem_limit_mb']} MB limit.", settings))
    if dp >= settings["disk_crit_pct"]:
        fired.append(await _alert("disk", "critical", "Server disk nearly full", f"/app is {dp}% used.", settings))
    elif dp >= settings["disk_warn_pct"]:
        fired.append(await _alert("disk", "warning", "Server disk filling up", f"/app is {dp}% used.", settings))
    if dbm >= settings["db_warn_mb"]:
        fired.append(await _alert("db", "warning", "Database size threshold reached",
                                  f"Data + indexes = {dbm:.0f} MB (threshold {settings['db_warn_mb']} MB).", settings))
    return {"sampled": True, "alerts_sent": sum(1 for f in fired if f), **{k: row[k] for k in ("rss_mb", "mem_pct", "cpu_pct", "disk_pct", "db_mb")}}


# ── housekeeping (technical debris only) ───────────────────────────────
def _purge_temp_files(max_age_hours: int) -> dict:
    cutoff = time.time() - max_age_hours * 3600
    removed = freed = 0
    tmpdir = tempfile.gettempdir()
    for name in os.listdir(tmpdir):
        p = os.path.join(tmpdir, name)
        try:
            st = os.stat(p)
            if os.path.isfile(p) and st.st_mtime < cutoff and not name.startswith("."):
                os.remove(p)
                removed += 1
                freed += st.st_size
        except OSError:
            continue
    return {"removed": removed, "freed_mb": round(freed / 1e6, 2)}


async def housekeeping() -> dict:
    settings = await get_settings()
    r = settings["retention"]
    result = {"at": now_iso(), "temp": _purge_temp_files(int(r["temp_file_hours"]))}
    if settings.get("retention_enabled", True):
        now = datetime.now(timezone.utc)
        iso = lambda days: (now - timedelta(days=int(days))).isoformat()
        res = await db.login_activity.delete_many({"at": {"$lt": iso(r["login_activity_days"])}})
        result["login_activity_deleted"] = res.deleted_count
        res = await db.notifications.delete_many({"read": True, "at": {"$lt": iso(r["notifications_read_days"])}})
        result["notifications_deleted"] = res.deleted_count
        res = await db.email_outbox.update_many(
            {"status": {"$in": ["sent", "failed"]}, "created_at": {"$lt": iso(r["email_outbox_body_days"])},
             "body_html": {"$exists": True}},
            {"$unset": {"body_html": "", "attachments_inline": ""}, "$set": {"body_pruned_at": now_iso()}})
        result["email_bodies_pruned"] = res.modified_count
        res = await db.cleanup_archive.delete_many({"expires_at_dt": {"$lt": now}})
        result["cleanup_archive_deleted"] = res.deleted_count
    trim_memory()
    result["rss_mb_after"] = rss_mb()
    await db.system_health_runs.insert_one({"id": new_id(), "kind": "housekeeping", **result})
    logger.info(f"[housekeeping] {result}")
    return result


def slow_requests() -> list:
    return list(_slow)
