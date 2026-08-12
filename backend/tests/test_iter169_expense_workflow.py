"""Iter 169 — Expense Type/Date/Settlement/Paid-To fields on project requests
and Accounts payment-queue enrichment + CMS Remarks column from verification.

Covers backend items from the current review request:
  1. POST /api/project-requests accepts expense_type/date/settlement_mode/paid_to_type
  2. GET  /api/project-requests attaches pay_stage/pay_info on approved payment rows
  3. GET  /api/accounts/payment-queue returns project_manager (+ project_name / employee fields when set)
  4. POST /api/accounts/payment-queue/bank-file CMS Remarks column = verification.remarks
  5. POST /api/project-expenses stores paid_to_type + employee fields
"""
import os
import io
import pytest
import requests
from openpyxl import load_workbook
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


# ---- helpers ----
def _first_project(admin):
    r = admin.get(f"{BASE}/api/projects")
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert rows, "need at least one project"
    return rows[0]


# ------------- 1. Create payment request with new fields -------------
def test_create_payment_request_with_new_fields(admin):
    proj = _first_project(admin)
    body = {
        "request_type": "accommodation",
        "project_id": proj["id"],
        "amount": 12345,
        "vendor": "SteelTech Supplies",
        "paid_to_type": "vendor",
        "expense_type": "travelling",           # override
        "expense_date": "2026-01-20",
        "settlement_mode": "vendor_payable",
        "description": "TEST iter169 travelling override",
        "priority": "medium",
    }
    r = admin.post(f"{BASE}/api/project-requests", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["expense_type"] == "travelling"    # override applied
    assert d["expense_date"] == "2026-01-20"
    assert d["settlement_mode"] == "vendor_payable"
    assert d["paid_to_type"] == "vendor"
    assert d["vendor"] == "SteelTech Supplies"
    assert d["is_payment"] is True
    assert d["status"] == "pending_approval"

    # GET back and confirm persistence
    r2 = admin.get(f"{BASE}/api/project-requests")
    assert r2.status_code == 200
    row = next((x for x in r2.json() if x["id"] == d["id"]), None)
    assert row is not None
    assert row["expense_type"] == "travelling"
    # pending_approval → NO pay_stage
    assert "pay_stage" not in row or row.get("pay_stage") is None


def test_create_request_invalid_expense_type_falls_back(admin):
    proj = _first_project(admin)
    r = admin.post(f"{BASE}/api/project-requests", json={
        "request_type": "fuel", "project_id": proj["id"],
        "amount": 500, "expense_type": "does_not_exist"})
    assert r.status_code == 200
    # falls back to routing meta (fuel → fuel)
    assert r.json()["expense_type"] == "fuel"


# ------------- 2. GET returns pay_stage on approved payment rows -------------
def test_list_requests_pay_stage_on_approved_payment(admin):
    r = admin.get(f"{BASE}/api/project-requests")
    assert r.status_code == 200
    rows = r.json()
    approved_payments = [x for x in rows if x.get("is_payment") and x.get("status") in
                         ("with_dept", "pr_raised", "sourcing", "fulfilled")]
    non_pay = [x for x in rows if not x.get("is_payment")]
    if approved_payments:
        r0 = approved_payments[0]
        assert "pay_stage" in r0
        assert r0["pay_stage"] in ("pending_verification", "verified", "rejected",
                                   "in_bank_file", "paid")
    for x in non_pay[:10]:
        assert "pay_stage" not in x or x.get("pay_stage") is None


# ------------- 3. Payment queue enrichment -------------
def test_payment_queue_enrichment(admin):
    r = admin.get(f"{BASE}/api/accounts/payment-queue")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    if rows:
        keys = set(rows[0].keys())
        # project_manager join key present (may be None if not set on project)
        assert "project_manager" in keys
        assert "project_name" in keys
        # employee_code / employee_name are optional on the doc, but keys should not throw
        # (they exist when set at raise time)


# ------------- 4. Bank file CMS Remarks from verification.remarks -------------
def _pick_pending(admin):
    r = admin.get(f"{BASE}/api/accounts/payment-queue")
    assert r.status_code == 200
    for row in r.json():
        if row.get("pay_stage") == "pending_verification":
            return row
    return None


def test_bank_file_cms_remarks_uses_verification_remarks(admin):
    row = _pick_pending(admin)
    if not row:
        pytest.skip("No pending_verification row to test CMS remark override")
    rid = row["id"]
    marker = "TEST CMS REMARK 123"
    body = {
        "decision": "verified",
        "vendor_name": "TEST_Iter169_Vendor",
        "vendor_account_no": "0011223344",
        "ifsc": "HDFC0001234",
        "bank_name": "HDFC",
        "invoice_no": "INV-ITER169-CMS",
        "verified_amount": 4321.0,
        "remarks": marker,
    }
    v = admin.post(f"{BASE}/api/accounts/payment-queue/{rid}/verify", json=body)
    assert v.status_code == 200, v.text

    bf = admin.post(f"{BASE}/api/accounts/payment-queue/bank-file",
                    json={"request_ids": [rid], "payment_mode": "N"})
    assert bf.status_code == 200, bf.text
    wb = load_workbook(io.BytesIO(bf.content))
    ws = wb.active
    headers = [c.value for c in ws[1]]
    assert headers[-1] == "Remarks"
    remark_col = len(headers)  # 1-indexed
    found = False
    for r_idx in range(2, ws.max_row + 1):
        val = ws.cell(row=r_idx, column=remark_col).value
        if val and marker in str(val):
            found = True
            break
    assert found, f"CMS Remarks column did not contain '{marker}'"


# ------------- 5. Project expense with paid_to_type=person -------------
def test_project_expense_paid_to_person(admin):
    proj = _first_project(admin)
    # try to find an employee via eligible-employees endpoint
    r = admin.get(f"{BASE}/api/advances/eligible-employees")
    emp = None
    if r.status_code == 200:
        rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        if rows:
            emp = rows[0]
    body = {
        "project_id": proj["id"],
        "expense_type": "travelling",
        "expense_date": "2026-01-20",
        "amount": 250.0,
        "description": "TEST iter169 person paid-to",
        "paid_to_type": "person",
        "paid_to": (emp or {}).get("name") or "TEST Person",
        "employee_id": (emp or {}).get("id"),
        "employee_code": (emp or {}).get("employee_id") or (emp or {}).get("emp_code"),
        "employee_name": (emp or {}).get("name") or "TEST Person",
        "settlement_mode": "employee_reimbursement",
        "payment_mode": "Cash",
    }
    r = admin.post(f"{BASE}/api/project-expenses", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["paid_to_type"] == "person"
    assert d["employee_name"] == body["employee_name"]
    assert d["settlement_mode"] == "employee_reimbursement"

    # GET verify
    g = admin.get(f"{BASE}/api/project-expenses",
                  params={"project_code": proj.get("code")})
    assert g.status_code == 200
    match = next((x for x in g.json() if x["id"] == d["id"]), None)
    assert match and match["paid_to_type"] == "person"
