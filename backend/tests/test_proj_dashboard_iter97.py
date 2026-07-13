"""Iter 97: P&O Phase 1 — Dashboard + Status Workflow + Validation."""
import os
import secrets

import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
EXPECTED_CARDS = {
    "total_projects", "active_projects", "planned_projects", "mobilization_pending_projects",
    "projects_on_hold", "completed_projects", "closure_pending_projects", "delayed_projects",
    "shutdown_projects", "projects_without_pm", "projects_without_site_incharge",
    "projects_pending_approval", "projects_requiring_manpower", "projects_requiring_material",
    "projects_requiring_safety_clearance", "projects_pending_billing",
    "projects_with_pending_closure", "recent_projects", "high_value_projects", "status_summary",
}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return s


def test_dashboard_returns_all_20_cards(admin_session):
    r = admin_session.get(f"{API_URL}/api/proj-masters/dashboard-kpis", timeout=10)
    assert r.status_code == 200
    k = r.json()
    missing = EXPECTED_CARDS - set(k.keys())
    assert not missing, f"missing dashboard cards: {missing}"
    # Each counted card carries either count+ids or count+items
    for ckey in ("total_projects", "delayed_projects"):
        assert "count" in k[ckey] and ("ids" in k[ckey] or "items" in k[ckey])


def test_dashboard_counts_from_real_db(admin_session):
    """Sanity: total_projects must equal len(/api/projects)."""
    a = admin_session.get(f"{API_URL}/api/proj-masters/dashboard-kpis", timeout=10).json()
    b = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    assert a["total_projects"]["count"] == len(b)


def test_duplicate_code_check(admin_session):
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    existing = projects[0]["code"]
    r = admin_session.get(f"{API_URL}/api/proj-masters/projects/check-code/{existing}", timeout=10).json()
    assert r["exists"] is True
    r = admin_session.get(f"{API_URL}/api/proj-masters/projects/check-code/FAKE-{secrets.token_hex(3)}", timeout=10).json()
    assert r["exists"] is False


def test_status_invalid_transition_blocked(admin_session):
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    p = projects[0]; orig = p.get("status")
    try:
        # Force to "planned" via override
        admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": "planned", "override": True}, timeout=10)
        # planned → active is INVALID
        r = admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": "active"}, timeout=10)
        assert r.status_code == 400, r.text
        assert "Cannot transition" in r.json().get("detail", "")
    finally:
        admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": orig or "planned", "override": True}, timeout=10)


def test_approval_blocks_missing_required(admin_session):
    """Project without PM or WO ref cannot move to approved."""
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    p = next((x for x in projects if not (x.get("manager") and x.get("work_order_number"))), None)
    if not p:
        pytest.skip("no project missing PM/WO to test guard")
    orig = p.get("status")
    try:
        admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": "planned", "override": True}, timeout=10)
        r = admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": "approved"}, timeout=10)
        assert r.status_code == 400
        assert "missing required" in r.json().get("detail", "").lower()
    finally:
        admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": orig or "planned", "override": True}, timeout=10)


def test_status_history_written(admin_session):
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    p = projects[0]; orig = p.get("status")
    try:
        admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": "planned", "override": True, "reason": "regression"}, timeout=10)
        hist = admin_session.get(f"{API_URL}/api/proj-masters/projects/{p['id']}/status-history", timeout=10).json()
        assert len(hist) >= 1
        last = hist[-1]
        assert last["to_status"] == "planned"
        assert "by_name" in last and "at" in last and "from_status" in last
    finally:
        admin_session.put(f"{API_URL}/api/proj-masters/projects/{p['id']}/status",
            json={"new_status": orig or "planned", "override": True}, timeout=10)


def test_drill_down_ids_resolve_to_projects(admin_session):
    """For each card with ids, every id must exist in db.projects."""
    a = admin_session.get(f"{API_URL}/api/proj-masters/dashboard-kpis", timeout=10).json()
    projects = {p["id"] for p in admin_session.get(f"{API_URL}/api/projects", timeout=10).json()}
    for key in ("delayed_projects", "active_projects", "planned_projects"):
        for pid in a[key].get("ids", []):
            assert pid in projects, f"{key} returned id {pid} which is not in /api/projects"
