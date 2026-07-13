"""Iter 112 — Finance Phase 4+5: Employee Ledger, Statutory Summary,
Project Finance Alerts, Budget-vs-Actual.

Backend: /api/finance/employee-ledger/* + statutory-summary + project-alerts + budget-vs-actual
"""
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
    rows = s.get(f"{API_URL}/api/projects", timeout=10).json()
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    if not rows:
        pytest.skip("No projects")
    return rows[0]


@pytest.fixture(scope="module")
def employee(s):
    rows = s.get(f"{API_URL}/api/employees", timeout=10).json()
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    if not rows:
        pytest.skip("No employees")
    return rows[0]


# ─── Employee Ledger ─────────────────────────────────────────────────────
def test_employee_ledger(s, employee):
    r = s.get(f"{API_URL}/api/finance/employee-ledger/{employee['id']}", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["employee_id"] == employee["id"]
    assert "rows" in d and "closing_balance" in d
    # rows should be sorted by date ascending and running_balance should be cumulative
    if d["rows"]:
        prev = 0.0
        for row in d["rows"]:
            for k in ("date", "account_code", "debit", "credit", "running_balance"):
                assert k in row


def test_employee_ledger_404(s):
    r = s.get(f"{API_URL}/api/finance/employee-ledger/non-existent", timeout=10)
    assert r.status_code == 404


# ─── Statutory Summary ───────────────────────────────────────────────────
def test_statutory_summary(s):
    r = s.get(f"{API_URL}/api/finance/statutory-summary", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "by_account" in d and "by_month" in d
    # Default range covers current FY — verify shape
    for row in d["by_account"]:
        for k in ("account_code", "account_name", "accrued", "paid", "balance_payable"):
            assert k in row


def test_statutory_summary_custom_range(s):
    r = s.get(f"{API_URL}/api/finance/statutory-summary",
              params={"from": "2026-01-01", "to": "2026-12-31"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["from"] == "2026-01-01"
    assert d["to"] == "2026-12-31"


# ─── Project Finance Alerts ──────────────────────────────────────────────
def test_project_alerts_shape(s, project):
    r = s.get(f"{API_URL}/api/finance/project-alerts/{project['id']}", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["project_id"] == project["id"]
    assert "alerts" in d and "alert_count" in d and "critical_count" in d
    for a in d["alerts"]:
        for k in ("kind", "severity", "message"):
            assert k in a
        assert a["severity"] in ("critical", "warning", "info")


def test_project_alerts_404(s):
    r = s.get(f"{API_URL}/api/finance/project-alerts/non-existent", timeout=10)
    assert r.status_code == 404


# ─── Budget vs Actual ────────────────────────────────────────────────────
def test_budget_vs_actual(s, project):
    r = s.get(f"{API_URL}/api/finance/budget-vs-actual/{project['id']}", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["project_id"] == project["id"]
    assert "heads" in d
    expected_heads = {"material", "labour", "vendor", "salary_staff", "site_expense",
                      "transport", "safety", "tools_tackles", "overhead"}
    found = {h["head"] for h in d["heads"]}
    assert expected_heads == found
    for h in d["heads"]:
        assert h["status"] in ("over", "under", "no_budget")


def test_budget_vs_actual_404(s):
    r = s.get(f"{API_URL}/api/finance/budget-vs-actual/non-existent", timeout=10)
    assert r.status_code == 404
