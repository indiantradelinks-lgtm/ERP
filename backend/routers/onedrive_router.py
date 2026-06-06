"""OneDrive admin router — settings, test connection, push queue, DB backup."""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id
from storage import get_object
from rbac import can
import onedrive_service as ods

logger = logging.getLogger("erp.onedrive_router")
router = APIRouter(prefix="/admin/onedrive", tags=["onedrive"])


# ────────────────────────────────────────────────────────────────────────
# Permission helpers — super_admin only
# ────────────────────────────────────────────────────────────────────────
def _require_admin(user: dict) -> None:
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")


# ────────────────────────────────────────────────────────────────────────
# Settings endpoints
# ────────────────────────────────────────────────────────────────────────
class OneDriveSettingsIn(BaseModel):
    enabled: bool = True
    tenant_id: str
    client_id: str
    client_secret: str = ""    # blank ⇒ keep existing
    backup_user_upn: str
    base_folder: str = "ITL-ERP-Backups"


@router.get("/settings")
async def get_onedrive_settings(user: dict = Depends(get_current_user)):
    _require_admin(user)
    return await ods.get_settings()


@router.put("/settings")
async def update_onedrive_settings(payload: OneDriveSettingsIn, user: dict = Depends(get_current_user)):
    _require_admin(user)
    return await ods.save_settings(payload.model_dump())


@router.post("/test-connection")
async def test_connection(user: dict = Depends(get_current_user)):
    _require_admin(user)
    return await ods.test_connection()


# ────────────────────────────────────────────────────────────────────────
# Push queue — written to from files_router on every new upload
# ────────────────────────────────────────────────────────────────────────
async def enqueue_file(file_id: str, folder_segments: list[str] | None = None) -> None:
    """Add a file to the OneDrive push queue. Idempotent — skips if already
    queued or already pushed."""
    existing = await db.onedrive_queue.find_one(
        {"file_id": file_id, "status": {"$in": ["pending", "pushed"]}}
    )
    if existing:
        return
    await db.onedrive_queue.insert_one({
        "id": new_id(),
        "file_id": file_id,
        "folder_segments": folder_segments or [],
        "status": "pending",
        "attempts": 0,
        "created_at": now_iso(),
    })


async def _module_label(folder: str | None, parent_type: str | None) -> str:
    """Maps Emergent folder/parent_type → user-facing OneDrive subfolder name."""
    if parent_type:
        return {
            "quotations": "Quotations",
            "purchase_orders": "Purchase-Orders",
            "purchase_requisitions": "Purchase-Requisitions",
            "rfqs": "RFQs",
            "grn": "GRN",
            "ra_bills": "RA-Bills",
            "dprs": "DPR",
            "measurements": "Measurements",
            "hr_letters": "HR-Letters",
            "employees": "Employees",
            "clients": "Clients",
            "client_sites": "Client-Sites",
            "vendors": "Vendors",
            "projects": "Projects",
            "assets": "Assets",
            "documents": "Documents",
            "safety": "Safety",
        }.get(parent_type, parent_type.replace("_", "-").title())
    return (folder or "Misc").replace("_", "-").title()


async def _push_queued_item(item: dict) -> dict:
    """Pushes a single queued file to OneDrive. Updates queue row."""
    f = await db.files.find_one({"id": item["file_id"]}, {"_id": 0})
    if not f:
        await db.onedrive_queue.update_one(
            {"id": item["id"]},
            {"$set": {"status": "failed", "error": "file not found", "updated_at": now_iso()}},
        )
        return {"ok": False, "error": "file_not_found"}

    try:
        data, ct = get_object(f["storage_path"])
    except Exception as e:
        await db.onedrive_queue.update_one(
            {"id": item["id"]},
            {"$inc": {"attempts": 1}, "$set": {"status": "failed", "error": f"download: {e}", "updated_at": now_iso()}},
        )
        return {"ok": False, "error": str(e)}

    created = f.get("created_at") or now_iso()
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)
    year = f"{dt.year:04d}"
    month = f"{dt.month:02d}"
    module_label = await _module_label(f.get("folder"), f.get("parent_type"))
    segments = item.get("folder_segments") or [year, month, module_label]

    fname = f.get("original_filename") or f.get("title") or f["id"]
    try:
        result = await ods.upload_to_folder(segments, fname, data, content_type=ct or f.get("content_type"))
        await db.onedrive_queue.update_one(
            {"id": item["id"]},
            {"$set": {
                "status": "pushed",
                "pushed_at": now_iso(),
                "drive_item_id": result.get("id"),
                "web_url": result.get("webUrl"),
                "remote_path": "/".join(segments) + "/" + fname,
                "size": result.get("size"),
                "updated_at": now_iso(),
            }, "$inc": {"attempts": 1}},
        )
        return {"ok": True, "drive_item_id": result.get("id")}
    except Exception as e:
        err = str(e)
        logger.exception(f"OneDrive push failed for file {f.get('id')}: {err}")
        await db.onedrive_queue.update_one(
            {"id": item["id"]},
            {"$inc": {"attempts": 1},
             "$set": {"status": "pending" if item.get("attempts", 0) < 4 else "failed",
                      "error": err[:500], "updated_at": now_iso()}},
        )
        return {"ok": False, "error": err}


