"""Iter 126 — Work Order ↔ Contract Handover linkage.

Verifies:
  * source_handover_id + source_handover_no are accepted and persisted
  * The linked WO round-trips through GET /work-orders
  * Update preserves the linkage (doesn't wipe it)
  * A picker-style flow (pick a handover → derive common fields) yields a
    valid WO payload that the backend accepts
"""
import os
import time
import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return s


def _pick_non_draft_handover(sess):
    rows = sess.get(f"{API}/ops/handovers", timeout=30).json() or []
    for r in rows:
        if r.get("status") not in ("draft", "sent_back"):
            return r
    pytest.skip("No non-draft handover available in the DB to test with")


def _derive_wo_payload_from_handover(h, wo_no):
    """Mirror the prefillFromHandover() helper on the frontend."""
    return {
        "wo_no": wo_no,
        "project_id": h.get("project_id") or None,
        "scope": h.get("scope_of_work") or "",
        "value": float(h.get("contract_value") or 0),
        "currency": "INR",
        "status": "received",
        "quotation_no": h.get("quotation_no") or "",
        "payment_terms": h.get("payment_terms") or "",
        "contractual_completion_date": h.get("contract_end_date") or None,
        "source_handover_id": h.get("id"),
        "source_handover_no": h.get("handover_no"),
    }


class TestWorkOrderHandoverLinkage:
    def test_create_wo_persists_source_handover(self, sess):
        h = _pick_non_draft_handover(sess)
        wo_no = f"ITER126-CREATE-{int(time.time())}"
        payload = _derive_wo_payload_from_handover(h, wo_no)
        r = sess.post(f"{API}/work-orders", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        wo = r.json()
        assert wo["wo_no"] == wo_no
        assert wo.get("source_handover_id") == h["id"]
        assert wo.get("source_handover_no") == h["handover_no"]
        # Common fields flowed through
        assert float(wo.get("value") or 0) == float(h.get("contract_value") or 0)

    def test_list_returns_source_handover(self, sess):
        h = _pick_non_draft_handover(sess)
        wo_no = f"ITER126-LIST-{int(time.time())}"
        payload = _derive_wo_payload_from_handover(h, wo_no)
        assert sess.post(f"{API}/work-orders", json=payload, timeout=30).status_code == 200
        rows = sess.get(f"{API}/work-orders", timeout=30).json()
        row = next(r for r in rows if r["wo_no"] == wo_no)
        assert row["source_handover_no"] == h["handover_no"]

    def test_update_preserves_linkage(self, sess):
        h = _pick_non_draft_handover(sess)
        wo_no = f"ITER126-UPD-{int(time.time())}"
        payload = _derive_wo_payload_from_handover(h, wo_no)
        wid = sess.post(f"{API}/work-orders", json=payload, timeout=30).json()["id"]
        # Update with a new value + remarks; linkage fields still in payload
        updated = {**payload, "value": 2222222.0, "remarks": "increment"}
        r = sess.put(f"{API}/work-orders/{wid}", json=updated, timeout=30)
        assert r.status_code == 200, r.text
        wo = r.json()
        assert wo["source_handover_id"] == h["id"]
        assert wo["source_handover_no"] == h["handover_no"]
        assert wo["value"] == 2222222.0

    def test_wo_without_linkage_still_works(self, sess):
        """The linkage fields must be optional — creating a plain WO should still work."""
        wo_no = f"ITER126-PLAIN-{int(time.time())}"
        r = sess.post(f"{API}/work-orders", json={"wo_no": wo_no, "value": 100.0, "status": "draft"}, timeout=30)
        assert r.status_code == 200, r.text
        wo = r.json()
        assert wo.get("source_handover_id") is None
        assert wo.get("source_handover_no") is None
