"""HR Phase 2 backend tests — shifts, attendance workflow, OT workflow,
compliance alerts, safety readiness."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
BASE = f"{BASE_URL}/api"
EMAIL = os.environ.get("ADMIN_EMAIL", "admin@erp.com")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})

    # Wrapper so existing tests using `.post("/path")` keep working
    class C:
        def __init__(self, sess): self._s = sess
        def post(self, url, json=None):
            return self._s.post(f"{BASE}{url}", json=json, timeout=30)
        def get(self, url):
            return self._s.get(f"{BASE}{url}", timeout=30)
        def put(self, url, json=None):
            return self._s.put(f"{BASE}{url}", json=json, timeout=30)

    yield C(s)
    s.close()


def test_seed_shifts(client):
    r = client.post("/hr2/shifts/seed-defaults")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total"] >= 5
    r2 = client.get("/hr2/shifts?active_only=true")
    assert r2.status_code == 200
    rows = r2.json()
    codes = {x["code"] for x in rows}
    assert {"GEN", "NIGHT", "DAY", "EVE", "HALF"}.issubset(codes)


def test_create_shift_duplicate(client):
    r = client.post("/hr2/shifts", json={
        "code": "TEST-S1", "name": "Test Shift", "start_time": "10:00",
        "end_time": "18:00", "break_minutes": 30, "standard_hours": 7.5,
        "overtime_after": 7.5, "active": True,
    })
    assert r.status_code == 200, r.text
    # Duplicate must 409
    r2 = client.post("/hr2/shifts", json={
        "code": "TEST-S1", "name": "Dup", "start_time": "10:00",
        "end_time": "18:00", "break_minutes": 0, "standard_hours": 8, "overtime_after": 8,
    })
    assert r2.status_code == 409


def test_bad_shift_time_format(client):
    r = client.post("/hr2/shifts", json={
        "code": "BADT", "name": "Bad Time", "start_time": "25:99",
        "end_time": "18:00", "standard_hours": 8, "overtime_after": 8,
    })
    assert r.status_code == 400


def test_mark_attendance_basic_and_dup(client):
    today = datetime.now(timezone.utc).date().isoformat()
    payload = {
        "employee_name": "PYTEST Worker A",
        "date": today, "project_code": "PRJ-PYT",
        "shift_code": "GEN", "in_time": "09:00", "out_time": "19:30",
        "status": "present", "source": "manual",
    }
    r = client.post("/hr2/attendance", json=payload)
    assert r.status_code == 200, r.text
    row = r.json()
    # 10.5 hours elapsed minus 60 min break = 9.5 total, OT after 8h = 1.5
    assert row["total_hours"] == 9.5
    assert row["overtime_hours"] == 1.5
    assert row["status"] == "present"
    assert row["approval_status"] == "pending"
    # Duplicate must 409
    r2 = client.post("/hr2/attendance", json=payload)
    assert r2.status_code == 409


def test_future_date_blocked(client):
    future = (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
    r = client.post("/hr2/attendance", json={
        "employee_name": "Future X", "date": future,
        "status": "present", "source": "manual",
    })
    assert r.status_code == 400


def test_night_shift_hours(client):
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    r = client.post("/hr2/attendance", json={
        "employee_name": "PYTEST Night Worker",
        "date": yesterday, "project_code": "PRJ-NIGHT",
        "shift_code": "NIGHT", "in_time": "22:00", "out_time": "08:00",
        "status": "present", "source": "manual",
    })
    assert r.status_code == 200, r.text
    row = r.json()
    # 10 hours elapsed minus 30 min break = 9.5
    assert row["total_hours"] == 9.5


def test_attendance_lock_and_block(client):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    # Lock
    r = client.post("/hr2/attendance/lock", json={
        "project_code": "PRJ-LOCKTEST", "month": month, "reason": "PYTEST"
    })
    assert r.status_code == 200, r.text
    # Try to create attendance — must be blocked
    today = datetime.now(timezone.utc).date().isoformat()
    r2 = client.post("/hr2/attendance", json={
        "employee_name": "Lock Try", "date": today,
        "project_code": "PRJ-LOCKTEST", "status": "present", "source": "manual",
    })
    assert r2.status_code == 400
    assert "LOCKED" in r2.json().get("detail", "")
    # Unlock
    r3 = client.post("/hr2/attendance/unlock", json={
        "project_code": "PRJ-LOCKTEST", "month": month,
    })
    assert r3.status_code == 200
    # Now mark OK
    r4 = client.post("/hr2/attendance", json={
        "employee_name": "After Unlock", "date": today,
        "project_code": "PRJ-LOCKTEST", "shift_code": "GEN",
        "in_time": "09:00", "out_time": "18:00",
        "status": "present", "source": "manual",
    })
    assert r4.status_code == 200


def test_attendance_bulk_approve(client):
    today = datetime.now(timezone.utc).date().isoformat()
    # Create 2 pending rows
    ids = []
    for n in ("APP A", "APP B"):
        r = client.post("/hr2/attendance", json={
            "employee_name": f"PYTEST {n}", "date": today,
            "project_code": f"PRJ-APV-{n[-1]}",
            "shift_code": "GEN", "in_time": "09:00", "out_time": "18:00",
            "status": "present", "source": "manual",
        })
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    # Bulk approve
    r2 = client.post("/hr2/attendance/approve",
                     json={"ids": ids, "decision": "approve", "remarks": "ok"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["updated"] == 2


def test_attendance_register_filter(client):
    today = datetime.now(timezone.utc).date().isoformat()
    r = client.get(f"/hr2/attendance/register?from_date={today}&to_date={today}")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1


def test_attendance_monthly_summary(client):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    r = client.get(f"/hr2/attendance/monthly-summary?month={month}")
    assert r.status_code == 200
    j = r.json()
    assert j["month"] == month
    assert isinstance(j["rows"], list)


def test_overtime_flow(client):
    # Create OT
    r = client.post("/hr2/overtime", json={
        "employee_name": "PYTEST OT Emp",
        "project_code": "PRJ-OT",
        "overtime_date": datetime.now(timezone.utc).date().isoformat(),
        "normal_hours": 8, "overtime_hours": 3.5,
        "overtime_rate": 200, "reason": "Critical bug fix",
    })
    assert r.status_code == 200, r.text
    ot = r.json()
    assert ot["overtime_amount"] == 700.0
    assert ot["status"] == "pending"
    assert ot["request_no"].startswith("OT-")
    oid = ot["id"]
    # Approve PM
    r2 = client.post(f"/hr2/overtime/{oid}/approve-pm", json={"remarks": "ok pm"})
    assert r2.status_code == 200
    assert r2.json()["pm_status"] == "approved"
    assert r2.json()["status"] == "hr_pending"
    # Approve HR
    r3 = client.post(f"/hr2/overtime/{oid}/approve-hr", json={"remarks": "approved"})
    assert r3.status_code == 200
    assert r3.json()["hr_status"] == "approved"
    assert r3.json()["status"] == "approved"


def test_overtime_hr_before_pm_rejected(client):
    r = client.post("/hr2/overtime", json={
        "employee_name": "PYTEST OT-HR First",
        "project_code": "PRJ-OT",
        "overtime_date": datetime.now(timezone.utc).date().isoformat(),
        "normal_hours": 8, "overtime_hours": 2, "overtime_rate": 100, "reason": "Test",
    })
    oid = r.json()["id"]
    r2 = client.post(f"/hr2/overtime/{oid}/approve-hr", json={})
    assert r2.status_code == 400
    assert "PM" in r2.json().get("detail", "")


def test_overtime_zero_hours_blocked(client):
    r = client.post("/hr2/overtime", json={
        "employee_name": "Zero OT", "overtime_date": "2026-06-01",
        "overtime_hours": 0, "reason": "nope",
    })
    assert r.status_code == 400


def test_overtime_project_cost(client):
    r = client.get("/hr2/overtime/project-cost?project_code=PRJ-OT")
    assert r.status_code == 200
    j = r.json()
    assert j["project_code"] == "PRJ-OT"
    assert j["total_hours"] > 0
    assert j["total_amount"] > 0


def test_compliance_alerts(client):
    r = client.get("/hr2/compliance-alerts?days=30")
    assert r.status_code == 200
    j = r.json()
    assert "cards" in j
    keys = {c["key"] for c in j["cards"]}
    expected = {"missing_documents", "expiring_documents", "medical_expired",
                "medical_expiring", "training_expiring", "rope_expiring",
                "police_pending", "pf_missing", "esic_missing", "bank_missing",
                "pan_missing", "inactive_deployed", "att_pending",
                "ot_pending", "leave_pending"}
    assert expected.issubset(keys)


def test_medical_fitness_expiry(client):
    r = client.get("/hr2/medical-fitness-expiry?days=30")
    assert r.status_code == 200
    j = r.json()
    assert "expired" in j and "expiring" in j


def test_training_expiry(client):
    r = client.get("/hr2/training-expiry?days=30")
    assert r.status_code == 200
    j = r.json()
    assert "expired" in j and "expiring" in j


def test_safety_readiness(client):
    r = client.get("/hr2/safety-readiness")
    assert r.status_code == 200
    j = r.json()
    assert "ready_count" in j and "blocked_count" in j
    assert "ready" in j and "blocked" in j


def test_hr2_dashboard(client):
    r = client.get("/hr2/dashboard")
    assert r.status_code == 200
    j = r.json()
    for k in ("active_shifts", "attendance_today",
              "attendance_pending_approval", "overtime_pending", "leave_pending"):
        assert k in j


def test_audit_log_recorded(client):
    # Make a fresh attendance + edit and ensure the audit log captured it
    today = datetime.now(timezone.utc).date().isoformat()
    r = client.post("/hr2/attendance", json={
        "employee_name": "PYTEST Audit Emp", "date": today,
        "project_code": "PRJ-AUDIT", "shift_code": "GEN",
        "in_time": "09:00", "out_time": "18:00",
        "status": "present", "source": "manual",
    })
    aid = r.json()["id"]
    # Edit
    r2 = client.put(f"/hr2/attendance/{aid}",
                    json={"out_time": "19:00", "remarks": "edited"})
    assert r2.status_code == 200
    # Read audit
    r3 = client.get(f"/hr2/attendance/{aid}/audit")
    assert r3.status_code == 200
    rows = r3.json()
    assert len(rows) >= 2  # create + update
    actions = {x["action"] for x in rows}
    assert "create" in actions
    assert "update" in actions


def test_leave_types_extended(client):
    r = client.get("/hr/leave-types")
    assert r.status_code == 200
    codes = {x["code"] for x in r.json()}
    assert {"LWP", "WO", "HOL", "SITE", "EMG"}.issubset(codes)
