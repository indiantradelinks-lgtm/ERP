"""Iter 90 regression: PM/PC dropdowns sourced from HRMS by designation."""
import os
import secrets

import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
PM_DESIG = "Projects & Operations"
PC_DESIG = "Data Entry Operator"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return s


def test_pm_dropdown_filters_by_projects_and_ops(admin_session):
    # Find an existing PM-role user → seed a matching employee with PM designation
    users = admin_session.get(f"{API_URL}/api/auth/users", timeout=10).json()
    pm_user = next((u for u in users if u.get("role") == "project_manager" and u.get("name")), None)
    if not pm_user:
        pytest.skip("no PM user seeded for linking test")
    emp_body = {
        "name": pm_user["name"],
        "designation": PM_DESIG,
        "employee_id": f"TEST_PM_{secrets.token_hex(2).upper()}",
        "department": "operations",
    }
    r = admin_session.post(f"{API_URL}/api/employees", json=emp_body, timeout=10)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    try:
        data = admin_session.get(f"{API_URL}/api/ops/assignable-users", timeout=10).json()
        pm_opts = data["project_manager"]
        # Only employees with PM_DESIG must appear (case-insensitive match)
        assert pm_opts, "PM dropdown must include at least the seeded option"
        for o in pm_opts:
            assert (o.get("designation") or "").strip().lower() == PM_DESIG.lower(), o
        # Linked user wins the id slot
        linked = next((o for o in pm_opts if o["name"] == pm_user["name"]), None)
        assert linked is not None
        assert linked["linked_user_id"] == pm_user["id"]
        assert linked["id"] == pm_user["id"]
    finally:
        admin_session.delete(f"{API_URL}/api/employees/{eid}", timeout=10)


def test_pc_dropdown_filters_by_data_entry_operator(admin_session):
    name = f"DEO_{secrets.token_hex(3)}"
    emp_body = {
        "name": name,
        "designation": PC_DESIG,
        "employee_id": f"TEST_DEO_{secrets.token_hex(2).upper()}",
        "department": "operations",
    }
    r = admin_session.post(f"{API_URL}/api/employees", json=emp_body, timeout=10)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    try:
        data = admin_session.get(f"{API_URL}/api/ops/assignable-users", timeout=10).json()
        pc_opts = data["project_coordinator"]
        assert pc_opts, "PC dropdown must include at least the seeded option"
        for o in pc_opts:
            assert (o.get("designation") or "").strip().lower() == PC_DESIG.lower(), o
        # No-link case: id falls back to employee_record_id
        new_opt = next((o for o in pc_opts if o["name"] == name), None)
        assert new_opt is not None
        assert new_opt.get("linked_user_id") is None
        assert new_opt["id"] == new_opt["employee_record_id"] == eid
    finally:
        admin_session.delete(f"{API_URL}/api/employees/{eid}", timeout=10)


def test_other_designations_excluded(admin_session):
    """An employee with an unrelated designation must NOT appear in either dropdown."""
    name = f"OtherDesig_{secrets.token_hex(3)}"
    r = admin_session.post(f"{API_URL}/api/employees", json={
        "name": name, "designation": "Welder", "employee_id": f"TEST_W_{secrets.token_hex(2).upper()}",
        "department": "operations",
    }, timeout=10)
    assert r.status_code == 200
    eid = r.json()["id"]
    try:
        data = admin_session.get(f"{API_URL}/api/ops/assignable-users", timeout=10).json()
        assert not any(o["name"] == name for o in data["project_manager"]), "Welder must NOT appear in PM"
        assert not any(o["name"] == name for o in data["project_coordinator"]), "Welder must NOT appear in PC"
    finally:
        admin_session.delete(f"{API_URL}/api/employees/{eid}", timeout=10)
