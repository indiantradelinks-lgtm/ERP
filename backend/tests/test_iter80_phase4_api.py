"""Iter 80 — Phase 4 Store & Inventory HTTP API e2e tests.

Covers: PPE Issue+Expiry+Inspection, Damage/Loss approval, Scrap+Sale, Recovery,
Employee Clearance, Tool Register, Transit Exceptions.
Uses live preview backend via REACT_APP_BACKEND_URL.
"""
from __future__ import annotations
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def test_item(admin):
    """Create a PPE-like inventory item once for the whole module."""
    body = {
        "name": "TEST_PPE_iter80_helmet",
        "code": f"TEST-PPE-{int(time.time())}",
        "category": "PPE", "unit": "Nos",
        "quantity": 100, "rate": 500, "min_stock": 5,
    }
    r = admin.post(f"{API}/inventory", json=body, timeout=20)
    assert r.status_code in (200, 201), f"create inventory failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def high_value_item(admin):
    body = {
        "name": "TEST_HV_iter80_tool",
        "code": f"TEST-HV-{int(time.time())}",
        "category": "Tools", "unit": "Nos",
        "quantity": 50, "rate": 30000, "min_stock": 1,
    }
    r = admin.post(f"{API}/inventory", json=body, timeout=20)
    assert r.status_code in (200, 201)
    return r.json()


