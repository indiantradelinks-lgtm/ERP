"""Iter 74 — Phase 3 Vendor Bill Processing & Payables tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
TS = str(int(time.time()))
VENDOR_NAME = f"ZQ Test Steel {TS}"
INVOICE_NO = f"UNIQUE-{TS}"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    s.headers["Content-Type"] = "application/json"
    return s


@pytest.fixture(scope="session")
def state():
    return {}


# ─── Catalogs ───────────────────────────────────────────────────────────
def test_expense_categories(client):
    r = client.get(f"{BASE_URL}/api/payables/expense-categories")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 18, f"expected 18 categories got {len(data)}"
    keys = {row["key"] for row in data}
    assert {"material", "labour", "subcontract", "tools", "fuel"}.issubset(keys)
    by_key = {row["key"]: row["account_code"] for row in data}
    assert by_key["material"] == "5105"


# ─── Bill creation & totals ─────────────────────────────────────────────
def test_create_vendor_bill_totals(client, state):
    payload = {
        "vendor_name": VENDOR_NAME,
        "invoice_no": INVOICE_NO,
        "invoice_date": "2026-06-06",
        "expense_category": "material",
        "force_no_po": True, "force_no_grn": True,
        "bank_verified": True,
        "lines": [{"description": "Pipes", "quantity": 100, "unit": "Mtr", "rate": 250}],
        "gst_rate": 18, "tds_section": "194C", "tds_rate": 2,
        "due_days": 30,
        "attachments": [{"name": "inv.pdf"}],
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills", json=payload)
    assert r.status_code == 200, r.text
    b = r.json()
    state["bill"] = b
    import re
    assert re.match(r"^VB-2026-\d{4}$", b["bill_no"]), b["bill_no"]
    t = b["totals"]
    assert t["taxable"] == 25000
    assert t["gst"] == 4500
    assert t["cgst"] == 2250
    assert t["sgst"] == 2250
    assert t["gross"] == 29500
    assert t["tds"] == 500
    assert t["net_payable"] == 29000
    assert b["outstanding"] == 29000
    assert b["status"] == "draft"


def test_duplicate_invoice_blocked(client):
    payload = {
        "vendor_name": VENDOR_NAME, "invoice_no": INVOICE_NO,
        "invoice_date": "2026-06-06", "expense_category": "material",
        "force_no_po": True, "force_no_grn": True, "bank_verified": True,
        "lines": [{"description": "Pipes", "quantity": 1, "rate": 100}],
        "attachments": [{"name": "x.pdf"}],
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills", json=payload)
    assert r.status_code == 409, r.text
    assert "uplicate" in r.json().get("detail", "")


def test_missing_po_grn_blocked(client):
    payload = {
        "vendor_name": f"ZQ_NoPO_{TS}", "invoice_no": f"NOPO-{TS}",
        "invoice_date": "2026-06-06", "expense_category": "material",
        "bank_verified": True,
        "lines": [{"description": "x", "quantity": 1, "rate": 100}],
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills", json=payload)
    assert r.status_code == 400
    msg = r.json().get("detail", "")
    assert ("PO" in msg) or ("GRN" in msg)


def test_tds_cap(client):
    payload = {
        "vendor_name": f"ZQ_TDS_{TS}", "invoice_no": f"TDS-{TS}",
        "invoice_date": "2026-06-06", "expense_category": "material",
        "force_no_po": True, "force_no_grn": True, "bank_verified": True,
        "lines": [{"description": "x", "quantity": 1, "rate": 1000}],
        "gst_rate": 18, "tds_rate": 200,
        "attachments": [{"name": "x.pdf"}],
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills", json=payload)
    assert r.status_code == 400
    assert "TDS" in r.json().get("detail", "")


# ─── Verify + approve + JE check ────────────────────────────────────────
def test_verify_and_approve_and_je(client, state):
    bid = state["bill"]["id"]
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills/{bid}/verify")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verified"

    r = client.post(f"{BASE_URL}/api/payables/vendor-bills/{bid}/approve")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "approved"
    assert b.get("je_voucher_number"), "JE voucher number missing"
    state["bill"] = b
    state["je_vno"] = b["je_voucher_number"]

    # Fetch JE
    r = client.get(f"{BASE_URL}/api/accounts/journal-entries",
                   params={"voucher_number": state["je_vno"]})
    if r.status_code != 200:
        # Try list w/o param
        r = client.get(f"{BASE_URL}/api/accounts/journal-entries")
    assert r.status_code == 200, r.text
    entries = r.json()
    if isinstance(entries, dict):
        entries = entries.get("rows") or entries.get("items") or []
    je = next((e for e in entries if e.get("voucher_number") == state["je_vno"]), None)
    assert je is not None, f"JE {state['je_vno']} not found"
    assert je.get("voucher_type") == "PUV"
    total_d = sum(float(l.get("debit") or 0) for l in je["lines"])
    total_c = sum(float(l.get("credit") or 0) for l in je["lines"])
    assert abs(total_d - total_c) < 0.01, f"Unbalanced JE: D={total_d} C={total_c}"
    by_code: dict = {}
    for ln in je["lines"]:
        c = ln.get("account_code")
        by_code.setdefault(c, {"d": 0.0, "c": 0.0})
        by_code[c]["d"] += float(ln.get("debit") or 0)
        by_code[c]["c"] += float(ln.get("credit") or 0)
    assert by_code.get("5105", {}).get("d") == 25000, by_code
    assert by_code.get("1700", {}).get("d") == 4500, by_code
    assert by_code.get("2100", {}).get("c") == 29000, by_code
    assert by_code.get("2400", {}).get("c") == 500, by_code


def test_reapprove_blocked(client, state):
    bid = state["bill"]["id"]
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills/{bid}/approve")
    assert r.status_code == 400
    assert "approved" in r.json().get("detail", "").lower()


# ─── Vendor payment + JE ────────────────────────────────────────────────
def test_vendor_payment(client, state):
    bid = state["bill"]["id"]
    payload = {
        "payment_date": "2026-06-10", "vendor_name": VENDOR_NAME,
        "bill_ids": [bid], "mode": "NEFT", "utr": f"UTR-{TS}",
        "amount": 28000, "retention_held": 1000,
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-payments", json=payload)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["total_settled"] == 29000
    assert p["status"] == "released"
    assert p.get("je_voucher_number")
    state["pay_je"] = p["je_voucher_number"]

    # Bill should be paid
    r = client.get(f"{BASE_URL}/api/payables/vendor-bills/{bid}")
    b = r.json()
    assert b["status"] == "paid", b
    assert b["outstanding"] == 0

    # Pay JE check
    r = client.get(f"{BASE_URL}/api/accounts/journal-entries")
    entries = r.json()
    if isinstance(entries, dict):
        entries = entries.get("rows") or entries.get("items") or []
    je = next((e for e in entries if e.get("voucher_number") == state["pay_je"]), None)
    assert je is not None
    assert je.get("voucher_type") == "PV"
    total_d = sum(float(l.get("debit") or 0) for l in je["lines"])
    total_c = sum(float(l.get("credit") or 0) for l in je["lines"])
    assert abs(total_d - total_c) < 0.01
    by_code = {}
    for ln in je["lines"]:
        c = ln.get("account_code")
        by_code.setdefault(c, {"d": 0.0, "c": 0.0})
        by_code[c]["d"] += float(ln.get("debit") or 0)
        by_code[c]["c"] += float(ln.get("credit") or 0)
    assert by_code.get("2100", {}).get("d") == 29000, by_code
    assert by_code.get("1100", {}).get("c") == 28000, by_code
    assert by_code.get("2110", {}).get("c") == 1000, by_code


def test_pay_unverified_bank(client, state):
    # Create a bill w/ bank_verified=false
    payload = {
        "vendor_name": f"ZQ_NoBank_{TS}", "invoice_no": f"NB-{TS}",
        "invoice_date": "2026-06-06", "expense_category": "material",
        "force_no_po": True, "force_no_grn": True, "bank_verified": False,
        "lines": [{"description": "x", "quantity": 1, "rate": 1000}],
        "gst_rate": 18, "attachments": [{"name": "x.pdf"}],
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills", json=payload)
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    client.post(f"{BASE_URL}/api/payables/vendor-bills/{bid}/verify")
    client.post(f"{BASE_URL}/api/payables/vendor-bills/{bid}/approve")
    pay = {"payment_date": "2026-06-10", "vendor_name": f"ZQ_NoBank_{TS}",
           "bill_ids": [bid], "mode": "NEFT", "amount": 1180}
    r = client.post(f"{BASE_URL}/api/payables/vendor-payments", json=pay)
    assert r.status_code == 400
    assert "bank" in r.json().get("detail", "").lower()
    state["unverified_bid"] = bid


def test_excess_payment(client):
    # Create a small bill
    payload = {
        "vendor_name": f"ZQ_Excess_{TS}", "invoice_no": f"EX-{TS}",
        "invoice_date": "2026-06-06", "expense_category": "material",
        "force_no_po": True, "force_no_grn": True, "bank_verified": True,
        "lines": [{"description": "x", "quantity": 1, "rate": 1000}],
        "gst_rate": 18, "attachments": [{"name": "x.pdf"}],
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills", json=payload)
    bid = r.json()["id"]
    client.post(f"{BASE_URL}/api/payables/vendor-bills/{bid}/verify")
    client.post(f"{BASE_URL}/api/payables/vendor-bills/{bid}/approve")
    # without reason
    pay = {"payment_date": "2026-06-10", "vendor_name": f"ZQ_Excess_{TS}",
           "bill_ids": [bid], "mode": "NEFT", "amount": 5000}
    r = client.post(f"{BASE_URL}/api/payables/vendor-payments", json=pay)
    assert r.status_code == 400
    assert "xcess" in r.json().get("detail", "")
    # with reason
    pay["excess_reason"] = "Advance for next bill"
    r = client.post(f"{BASE_URL}/api/payables/vendor-payments", json=pay)
    assert r.status_code == 200, r.text


def test_po_grn_mismatch(client):
    # Known existing GRN+PO pair from preview DB
    grn_no, real_po = "GRN-2026-0006", "PO-2026-0043"
    payload = {
        "vendor_name": f"ZQ_Mis_{TS}", "invoice_no": f"MIS-{TS}",
        "invoice_date": "2026-06-06", "expense_category": "material",
        "grn_number": grn_no, "po_number": "FAKE-PO-XYZ-9999",
        "force_no_po": True,  # allow phantom po
        "bank_verified": True,
        "lines": [{"description": "x", "quantity": 1, "rate": 100}],
        "attachments": [{"name": "x.pdf"}],
    }
    r = client.post(f"{BASE_URL}/api/payables/vendor-bills", json=payload)
    assert r.status_code == 400
    assert "belongs to PO" in r.json().get("detail", "")


# ─── Reports ────────────────────────────────────────────────────────────
def test_report_vendor_outstanding(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/vendor-outstanding")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "buckets" in d and set(d["buckets"].keys()) == {"0-30", "31-60", "61-90", "90+"}
    assert "total_outstanding" in d
    assert "vendors" in d


def test_report_payable_aging_alias(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/payable-aging")
    assert r.status_code == 200
    d = r.json()
    assert "buckets" in d


def test_report_payment_due(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/payment-due", params={"days_ahead": 7})
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d and "total_due" in d


def test_report_vendor_advance(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/vendor-advance")
    assert r.status_code == 200
    assert "vendors" in r.json()


def test_report_retention_payable(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/retention-payable")
    assert r.status_code == 200
    d = r.json()
    assert "vendors" in d and "total_retention" in d
    assert d["total_retention"] >= 1000


def test_report_tds_payable(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/tds-payable")
    assert r.status_code == 200
    d = r.json()
    assert d["total_tds"] >= 500
    assert any(s["section"] == "194C" for s in d["by_section"])


def test_report_gst_purchase(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/gst-purchase-register")
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d and "totals" in d
    row_total = round(sum(float(r.get("gross") or 0) for r in d["rows"]), 2)
    assert abs(row_total - d["totals"]["gross"]) < 1


def test_report_project_vendor_cost(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/project-vendor-cost")
    assert r.status_code == 200
    assert "projects" in r.json()


def test_report_grn_pending(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/grn-pending-invoice")
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d and "count" in d


def test_report_duplicate_check(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/duplicate-invoice-check")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_report_vendor_ledger(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/vendor-ledger",
                   params={"vendor_name": VENDOR_NAME})
    assert r.status_code == 200
    d = r.json()
    assert "events" in d
    # bill + payment events
    assert len(d["events"]) >= 2
    dates = [e["date"] for e in d["events"]]
    assert dates == sorted(dates)


def test_report_po_payable(client):
    r = client.get(f"{BASE_URL}/api/payables/reports/po-payable")
    assert r.status_code == 200
    assert "pos" in r.json()
