"""Iter 98: P&O Phase 2 Round 1 — Project Planning + BOQ endpoints."""
import io
import os
import secrets

import pytest
import requests
from openpyxl import Workbook


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def any_project(admin_session):
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    assert projects, "Need at least one seed project for Phase 2 tests"
    return projects[0]


# ─── Planning ──────────────────────────────────────────────────────────
def test_planning_get_creates_draft(admin_session, any_project):
    pid = any_project["id"]
    r = admin_session.get(f"{API_URL}/api/proj-phase2/planning/{pid}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["project_id"] == pid
    assert d["planning_status"] in ("draft", "approved")


def test_planning_upsert_persists(admin_session, any_project):
    pid = any_project["id"]
    payload = {
        "kickoff_date": "2026-03-01",
        "charter_summary": f"Test charter {secrets.token_hex(3)}",
        "objectives": "Deliver on time, on scope",
        "scope_summary": "Phase 1 scaffolding",
        "milestones": [{"name": "Kickoff", "target_date": "2026-03-01", "status": "pending"}],
        "risks": [{"description": "Weather risk", "severity": "high", "likelihood": "medium", "mitigation": "Plan around monsoon"}],
        "stakeholders": [{"name": "Mr. Owner", "role": "Client PM", "organization": "Acme Ltd"}],
    }
    r = admin_session.put(f"{API_URL}/api/proj-phase2/planning/{pid}", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["charter_summary"] == payload["charter_summary"]
    assert len(d["milestones"]) == 1 and d["milestones"][0]["id"]
    assert len(d["risks"]) == 1


def test_planning_approve_locks(admin_session, any_project):
    pid = any_project["id"]
    # Ensure a record exists
    admin_session.put(f"{API_URL}/api/proj-phase2/planning/{pid}",
                       json={"charter_summary": "ready", "milestones": [], "risks": [], "stakeholders": []},
                       timeout=10)
    r = admin_session.post(f"{API_URL}/api/proj-phase2/planning/{pid}/approve", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["planning_status"] == "approved"
    assert d.get("approved_by")


# ─── BOQ Header + Lines ────────────────────────────────────────────────
def test_boq_full_crud_cycle(admin_session, any_project):
    pid = any_project["id"]
    # 1. create
    r = admin_session.post(f"{API_URL}/api/proj-phase2/boqs",
                            json={"project_id": pid, "title": "Test BOQ", "tax_rate": 18},
                            timeout=10)
    assert r.status_code == 200, r.text
    boq = r.json()
    bid = boq["id"]
    assert boq["boq_no"].startswith("BOQ-")
    assert boq["subtotal"] == 0

    # 2. add line
    r = admin_session.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines",
                            json={"description": "Paint epoxy", "uom": "sqm", "quantity": 100, "unit_rate": 250},
                            timeout=10)
    assert r.status_code == 200, r.text
    line = r.json()
    assert line["amount"] == 25000
    assert line["_totals"]["subtotal"] == 25000
    lid = line["id"]

    # 3. update line
    r = admin_session.put(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines/{lid}",
                          json={"description": "Paint epoxy 2 coats", "uom": "sqm", "quantity": 120, "unit_rate": 250},
                          timeout=10)
    assert r.status_code == 200
    assert r.json()["_totals"]["subtotal"] == 30000

    # 4. detail (header + lines + amounts hydrated)
    r = admin_session.get(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["subtotal"] == 30000
    assert d["tax_amount"] == round(30000 * 0.18, 2)
    assert d["total"] == round(30000 + 30000 * 0.18, 2)
    assert len(d["lines"]) == 1

    # 5. bulk add lines
    r = admin_session.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines/bulk", json={
        "lines": [
            {"description": "Steel pipe 48mm", "uom": "lm", "quantity": 200, "unit_rate": 80},
            {"description": "Couplers", "uom": "nos", "quantity": 500, "unit_rate": 20},
        ]
    }, timeout=10)
    assert r.status_code == 200
    assert r.json()["inserted"] == 2

    # 6. approve
    r = admin_session.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/approve", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    # 7. clean
    r = admin_session.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)
    assert r.status_code == 200


def test_boq_excel_template_download(admin_session):
    r = admin_session.get(f"{API_URL}/api/proj-phase2/boqs/template", timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(r.content) > 100


def test_boq_import_export_roundtrip(admin_session, any_project):
    pid = any_project["id"]
    r = admin_session.post(f"{API_URL}/api/proj-phase2/boqs",
                            json={"project_id": pid, "title": "Excel Import Test", "tax_rate": 18},
                            timeout=10)
    bid = r.json()["id"]

    # Build a small Excel
    wb = Workbook()
    ws = wb.active
    ws.append(["Sl No", "Item Code", "Description", "Category", "Scope Type",
               "UOM", "Quantity", "Unit Rate", "Amount", "WBS Code", "Remarks"])
    ws.append([1, "P001", "Scaffolding erection", "Scaffolding", "service",
               "cum", 10, 1500, "", "WBS-1.1", "demo"])
    ws.append([2, "P002", "Painting", "Painting", "service",
               "sqm", 50, 200, "", "WBS-1.2", ""])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    files = {"file": ("boq.xlsx", bio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = admin_session.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/import", files=files, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["inserted"] == 2
    assert data["_totals"]["subtotal"] == 10 * 1500 + 50 * 200

    # Export must succeed
    r = admin_session.get(f"{API_URL}/api/proj-phase2/boqs/{bid}/export", timeout=15)
    assert r.status_code == 200
    assert len(r.content) > 500

    # Cleanup
    admin_session.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)
