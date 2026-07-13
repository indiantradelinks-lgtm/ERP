"""Phase C/D/E/F regression suite — Store transactions, Safety, HR, Vendor portal."""
import os
import re
import time
import pytest
import requests

def _read_env(key):
    # Load from frontend/.env (matches user-facing URL)
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.environ.get(key)


BASE_URL = (_read_env("REACT_APP_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}


def _login(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login {creds['email']} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def site_engineer(admin):
    # Try login first; if missing, create via /api/auth/register
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=SITE_ENG, timeout=20)
    if r.status_code != 200:
        reg = admin.post(f"{API}/auth/register", json={
            "email": SITE_ENG["email"], "password": SITE_ENG["password"],
            "name": "TEST Site Engineer", "role": "site_engineer", "department": "Operations"
        })
        assert reg.status_code in (200, 201, 409), f"register failed: {reg.status_code} {reg.text}"
        r = s.post(f"{API}/auth/login", json=SITE_ENG, timeout=20)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="session")
def inv_item(admin):
    payload = {
        "name": "TEST_PhaseC Bolt M10", "sku": "TESTBOLT-M10",
        "barcode": "BC-TESTBOLT-M10", "unit": "pc",
        "quantity": 100, "unit_price": 5, "issue_threshold": 50,
        "category": "fasteners",
    }
    r = admin.post(f"{API}/inventory", json=payload)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    yield data
    admin.delete(f"{API}/inventory/{data['id']}")


# ===== Phase C — Store transactions =====
class TestPhaseCStore:
    def test_inward_increases_qty_and_returns_balance(self, admin, inv_item):
        before = inv_item["quantity"]
        r = admin.post(f"{API}/store/transactions", json={
            "txn_type": "inward", "item_id": inv_item["id"], "quantity": 50,
            "received_from": "TEST_SUPP", "note": "TEST inward"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "posted"
        assert d["balance_after"] == before + 50
        assert re.match(r"^INV-\d{4}-\d{4}$", d["txn_no"]), d["txn_no"]
        # Confirm inventory updated
        g = admin.get(f"{API}/inventory/{inv_item['id']}").json()
        assert g["quantity"] == before + 50

    def test_outward_above_threshold_creates_approval(self, admin, inv_item):
        # current qty 150; threshold 50; outward 60 → awaiting_approval
        cur = admin.get(f"{API}/inventory/{inv_item['id']}").json()["quantity"]
        r = admin.post(f"{API}/store/transactions", json={
            "txn_type": "outward", "item_id": inv_item["id"], "quantity": 60,
            "issued_to": "TEST_PRJ", "note": "TEST outward big"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "awaiting_approval"
        assert d.get("approval_id")
        # Inventory NOT decremented
        g = admin.get(f"{API}/inventory/{inv_item['id']}").json()
        assert g["quantity"] == cur

    def test_overdraft_returns_400(self, admin, inv_item):
        r = admin.post(f"{API}/store/transactions", json={
            "txn_type": "outward", "item_id": inv_item["id"], "quantity": 99999
        })
        assert r.status_code == 400

    def test_scrap_below_threshold_decrements(self, admin, inv_item):
        cur = admin.get(f"{API}/inventory/{inv_item['id']}").json()["quantity"]
        r = admin.post(f"{API}/store/transactions", json={
            "txn_type": "scrap", "item_id": inv_item["id"], "quantity": 5,
            "note": "TEST scrap"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "posted"
        assert d["balance_after"] == cur - 5
        g = admin.get(f"{API}/inventory/{inv_item['id']}").json()
        assert g["quantity"] == cur - 5

    def test_lookup_by_sku_and_barcode_and_id(self, admin, inv_item):
        r1 = admin.get(f"{API}/store/lookup/{inv_item['sku']}")
        assert r1.status_code == 200 and r1.json()["id"] == inv_item["id"]
        r2 = admin.get(f"{API}/store/lookup/{inv_item['barcode']}")
        assert r2.status_code == 200 and r2.json()["id"] == inv_item["id"]
        r3 = admin.get(f"{API}/store/lookup/{inv_item['id']}")
        assert r3.status_code == 200
        r4 = admin.get(f"{API}/store/lookup/NOPE-DOES-NOT-EXIST-XYZ")
        assert r4.status_code == 404

    def test_list_filters(self, admin, inv_item):
        r = admin.get(f"{API}/store/transactions", params={
            "item_id": inv_item["id"], "txn_type": "outward"
        })
        assert r.status_code == 200
        rows = r.json()
        assert all(x["item_id"] == inv_item["id"] and x["txn_type"] == "outward" for x in rows)


# ===== Phase D — Safety pack =====
SAFETY_RESOURCES = [
    ("ppe-issuance", {"employee": "TEST_E1", "item": "Helmet", "qty": 1, "issue_date": "2026-01-01"}),
    ("ptws", {"title": "TEST PTW", "permit_type": "hot_work", "site": "Site-A", "valid_from": "2026-01-01", "valid_to": "2026-01-02"}),
    ("safety-trainings", {"title": "TEST Safety Training", "trainer": "T", "date": "2026-01-01", "attendees": []}),
    ("toolbox-talks", {"title": "TEST TBT", "topic": "PPE", "date": "2026-01-01", "conducted_by": "Foreman"}),
]


@pytest.mark.parametrize("path,payload", SAFETY_RESOURCES)
class TestPhaseDSafety:
    def test_crud_super_admin(self, admin, path, payload):
        r = admin.post(f"{API}/{path}", json=payload)
        assert r.status_code in (200, 201), f"{path} create: {r.status_code} {r.text}"
        rid = r.json()["id"]
        g = admin.get(f"{API}/{path}")
        assert g.status_code == 200 and any(x["id"] == rid for x in g.json())
        u = admin.put(f"{API}/{path}/{rid}", json={"note": "TEST update"})
        assert u.status_code == 200, u.text
        d = admin.delete(f"{API}/{path}/{rid}")
        assert d.status_code in (200, 204)

    def test_site_engineer_can_read_but_not_delete(self, admin, site_engineer, path, payload):
        # admin seeds
        r = admin.post(f"{API}/{path}", json=payload)
        assert r.status_code in (200, 201), r.text
        rid = r.json()["id"]
        try:
            g = site_engineer.get(f"{API}/{path}")
            assert g.status_code == 200, f"site eng read denied on {path}: {g.status_code}"
            d = site_engineer.delete(f"{API}/{path}/{rid}")
            assert d.status_code == 403, f"site_engineer should NOT delete {path}, got {d.status_code}"
        finally:
            admin.delete(f"{API}/{path}/{rid}")


# ===== Phase E — HR pack =====
HR_RESOURCES = [
    ("recruitment-requests", {"position": "TEST Engineer", "department": "Ops", "vacancies": 1, "status": "open"}),
    ("candidates", {"name": "TEST Cand", "email": "test_cand@example.com", "phone": "+10000000", "position": "Engineer"}),
    ("deployments", {"employee": "TEST_E1", "project": "TEST_P", "from_date": "2026-01-01", "to_date": "2026-01-31"}),
    ("accommodations", {"name": "TEST Accom", "type": "camp", "location": "Site-A", "capacity": 10}),
    ("overtime", {"employee": "TEST_E1", "date": "2026-01-01", "hours": 4, "approved": False}),
]


@pytest.mark.parametrize("path,payload", HR_RESOURCES)
def test_phase_e_admin_crud(admin, path, payload):
    r = admin.post(f"{API}/{path}", json=payload)
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"
    rid = r.json()["id"]
    g = admin.get(f"{API}/{path}")
    assert g.status_code == 200
    u = admin.put(f"{API}/{path}/{rid}", json={"note": "TEST"})
    assert u.status_code == 200
    d = admin.delete(f"{API}/{path}/{rid}")
    assert d.status_code in (200, 204)


def test_candidates_restricted_for_site_engineer(site_engineer):
    r = site_engineer.get(f"{API}/candidates")
    assert r.status_code == 403, f"site_engineer must be 403 on candidates, got {r.status_code}"


def test_recruitment_requests_readable_by_site_engineer(site_engineer):
    # site_engineer not in read list — should be 403 per rbac
    r = site_engineer.get(f"{API}/recruitment-requests")
    assert r.status_code == 403


# ===== Phase F — Vendor Portal =====
class TestPhaseFVendor:
    def test_me_without_vendor_link_404(self, admin):
        # admin email not linked to any vendor → 404 per spec
        r = admin.get(f"{API}/vendor-portal/me")
        assert r.status_code == 404, f"expected 404 for unlinked admin, got {r.status_code}: {r.text}"

    def test_evaluation_rolling_average(self, admin):
        # Create vendor
        v = admin.post(f"{API}/vendors", json={
            "name": "TEST_PhaseF Vendor", "category": "general",
            "contact_email": "test_vendor_phasef@example.com",
            "contact_phone": "+1111", "status": "active"
        })
        assert v.status_code in (200, 201), v.text
        vid = v.json()["id"]
        try:
            r1 = admin.post(f"{API}/vendor-portal/evaluations/{vid}", json={
                "rating": 4.0, "period": "2026-Q1", "note": "TEST"
            })
            assert r1.status_code == 200, r1.text
            r2 = admin.post(f"{API}/vendor-portal/evaluations/{vid}", json={
                "rating": 5.0, "period": "2026-Q2", "note": "TEST"
            })
            assert r2.status_code == 200, r2.text
            vget = admin.get(f"{API}/vendors/{vid}").json()
            assert abs(vget["rating"] - 4.5) < 0.01, f"avg should be 4.5 got {vget.get('rating')}"
            assert vget.get("rating_count") == 2
        finally:
            admin.delete(f"{API}/vendors/{vid}")

    def test_evaluation_rbac_site_engineer_forbidden(self, admin, site_engineer):
        v = admin.post(f"{API}/vendors", json={
            "name": "TEST_PhaseF Vendor2", "category": "general",
            "contact_email": "test_vendor2_phasef@example.com",
            "status": "active"
        }).json()
        try:
            r = site_engineer.post(f"{API}/vendor-portal/evaluations/{v['id']}", json={
                "rating": 3.0, "period": "2026-Q1"
            })
            assert r.status_code == 403
        finally:
            admin.delete(f"{API}/vendors/{v['id']}")

    def test_invoice_submit_for_linked_admin_uses_vendor_id(self, admin):
        # admin has no linked vendor → /vendor-portal/invoices POST should 404
        r = admin.post(f"{API}/vendor-portal/invoices", json={
            "invoice_no": "TEST-INV-1", "date": "2026-01-01", "amount": 1000
        })
        assert r.status_code == 404


# ===== Regression — Phase A/B endpoints =====
def test_regression_auth_me(admin):
    r = admin.get(f"{API}/auth/me")
    assert r.status_code == 200
    assert r.json().get("role") == "super_admin"


def test_regression_dashboard_summary(admin):
    r = admin.get(f"{API}/dashboard/summary")
    assert r.status_code == 200


def test_regression_enquiries_list(admin):
    r = admin.get(f"{API}/enquiries")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_regression_orders_list(admin):
    r = admin.get(f"{API}/orders")
    assert r.status_code == 200
