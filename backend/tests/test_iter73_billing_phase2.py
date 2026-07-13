"""Iter 73 — Phase 2 Client Billing & Receivables (POST/REPORT verification).

Walks the full billing cycle for the new /api/billing/* surface:
  - invoice-types/service-types catalogs
  - Invoice creation (RA, scaffolding) with computed totals
  - Invoice approve → JE auto-posted (DR 1200 / CR 4101 / CR 2300)
  - Re-approve guarded; WO over-billing guarded; TDS>gross guarded
  - Service-type → income-code mapping (painting=4102, manpower=4105)
  - Receipt with TDS+Retention splits → JE (DR 1100 + 1220 + 1210 / CR 1200)
  - Excess receipt requires excess_reason
  - Receivable reports: client-outstanding, gst-sales-register, tds-receivable,
    retention-receivable, collection, overdue, invoice-register, client-ledger
"""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TS = str(int(time.time()))

CLIENT_A = f"TEST_Client_A_{TS}"
CLIENT_P = f"TEST_Client_Paint_{TS}"
CLIENT_M = f"TEST_Client_Manp_{TS}"
WO_A = f"WOT-{TS}"


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, r.text
    return s


# ─── Catalog endpoints ──────────────────────────────────────────────────
class TestCatalogs:
    def test_invoice_types(self, admin):
        r = admin.get(f"{API}/billing/invoice-types", timeout=30)
        assert r.status_code == 200, r.text
        codes = {row["code"] for row in r.json()}
        assert codes == {"TAX", "PROF", "RA", "FINAL", "MOB", "RETN", "EXTRA", "REIMB", "DN", "CN"}, codes

    def test_service_types(self, admin):
        r = admin.get(f"{API}/billing/service-types", timeout=30)
        assert r.status_code == 200, r.text
        st = r.json()
        assert set(st) == {"scaffolding", "painting", "roof_sheeting", "rope_access",
                           "manpower", "material_supply", "other"}


