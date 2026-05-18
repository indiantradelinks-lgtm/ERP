"""Iteration 4 backend tests: scheduler status endpoint + post-refactor smoke.

Validates the new GET /api/scheduler/status endpoint and confirms the server.py
refactor (now thin entrypoint + routers/) did not break key endpoints across all
iterations (auth, RBAC, CRUD, dashboard, files, approvals, notifications, exports).
"""
import os
import io
import uuid
import pytest
import requests


def _base():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
                    break
    return url.rstrip("/")


BASE = _base()
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"

RUN_TAG = uuid.uuid4().hex[:6]
HR_EMAIL = f"hr_iter4_{RUN_TAG}@erp.com"
HR_PASS = "Hr@1234"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def hr_session(admin_session):
    admin_session.post(f"{API}/auth/register", json={
        "email": HR_EMAIL, "password": HR_PASS, "name": "HR Iter4", "role": "hr_executive"
    }, timeout=20)
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": HR_EMAIL, "password": HR_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return s


# ---------------- Scheduler ----------------
class TestScheduler:
    def test_scheduler_status_running(self, admin_session):
        r = admin_session.get(f"{API}/scheduler/status", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("running") is True
        jobs = d.get("jobs") or []
        ids = sorted([j["id"] for j in jobs])
        assert ids == ["expiry_scan", "invoice_reminders"], ids
        for j in jobs:
            assert j.get("next_run_time"), j
            assert "cron" in (j.get("trigger") or "")
        assert "last_results" in d
        lr = d["last_results"]
        assert "expiry_scan" in lr and "invoice_reminders" in lr


# ---------------- Auth ----------------
class TestAuth:
    def test_login_me_permissions(self, admin_session):
        me = admin_session.get(f"{API}/auth/me", timeout=20)
        assert me.status_code == 200
        assert me.json().get("email") == ADMIN_EMAIL
        perms = admin_session.get(f"{API}/auth/permissions", timeout=20)
        assert perms.status_code == 200
        assert isinstance(perms.json(), (list, dict))

    def test_users_list(self, admin_session):
        r = admin_session.get(f"{API}/auth/users", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_register_requires_super_admin(self, hr_session):
        r = hr_session.post(f"{API}/auth/register", json={
            "email": f"x_{RUN_TAG}@e.com", "password": "P@ss1234", "name": "x", "role": "hr_executive"
        }, timeout=20)
        assert r.status_code in (401, 403)


# ---------------- RBAC sanity post-refactor ----------------
class TestRBAC:
    def test_hr_cannot_access_journal_entries(self, hr_session):
        r = hr_session.get(f"{API}/journal-entries", timeout=20)
        assert r.status_code == 403

    def test_hr_can_access_employees(self, hr_session):
        r = hr_session.get(f"{API}/employees", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- CRUD modules smoke ----------------
MODULES = [
    "clients", "vendors", "employees", "attendance", "projects",
    "inventory", "purchase-orders", "quotations", "journal-entries",
    "safety-reports", "assets", "payroll", "vehicles", "documents",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_list_admin(admin_session, mod):
    r = admin_session.get(f"{API}/{mod}", timeout=30)
    assert r.status_code == 200, f"{mod}: {r.status_code} {r.text[:200]}"
    assert isinstance(r.json(), list), mod


# ---------------- Dashboard ----------------
class TestDashboard:
    def test_summary(self, admin_session):
        r = admin_session.get(f"{API}/dashboard/summary", timeout=30)
        assert r.status_code == 200
        d = r.json()
        # Some keys should be present; loose check across versions
        assert isinstance(d, dict)
        assert len(d) > 0


# ---------------- Approvals ----------------
class TestApprovals:
    def test_inbox_mine(self, admin_session):
        r = admin_session.get(f"{API}/approvals/inbox/mine", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_chains_config(self, admin_session):
        r = admin_session.get(f"{API}/approvals-config/chains", timeout=20)
        assert r.status_code == 200

    def test_create_and_action(self, admin_session):
        cr = admin_session.post(f"{API}/approvals", json={
            "title": f"TEST IT4 {RUN_TAG}", "type": "leave", "amount": 0, "requested_by": "admin@erp.com"
        }, timeout=20)
        assert cr.status_code == 200, cr.text
        aid = cr.json()["id"]
        try:
            ar = admin_session.post(f"{API}/approvals/{aid}/action",
                                    json={"action": "approve", "comment": "ok"}, timeout=30)
            assert ar.status_code == 200, ar.text
        finally:
            admin_session.delete(f"{API}/approvals/{aid}", timeout=20)


# ---------------- Files end-to-end ----------------
class TestFiles:
    def test_upload_list_download_delete(self, admin_session):
        content = b"iter4-upload-" + RUN_TAG.encode()
        up = admin_session.post(
            f"{API}/uploads",
            files={"file": (f"iter4_{RUN_TAG}.txt", content, "text/plain")},
            data={"folder": "documents", "parent_type": "documents", "title": f"TEST_IT4_{RUN_TAG}"},
            timeout=60,
        )
        assert up.status_code == 200, up.text
        fid = up.json()["id"]
        # list shows it
        ls = admin_session.get(f"{API}/files", params={"folder": "documents"}, timeout=20)
        assert fid in [x["id"] for x in ls.json()]
        # download bytes
        dl = admin_session.get(f"{API}/files/{fid}/download", timeout=30)
        assert dl.status_code == 200 and dl.content == content
        # query auth token download
        token = admin_session.cookies.get("access_token")
        assert token
        dl2 = requests.get(f"{API}/files/{fid}/download", params={"auth": token}, timeout=30)
        assert dl2.status_code == 200 and dl2.content == content
        # delete -> 404 + excluded
        d = admin_session.delete(f"{API}/files/{fid}", timeout=20)
        assert d.status_code == 200
        dl3 = admin_session.get(f"{API}/files/{fid}/download", timeout=20)
        assert dl3.status_code == 404
        ls2 = admin_session.get(f"{API}/files", params={"folder": "documents"}, timeout=20)
        assert fid not in [x["id"] for x in ls2.json()]


# ---------------- Notifications ----------------
class TestNotifications:
    def test_email_status(self, admin_session):
        r = admin_session.get(f"{API}/notifications/email-status", timeout=20)
        assert r.status_code == 200
        assert "enabled" in r.json()

    def test_expiry_scan_admin(self, admin_session):
        r = admin_session.post(f"{API}/notifications/expiry-scan", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "scanned" in d and "sent" in d

    def test_invoice_reminders_admin(self, admin_session):
        r = admin_session.post(f"{API}/notifications/invoice-reminders", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "scanned" in d and "sent" in d


# ---------------- Exports ----------------
class TestExports:
    @pytest.mark.parametrize("res", ["clients", "employees", "projects"])
    def test_export_xlsx(self, admin_session, res):
        r = admin_session.get(f"{API}/export/{res}.xlsx", timeout=60)
        assert r.status_code == 200, f"{res}: {r.status_code}"
        ct = r.headers.get("content-type", "")
        assert "spreadsheet" in ct or "octet-stream" in ct or "xlsx" in ct

    @pytest.mark.parametrize("res", ["clients", "employees"])
    def test_export_pdf(self, admin_session, res):
        r = admin_session.get(f"{API}/export/{res}.pdf", timeout=60)
        assert r.status_code == 200, f"{res}: {r.status_code}"
        assert r.headers.get("content-type", "").startswith("application/pdf")


# ---------------- Logout ----------------
class TestLogout:
    def test_logout(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
        assert r.status_code == 200
        out = s.post(f"{API}/auth/logout", timeout=20)
        assert out.status_code in (200, 204)
        me = s.get(f"{API}/auth/me", timeout=20)
        assert me.status_code in (401, 403)
