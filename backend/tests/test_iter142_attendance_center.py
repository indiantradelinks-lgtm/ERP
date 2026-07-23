"""Iter 142 — Attendance Center backend tests.

Covers:
  - Admin day-sheet GET/POST for HEAD-OFFICE
  - PM 403 on HEAD-OFFICE day-sheet (read + write)
  - PM allowed on assigned project day-sheet
  - Register filtering + project-scope for PM
  - Bulk template xlsx download
  - Future-date rejection, invalid status errors[]
  - Regression: monthly-summary still works
"""
import os
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin() -> requests.Session:
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def pm() -> requests.Session:
    return _login("test_pm@erp.com", "PM@12345")


@pytest.fixture(scope="module")
def pm_project_code(pm) -> str:
    r = pm.get(f"{BASE_URL}/api/projects", timeout=30)
    assert r.status_code == 200, r.text[:200]
    rows = r.json() or []
    assert rows, "PM has no projects assigned — cannot run project-scoped tests"
    # Prefer a code, fallback to name
    return rows[0].get("code") or rows[0].get("name")


TODAY = date.today().isoformat()
FUTURE = (date.today() + timedelta(days=5)).isoformat()


# ────────── Admin: HEAD-OFFICE day-sheet ──────────
class TestAdminDaySheetHeadOffice:
    def test_get_head_office(self, admin):
        r = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                      params={"date": TODAY, "master": "employee", "project_code": "HEAD-OFFICE"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["date"] == TODAY
        assert d["project_code"] == "HEAD-OFFICE"
        assert "designations" in d and isinstance(d["designations"], list)
        assert "rows" in d and isinstance(d["rows"], list)
        assert d["rows"], "expected non-empty rows for admin HEAD-OFFICE"
        row = d["rows"][0]
        for k in ("employee_id", "code", "name", "designation", "status", "overtime_hours", "approval_status", "entry_locked"):
            assert k in row

    def test_designation_filter(self, admin):
        base = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                         params={"date": TODAY, "master": "employee", "project_code": "HEAD-OFFICE"}, timeout=30).json()
        desigs = [x for x in base.get("designations", []) if x]
        if not desigs:
            pytest.skip("no designations available")
        r = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                      params={"date": TODAY, "master": "employee", "project_code": "HEAD-OFFICE",
                              "designation": desigs[0]}, timeout=30)
        assert r.status_code == 200
        for row in r.json()["rows"]:
            assert row["designation"] == desigs[0]

    def test_post_and_reget(self, admin):
        d = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                      params={"date": TODAY, "master": "employee", "project_code": "HEAD-OFFICE"}, timeout=30).json()
        target = d["rows"][0]
        payload = {
            "date": TODAY, "project_code": "HEAD-OFFICE", "master": "employee",
            "entries": [{"employee_id": target["employee_id"], "status": "present", "overtime_hours": 2}],
        }
        r = admin.post(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:200]
        rj = r.json()
        assert rj["ok"] is True
        assert (rj["created"] + rj["updated"]) >= 1
        assert rj["errors"] == []

        # Re-post idempotent → updated (not created twice)
        r2 = admin.post(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet", json=payload, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["created"] == 0
        assert r2.json()["updated"] >= 1

        # Re-get: row should now have approval_status=pending
        d2 = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                       params={"date": TODAY, "master": "employee", "project_code": "HEAD-OFFICE"}, timeout=30).json()
        got = next((r for r in d2["rows"] if r["employee_id"] == target["employee_id"]), None)
        assert got and got["status"] == "present"
        assert got["approval_status"] == "pending"
        assert (got["overtime_hours"] or 0) == 2

    def test_future_date_rejected(self, admin):
        r = admin.post(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet", json={
            "date": FUTURE, "project_code": "HEAD-OFFICE", "master": "employee",
            "entries": [{"employee_id": "x", "status": "present"}],
        }, timeout=30)
        assert r.status_code == 400

    def test_invalid_status_goes_to_errors(self, admin):
        d = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                      params={"date": TODAY, "master": "employee", "project_code": "HEAD-OFFICE"}, timeout=30).json()
        eid = d["rows"][0]["employee_id"]
        r = admin.post(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet", json={
            "date": TODAY, "project_code": "HEAD-OFFICE", "master": "employee",
            "entries": [{"employee_id": eid, "status": "bogus"}],
        }, timeout=30)
        assert r.status_code == 200
        assert r.json()["errors"], "expected errors[] for invalid status"


# ────────── PM scoping ──────────
class TestPmScoping:
    def test_pm_forbidden_on_head_office_read(self, pm):
        r = pm.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                   params={"date": TODAY, "master": "employee", "project_code": "HEAD-OFFICE"}, timeout=30)
        assert r.status_code == 403
        assert "Head Office" in r.text

    def test_pm_forbidden_on_head_office_write(self, pm):
        r = pm.post(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet", json={
            "date": TODAY, "project_code": "HEAD-OFFICE", "master": "employee",
            "entries": [{"employee_id": "x", "status": "present"}],
        }, timeout=30)
        assert r.status_code == 403

    def test_pm_forbidden_on_unassigned_project(self, pm):
        r = pm.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                   params={"date": TODAY, "master": "employee", "project_code": "__NOT_ASSIGNED__"}, timeout=30)
        assert r.status_code == 403

    def test_pm_allowed_on_assigned_project(self, pm, pm_project_code):
        r = pm.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                   params={"date": TODAY, "master": "employee", "project_code": pm_project_code}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        assert r.json()["project_code"] == pm_project_code

    def test_pm_register_is_scoped(self, pm):
        r = pm.get(f"{BASE_URL}/api/hr2/attendance/register",
                   params={"from_date": (date.today() - timedelta(days=30)).isoformat(),
                           "to_date": TODAY, "limit": 500}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        rows = r.json() or []
        # No row should be for HEAD-OFFICE
        assert not any((row.get("project_code") == "HEAD-OFFICE") for row in rows), \
            "PM register leaks HEAD-OFFICE rows"


# ────────── Register (admin) ──────────
class TestRegister:
    def test_admin_register_returns_rows(self, admin):
        r = admin.get(f"{BASE_URL}/api/hr2/attendance/register",
                      params={"from_date": (date.today() - timedelta(days=30)).isoformat(),
                              "to_date": TODAY, "project_code": "HEAD-OFFICE", "limit": 500}, timeout=30)
        assert r.status_code == 200
        rows = r.json() or []
        # After we posted above there is at least one HEAD-OFFICE row
        assert any(row.get("project_code") == "HEAD-OFFICE" for row in rows)


# ────────── Bulk template ──────────
class TestBulkTemplate:
    def test_template_employee(self, admin):
        r = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/template",
                      params={"month": "2026-06", "master": "employee"}, timeout=60)
        assert r.status_code == 200
        assert "spreadsheet" in r.headers.get("content-type", "")

    def test_template_worker(self, admin):
        r = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/template",
                      params={"month": "2026-06", "master": "worker"}, timeout=60)
        assert r.status_code == 200

    def test_template_bad_month(self, admin):
        r = admin.get(f"{BASE_URL}/api/hr2/attendance/bulk/template",
                      params={"month": "bad", "master": "employee"}, timeout=30)
        assert r.status_code == 400


# ────────── Regression ──────────
class TestRegression:
    def test_monthly_summary(self, admin):
        r = admin.get(f"{BASE_URL}/api/hr2/attendance/monthly-summary",
                      params={"month": "2026-06"}, timeout=30)
        assert r.status_code == 200
