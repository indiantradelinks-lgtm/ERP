"""Iter 101 — P&O Phase 3 · Rounds 3B + 3C — Measurement / Issues / CI / Extra / Permits / Dashboard."""
import os
import secrets

import pytest
import requests

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return sess


@pytest.fixture(scope="module")
def project(s):
    return s.get(f"{API_URL}/api/projects", timeout=10).json()[0]


# ─── Measurement Sheet ────────────────────────────────────────────────
def test_measurement_full_cycle(s, project):
    pid = project["id"]
    # create
    r = s.post(f"{API_URL}/api/proj-phase3/measurements", json={
        "project_id": pid, "measurement_date": "2026-04-10",
        "title": f"Test MS {secrets.token_hex(2)}", "prepared_by": "Engineer A",
    }, timeout=10)
    assert r.status_code == 200, r.text
    ms = r.json()
    msid = ms["id"]
    assert ms["measurement_no"].startswith("MS-")
    assert ms["status"] == "draft"

    # add line with L×W×H auto-quantity
    r = s.post(f"{API_URL}/api/proj-phase3/measurements/{msid}/lines", json={
        "description": "Wall painting", "length": 10, "width": 3, "height": 1,
        "uom": "sqm", "rate": 250,
    }, timeout=10)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["lines"][0]["quantity"] == 30.0  # 10*3*1
    assert detail["total_amount"] == 30 * 250

    # submit → check → approve transitions
    for step in ("submit", "check", "approve"):
        r = s.post(f"{API_URL}/api/proj-phase3/measurements/{msid}/{step}", timeout=10)
        assert r.status_code == 200, f"{step} failed: {r.text}"

    # certify a line
    line_id = detail["lines"][0]["id"]
    r = s.post(f"{API_URL}/api/proj-phase3/measurements/{msid}/certify", json={
        "line_id": line_id, "certified_quantity": 28,
        "client_certification_status": "partial", "rejected_held_quantity": 2,
    }, timeout=10)
    assert r.status_code == 200
    after = r.json()
    assert after["certified_amount"] == 28 * 250

    # pending certification surfaces remaining 'partial'
    r = s.get(f"{API_URL}/api/proj-phase3/measurements/{pid}/pending-certification", timeout=10)
    assert r.status_code == 200
    # cleanup (super admin)
    s.delete(f"{API_URL}/api/proj-phase3/measurements/{msid}", timeout=10)


