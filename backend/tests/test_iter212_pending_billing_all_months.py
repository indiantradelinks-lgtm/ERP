"""Iter 212 — Pending Billing Report: All-Months view + filtered Excel/CSV/PDF exports."""
import io
import os

import pytest
import requests
from openpyxl import load_workbook

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


def _report(s, **params):
    r = s.get(f"{API}/billing/pending-report", params=params, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()


def test_all_months_view(s):
    d = _report(s, month="all")
    assert d["month"] == "all"
    assert d["rows"], "expected projects"
    monthly = [r for r in d["rows"] if r["billing_mode"] == "monthly"]
    for r in monthly:
        assert "all" not in (r["billing_period"] or ""), r["billing_period"]
        if r["pending_months"]:
            assert r["billing_status"] == "pending"
    for r in d["rows"]:
        assert r["billing_period"] and r["billing_period"] != "all"


def test_single_month_view_still_works(s):
    d = _report(s, month="2026-10")
    assert d["month"] == "2026-10"
    assert d["rows"]


def test_rows_carry_pending_remarks(s):
    d = _report(s, month="all")
    assert "remarks" in d["rows"][0]
    assert any(r["remarks"] for r in d["rows"])
    for r in d["rows"]:
        if r["billing_mode"] == "monthly" and r["pending_months"] and not r["pending_amount"]:
            assert "Monthly amount not set" in r["remarks"]


def test_excel_export_has_remarks_and_respects_filters(s):
    unfiltered = _report(s, month="all")
    filtered = _report(s, month="all", category="amc_arc", status="pending")
    r = s.get(f"{API}/billing/pending-report/export",
              params={"fmt": "xlsx", "month": "all", "category": "amc_arc", "status": "pending"}, timeout=120)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Pending Billing", "Month-wise Pending", "Summary"]
    rows = list(wb["Pending Billing"].iter_rows(values_only=True))
    assert rows[0][-1] == "Pending Remarks"
    assert len(rows) - 1 == len(filtered["rows"])
    assert len(filtered["rows"]) < len(unfiltered["rows"])
    summary = {r[0]: r[1] for r in wb["Summary"].iter_rows(values_only=True) if r[0]}
    assert summary["Billing Month"] == "All Months"
    assert summary["Project Category"] == "amc arc"


def test_csv_export_filtered(s):
    filtered = _report(s, month="all", status="pending")
    r = s.get(f"{API}/billing/pending-report/export",
              params={"fmt": "csv", "month": "all", "status": "pending"}, timeout=120)
    assert r.status_code == 200
    lines = r.text.splitlines()
    assert lines[0].startswith("Pending Billing Report,All Months")
    assert "Billing Status: pending" in lines[1]
    assert lines[3].endswith("Pending Remarks")
    body = lines[4:4 + len(filtered["rows"])]
    assert len(body) == len(filtered["rows"])


def test_pdf_export_filtered(s):
    r = s.get(f"{API}/billing/pending-report/export",
              params={"fmt": "pdf", "month": "all", "status": "pending"}, timeout=180)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000


def test_project_filter_returns_single_project(s):
    code = _report(s, month="all")["rows"][0]["project_code"]
    r = s.get(f"{API}/billing/pending-report/export",
              params={"fmt": "xlsx", "month": "all", "project_code": code}, timeout=120)
    wb = load_workbook(io.BytesIO(r.content))
    rows = list(wb["Pending Billing"].iter_rows(values_only=True))
    assert len(rows) == 2
    assert rows[1][0] == code
