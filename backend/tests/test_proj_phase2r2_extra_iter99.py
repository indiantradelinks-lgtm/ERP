"""Iter 99 — extra coverage for P&O Phase 2 R2: dot-notation levels, cascade unlink, summary counts, type filter."""
import os
import secrets
import pytest
import requests

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def project(session):
    projects = session.get(f"{API_URL}/api/projects", timeout=10).json()
    assert projects
    return projects[0]


# ── WBS level auto-compute from dot notation ──────────────────────────
def test_wbs_level_autocompute_3_deep(session, project):
    pid = project["id"]
    pfx = f"L{secrets.token_hex(2)}"
    created = []
    try:
        r1 = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                          json={"code": f"{pfx}", "name": "L1"}, timeout=10)
        assert r1.status_code == 200
        assert r1.json()["level"] == 1
        created.append(r1.json()["id"])

        r2 = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                          json={"code": f"{pfx}.1", "name": "L2", "parent_id": r1.json()["id"]},
                          timeout=10)
        assert r2.status_code == 200
        assert r2.json()["level"] == 2
        created.append(r2.json()["id"])

        r3 = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                          json={"code": f"{pfx}.1.2", "name": "L3", "parent_id": r2.json()["id"]},
                          timeout=10)
        assert r3.status_code == 200
        assert r3.json()["level"] == 3
        created.append(r3.json()["id"])
    finally:
        # cascade delete root
        if created:
            session.delete(f"{API_URL}/api/proj-phase2/wbs/nodes/{created[0]}", timeout=10)


# ── WBS cascade unlinks activities / resources (sets wbs_id to None) ──
def test_wbs_delete_cascades_unlinks_activities_and_resources(session, project):
    pid = project["id"]
    pfx = f"U{secrets.token_hex(2)}"
    w = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                     json={"code": pfx, "name": "Wbs to delete"}, timeout=10).json()
    wid = w["id"]

    a = session.post(f"{API_URL}/api/proj-phase2/activities/{pid}",
                     json={"name": "Linked activity", "wbs_id": wid}, timeout=10).json()
    aid = a["id"]
    assert a["wbs_id"] == wid

    r = session.post(f"{API_URL}/api/proj-phase2/resources/{pid}",
                     json={"resource_type": "tools", "tool_name": "Linked tool",
                           "count_required": 1, "days": 1, "daily_rate": 100,
                           "wbs_id": wid}, timeout=10).json()
    rid = r["id"]
    assert r["wbs_id"] == wid

    # delete WBS
    dr = session.delete(f"{API_URL}/api/proj-phase2/wbs/nodes/{wid}", timeout=10)
    assert dr.status_code == 200

    # activity still exists but wbs_id is None
    acts = session.get(f"{API_URL}/api/proj-phase2/activities/{pid}", timeout=10).json()
    a_after = next((x for x in acts if x["id"] == aid), None)
    assert a_after is not None
    assert a_after.get("wbs_id") is None

    # resource still exists but wbs_id is None
    res = session.get(f"{API_URL}/api/proj-phase2/resources/{pid}", timeout=10).json()
    r_after = next((x for x in res if x["id"] == rid), None)
    assert r_after is not None
    assert r_after.get("wbs_id") is None

    # cleanup
    session.delete(f"{API_URL}/api/proj-phase2/activities/{aid}", timeout=10)
    session.delete(f"{API_URL}/api/proj-phase2/resources/{rid}", timeout=10)


# ── Activity invalid status on create ─────────────────────────────────
def test_activity_invalid_status_on_create(session, project):
    pid = project["id"]
    r = session.post(f"{API_URL}/api/proj-phase2/activities/{pid}",
                     json={"name": "BadStatus", "status": "nope"}, timeout=10)
    assert r.status_code == 400


# ── Activity auto-code generation when blank ──────────────────────────
def test_activity_autogen_code_format(session, project):
    pid = project["id"]
    r = session.post(f"{API_URL}/api/proj-phase2/activities/{pid}",
                     json={"name": "AutoCodeTest", "code": ""}, timeout=10)
    assert r.status_code == 200
    code = r.json()["code"]
    assert code.startswith("ACT-") and len(code) == 8
    session.delete(f"{API_URL}/api/proj-phase2/activities/{r.json()['id']}", timeout=10)


# ── Resource summary counts per type ──────────────────────────────────
def test_resources_summary_counts(session, project):
    pid = project["id"]
    before = session.get(f"{API_URL}/api/proj-phase2/resources/{pid}/summary", timeout=10).json()
    # create one tools resource
    tool = session.post(f"{API_URL}/api/proj-phase2/resources/{pid}",
                        json={"resource_type": "tools", "tool_name": "Drill",
                              "count_required": 1, "days": 5, "daily_rate": 200},
                        timeout=10).json()
    after = session.get(f"{API_URL}/api/proj-phase2/resources/{pid}/summary", timeout=10).json()
    assert after["tools_count"] == before["tools_count"] + 1
    assert round(after["tools"] - before["tools"], 2) == 1000.0
    assert round(after["grand_total"] - before["grand_total"], 2) == 1000.0
    session.delete(f"{API_URL}/api/proj-phase2/resources/{tool['id']}", timeout=10)


# ── Resource update recomputes total_cost ─────────────────────────────
def test_resource_update_recomputes_total(session, project):
    pid = project["id"]
    r = session.post(f"{API_URL}/api/proj-phase2/resources/{pid}",
                     json={"resource_type": "tools", "tool_name": "Saw",
                           "count_required": 1, "days": 2, "daily_rate": 100},
                     timeout=10).json()
    assert r["total_cost"] == 200
    upd = session.put(f"{API_URL}/api/proj-phase2/resources/{r['id']}",
                      json={"resource_type": "tools", "tool_name": "Saw",
                            "count_required": 3, "days": 4, "daily_rate": 100},
                      timeout=10).json()
    assert upd["total_cost"] == 1200
    session.delete(f"{API_URL}/api/proj-phase2/resources/{r['id']}", timeout=10)
