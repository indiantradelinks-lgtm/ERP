"""Iter 79 — Phase 3 HTTP API end-to-end regression suite.

Covers Material Request lifecycle, 2-step Material Transfer, Site/Project stock
aggregations, Pending Returnable register and Project Closure Check.
Requires the backend at REACT_APP_BACKEND_URL with super_admin credentials.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"
PROJECT_CODE = f"TEST_PRJ_ITER79_{uuid.uuid4().hex[:6]}"


# ───── Auth fixture ─────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def items(client):
    """Pick two existing inventory items with stock >= 20."""
    r = client.get(f"{BASE_URL}/api/inventory", timeout=20)
    assert r.status_code == 200, r.text[:200]
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items") or r.json().get("rows") or []
    have_stock = [x for x in rows if float(x.get("quantity") or 0) >= 20]
    if len(have_stock) < 2:
        pytest.skip("Need >=2 inventory items with qty>=20 in DB to run Phase 3 E2E")
    return have_stock[:2]


@pytest.fixture(scope="module")
def stores(client):
    r = client.get(f"{BASE_URL}/api/inv/stores", timeout=20)
    if r.status_code != 200:
        pytest.skip(f"/api/inv/stores not available: {r.status_code}")
    rows = r.json() if isinstance(r.json(), list) else r.json().get("rows", [])
    if len(rows) < 2:
        pytest.skip("Need >=2 stores for transfer tests")
    return rows[:2]


# ───── Material Request ─────────────────────────────────────────────
class TestMaterialRequest:
    mr_id = None
    mr_number = None

    def test_create_mr_success(self, client, items):
        payload = {
            "project_code": PROJECT_CODE,
            "priority": "urgent",
            "remarks": "TEST_iter79 MR",
            "lines": [
                {"item_id": items[0]["id"], "required_qty": 5},
                {"item_id": items[1]["id"], "required_qty": 5},
            ],
        }
        r = client.post(f"{BASE_URL}/api/inv3/material-requests", json=payload, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["mr_number"].startswith("MR-")
        assert d["status"] == "submitted"
        assert d["priority"] == "urgent"
        assert d["project_code"] == PROJECT_CODE
        assert len(d["lines"]) == 2
        expected_val = sum(5 * float(it.get("rate") or 0) for it in items)
        assert abs(d["total_required_value"] - round(expected_val, 2)) < 0.01
        TestMaterialRequest.mr_id = d["id"]
        TestMaterialRequest.mr_number = d["mr_number"]

    def test_create_mr_missing_project_code(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests", json={
            "project_code": "",
            "lines": [{"item_id": items[0]["id"], "required_qty": 1}],
        }, timeout=20)
        assert r.status_code in (400, 422)

    def test_create_mr_empty_lines(self, client):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests", json={
            "project_code": PROJECT_CODE, "lines": [],
        }, timeout=20)
        assert r.status_code == 422

    def test_create_mr_missing_item(self, client):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests", json={
            "project_code": PROJECT_CODE,
            "lines": [{"item_id": "non-existent-item-id", "required_qty": 1}],
        }, timeout=20)
        assert r.status_code == 404

    def test_create_mr_negative_qty(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests", json={
            "project_code": PROJECT_CODE,
            "lines": [{"item_id": items[0]["id"], "required_qty": 0}],
        }, timeout=20)
        assert r.status_code == 400

    def test_list_mr_filter(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/material-requests?project_code={PROJECT_CODE}", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert any(m["id"] == TestMaterialRequest.mr_id for m in rows)

    def test_approve_mr(self, client):
        assert TestMaterialRequest.mr_id, "MR not created"
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{TestMaterialRequest.mr_id}/approve",
                        json={}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] == "approved"
        for ln in d["lines"]:
            assert ln["approved_qty"] == ln["required_qty"]

    def test_approve_non_submitted_fails(self, client):
        # MR is already approved; cannot approve again
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{TestMaterialRequest.mr_id}/approve",
                        json={}, timeout=20)
        assert r.status_code == 400

    def test_issue_partial(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{TestMaterialRequest.mr_id}/issue", json={
            "lines": [{"item_id": items[0]["id"], "issue_qty": 3}],
            "returnable": True,
            "expected_return_date": "2027-01-01",
        }, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["new_status"] == "partially_issued"
        assert d["allocations_created"] == 1

    def test_issue_exceeds_balance(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{TestMaterialRequest.mr_id}/issue", json={
            "lines": [{"item_id": items[0]["id"], "issue_qty": 999}],
        }, timeout=20)
        assert r.status_code == 400

    def test_issue_item_not_in_mr(self, client):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{TestMaterialRequest.mr_id}/issue", json={
            "lines": [{"item_id": "ghost-item-id", "issue_qty": 1}],
        }, timeout=20)
        assert r.status_code == 400

    def test_issue_remaining_completes_mr(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{TestMaterialRequest.mr_id}/issue", json={
            "lines": [
                {"item_id": items[0]["id"], "issue_qty": 2},
                {"item_id": items[1]["id"], "issue_qty": 5},
            ],
            "returnable": False,
        }, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["new_status"] == "issued"

    def test_reject_after_approved_fails(self, client, items):
        # Create another MR then approve then try reject (should fail)
        mr = client.post(f"{BASE_URL}/api/inv3/material-requests", json={
            "project_code": PROJECT_CODE + "_REJ",
            "lines": [{"item_id": items[0]["id"], "required_qty": 1}],
        }, timeout=20).json()
        client.post(f"{BASE_URL}/api/inv3/material-requests/{mr['id']}/approve", json={}, timeout=20)
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{mr['id']}/reject",
                        json={"reason": "TEST"}, timeout=20)
        assert r.status_code == 400

    def test_reject_submitted_mr(self, client, items):
        mr = client.post(f"{BASE_URL}/api/inv3/material-requests", json={
            "project_code": PROJECT_CODE + "_REJ2",
            "lines": [{"item_id": items[0]["id"], "required_qty": 1}],
        }, timeout=20).json()
        r = client.post(f"{BASE_URL}/api/inv3/material-requests/{mr['id']}/reject",
                        json={"reason": "TEST_iter79 rejection"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"


# ───── Material Transfer 2-step ─────────────────────────────────────
class TestMaterialTransfer:
    transfer_id = None

    def test_create_transfer_dispatch(self, client, items, stores):
        r = client.post(f"{BASE_URL}/api/inv3/transfers", json={
            "from_store_id": stores[0]["id"],
            "to_store_id": stores[1]["id"],
            "project_code": PROJECT_CODE,
            "vehicle_number": "TEST-1234",
            "lines": [{"item_id": items[0]["id"], "quantity": 2}],
        }, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] == "in_transit"
        assert d["transfer_no"].startswith("TRF-")
        TestMaterialTransfer.transfer_id = d["id"]

    def test_same_store_rejected(self, client, items, stores):
        r = client.post(f"{BASE_URL}/api/inv3/transfers", json={
            "from_store_id": stores[0]["id"],
            "to_store_id": stores[0]["id"],
            "lines": [{"item_id": items[0]["id"], "quantity": 1}],
        }, timeout=20)
        assert r.status_code == 400

    def test_missing_store_404(self, client, items, stores):
        r = client.post(f"{BASE_URL}/api/inv3/transfers", json={
            "from_store_id": "missing-store-x",
            "to_store_id": stores[1]["id"],
            "lines": [{"item_id": items[0]["id"], "quantity": 1}],
        }, timeout=20)
        assert r.status_code == 404

    def test_negative_qty_rejected(self, client, items, stores):
        r = client.post(f"{BASE_URL}/api/inv3/transfers", json={
            "from_store_id": stores[0]["id"],
            "to_store_id": stores[1]["id"],
            "lines": [{"item_id": items[0]["id"], "quantity": -1}],
        }, timeout=20)
        assert r.status_code == 400

    def test_in_transit_list(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/in-transit-stock", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "count" in d and "total_value" in d
        assert any(t["id"] == TestMaterialTransfer.transfer_id for t in d["rows"])
        for t in d["rows"]:
            assert "age_days" in t

    def test_receive_shortage_requires_remarks(self, client, items):
        # Try receive with shortage but no remarks/attachment -> 400
        r = client.post(f"{BASE_URL}/api/inv3/transfers/{TestMaterialTransfer.transfer_id}/receive", json={
            "lines": [{"item_id": items[0]["id"], "received_qty": 1, "shortage_qty": 1}],
        }, timeout=20)
        assert r.status_code == 400

    def test_receive_overflow_rejected(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/transfers/{TestMaterialTransfer.transfer_id}/receive", json={
            "lines": [{"item_id": items[0]["id"], "received_qty": 5}],
        }, timeout=20)
        assert r.status_code == 400

    def test_receive_with_exception(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/transfers/{TestMaterialTransfer.transfer_id}/receive", json={
            "lines": [{"item_id": items[0]["id"], "received_qty": 1, "shortage_qty": 1}],
            "received_remarks": "TEST_iter79: 1 unit short on arrival",
        }, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] == "received_with_exception"

    def test_receive_already_received_fails(self, client, items):
        r = client.post(f"{BASE_URL}/api/inv3/transfers/{TestMaterialTransfer.transfer_id}/receive", json={
            "lines": [{"item_id": items[0]["id"], "received_qty": 0}],
        }, timeout=20)
        assert r.status_code == 400

    def test_list_transfers(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/transfers", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ───── Aggregation reports ──────────────────────────────────────────
class TestAggregations:
    def test_site_stock_shape(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/site-stock", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "count" in d
        for row in d["rows"][:3]:
            assert "site_code" in row and "total_value" in row

    def test_project_stock_shape(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/project-stock", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d
        for row in d["rows"][:3]:
            assert "project_code" in row and "total_value" in row and "items" in row

    def test_project_consumption_with_date_filter(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/project-consumption?date_from=2020-01-01&date_to=2030-12-31",
                       timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d
        # Our test project should appear due to the issued MR allocations
        if d["rows"]:
            sample = d["rows"][0]
            assert "items" in sample and "total_value" in sample

    def test_pending_returnable(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/pending-returnable", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "total_value" in d
        # We issued returnable=true qty=3 for items[0] under PROJECT_CODE
        ours = [x for x in d["rows"] if x.get("project_code") == PROJECT_CODE]
        assert ours, "Expected at least one pending-returnable row for the test project"
        for row in ours:
            for k in ("outstanding_qty", "outstanding_value", "days_out", "overdue"):
                assert k in row


# ───── Closure Check ────────────────────────────────────────────────
class TestClosureCheck:
    def test_closure_blocked_by_pending_returnable(self, client):
        r = client.get(f"{BASE_URL}/api/inv3/project-closure-check/{PROJECT_CODE}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["project_code"] == PROJECT_CODE
        # Returnable=3 for items[0] still outstanding, so should be blocked
        assert d["can_close"] is False
        assert d["pending_returnable_count"] >= 1
        assert d["blockers"] and isinstance(d["blockers"], list)

    def test_closure_clean_project_can_close(self, client):
        # Random project with no activity should be cleanly closable
        clean_code = f"TEST_CLEAN_{uuid.uuid4().hex[:6]}"
        r = client.get(f"{BASE_URL}/api/inv3/project-closure-check/{clean_code}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["can_close"] is True
        assert d["blockers"] == []
