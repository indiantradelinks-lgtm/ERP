"""Iter 61 - Projects & Operations Workflow Phase 2, 3, 4 verification.

Covers:
 - Resource Requests CRUD + submit lifecycle (Phase 2)
 - Project Ops Dashboard (Phase 3)
 - Operations Reports - all 13 kinds (Phase 4)
"""
import os
import re
import pytest
import requests


def _api():
    txt = open("/app/frontend/.env").read()
    m = re.search(r"^REACT_APP_BACKEND_URL=(.+)$", txt, re.MULTILINE)
    return os.environ.get("REACT_APP_BACKEND_URL") or m.group(1).strip()


BASE = f"{_api().rstrip('/')}/api"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, f"login failed: {r.text}"
    # Verify httpOnly cookie set
    cookie_names = [c.name for c in s.cookies]
    assert any("token" in c.lower() or "session" in c.lower() or "auth" in c.lower() for c in cookie_names), \
        f"No auth cookie set; got cookies: {cookie_names}"
    return s


@pytest.fixture(scope="module")
def first_project_id(admin_session):
    r = admin_session.get(f"{BASE}/projects")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list) and len(rows) > 0, "Need at least 1 project; preview is empty"
    return rows[0]["id"], rows[0].get("name")


# ---------- Phase 2: Resource Requests ----------
class TestResourceRequests:
    def test_list_resource_requests(self, admin_session):
        r = admin_session.get(f"{BASE}/ops/resource-requests")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_create_then_submit_rr(self, admin_session, first_project_id):
        pid, _pname = first_project_id
        payload = {
            "project_id": pid,
            "resource_type": "consumable",
            "item_name": "TEST_Welding Rods x 50 kg",
            "quantity": 50,
            "unit": "kg",
            "required_date": "2026-07-15",
            "site_location": "Site A",
            "priority": "medium",
            "justification": "Phase 1 welding",
        }
        r = admin_session.post(f"{BASE}/ops/resource-requests", json=payload)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert "rr_no" in doc
        assert re.match(r"^RR-\d{4}-\d+$", doc["rr_no"]), f"Unexpected rr_no: {doc['rr_no']}"
        assert doc["status"] == "draft"
        assert doc["project_id"] == pid
        assert doc["resource_type"] == "consumable"
        assert doc["quantity"] == 50
        rid = doc["id"]

        # GET by id - persistence
        g = admin_session.get(f"{BASE}/ops/resource-requests/{rid}")
        assert g.status_code == 200
        assert g.json()["item_name"] == payload["item_name"]

        # Submit
        s = admin_session.post(f"{BASE}/ops/resource-requests/{rid}/submit")
        assert s.status_code == 200, s.text
        body = s.json()
        assert body.get("ok") is True
        assert "approval_id" in body

        # Verify status changed
        g2 = admin_session.get(f"{BASE}/ops/resource-requests/{rid}")
        assert g2.status_code == 200
        assert g2.json()["status"] in {"pending_approval", "submitted"}, g2.json()

    def test_invalid_resource_type_rejected(self, admin_session, first_project_id):
        pid, _ = first_project_id
        r = admin_session.post(f"{BASE}/ops/resource-requests", json={
            "project_id": pid, "resource_type": "spaceship",
            "item_name": "TEST_invalid", "quantity": 1,
        })
        assert r.status_code == 400

    def test_unknown_project_404(self, admin_session):
        r = admin_session.post(f"{BASE}/ops/resource-requests", json={
            "project_id": "nonexistent-project-id",
            "resource_type": "consumable",
            "item_name": "TEST_bad_project", "quantity": 1,
        })
        assert r.status_code == 404


# ---------- Phase 3: Project Ops Dashboard ----------
class TestProjectDashboard:
    def test_dashboard_shape(self, admin_session, first_project_id):
        pid, _ = first_project_id
        r = admin_session.get(f"{BASE}/ops/projects/{pid}/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ["project", "operations", "resources", "material", "purchase", "financial", "alerts"]:
            assert key in d, f"Missing key '{key}' in dashboard response"
        fin = d["financial"]
        for f in ["contract_value", "billing_done", "total_project_cost", "net_profit",
                   "profit_percentage", "gross_profit", "outstanding", "is_loss", "over_budget"]:
            assert f in fin, f"financial missing field: {f}"

    def test_dashboard_unknown_project_404(self, admin_session):
        r = admin_session.get(f"{BASE}/ops/projects/nonexistent-id/dashboard")
        assert r.status_code == 404


# ---------- Phase 4: Operations Reports ----------
ALL_KINDS = [
    "pl", "loss_making", "outstanding_payments", "by_department", "by_pm",
    "pending_approvals", "store_pending", "resources",
    "material_requests", "purchase_requests", "purchase_cost",
    "manpower", "assets",
]


class TestOpsReports:
    @pytest.mark.parametrize("kind", ALL_KINDS)
    def test_report_kind_returns_200_shape(self, admin_session, kind):
        r = admin_session.get(f"{BASE}/ops/reports", params={"kind": kind})
        assert r.status_code == 200, f"kind={kind} -> {r.status_code} {r.text[:300]}"
        body = r.json()
        assert body.get("kind") == kind
        assert "count" in body
        assert "rows" in body
        assert isinstance(body["rows"], list)
        assert "filters" in body
        assert body["count"] == len(body["rows"])

    def test_invalid_kind_rejected(self, admin_session):
        r = admin_session.get(f"{BASE}/ops/reports", params={"kind": "bogus_kind"})
        assert r.status_code == 400

    def test_pl_rows_have_financial_fields(self, admin_session):
        r = admin_session.get(f"{BASE}/ops/reports", params={"kind": "pl"})
        assert r.status_code == 200
        body = r.json()
        if body["rows"]:
            row = body["rows"][0]
            for f in ["contract_value", "billing_done", "total_project_cost",
                       "net_profit", "profit_percentage"]:
                assert f in row, f"P&L row missing {f}; got keys {list(row.keys())}"
