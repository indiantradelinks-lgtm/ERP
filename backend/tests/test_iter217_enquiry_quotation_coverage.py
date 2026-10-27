"""Iter 217 — every enquiry must appear on Sales & Quotations (no gaps, no duplicates)."""
import os
import time

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def mdb():
    return MongoClient("mongodb://localhost:27017")["erp_database"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


def _coverage(s):
    r = s.get(f"{API}/quotations/coverage", timeout=120)
    assert r.status_code == 200, r.text
    return r.json()


def _sync(s, force=True):
    r = s.post(f"{API}/quotations/sync-from-enquiries", params={"force": str(force).lower()}, timeout=180)
    assert r.status_code == 200, r.text
    return r.json()


def _quote_numbers(s):
    d = s.get(f"{API}/quotations", timeout=120).json()
    rows = d["rows"] if isinstance(d, dict) else d
    return [q["quote_number"] for q in rows]


def test_every_enquiry_is_covered(s):
    _sync(s)
    c = _coverage(s)
    assert c["missing"] == 0, c["missing_enquiries"]
    assert c["linked_enquiries"] == c["enquiries"]
    assert c["duplicate_quote_numbers"] == []


def test_a_missing_quotation_is_healed_exactly_once(s, mdb):
    enq = mdb.enquiries.find_one({"status": "open"}, {"id": 1, "enquiry_no": 1})
    assert enq, "need an enquiry"
    removed = list(mdb.quotations.find({"enquiry_id": enq["id"]}))
    assert removed, "enquiry should already have a quotation"
    mdb.quotations.delete_many({"enquiry_id": enq["id"]})
    mdb.enquiries.update_one({"id": enq["id"]}, {"$unset": {"quotation_id": "", "quotation_no": ""}})
    try:
        gap = _coverage(s)
        assert gap["missing"] == 1
        assert gap["missing_enquiries"][0]["enquiry_no"] == enq["enquiry_no"]

        first = _sync(s)
        assert first["created"] == 1
        assert first["quotations"][0]["enquiry_no"] == enq["enquiry_no"]
        new_no = first["quotations"][0]["quote_number"]
        assert new_no in _quote_numbers(s)

        again = _sync(s)
        assert again["created"] == 0, "sync must never create a second quotation"
        assert _coverage(s)["missing"] == 0
        assert _quote_numbers(s).count(new_no) == 1
        healed = mdb.enquiries.find_one({"id": enq["id"]}, {"quotation_no": 1})
        assert healed.get("quotation_no") == new_no
    finally:
        mdb.quotations.delete_many({"enquiry_id": enq["id"]})
        for r in removed:
            r.pop("_id", None)
            mdb.quotations.insert_one(r)
        mdb.enquiries.update_one({"id": enq["id"]}, {"$set": {
            "quotation_id": removed[0]["id"], "quotation_no": removed[0]["quote_number"]}})


def test_duplicate_quote_numbers_are_renumbered(s, mdb):
    donor = mdb.quotations.find_one({"enquiry_id": {"$ne": None}})
    clone = {**donor, "id": f"iter217-{int(time.time())}", "created_at": "2099-01-01T00:00:00+00:00"}
    clone.pop("_id", None)
    mdb.quotations.insert_one(clone)
    try:
        assert donor["quote_number"] in _coverage(s)["duplicate_quote_numbers"]
        out = _sync(s)
        assert out["renumbered"] >= 1
        fix = next(x for x in out["renumbered_detail"] if x["was"] == donor["quote_number"])
        assert fix["now"] != donor["quote_number"]
        assert _coverage(s)["duplicate_quote_numbers"] == []
        # the original kept its number, only the newer row moved
        assert mdb.quotations.find_one({"id": donor["id"]})["quote_number"] == donor["quote_number"]
        assert mdb.quotations.find_one({"id": clone["id"]})["quote_number"] == fix["now"]
    finally:
        mdb.quotations.delete_one({"id": clone["id"]})


def test_new_enquiry_shows_up_immediately(s, mdb):
    site = s.get(f"{API}/sites", timeout=60).json()[0]
    body = {"site_id": site["id"], "service_type": "services",
            "scope_of_work": f"ITER217 auto visibility {time.time()}", "expected_value": 1000}
    enq = s.post(f"{API}/enquiries", json=body, timeout=90).json()
    assert "enquiry_no" in enq, enq
    try:
        assert enq.get("quotation_no"), "a draft quotation must be created with the enquiry"
        nums = _quote_numbers(s)
        assert enq["quotation_no"] in nums
        assert nums.count(enq["quotation_no"]) == 1
        assert mdb.quotations.count_documents({"enquiry_id": enq["id"]}) == 1
        assert _sync(s)["created"] == 0
    finally:
        mdb.quotations.delete_many({"enquiry_id": enq["id"]})
        mdb.enquiries.delete_one({"id": enq["id"]})


def test_quote_numbers_are_unique_across_the_list(s):
    nums = [n for n in _quote_numbers(s) if n]
    assert len(nums) == len(set(nums))


def test_recent_clean_scan_is_cached(s):
    """The Sales screen calls the sync on every visit — a clean result is cached
    so the page does not pay for a full scan each time."""
    _sync(s, force=True)
    cheap = s.post(f"{API}/quotations/sync-from-enquiries", timeout=60).json()
    assert cheap.get("skipped") is True
    assert cheap["created"] == 0 and cheap["renumbered"] == 0
