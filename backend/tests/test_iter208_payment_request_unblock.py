"""Iteration 208 — payment requests must never be blocked by the duplicate guard
for legitimate business repeats.

Reported bug: no payment request could be raised any more — the Iter 205 rule
matched on project + payee + amount + type only, so once one ₹5,000 fuel request
sat open, every further ₹5,000 fuel request on that project was refused.

The rule now also requires the SAME description and the SAME day, so:
  • every payment type can be raised,
  • a second request for the same vendor/amount with a different purpose passes,
  • only a true re-submission (identical description, same day, still open) is refused.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}

PROJECT_PAYMENT_TYPES = ["fuel", "accommodation", "insurance", "one_time_vehicle", "other"]
HO_TYPES = ["self_expense", "head_office_expense"]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def ctx(session):
    """A project + cost center to raise against, and the Head Office pair."""
    rows = session.get(f"{API}/project-requests?page=1&page_size=50", timeout=30).json().get("rows", [])
    live = next((x for x in rows if x.get("project_id") and x.get("cost_center_id")
                 and x.get("project_code") != "HEAD-OFFICE"), None)
    if not live:
        pytest.skip("no existing request to model project/cost-center on")
    ho_ccs = session.get(f"{API}/head-office-cost-centers", timeout=30).json() or []
    data = {"project_id": live["project_id"], "cost_center_id": live["cost_center_id"],
            "ho_project_id": "ho-delhi" if ho_ccs else None,
            "ho_cc": (ho_ccs[0] or {}).get("id") if ho_ccs else None,
            "ids": []}
    yield data
    try:
        from pymongo import MongoClient
        from dotenv import dotenv_values
        env = dotenv_values("/app/backend/.env")
        db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
        docs = list(db.project_requests.find({"id": {"$in": data["ids"]}}, {"_id": 0, "approval_id": 1}))
        db.project_requests.delete_many({"id": {"$in": data["ids"]}})
        db.approvals.delete_many({"id": {"$in": [d.get("approval_id") for d in docs if d.get("approval_id")]}})
    except Exception as e:  # noqa: BLE001
        print(f"cleanup skipped: {e}")


def _raise(session, ctx, rtype, description, *, amount=5000, ho=False, **extra):
    body = {"request_type": rtype, "amount": amount, "priority": "medium",
            "description": description,
            "project_id": ctx["ho_project_id"] if ho else ctx["project_id"],
            "cost_center_id": ctx["ho_cc"] if ho else ctx["cost_center_id"], **extra}
    r = session.post(f"{API}/project-requests", json=body, timeout=40)
    if r.status_code == 200:
        ctx["ids"].append(r.json()["id"])
    return r


@pytest.mark.parametrize("rtype", PROJECT_PAYMENT_TYPES)
def test_every_project_payment_type_can_be_raised(session, ctx, rtype):
    r = _raise(session, ctx, rtype, f"Iter208 smoke {rtype} {uuid.uuid4().hex[:6]}")
    assert r.status_code == 200, f"{rtype} could not be raised: {r.status_code} {r.text[:200]}"
    assert r.json().get("request_no")


@pytest.mark.parametrize("rtype", HO_TYPES)
def test_head_office_payment_types_can_be_raised(session, ctx, rtype):
    if not ctx["ho_project_id"]:
        pytest.skip("no Head Office request available to model the cost center on")
    extra = {"vendor": f"Iter208 HO Vendor {uuid.uuid4().hex[:4]}"} if rtype == "head_office_expense" else {}
    r = _raise(session, ctx, rtype, f"Iter208 smoke {rtype} {uuid.uuid4().hex[:6]}", ho=True, **extra)
    assert r.status_code == 200, f"{rtype} could not be raised: {r.status_code} {r.text[:200]}"


def test_same_amount_different_purpose_is_allowed(session, ctx):
    """The exact bug: a second ₹5,000 fuel request for another vehicle must pass."""
    vendor = f"Iter208 Fuel Vendor {uuid.uuid4().hex[:4]}"
    first = _raise(session, ctx, "fuel", "Diesel required at TISCO JH05EJ5684", vendor=vendor)
    assert first.status_code == 200, first.text[:300]
    second = _raise(session, ctx, "fuel", "Diesel required at TISCO JH05EJ9999", vendor=vendor)
    assert second.status_code == 200, f"a different vehicle was wrongly blocked: {second.text[:200]}"
    assert second.json()["request_no"] != first.json()["request_no"]

    third = _raise(session, ctx, "fuel", "Diesel required at TISCO JH05EJ5684",
                   vendor=vendor, remarks="resubmitted")
    assert third.status_code == 409, f"an identical re-submission should be refused: {third.status_code}"
    assert third.json()["existing_no"] == first.json()["request_no"]


def test_different_amount_same_purpose_is_allowed(session, ctx):
    desc = f"Monthly toll recharge {uuid.uuid4().hex[:5]}"
    a = _raise(session, ctx, "other", desc, amount=4100)
    b = _raise(session, ctx, "other", desc, amount=4200)
    assert a.status_code == 200 and b.status_code == 200, (a.text[:150], b.text[:150])
