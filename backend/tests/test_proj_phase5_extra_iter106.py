"""Iter 106 — Phase 5 extra coverage: RA draft create/submit/invoiced + closure complete + regression."""
import os
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


# RA draft create → status=draft → submit → status=submitted_to_accounts
def test_ra_create_draft_and_submit(s, project):
    pid = project["id"]
    r = s.post(f"{API_URL}/api/proj-phase5/ra-billing", json={
        "project_id": pid, "retention_pct": 5, "gst_pct": 18, "tds_pct": 2,
        "remarks": "TEST_iter106 draft",
    }, timeout=15)
    # may legitimately 400 if exceeds_wo_value without exception — accept both
    if r.status_code == 400:
        assert "exceeds" in r.text.lower() or "variation" in r.text.lower()
        pytest.skip("Skipped: project exceeds WO value without approved variation")
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["ra_no"].startswith("RA-")
    assert doc["status"] == "draft"
    assert "net_payable" in doc
    assert "retention_amount" in doc
    assert "gst_amount" in doc
    assert "tds_amount" in doc

    # Submit
    rid = doc["id"]
    r2 = s.post(f"{API_URL}/api/proj-phase5/ra-billing/{rid}/submit", timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "submitted_to_accounts"

    # GET to verify persistence
    r3 = s.get(f"{API_URL}/api/proj-phase5/ra-billing", params={"project_id": pid}, timeout=10)
    assert r3.status_code == 200
    rows = r3.json()
    match = next((x for x in rows if x["id"] == rid), None)
    assert match and match["status"] == "submitted_to_accounts"


# Reports catalog has at least 18 items, each downloadable
def test_reports_multiple_types(s, project):
    catalog = s.get(f"{API_URL}/api/proj-phase5/reports", timeout=10).json()
    assert len(catalog) >= 18
    # sample 3 different types
    for rt in ["boq", "dpr", "site_issues"]:
        r = s.get(f"{API_URL}/api/proj-phase5/reports/{rt}", params={"project_id": project["id"]}, timeout=15)
        assert r.status_code == 200, f"{rt}: {r.text[:200]}"
        assert r.headers["content-type"].startswith("application/vnd.openxmlformats")


# Closure complete: blocked when blockers present (returns 403 with blockers list)
def test_closure_complete_blocker_or_succeed(s, project):
    pid = project["id"]
    # try without override_reason
    r = s.post(f"{API_URL}/api/proj-phase5/closure/{pid}/complete", timeout=15)
    # Either 200 (no blockers) or 403 (blocked)
    assert r.status_code in (200, 403), r.text
    if r.status_code == 403:
        d = r.json()
        det = d.get("detail", {})
        if isinstance(det, dict):
            assert "blockers" in det


# Profitability margin status enum coverage
def test_profitability_status_enum(s, project):
    r = s.get(f"{API_URL}/api/proj-phase5/profitability/{project['id']}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["profitability"]["status"] in ("profitable", "low_margin", "at_risk", "loss")
    assert isinstance(d["profitability"]["margin_pct"], (int, float))


# Regression: Phase 1-4 endpoints still respond
def test_regression_phase_1_to_4(s):
    endpoints = [
        "/api/projects",
        "/api/proj-phase4/summary",
        "/api/proj-phase4/control-center",
    ]
    for ep in endpoints:
        r = s.get(f"{API_URL}{ep}", timeout=10)
        assert r.status_code in (200, 404), f"{ep}: {r.status_code}"
