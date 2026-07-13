"""Iter 99 — P&O Phase 2 · Round 2 — WBS, Activities, Resources."""
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


# ─── WBS ──────────────────────────────────────────────────────────────
def test_wbs_create_with_parent_then_tree(session, project):
    pid = project["id"]
    suffix = secrets.token_hex(2)
    # root
    r = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                      json={"code": f"T{suffix}", "name": "Site Prep", "weight_pct": 30,
                            "estimated_hours": 40, "status": "not_started"},
                      timeout=10)
    assert r.status_code == 200, r.text
    root_id = r.json()["id"]
    assert r.json()["level"] == 1

    # duplicate code rejected
    dup = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                        json={"code": f"T{suffix}", "name": "Dup"}, timeout=10)
    assert dup.status_code == 409

    # child
    r = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                      json={"code": f"T{suffix}.1", "name": "Excavation", "parent_id": root_id,
                            "weight_pct": 15, "estimated_hours": 18},
                      timeout=10)
    assert r.status_code == 200
    assert r.json()["level"] == 2
    child_id = r.json()["id"]

    # tree exposes children[]
    tree = session.get(f"{API_URL}/api/proj-phase2/wbs/{pid}/tree", timeout=10).json()
    root_node = next((n for n in tree if n["id"] == root_id), None)
    assert root_node and any(c["id"] == child_id for c in root_node.get("children", []))

    # update via PUT (rename child)
    r = session.put(f"{API_URL}/api/proj-phase2/wbs/nodes/{child_id}",
                     json={"code": f"T{suffix}.1", "name": "Excavation & Grading",
                           "parent_id": root_id, "weight_pct": 15, "estimated_hours": 18,
                           "status": "in_progress"},
                     timeout=10)
    assert r.status_code == 200
    assert r.json()["name"] == "Excavation & Grading"
    assert r.json()["status"] == "in_progress"

    # cascade delete from root
    r = session.delete(f"{API_URL}/api/proj-phase2/wbs/nodes/{root_id}", timeout=10)
    assert r.status_code == 200
    assert r.json()["deleted"] >= 2  # parent + 1 child


def test_wbs_invalid_parent_rejected(session, project):
    pid = project["id"]
    r = session.post(f"{API_URL}/api/proj-phase2/wbs/{pid}",
                      json={"code": f"X{secrets.token_hex(2)}", "name": "n", "parent_id": "no-such-id"},
                      timeout=10)
    assert r.status_code == 404


# ─── Activities ───────────────────────────────────────────────────────
def test_activity_full_cycle(session, project):
    pid = project["id"]
    # create
    r = session.post(f"{API_URL}/api/proj-phase2/activities/{pid}",
                      json={"name": "Site Mobilization",
                            "start_date": "2026-04-01", "end_date": "2026-04-10",
                            "status": "in_progress", "progress_pct": 25,
                            "responsible": "Site Engineer"},
                      timeout=10)
    assert r.status_code == 200, r.text
    a = r.json()
    aid = a["id"]
    assert a["code"].startswith("ACT-")
    assert a["duration_days"] == 9  # 10-1

    # update — change dates, duration auto-recomputes when blank
    r = session.put(f"{API_URL}/api/proj-phase2/activities/{aid}",
                     json={"name": "Mobilization", "start_date": "2026-04-01", "end_date": "2026-04-15",
                           "status": "in_progress", "progress_pct": 50},
                     timeout=10)
    assert r.status_code == 200
    assert r.json()["duration_days"] == 14

    # invalid status
    r = session.put(f"{API_URL}/api/proj-phase2/activities/{aid}",
                     json={"name": "x", "status": "bogus", "predecessor_ids": []},
                     timeout=10)
    assert r.status_code == 400

    # delete
    r = session.delete(f"{API_URL}/api/proj-phase2/activities/{aid}", timeout=10)
    assert r.status_code == 200


