"""Iter 114 — Finance Phase 7: Management Dashboard + Cash Flow Forecast."""
import os, pytest, requests

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return sess


def test_dashboard_summary(s):
    r = s.get(f"{API_URL}/api/finance/dashboard/summary", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("as_of", "receivable", "payable", "balances", "this_month",
              "net_cash_position", "pending_approvals", "statutory_payable"):
        assert k in d
    for k in ("total", "overdue"):
        assert k in d["receivable"]
        assert k in d["payable"]
    for k in ("bank", "cash", "total"):
        assert k in d["balances"]
    for k in ("billing", "collection", "expense", "start", "end"):
        assert k in d["this_month"]
    for k in ("client_invoices", "vendor_bills", "journal_entries", "advances", "total"):
        assert k in d["pending_approvals"]
    for k in ("pf", "esic", "tds", "gst_payable", "gst_output", "gst_input"):
        assert k in d["statutory_payable"]


def test_cashflow_forecast(s):
    r = s.get(f"{API_URL}/api/finance/dashboard/cashflow", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("from", "to", "days", "total_expected_inflow", "total_expected_outflow",
              "net_projected", "inflows", "outflows", "timeline"):
        assert k in d
    assert d["days"] == 30
    # inflows/outflows shape
    for r2 in d["inflows"] + d["outflows"]:
        for k in ("date", "kind", "party", "ref", "amount"):
            assert k in r2


def test_cashflow_custom_days(s):
    r = s.get(f"{API_URL}/api/finance/dashboard/cashflow?days=60", timeout=20)
    assert r.status_code == 200
    assert r.json()["days"] == 60


def test_cashflow_days_validation(s):
    r = s.get(f"{API_URL}/api/finance/dashboard/cashflow?days=999", timeout=10)
    assert r.status_code == 422  # > 180 not allowed


def test_cashflow_inflow_amounts_positive(s):
    r = s.get(f"{API_URL}/api/finance/dashboard/cashflow", timeout=20)
    for row in r.json()["inflows"]:
        assert row["amount"] > 0
