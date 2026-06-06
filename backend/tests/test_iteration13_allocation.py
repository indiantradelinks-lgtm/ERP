"""Iteration 13 — Employee & Project Allocation backend tests.

Auth uses httpOnly cookies; we use requests.Session per user.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def eng():
    try:
        return _login(SITE_ENG)
    except AssertionError:
        pytest.skip("site engineer not available")


@pytest.fixture(scope="module")
def created():
    return {"employees": [], "deployments": []}


def U(p): return f"{BASE_URL}{p}"


# ---------------- Employees: multi-dept + auto-number ----------------
class TestEmployeesMultiDept:
    def test_create_employee_with_multi_dept(self, admin, created):
        payload = {
            "name": "TEST_Alloc Multi", "designation": "Engineer",
            "departments": ["Operations", "HSE"], "allow_multi_dept": True,
            "status": "active",
        }
        r = admin.post(U("/api/employees"), json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d["departments"] == ["Operations", "HSE"]
        assert d["department"] == "Operations"
        assert re.match(r"^EMP-\d{4}-\d{4}$", d["employee_id"]), d.get("employee_id")
        assert d["allow_multi_dept"] is True
        created["employees"].append(d["id"])
        g = admin.get(U(f"/api/employees/{d['id']}"), timeout=10)
        assert g.status_code == 200
        assert g.json()["departments"] == ["Operations", "HSE"]

    def test_create_employee_with_single_dept_string(self, admin, created):
        payload = {"name": "TEST_Alloc Single", "department": "Finance", "status": "active"}
        r = admin.post(U("/api/employees"), json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d["departments"] == ["Finance"]
        assert d["department"] == "Finance"
        assert d.get("allow_multi_dept") is False
        created["employees"].append(d["id"])

    def test_update_blocks_multi_when_not_approved(self, admin, created):
        r = admin.post(U("/api/employees"),
                       json={"name": "TEST_Alloc NoMulti", "department": "Stores", "status": "active"},
                       timeout=15)
        assert r.status_code in (200, 201)
        emp_id = r.json()["id"]
        created["employees"].append(emp_id)
        upd = admin.put(U(f"/api/employees/{emp_id}"),
                        json={"departments": ["Stores", "HR"]}, timeout=15)
        assert upd.status_code == 400
        assert "multi-department" in upd.text.lower() or "not approved" in upd.text.lower()


# ---------------- move-department + history ----------------
class TestMoveDepartment:
    def test_move_requires_departments(self, admin, created):
        r = admin.post(U("/api/employees"),
                       json={"name": "TEST_Alloc Move", "department": "HR", "status": "active",
                             "allow_multi_dept": True}, timeout=15)
        emp_id = r.json()["id"]
        created["employees"].append(emp_id)
        bad = admin.post(U(f"/api/employees/{emp_id}/move-department"),
                         json={"departments": []}, timeout=15)
        assert bad.status_code == 400
        ok = admin.post(U(f"/api/employees/{emp_id}/move-department"),
                        json={"departments": ["Procurement", "Stores"], "note": "rebalance"}, timeout=15)
        assert ok.status_code == 200
        assert ok.json()["departments"] == ["Procurement", "Stores"]
        hist = admin.get(U("/api/allocation/history"),
                         params={"employee_id": emp_id}, timeout=15)
        assert hist.status_code == 200
        rows = hist.json()
        assert any(rr.get("action") == "department_move" for rr in rows), rows


# ---------------- Deployments + auto-number + history + end ----------------
class TestDeployments:
    def test_create_deployment_autonumber_and_end_with_history(self, admin, created):
        emp = admin.post(U("/api/employees"),
                         json={"name": "TEST_Alloc Deployable", "department": "Operations", "status": "active"},
                         timeout=15).json()
        created["employees"].append(emp["id"])
        projs = admin.get(U("/api/projects"), timeout=15).json()
        if projs:
            proj_code = projs[0].get("code") or projs[0].get("name")
        else:
            pj = admin.post(U("/api/projects"),
                            json={"name": "TEST Alloc Project", "code": "TEST-ALLOC-01", "status": "active"},
                            timeout=15).json()
            proj_code = pj.get("code") or pj.get("name")
        payload = {
            "employee_id": emp["id"], "employee": emp["name"],
            "project": proj_code, "site_role": "engineer", "shift": "day",
            "start_date": "2026-01-01", "status": "active",
        }
        r = admin.post(U("/api/deployments"), json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        dep = r.json()
        assert re.match(r"^DEP-\d{4}-\d{4}$", dep.get("deployment_no", "")), dep
        created["deployments"].append(dep["id"])
        hist = admin.get(U("/api/allocation/history"),
                         params={"employee_id": emp["id"]}, timeout=15).json()
        assert any(rr.get("action") == "deployment_start" for rr in hist)
        end = admin.post(U(f"/api/deployments/{dep['id']}/end"),
                         json={"note": "test end"}, timeout=15)
        assert end.status_code == 200
        ended = end.json()
        assert ended["status"] == "completed"
        assert ended.get("end_date")
        hist2 = admin.get(U("/api/allocation/history"),
                          params={"employee_id": emp["id"]}, timeout=15).json()
        assert any(rr.get("action") == "deployment_end" for rr in hist2)


# ---------------- Allocation reports ----------------
class TestAllocationReports:
    def test_idle_employees(self, admin):
        r = admin.get(U("/api/allocation/idle-employees"), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_by_department(self, admin):
        r = admin.get(U("/api/allocation/by-department"), timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            assert "department" in rows[0] and "count" in rows[0]

    def test_by_project(self, admin):
        r = admin.get(U("/api/allocation/by-project"), timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            assert "project" in rows[0] and "count" in rows[0]

    def test_history_sorted_desc(self, admin):
        r = admin.get(U("/api/allocation/history"), timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if len(rows) >= 2:
            assert rows[0]["at"] >= rows[1]["at"]


# ---------------- /me/scope ----------------
class TestMeScope:
    def test_admin_scope_global(self, admin):
        r = admin.get(U("/api/me/scope"), timeout=15)
        assert r.status_code == 200
        s = r.json()
        assert s["role"] == "super_admin"
        assert s["global"] is True
        assert isinstance(s["departments"], list)
        assert isinstance(s["active_projects"], list)

    def test_engineer_scope_not_global(self, eng):
        r = eng.get(U("/api/me/scope"), timeout=15)
        assert r.status_code == 200
        s = r.json()
        assert s["role"] == "site_engineer"
        assert s["global"] is False
        assert isinstance(s["active_projects"], list)


# ---------------- Project manpower ----------------
class TestProjectManpower:
    def test_manpower_404_for_unknown(self, admin):
        r = admin.get(U("/api/projects/__NO_SUCH__/manpower"), timeout=15)
        assert r.status_code == 404

    def test_manpower_for_existing_project(self, admin):
        projs = admin.get(U("/api/projects"), timeout=15).json()
        if not projs:
            pytest.skip("no projects")
        code = projs[0].get("code") or projs[0].get("name")
        r = admin.get(U(f"/api/projects/{code}/manpower"), timeout=15)
        assert r.status_code == 200, r.text
        payload = r.json()
        assert "project" in payload and "kpis" in payload
        k = payload["kpis"]
        for key in ("total_deployed", "present_today", "absent_today", "distinct_depts"):
            assert key in k
        assert isinstance(payload["by_role"], list)
        assert isinstance(payload["by_department"], list)
        assert isinstance(payload["deployments"], list)


# ---------------- RBAC visibility filter ----------------
class TestVisibility:
    def test_engineer_deployments_scoped(self, admin, eng):
        admin_rows = admin.get(U("/api/deployments"), timeout=15).json()
        eng_rows = eng.get(U("/api/deployments"), timeout=15).json()
        assert isinstance(eng_rows, list)
        assert len(eng_rows) <= len(admin_rows)
        scope = eng.get(U("/api/me/scope"), timeout=15).json()
        ap = set(scope.get("active_projects") or [])
        for d in eng_rows:
            assert d.get("project") in ap or not ap

    def test_engineer_safety_reports_scoped(self, admin, eng):
        admin_rows = admin.get(U("/api/safety-reports"), timeout=15).json()
        eng_rows = eng.get(U("/api/safety-reports"), timeout=15).json()
        assert isinstance(eng_rows, list)
        assert len(eng_rows) <= len(admin_rows)


# ---------------- Cleanup ----------------
def test_zzz_cleanup(admin, created):
    for eid in created["employees"]:
        admin.delete(U(f"/api/employees/{eid}"), timeout=10)
    for did in created["deployments"]:
        admin.delete(U(f"/api/deployments/{did}"), timeout=10)
