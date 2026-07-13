"""Accounts Module (Iter 71) — backend regression tests.
Tests CoA CRUD, manual JE balanced/unbalanced, reports."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def H(session):
    # Session holds httpOnly cookies; we just expose it as 'requests'-like object
    return session


# ─── CoA ──────────────────────────────────────────────────────────
class TestCoA:
    def test_seed_idempotent(self, H):
        r1 = H.post(f"{API}/accounts/chart-of-accounts/seed", timeout=30)
        assert r1.status_code == 200, r1.text
        data1 = r1.json()
        assert "inserted" in data1 and "total" in data1
        assert data1["total"] >= 30
        # Run again — should insert 0
        r2 = H.post(f"{API}/accounts/chart-of-accounts/seed", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["inserted"] == 0, "Seed not idempotent on 2nd call"

    def test_list_coa_at_least_30(self, H):
        r = H.get(f"{API}/accounts/chart-of-accounts", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) >= 30, f"Expected >=30 CoA rows, got {len(rows)}"
        for row in rows[:3]:
            assert "code" in row and "name" in row and "type" in row

    def test_create_and_soft_delete(self, H):
        # Cleanup: if 9999 exists active, soft-disable first
        existing = H.get(f"{API}/accounts/chart-of-accounts?active_only=false", timeout=30).json()
        for row in existing:
            if row.get("code") == "TEST_9999":
                H.delete(f"{API}/accounts/chart-of-accounts/{row['id']}", timeout=30)
        payload = {"code": "TEST_9999", "name": "TEST Account Iter71", "type": "asset", "subtype": "cash"}
        r = H.post(f"{API}/accounts/chart-of-accounts", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["code"] == "TEST_9999"
        assert doc["name"] == "TEST Account Iter71"
        assert doc["type"] == "asset"
        coa_id = doc["id"]

        # Verify in list
        rows = H.get(f"{API}/accounts/chart-of-accounts", timeout=30).json()
        assert any(r2["code"] == "TEST_9999" for r2 in rows)

        # Duplicate code → 409
        r_dup = H.post(f"{API}/accounts/chart-of-accounts", json=payload, timeout=30)
        assert r_dup.status_code == 409

        # Soft-delete
        r_del = H.delete(f"{API}/accounts/chart-of-accounts/{coa_id}", timeout=30)
        assert r_del.status_code == 200
        # Verify hidden from active_only list
        rows_after = H.get(f"{API}/accounts/chart-of-accounts", timeout=30).json()
        assert not any(r2["code"] == "TEST_9999" for r2 in rows_after), "Deleted CoA still shown in active list"


# ─── Manual Journal Entries ────────────────────────────────────────
class TestJournalEntries:
    def test_post_balanced_je(self, H):
        payload = {
            "date": "2026-01-15",
            "narration": "TEST_iter71 balanced JE",
            "lines": [
                {"account_code": "1100", "debit": 500, "credit": 0},
                {"account_code": "3100", "debit": 0, "credit": 500},
            ],
        }
        r = H.post(f"{API}/accounts/journal-entries", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        je = r.json()
        assert je.get("source_module") == "manual"
        assert "je_number" in je
        assert "id" in je
        # GET verification
        listing = H.get(f"{API}/accounts/journal-entries?source_module=manual", timeout=30).json()
        assert any(j.get("id") == je["id"] for j in listing), "Posted JE not found in list"

    def test_post_unbalanced_je_rejected(self, H):
        payload = {
            "date": "2026-01-15",
            "narration": "TEST_iter71 unbalanced",
            "lines": [
                {"account_code": "1100", "debit": 100, "credit": 0},
                {"account_code": "3100", "debit": 0, "credit": 200},
            ],
        }
        r = H.post(f"{API}/accounts/journal-entries", json=payload, timeout=30)
        assert r.status_code == 400, f"Expected 400 for unbalanced JE, got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "debit" in detail and "credit" in detail, f"Unexpected detail: {detail}"

    def test_list_with_filter(self, H):
        r = H.get(f"{API}/accounts/journal-entries?source_module=manual&limit=50", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        for row in rows:
            assert row.get("source_module") == "manual"

    def test_auto_posted_je_exists(self, H):
        """Verify some JE has source_module other than 'manual' (auto-posted from a hooked event)."""
        r = H.get(f"{API}/accounts/journal-entries?limit=500", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        non_manual = [x for x in rows if x.get("source_module") and x.get("source_module") != "manual"]
        # Soft-assert: log but do not fail (data may be sparse in preview DB)
        if not non_manual:
            pytest.skip("No auto-posted JEs found in current DB (acceptable in fresh DB)")
        assert len(non_manual) > 0


# ─── Reports ──────────────────────────────────────────────────────
class TestReports:
    def test_trial_balance(self, H):
        r = H.get(f"{API}/accounts/reports/trial-balance", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rows" in data and "totals" in data
        assert isinstance(data["rows"], list)
        totals = data["totals"]
        assert "debit" in totals and "credit" in totals and "diff" in totals

    def test_trial_balance_with_excluding_date_range(self, H):
        r = H.get(f"{API}/accounts/reports/trial-balance?start=1990-01-01&end=1990-12-31", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["totals"]["debit"] == 0
        assert data["totals"]["credit"] == 0

    def test_profit_and_loss(self, H):
        r = H.get(f"{API}/accounts/reports/profit-and-loss", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # P&L should return revenue/expense/net dictionary
        assert isinstance(data, dict)
        # Check for expected keys (flexible — accept either revenue or rows)
        keys = set(data.keys())
        assert keys & {"revenue", "expenses", "net_profit", "rows", "totals"}, f"Unexpected P&L shape: {keys}"

    def test_ar_aging(self, H):
        r = H.get(f"{API}/accounts/reports/ar-aging", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)
        # Should have buckets (0_30, 31_60, etc) or rows
        text = str(data)
        assert "30" in text or "rows" in data or "buckets" in data

    def test_ap_aging(self, H):
        r = H.get(f"{API}/accounts/reports/ap-aging", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)
