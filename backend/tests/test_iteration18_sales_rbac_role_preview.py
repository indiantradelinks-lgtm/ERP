"""Iteration 18 backend tests.

Covers:
1. Sales Reports endpoints now gated by `sales_reports:read` — project_manager
   must get 403, sales_executive and super_admin must get 200.
2. PM no-regression on enquiries / quotations / orders / enquiry-pulse.
3. New /api/admin/role-preview/{role} endpoint:
   - super_admin only (403 for project_manager)
   - super_admin role -> 9 departments, fallback_all=false
   - unmapped role -> all departments, fallback_all=true
   - explicitly mapped role -> only mapped slugs
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SALES = {"email": "sales@erp.com", "password": "Sales@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345"}

SALES_REPORT_ENDPOINTS = [
    "/api/sales/reports/monthly",
    "/api/sales/reports/by-client",
    "/api/sales/reports/by-service",
    "/api/sales/reports/won-lost",
    "/api/sales/reports/deadline-tracker",
]


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def sales_session():
    return _login(SALES)


@pytest.fixture(scope="module")
def pm_session():
    return _login(PM)


# -------- 1. Sales reports RBAC --------
class TestSalesReportsRBAC:
    @pytest.mark.parametrize("path", SALES_REPORT_ENDPOINTS)
    def test_pm_denied_on_reports(self, pm_session, path):
        r = pm_session.get(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code == 403, f"PM should be 403 on {path}, got {r.status_code}: {r.text[:200]}"

    def test_pm_denied_on_search(self, pm_session):
        r = pm_session.get(f"{BASE_URL}/api/sales/search?q=ENQ", timeout=15)
        assert r.status_code == 403, f"PM should be 403 on search, got {r.status_code}"

    @pytest.mark.parametrize("path", SALES_REPORT_ENDPOINTS)
    def test_sales_allowed_on_reports(self, sales_session, path):
        r = sales_session.get(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code == 200, f"sales_executive should be 200 on {path}, got {r.status_code}: {r.text[:200]}"

    def test_sales_allowed_on_search(self, sales_session):
        r = sales_session.get(f"{BASE_URL}/api/sales/search?q=ENQ", timeout=15)
        assert r.status_code == 200, f"sales_executive should be 200 on search, got {r.status_code}"

    @pytest.mark.parametrize("path", SALES_REPORT_ENDPOINTS)
    def test_admin_allowed_on_reports(self, admin_session, path):
        r = admin_session.get(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code == 200, f"super_admin should be 200 on {path}, got {r.status_code}"


# -------- 2. PM no-regression --------
class TestPMNoRegression:
    @pytest.mark.parametrize("path", [
        "/api/enquiries",
        "/api/quotations",
        "/api/orders",
        "/api/sales/enquiry-pulse",
    ])
    def test_pm_still_has_access(self, pm_session, path):
        r = pm_session.get(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code == 200, f"PM lost access to {path}: {r.status_code} {r.text[:200]}"


# -------- 3. role-preview endpoint --------
class TestRolePreview:
    def test_pm_denied(self, pm_session):
        r = pm_session.get(f"{BASE_URL}/api/admin/role-preview/super_admin", timeout=15)
        assert r.status_code == 403, f"PM should be 403 on role-preview, got {r.status_code}"

    def test_super_admin_preview(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/role-preview/super_admin", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "super_admin"
        assert data["fallback_all"] is False
        depts = data["departments"]
        assert isinstance(depts, list)
        assert len(depts) == 9, f"super_admin should see 9 departments, got {len(depts)}"
        for d in depts:
            assert set(d.keys()) >= {"slug", "title", "tagline", "icon", "color"}

    def test_unmapped_role_fallback(self, admin_session):
        # A role string that's almost certainly not in the role->dept map
        r = admin_session.get(f"{BASE_URL}/api/admin/role-preview/nonexistent_role_xyz", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "nonexistent_role_xyz"
        assert data["fallback_all"] is True
        assert len(data["departments"]) == 9, "fail-open should show all 9 departments"

    def test_mapped_role_scoped(self, admin_session):
        # Set an explicit mapping for a synthetic role, then verify preview is scoped
        # Using existing settings endpoint
        new_map_resp = admin_session.get(f"{BASE_URL}/api/admin/role-department-map", timeout=15)
        assert new_map_resp.status_code == 200, f"Could not GET role-department-map: {new_map_resp.status_code}"
        current = new_map_resp.json().get("map", {})
        # Pick a role from existing map; if empty, set one
        target_role = None
        target_slugs = None
        for role, slugs in current.items():
            if isinstance(slugs, list) and 0 < len(slugs) < 9:
                target_role = role
                target_slugs = slugs
                break
        if not target_role:
            # Seed: set sales_executive -> ["sales"] (or first available slug)
            target_role = "sales_executive"
            target_slugs = ["sales"]
            updated = {**current, target_role: target_slugs}
            put_r = admin_session.put(
                f"{BASE_URL}/api/admin/role-department-map",
                json={"map": updated}, timeout=15
            )
            assert put_r.status_code == 200, f"PUT role-department-map failed: {put_r.status_code} {put_r.text}"

        r = admin_session.get(f"{BASE_URL}/api/admin/role-preview/{target_role}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["fallback_all"] is False, f"Mapped role should not be fallback. Got: {data}"
        returned = sorted([d["slug"] for d in data["departments"]])
        assert returned == sorted(target_slugs), f"Expected {target_slugs}, got {returned}"
