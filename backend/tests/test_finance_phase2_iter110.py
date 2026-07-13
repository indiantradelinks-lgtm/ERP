"""Iter 110 — Finance Phase 2: CoA policy + DN/CN + Voucher PDF.

Backend: /api/finance/* + /api/accounts/* (CoA policy patch)
"""
import os
import time
import pytest
import requests

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return sess


# ───────────── CoA policy ─────────────
def test_coa_policy_migration(s):
    """Stamps default policy flags onto all CoA rows based on subtype."""
    r = s.post(f"{API_URL}/api/finance/coa/migrate-policy-defaults", timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["updated"] >= 0
    # Verify a known row got policy flags
    coa = s.get(f"{API_URL}/api/accounts/chart-of-accounts", timeout=10).json()
    ar = next((c for c in coa if c["code"] == "1200"), None)  # Accounts Receivable
    assert ar is not None
    assert ar.get("party_type") == "client"
    assert ar.get("is_sub_ledger") is True
    ap = next((c for c in coa if c["code"] == "2100"), None)
    assert ap is not None
    assert ap.get("party_type") == "vendor"
    assert ap.get("tds_applicable") is True


def test_coa_policy_patch(s):
    coa = s.get(f"{API_URL}/api/accounts/chart-of-accounts", timeout=10).json()
    bank = next(c for c in coa if c["code"] == "1100")
    r = s.patch(f"{API_URL}/api/finance/coa/{bank['id']}/policy",
                json={"gst_applicable": False, "cost_center_required": False}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["updated"]["gst_applicable"] is False


def test_coa_policy_invalid_party_type(s):
    coa = s.get(f"{API_URL}/api/accounts/chart-of-accounts", timeout=10).json()
    r = s.patch(f"{API_URL}/api/finance/coa/{coa[0]['id']}/policy",
                json={"party_type": "alien"}, timeout=10)
    assert r.status_code == 400


# ───────────── Debit / Credit Notes ─────────────
@pytest.fixture(scope="module")
def client_obj(s):
    rows = s.get(f"{API_URL}/api/clients", timeout=10).json() or []
    if isinstance(rows, dict):
        rows = rows.get("data", [])
    if not rows:
        pytest.skip("No clients in preview DB")
    return rows[0]


@pytest.fixture(scope="module")
def vendor_obj(s):
    rows = s.get(f"{API_URL}/api/vendors", timeout=10).json() or []
    if not rows:
        pytest.skip("No vendors in preview DB")
    return rows[0]


def test_list_reason_codes(s):
    r = s.get(f"{API_URL}/api/finance/notes/reason-codes", timeout=10)
    assert r.status_code == 200
    codes = {x["code"] for x in r.json()}
    for must in ("price_difference", "quality", "quantity", "gst_correction", "other"):
        assert must in codes


@pytest.fixture(scope="module")
def credit_note(s, client_obj):
    payload = {
        "kind": "credit_note",
        "against_type": "invoice",
        "against_number": "INV-TEST-001",
        "party_id": client_obj["id"],
        "party_type": "client",
        "project_id": None,
        "reason_code": "price_difference",
        "reason": "Negotiated rate revision after delivery",
        "taxable_value": 10000.0,
        "gst_percent": 18.0,
        "tds_percent": 0.0,
    }
    r = s.post(f"{API_URL}/api/finance/notes", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def test_credit_note_created(credit_note):
    assert credit_note["note_number"].startswith("CN-")
    assert credit_note["status"] == "draft"
    assert credit_note["taxable_value"] == 10000.0
    assert credit_note["gst_amount"] == 1800.0
    assert credit_note["total_amount"] == 11800.0


def test_credit_note_submit_and_approve_posts_je(s, credit_note):
    # submit
    r = s.post(f"{API_URL}/api/finance/notes/{credit_note['id']}/submit", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "pending_approval"
    # approve → posts JE
    r = s.post(f"{API_URL}/api/finance/notes/{credit_note['id']}/approve", timeout=15)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "approved"
    assert out["je_number"]
    # Verify JE in DB
    jes = s.get(f"{API_URL}/api/accounts/journal-entries", timeout=10).json() or []
    if isinstance(jes, dict):
        jes = jes.get("data", [])
    matching = [j for j in jes if j.get("je_number") == out["je_number"]]
    assert matching, f"JE {out['je_number']} not visible after approval"
    je = matching[0]
    assert je["total_debit"] == je["total_credit"] == 11800.0
    assert je["voucher_type"] == "CN"


def test_debit_note_against_vendor(s, vendor_obj):
    payload = {
        "kind": "debit_note",
        "against_type": "vendor_bill",
        "against_number": "VB-TEST-001",
        "party_id": vendor_obj["id"],
        "party_type": "vendor",
        "reason_code": "quality",
        "reason": "Material rejected at site",
        "taxable_value": 5000.0,
        "gst_percent": 18.0,
        "tds_percent": 2.0,
    }
    r = s.post(f"{API_URL}/api/finance/notes", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    dn = r.json()
    assert dn["note_number"].startswith("DN-")
    assert dn["tds_amount"] == 100.0
    assert dn["total_amount"] == 5000 + 900 - 100  # 5800


def test_note_pdf_download(s, credit_note):
    r = s.get(f"{API_URL}/api/finance/notes/{credit_note['id']}/pdf", timeout=15)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 1500  # plausible PDF size


def test_note_list_filter_by_kind(s):
    r = s.get(f"{API_URL}/api/finance/notes?kind=credit_note", timeout=10)
    assert r.status_code == 200
    assert all(n["kind"] == "credit_note" for n in r.json())


def test_cannot_approve_already_approved_note(s, credit_note):
    r = s.post(f"{API_URL}/api/finance/notes/{credit_note['id']}/approve", timeout=10)
    assert r.status_code == 400


def test_invalid_party_404(s):
    r = s.post(f"{API_URL}/api/finance/notes", json={
        "kind": "credit_note", "against_type": "invoice",
        "party_id": "non-existent", "party_type": "client",
        "reason_code": "other", "reason": "test",
        "taxable_value": 100.0,
    }, timeout=10)
    assert r.status_code == 404


# ───────────── Voucher PDF ─────────────
def test_voucher_pdf_export(s, credit_note):
    """The CN approval auto-posted a JE — fetch its PDF."""
    je_number = credit_note.get("note_number")  # the JE was numbered the same way
    jes = s.get(f"{API_URL}/api/accounts/journal-entries", timeout=10).json() or []
    if isinstance(jes, dict):
        jes = jes.get("data", [])
    je = next((j for j in jes if j.get("je_number") == je_number), None)
    assert je, "Auto-posted JE missing"
    r = s.get(f"{API_URL}/api/finance/vouchers/{je['id']}/pdf", timeout=15)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 1500
