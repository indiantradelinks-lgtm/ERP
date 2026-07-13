"""Regression tests for Inventory bulk + My Assigned Projects scoping.

Verifies:
  1. Item Master template + diff-aware import.
  2. Item Category Master template + diff-aware import.
  3. /api/ops/my-projects scoping — admin sees all, PM sees only assigned, others see 0.
"""
import io
import os

import openpyxl
import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200, r.text
    return s


# ─────────────────────── Item Master bulk ───────────────────────
def test_items_template(admin_session):
    r = admin_session.get(f"{API_URL}/api/inv-bulk/items/template", timeout=10)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Items" in wb.sheetnames
    assert "INSTRUCTIONS" in wb.sheetnames
    headers = [c.value for c in wb["Items"][1]]
    assert headers[0] == "id"
    assert "name" in headers


def test_items_diff_aware_import(admin_session):
    r = admin_session.get(f"{API_URL}/api/inv-bulk/items/template", timeout=10)
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["Items"]
    if ws.max_row < 2:
        pytest.skip("no items seeded")
    headers = [c.value for c in ws[1]]
    loc_col = headers.index("location") + 1
    ws.cell(row=2, column=loc_col).value = "Regression-Test-Loc-XYZ"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    files = {"file": ("t.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r2 = admin_session.post(f"{API_URL}/api/inv-bulk/items/import", files=files, timeout=15)
    assert r2.status_code == 200, r2.text
    summary = r2.json()["summary"]
    assert summary["updated"] == 1, summary
    assert summary["unchanged"] == summary["total_rows"] - 1, summary


def test_items_noop_import(admin_session):
    r = admin_session.get(f"{API_URL}/api/inv-bulk/items/template", timeout=10)
    files = {"file": ("noop.xlsx", io.BytesIO(r.content),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r2 = admin_session.post(f"{API_URL}/api/inv-bulk/items/import", files=files, timeout=15)
    assert r2.status_code == 200
    summary = r2.json()["summary"]
    assert summary["updated"] == 0, summary
    assert summary["unchanged"] == summary["total_rows"], summary


# ─────────────────────── Item Category Master bulk ───────────────────────
def test_categories_template(admin_session):
    r = admin_session.get(f"{API_URL}/api/inv-bulk/categories/template", timeout=10)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Categories" in wb.sheetnames
    headers = [c.value for c in wb["Categories"][1]]
    assert headers[0] == "id"
    assert "code" in headers and "name" in headers


def test_categories_diff_aware_import(admin_session):
    r = admin_session.get(f"{API_URL}/api/inv-bulk/categories/template", timeout=10)
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["Categories"]
    if ws.max_row < 2:
        pytest.skip("no categories seeded")
    headers = [c.value for c in ws[1]]
    desc_col = headers.index("description") + 1
    ws.cell(row=2, column=desc_col).value = "Regression description XYZ"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    files = {"file": ("c.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r2 = admin_session.post(f"{API_URL}/api/inv-bulk/categories/import", files=files, timeout=15)
    assert r2.status_code == 200
    summary = r2.json()["summary"]
    assert summary["updated"] == 1, summary


# ─────────────────────── My Assigned Projects scoping ───────────────────────
def test_my_projects_admin_sees_all(admin_session):
    r = admin_session.get(f"{API_URL}/api/ops/my-projects", timeout=10)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    # Admin should see at least all handovers — at minimum, the same count
    # the unscoped /ops/handovers returns.
    all_r = admin_session.get(f"{API_URL}/api/ops/handovers", timeout=10).json()
    assert len(rows) == len(all_r), (len(rows), len(all_r))


def test_my_projects_pm_only_own(admin_session):
    # Ensure test_pm@erp.com password reset for the test
    users = admin_session.get(f"{API_URL}/api/auth/users", timeout=10).json()
    pm = next((u for u in users if u.get("email") == "test_pm@erp.com"), None)
    if not pm:
        pytest.skip("test_pm seed not present")
    admin_session.post(f"{API_URL}/api/admin/users/{pm['id']}/reset-password",
                        json={"password": "PM@12345"}, timeout=10)
    s2 = requests.Session()
    r = s2.post(f"{API_URL}/api/auth/login", json={"email": "test_pm@erp.com", "password": "PM@12345"}, timeout=10)
    assert r.status_code == 200, r.text
    pm_uid = r.json()["id"]
    rows = s2.get(f"{API_URL}/api/ops/my-projects", timeout=10).json()
    for row in rows:
        # Every row returned must reference this PM in one of the 3 slots
        assert pm_uid in (row.get("project_manager_id"),
                          row.get("project_coordinator_id"),
                          row.get("reporting_manager_id")), row


def test_my_projects_non_assigned_role_sees_zero(admin_session):
    # safety_officer is neither management nor PM/coordinator → 0 handovers
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login",
                json={"email": "safety@erp.com", "password": "Safety@123"}, timeout=10)
    if r.status_code != 200:
        pytest.skip("safety@erp.com not seeded")
    rows = s.get(f"{API_URL}/api/ops/my-projects", timeout=10).json()
    assert rows == [], rows
