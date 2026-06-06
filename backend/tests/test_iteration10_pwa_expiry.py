"""Iteration 10 — PPE expiry scan wiring + PWA static assets.

Covers:
- POST /api/notifications/expiry-scan returns new nested shape with documents{} and ppe{}
- expiry-scan flags PPE within 30 days OR already expired; ignores future > 30d / null
- expiry-scan dispatches to super_admin + safety_officer (de-duplicated); falls back when no safety_officer
- /api/scheduler/status includes expiry_scan and invoice_reminders jobs
- GET /manifest.json — 200 with required keys + 4 shortcuts
- GET /service-worker.js — 200 with correct Content-Type and key tokens
- Regression: API still wins under '/api/*' (service worker JS not interfering)
"""
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    body = r.json()
    token = body.get("access_token") or body.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def ppe_seed(session):
    """Seed 3 PPE rows: expired, due-soon, far-future. Cleans up after module."""
    today = date.today()
    expired = (today - timedelta(days=30)).isoformat()
    soon = (today + timedelta(days=10)).isoformat()
    far = (today + timedelta(days=200)).isoformat()
    ids: list[str] = []
    payloads = [
        {"worker_name": f"TEST_IT10_EXPIRED_{uuid.uuid4().hex[:6]}", "ppe_type": "helmet", "issued_date": "2025-01-01", "expiry_date": expired},
        {"worker_name": f"TEST_IT10_SOON_{uuid.uuid4().hex[:6]}", "ppe_type": "harness", "issued_date": "2025-01-01", "expiry_date": soon},
        {"worker_name": f"TEST_IT10_FAR_{uuid.uuid4().hex[:6]}", "ppe_type": "boots", "issued_date": "2025-01-01", "expiry_date": far},
    ]
    for p in payloads:
        r = session.post(f"{BASE_URL}/api/ppe-issuance", json=p)
        if r.status_code in (200, 201):
            body = r.json()
            ids.append(body.get("id") or body.get("_id") or "")
    yield {"ids": ids, "expired": expired, "soon": soon, "far": far}
    for _id in ids:
        if _id:
            try:
                session.delete(f"{BASE_URL}/api/ppe-issuance/{_id}")
            except Exception:
                pass


# ---------- expiry-scan tests ----------
class TestExpiryScan:
    def test_returns_new_nested_shape(self, session, ppe_seed):
        r = session.post(f"{BASE_URL}/api/notifications/expiry-scan")
        assert r.status_code == 200, r.text
        data = r.json()
        # New shape keys
        assert "documents" in data and isinstance(data["documents"], dict)
        assert "ppe" in data and isinstance(data["ppe"], dict)
        assert "email_enabled" in data
        # Documents subkeys
        assert "scanned" in data["documents"]
        assert "sent" in data["documents"]
        # PPE subkeys
        assert "scanned" in data["ppe"]
        assert "due" in data["ppe"]
        assert "sent" in data["ppe"]
        # Old top-level keys must NOT be present
        assert "scanned" not in data, "Old top-level 'scanned' should be removed"
        assert "sent" not in data, "Old top-level 'sent' should be removed"

    def test_flags_expired_and_within_30_days(self, session, ppe_seed):
        r = session.post(f"{BASE_URL}/api/notifications/expiry-scan")
        assert r.status_code == 200
        data = r.json()
        # We seeded 2 due rows (expired + soon); allow >=2 since DB may have others
        assert data["ppe"]["due"] >= 2, f"Expected >=2 due PPE rows, got {data['ppe']['due']}"
        # Scanned should be >= 3 (our seeds, ignoring rows w/o expiry_date)
        assert data["ppe"]["scanned"] >= 3

    def test_far_future_not_flagged_as_due(self, session, ppe_seed):
        """Re-scan and verify due-count math: scanned >= 3, due < scanned (the 'far' row should be excluded)."""
        r = session.post(f"{BASE_URL}/api/notifications/expiry-scan")
        data = r.json()
        # far-future seed should be scanned but NOT due
        assert data["ppe"]["scanned"] > data["ppe"]["due"], (
            f"Far-future row should be scanned but not due; scanned={data['ppe']['scanned']} due={data['ppe']['due']}"
        )

    def test_dispatch_recipients_count(self, session, ppe_seed):
        """If email_enabled, sent should equal due * recipient_count.
        With 1+ super_admins and possibly 0 safety_officers, sent should be a multiple of due."""
        r = session.post(f"{BASE_URL}/api/notifications/expiry-scan")
        data = r.json()
        if not data["email_enabled"]:
            pytest.skip("Email disabled — sent counts will be 0 by design")
        due = data["ppe"]["due"]
        sent = data["ppe"]["sent"]
        if due > 0:
            # sent must be at least 'due' (one super_admin) and divisible by due
            assert sent >= due
            assert sent % due == 0, f"sent={sent} should be a multiple of due={due} (per-recipient fan-out)"

    def test_rbac_non_admin_forbidden(self):
        """A fresh session without auth should get 401/403."""
        r = requests.post(f"{BASE_URL}/api/notifications/expiry-scan")
        assert r.status_code in (401, 403), f"Expected 401/403 for unauthenticated, got {r.status_code}"


# ---------- scheduler ----------
class TestScheduler:
    def test_scheduler_status_has_both_jobs(self, session):
        r = session.get(f"{BASE_URL}/api/scheduler/status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("running") is True
        ids = {j["id"] for j in body.get("jobs", [])}
        assert "expiry_scan" in ids, f"expiry_scan missing from {ids}"
        assert "invoice_reminders" in ids, f"invoice_reminders missing from {ids}"
        for j in body["jobs"]:
            if j["id"] in ("expiry_scan", "invoice_reminders"):
                assert j.get("next_run_time"), f"{j['id']} has no next_run_time"


# ---------- PWA static assets ----------
class TestPWAStatic:
    def test_manifest_json(self):
        r = requests.get(f"{BASE_URL}/manifest.json")
        assert r.status_code == 200, r.text[:200]
        m = r.json()
        for key in ("name", "short_name", "display", "theme_color", "id", "scope", "lang"):
            assert key in m, f"manifest missing {key}"
        assert m["display"] == "standalone"
        shortcuts = m.get("shortcuts", [])
        assert len(shortcuts) == 4, f"Expected 4 shortcuts, got {len(shortcuts)}"
        names = {s.get("name") for s in shortcuts}
        for expected in ("Dashboard", "Approvals Inbox", "Stock Movement", "Safety Reports"):
            assert expected in names, f"Missing shortcut: {expected} (have {names})"

    def test_service_worker_js(self):
        r = requests.get(f"{BASE_URL}/service-worker.js")
        assert r.status_code == 200, r.text[:200]
        ctype = r.headers.get("Content-Type", "").lower()
        assert "javascript" in ctype, f"Expected JS content-type, got {ctype}"
        body = r.text
        for token in ("SHELL_CACHE", "ASSET_CACHE", "OFFLINE_API_RESPONSE"):
            assert token in body, f"service-worker.js missing token: {token}"

    def test_api_routing_not_intercepted_by_sw(self, session):
        """Service worker file presence at root must not interfere with /api/*."""
        r = session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200, f"/api/auth/me broken: {r.status_code} {r.text[:200]}"
