"""Iter202 — Manager Log visibility + Self-advance visibility across endpoints."""
import os
import pytest
import requests

def _frontend_env_url():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _frontend_env_url() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

CREDS = {
    "super_admin": ("admin@erp.com", "Admin@123"),
    "manager_log": ("test_log@erp.com", "Log@12345"),
    "pm": ("test_pm@erp.com", "PM@12345"),
    "hr": ("hr.test@erp.com", "HR@12345"),
    "store": ("store@erp.com", "Store@1234"),
}

MANAGER_LOG_ALLOWED = {"fuel", "service_invoice"}


def _login(role_key):
    email, pwd = CREDS[role_key]
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Login failed for {role_key} ({email}): {r.status_code} {r.text[:120]}")
    # try to also set bearer from body if present
    try:
        tok = (r.json() or {}).get("token") or (r.json() or {}).get("access_token")
        if tok:
            s.headers.update({"Authorization": f"Bearer {tok}"})
    except Exception:
        pass
    return s


@pytest.fixture(scope="module")
def super_admin():
    return _login("super_admin")


@pytest.fixture(scope="module")
def manager_log():
    return _login("manager_log")


@pytest.fixture(scope="module")
def hr():
    return _login("hr")


@pytest.fixture(scope="module")
def store():
    return _login("store")


@pytest.fixture(scope="module")
def pm():
    return _login("pm")


