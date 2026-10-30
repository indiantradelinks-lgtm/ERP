"""Iter 221 — a 422 from the API must never blank the screen.

FastAPI returns `detail` as a LIST of validation objects. The UI toasts
`detail` directly, so an object used to reach React as a child and unmount the
whole app (white screen on New RA Bill → Save). The axios interceptor now
flattens any non-string detail to text; these tests pin the server contract the
fix relies on, plus the RA bill save path itself.
"""
import os

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"


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
def made(db):
    ids = []
    yield ids
    db.ra_bills.delete_many({"id": {"$in": ids}})


def _bill(**over):
    body = {
        "bill_type": "running", "bill_date": "2026-10-30", "client_name": "ITER221 CLIENT",
        "project_code": "PRJ-2026-0112", "site_name": "Goa", "po_number": "4564027934",
        "items": [{"description": "SCAFFOLDING MATERIAL RENTAL", "quantity": 11.93, "unit": "each", "rate": 4116},
                  {"description": "GANG FOR ERECTION", "quantity": 0.968, "unit": "each", "rate": 218462}],
        "gst_pct": 18, "retention_pct": 5, "tds_pct": 0, "advance_recovery": 0,
        "notes": "iter221 regression",
    }
    body.update(over)
    return body


def test_blank_numeric_field_is_a_422_with_a_list_detail(s):
    """The exact payload the form used to send when a % box was cleared."""
    r = s.post(f"{API}/ra-bills", json=_bill(gst_pct=""), timeout=60)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and isinstance(detail[0], dict)
    assert "msg" in detail[0] and "loc" in detail[0], "the UI formatter keys on msg/loc"


def test_bill_saves_with_every_entered_value_preserved(s, made):
    r = s.post(f"{API}/ra-bills", json=_bill(), timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    made.append(d["id"])
    assert d["bill_number"].startswith("RA-")
    assert d["client_name"] == "ITER221 CLIENT" and d["site_name"] == "Goa"
    assert d["po_number"] == "4564027934" and d["notes"] == "iter221 regression"
    assert [i["description"] for i in d["items"]] == ["SCAFFOLDING MATERIAL RENTAL", "GANG FOR ERECTION"]
    assert d["items"][0]["quantity"] == 11.93 and d["items"][1]["rate"] == 218462
    assert d["subtotal"] == 260575.1 and d["gst_amount"] == 46903.52
    assert d["retention_amount"] == 13028.75 and d["net_payable"] == 294449.87
    assert d["status"] == "draft"


def test_zeroed_percentages_save_cleanly(s, made):
    """What the UI now sends when a % box is left blank — zero, not ''."""
    r = s.post(f"{API}/ra-bills", json=_bill(gst_pct=0, retention_pct=0, tds_pct=0), timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    made.append(d["id"])
    assert d["gst_amount"] == 0 and d["retention_amount"] == 0
    assert d["net_payable"] == d["subtotal"]


def test_saved_bill_is_listed(s, made):
    rows = s.get(f"{API}/ra-bills?page=1&page_size=50", timeout=60).json()
    rows = rows.get("rows", rows if isinstance(rows, list) else [])
    assert any(r["id"] in made for r in rows), "a freshly saved bill must appear in the list"
