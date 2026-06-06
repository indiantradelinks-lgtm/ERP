"""Iter 60 — Projects & Operations Workflow Phase 1 regression."""
import os, re, requests

def _api():
    txt = open("/app/frontend/.env").read()
    m = re.search(r"^REACT_APP_BACKEND_URL=(.+)$", txt, re.MULTILINE)
    return os.environ.get("REACT_APP_BACKEND_URL") or m.group(1).strip()

BASE = f"{_api()}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return s


def test_full_handover_lifecycle():
    s = _login("admin@erp.com", "Admin@123")
    # Create
    r = s.post(f"{BASE}/ops/handovers", json={
        "project_name": "Pytest Project",
        "client_name": "Pytest Client",
        "contract_value": 100000,
    })
    assert r.status_code == 200, r.text
    h = r.json()
    assert h["status"] == "draft"
    assert h["handover_no"].startswith("CHO-")
    hid = h["id"]
    # Update
    r = s.put(f"{BASE}/ops/handovers/{hid}", json={"site_location": "Test Site"})
    assert r.status_code == 200
    assert r.json()["site_location"] == "Test Site"
    # Submit
    r = s.post(f"{BASE}/ops/handovers/{hid}/submit")
    assert r.status_code == 200
    assert "dept_head" in r.json()["notified_roles"]
    # Verify status flipped
    r = s.get(f"{BASE}/ops/handovers/{hid}")
    assert r.json()["status"] == "submitted"
    # Get a PM to allocate
    pmu = s.get(f"{BASE}/ops/assignable-users").json()["project_manager"]
    assert len(pmu) > 0, "expected at least 1 project_manager user"
    pmid = pmu[0]["id"]
    # Allocate
    r = s.post(f"{BASE}/ops/handovers/{hid}/allocate", json={
        "project_manager_id": pmid, "department": "Operations", "priority": "high",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["project_id"]
    # Timeline has 3 events
    tl = s.get(f"{BASE}/ops/handovers/{hid}/timeline").json()
    events = [t["event"] for t in tl]
    assert "created" in events
    assert "submitted" in events
    assert "allocated" in events


def test_dup_wo_blocks():
    s = _login("admin@erp.com", "Admin@123")
    wo = f"WO/PYTEST/{os.urandom(4).hex()}"
    payload = {"project_name": "Alpha", "client_name": "Beta", "contract_value": 1, "work_order_number": wo}
    r1 = s.post(f"{BASE}/ops/handovers", json=payload)
    assert r1.status_code == 200
    r2 = s.post(f"{BASE}/ops/handovers", json=payload)
    assert r2.status_code == 400
    assert "already used" in r2.json()["detail"]


def test_submit_blocks_missing_fields():
    s = _login("admin@erp.com", "Admin@123")
    r = s.post(f"{BASE}/ops/handovers", json={"project_name": "XY", "client_name": "YZ", "contract_value": 0})
    hid = r.json()["id"]
    r2 = s.post(f"{BASE}/ops/handovers/{hid}/submit")
    assert r2.status_code == 400
    assert "Missing" in r2.json()["detail"]


def test_my_projects():
    s = _login("admin@erp.com", "Admin@123")
    r = s.get(f"{BASE}/ops/my-projects")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
