"""Iteration 2 backend tests: RBAC, permissions, approvals workflow, exports."""
import os
import time
import uuid
import pytest
import requests

def _base():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"')
                        break
    return url.rstrip("/")

BASE = _base()
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"

# unique per-run user so reruns don't collide
RUN_TAG = uuid.uuid4().hex[:6]
HR_EMAIL = f"hr_{RUN_TAG}@test.com"
HR_PASS = "HrTest@123"
STORE_EMAIL = f"store_{RUN_TAG}@test.com"
STORE_PASS = "StoreTest@123"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def hr_session(admin_session):
    # register hr_executive
    r = admin_session.post(f"{API}/auth/register", json={
        "email": HR_EMAIL, "password": HR_PASS, "name": "HR Test", "role": "hr_executive"
    }, timeout=20)
    assert r.status_code in (200, 400), r.text  # 400 if pre-existing
    s = requests.Session()
    rl = s.post(f"{API}/auth/login", json={"email": HR_EMAIL, "password": HR_PASS}, timeout=20)
    assert rl.status_code == 200, rl.text
    return s


@pytest.fixture(scope="session")
def store_session(admin_session):
    r = admin_session.post(f"{API}/auth/register", json={
        "email": STORE_EMAIL, "password": STORE_PASS, "name": "Store Test", "role": "store_incharge"
    }, timeout=20)
    assert r.status_code in (200, 400), r.text
    s = requests.Session()
    rl = s.post(f"{API}/auth/login", json={"email": STORE_EMAIL, "password": STORE_PASS}, timeout=20)
    assert rl.status_code == 200, rl.text
    return s


