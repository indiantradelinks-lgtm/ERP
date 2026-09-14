"""Iteration 186 — Receivables reports (Collection, TDS Receivable, Retention) + TDS certificate + Receipt drill.

Backend endpoints covered:
  GET  /api/billing/reports/collection (+ /export)
  GET  /api/billing/reports/tds-receivable (+ /export)
  GET  /api/billing/reports/retention-receivable/export
  PATCH /api/billing/receipts/{id}/tds-certificate
  GET  /api/billing/receipts/{id} (journal_entry + invoices enrich)
RBAC: super_admin ok, sales_executive 403.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read frontend .env directly
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE_URL}/api"

ADMIN = ("admin@erp.com", "Admin@123")
SALES = ("sales@erp.com", "Sales@123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def sales():
    try:
        return _login(*SALES)
    except AssertionError:
        pytest.skip("sales user not available")


# ── Collection report ────────────────────────────────────────────────
class TestCollectionReport:
    def test_unfiltered(self, admin):
        r = admin.get(f"{API}/billing/reports/collection", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("rows", "trend", "by_client", "modes", "totals"):
            assert k in d, f"missing {k}"
        assert isinstance(d["rows"], list)
        assert isinstance(d["trend"], list)
        assert isinstance(d["by_client"], list)
        for k in ("total_adjusted", "amount_received", "tds_deducted", "retention_deducted", "count"):
            assert k in d["totals"], f"totals missing {k}"
        assert d["totals"]["count"] == len(d["rows"])
        # save for downstream tests
        pytest.rows_all = d["rows"]
        pytest.totals_all = d["totals"]

    def test_trend_buckets_have_month(self, admin):
        r = admin.get(f"{API}/billing/reports/collection", timeout=30).json()
        for b in r["trend"]:
            assert "month" in b and "amount_received" in b and "count" in b

    def test_filter_by_client_name(self, admin):
        rows = getattr(pytest, "rows_all", None) or admin.get(f"{API}/billing/reports/collection").json()["rows"]
        if not rows:
            pytest.skip("no receipts to filter")
        cn = rows[0]["client_name"]
        r = admin.get(f"{API}/billing/reports/collection", params={"client_name": cn}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert all(row.get("client_name") == cn for row in d["rows"])
        assert d["totals"]["count"] <= pytest.totals_all["count"]

    def test_filter_by_mode(self, admin):
        rows = pytest.rows_all
        modes = [r.get("mode") for r in rows if r.get("mode")]
        if not modes:
            pytest.skip("no mode data")
        m = modes[0]
        r = admin.get(f"{API}/billing/reports/collection", params={"mode": m}, timeout=30).json()
        assert all(row.get("mode") == m for row in r["rows"])

    def test_date_range_subset(self, admin):
        r = admin.get(f"{API}/billing/reports/collection",
                      params={"start": "2000-01-01", "end": "2000-12-31"}, timeout=30).json()
        assert r["totals"]["count"] == 0
        assert r["rows"] == []

    def test_export_csv(self, admin):
        r = admin.get(f"{API}/billing/reports/collection/export", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        body = r.content.decode("utf-8-sig", errors="replace")
        assert "Receipt No" in body.splitlines()[0]

    def test_rbac_sales_denied(self, sales):
        r = sales.get(f"{API}/billing/reports/collection", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}"


# ── TDS Receivable report ────────────────────────────────────────────
class TestTDSReceivable:
    def test_report_shape(self, admin):
        r = admin.get(f"{API}/billing/reports/tds-receivable", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("clients", "total_tds", "certificate_received", "certificate_pending", "fy_options"):
            assert k in d
        assert isinstance(d["clients"], list)
        assert isinstance(d["fy_options"], list)
        if d["clients"]:
            first_rcpt = d["clients"][0]["receipts"][0]
            for k in ("id", "receipt_no", "fy", "quarter", "certificate_received"):
                assert k in first_rcpt
        pytest.tds_data = d

    def test_filter_pending(self, admin):
        r = admin.get(f"{API}/billing/reports/tds-receivable",
                      params={"cert_status": "pending"}, timeout=30).json()
        for c in r["clients"]:
            for rc in c["receipts"]:
                assert rc["certificate_received"] is False

    def test_filter_received(self, admin):
        r = admin.get(f"{API}/billing/reports/tds-receivable",
                      params={"cert_status": "received"}, timeout=30).json()
        for c in r["clients"]:
            for rc in c["receipts"]:
                assert rc["certificate_received"] is True

    def test_export_csv(self, admin):
        r = admin.get(f"{API}/billing/reports/tds-receivable/export", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_rbac_sales_denied(self, sales):
        r = sales.get(f"{API}/billing/reports/tds-receivable", timeout=30)
        assert r.status_code == 403


# ── TDS Certificate PATCH ───────────────────────────────────────────
class TestTDSCertificate:
    def _pick_receipt_with_tds(self, admin):
        d = admin.get(f"{API}/billing/reports/tds-receivable").json()
        for c in d["clients"]:
            for rc in c["receipts"]:
                return rc["id"], rc["receipt_no"], rc["certificate_received"]
        pytest.skip("no receipt with TDS")

    def test_mark_and_clear(self, admin):
        rid, rno, _prev = self._pick_receipt_with_tds(admin)
        # Mark received
        r = admin.patch(f"{API}/billing/receipts/{rid}/tds-certificate",
                        json={"received": True, "certificate_no": "16A/TEST/ITER186",
                              "certificate_date": "2026-01-15", "remarks": "iter186 test"},
                        timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["ok"] is True
        assert b["tds_certificate"]["certificate_no"] == "16A/TEST/ITER186"

        # Verify in report
        got = admin.get(f"{API}/billing/reports/tds-receivable",
                        params={"cert_status": "received"}).json()
        found = False
        for c in got["clients"]:
            for rc in c["receipts"]:
                if rc["id"] == rid and rc["certificate_received"] is True:
                    found = True
                    break
        assert found, "receipt not shown as certificate_received after PATCH"

        # Clear
        r2 = admin.patch(f"{API}/billing/receipts/{rid}/tds-certificate",
                         json={"received": False}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["tds_certificate"] == {}

    def test_404_unknown(self, admin):
        r = admin.patch(f"{API}/billing/receipts/RCPT-NOPE-XYZ/tds-certificate",
                        json={"received": True}, timeout=30)
        assert r.status_code == 404

    def test_400_no_tds(self, admin):
        """Find a receipt with zero TDS and try to mark cert → 400."""
        rows = admin.get(f"{API}/billing/reports/collection").json()["rows"]
        target = next((r for r in rows if float(r.get("tds_deducted") or 0) == 0), None)
        if not target:
            pytest.skip("no zero-TDS receipt to test")
        r = admin.patch(f"{API}/billing/receipts/{target['id']}/tds-certificate",
                        json={"received": True}, timeout=30)
        assert r.status_code == 400

    def test_rbac_sales_denied(self, sales, admin):
        rid, *_ = self._pick_receipt_with_tds(admin)
        r = sales.patch(f"{API}/billing/receipts/{rid}/tds-certificate",
                        json={"received": True}, timeout=30)
        assert r.status_code == 403


# ── Retention export & receipt drill-down ───────────────────────────
class TestRetentionAndDrill:
    def test_retention_export(self, admin):
        r = admin.get(f"{API}/billing/reports/retention-receivable/export", timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_retention_report(self, admin):
        r = admin.get(f"{API}/billing/reports/retention-receivable", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "clients" in d and "total_retention" in d

    def test_receipt_drill_enrichment(self, admin):
        rows = admin.get(f"{API}/billing/reports/collection").json()["rows"]
        if not rows:
            pytest.skip("no receipts")
        # find one with je_id and invoice_ids ideally
        target = next((r for r in rows if r.get("je_id")), rows[0])
        r = admin.get(f"{API}/billing/receipts/{target['id']}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == target["id"]
        if target.get("je_id"):
            assert "journal_entry" in d, "journal_entry missing"
            assert "lines" in d["journal_entry"], "journal_entry.lines missing"
        if target.get("invoice_ids"):
            assert "invoices" in d
            assert isinstance(d["invoices"], list)

    def test_rbac_retention_sales_denied(self, sales):
        r = sales.get(f"{API}/billing/reports/retention-receivable/export", timeout=30)
        assert r.status_code == 403