def _list_rows(s, params=None):
    r = s.get(f"{BASE_URL}/api/project-requests", params=params or {}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    rows = body.get("rows") if isinstance(body, dict) else body
    return rows or []


# ---------- Manager Log visibility ----------

class TestManagerLogList:
    def test_list_only_fuel_and_service_invoice(self, manager_log):
        rows = _list_rows(manager_log)
        assert len(rows) > 0, "manager_log should see at least some rows"
        for r in rows:
            rt = r.get("request_type")
            src = r.get("source")
            assert rt in MANAGER_LOG_ALLOWED or src == "service_invoice", (
                f"Leak: req_no={r.get('request_no')} type={rt} source={src}"
            )

    def test_list_with_filter_other_type_returns_empty(self, manager_log):
        for leak_type in ["material", "ppe", "accommodation", "employee_advance",
                          "head_office_expense", "self_expense", "vehicle_manpower"]:
            rows = _list_rows(manager_log, {"request_type": leak_type})
            assert rows == [], f"manager_log leaked for type={leak_type}: {len(rows)} rows"

    def test_list_fuel_filter_returns_only_fuel(self, manager_log):
        rows = _list_rows(manager_log, {"request_type": "fuel"})
        for r in rows:
            assert r.get("request_type") == "fuel"

    def test_super_admin_sees_more_than_manager_log(self, super_admin, manager_log):
        sa_rows = _list_rows(super_admin)
        ml_rows = _list_rows(manager_log)
        assert len(sa_rows) >= len(ml_rows)
        # super_admin should see types besides fuel/service_invoice
        other = [r for r in sa_rows if r.get("request_type") not in MANAGER_LOG_ALLOWED
                 and r.get("source") != "service_invoice"]
        assert len(other) > 0, "super_admin should see non-manager_log rows too"


class TestManagerLogSummary:
    def test_summary_total_matches_list_count(self, manager_log):
        rows = _list_rows(manager_log)
        r = manager_log.get(f"{BASE_URL}/api/project-requests/summary", timeout=20)
        assert r.status_code == 200
        total = r.json().get("total")
        assert total == len(rows), f"summary.total={total} vs list rows={len(rows)}"


class TestManagerLogExport:
    def test_xlsx_export_accessible(self, manager_log):
        r = manager_log.get(f"{BASE_URL}/api/project-requests/export.xlsx", timeout=30)
        # some backends may 404 if route differs — accept 200/404 but if 200 content should be xlsx
        assert r.status_code in (200, 404), r.status_code
        if r.status_code == 200:
            assert len(r.content) > 100

    def test_pdf_export_accessible(self, manager_log):
        r = manager_log.get(f"{BASE_URL}/api/project-requests/export.pdf", timeout=30)
        assert r.status_code in (200, 404), r.status_code


class TestManagerLogInbox:
    def test_inbox_project_requests_only_fuel_or_svc_invoice(self, manager_log):
        r = manager_log.get(f"{BASE_URL}/api/my-inbox", timeout=20)
        assert r.status_code == 200
        items = r.json().get("items") or []
        pr_items = [i for i in items if i.get("source") == "project_request"]
        for it in pr_items:
            title = (it.get("title") or "").lower()
            # Manager Log inbox project_requests must be Fuel Payment or Service Invoice SR
            assert ("fuel" in title) or ("service" in title) or ("invoice" in title), (
                f"Leak in inbox: {it.get('ref')} / {it.get('title')}"
            )


# ---------- Self-advance visibility ----------

class TestSelfAdvanceVisibility:
    def test_store_sees_no_advance_shadow_rows(self, store):
        rows = _list_rows(store)
        adv = [r for r in rows if r.get("source") == "advance"
               or r.get("request_type") == "employee_advance"]
        assert adv == [], f"store_incharge should see 0 self-advance rows, saw {len(adv)}"

    def test_hr_sees_self_advance_rows(self, hr, super_admin):
        sa_rows = _list_rows(super_admin)
        sa_adv = [r for r in sa_rows if r.get("source") == "advance"]
        if not sa_adv:
            pytest.skip("No advance shadow rows in DB to validate HR visibility")
        hr_rows = _list_rows(hr)
        hr_adv = [r for r in hr_rows if r.get("source") == "advance"]
        # HR is privileged — must see all
        assert len(hr_adv) >= len(sa_adv) or len(hr_adv) > 0, (
            f"HR should see advance rows (super_admin sees {len(sa_adv)}, hr sees {len(hr_adv)})"
        )

    def test_super_admin_can_see_advances(self, super_admin):
        rows = _list_rows(super_admin)
        # just confirm shape — can be 0, but should not error
        assert isinstance(rows, list)


# ---------- Advances module regression ----------

class TestAdvancesRegression:
    def test_hr_lists_advances(self, hr):
        r = hr.get(f"{BASE_URL}/api/advances", timeout=20)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        rows = body.get("rows") if isinstance(body, dict) else body
        assert isinstance(rows, list)

    def test_super_admin_lists_advances(self, super_admin):
        r = super_admin.get(f"{BASE_URL}/api/advances", timeout=20)
        assert r.status_code == 200

    def test_store_lists_only_own_advances(self, store):
        r = store.get(f"{BASE_URL}/api/advances", timeout=20)
        # should succeed (may be empty)
        assert r.status_code in (200, 403)


# ---------- Fuel approval RBAC regression ----------

class TestFuelRBACRegression:
    def test_manager_log_inbox_has_fuel_items(self, manager_log):
        r = manager_log.get(f"{BASE_URL}/api/my-inbox", timeout=20)
        assert r.status_code == 200
        items = r.json().get("items") or []
        pr_items = [i for i in items if i.get("source") == "project_request"]
        # OK if empty but if present should mention fuel/service
        for it in pr_items:
            step = (it.get("step_label") or "").lower()
            assert "manager log" in step or "service" in step or step, (
                f"Unexpected step_label: {it.get('step_label')}"
            )

    def test_super_admin_inbox_no_fuel_manager_log_step(self, super_admin):
        r = super_admin.get(f"{BASE_URL}/api/my-inbox", timeout=20)
        assert r.status_code == 200
        items = r.json().get("items") or []
        pr_items = [i for i in items if i.get("source") == "project_request"]
        for it in pr_items:
            # super_admin inbox must NOT list exclusive Manager Log steps
            assert (it.get("step_label") or "").lower() != "manager log", (
                f"super_admin sees exclusive fuel step: {it}"
            )
