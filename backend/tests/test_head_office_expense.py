"""Backend tests for Project Request Center — Head Office Expense workflow.

Covers:
 - GET /api/office-locations seeds Delhi Head Office and is idempotent
 - POST /api/office-locations is super_admin-only + duplicate 400
 - GET /api/project-requests/types includes 'head_office_expense'
 - POST /api/project-requests HO branch + validation errors
 - Approval chain (dept_head -> GM -> Director) + fulfil books HO expense
 - HO expense listed under scope=head_office and excluded from scope=project
 - POST /api/project-expenses direct HO booking, project regression
 - RBAC: sales_executive gets 403 on HO expense raise
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def sales():
    return _login("sales@erp.com", "Sales@123")


# ── office-locations ──────────────────────────────────────────────────────
class TestOfficeLocations:
    def test_get_seeds_delhi(self, admin):
        r = admin.get(f"{BASE_URL}/api/office-locations", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and rows, "office-locations should not be empty"
        del_ho = next((o for o in rows if o.get("code") == "DEL-HO"), None)
        assert del_ho, f"Delhi Head Office not seeded: {rows}"
        assert del_ho["name"] == "Delhi Head Office"
        assert del_ho["is_default"] is True

    def test_get_is_idempotent(self, admin):
        n1 = len(admin.get(f"{BASE_URL}/api/office-locations", timeout=30).json())
        n2 = len(admin.get(f"{BASE_URL}/api/office-locations", timeout=30).json())
        assert n1 == n2, "office-locations must be idempotent"

    def test_post_requires_super_admin(self, sales):
        r = sales.post(f"{BASE_URL}/api/office-locations",
                       json={"code": "TEST-HO", "name": "Test HO"}, timeout=30)
        # sales_executive lacks project_requests write; either 403 or role-check 403
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_post_duplicate_rejected(self, admin):
        r = admin.post(f"{BASE_URL}/api/office-locations",
                       json={"code": "DEL-HO", "name": "Delhi Head Office"}, timeout=30)
        assert r.status_code == 400, r.text[:300]


# ── request types ─────────────────────────────────────────────────────────
class TestRequestTypes:
    def test_head_office_expense_present(self, admin):
        r = admin.get(f"{BASE_URL}/api/project-requests/types", timeout=30)
        assert r.status_code == 200
        types = {t["key"]: t for t in r.json()}
        assert "head_office_expense" in types
        assert "Head Office Expense" in types["head_office_expense"]["label"]


# ── shared helpers ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ho_cost_center(admin):
    r = admin.get(f"{BASE_URL}/api/head-office-cost-centers", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    assert rows, "no HO cost centers available"
    return rows[0]


@pytest.fixture(scope="module")
def project_cost_center(admin):
    """Pick any project cost center (has project_id set)."""
    r = admin.get(f"{BASE_URL}/api/procurement/master/cost-centers", timeout=30)
    if r.status_code != 200:
        pytest.skip("cost-centers endpoint unavailable")
    rows = r.json() if isinstance(r.json(), list) else r.json().get("rows") or []
    proj = next((c for c in rows if c.get("project_id")), None)
    if not proj:
        pytest.skip("no project cost centers seeded")
    return proj


@pytest.fixture(scope="module")
def approved_vendor(admin):
    r = admin.get(f"{BASE_URL}/api/vendors", timeout=30)
    assert r.status_code == 200, r.text[:200]
    rows = r.json() if isinstance(r.json(), list) else r.json().get("rows") or []
    v = next((v for v in rows if (v.get("status") or "").lower() in ("approved", "active")), None) or (rows[0] if rows else None)
    assert v, "no vendors available"
    return v


# ── HO expense request validation ─────────────────────────────────────────
class TestHOExpenseValidation:
    def _base(self, cc_id, vendor_name, extra=None):
        p = {
            "request_type": "head_office_expense",
            "office_location": "Delhi Head Office",
            "cost_center_id": cc_id,
            "paid_to_type": "vendor",
            "vendor": vendor_name,
            "amount": 12500,
            "description": "TEST_HO_expense",
            "priority": "medium",
        }
        if extra:
            p.update(extra)
        return p

    def test_reject_project_cost_center(self, admin, project_cost_center, approved_vendor):
        p = self._base(project_cost_center["id"], approved_vendor.get("name") or approved_vendor.get("vendor_name"))
        r = admin.post(f"{BASE_URL}/api/project-requests", json=p, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

    def test_reject_no_cost_center(self, admin, approved_vendor):
        p = self._base(None, approved_vendor.get("name") or approved_vendor.get("vendor_name"))
        p.pop("cost_center_id", None)
        r = admin.post(f"{BASE_URL}/api/project-requests", json=p, timeout=30)
        assert r.status_code == 400

    def test_reject_zero_amount(self, admin, ho_cost_center, approved_vendor):
        p = self._base(ho_cost_center["id"], approved_vendor.get("name") or approved_vendor.get("vendor_name"),
                       extra={"amount": 0})
        r = admin.post(f"{BASE_URL}/api/project-requests", json=p, timeout=30)
        assert r.status_code == 400

    def test_reject_vendor_without_vendor(self, admin, ho_cost_center):
        p = self._base(ho_cost_center["id"], None)
        p["vendor"] = ""
        r = admin.post(f"{BASE_URL}/api/project-requests", json=p, timeout=30)
        assert r.status_code == 400

    def test_reject_project_id_supplied(self, admin, ho_cost_center, approved_vendor):
        # Grab any project to attempt
        pr = admin.get(f"{BASE_URL}/api/projects", timeout=30)
        rows = pr.json() if isinstance(pr.json(), list) else pr.json().get("rows") or []
        if not rows:
            pytest.skip("no projects available")
        p = self._base(ho_cost_center["id"], approved_vendor.get("name") or approved_vendor.get("vendor_name"),
                       extra={"project_id": rows[0]["id"]})
        r = admin.post(f"{BASE_URL}/api/project-requests", json=p, timeout=30)
        assert r.status_code == 400, r.text[:300]


# ── RBAC ──────────────────────────────────────────────────────────────────
class TestHORaiseRBAC:
    def test_sales_forbidden(self, sales, ho_cost_center, approved_vendor):
        p = {
            "request_type": "head_office_expense",
            "office_location": "Delhi Head Office",
            "cost_center_id": ho_cost_center["id"],
            "paid_to_type": "vendor",
            "vendor": approved_vendor.get("name") or approved_vendor.get("vendor_name"),
            "amount": 3000,
        }
        r = sales.post(f"{BASE_URL}/api/project-requests", json=p, timeout=30)
        assert r.status_code == 403


# ── full happy path: create → approve chain → fulfil → expense booked ────
class TestHOEndToEnd:
    def test_full_flow(self, admin, ho_cost_center, approved_vendor):
        vendor_name = approved_vendor.get("name") or approved_vendor.get("vendor_name")
        # Amount above default large threshold (10 000) so we get PH → GM → Director chain
        payload = {
            "request_type": "head_office_expense",
            "office_location": "Delhi Head Office",
            "cost_center_id": ho_cost_center["id"],
            "paid_to_type": "vendor",
            "vendor": vendor_name,
            "amount": 18500,
            "description": "TEST_HO_e2e",
            "priority": "medium",
        }
        r = admin.post(f"{BASE_URL}/api/project-requests", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:400]
        req = r.json()
        assert req["project_id"] is None
        assert req["project_code"] == "HEAD-OFFICE"
        assert req["project_name"] == "Delhi Head Office"
        assert req["is_head_office"] is True
        assert req["office_location"] == "Delhi Head Office"
        assert req["vendor"] == vendor_name
        chain_roles = [c["role"] for c in req["chain"]]
        assert chain_roles == ["dept_head", "general_manager", "director"], chain_roles

        rid = req["id"]
        # super_admin can approve every step
        for _ in range(3):
            ar = admin.post(f"{BASE_URL}/api/project-requests/{rid}/approve",
                            json={"remarks": "ok"}, timeout=30)
            assert ar.status_code == 200, ar.text[:300]
        after_approve = ar.json()
        assert after_approve["status"] == "with_dept", after_approve["status"]

        # fulfil
        fr = admin.post(f"{BASE_URL}/api/project-requests/{rid}/fulfil",
                        json={"remarks": "ok"}, timeout=30)
        assert fr.status_code == 200, fr.text[:300]
        after = fr.json()
        assert after["status"] == "fulfilled"
        assert after.get("expense_id"), f"expense_id missing: {after}"

        # Verify project expense created
        eid = after["expense_id"]
        er = admin.get(f"{BASE_URL}/api/project-expenses?scope=head_office", timeout=30)
        assert er.status_code == 200
        rows = er.json()
        exp = next((e for e in rows if e["id"] == eid), None)
        assert exp, f"expense {eid} not returned in scope=head_office"
        assert exp["project_code"] == "HEAD-OFFICE"
        assert exp["office_location"] == "Delhi Head Office"
        assert exp["is_head_office"] is True
        assert exp["status"] == "approved_for_payment"
        assert exp.get("source_request_no") == req["request_no"]
        assert exp.get("paid_to") == vendor_name

        # Must NOT appear under scope=project
        pr = admin.get(f"{BASE_URL}/api/project-expenses?scope=project", timeout=30)
        assert pr.status_code == 200
        assert not any(e["id"] == eid for e in pr.json()), "HO expense leaked into scope=project"


# ── direct daily HO expense booking ───────────────────────────────────────
class TestDirectHOExpense:
    def test_book_direct_ho(self, admin, ho_cost_center):
        p = {
            "office_location": "Delhi Head Office",
            "cost_center_id": ho_cost_center["id"],
            "expense_type": "head_office",
            "expense_date": "2026-09-17",
            "amount": 2450,
            "description": "TEST_direct_HO",
            "payment_mode": "Cash",
            "settlement_mode": "petty_cash",
        }
        r = admin.post(f"{BASE_URL}/api/project-expenses", json=p, timeout=30)
        assert r.status_code == 200, r.text[:400]
        exp = r.json()
        assert exp["is_head_office"] is True
        assert exp["project_code"] == "HEAD-OFFICE"
        assert exp["office_location"] == "Delhi Head Office"

    def test_no_project_no_office_400(self, admin, ho_cost_center):
        p = {
            "cost_center_id": ho_cost_center["id"],
            "expense_type": "head_office",
            "expense_date": "2026-09-17",
            "amount": 100,
        }
        r = admin.post(f"{BASE_URL}/api/project-expenses", json=p, timeout=30)
        assert r.status_code == 400

    def test_project_cc_with_office_400(self, admin, project_cost_center):
        p = {
            "office_location": "Delhi Head Office",
            "cost_center_id": project_cost_center["id"],
            "expense_type": "misc",
            "expense_date": "2026-09-17",
            "amount": 100,
        }
        r = admin.post(f"{BASE_URL}/api/project-expenses", json=p, timeout=30)
        assert r.status_code == 400

    def test_project_expense_regression(self, admin, project_cost_center):
        # Original project expense still works
        p = {
            "project_id": project_cost_center["project_id"],
            "cost_center_id": project_cost_center["id"],
            "expense_type": "misc",
            "expense_date": "2026-09-17",
            "amount": 500,
            "description": "TEST_regression",
        }
        r = admin.post(f"{BASE_URL}/api/project-expenses", json=p, timeout=30)
        assert r.status_code == 200, r.text[:400]
        exp = r.json()
        assert exp["is_head_office"] is False
        assert exp["project_id"] == project_cost_center["project_id"]
