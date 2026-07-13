"""Iteration 3 backend tests: object storage uploads, files CRUD, my-approvals inbox,
email notifications status, expiry-scan, invoice-reminders, approval action fires email."""
import os
import uuid
import pytest
import requests


def _base():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
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
HR_EMAIL = f"hr_it3_{RUN_TAG}@test.com"
HR_PASS = "HrTest@123"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def hr_session(admin_session):
    admin_session.post(f"{API}/auth/register", json={
        "email": HR_EMAIL, "password": HR_PASS, "name": "HR It3", "role": "hr_executive"
    }, timeout=20)
    s = requests.Session()
    rl = s.post(f"{API}/auth/login", json={"email": HR_EMAIL, "password": HR_PASS}, timeout=20)
    assert rl.status_code == 200, rl.text
    return s


# ---------------- Uploads / files ----------------
class TestUploads:
    def test_upload_requires_auth(self):
        r = requests.post(f"{API}/uploads", files={"file": ("a.txt", b"hello")},
                          data={"folder": "documents"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_upload_documents(self, admin_session):
        content = b"hello from iteration3 " + RUN_TAG.encode()
        r = admin_session.post(
            f"{API}/uploads",
            files={"file": (f"it3_{RUN_TAG}.txt", content, "text/plain")},
            data={"folder": "documents", "parent_type": "documents", "title": f"TEST_IT3_{RUN_TAG}"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "id" in d
        assert d["storage_path"].startswith("worksite-command/documents/")
        assert d["size"] == len(content)
        assert d["content_type"] == "text/plain"
        # Save for next tests
        pytest._it3_file_id = d["id"]  # type: ignore
        pytest._it3_file_content = content  # type: ignore

    def test_upload_safety_image(self, admin_session):
        # Tiny PNG bytes (1x1 white)
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
            b"\xc0\x00\x00\x00\x03\x00\x01\x9c\x18\xfa\xdf\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = admin_session.post(
            f"{API}/uploads",
            files={"file": (f"it3_{RUN_TAG}.png", png, "image/png")},
            data={"folder": "safety", "parent_type": "safety_report", "parent_id": f"sf_{RUN_TAG}"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["storage_path"].startswith("worksite-command/safety/")
        assert d["content_type"] == "image/png"
        pytest._it3_safety_id = d["id"]  # type: ignore

    def test_upload_bad_folder(self, admin_session):
        r = admin_session.post(
            f"{API}/uploads",
            files={"file": ("x.txt", b"x", "text/plain")},
            data={"folder": "invalid"},
            timeout=30,
        )
        assert r.status_code == 400

    def test_list_files_documents(self, admin_session):
        r = admin_session.get(f"{API}/files", params={"folder": "documents"}, timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        ids = [x["id"] for x in rows]
        assert pytest._it3_file_id in ids
        # ensure soft-deleted not included is checked in delete test

    def test_list_files_safety(self, admin_session):
        r = admin_session.get(f"{API}/files", params={"folder": "safety"}, timeout=20)
        assert r.status_code == 200
        rows = r.json()
        ids = [x["id"] for x in rows]
        assert pytest._it3_safety_id in ids

    def test_download_file_cookie_auth(self, admin_session):
        r = admin_session.get(f"{API}/files/{pytest._it3_file_id}/download", timeout=60)
        assert r.status_code == 200
        assert r.content == pytest._it3_file_content
        assert r.headers.get("content-type", "").startswith("text/plain")

    def test_download_file_query_auth(self, admin_session):
        # extract access_token cookie
        token = admin_session.cookies.get("access_token")
        assert token
        bare = requests.Session()
        r = bare.get(f"{API}/files/{pytest._it3_file_id}/download",
                     params={"auth": token}, timeout=60)
        assert r.status_code == 200
        assert r.content == pytest._it3_file_content

    def test_download_unknown_404(self, admin_session):
        r = admin_session.get(f"{API}/files/does-not-exist/download", timeout=20)
        assert r.status_code == 404

    def test_delete_soft_delete(self, admin_session):
        # delete the safety file
        r = admin_session.delete(f"{API}/files/{pytest._it3_safety_id}", timeout=20)
        assert r.status_code == 200
        # subsequent download 404
        r2 = admin_session.get(f"{API}/files/{pytest._it3_safety_id}/download", timeout=20)
        assert r2.status_code == 404
        # list excludes
        r3 = admin_session.get(f"{API}/files", params={"folder": "safety"}, timeout=20)
        ids = [x["id"] for x in r3.json()]
        assert pytest._it3_safety_id not in ids


# ---------------- My Approvals inbox ----------------
class TestMyInbox:
    def test_inbox_super_admin(self, admin_session):
        r = admin_session.get(f"{API}/approvals/inbox/mine", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        for x in rows:
            assert x.get("status") in ("pending", "in_progress", None)
            assert "_my_step" in x or "current_step" in x

    def test_inbox_includes_newly_created(self, admin_session):
        cr = admin_session.post(f"{API}/approvals", json={
            "title": f"TEST INBOX {RUN_TAG}", "type": "leave", "amount": 0, "requested_by": "tester"
        }, timeout=20)
        assert cr.status_code == 200, cr.text
        aid = cr.json()["id"]
        try:
            r = admin_session.get(f"{API}/approvals/inbox/mine", timeout=20)
            assert r.status_code == 200
            ids = [x["id"] for x in r.json()]
            assert aid in ids
        finally:
            admin_session.delete(f"{API}/approvals/{aid}", timeout=20)


# ---------------- Email notifications ----------------
class TestEmailNotifications:
    def test_email_status_enabled(self, admin_session):
        r = admin_session.get(f"{API}/notifications/email-status", timeout=20)
        assert r.status_code == 200
        assert r.json() == {"enabled": True}

    def test_expiry_scan_admin_ok(self, admin_session):
        r = admin_session.post(f"{API}/notifications/expiry-scan", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "scanned" in d and "sent" in d
        assert d.get("email_enabled") is True

    def test_expiry_scan_forbidden_for_hr(self, hr_session):
        r = hr_session.post(f"{API}/notifications/expiry-scan", timeout=30)
        assert r.status_code == 403

    def test_invoice_reminders_admin_ok(self, admin_session):
        r = admin_session.post(f"{API}/notifications/invoice-reminders", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "scanned" in d and "sent" in d

    def test_invoice_reminders_forbidden_for_hr(self, hr_session):
        r = hr_session.post(f"{API}/notifications/invoice-reminders", timeout=30)
        assert r.status_code == 403

    def test_approval_action_fires_email_no_error(self, admin_session):
        cr = admin_session.post(f"{API}/approvals", json={
            "title": f"TEST EMAIL {RUN_TAG}", "type": "leave", "amount": 0, "requested_by": "admin@erp.com"
        }, timeout=20)
        aid = cr.json()["id"]
        try:
            r = admin_session.post(f"{API}/approvals/{aid}/action",
                                   json={"action": "approve", "comment": "ok"}, timeout=30)
            assert r.status_code == 200, r.text
        finally:
            admin_session.delete(f"{API}/approvals/{aid}", timeout=20)
