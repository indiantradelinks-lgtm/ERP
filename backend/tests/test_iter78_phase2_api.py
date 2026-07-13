"""Iter 78 — Phase 2 Store & Inventory: full HTTP API regression.

Tests the new /api/inv2/* endpoints + GRN enrichment + manual_grn override.
"""
import os
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"
PM_EMAIL = "test_pm@erp.com"
PM_PASSWORD = "PM@12345"


# ──────────────────────── fixtures ────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def pm_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": PM_EMAIL, "password": PM_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"PM login unavailable: {r.status_code}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ──────────────────────── Phase 2 GET smoke ────────────────────────
class TestPhase2GETs:
    def test_stock_shortage_suggestions(self, admin_session):
        r = admin_session.get(f"{API}/inv2/stock-shortage-suggestions", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "count" in d and "rows" in d
        assert isinstance(d["rows"], list)

    def test_pending_pos_for_grn(self, admin_session):
        r = admin_session.get(f"{API}/inv2/pending-pos-for-grn", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("count", "rows", "total_pending_value"):
            assert k in d
        for row in d["rows"][:3]:
            for k in ("po_id", "po_number", "lines", "pending_qty_total", "pending_value_total"):
                assert k in row
            for ln in row["lines"][:1]:
                # ordered - received == pending
                assert abs((ln["ordered_qty"] - ln["received_qty"]) - ln["pending_qty"]) < 1e-3

    def test_stock_inward_report(self, admin_session):
        df = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%d")
        dt = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = admin_session.get(f"{API}/inv2/stock-inward-report",
                              params={"date_from": df, "date_to": dt}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("count", "total_value", "by_type", "rows"):
            assert k in d
        assert isinstance(d["by_type"], dict)

    def test_grn_pending_invoice(self, admin_session):
        r = admin_session.get(f"{API}/inv2/grn-pending-invoice", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("count", "matched_count", "total_count", "rows"):
            assert k in d
        for row in d["rows"][:3]:
            assert "days_pending" in row and row["days_pending"] >= 0

    def test_accounts_grn_visibility(self, admin_session):
        r = admin_session.get(f"{API}/inv2/accounts-grn-visibility", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "rows" in d
        for row in d["rows"][:5]:
            assert "three_way_match" in row
            # three_way_match True only if bill exists AND amount diff < 1
            if row.get("bill_id"):
                if row.get("bill_amount") is not None:
                    expected = abs(float(row["bill_amount"]) - float(row.get("estimated_grn_value") or 0)) < 1.0
                    assert row["three_way_match"] == expected
            else:
                assert row["three_way_match"] is False

    def test_inspection_hold(self, admin_session):
        r = admin_session.get(f"{API}/inv2/inspection-hold", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "count" in d and "rows" in d

    def test_procurement_pipeline_keys(self, admin_session):
        r = admin_session.get(f"{API}/inv2/procurement-pipeline", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("pr_pending_count", "pr_pending_value", "po_pending_count",
                  "po_pending_value", "grn_30d_count", "grn_30d_value",
                  "emergency_pr_count"):
            assert k in d, f"missing key {k}"
        # numeric sanity
        assert d["grn_30d_count"] >= 0
        assert d["pr_pending_value"] >= 0


# ──────────────────────── PR from Stock ────────────────────────
class TestPRFromStock:
    @pytest.fixture(scope="class")
    def sample_item(self, admin_session):
        # Use any existing inventory item
        r = admin_session.get(f"{API}/inventory", timeout=30)
        assert r.status_code == 200, r.text[:200]
        items = r.json() if isinstance(r.json(), list) else r.json().get("items") or r.json().get("rows") or []
        if not items:
            pytest.skip("No inventory items in DB to use for PR test")
        return items[0]

    def test_pr_validation_zero_qty(self, admin_session, sample_item):
        r = admin_session.post(f"{API}/inv2/pr-from-stock", json={
            "priority": "normal",
            "reason": "stock_below_reorder",
            "lines": [{"item_id": sample_item["id"], "required_qty": 0}],
        }, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"

    def test_pr_validation_invalid_priority(self, admin_session, sample_item):
        r = admin_session.post(f"{API}/inv2/pr-from-stock", json={
            "priority": "INVALID_X",
            "reason": "stock_below_reorder",
            "lines": [{"item_id": sample_item["id"], "required_qty": 5}],
        }, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"

    def test_pr_validation_missing_item(self, admin_session):
        r = admin_session.post(f"{API}/inv2/pr-from-stock", json={
            "priority": "normal",
            "reason": "stock_below_reorder",
            "lines": [{"item_id": "NON_EXISTENT_ITEM_ID", "required_qty": 5}],
        }, timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"

    def test_pr_create_success_and_persisted(self, admin_session, sample_item):
        r = admin_session.post(f"{API}/inv2/pr-from-stock", json={
            "priority": "normal",
            "reason": "stock_below_reorder",
            "remarks": "TEST_iter78 PR from stock",
            "lines": [{"item_id": sample_item["id"], "required_qty": 7, "remarks": "TEST line"}],
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["pr_number"].startswith("PR-"), d["pr_number"]
        parts = d["pr_number"].split("-")
        assert len(parts) == 3 and len(parts[1]) == 6 and len(parts[2]) == 5
        assert d["status"] == "submitted"
        assert d["source"] == "stock_shortage"
        assert d["priority"] in ("normal", "urgent")  # may auto-bump
        # Persistence: GET /api/procurement/prs and find the new PR
        rr = admin_session.get(f"{API}/procurement/prs", timeout=30)
        assert rr.status_code == 200, rr.text[:200]
        body = rr.json()
        prs = body if isinstance(body, list) else (body.get("rows") or body.get("items") or [])
        numbers = [p.get("pr_number") for p in prs]
        assert d["pr_number"] in numbers, f"new PR not in list (got {len(numbers)} PRs)"


# ──────────────────────── GRN enrichment ────────────────────────
class TestGRNEnrichment:
    def test_grn_model_fields_accepted_via_options(self, admin_session):
        """Hit OpenAPI to confirm the Phase 2 fields are in the GRN schema."""
        r = admin_session.get(f"{API}/openapi.json", timeout=30)
        if r.status_code != 200:
            pytest.skip("OpenAPI not available")
        spec = r.json()
        schemas = spec.get("components", {}).get("schemas", {})
        grnin = schemas.get("GRNIn")
        if not grnin:
            pytest.skip("GRNIn schema not in openapi")
        props = grnin.get("properties", {})
        for k in ("vendor_invoice_no", "vendor_invoice_date", "vendor_invoice_value",
                  "vehicle_number", "transporter_name", "transporter_lr_no",
                  "attachment_url", "attachment_urls", "project_code", "manual_grn"):
            assert k in props, f"GRNIn missing property {k}"

    def test_manual_grn_pm_forbidden(self, admin_session, pm_session):
        """A non-elevated role (project_manager) must get 403 when posting
        manual_grn=true against a non-approved PO. We need a real non-approved
        PO to actually trigger the manual_grn branch (PO not found short-circuits)."""
        # Find a non-approved PO (draft, pending_approval, rejected, etc.)
        r = admin_session.get(f"{API}/procurement/pos", timeout=30)
        if r.status_code != 200:
            pytest.skip(f"PO list endpoint missing: {r.status_code}")
        body = r.json()
        pos = body if isinstance(body, list) else (body.get("rows") or body.get("items") or [])
        non_approved = [p for p in pos if p.get("status") not in (None, "approved", "sent_to_vendor", "partially_received")]
        if not non_approved:
            pytest.skip("No non-approved PO available to test manual_grn override")
        po = non_approved[0]
        r2 = pm_session.post(f"{API}/procurement/grns", json={
            "po_id": po["id"],
            "manual_grn": True,
            "items": [],
            "vendor_invoice_no": "TEST_PM_INV_iter78",
        }, timeout=30)
        # PM lacks elevated role -> 403; or lacks grn-write entirely -> 403/401
        assert r2.status_code in (403, 401), f"expected 403/401 got {r2.status_code}: {r2.text[:200]}"
