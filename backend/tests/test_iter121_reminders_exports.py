"""Iter 121 — reminder cron + CSV exports + my-action-items widget API."""
import os
import requests
import asyncio
import uuid
import re
from pathlib import Path

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


def _db():
    import motor.motor_asyncio
    env = {}
    for line in Path("/app/backend/.env").read_text().splitlines():
        m = re.match(r'^\s*([A-Z_]+)\s*=\s*\"?([^\"]*)\"?\s*$', line)
        if m: env[m.group(1)] = m.group(2)
    return motor.motor_asyncio.AsyncIOMotorClient(env["MONGO_URL"])[env["DB_NAME"]]


import pytest
@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return sess


# ─── Reminder cron ────────────────────────────────────────────────────────
def test_enquiry_reminder_cron_fires(s):
    db = _db()
    # Seed a pending reminder with past date
    rid = f"r-test-{uuid.uuid4().hex[:8]}"
    enq_id = f"e-test-{uuid.uuid4().hex[:8]}"
    async def _seed():
        await db.enquiries.insert_one({"id": enq_id, "client_name": "Cron Test", "status": "quotation_pending"})
        await db.enquiry_reminders.insert_one({
            "id": rid, "enquiry_id": enq_id,
            "reminder_date": "2020-01-01",  # far in past
            "owner": "Tester", "remarks": "Test cron", "status": "pending",
            "created_at": "2020-01-01T00:00:00+00:00",
        })
    asyncio.get_event_loop().run_until_complete(_seed())

    try:
        r = s.post(f"{API_URL}/api/scheduler/run-enquiry-reminders", timeout=15)
        assert r.status_code == 200, r.text
        # Reminder status flipped to 'fired'
        async def _check():
            doc = await db.enquiry_reminders.find_one({"id": rid}, {"_id": 0, "status": 1})
            alert = await db.alerts.find_one({"id": rid}, {"_id": 0, "kind": 1})
            return doc, alert
        doc, alert = asyncio.get_event_loop().run_until_complete(_check())
        assert doc["status"] == "fired", f"Expected fired, got {doc}"
        assert alert is not None and alert["kind"] == "enquiry_reminder"
    finally:
        async def _cleanup():
            await db.enquiries.delete_one({"id": enq_id})
            await db.enquiry_reminders.delete_one({"id": rid})
            await db.alerts.delete_one({"id": rid})
        asyncio.get_event_loop().run_until_complete(_cleanup())


# ─── CSV exports ──────────────────────────────────────────────────────────
def test_export_followups_csv(s):
    r = s.get(f"{API_URL}/api/enquiry-followups/export.csv?view=all", timeout=15)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    lines = r.text.splitlines()
    assert lines[0].startswith("enquiry_number,client_name,service_type")


def test_export_reviews_csv(s):
    r = s.get(f"{API_URL}/api/internal-reviews/export.csv", timeout=15)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "manpower_status" in r.text.splitlines()[0]


def test_export_action_items_csv(s):
    r = s.get(f"{API_URL}/api/action-items/export.csv?view=all", timeout=15)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")


# ─── My action items summary ──────────────────────────────────────────────
def test_my_action_items_summary(s):
    r = s.get(f"{API_URL}/api/me/action-items/summary", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("pending", "overdue", "completed_7d", "top"):
        assert k in d
    assert isinstance(d["top"], list)
