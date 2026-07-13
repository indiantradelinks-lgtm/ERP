"""Regression tests for /api/employees/bulk endpoints.

Verifies:
  1. Template download returns a valid xlsx with the expected sheets and headers.
  2. Editing a single cell results in `updated: 1` and `unchanged: rest`.
  3. A no-op re-upload reports `updated: 0` (diff-aware).
"""
import io
import os

import openpyxl
import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200, r.text
    return s


def test_template_download(session):
    r = session.get(f"{API_URL}/api/employees/bulk/template", timeout=10)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Employees" in wb.sheetnames
    assert "INSTRUCTIONS" in wb.sheetnames
    headers = [c.value for c in wb["Employees"][1]]
    assert headers[0] == "id"
    assert "phone" in headers


def test_diff_aware_import(session):
    r = session.get(f"{API_URL}/api/employees/bulk/template", timeout=10)
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["Employees"]
    headers = [c.value for c in ws[1]]
    if ws.max_row < 2:
        pytest.skip("no employees seeded")
    phone_col = headers.index("phone") + 1
    # Set a unique sentinel
    sentinel = "9000000777"
    ws.cell(row=2, column=phone_col).value = sentinel
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    files = {"file": ("t.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r2 = session.post(f"{API_URL}/api/employees/bulk/import", files=files, timeout=15)
    assert r2.status_code == 200, r2.text
    summary = r2.json()["summary"]
    assert summary["updated"] == 1, summary
    assert summary["unchanged"] == summary["total_rows"] - 1, summary


def test_noop_import(session):
    # Re-download the now-current state and re-upload unchanged
    r = session.get(f"{API_URL}/api/employees/bulk/template", timeout=10)
    files = {"file": ("noop.xlsx", io.BytesIO(r.content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r2 = session.post(f"{API_URL}/api/employees/bulk/import", files=files, timeout=15)
    assert r2.status_code == 200
    summary = r2.json()["summary"]
    assert summary["updated"] == 0, summary
    assert summary["unchanged"] == summary["total_rows"], summary
