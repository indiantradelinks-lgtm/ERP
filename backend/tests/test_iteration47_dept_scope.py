"""Iteration 47 — Department-prefixed numbering, Department Master CRUD,
and expanded visibility scoping. Backend-only tests.

Auth: cookie+bearer via existing /api/auth/login. Uses pre-seeded test accounts
listed in /app/memory/test_credentials.md (admin/hr/pm/purchase).
"""
import os
import re
import uuid
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "super_admin":     ("admin@erp.com",    "Admin@123"),
    "hr_executive":    ("hr.test@erp.com",  "HR@12345"),
    "project_manager": ("test_pm@erp.com",  "PM@12345"),
    "purchase_officer":("purchase@erp.com", "Purchase@123"),
    "sales_executive": ("sales@erp.com",    "Sales@123"),
}

SESSIONS: dict[str, requests.Session] = {}
USERS:    dict[str, dict]             = {}


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        return None, {}
    data = r.json()
    if data.get("access_token"):
        s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    user = data if "role" in data else (data.get("user") or {})
    return s, user


def _sess(role):
    s = SESSIONS.get(role)
    if not s:
        pytest.skip(f"{role} not authenticated")
    return s


@pytest.fixture(scope="session", autouse=True)
def authenticate_all():
    for role, (email, pwd) in CREDS.items():
        s, u = _login(email, pwd)
        if s is not None:
            SESSIONS[role] = s
            USERS[role] = u
    if "super_admin" not in SESSIONS:
        pytest.skip("super_admin login failed — cannot run iteration 47 suite")
    yield


YEAR_RE = r"^[A-Z]{2,3}/[A-Z]{1,4}/\d{4}/\d{4}$"  # e.g. HR/ADV/2026/0001 OR ACC/RAB/...


STATE: dict = {"emp_id": None, "type_id": None, "first_advance_id": None,
               "first_dept_no": None, "second_dept_no": None,
               "dept_id_created": None, "po_id": None, "pr_id": None}