# ----------------- RBAC -----------------
class TestRBAC:
    def test_hr_can_read_employees(self, hr_session):
        r = hr_session.get(f"{API}/employees", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_hr_cannot_read_journal_entries(self, hr_session):
        r = hr_session.get(f"{API}/journal-entries", timeout=20)
        assert r.status_code == 403

    def test_hr_can_read_clients(self, hr_session):
        r = hr_session.get(f"{API}/clients", timeout=20)
        assert r.status_code == 200

    def test_hr_cannot_write_journal_entries(self, hr_session):
        r = hr_session.post(f"{API}/journal-entries", json={"amount": 1}, timeout=20)
        assert r.status_code == 403

    def test_admin_can_read_journal_entries(self, admin_session):
        r = admin_session.get(f"{API}/journal-entries", timeout=20)
        assert r.status_code == 200

    def test_admin_can_write_journal_entries(self, admin_session):
        r = admin_session.post(f"{API}/journal-entries", json={"name": "TEST_RBAC_JE", "amount": 1}, timeout=20)
        assert r.status_code == 200
        # cleanup
        admin_session.delete(f"{API}/journal-entries/{r.json()['id']}", timeout=20)


class TestPermissions:
    def test_permissions_map_admin(self, admin_session):
        r = admin_session.get(f"{API}/auth/permissions", timeout=20)
        assert r.status_code == 200
        data = r.json()
        for key in ("clients", "journal_entries", "employees", "approvals"):
            assert key in data, f"missing perm key {key}"
            assert all(k in data[key] for k in ("read", "write", "delete"))
        # super_admin sees all true
        assert data["journal_entries"]["read"] is True
        assert data["journal_entries"]["write"] is True

    def test_permissions_map_hr(self, hr_session):
        r = hr_session.get(f"{API}/auth/permissions", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["employees"]["read"] is True
        assert d["employees"]["write"] is True
        assert d["journal_entries"]["read"] is False
        assert d["journal_entries"]["write"] is False
        assert d["clients"]["read"] is True


# ----------------- Approvals -----------------
class TestApprovals:
    def test_chains_catalogue(self, admin_session):
        r = admin_session.get(f"{API}/approvals-config/chains", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("purchase_order", "leave", "capex", "expense", "vendor", "quotation"):
            assert k in d, f"chain missing: {k}"

    def test_list_approvals_has_chain_fields(self, admin_session):
        r = admin_session.get(f"{API}/approvals", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        a = rows[0]
        for k in ("chain", "current_step", "history", "status"):
            assert k in a, f"approval row missing key: {k}"
        assert isinstance(a["chain"], list)

    def test_create_po_approval_autopopulates_chain(self, admin_session):
        payload = {"title": "TEST_PO_APPR", "type": "purchase_order",
                   "reference": "TEST-1", "amount": 1000, "requested_by": "tester"}
        r = admin_session.post(f"{API}/approvals", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        a = r.json()
        assert isinstance(a.get("chain"), list)
        assert len(a["chain"]) == 4
        assert a["current_step"] == 0
        assert a["status"] == "pending"
        # cleanup
        admin_session.delete(f"{API}/approvals/{a['id']}", timeout=20)

    def test_full_approve_workflow(self, admin_session):
        # Create fresh approval to drive
        cr = admin_session.post(f"{API}/approvals", json={
            "title": "TEST_APR_FLOW", "type": "purchase_order",
            "reference": "FLOW-1", "amount": 500, "requested_by": "tester"
        }, timeout=20)
        assert cr.status_code == 200
        aid = cr.json()["id"]
        chain_len = len(cr.json()["chain"])
        try:
            for i in range(chain_len):
                r = admin_session.post(f"{API}/approvals/{aid}/action",
                                       json={"action": "approve", "comment": f"step {i}"}, timeout=20)
                assert r.status_code == 200, r.text
                data = r.json()
                assert len(data["history"]) == i + 1
                if i < chain_len - 1:
                    assert data["status"] == "in_progress"
                else:
                    assert data["status"] == "approved"
        finally:
            admin_session.delete(f"{API}/approvals/{aid}", timeout=20)

    def test_reject_sets_rejected(self, admin_session):
        cr = admin_session.post(f"{API}/approvals", json={
            "title": "TEST_REJ", "type": "purchase_order",
            "reference": "REJ-1", "amount": 500, "requested_by": "tester"
        }, timeout=20)
        aid = cr.json()["id"]
        try:
            r = admin_session.post(f"{API}/approvals/{aid}/action",
                                   json={"action": "reject", "comment": "no"}, timeout=20)
            assert r.status_code == 200
            assert r.json()["status"] == "rejected"
        finally:
            admin_session.delete(f"{API}/approvals/{aid}", timeout=20)

    def test_non_matching_role_403(self, admin_session, hr_session):
        # HR cannot act on PO step (dept_head first). super_admin bypasses.
        cr = admin_session.post(f"{API}/approvals", json={
            "title": "TEST_ROLE_BLOCK", "type": "purchase_order",
            "reference": "BLK-1", "amount": 500, "requested_by": "tester"
        }, timeout=20)
        aid = cr.json()["id"]
        try:
            r = hr_session.post(f"{API}/approvals/{aid}/action",
                                json={"action": "approve", "comment": "x"}, timeout=20)
            assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"
        finally:
            admin_session.delete(f"{API}/approvals/{aid}", timeout=20)


# ----------------- Exports -----------------
class TestExports:
    def test_clients_xlsx(self, admin_session):
        r = admin_session.get(f"{API}/export/clients.xlsx", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert len(r.content) > 100
        # XLSX is a zip; starts with PK
        assert r.content[:2] == b"PK"

    def test_projects_pdf(self, admin_session):
        r = admin_session.get(f"{API}/export/projects.pdf", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_hr_cannot_export_journal_entries(self, hr_session):
        r = hr_session.get(f"{API}/export/journal-entries.xlsx", timeout=30)
        assert r.status_code == 403

    def test_hr_can_export_clients(self, hr_session):
        r = hr_session.get(f"{API}/export/clients.xlsx", timeout=30)
        assert r.status_code == 200
