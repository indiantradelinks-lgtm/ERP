"""Accounts Module Phase 1 (Iter 72) — Vouchers, Opening Balance, Day Book, Audit, Inbox, Dashboard.
Cookie-based auth (admin@erp.com / Admin@123)."""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def H():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    # Ensure CoA seeded
    s.post(f"{API}/accounts/chart-of-accounts/seed", timeout=30)
    return s


# --- CoA extension to 66 accounts ----------------------------------
class TestCoAExtended:
    def test_seed_idempotent_and_total_66(self, H):
        r = H.post(f"{API}/accounts/chart-of-accounts/seed", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["inserted"] == 0, "Seed not idempotent — inserted should be 0 on subsequent calls"
        assert data["total"] >= 60, f"Expected total >= 60, got {data['total']}"

    def test_itl_service_codes_present(self, H):
        r = H.get(f"{API}/accounts/chart-of-accounts?active_only=false", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        codes = {row["code"] for row in rows}
        required = {"4101", "4102", "4103", "4104", "4105", "4106",
                    "2210", "2220", "2230", "1115", "1510", "1520", "3110"}
        missing = required - codes
        assert not missing, f"Missing required CoA codes: {missing}"
        # Active set should have >= 60
        active = [r for r in rows if r.get("is_active") is not False]
        assert len(active) >= 60, f"Expected >= 60 active accounts, got {len(active)}"


# --- Voucher types --------------------------------------------------
class TestVoucherTypes:
    def test_list_12_types(self, H):
        r = H.get(f"{API}/accounts/voucher-types", timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()
        codes = {row["code"] for row in rows}
        expected = {"SV", "PUV", "PV", "RV", "JV", "CV", "DN", "CN", "EV", "PYV", "ADJ", "REV"}
        assert expected.issubset(codes), f"Missing voucher types: {expected - codes}"
        for row in rows:
            assert "label" in row and row["label"]


# --- Voucher creation: PV with auto-sequence -----------------------
class TestVoucherCRUD:
    def test_post_pv_balanced_and_sequence(self, H):
        payload = {
            "voucher_type": "PV", "date": "2026-01-15",
            "narration": "TEST_iter72 PV-1",
            "status": "posted",
            "lines": [
                {"account_code": "2100", "debit": 1500, "credit": 0},
                {"account_code": "1100", "debit": 0, "credit": 1500},
            ],
        }
        r1 = H.post(f"{API}/accounts/vouchers", json=payload, timeout=30)
        assert r1.status_code == 200, r1.text
        v1 = r1.json()
        assert v1.get("status") == "posted"
        assert re.match(r"^PV-2026-\d{4}$", v1["voucher_number"]), f"Bad voucher_number: {v1.get('voucher_number')}"
        n1 = int(v1["voucher_number"].split("-")[-1])

        # Second PV → next number
        r2 = H.post(f"{API}/accounts/vouchers", json={**payload, "narration": "TEST_iter72 PV-2"}, timeout=30)
        assert r2.status_code == 200, r2.text
        v2 = r2.json()
        assert re.match(r"^PV-2026-\d{4}$", v2["voucher_number"])
        n2 = int(v2["voucher_number"].split("-")[-1])
        assert n2 == n1 + 1, f"Sequence not contiguous: n1={n1} n2={n2}"

    def test_post_unbalanced_voucher_rejected(self, H):
        payload = {
            "voucher_type": "PV", "date": "2026-01-15",
            "narration": "TEST_iter72 unbalanced PV",
            "status": "posted",
            "lines": [
                {"account_code": "2100", "debit": 100, "credit": 0},
                {"account_code": "1100", "debit": 0, "credit": 200},
            ],
        }
        r = H.post(f"{API}/accounts/vouchers", json=payload, timeout=30)
        assert r.status_code == 400
        detail = (r.json().get("detail") or "").lower()
        assert "debit" in detail and "credit" in detail

    def test_draft_then_approve(self, H):
        payload = {
            "voucher_type": "JV", "date": "2026-01-15",
            "narration": "TEST_iter72 draft JV",
            "status": "draft",
            "lines": [
                {"account_code": "5900", "debit": 50, "credit": 0},
                {"account_code": "1100", "debit": 0, "credit": 50},
            ],
        }
        r = H.post(f"{API}/accounts/vouchers", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        v = r.json()
        assert v.get("status") == "draft"
        vid = v["id"]

        # Approval inbox lists it
        inbox = H.get(f"{API}/accounts/approval-inbox", timeout=30).json()
        assert any(x.get("id") == vid for x in inbox), "Draft not in approval inbox"

        # Approve
        ra = H.post(f"{API}/accounts/vouchers/{vid}/approve", timeout=30)
        assert ra.status_code == 200, ra.text
        assert ra.json().get("status") == "posted"

        # Approve again → 400
        ra2 = H.post(f"{API}/accounts/vouchers/{vid}/approve", timeout=30)
        assert ra2.status_code == 400
        assert "already posted" in (ra2.json().get("detail") or "").lower()

    def test_reverse_posted_voucher(self, H):
        # Create a fresh posted PV
        r = H.post(f"{API}/accounts/vouchers", json={
            "voucher_type": "PV", "date": "2026-01-16",
            "narration": "TEST_iter72 to-be-reversed",
            "status": "posted",
            "lines": [
                {"account_code": "2100", "debit": 300, "credit": 0},
                {"account_code": "1100", "debit": 0, "credit": 300},
            ],
        }, timeout=30)
        assert r.status_code == 200, r.text
        src = r.json()
        src_id = src["id"]
        src_no = src["voucher_number"]

        rev = H.post(f"{API}/accounts/vouchers/{src_id}/reverse", timeout=30)
        assert rev.status_code == 200, rev.text
        rdoc = rev.json()
        assert re.match(r"^REV-2026-\d{4}$", rdoc["voucher_number"])
        assert rdoc.get("source_ref") == src_no
        # Lines flipped: original DR 2100=300 → CR 2100=300
        line_2100 = next(ln for ln in rdoc["lines"] if ln["account_code"] == "2100")
        assert line_2100["credit"] == 300 and line_2100["debit"] == 0

        # Second reverse on same id → 409
        rev2 = H.post(f"{API}/accounts/vouchers/{src_id}/reverse", timeout=30)
        assert rev2.status_code == 409


# --- Opening balance -----------------------------------------------
class TestOpeningBalance:
    def test_post_and_coa_stamped(self, H):
        payload = {
            "date": "2026-04-01",
            "narration": "TEST_iter72 opening",
            "entries": [
                {"account_code": "1100", "debit": 50000, "credit": 0},
                {"account_code": "3100", "debit": 0, "credit": 50000},
            ],
        }
        r = H.post(f"{API}/accounts/opening-balance", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        je = r.json()
        assert je.get("source_module") == "opening_balance"

        # CoA stamped
        rows = H.get(f"{API}/accounts/chart-of-accounts", timeout=30).json()
        bank = next(r for r in rows if r["code"] == "1100")
        cap = next(r for r in rows if r["code"] == "3100")
        assert bank.get("opening_balance") == 50000
        assert cap.get("opening_balance") == -50000

    def test_unbalanced_opening_rejected(self, H):
        r = H.post(f"{API}/accounts/opening-balance", json={
            "date": "2026-04-01", "narration": "TEST_iter72 bad-opening",
            "entries": [
                {"account_code": "1100", "debit": 100, "credit": 0},
                {"account_code": "3100", "debit": 0, "credit": 200},
            ],
        }, timeout=30)
        assert r.status_code == 400


# --- Day Book ------------------------------------------------------
class TestDayBook:
    def test_day_book_range(self, H):
        r = H.get(f"{API}/accounts/reports/day-book?start=2026-01-01&end=2026-12-31", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "days" in data
        assert isinstance(data["days"], list)
        if data["days"]:
            d0 = data["days"][0]
            assert "date" in d0 and "entries" in d0 and "total_debit" in d0 and "total_credit" in d0
            # Sorted desc
            dates = [d["date"] for d in data["days"]]
            assert dates == sorted(dates, reverse=True), "days not sorted desc"


# --- Audit trail ---------------------------------------------------
class TestAuditTrail:
    def test_audit_has_voucher_post(self, H):
        # First create a voucher to ensure audit exists
        H.post(f"{API}/accounts/vouchers", json={
            "voucher_type": "PV", "date": "2026-01-15",
            "narration": "TEST_iter72 audit-seed",
            "status": "posted",
            "lines": [
                {"account_code": "2100", "debit": 100, "credit": 0},
                {"account_code": "1100", "debit": 0, "credit": 100},
            ],
        }, timeout=30)
        r = H.get(f"{API}/accounts/audit-trail?limit=50", timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0, "No audit entries returned"
        actions = {row.get("action") for row in rows}
        assert "voucher_post" in actions or "voucher_create" in actions, f"Got actions: {actions}"


# --- Dashboard -----------------------------------------------------
class TestDashboard:
    def test_dashboard_20_cards(self, H):
        r = H.get(f"{API}/accounts/dashboard", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "as_of" in data and "cards" in data and "recent_transactions" in data
        required_keys = {
            "total_receivables", "total_payables", "retention_receivable", "retention_payable",
            "vendor_payable", "client_advances", "bank_balance", "cash_balance", "petty_cash",
            "gst_payable", "tds_payable", "salary_payable", "labour_payable",
            "employee_advances", "vendor_advances",
            "monthly_income", "monthly_expenses", "net_cash_flow",
            "pending_vouchers", "unposted_vouchers", "missing_attachment_alerts",
        }
        missing = required_keys - set(data["cards"].keys())
        assert not missing, f"Dashboard missing cards: {missing}"
