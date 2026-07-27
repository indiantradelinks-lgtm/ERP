"""Iter 146 — Bill Generation Request workflow (backend).
Covers POST/GET /api/bill-requests, 4-step approval chain, mark-generated, RBAC.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def project_code(admin_session):
    # Prefer PRJ-2026-0022 which main-agent seeded with offer
    r = admin_session.get(f"{API}/projects")
    assert r.status_code == 200
    projs = r.json()
    codes = [p.get("code") for p in projs if p.get("code")]
    if "PRJ-2026-0022" in codes:
        return "PRJ-2026-0022"
    assert codes, "no projects seeded"
    return codes[0]


# ── Create + validation ─────────────────────────────────────────────────
class TestBillRequestCreate:
    def test_bad_bill_type_400(self, admin_session, project_code):
        r = admin_session.post(f"{API}/bill-requests", json={
            "project_code": project_code, "bill_type": "debit_note", "expected_amount": 1000
        })
        assert r.status_code == 400

    def test_unknown_project_404(self, admin_session):
        r = admin_session.post(f"{API}/bill-requests", json={
            "project_code": "PRJ-NOPE-9999", "bill_type": "running", "expected_amount": 1000
        })
        assert r.status_code == 404

    def test_create_ok(self, admin_session, project_code):
        r = admin_session.post(f"{API}/bill-requests", json={
            "project_code": project_code, "bill_type": "running",
            "period_from": "2026-01-01", "period_to": "2026-01-31",
            "expected_amount": 250000, "remarks": "TEST_iter146 backend RA"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["request_no"].startswith("BR-")
        assert d["status"] == "pending_approval"
        assert d["approval_id"]
        assert d["project_code"] == project_code
        pytest.br = d  # stash


# ── List returns chain + status filter works ────────────────────────────
class TestBillRequestList:
    def test_list_has_chain(self, admin_session):
        r = admin_session.get(f"{API}/bill-requests")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        target = next((x for x in rows if x["id"] == pytest.br["id"]), None)
        assert target, "created request missing from list"
        assert len(target["chain"]) == 4
        labels = [s["label"] for s in target["chain"]]
        assert labels == ["Project Manager", "Department Head", "General Manager", "Director"]
        assert target["current_step"] == 0
        assert target["status"] == "pending_approval"

    def test_status_filter(self, admin_session):
        r = admin_session.get(f"{API}/bill-requests", params={"status": "pending_approval"})
        assert r.status_code == 200
        assert all(x["status"] == "pending_approval" for x in r.json())
        r2 = admin_session.get(f"{API}/bill-requests", params={"status": "bill_generated"})
        assert r2.status_code == 200


# ── Mark-generated pre-approval → 400 ───────────────────────────────────
class TestMarkGeneratedGate:
    def test_400_when_not_approved(self, admin_session):
        # find some existing bill id
        r = admin_session.get(f"{API}/ra-bills")
        bills = r.json()
        bid = bills[0]["id"] if bills else "nope"
        r2 = admin_session.post(
            f"{API}/bill-requests/{pytest.br['id']}/mark-generated",
            json={"bill_id": bid})
        assert r2.status_code == 400


# ── Approve 4 steps as super_admin, then mark-generated ─────────────────
class TestFullApprovalFlow:
    def test_approve_all_4_steps(self, admin_session):
        aid = pytest.br["approval_id"]
        for step in range(4):
            r = admin_session.post(
                f"{API}/approvals/{aid}/action",
                json={"action": "approve", "comment": f"iter146 step {step}"})
            assert r.status_code == 200, r.text
        # Now list should show approved
        r2 = admin_session.get(f"{API}/bill-requests")
        row = next(x for x in r2.json() if x["id"] == pytest.br["id"])
        assert row["status"] == "approved", row

    def test_mark_generated_bad_bill(self, admin_session):
        r = admin_session.post(
            f"{API}/bill-requests/{pytest.br['id']}/mark-generated",
            json={"bill_id": "does-not-exist"})
        assert r.status_code == 404

    def test_mark_generated_ok(self, admin_session, project_code):
        # Create a real bill first
        r = admin_session.post(f"{API}/ra-bills", json={
            "bill_type": "running", "project_code": project_code,
            "client_name": "TEST_iter146_client",
            "items": [{"description": "TEST_iter146 line", "quantity": 1, "unit": "Nos", "rate": 100}],
            "gst_pct": 18,
        })
        assert r.status_code == 200, r.text
        bill = r.json()
        pytest.bill_id = bill["id"]

        r2 = admin_session.post(
            f"{API}/bill-requests/{pytest.br['id']}/mark-generated",
            json={"bill_id": bill["id"]})
        assert r2.status_code == 200, r2.text
        assert r2.json()["bill_number"] == bill["bill_number"]

        # Verify persistence
        r3 = admin_session.get(f"{API}/bill-requests/{pytest.br['id']}")
        assert r3.json()["status"] == "bill_generated"
        assert r3.json()["bill_number"] == bill["bill_number"]


# ── Cleanup ─────────────────────────────────────────────────────────────
def test_cleanup(admin_session):
    bid = getattr(pytest, "bill_id", None)
    if bid:
        r = admin_session.get(f"{API}/ra-bills/{bid}")
        if r.status_code == 200 and r.json().get("status") == "draft":
            admin_session.delete(f"{API}/ra-bills/{bid}")
