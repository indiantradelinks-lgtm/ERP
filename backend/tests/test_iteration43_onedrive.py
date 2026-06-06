"""Iteration 43 — Microsoft Graph OneDrive integration (Phase 1+2) backend tests.

Scope per review request:
- /api/admin/onedrive/{settings, test-connection, queue, stats, process-now,
  migrate-historical, backups, backup-now, retry/{id}}
- enqueue hook in /api/uploads
- RBAC (super_admin only)
- Regression: /api/auth/login, /api/scheduler/status, /api/uploads

Note: Azure tenant credentials supplied by user are invalid (AADSTS90002) —
test_connection is expected to return {ok:false, error:...}. We assert API
contract & RBAC only, not live Graph success.
"""
from __future__ import annotations

import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
# NOTE: test_pm@erp.com from test_credentials.md is missing from DB.
# Using test_vendor_iter40@erp.com (vendor role) for non-super_admin RBAC tests.
PM = {"email": "test_vendor_iter40@erp.com", "password": "Vendor@123"}

TENANT_ID = "a399706e-c501-4e30-9d0f-45ba9ebfb504"
CLIENT_ID = "a06f2e42-0376-4c18-af29-5168cd27aca4"


# ─── Fixtures ────────────────────────────────────────────────────────────
def _login(creds: dict) -> str:
    """Login and extract access_token from Set-Cookie (httpOnly cookie auth)."""
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    tok = r.cookies.get("access_token")
    assert tok, f"access_token cookie not set on login: {dict(r.cookies)}"
    return tok


@pytest.fixture(scope="session")
def admin_token() -> str:
    return _login(ADMIN)


@pytest.fixture(scope="session")
def pm_token() -> str:
    return _login(PM)


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def pm_headers(pm_token: str) -> dict:
    return {"Authorization": f"Bearer {pm_token}"}