# ─── Invoice create / totals math / approval / JE ───────────────────────
class TestInvoiceFlow:
    def test_create_ra_invoice_totals(self, admin):
        payload = {
            "invoice_type": "RA", "invoice_date": "2026-06-01",
            "client_name": CLIENT_A,
            "project_code": "P-A-1", "work_order_no": WO_A, "contract_value": 500000,
            "service_type": "scaffolding",
            "lines": [{"description": "Scaffolding May", "quantity": 1, "unit": "Lot", "rate": 50000}],
            "gst_rate": 18, "is_intra_state": True,
            "tds_rate": 2, "retention_rate": 5, "due_days": 30,
        }
        r = admin.post(f"{API}/billing/invoices", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert re.match(r"^RA-2026-\d{4}$", inv["invoice_no"]), inv["invoice_no"]
        t = inv["totals"]
        assert t["taxable_value"] == 50000
        assert t["cgst"] == 4500 and t["sgst"] == 4500
        assert t["gross_value"] == 59000
        assert t["tds_expected"] == 1000
        assert t["retention_amount"] == 2500
        assert t["net_receivable"] == 55500
        assert inv["outstanding"] == 59000
        assert inv["status"] == "draft"
        pytest.inv_a_id = inv["id"]
        pytest.inv_a_no = inv["invoice_no"]

    def test_approve_creates_je(self, admin):
        r = admin.post(f"{API}/billing/invoices/{pytest.inv_a_id}/approve", timeout=30)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["status"] == "approved"
        assert re.match(r"^JE-2026-\d{4}$", inv["je_voucher_number"]), inv.get("je_voucher_number")
        pytest.je_a = inv["je_voucher_number"]

    def test_je_lines_correct(self, admin):
        # Locate the JE via list and assert DR 1200 / CR 4101 / CR 2300
        r = admin.get(f"{API}/accounts/journal-entries", params={"voucher_type": "SV", "limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        je = next((j for j in r.json() if j.get("voucher_number") == pytest.je_a), None)
        assert je, f"JE {pytest.je_a} not found in list"
        assert round(float(je["total_debit"]), 2) == 59000.0
        assert round(float(je["total_credit"]), 2) == 59000.0
        # Inspect lines
        lines = je.get("lines") or je.get("entries") or []
        dr = {l["account_code"]: float(l.get("debit") or 0) for l in lines if float(l.get("debit") or 0) > 0}
        cr = {l["account_code"]: float(l.get("credit") or 0) for l in lines if float(l.get("credit") or 0) > 0}
        assert dr.get("1200") == 59000.0, f"DR lines: {dr}"
        assert cr.get("4101") == 50000.0, f"CR lines: {cr}"
        assert cr.get("2300") == 9000.0, f"CR lines: {cr}"

    def test_reapprove_blocked(self, admin):
        r = admin.post(f"{API}/billing/invoices/{pytest.inv_a_id}/approve", timeout=30)
        assert r.status_code == 400
        assert "Cannot approve invoice in status approved" in r.text

    def test_wo_overbilling_blocked(self, admin):
        # First invoice was 50k; contract 500k. Try 500k → cumulative 550k > 500k.
        payload = {
            "invoice_type": "RA", "invoice_date": "2026-06-02",
            "client_name": CLIENT_A, "project_code": "P-A-1",
            "work_order_no": WO_A, "contract_value": 500000,
            "service_type": "scaffolding",
            "lines": [{"description": "Over bill", "quantity": 1, "rate": 500000}],
            "gst_rate": 18, "tds_rate": 0, "retention_rate": 0, "due_days": 30,
        }
        r = admin.post(f"{API}/billing/invoices", json=payload, timeout=30)
        assert r.status_code == 400, r.text
        assert "Billing exceeds work-order value" in r.text

    def test_tds_exceeds_invoice(self, admin):
        payload = {
            "invoice_type": "TAX", "invoice_date": "2026-06-03",
            "client_name": f"TEST_TDS_X_{TS}", "service_type": "other",
            "lines": [{"description": "X", "quantity": 1, "rate": 1000}],
            "gst_rate": 18, "tds_rate": 200, "retention_rate": 0, "due_days": 30,
        }
        r = admin.post(f"{API}/billing/invoices", json=payload, timeout=30)
        assert r.status_code == 400, r.text
        assert "TDS expected cannot exceed invoice value" in r.text


# ─── Service-type → income code mapping ─────────────────────────────────
class TestServiceMapping:
    def _create_and_approve(self, admin, client, service):
        payload = {
            "invoice_type": "TAX", "invoice_date": "2026-06-05",
            "client_name": client, "service_type": service,
            "lines": [{"description": f"{service} svc", "quantity": 1, "rate": 10000}],
            "gst_rate": 18, "tds_rate": 0, "retention_rate": 0, "due_days": 30,
        }
        inv = admin.post(f"{API}/billing/invoices", json=payload, timeout=30).json()
        appr = admin.post(f"{API}/billing/invoices/{inv['id']}/approve", timeout=30).json()
        return appr["je_voucher_number"]

    def test_painting_maps_4102(self, admin):
        vn = self._create_and_approve(admin, CLIENT_P, "painting")
        r = admin.get(f"{API}/accounts/journal-entries", params={"voucher_type": "SV", "limit": 50}, timeout=30)
        je = next((j for j in r.json() if j.get("voucher_number") == vn), None)
        assert je is not None
        cr = {l["account_code"]: float(l.get("credit") or 0) for l in (je.get("lines") or []) if float(l.get("credit") or 0) > 0}
        assert cr.get("4102") == 10000.0, f"painting did not credit 4102; got {cr}"

    def test_manpower_maps_4105(self, admin):
        vn = self._create_and_approve(admin, CLIENT_M, "manpower")
        r = admin.get(f"{API}/accounts/journal-entries", params={"voucher_type": "SV", "limit": 50}, timeout=30)
        je = next((j for j in r.json() if j.get("voucher_number") == vn), None)
        assert je is not None
        cr = {l["account_code"]: float(l.get("credit") or 0) for l in (je.get("lines") or []) if float(l.get("credit") or 0) > 0}
        assert cr.get("4105") == 10000.0, f"manpower did not credit 4105; got {cr}"


# ─── Receipt flow ───────────────────────────────────────────────────────
class TestReceiptFlow:
    def test_receipt_full_settlement(self, admin):
        payload = {
            "receipt_date": "2026-06-10", "client_name": CLIENT_A,
            "invoice_ids": [pytest.inv_a_id],
            "mode": "NEFT", "txn_reference": f"UTR-{TS}",
            "amount": 55500, "tds_deducted": 1000, "retention_deducted": 2500,
        }
        r = admin.post(f"{API}/billing/receipts", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        rcpt = r.json()
        assert rcpt["total_adjusted"] == 59000
        assert rcpt["status"] == "posted"
        assert rcpt.get("je_voucher_number"), "Receipt JE not created"
        pytest.rcpt_a_id = rcpt["id"]
        pytest.rcpt_a_je = rcpt["je_voucher_number"]
        # Invoice paid
        inv = admin.get(f"{API}/billing/invoices/{pytest.inv_a_id}", timeout=30).json()
        assert inv["status"] == "paid"
        assert inv["outstanding"] == 0
        assert inv["paid_amount"] == 59000

    def test_receipt_je_lines(self, admin):
        r = admin.get(f"{API}/accounts/journal-entries", params={"voucher_type": "RV", "limit": 50}, timeout=30)
        je = next((j for j in r.json() if j.get("voucher_number") == pytest.rcpt_a_je), None)
        assert je is not None, f"Receipt JE {pytest.rcpt_a_je} not found"
        assert round(float(je["total_debit"]), 2) == 59000.0
        assert round(float(je["total_credit"]), 2) == 59000.0
        dr = {l["account_code"]: float(l.get("debit") or 0) for l in (je.get("lines") or []) if float(l.get("debit") or 0) > 0}
        cr = {l["account_code"]: float(l.get("credit") or 0) for l in (je.get("lines") or []) if float(l.get("credit") or 0) > 0}
        assert dr.get("1100") == 55500.0, f"DR 1100 wrong: {dr}"
        assert dr.get("1220") == 1000.0, f"DR 1220 wrong: {dr}"
        assert dr.get("1210") == 2500.0, f"DR 1210 wrong: {dr}"
        assert cr.get("1200") == 59000.0, f"CR 1200 wrong: {cr}"

    def test_excess_receipt_requires_reason(self, admin):
        # Create one fresh invoice to receive against
        payload_inv = {
            "invoice_type": "TAX", "invoice_date": "2026-06-15",
            "client_name": f"TEST_Excess_{TS}", "service_type": "other",
            "lines": [{"description": "x", "quantity": 1, "rate": 50000}],
            "gst_rate": 18, "tds_rate": 0, "retention_rate": 0, "due_days": 30,
        }
        inv = admin.post(f"{API}/billing/invoices", json=payload_inv, timeout=30).json()
        admin.post(f"{API}/billing/invoices/{inv['id']}/approve", timeout=30)
        # Outstanding 59000. Try 70000 with no reason
        r = admin.post(f"{API}/billing/receipts", json={
            "receipt_date": "2026-06-16", "client_name": f"TEST_Excess_{TS}",
            "invoice_ids": [inv["id"]], "mode": "NEFT",
            "amount": 70000, "tds_deducted": 0, "retention_deducted": 0,
        }, timeout=30)
        assert r.status_code == 400, r.text
        assert "Excess receipt" in r.text and "excess_reason" in r.text

        r2 = admin.post(f"{API}/billing/receipts", json={
            "receipt_date": "2026-06-16", "client_name": f"TEST_Excess_{TS}",
            "invoice_ids": [inv["id"]], "mode": "NEFT",
            "amount": 70000, "excess_reason": "Advance for next bill",
        }, timeout=30)
        assert r2.status_code == 200, r2.text


# ─── Reports ────────────────────────────────────────────────────────────
class TestReports:
    def test_client_outstanding(self, admin):
        r = admin.get(f"{API}/billing/reports/client-outstanding", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body["buckets"].keys()) == {"0-30", "31-60", "61-90", "90+"}
        assert "total_outstanding" in body
        assert "clients" in body

    def test_gst_sales_register(self, admin):
        r = admin.get(f"{API}/billing/reports/gst-sales-register",
                      params={"start": "2026-01-01", "end": "2026-12-31"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rows" in body
        assert set(body["totals"].keys()) >= {"taxable", "cgst", "sgst", "igst", "gross"}
        # Sum-of-rows == totals
        sum_gross = round(sum(float(row.get("gross_value") or 0) for row in body["rows"]), 2)
        assert sum_gross == body["totals"]["gross"]

    def test_tds_receivable(self, admin):
        r = admin.get(f"{API}/billing/reports/tds-receivable", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "clients" in body and "total_tds" in body
        # Our receipt deducted 1000 TDS
        assert body["total_tds"] >= 1000

    def test_retention_receivable(self, admin):
        r = admin.get(f"{API}/billing/reports/retention-receivable", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "clients" in body and "total_retention" in body
        assert body["total_retention"] >= 2500

    def test_collection(self, admin):
        r = admin.get(f"{API}/billing/reports/collection",
                      params={"start": "2026-06-01", "end": "2026-06-30"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rows" in body
        t = body["totals"]
        assert set(t.keys()) >= {"total_adjusted", "amount_received", "tds_deducted", "retention_deducted"}

    def test_overdue(self, admin):
        r = admin.get(f"{API}/billing/reports/overdue", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rows" in body
        for row in body["rows"]:
            assert "overdue_days" in row
            assert float(row.get("outstanding") or 0) > 0

    def test_invoice_register(self, admin):
        r = admin.get(f"{API}/billing/reports/invoice-register", timeout=30)
        assert r.status_code == 200, r.text
        assert "rows" in r.json() and "totals" in r.json()
        # Filtered
        r2 = admin.get(f"{API}/billing/reports/invoice-register",
                       params={"invoice_type": "RA"}, timeout=30)
        assert r2.status_code == 200
        for row in r2.json()["rows"]:
            assert row["invoice_type"] == "RA"

    def test_client_ledger(self, admin):
        r = admin.get(f"{API}/billing/reports/client-ledger",
                      params={"client_name": CLIENT_A}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "events" in body and "closing_balance" in body
        assert isinstance(body["closing_balance"], (int, float))
        # Events must be date-sorted ascending
        dates = [e["date"] for e in body["events"]]
        assert dates == sorted(dates)
        # Client A had invoice 59000 and receipt 59000 → closing should be ~0
        assert abs(body["closing_balance"]) < 0.01
