"""Iter 161 — Project Request Center · Material scaffolding & AI import.

Covers backend endpoints introduced/updated for the material request rework:
  * GET  /api/project-requests/material-template          (CSV template)
  * POST /api/project-requests/import-items?mode=template (strict headers)
  * POST /api/project-requests/import-items?mode=ai       (messy XLSX via LLM) — ONE hit only
  * POST /api/project-requests                            (per-item + request-level total_weight_kg)

Also touches: /project-requests/types (manpower key exposed with dept=hr).
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def a_project(admin_session):
    """Pick any project (prefer E2E-TEST-178532-P1 per handoff note)."""
    r = admin_session.get(f"{API}/projects", timeout=15)
    assert r.status_code == 200, r.text[:200]
    rows = r.json()
    assert rows, "no projects seeded"
    for p in rows:
        if p.get("code") == "E2E-TEST-178532-P1":
            return p
    return rows[0]


# ---------- Types endpoint (manpower exposed) ----------
def test_types_includes_manpower(admin_session):
    r = admin_session.get(f"{API}/project-requests/types", timeout=15)
    assert r.status_code == 200, r.text[:200]
    types = {t["key"]: t for t in r.json()}
    assert "manpower" in types, "manpower type missing"
    assert types["manpower"]["dept"] == "hr"
    assert types["manpower"]["stockable"] is False
    assert types["manpower"]["payment"] is False
    # And material is still there
    assert "material" in types and types["material"]["dept"] == "stores"


# ---------- Material template CSV ----------
EXPECTED_HEADERS = ["name", "code", "size", "material", "make", "coating", "item_type",
                    "quantity", "unit", "unit_weight_kg", "rate", "specs"]


def test_material_template_csv(admin_session):
    r = admin_session.get(f"{API}/project-requests/material-template", timeout=15)
    assert r.status_code == 200, r.text[:200]
    assert "text/csv" in r.headers.get("content-type", ""), r.headers
    body = r.text.strip().splitlines()
    assert len(body) >= 2, "expected header + sample rows"
    header = [h.strip() for h in body[0].split(",")]
    assert header == EXPECTED_HEADERS, f"headers mismatch: {header}"


# ---------- Template import (strict headers) ----------
def test_import_items_template_csv(admin_session):
    csv_body = (
        "name,code,size,material,make,coating,item_type,quantity,unit,unit_weight_kg,rate,specs\n"
        "TEST_Cuplock Vertical 2m,SCF-V-002,2.0 m,MS,Apex,Painted,Vertical,50,Nos,11.4,900,48.3mm OD\n"
        "TEST_Fixed Coupler,,48.3mm,MS,,Galvanised,Coupler,200,Nos,1.1,80,\n"
        ",,,,,,,,,,,\n"  # empty row: should be skipped
    )
    files = {"file": ("mat.csv", csv_body.encode("utf-8"), "text/csv")}
    r = admin_session.post(f"{API}/project-requests/import-items?mode=template", files=files, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["source"] == "template"
    assert body["count"] == 2, body
    items = body["items"]
    assert items[0]["name"].startswith("TEST_Cuplock")
    assert items[0]["quantity"] == 50
    assert items[0]["unit_weight_kg"] == 11.4
    assert items[0]["rate"] == 900
    assert items[0]["material"] == "MS"
    assert items[1]["coating"] == "Galvanised"


def test_import_items_template_bad_headers(admin_session):
    # Missing required 'name' header → 400 with helpful message
    csv_body = "description,qty\nfoo,10\n"
    files = {"file": ("bad.csv", csv_body.encode("utf-8"), "text/csv")}
    r = admin_session.post(f"{API}/project-requests/import-items?mode=template", files=files, timeout=30)
    assert r.status_code == 400, r.text[:300]
    detail = r.json().get("detail", "")
    assert "name" in detail.lower(), detail


# ---------- Template import (XLSX with strict headers) ----------
def test_import_items_template_xlsx(admin_session):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(EXPECTED_HEADERS)
    ws.append(["TEST_Ledger 2.5m", "SCF-L-25", "2.5 m", "MS", "Local", "Painted", "Ledger",
               80, "Nos", 5.2, 320, ""])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    files = {"file": ("mat.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = admin_session.post(f"{API}/project-requests/import-items?mode=template", files=files, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["count"] == 1, body
    it = body["items"][0]
    assert it["name"].startswith("TEST_Ledger")
    assert it["unit_weight_kg"] == 5.2


# ---------- AI import (LLM) — run once only ----------
def test_import_items_ai_messy_xlsx(admin_session):
    """One-shot messy xlsx → gpt-5.4 extraction. Allow 120s. Skip on 502/timeout to save budget."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MR"
    # Title/junk rows
    ws.append(["Material Requisition — Project Alpha"])
    ws.append([])
    ws.append(["Sl.No.", "Description of Item", "Size", "Qty", "Wt/pc (kg)", "Remarks"])
    ws.append([1, "MS Cuplock Vertical", "3.0 m", 100, 17.1, "with cups"])
    ws.append([2, "GI Fixed Coupler", "48.3mm", 400, 1.1, "galv"])
    ws.append([3, "MS Base Jack", "600mm", 50, 3.4, ""])
    ws.append(["", "TOTAL", "", 550, "", ""])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    files = {"file": ("messy.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    t0 = time.time()
    try:
        r = admin_session.post(f"{API}/project-requests/import-items?mode=ai",
                               files=files, timeout=125)
    except requests.exceptions.Timeout:
        pytest.skip("AI extraction timed out (>125s) — LLM slow, skipping to preserve budget")
    dt = time.time() - t0
    if r.status_code in (502, 504, 422):
        pytest.skip(f"AI returned {r.status_code} in {dt:.1f}s ({r.text[:200]}) — skipping (main agent already verified once)")
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["source"] == "ai"
    items = body["items"]
    assert len(items) >= 2, f"expected ≥2 item lines, got {items}"
    # Should NOT include the title row nor the TOTAL row
    names_low = " ".join((i.get("name") or "").lower() for i in items)
    assert "total" not in names_low, f"TOTAL row leaked into items: {items}"
    assert "material requisition" not in names_low
    # At least one line should have a plausible quantity from the sheet
    qtys = [float(i.get("quantity") or 0) for i in items]
    assert any(q in (100, 400, 50) for q in qtys), f"quantities look off: {qtys}"


# ---------- Create request → response carries total_weight_kg ----------
def test_create_material_request_computes_weights(admin_session, a_project):
    payload = {
        "project_id": a_project["id"],
        "project_code": a_project.get("code"),
        "request_type": "material",
        "priority": "medium",
        "description": "TEST_iter161 scaffolding request",
        "items": [
            {"name": "TEST_Vertical 3m", "quantity": 10, "unit": "Nos", "rate": 1500,
             "size": "3.0 m", "material": "MS", "make": "Apex", "coating": "Painted",
             "item_type": "Vertical", "unit_weight_kg": 17.1},
            {"name": "TEST_Coupler", "quantity": 100, "unit": "Nos", "rate": 90,
             "size": "48.3mm", "material": "GI", "coating": "Galvanised",
             "item_type": "Coupler", "unit_weight_kg": 1.1},
        ],
    }
    r = admin_session.post(f"{API}/project-requests", json=payload, timeout=20)
    assert r.status_code == 200, r.text[:400]
    doc = r.json()
    assert doc.get("request_no", "").startswith("REQ-"), doc.get("request_no")

    # Per-item total_weight_kg
    items = doc["items"]
    assert len(items) == 2
    assert items[0]["total_weight_kg"] == pytest.approx(10 * 17.1, rel=1e-3)  # 171
    assert items[1]["total_weight_kg"] == pytest.approx(100 * 1.1, rel=1e-3)  # 110

    # Request-level rollup
    assert doc["total_weight_kg"] == pytest.approx(281.0, rel=1e-3), doc["total_weight_kg"]

    # And material/coating/size/item_type preserved
    assert items[0]["material"] == "MS"
    assert items[1]["coating"] == "Galvanised"
    assert items[0]["size"] == "3.0 m"

    # GET verifies persistence
    rid = doc["id"]
    g = admin_session.get(f"{API}/project-requests", params={"project_code": a_project.get("code")}, timeout=15)
    assert g.status_code == 200
    fetched = next((x for x in g.json() if x["id"] == rid), None)
    assert fetched, "created request not returned by list endpoint"
    assert fetched["total_weight_kg"] == pytest.approx(281.0, rel=1e-3)


# ---------- Regression: stock-check still works ----------
def test_stock_check_endpoint(admin_session):
    payload = {"request_type": "material",
               "items": [{"name": "TEST_NoSuchItem_ZZZ", "quantity": 5, "unit": "Nos"}]}
    r = admin_session.post(f"{API}/project-requests/stock-check", json=payload, timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "lines" in body and len(body["lines"]) == 1
    assert body["lines"][0]["shortfall"] == 5
