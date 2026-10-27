"""Iter 220 — Fuel vehicle number + Payment Mode in My Pending Approvals."""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


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
def ctx(s, db):
    rows = s.get(f"{API}/project-requests?page=1&page_size=50", timeout=60).json().get("rows", [])
    live = next((x for x in rows if x.get("project_id") and x.get("cost_center_id")
                 and x.get("project_code") != "HEAD-OFFICE"), None)
    if not live:
        pytest.skip("no existing request to model project / cost-center on")
    data = {"project_id": live["project_id"], "cost_center_id": live["cost_center_id"], "ids": []}
    yield data
    docs = list(db.project_requests.find({"id": {"$in": data["ids"]}}, {"_id": 0, "approval_id": 1}))
    db.project_requests.delete_many({"id": {"$in": data["ids"]}})
    db.approvals.delete_many({"id": {"$in": [d.get("approval_id") for d in docs if d.get("approval_id")]}})


def _raise(s, ctx, **extra):
    body = {"amount": 5000, "priority": "medium", "project_id": ctx["project_id"],
            "cost_center_id": ctx["cost_center_id"], **extra}
    r = s.post(f"{API}/project-requests", json=body, timeout=60)
    if r.status_code == 200:
        ctx["ids"].append(r.json()["id"])
    return r


def test_fuel_without_vehicle_number_is_blocked(s, ctx):
    r = _raise(s, ctx, request_type="fuel", description=f"iter220 no vehicle {uuid.uuid4().hex[:6]}")
    assert r.status_code == 400
    assert "Vehicle Number is mandatory" in r.json()["detail"]


def test_fuel_with_vehicle_number_is_stored_uppercase(s, ctx):
    r = _raise(s, ctx, request_type="fuel", vehicle_ref=" hr26 dk 8337 ",
               description=f"iter220 fuel {uuid.uuid4().hex[:6]}")
    assert r.status_code == 200, r.text
    assert r.json()["vehicle_ref"] == "HR26 DK 8337"


def test_other_payment_types_do_not_need_a_vehicle_number(s, ctx):
    r = _raise(s, ctx, request_type="other", description=f"iter220 other {uuid.uuid4().hex[:6]}")
    assert r.status_code == 200, r.text


def test_inbox_exposes_payment_mode(s, ctx):
    r = _raise(s, ctx, request_type="other", priority="high", payment_mode="UPI",
               upi_any_name="Iter220 Payee", description=f"iter220 upi {uuid.uuid4().hex[:6]}")
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    inbox = s.get(f"{API}/my-inbox", timeout=90).json()
    assert all("payment_mode" in it for it in inbox["items"]), "every inbox row must carry the field"
    row = next((it for it in inbox["items"] if it["id"] == rid), None)
    if row:
        assert row["payment_mode"] == "UPI"


def test_inbox_payment_mode_is_none_for_non_payment_rows(s):
    inbox = s.get(f"{API}/my-inbox", timeout=90).json()
    for it in inbox["items"]:
        if it["source"] in ("dpr", "scaffolding"):
            assert it["payment_mode"] is None
