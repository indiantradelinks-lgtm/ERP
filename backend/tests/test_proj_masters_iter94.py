"""Iter 94 regression: Projects & Operations Phase 1 Round 1 — Masters."""
import io
import os
import secrets

import openpyxl
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


def test_service_types_auto_seeded(admin_session):
    r = admin_session.get(f"{API_URL}/api/proj-masters/service-types", timeout=10)
    assert r.status_code == 200
    rows = r.json()
    codes = {x["code"] for x in rows}
    # All 7 default services must auto-seed on first call
    assert {"SCF", "PNT", "RTS", "RAC", "MAN", "MAT", "EXEC"}.issubset(codes), codes


def test_service_types_active_only_filter(admin_session):
    r = admin_session.get(f"{API_URL}/api/proj-masters/service-types?active_only=true", timeout=10)
    assert r.status_code == 200
    for row in r.json():
        assert row["is_active"] is True


def test_service_type_crud(admin_session):
    code = f"TST{secrets.token_hex(2).upper()}"
    r = admin_session.post(f"{API_URL}/api/proj-masters/service-types",
        json={"code": code, "name": "Test", "category": "service",
              "billing_uom": "manday", "default_rate": 1000, "sla_days": 5},
        timeout=10)
    assert r.status_code == 200
    sid = r.json()["id"]
    try:
        # Update
        r = admin_session.put(f"{API_URL}/api/proj-masters/service-types/{sid}",
            json={**r.json(), "default_rate": 1500}, timeout=10)
        assert r.status_code == 200
        assert r.json()["default_rate"] == 1500
        # Duplicate code → 409
        r = admin_session.post(f"{API_URL}/api/proj-masters/service-types",
            json={"code": code, "name": "Dup", "billing_uom": "LS", "category": "service"},
            timeout=10)
        assert r.status_code == 409
    finally:
        admin_session.delete(f"{API_URL}/api/proj-masters/service-types/{sid}", timeout=10)


def test_service_type_template_xlsx(admin_session):
    r = admin_session.get(f"{API_URL}/api/proj-masters/service-types/template.xlsx", timeout=10)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "ServiceTypes" in wb.sheetnames
    assert "INSTRUCTIONS" in wb.sheetnames
    headers = [c.value for c in wb["ServiceTypes"][1]]
    assert "code" in headers and "billing_uom" in headers


def test_service_type_stats(admin_session):
    r = admin_session.get(f"{API_URL}/api/proj-masters/service-types/stats", timeout=10)
    assert r.status_code == 200
    rows = r.json()
    assert all("code" in s and "project_count" in s and "enquiry_count" in s for s in rows)


def test_delete_blocked_when_in_use(admin_session):
    """Cannot delete a service type that's referenced by a project."""
    # Seed a service type
    code = f"USE{secrets.token_hex(2).upper()}"
    st = admin_session.post(f"{API_URL}/api/proj-masters/service-types",
        json={"code": code, "name": "InUse", "category": "service", "billing_uom": "LS"},
        timeout=10).json()
    sid = st["id"]
    # Create a project referencing it
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    if not projects:
        admin_session.delete(f"{API_URL}/api/proj-masters/service-types/{sid}")
        pytest.skip("no projects to link")
    p = projects[0]
    admin_session.put(f"{API_URL}/api/projects/{p['id']}", json={**p, "service_type_id": sid}, timeout=10)
    try:
        r = admin_session.delete(f"{API_URL}/api/proj-masters/service-types/{sid}", timeout=10)
        assert r.status_code == 409, r.text
        assert "in use" in r.json().get("detail", "").lower()
    finally:
        # Cleanup
        admin_session.put(f"{API_URL}/api/projects/{p['id']}", json={**p, "service_type_id": None}, timeout=10)
        admin_session.delete(f"{API_URL}/api/proj-masters/service-types/{sid}", timeout=10)
