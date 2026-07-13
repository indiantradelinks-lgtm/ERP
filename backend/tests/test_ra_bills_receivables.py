"""RA Bills + Receivables — Modules C + D.

Walks the full revenue-side cycle:
  Measurement → approved_for_billing → bulk-create RA bill → totals math
  → submit → approve → invoice → receive payment → bill flips to paid
  → receivables ageing & overdue endpoints reflect zero outstanding
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TS = str(int(time.time()))


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def measurement(admin):
    """Create a measurement, walk it to approved_for_billing."""
    payload = {
        "date": "2026-04-01", "project_code": f"PRJ-RA-{TS}", "site_name": "Tank Bund",
        "service_type": "scaffolding",
        "items": [
            {"service": "scaffolding", "activity": "erected", "executed_qty": 200, "certified_qty": 200, "unit": "m²", "rate": 100},
            {"service": "scaffolding", "activity": "dismantled", "executed_qty": 100, "certified_qty": 100, "unit": "m²", "rate": 50},
        ],
        "submit": True,
    }
    m = admin.post(f"{API}/measurements", json=payload, timeout=30).json()
    admin.post(f"{API}/measurements/{m['id']}/certify",
               json={"signatory_name": "Mr. Joshi", "signatory_designation": "Plant Engineer"}, timeout=30)
    admin.post(f"{API}/measurements/{m['id']}/approve-for-billing", timeout=30)
    return m


class TestRABills:
    def test_create_from_measurement(self, admin, measurement):
        payload = {
            "measurement_ids": [measurement["id"]],
            "client_id": f"CL-RA-{TS}", "client_name": "Vega Refinery",
            "po_number": f"PO-RA-{TS}",
            "gst_pct": 18, "retention_pct": 5, "tds_pct": 2,
            "advance_recovery": 1000,
        }
        r = admin.post(f"{API}/ra-bills/from-measurements", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        # subtotal = 200*100 + 100*50 = 25000
        # gst = 25000 * 0.18 = 4500
        # gross = 29500
        # retention = 25000 * 0.05 = 1250
        # tds = 25000 * 0.02 = 500
        # other = 0; advance = 1000
        # net = 29500 - 1250 - 500 - 0 - 1000 = 26750
        assert b["subtotal"] == 25000
        assert b["gst_amount"] == 4500
        assert b["gross_value"] == 29500
        assert b["retention_amount"] == 1250
        assert b["tds_amount"] == 500
        assert b["advance_recovery"] == 1000
        assert b["net_payable"] == 26750
        assert b["bill_number"].startswith("RA-")
        assert b["status"] == "draft"
        assert len(b["items"]) == 2
        pytest.bill_id = b["id"]
        pytest.bill_no = b["bill_number"]

    def test_submit_approve(self, admin, measurement):
        r1 = admin.post(f"{API}/ra-bills/{pytest.bill_id}/submit", timeout=30)
        assert r1.status_code == 200 and r1.json()["status"] == "submitted"
        r2 = admin.post(f"{API}/ra-bills/{pytest.bill_id}/approve", timeout=30)
        assert r2.status_code == 200 and r2.json()["status"] == "approved"
        # Linked measurement flipped to `billed`
        m = admin.get(f"{API}/measurements/{measurement['id']}", timeout=30).json()
        assert m["status"] == "billed"
        assert m["ra_bill_id"] == pytest.bill_id

    def test_issue_invoice(self, admin):
        r = admin.post(f"{API}/ra-bills/{pytest.bill_id}/issue-invoice",
                       json={"due_days": 30, "issue_date": "2026-04-05"}, timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "invoiced"
        assert b["due_date"] == "2026-05-05"
        assert b["invoice_no"] == b["bill_number"]

    def test_invalid_dn_without_link(self, admin):
        r = admin.post(f"{API}/ra-bills",
                       json={"bill_type": "debit_note", "items": [{"description": "x", "quantity": 1, "rate": 1}]},
                       timeout=30)
        assert r.status_code == 400 and "against_ra_bill_id" in r.text

    def test_validation_empty_items(self, admin):
        r = admin.post(f"{API}/ra-bills",
                       json={"bill_type": "running", "items": []}, timeout=30)
        assert r.status_code == 400


class TestPaymentsAndReceivables:
    def test_payment_full_settles_bill(self, admin):
        # Pay the FULL net_payable (26750)
        r = admin.post(f"{API}/payments-in", json={
            "client_id": f"CL-RA-{TS}", "client_name": "Vega Refinery",
            "amount": 26750, "mode": "bank_transfer", "reference_no": f"NEFT-{TS}",
            "allocations": [{"ra_bill_id": pytest.bill_id, "amount": 26750}],
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["payment_no"].startswith("PAY-")
        assert body["unallocated"] == 0
        # Bill should now be paid
        b = admin.get(f"{API}/ra-bills/{pytest.bill_id}", timeout=30).json()
        assert b["status"] == "paid"
        assert b["paid_amount"] == 26750
        assert b["balance_due"] == 0

    def test_payment_partial_keeps_invoiced(self, admin):
        """Make a NEW bill, pay only half — bill should stay 'invoiced'."""
        # Reuse: create another billed measurement quickly
        m = admin.post(f"{API}/measurements", json={
            "project_code": f"PRJ-PART-{TS}",
            "items": [{"service": "painting", "activity": "painted", "executed_qty": 100, "certified_qty": 100, "unit": "m²", "rate": 50}],
            "submit": True,
        }, timeout=30).json()
        admin.post(f"{API}/measurements/{m['id']}/certify", json={"signatory_name": "Mr. X"}, timeout=30)
        admin.post(f"{API}/measurements/{m['id']}/approve-for-billing", timeout=30)
        b = admin.post(f"{API}/ra-bills/from-measurements", json={
            "measurement_ids": [m["id"]], "client_id": f"CL-P-{TS}", "client_name": "Acme Co",
            "gst_pct": 18, "retention_pct": 0, "tds_pct": 0,
        }, timeout=30).json()
        # net = 5000 + 900 GST = 5900
        assert b["net_payable"] == 5900
        admin.post(f"{API}/ra-bills/{b['id']}/submit", timeout=30)
        admin.post(f"{API}/ra-bills/{b['id']}/approve", timeout=30)
        admin.post(f"{API}/ra-bills/{b['id']}/issue-invoice", json={"due_days": 5, "issue_date": "2026-01-01"}, timeout=30)
        # Pay half
        admin.post(f"{API}/payments-in", json={
            "client_id": f"CL-P-{TS}", "amount": 2950,
            "allocations": [{"ra_bill_id": b["id"], "amount": 2950}],
        }, timeout=30)
        b2 = admin.get(f"{API}/ra-bills/{b['id']}", timeout=30).json()
        assert b2["status"] == "invoiced"
        assert b2["balance_due"] == 2950
        pytest.partial_bill_id = b["id"]
        pytest.partial_client = f"CL-P-{TS}"

    def test_ageing(self, admin):
        """Our partial bill issued 2026-01-01 with 5 days due → way overdue."""
        r = admin.get(f"{API}/receivables/ageing", params={"client_id": pytest.partial_client}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        # Must show 2950 outstanding
        assert body["total_outstanding"] == 2950
        # Most past-due bucket should hold it (>180d from 2026-01-06 due)
        all_amts = [b["amount"] for b in body["buckets"]] + [body["not_due"]["amount"]]
        assert any(a > 0 for a in all_amts)

    def test_client_ledger(self, admin):
        r = admin.get(f"{API}/receivables/client-ledger", params={"client_id": pytest.partial_client}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["invoiced"] == 5900
        assert body["summary"]["received"] == 2950
        assert body["summary"]["balance"] == 2950

    def test_overdue(self, admin):
        r = admin.get(f"{API}/receivables/overdue", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1
        ours = [r for r in body["rows"] if r["client_name"] == "Acme Co"]
        assert ours and ours[0]["balance"] == 2950
        assert ours[0]["severity"] == "high"   # ≥ 91 days

    def test_dashboard(self, admin):
        r = admin.get(f"{API}/receivables/dashboard", timeout=30)
        assert r.status_code == 200
        kpis = r.json()["kpis"]
        assert kpis["overdue_total"] >= 2950
        assert kpis["invoiced_lifetime"] >= 29500 + 5900

    def test_cashflow(self, admin):
        r = admin.get(f"{API}/receivables/cashflow", params={"days": 30}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["horizon_days"] == 30
        assert "weekly_inflow" in body


class TestCancelAndDelete:
    def test_cancel_rolls_back_measurement(self, admin):
        # Re-walk a fresh measurement → bill → cancel; the measurement should
        # revert to approved_for_billing.
        m = admin.post(f"{API}/measurements", json={
            "project_code": f"PRJ-CN-{TS}",
            "items": [{"service": "insulation", "activity": "insulated", "executed_qty": 10, "certified_qty": 10, "unit": "m²", "rate": 100}],
            "submit": True,
        }, timeout=30).json()
        admin.post(f"{API}/measurements/{m['id']}/certify", json={"signatory_name": "Mr. Q"}, timeout=30)
        admin.post(f"{API}/measurements/{m['id']}/approve-for-billing", timeout=30)
        b = admin.post(f"{API}/ra-bills/from-measurements", json={"measurement_ids": [m["id"]]}, timeout=30).json()
        admin.post(f"{API}/ra-bills/{b['id']}/submit", timeout=30)
        admin.post(f"{API}/ra-bills/{b['id']}/approve", timeout=30)
        # Now cancel
        r = admin.post(f"{API}/ra-bills/{b['id']}/cancel", json={"reason": "duplicate"}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        m2 = admin.get(f"{API}/measurements/{m['id']}", timeout=30).json()
        assert m2["status"] == "approved_for_billing"
        # Delete cancelled bill
        d = admin.delete(f"{API}/ra-bills/{b['id']}", timeout=30)
        assert d.status_code == 200
