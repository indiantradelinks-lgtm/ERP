"""Iteration 194 backend tests: Bulk UTR upload/apply + Bill Request 'full' view."""
import io
import os
import time
import pytest
import requests
from openpyxl import Workbook, load_workbook


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    assert v
    return v.rstrip("/")


BASE = _base()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def pm():
    return _login("test_pm@erp.com", "PM@12345")


# ── Bulk UTR ─────────────────────────────────────────────────────────────────
def _template_rows(sess):
    r = sess.get(f"{BASE}/api/accounts/payment-queue/bulk-utr/template", timeout=30)
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct, ct
    wb = load_workbook(io.BytesIO(r.content), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    assert header[0] == "Request No" and header[1] == "UTR No"
    return rows[1:]


def _build_xlsx(records):
    wb = Workbook()
    ws = wb.active
    ws.append(["Request No", "UTR No", "Paid Date (YYYY-MM-DD)", "Vendor", "Net Payable", "Stage"])
    for rec in records:
        ws.append(rec)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_template_downloads(admin):
    rows = _template_rows(admin)
    assert isinstance(rows, list)


def test_bulk_utr_validate_and_apply(admin):
    rows = _template_rows(admin)
    real_rows = [r for r in rows if r and r[0]]
    if not real_rows:
        pytest.skip("No verified/in_bank_file payments in queue — cannot exercise bulk UTR")
    first_req = real_rows[0][0]
    second_req = real_rows[1][0] if len(real_rows) > 1 else None
    ts = int(time.time())
    utr1 = f"UTR-T194-{ts}"
    utr2 = f"UTR-T194-{ts}-B"

    records = [
        [first_req, utr1, "2026-01-15", real_rows[0][3], real_rows[0][4], real_rows[0][5]],
        [first_req, "", "2026-01-15", "", "", ""],  # skipped (blank UTR)
        ["REQ-9999-XXXX", f"UTR-BOGUS-{ts}", "2026-01-15", "", "", ""],
        [first_req, utr2, "2026-01-15", "", "", ""],  # duplicate Request No
    ]
    if second_req:
        records.append([second_req, utr1, "2026-01-15", "", "", ""])  # duplicate UTR in file
    xlsx = _build_xlsx(records)

    # Validate
    r = admin.post(f"{BASE}/api/accounts/payment-queue/bulk-utr/validate",
                   files={"file": ("bulk.xlsx", xlsx,
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                   timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["skipped"] == 1
    valid_reqs = [v["request_no"] for v in d["valid"]]
    assert valid_reqs == [first_req]
    error_msgs = " | ".join(e.get("error", "") for e in d["errors"])
    assert "not found" in error_msgs.lower()
    assert "duplicate request" in error_msgs.lower()
    if second_req:
        assert "duplicate utr" in error_msgs.lower() or "utr already" in error_msgs.lower()

    # Non-xlsx → 400
    r = admin.post(f"{BASE}/api/accounts/payment-queue/bulk-utr/validate",
                   files={"file": ("bulk.csv", b"a,b,c", "text/csv")}, timeout=30)
    assert r.status_code == 400

    # Apply with only the valid first row
    xlsx_ok = _build_xlsx([[first_req, utr1, "2026-01-15", "", "", ""]])
    r = admin.post(f"{BASE}/api/accounts/payment-queue/bulk-utr/apply",
                   files={"file": ("apply.xlsx", xlsx_ok,
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                   timeout=120)
    assert r.status_code == 200, r.text
    ap = r.json()
    assert len(ap["paid"]) == 1
    assert ap["paid"][0]["request_no"] == first_req
    assert ap["paid"][0]["utr_no"] == utr1

    # Verify state: request moved to paid
    q = admin.get(f"{BASE}/api/accounts/payment-queue", timeout=30).json()
    match = [x for x in q if x.get("request_no") == first_req]
    if match:
        assert match[0].get("pay_stage") == "paid"
        assert (match[0].get("verification") or {}).get("utr_no") == utr1

    # Voucher exists
    v = admin.get(f"{BASE}/api/accounts/vouchers", params={"voucher_type": "PYV", "page": 1}, timeout=30)
    assert v.status_code == 200

    # Re-upload same row → 'Already paid'
    r = admin.post(f"{BASE}/api/accounts/payment-queue/bulk-utr/validate",
                   files={"file": ("bulk2.xlsx", xlsx_ok,
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                   timeout=30)
    assert r.status_code == 200
    d2 = r.json()
    assert d2["valid"] == []
    assert any("already paid" in (e.get("error") or "").lower() for e in d2["errors"])


def test_bulk_utr_pm_forbidden(pm):
    xlsx = _build_xlsx([["REQ-9999", "UTR-X", "2026-01-15", "", "", ""]])
    r = pm.post(f"{BASE}/api/accounts/payment-queue/bulk-utr/validate",
                files={"file": ("bulk.xlsx", xlsx,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=30)
    assert r.status_code == 403


# ── Bill request full view ───────────────────────────────────────────────────
RID = "010758f6-4e56-4aea-ba63-91bfdd5b459d"
BILL_ID = "e54853c9-5b86-4a4f-adb5-2c8fea8f42fa"
DELETED_BILL_RID = "b8aba2a0-ecca-44fa-ad42-df059b04a263"


def test_bill_request_full(admin):
    r = admin.get(f"{BASE}/api/bill-requests/{RID}/full", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    req = d.get("request") or {}
    assert req.get("request_no") == "BR-2026-0008"
    assert req.get("status") == "bill_generated"
    assert d.get("approval") and (d["approval"].get("chain") or [])
    bill = d.get("bill") or {}
    assert bill.get("bill_number") == "RA-2026-0024"
    assert d.get("bill_pdf_url", "").endswith(f"/api/ra-bills/{bill['id']}/pdf")
    assert isinstance(d.get("files"), list)
    assert isinstance(d.get("history"), list)


def test_bill_request_full_unknown(admin):
    r = admin.get(f"{BASE}/api/bill-requests/does-not-exist-xyz/full", timeout=30)
    assert r.status_code == 404


def test_bill_request_deleted_bill(admin):
    r = admin.get(f"{BASE}/api/bill-requests/{DELETED_BILL_RID}/full", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("bill") is None
    # bill_pdf_url should be null when no bill
    assert not d.get("bill_pdf_url")


def test_ra_bill_pdf(admin):
    r = admin.get(f"{BASE}/api/ra-bills/{BILL_ID}/pdf", timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 10_000


def test_bill_request_full_readonly(admin):
    """Ensure GET /full does NOT mutate the bill_requests document."""
    before = admin.get(f"{BASE}/api/bill-requests/{RID}", timeout=30).json()
    admin.get(f"{BASE}/api/bill-requests/{RID}/full", timeout=30)
    after = admin.get(f"{BASE}/api/bill-requests/{RID}", timeout=30).json()
    # Compare stable fields
    for k in ("request_no", "status", "bill_id", "bill_number", "created_at"):
        assert before.get(k) == after.get(k)
