"""Iter 163 bug-fix verification:
   1. GET /api/assignments — pm_users only 'Manager O P' role; coord_users only 'Executive O P' role, active only.
   2. GET /api/admin/users — includes active+inactive; status=active|inactive filters correctly.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for tests only (env should be set by supervisor)
    BASE_URL = "https://worksite-command.preview.emergentagent.com"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def role_catalog(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/role-catalog", timeout=30)
    assert r.status_code == 200, f"Role catalog fetch failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    if isinstance(data, dict):
        data = data.get("roles") or data.get("items") or []
    return data


def _norm(s):
    import re
    return re.sub(r"[^a-z]", "", (s or "").lower())


# ============== BUG 1: Assignment users dropdown filtering ==============
class TestAssignmentUsersFilter:

    def test_get_assignments_returns_filtered_pm_coord(self, admin_session, role_catalog):
        r = admin_session.get(f"{BASE_URL}/api/ops/project-assignments", timeout=30)
        assert r.status_code == 200, f"GET /api/ops/project-assignments failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        assert "pm_users" in data and "coord_users" in data
        pm_users = data["pm_users"]
        coord_users = data["coord_users"]

        # Derive allowed role keys from catalog (labels 'Manager O P' / 'Executive O P')
        pm_keys = {r_["key"] for r_ in role_catalog if _norm(r_.get("label")) == _norm("Manager O P")}
        coord_keys = {r_["key"] for r_ in role_catalog if _norm(r_.get("label")) == _norm("Executive O P")}
        # Fallback keys used by backend when catalog has no such labels
        if not pm_keys:
            pm_keys = {"project_manager"}
        if not coord_keys:
            coord_keys = {"project_coordinator", "pro_coor"}
        print(f"Effective PM role keys: {pm_keys}")
        print(f"Effective Coord role keys: {coord_keys}")
        print(f"pm_users count: {len(pm_users)}, coord_users count: {len(coord_users)}")

        for u in pm_users:
            assert u["role"] in pm_keys, f"PM user {u.get('name')} has role '{u['role']}' NOT in {pm_keys}"
        for u in coord_users:
            assert u["role"] in coord_keys, f"Coord user {u.get('name')} has role '{u['role']}' NOT in {coord_keys}"

        # No unrelated roles like sales/safety/vendor
        bad_roles = {"sales_executive", "safety_officer", "vendor", "hr_executive", "store_incharge"}
        for u in pm_users + coord_users:
            assert u["role"] not in bad_roles, f"Unexpected role {u['role']} in dropdown"

    def test_inactive_users_excluded(self, admin_session):
        """Inactive users must not appear in pm_users or coord_users."""
        r = admin_session.get(f"{BASE_URL}/api/ops/project-assignments", timeout=30)
        assert r.status_code == 200
        data = r.json()
        pm_ids = {u["id"] for u in data["pm_users"]}
        coord_ids = {u["id"] for u in data["coord_users"]}

        # Fetch inactive users
        r2 = admin_session.get(f"{BASE_URL}/api/admin/users?status=inactive", timeout=30)
        assert r2.status_code == 200
        inactive = r2.json()
        for u in inactive:
            assert u["id"] not in pm_ids, f"Inactive user {u.get('email')} leaked into pm_users"
            assert u["id"] not in coord_ids, f"Inactive user {u.get('email')} leaked into coord_users"


# ============== BUG 2: Admin users list includes inactive ==============
class TestAdminUsersInactive:

    def test_list_all_includes_active_and_inactive(self, admin_session):
        all_r = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=30)
        assert all_r.status_code == 200, f"GET /api/admin/users failed: {all_r.status_code}"
        all_users = all_r.json()
        assert isinstance(all_users, list)

        active_r = admin_session.get(f"{BASE_URL}/api/admin/users?status=active", timeout=30)
        inactive_r = admin_session.get(f"{BASE_URL}/api/admin/users?status=inactive", timeout=30)
        assert active_r.status_code == 200 and inactive_r.status_code == 200
        active = active_r.json()
        inactive = inactive_r.json()

        print(f"All users: {len(all_users)}, Active: {len(active)}, Inactive: {len(inactive)}")
        # Sum property
        assert len(all_users) == len(active) + len(inactive), \
            f"Sum mismatch: all={len(all_users)}, active={len(active)}, inactive={len(inactive)}"

        # No inactive user in active list
        for u in active:
            assert u.get("active") is not False, f"Inactive user {u.get('email')} in active list"
        for u in inactive:
            assert u.get("active") is False, f"Active user {u.get('email')} in inactive list"

    def test_toggle_active_and_verify_visible_in_inactive(self, admin_session):
        """Find a non-admin user, toggle inactive, verify it appears in status=inactive; restore."""
        all_r = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=30)
        users = all_r.json()
        target = None
        for u in users:
            if u.get("email") not in (ADMIN_EMAIL,) and u.get("active") is not False and u.get("role") != "super_admin":
                target = u
                break
        if not target:
            pytest.skip("No suitable non-admin active user to toggle")

        uid = target["id"]
        try:
            # Toggle to inactive
            tog = admin_session.post(f"{BASE_URL}/api/admin/users/{uid}/toggle-active", timeout=30)
            assert tog.status_code == 200, f"Toggle failed: {tog.status_code} {tog.text[:200]}"

            # Verify appears in inactive
            inactive_r = admin_session.get(f"{BASE_URL}/api/admin/users?status=inactive", timeout=30)
            inactive_ids = {u["id"] for u in inactive_r.json()}
            assert uid in inactive_ids, f"Toggled user {target['email']} not in inactive list"

            # Verify visible in full list too
            all_now = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=30).json()
            assert uid in {u["id"] for u in all_now}, "User missing from full list after toggle"

            # Verify NOT in active list
            active_now = admin_session.get(f"{BASE_URL}/api/admin/users?status=active", timeout=30).json()
            assert uid not in {u["id"] for u in active_now}, "Inactive user leaked into active list"
        finally:
            # Restore
            admin_session.post(f"{BASE_URL}/api/admin/users/{uid}/toggle-active", timeout=30)
