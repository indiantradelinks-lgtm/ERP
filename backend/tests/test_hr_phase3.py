"""HR Phase 3 tests — Manpower Requirements, Availability, Deployment, Mobilization, Demobilization, Replacement."""
from __future__ import annotations

import os
from datetime import datetime, timezone

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

    class C:
        def __init__(self, sess): self._s = sess
        def post(self, url, json=None): return self._s.post(f"{BASE}{url}", json=json, timeout=30)
        def get(self, url):              return self._s.get(f"{BASE}{url}", timeout=30)
        def put(self, url, json=None):   return self._s.put(f"{BASE}{url}", json=json, timeout=30)

    yield C(s)
    s.close()


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Manpower Requirements
# ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def requirement(client):
    r = client.post("/hr3/manpower-requirements", json={
        "project_code": "PRJ-PYT-HR3",
        "client": "PYT Client",
        "site_location": "Mumbai",
        "service_type": "scaffolding",
        "priority": "high",
        "expected_start_date": "2026-07-01",
        "expected_duration_days": 60,
        "billing_basis": "day",
        "lines": [
            {"skill": "scaffolder", "required_headcount": 10, "required_date": "2026-07-01"},
            {"skill": "helper", "required_headcount": 5, "required_date": "2026-07-01"},
        ],
        "remarks": "PYTEST run",
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_requirement_created(requirement):
    assert requirement["requirement_no"].startswith("MR-")
    assert requirement["total_required"] == 15
    assert requirement["approval_status"] == "pending"
    assert len(requirement["lines"]) == 2


def test_requirement_missing_project(client):
    r = client.post("/hr3/manpower-requirements", json={
        "project_code": "",
        "lines": [{"skill": "x", "required_headcount": 1}],
    })
    assert r.status_code == 400


def test_requirement_bad_service(client):
    r = client.post("/hr3/manpower-requirements", json={
        "project_code": "PRJ-A",
        "service_type": "nuclear",
        "lines": [{"skill": "x", "required_headcount": 1}],
    })
    assert r.status_code == 400


def test_requirement_no_lines(client):
    r = client.post("/hr3/manpower-requirements", json={"project_code": "PRJ-A", "lines": []})
    assert r.status_code == 400


def test_requirement_list_and_get(client, requirement):
    r = client.get("/hr3/manpower-requirements")
    assert r.status_code == 200
    assert any(x["id"] == requirement["id"] for x in r.json())
    r2 = client.get(f"/hr3/manpower-requirements/{requirement['id']}")
    assert r2.status_code == 200
    assert r2.json()["requirement_no"] == requirement["requirement_no"]


def test_requirement_approve(client, requirement):
    r = client.post(f"/hr3/manpower-requirements/{requirement['id']}/approve",
                    json={"decision": "approve", "remarks": "approved"})
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == "approved"


def test_requirement_refresh(client, requirement):
    r = client.post(f"/hr3/manpower-requirements/{requirement['id']}/refresh")
    assert r.status_code == 200
    body = r.json()
    assert "total_available" in body
    assert "total_shortage" in body


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Availability
# ──────────────────────────────────────────────────────────────────────────────
def test_availability_endpoint(client):
    r = client.get("/hr3/availability")
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j and isinstance(j["rows"], list)


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Deployment validations
# ──────────────────────────────────────────────────────────────────────────────
def test_deployment_missing_project(client):
    r = client.post("/hr3/deployments", json={
        "person_type": "employee", "person_id": "x",
        "project_code": "", "deployment_start_date": "2026-07-01",
    })
    assert r.status_code in (400, 422)


def test_deployment_unknown_person(client):
    r = client.post("/hr3/deployments", json={
        "person_type": "employee", "person_id": "nonexistent",
        "project_code": "PRJ-X", "deployment_start_date": "2026-07-01",
    })
    assert r.status_code == 404


@pytest.fixture(scope="module")
def test_employee(client):
    """Create a fully compliant test employee (non-hazardous trade)."""
    payload = {
        "name": "PYTEST HR3 Emp",
        "department": "Operations",
        "designation": "Site Supervisor",
        "skill_name": "supervisor",
        "status": "active",
        "documents_verified": True,
        "safety_induction": True,
        "medical_fitness": True,
        "medical_fitness_valid_till": "2099-12-31",
        "certifications": [],
    }
    r = client.post("/employees", json=payload)
    if r.status_code not in (200, 201):
        pytest.skip(f"employees POST not available: {r.status_code} {r.text[:80]}")
    return r.json()


def test_deployment_full_flow(client, test_employee):
    eid = test_employee["id"]
    # Create deployment
    r = client.post("/hr3/deployments", json={
        "person_type": "employee", "person_id": eid,
        "project_code": "PRJ-PYT-DEP",
        "client": "Test", "site_location": "Site-1",
        "service_type": "manpower",
        "skill": "supervisor",
        "deployment_start_date": "2026-07-01",
        "expected_end_date": "2026-09-30",
        "ppe_required": True, "tool_required": True,
        "remarks": "PYTEST deployment",
    })
    assert r.status_code == 200, r.text
    dep = r.json()
    assert dep["deployment_no"].startswith("DEP-")
    assert dep["status"] == "planned"
    assert dep["document_status"] == "ok"
    assert dep["medical_fitness_status"] == "ok"
    assert dep["safety_induction_status"] == "ok"


def test_duplicate_deployment_blocked(client, test_employee):
    eid = test_employee["id"]
    # First deploy
    client.post("/hr3/deployments", json={
        "person_type": "employee", "person_id": eid,
        "project_code": "PRJ-PYT-DUP1",
        "deployment_start_date": "2026-07-01",
    })
    # Move to active so multi-site guard kicks in
    deps = client.get("/hr3/deployment-calendar?from_date=2026-01-01&to_date=2026-12-31").json()
    active_dep = next((d for d in deps if d.get("project_code") == "PRJ-PYT-DUP1"), None)
    if active_dep:
        # find id via deployments collection (use direct GET via crud) — use HR3 audit alternative
        pass
    # Second deploy without allow_multi_site → must 400
    r = client.post("/hr3/deployments", json={
        "person_type": "employee", "person_id": eid,
        "project_code": "PRJ-PYT-DUP2",
        "deployment_start_date": "2026-08-01",
    })
    assert r.status_code == 400, r.text
    assert "Already deployed" in r.json().get("detail", "")


def test_deployment_override_multi_site(client, test_employee):
    eid = test_employee["id"]
    r = client.post("/hr3/deployments", json={
        "person_type": "employee", "person_id": eid,
        "project_code": "PRJ-PYT-MULTI",
        "deployment_start_date": "2026-08-01",
        "allow_multi_site": True,
    })
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def fresh_deployment(client):
    """A throw-away deployment used for mobilization/demobilization workflow."""
    # Compliant employee
    r = client.post("/employees", json={
        "name": "PYTEST MOB Emp",
        "department": "Operations", "designation": "site_supervisor",
        "skill_name": "supervisor", "status": "active",
        "documents_verified": True, "safety_induction": True,
        "medical_fitness": True, "medical_fitness_valid_till": "2099-12-31",
    })
    if r.status_code not in (200, 201):
        pytest.skip(f"employees endpoint unavailable: {r.status_code}")
    emp = r.json()
    r2 = client.post("/hr3/deployments", json={
        "person_type": "employee", "person_id": emp["id"],
        "project_code": "PRJ-PYT-MOBFLOW",
        "site_location": "MOB Site",
        "skill": "supervisor",
        "deployment_start_date": "2026-07-15",
        "ppe_required": True, "travel_required": True,
        "accommodation_required": True,
    })
    assert r2.status_code == 200, r2.text
    return r2.json()


# ──────────────────────────────────────────────────────────────────────────────
# 4.  Mobilization
# ──────────────────────────────────────────────────────────────────────────────
def test_mobilization_workflow(client, fresh_deployment):
    dep = fresh_deployment
    # Create mob
    r = client.post("/hr3/mobilizations", json={
        "deployment_id": dep["id"],
        "travel_date": "2026-07-14",
        "reporting_date": "2026-07-15",
        "travel_required": True,
        "accommodation_required": True,
        "ppe_required": True,
        "tool_required": False,
    })
    assert r.status_code == 200, r.text
    mob = r.json()
    assert mob["mobilization_no"].startswith("MOB-")
    assert mob["logistics_status"] == "pending"
    mid = mob["id"]
    # Try to close while sections are pending — must 400
    r2 = client.post(f"/hr3/mobilizations/{mid}/close")
    assert r2.status_code == 400
    # Complete all 3 sections
    for sec in ("logistics", "store", "safety"):
        rs = client.post(f"/hr3/mobilizations/{mid}/section",
                         json={"section": sec, "status": "ok"})
        assert rs.status_code == 200, rs.text
    # Now close OK
    r3 = client.post(f"/hr3/mobilizations/{mid}/close")
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "closed"


def test_mobilization_bad_section(client, fresh_deployment):
    r = client.post("/hr3/mobilizations", json={"deployment_id": fresh_deployment["id"]})
    mid = r.json()["id"]
    r2 = client.post(f"/hr3/mobilizations/{mid}/section",
                     json={"section": "kitchen", "status": "ok"})
    assert r2.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# 5.  Demobilization
# ──────────────────────────────────────────────────────────────────────────────
def test_demobilization_workflow(client, fresh_deployment):
    dep = fresh_deployment
    r = client.post("/hr3/demobilizations", json={
        "deployment_id": dep["id"],
        "reason": "Project complete",
        "return_travel_required": True,
        "ppe_return_required": True,
        "tool_return_required": False,
    })
    assert r.status_code == 200, r.text
    demob = r.json()
    assert demob["demobilization_no"].startswith("DMB-")
    did = demob["id"]
    # Close while pending → 400
    r2 = client.post(f"/hr3/demobilizations/{did}/close")
    assert r2.status_code == 400
    # Set every clearance OK
    for sec in ("store", "safety", "project", "hr", "logistics"):
        rs = client.post(f"/hr3/demobilizations/{did}/clearance",
                         json={"section": sec, "status": "ok"})
        assert rs.status_code == 200, rs.text
    r3 = client.post(f"/hr3/demobilizations/{did}/close")
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "closed"


# ──────────────────────────────────────────────────────────────────────────────
# 6.  Replacement
# ──────────────────────────────────────────────────────────────────────────────
def test_replacement_flow(client, test_employee):
    r = client.post("/hr3/replacements", json={
        "project_code": "PRJ-PYT-REP",
        "site_location": "REP Site",
        "existing_employee_id": test_employee["id"],
        "reason": "Performance issue",
        "required_skill": "scaffolder",
        "required_date": "2026-08-01",
        "urgency": "high",
    })
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["replacement_no"].startswith("REP-")
    assert rep["approval_status"] == "pending"
    rid = rep["id"]
    r2 = client.post(f"/hr3/replacements/{rid}/approve",
                     json={"decision": "approve"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["approval_status"] == "approved"


def test_replacement_bad_urgency(client):
    r = client.post("/hr3/replacements", json={
        "project_code": "PRJ-X",
        "existing_employee_id": "x",
        "reason": "test",
        "required_skill": "x",
        "urgency": "extreme",
    })
    assert r.status_code == 400


def test_replacement_empty_reason(client):
    r = client.post("/hr3/replacements", json={
        "project_code": "PRJ-X",
        "existing_employee_id": "x",
        "reason": "   ",
        "required_skill": "x",
        "urgency": "high",
    })
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# 7.  Rollups
# ──────────────────────────────────────────────────────────────────────────────
def test_project_manpower(client):
    r = client.get("/hr3/project-manpower")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_site_manpower(client):
    r = client.get("/hr3/site-manpower")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_shortage_report(client):
    r = client.get("/hr3/shortage-report")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_deployment_calendar(client):
    r = client.get("/hr3/deployment-calendar?from_date=2026-01-01&to_date=2026-12-31")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_hr3_dashboard(client):
    r = client.get("/hr3/dashboard")
    assert r.status_code == 200
    j = r.json()
    for k in ("open_requirements", "active_deployments",
              "mobilizations_open", "demobilizations_open",
              "replacements_open", "total_shortage"):
        assert k in j


def test_sales_requirements(client):
    r = client.get("/hr3/sales-requirements")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
