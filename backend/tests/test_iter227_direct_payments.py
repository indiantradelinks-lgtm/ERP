"""Iter 227 — Direct Payment Requests for existing service vendors.

raise (Accounts/Proc/Logistics) → edit → Super Admin approve → Payment Processing
queue row → verify → mark paid → request & vendor history reflect it. Also: RBAC,
duplicate guards, eligibility, optional PO link, My Approvals inbox, SR workflow untouched.
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
ENV = dotenv_values("/app/backend/.env")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=60)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def purchase():
    return _login("purchase@erp.com", "Purchase@123")


@pytest.fixture(scope="module")
def sales():
    return _login("sales@erp.com", "Sales@123")


@pytest.fixture(scope="module")
def vendor(admin, mongo):
    """A vendor with a paid service invoice (eligible) — seeded directly."""
    vid = str(uuid.uuid4())
    mongo.vendors.insert_one({"id": vid, "name": f"DP Test Vendor {vid[:6]}", "code": f"DPV{vid[:4]}", "gst": "27AAAAA0000A1Z5",
                              "status": "approved", "bank_accounts": [{"bank_name": "HDFC", "account_no": "1234567890", "ifsc": "HDFC0000001"}],
                              "created_at": "2026-01-01T00:00:00+00:00"})
    po_id = str(uuid.uuid4())
    mongo.svc_pos.insert_one({"id": po_id, "po_no": f"SPO-TEST-{vid[:4]}", "sr_id": "sr-x", "sr_no": "SVC-TEST-1", "vendor_id": vid,
                              "vendor_name": f"DP Test Vendor {vid[:6]}", "status": "issued", "total_value": 50000,
                              "project_code": "PRJ-2025-01", "project_name": "Test Project", "created_at": "2026-02-01T00:00:00+00:00"})
    mongo.svc_invoices.insert_one({"id": str(uuid.uuid4()), "inv_no": f"SVI-TEST-{vid[:4]}", "vendor_id": vid, "po_id": po_id,
                                   "vendor_invoice_no": "V/001", "net_payable": 12000, "invoice_amount": 12000, "status": "paid",
                                   "invoice_date": "2026-03-01", "payment": {"utr_no": "UTR001", "paid_date": "2026-03-10", "paid_at": "2026-03-10T00:00:00+00:00"},
                                   "created_at": "2026-03-01T00:00:00+00:00", "updated_at": "2026-03-10T00:00:00+00:00"})
    yield {"id": vid, "po_id": po_id}
    mongo.vendors.delete_one({"id": vid})
    mongo.svc_pos.delete_one({"id": po_id})
    mongo.svc_invoices.delete_many({"vendor_id": vid})
    for d in mongo.svc_direct_payments.find({"vendor_id": vid}, {"id": 1}):
        mongo.project_requests.delete_many({"source": "service_direct_payment", "source_id": d["id"]})
        mongo.payment_verifications.delete_many({"request_id": {"$in": [r["id"] for r in mongo.project_requests.find({"source_id": d["id"]}, {"id": 1})]}})
    mongo.svc_direct_payments.delete_many({"vendor_id": vid})


@pytest.fixture(scope="module")
def ineligible_vendor(mongo):
    vid = str(uuid.uuid4())
    mongo.vendors.insert_one({"id": vid, "name": f"Never Paid {vid[:6]}", "status": "approved"})
    yield vid
    mongo.vendors.delete_one({"id": vid})


def test_meta_lists_only_vendors_paid_via_service_workflow(admin, vendor, ineligible_vendor):
    m = admin.get(f"{API}/service-direct-payments/meta", timeout=30).json()
    ids = {v["id"] for v in m["vendors"]}
    assert vendor["id"] in ids and ineligible_vendor not in ids
    assert m["can_raise"] is True and m["can_approve"] is True


def test_vendor_summary_autofetches_history_and_last_po(purchase, vendor):
    s = purchase.get(f"{API}/service-direct-payments/vendors/{vendor['id']}/summary", timeout=30).json()
    assert s["vendor"]["gst"] == "27AAAAA0000A1Z5"
    assert s["last_po"]["id"] == vendor["po_id"]
    assert s["last_paid_amount"] == 12000 and s["service_invoices_paid"] == 1
    assert s["vendor"]["bank_accounts"][0]["ifsc"] == "HDFC0000001"


def test_ineligible_vendor_is_rejected(purchase, ineligible_vendor):
    r = purchase.post(f"{API}/service-direct-payments", json={"vendor_id": ineligible_vendor, "invoice_amount": 100}, timeout=30)
    assert r.status_code == 400 and "Service workflow" in r.text


def test_sales_cannot_raise(sales, vendor):
    r = sales.post(f"{API}/service-direct-payments", json={"vendor_id": vendor["id"], "invoice_amount": 100}, timeout=30)
    assert r.status_code == 403


def test_raise_with_warning_and_optional_po(purchase, vendor):
    body = {"vendor_id": vendor["id"], "ref_po_id": vendor["po_id"], "service_period": "2026-11",
            "vendor_invoice_no": "V/NOV-01", "invoice_date": "2026-11-05", "invoice_amount": 15000,
            "tax_amount": 2700, "tds_amount": 300, "description": "Transport Nov"}
    r = purchase.post(f"{API}/service-direct-payments", json=body, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "pending_approval" and d["dp_no"].startswith("SDP")
    assert d["net_payable"] == 17400 and d["payment_amount"] == 17400
    assert d["ref_po_no"] == f"SPO-TEST-{vendor['id'][:4]}" and d["project_code"] == "PRJ-2025-01"
    assert any("exceeds" in w for w in d["warnings"]), "exceeding last paid amount must warn, not block"
    pytest.dp_id = d["id"]


def test_duplicate_invoice_number_blocked(purchase, vendor):
    r = purchase.post(f"{API}/service-direct-payments", json={"vendor_id": vendor["id"], "vendor_invoice_no": "V/NOV-01", "invoice_amount": 10}, timeout=30)
    assert r.status_code in (400, 409) and "already" in r.text
    r = purchase.post(f"{API}/service-direct-payments", json={"vendor_id": vendor["id"], "vendor_invoice_no": "V/001", "invoice_amount": 10}, timeout=30)
    assert r.status_code in (400, 409) and "service invoice" in r.text


def test_no_po_link_and_second_month_allowed(purchase, vendor):
    r = purchase.post(f"{API}/service-direct-payments", json={"vendor_id": vendor["id"], "service_period": "2026-12", "invoice_amount": 5000, "payment_amount": 2500}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["ref_po_id"] is None and r.json()["payment_amount"] == 2500
    pytest.dp2_id = r.json()["id"]
    # a re-submit with the same amount/month (different wording) must be blocked — not just replayed by the dedupe middleware
    r = purchase.post(f"{API}/service-direct-payments", json={"vendor_id": vendor["id"], "service_period": "2026-12", "invoice_amount": 5000, "payment_amount": 2500, "description": "again"}, timeout=30)
    assert r.status_code == 409, "identical open request for the same month must be blocked"


def test_payment_cannot_exceed_net(purchase, vendor):
    r = purchase.post(f"{API}/service-direct-payments", json={"vendor_id": vendor["id"], "invoice_amount": 100, "payment_amount": 150}, timeout=30)
    assert r.status_code == 400 and "exceed" in r.text


def test_edit_amounts_before_approval(purchase, vendor):
    body = {"vendor_id": vendor["id"], "ref_po_id": vendor["po_id"], "service_period": "2026-11", "vendor_invoice_no": "V/NOV-01",
            "invoice_date": "2026-11-05", "invoice_amount": 16000, "tax_amount": 2880, "tds_amount": 320, "payment_amount": 18000}
    r = purchase.put(f"{API}/service-direct-payments/{pytest.dp_id}", json=body, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["net_payable"] == 18560 and r.json()["payment_amount"] == 18000
    assert any(h["action"] == "edited" for h in r.json()["history"])


def test_purchase_cannot_approve_but_super_admin_can(purchase, admin, mongo, vendor):
    r = purchase.post(f"{API}/service-direct-payments/{pytest.dp_id}/action", json={"action": "approve"}, timeout=30)
    assert r.status_code == 403
    inbox = admin.get(f"{API}/my-inbox", timeout=60).json()
    mine = [i for i in inbox["items"] if i["source"] == "service_direct_payment" and i["id"] == pytest.dp_id]
    assert mine and mine[0]["approve_path"].endswith("/inbox-approve") and mine[0]["amount"] == 18000
    r = admin.post(f"{API}{mine[0]['approve_path']}", json={"remarks": "ok"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "payment_pending" and d["approval"]["role"] == "super_admin"
    pr = mongo.project_requests.find_one({"source": "service_direct_payment", "source_id": pytest.dp_id})
    assert pr and pr["is_payment"] and pr["payment_status"] == "payment_pending" and pr["amount"] == 18000
    assert pr["vendor_id"] == vendor["id"] and pr["request_no"] == d["dp_no"]
    pytest.pr_id = pr["id"]


def test_approved_request_visible_in_payment_processing_queue(admin):
    q = admin.get(f"{API}/accounts/payment-queue", timeout=60).json()
    rows = q if isinstance(q, list) else q.get("items") or q.get("rows") or []
    row = next((r for r in rows if r["id"] == pytest.pr_id), None)
    assert row is not None, "approved direct payment must appear in Payment Processing Center"
    assert row["vendor_master"] and row["vendor_master"]["bank"], "vendor bank details must resolve from Vendor Master"


def test_mark_paid_closes_request_and_updates_history(admin, vendor):
    r = admin.post(f"{API}/accounts/payment-queue/{pytest.pr_id}/verify",
                   json={"decision": "verified", "vendor_name": "x", "vendor_account_no": "1234567890", "ifsc": "HDFC0000001", "bank_name": "HDFC", "invoice_no": "V/NOV-01", "verified_amount": 18000}, timeout=30)
    assert r.status_code == 200, r.text
    r = admin.post(f"{API}/accounts/payment-queue/{pytest.pr_id}/mark-paid", json={"utr_no": "UTRDP001", "paid_date": "2026-11-20"}, timeout=30)
    assert r.status_code == 200, r.text
    d = admin.get(f"{API}/service-direct-payments/{pytest.dp_id}", timeout=30).json()
    assert d["status"] == "paid" and d["payment"]["utr_no"] == "UTRDP001"
    hist = admin.get(f"{API}/service-direct-payments/vendors/{vendor['id']}/history", timeout=30).json()
    kinds = {(h["kind"], h["ref"]) for h in hist}
    assert ("direct_payment", d["dp_no"]) in kinds and any(k == "service_invoice" for k, _ in kinds)
    s = admin.get(f"{API}/service-direct-payments/vendors/{vendor['id']}/summary", timeout=30).json()
    assert s["direct_payments_paid"] == 1 and s["last_paid_amount"] == 18000


def test_reject_requires_remarks_and_withdraw_by_requester(admin, purchase, vendor):
    r = admin.post(f"{API}/service-direct-payments/{pytest.dp2_id}/action", json={"action": "reject", "remarks": ""}, timeout=30)
    assert r.status_code == 400
    r = purchase.post(f"{API}/service-direct-payments/{pytest.dp2_id}/action", json={"action": "withdraw", "remarks": "raised by mistake"}, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    r = admin.post(f"{API}/service-direct-payments/{pytest.dp2_id}/action", json={"action": "approve"}, timeout=30)
    assert r.status_code == 400


def test_audit_trail_recorded(mongo):
    acts = {a["action"] for a in mongo.audit_logs.find({"resource": "service_direct_payment", "record_id": pytest.dp_id}, {"action": 1})}
    assert {"svc_direct_payment_create", "svc_direct_payment_update", "svc_direct_payment_approve"} <= acts


def test_service_request_workflow_untouched(admin):
    r = admin.get(f"{API}/service-workflow/meta", timeout=30)
    assert r.status_code == 200 and "role_caps" in r.json()
    r = admin.get(f"{API}/service-workflow/requests", timeout=60)
    assert r.status_code == 200
