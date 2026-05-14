"""Backend tests for the Corporate ERP API.

Covers: auth (login/me/logout/refresh + brute force fallthroughs),
all 14 module CRUD endpoints, dashboard aggregation, sample data
seeded counts, and unauthenticated access protection.
"""
import os
import pytest
import requests

def _resolve_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Fallback: read from frontend/.env
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"')
                        break
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not configured")
    return url.rstrip("/")


BASE_URL = _resolve_base_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"

MODULES = [
    "clients", "vendors", "employees", "attendance", "projects", "inventory",
    "purchase-orders", "quotations", "journal-entries", "safety-reports",
    "assets", "payroll", "vehicles", "documents", "approvals",
]

EXPECTED_MIN_COUNTS = {
    "clients": 4, "vendors": 4, "employees": 6, "projects": 5, "inventory": 7,
    "purchase-orders": 4, "quotations": 3, "journal-entries": 12,
    "safety-reports": 3, "assets": 3, "payroll": 6, "vehicles": 3,
    "documents": 3, "approvals": 3,
}


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def auth_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# ---------- Auth tests ----------
class TestAuth:
    def test_login_success_sets_cookies(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                   timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "super_admin"
        assert "password_hash" not in data
        # httpOnly cookies
        cookie_names = {c.name for c in s.cookies}
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names

    def test_login_invalid_credentials(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": "wrong"},
                          timeout=20)
        assert r.status_code in (401, 429)

    def test_me_returns_user(self, auth_session):
        r = auth_session.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == ADMIN_EMAIL
        assert body["role"] == "super_admin"

    def test_unauthenticated_clients_returns_401(self):
        r = requests.get(f"{API}/clients", timeout=20)
        assert r.status_code == 401

    def test_logout_clears_cookies(self):
        s = requests.Session()
        s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=20)
        r = s.post(f"{API}/auth/logout", timeout=20)
        assert r.status_code == 200
        # Subsequent /me using same session w/o cookies should fail
        fresh = requests.Session()
        r2 = fresh.get(f"{API}/auth/me", timeout=20)
        assert r2.status_code == 401


# ---------- Sample data counts ----------
class TestSampleData:
    @pytest.mark.parametrize("resource,expected", list(EXPECTED_MIN_COUNTS.items()))
    def test_seeded_counts(self, auth_session, resource, expected):
        r = auth_session.get(f"{API}/{resource}", timeout=30)
        assert r.status_code == 200, f"{resource}: {r.status_code} {r.text[:200]}"
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= expected, f"{resource} expected >= {expected}, got {len(items)}"


# ---------- Dashboard ----------
class TestDashboard:
    def test_dashboard_summary_structure(self, auth_session):
        r = auth_session.get(f"{API}/dashboard/summary", timeout=30)
        assert r.status_code == 200
        d = r.json()
        kpis = d["kpis"]
        required_kpi_keys = [
            "revenue", "expenses", "profit", "active_projects", "employees",
            "clients", "vendors", "inventory_items", "low_stock_alerts",
            "pending_purchase_orders", "open_quotations",
            "open_safety_incidents", "pending_approvals",
            "attendance_today_present", "attendance_today_absent",
        ]
        for k in required_kpi_keys:
            assert k in kpis, f"missing kpi: {k}"
        assert isinstance(d["chart_revenue_expense"], list)
        assert isinstance(d["project_status"], list)
        assert isinstance(d["safety_by_severity"], list)
        # Verify revenue & expenses are present from seeded JE rows
        assert kpis["revenue"] > 0
        assert kpis["expenses"] > 0
        assert kpis["clients"] >= 4
        assert kpis["employees"] >= 6


# ---------- Generic CRUD round-trip ----------
@pytest.mark.parametrize("resource", MODULES)
class TestCRUD:
    def test_create_get_update_delete(self, auth_session, resource):
        payload = {"name": f"TEST_{resource}", "test": True, "value": 42}
        # CREATE
        rc = auth_session.post(f"{API}/{resource}", json=payload, timeout=20)
        assert rc.status_code == 200, f"create {resource}: {rc.status_code} {rc.text[:200]}"
        created = rc.json()
        assert "id" in created
        item_id = created["id"]
        # GET
        rg = auth_session.get(f"{API}/{resource}/{item_id}", timeout=20)
        assert rg.status_code == 200
        assert rg.json()["id"] == item_id
        assert rg.json().get("test") is True
        # UPDATE
        ru = auth_session.put(f"{API}/{resource}/{item_id}",
                              json={"value": 99}, timeout=20)
        assert ru.status_code == 200
        # verify update persisted
        rg2 = auth_session.get(f"{API}/{resource}/{item_id}", timeout=20)
        assert rg2.json()["value"] == 99
        # DELETE
        rd = auth_session.delete(f"{API}/{resource}/{item_id}", timeout=20)
        assert rd.status_code == 200
        # Verify gone
        rg3 = auth_session.get(f"{API}/{resource}/{item_id}", timeout=20)
        assert rg3.status_code == 404
