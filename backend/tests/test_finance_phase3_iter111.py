"""Iter 111 — Finance Phase 3: Store/Inventory/Procurement integration.

Backend: /api/finance/budget/check + /reports/* + /material-return/post-reversal
"""
import os
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


@pytest.fixture(scope="module")
def project(s):
    rows = s.get(f"{API_URL}/api/projects", timeout=10).json()
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    if not rows:
        pytest.skip("No projects")
    return rows[0]


# ─── Budget check ────────────────────────────────────────────────────────
def test_budget_check_returns_full_payload(s, project):
    r = s.get(f"{API_URL}/api/finance/budget/check",
              params={"project_id": project["id"], "amount": 100000}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("project_id", "budget_value", "committed_pos_sos", "spent_approved_bills",
              "pending_bills", "available", "requested_amount", "available_after_request"):
        assert k in d
    assert d["requested_amount"] == 100000


def test_budget_check_404_unknown_project(s):
    r = s.get(f"{API_URL}/api/finance/budget/check",
              params={"project_id": "non-existent", "amount": 0}, timeout=10)
    assert r.status_code == 404


# ─── PO commitment report ────────────────────────────────────────────────
def test_po_commitment_report(s):
    r = s.get(f"{API_URL}/api/finance/reports/po-commitment", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "count" in d and "rows" in d and "total_open_commitment" in d
    # Every row should have open_commitment > 0
    for row in d["rows"]:
        assert row["open_commitment"] > 0
        assert row["po_total"] >= row["received_value"]


# ─── GRN-not-billed ──────────────────────────────────────────────────────
def test_grn_not_billed_report(s):
    r = s.get(f"{API_URL}/api/finance/reports/grn-not-billed",
              params={"days_old": 0}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "count" in d and "rows" in d and "total_open_grni" in d
    # Each row should have a severity
    for row in d["rows"]:
        assert row["severity"] in ("critical", "warning", "info")


# ─── Bill-without-GRN ────────────────────────────────────────────────────
def test_bill_without_grn_report(s):
    r = s.get(f"{API_URL}/api/finance/reports/bill-without-grn", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "count" in d and "audit_risk_count" in d and "rows" in d
    assert d["audit_risk_count"] <= d["count"]


# ─── Project procurement cost rollup ─────────────────────────────────────
def test_project_procurement_rollup(s):
    r = s.get(f"{API_URL}/api/finance/reports/project-procurement-cost", timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d
    for row in d["rows"]:
        for k in ("project_id", "budget", "po_committed_open", "approved_bills", "pending_bills"):
            assert k in row


# ─── Material return → reverse JE ────────────────────────────────────────
def test_material_return_reversal_posts_je(s, project):
    """The reversal endpoint creates a balanced JE (idempotent on source_event)."""
    r = s.post(f"{API_URL}/api/finance/material-return/post-reversal", json={
        "project_id": project["id"], "amount": 12500.0,
        "item_name": "Pipe MS 50mm", "return_date": "2026-02-15",
        "notes": "Returned 10 mt from site",
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount"] == 12500.0
    assert d["je_number"]
    # JE must balance
    jes = s.get(f"{API_URL}/api/accounts/journal-entries", timeout=10).json()
    jes = jes if isinstance(jes, list) else jes.get("data", [])
    found = next((j for j in jes if j.get("je_number") == d["je_number"]), None)
    assert found, f"JE {d['je_number']} missing"
    assert found["total_debit"] == found["total_credit"] == 12500.0
    assert found["source_module"] == "material_return"
    # Lines: DR 1300 / CR 5100
    codes = {ln["account_code"] for ln in found["lines"]}
    assert "1300" in codes and "5100" in codes


def test_material_return_rejects_zero_amount(s, project):
    r = s.post(f"{API_URL}/api/finance/material-return/post-reversal", json={
        "project_id": project["id"], "amount": 0,
    }, timeout=10)
    assert r.status_code == 400
