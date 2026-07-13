"""Iter 100 — P&O Phase 3 · Round 3A — DPR + Work Progress."""
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


@pytest.fixture(scope="module")
def boq_with_lines(s, project):
    """Create a BOQ with two lines for testing cumulative qty caps."""
    boq = s.post(f"{API_URL}/api/proj-phase2/boqs",
                  json={"project_id": project["id"], "title": "DPR Test BOQ", "tax_rate": 18},
                  timeout=10).json()
    l1 = s.post(f"{API_URL}/api/proj-phase2/boqs/{boq['id']}/lines",
                 json={"description": "Painting", "uom": "sqm", "quantity": 100, "unit_rate": 250},
                 timeout=10).json()
    l2 = s.post(f"{API_URL}/api/proj-phase2/boqs/{boq['id']}/lines",
                 json={"description": "Scaffolding", "uom": "cum", "quantity": 50, "unit_rate": 500},
                 timeout=10).json()
    yield {"boq_id": boq["id"], "lines": [l1, l2]}
    # cleanup
    s.delete(f"{API_URL}/api/proj-phase2/boqs/{boq['id']}", timeout=10)


# ─── DPR validations ──────────────────────────────────────────────────
def test_dpr_create_with_lines_and_cumulative(s, project, boq_with_lines):
    pid = project["id"]
    bln = boq_with_lines["lines"][0]
    # DPR with one line on Painting (40 sqm of 100)
    r = s.post(f"{API_URL}/api/proj-phase3/dprs", json={
        "project_id": pid, "dpr_date": project.get("start_date") or "2026-04-01",
        "site_location": "Site A", "manpower_deployed": 10, "manpower_present": 9,
        "work_performed": "Started painting",
        "lines": [
            {"description": "Painting", "boq_line_id": bln["id"], "boq_id": boq_with_lines["boq_id"],
             "uom": "sqm", "qty_completed_today": 40},
        ],
    }, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dpr_no"].startswith("DPR-")
    assert d["status"] == "draft"
    assert len(d["lines"]) == 1
    line = d["lines"][0]
    assert line["cumulative_qty_completed"] == 40
    assert line["balance_qty"] == 60   # 100 - 40
    # cleanup
    s.delete(f"{API_URL}/api/proj-phase3/dprs/{d['id']}", timeout=10)


def test_dpr_negative_qty_rejected(s, project):
    r = s.post(f"{API_URL}/api/proj-phase3/dprs", json={
        "project_id": project["id"], "dpr_date": "2026-04-01",
        "lines": [{"description": "x", "qty_completed_today": -5}],
    }, timeout=10)
    assert r.status_code == 400
    assert "negative" in r.json()["detail"].lower()


def test_dpr_boq_qty_cap_enforced(s, project, boq_with_lines):
    pid = project["id"]
    bln = boq_with_lines["lines"][1]    # Scaffolding 50 cum
    # try to log 60 cum in one shot — should fail (exceeds 50)
    r = s.post(f"{API_URL}/api/proj-phase3/dprs", json={
        "project_id": pid, "dpr_date": "2026-04-02",
        "lines": [{"description": "Scaffold", "boq_line_id": bln["id"], "qty_completed_today": 60}],
    }, timeout=10)
    assert r.status_code == 400
    assert "exceed" in r.json()["detail"].lower()
    # marking extra_work allows it
    r = s.post(f"{API_URL}/api/proj-phase3/dprs", json={
        "project_id": pid, "dpr_date": "2026-04-02",
        "lines": [{"description": "Scaffold", "boq_line_id": bln["id"],
                   "qty_completed_today": 60, "extra_work": True}],
    }, timeout=10)
    assert r.status_code == 200
    s.delete(f"{API_URL}/api/proj-phase3/dprs/{r.json()['id']}", timeout=10)


# ─── Status workflow + cascade ────────────────────────────────────────
def test_dpr_full_workflow_and_progress_cascade(s, project, boq_with_lines):
    pid = project["id"]
    bln = boq_with_lines["lines"][0]   # Painting 100 sqm
    # 1. create draft
    r = s.post(f"{API_URL}/api/proj-phase3/dprs", json={
        "project_id": pid, "dpr_date": "2026-04-03",
        "lines": [{"description": "Painting day 1", "boq_line_id": bln["id"], "qty_completed_today": 30}],
    }, timeout=10)
    d = r.json()
    did = d["id"]
    assert d["status"] == "draft"

    # 2. submit
    r = s.post(f"{API_URL}/api/proj-phase3/dprs/{did}/submit", timeout=10)
    assert r.status_code == 200 and r.json()["status"] == "submitted"

    # 3. approve → cascades to work_progress
    r = s.post(f"{API_URL}/api/proj-phase3/dprs/{did}/approve", timeout=10)
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # 4. work_progress should now have a row for this BOQ line
    rows = s.get(f"{API_URL}/api/proj-phase3/work-progress/{pid}", timeout=10).json()
    wp = next((x for x in rows if x.get("boq_line_id") == bln["id"]), None)
    assert wp is not None, "WorkProgress row should exist post-approval"
    assert wp["cumulative_completed_qty"] == 30
    assert wp["planned_qty"] == 100
    assert wp["actual_progress_pct"] == 30.0

    # 5. cannot delete approved DPR as a normal user — but admin OK
    r = s.delete(f"{API_URL}/api/proj-phase3/dprs/{did}", timeout=10)
    assert r.status_code == 200  # super_admin override
    # work_progress survives (it's separate)
    rows = s.get(f"{API_URL}/api/proj-phase3/work-progress/{pid}", timeout=10).json()
    wp_after = next((x for x in rows if x.get("boq_line_id") == bln["id"]), None)
    assert wp_after is not None


def test_dpr_revise_creates_snapshot(s, project, boq_with_lines):
    pid = project["id"]
    bln = boq_with_lines["lines"][0]
    r = s.post(f"{API_URL}/api/proj-phase3/dprs", json={
        "project_id": pid, "dpr_date": "2026-04-05",
        "lines": [{"description": "x", "boq_line_id": bln["id"], "qty_completed_today": 5}],
    }, timeout=10)
    did = r.json()["id"]
    s.post(f"{API_URL}/api/proj-phase3/dprs/{did}/submit", timeout=10)
    s.post(f"{API_URL}/api/proj-phase3/dprs/{did}/approve", timeout=10)
    # cannot edit while approved
    r = s.put(f"{API_URL}/api/proj-phase3/dprs/{did}", json={
        "project_id": pid, "dpr_date": "2026-04-05",
        "lines": [{"description": "x", "qty_completed_today": 6}],
    }, timeout=10)
    assert r.status_code == 403

    # revise unlocks
    r = s.post(f"{API_URL}/api/proj-phase3/dprs/{did}/revise", timeout=10)
    assert r.status_code == 200 and r.json()["status"] == "revised"
    s.delete(f"{API_URL}/api/proj-phase3/dprs/{did}", timeout=10)


def test_dpr_date_outside_project_period_rejected(s, project):
    """If project has a start_date / end_date, DPR date outside it must 400."""
    if not project.get("start_date"):
        pytest.skip("Project lacks start_date — cannot exercise this rule")
    r = s.post(f"{API_URL}/api/proj-phase3/dprs", json={
        "project_id": project["id"], "dpr_date": "1999-01-01",
        "lines": [],
    }, timeout=10)
    assert r.status_code == 400
    assert "outside project period" in r.json()["detail"].lower()


# ─── Integration READ endpoints ───────────────────────────────────────
def test_integration_manpower_endpoint(s, project):
    r = s.get(f"{API_URL}/api/proj-phase3/integrations/{project['id']}/manpower", timeout=10)
    assert r.status_code == 200
    assert "deployed_count" in r.json()
    assert "present_count" in r.json()


def test_integration_material_safety_logistics_endpoints(s, project):
    for sub in ("material", "safety", "logistics"):
        r = s.get(f"{API_URL}/api/proj-phase3/integrations/{project['id']}/{sub}", timeout=10)
        assert r.status_code == 200
