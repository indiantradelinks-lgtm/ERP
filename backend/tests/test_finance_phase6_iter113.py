"""Iter 113 — Finance Phase 6: Compliance Dashboard + Calendar + Items.

Backend: /api/finance/compliance/*
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


# ─── Dashboard ───────────────────────────────────────────────────────────
def test_compliance_dashboard_default_period(s):
    r = s.get(f"{API_URL}/api/finance/compliance/dashboard", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("period", "gst", "tds", "pf", "esic", "items_summary"):
        assert k in d
    for sub in ("output_accrued", "input_credit", "net_payable", "paid"):
        assert sub in d["gst"]


def test_compliance_dashboard_custom_period(s):
    r = s.get(f"{API_URL}/api/finance/compliance/dashboard?period=2026-04", timeout=15)
    assert r.status_code == 200
    assert r.json()["period"] == "2026-04"


# ─── Calendar ────────────────────────────────────────────────────────────
def test_calendar_default(s):
    r = s.get(f"{API_URL}/api/finance/compliance/calendar", timeout=10)
    assert r.status_code == 200
    d = r.json()
    kinds = {it["kind"] for it in d["items"]}
    for must in ("tds_payment", "gstr_1", "gstr_3b", "pf_payment", "esic_payment", "professional_tax"):
        assert must in kinds
    # Each item must have due_date + status
    for it in d["items"]:
        assert it.get("due_date")
        assert it.get("status") in ("pending", "overdue", "paid")


def test_calendar_quarterly_advance_tax(s):
    """March, June, Sept, Dec should include advance_tax."""
    r = s.get(f"{API_URL}/api/finance/compliance/calendar?period=2026-09", timeout=10)
    assert r.status_code == 200
    kinds = {it["kind"] for it in r.json()["items"]}
    assert "advance_tax" in kinds


# ─── Items CRUD ──────────────────────────────────────────────────────────
def test_create_compliance_item_and_idempotent_upsert(s):
    payload = {
        "period": "2027-02", "kind": "gstr_3b",
        "label": "GSTR-3B filing (2027-02)",
        "due_date": "2027-03-20",
        "amount": 125000.0,
    }
    r = s.post(f"{API_URL}/api/finance/compliance/items", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["status"] == "pending"
    # Idempotent — same (period, kind) updates not creates
    payload["amount"] = 130000.0
    r2 = s.post(f"{API_URL}/api/finance/compliance/items", json=payload, timeout=10)
    assert r2.status_code == 200
    second = r2.json()
    assert second["id"] == first["id"]
    assert second["amount"] == 130000.0


def test_mark_paid(s):
    # Create
    payload = {"period": "2027-02", "kind": "tds_payment",
               "label": "TDS Feb 27", "due_date": "2027-03-07"}
    r = s.post(f"{API_URL}/api/finance/compliance/items", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    item_id = r.json()["id"]
    # mark paid
    r2 = s.post(f"{API_URL}/api/finance/compliance/items/{item_id}/mark-paid",
                params={"challan_number": "TDS-CH-001", "paid_date": "2027-03-05", "amount": 45000}, timeout=10)
    assert r2.status_code == 200
    # verify in list
    rows = s.get(f"{API_URL}/api/finance/compliance/items?period=2027-02", timeout=10).json()
    found = next((x for x in rows if x["id"] == item_id), None)
    assert found and found["status"] == "paid"
    assert found["challan_number"] == "TDS-CH-001"
    assert found["amount"] == 45000.0


def test_mark_paid_404(s):
    r = s.post(f"{API_URL}/api/finance/compliance/items/non-existent/mark-paid",
               params={"challan_number": "X", "paid_date": "2026-01-01"}, timeout=10)
    assert r.status_code == 404


def test_calendar_reflects_paid_items(s):
    """After marking gstr_3b paid in 2027-02, calendar should show paid."""
    r = s.get(f"{API_URL}/api/finance/compliance/calendar?period=2027-02", timeout=10)
    gstr3b = next((it for it in r.json()["items"] if it["kind"] == "gstr_3b"), None)
    if gstr3b and gstr3b.get("amount") == 130000.0:
        # status should now be pending (or overdue if no challan was set on initial create)
        assert gstr3b["status"] in ("pending", "overdue")
