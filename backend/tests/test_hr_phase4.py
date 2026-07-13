"""HR Phase 4 backend tests — salary structures, loans, reimbursements,
store recoveries, payroll finance-approval + accounts posting, statutory reports."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
BASE = f"{BASE_URL}/api"
EMAIL = os.environ.get("ADMIN_EMAIL", "admin@erp.com")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text

    class C:
        def __init__(self, sess): self._s = sess
        def post(self, url, json=None): return self._s.post(f"{BASE}{url}", json=json, timeout=30)
        def get(self, url):              return self._s.get(f"{BASE}{url}", timeout=30)
        def put(self, url, json=None):   return self._s.put(f"{BASE}{url}", json=json, timeout=30)

    yield C(s)
    s.close()


@pytest.fixture(scope="module")
def test_emp(client):
    r = client.post("/employees", json={
        "name": "PYTEST HR4 Emp", "department": "Operations",
        "designation": "Engineer", "status": "active",
    })
    if r.status_code not in (200, 201):
        pytest.skip(f"employees POST unavailable: {r.status_code}")
    return r.json()


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Salary structure
# ──────────────────────────────────────────────────────────────────────────────
def test_dashboard(client):
    r = client.get("/hr4/dashboard")
    assert r.status_code == 200
    j = r.json()
    for k in ("salary_structures_pending", "loans_active",
              "reimbursements_pending", "store_recoveries_pending"):
        assert k in j


def test_structure_create_approve(client, test_emp):
    r = client.post("/hr4/salary-structures", json={
        "employee_id": test_emp["id"],
        "wage_type": "monthly",
        "basic": 25000, "hra": 10000, "conveyance": 1600,
        "site_allowance": 5000, "food_allowance": 2000, "other_allowance": 1500,
        "overtime_rate": 200, "pf_applicable": True, "esic_applicable": False,
        "tds_applicable": True, "professional_tax": 200,
        "effective_from": "2026-01-01",
    })
    assert r.status_code == 200, r.text
    ss = r.json()
    assert ss["structure_no"].startswith("SS-")
    assert ss["approval_status"] == "pending"
    # Approve
    r2 = client.post(f"/hr4/salary-structures/{ss['id']}/approve",
                     json={"decision": "approve"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["approval_status"] == "approved"
    # Audit
    r3 = client.get(f"/hr4/salary-structures/{ss['id']}/audit")
    assert r3.status_code == 200
    actions = [x["action"] for x in r3.json()]
    assert "create" in actions and "approval_approve" in actions
    # payroll_master synced
    r4 = client.get(f"/payroll/master/{test_emp['id']}")
    assert r4.status_code == 200, r4.text
    pm = r4.json()
    assert pm["basic"] == 25000
    assert pm["hra"] == 10000


def test_structure_bad_wage_type(client, test_emp):
    r = client.post("/hr4/salary-structures", json={
        "employee_id": test_emp["id"],
        "wage_type": "yearly", "effective_from": "2026-01-01",
    })
    assert r.status_code == 400


def test_structure_unknown_employee(client):
    r = client.post("/hr4/salary-structures", json={
        "employee_id": "nonexistent",
        "wage_type": "monthly", "effective_from": "2026-01-01",
    })
    assert r.status_code == 404


def test_structure_list(client):
    r = client.get("/hr4/salary-structures?approval_status=approved")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Loans
# ──────────────────────────────────────────────────────────────────────────────
def test_loan_full_flow(client, test_emp):
    r = client.post("/hr4/loans", json={
        "employee_id": test_emp["id"], "loan_amount": 50000,
        "reason": "Medical emergency", "emi_amount": 5000,
        "recovery_start_month": "2026-07", "tenure_months": 10,
    })
    assert r.status_code == 200, r.text
    loan = r.json()
    assert loan["loan_no"].startswith("LN-")
    assert loan["approval_status"] == "pending"
    lid = loan["id"]
    # Approve
    r2 = client.post(f"/hr4/loans/{lid}/approve", json={"decision": "approve"})
    assert r2.status_code == 200
    assert r2.json()["approval_status"] == "approved"
    # Mark paid → creates JV
    r3 = client.post(f"/hr4/loans/{lid}/mark-paid")
    assert r3.status_code == 200, r3.text
    assert r3.json()["payment_status"] == "paid"


def test_loan_zero_amount(client, test_emp):
    r = client.post("/hr4/loans", json={
        "employee_id": test_emp["id"], "loan_amount": 0,
        "reason": "x", "emi_amount": 0, "recovery_start_month": "2026-08",
    })
    assert r.status_code == 400


def test_loan_bad_month(client, test_emp):
    r = client.post("/hr4/loans", json={
        "employee_id": test_emp["id"], "loan_amount": 1000,
        "reason": "x", "emi_amount": 100, "recovery_start_month": "07-2026",
    })
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Reimbursement
# ──────────────────────────────────────────────────────────────────────────────
def test_reimbursement_flow(client, test_emp):
    r = client.post("/hr4/reimbursements", json={
        "employee_id": test_emp["id"],
        "project_code": "PRJ-HR4",
        "expense_type": "travel",
        "amount": 4500.5,
        "description": "Cab from airport",
    })
    assert r.status_code == 200, r.text
    rmb = r.json()
    assert rmb["reimbursement_no"].startswith("RMB-")
    rid = rmb["id"]
    r2 = client.post(f"/hr4/reimbursements/{rid}/approve", json={"decision": "approve"})
    assert r2.status_code == 200
    assert r2.json()["approval_status"] == "approved"
    r3 = client.post(f"/hr4/reimbursements/{rid}/mark-paid")
    assert r3.status_code == 200
    assert r3.json()["payment_status"] == "paid"


def test_reimbursement_zero(client, test_emp):
    r = client.post("/hr4/reimbursements", json={
        "employee_id": test_emp["id"], "expense_type": "x", "amount": 0,
    })
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# 4.  Store recovery
# ──────────────────────────────────────────────────────────────────────────────
def test_store_recovery_flow(client, test_emp):
    r = client.post("/hr4/store-recoveries", json={
        "employee_id": test_emp["id"], "project_code": "PRJ-HR4",
        "item": "Safety harness", "reason": "lost",
        "amount": 2500, "recovery_month": "2026-07",
    })
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r2 = client.post(f"/hr4/store-recoveries/{rid}/approve", json={"decision": "approve"})
    assert r2.status_code == 200
    assert r2.json()["approval_status"] == "approved"


# ──────────────────────────────────────────────────────────────────────────────
# 5.  Payroll posting workflow
# ──────────────────────────────────────────────────────────────────────────────
def test_finance_approve_without_run(client):
    r = client.post("/hr4/payroll/finance-approve",
                    json={"month": "2099-12", "decision": "approve"})
    assert r.status_code == 404


def test_post_without_approval(client):
    r = client.post("/hr4/payroll/post-to-accounts",
                    json={"month": "2099-12", "decision": "approve"})
    assert r.status_code in (400, 404)


# ──────────────────────────────────────────────────────────────────────────────
# 6.  Statutory reports
# ──────────────────────────────────────────────────────────────────────────────
def test_statutory_pf(client):
    r = client.get("/hr4/statutory/pf?month=2026-01")
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j and "totals" in j


def test_statutory_esic(client):
    r = client.get("/hr4/statutory/esic?month=2026-01")
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j and "totals" in j


def test_statutory_tds(client):
    r = client.get("/hr4/statutory/tds?month=2026-01")
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j and "total_tds" in j


# ──────────────────────────────────────────────────────────────────────────────
# 7.  Project cost
# ──────────────────────────────────────────────────────────────────────────────
def test_project_cost(client):
    r = client.get("/hr4/project-cost?month=2026-01")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_chart_of_accounts_seeded(client):
    # Trigger any flow that calls _ensure_coa
    r = client.get("/accounts/chart-of-accounts")
    assert r.status_code == 200
    codes = {x["code"] for x in r.json()}
    # After running loan-paid + reimburse-paid earlier, _ensure_coa should have populated these.
    assert {"5101", "2201", "2202", "2203", "2204"}.issubset(codes), f"missing: {{'5101','2201','2202','2203','2204'}} - {codes}"
