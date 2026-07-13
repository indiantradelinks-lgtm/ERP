"""Iter 98 — Extra coverage for P&O Phase 2 Round 1 endpoints.

Covers gaps not in test_proj_phase2_boq_planning_iter98.py:
  - GET /boqs filtering by project_id and status
  - DELETE line recomputes totals
  - DELETE boq cascades to lines
  - GET /boqs/template route-ordering (must NOT 404 — was a known bug)
  - planning idempotency / draft fields
  - import with ?replace=true wipes first
"""
import io
import os

import pytest
import requests
from openpyxl import Workbook


API_URL = os.environ.get("REACT_APP_BACKEND_URL") or os.popen(
    "grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2"
).read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def project(s):
    rows = s.get(f"{API_URL}/api/projects", timeout=10).json()
    assert rows
    return rows[0]


# ── Template route-ordering bug regression ────────────────────────────
def test_template_not_treated_as_id(s):
    """GET /boqs/template must not be matched by GET /boqs/{boq_id}"""
    r = s.get(f"{API_URL}/api/proj-phase2/boqs/template", timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")


# ── Planning GET draft (no persistence) ───────────────────────────────
def test_planning_get_returns_draft_without_persist(s, project):
    # use a project for which planning may not exist — but DB shared; check is_new toggling
    r = s.get(f"{API_URL}/api/proj-phase2/planning/{project['id']}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["project_id"] == project["id"]
    assert d.get("project_code") == project.get("code")
    assert "milestones" in d and isinstance(d["milestones"], list)


def test_planning_invalid_project_returns_404(s):
    r = s.get(f"{API_URL}/api/proj-phase2/planning/nonexistent-pid-xyz", timeout=10)
    assert r.status_code == 404


# ── BOQ list filtering ────────────────────────────────────────────────
def test_boq_list_filters_by_project_and_status(s, project):
    pid = project["id"]
    # create draft
    r = s.post(f"{API_URL}/api/proj-phase2/boqs",
               json={"project_id": pid, "title": "Filter test", "tax_rate": 18},
               timeout=10)
    assert r.status_code == 200
    bid = r.json()["id"]

    try:
        r2 = s.get(f"{API_URL}/api/proj-phase2/boqs?project_id={pid}&status=draft", timeout=10)
        assert r2.status_code == 200
        rows = r2.json()
        assert any(b["id"] == bid for b in rows)
        assert all(b["project_id"] == pid and b["status"] == "draft" for b in rows)

        # filter that should not match
        r3 = s.get(f"{API_URL}/api/proj-phase2/boqs?project_id={pid}&status=cancelled", timeout=10)
        assert r3.status_code == 200
        assert all(b["status"] == "cancelled" for b in r3.json())
    finally:
        s.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)


# ── DELETE line recomputes; DELETE boq cascades ───────────────────────
def test_line_delete_recomputes_totals(s, project):
    pid = project["id"]
    r = s.post(f"{API_URL}/api/proj-phase2/boqs",
               json={"project_id": pid, "title": "Del-line test", "tax_rate": 10},
               timeout=10)
    bid = r.json()["id"]
    try:
        ln = s.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines",
                    json={"description": "X", "uom": "nos", "quantity": 5, "unit_rate": 100},
                    timeout=10).json()
        ln2 = s.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines",
                     json={"description": "Y", "uom": "nos", "quantity": 2, "unit_rate": 50},
                     timeout=10).json()
        # subtotal = 500 + 100 = 600, tax 10% = 60, total 660
        det = s.get(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10).json()
        assert det["subtotal"] == 600
        assert det["total"] == 660

        # delete one
        r2 = s.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines/{ln['id']}", timeout=10)
        assert r2.status_code == 200
        assert r2.json()["_totals"]["subtotal"] == 100

        # delete on missing line -> 404
        r3 = s.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines/nonexistent", timeout=10)
        assert r3.status_code == 404
    finally:
        s.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)


def test_boq_delete_cascades_to_lines(s, project):
    pid = project["id"]
    r = s.post(f"{API_URL}/api/proj-phase2/boqs",
               json={"project_id": pid, "title": "Cascade test", "tax_rate": 0},
               timeout=10)
    bid = r.json()["id"]
    s.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines",
           json={"description": "Z", "uom": "nos", "quantity": 1, "unit_rate": 1},
           timeout=10)
    # confirm one line present
    det = s.get(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10).json()
    assert len(det["lines"]) == 1

    r2 = s.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)
    assert r2.status_code == 200

    # subsequent GET on header → 404
    r3 = s.get(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)
    assert r3.status_code == 404

    # lines list with that boq_id should also 404 (header check)
    r4 = s.get(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines", timeout=10)
    assert r4.status_code == 404


# ── Import replace=true wipes first ──────────────────────────────────
def test_import_replace_wipes_existing(s, project):
    pid = project["id"]
    r = s.post(f"{API_URL}/api/proj-phase2/boqs",
               json={"project_id": pid, "title": "Replace import test", "tax_rate": 0},
               timeout=10)
    bid = r.json()["id"]
    try:
        # Seed 2 manual lines
        s.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/lines/bulk", json={"lines": [
            {"description": "A", "uom": "nos", "quantity": 1, "unit_rate": 10},
            {"description": "B", "uom": "nos", "quantity": 2, "unit_rate": 20},
        ]}, timeout=10)

        # Build small xlsx with 1 line
        wb = Workbook(); ws = wb.active
        ws.append(["Sl No", "Item Code", "Description", "Category", "Scope Type",
                   "UOM", "Quantity", "Unit Rate", "Amount", "WBS Code", "Remarks"])
        ws.append([1, "I1", "Imported only", "Misc", "service", "nos", 3, 30, "", "", ""])
        bio = io.BytesIO(); wb.save(bio); bio.seek(0)
        files = {"file": ("boq.xlsx", bio.getvalue(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

        # replace=true
        r2 = s.post(f"{API_URL}/api/proj-phase2/boqs/{bid}/import?replace=true",
                    files=files, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["inserted"] == 1

        det = s.get(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10).json()
        assert len(det["lines"]) == 1
        assert det["lines"][0]["description"] == "Imported only"
        assert det["subtotal"] == 90
    finally:
        s.delete(f"{API_URL}/api/proj-phase2/boqs/{bid}", timeout=10)


# ── Validation: missing title ──────────────────────────────────────────
def test_boq_create_rejects_missing_title(s, project):
    r = s.post(f"{API_URL}/api/proj-phase2/boqs",
               json={"project_id": project["id"]}, timeout=10)
    assert r.status_code == 422


def test_boq_create_invalid_project_404(s):
    r = s.post(f"{API_URL}/api/proj-phase2/boqs",
               json={"project_id": "nope-pid", "title": "Sample title"}, timeout=10)
    assert r.status_code == 404