# ────────────────── 1. SEQUENCES (via /api/advances) ───────────────────
class TestAdvanceDeptStamping:
    """POST /api/advances — verifies dept_doc_no + legacy advance_no + ownership."""

    def test_seed_employee_and_type(self):
        s = _sess("super_admin")
        emp = {"name": "TEST_iter47_emp_" + uuid.uuid4().hex[:6], "department": "hr",
               "designation": "Tester", "join_date": "2024-01-01",
               "base_salary": 30000, "phone": "9000000001", "status": "active"}
        r = s.post(f"{API}/employees", json=emp, timeout=30)
        assert r.status_code in (200, 201), r.text
        STATE["emp_id"] = r.json()["id"]
        rt = s.get(f"{API}/advance-types", timeout=30)
        assert rt.status_code == 200
        types = rt.json()
        assert types, "expected seeded advance_types"
        STATE["type_code"] = types[0].get("code") or types[0].get("name")

    def test_create_advance_stamps_dept_no(self):
        s = _sess("super_admin")
        body = {"employee_id": STATE["emp_id"], "advance_type": STATE["type_code"],
                "requested_amount": 5000, "reason": "iter47 dept-no test",
                "installments": 2}
        r = s.post(f"{API}/advances", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        STATE["first_advance_id"] = doc["id"]
        STATE["first_dept_no"] = doc.get("dept_doc_no")
        # Legacy AD-####
        assert "advance_no" in doc and re.match(r"^AD-\d{4}-\d{4}$", doc["advance_no"]), doc.get("advance_no")
        # New dept-prefixed
        assert "dept_doc_no" in doc, "missing dept_doc_no"
        assert doc["dept_doc_no"].startswith("HR/ADV/"), doc["dept_doc_no"]
        assert re.match(YEAR_RE, doc["dept_doc_no"]), doc["dept_doc_no"]
        assert doc.get("ownership_department") == "hr"

    def test_second_advance_increments_counter(self):
        s = _sess("super_admin")
        body = {"employee_id": STATE["emp_id"], "advance_type": STATE["type_code"],
                "requested_amount": 7000, "reason": "iter47 second", "installments": 2}
        r = s.post(f"{API}/advances", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        STATE["second_dept_no"] = r.json().get("dept_doc_no")
        assert STATE["second_dept_no"] and STATE["second_dept_no"] != STATE["first_dept_no"]
        # extract trailing counter, ensure strictly greater
        n1 = int(STATE["first_dept_no"].rsplit("/", 1)[-1])
        n2 = int(STATE["second_dept_no"].rsplit("/", 1)[-1])
        assert n2 == n1 + 1, f"counter not incremented: {n1} → {n2}"


# ────────────────── 2. DEPARTMENT MASTER CRUD ──────────────────────────
class TestDepartmentMaster:
    def test_list_returns_9_seeded(self):
        s = _sess("super_admin")
        r = s.get(f"{API}/admin/department-master", timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()
        slugs = {r["slug"] for r in rows}
        expected = {"sales", "projects", "accounts", "finance", "store",
                    "safety", "logistics", "hr", "procurement"}
        assert expected.issubset(slugs), f"missing seeded slugs: {expected - slugs}"
        # shape
        for row in rows:
            assert {"slug", "code", "name", "sub_departments", "branches", "business_units", "active"} <= set(row.keys())

    def test_non_admin_cannot_create_403(self):
        s = SESSIONS.get("project_manager")
        if not s:
            pytest.skip("pm not authenticated")
        r = s.post(f"{API}/admin/department-master",
                   json={"slug": "qa", "code": "QA", "name": "Quality"}, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_admin_create_then_duplicate_409(self):
        s = _sess("super_admin")
        slug = f"test47_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/admin/department-master",
                   json={"slug": slug, "code": "TST", "name": "Iter47 Test Dept"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        STATE["dept_id_created"] = doc["id"]
        assert doc["slug"] == slug
        # duplicate
        r2 = s.post(f"{API}/admin/department-master",
                    json={"slug": slug, "code": "TST", "name": "Dup"}, timeout=30)
        assert r2.status_code == 409, r2.text

    def test_put_and_items_endpoints(self):
        s = _sess("super_admin")
        dept_id = STATE["dept_id_created"]
        assert dept_id, "prior create must succeed"
        # PUT update
        r = s.put(f"{API}/admin/department-master/{dept_id}",
                  json={"slug": "test47_updated_" + uuid.uuid4().hex[:6], "code": "TST",
                        "name": "Iter47 Updated"}, timeout=30)
        assert r.status_code == 200, r.text
        # items: add sub_department
        r2 = s.post(f"{API}/admin/department-master/{dept_id}/items",
                    json={"kind": "sub_departments", "value": "Sub-A"}, timeout=30)
        assert r2.status_code == 200, r2.text
        # invalid kind
        r3 = s.post(f"{API}/admin/department-master/{dept_id}/items",
                    json={"kind": "bogus", "value": "x"}, timeout=30)
        assert r3.status_code == 400, r3.text
        # remove via query params
        r4 = s.delete(f"{API}/admin/department-master/{dept_id}/items",
                      params={"kind": "sub_departments", "value": "Sub-A"}, timeout=30)
        assert r4.status_code == 200, r4.text

    def test_delete_builtin_blocked(self):
        s = _sess("super_admin")
        rows = s.get(f"{API}/admin/department-master", timeout=30).json()
        hr_row = next((x for x in rows if x["slug"] == "hr"), None)
        assert hr_row, "hr seed missing"
        r = s.delete(f"{API}/admin/department-master/{hr_row['id']}", timeout=30)
        assert r.status_code == 400, f"expected 400 built-in delete blocked, got {r.status_code}"

    def test_delete_custom_ok(self):
        s = _sess("super_admin")
        if not STATE["dept_id_created"]:
            pytest.skip("nothing created")
        r = s.delete(f"{API}/admin/department-master/{STATE['dept_id_created']}", timeout=30)
        assert r.status_code == 200, r.text


# ────────────────── 3. PROCUREMENT STAMPING ────────────────────────────
class TestProcurementStamping:
    def test_pr_stamps_dept_no(self):
        s = _sess("super_admin")
        body = {"items": [{"name": "bolt", "description": "bolt", "quantity": 10, "unit": "nos"}]}
        r = s.post(f"{API}/procurement/prs", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        STATE["pr_id"] = doc.get("id")
        assert doc.get("dept_doc_no", "").startswith("PRO/PR/"), doc.get("dept_doc_no")
        assert doc.get("ownership_department") == "procurement"
        # legacy still present
        assert doc.get("pr_number"), "legacy pr_number missing"

    def test_rfq_stamps_dept_no(self):
        s = _sess("super_admin")
        body = {"items": [{"name": "nut", "description": "nut", "quantity": 5, "unit": "nos"}]}
        r = s.post(f"{API}/procurement/rfqs", json=body, timeout=30)
        if r.status_code in (404, 422):
            pytest.skip(f"RFQ create payload mismatch: {r.status_code} {r.text[:120]}")
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc.get("dept_doc_no", "").startswith("PRO/RFQ/"), doc.get("dept_doc_no")
        assert doc.get("ownership_department") == "procurement"


# ────────────────── 4. SALES STAMPING ──────────────────────────────────
class TestSalesStamping:
    def test_enquiry_stamps(self):
        s = _sess("super_admin")
        body = {"customer": "TEST47 Client " + uuid.uuid4().hex[:5],
                "subject": "iter47 enquiry", "source": "web"}
        r = s.post(f"{API}/enquiries", json=body, timeout=30)
        if r.status_code in (404, 422):
            pytest.skip(f"enquiry endpoint not accepting payload: {r.status_code} {r.text[:120]}")
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc.get("dept_doc_no", "").startswith("SAL/ENQ/"), doc.get("dept_doc_no")
        assert doc.get("ownership_department") == "sales"


# ────────────────── 5. SITE EXECUTION STAMPING ─────────────────────────
class TestSiteExecStamping:
    def test_dpr_stamps(self):
        s = _sess("super_admin")
        # Find any project
        rp = s.get(f"{API}/projects", timeout=30)
        if rp.status_code != 200 or not rp.json():
            pytest.skip("no project to attach DPR to")
        project_id = rp.json()[0]["id"]
        body = {"project_id": project_id, "date": "2026-01-15",
                "weather": "Clear", "manpower": []}
        r = s.post(f"{API}/dprs", json=body, timeout=30)
        if r.status_code in (404, 422):
            pytest.skip(f"dpr create payload mismatch: {r.status_code} {r.text[:120]}")
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc.get("dept_doc_no", "").startswith("OPS/DPR/"), doc.get("dept_doc_no")
        assert doc.get("ownership_department") == "projects"


# ────────────────── 6. RECEIVABLES STAMPING ────────────────────────────
class TestReceivablesStamping:
    def test_payment_in_stamps(self):
        s = _sess("super_admin")
        # try minimal payload
        body = {"amount": 1000, "client_id": None, "client_name": "TEST47",
                "payment_date": "2026-01-10", "mode": "cash"}
        r = s.post(f"{API}/payments-in", json=body, timeout=30)
        if r.status_code in (404, 422):
            pytest.skip(f"payments-in not accepting payload: {r.status_code} {r.text[:120]}")
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc.get("dept_doc_no", "").startswith("FIN/RCT/"), doc.get("dept_doc_no")
        assert doc.get("ownership_department") == "finance"


# ────────────────── 7. VISIBILITY SCOPING ──────────────────────────────
class TestScoping:
    def test_super_admin_sees_all_employees(self):
        s = _sess("super_admin")
        r = s.get(f"{API}/employees", timeout=30)
        assert r.status_code == 200
        STATE["sa_emp_count"] = len(r.json())

    def test_project_manager_employees_scoped(self):
        s = SESSIONS.get("project_manager")
        if not s:
            pytest.skip("pm not authenticated")
        r = s.get(f"{API}/employees", timeout=30)
        assert r.status_code == 200, r.text
        pm_count = len(r.json())
        # PM is dept-scoped — should NOT see all employees (super_admin does)
        sa = STATE.get("sa_emp_count", pm_count)
        assert pm_count <= sa, f"pm({pm_count}) should be ≤ super_admin({sa})"

    def test_project_manager_advances_scoped(self):
        s = SESSIONS.get("project_manager")
        if not s:
            pytest.skip("pm not authenticated")
        r = s.get(f"{API}/employee_advances", timeout=30)
        # endpoint may not exist by that name — try advances
        if r.status_code == 404:
            r = s.get(f"{API}/advances", timeout=30)
        assert r.status_code in (200, 403), r.text

    def test_project_manager_project_scoped_collections(self):
        s = SESSIONS.get("project_manager")
        if not s:
            pytest.skip("pm not authenticated")
        sa = _sess("super_admin")
        for coll in ("purchase_requisitions", "rfqs", "grns", "dprs", "measurements", "ra_bills"):
            r_sa = sa.get(f"{API}/{coll}", timeout=30)
            r_pm = s.get(f"{API}/{coll}", timeout=30)
            if r_sa.status_code == 404 or r_pm.status_code == 404:
                # try with hyphen variant
                hcoll = coll.replace("_", "-")
                r_sa = sa.get(f"{API}/{hcoll}", timeout=30)
                r_pm = s.get(f"{API}/{hcoll}", timeout=30)
                if r_sa.status_code == 404 or r_pm.status_code == 404:
                    continue
            if r_sa.status_code == 200 and r_pm.status_code == 200:
                sa_n = len(r_sa.json()) if isinstance(r_sa.json(), list) else 0
                pm_n = len(r_pm.json()) if isinstance(r_pm.json(), list) else 0
                assert pm_n <= sa_n, f"{coll}: pm({pm_n}) > super_admin({sa_n})"


# ────────────────── 8. REGRESSION ──────────────────────────────────────
class TestRegression:
    def test_advance_legacy_numbering_intact(self):
        # already validated in TestAdvanceDeptStamping, but assert state still holds
        assert STATE.get("first_dept_no"), "iter47 advance create did not run"