async def run_push_queue(limit: int = 25) -> dict:
    """Process pending OneDrive push queue items."""
    s = await ods.get_settings()
    if not s.get("enabled") or not s.get("configured"):
        return {"processed": 0, "skipped": "disabled"}
    items = await db.onedrive_queue.find(
        {"status": "pending", "attempts": {"$lt": 5}}, {"_id": 0}
    ).limit(limit).to_list(limit)
    pushed = failed = 0
    for it in items:
        r = await _push_queued_item(it)
        if r.get("ok"):
            pushed += 1
        else:
            failed += 1
    return {"processed": len(items), "pushed": pushed, "failed": failed}


@router.get("/queue")
async def list_queue(status: str = "", limit: int = 100, user: dict = Depends(get_current_user)):
    _require_admin(user)
    q: dict = {}
    if status:
        q["status"] = status
    rows = await db.onedrive_queue.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return rows


@router.get("/stats")
async def queue_stats(user: dict = Depends(get_current_user)):
    _require_admin(user)
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    rows = await db.onedrive_queue.aggregate(pipeline).to_list(20)
    stats = {r["_id"]: r["n"] for r in rows}
    return {
        "pending": stats.get("pending", 0),
        "pushed": stats.get("pushed", 0),
        "failed": stats.get("failed", 0),
        "total": sum(stats.values()),
    }


@router.post("/process-now")
async def process_now(background: BackgroundTasks, user: dict = Depends(get_current_user)):
    _require_admin(user)
    background.add_task(run_push_queue, 50)
    return {"ok": True, "scheduled": True}


@router.post("/retry/{queue_id}")
async def retry_item(queue_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    await db.onedrive_queue.update_one(
        {"id": queue_id},
        {"$set": {"status": "pending", "error": None, "attempts": 0, "updated_at": now_iso()}},
    )
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────
# Database backup → OneDrive
# ────────────────────────────────────────────────────────────────────────
async def _create_db_dump() -> tuple[bytes, str]:
    """Returns (gzip bytes, suggested filename). Uses mongodump → gz pipe."""
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fname = f"{db_name}-{ts}.archive.gz"

    # Prefer mongodump if available; fall back to JSON export
    try:
        proc = await asyncio.create_subprocess_exec(
            "mongodump", f"--uri={mongo_url}", f"--db={db_name}",
            "--archive", "--gzip",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0 and stdout:
            return stdout, fname
        logger.warning(f"mongodump rc={proc.returncode}; stderr: {stderr[:200].decode(errors='ignore')}")
    except FileNotFoundError:
        logger.warning("mongodump not installed; falling back to JSON export")

    # Fallback: JSON export of every collection
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        collections = await db.list_collection_names()
        for coll in collections:
            if coll.startswith("system."):
                continue
            cursor = db[coll].find({})
            docs = await cursor.to_list(None)
            for d in docs:
                d.pop("_id", None)
            line = json.dumps({"collection": coll, "documents": docs}, default=str).encode("utf-8")
            gz.write(line + b"\n")
    return buf.getvalue(), fname.replace(".archive.gz", ".jsonl.gz")


async def run_db_backup() -> dict:
    """Generate a fresh DB dump and push to OneDrive under Backups/YYYY/MM/."""
    s = await ods.get_settings()
    if not s.get("enabled") or not s.get("configured"):
        return {"ok": False, "skipped": "disabled"}
    try:
        data, fname = await _create_db_dump()
    except Exception as e:
        logger.exception(f"DB dump failed: {e}")
        return {"ok": False, "error": f"dump: {e}"}

    now = datetime.now(timezone.utc)
    segments = ["Backups", f"{now.year:04d}", f"{now.month:02d}"]
    try:
        result = await ods.upload_to_folder(segments, fname, data, content_type="application/gzip")
        await db.onedrive_backups.insert_one({
            "id": new_id(),
            "filename": fname,
            "size": len(data),
            "drive_item_id": result.get("id"),
            "web_url": result.get("webUrl"),
            "remote_path": "/".join(segments) + "/" + fname,
            "at": now_iso(),
        })
        return {"ok": True, "filename": fname, "size": len(data), "web_url": result.get("webUrl")}
    except Exception as e:
        logger.exception(f"DB backup upload failed: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/backup-now")
async def backup_now(background: BackgroundTasks, user: dict = Depends(get_current_user)):
    _require_admin(user)
    background.add_task(run_db_backup)
    return {"ok": True, "scheduled": True}


@router.get("/backups")
async def list_backups(user: dict = Depends(get_current_user)):
    _require_admin(user)
    rows = await db.onedrive_backups.find({}, {"_id": 0}).sort("at", -1).limit(50).to_list(50)
    return rows


# ────────────────────────────────────────────────────────────────────────
# Historical migration job
# ────────────────────────────────────────────────────────────────────────
@router.post("/migrate-historical")
async def migrate_historical(user: dict = Depends(get_current_user)):
    """Queues every existing non-deleted file for OneDrive push."""
    _require_admin(user)
    cursor = db.files.find({"is_deleted": False}, {"_id": 0, "id": 1})
    queued = 0
    async for f in cursor:
        existing = await db.onedrive_queue.find_one(
            {"file_id": f["id"], "status": {"$in": ["pending", "pushed"]}}
        )
        if existing:
            continue
        await db.onedrive_queue.insert_one({
            "id": new_id(),
            "file_id": f["id"],
            "folder_segments": [],
            "status": "pending",
            "attempts": 0,
            "created_at": now_iso(),
            "migration": True,
        })
        queued += 1
    return {"ok": True, "queued": queued}
