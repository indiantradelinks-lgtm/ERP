"""Iter 219 — pending payment raised from the Vendor Bill Payments popup must
land in Accounts → Payment Processing."""
import os

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
INVOICE_NO = "ITER219-PENDING-PAY"


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


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
        "lines": [{"description": "pending pay routing test", "quantity": 1, "unit": "Nos", "rate": 1000, "gst_pct": 0}],
    }
    r = s.post(f"{API}/payables/vendor-bills", json=body, timeout=90)
    assert r.status_code == 200, r.text
    b = r.json()
    yield b
    reqs = [x["id"] for x in db.project_requests.find({"source_id": b["id"]}, {"id": 1})]
    db.payment_verifications.delete_many({"request_id": {"$in": reqs}})
    db.project_requests.delete_many({"source_id": b["id"]})
    ids = [p["id"] for p in db.vendor_payments.find({"bill_ids": b["id"]}, {"id": 1})]
    db.journal_entries.delete_many({"source_id": {"$in": ids}})
    db.vendor_payments.delete_many({"bill_ids": b["id"]})
    db.vendor_bills.delete_one({"id": b["id"]})


def test_history_starts_with_nothing_pending(s, bill):
    d = s.get(f"{API}/payables/vendor-bills/{bill['id']}/payments", timeout=60).json()
    assert d["outstanding"] == 1000
    assert d["pending_requests"] == [] and d["pending_amount"] == 0
    assert d["payable_now"] == 1000


def test_pending_payment_appears_in_payment_processing(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payment-requests",
               json={"amount": 400, "remarks": "instalment 1"}, timeout=90)
    assert r.status_code == 200, r.text
    req = r.json()["request"]
    assert req["is_payment"] is True and req["status"] == "with_dept"
    assert req["est_value"] == 400
    assert req["source"] == "accounts_vendor_bill" and req["source_id"] == bill["id"]

    queue = s.get(f"{API}/accounts/payment-queue", timeout=90).json()
    row = next((q for q in queue if q["id"] == req["id"]), None)
    assert row, "newly raised payment request must show in the Payment Processing queue"
    assert row["pay_stage"] == "pending_verification"
    assert row["vendor"] == bill["vendor_name"]
    assert row["est_value"] == 400


def test_history_reflects_the_pending_request(s, bill):
    d = s.get(f"{API}/payables/vendor-bills/{bill['id']}/payments", timeout=60).json()
    assert d["pending_amount"] == 400
    assert d["payable_now"] == 600
    assert d["pending_requests"][0]["stage"] == "pending_verification"
    assert d["paid_amount"] == 0, "a pending request must not mark the bill as paid"


def test_second_instalment_gets_its_own_request(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payment-requests",
               json={"amount": 600}, timeout=90)
    assert r.status_code == 200, r.text
    assert r.json()["request"]["request_no"] != bill["bill_no"], "second request needs a distinct number"
    d = s.get(f"{API}/payables/vendor-bills/{bill['id']}/payments", timeout=60).json()
    assert len(d["pending_requests"]) == 2
    assert d["pending_amount"] == 1000 and d["payable_now"] == 0


def test_request_beyond_outstanding_is_blocked(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payment-requests",
               json={"amount": 100}, timeout=60)
    assert r.status_code == 400
    assert "awaiting payment processing" in r.json()["detail"]


def test_zero_amount_is_blocked(s, bill):
    r = s.post(f"{API}/payables/vendor-bills/{bill['id']}/payment-requests",
               json={"amount": 0}, timeout=60)
    assert r.status_code == 400


# ─── Full loop: raise → verify → mark paid → bill history stays in sync ───
INVOICE_NO_2 = "ITER219-FULL-LOOP"


