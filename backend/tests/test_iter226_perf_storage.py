"""Iter 226 — Performance remediation: AI subprocess isolation, system-health
monitoring/housekeeping, verified OneDrive-primary document storage."""
import asyncio
import hashlib
import os
import sys
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")


@pytest.fixture(scope="module")
def mongo():
    env = dotenv_values("/app/backend/.env")
    return MongoClient(env["MONGO_URL"])[env["DB_NAME"]]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


# ── A. AI library never enters the API process ─────────────────────────
def test_api_process_has_no_litellm_loaded(s):
    snap = s.get(f"{API}/admin/system-health", timeout=60).json()
    assert snap["process"]["litellm_loaded"] is False
    assert snap["process"]["rss_mb"] < 330, "API process should idle well under the 512 Mi tier"


def test_ai_worker_runs_in_child_process_and_reports_errors_cleanly():
    from ai_worker import llm_send, AIWorkerError
    # An unknown model makes the child fail fast; the parent must get a clean error, not a crash.
    with pytest.raises(AIWorkerError):
        asyncio.run(llm_send("gemini", "no-such-model-xyz", "sys", "hi"))
    assert "litellm" not in sys.modules, "parent process must not import litellm"


def test_no_router_imports_emergentintegrations_directly():
    import subprocess
    out = subprocess.run(["grep", "-rl", "--include=*.py", "from emergentintegrations", "/app/backend/routers", "/app/backend/challan_ai.py"],
                         capture_output=True, text=True).stdout.split()
    assert out == [], f"direct LLM imports must go through ai_worker: {out}"


# ── B. System health endpoint, settings, slow-request capture ──────────
def test_system_health_snapshot_shape(s):
    d = s.get(f"{API}/admin/system-health", timeout=60).json()
    for k in ("process", "disk", "db", "requests", "scheduler", "slow_requests", "settings"):
        assert k in d
    assert d["process"]["mem_limit_mb"] > 0 and d["disk"]["app"]["total_gb"] > 0
    assert d["db"]["collections"] > 0


def test_system_health_is_super_admin_only(s):
    anon = requests.get(f"{API}/admin/system-health", timeout=30)
    assert anon.status_code == 401


def test_settings_roundtrip(s):
    r = s.put(f"{API}/admin/system-health/settings", json={"slow_ms": 1234, "retention": {"login_activity_days": 181}}, timeout=30)
    assert r.status_code == 200 and r.json()["slow_ms"] == 1234 and r.json()["retention"]["login_activity_days"] == 181
    r = s.put(f"{API}/admin/system-health/settings", json={"slow_ms": 1500, "retention": {"login_activity_days": 180}}, timeout=30)
    assert r.json()["slow_ms"] == 1500


def test_sample_now_persists_history(s):
    r = s.post(f"{API}/admin/system-health/sample-now", timeout=60).json()
    assert r["sampled"] is True and r["rss_mb"] > 0
    hist = s.get(f"{API}/admin/system-health/history?days=1", timeout=30).json()
    assert len(hist) >= 1 and "rss_mb" in hist[-1]


# ── C. Housekeeping touches only technical debris ─────────────────────
def test_housekeeping_keeps_business_data_and_recent_tmp(s, mongo):
    before = {c: mongo[c].count_documents({}) for c in ("approvals", "quotations", "files", "employees", "audit_logs", "projects")}
    fresh = f"/tmp/probe-{uuid.uuid4().hex}"
    old = f"/tmp/probe-old-{uuid.uuid4().hex}"
    open(fresh, "w").write("x"); open(old, "w").write("x")
    os.utime(old, (time.time() - 5 * 3600, time.time() - 5 * 3600))
    recent_login = {"id": str(uuid.uuid4()), "at": "2999-01-01T00:00:00+00:00", "email": "probe@x"}
    mongo.login_activity.insert_one(recent_login)
    r = s.post(f"{API}/admin/system-health/housekeeping/run", timeout=120).json()
    assert "temp" in r and r["rss_mb_after"] > 0
    assert os.path.exists(fresh) and not os.path.exists(old)
    after = {c: mongo[c].count_documents({}) for c in before}
    assert after == before, "housekeeping must never remove business records"
    assert mongo.login_activity.count_documents({"id": recent_login["id"]}) == 1
    mongo.login_activity.delete_one({"id": recent_login["id"]})
    os.remove(fresh)


