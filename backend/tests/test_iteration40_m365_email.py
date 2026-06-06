"""Iteration 40 — Microsoft 365 SMTP Email + Outbox tests.

Covers:
  - GET /api/email/config (super_admin allowed, vendor 403)
  - POST /api/email/config/test (400 when shared mailbox not configured; Pydantic validation)
  - GET/PUT/DELETE /api/email/me/smtp (per-user creds, Fernet encryption at rest)
  - POST /api/email/me/test (no creds → 400; with fake creds → outbox record with status='failed')
  - POST /api/email/send (sender='shared' → 400 when shared not configured; sender='user' no creds → 400)
  - GET /api/email/outbox (pagination, filters, _id excluded)
  - GET /api/email/outbox/{id} (404 missing)
  - POST /api/email/outbox/{id}/retry (already-sent → 400)
  - RBAC: vendor role 403 on config / outbox / send
  - MongoDB hygiene: _id excluded
  - Indexes: email_outbox.id unique, smtp_user_credentials.user_id unique
  - UPSERT on PUT /me/smtp (idempotent)
"""
import os
import re
import time
import asyncio
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://worksite-command.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"
VENDOR_EMAIL = "TEST_vendor_iter40@erp.com"
VENDOR_PASSWORD = "Vendor@123"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "erp_database")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def admin_client():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def vendor_client(admin_client):
    # Try to register vendor user via super_admin
    payload = {
        "email": VENDOR_EMAIL,
        "password": VENDOR_PASSWORD,
        "name": "TEST Vendor Iter40",
        "role": "vendor",
    }
    r = admin_client.post(f"{API}/auth/register", json=payload, timeout=20)
    # 200 created or 400 already exists are both fine
    if r.status_code not in (200, 201, 400, 409):
        pytest.skip(f"Could not create vendor user (status={r.status_code}): {r.text}")
    return _login(VENDOR_EMAIL, VENDOR_PASSWORD)


