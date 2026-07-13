"""Iteration 14 — Phase 3 approval workflow on dept-moves + deployments + new reports."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Last-resort fallback to local
    BASE_URL = "http://localhost:8001"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345", "name": "Test PM",
      "role": "project_manager", "department": "Operations"}


def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(s, creds):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": creds["email"], "password": creds["password"]})
    return r


@pytest.fixture(scope="module")
def admin_sess():
    s = _session()
    r = _login(s, ADMIN)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def pm_sess(admin_sess):
    s = _session()
    r = _login(s, PM)
    if r.status_code != 200:
        # Register via super_admin
        reg = admin_sess.post(f"{BASE_URL}/api/auth/register", json={
            "email": PM["email"], "name": PM["name"], "password": PM["password"],
            "role": PM["role"], "department": PM["department"],
        })
        assert reg.status_code in (200, 201), f"PM register failed: {reg.status_code} {reg.text}"
        r = _login(s, PM)
        assert r.status_code == 200, f"PM login failed after register: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def test_employee(admin_sess):
    """Create a TEST_ employee (multi-dept) we can move around."""
    payload = {
        "name": "TEST_Phase3 Employee",
        "designation": "Mason",
        "department": "Operations",
        "departments": ["Operations"],
        "allow_multi_dept": True,
        "joining_date": "2024-01-01",
        "status": "active",
    }
    r = admin_sess.post(f"{BASE_URL}/api/employees", json=payload)
    assert r.status_code in (200, 201), f"emp create: {r.status_code} {r.text}"
    emp = r.json()
    yield emp
    admin_sess.delete(f"{BASE_URL}/api/employees/{emp['id']}")


# ============ APPROVAL CHAIN TEMPLATES ============
def test_approval_chains_include_phase3(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/approvals-config/chains")
    assert r.status_code == 200
    chains = r.json()
    assert "department_move" in chains, "department_move chain missing"
    assert "deployment" in chains, "deployment chain missing"
    dm = chains["department_move"]
    assert [s["role"] for s in dm] == ["dept_head", "hr_executive"]
    dep = chains["deployment"]
    assert [s["role"] for s in dep] == ["project_manager", "dept_head"]


# ============ DEPARTMENT MOVE — DIRECT (super_admin) ============
def test_move_department_super_admin_immediate(admin_sess, test_employee):
    r = admin_sess.post(
        f"{BASE_URL}/api/employees/{test_employee['id']}/move-department",
        json={"departments": ["HSE"], "note": "direct admin move"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("pending_approval") is not True
    assert "HSE" in (body.get("departments") or [])
    # Verify history written
    h = admin_sess.get(f"{BASE_URL}/api/allocation/history",
                       params={"employee_id": test_employee["id"], "action": "department_move"})
    assert h.status_code == 200
    assert any(row.get("action") == "department_move" for row in h.json())


# ============ DEPARTMENT MOVE — PM raises approval ============
def test_move_department_pm_creates_approval(pm_sess, admin_sess, test_employee):
    # First reset emp back to Operations as admin
    admin_sess.post(f"{BASE_URL}/api/employees/{test_employee['id']}/move-department",
                    json={"departments": ["Operations"]})
    r = pm_sess.post(
        f"{BASE_URL}/api/employees/{test_employee['id']}/move-department",
        json={"departments": ["Finance"], "note": "PM requested"},
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body.get("pending_approval") is True, f"Expected pending_approval, got: {body}"
    assert body.get("approval_id"), "approval_id missing"
    approval_id = body["approval_id"]
    # Verify employee NOT mutated
    emp_r = admin_sess.get(f"{BASE_URL}/api/employees/{test_employee['id']}")
    assert emp_r.status_code == 200
    cur_depts = emp_r.json().get("departments") or []
    assert "Finance" not in cur_depts, f"Employee was mutated prematurely: {cur_depts}"
    # Verify approval doc shape
    inbox_r = admin_sess.get(f"{BASE_URL}/api/approvals/inbox/mine")
    assert inbox_r.status_code == 200
    found = next((a for a in inbox_r.json() if a.get("id") == approval_id), None)
    assert found, "approval doc not visible in super_admin inbox"
    assert found["type"] == "department_move"
    assert found["record_id"] == test_employee["id"]
    meta = found.get("metadata") or {}
    assert meta.get("employee_id") == test_employee["id"]
    assert meta.get("target_departments") == ["Finance"]
    assert meta.get("previous_departments") == ["Operations"]
    # Save for next test
    pytest.dept_move_approval_id = approval_id


def test_dept_move_final_approval_mutates_and_writes_history(admin_sess, test_employee):
    aid = getattr(pytest, "dept_move_approval_id", None)
    assert aid, "previous test must seed approval"
    # Step 1 (dept_head) – super_admin can act on any step
    r1 = admin_sess.post(f"{BASE_URL}/api/approvals/{aid}/action",
                         json={"action": "approve", "comment": "ok step1"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "in_progress"
    # Step 2 (hr_executive) – final
    r2 = admin_sess.post(f"{BASE_URL}/api/approvals/{aid}/action",
                         json={"action": "approve", "comment": "ok final"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "approved"
    # Verify mutation
    emp_r = admin_sess.get(f"{BASE_URL}/api/employees/{test_employee['id']}")
    assert emp_r.status_code == 200
    assert "Finance" in (emp_r.json().get("departments") or [])
    # Verify a history row exists matching the approved target depts
    h = admin_sess.get(f"{BASE_URL}/api/allocation/history",
                       params={"employee_id": test_employee["id"], "action": "department_move"}).json()
    rec = next((row for row in h if row.get("to") == ["Finance"]), None)
    assert rec, f"history not written for Finance move; rows={h}"
    # Note can be the user-supplied one OR the fallback 'via approval'.
    assert (rec.get("note") or "") in ("PM requested", "via approval"), \
        f"unexpected note: {rec.get('note')!r}"


def test_dept_move_rejection_leaves_employee_unchanged(pm_sess, admin_sess, test_employee):
    # Reset
    admin_sess.post(f"{BASE_URL}/api/employees/{test_employee['id']}/move-department",
                    json={"departments": ["Operations"]})
    r = pm_sess.post(f"{BASE_URL}/api/employees/{test_employee['id']}/move-department",
                     json={"departments": ["IT"]})
    assert r.status_code == 200 and r.json().get("pending_approval")
    aid = r.json()["approval_id"]
    rej = admin_sess.post(f"{BASE_URL}/api/approvals/{aid}/action",
                         json={"action": "reject", "comment": "no"})
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"
    emp_r = admin_sess.get(f"{BASE_URL}/api/employees/{test_employee['id']}")
    assert "IT" not in (emp_r.json().get("departments") or []), "employee mutated on rejection!"


# ============ DEPLOYMENTS ============
def _make_deployment_payload(emp):
    return {
        "employee": emp["name"],
        "employee_id": emp["id"],
        "project": "TEST_PROJ",
        "site_role": "mason",
        "shift": "day",
        "start_date": "2026-01-15",
        "status": "active",  # caller tries to bypass, server must override
    }


def test_deployment_admin_immediate_active(admin_sess, test_employee):
    payload = _make_deployment_payload(test_employee)
    r = admin_sess.post(f"{BASE_URL}/api/deployments", json=payload)
    assert r.status_code in (200, 201)
    dep = r.json()
    assert dep["status"] == "active", f"admin deployment should be live, got {dep['status']}"
    # history row written
    h = admin_sess.get(f"{BASE_URL}/api/allocation/history",
                       params={"employee_id": test_employee["id"], "action": "deployment_start"})
    assert any(row.get("project") == "TEST_PROJ" for row in h.json())
    # cleanup
    admin_sess.delete(f"{BASE_URL}/api/deployments/{dep['id']}")


def test_deployment_pm_creates_approval(pm_sess, admin_sess, test_employee):
    payload = _make_deployment_payload(test_employee)
    payload["project"] = "TEST_PROJ_PM"
    r = pm_sess.post(f"{BASE_URL}/api/deployments", json=payload)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
    dep = r.json()
    assert dep["status"] == "pending_approval", \
        f"expected pending_approval, got {dep.get('status')}"
    pytest.pending_dep_id = dep["id"]
    # No deployment_start history yet
    h = admin_sess.get(f"{BASE_URL}/api/allocation/history",
                       params={"employee_id": test_employee["id"], "action": "deployment_start"})
    assert not any(row.get("project") == "TEST_PROJ_PM" for row in h.json()), \
        "deployment_start history written before approval"
    # Companion approval exists
    time.sleep(0.3)
    inbox = admin_sess.get(f"{BASE_URL}/api/approvals/inbox/mine").json()
    found = next((a for a in inbox if a.get("type") == "deployment"
                  and a.get("record_id") == dep["id"]), None)
    assert found, "deployment approval doc not found"
    pytest.dep_approval_id = found["id"]


def test_deployment_approval_activates_and_writes_history(admin_sess, test_employee):
    aid = getattr(pytest, "dep_approval_id", None)
    dep_id = getattr(pytest, "pending_dep_id", None)
    assert aid and dep_id
    # 2-step chain
    admin_sess.post(f"{BASE_URL}/api/approvals/{aid}/action", json={"action": "approve"})
    r = admin_sess.post(f"{BASE_URL}/api/approvals/{aid}/action", json={"action": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    # deployment now active
    deps = admin_sess.get(f"{BASE_URL}/api/deployments").json()
    dep = next((d for d in deps if d.get("id") == dep_id), None)
    assert dep, "deployment missing"
    assert dep["status"] == "active", f"expected active, got {dep['status']}"
    # deployment_start history exists with 'via approval'
    h = admin_sess.get(f"{BASE_URL}/api/allocation/history",
                       params={"employee_id": test_employee["id"], "action": "deployment_start"}).json()
    rec = next((row for row in h if row.get("project") == "TEST_PROJ_PM"), None)
    assert rec, "deployment_start history not written after approval"
    assert "approval" in (rec.get("note") or "")
    # cleanup
    admin_sess.delete(f"{BASE_URL}/api/deployments/{dep_id}")


def test_deployment_rejection_marks_withdrawn(pm_sess, admin_sess, test_employee):
    payload = _make_deployment_payload(test_employee)
    payload["project"] = "TEST_PROJ_REJECT"
    r = pm_sess.post(f"{BASE_URL}/api/deployments", json=payload)
    assert r.status_code in (200, 201)
    dep = r.json()
    assert dep["status"] == "pending_approval"
    time.sleep(0.3)
    inbox = admin_sess.get(f"{BASE_URL}/api/approvals/inbox/mine").json()
    appr = next((a for a in inbox if a.get("type") == "deployment" and a.get("record_id") == dep["id"]), None)
    assert appr
    rej = admin_sess.post(f"{BASE_URL}/api/approvals/{appr['id']}/action",
                          json={"action": "reject", "comment": "denied"})
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    deps = admin_sess.get(f"{BASE_URL}/api/deployments").json()
    d = next((x for x in deps if x.get("id") == dep["id"]), None)
    assert d and d["status"] == "withdrawn", f"expected withdrawn, got {d and d.get('status')}"
    admin_sess.delete(f"{BASE_URL}/api/deployments/{dep['id']}")


# ============ REPORTS ============
def test_resource_utilization(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/allocation/resource-utilization")
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body and "rows" in body
    s = body["summary"]
    for k in ("avg_utilization", "deployed_employees", "total_employees"):
        assert k in s, f"summary missing {k}"
    if body["rows"]:
        row = body["rows"][0]
        for k in ("deployed_days", "available_days", "utilization_pct"):
            assert k in row, f"row missing {k}"


def test_site_attendance(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/allocation/site-attendance")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    if body:
        row = body[0]
        for k in ("project", "present", "absent", "unknown", "total"):
            assert k in row


def test_transfer_history(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/allocation/transfer-history")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    actions = {row.get("action") for row in rows}
    # All actions should be in expected set
    assert actions.issubset({"department_move", "deployment_start", "deployment_end"})
    # Sorted desc by at
    ats = [row.get("at") for row in rows if row.get("at")]
    assert ats == sorted(ats, reverse=True), "transfer-history not sorted desc"
    # since filter
    r2 = admin_sess.get(f"{BASE_URL}/api/allocation/transfer-history",
                        params={"since": "2099-01-01"})
    assert r2.status_code == 200
    assert r2.json() == []


# ============ REGRESSION — iteration_13 endpoints ============
def test_regression_idle_employees(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/allocation/idle-employees")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_regression_by_department(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/allocation/by-department")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    if rows:
        assert "department" in rows[0] and "count" in rows[0]


def test_regression_by_project(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/allocation/by-project")
    assert r.status_code == 200


def test_zzz_cleanup_stray_deployments(admin_sess):
    """Belt-and-braces: delete any leftover TEST_PROJ deployments."""
    deps = admin_sess.get(f"{BASE_URL}/api/deployments").json()
    for d in deps:
        if str(d.get("project", "")).startswith("TEST_PROJ"):
            admin_sess.delete(f"{BASE_URL}/api/deployments/{d['id']}")