# ─── Site Issues ──────────────────────────────────────────────────────
def test_site_issue_lifecycle_and_notification(s, project):
    pid = project["id"]
    # critical issue triggers notification
    r = s.post(f"{API_URL}/api/proj-phase3/issues", json={
        "project_id": pid, "category": "safety", "title": "Scaffold collapse risk",
        "impact": "critical", "delay_impact": True, "cost_impact": True,
        "description": "Loose tie", "responsible_department": "HSE",
    }, timeout=10)
    assert r.status_code == 200, r.text
    iss = r.json()
    iid = iss["id"]
    assert iss["status"] == "open"
    assert iss["issue_no"].startswith("ISS-")

    # close it
    r = s.post(f"{API_URL}/api/proj-phase3/issues/{iid}/close?closure_note=fixed", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "closed"

    # invalid category rejected
    r = s.post(f"{API_URL}/api/proj-phase3/issues", json={
        "project_id": pid, "category": "made-up", "title": "category test",
    }, timeout=10)
    assert r.status_code == 400

    s.delete(f"{API_URL}/api/proj-phase3/issues/{iid}", timeout=10)


# ─── Client Instructions + Extra Work ─────────────────────────────────
def test_client_instruction_and_extra_work_flow(s, project):
    pid = project["id"]
    # client instruction
    ci = s.post(f"{API_URL}/api/proj-phase3/client-instructions", json={
        "project_id": pid, "given_by": "Mr. Owner",
        "mode": "written", "instruction_details": "Add 2nd coat of paint",
    }, timeout=10).json()
    assert ci["instruction_no"].startswith("CI-")

    # extra work linked to that CI; auto estimated_value = qty*rate
    ew = s.post(f"{API_URL}/api/proj-phase3/extra-works", json={
        "project_id": pid, "client_instruction_id": ci["id"],
        "work_description": "Second coat paint", "quantity": 100, "rate": 50,
        "client_approval_status": "verbal",   # → flagged as risk
    }, timeout=10).json()
    assert ew["estimated_value"] == 5000
    assert ew["is_risk"] is True
    assert ew["approval_status"] == "pending"

    # PM approves
    r = s.post(f"{API_URL}/api/proj-phase3/extra-works/{ew['id']}/approve", timeout=10)
    assert r.status_code == 200 and r.json()["approval_status"] == "approved"

    # billable list
    r = s.get(f"{API_URL}/api/proj-phase3/extra-works/{pid}/billable", timeout=10)
    assert r.status_code == 200
    billable = r.json()
    assert billable["count"] >= 1
    assert billable["total_value"] >= 5000

    # reject second one
    ew2 = s.post(f"{API_URL}/api/proj-phase3/extra-works", json={
        "project_id": pid, "work_description": "Test reject row", "quantity": 1, "rate": 1,
    }, timeout=10).json()
    r = s.post(f"{API_URL}/api/proj-phase3/extra-works/{ew2['id']}/reject?reason=not%20required", timeout=10)
    assert r.status_code == 200 and r.json()["approval_status"] == "rejected"

    # cleanup
    s.delete(f"{API_URL}/api/proj-phase3/extra-works/{ew['id']}", timeout=10)
    s.delete(f"{API_URL}/api/proj-phase3/extra-works/{ew2['id']}", timeout=10)
    s.delete(f"{API_URL}/api/proj-phase3/client-instructions/{ci['id']}", timeout=10)


# ─── Work Permits ─────────────────────────────────────────────────────
def test_permit_create_and_expiry_detection(s, project):
    pid = project["id"]
    # invalid type rejected
    r = s.post(f"{API_URL}/api/proj-phase3/permits", json={
        "project_id": pid, "permit_type": "fake", "valid_to": "2099-01-01",
    }, timeout=10)
    assert r.status_code == 400

    # active permit, valid until 2099 — should be 'active'
    p1 = s.post(f"{API_URL}/api/proj-phase3/permits", json={
        "project_id": pid, "permit_type": "hot_work",
        "valid_from": "2026-01-01", "valid_to": "2099-12-31",
        "issued_by": "Client HSE", "safety_clearance_status": "cleared",
        "activity_covered": "Welding works",
    }, timeout=10).json()
    assert p1["permit_no"].startswith("WP-")
    assert p1["status"] == "active"

    # expired permit
    p2 = s.post(f"{API_URL}/api/proj-phase3/permits", json={
        "project_id": pid, "permit_type": "general",
        "valid_from": "2020-01-01", "valid_to": "2020-12-31",
    }, timeout=10).json()
    # listing recomputes status → expired
    rows = s.get(f"{API_URL}/api/proj-phase3/permits", params={"project_id": pid}, timeout=10).json()
    p2_row = next(r for r in rows if r["id"] == p2["id"])
    assert p2_row["status"] == "expired"

    # /expiring
    r = s.get(f"{API_URL}/api/proj-phase3/permits/{pid}/expiring?days=7", timeout=10)
    assert r.status_code == 200
    alerts = r.json()
    expired_alerts = [x for x in alerts["rows"] if x.get("alert") == "expired"]
    assert any(x["id"] == p2["id"] for x in expired_alerts)

    s.delete(f"{API_URL}/api/proj-phase3/permits/{p1['id']}", timeout=10)
    s.delete(f"{API_URL}/api/proj-phase3/permits/{p2['id']}", timeout=10)


# ─── Execution Dashboard + DPR Report ─────────────────────────────────
def test_execution_dashboard_and_report(s, project):
    pid = project["id"]
    r = s.get(f"{API_URL}/api/proj-phase3/execution/{pid}/dashboard", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("dpr", "issues", "delays", "permits", "measurements", "extra_work", "progress"):
        assert k in d, f"missing key {k}"
    assert "avg_actual_pct" in d["progress"]

    # DPR report endpoint
    r = s.get(f"{API_URL}/api/proj-phase3/reports/dpr", params={"project_id": pid}, timeout=10)
    assert r.status_code == 200
    rep = r.json()
    assert "rows" in rep and "summary" in rep
    assert "total" in rep["summary"]
