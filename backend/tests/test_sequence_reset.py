"""Iter 52 — Sequence reset utility regression."""
import os
import time
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def admin():
    c = httpx.Client(base_url=f"{API}/api", timeout=30.0)
    r = c.post("/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200
    yield c
    c.close()


def _seed_counter(key: str, value: int):
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.sequences.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)
    asyncio.run(_do())


def _cleanup_counter(key: str):
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.sequences.delete_one({"_id": key})
    asyncio.run(_do())


def test_list_sequences_returns_shape(admin):
    r = admin.get("/admin/sequences")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    if rows:
        keys = {"key", "current_value", "max_in_data", "drift", "can_safely_reset_to_zero"}
        assert keys.issubset(set(rows[0].keys()))


def test_auto_sync_zeroes_orphan_counter(admin):
    key = f"ITR52-TEST-{int(time.time())}"
    _seed_counter(key, 99)
    try:
        r = admin.post("/admin/sequences/reset", json={"mode": "auto", "keys": [key]})
        assert r.status_code == 200
        changes = {c["key"]: c for c in r.json()["changes"]}
        assert key in changes
        # No real data exists for this prefix → max_in_data = 0 → new value = 0
        assert changes[key]["new"] == 0
        assert changes[key]["next_allocation"] == 1
    finally:
        _cleanup_counter(key)


def test_force_reset_zeroes_specific_key(admin):
    key = f"ITR52-FORCE-{int(time.time())}"
    _seed_counter(key, 42)
    try:
        r = admin.post("/admin/sequences/reset", json={"mode": "force", "keys": [key]})
        assert r.status_code == 200
        ch = next(c for c in r.json()["changes"] if c["key"] == key)
        assert ch["old"] == 42
        assert ch["new"] == 0
    finally:
        _cleanup_counter(key)


def test_invalid_mode_returns_400(admin):
    r = admin.post("/admin/sequences/reset", json={"mode": "bogus"})
    assert r.status_code == 400


def test_delete_sequence_key(admin):
    key = f"ITR52-DEL-{int(time.time())}"
    _seed_counter(key, 5)
    r = admin.delete(f"/admin/sequences/{key}")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    # Idempotent — second delete returns 0
    r2 = admin.delete(f"/admin/sequences/{key}")
    assert r2.status_code == 200
    assert r2.json()["deleted"] == 0


def test_non_admin_blocked():
    bare = httpx.Client(base_url=f"{API}/api", timeout=15.0)
    r = bare.get("/admin/sequences")
    assert r.status_code == 401
    bare.close()


def test_auto_keeps_counter_at_max_when_data_exists(admin):
    """If the corresponding collection still has documents using the prefix,
    auto-sync must respect that high-water mark instead of zeroing."""
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timezone

    key = "ENQ-2099"
    test_doc_no = "ENQ-2099-0007"

    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        # Seed counter and a real enquiry doc.
        await db.sequences.update_one({"_id": key}, {"$set": {"value": 50}}, upsert=True)
        await db.enquiries.insert_one({
            "id": "itr52-enq-test",
            "enquiry_no": test_doc_no,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def _teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.sequences.delete_one({"_id": key})
        await db.enquiries.delete_one({"id": "itr52-enq-test"})

    asyncio.run(_setup())
    try:
        r = admin.post("/admin/sequences/reset", json={"mode": "auto", "keys": [key]})
        assert r.status_code == 200
        ch = next(c for c in r.json()["changes"] if c["key"] == key)
        assert ch["new"] == 7   # high-water mark from the real doc
        assert ch["next_allocation"] == 8
    finally:
        asyncio.run(_teardown())
