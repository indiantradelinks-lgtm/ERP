"""Iter 131 — Safety Phase 5 · Closure · Reports Center · Dashboard-v2 · Audit Trail."""
import os
import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SAFETY = {"email": "safety@erp.com", "password": "Safety@123"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}
SALES = {"email": "sales@erp.com", "password": "Sales@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed for {creds['email']}: {r.status_code} {r.text[:120]}")
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def project_id(admin_sess):
    r = admin_sess.get(f"{API}/projects", timeout=30)
    assert r.status_code == 200
    projects = r.json()
    if not projects:
        pytest.skip("No projects available")
    return projects[0]["id"]


# ────────── 1. Closure — check / submit / override ─────────────
class TestClosure:
    def test_closure_check(self, admin_sess, project_id):
        r = admin_sess.post(f"{API}/safety/closure/{project_id}/check", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j.get("checklist"), list)
        assert len(j["checklist"]) == 15
        for item in j["checklist"]:
            assert set(item.keys()) >= {"key", "label", "passed"}
        assert j["total"] == 15
        assert "passed" in j
        assert "can_close" in j
        assert "counts" in j
        assert "closure_status" in j

    def test_closure_get(self, admin_sess, project_id):
        r = admin_sess.get(f"{API}/safety/closure/{project_id}", timeout=30)
        assert r.status_code == 200
        assert len(r.json()["checklist"]) == 15

    def test_submit_safety_head_admin(self, admin_sess, project_id):
        r = admin_sess.post(
            f"{API}/safety/closure/{project_id}/submit",
            json={"final_report_url": "https://example.com/report.pdf",
                  "approve_as": "safety_head"}, timeout=30)
        assert r.status_code == 200, r.text
        # Verify via GET
        g = admin_sess.get(f"{API}/safety/closure/{project_id}", timeout=30).json()
        # safety_head_approved should be True now
        by_key = {c["key"]: c["passed"] for c in g["checklist"]}
        assert by_key["safety_head_approved"] is True
        assert by_key["final_report_uploaded"] is True

    def test_submit_project_manager_admin(self, admin_sess, project_id):
        r = admin_sess.post(
            f"{API}/safety/closure/{project_id}/submit",
            json={"approve_as": "project_manager"}, timeout=30)
        assert r.status_code == 200, r.text
        g = admin_sess.get(f"{API}/safety/closure/{project_id}", timeout=30).json()
        by_key = {c["key"]: c["passed"] for c in g["checklist"]}
        assert by_key["project_manager_approved"] is True

    def test_submit_safety_head_denied_for_site_engineer(self, project_id):
        s = _login(SITE_ENG)
        r = s.post(f"{API}/safety/closure/{project_id}/submit",
                   json={"approve_as": "safety_head"}, timeout=30)
        # RBAC blocks site_engineer at safety_closure write gate (403)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"

    def test_override_admin_success(self, admin_sess, project_id):
        r = admin_sess.post(
            f"{API}/safety/closure/{project_id}/override",
            json={"reason": "Client extended timeline, safety wrap-up delayed"},
            timeout=30)
        assert r.status_code == 200, r.text
        g = admin_sess.get(f"{API}/safety/closure/{project_id}", timeout=30).json()
        ov = g.get("override")
        assert ov and ov.get("id") and ov.get("reason") and ov.get("by") and ov.get("at")

    def test_override_short_reason_422(self, admin_sess, project_id):
        r = admin_sess.post(f"{API}/safety/closure/{project_id}/override",
                            json={"reason": "short"}, timeout=30)
        assert r.status_code == 422

    def test_override_denied_for_sales(self, project_id):
        s = _login(SALES)
        r = s.post(f"{API}/safety/closure/{project_id}/override",
                   json={"reason": "trying to override without permission"},
                   timeout=30)
        assert r.status_code == 403


# ────────── 2. Reports catalog / filters / exports ─────────────
class TestReports:
    def test_report_keys(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/keys", timeout=30)
        assert r.status_code == 200
        keys = r.json()
        assert isinstance(keys, list)
        assert len(keys) >= 30, f"expected >=30 report keys, got {len(keys)}"
        assert all("key" in k and "label" in k for k in keys)

    def test_report_hira_json(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/hira", timeout=30)
        assert r.status_code == 200
        j = r.json()
        for f in ("report_key", "label", "filters", "columns", "rows", "count", "generated_at"):
            assert f in j, f"missing field {f}"
        assert j["report_key"] == "hira"

    def test_report_incident_date_filter(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/incident",
                           params={"from": "2020-01-01", "to": "2030-12-31"}, timeout=30)
        assert r.status_code == 200

    def test_report_capa_status_filter(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/capa",
                           params={"status": "closed"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["filters"]["status"] == "closed"

    def test_report_hira_risk_filter(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/hira",
                           params={"risk": "high"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["filters"]["risk"] == "high"

    def test_report_xlsx_export(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/hira",
                           params={"format": "xlsx"}, timeout=60)
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers.get("content-type", "").lower()
        assert r.content[:2] == b"PK"
        assert len(r.content) > 4000, f"xlsx too small: {len(r.content)} bytes"

    def test_report_pdf_export(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/incident",
                           params={"format": "pdf"}, timeout=60)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:7] == b"%PDF-1."
        assert len(r.content) > 1000

    def test_report_unknown_key(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/reports/nonexistent_key", timeout=30)
        assert r.status_code == 404
        assert "Unknown report_key" in r.text

    def test_reports_read_open_to_any_authenticated(self):
        s = _login(SITE_ENG)
        r = s.get(f"{API}/safety/reports/hira", timeout=30)
        assert r.status_code == 200


# ────────── 3. Dashboard-v2 ─────────────
class TestDashboardV2:
    def test_dashboard_v2(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/dashboard-v2", timeout=30)
        assert r.status_code == 200
        j = r.json()
        for f in ("as_of", "kpis", "recent_incidents", "recent_closures"):
            assert f in j
        kpis = j["kpis"]
        assert isinstance(kpis, dict)
        # Review request said 29 keys
        assert len(kpis) == 29, f"expected 29 kpi keys, got {len(kpis)}"
        required = {"total_projects_monitored", "projects_safety_ready", "hira_pending",
                    "work_permits_active", "open_capa", "overdue_capa",
                    "safety_cost_this_month", "projects_pending_closure",
                    "high_risk_activities", "safety_approval_pending"}
        missing = required - set(kpis.keys())
        assert not missing, f"missing kpis: {missing}"


# ────────── 4. Audit trail ─────────────
class TestAuditTrail:
    def test_audit_trail_list(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/audit-trail", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert "count" in j and "rows" in j
        assert isinstance(j["rows"], list)

    def test_audit_trail_filter_kind(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/audit-trail",
                           params={"record_kind": "project_closure"}, timeout=30)
        assert r.status_code == 200
        for row in r.json()["rows"]:
            assert row["record_kind"] == "project_closure"

    def test_audit_trail_kinds_sorted(self, admin_sess):
        r = admin_sess.get(f"{API}/safety/audit-trail/kinds", timeout=30)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        assert arr == sorted(arr)
