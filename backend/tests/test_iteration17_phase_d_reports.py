"""Iteration 17 — Phase D Sales Reports + Global Search + new enquiry schema.

Endpoints covered:
  GET /api/sales/reports/monthly
  GET /api/sales/reports/by-client
  GET /api/sales/reports/by-service
  GET /api/sales/reports/won-lost
  GET /api/sales/reports/deadline-tracker
  GET /api/sales/search?q=
  POST /api/enquiries  (new schema + auto-quote)
  GET  /api/sales/enquiry-pulse
  RBAC: sales_executive can read, project_manager (unrelated) should be denied.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
TS = int(time.time())


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return s


# ------- Fixtures -------
@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def sales():
    return _login("sales@erp.com", "Sales@123")


@pytest.fixture(scope="module")
def pm():
    # project_manager is unrelated to quotations:read -> good RBAC negative
    return _login("test_pm@erp.com", "PM@12345")


# ------- Phase D Reports -------
class TestSalesReports:
    def test_monthly(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/reports/monthly", timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert isinstance(data, list)
        if data:
            row = data[0]
            for k in ("month", "total", "won", "lost", "pipeline_value", "won_value"):
                assert k in row, f"missing {k} in monthly row"

    def test_by_client(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/reports/by-client", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            row = data[0]
            for k in ("customer", "total", "won", "lost", "win_ratio_pct", "pipeline_value", "won_value"):
                assert k in row, f"missing {k} in by-client row"

    def test_by_service(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/reports/by-service", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # may be empty if no service_categories yet - just verify schema if present
        if data:
            for k in ("service", "total", "won", "lost", "win_ratio_pct", "pipeline_value", "won_value"):
                assert k in data[0]

    def test_won_lost(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/reports/won-lost", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("won", "lost", "win_ratio_pct", "avg_cycle_days", "as_of"):
            assert k in d, f"missing {k}"
        assert isinstance(d["won"], int)
        assert isinstance(d["lost"], int)

    def test_deadline_tracker(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/reports/deadline-tracker", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        for row in rows:
            assert row.get("bucket") in {"overdue", "due_soon", "upcoming"}, f"bad bucket {row.get('bucket')}"

    def test_global_search_returns_buckets(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/search", params={"q": "ENQ"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("enquiries", "quotations", "orders"):
            assert k in d
            assert isinstance(d[k], list)

    def test_global_search_empty_q(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/search", params={"q": ""}, timeout=15)
        # empty -> still 200 with empty buckets (no validation error)
        assert r.status_code == 200
        d = r.json()
        assert d == {"enquiries": [], "quotations": [], "orders": []}


# ------- RBAC -------
class TestRBAC:
    def test_sales_exec_can_read_monthly(self, sales):
        r = sales.get(f"{BASE_URL}/api/sales/reports/monthly", timeout=15)
        assert r.status_code == 200, f"sales_executive denied: {r.status_code} {r.text[:200]}"

    def test_sales_exec_can_read_by_client(self, sales):
        r = sales.get(f"{BASE_URL}/api/sales/reports/by-client", timeout=15)
        assert r.status_code == 200

    def test_sales_exec_can_read_won_lost(self, sales):
        r = sales.get(f"{BASE_URL}/api/sales/reports/won-lost", timeout=15)
        assert r.status_code == 200

    def test_sales_exec_can_search(self, sales):
        r = sales.get(f"{BASE_URL}/api/sales/search", params={"q": "TEST"}, timeout=15)
        assert r.status_code == 200

    def test_unrelated_role_denied(self, pm):
        # project_manager does not have quotations:read -> should be 403
        r = pm.get(f"{BASE_URL}/api/sales/reports/monthly", timeout=15)
        assert r.status_code in (401, 403), f"expected denial, got {r.status_code} {r.text[:200]}"


# ------- Enquiry create with new schema + auto-quote -------
class TestEnquiryNewSchemaAutoQuote:
    created_ids = []

    def test_create_with_new_schema_creates_quote(self, sales):
        payload = {
            "customer": f"TEST_PhaseD_{TS}",
            "contact_person": "Test Contact",
            "rfq_type": ["supply", "service"],
            "service_categories": ["scaffolding", "painting"],
            "scope_of_work": "Phase D regression test scope",
            "submission_deadline": "2026-03-01",
            "priority": "high",
            "expected_value": 250000,
        }
        r = sales.post(f"{BASE_URL}/api/enquiries", json=payload, timeout=20)
        assert r.status_code == 200, f"create enquiry failed: {r.status_code} {r.text[:300]}"
        d = r.json()
        assert d.get("enquiry_no", "").startswith("ENQ-")
        assert d.get("quotation_id"), "auto-quote not linked"
        assert d.get("quotation_no", "").startswith("QTN-"), f"bad quote no: {d.get('quotation_no')}"
        assert d["rfq_type"] == ["supply", "service"]
        assert d["service_categories"] == ["scaffolding", "painting"]
        self.__class__.created_ids.append(d["id"])

    def test_created_enquiry_appears_in_global_search(self, sales):
        # Allow brief commit time
        time.sleep(0.5)
        r = sales.get(f"{BASE_URL}/api/sales/search", params={"q": f"TEST_PhaseD_{TS}"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert any(e.get("customer", "").startswith(f"TEST_PhaseD_{TS}") for e in d["enquiries"]), \
            f"new enquiry not in search results: {d}"
        # Auto-quote should also be searchable by client name
        assert any(q.get("client", "").startswith(f"TEST_PhaseD_{TS}") for q in d["quotations"]), \
            f"auto-quote not in search results: {d}"

    def test_invalid_rfq_type_rejected(self, sales):
        bad = {
            "customer": f"TEST_BadRFQ_{TS}",
            "rfq_type": ["bogus_value"],
        }
        r = sales.post(f"{BASE_URL}/api/enquiries", json=bad, timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}"

    def test_missing_customer_rejected(self, sales):
        r = sales.post(f"{BASE_URL}/api/enquiries", json={"rfq_type": ["supply"]}, timeout=15)
        assert r.status_code == 400


# ------- Enquiry Pulse dashboard -------
class TestEnquiryPulse:
    def test_pulse_returns_full_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/sales/enquiry-pulse", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "kpis" in d and "by_service" in d and "by_rfq_type" in d
        kpis = d["kpis"]
        for k in ("total", "open", "won", "lost", "pending_quotations", "deadline_approaching"):
            assert k in kpis, f"missing kpi {k}"
        assert isinstance(d["by_service"], list)
        assert isinstance(d["by_rfq_type"], list)


# ------- Teardown -------
def teardown_module(_):
    """Best-effort cleanup of TEST_PhaseD_ enquiries created above."""
    try:
        s = _login("admin@erp.com", "Admin@123")
        rows = s.get(f"{BASE_URL}/api/enquiries", timeout=15).json()
        for e in rows:
            if (e.get("customer") or "").startswith(f"TEST_PhaseD_{TS}") or \
               (e.get("customer") or "").startswith(f"TEST_BadRFQ_{TS}"):
                s.delete(f"{BASE_URL}/api/enquiries/{e['id']}", timeout=10)
    except Exception:
        pass
