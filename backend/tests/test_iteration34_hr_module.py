"""Iteration 34 HR module backend tests: Onboarding, Employee 360, Leave."""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    BASE = "https://worksite-command.preview.emergentagent.com"
API = f"{BASE}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def supervisor():
    try:
        return _login("supervisor@erp.com", "Super@1234")
    except AssertionError:
        pytest.skip("supervisor login not available")


@pytest.fixture(scope="module")
def hr():
    try:
        return _login("hr.test@erp.com", "HR@12345")
    except AssertionError:
        return None


# ── Onboarding ──────────────────────────────────────────────────────────
class TestOnboarding:
    def test_stages_list(self, admin):
        r = admin.get(f"{API}/hr/onboardings/stages")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 6
        keys = [s["key"] for s in data]
        assert keys == ["offer_accepted", "docs_uploaded", "id_card_issued",
                        "ppe_issued", "induction_done", "site_assigned"]

    def test_create_onboarding(self, admin):
        payload = {"name": "TEST_Joiner_QA", "email": "test_joiner_qa@example.com",
                   "phone": "9999000000", "role": "supervisor", "department": "Operations",
                   "joining_date": "2026-02-01", "designation": "QA Test",
                   "salary": 35000}
        r = admin.post(f"{API}/hr/onboardings", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "in_progress"
        assert len(d["stages"]) == 6
        assert all(s["done"] is False for s in d["stages"])
        pytest.onboarding_id = d["id"]

    def test_advance_stage(self, admin):
        oid = pytest.onboarding_id
        r = admin.post(f"{API}/hr/onboardings/{oid}/advance",
                       json={"stage_key": "offer_accepted", "notes": "ok"})
        assert r.status_code == 200, r.text
        d = r.json()
        s0 = next(s for s in d["stages"] if s["key"] == "offer_accepted")
        assert s0["done"] is True
        assert s0["done_by"]
        first_done_at = s0["done_at"]
        # idempotent re-advance updates done_at
        r2 = admin.post(f"{API}/hr/onboardings/{oid}/advance",
                        json={"stage_key": "offer_accepted"})
        assert r2.status_code == 200
        s1 = next(s for s in r2.json()["stages"] if s["key"] == "offer_accepted")
        assert s1["done"] is True

    def test_rbac_supervisor_403(self, supervisor):
        r = supervisor.post(f"{API}/hr/onboardings",
                            json={"name": "should_fail", "role": "supervisor"})
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_complete_triggers(self, admin):
        oid = pytest.onboarding_id
        r = admin.post(f"{API}/hr/onboardings/{oid}/complete",
                       json={"create_login": True, "issue_ppe_kit": True,
                             "schedule_induction": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        t = d["triggers"]
        assert t.get("emp_code", "").startswith("E-")
        assert t.get("employee_id")
        assert t.get("ppe_issuance_id")
        assert t.get("safety_training_id")
        assert t.get("user_login") in ("created", "existing")
        assert t.get("leave_balances_granted", 0) >= 4
        pytest.test_emp_id = t["employee_id"]
        # status flipped
        r2 = admin.get(f"{API}/hr/onboardings/{oid}")
        assert r2.json()["status"] == "completed"

    def test_complete_twice_400(self, admin):
        r = admin.post(f"{API}/hr/onboardings/{pytest.onboarding_id}/complete",
                       json={"create_login": False, "issue_ppe_kit": False,
                             "schedule_induction": False})
        assert r.status_code == 400


# ── Employee 360 ────────────────────────────────────────────────────────
class TestEmployee360:
    def test_360_payload(self, admin):
        eid = pytest.test_emp_id
        r = admin.get(f"{API}/hr/employee-360/{eid}")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("personal", "skills", "certifications", "ppe_history",
                  "trainings", "deployments", "attendance_30d", "payroll",
                  "documents", "leave_balances", "recent_leaves"):
            assert k in d, f"missing key {k}"
        assert len(d["leave_balances"]) >= 4
        assert len(d["ppe_history"]) >= 1
        assert len(d["trainings"]) >= 1

    def test_add_skill(self, admin):
        eid = pytest.test_emp_id
        r = admin.post(f"{API}/hr/employees/{eid}/skills",
                       json={"skill": "Welding", "level": "expert", "years": 3})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        # delete
        r2 = admin.delete(f"{API}/hr/employees/{eid}/skills/{sid}")
        assert r2.status_code == 200

    def test_missing_emp_404(self, admin):
        r = admin.post(f"{API}/hr/employees/nonexistent/skills",
                       json={"skill": "x"})
        assert r.status_code == 404

    def test_add_cert_expiry_status(self, admin):
        eid = pytest.test_emp_id
        # cert expiring in ~23 days from today => "expiring_soon"
        future = (datetime.utcnow().date() + timedelta(days=20)).isoformat()
        r = admin.post(f"{API}/hr/employees/{eid}/certifications",
                       json={"name": "Test Cert", "expiry_date": future})
        assert r.status_code == 200
        # check via 360
        r2 = admin.get(f"{API}/hr/employee-360/{eid}")
        certs = r2.json()["certifications"]
        c = next((c for c in certs if c["name"] == "Test Cert"), None)
        assert c is not None
        assert c["expiry_status"] == "expiring_soon", f"got {c['expiry_status']}, days={c.get('expires_in_days')}"


# ── Leave Management ────────────────────────────────────────────────────
class TestLeave:
    def test_leave_types(self, admin):
        r = admin.get(f"{API}/hr/leave-types")
        assert r.status_code == 200
        types = {t["code"] for t in r.json()}
        for code in ("CL", "SL", "EL", "PL"):
            assert code in types, f"missing {code}"

    def test_over_apply_400(self, admin):
        eid = pytest.test_emp_id
        # CL has 12 quota; try 30 days
        r = admin.post(f"{API}/hr/leave-applications", json={
            "employee_id": eid, "leave_type": "CL",
            "from_date": "2026-06-01", "to_date": "2026-06-30",
        })
        assert r.status_code == 400
        assert "Insufficient" in r.text and "balance" in r.text

    def test_apply_approve_balance_deducts(self, admin):
        eid = pytest.test_emp_id
        r = admin.post(f"{API}/hr/leave-applications", json={
            "employee_id": eid, "leave_type": "CL",
            "from_date": "2026-06-10", "to_date": "2026-06-12",
            "reason": "test"
        })
        assert r.status_code == 200, r.text
        lid = r.json()["id"]
        pytest.test_leave_id = lid

        # check balance before
        bal_before = admin.get(f"{API}/hr/leave-balances/{eid}").json()
        cl_before = next(b for b in bal_before["balances"] if b["leave_type"] == "CL")

        r2 = admin.post(f"{API}/hr/leave-applications/{lid}/approve",
                        json={"remarks": "ok"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "approved"

        bal_after = admin.get(f"{API}/hr/leave-balances/{eid}").json()
        cl_after = next(b for b in bal_after["balances"] if b["leave_type"] == "CL")
        assert cl_after["balance"] == cl_before["balance"] - 3
        assert cl_after["used"] == cl_before["used"] + 3

    def test_cancel_restores_balance(self, admin):
        eid = pytest.test_emp_id
        bal_before = admin.get(f"{API}/hr/leave-balances/{eid}").json()
        cl_before = next(b for b in bal_before["balances"] if b["leave_type"] == "CL")

        r = admin.post(f"{API}/hr/leave-applications/{pytest.test_leave_id}/cancel")
        assert r.status_code == 200

        bal_after = admin.get(f"{API}/hr/leave-balances/{eid}").json()
        cl_after = next(b for b in bal_after["balances"] if b["leave_type"] == "CL")
        assert cl_after["balance"] == cl_before["balance"] + 3

    def test_calendar_filter(self, admin):
        eid = pytest.test_emp_id
        # create + approve a leave in July 2026
        r = admin.post(f"{API}/hr/leave-applications", json={
            "employee_id": eid, "leave_type": "SL",
            "from_date": "2026-07-05", "to_date": "2026-07-06"
        })
        assert r.status_code == 200
        lid = r.json()["id"]
        admin.post(f"{API}/hr/leave-applications/{lid}/approve", json={})

        r2 = admin.get(f"{API}/hr/leave-calendar?month=2026-07")
        assert r2.status_code == 200
        d = r2.json()
        assert d["month"] == "2026-07"
        assert any(row["id"] == lid for row in d["rows"])

        # other month should not contain it
        r3 = admin.get(f"{API}/hr/leave-calendar?month=2026-08")
        assert all(row["id"] != lid for row in r3.json()["rows"])

    def test_grant_balance(self, admin):
        eid = pytest.test_emp_id
        bal_before = admin.get(f"{API}/hr/leave-balances/{eid}").json()
        cl_before = next(b for b in bal_before["balances"] if b["leave_type"] == "CL")

        r = admin.post(f"{API}/hr/leave-balances/grant", json={
            "leave_type": "CL", "quantity": 5,
            "employee_ids": [eid], "year": 2026
        })
        assert r.status_code == 200
        assert r.json()["granted_to"] == 1

        bal_after = admin.get(f"{API}/hr/leave-balances/{eid}").json()
        cl_after = next(b for b in bal_after["balances"] if b["leave_type"] == "CL")
        assert cl_after["balance"] == cl_before["balance"] + 5
        assert cl_after["granted"] == cl_before["granted"] + 5


# ── Dashboard ───────────────────────────────────────────────────────────
class TestDashboard:
    def test_dashboard(self, admin):
        r = admin.get(f"{API}/hr/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("active_employees", "onboarding_in_progress",
                  "onboarding_completed_total", "pending_leaves",
                  "expiring_certifications"):
            assert k in d
        assert isinstance(d["expiring_certifications"], list)
