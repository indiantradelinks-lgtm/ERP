"""Iter 155 — new business-rule guards on raise-pr and close."""
import os, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200
    t = r.json().get("access_token") or r.json().get("token")
    if t:
        s.headers.update({"Authorization": f"Bearer {t}"})
    return s


def _project():
    s = _login("admin@erp.com", "Admin@123")
    r = s.get(f"{API}/projects", timeout=30).json()
    rows = r if isinstance(r, list) else r.get("items", [])
    for p in rows:
        if p.get("code") == "PRJ-2025-01":
            return p["code"]
    return rows[0]["code"]


def test_raise_pr_blocked_when_pending_approval():
    admin = _login("admin@erp.com", "Admin@123")
    pm = _login("test_pm@erp.com", "PM@12345")
    pc = _project()
    r = pm.post(f"{API}/project-requests", json={
        "project_code": pc, "request_type": "material",
        "description": "TEST_iter155 pending pr",
        "items": [{"name": "ZZZ_UnknownX", "quantity": 5, "rate": 10}]
    }, timeout=30)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert r.json()["status"] == "pending_approval"
    bad = admin.post(f"{API}/project-requests/{rid}/raise-pr", timeout=30)
    assert bad.status_code == 400, f"expected 400 got {bad.status_code} {bad.text[:200]}"
    # cleanup
    admin.delete(f"{API}/project-requests/{rid}", timeout=30)


def test_close_blocked_when_pending_approval():
    admin = _login("admin@erp.com", "Admin@123")
    pm = _login("test_pm@erp.com", "PM@12345")
    pc = _project()
    r = pm.post(f"{API}/project-requests", json={
        "project_code": pc, "request_type": "fuel", "vehicle_ref": "HR26DK8337", "amount": 200,
        "description": "TEST_iter155 close pending"}, timeout=30)
    assert r.status_code == 200
    rid = r.json()["id"]
    bad = admin.post(f"{API}/project-requests/{rid}/close", timeout=30)
    assert bad.status_code == 400
    admin.delete(f"{API}/project-requests/{rid}", timeout=30)


def test_close_blocked_when_rejected():
    admin = _login("admin@erp.com", "Admin@123")
    pm = _login("test_pm@erp.com", "PM@12345")
    dh = _login("depthead.ops@erp.com", "DeptHead@123")
    pc = _project()
    r = pm.post(f"{API}/project-requests", json={
        "project_code": pc, "request_type": "fuel", "vehicle_ref": "HR26DK8337", "amount": 300,
        "description": "TEST_iter155 rejected close"}, timeout=30)
    assert r.status_code == 200
    rid = r.json()["id"]
    j = dh.post(f"{API}/project-requests/{rid}/reject", json={"remarks": "nope"}, timeout=30)
    assert j.status_code == 200 and j.json()["status"] == "rejected"
    bad = admin.post(f"{API}/project-requests/{rid}/close", timeout=30)
    assert bad.status_code == 400
    admin.delete(f"{API}/project-requests/{rid}", timeout=30)
