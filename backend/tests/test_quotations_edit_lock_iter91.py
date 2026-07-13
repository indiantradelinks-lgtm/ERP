"""Iter 91 regression: only super_admin can directly PUT /api/quotations/{id}."""
import os

import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return s


@pytest.fixture
def sample_quote(admin_session):
    qs = admin_session.get(f"{API_URL}/api/quotations", timeout=10).json()
    assert qs, "no quotations seeded"
    return qs[0]


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=10)
    return s if r.status_code == 200 else None


def test_super_admin_can_edit_quotation(admin_session, sample_quote):
    qid = sample_quote["id"]
    orig = sample_quote.get("client")
    r = admin_session.put(f"{API_URL}/api/quotations/{qid}", json={**sample_quote, "client": orig}, timeout=10)
    assert r.status_code == 200


def test_sales_executive_blocked_from_direct_edit(sample_quote):
    s = _login("sales@erp.com", "Sales@123")
    if not s:
        pytest.skip("sales user not seeded")
    qid = sample_quote["id"]
    r = s.put(f"{API_URL}/api/quotations/{qid}", json={**sample_quote, "client": "HACKED"}, timeout=10)
    assert r.status_code == 403, r.text
    detail = r.json().get("detail", "").lower()
    assert "super admin" in detail or "only" in detail


def test_project_manager_blocked_from_direct_edit(admin_session, sample_quote):
    users = admin_session.get(f"{API_URL}/api/auth/users", timeout=10).json()
    pm = next((u for u in users if u.get("email") == "test_pm@erp.com"), None)
    if not pm:
        pytest.skip("test_pm not seeded")
    admin_session.post(f"{API_URL}/api/admin/users/{pm['id']}/reset-password",
                        json={"password": "PM@12345"}, timeout=10)
    s = _login("test_pm@erp.com", "PM@12345")
    assert s
    qid = sample_quote["id"]
    r = s.put(f"{API_URL}/api/quotations/{qid}", json={**sample_quote, "client": "HACKED"}, timeout=10)
    assert r.status_code == 403


def test_db_unchanged_after_blocked_edit(admin_session, sample_quote):
    """The DB must be untouched after a 403 — defensive integrity check."""
    qid = sample_quote["id"]
    before = admin_session.get(f"{API_URL}/api/quotations/{qid}", timeout=10).json()
    s = _login("sales@erp.com", "Sales@123")
    if not s:
        pytest.skip("sales user not seeded")
    s.put(f"{API_URL}/api/quotations/{qid}", json={**sample_quote, "client": "MALICIOUS"}, timeout=10)
    after = admin_session.get(f"{API_URL}/api/quotations/{qid}", timeout=10).json()
    assert after["client"] == before["client"]
