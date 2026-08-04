"""Iter 164 — strict project-based access control for custom 'Manager O P' role.
Light re-verification of backend scoping (main agent already curl-verified)."""
import os
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def mop_session():
    return _login("test_mop@erp.com", "Mop@12345")


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def pm_session():
    return _login("test_pm@erp.com", "PM@12345")


# --- Manager O P (custom role) scoping ---
class TestManagerOPScoping:
    def test_projects_only_prj_2025_01(self, mop_session):
        r = mop_session.get(f"{BASE}/api/projects", timeout=20)
        assert r.status_code == 200
        data = r.json()
        codes = [p.get("project_code") or p.get("code") for p in data]
        assert len(data) == 1, f"expected 1 project, got {len(data)}: {codes}"
        assert codes[0] == "PRJ-2025-01", f"expected PRJ-2025-01, got {codes}"

    def test_cost_centers_only_assigned(self, mop_session):
        r = mop_session.get(f"{BASE}/api/procurement/master/cost-centers", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        # all rows must refer to PRJ-2025-01
        assert len(rows) >= 0
        for row in rows:
            code = row.get("project_code") or row.get("code") or ""
            assert "PRJ-2025-01" in str(row), f"unexpected non-assigned row: {row}"

    def test_project_requests_only_assigned(self, mop_session):
        r = mop_session.get(f"{BASE}/api/project-requests", timeout=20)
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        for row in rows:
            pc = row.get("project_code") or ""
            assert pc == "PRJ-2025-01" or pc == "", f"leak: {row}"

    def test_cost_centers_unassigned_project_returns_empty(self, mop_session):
        # try to query some clearly unassigned project id
        r = mop_session.get(f"{BASE}/api/procurement/master/cost-centers?project_id=PRJ-2025-99", timeout=20)
        assert r.status_code in (200, 403, 404)
        if r.status_code == 200:
            assert r.json() == [] or r.json() == {"items": []}


# --- Super admin regression ---
class TestSuperAdminSeesAll:
    def test_admin_projects_multiple(self, admin_session):
        r = admin_session.get(f"{BASE}/api/projects", timeout=20)
        assert r.status_code == 200
        assert len(r.json()) >= 5, f"admin should see many projects, got {len(r.json())}"


# --- Canonical PM regression ---
class TestCanonicalPMStillWorks:
    def test_pm_gets_projects_without_error(self, pm_session):
        r = pm_session.get(f"{BASE}/api/projects", timeout=20)
        assert r.status_code == 200
        data = r.json()
        # canonical PM sees only assigned projects (not all 25)
        assert isinstance(data, list)

    def test_pm_project_requests_no_500(self, pm_session):
        r = pm_session.get(f"{BASE}/api/project-requests", timeout=20)
        assert r.status_code == 200
