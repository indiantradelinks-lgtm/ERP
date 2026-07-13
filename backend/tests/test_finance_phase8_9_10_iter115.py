"""Iter 115 — Finance Phase 8 (Alerts & Follow-ups) + Phase 9 (Security) + Phase 10 (Go-Live)."""
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


# ─── PHASE 8 ──────────────────────────────────────────────────────────────
def test_phase8_alerts_feed(s):
    r = s.get(f"{API_URL}/api/finance/alerts/feed", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("total", "critical", "alerts"):
        assert k in d
    assert isinstance(d["alerts"], list)
    if d["alerts"]:
        a = d["alerts"][0]
        for k in ("kind", "severity", "title", "count"):
            assert k in a


def test_phase8_followups_inbox(s):
    r = s.get(f"{API_URL}/api/finance/followups/inbox?days_ahead=7", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "count" in d and "rows" in d
    for row in d["rows"][:5]:
        for k in ("kind", "invoice_id", "due_date", "has_followup"):
            assert k in row
        assert row["kind"] in {"overdue", "due_soon", "partly_paid", "tds_unrec", "retention_due"}


def test_phase8_followups_list(s):
    r = s.get(f"{API_URL}/api/finance/followups", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_phase8_followup_validation(s):
    # invalid status
    r = s.post(f"{API_URL}/api/finance/followups",
               json={"invoice_id": "non-existent-id", "status": "bogus_status"}, timeout=10)
    assert r.status_code in (400, 422)
    # not found
    r = s.post(f"{API_URL}/api/finance/followups",
               json={"invoice_id": "non-existent-id-12345", "status": "pending"}, timeout=10)
    assert r.status_code == 404


def test_phase8_followups_escalate_stale(s):
    r = s.post(f"{API_URL}/api/finance/followups/escalate-stale?stale_days=14", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "escalated" in d and "stale_days" in d


# ─── PHASE 9 ──────────────────────────────────────────────────────────────
def test_phase9_extended_actions(s):
    r = s.get(f"{API_URL}/api/finance/phase9/extended-actions", timeout=10)
    assert r.status_code == 200
    actions = r.json()["actions"]
    # All 13 verbs from the spec are present
    for verb in ("view", "create", "edit", "submit", "approve", "reject", "cancel",
                  "export", "print", "soft_delete", "delete", "reopen", "post_to_ledger"):
        assert verb in actions, f"missing extended action {verb}"
        assert actions[verb]["maps_to"] in ("read", "write", "delete")


def test_phase9_masking_config(s):
    r = s.get(f"{API_URL}/api/finance/phase9/masking-config", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "privileged_roles" in d and "rules" in d
    assert "super_admin" in d["privileged_roles"]
    assert "employees" in d["rules"]
    # salary should be stripped, not masked
    assert d["rules"]["employees"]["salary"] == "strip"
    assert d["rules"]["employees"]["pan"] == "mask"


def test_phase9_tile_visibility(s):
    r = s.get(f"{API_URL}/api/finance/phase9/role-tile-visibility", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "defaults" in d and "config" in d
    assert "ar_summary" in d["defaults"]


def test_phase9_security_summary(s):
    r = s.get(f"{API_URL}/api/finance/phase9/security-summary", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("users", "permissions", "audit", "exports", "period_locks", "approvals",
              "security_events", "masking_resources", "frozen_statuses", "extended_actions"):
        assert k in d
    assert d["users"]["total"] > 0
    assert d["permissions"]["resources"] > 0
    assert d["permissions"]["base_count"] > 0
    assert "super_admin" in d["users"]["by_role"]
    # All 13 extended actions exposed
    assert len(d["extended_actions"]) == 13


def test_phase9_export_log_and_list(s):
    r = s.post(
        f"{API_URL}/api/finance/phase9/export-logs/log",
        json={"activity": "export", "resource": "test_resource", "format": "pdf",
              "record_label": "iter115-test"},
        timeout=10,
    )
    assert r.status_code == 200
    r = s.get(f"{API_URL}/api/finance/phase9/export-logs?resource=test_resource", timeout=10)
    assert r.status_code == 200
    rows = r.json()
    assert any(x.get("record_label") == "iter115-test" for x in rows)


def test_phase9_permission_matrix_csv(s):
    r = s.get(f"{API_URL}/api/finance/phase9/permission-matrix.csv", timeout=15)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "Resource,Action,Roles Allowed" in r.text.splitlines()[0]
    # logging side-effect — last export should be permission_matrix
    r = s.get(f"{API_URL}/api/finance/phase9/export-logs?resource=permission_matrix&limit=1", timeout=10)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1 and rows[0]["resource"] == "permission_matrix"


def test_phase9_check_ledger_deletable(s):
    # Non-existent account
    r = s.post(f"{API_URL}/api/finance/phase9/check-ledger-deletable",
               json={"account_id": "bogus-id-xxx"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["deletable"] is False


# ─── PHASE 10 ─────────────────────────────────────────────────────────────
def test_phase10_migration_coverage(s):
    r = s.get(f"{API_URL}/api/finance/phase10/migration/coverage", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("ledgers", "client_invoices", "vendor_bills", "payments",
              "journal_entries", "vouchers_in_draft", "advances"):
        assert k in d
    assert d["ledgers"]["total"] > 0


def test_phase10_reconciliation_summary(s):
    r = s.get(f"{API_URL}/api/finance/phase10/reconciliation/summary", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("ar", "ap", "cash_bank_balance", "gst", "tds", "advances", "payroll_payable"):
        assert k in d
    for k in ("total", "received", "outstanding"):
        assert k in d["ar"]
    for k in ("total", "paid", "outstanding"):
        assert k in d["ap"]


def test_phase10_ledger_tie_out(s):
    r = s.get(f"{API_URL}/api/finance/phase10/reconciliation/ledger-tie-out", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("total_debit", "total_credit", "difference", "balanced"):
        assert k in d


def test_phase10_negative_tests(s):
    r = s.get(f"{API_URL}/api/finance/phase10/negative-tests/run", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "tests" in d and "passed" in d and "failed" in d
    keys = {t["key"] for t in d["tests"]}
    # The documented negative tests must be present
    for required in (
        "unbalanced_vouchers", "duplicate_invoices", "payment_without_approval",
        "bills_without_vendor", "invoices_without_client", "posting_without_ledger",
        "backdated_into_locked", "tax_mismatch", "inactive_ledger_with_txn",
    ):
        assert required in keys, f"missing negative test {required}"


def test_phase10_go_live_checklist(s):
    r = s.get(f"{API_URL}/api/finance/phase10/go-live/checklist", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("score", "ready_for_go_live", "items", "reconciliation", "coverage", "negative_tests"):
        assert k in d
    assert 0 <= d["score"] <= 100
    assert isinstance(d["items"], list) and len(d["items"]) >= 5


def test_phase10_pending_approvals(s):
    r = s.get(f"{API_URL}/api/finance/phase10/go-live/pending-approvals", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "count" in d and "rows" in d


# ─── NEGATIVE — non-privileged user blocked from masking config / matrix ──
def test_phase9_unauthorized_role_blocked():
    """A read-only/non-role-register user must get 403 on protected endpoints."""
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json={"email": "sales@erp.com", "password": "Sales@123"}, timeout=10)
    if r.status_code != 200:
        pytest.skip("sales user not available in this env")
    r = sess.get(f"{API_URL}/api/finance/phase9/masking-config", timeout=10)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