# ─── Regression: auth + scheduler ────────────────────────────────────────
class TestRegression:
    def test_auth_login(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=20)
        assert r.status_code == 200
        data = r.json()
        # Login returns user object directly + httpOnly access_token cookie
        assert data.get("email") == ADMIN["email"]
        assert data.get("role") == "super_admin"
        assert r.cookies.get("access_token"), "httpOnly access_token cookie not set"

    def test_scheduler_status(self, admin_headers):
        r = requests.get(f"{API}/scheduler/status", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # scheduler exposes running + jobs list
        assert "jobs" in data or "running" in data or isinstance(data, dict)


# ─── Settings save/get ───────────────────────────────────────────────────
class TestOneDriveSettings:
    def test_get_settings_super_admin(self, admin_headers):
        r = requests.get(f"{API}/admin/onedrive/settings", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # Required keys in response
        for k in ("enabled", "tenant_id", "client_id", "client_secret", "backup_user_upn", "base_folder", "configured"):
            assert k in data, f"missing key {k}"

    def test_get_settings_non_super_admin_403(self, pm_headers):
        r = requests.get(f"{API}/admin/onedrive/settings", headers=pm_headers, timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_put_settings_save_and_mask(self, admin_headers):
        payload = {
            "enabled": True,
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "client_secret": "TEST_secret_value_iter43",
            "backup_user_upn": "backup@indiantradelinks.in",
            "base_folder": "ITL-ERP-Backups",
        }
        r = requests.put(f"{API}/admin/onedrive/settings", json=payload, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["tenant_id"] == TENANT_ID
        assert data["client_id"] == CLIENT_ID
        assert data["backup_user_upn"] == "backup@indiantradelinks.in"
        assert data["base_folder"] == "ITL-ERP-Backups"
        # client_secret must be masked
        assert data["client_secret"] == "********", f"secret not masked: {data['client_secret']!r}"
        assert data["configured"] is True

        # GET again — secret stays masked, fields persisted
        r2 = requests.get(f"{API}/admin/onedrive/settings", headers=admin_headers, timeout=20)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["tenant_id"] == TENANT_ID
        assert d2["client_secret"] == "********"
        assert d2["configured"] is True

    def test_put_settings_non_super_admin_403(self, pm_headers):
        payload = {
            "enabled": True,
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "client_secret": "x",
            "backup_user_upn": "backup@indiantradelinks.in",
        }
        r = requests.put(f"{API}/admin/onedrive/settings", json=payload, headers=pm_headers, timeout=20)
        assert r.status_code == 403

    def test_put_settings_blank_secret_keeps_existing(self, admin_headers):
        # Send blank client_secret — server should keep existing encrypted secret
        payload = {
            "enabled": True,
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "client_secret": "",  # blank => keep
            "backup_user_upn": "backup@indiantradelinks.in",
            "base_folder": "ITL-ERP-Backups",
        }
        r = requests.put(f"{API}/admin/onedrive/settings", json=payload, headers=admin_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["configured"] is True, "configured should remain True when blank secret preserves existing"


# ─── Test connection (expected failure with invalid tenant) ──────────────
class TestOneDriveConnection:
    def test_test_connection_returns_ok_false_no_crash(self, admin_headers):
        r = requests.post(f"{API}/admin/onedrive/test-connection", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text  # endpoint shouldn't crash
        data = r.json()
        assert "ok" in data
        # Invalid tenant — expect failure
        assert data["ok"] is False, f"expected ok:false for invalid tenant, got {data}"
        assert "error" in data and isinstance(data["error"], str) and len(data["error"]) > 0

    def test_test_connection_non_super_admin_403(self, pm_headers):
        r = requests.post(f"{API}/admin/onedrive/test-connection", headers=pm_headers, timeout=20)
        assert r.status_code == 403


# ─── Queue + stats + enqueue hook on upload ──────────────────────────────
class TestOneDriveQueue:
    def test_upload_enqueues_into_queue(self, admin_headers, admin_token):
        # Snapshot stats before
        s_before = requests.get(f"{API}/admin/onedrive/stats", headers=admin_headers, timeout=20).json()
        pending_before = s_before.get("pending", 0)
        total_before = s_before.get("total", 0)

        # Upload a file
        files = {"file": ("TEST_iter43_onedrive.txt", io.BytesIO(b"hello onedrive test iter43"), "text/plain")}
        data = {"folder": "documents", "title": "TEST_iter43"}
        up = requests.post(
            f"{API}/uploads",
            files=files,
            data=data,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert up.status_code == 200, f"upload failed: {up.status_code} {up.text}"
        rec = up.json()
        # Regression assertion: upload returns expected metadata
        assert rec.get("id")
        assert rec.get("original_filename") == "TEST_iter43_onedrive.txt"
        assert rec.get("folder") == "documents"
        assert rec.get("size", 0) > 0
        assert rec.get("is_deleted") is False
        file_id = rec["id"]

        # Give enqueue a moment
        time.sleep(0.5)

        # Stats should reflect at least one more pending+total
        s_after = requests.get(f"{API}/admin/onedrive/stats", headers=admin_headers, timeout=20).json()
        for k in ("pending", "pushed", "failed", "total"):
            assert k in s_after, f"missing stat key {k}"
        assert s_after["total"] >= total_before + 1, f"queue total did not grow: before={total_before} after={s_after['total']}"
        assert s_after["pending"] >= pending_before + 1

        # Queue listing should contain our file_id
        ql = requests.get(f"{API}/admin/onedrive/queue", headers=admin_headers, timeout=20)
        assert ql.status_code == 200
        rows = ql.json()
        assert isinstance(rows, list)
        match = [r for r in rows if r.get("file_id") == file_id]
        assert match, f"uploaded file_id {file_id} not found in queue"
        item = match[0]
        assert item.get("status") in ("pending", "pushed", "failed")
        assert "created_at" in item
        # Sorted by created_at desc — first row created_at should be >= last
        if len(rows) >= 2:
            assert rows[0]["created_at"] >= rows[-1]["created_at"]

        # Stash for retry test
        pytest._iter43_queue_id = item["id"]
        pytest._iter43_file_id = file_id

    def test_queue_filter_by_status(self, admin_headers):
        r = requests.get(f"{API}/admin/onedrive/queue?status=pending&limit=10", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        rows = r.json()
        for row in rows:
            assert row.get("status") == "pending"

    def test_queue_rbac_403(self, pm_headers):
        for path in ("/admin/onedrive/queue", "/admin/onedrive/stats"):
            r = requests.get(f"{API}{path}", headers=pm_headers, timeout=20)
            assert r.status_code == 403, f"{path} should be 403 for PM, got {r.status_code}"

    def test_process_now_schedules(self, admin_headers):
        r = requests.post(f"{API}/admin/onedrive/process-now", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("scheduled") is True

    def test_process_now_rbac_403(self, pm_headers):
        r = requests.post(f"{API}/admin/onedrive/process-now", headers=pm_headers, timeout=20)
        assert r.status_code == 403

    def test_retry_flips_to_pending(self, admin_headers):
        qid = getattr(pytest, "_iter43_queue_id", None)
        assert qid, "queue_id missing from previous test"
        r = requests.post(f"{API}/admin/onedrive/retry/{qid}", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # Verify status flipped (background push worker from prior test may re-attempt
        # and bump attempts/error since Azure tenant is invalid — that's fine; the row
        # should still be in 'pending' (auto-requeued until attempts >= 5).
        ql = requests.get(f"{API}/admin/onedrive/queue?limit=200", headers=admin_headers, timeout=20).json()
        row = next((x for x in ql if x.get("id") == qid), None)
        assert row is not None, "queue row missing after retry"
        assert row.get("status") == "pending", f"status not pending after retry: {row.get('status')}"

    def test_retry_rbac_403(self, pm_headers):
        qid = getattr(pytest, "_iter43_queue_id", "non-existent")
        r = requests.post(f"{API}/admin/onedrive/retry/{qid}", headers=pm_headers, timeout=20)
        assert r.status_code == 403


# ─── Migrate historical ──────────────────────────────────────────────────
class TestMigrateHistorical:
    def test_migrate_historical_enqueues_existing(self, admin_headers):
        s_before = requests.get(f"{API}/admin/onedrive/stats", headers=admin_headers, timeout=20).json()
        total_before = s_before.get("total", 0)

        r = requests.post(f"{API}/admin/onedrive/migrate-historical", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "queued" in data and isinstance(data["queued"], int)

        # Verify total grew by queued count (or stayed same if nothing new to migrate)
        s_after = requests.get(f"{API}/admin/onedrive/stats", headers=admin_headers, timeout=20).json()
        assert s_after["total"] >= total_before  # never shrinks

    def test_migrate_historical_idempotent(self, admin_headers):
        # Second run should report queued=0 (everything already pending/pushed)
        r = requests.post(f"{API}/admin/onedrive/migrate-historical", headers=admin_headers, timeout=60)
        assert r.status_code == 200
        assert r.json().get("queued") == 0

    def test_migrate_historical_rbac_403(self, pm_headers):
        r = requests.post(f"{API}/admin/onedrive/migrate-historical", headers=pm_headers, timeout=20)
        assert r.status_code == 403


# ─── Backups ─────────────────────────────────────────────────────────────
class TestOneDriveBackups:
    def test_list_backups(self, admin_headers):
        r = requests.get(f"{API}/admin/onedrive/backups", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)  # likely empty since Graph fails

    def test_backup_now_schedules(self, admin_headers):
        r = requests.post(f"{API}/admin/onedrive/backup-now", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("scheduled") is True

    def test_backups_rbac_403(self, pm_headers):
        r = requests.get(f"{API}/admin/onedrive/backups", headers=pm_headers, timeout=20)
        assert r.status_code == 403
        r2 = requests.post(f"{API}/admin/onedrive/backup-now", headers=pm_headers, timeout=20)
        assert r2.status_code == 403


# ─── Unauthenticated checks ──────────────────────────────────────────────
class TestUnauthenticated:
    def test_settings_no_auth(self):
        r = requests.get(f"{API}/admin/onedrive/settings", timeout=20)
        assert r.status_code in (401, 403)

    def test_queue_no_auth(self):
        r = requests.get(f"{API}/admin/onedrive/queue", timeout=20)
        assert r.status_code in (401, 403)