def test_activity_predecessor_cleanup_on_delete(session, project):
    pid = project["id"]
    a = session.post(f"{API_URL}/api/proj-phase2/activities/{pid}",
                      json={"name": "Pred A"}, timeout=10).json()
    b = session.post(f"{API_URL}/api/proj-phase2/activities/{pid}",
                      json={"name": "Pred B"}, timeout=10).json()
    c = session.post(f"{API_URL}/api/proj-phase2/activities/{pid}",
                      json={"name": "Dependent C", "predecessor_ids": [a["id"], b["id"]]},
                      timeout=10).json()
    assert sorted(c["predecessor_ids"]) == sorted([a["id"], b["id"]])
    # delete A → C's predecessor list must drop A
    session.delete(f"{API_URL}/api/proj-phase2/activities/{a['id']}", timeout=10)
    refreshed = next(x for x in session.get(f"{API_URL}/api/proj-phase2/activities/{pid}", timeout=10).json()
                     if x["id"] == c["id"])
    assert a["id"] not in refreshed["predecessor_ids"]
    # cleanup
    session.delete(f"{API_URL}/api/proj-phase2/activities/{b['id']}", timeout=10)
    session.delete(f"{API_URL}/api/proj-phase2/activities/{c['id']}", timeout=10)


# ─── Resources ────────────────────────────────────────────────────────
def test_resources_manpower(session, project):
    pid = project["id"]
    # pick any designation if available, else create minimal
    desigs = session.get(f"{API_URL}/api/hr1/designations", timeout=10).json()
    if not desigs:
        d = session.post(f"{API_URL}/api/hr1/designations",
                          json={"code": f"DSG{secrets.token_hex(2)}", "name": "Test Welder", "active": True},
                          timeout=10).json()
        desigs = [d]
    dg = desigs[0]
    r = session.post(f"{API_URL}/api/proj-phase2/resources/{pid}",
                      json={"resource_type": "manpower", "designation_id": dg["id"],
                            "count_required": 5, "mandays": 30, "daily_rate": 800},
                      timeout=10)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["designation_name"] == dg["name"]  # auto-enriched
    assert res["total_cost"] == 30 * 800  # 24000

    # list filtered by type
    rows = session.get(f"{API_URL}/api/proj-phase2/resources/{pid}?type=manpower", timeout=10).json()
    assert any(x["id"] == res["id"] for x in rows)

    # update — total recomputes
    r = session.put(f"{API_URL}/api/proj-phase2/resources/{res['id']}",
                     json={"resource_type": "manpower", "designation_id": dg["id"],
                           "count_required": 10, "mandays": 30, "daily_rate": 1000},
                     timeout=10)
    assert r.status_code == 200
    # cleanup
    session.delete(f"{API_URL}/api/proj-phase2/resources/{res['id']}", timeout=10)


def test_resources_material_subcontract_and_summary(session, project):
    pid = project["id"]
    items = session.get(f"{API_URL}/api/procurement/master/items", timeout=10).json()
    vendors = session.get(f"{API_URL}/api/vendors", timeout=10).json()
    if not items or not vendors:
        pytest.skip("Seed data for items/vendors required for this test")

    ids_to_clean = []

    # material
    r = session.post(f"{API_URL}/api/proj-phase2/resources/{pid}",
                      json={"resource_type": "material", "item_id": items[0]["id"],
                            "quantity": 100, "unit_rate": 50, "source": "purchase"},
                      timeout=10)
    assert r.status_code == 200, r.text
    mat = r.json()
    ids_to_clean.append(mat["id"])
    assert mat["item_name"] == items[0]["name"]
    assert mat["total_cost"] == 100 * 50

    # tools
    r = session.post(f"{API_URL}/api/proj-phase2/resources/{pid}",
                      json={"resource_type": "tools", "tool_name": "Welding Machine",
                            "count_required": 2, "days": 10, "daily_rate": 500,
                            "tool_owned_or_rented": "rented"},
                      timeout=10)
    assert r.status_code == 200
    tool = r.json()
    ids_to_clean.append(tool["id"])
    assert tool["total_cost"] == 2 * 10 * 500

    # subcontract
    r = session.post(f"{API_URL}/api/proj-phase2/resources/{pid}",
                      json={"resource_type": "subcontract", "vendor_id": vendors[0]["id"],
                            "scope": "Painting works", "basis": "lumpsum", "value": 25000},
                      timeout=10)
    assert r.status_code == 200
    sub = r.json()
    ids_to_clean.append(sub["id"])
    assert sub["vendor_name"] == vendors[0]["name"]
    assert sub["total_cost"] == 25000

    # summary aggregates per type
    s = session.get(f"{API_URL}/api/proj-phase2/resources/{pid}/summary", timeout=10).json()
    assert s["material"] >= 5000
    assert s["tools"] >= 10000
    assert s["subcontract"] >= 25000
    assert s["grand_total"] >= s["material"] + s["tools"] + s["subcontract"] - 1

    for rid in ids_to_clean:
        session.delete(f"{API_URL}/api/proj-phase2/resources/{rid}", timeout=10)