# ──────────────────────────────────────────────────────────────────
# 1. PPE Issue + Expiry + Inspection
# ──────────────────────────────────────────────────────────────────
class TestPPEIssue:
    def test_ppe_issue_success(self, admin, test_item):
        body = {
            "employee_id": "TEST_EMP_iter80",
            "employee_name": "Iter80 Tester",
            "project_code": "TEST_PRJ_ITER80",
            "item_id": test_item["id"],
            "quantity": 2,
            "issue_type": "new",
            "expiry_date": "2027-01-01",
        }
        r = admin.post(f"{API}/inv4/ppe-issues", json=body, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "issued"
        assert d["issue_no"].startswith("PPE-")
        assert d["quantity"] == 2
        assert d["value"] == round(2 * test_item["rate"], 2)

    def test_ppe_issue_invalid_issue_type(self, admin, test_item):
        r = admin.post(f"{API}/inv4/ppe-issues", json={
            "employee_id": "X", "item_id": test_item["id"], "quantity": 1, "issue_type": "BAD",
        })
        assert r.status_code == 400
        assert "issue_type" in r.text

    def test_ppe_issue_insufficient_stock(self, admin, test_item):
        r = admin.post(f"{API}/inv4/ppe-issues", json={
            "employee_id": "X", "item_id": test_item["id"], "quantity": 999999,
        })
        assert r.status_code == 400
        assert "insufficient" in r.text.lower() or "available" in r.text.lower()

    def test_ppe_issue_qty_zero(self, admin, test_item):
        r = admin.post(f"{API}/inv4/ppe-issues", json={
            "employee_id": "X", "item_id": test_item["id"], "quantity": 0,
        })
        assert r.status_code == 400

    def test_ppe_issue_item_not_found(self, admin):
        r = admin.post(f"{API}/inv4/ppe-issues", json={
            "employee_id": "X", "item_id": "nonexistent-id", "quantity": 1,
        })
        assert r.status_code == 404

    def test_ppe_issues_list_filter(self, admin):
        r = admin.get(f"{API}/inv4/ppe-issues?employee_id=TEST_EMP_iter80")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert any(row["employee_id"] == "TEST_EMP_iter80" for row in rows)

    def test_ppe_expiry_register(self, admin):
        r = admin.get(f"{API}/inv4/ppe-expiry-register?within_days=400")
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "count" in d and "horizon" in d
        # Our test row has expiry_date=2027-01-01 which is within 400 days from 2026-Jan
        # Just assert response shape
        for r0 in d["rows"]:
            assert "expired" in r0 and "days_to_expiry" in r0


class TestPPEInspection:
    def test_inspection_missing_target(self, admin):
        r = admin.post(f"{API}/inv4/ppe-inspections", json={
            "inspection_date": "2026-01-15",
            "inspector_name": "Tester",
            "result": "pass",
        })
        assert r.status_code == 400

    def test_inspection_invalid_result(self, admin, test_item):
        r = admin.post(f"{API}/inv4/ppe-inspections", json={
            "inspection_date": "2026-01-15",
            "inspector_name": "Tester",
            "result": "garbage",
            "item_id": test_item["id"],
        })
        assert r.status_code == 400

    def test_inspection_pass_success(self, admin, test_item):
        r = admin.post(f"{API}/inv4/ppe-inspections", json={
            "inspection_date": "2026-01-15",
            "inspector_name": "Tester",
            "result": "pass",
            "item_id": test_item["id"],
        })
        assert r.status_code == 200
        assert r.json()["result"] == "pass"


# ──────────────────────────────────────────────────────────────────
# 2. Damage / Loss
# ──────────────────────────────────────────────────────────────────
class TestDamageLoss:
    def test_dl_missing_attachment(self, admin, test_item):
        r = admin.post(f"{API}/inv4/damage-loss", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 1, "reason": "drop"
        })
        assert r.status_code == 400 and "attachment" in r.text.lower()

    def test_dl_missing_reason(self, admin, test_item):
        r = admin.post(f"{API}/inv4/damage-loss", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 1, "reason": "",
            "attachment_url": "https://x.com/photo.jpg",
        })
        assert r.status_code == 400 and "reason" in r.text.lower()

    def test_dl_qty_zero(self, admin, test_item):
        r = admin.post(f"{API}/inv4/damage-loss", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 0, "reason": "x",
            "attachment_url": "https://x.com/a.jpg",
        })
        assert r.status_code == 400

    def test_dl_low_value_create_and_approve(self, admin, test_item):
        r = admin.post(f"{API}/inv4/damage-loss", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 1, "reason": "Dropped",
            "attachment_url": "https://x.com/a.jpg",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["needs_finance_approval"] is False
        assert d["status"] == "submitted"
        assert d["value"] == 500.0
        dl_id = d["id"]
        # Self-approve guard: reporter == approver (admin) — admin is super_admin so allowed
        ar = admin.post(f"{API}/inv4/damage-loss/{dl_id}/approve")
        assert ar.status_code == 200, ar.text
        assert ar.json()["status"] == "approved"

    def test_dl_high_value_sets_needs_finance(self, admin, high_value_item):
        r = admin.post(f"{API}/inv4/damage-loss", json={
            "date": "2026-01-15", "item_id": high_value_item["id"], "quantity": 1,
            "reason": "Crashed", "attachment_url": "https://x.com/b.jpg",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["needs_finance_approval"] is True
        assert d["value"] >= 25000

    def test_dl_recoverable_creates_recovery_row(self, admin, test_item):
        r = admin.post(f"{API}/inv4/damage-loss", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 1, "reason": "Negligence",
            "attachment_url": "https://x.com/c.jpg",
            "recoverable": True, "recovery_amount": 500,
            "employee_id": "TEST_EMP_REC_iter80", "employee_name": "Recoverer",
        })
        assert r.status_code == 200
        dl_id = r.json()["id"]
        admin.post(f"{API}/inv4/damage-loss/{dl_id}/approve")
        # Check recovery created
        rr = admin.get(f"{API}/inv4/recoveries?employee_id=TEST_EMP_REC_iter80")
        assert rr.status_code == 200
        d2 = rr.json()
        assert d2["count"] >= 1
        assert any(row["source_id"] == dl_id for row in d2["rows"])


# ──────────────────────────────────────────────────────────────────
# 3. Scrap workflow
# ──────────────────────────────────────────────────────────────────
class TestScrap:
    @pytest.fixture(scope="class")
    def scrap_id(self, admin, test_item):
        r = admin.post(f"{API}/inv4/scrap-entries", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 3,
            "reason": "Beyond repair",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["scrap_no"].startswith("SCR-")
        assert d["status"] == "submitted"
        return d["id"]

    def test_scrap_qty_zero(self, admin, test_item):
        r = admin.post(f"{API}/inv4/scrap-entries", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 0, "reason": "x",
        })
        assert r.status_code == 400

    def test_scrap_missing_reason(self, admin, test_item):
        r = admin.post(f"{API}/inv4/scrap-entries", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 1, "reason": "",
        })
        assert r.status_code == 400

    def test_scrap_approve(self, admin, scrap_id):
        r = admin.post(f"{API}/inv4/scrap-entries/{scrap_id}/approve")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

    def test_scrap_sale_requires_approved(self, admin, test_item):
        # Create unapproved scrap and try to sell it
        sc = admin.post(f"{API}/inv4/scrap-entries", json={
            "date": "2026-01-15", "item_id": test_item["id"], "quantity": 1, "reason": "x",
        }).json()
        r = admin.post(f"{API}/inv4/scrap-sales", json={
            "scrap_entry_ids": [sc["id"]], "buyer_name": "B", "sale_rate": 10, "quantity": 1,
        })
        assert r.status_code == 400 and "not approved" in r.text.lower()

    def test_scrap_sale_create_and_approve(self, admin, scrap_id):
        r = admin.post(f"{API}/inv4/scrap-sales", json={
            "scrap_entry_ids": [scrap_id], "buyer_name": "TestBuyer",
            "sale_rate": 100, "quantity": 3, "gst_applicable": True, "gst_rate": 18,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["taxable_value"] == 300.0
        assert d["gst_amount"] == 54.0
        assert d["total_value"] == 354.0
        sale_id = d["id"]
        ar = admin.post(f"{API}/inv4/scrap-sales/{sale_id}/approve")
        assert ar.status_code == 200
        assert ar.json()["status"] == "approved"


# ──────────────────────────────────────────────────────────────────
# 4. Recovery / Clearance / Tool / Transit
# ──────────────────────────────────────────────────────────────────
class TestRegisters:
    def test_recoveries_list(self, admin):
        r = admin.get(f"{API}/inv4/recoveries")
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "total_pending" in d and "rows" in d

    def test_waive_requires_reason(self, admin):
        # Find a pending recovery to test against
        recs = admin.get(f"{API}/inv4/recoveries?status=pending").json()["rows"]
        if not recs:
            pytest.skip("no pending recovery available")
        rid = recs[0]["id"]
        r = admin.post(f"{API}/inv4/recoveries/{rid}/waive", json={})
        assert r.status_code == 400 and "reason" in r.text.lower()

    def test_mark_recovered(self, admin):
        recs = admin.get(f"{API}/inv4/recoveries?status=pending").json()["rows"]
        if not recs:
            pytest.skip("no pending recovery")
        rid = recs[0]["id"]
        r = admin.post(f"{API}/inv4/recoveries/{rid}/mark-recovered", json={"note": "Recovered cash"})
        assert r.status_code == 200
        assert r.json()["status"] == "recovered"

    def test_employee_clearance(self, admin):
        r = admin.get(f"{API}/inv4/employee-clearance/TEST_EMP_iter80")
        assert r.status_code == 200
        d = r.json()
        for k in ("can_clear", "total_blockers", "outstanding_value", "pending_by_kind",
                  "pending_ppe", "pending_recoveries"):
            assert k in d
        for kind in ("tool", "asset", "material", "consumable"):
            assert kind in d["pending_by_kind"]

    def test_tool_register(self, admin):
        r = admin.get(f"{API}/inv4/tool-issue-register")
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "pending_count" in d and "pending_value" in d and "rows" in d

    def test_employee_pending_tools(self, admin):
        r = admin.get(f"{API}/inv4/employee-pending-tools/TEST_EMP_iter80")
        assert r.status_code == 200
        d = r.json()
        assert d["employee_id"] == "TEST_EMP_iter80"
        assert "rows" in d and "total_value" in d

    def test_transit_exceptions(self, admin):
        r = admin.get(f"{API}/inv4/transit-exceptions")
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "rows" in d
        assert "total_shortage_value" in d and "total_damaged_value" in d


# ──────────────────────────────────────────────────────────────────
# 5. Regression — Phase 1+2+3 still alive
# ──────────────────────────────────────────────────────────────────
class TestRegression:
    def test_inventory_list(self, admin):
        r = admin.get(f"{API}/inventory")
        assert r.status_code == 200

    def test_inv2_procurement_pipeline(self, admin):
        r = admin.get(f"{API}/inv2/procurement-pipeline")
        assert r.status_code == 200

    def test_inv3_material_requests(self, admin):
        r = admin.get(f"{API}/inv3/material-requests")
        assert r.status_code == 200
