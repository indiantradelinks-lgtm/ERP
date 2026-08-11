"""Iter 168 — Payment Processing Center (Accounts).

Tests the centralized payment queue flow:
  queue → verify (TDS + advance) → bank-file (xlsx) → mark-paid → JE post + RBAC.
"""
import os
import pytest
import requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(session, email, pwd):
    r = session.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd})
    return r


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = _login(s, "admin@erp.com", "Admin@123")
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def accounts():
    s = requests.Session()
    r = _login(s, "accounts@erp.com", "Accounts@123")
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def safety():
    s = requests.Session()
    r = _login(s, "safety@erp.com", "Safety@123")
    assert r.status_code == 200, r.text
    return s


# ---------------- RBAC ----------------
def test_rbac_safety_forbidden(safety):
    r = safety.get(f"{BASE}/api/accounts/payment-queue")
    assert r.status_code == 403, f"safety_officer should be 403, got {r.status_code}"


def test_rbac_accounts_ok(accounts):
    r = accounts.get(f"{BASE}/api/accounts/payment-queue")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------------- Queue ----------------
@pytest.fixture(scope="module")
def queue_rows(admin):
    r = admin.get(f"{BASE}/api/accounts/payment-queue")
    assert r.status_code == 200
    rows = r.json()
    return rows


def test_queue_returns_payment_rows(queue_rows):
    assert isinstance(queue_rows, list)
    if queue_rows:
        r0 = queue_rows[0]
        assert r0.get("is_payment") is True
        assert "verification" in r0
        assert "pay_stage" in r0


# ---------------- Pick a pending row ----------------
@pytest.fixture(scope="module")
def pending_row(queue_rows):
    pending = [r for r in queue_rows if r.get("pay_stage") == "pending_verification"]
    if not pending:
        pytest.skip("No pending_verification row available to test verify flow")
    return pending[0]


# ---------------- Verify validation ----------------
def test_verify_missing_fields_400(admin, pending_row):
    rid = pending_row["id"]
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify",
                   json={"decision": "verified"})
    assert r.status_code == 400


def test_verify_negative_net_400(admin, pending_row):
    rid = pending_row["id"]
    body = {
        "decision": "verified", "vendor_name": "TEST Vendor", "vendor_account_no": "1234567890",
        "ifsc": "HDFC0000123", "invoice_no": "INV-TEST-1", "verified_amount": 100,
        "tds_applicable": True, "tds_amount": 200,
    }
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify", json=body)
    assert r.status_code == 400


def test_verify_tds_applicable_zero_400(admin, pending_row):
    rid = pending_row["id"]
    body = {
        "decision": "verified", "vendor_name": "TEST Vendor", "vendor_account_no": "1234567890",
        "ifsc": "HDFC0000123", "invoice_no": "INV-TEST-1", "verified_amount": 1000,
        "tds_applicable": True, "tds_amount": 0,
    }
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify", json=body)
    assert r.status_code == 400


def test_verify_gst_required_400(admin, pending_row):
    rid = pending_row["id"]
    body = {
        "decision": "verified", "vendor_name": "TEST Vendor", "vendor_account_no": "1234567890",
        "ifsc": "HDFC0000123", "invoice_no": "INV-TEST-1", "verified_amount": 1000,
        "gst_applicable": True, "gstin": "",
    }
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify", json=body)
    assert r.status_code == 400


# ---------------- Happy path verify ----------------
def test_verify_success_with_tds_and_advance(admin, pending_row):
    rid = pending_row["id"]
    body = {
        "decision": "verified", "vendor_name": "TEST Vendor Iter168",
        "vendor_account_no": "9876543210", "ifsc": "HDFC0000999",
        "bank_name": "HDFC Bank",
        "invoice_no": "INV-ITER168-01", "invoice_date": "2026-01-15",
        "verified_amount": 10000, "tds_applicable": True, "tds_pct": 10,
        "tds_amount": 1000, "advance_adjusted": 500,
        "expense_account_code": "5150",
    }
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stage"] == "verified"
    assert d["net_payable"] == 8500
    assert d["tds_amount"] == 1000
    assert d["advance_adjusted"] == 500


# ---------------- Bank file ----------------
def test_bank_file_reject_unverified(admin):
    r = admin.post(f"{BASE}/api/accounts/payment-queue/bank-file",
                   json={"request_ids": ["nonexistent-xyz-123"]})
    assert r.status_code == 400


def test_bank_file_create_and_download(admin, pending_row):
    rid = pending_row["id"]
    r = admin.post(f"{BASE}/api/accounts/payment-queue/bank-file",
                   json={"request_ids": [rid], "payment_mode": "NEFT"})
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.headers.get("X-File-No", "").startswith("BPF")
    assert len(r.content) > 100  # xlsx bytes

    # list bank files
    lst = admin.get(f"{BASE}/api/accounts/payment-queue/bank-files")
    assert lst.status_code == 200
    files = lst.json()
    assert any(f["file_no"] == r.headers["X-File-No"] for f in files)

    # download re-fetch
    fid = next(f["id"] for f in files if f["file_no"] == r.headers["X-File-No"])
    dl = admin.get(f"{BASE}/api/accounts/payment-queue/bank-files/{fid}/download")
    assert dl.status_code == 200
    assert len(dl.content) > 100


# ---------------- Re-verify after in_bank_file ----------------
def test_reverify_after_bank_file_400(admin, pending_row):
    rid = pending_row["id"]
    body = {
        "decision": "verified", "vendor_name": "X", "vendor_account_no": "1",
        "ifsc": "H", "invoice_no": "I", "verified_amount": 100,
    }
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify", json=body)
    assert r.status_code == 400


# ---------------- Mark paid → JE ----------------
def test_mark_paid_posts_balanced_je(admin, pending_row):
    rid = pending_row["id"]
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/mark-paid",
                   json={"utr_no": "UTRITER168TEST01", "paid_date": "2026-01-16"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stage"] == "paid"
    assert d["utr_no"] == "UTRITER168TEST01"
    voucher = d.get("voucher_number")
    assert voucher

    # Fetch JE and verify balanced with expected legs
    je_list = admin.get(f"{BASE}/api/accounts/journal-entries")
    assert je_list.status_code == 200
    entries = je_list.json()
    # entries may be list or dict; normalize
    if isinstance(entries, dict):
        entries = entries.get("items") or entries.get("data") or []
    match = [e for e in entries if e.get("voucher_number") == voucher]
    assert match, f"JE {voucher} not found"
    je = match[0]
    assert je.get("voucher_type") == "PYV"
    lines = je.get("lines") or []
    total_dr = sum(float(l.get("debit") or 0) for l in lines)
    total_cr = sum(float(l.get("credit") or 0) for l in lines)
    assert round(total_dr, 2) == round(total_cr, 2), f"unbalanced JE {total_dr} vs {total_cr}"
    # check line accounts
    codes = {l.get("account_code") for l in lines}
    assert "5150" in codes  # expense DR
    assert "1100" in codes  # bank CR
    # verified_amount=10000, tds=1000 → 2400 CR should be present
    assert "2400" in codes
    assert "1510" in codes


def test_reverify_after_paid_400(admin, pending_row):
    rid = pending_row["id"]
    body = {
        "decision": "verified", "vendor_name": "X", "vendor_account_no": "1",
        "ifsc": "H", "invoice_no": "I", "verified_amount": 100,
    }
    r = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify", json=body)
    assert r.status_code == 400
