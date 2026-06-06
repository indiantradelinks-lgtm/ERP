"""Phase A — Super-Admin power tools tests.

Covers: login activity & audit, Approval Matrix (default/override/reset/role validation),
Dropdowns CRUD + public reads, Departments CRUD via crud_router, audit log filters,
RBAC enforcement for non-super_admin, regression on existing CRUD and approval flow.
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["role"] == "super_admin"
    return s


@pytest.fixture(scope="module")
def non_admin_client(admin_client):
    """Create a site_engineer test user (or reuse) and return a logged-in session."""
    email = "test_site_engineer@erp.com"
    password = "TestPass@123"
    # Register (may already exist)
    admin_client.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "name": "Test SE", "role": "site_engineer"},
        timeout=20,
    )
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Cannot login as site_engineer: {r.status_code} {r.text}")
    return s


# ---------- Login activity & audit ----------
class TestLoginActivity:
    def test_login_writes_login_activity_and_audit(self, admin_client):
        # Force a fresh login to ensure activity row
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
        assert r.status_code == 200
        time.sleep(0.5)

        r2 = admin_client.get(f"{API}/admin/login-activity", timeout=20)
        assert r2.status_code == 200, r2.text
        rows = r2.json()
        assert isinstance(rows, list) and len(rows) >= 1
        latest = rows[0]
        assert latest["email"] == ADMIN_EMAIL
        assert latest["role"] == "super_admin"
        assert "ip" in latest and "user_agent" in latest and "at" in latest

        r3 = admin_client.get(f"{API}/admin/audit-logs", params={"action": "login", "resource": "auth"}, timeout=20)
        assert r3.status_code == 200
        logs = r3.json()
        assert any(l.get("action") == "login" and l.get("resource") == "auth" for l in logs)


# ---------- Approval Matrix ----------
class TestApprovalMatrix:
    def test_list_returns_six_defaults(self, admin_client):
        r = admin_client.get(f"{API}/admin/approval-matrix", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        types = {row["type"]: row for row in rows}
        for t in ["purchase_order", "leave", "capex", "expense", "vendor", "quotation"]:
            assert t in types, f"missing chain: {t}"
            # If a previous test ran already, may be custom; reset first via DELETE if needed.
            if types[t]["source"] != "default":
                admin_client.delete(f"{API}/admin/approval-matrix/{t}", timeout=20)
        # re-fetch
        rows = admin_client.get(f"{API}/admin/approval-matrix", timeout=20).json()
        types = {row["type"]: row for row in rows}
        for t in ["purchase_order", "leave", "capex", "expense", "vendor", "quotation"]:
            assert types[t]["source"] == "default"
            assert isinstance(types[t]["steps"], list) and len(types[t]["steps"]) >= 1

    def test_override_then_reset(self, admin_client):
        new_steps = [
            {"role": "dept_head", "label": "Dept Head"},
            {"role": "director", "label": "Director Approves"},
        ]
        r = admin_client.put(
            f"{API}/admin/approval-matrix/expense",
            json={"type": "expense", "steps": new_steps},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        rows = admin_client.get(f"{API}/admin/approval-matrix", timeout=20).json()
        exp = next(row for row in rows if row["type"] == "expense")
        assert exp["source"] == "custom"
        assert exp["steps"][0]["role"] == "dept_head"
        assert exp["steps"][1]["label"] == "Director Approves"

        # Reset
        r2 = admin_client.delete(f"{API}/admin/approval-matrix/expense", timeout=20)
        assert r2.status_code == 200
        rows = admin_client.get(f"{API}/admin/approval-matrix", timeout=20).json()
        exp = next(row for row in rows if row["type"] == "expense")
        assert exp["source"] == "default"

    def test_unknown_role_rejected(self, admin_client):
        r = admin_client.put(
            f"{API}/admin/approval-matrix/expense",
            json={"type": "expense", "steps": [{"role": "made_up_role", "label": "X"}]},
            timeout=20,
        )
        assert r.status_code == 400

    def test_create_approval_uses_overridden_chain(self, admin_client):
        # Override leave chain with a single step
        new_steps = [{"role": "hr_executive", "label": "HR Final"}]
        admin_client.put(
            f"{API}/admin/approval-matrix/leave",
            json={"type": "leave", "steps": new_steps},
            timeout=20,
        )
        # Create an approval of type=leave; chain should be the overridden one.
        r = admin_client.post(
            f"{API}/api/approvals" if False else f"{API}/approvals",
            json={"type": "leave", "title": "TEST_leave override", "amount": 0},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text
        appr = r.json()
        assert isinstance(appr.get("chain"), list)
        assert len(appr["chain"]) == 1
        assert appr["chain"][0]["role"] == "hr_executive"
        # Cleanup: reset chain
        admin_client.delete(f"{API}/admin/approval-matrix/leave", timeout=20)
        # Cleanup approval
        admin_client.delete(f"{API}/approvals/{appr['id']}", timeout=20)


# ---------- Dropdowns ----------
class TestDropdowns:
    created_id = None

    def test_create_list_filter_update_delete(self, admin_client):
        cat = f"TEST_cat_{uuid.uuid4().hex[:6]}"
        payload = {"category": cat, "label": "Option A", "value": "opt_a", "order": 1, "active": True}
        r = admin_client.post(f"{API}/admin/dropdowns", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        opt = r.json()
        assert opt["category"] == cat and opt["label"] == "Option A"
        opt_id = opt["id"]

        # list
        r2 = admin_client.get(f"{API}/admin/dropdowns", params={"category": cat}, timeout=20)
        assert r2.status_code == 200 and any(x["id"] == opt_id for x in r2.json())

        # by-category active only
        r3 = admin_client.get(f"{API}/admin/dropdowns/by-category/{cat}", timeout=20)
        assert r3.status_code == 200 and len(r3.json()) == 1

        # update -> inactive
        r4 = admin_client.put(f"{API}/admin/dropdowns/{opt_id}", json={"active": False, "label": "Option A2"}, timeout=20)
        assert r4.status_code == 200 and r4.json()["active"] is False and r4.json()["label"] == "Option A2"

        r5 = admin_client.get(f"{API}/admin/dropdowns/by-category/{cat}", timeout=20)
        assert r5.status_code == 200 and len(r5.json()) == 0

        # delete
        r6 = admin_client.delete(f"{API}/admin/dropdowns/{opt_id}", timeout=20)
        assert r6.status_code == 200 and r6.json().get("ok") is True


# ---------- Departments via crud_router ----------
class TestDepartments:
    def test_super_admin_can_create_and_audit_logged(self, admin_client):
        name = f"TEST_dept_{uuid.uuid4().hex[:6]}"
        r = admin_client.post(f"{API}/departments", json={"name": name, "code": name[:8]}, timeout=20)
        assert r.status_code == 200, r.text
        dept = r.json()
        assert dept["name"] == name and "id" in dept
        dept_id = dept["id"]

        # GET by id
        r2 = admin_client.get(f"{API}/departments/{dept_id}", timeout=20)
        assert r2.status_code == 200 and r2.json()["name"] == name

        # Audit log entry for departments create
        r3 = admin_client.get(f"{API}/admin/audit-logs", params={"resource": "departments", "record_id": dept_id}, timeout=20)
        assert r3.status_code == 200
        logs = r3.json()
        assert any(l["action"] == "create" and l["resource"] == "departments" and l["record_id"] == dept_id for l in logs), logs

        # Cleanup
        admin_client.delete(f"{API}/departments/{dept_id}", timeout=20)


# ---------- RBAC: non-super_admin forbidden ----------
class TestRBAC:
    def test_site_engineer_forbidden(self, non_admin_client):
        r = non_admin_client.post(
            f"{API}/admin/dropdowns",
            json={"category": "x", "label": "x", "value": "x"},
            timeout=20,
        )
        assert r.status_code == 403, r.text
        r2 = non_admin_client.put(
            f"{API}/admin/approval-matrix/expense",
            json={"type": "expense", "steps": [{"role": "dept_head", "label": "x"}]},
            timeout=20,
        )
        assert r2.status_code == 403
        r3 = non_admin_client.delete(f"{API}/admin/dropdowns/nonexistent", timeout=20)
        assert r3.status_code == 403

    def test_categories_read_open_to_authenticated(self, non_admin_client):
        r = non_admin_client.get(f"{API}/admin/dropdowns/categories", timeout=20)
        assert r.status_code == 200
        r2 = non_admin_client.get(f"{API}/admin/approval-matrix/roles", timeout=20)
        assert r2.status_code == 200 and isinstance(r2.json(), list) and len(r2.json()) > 0


# ---------- Audit log filters ----------
class TestAuditFilters:
    def test_filter_by_resource_and_action(self, admin_client):
        # ensure at least one dropdown create to filter on
        cat = f"TEST_audf_{uuid.uuid4().hex[:6]}"
        c = admin_client.post(f"{API}/admin/dropdowns", json={"category": cat, "label": "L", "value": "v"}, timeout=20)
        opt_id = c.json()["id"]
        r = admin_client.get(f"{API}/admin/audit-logs", params={"resource": "dropdown_options", "action": "create"}, timeout=20)
        assert r.status_code == 200
        assert all(l["resource"] == "dropdown_options" and l["action"] == "create" for l in r.json())
        # filter by record_id
        r2 = admin_client.get(f"{API}/admin/audit-logs", params={"record_id": opt_id}, timeout=20)
        assert r2.status_code == 200 and any(l["record_id"] == opt_id for l in r2.json())
        admin_client.delete(f"{API}/admin/dropdowns/{opt_id}", timeout=20)


# ---------- Regression: existing CRUD + approvals action ----------
class TestRegression:
    def test_clients_crud_still_works(self, admin_client):
        name = f"TEST_client_{uuid.uuid4().hex[:6]}"
        r = admin_client.post(f"{API}/clients", json={"name": name, "email": "x@y.com"}, timeout=20)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        rg = admin_client.get(f"{API}/clients/{cid}", timeout=20)
        assert rg.status_code == 200 and rg.json()["name"] == name
        ru = admin_client.put(f"{API}/clients/{cid}", json={"name": name + "_u"}, timeout=20)
        assert ru.status_code == 200 and ru.json()["name"].endswith("_u")
        rd = admin_client.delete(f"{API}/clients/{cid}", timeout=20)
        assert rd.status_code == 200

    def test_approval_action_after_async_build_chain(self, admin_client):
        # create an approval (default chain)
        r = admin_client.post(f"{API}/approvals", json={"type": "expense", "title": "TEST_reg_expense"}, timeout=20)
        assert r.status_code == 200, r.text
        appr = r.json()
        assert appr.get("chain") and len(appr["chain"]) >= 1
        aid = appr["id"]
        # super_admin can act on any step
        ra = admin_client.post(f"{API}/approvals/{aid}/action", json={"action": "approve", "comment": "ok"}, timeout=20)
        assert ra.status_code == 200, ra.text
        out = ra.json()
        assert out.get("status") in ("in_progress", "approved")
        # cleanup
        admin_client.delete(f"{API}/approvals/{aid}", timeout=20)
