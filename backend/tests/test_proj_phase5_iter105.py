"""Iter 105 — P&O Phase 5 — RA Billing / Profitability / Closure / Handover / Reports / Audit."""
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


def test_ra_billing_computed_returns_structure(s, project):
    r = s.get(f"{API_URL}/api/proj-phase5/ra-billing/{project['id']}/computed", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("project", "work_order_value", "previous_billed", "certified_subtotal",
              "current_billing", "balance_after_billing", "exceeds_wo_value", "rows"):
        assert k in d


def test_profitability_endpoint(s, project):
    r = s.get(f"{API_URL}/api/proj-phase5/profitability/{project['id']}", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "revenue" in d and "cost" in d and "profitability" in d
    assert d["profitability"]["status"] in ("profitable", "low_margin", "at_risk", "loss")


def test_closure_checklist_has_18_items(s, project):
    r = s.get(f"{API_URL}/api/proj-phase5/closure/{project['id']}/checklist", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 18
    assert all("key" in it and "label" in it for it in d["items"])


def test_closure_mark_item_persists_override(s, project):
    pid = project["id"]
    r = s.post(f"{API_URL}/api/proj-phase5/closure/{pid}/mark-item",
                json={"key": "jcc_uploaded", "complete": True, "remarks": "uploaded"}, timeout=10)
    assert r.status_code == 200
    found = next((it for it in r.json()["items"] if it["key"] == "jcc_uploaded"), None)
    assert found and found["complete"] is True

    # unknown key rejected
    r = s.post(f"{API_URL}/api/proj-phase5/closure/{pid}/mark-item",
                json={"key": "bogus", "complete": True}, timeout=10)
    assert r.status_code == 400


def test_handover_and_jcc_flow(s, project):
    pid = project["id"]
    # handover
    r = s.post(f"{API_URL}/api/proj-phase5/handovers/client", json={
        "project_id": pid, "client_representative": "Mr. X",
        "itl_representative": "Mr. Y", "final_acceptance_status": "accepted",
    }, timeout=10)
    assert r.status_code == 200, r.text
    ho = r.json()
    assert ho["handover_no"].startswith("HO-")

    # jcc
    r = s.post(f"{API_URL}/api/proj-phase5/handovers/jcc", json={
        "project_id": pid, "issued_to": "Owner",
        "scope_summary": "All works complete", "defect_liability_period": "12 months",
    }, timeout=10)
    assert r.status_code == 200, r.text
    jcc = r.json()
    assert jcc["jcc_no"].startswith("JCC-")
    assert jcc["status"] == "draft"

    r = s.post(f"{API_URL}/api/proj-phase5/handovers/jcc/{jcc['id']}/issue", timeout=10)
    assert r.status_code == 200 and r.json()["status"] == "issued"


def test_reports_catalog_and_export(s, project):
    r = s.get(f"{API_URL}/api/proj-phase5/reports", timeout=10)
    assert r.status_code == 200
    catalog = r.json()
    assert len(catalog) >= 18
    # download a sample Excel
    r = s.get(f"{API_URL}/api/proj-phase5/reports/project_master", timeout=15)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(r.content) > 200

    # unknown report rejected
    r = s.get(f"{API_URL}/api/proj-phase5/reports/foo", timeout=10)
    assert r.status_code == 400


def test_audit_trail(s, project):
    r = s.get(f"{API_URL}/api/proj-phase5/audit/{project['id']}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d and "count" in d
