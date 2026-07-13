"""Iteration 20 - Phase A Procurement Cycle Backbone (PR -> RFQ -> PO -> GRN).
Tests run as super_admin (admin@erp.com / Admin@123) which bypasses approval steps.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TS = str(int(time.time()))


# ─── auth ────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def vendor_ids(admin_session):
    r = admin_session.get(f"{API}/vendors", timeout=30)
    assert r.status_code == 200, r.text
    vs = r.json()
    assert len(vs) >= 2, f"need at least 2 vendors in seed, got {len(vs)}"
    return [v["id"] for v in vs[:2]]


@pytest.fixture(scope="session")
def inventory_item(admin_session):
    """Pick or create an inventory item for GRN inward verification."""
    r = admin_session.get(f"{API}/inventory", timeout=30)
    if r.status_code == 200 and isinstance(r.json(), list) and r.json():
        return r.json()[0]
    # create one
    payload = {"name": f"TEST_PROC_ITEM_{TS}", "category": "raw_material", "unit": "Nos", "quantity": 0}
    r = admin_session.post(f"{API}/inventory", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


# ─── PR ──────────────────────────────────────────────────────────────────────
class TestPR:
    def test_create_pr_draft(self, admin_session):
        payload = {
            "department": "Procurement", "priority": "medium",
            "items": [{"name": f"TEST_pr_item_{TS}", "quantity": 10, "unit": "Nos"}],
            "submit_for_approval": False,
        }
        r = admin_session.post(f"{API}/procurement/prs", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "draft"
        assert d["pr_number"].startswith("PR-")
        assert "approval_id" not in d
        pytest.shared_pr_draft = d["id"]

    def test_submit_draft(self, admin_session):
        pr_id = pytest.shared_pr_draft
        r = admin_session.post(f"{API}/procurement/prs/{pr_id}/submit", timeout=30)
        assert r.status_code == 200, r.text
        ap = r.json()["approval_id"]
        # verify PR is now pending_approval
        r2 = admin_session.get(f"{API}/procurement/prs/{pr_id}", timeout=30)
        assert r2.json()["status"] == "pending_approval"
        assert r2.json()["approval_id"] == ap
        pytest.shared_approval_draft = ap

    def test_create_pr_submit_directly(self, admin_session):
        payload = {
            "department": "Stores", "priority": "high",
            "items": [
                {"name": f"TEST_steel_{TS}", "quantity": 100, "unit": "Kg"},
                {"name": f"TEST_bolts_{TS}", "quantity": 50, "unit": "Nos"},
            ],
            "submit_for_approval": True,
        }
        r = admin_session.post(f"{API}/procurement/prs", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending_approval"
        assert "approval_id" in d
        # verify approval chain has 5 steps
        ap = admin_session.get(f"{API}/approvals/{d['approval_id']}", timeout=30).json()
        assert ap["type"] == "purchase_requisition"
        assert len(ap["chain"]) == 5
        pytest.shared_pr_for_full = d["id"]
        pytest.shared_approval_full = d["approval_id"]

    def test_approve_full_chain(self, admin_session):
        ap_id = pytest.shared_approval_full
        for step in range(5):
            r = admin_session.post(f"{API}/approvals/{ap_id}/action",
                                   json={"action": "approve", "comment": f"step {step}"}, timeout=30)
            assert r.status_code == 200, f"step {step}: {r.text}"
        # confirm PR moved to approved
        pr = admin_session.get(f"{API}/procurement/prs/{pytest.shared_pr_for_full}", timeout=30).json()
        assert pr["status"] == "approved", f"PR status={pr['status']}"

    def test_reject_pr_chain(self, admin_session):
        # create a fresh PR and reject it
        payload = {
            "department": "QA", "priority": "low",
            "items": [{"name": f"TEST_rej_{TS}", "quantity": 1, "unit": "Nos"}],
            "submit_for_approval": True,
        }
        r = admin_session.post(f"{API}/procurement/prs", json=payload, timeout=30)
        assert r.status_code == 200
        pr_id = r.json()["id"]
        ap_id = r.json()["approval_id"]
        rr = admin_session.post(f"{API}/approvals/{ap_id}/action",
                                json={"action": "reject", "comment": "not justified"}, timeout=30)
        assert rr.status_code == 200
        pr = admin_session.get(f"{API}/procurement/prs/{pr_id}", timeout=30).json()
        # Iter 50: rejection bounces PR back to pending_revision (not terminal).
        assert pr["status"] == "pending_revision"
        assert pr.get("reject_reason") == "not justified"

    def test_update_pr_blocked_after_approval(self, admin_session):
        pr_id = pytest.shared_pr_for_full
        r = admin_session.put(f"{API}/procurement/prs/{pr_id}", json={"remarks": "edit"}, timeout=30)
        assert r.status_code == 400

    def test_list_pr(self, admin_session):
        r = admin_session.get(f"{API}/procurement/prs", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ─── RFQ → PO ────────────────────────────────────────────────────────────────
class TestRFQ:
    def test_create_rfq_requires_approved_pr(self, admin_session, vendor_ids):
        # using draft PR should fail
        payload = {"department": "Ops", "priority": "low",
                   "items": [{"name": "x", "quantity": 1, "unit": "Nos"}],
                   "submit_for_approval": False}
        pr = admin_session.post(f"{API}/procurement/prs", json=payload, timeout=30).json()
        r = admin_session.post(f"{API}/procurement/rfqs",
                               json={"pr_id": pr["id"],
                                     "vendors": [{"vendor_id": vendor_ids[0]}]}, timeout=30)
        assert r.status_code == 400

    def test_create_rfq_from_approved_pr(self, admin_session, vendor_ids):
        pr_id = pytest.shared_pr_for_full  # already approved in previous class
        r = admin_session.post(f"{API}/procurement/rfqs",
                               json={"pr_id": pr_id,
                                     "vendors": [{"vendor_id": vendor_ids[0]},
                                                 {"vendor_id": vendor_ids[1]}],
                                     "notes": "TEST_RFQ"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["rfq_number"].startswith("RFQ-")
        assert len(d["vendors"]) == 2
        assert d["status"] == "response_pending"
        pytest.shared_rfq_id = d["id"]

    def test_record_responses(self, admin_session, vendor_ids):
        rfq_id = pytest.shared_rfq_id
        r1 = admin_session.post(f"{API}/procurement/rfqs/{rfq_id}/respond",
                                json={"vendor_id": vendor_ids[0], "rate_quoted": 100,
                                      "delivery_days": 7, "payment_terms": "30 days",
                                      "technical_score": 85}, timeout=30)
        assert r1.status_code == 200, r1.text
        assert r1.json()["status"] == "under_evaluation"
        r2 = admin_session.post(f"{API}/procurement/rfqs/{rfq_id}/respond",
                                json={"vendor_id": vendor_ids[1], "rate_quoted": 110,
                                      "delivery_days": 5, "payment_terms": "45 days",
                                      "technical_score": 90}, timeout=30)
        assert r2.status_code == 200

    def test_comparative_sorted_by_landed(self, admin_session, vendor_ids):
        rfq_id = pytest.shared_rfq_id
        r = admin_session.get(f"{API}/procurement/rfqs/{rfq_id}/comparative", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        rows = d["rows"]
        assert len(rows) == 2
        # cheapest first
        assert rows[0]["vendor_id"] == vendor_ids[0]
        # landed_value = rate * total_qty (=150 for current PR: 100+50)
        assert rows[0]["landed_value"] == 100 * d["total_qty"]
        assert rows[1]["landed_value"] == 110 * d["total_qty"]

    def test_select_vendor_invalid(self, admin_session):
        rfq_id = pytest.shared_rfq_id
        r = admin_session.post(f"{API}/procurement/rfqs/{rfq_id}/select-vendor",
                               json={"vendor_id": "does-not-exist"}, timeout=30)
        assert r.status_code == 400

    def test_select_vendor_and_convert(self, admin_session, vendor_ids):
        rfq_id = pytest.shared_rfq_id
        r = admin_session.post(f"{API}/procurement/rfqs/{rfq_id}/select-vendor",
                               json={"vendor_id": vendor_ids[0]}, timeout=30)
        assert r.status_code == 200
        # convert to PO
        c = admin_session.post(f"{API}/procurement/rfqs/{rfq_id}/convert-to-po", timeout=30)
        assert c.status_code == 200, c.text
        po = c.json()
        assert po["po_number"].startswith("PO-")
        assert po["rfq_id"] == rfq_id
        assert po["pr_id"] == pytest.shared_pr_for_full
        assert po["status"] == "approved"
        assert po["amount"] == 100 * 150  # rate * qty
        # PR + RFQ statuses should flip
        rfq = admin_session.get(f"{API}/procurement/rfqs/{rfq_id}", timeout=30).json()
        assert rfq["status"] == "converted_to_po"
        pr = admin_session.get(f"{API}/procurement/prs/{pytest.shared_pr_for_full}", timeout=30).json()
        assert pr["status"] == "po_generated"
        pytest.shared_po_id = po["id"]


# ─── GRN ─────────────────────────────────────────────────────────────────────
class TestGRN:
    def test_create_partial_grn(self, admin_session, inventory_item):
        po_id = pytest.shared_po_id
        # before
        inv_before = admin_session.get(f"{API}/inventory", timeout=30).json()
        item_before = next((x for x in inv_before if x["id"] == inventory_item["id"]), None)
        qty_before = float((item_before or {}).get("quantity") or 0)

        payload = {
            "po_id": po_id,
            "store_location": "Main Store",
            "items": [
                {"po_item_index": 0, "item_id": inventory_item["id"],
                 "item_name": inventory_item.get("name", "X"),
                 "ordered_qty": 100, "received_qty": 80, "accepted_qty": 70,
                 "rejected_qty": 10, "unit": "Nos",
                 "inspection_status": "partial_accepted", "batch": f"B{TS}"},
                {"po_item_index": 1, "item_name": "TEST_no_item",
                 "ordered_qty": 50, "received_qty": 50, "accepted_qty": 50,
                 "rejected_qty": 0, "unit": "Nos", "inspection_status": "approved"},
            ],
            "remarks": "TEST partial",
        }
        r = admin_session.post(f"{API}/procurement/grns", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        g = r.json()
        assert g["grn_number"].startswith("GRN-")
        assert g["total_accepted"] == 120
        assert g["total_rejected"] == 10
        assert g["status"] == "partial_accepted"
        pytest.shared_grn_id = g["id"]

        # inventory bumped for the item_id line
        inv_after = admin_session.get(f"{API}/inventory", timeout=30).json()
        item_after = next((x for x in inv_after if x["id"] == inventory_item["id"]), None)
        qty_after = float((item_after or {}).get("quantity") or 0)
        assert qty_after - qty_before == 70, f"expected +70 inward, got {qty_after - qty_before}"

        # PO flipped to partially_received
        po = admin_session.get(f"{API}/purchase-orders/{po_id}", timeout=30)
        if po.status_code == 200:
            assert po.json()["status"] == "partially_received"

    def test_delete_grn_reverses_inventory(self, admin_session, inventory_item):
        inv_before = admin_session.get(f"{API}/inventory", timeout=30).json()
        qty_before = float(next(x for x in inv_before if x["id"] == inventory_item["id"]).get("quantity") or 0)
        r = admin_session.delete(f"{API}/procurement/grns/{pytest.shared_grn_id}", timeout=30)
        assert r.status_code == 200
        inv_after = admin_session.get(f"{API}/inventory", timeout=30).json()
        qty_after = float(next(x for x in inv_after if x["id"] == inventory_item["id"]).get("quantity") or 0)
        assert qty_before - qty_after == 70, f"expected -70 reversal, got {qty_before - qty_after}"


# ─── Dashboard & RBAC ────────────────────────────────────────────────────────
class TestDashboardRBAC:
    def test_dashboard_kpis(self, admin_session):
        r = admin_session.get(f"{API}/procurement/dashboard", timeout=30)
        assert r.status_code == 200, r.text
        k = r.json()["kpis"]
        for key in ("pr_total", "pr_pending", "pr_approved", "pr_rejected",
                    "rfq_total", "rfq_open", "po_total", "po_open",
                    "grn_total", "grn_partial", "avg_cycle_days"):
            assert key in k, f"missing kpi {key}"
        assert k["pr_total"] >= 1
        assert k["po_total"] >= 1

    def test_rbac_purchase_officer_can_read(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": "purchase@erp.com", "password": "Purchase@123"}, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"purchase_officer login failed: {r.status_code}")
        tok = r.json().get("access_token") or r.json().get("token")
        if tok:
            s.headers.update({"Authorization": f"Bearer {tok}"})
        lr = s.get(f"{API}/procurement/prs", timeout=30)
        assert lr.status_code == 200, f"purchase_officer GET /prs -> {lr.status_code}"