# ── D. Verified OneDrive-primary migration (Graph mocked) ─────────────
def test_verification_promotes_only_on_hash_match(mongo, monkeypatch):
    import doc_storage
    import onedrive_service as ods
    payload = b"%PDF-1.4 probe " + uuid.uuid4().bytes
    fid = str(uuid.uuid4())
    mongo.files.insert_one({"id": fid, "storage_path": "probe/none.pdf", "sha256": hashlib.sha256(payload).hexdigest(),
                            "size": len(payload), "is_deleted": False, "onedrive_item_id": "ITEM1",
                            "original_filename": "probe.pdf", "created_at": "2026-01-01T00:00:00+00:00"})
    async def scenario():
        async def good(item_id):
            return payload, "application/pdf"

        async def bad(item_id):
            return payload + b"corrupt", "application/pdf"

        monkeypatch.setattr(ods, "download_item", bad)
        f = mongo.files.find_one({"id": fid}, {"_id": 0})
        r = await doc_storage.verify_file(f)
        assert r["ok"] is False and "mismatch" in r["error"]
        f = mongo.files.find_one({"id": fid}, {"_id": 0})
        assert f.get("storage_tier") != "onedrive" and f["onedrive_verify_attempts"] == 1

        monkeypatch.setattr(ods, "download_item", good)
        r = await doc_storage.verify_file(f)
        assert r["ok"] is True
        f = mongo.files.find_one({"id": fid}, {"_id": 0})
        assert f["storage_tier"] == "onedrive" and f["storage_path_archived"] == "probe/none.pdf"
        assert f["storage_path"] == "probe/none.pdf", "object-store reference must be kept for rollback"

        async def settings(**kw):
            return {"enabled": True, "configured": True, "primary_reads": True}
        monkeypatch.setattr(ods, "get_settings", settings)
        data, _ = await doc_storage.fetch_bytes(f)
        assert data == payload

        async def down(item_id):
            raise RuntimeError("graph down")
        monkeypatch.setattr(ods, "download_item", down)
        monkeypatch.setattr(doc_storage, "get_object", lambda path: (payload, "application/pdf"))
        data, _ = await doc_storage.fetch_bytes(f)
        assert data == payload
        assert mongo.files.find_one({"id": fid})["onedrive_read_error"].startswith("graph down")

    try:
        asyncio.run(scenario())
    finally:
        mongo.files.delete_one({"id": fid})
        mongo.onedrive_queue.delete_many({"file_id": fid})


def test_storage_audit_endpoint(s):
    d = s.get(f"{API}/admin/onedrive/storage-audit", timeout=60).json()
    assert {"modules", "totals", "queue", "not_queued"} <= set(d)
    assert d["totals"]["files"] >= d["totals"]["verified"] >= 0 and d["not_queued"] >= 0


def test_primary_reads_setting_roundtrip(s):
    cur = s.get(f"{API}/admin/onedrive/settings", timeout=30).json()
    body = {k: cur[k] for k in ("tenant_id", "client_id", "backup_user_upn", "base_folder", "enabled")}
    r = s.put(f"{API}/admin/onedrive/settings", json={**body, "primary_reads": False}, timeout=30)
    assert r.status_code == 200 and r.json()["primary_reads"] is False
    r = s.put(f"{API}/admin/onedrive/settings", json={**body, "primary_reads": True}, timeout=30)
    assert r.json()["primary_reads"] is True


# ── E. Existing document access is unchanged ──────────────────────────
def test_existing_file_download_still_works(s, mongo):
    f = mongo.files.find_one({"is_deleted": False, "storage_path": {"$regex": "^itl-erp|^worksite"}}, {"_id": 0, "id": 1})
    if not f:
        pytest.skip("no object-store file in this DB")
    r = s.get(f"{API}/files/{f['id']}/download", timeout=120)
    assert r.status_code == 200 and len(r.content) > 0
