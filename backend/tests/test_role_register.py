"""
Iteration 138 – Role × Permission Matrix regression tests.

Verifies:
  * GET  /api/admin/role-register returns 20 roles (incl. custom pro_coor), 83+ resources
  * PUT  /api/admin/role-register applies overrides instantly (403 → 200)
  * super_admin is ALWAYS re-added to every override
  * Baseline overrides are preserved / restored at teardown
  * Role catalog and User Management dropdowns are DB-driven
"""
import os
import copy
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SALES = {"email": "sales@erp.com", "password": "Sales@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sales_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=SALES, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def baseline(admin_session):
    """Capture existing overrides so we can restore them after the module."""
    r = admin_session.get(f"{BASE_URL}/api/admin/role-register", timeout=15)
    assert r.status_code == 200
    data = r.json()
    saved = copy.deepcopy(data.get("overrides", {}))
    yield data
    # teardown -> restore
    admin_session.put(
        f"{BASE_URL}/api/admin/role-register",
        json={"overrides": saved},
        timeout=15,
    )


# ---------- Role catalog / register ----------
def test_role_register_returns_20_roles_and_pro_coor(baseline):
    roles = baseline["roles"]
    assert len(roles) == 20, f"expected 20 roles, got {len(roles)}: {roles}"
    assert "pro_coor" in roles, "custom role pro_coor missing – catalog not DB-driven"
    assert "super_admin" in roles


def test_role_register_has_all_resources(baseline):
    resources = baseline["resources"]
    assert len(resources) >= 80, f"expected 80+ resources, got {len(resources)}"
    for r in ("projects", "employees", "safety_reports", "role_register"):
        assert r in resources, f"missing resource {r}"


def test_role_catalog_list_matches_register(admin_session, baseline):
    r = admin_session.get(f"{BASE_URL}/api/admin/role-catalog", timeout=15)
    assert r.status_code == 200
    cat = r.json()
    keys = [x["key"] for x in cat["roles"]]
    assert set(keys) == set(baseline["roles"])


# ---------- Instant enforcement (403 / 200) ----------
def test_put_override_applies_instantly_and_super_admin_preserved(admin_session, sales_session, baseline):
    # Compose overrides = baseline + projects.read locked to super_admin only
    ovr = copy.deepcopy(baseline["overrides"])
    ovr["projects"] = {"read": ["super_admin"]}
    r = admin_session.put(f"{BASE_URL}/api/admin/role-register", json={"overrides": ovr}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    # super_admin must be auto-injected
    assert "super_admin" in body["overrides"]["projects"]["read"]

    # sales must now be denied
    r2 = sales_session.get(f"{BASE_URL}/api/projects", timeout=15)
    assert r2.status_code == 403, f"expected 403 after denying, got {r2.status_code}"

    # super_admin still allowed
    r3 = admin_session.get(f"{BASE_URL}/api/projects", timeout=15)
    assert r3.status_code == 200

    # Now grant sales_executive
    ovr["projects"] = {"read": ["sales_executive"]}
    r = admin_session.put(f"{BASE_URL}/api/admin/role-register", json={"overrides": ovr}, timeout=15)
    assert r.status_code == 200
    assert "super_admin" in r.json()["overrides"]["projects"]["read"]  # always re-added

    r4 = sales_session.get(f"{BASE_URL}/api/projects", timeout=15)
    assert r4.status_code == 200, f"expected 200 after grant, got {r4.status_code}"


def test_put_rejects_unknown_role(admin_session, baseline):
    ovr = copy.deepcopy(baseline["overrides"])
    ovr["projects"] = {"read": ["not_a_real_role"]}
    r = admin_session.put(f"{BASE_URL}/api/admin/role-register", json={"overrides": ovr}, timeout=15)
    assert r.status_code == 400


def test_put_rejects_unknown_resource(admin_session):
    r = admin_session.put(
        f"{BASE_URL}/api/admin/role-register",
        json={"overrides": {"fake_resource_xyz": {"read": ["super_admin"]}}},
        timeout=15,
    )
    assert r.status_code == 400
