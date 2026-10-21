"""Iter 210 — repeat advance requests (same employee/type/amount/reason same day) must
be allowed; only an identical still-pending request created within the last
RESUBMIT_WINDOW_MINUTES (2) is refused. Same relaxation for payment requests."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
EMP_ID = "b14f6b91-c6d8-42a8-9ebd-4fbbb03ddf9e"  # Abhilash Kumar EMPITL017

_env = dotenv_values("/app/backend/.env")
mdb = MongoClient(_env["MONGO_URL"])[_env["DB_NAME"]]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return sess


@pytest.fixture(scope="module")
def created():
    ids = {"adv": [], "req": []}
    yield ids
    advs = list(mdb.employee_advances.find({"id": {"$in": ids["adv"]}}, {"_id": 0, "approval_id": 1}))
    mdb.employee_advances.delete_many({"id": {"$in": ids["adv"]}})
    reqs = list(mdb.project_requests.find({"id": {"$in": ids["req"]}}, {"_id": 0, "approval_id": 1}))
    mdb.project_requests.delete_many({"id": {"$in": ids["req"]}})
    apids = [d.get("approval_id") for d in advs + reqs if d.get("approval_id")]
    mdb.approvals.delete_many({"id": {"$in": apids}})


def _adv(s, created, *, amount, atype="EMG", reason, remarks=None):
    body = {"employee_id": EMP_ID, "advance_type": atype, "requested_amount": amount,
            "installments": 1, "reason": reason, "documents_not_required": True,
            "documents_not_required_reason": "no needed", "submit": True,
            "remarks": remarks or uuid.uuid4().hex[:8]}
    r = s.post(f"{API}/advances", json=body, timeout=40)
    if r.status_code == 200:
        j = r.json()
        aid = j.get("id") or (j.get("advance") or {}).get("id")
        if aid and aid not in created["adv"]:
            created["adv"].append(aid)
    return r


def _backdate_adv(aid, minutes=3):
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    mdb.employee_advances.update_one({"id": aid}, {"$set": {"created_at": ts}})


def _no(r):
    j = r.json()
    return j.get("advance_no") or (j.get("advance") or {}).get("advance_no")


class TestAdvanceRepeat:
    def test_first_create_ok(self, s, created):
        r = _adv(s, created, amount=1111, reason="TEST_iter210 repeat")
        assert r.status_code == 200, r.text[:300]
        assert _no(r).startswith("AD-")
        doc = mdb.employee_advances.find_one({"id": created["adv"][-1]}, {"_id": 0})
        assert doc["status"] == "submitted"

    def test_immediate_identical_repeat_blocked(self, s, created):
        first_no = mdb.employee_advances.find_one({"id": created["adv"][0]}, {"_id": 0})["advance_no"]
        n_before = mdb.employee_advances.count_documents({"employee_id": EMP_ID})
        r = _adv(s, created, amount=1111, reason="TEST_iter210 repeat")
        assert r.status_code == 409, r.text[:300]
        assert first_no in r.text
        assert mdb.employee_advances.count_documents({"employee_id": EMP_ID}) == n_before

    def test_reason_case_whitespace_variation_still_blocked(self, s, created):
        r = _adv(s, created, amount=1111, reason="  test_ITER210   repeat ")
        assert r.status_code == 409, r.text[:300]

    def test_identical_repeat_later_same_day_allowed(self, s, created):
        _backdate_adv(created["adv"][0], 3)
        r = _adv(s, created, amount=1111, reason="TEST_iter210 repeat")
        assert r.status_code == 200, r.text[:300]
        assert len(created["adv"]) == 2
        doc = mdb.employee_advances.find_one({"id": created["adv"][1]}, {"_id": 0})
        assert doc["status"] == "submitted" and doc["advance_no"].startswith("AD-")

    def test_different_amount_immediate_ok(self, s, created):
        r = _adv(s, created, amount=1112, reason="TEST_iter210 repeat")
        assert r.status_code == 200, r.text[:300]

    def test_different_type_immediate_ok(self, s, created):
        r = _adv(s, created, amount=1111, atype="MED", reason="TEST_iter210 repeat")
        assert r.status_code == 200, r.text[:300]

    def test_different_reason_immediate_ok(self, s, created):
        r = _adv(s, created, amount=1111, reason="TEST_iter210 another reason")
        assert r.status_code == 200, r.text[:300]

    def test_fingerprint_replay_does_not_duplicate(self, s, created):
        n_before = mdb.employee_advances.count_documents({"employee_id": EMP_ID})
        r1 = _adv(s, created, amount=1113, reason="TEST_iter210 fp", remarks="samefp")
        r2 = _adv(s, created, amount=1113, reason="TEST_iter210 fp", remarks="samefp")
        assert r1.status_code == 200
        assert r2.status_code in (200, 409), r2.text[:200]
        assert mdb.employee_advances.count_documents({"employee_id": EMP_ID}) == n_before + 1


@pytest.fixture(scope="module")
def pctx(s):
    rows = s.get(f"{API}/project-requests?page=1&page_size=50", timeout=30).json().get("rows", [])
    live = next((x for x in rows if x.get("project_id") and x.get("cost_center_id")
                 and x.get("project_code") != "HEAD-OFFICE"), None)
    if not live:
        pytest.skip("no project to model on")
    return live


def _preq(s, created, pctx, desc, amount=4321, priority="medium"):
    body = {"request_type": "fuel", "amount": amount, "priority": priority, "description": desc,
            "project_id": pctx["project_id"], "cost_center_id": pctx["cost_center_id"],
            "vendor": "TEST_iter210 vendor", "notes": uuid.uuid4().hex[:6]}
    r = s.post(f"{API}/project-requests", json=body, timeout=40)
    if r.status_code == 200 and r.json()["id"] not in created["req"]:
        created["req"].append(r.json()["id"])
    return r


class TestPaymentRequestRepeat:
    def test_first_ok_immediate_repeat_blocked_later_allowed(self, s, created, pctx):
        desc = f"TEST_iter210 fuel {uuid.uuid4().hex[:5]}"
        r1 = _preq(s, created, pctx, desc)
        assert r1.status_code == 200, r1.text[:300]
        r2 = _preq(s, created, pctx, desc, priority="low")
        assert r2.status_code == 409, f"{r2.status_code} {r2.text[:300]}"
        assert r1.json()["request_no"] in r2.text
        ts = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        mdb.project_requests.update_one({"id": r1.json()["id"]}, {"$set": {"created_at": ts}})
        r3 = _preq(s, created, pctx, desc, priority="medium")
        assert r3.status_code == 200, r3.text[:300]
        assert r3.json()["request_no"] != r1.json()["request_no"]
