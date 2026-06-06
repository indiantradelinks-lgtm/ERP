"""Phase B (Sales pipeline) backend regression.

Covers:
- POST /api/enquiries auto-numbering ENQ-YYYY-#### + initial status='open' + status_history
- POST /api/enquiries/{id}/status (allowed transitions, forbidden 400, terminal won/lost)
- POST /api/enquiries/{id}/convert (only when 'won', creates Order ORD-YYYY-#### + optional Project PRJ-YYYY-####; double convert → 409)
- GET /api/orders shape (order_no/customer/contract_value/project_code/enquiry_no)
- POST /api/quotations/{id}/revise (revision_no, parent_id, root_id, quote_number+" Rev{n}", status='draft')
- GET /api/quotations/{id}/revisions sorted ASC by revision_no
- next_sequence is sequential within a year
- Phase A regression: admin endpoints + dashboard still 200
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="session")
def created():
    """Track ids created during tests so we can assert chain & cleanup-ish."""
    return {"enquiries": [], "orders": [], "quotations": [], "revisions": []}


# ---------- Health / regression baseline ----------
class TestRegressionPhaseA:
    def test_auth_me(self, admin_client):
        r = admin_client.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json().get("email") == "admin@erp.com"

    def test_dashboard_stats(self, admin_client):
        r = admin_client.get(f"{API}/dashboard/summary")
        assert r.status_code == 200

    def test_admin_approval_matrix(self, admin_client):
        r = admin_client.get(f"{API}/admin/approval-matrix")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Auto-numbering / Enquiry create ----------
class TestEnquiryCreate:
    NUM_RE = re.compile(r"^ENQ-\d{4}-\d{4}$")

    def test_create_enquiry_auto_number(self, admin_client, created):
        payload = {
            "customer": "TEST_PhaseB Customer A",
            "contact_person": "Alice",
            "service_type": "sales",
            "scope": "Phase B test enquiry",
            "expected_value": 100000,
        }
        r = admin_client.post(f"{API}/enquiries", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert self.NUM_RE.match(data["enquiry_no"]), f"bad enquiry_no: {data['enquiry_no']}"
        assert data["status"] == "open"
        assert isinstance(data.get("status_history"), list) and len(data["status_history"]) == 1
        assert data["status_history"][0]["status"] == "open"
        created["enquiries"].append(data)

    def test_create_second_enquiry_sequence_increments(self, admin_client, created):
        first_no = created["enquiries"][0]["enquiry_no"]
        r = admin_client.post(f"{API}/enquiries", json={"customer": "TEST_PhaseB Customer B", "service_type": "services"})
        assert r.status_code == 200
        second = r.json()
        assert self.NUM_RE.match(second["enquiry_no"])
        # extract last 4 digits
        n1 = int(first_no.split("-")[-1])
        n2 = int(second["enquiry_no"].split("-")[-1])
        assert n2 == n1 + 1, f"sequence not incrementing: {first_no} -> {second['enquiry_no']}"
        created["enquiries"].append(second)

    def test_invalid_service_type_400(self, admin_client):
        r = admin_client.post(f"{API}/enquiries", json={"customer": "X", "service_type": "garbage"})
        assert r.status_code == 400


# ---------- Status transitions ----------
class TestEnquiryStatusTransitions:
    def test_open_to_under_review_allowed(self, admin_client, created):
        eid = created["enquiries"][0]["id"]
        r = admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "under_review"})
        assert r.status_code == 200
        assert r.json()["status"] == "under_review"
        assert len(r.json()["status_history"]) == 2

    def test_under_review_to_open_forbidden(self, admin_client, created):
        eid = created["enquiries"][0]["id"]
        r = admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "open"})
        assert r.status_code == 400

    def test_invalid_status_value_400(self, admin_client, created):
        eid = created["enquiries"][0]["id"]
        r = admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "completed"})
        assert r.status_code == 400

    def test_chain_to_won(self, admin_client, created):
        eid = created["enquiries"][0]["id"]
        # under_review -> submitted -> negotiation -> won
        for nxt in ["submitted", "negotiation", "won"]:
            r = admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": nxt})
            assert r.status_code == 200, f"{nxt}: {r.text}"
        r = admin_client.get(f"{API}/enquiries/{eid}")
        assert r.json()["status"] == "won"

    def test_won_to_anything_forbidden(self, admin_client, created):
        eid = created["enquiries"][0]["id"]
        r = admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "open"})
        assert r.status_code == 400

    def test_lost_terminal(self, admin_client, created):
        # take second enquiry to lost then try to revive
        eid = created["enquiries"][1]["id"]
        admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "under_review"})
        admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "submitted"})
        r = admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "lost"})
        assert r.status_code == 200
        r2 = admin_client.post(f"{API}/enquiries/{eid}/status", json={"status": "won"})
        assert r2.status_code == 400


# ---------- Convert ----------
class TestEnquiryConvert:
    ORD_RE = re.compile(r"^ORD-\d{4}-\d{4}$")
    PRJ_RE = re.compile(r"^PRJ-\d{4}-\d{4}$")

    def test_convert_requires_won(self, admin_client, created):
        # second enquiry is now 'lost', try to convert
        eid = created["enquiries"][1]["id"]
        r = admin_client.post(f"{API}/enquiries/{eid}/convert", json={})
        assert r.status_code == 400

    def test_convert_won_creates_order_and_project(self, admin_client, created):
        eid = created["enquiries"][0]["id"]
        payload = {"customer_po": "PO-TEST-001", "contract_value": 150000, "payment_terms": "Net 30", "create_project": True}
        r = admin_client.post(f"{API}/enquiries/{eid}/convert", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        order = body["order"]
        project = body["project"]
        assert self.ORD_RE.match(order["order_no"]), order["order_no"]
        assert self.PRJ_RE.match(project["code"]), project["code"]
        assert order["customer"] == "TEST_PhaseB Customer A"
        assert order["contract_value"] == 150000
        assert order["enquiry_id"] == eid
        assert order["project_code"] == project["code"]
        created["orders"].append(order)

        # enquiry now carries order_id + project_code
        enq = admin_client.get(f"{API}/enquiries/{eid}").json()
        assert enq["order_id"] == order["id"]
        assert enq["order_no"] == order["order_no"]
        assert enq["project_code"] == project["code"]

    def test_double_convert_returns_409(self, admin_client, created):
        eid = created["enquiries"][0]["id"]
        r = admin_client.post(f"{API}/enquiries/{eid}/convert", json={})
        assert r.status_code == 409
        assert "already" in (r.json().get("detail") or "").lower()


# ---------- Orders list ----------
class TestOrders:
    def test_list_orders_includes_converted(self, admin_client, created):
        r = admin_client.get(f"{API}/orders")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 1
        target_id = created["orders"][0]["id"]
        match = next((o for o in rows if o["id"] == target_id), None)
        assert match is not None
        for key in ("order_no", "customer", "contract_value", "project_code", "enquiry_no"):
            assert key in match, f"missing {key} in order row"
        assert match["customer"] == "TEST_PhaseB Customer A"


# ---------- Quotation revisions ----------
class TestQuotationRevisions:
    def test_create_quotation_then_revise(self, admin_client, created):
        # create base quotation via crud_router
        payload = {
            "quote_number": "QTN-PHASEB-1",
            "client": "TEST_PhaseB Customer A",
            "project": "Demo",
            "date": "2026-01-15",
            "valid_until": "2026-02-15",
            "total": 50000,
            "status": "draft",
        }
        r = admin_client.post(f"{API}/quotations", json=payload)
        assert r.status_code == 200, r.text
        base = r.json()
        created["quotations"].append(base)

        # Revise once
        r1 = admin_client.post(f"{API}/quotations/{base['id']}/revise")
        assert r1.status_code == 200, r1.text
        rev1 = r1.json()
        assert rev1["revision_no"] == 1
        assert rev1["parent_id"] == base["id"]
        assert rev1["root_id"] == base["id"]
        assert rev1["quote_number"].endswith(" Rev1")
        assert rev1["status"] == "draft"
        assert rev1["id"] != base["id"]
        created["revisions"].append(rev1)

        # Revise again — should produce Rev2 with same root_id
        r2 = admin_client.post(f"{API}/quotations/{rev1['id']}/revise")
        assert r2.status_code == 200
        rev2 = r2.json()
        assert rev2["revision_no"] == 2
        assert rev2["root_id"] == base["id"]
        assert rev2["parent_id"] == rev1["id"]
        assert rev2["quote_number"].endswith(" Rev2")
        # Should not double-suffix
        assert "Rev1 Rev" not in rev2["quote_number"]
        created["revisions"].append(rev2)

    def test_list_revisions_sorted_asc(self, admin_client, created):
        base_id = created["quotations"][0]["id"]
        r = admin_client.get(f"{API}/quotations/{base_id}/revisions")
        assert r.status_code == 200
        chain = r.json()
        assert len(chain) >= 3  # base + Rev1 + Rev2
        revs = [c.get("revision_no") or 0 for c in chain]
        assert revs == sorted(revs), f"chain not sorted asc: {revs}"
        # All share same root_id chain (root_id absent on base is ok)
        for c in chain:
            rid = c.get("root_id") or c.get("id")
            assert rid == base_id

    def test_revise_unknown_id_404(self, admin_client):
        r = admin_client.post(f"{API}/quotations/does-not-exist/revise")
        assert r.status_code == 404


# ---------- Cleanup ----------
@pytest.fixture(scope="session", autouse=True)
def _cleanup(admin_client, created):
    yield
    # Best-effort delete of test-created enquiries & quotations.
    for q in created.get("revisions", []) + created.get("quotations", []):
        try:
            admin_client.delete(f"{API}/quotations/{q['id']}")
        except Exception:
            pass
    for e in created.get("enquiries", []):
        try:
            admin_client.delete(f"{API}/enquiries/{e['id']}")
        except Exception:
            pass
