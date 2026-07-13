"""Regression: New Enquiry resource-requirement fields + Enquiries Excel/PDF export."""
import io
import os
import secrets

import openpyxl
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


def _seed_enquiry(session):
    sites = session.get(f"{API_URL}/api/sites", timeout=10).json()
    clients = session.get(f"{API_URL}/api/clients", timeout=10).json()
    body = {
        "client_id": clients[0]["id"],
        "site_id": sites[0]["id"],
        "customer": f"Regression Test {secrets.token_hex(3)}",
        "enquiry_date": "2026-02-17",
        "priority": "medium",
        "rfq_type": ["service"],
        "scope_of_work": "Regression scope",
        "material_requirement": "150 m³ pipes + 80 swivel couplers",
        "manpower_requirement": "8 scaffolders + 2 supervisors for 14 days",
        "expected_value": 100000,
    }
    r = session.post(f"{API_URL}/api/enquiries", json=body, timeout=10)
    assert r.status_code == 200, r.text
    return body, r.json()


def test_new_resource_requirement_fields_persist(session):
    body, created = _seed_enquiry(session)
    try:
        fetched = session.get(f"{API_URL}/api/enquiries/{created['id']}", timeout=10).json()
        assert fetched["material_requirement"] == body["material_requirement"]
        assert fetched["manpower_requirement"] == body["manpower_requirement"]
        # Auto-created quote must inherit them
        quote = session.get(f"{API_URL}/api/quotations/{fetched['quotation_id']}", timeout=10).json()
        assert quote["material_requirement"] == body["material_requirement"]
        assert quote["manpower_requirement"] == body["manpower_requirement"]
    finally:
        session.delete(f"{API_URL}/api/enquiries/{created['id']}", timeout=10)


def test_enquiries_xlsx_export(session):
    body, created = _seed_enquiry(session)
    try:
        r = session.get(f"{API_URL}/api/export/enquiries.xlsx", timeout=15)
        assert r.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb.active
        headers = [c.value for c in ws[5]]
        assert "Material Requirement" in headers
        assert "Manpower Requirement" in headers
        mat_col = headers.index("Material Requirement") + 1
        man_col = headers.index("Manpower Requirement") + 1
        found = False
        for ri in range(6, ws.max_row + 1):
            if body["customer"] in str(ws.cell(row=ri, column=3).value or ""):
                assert ws.cell(row=ri, column=mat_col).value == body["material_requirement"]
                assert ws.cell(row=ri, column=man_col).value == body["manpower_requirement"]
                found = True
                break
        assert found, "newly-created enquiry not present in export"
    finally:
        session.delete(f"{API_URL}/api/enquiries/{created['id']}", timeout=10)


def test_enquiries_pdf_export(session):
    r = session.get(f"{API_URL}/api/export/enquiries.pdf", timeout=20)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
    assert r.content[:4] == b"%PDF", r.content[:20]
