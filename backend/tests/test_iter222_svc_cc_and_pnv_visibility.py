"""Iter 222 — unique Cost Center categories + Manager PNV visibility of Manager OP SRs."""
import os

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"


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


# ─────────────────── 1 · unique cost centre categories ───────────────────
def test_meta_lists_each_cost_center_category_once(mop):
    meta = mop.get(f"{API}/service-workflow/meta", timeout=60).json()
    cats = meta["cost_center_categories"]
    names = [c["category_name"] for c in cats]
    assert names, "cost centre categories must be exposed"
    assert len(names) == len({n.lower() for n in names}), f"duplicate categories: {names}"
    assert len(names) < len(meta["cost_centers"]), "categories must collapse the per-project rows"


def test_cost_center_categories_carry_no_project_codes(mop):
    meta = mop.get(f"{API}/service-workflow/meta", timeout=60).json()
    for c in meta["cost_center_categories"]:
        assert "PRJ-" not in c["category_name"] and "CC-" not in c["category_name"], c
        assert "·" not in c["category_name"], c
        assert c["category_id"]


# ─────────────────── 2 · Manager PNV sees Manager OP requests ───────────────────
@pytest.fixture(scope="module")
def op_requests(mop, db):
    made = []

    def raise_sr(category, desc):
        r = mop.post(f"{API}/service-workflow/requests", json={
            "department": "Operations", "service_category": category,
            "service_type": "iter222", "service_description": desc,
            "site_location": "Goa", "priority": "Medium", "submit": True,
            **({"from_location": "A", "to_location": "B"} if category == "Transportation" else {}),
        }, timeout=60)
        assert r.status_code == 200, r.text
        made.append(r.json())
        return r.json()

    visible = raise_sr("AMC / Maintenance", "iter222 amc visible to pnv")
    transport = raise_sr("Transportation", "iter222 transport hidden from pnv")
    room = raise_sr("Room Rent", "iter222 room rent hidden from pnv")
    yield {"visible": visible, "transport": transport, "room": room}
    db.svc_requests.delete_many({"id": {"$in": [m["id"] for m in made]}})


def test_pnv_sees_manager_op_requests(pnv, op_requests):
    rows = pnv.get(f"{API}/service-workflow/requests", timeout=60).json()
    ids = {r["id"] for r in rows}
    assert op_requests["visible"]["id"] in ids, "Manager OP request must reach Manager PNV"


def test_pnv_does_not_see_transportation_or_room_rent(pnv, op_requests):
    rows = pnv.get(f"{API}/service-workflow/requests", timeout=60).json()
    ids = {r["id"] for r in rows}
    assert op_requests["transport"]["id"] not in ids
    assert op_requests["room"]["id"] not in ids


def test_pnv_can_open_a_visible_request(pnv, op_requests):
    r = pnv.get(f"{API}/service-workflow/requests/{op_requests['visible']['id']}", timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["request"]["requester_role"] == "manager_o_p"


def test_pnv_cannot_open_an_excluded_request(pnv, op_requests):
    r = pnv.get(f"{API}/service-workflow/requests/{op_requests['transport']['id']}", timeout=60)
    assert r.status_code == 403


def test_search_still_works_for_pnv(pnv, op_requests):
    rows = pnv.get(f"{API}/service-workflow/requests", params={"q": "iter222"}, timeout=60).json()
    ids = {r["id"] for r in rows}
    assert op_requests["visible"]["id"] in ids
    assert op_requests["transport"]["id"] not in ids, "the q filter must not widen visibility"


def test_super_admin_still_sees_everything(admin, op_requests):
    rows = admin.get(f"{API}/service-workflow/requests", timeout=60).json()
    ids = {r["id"] for r in rows}
    assert {op_requests["visible"]["id"], op_requests["transport"]["id"],
            op_requests["room"]["id"]} <= ids


def test_manager_op_still_sees_only_its_own(mop, op_requests):
    rows = mop.get(f"{API}/service-workflow/requests", timeout=60).json()
    assert {r["id"] for r in rows} >= {v["id"] for v in op_requests.values()}
    assert all(r.get("requester_role") == "manager_o_p" for r in rows), \
        "Manager OP visibility must stay unchanged (own requests only)"
