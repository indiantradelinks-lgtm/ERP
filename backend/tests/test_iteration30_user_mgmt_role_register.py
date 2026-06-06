"""Iteration 30 — User Management + Role Register control panel tests.

Covers:
  • RBAC gating on /api/admin/users (super_admin, hr_executive read; others 403)
  • POST /admin/users create + login + edge cases (weak pw, duplicate, bad role)
  • PUT /admin/users/{id} update + last super_admin guards
  • POST /admin/users/{id}/reset-password — old pw invalid, lockout cleared
  • POST /admin/users/{id}/toggle-active — inactive 403 on login
  • DELETE /admin/users/{id} — cannot delete only super_admin, cannot delete self
  • GET /admin/role-register matrix shape + RBAC
  • PUT /admin/role-register applies override, super_admin auto-injected,
    validates roles/actions/resources, takes effect IMMEDIATELY (sales_exec POST employees)
  • POST /admin/role-register/reset clears overrides
  • Regression: dropdowns, approval-matrix, audit-logs, login-activity still 200
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
HR    = {"email": "hr.test@erp.com", "password": "HR@12345"}
SALES = {"email": "sales@erp.com", "password": "Sales@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login {creds['email']} failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(ADMIN)

@pytest.fixture(scope="module")
def hr_s():
    return _login(HR)

@pytest.fixture(scope="module")
def sales_s():
    return _login(SALES)


@pytest.fixture(scope="module")
def created_user(admin_s):
    """Create a fresh test user (sales_executive) used across tests."""
    email = f"test_iter30_{uuid.uuid4().hex[:6]}@erp.com"
    payload = {
        "email": email, "password": "Test@1234", "name": "Iter30 Tester",
        "role": "sales_executive", "department": "Sales", "phone": "9000000001",
    }
    r = admin_s.post(f"{API}/admin/users", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "password_hash" not in data
    assert data["email"] == email
    yield {"id": data["id"], "email": email, "password": "Test@1234"}
    # Cleanup
    try:
        admin_s.delete(f"{API}/admin/users/{data['id']}", timeout=15)
    except Exception:
        pass


# ============================================================================
# /api/admin/users — list + RBAC
# ============================================================================
class TestAdminUsersList:
    def test_admin_can_list(self, admin_s):
        r = admin_s.get(f"{API}/admin/users", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        sample = rows[0]
        assert "password_hash" not in sample
        assert "active" in sample
        assert "email" in sample and "id" in sample

    def test_hr_can_read(self, hr_s):
        r = hr_s.get(f"{API}/admin/users", timeout=15)
        assert r.status_code == 200

    def test_sales_403(self, sales_s):
        r = sales_s.get(f"{API}/admin/users", timeout=15)
        assert r.status_code == 403


# ============================================================================
# POST / login / edge cases
# ============================================================================
class TestUserCreate:
    def test_new_user_can_login(self, created_user):
        # Login with the brand new creds
        s2 = requests.Session()
        r = s2.post(f"{API}/auth/login", json={"email": created_user["email"], "password": created_user["password"]}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("email") == created_user["email"]

    def test_duplicate_email_400(self, admin_s, created_user):
        r = admin_s.post(f"{API}/admin/users", json={
            "email": created_user["email"], "password": "Test@1234", "name": "Dup",
            "role": "site_engineer",
        }, timeout=15)
        assert r.status_code == 400

    def test_weak_password_400(self, admin_s):
        r = admin_s.post(f"{API}/admin/users", json={
            "email": f"weak_{uuid.uuid4().hex[:6]}@erp.com", "password": "alllower",
            "name": "Weak", "role": "site_engineer",
        }, timeout=15)
        assert r.status_code == 400

    def test_bad_role_400(self, admin_s):
        r = admin_s.post(f"{API}/admin/users", json={
            "email": f"badrole_{uuid.uuid4().hex[:6]}@erp.com", "password": "Test@1234",
            "name": "Bad", "role": "not_a_role",
        }, timeout=15)
        assert r.status_code == 400


# ============================================================================
# PUT update + super_admin guards
# ============================================================================
class TestUserUpdate:
    def test_update_name_role(self, admin_s, created_user):
        r = admin_s.put(f"{API}/admin/users/{created_user['id']}",
                        json={"name": "Updated Name", "role": "site_engineer"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("name") == "Updated Name"
        # GET verification via list
        rows = admin_s.get(f"{API}/admin/users", timeout=15).json()
        row = next((u for u in rows if u["id"] == created_user["id"]), None)
        assert row and row["role"] == "site_engineer"

    def test_cannot_demote_only_super_admin(self, admin_s):
        rows = admin_s.get(f"{API}/admin/users", timeout=15).json()
        admins = [u for u in rows if u["role"] == "super_admin" and u.get("active") is not False]
        if len(admins) != 1:
            pytest.skip(f"need exactly 1 active super_admin; found {len(admins)}")
        only_admin = admins[0]
        r = admin_s.put(f"{API}/admin/users/{only_admin['id']}",
                        json={"role": "site_engineer"}, timeout=15)
        assert r.status_code == 400
        assert "super_admin" in r.text.lower()

    def test_cannot_deactivate_only_super_admin(self, admin_s):
        rows = admin_s.get(f"{API}/admin/users", timeout=15).json()
        admins = [u for u in rows if u["role"] == "super_admin" and u.get("active") is not False]
        if len(admins) != 1:
            pytest.skip("more than one active super_admin")
        only_admin = admins[0]
        r = admin_s.put(f"{API}/admin/users/{only_admin['id']}",
                        json={"active": False}, timeout=15)
        assert r.status_code == 400


# ============================================================================
# Reset password
# ============================================================================
class TestResetPassword:
    def test_old_password_invalid_after_reset(self, admin_s, created_user):
        new_pw = "NewPass@456"
        r = admin_s.post(f"{API}/admin/users/{created_user['id']}/reset-password",
                         json={"password": new_pw}, timeout=15)
        assert r.status_code == 200
        # Old should fail
        bad = requests.post(f"{API}/auth/login",
                            json={"email": created_user["email"], "password": created_user["password"]}, timeout=15)
        assert bad.status_code == 401
        # New should succeed
        good = requests.post(f"{API}/auth/login",
                             json={"email": created_user["email"], "password": new_pw}, timeout=15)
        assert good.status_code == 200
        created_user["password"] = new_pw  # persist for downstream test

    def test_reset_weak_rejected(self, admin_s, created_user):
        # Length-only failure → Pydantic Field min_length=8 → 422
        r = admin_s.post(f"{API}/admin/users/{created_user['id']}/reset-password",
                         json={"password": "shrt"}, timeout=15)
        assert r.status_code in (400, 422)
        # Strength failure (≥8 chars but no digit) → custom check → 400
        r2 = admin_s.post(f"{API}/admin/users/{created_user['id']}/reset-password",
                          json={"password": "alllowercase"}, timeout=15)
        assert r2.status_code == 400


# ============================================================================
# Toggle active → inactive login 403
# ============================================================================
class TestToggleActive:
    def test_toggle_then_inactive_login_403(self, admin_s, created_user):
        r = admin_s.post(f"{API}/admin/users/{created_user['id']}/toggle-active", timeout=15)
        assert r.status_code == 200
        assert r.json().get("active") is False
        # Inactive login attempt
        bad = requests.post(f"{API}/auth/login",
                            json={"email": created_user["email"], "password": created_user["password"]}, timeout=15)
        assert bad.status_code == 403
        assert "disabled" in bad.text.lower()
        # Reactivate
        r2 = admin_s.post(f"{API}/admin/users/{created_user['id']}/toggle-active", timeout=15)
        assert r2.status_code == 200 and r2.json().get("active") is True


# ============================================================================
# DELETE
# ============================================================================
class TestDeleteUser:
    def test_cannot_delete_self(self, admin_s):
        me = admin_s.get(f"{API}/auth/me", timeout=15).json()
        r = admin_s.delete(f"{API}/admin/users/{me['id']}", timeout=15)
        assert r.status_code == 400

    def test_cannot_delete_only_super_admin(self, admin_s):
        rows = admin_s.get(f"{API}/admin/users", timeout=15).json()
        admins = [u for u in rows if u["role"] == "super_admin"]
        if len(admins) != 1:
            pytest.skip("multiple super_admins")
        r = admin_s.delete(f"{API}/admin/users/{admins[0]['id']}", timeout=15)
        assert r.status_code == 400


# ============================================================================
# last_login stamp
# ============================================================================
class TestLastLogin:
    def test_last_login_stamped(self, admin_s, created_user):
        # Log in as the test user — should stamp last_login
        s = requests.Session()
        r = s.post(f"{API}/auth/login",
                   json={"email": created_user["email"], "password": created_user["password"]}, timeout=15)
        assert r.status_code == 200
        rows = admin_s.get(f"{API}/admin/users", timeout=15).json()
        row = next((u for u in rows if u["id"] == created_user["id"]), None)
        assert row, "user vanished"
        assert row.get("last_login"), f"last_login not stamped: {row}"


# ============================================================================
# Role Register
# ============================================================================
class TestRoleRegisterRead:
    def test_admin_get(self, admin_s):
        r = admin_s.get(f"{API}/admin/role-register", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("roles", "actions", "resources", "base", "overrides", "effective"):
            assert k in d, f"missing {k}"
        assert d["actions"] == ["read", "write", "delete"]
        assert "super_admin" in d["roles"]
        # base + effective have same resource keys
        assert set(d["base"].keys()).issubset(set(d["effective"].keys()))

    def test_sales_403(self, sales_s):
        r = sales_s.get(f"{API}/admin/role-register", timeout=15)
        assert r.status_code == 403


class TestRoleRegisterUpdate:
    def test_unknown_resource_400(self, admin_s):
        r = admin_s.put(f"{API}/admin/role-register",
                        json={"overrides": {"not_a_resource": {"read": ["sales_executive"]}}}, timeout=15)
        assert r.status_code == 400

    def test_unknown_action_400(self, admin_s):
        r = admin_s.put(f"{API}/admin/role-register",
                        json={"overrides": {"employees": {"explode": ["sales_executive"]}}}, timeout=15)
        assert r.status_code == 400

    def test_unknown_role_400(self, admin_s):
        r = admin_s.put(f"{API}/admin/role-register",
                        json={"overrides": {"employees": {"read": ["wizard"]}}}, timeout=15)
        assert r.status_code == 400

    def test_override_applies_immediately(self, admin_s, sales_s):
        """Grant sales_executive write to employees; sales POST /employees should now succeed."""
        # Baseline: sales should be blocked
        probe = sales_s.post(f"{API}/employees", json={"name": "TEST_iter30 baseline",
                                                       "designation": "X", "department": "Sales"}, timeout=15)
        # 403 expected (or could be 401 if perms differ — we accept >=400)
        baseline_blocked = probe.status_code in (401, 403)

        # Apply override
        put = admin_s.put(f"{API}/admin/role-register",
                          json={"overrides": {"employees": {"write": ["sales_executive"]}}}, timeout=20)
        assert put.status_code == 200, put.text
        eff = put.json()["effective"]["employees"]["write"]
        assert "sales_executive" in eff
        assert "super_admin" in eff, "super_admin must be auto-included"

        # Now sales SHOULD be able to write employees
        emp_id = None
        try:
            r2 = sales_s.post(f"{API}/employees", json={"name": "TEST_iter30 override emp",
                                                        "designation": "Engineer", "department": "Sales"}, timeout=20)
            assert r2.status_code in (200, 201), f"after override, sales got {r2.status_code}: {r2.text[:300]}"
            try:
                emp_id = r2.json().get("id")
            except Exception:
                pass
        finally:
            # Always clean up the override and any test data
            if emp_id:
                try:
                    admin_s.delete(f"{API}/employees/{emp_id}", timeout=15)
                except Exception:
                    pass
            reset = admin_s.post(f"{API}/admin/role-register/reset", timeout=15)
            assert reset.status_code == 200

        # Post-reset sanity: sales blocked again
        probe2 = sales_s.post(f"{API}/employees",
                              json={"name": "TEST_iter30 post-reset", "designation": "X", "department": "Sales"}, timeout=15)
        assert probe2.status_code in (401, 403), f"post-reset still allowed: {probe2.status_code}"
        if baseline_blocked is False:
            pytest.skip("baseline was not blocked — RBAC for sales_exec on employees write may have been already open")

    def test_reset_clears(self, admin_s):
        r = admin_s.post(f"{API}/admin/role-register/reset", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["overrides"] == {} or d["overrides"] is None or len(d["overrides"]) == 0


# ============================================================================
# Regression — existing admin endpoints still work
# ============================================================================
class TestRegression:
    def test_dropdowns(self, admin_s):
        assert admin_s.get(f"{API}/admin/dropdowns", timeout=15).status_code == 200

    def test_approval_matrix(self, admin_s):
        assert admin_s.get(f"{API}/admin/approval-matrix", timeout=15).status_code == 200

    def test_audit_logs(self, admin_s):
        assert admin_s.get(f"{API}/admin/audit-logs?limit=10", timeout=15).status_code == 200

    def test_login_activity(self, admin_s):
        assert admin_s.get(f"{API}/admin/login-activity?limit=10", timeout=15).status_code == 200
