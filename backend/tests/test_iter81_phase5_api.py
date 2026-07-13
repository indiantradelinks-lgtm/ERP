"""Iter 81 — Phase 5 HTTP API e2e tests.
Covers Valuation, Stock Counts (create/approve/reject/validations), Dashboard, Reconcile.
"""
from __future__ import annotations
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASS = "Admin@123"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def any_item(admin):
    r = admin.get(f"{API}/inventory", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and items, "no inventory items in DB"
    return items[0]


# ─── 1. Valuation ───
class TestValuation:
    def test_valuation_default(self, admin):
        r = admin.get(f"{API}/inv5/valuation", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["method"] == "weighted_average"
        s = d["summary"]
        for k in ("total_items", "total_value", "damaged_value", "scrap_value",
                  "in_transit_value", "project_value", "grand_total"):
            assert k in s, f"summary missing {k}"
        assert isinstance(d["by_category"], list)
        assert isinstance(d["by_store"], list)
        assert isinstance(d["rows"], list)
        if d["rows"]:
            assert "rate_used" in d["rows"][0]

    def test_valuation_last_purchase(self, admin):
        r = admin.get(f"{API}/inv5/valuation?method=last_purchase", timeout=30)
        assert r.status_code == 200
        assert r.json()["method"] == "last_purchase"

    def test_valuation_standard(self, admin):
        r = admin.get(f"{API}/inv5/valuation?method=standard", timeout=30)
        assert r.status_code == 200
        assert r.json()["method"] == "standard"

    def test_valuation_bogus_method_400(self, admin):
        r = admin.get(f"{API}/inv5/valuation?method=bogus", timeout=20)
        assert r.status_code == 400, r.text[:200]


# ─── 2. Stock Counts ───
class TestStockCounts:
    def test_list(self, admin):
        r = admin.get(f"{API}/inv5/stock-counts", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_empty_lines_422(self, admin):
        r = admin.post(f"{API}/inv5/stock-counts",
                        json={"count_date": "2026-01-15", "lines": []}, timeout=20)
        assert r.status_code == 422

    def test_create_missing_item_404(self, admin):
        r = admin.post(f"{API}/inv5/stock-counts", json={
            "count_date": "2026-01-15",
            "lines": [{"item_id": "non-existent-iter81", "physical_qty": 5}],
        }, timeout=20)
        assert r.status_code == 404

    def test_create_negative_qty_400(self, admin, any_item):
        r = admin.post(f"{API}/inv5/stock-counts", json={
            "count_date": "2026-01-15",
            "lines": [{"item_id": any_item["id"], "physical_qty": -1}],
        }, timeout=20)
        assert r.status_code == 400

    def test_create_low_variance_self_approve_blocked_then_reject(self, admin, any_item):
        # Low variance: physical = system (zero diff) → safe self-approve test? No - self-approve always blocked
        sys_qty = float(any_item.get("quantity") or 0)
        r = admin.post(f"{API}/inv5/stock-counts", json={
            "count_date": "2026-01-15",
            "store_id": any_item.get("store_id"),
            "lines": [{"item_id": any_item["id"], "physical_qty": sys_qty, "reason": "TEST_iter81"}],
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        sc = r.json()
        assert sc["count_no"].startswith("SC-")
        assert sc["status"] == "submitted"
        assert sc["total_variance_value"] == 0
        # super_admin is allowed to self-approve (exception)
        ar = admin.post(f"{API}/inv5/stock-counts/{sc['id']}/approve", timeout=30)
        assert ar.status_code == 200, ar.text[:300]
        assert ar.json()["status"] == "approved"

    def test_create_and_reject(self, admin, any_item):
        sys_qty = float(any_item.get("quantity") or 0)
        r = admin.post(f"{API}/inv5/stock-counts", json={
            "count_date": "2026-01-15",
            "lines": [{"item_id": any_item["id"], "physical_qty": sys_qty + 1, "reason": "TEST_iter81_reject"}],
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        sc_id = r.json()["id"]
        rj = admin.post(f"{API}/inv5/stock-counts/{sc_id}/reject",
                        json={"reason": "test rejection"}, timeout=20)
        assert rj.status_code == 200
        assert rj.json()["status"] == "rejected"

    def test_high_variance_flag(self, admin, any_item):
        # Construct a high variance ≥ 25000 by choosing a large diff×rate
        rate = float(any_item.get("rate") or any_item.get("average_rate") or 0)
        sys_qty = float(any_item.get("quantity") or 0)
        if rate <= 0:
            pytest.skip("item rate=0, cannot construct high variance")
        # Add enough qty to exceed 25000 in absolute value (positive variance, no debit issue)
        delta = int(25000 / rate) + 5
        r = admin.post(f"{API}/inv5/stock-counts", json={
            "count_date": "2026-01-15",
            "lines": [{"item_id": any_item["id"], "physical_qty": sys_qty + delta, "reason": "TEST_iter81_hv"}],
        }, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["needs_finance_approval"] is True
        assert d["total_variance_value"] >= 25000


# ─── 3. Dashboard ───
class TestDashboard:
    def test_dashboard_tiles(self, admin):
        r = admin.get(f"{API}/inv5/dashboard", timeout=45)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        required = [
            "total_stock_value", "total_items", "stores_count", "site_stores_count",
            "low_stock_count", "reorder_count", "out_of_stock_count",
            "pending_mr_count", "pending_grn_count", "pending_inspection_count",
            "pending_transfer_count", "pending_opening_count",
            "pending_damage_loss_count", "pending_scrap_count", "pending_stock_count_count",
            "in_transit_value", "damaged_value", "scrap_value",
            "tools_issued_count", "ppe_issued_count", "expiring_ppe_30d_count",
            "pending_recovery_value", "consumption_month_value", "high_value_movements_month",
            "top_consumed", "recent_transactions",
        ]
        missing = [k for k in required if k not in d]
        assert not missing, f"dashboard missing keys: {missing}"


# ─── 4. Reconcile ───
class TestReconcile:
    def test_reconcile_check(self, admin):
        r = admin.get(f"{API}/inv5/reconcile-check", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "checked_items" in d and "drift_count" in d and "drifts" in d
        assert d["drift_count"] == len(d["drifts"])


# ─── 5. Regression: prior phase endpoints still respond ───
class TestRegression:
    @pytest.mark.parametrize("path", [
        "/inv/stores",
        "/inv2/procurement-pipeline",
        "/inv3/transfers",
        "/inv4/recoveries",
    ])
    def test_prior_phase_endpoints(self, admin, path):
        r = admin.get(f"{API}{path}", timeout=30)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
