"""Iter 223 — Manager PNV runs the service procurement chain end to end."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
TAG = f"iter223-{uuid.uuid4().hex[:6]}"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    assert r.status_code == 200, f"{email}: {r.text}"
    return s


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def mop():
    return _login("test_mop@erp.com", "Mop@12345")


@pytest.fixture(scope="module")
def pnv():
    return _login("test_pnv@erp.com", "Pnv@12345")


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def vendor_id(admin):
    data = admin.get(f"{API}/vendors?page=1&page_size=5", timeout=60).json()
    rows = data if isinstance(data, list) else data.get("rows", [])
    if not rows:
        pytest.skip("no vendors in this environment")
    return rows[0]["id"]


@pytest.fixture(scope="module")
def srs(mop, db):
    """One billable SR and one Transportation SR, both raised by Manager OP."""
    made = {}
    for key, cat in (("ok", "AMC / Maintenance"), ("excluded", "Transportation")):
        r = mop.post(f"{API}/service-workflow/requests", json={
            "department": "Operations", "service_category": cat, "service_type": TAG,
            "service_description": f"{TAG} {cat}", "site_location": "Goa",
            "priority": "Medium", "submit": True,
            **({"from_location": "A", "to_location": "B"} if cat == "Transportation" else {}),
        }, timeout=60)
        assert r.status_code == 200, r.text
        made[key] = r.json()
    yield made
    ids = [m["id"] for m in made.values()]
    pos = [p["id"] for p in db.svc_pos.find({"sr_id": {"$in": ids}}, {"id": 1})]
    db.svc_invoices.delete_many({"po_id": {"$in": pos}})
    db.svc_srns.delete_many({"po_id": {"$in": pos}})
    db.svc_pos.delete_many({"sr_id": {"$in": ids}})
    db.svc_rfqs.delete_many({"sr_id": {"$in": ids}})
    db.svc_requests.delete_many({"id": {"$in": ids}})


@pytest.fixture(scope="module")
def chain():
    return {}


def test_pnv_meta_grants_the_procurement_capability(pnv):
    caps = pnv.get(f"{API}/service-workflow/meta", timeout=60).json()["role_caps"]
    assert caps["procurement"] is True, "Create RFQ / PO buttons are gated on this"
    assert caps["srn"] is True
    assert caps["sr_approver"] is False, "approval gates stay with the approvers"
    assert caps["accounts"] is False, "the bank release stays with Accounts"


def test_pnv_creates_the_rfq(pnv, srs, vendor_id, chain):
    r = pnv.post(f"{API}/service-workflow/requests/{srs['ok']['id']}/rfq",
                 json={"vendor_ids": [vendor_id], "scope_of_work": f"{TAG} scope"}, timeout=60)
    assert r.status_code == 200, r.text
    chain["rfq"] = r.json()
    assert chain["rfq"]["rfq_no"].startswith("SRFQ-")
    assert chain["rfq"]["status"] == "draft"


def test_pnv_cannot_rfq_an_out_of_scope_request(pnv, srs, vendor_id):
    r = pnv.post(f"{API}/service-workflow/requests/{srs['excluded']['id']}/rfq",
                 json={"vendor_ids": [vendor_id]}, timeout=60)
    assert r.status_code == 403, "Transportation stays with Logistics"


def test_pnv_issues_the_rfq_and_records_a_quotation(pnv, chain, vendor_id):
    rfq_id = chain["rfq"]["id"]
    i = pnv.post(f"{API}/service-workflow/rfqs/{rfq_id}/issue", timeout=60)
    assert i.status_code == 200, i.text
    assert i.json()["status"] == "issued"
    q = pnv.post(f"{API}/service-workflow/rfqs/{rfq_id}/quotation", json={
        "vendor_id": vendor_id, "amount": 100000, "tax_pct": 18,
        "timeline_days": 7, "payment_terms": "30 days", "remarks": TAG}, timeout=60)
    assert q.status_code == 200, q.text


def test_pnv_sees_the_comparison_and_selects_the_vendor(pnv, chain, vendor_id):
    rfq_id = chain["rfq"]["id"]
    c = pnv.get(f"{API}/service-workflow/rfqs/{rfq_id}/comparison", timeout=60)
    assert c.status_code == 200, c.text
    assert c.json()["rows"], "comparison must list the captured quote"
    rec = pnv.post(f"{API}/service-workflow/rfqs/{rfq_id}/recommend",
                   json={"vendor_id": vendor_id, "remarks": "lowest"}, timeout=60)
    assert rec.status_code == 200, rec.text
    assert rec.json()["recommended_vendor_id"] == vendor_id


def test_pnv_creates_and_issues_the_po(pnv, chain):
    rfq_id = chain["rfq"]["id"]
    po = pnv.post(f"{API}/service-workflow/rfqs/{rfq_id}/po",
                  json={"rate": 100000, "quantity": 1, "tax_pct": 18,
                        "service_period_from": "2026-11-01", "service_period_to": "2026-11-30",
                        "payment_terms": "30 days"}, timeout=90)
    assert po.status_code == 200, po.text
    chain["po"] = po.json()
    assert chain["po"]["po_no"].startswith("SPO-")
    sub = pnv.post(f"{API}/service-workflow/pos/{chain['po']['id']}/submit", timeout=60)
    assert sub.status_code == 200, sub.text
    iss = pnv.post(f"{API}/service-workflow/pos/{chain['po']['id']}/issue", timeout=90)
    assert iss.status_code == 200, iss.text
    assert iss.json()["status"] == "issued"


def test_pnv_books_and_approves_the_srn(pnv, chain):
    srn = pnv.post(f"{API}/service-workflow/pos/{chain['po']['id']}/srn", json={
        "receipt_date": "2026-11-30", "service_details": f"{TAG} done",
        "completed_pct": 100, "accepted_pct": 100, "receipt_type": "full",
        "quality_status": "accepted", "remarks": TAG, "submit": True}, timeout=90)
    assert srn.status_code == 200, srn.text
    chain["srn"] = srn.json()
    act = pnv.post(f"{API}/service-workflow/srns/{chain['srn']['id']}/action",
                   json={"action": "approve", "remarks": "verified"}, timeout=60)
    assert act.status_code == 200, act.text


def test_pnv_records_the_vendor_invoice(pnv, chain):
    inv = pnv.post(f"{API}/service-workflow/invoices", json={
        "po_id": chain["po"]["id"], "srn_id": chain["srn"]["id"],
        "vendor_invoice_no": f"INV-{TAG}", "invoice_date": "2026-11-30",
        "invoice_amount": 100000, "tax_amount": 18000}, timeout=90)
    assert inv.status_code == 200, inv.text
    chain["invoice"] = inv.json()
    assert chain["invoice"]["status"] in ("pending_approval", "exception_review")


def test_payment_release_still_belongs_to_accounts(pnv, chain):
    r = pnv.post(f"{API}/service-workflow/invoices/{chain['invoice']['id']}/action",
                 json={"action": "approve", "remarks": "x"}, timeout=60)
    assert r.status_code == 403, "a procurement role must not release the payment"


def test_pnv_can_watch_the_payment_stage(pnv):
    r = pnv.get(f"{API}/service-workflow/payments", timeout=60)
    assert r.status_code == 200, r.text