@pytest.fixture(scope="module")
def bill2(s, grn, db):
    body = {
        "vendor_name": grn["vendor_name"], "vendor_id": grn.get("vendor_id"), "bank_verified": True,
        "po_number": grn.get("po_number"), "grn_number": grn["grn_number"], "grn_id": grn.get("grn_id"),
        "project_code": grn.get("project_code"), "invoice_no": INVOICE_NO_2, "invoice_date": "2026-10-23",
        "expense_category": "material", "gst_rate": 0, "due_days": 30,
        "lines": [{"description": "full loop test", "quantity": 1, "unit": "Nos", "rate": 1000, "gst_pct": 0}],
    }
    r = s.post(f"{API}/payables/vendor-bills", json=body, timeout=90)
    assert r.status_code == 200, r.text
    b = r.json()
    yield b
    reqs = [x["id"] for x in db.project_requests.find({"source_id": b["id"]}, {"id": 1})]
    db.journal_entries.delete_many({"source_id": {"$in": reqs}})
    db.payment_verifications.delete_many({"request_id": {"$in": reqs}})
    db.project_requests.delete_many({"source_id": b["id"]})
    ids = [p["id"] for p in db.vendor_payments.find({"bill_ids": b["id"]}, {"id": 1})]
    db.journal_entries.delete_many({"source_id": {"$in": ids}})
    db.vendor_payments.delete_many({"bill_ids": b["id"]})
    db.vendor_bills.delete_one({"id": b["id"]})


@pytest.fixture(scope="module")
def loop_request(s, bill2):
    r = s.post(f"{API}/payables/vendor-bills/{bill2['id']}/payment-requests",
               json={"amount": 400, "remarks": "loop"}, timeout=90)
    assert r.status_code == 200, r.text
    return r.json()["request"]


def test_verify_cannot_exceed_the_requested_amount(s, loop_request, bill2):
    r = s.post(f"{API}/accounts/payment-queue/{loop_request['id']}/verify",
               json={"decision": "verified", "vendor_name": bill2["vendor_name"],
                     "vendor_account_no": "000111222333", "ifsc": "ICIC0000001",
                     "invoice_no": INVOICE_NO_2, "verified_amount": 900}, timeout=60)
    assert r.status_code == 400
    assert "cannot exceed the requested" in r.json()["detail"]


def test_paid_through_payment_processing_syncs_the_bill(s, loop_request, bill2, db):
    v = s.post(f"{API}/accounts/payment-queue/{loop_request['id']}/verify",
               json={"decision": "verified", "vendor_name": bill2["vendor_name"],
                     "vendor_account_no": "000111222333", "ifsc": "ICIC0000001",
                     "invoice_no": INVOICE_NO_2, "verified_amount": 400}, timeout=60)
    assert v.status_code == 200, v.text
    mp = s.post(f"{API}/accounts/payment-queue/{loop_request['id']}/mark-paid",
                json={"utr_no": "ITER219UTR", "paid_date": "2026-10-27"}, timeout=90)
    assert mp.status_code == 200, mp.text

    d = s.get(f"{API}/payables/vendor-bills/{bill2['id']}/payments", timeout=60).json()
    assert d["paid_amount"] == 400 and d["outstanding"] == 600
    assert d["payment_status"] in ("advance_paid", "partially_paid")
    assert len(d["payments"]) == 1
    assert d["payments"][0]["utr"] == "ITER219UTR" and d["payments"][0]["amount"] == 400
    assert d["pending_requests"] == [] and d["payable_now"] == 600

    doc = db.vendor_bills.find_one({"id": bill2["id"]}, {"_id": 0, "status": 1, "paid_amount": 1})
    assert doc["paid_amount"] == 400
    assert doc["status"] == "draft", "a payment release must not short-circuit the approval chain"


def test_already_paid_route_respects_a_queued_request(s, bill2):
    q = s.post(f"{API}/payables/vendor-bills/{bill2['id']}/payment-requests",
               json={"amount": 300}, timeout=90)
    assert q.status_code == 200, q.text
    r = s.post(f"{API}/payables/vendor-bills/{bill2['id']}/payments",
               json={"amount": 600, "mode": "NEFT", "utr": "ITER219DOUBLE"}, timeout=60)
    assert r.status_code == 400
    assert "awaiting release in Payment Processing" in r.json()["detail"]
    ok = s.post(f"{API}/payables/vendor-bills/{bill2['id']}/payments",
                json={"amount": 300, "mode": "NEFT", "utr": "ITER219OK"}, timeout=90)
    assert ok.status_code == 200, ok.text
    assert ok.json()["bill"]["paid_amount"] == 700
