"""Iter 213 — Vendor Bill advance / part payment against the same invoice."""
import os

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
INVOICE_NO = "ITER213-ADV-PAY"


@pytest.fixture(scope="module")
def db():
    return MongoClient("mongodb://localhost:27017")["erp_database"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def grn(s):
    rows = s.get(f"{API}/payables/reports/grn-pending-invoice", timeout=60).json().get("rows") or []
    if not rows:
        pytest.skip("no GRN pending invoice in this environment")
    g = rows[0]["grn_number"]
    return s.get(f"{API}/payables/grn-prefill", params={"grn_number": g}, timeout=60).json() | {"grn_number": g}


@pytest.fixture(scope="module")
def bill(s, grn, db):
    body = {
        "vendor_name": grn["vendor_name"], "vendor_id": grn.get("vendor_id"), "bank_verified": True,
        "po_number": grn.get("po_number"), "grn_number": grn["grn_number"], "grn_id": grn.get("grn_id"),
        "project_code": grn.get("project_code"), "invoice_no": INVOICE_NO, "invoice_date": "2026-10-23",
        "expense_category": "material", "gst_rate": 0, "due_days": 30,
        "lines": [{"description": "advance pay test", "quantity": 1, "unit": "Nos", "rate": 1000, "gst_pct": 0}],
        "advance_payment": {"amount": 250, "payment_date": "2026-10-23", "mode": "NEFT",
                            "utr": "ITER213ADV", "remarks": "25% advance"},
    }
    r = s.post(f"{API}/payables/vendor-bills", json=body, timeout=90)
    assert r.status_code == 200, r.text
    b = r.json()
    yield b
    ids = [p["id"] for p in db.vendor_payments.find({"bill_ids": b["id"]}, {"id": 1})]
    db.journal_entries.delete_many({"source_id": {"$in": ids}})
    db.vendor_payments.delete_many({"bill_ids": b["id"]})
    db.vendor_bills.delete_one({"id": b["id"]})


def test_advance_recorded_at_bill_creation(bill):
    assert bill["paid_amount"] == 250
    assert bill["outstanding"] == 750
    assert bill["payment_status"] == "advance_paid"
    assert bill["advance_payment_no"].startswith("VPAY-")
    assert bill["status"] == "draft", "an advance must not short-circuit the approval chain"


def test_history_shows_the_advance(s, bill):
    d = s.get(f"{API}/payables/vendor-bills/{bill['id']}/payments", timeout=60).json()
    assert d["invoice_total"] == 1000
    assert d["paid_amount"] == 250 and d["outstanding"] == 750
    assert d["payment_status"] == "advance_paid"
    assert len(d["payments"]) == 1
    p = d["payments"][0]
    assert p["payment_kind"] == "advance" and p["amount"] == 250 and p["outstanding_after"] == 750


def test_second_payment_is_partially_paid_and_reuses_the_bill(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payments",
               json={"amount": 250, "mode": "UPI", "remarks": "instalment 2"}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["payment"]["payment_kind"] == "part"
    assert d["bill"]["paid_amount"] == 500
    assert d["bill"]["outstanding"] == 500
    assert d["bill"]["payment_status"] == "partially_paid"
    bills = s.get(f"{API}/payables/vendor-bills", params={"limit": 500}, timeout=60).json()
    rows = bills.get("rows", bills) if isinstance(bills, dict) else bills
    assert len([x for x in rows if x.get("invoice_no") == INVOICE_NO]) == 1, "no duplicate bill may be created"


def test_overpayment_is_blocked(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payments", json={"amount": 5000}, timeout=60)
    assert r.status_code == 400
    assert "exceeds the outstanding balance" in r.json()["detail"]


def test_zero_payment_is_blocked(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payments", json={"amount": 0}, timeout=60)
    assert r.status_code == 400


def test_edit_cannot_drop_net_below_amount_already_paid(s, bill, grn):
    body = {
        "vendor_name": grn["vendor_name"], "bank_verified": True, "po_number": grn.get("po_number"),
        "grn_number": grn["grn_number"], "invoice_no": INVOICE_NO, "invoice_date": "2026-10-23",
        "expense_category": "material", "gst_rate": 0, "due_days": 30,
        "lines": [{"description": "reduced", "quantity": 1, "unit": "Nos", "rate": 100, "gst_pct": 0}],
    }
    r = s.put(f"{API}/payables/vendor-bills/{bill['id']}", json=body, timeout=60)
    assert r.status_code == 400
    assert "already been paid" in r.json()["detail"]


def test_final_payment_marks_fully_paid(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payments",
               json={"amount": 500, "mode": "RTGS", "utr": "ITER213FINAL"}, timeout=90)
    assert r.status_code == 200, r.text
    assert r.json()["bill"]["payment_status"] == "fully_paid"
    assert r.json()["bill"]["outstanding"] == 0
    d = s.get(f"{API}/payables/vendor-bills/{bill['id']}/payments", timeout=60).json()
    assert len(d["payments"]) == 3
    assert [p["outstanding_after"] for p in d["payments"]] == [750, 500, 0]
