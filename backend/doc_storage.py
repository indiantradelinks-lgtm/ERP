"""Document storage tiers: object store (upload landing zone) → OneDrive (primary).

A file becomes OneDrive-primary only after a three-point check: Graph reports the
item, the bytes are downloaded back and their SHA-256 equals the hash recorded at
upload. Nothing is ever deleted — the object-store reference is kept as rollback,
so a OneDrive outage transparently falls back to it.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from core import db, now_iso
from offload import run_blocking
from storage import get_object
import onedrive_service as ods

logger = logging.getLogger("erp.docstorage")

VERIFY_MAX_ATTEMPTS = 5


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def verify_file(f: dict) -> dict:
    """Download the OneDrive copy, compare with the recorded hash, promote tier."""
    fid, item_id = f["id"], f.get("onedrive_item_id")
    if not item_id:
        return {"ok": False, "error": "not pushed yet"}
    attempts = int(f.get("onedrive_verify_attempts") or 0) + 1
    try:
        expected = f.get("sha256")
        if not expected:
            src, _ = await run_blocking(get_object, f["storage_path"])
            expected = _sha(src)
            await db.files.update_one({"id": fid}, {"$set": {"sha256": expected}})
        remote, _ = await ods.download_item(item_id)
        got = _sha(remote)
        if got != expected or (f.get("size") and len(remote) != int(f["size"])):
            raise ValueError(f"hash/size mismatch (expected {expected[:12]}…/{f.get('size')}, got {got[:12]}…/{len(remote)})")
        await db.files.update_one({"id": fid}, {"$set": {
            "storage_tier": "onedrive", "onedrive_verified_at": now_iso(), "onedrive_verified_sha256": got,
            "onedrive_verified_size": len(remote), "onedrive_verify_error": None,
            "onedrive_verify_attempts": attempts,
            "storage_path_archived": f.get("storage_path")}})
        return {"ok": True, "file_id": fid}
    except Exception as e:  # noqa: BLE001 — recorded on the row, retried later
        err = str(e)[:300]
        logger.warning("verify failed for %s (attempt %s): %s", fid, attempts, err)
        await db.files.update_one({"id": fid}, {"$set": {
            "onedrive_verify_error": err, "onedrive_verify_attempts": attempts,
            "onedrive_verify_last_at": now_iso()}})
        if "mismatch" in err:
            # Content differs — re-push so the queue uploads a fresh copy (replace semantics)
            await db.onedrive_queue.update_one(
                {"file_id": fid}, {"$set": {"status": "pending", "attempts": 0, "next_attempt_at": now_iso(),
                                            "error": "re-push after verification mismatch", "updated_at": now_iso()}})
        return {"ok": False, "file_id": fid, "error": err}


async def run_verification_batch(limit: int = 25) -> dict:
    s = await ods.get_settings()
    if not s.get("enabled") or not s.get("configured"):
        return {"verified": 0, "failed": 0, "skipped": "disabled"}
    q = {"is_deleted": False, "onedrive_item_id": {"$exists": True, "$ne": None},
         "storage_tier": {"$ne": "onedrive"},
         "$or": [{"onedrive_verify_attempts": {"$exists": False}}, {"onedrive_verify_attempts": {"$lt": VERIFY_MAX_ATTEMPTS}}],
         "$nor": [{"onedrive_verify_last_at": {"$gt": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}}]}
    rows = await db.files.find(q, {"_id": 0}).sort("onedrive_pushed_at", 1).limit(limit).to_list(limit)
    ok = bad = 0
    for f in rows:
        r = await verify_file(f)
        ok += 1 if r.get("ok") else 0
        bad += 0 if r.get("ok") else 1
        if not r.get("ok") and ("token" in (r.get("error") or "").lower() or "AADSTS" in (r.get("error") or "")):
            return {"candidates": len(rows), "verified": ok, "failed": bad, "aborted": "auth"}
    return {"candidates": len(rows), "verified": ok, "failed": bad}


async def fetch_bytes(record: dict) -> tuple[bytes, str]:
    """Read a document: OneDrive first when it is the verified primary (and
    primary reads are on), object store otherwise; each path falls back to the other."""
    s = await ods.get_settings()
    onedrive_first = record.get("storage_tier") == "onedrive" and s.get("primary_reads", True) and s.get("enabled")
    if onedrive_first:
        try:
            return await ods.download_item(record["onedrive_item_id"])
        except Exception as e:  # noqa: BLE001
            logger.warning("onedrive read failed for %s, falling back to object store: %s", record.get("id"), str(e)[:160])
            await db.files.update_one({"id": record["id"]}, {"$set": {"onedrive_read_error": str(e)[:200],
                                                                      "onedrive_read_error_at": now_iso()}})
    try:
        return await run_blocking(get_object, record["storage_path"])
    except Exception:
        if record.get("onedrive_item_id") and not onedrive_first:
            return await ods.download_item(record["onedrive_item_id"])
        raise


async def storage_audit() -> dict:
    pipeline = [
        {"$match": {"is_deleted": False}},
        {"$group": {"_id": {"$ifNull": ["$parent_type", "$folder"]},
                    "files": {"$sum": 1}, "bytes": {"$sum": {"$ifNull": ["$size", 0]}},
                    "pushed": {"$sum": {"$cond": [{"$ifNull": ["$onedrive_item_id", False]}, 1, 0]}},
                    "verified": {"$sum": {"$cond": [{"$eq": ["$storage_tier", "onedrive"]}, 1, 0]}},
                    "verified_bytes": {"$sum": {"$cond": [{"$eq": ["$storage_tier", "onedrive"]}, {"$ifNull": ["$size", 0]}, 0]}},
                    "verify_failed": {"$sum": {"$cond": [{"$and": [{"$ifNull": ["$onedrive_verify_error", False]},
                                                                    {"$ne": ["$storage_tier", "onedrive"]}]}, 1, 0]}}}},
        {"$sort": {"bytes": -1}},
    ]
    rows = [{"module": r["_id"] or "misc", **{k: v for k, v in r.items() if k != "_id"}}
            async for r in db.files.aggregate(pipeline)]
    tot = {k: sum(r[k] for r in rows) for k in ("files", "bytes", "pushed", "verified", "verified_bytes", "verify_failed")}
    queue = {r["_id"]: r["n"] async for r in db.onedrive_queue.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    deleted = await db.files.count_documents({"is_deleted": True})
    unpushed_ids = [r["id"] async for r in db.files.find(
        {"is_deleted": False, "onedrive_item_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1})]
    queued_ids = set(await db.onedrive_queue.distinct("file_id", {"file_id": {"$in": unpushed_ids},
                                                                  "status": {"$in": ["pending", "failed"]}}))
    return {"modules": rows, "totals": tot, "queue": queue, "soft_deleted_files": deleted,
            "not_queued": len([i for i in unpushed_ids if i not in queued_ids])}
