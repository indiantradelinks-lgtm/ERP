"""Phase C (Inventory Intel) + Phase D (Procurement Intel) + Phase A-debt (RFQ select-vendor status).

Run:
  pytest /app/backend/tests/test_phase_cd.py -v --tb=short \
      --junitxml=/app/test_reports/pytest/phase_cd.xml
"""
import io
import os
import csv
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PW = "Admin@123"


# ───── fixtures ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def purchase_officer():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "purchase@erp.com", "password": "Purchase@123"}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"purchase_officer login unavailable: {r.status_code}")
    return s


# ───── Phase C — InventoryIntel ────────────────────────────────────────────
class TestImportTemplate:
    def test_import_template_csv(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/import-template", timeout=20)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "").lower()
        lines = r.text.splitlines()
        assert len(lines) >= 2, "must include header + ≥1 data row"
        header = lines[0]
        expected = "item_code,name,category,unit,opening_quantity,rate,store_location,batch,serial_no,vendor_name,asset_tag,reorder_level,min_stock,max_stock"
        assert header == expected, f"header mismatch:\n got: {header}\n want: {expected}"


class TestBulkImport:
    @pytest.fixture(scope="class")
    def csv_payload(self):
        tag = uuid.uuid4().hex[:8]
        rows = [
            ["item_code", "name", "category", "unit", "opening_quantity", "rate",
             "store_location", "batch", "serial_no", "vendor_name", "asset_tag",
             "reorder_level", "min_stock", "max_stock"],
            [f"TEST-BOLT-{tag}", f"TEST Bolt {tag}", "Consumable", "Nos", "100", "10.5",
             "Main", "", "", "VendorX", "", "20", "10", "500"],
            [f"TEST-NUT-{tag}",  f"TEST Nut {tag}",  "Consumable", "Nos", "50", "5",
             "Main", "", "", "VendorX", "", "20", "10", "500"],
        ]
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        return tag, buf.getvalue().encode("utf-8")

    def test_import_success(self, admin, csv_payload):
        tag, data = csv_payload
        r = admin.post(f"{BASE_URL}/api/inventory-intel/import.csv",
                       files={"file": ("imp.csv", data, "text/csv")}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "summary" in body and {"created", "updated", "errors"} <= set(body["summary"].keys())
        assert body["summary"]["created"] >= 2

    def test_reupload_bumps_updated(self, admin, csv_payload):
        tag, data = csv_payload
        r = admin.post(f"{BASE_URL}/api/inventory-intel/import.csv",
                       files={"file": ("imp2.csv", data, "text/csv")}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["summary"]["updated"] >= 2, f"expected updated>=2 on re-upload, got {body['summary']}"

    def test_row_missing_name_continues(self, admin):
        rows = [
            ["item_code", "name", "category", "unit", "opening_quantity", "rate",
             "store_location", "batch", "serial_no", "vendor_name", "asset_tag",
             "reorder_level", "min_stock", "max_stock"],
            ["TEST-NONAME", "", "Consumable", "Nos", "5", "1", "", "", "", "", "", "", "", ""],
            [f"TEST-OK-{uuid.uuid4().hex[:6]}", "TEST OK Item", "Consumable", "Nos", "5", "1", "", "", "", "", "", "", "", ""],
        ]
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        r = admin.post(f"{BASE_URL}/api/inventory-intel/import.csv",
                       files={"file": ("bad.csv", buf.getvalue().encode(), "text/csv")}, timeout=30)
        assert r.status_code == 200, r.text  # should NOT be 400
        body = r.json()
        assert body["summary"]["errors"] >= 1
        assert any("row" in e and "name" in str(e.get("error", "")).lower() for e in body["errors"])

    def test_missing_required_header_returns_400(self, admin):
        # drop the 'name' column entirely
        rows = [
            ["item_code", "category", "unit", "opening_quantity", "rate"],
            ["TEST-X", "Cons", "Nos", "1", "1"],
        ]
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        r = admin.post(f"{BASE_URL}/api/inventory-intel/import.csv",
                       files={"file": ("noheader.csv", buf.getvalue().encode(), "text/csv")}, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"


class TestValuation:
    def test_fifo(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/valuation?method=fifo", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert b["method"] == "fifo"
        assert isinstance(b["total_value"], (int, float))
        assert isinstance(b["items"], list)
        if b["items"]:
            it = b["items"][0]
            for k in ("item_id", "name", "quantity", "value", "weighted_rate", "layers"):
                assert k in it, f"missing key {k} in valuation item"

    def test_lifo(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/valuation?method=lifo", timeout=30)
        assert r.status_code == 200
        assert r.json()["method"] == "lifo"

    def test_weighted_avg(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/valuation?method=weighted_avg", timeout=30)
        assert r.status_code == 200
        assert r.json()["method"] == "weighted_avg"

    def test_bogus_method_400(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/valuation?method=bogus", timeout=15)
        assert r.status_code == 400


class TestIntelReports:
    def test_aging(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/reports/aging", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert "as_of" in b and "buckets" in b and "summary" in b
        for k in ("0-30d", "30-90d", "90-180d", "180-365d", ">365d", "never_inward"):
            assert k in b["buckets"], f"missing bucket {k}"

    def test_dead_stock(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/reports/dead-stock?days=180", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert b["days_threshold"] == 180
        assert "count" in b and "total_value" in b and isinstance(b["items"], list)
        for it in b["items"][:5]:
            assert float(it.get("quantity") or 0) > 0

    def test_movers(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/reports/movers?days=90", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert b["days_window"] == 90 and "fast_movers" in b and "slow_movers" in b

    def test_idle(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/reports/idle?days=90", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert "count" in b and isinstance(b["items"], list)

    def test_reorder_alerts(self, admin):
        r = admin.get(f"{BASE_URL}/api/inventory-intel/reorder-alerts", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert "count" in b and isinstance(b["items"], list)
        for it in b["items"][:5]:
            assert it["severity"] in ("critical", "high", "warning")


# ───── Phase D — ProcurementIntel ──────────────────────────────────────────
class TestVendorPerf:
    def test_leaderboard(self, admin):
        r = admin.get(f"{BASE_URL}/api/vendor-performance", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert "as_of" in b and isinstance(b["vendors"], list)
        assert len(b["vendors"]) >= 1
        v0 = b["vendors"][0]
        for k in ("vendor_id", "vendor_name", "score", "grade", "po_count",
                  "po_value", "quality_pct", "on_time_pct", "response_pct", "rfqs_invited"):
            assert k in v0, f"missing key {k} in vendor row"

    def test_single_vendor(self, admin):
        leader = admin.get(f"{BASE_URL}/api/vendor-performance", timeout=30).json()
        if not leader["vendors"]:
            pytest.skip("no vendors seeded")
        vid = leader["vendors"][0]["vendor_id"]
        r = admin.get(f"{BASE_URL}/api/vendors/{vid}/performance", timeout=30)
        assert r.status_code == 200
        assert r.json()["vendor_id"] == vid

    def test_single_vendor_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/vendors/__nope__/performance", timeout=15)
        assert r.status_code == 404


class TestBudgetsAndReservations:
    def test_budgets(self, admin):
        r = admin.get(f"{BASE_URL}/api/procurement/budgets", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert "as_of" in b and isinstance(b["budgets"], list)
        for row in b["budgets"][:3]:
            for k in ("budget_reference", "pr_count", "po_count", "committed_value", "departments"):
                assert k in row

    def test_reservations(self, admin):
        r = admin.get(f"{BASE_URL}/api/procurement/reservations", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert "as_of" in b and "open_pr_count" in b and isinstance(b["items"], list)
        for it in b["items"][:3]:
            for k in ("id", "name", "on_hand", "reserved", "available", "shortfall"):
                assert k in it


class TestAuditExplorer:
    def test_admin_can_read(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit/explorer?limit=5", timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert "rows" in b and "count" in b

    def test_resource_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit/explorer?resource=purchase_orders&limit=5", timeout=20)
        assert r.status_code == 200

    def test_action_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit/explorer?action=create&limit=5", timeout=20)
        assert r.status_code == 200

    def test_user_id_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit/explorer?user_id=abc&limit=5", timeout=20)
        assert r.status_code == 200

    def test_date_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/audit/explorer?from_date=2025-01-01&to_date=2030-01-01&limit=5", timeout=20)
        assert r.status_code == 200

    def test_purchase_officer_403(self, purchase_officer):
        r = purchase_officer.get(f"{BASE_URL}/api/audit/explorer?limit=5", timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code}"


# ───── Phase A-debt — RFQ select-vendor sets vendor_selected ───────────────
class TestRfqSelectVendor:
    def test_fresh_chain_select_vendor_status(self, admin):
        # 1) create PR with submit_for_approval=True (chain auto-created)
        pr_payload = {
            "department": "Procurement",
            "priority": "medium",
            "items": [{"name": "TEST_PHC_CD_ITEM", "quantity": 5, "unit": "Nos", "rate": 100}],
            "submit_for_approval": True,
        }
        rpr = admin.post(f"{BASE_URL}/api/procurement/prs", json=pr_payload, timeout=20)
        assert rpr.status_code in (200, 201), f"PR create failed: {rpr.status_code} {rpr.text[:300]}"
        pr = rpr.json()
        pr_id = pr["id"]
        approval_id = pr.get("approval_id")
        # 2) walk the approval chain to 'approved' (super_admin can approve any step)
        # Loop a few times to cover multi-step chains.
        for _ in range(8):
            r = admin.post(f"{BASE_URL}/api/approvals/{approval_id}/action",
                           json={"action": "approve"}, timeout=20)
            if r.status_code not in (200, 201):
                break
            # check if PR is now 'approved'
            got = admin.get(f"{BASE_URL}/api/procurement/prs/{pr_id}", timeout=20)
            if got.status_code == 200 and got.json().get("status") == "approved":
                break
        # 3) get a vendor
        vlist = admin.get(f"{BASE_URL}/api/vendors", timeout=20).json()
        vendors = vlist if isinstance(vlist, list) else vlist.get("items") or []
        if not vendors:
            pytest.skip("no vendors available")
        vid = vendors[0]["id"]
        vname = vendors[0].get("name")
        # 4) create RFQ from PR
        rfq_payload = {
            "pr_id": pr_id,
            "vendors": [{"vendor_id": vid, "vendor_name": vname}],
            "notes": "TEST_PHC_CD",
        }
        rrfq = admin.post(f"{BASE_URL}/api/procurement/rfqs", json=rfq_payload, timeout=20)
        assert rrfq.status_code in (200, 201), f"rfq create failed: {rrfq.status_code} {rrfq.text[:300]}"
        rfq_id = rrfq.json()["id"]
        # 5) vendor responds with a quote
        quote = {"vendor_id": vid, "rate_quoted": 99, "delivery_days": 7}
        rq = admin.post(f"{BASE_URL}/api/procurement/rfqs/{rfq_id}/respond", json=quote, timeout=20)
        assert rq.status_code in (200, 201), f"respond failed: {rq.status_code} {rq.text[:300]}"
        # 6) select vendor
        sel = admin.post(f"{BASE_URL}/api/procurement/rfqs/{rfq_id}/select-vendor",
                         json={"vendor_id": vid}, timeout=20)
        assert sel.status_code in (200, 201), sel.text
        # 7) verify status == 'vendor_selected' (NOT 'approved' or 'converted_to_po')
        got = admin.get(f"{BASE_URL}/api/procurement/rfqs/{rfq_id}", timeout=20)
        assert got.status_code == 200, got.text
        status = got.json().get("status")
        assert status == "vendor_selected", f"expected status=vendor_selected, got {status!r}"
