"""Iter199 — Account module enhancements:
- Verified / Bank File bulk selection (payment-queue flows)
- Auto-fetch vendor bank details (vendor_master in payment-queue response)
- Save back to Vendor Master (save-vendor-bank-details, 400 on bad input)
- Today's Payment Verification Report (verification-report + export + remarks + 404)
- RBAC on report endpoints (403 for non-accounting roles)
"""
import os
import io
import re
import time
import pytest
import requests
from datetime import date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@erp.com", "Admin@123")


def _login(session: requests.Session, email: str, password: str):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        session.headers.update({"Authorization": f"Bearer {tok}"})
    return r.json()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    _login(s, *ADMIN)
    return s


# ─── 1) GET /api/accounts/payment-queue  → vendor_master present on vendor-linked rows ──
def test_payment_queue_has_vendor_master(admin):
    r = admin.get(f"{API}/accounts/payment-queue", timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = r.json()
    assert isinstance(rows, list)
    vm_rows = [row for row in rows if row.get("vendor_master")]
    print(f"[queue] total={len(rows)} with vendor_master={len(vm_rows)}")
    # Not strictly required to have any, but if any vendor rows exist, structure must be right
    for row in vm_rows[:5]:
        vm = row["vendor_master"]
        assert "id" in vm and "name" in vm
        assert "bank" in vm  # may be None if no bank attached


# ─── 2) Verification Report endpoint ────────────────────────────────────────
def test_verification_report_today(admin):
    today = date.today().isoformat()
    r = admin.get(f"{API}/accounts/payment-queue/verification-report?date={today}", timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "label" in data and "rows" in data and "totals" in data
    assert "verified_amount" in data["totals"]
    for row in data["rows"]:
        assert row.get("request_id") and row.get("beneficiary_name") is not None
    print(f"[report today] rows={len(data['rows'])} totals={data['totals']}")


def test_verification_report_wide_range(admin):
    r = admin.get(f"{API}/accounts/payment-queue/verification-report?date_from=2025-01-01&date_to=2027-12-31",
                  timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("rows"), list)
    print(f"[report wide] rows={len(data['rows'])}")
    # Save first rid for later remark tests
    pytest.first_rid = data["rows"][0]["request_id"] if data["rows"] else None


# ─── 3) PATCH report-remarks persistence and 404 ────────────────────────────
def test_report_remarks_404(admin):
    r = admin.patch(f"{API}/accounts/payment-queue/does-not-exist-xyz/report-remarks",
                    json={"remarks": "x"}, timeout=30)
    assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text[:200]}"


def test_report_remarks_persistence(admin):
    rid = getattr(pytest, "first_rid", None)
    if not rid:
        pytest.skip("No verified payment rows available to test remarks persistence")
    marker = f"TEST_iter199_remark_{int(time.time())}"
    r = admin.patch(f"{API}/accounts/payment-queue/{rid}/report-remarks",
                    json={"remarks": marker}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("remarks") == marker
    # Verify it appears in the next report fetch
    rep = admin.get(f"{API}/accounts/payment-queue/verification-report?date_from=2025-01-01&date_to=2027-12-31",
                    timeout=60).json()
    row = next((x for x in rep["rows"] if x["request_id"] == rid), None)
    assert row and row.get("remarks") == marker, f"remark did not persist: {row}"


# ─── 4) Exports: xlsx + pdf + invalid fmt ───────────────────────────────────
def test_export_xlsx(admin):
    today = date.today().isoformat()
    r = admin.get(f"{API}/accounts/payment-queue/verification-report/export/xlsx?date_from=2025-01-01&date_to=2027-12-31",
                  timeout=60)
    assert r.status_code == 200, r.text[:200]
    ct = r.headers.get("content-type", "")
    assert "spreadsheetml" in ct or "officedocument" in ct, ct
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd.lower() and ".xlsx" in cd.lower()
    assert r.content[:2] == b"PK", "xlsx must start with ZIP magic bytes"
    assert len(r.content) > 2000
    print(f"[xlsx] size={len(r.content)}")


def test_export_pdf(admin):
    r = admin.get(f"{API}/accounts/payment-queue/verification-report/export/pdf?date_from=2025-01-01&date_to=2027-12-31",
                  timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd.lower() and ".pdf" in cd.lower()
    assert r.content[:4] == b"%PDF", "pdf must start with %PDF magic"
    print(f"[pdf] size={len(r.content)}")


def test_export_invalid_fmt(admin):
    r = admin.get(f"{API}/accounts/payment-queue/verification-report/export/csv?date=2026-01-01",
                  timeout=30)
    assert r.status_code == 400, f"expected 400, got {r.status_code}"


# ─── 5) save-vendor-bank-details: validation errors ────────────────────────
def test_save_vendor_bank_invalid_account(admin):
    # Try with a real payment queue row that has a vendor linkage; else fall back
    r = admin.get(f"{API}/accounts/payment-queue", timeout=60).json()
    row = next((x for x in r if x.get("vendor_master")), None)
    if not row:
        pytest.skip("no vendor-linked payment row to test save-vendor-bank-details validation")
    rid = row["id"]
    bad = admin.post(f"{API}/accounts/payment-queue/{rid}/save-vendor-bank-details",
                     json={"account_no": "???", "ifsc": "HDFC0001234",
                           "bank_name": "x", "beneficiary_name": "x"}, timeout=30)
    assert bad.status_code == 400, bad.text[:200]
    bad2 = admin.post(f"{API}/accounts/payment-queue/{rid}/save-vendor-bank-details",
                      json={"account_no": "1234567890", "ifsc": "BAD_IFSC",
                            "bank_name": "x", "beneficiary_name": "x"}, timeout=30)
    assert bad2.status_code == 400, bad2.text[:200]


def test_save_vendor_bank_404(admin):
    r = admin.post(f"{API}/accounts/payment-queue/not-a-real-id/save-vendor-bank-details",
                   json={"account_no": "1234567890", "ifsc": "HDFC0001234",
                         "bank_name": "x", "beneficiary_name": "x"}, timeout=30)
    assert r.status_code == 404


# ─── 6) RBAC — non-accounting role should get 403 ───────────────────────────
def test_report_rbac_forbidden():
    s = requests.Session()
    try:
        _login(s, "safety@erp.com", "Safety@123")
    except AssertionError:
        pytest.skip("safety role login unavailable")
    r = s.get(f"{API}/accounts/payment-queue/verification-report?date=2026-01-01", timeout=30)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
    r2 = s.get(f"{API}/accounts/payment-queue/verification-report/export/pdf?date=2026-01-01", timeout=30)
    assert r2.status_code in (401, 403)
