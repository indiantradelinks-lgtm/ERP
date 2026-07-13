"""HR Phase 5 tests — Final dashboard, Reports Center, Audit Trail, Integration
Review, Final Controls."""
from __future__ import annotations

import os
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
    assert r.status_code == 200
    yield s
    s.close()


def G(client, path):
    return client.get(f"{BASE}{path}", timeout=30)


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────
def test_dashboard_30_cards(client):
    r = G(client, "/hr5/dashboard")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total_cards"] == 30
    keys = {c["key"] for c in j["cards"]}
    expected = {
        "total_active_employees", "total_active_workers", "available_manpower",
        "deployed_manpower", "project_wise", "skill_wise", "manpower_shortage",
        "attendance_pending", "today_present", "today_absent",
        "ot_pending", "leave_pending", "payroll_pending",
        "salary_payable", "pf_payable", "esic_payable", "tds_payable",
        "docs_missing", "docs_expiring", "medical_expiring", "training_expiring",
        "ppe_clearance_pending", "mr_open", "fnf_pending",
        "recent_joining", "recent_exits", "blocked_deployment",
        "project_cost_month", "mob_pending", "demob_pending",
    }
    assert expected.issubset(keys), f"Missing keys: {expected - keys}"
    # All cards must have label, value, severity, link
    for c in j["cards"]:
        assert "label" in c and "value" in c and "severity" in c


# ──────────────────────────────────────────────────────────────────────────────
# Reports center
# ──────────────────────────────────────────────────────────────────────────────
def test_reports_catalog(client):
    r = G(client, "/hr5/reports/catalog")
    assert r.status_code == 200
    j = r.json()
    assert len(j) >= 30
    cats = {c["category"] for c in j}
    assert cats == {"employee", "compliance", "attendance",
                    "payroll", "statutory", "clearance", "management"}


@pytest.mark.parametrize("key", [
    "employee_master", "active_employees", "by_department", "by_designation",
    "missing_documents", "training_expiry", "safety_induction_pending",
    "monthly_attendance", "overtime", "salary_register", "payroll_summary",
    "project_cost", "advance_recovery", "reimbursement",
    "pf", "esic", "tds",
    "ppe_pending", "fnf_pending",
    "manpower_availability", "manpower_shortage", "deployment", "hr_cost",
])
def test_each_report_runs(client, key):
    r = G(client, f"/hr5/reports/{key}?month=2026-06")
    assert r.status_code == 200, f"{key}: {r.text[:200]}"
    j = r.json()
    assert j["key"] == key
    assert "rows" in j
    assert "label" in j


def test_unknown_report_404(client):
    r = G(client, "/hr5/reports/nonexistent_report")
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Audit trail
# ──────────────────────────────────────────────────────────────────────────────
def test_audit_trail(client):
    r = G(client, "/hr5/audit-trail?limit=50")
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j
    assert isinstance(j["rows"], list)


def test_audit_trail_filter_by_resource(client):
    r = G(client, "/hr5/audit-trail?resource=attendance")
    assert r.status_code == 200
    j = r.json()
    for row in j["rows"]:
        # When filtered, resource should be attendance OR source should be hr_attendance_audit
        assert row.get("resource") == "attendance"


# ──────────────────────────────────────────────────────────────────────────────
# Integration review
# ──────────────────────────────────────────────────────────────────────────────
def test_integration_review(client):
    r = G(client, "/hr5/integration-review")
    assert r.status_code == 200
    j = r.json()
    modules = {c["module"] for c in j["checks"]}
    expected = {"Sales", "Projects/Operations", "Accounts", "Finance",
                "Store/Inventory", "Safety", "Logistics", "HR",
                "Procurement/Vendors"}
    assert expected.issubset(modules), f"missing: {expected - modules}"
    assert "health_pct" in j and 0 <= j["health_pct"] <= 100


# ──────────────────────────────────────────────────────────────────────────────
# Preflight controls
# ──────────────────────────────────────────────────────────────────────────────
def test_preflight_controls(client):
    r = G(client, "/hr5/controls/preflight?month=2026-06")
    assert r.status_code == 200
    j = r.json()
    keys = {c["key"] for c in j["controls"]}
    expected = {
        "payroll_requires_locked_attendance", "deployment_compliance",
        "finance_approval_required", "exit_requires_clearance",
        "fnf_requires_approval", "pii_masking_enabled", "audit_trail_active",
    }
    assert expected.issubset(keys)
