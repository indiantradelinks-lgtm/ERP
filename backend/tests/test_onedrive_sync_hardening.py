"""OneDrive sync hardening — queue behaviour with a stubbed Graph layer.

Covers: sanitised remote names, permanent 4xx vs transient retry+backoff,
orphan rows skipped (not "failing"), self-healing requeue of old-sanitizer rows.
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

import httpx  # noqa: E402
import onedrive_service as ods  # noqa: E402
from core import db, new_id, now_iso  # noqa: E402
from routers import onedrive_router as odr  # noqa: E402

PREFIX = "SYNCTEST_"


async def _mk_file(name: str) -> dict:
    doc = {"id": new_id(), "storage_path": "x/y.pdf", "sha256": None,
           "original_filename": name, "content_type": "application/pdf",
           "size": 10, "title": name, "folder": "documents",
           "parent_type": "projects", "parent_id": PREFIX + "P1",
           "is_deleted": False, "created_at": now_iso()}
    await db.files.insert_one(dict(doc))
    return doc


async def _mk_queue(file_id: str, **extra) -> dict:
    row = {"id": new_id(), "file_id": file_id, "folder_segments": [], "status": "pending",
           "attempts": 0, "permanent": False, "next_attempt_at": now_iso(),
           "sanitizer_v": ods.SANITIZER_VERSION, "created_at": now_iso(), **extra}
    await db.onedrive_queue.insert_one(dict(row))
    return row


async def main():
    results = []

    def ok(label, cond, extra=""):
        results.append((label, bool(cond), extra))

    # ---- 1. sanitiser
    bad = "fb0d5181_MOBILZTION%20BILL%20-%20MBF#2.pdf"
    ok("sanitiser strips '#'/'%' from the failing name",
       "#" not in ods.safe_name(bad) and "%" not in ods.safe_name(bad), ods.safe_name(bad))
    ok("path is URL-encoded", "%20" in ods._quote_path("a/b c.pdf"))
    ok("400 classified permanent",
       ods.is_retryable(httpx.HTTPStatusError("x", request=None, response=httpx.Response(400)))[0] is False)
    ok("429 classified retryable",
       ods.is_retryable(httpx.HTTPStatusError("x", request=None, response=httpx.Response(429)))[0] is True)

    # ---- stubs
    orig_upload, orig_get, orig_settings = ods.upload_to_folder, odr.get_object, ods.get_settings
    odr.get_object = lambda path: (b"%PDF-1.4 stub", "application/pdf")
    ods.get_settings = lambda **kw: asyncio.sleep(0, result={"enabled": True, "configured": True})

    sent = {}

    async def fake_ok(segments, filename, data, content_type=None):
        sent["name"] = ods.safe_name(filename)
        return {"id": "DRIVE!1", "webUrl": "https://onedrive/x", "size": len(data)}

    async def fake_400(segments, filename, data, content_type=None):
        raise httpx.HTTPStatusError("bad", request=None, response=httpx.Response(400, text="invalidRequest"))

    async def fake_503(segments, filename, data, content_type=None):
        raise httpx.HTTPStatusError("busy", request=None, response=httpx.Response(503, text="serviceNotAvailable"))

    try:
        # ---- 2. happy path: sanitised remote path, file row linked
        f1 = await _mk_file(bad)
        q1 = await _mk_queue(f1["id"])
        ods.upload_to_folder = fake_ok
        r = await odr._push_queued_item(q1)
        row = await db.onedrive_queue.find_one({"id": q1["id"]}, {"_id": 0})
        fdoc = await db.files.find_one({"id": f1["id"]}, {"_id": 0})
        ok("push succeeds", r.get("ok"))
        ok("remote name sanitised", "#" not in row["remote_path"] and "%20" not in row["remote_path"],
           row["remote_path"])
        ok("queue row pushed", row["status"] == "pushed")
        ok("file row links drive item", fdoc.get("onedrive_item_id") == "DRIVE!1")
        ok("file row error cleared", fdoc.get("onedrive_error") is None)

        # ---- 3. permanent failure (400) → failed + permanent, no endless retry
        f2 = await _mk_file("bad-request.pdf")
        q2 = await _mk_queue(f2["id"])
        ods.upload_to_folder = fake_400
        await odr._push_queued_item(q2)
        row = await db.onedrive_queue.find_one({"id": q2["id"]}, {"_id": 0})
        ok("400 → failed", row["status"] == "failed")
        ok("400 → permanent", row["permanent"] is True)
        ok("400 → no next attempt scheduled", row.get("next_attempt_at") is None)
        f2doc = await db.files.find_one({"id": f2["id"]}, {"_id": 0})
        ok("ERP copy still intact after sync failure", f2doc and f2doc["is_deleted"] is False)

        # ---- 4. transient failure (503) → pending with backoff
        f3 = await _mk_file("transient.pdf")
        q3 = await _mk_queue(f3["id"])
        ods.upload_to_folder = fake_503
        await odr._push_queued_item(q3)
        row = await db.onedrive_queue.find_one({"id": q3["id"]}, {"_id": 0})
        ok("503 → stays pending", row["status"] == "pending")
        ok("503 → backoff scheduled in the future", row.get("next_attempt_at") > now_iso(),
           row.get("next_attempt_at"))
        ok("503 → not permanent", row["permanent"] is False)

        # not due yet ⇒ the queue run must not pick it up
        due = await db.onedrive_queue.find_one(
            {"id": q3["id"], "next_attempt_at": {"$lte": now_iso()}}, {"_id": 0})
        ok("backoff respected (row not due yet)", due is None)

        # once due, it retries and succeeds
        await db.onedrive_queue.update_one({"id": q3["id"]}, {"$set": {"next_attempt_at": now_iso()}})
        ods.upload_to_folder = fake_ok
        q3 = await db.onedrive_queue.find_one({"id": q3["id"]}, {"_id": 0})
        await odr._push_queued_item(q3)
        row = await db.onedrive_queue.find_one({"id": q3["id"]}, {"_id": 0})
        ok("retry after backoff succeeds", row["status"] == "pushed")

        # ---- 5. orphan row (file deleted) → skipped, not "failing"
        f4 = await _mk_file("deleted.pdf")
        await db.files.update_one({"id": f4["id"]}, {"$set": {"is_deleted": True}})
        q4 = await _mk_queue(f4["id"])
        await odr._push_queued_item(q4)
        row = await db.onedrive_queue.find_one({"id": q4["id"]}, {"_id": 0})
        ok("deleted file → skipped (not failed)", row["status"] == "skipped", row.get("error_code"))

        # ---- 6. self-healing requeue of rows failed under the old sanitiser
        f5 = await _mk_file("old-sanitizer#1.pdf")
        q5 = await _mk_queue(f5["id"], status="failed", attempts=5, error="400 Bad Request")
        await db.onedrive_queue.update_one({"id": q5["id"]}, {"$unset": {"sanitizer_v": ""}})
        ods.upload_to_folder = fake_ok
        res = await odr.run_push_queue(limit=1)   # heal sweep runs regardless of batch size
        healed = await db.onedrive_queue.find_one({"id": q5["id"]}, {"_id": 0})
        ok("old-sanitiser failure auto-requeued to pending", healed["status"] == "pending",
           f"requeued={res.get('requeued')}")
        await odr._push_queued_item(healed)
        row = await db.onedrive_queue.find_one({"id": q5["id"]}, {"_id": 0})
        ok("re-queued row then pushes with the sanitised name", row["status"] == "pushed",
           row.get("remote_path"))
    finally:
        ods.upload_to_folder, odr.get_object, ods.get_settings = orig_upload, orig_get, orig_settings
        ids = [f["id"] async for f in db.files.find({"parent_id": PREFIX + "P1"}, {"id": 1})]
        await db.onedrive_queue.delete_many({"file_id": {"$in": ids}})
        await db.files.delete_many({"parent_id": PREFIX + "P1"})

    print()
    for label, passed, extra in results:
        print(("PASS  " if passed else "FAIL  ") + label + (f"   [{extra}]" if extra else ""))
    bad_n = sum(1 for _, p, _ in results if not p)
    print(f"\n{len(results) - bad_n}/{len(results)} checks passed")
    return 1 if bad_n else 0


sys.exit(asyncio.run(main()))
