"""Iter200 — Payment Processing Center: Reject Payment endpoint
Covers:
- Happy path reject from `verified`
- Mandatory reason validation (missing / blank / <3 char → 400)
- Reject already-paid payment → 400
- Reject pending_verification payment → 400
- Reject unknown rid → 404
- RBAC: no accounting write permission → 403
- No journal entry is created on rejection
- Re-verify a rejected row restores it to `verified`
Cleans up by re-verifying any row it rejected.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@erp.com", "Admin@123")
SAFETY = ("safety@erp.com", "Safety@123")


def _login(sess: requests.Session, email: str, password: str):
    r = sess.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        sess.headers.update({"Authorization": f"Bearer {tok}"})
    return r.json()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    _login(s, *ADMIN)
    return s


@pytest.fixture(scope="module")
def safety():
    s = requests.Session()
    try:
        _login(s, *SAFETY)
    except AssertionError:
        pytest.skip("safety_officer login unavailable")
    return s


@pytest.fixture(scope="module")
def queue(admin):
    r = admin.get(f"{API}/accounts/payment-queue", timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _find_by_stage(rows, stage):
    return [r for r in rows if r.get("pay_stage") == stage]


def _verify_row(admin, rid, prior_verif=None, amount=None):
    """Re-verify a row — reuses the previous verification fields when available."""
    v = prior_verif or {}
    payload = {"decision": "verified",
               "vendor_name": v.get("vendor_name") or "TEST_ITER200",
               "vendor_account_no": v.get("vendor_account_no") or "123456789012",
               "ifsc": v.get("ifsc") or "HDFC0001234",
               "bank_name": v.get("bank_name") or "HDFC",
               "gst_applicable": bool(v.get("gst_applicable")),
               "gstin": v.get("gstin") or "",
               "gst_amount": float(v.get("gst_amount") or 0),
               "invoice_type": v.get("invoice_type") or "bill",
               "invoice_no": v.get("invoice_no") or f"TEST-ITER200-{rid[:6]}",
               "invoice_date": v.get("invoice_date") or "2026-01-01",
               "vendor_email": v.get("vendor_email") or "",
               "verified_amount": float(amount if amount is not None else (v.get("verified_amount") or 100.0)),
               "tds_applicable": bool(v.get("tds_applicable")),
               "tds_pct": float(v.get("tds_pct") or 0),
               "tds_amount": float(v.get("tds_amount") or 0),
               "advance_adjusted": float(v.get("advance_adjusted") or 0),
               "expense_account_code": v.get("expense_account_code") or "5150",
               "remarks": v.get("remarks") or ""}
    return admin.post(f"{API}/accounts/payment-queue/{rid}/verify", json=payload, timeout=30)


# ─── Reject-payment: happy path ────────────────────────────────────────────
def test_reject_from_verified(admin, queue):
    verified = _find_by_stage(queue, "verified") + _find_by_stage(queue, "in_bank_file")
    if not verified:
        pytest.skip("No verified / in_bank_file row to reject")
    target = verified[0]
    rid = target["id"]
    original_stage = target["pay_stage"]
    original_amount = (target.get("verification") or {}).get("verified_amount")
    r = admin.post(f"{API}/accounts/payment-queue/{rid}/reject-payment",
                   json={"reason": "TEST_ITER200 duplicate invoice — reject"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["stage"] == "rejected"
    assert data["rejection_reason"].startswith("TEST_ITER200")
    assert data["rejected_from_stage"] == original_stage
    assert data.get("rejected_by")
    assert data.get("rejected_at")

    # Verify project_requests row got the mirror fields
    r2 = admin.get(f"{API}/accounts/payment-queue", timeout=60)
    assert r2.status_code == 200
    row = next((x for x in r2.json() if x["id"] == rid), None)
    assert row is not None, "rid vanished from queue after reject"
    assert row["pay_stage"] == "rejected"
    assert row.get("payment_status") == "rejected" or (row.get("verification") or {}).get("stage") == "rejected"

    # No journal entry should be created from the reject action
    je = admin.get(f"{API}/finance/journal-entries", params={"source_id": rid}, timeout=30)
    if je.status_code == 200:
        for j in je.json() or []:
            assert j.get("source_event") != "rejected", "No JE should be created on reject"

    # Cleanup: re-verify to restore
    rev = _verify_row(admin, rid, prior_verif=target.get("verification"))
    assert rev.status_code == 200, f"cleanup re-verify failed: {rev.status_code} {rev.text[:200]}"


# ─── Mandatory reason validations ──────────────────────────────────────────
@pytest.mark.parametrize("body", [
    {},
    {"reason": ""},
    {"reason": "   "},
    {"reason": "ab"},
])
def test_reject_requires_reason(admin, queue, body):
    verified = _find_by_stage(queue, "verified") + _find_by_stage(queue, "in_bank_file")
    if not verified:
        pytest.skip("No verified row to test")
    rid = verified[0]["id"]
    r = admin.post(f"{API}/accounts/payment-queue/{rid}/reject-payment", json=body, timeout=30)
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"
    assert "mandatory" in r.text.lower() or "reason" in r.text.lower()


# ─── Unknown rid → 404 ─────────────────────────────────────────────────────
def test_reject_unknown_rid(admin):
    r = admin.post(f"{API}/accounts/payment-queue/does-not-exist-xyz/reject-payment",
                   json={"reason": "TEST_ITER200 bogus id"}, timeout=30)
    assert r.status_code == 404, f"got {r.status_code} {r.text[:200]}"


# ─── Pending verification → 400 ────────────────────────────────────────────
def test_reject_pending_verification(admin, queue):
    pending = _find_by_stage(queue, "pending_verification")
    if not pending:
        pytest.skip("no pending_verification row to test")
    rid = pending[0]["id"]
    r = admin.post(f"{API}/accounts/payment-queue/{rid}/reject-payment",
                   json={"reason": "TEST_ITER200 should fail — pending stage"}, timeout=30)
    assert r.status_code in (400, 404)
    if r.status_code == 400:
        assert "verif" in r.text.lower() or "stage" in r.text.lower()


# ─── Already paid → 400 ────────────────────────────────────────────────────
def test_reject_already_paid(admin, queue):
    paid = _find_by_stage(queue, "paid")
    if not paid:
        pytest.skip("no paid row to test")
    rid = paid[0]["id"]
    r = admin.post(f"{API}/accounts/payment-queue/{rid}/reject-payment",
                   json={"reason": "TEST_ITER200 should fail — already paid"}, timeout=30)
    assert r.status_code == 400
    assert "paid" in r.text.lower()


# ─── RBAC: safety_officer must be denied ────────────────────────────────────
def test_reject_rbac_denied(safety, queue):
    verified = _find_by_stage(queue, "verified") + _find_by_stage(queue, "in_bank_file")
    rid = verified[0]["id"] if verified else "any-id"
    r = safety.post(f"{API}/accounts/payment-queue/{rid}/reject-payment",
                    json={"reason": "TEST_ITER200 rbac check"}, timeout=30)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# ─── Re-verify after reject restores to verified ───────────────────────────
def test_reverify_after_reject(admin, queue):
    verified = _find_by_stage(queue, "verified") + _find_by_stage(queue, "in_bank_file")
    if not verified:
        pytest.skip("No verified row")
    target = verified[0]
    rid = target["id"]
    prior = target.get("verification")
    # reject
    r1 = admin.post(f"{API}/accounts/payment-queue/{rid}/reject-payment",
                    json={"reason": "TEST_ITER200 reverify flow"}, timeout=30)
    assert r1.status_code == 200
    # re-verify
    r2 = _verify_row(admin, rid, prior_verif=prior)
    assert r2.status_code == 200, f"re-verify failed: {r2.status_code} {r2.text[:200]}"
    # confirm queue reflects verified
    r3 = admin.get(f"{API}/accounts/payment-queue", timeout=60)
    row = next((x for x in r3.json() if x["id"] == rid), None)
    assert row and row["pay_stage"] in ("verified", "in_bank_file")
