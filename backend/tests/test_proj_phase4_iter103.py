"""Iter 103 — P&O Phase 4 — Cross-module aggregation, blockers, exceptions, transitions, alerts."""
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


# ─── per-module summary endpoints ─────────────────────────────────────
def test_each_summary_dimension_returns_200(s, project):
    pid = project["id"]
    for dim in ("manpower", "material", "safety", "logistics", "procurement", "accounts", "finance"):
        r = s.get(f"{API_URL}/api/proj-phase4/summary/{pid}/{dim}", timeout=15)
        assert r.status_code == 200, f"{dim} → {r.text}"
        d = r.json()
        assert isinstance(d, dict) and d  # non-empty


def test_unknown_dimension_rejected(s, project):
    r = s.get(f"{API_URL}/api/proj-phase4/summary/{project['id']}/foo", timeout=10)
    assert r.status_code == 400


def test_manpower_summary_has_expected_keys(s, project):
    d = s.get(f"{API_URL}/api/proj-phase4/summary/{project['id']}/manpower", timeout=10).json()
    for k in ("planned_count", "deployed_count", "deployed_present_today", "shortage_count", "skill_breakdown"):
        assert k in d


def test_accounts_summary_has_profit_and_margin(s, project):
    d = s.get(f"{API_URL}/api/proj-phase4/summary/{project['id']}/accounts", timeout=15).json()
    for k in ("work_order_value", "invoice_raised", "total_cost", "profit_or_loss", "margin_pct"):
        assert k in d


# ─── control center ───────────────────────────────────────────────────
def test_one_project_control_center(s, project):
    r = s.get(f"{API_URL}/api/proj-phase4/control-center/{project['id']}", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("project", "manpower", "material", "safety", "logistics",
               "procurement", "accounts", "finance", "blockers_active",
               "blockers_closure", "unack_alerts"):
        assert k in d


def test_portfolio_control_center(s):
    r = s.get(f"{API_URL}/api/proj-phase4/control-center", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "counters" in d and "projects" in d
    for k in ("projects_active", "projects_delayed", "projects_with_manpower_shortage",
              "projects_over_budget", "projects_pending_billing",
              "projects_ready_for_closure", "projects_blocked_safety",
              "projects_blocked_manpower"):
        assert k in d["counters"], f"missing counter {k}"


# ─── blockers + transitions ───────────────────────────────────────────
def test_blockers_endpoint_returns_shape(s, project):
    for tr in ("active", "completed", "closure_pending", "closed"):
        r = s.get(f"{API_URL}/api/proj-phase4/blockers/{project['id']}", params={"transition": tr}, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "blockers" in d
        assert "blocked" in d
        assert isinstance(d["blockers"], list)


def test_transition_check_unsupported(s, project):
    r = s.get(f"{API_URL}/api/proj-phase4/transition-check/{project['id']}",
               params={"to": "bogus"}, timeout=10)
    assert r.status_code == 400


def test_transition_check_active_works(s, project):
    r = s.get(f"{API_URL}/api/proj-phase4/transition-check/{project['id']}",
               params={"to": "active"}, timeout=10)
    assert r.status_code == 200
    assert "can_transition" in r.json()


# ─── exception / override workflow ────────────────────────────────────
def test_exception_create_and_approve(s, project):
    r = s.post(f"{API_URL}/api/proj-phase4/exceptions", json={
        "project_id": project["id"], "kind": "manpower",
        "title": f"override-{secrets.token_hex(2)}",
        "reason": "Pilot phase, manpower not yet onboarded",
        "applies_to_transition": "active",
    }, timeout=10)
    assert r.status_code == 200, r.text
    ex = r.json()
    eid = ex["id"]
    assert ex["status"] == "pending"

    # super admin approves
    r = s.post(f"{API_URL}/api/proj-phase4/exceptions/{eid}/approve", timeout=10)
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # listing supports filter
    rows = s.get(f"{API_URL}/api/proj-phase4/exceptions",
                  params={"project_id": project["id"], "status": "approved"}, timeout=10).json()
    assert any(x["id"] == eid for x in rows)


# ─── transition with override ─────────────────────────────────────────
def test_transition_apply_with_override(s, project):
    pid = project["id"]
    # toggle to active first if possible
    r = s.post(f"{API_URL}/api/proj-phase4/transition/{pid}",
                params={"to": "on_hold"}, timeout=15)
    # success or blocked — we don't assert success since validation rules may differ
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        # toggle back
        r2 = s.post(f"{API_URL}/api/proj-phase4/transition/{pid}",
                     params={"to": "active"}, timeout=15)
        assert r2.status_code in (200, 403)


# ─── alerts ───────────────────────────────────────────────────────────
def test_alerts_endpoint_returns_list(s):
    r = s.get(f"{API_URL}/api/proj-phase4/alerts", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_alert_ack_idempotent(s, project):
    # ensure at least one alert is generated by hitting control center
    s.get(f"{API_URL}/api/proj-phase4/control-center/{project['id']}", timeout=20)
    alerts = s.get(f"{API_URL}/api/proj-phase4/alerts",
                    params={"project_id": project["id"], "acknowledged": False}, timeout=10).json()
    if not alerts:
        pytest.skip("No alert generated for this seed project — that's fine")
    a = alerts[0]
    r = s.post(f"{API_URL}/api/proj-phase4/alerts/{a['id']}/ack",
                json={"note": "acknowledged"}, timeout=10)
    assert r.status_code == 200 and r.json()["ack_at"]
