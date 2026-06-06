"""Iteration 16 — Multi-location Client Management (Phase A+B+C).

Covers: customer-code-format admin, /clients CRUD with auto code + dup name guard,
sites CRUD with auto site_code + GST dup guard, contacts CRUD with dept validation,
tree view, search, 7 reports, sales_executive RBAC, legacy migration backfill,
and Quotations/Projects regression."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _login_session(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    # cookies auto-stored. also try to grab Bearer token if available.
    tok = None
    try:
        body = r.json()
        tok = body.get("access_token") or body.get("token")
    except Exception:
        pass
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin_h():
    return _login_session("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def sales_h(admin_h):
    r = admin_h.get(f"{API}/auth/users", timeout=15)
    users = r.json() if r.status_code == 200 else []
    if not any(u.get("email") == "sales@erp.com" for u in users):
        admin_h.post(f"{API}/auth/register", json={
            "email": "sales@erp.com", "password": "Sales@123", "name": "Sales Exec",
            "role": "sales_executive"
        }, timeout=15)
    return _login_session("sales@erp.com", "Sales@123")


@pytest.fixture(scope="module")
def pm_h():
    return _login_session("test_pm@erp.com", "PM@12345")


# ---------- Customer Code Format ----------
class TestCustomerCodeFormat:
    def test_get_default_format(self, admin_h):
        r = admin_h.get(f"{API}/admin/customer-code-format", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("prefix", "padding", "include_fy"):
            assert k in d

    def test_put_rejects_empty_prefix(self, admin_h):
        r = admin_h.put(f"{API}/admin/customer-code-format", json={"prefix": "", "padding": 4}, timeout=15)
        assert r.status_code == 400

    def test_put_rejects_long_prefix(self, admin_h):
        r = admin_h.put(f"{API}/admin/customer-code-format", json={"prefix": "TOOLONGPREFIX", "padding": 4}, timeout=15)
        assert r.status_code == 400

    def test_put_rejects_bad_padding(self, admin_h):
        r = admin_h.put(f"{API}/admin/customer-code-format", json={"prefix": "CUST", "padding": 2}, timeout=15)
        assert r.status_code == 400
        r2 = admin_h.put(f"{API}/admin/customer-code-format", json={"prefix": "CUST", "padding": 9}, timeout=15)
        assert r2.status_code == 400

    def test_sales_executive_cannot_update_format(self, sales_h):
        r = sales_h.put(f"{API}/admin/customer-code-format", json={"prefix": "EVIL", "padding": 4}, timeout=15)
        assert r.status_code == 403, f"sales_executive should not have clients.delete: {r.status_code}"

    def test_format_applies_to_new_client(self, admin_h):
        # set TATA / 5
        r = admin_h.put(f"{API}/admin/customer-code-format", json={"prefix": "TATA", "padding": 5, "include_fy": False}, timeout=15)
        assert r.status_code == 200
        name = f"TEST_CodeFmt_{int(time.time())}"
        r2 = admin_h.post(f"{API}/clients", json={"name": name}, timeout=15)
        assert r2.status_code == 200, r2.text
        code = r2.json()["customer_code"]
        assert code.startswith("TATA-"), code
        # numeric portion length == 5
        num = code.split("-")[-1]
        assert len(num) == 5 and num.isdigit(), code
        # cleanup client
        admin_h.delete(f"{API}/clients/{r2.json()['id']}", timeout=15)
        # reset format
        admin_h.put(f"{API}/admin/customer-code-format", json={"prefix": "CUST", "padding": 4, "include_fy": False}, timeout=15)


# ---------- Clients CRUD ----------
class TestClientsCRUD:
    def test_create_client_auto_code(self, admin_h):
        name = f"TEST_Client_{int(time.time())}"
        r = admin_h.post(f"{API}/clients", json={"name": name, "main_email": "x@y.com"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == name
        assert d["customer_code"]
        assert d["code"] == d["customer_code"], "legacy code mirror missing"
        pytest.shared_client = d

    def test_duplicate_name_blocked(self, admin_h):
        n = pytest.shared_client["name"]
        r = admin_h.post(f"{API}/clients", json={"name": n}, timeout=15)
        assert r.status_code == 400
        assert "already exists" in r.text.lower()

    def test_duplicate_name_case_insensitive(self, admin_h):
        n = pytest.shared_client["name"].upper()
        r = admin_h.post(f"{API}/clients", json={"name": n}, timeout=15)
        assert r.status_code == 400

    def test_list_clients(self, admin_h):
        r = admin_h.get(f"{API}/clients", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        # legacy migration: every row must have customer_code
        missing = [c for c in rows if not c.get("customer_code")]
        assert not missing, f"clients without customer_code: {[c.get('name') for c in missing[:5]]}"


# ---------- Sites ----------
class TestSites:
    def test_create_first_site_suffix_01(self, admin_h):
        cid = pytest.shared_client["id"]
        ccode = pytest.shared_client["customer_code"]
        r = admin_h.post(f"{API}/clients/{cid}/sites", json={
            "city": "Mumbai", "state": "Maharashtra", "gst": "99TESTGST1Z0"
        }, timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["site_code"] == f"{ccode}-01", s
        pytest.shared_site = s

    def test_create_second_site_suffix_02(self, admin_h):
        cid = pytest.shared_client["id"]
        ccode = pytest.shared_client["customer_code"]
        r = admin_h.post(f"{API}/clients/{cid}/sites", json={
            "city": "Pune", "state": "Maharashtra", "gst": "99TESTGST2Z0"
        }, timeout=15)
        assert r.status_code == 200
        assert r.json()["site_code"] == f"{ccode}-02"

    def test_duplicate_gst_blocked(self, admin_h):
        cid = pytest.shared_client["id"]
        r = admin_h.post(f"{API}/clients/{cid}/sites", json={
            "city": "Delhi", "gst": "99TESTGST1Z0"
        }, timeout=15)
        assert r.status_code == 400
        assert "gst" in r.text.lower() or "already" in r.text.lower()

    def test_update_site_blocks_dup_gst(self, admin_h):
        sid = pytest.shared_site["id"]
        # try setting it to the 2nd site's GST
        r = admin_h.put(f"{API}/sites/{sid}", json={"gst": "99TESTGST2Z0"}, timeout=15)
        assert r.status_code == 400

    def test_update_site_cannot_change_code(self, admin_h):
        sid = pytest.shared_site["id"]
        orig = pytest.shared_site["site_code"]
        r = admin_h.put(f"{API}/sites/{sid}", json={
            "site_code": "HACKED-99", "client_id": "another", "city": "MumbaiUpdated"
        }, timeout=15)
        assert r.status_code == 200
        assert r.json()["site_code"] == orig
        assert r.json()["city"] == "MumbaiUpdated"

    def test_list_sites_by_client(self, admin_h):
        cid = pytest.shared_client["id"]
        r = admin_h.get(f"{API}/sites?client_id={cid}", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 2


# ---------- Contacts ----------
class TestContacts:
    def test_create_contact_valid_dept(self, admin_h):
        sid = pytest.shared_site["id"]
        r = admin_h.post(f"{API}/sites/{sid}/contacts", json={
            "name": "TEST Contact", "department": "Purchase",
            "mobile": "9876500001", "email": "c@x.com"
        }, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["department"] == "Purchase"

    def test_create_contact_unknown_dept(self, admin_h):
        sid = pytest.shared_site["id"]
        r = admin_h.post(f"{API}/sites/{sid}/contacts", json={
            "name": "Bad Dept", "department": "InvalidDept"
        }, timeout=15)
        assert r.status_code == 400


# ---------- Tree & search ----------
class TestTreeAndSearch:
    def test_clients_tree_nested(self, admin_h):
        r = admin_h.get(f"{API}/clients-tree", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        ours = next((c for c in rows if c["id"] == pytest.shared_client["id"]), None)
        assert ours is not None
        assert "sites" in ours and len(ours["sites"]) >= 2
        site = next((s for s in ours["sites"] if s["id"] == pytest.shared_site["id"]), None)
        assert site and "contacts" in site and len(site["contacts"]) >= 1

    def test_search_by_gst(self, admin_h):
        r = admin_h.get(f"{API}/clients/search?q=99TESTGST1Z0", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("clients", "sites", "contacts"):
            assert k in d
        assert len(d["sites"]) >= 1

    def test_search_by_mobile(self, admin_h):
        r = admin_h.get(f"{API}/clients/search?q=9876500001", timeout=15)
        assert r.status_code == 200
        assert len(r.json()["contacts"]) >= 1


# ---------- Reports ----------
class TestReports:
    @pytest.mark.parametrize("path", [
        "/clients/reports/by-client",
        "/clients/reports/by-site",
        "/clients/reports/by-gst",
        "/clients/reports/outstanding-by-site",
        "/clients/reports/by-location",
        "/clients/reports/contact-directory",
        "/clients/reports/activity-history",
    ])
    def test_report_endpoint(self, admin_h, path):
        r = admin_h.get(f"{API}{path}", timeout=20)
        assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
        assert isinstance(r.json(), list)

    def test_contact_directory_enriched(self, admin_h):
        r = admin_h.get(f"{API}/clients/reports/contact-directory", timeout=15)
        rows = r.json()
        if rows:
            sample = rows[0]
            assert "site_code" in sample and "client_name" in sample


# ---------- RBAC: sales_executive ----------
class TestSalesExecRBAC:
    def test_sales_can_read_clients(self, sales_h):
        r = sales_h.get(f"{API}/clients", timeout=15)
        assert r.status_code == 200

    def test_sales_can_write_clients(self, sales_h):
        name = f"TEST_SalesCreated_{int(time.time())}"
        r = sales_h.post(f"{API}/clients", json={"name": name}, timeout=15)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        # cleanup with admin (sales cannot delete)
        pytest.sales_created = cid

    def test_sales_cannot_delete_clients(self, sales_h):
        cid = getattr(pytest, "sales_created", None)
        if not cid:
            pytest.skip("no created client")
        r = sales_h.delete(f"{API}/clients/{cid}", timeout=15)
        assert r.status_code == 403

    def test_admin_cleanup(self, admin_h):
        cid = getattr(pytest, "sales_created", None)
        if cid:
            admin_h.delete(f"{API}/clients/{cid}", timeout=15)


# ---------- Regression: Quotations, Projects, Auth ----------
class TestRegression:
    def test_pm_login(self, pm_h):
        r = pm_h.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json().get("role") == "project_manager"

    def test_quotations_list(self, admin_h):
        r = admin_h.get(f"{API}/quotations", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_projects_list(self, admin_h):
        r = admin_h.get(f"{API}/projects", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Cleanup ----------
def test_zz_cleanup(admin_h):
    cid = getattr(pytest, "shared_client", {}).get("id") if hasattr(pytest, "shared_client") else None
    if cid:
        admin_h.delete(f"{API}/clients/{cid}", timeout=15)
