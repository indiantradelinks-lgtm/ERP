"""Iteration 12 — Department modules + auto-numbering."""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
ENGINEER = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}

EXPECTED_SLUGS = ["sales", "projects", "accounts", "finance", "store", "safety", "logistics", "hr", "procurement"]


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    if r.status_code != 200:
        return None
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = _login(ADMIN)
    assert s is not None, "Admin login failed"
    return s


@pytest.fixture(scope="module")
def engineer_session(admin_session):
    s = _login(ENGINEER)
    if s is None:
        # Try to register
        admin_session.post(f"{API}/auth/register", json={
            "email": ENGINEER["email"],
            "password": ENGINEER["password"],
            "name": "Site Engineer",
            "role": "site_engineer",
        }, timeout=20)
        s = _login(ENGINEER)
    assert s is not None, "Engineer login/registration failed"
    return s


# ── /dashboard/departments ──────────────────────────────────────────────
class TestDepartmentsList:
    def test_list_returns_9_slugs(self, admin_session):
        r = admin_session.get(f"{API}/dashboard/departments", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "departments" in data
        depts = data["departments"]
        assert len(depts) == 9
        slugs = [d["slug"] for d in depts]
        for s in EXPECTED_SLUGS:
            assert s in slugs, f"Missing slug {s}"

    def test_each_dept_has_required_fields(self, admin_session):
        r = admin_session.get(f"{API}/dashboard/departments", timeout=20)
        for d in r.json()["departments"]:
            for k in ("slug", "title", "tagline", "icon", "color", "headline"):
                assert k in d, f"{d.get('slug')} missing {k}"

    def test_non_super_admin_can_access(self, engineer_session):
        r = engineer_session.get(f"{API}/dashboard/departments", timeout=20)
        assert r.status_code == 200, r.text
        assert len(r.json()["departments"]) == 9


# ── /dashboard/department/{slug} ────────────────────────────────────────
class TestDepartmentDetail:
    def test_sales_shape(self, admin_session):
        r = admin_session.get(f"{API}/dashboard/department/sales", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("slug", "title", "tagline", "icon", "color", "kpis", "links"):
            assert k in d
        assert d["slug"] == "sales"
        assert isinstance(d["kpis"], list) and len(d["kpis"]) >= 1
        for kpi in d["kpis"]:
            for k in ("label", "value", "tone", "deeplink", "format"):
                assert k in kpi, f"KPI missing key {k}: {kpi}"
        assert isinstance(d["links"], list) and len(d["links"]) >= 1
        for ln in d["links"]:
            for k in ("label", "to", "description"):
                assert k in ln

    @pytest.mark.parametrize("slug", EXPECTED_SLUGS)
    def test_all_9_slugs_work(self, admin_session, slug):
        r = admin_session.get(f"{API}/dashboard/department/{slug}", timeout=20)
        assert r.status_code == 200, f"{slug}: {r.text}"
        d = r.json()
        assert d["slug"] == slug
        assert isinstance(d["kpis"], list)
        assert isinstance(d["links"], list)

    def test_unknown_slug_returns_404(self, admin_session):
        r = admin_session.get(f"{API}/dashboard/department/foo", timeout=20)
        assert r.status_code == 404
        assert "Unknown department" in r.json().get("detail", "")
        assert "foo" in r.json().get("detail", "")

    def test_engineer_can_access_sales(self, engineer_session):
        r = engineer_session.get(f"{API}/dashboard/department/sales", timeout=20)
        assert r.status_code == 200


# ── Auto-numbering ──────────────────────────────────────────────────────
YEAR_RE = r"\d{4}"

class TestAutoNumbering:
    def test_ptw_auto_number(self, admin_session):
        payload = {"title": "TEST_AUTO_PTW", "type": "hot_work", "status": "open"}
        r = admin_session.post(f"{API}/ptws", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert "ptw_no" in d and d["ptw_no"], "ptw_no not auto-assigned"
        assert re.match(rf"^PTW-{YEAR_RE}-\d+$", d["ptw_no"]), f"Bad pattern: {d['ptw_no']}"
        admin_session.delete(f"{API}/ptws/{d['id']}", timeout=10)

    def test_ptw_explicit_number_preserved(self, admin_session):
        payload = {"title": "TEST_CUSTOM_PTW", "ptw_no": "CUSTOM-1", "status": "open"}
        r = admin_session.post(f"{API}/ptws", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d["ptw_no"] == "CUSTOM-1", f"Custom number overwritten: {d.get('ptw_no')}"
        admin_session.delete(f"{API}/ptws/{d['id']}", timeout=10)

    def test_jv_auto_number(self, admin_session):
        payload = {"description": "TEST_AUTO_JV", "type": "expense", "amount": 100}
        r = admin_session.post(f"{API}/journal-entries", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("voucher_no"), "voucher_no not auto-assigned"
        assert re.match(rf"^JV-{YEAR_RE}-\d+$", d["voucher_no"]), f"Bad: {d['voucher_no']}"
        admin_session.delete(f"{API}/journal-entries/{d['id']}", timeout=10)

    def test_incident_auto_number(self, admin_session):
        payload = {"title": "TEST_INC", "severity": "low", "status": "open"}
        r = admin_session.post(f"{API}/safety-reports", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("incident_no"), "incident_no not assigned"
        assert re.match(rf"^INC-{YEAR_RE}-\d+$", d["incident_no"]), f"Bad: {d['incident_no']}"
        admin_session.delete(f"{API}/safety-reports/{d['id']}", timeout=10)

    def test_recruitment_auto_number(self, admin_session):
        payload = {"role": "TEST_ROLE", "status": "open"}
        r = admin_session.post(f"{API}/recruitment-requests", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("req_no"), "req_no not assigned"
        assert re.match(rf"^REQ-{YEAR_RE}-\d+$", d["req_no"]), f"Bad: {d['req_no']}"
        admin_session.delete(f"{API}/recruitment-requests/{d['id']}", timeout=10)
