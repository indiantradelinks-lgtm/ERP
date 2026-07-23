"""Iter143 · Onboarding Employee Status + Existing-employee Reuse tests.

Covers:
- GET /api/hr/onboardings/employee-status (employee & worker masters, count sanity)
- POST /api/hr/onboardings/start-for-employee (create + duplicate 400 + unknown 404)
- POST /api/hr/onboardings/{oid}/advance (progress_pct increases)
- POST /api/hr/onboardings/{oid}/complete for existing employee → triggers.employee_reused=True,
  no duplicate employee created, status=completed
- Regression: normal new joiner flow (create → advance → complete) creates NEW employee
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASS = "Admin@123"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


def _get_status(api, master="employee"):
    r = api.get(f"{BASE_URL}/api/hr/onboardings/employee-status", params={"master": master}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


class TestEmployeeStatus:
    def test_shape_and_counts_employee(self, api):
        data = _get_status(api, "employee")
        assert "total" in data and "completed" in data and "in_progress" in data and "not_started" in data
        assert "rows" in data and isinstance(data["rows"], list)
        assert data["completed"] + data["in_progress"] + data["not_started"] == data["total"]
        assert len(data["rows"]) == data["total"]
        if data["rows"]:
            row = data["rows"][0]
            for k in ["employee_id", "emp_code", "name", "status", "progress_pct",
                      "stages_done", "stages_total"]:
                assert k in row, f"missing key {k}"

    def test_worker_master(self, api):
        data = _get_status(api, "worker")
        assert "total" in data
        assert data["completed"] + data["in_progress"] + data["not_started"] == data["total"]


class TestStartForEmployee:
    """Full flow: pick a not_started employee, start, advance, complete → reused=True."""

    def test_full_reuse_flow(self, api):
        before = _get_status(api, "employee")
        ns_rows = [r for r in before["rows"] if r["status"] == "not_started"]
        if not ns_rows:
            pytest.skip("no not_started employee available")
        emp_id = ns_rows[0]["employee_id"]

        # Start
        r = api.post(f"{BASE_URL}/api/hr/onboardings/start-for-employee",
                     json={"employee_id": emp_id}, timeout=30)
        assert r.status_code == 200, r.text
        onb = r.json()
        oid = onb["id"]
        assert onb.get("for_existing_employee") is True
        assert onb.get("employee_id") == emp_id
        assert onb.get("status") == "in_progress"
        assert len(onb.get("stages") or []) == 6

        # Duplicate → 400
        r2 = api.post(f"{BASE_URL}/api/hr/onboardings/start-for-employee",
                      json={"employee_id": emp_id}, timeout=30)
        assert r2.status_code == 400, r2.text

        # Unknown → 404
        r3 = api.post(f"{BASE_URL}/api/hr/onboardings/start-for-employee",
                      json={"employee_id": "no-such-id-xyz"}, timeout=30)
        assert r3.status_code == 404

        # Verify employee-status now shows this emp as in_progress
        after_start = _get_status(api, "employee")
        row = next((r for r in after_start["rows"] if r["employee_id"] == emp_id), None)
        assert row is not None
        assert row["status"] == "in_progress"
        assert row["onboarding_id"] == oid

        # Advance one stage → progress_pct > 0
        r4 = api.post(f"{BASE_URL}/api/hr/onboardings/{oid}/advance",
                      json={"stage_key": "offer_accepted"}, timeout=30)
        assert r4.status_code == 200, r4.text
        after_adv = _get_status(api, "employee")
        row2 = next((r for r in after_adv["rows"] if r["employee_id"] == emp_id), None)
        assert row2["progress_pct"] > 0

        # Snapshot employee count before complete
        emp_count_before = before["total"]

        # Complete WITHOUT create_login/ppe/induction to minimise side-effects
        r5 = api.post(f"{BASE_URL}/api/hr/onboardings/{oid}/complete",
                      json={"create_login": False, "issue_ppe_kit": False,
                            "schedule_induction": False}, timeout=45)
        assert r5.status_code == 200, r5.text
        result = r5.json()
        triggers = result.get("triggers") or {}
        assert triggers.get("employee_reused") is True, f"triggers={triggers}"
        # emp_code should match existing employee
        assert triggers.get("emp_code")

        # After complete: total should be unchanged (no duplicate employee created)
        after_complete = _get_status(api, "employee")
        assert after_complete["total"] == emp_count_before, \
            f"employee count changed: before={emp_count_before} after={after_complete['total']}"
        row3 = next((r for r in after_complete["rows"] if r["employee_id"] == emp_id), None)
        assert row3["status"] == "completed"
        assert row3["progress_pct"] == 100

        # Cleanup: onboarding is completed → delete via mongo-style is skipped
        # We store the id for reporting
        pytest.completed_onb_id = oid


class TestNewJoinerRegression:
    def test_new_joiner_creates_new_employee(self, api):
        before = _get_status(api, "employee")
        total_before = before["total"]

        # Create new onboarding (no employee_id)
        payload = {
            "name": "TEST_iter143_NewJoiner",
            "email": f"test_iter143_{int(time.time())}@example.com",
            "role": "supervisor",
            "department": "Operations",
            "designation": "Test Supervisor",
        }
        r = api.post(f"{BASE_URL}/api/hr/onboardings", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        onb = r.json()
        oid = onb["id"]
        assert onb.get("status") == "in_progress"
        assert onb.get("employee_id") is None

        # Advance a stage
        r2 = api.post(f"{BASE_URL}/api/hr/onboardings/{oid}/advance",
                      json={"stage_key": "offer_accepted"}, timeout=30)
        assert r2.status_code == 200

        # Complete without triggers (still creates employee)
        r3 = api.post(f"{BASE_URL}/api/hr/onboardings/{oid}/complete",
                      json={"create_login": False, "issue_ppe_kit": False,
                            "schedule_induction": False}, timeout=45)
        assert r3.status_code == 200, r3.text
        result = r3.json()
        triggers = result.get("triggers") or {}
        # employee_reused should be absent (or falsy) — this is a new-joiner
        assert not triggers.get("employee_reused"), f"expected new employee, got {triggers}"
        assert triggers.get("employee_id")
        assert triggers.get("emp_code")

        # Employee count should have +1
        after = _get_status(api, "employee")
        assert after["total"] == total_before + 1, \
            f"expected +1 employee, got before={total_before} after={after['total']}"

        # Cleanup: mark employee inactive so it doesn't pollute future runs
        new_emp_id = triggers["employee_id"]
        api.patch(f"{BASE_URL}/api/hr/employees/{new_emp_id}",
                  json={"status": "inactive"}, timeout=15)
