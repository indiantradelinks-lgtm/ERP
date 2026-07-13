"""Iter 95 regression: Work Orders + Project Settings + Project Audit."""
import os
import secrets

import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return s


def test_work_orders_crud(admin_session):
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    pid = projects[0]["id"] if projects else None
    wo_no = f"PO-RT-{secrets.token_hex(2).upper()}"
    body = {"wo_no": wo_no, "project_id": pid, "value": 250000, "currency": "INR",
            "status": "received", "scope": "Phase 1 release"}
    r = admin_session.post(f"{API_URL}/api/work-orders", json=body, timeout=10)
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    try:
        # List + filter by project
        rows = admin_session.get(f"{API_URL}/api/work-orders?project_id={pid}", timeout=10).json()
        assert any(x["id"] == wid for x in rows)
        # Update
        r = admin_session.put(f"{API_URL}/api/work-orders/{wid}",
            json={**body, "status": "active", "value": 300000}, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "active"
        # Duplicate wo_no → 409
        r = admin_session.post(f"{API_URL}/api/work-orders", json=body, timeout=10)
        assert r.status_code == 409
        # Stats
        s = admin_session.get(f"{API_URL}/api/work-orders/stats", timeout=10).json()
        assert "total" in s and "by_status" in s
    finally:
        admin_session.delete(f"{API_URL}/api/work-orders/{wid}", timeout=10)


def test_project_settings_get_and_put(admin_session):
    r = admin_session.get(f"{API_URL}/api/proj-settings", timeout=10)
    assert r.status_code == 200
    cur = r.json()
    assert "default_ra_bill_frequency" in cur
    r = admin_session.put(f"{API_URL}/api/proj-settings",
        json={**cur, "default_ra_bill_frequency": "fortnightly",
              "notification_emails": ["ops@itlis.in"]}, timeout=10)
    assert r.status_code == 200
    assert r.json()["default_ra_bill_frequency"] == "fortnightly"
    # restore
    admin_session.put(f"{API_URL}/api/proj-settings", json=cur, timeout=10)


def test_project_settings_blocked_for_non_management(admin_session):
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login",
                json={"email": "sales@erp.com", "password": "Sales@123"}, timeout=10)
    if r.status_code != 200:
        pytest.skip("sales user not seeded")
    cur = s.get(f"{API_URL}/api/proj-settings", timeout=10).json()
    r = s.put(f"{API_URL}/api/proj-settings", json=cur, timeout=10)
    assert r.status_code == 403


def test_project_audit_endpoint(admin_session):
    r = admin_session.get(f"{API_URL}/api/project-audit?limit=50", timeout=10)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    for row in rows:
        assert row.get("resource") in {
            "projects", "project_handovers", "work_orders",
            "orders", "enquiries", "quotations",
        }