# ---------- GET /api/email/config ----------
class TestEmailConfig:
    def test_config_super_admin_shape(self, admin_client):
        r = admin_client.get(f"{API}/email/config", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # Expected shape
        assert d.get("shared_mailbox_configured") is False, "should be False until .env populated"
        assert d.get("fernet_ready") is True, "M365_FERNET_KEY is set in .env"
        assert d.get("smtp_host") == "smtp.office365.com"
        assert d.get("smtp_port") == 587
        # Redaction: empty username → "" (no leak)
        assert d.get("shared_mailbox") in ("", None)
        assert "shared_display_name" in d

    def test_config_vendor_forbidden(self, vendor_client):
        r = vendor_client.get(f"{API}/email/config", timeout=15)
        assert r.status_code == 403, f"vendor must be 403, got {r.status_code}: {r.text}"


# ---------- POST /api/email/config/test ----------
class TestSharedTest:
    def test_shared_test_400_when_not_configured(self, admin_client):
        r = admin_client.post(
            f"{API}/email/config/test",
            json={"to": "ops@example.com", "subject": "x", "body": "y"},
            timeout=20,
        )
        assert r.status_code == 400, r.text
        assert "shared mailbox not configured" in r.text.lower()

    def test_shared_test_pydantic_validation(self, admin_client):
        r = admin_client.post(
            f"{API}/email/config/test",
            json={"to": "not-an-email"},
            timeout=15,
        )
        assert r.status_code == 422, f"expected 422 EmailStr validation, got {r.status_code}"


# ---------- per-user SMTP credentials ----------
class TestUserSmtp:
    def test_get_me_smtp_initial_not_configured(self, admin_client, mongo_db):
        # ensure clean state
        admin_client.delete(f"{API}/email/me/smtp", timeout=15)
        r = admin_client.get(f"{API}/email/me/smtp", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"configured": False}

    def test_put_me_smtp_encrypts_password(self, admin_client, mongo_db):
        payload = {
            "smtp_username": "TEST_iter40@itlis.in",
            "app_password": "Plaintext-AppPassword-1234",
            "display_name": "Iter40 Tester",
        }
        r = admin_client.put(f"{API}/email/me/smtp", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("smtp_username") == payload["smtp_username"]

        # Verify in MongoDB
        admin_user = mongo_db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "id": 1})
        assert admin_user, "admin user not found in db"
        doc = mongo_db.smtp_user_credentials.find_one({"user_id": admin_user["id"]})
        assert doc, "credentials not persisted"
        enc = doc.get("encrypted_app_password", "")
        assert isinstance(enc, str) and enc, "encrypted_app_password missing"
        # Fernet token starts with 'gAAAAA' (base64 of version byte 0x80)
        assert enc.startswith("gAAAAA"), f"not a Fernet token: {enc[:20]}"
        assert payload["app_password"] not in enc, "plaintext leak into stored value"

    def test_get_me_smtp_after_put(self, admin_client):
        r = admin_client.get(f"{API}/email/me/smtp", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("configured") is True
        assert d.get("smtp_username") == "TEST_iter40@itlis.in"
        assert d.get("display_name") == "Iter40 Tester"
        assert "updated_at" in d

    def test_put_me_smtp_upserts_idempotent(self, admin_client, mongo_db):
        # second PUT should update, not error
        payload = {
            "smtp_username": "TEST_iter40b@itlis.in",
            "app_password": "Plaintext-AppPassword-9999",
            "display_name": "Iter40 Tester v2",
        }
        r = admin_client.put(f"{API}/email/me/smtp", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        # Verify only one doc per user_id
        admin_user = mongo_db.users.find_one({"email": ADMIN_EMAIL}, {"id": 1})
        cnt = mongo_db.smtp_user_credentials.count_documents({"user_id": admin_user["id"]})
        assert cnt == 1, f"expected single doc per user_id, got {cnt}"
        # And the new username was saved
        d = admin_client.get(f"{API}/email/me/smtp", timeout=15).json()
        assert d["smtp_username"] == "TEST_iter40b@itlis.in"

    def test_delete_me_smtp(self, admin_client):
        r = admin_client.delete(f"{API}/email/me/smtp", timeout=15)
        assert r.status_code == 200
        r2 = admin_client.get(f"{API}/email/me/smtp", timeout=15)
        assert r2.json() == {"configured": False}


# ---------- POST /api/email/me/test ----------
class TestMeTest:
    def test_me_test_no_creds_400(self, admin_client):
        # ensure cleared
        admin_client.delete(f"{API}/email/me/smtp", timeout=15)
        r = admin_client.post(
            f"{API}/email/me/test",
            json={"to": "ops@example.com"},
            timeout=20,
        )
        assert r.status_code == 400, r.text
        assert "no smtp credentials saved" in r.text.lower()

    def test_me_test_with_fake_creds_creates_failed_outbox(self, admin_client, mongo_db):
        # Save fake credentials
        put_resp = admin_client.put(
            f"{API}/email/me/smtp",
            json={
                "smtp_username": "TEST_iter40_fake@itlis-fake.com",
                "app_password": "definitely-not-a-real-password-xyz",
                "display_name": "Iter40 Fake",
            },
            timeout=20,
        )
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.status_code} {put_resp.text}"
        # Confirm creds present before /me/test
        g = admin_client.get(f"{API}/email/me/smtp", timeout=10).json()
        assert g.get("configured") is True, f"creds did not persist: {g}"
        # Send test — SMTP connect to smtp.office365.com may take 10-30s
        r = admin_client.post(
            f"{API}/email/me/test",
            json={"to": "ops@example.com", "subject": "Iter40 fake test"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "outbox_id" in body
        rec = body.get("record") or {}
        assert rec.get("status") == "failed", f"expected failed, got {rec.get('status')}"
        assert rec.get("last_error"), "should have a friendly error message"
        # _id should never be on the response
        assert "_id" not in rec
        # cleanup
        admin_client.delete(f"{API}/email/me/smtp", timeout=15)


# ---------- POST /api/email/send ----------
class TestSend:
    def test_send_shared_400_when_not_configured(self, admin_client):
        r = admin_client.post(
            f"{API}/email/send",
            data={
                "to": "ops@example.com",
                "subject": "Iter40 send shared",
                "body_text": "hello",
                "sender": "shared",
            },
            timeout=20,
        )
        assert r.status_code == 400, r.text
        assert "shared mailbox not configured" in r.text.lower()

    def test_send_user_400_when_no_creds(self, admin_client):
        admin_client.delete(f"{API}/email/me/smtp", timeout=15)
        r = admin_client.post(
            f"{API}/email/send",
            data={
                "to": "ops@example.com",
                "subject": "Iter40 send user",
                "body_text": "hello",
                "sender": "user",
            },
            timeout=20,
        )
        assert r.status_code == 400, r.text
        assert "per-user smtp credentials" in r.text.lower() or "no" in r.text.lower()

    def test_send_invalid_sender_400(self, admin_client):
        r = admin_client.post(
            f"{API}/email/send",
            data={
                "to": "ops@example.com",
                "subject": "x",
                "body_text": "x",
                "sender": "garbage",
            },
            timeout=15,
        )
        assert r.status_code == 400

    def test_send_missing_to_400(self, admin_client):
        r = admin_client.post(
            f"{API}/email/send",
            data={
                "to": "",
                "subject": "x",
                "body_text": "x",
                "sender": "shared",
            },
            timeout=15,
        )
        # FastAPI Form(...) may reject empty as 422 (Pydantic) or backend may return 400.
        # Either is acceptable — both are 4xx errors signalling missing 'to'.
        assert r.status_code in (400, 422), f"expected 400 or 422, got {r.status_code}: {r.text}"

    def test_send_vendor_forbidden(self, vendor_client):
        r = vendor_client.post(
            f"{API}/email/send",
            data={"to": "x@y.com", "subject": "x", "body_text": "x", "sender": "shared"},
            timeout=15,
        )
        assert r.status_code == 403


# ---------- GET /api/email/outbox ----------
class TestOutbox:
    def test_outbox_list_shape_and_no_id(self, admin_client):
        r = admin_client.get(f"{API}/email/outbox?limit=5&skip=0", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert {"total", "skip", "limit", "rows"} <= set(d.keys())
        assert d["skip"] == 0 and d["limit"] == 5
        for row in d["rows"]:
            assert "_id" not in row, "_id leaked into list response"
            assert "id" in row

    def test_outbox_pagination(self, admin_client):
        r1 = admin_client.get(f"{API}/email/outbox?limit=1&skip=0", timeout=15).json()
        r2 = admin_client.get(f"{API}/email/outbox?limit=1&skip=1", timeout=15).json()
        assert r1["limit"] == 1 and r2["skip"] == 1
        if r1["total"] >= 2:
            assert r1["rows"][0].get("id") != r2["rows"][0].get("id")

    def test_outbox_filter_status_failed(self, admin_client):
        r = admin_client.get(f"{API}/email/outbox?status=failed", timeout=15)
        assert r.status_code == 200
        for row in r.json().get("rows", []):
            assert row["status"] == "failed"

    def test_outbox_detail_404(self, admin_client):
        r = admin_client.get(f"{API}/email/outbox/does-not-exist-xyz", timeout=15)
        assert r.status_code == 404

    def test_outbox_detail_no_id(self, admin_client):
        # Pull one to inspect
        rows = admin_client.get(f"{API}/email/outbox?limit=1", timeout=15).json().get("rows", [])
        if not rows:
            pytest.skip("no outbox rows yet")
        rid = rows[0]["id"]
        r = admin_client.get(f"{API}/email/outbox/{rid}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "_id" not in d
        assert d["id"] == rid

    def test_outbox_vendor_forbidden(self, vendor_client):
        r = vendor_client.get(f"{API}/email/outbox", timeout=15)
        assert r.status_code == 403


# ---------- POST /api/email/outbox/{id}/retry ----------
class TestRetry:
    def test_retry_failed_record_queues(self, admin_client, mongo_db):
        rows = admin_client.get(f"{API}/email/outbox?status=failed&limit=1", timeout=15).json().get("rows", [])
        if not rows:
            pytest.skip("no failed outbox to retry")
        rid = rows[0]["id"]
        r = admin_client.post(f"{API}/email/outbox/{rid}/retry", timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "queued"

    def test_retry_already_sent_400(self, admin_client, mongo_db):
        # Force a record to status='sent' to test the 400 path
        fake_id = "TEST_iter40_sent_xyz"
        mongo_db.email_outbox.insert_one({
            "id": fake_id,
            "sender_type": "shared",
            "status": "sent",
            "to": ["x@y.com"],
            "subject": "stub",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })
        try:
            r = admin_client.post(f"{API}/email/outbox/{fake_id}/retry", timeout=15)
            assert r.status_code == 400
            assert "already sent" in r.text.lower()
        finally:
            mongo_db.email_outbox.delete_one({"id": fake_id})

    def test_retry_missing_404(self, admin_client):
        r = admin_client.post(f"{API}/email/outbox/does-not-exist-xyz/retry", timeout=15)
        assert r.status_code == 404


# ---------- indexes ----------
class TestIndexes:
    def test_outbox_id_unique(self, mongo_db):
        idx = mongo_db.email_outbox.index_information()
        # find an index that is on 'id' alone and unique
        found = False
        for name, meta in idx.items():
            keys = meta.get("key", [])
            if keys == [("id", 1)] and meta.get("unique"):
                found = True
                break
        assert found, f"email_outbox.id unique index not found: {idx}"

    def test_smtp_user_creds_user_id_unique(self, mongo_db):
        idx = mongo_db.smtp_user_credentials.index_information()
        found = False
        for name, meta in idx.items():
            keys = meta.get("key", [])
            if keys == [("user_id", 1)] and meta.get("unique"):
                found = True
                break
        assert found, f"smtp_user_credentials.user_id unique index not found: {idx}"


# ---------- module teardown ----------
@pytest.fixture(scope="module", autouse=True)
def cleanup(mongo_db):
    yield
    # Drop any TEST_ artifacts
    try:
        admin = mongo_db.users.find_one({"email": ADMIN_EMAIL}, {"id": 1})
        if admin:
            mongo_db.smtp_user_credentials.delete_one({"user_id": admin["id"]})
        mongo_db.email_outbox.delete_many({"subject": {"$regex": "^Iter40 "}})
    except Exception:
        pass
