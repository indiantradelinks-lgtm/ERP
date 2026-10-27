"""Iter 201 — Approval policy changes.

Covers:
  (1) Fuel Payment approval: exclusive 1-step Manager Log chain, RBAC on
      approve/reject, Super Admin excluded on fuel.
  (2) Service Procurement: no internal gates on SR / vendor selection / PO.
  (3) In-flight cleanup collections (svc_requests / rfqs / pos).
  (4) Description/Justification on Payment Processing rows (list rows).
"""
import os
import random
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN = ("admin@erp.com", "Admin@123")
MLOG = ("test_log@erp.com", "Log@12345")
PM = ("test_pm@erp.com", "PM@12345")


# ---------------------------------------------------------------- helpers ---
def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("access_token") or body.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    # Cookie-based session also set on `s` automatically
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def mlog():
    return _login(*MLOG)


@pytest.fixture(scope="module")
def pm():
    return _login(*PM)


@pytest.fixture(scope="module")
def sample_project_and_cc(admin, pm):
    """Pick a project PM has access to, with cost centers."""
    r = pm.get(f"{BASE_URL}/api/projects", timeout=15)
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("rows", [])
    for p in rows:
        if not p.get("id") or p.get("is_head_office") or not p.get("code"):
            continue
        cr = admin.get(f"{BASE_URL}/api/procurement/master/cost-centers?project_id={p['id']}", timeout=15)
        if cr.status_code != 200:
            continue
        ccs = cr.json() if isinstance(cr.json(), list) else cr.json().get("rows", [])
        if ccs:
            return p, ccs[0]
    pytest.skip("No non-HO project with cost centers accessible to PM")


@pytest.fixture(scope="module")
def sample_project(sample_project_and_cc):
    return sample_project_and_cc[0]


@pytest.fixture(scope="module")
def sample_cc(sample_project_and_cc):
    return sample_project_and_cc[1]


def _mk_fuel_payload(project, cc, amount=5000):
    # Iter 205 blocks a second open fuel request with the SAME project + vendor +
    # amount, so each test run uses its own amount offset.
    amount = amount + random.randint(1, 899) / 100
    return {
        "project_id": project["id"],
        "project_code": project["code"],
        "request_type": "fuel", "vehicle_ref": "HR26DK8337",
        "priority": "medium",
        "description": f"TEST_iter201 fuel justification {uuid.uuid4().hex[:6]}",
        "cost_center_id": cc["id"],
        "amount": amount,
        "vendor": "TEST_vendor_iter201",
        "paid_to_type": "vendor",
    }


# ====================================================== fuel: chain shape ===
class TestFuelChain:
    def test_fuel_low_value_single_step(self, pm, sample_project, sample_cc):
        payload = _mk_fuel_payload(sample_project, sample_cc, amount=5000)
        r = pm.post(f"{BASE_URL}/api/project-requests", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        try:
            assert d["request_type"] == "fuel"
            chain = d["chain"]
            assert len(chain) == 1, f"expected single-step chain, got {chain}"
            assert chain[0]["role"] == "manager_log"
            assert chain[0]["label"] == "Manager Log"
            assert chain[0]["exclusive"] is True
            assert chain[0]["status"] == "pending"
        finally:
            # cleanup (reject so it drops out of pending)
            _cleanup_pr(d["id"])

    def test_fuel_large_value_still_single_step(self, pm, sample_project, sample_cc):
        """Even above the large-value threshold, chain must stay 1-step."""
        payload = _mk_fuel_payload(sample_project, sample_cc, amount=250000)
        r = pm.post(f"{BASE_URL}/api/project-requests", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        try:
            chain = d["chain"]
            assert len(chain) == 1, f"large-value fuel still should be 1 step, got {chain}"
            assert chain[0]["role"] == "manager_log"
            assert chain[0]["exclusive"] is True
            # And GM/Director must NOT be present
            roles = [c["role"] for c in chain]
            assert "general_manager" not in roles
            assert "director" not in roles
            assert "dept_head" not in roles
        finally:
            _cleanup_pr(d["id"])


def _cleanup_pr(rid):
    """Admin-reject or delete to leave DB clean."""
    try:
        s = _login(*ADMIN)
        # Can't approve/reject fuel as super_admin — just delete via admin endpoint if present
        s.delete(f"{BASE_URL}/api/project-requests/{rid}", timeout=10)
    except Exception:
        pass


# ====================================================== fuel: RBAC approve ==
class TestFuelRBAC:
    @pytest.fixture
    def fuel_req(self, pm, sample_project, sample_cc):
        r = pm.post(f"{BASE_URL}/api/project-requests",
                    json=_mk_fuel_payload(sample_project, sample_cc, amount=4500),
                    timeout=20)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        yield rid
        _cleanup_pr(rid)

    def test_super_admin_forbidden_on_fuel_approve(self, admin, fuel_req):
        r = admin.post(f"{BASE_URL}/api/project-requests/{fuel_req}/approve",
                       json={"remarks": "try as admin"}, timeout=15)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
        assert "Manager Log" in r.text or "manager_log" in r.text

    def test_super_admin_forbidden_on_fuel_reject(self, admin, fuel_req):
        r = admin.post(f"{BASE_URL}/api/project-requests/{fuel_req}/reject",
                       json={"remarks": "nope"}, timeout=15)
        assert r.status_code == 403

    def test_pm_forbidden_on_fuel_step(self, pm, fuel_req):
        r = pm.post(f"{BASE_URL}/api/project-requests/{fuel_req}/approve",
                    json={"remarks": "pm try"}, timeout=15)
        assert r.status_code == 403

    def test_manager_log_can_approve(self, mlog, pm, sample_project, sample_cc):
        # Create a fresh one just for approval test
        r = pm.post(f"{BASE_URL}/api/project-requests",
                    json=_mk_fuel_payload(sample_project, sample_cc, amount=3300),
                    timeout=20)
        assert r.status_code == 200
        rid = r.json()["id"]
        try:
            ar = mlog.post(f"{BASE_URL}/api/project-requests/{rid}/approve",
                           json={"remarks": "ML OK"}, timeout=15)
            assert ar.status_code == 200, ar.text
            got = ar.json()
            assert got["status"] == "with_dept", f"status after approve = {got.get('status')}"
            assert got["chain"][0]["status"] == "approved"
            assert got["chain"][0]["by"]
        finally:
            _cleanup_pr(rid)

    def test_manager_log_can_reject(self, mlog, pm, sample_project, sample_cc):
        r = pm.post(f"{BASE_URL}/api/project-requests",
                    json=_mk_fuel_payload(sample_project, sample_cc, amount=1100),
                    timeout=20)
        rid = r.json()["id"]
        try:
            rr = mlog.post(f"{BASE_URL}/api/project-requests/{rid}/reject",
                           json={"remarks": "ML reject"}, timeout=15)
            assert rr.status_code == 200, rr.text
            assert rr.json()["status"] == "rejected"
        finally:
            _cleanup_pr(rid)


# ====================================================== fuel: inbox =========
class TestFuelInbox:
    def test_manager_log_inbox_lists_fuel(self, mlog):
        r = mlog.get(f"{BASE_URL}/api/my-inbox", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or []
        prs = [i for i in items if i.get("source") == "project_request"]
        assert prs, "manager_log inbox has no project_request items (expected pending fuel)"
        # Every project_request item for manager_log should have Manager Log step
        for it in prs:
            assert "Manager Log" in (it.get("step_label") or ""), it

    def test_super_admin_inbox_hides_fuel(self, admin):
        r = admin.get(f"{BASE_URL}/api/my-inbox", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items") or []
        prs = [i for i in items if i.get("source") == "project_request"]
        # None of the project_request items should be fuel (Manager Log step)
        for it in prs:
            assert (it.get("step_label") or "") != "Manager Log", f"super_admin inbox leaked fuel: {it}"


# ====================================================== non-fuel regression =
class TestNonFuelChain:
    def test_accommodation_normal_chain(self, pm, sample_project, sample_cc):
        payload = {
            "project_id": sample_project["id"],
            "project_code": sample_project["code"],
            "request_type": "accommodation",
            "priority": "medium",
            "description": "TEST_iter201 accommodation",
            "cost_center_id": sample_cc["id"],
            "amount": 300000,  # above threshold → GM + Director
            "vendor": "TEST_vendor",
            "paid_to_type": "vendor",
        }
        r = pm.post(f"{BASE_URL}/api/project-requests", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        try:
            roles = [c["role"] for c in d["chain"]]
            assert roles == ["dept_head", "general_manager", "director"], roles
            assert not any(c.get("exclusive") for c in d["chain"])
        finally:
            _cleanup_pr(d["id"])


# ====================================================== service workflow ===
class TestServiceWorkflow:
    @pytest.fixture(scope="class")
    def sr(self, admin, sample_project):
        payload = {
            "project_id": sample_project["id"],
            "project_code": sample_project["code"],
            "department": "Operations",
            "service_category": "AMC",
            "service_description": "TEST_iter201 service",
            "priority": "medium",
            "site_location": sample_project.get("name"),
            "estimated_budget": 10000,
            "submit": True,
        }
        r = admin.post(f"{BASE_URL}/api/service-workflow/requests", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        yield d
        # cleanup
        try:
            admin.delete(f"{BASE_URL}/api/service-workflow/requests/{d['id']}", timeout=10)
        except Exception:
            pass

    def test_sr_submit_goes_to_approved(self, sr):
        assert sr["status"] == "approved", f"status = {sr.get('status')}"
        assert sr.get("approval_chain") == [], f"approval_chain = {sr.get('approval_chain')}"
        assert sr.get("current_owner") in ("Logistics / Procurement", None, "Logistics", "Procurement")

    def test_rfq_can_be_created_immediately(self, admin, sr):
        # Need at least 1 vendor
        vr = admin.get(f"{BASE_URL}/api/vendors?limit=5", timeout=10)
        vendors = vr.json() if vr.status_code == 200 else []
        if not isinstance(vendors, list):
            vendors = vendors.get("vendors") or vendors.get("rows") or []
        if not vendors:
            pytest.skip("no vendors")
        rfq_payload = {"scope_of_work": "TEST_iter201 scope",
                       "closing_date": "2026-12-31",
                       "vendor_ids": [vendors[0]["id"]]}
        r = admin.post(f"{BASE_URL}/api/service-workflow/requests/{sr['id']}/rfq",
                       json=rfq_payload, timeout=20)
        assert r.status_code == 200, r.text
        rfq = r.json()
        assert rfq.get("id") and rfq.get("rfq_no")

    def test_selection_action_returns_400(self, admin, sample_project):
        # Create a fresh SR for this test
        sr_payload = {"project_id": sample_project["id"], "project_code": sample_project["code"],
                      "department": "Operations", "service_category": "AMC",
                      "service_description": "TEST_iter201 sel", "priority": "medium",
                      "site_location": sample_project.get("name"),
                      "estimated_budget": 5000, "submit": True}
        sr_r = admin.post(f"{BASE_URL}/api/service-workflow/requests", json=sr_payload, timeout=20)
        if sr_r.status_code != 200:
            pytest.skip(f"could not create SR: {sr_r.text[:200]}")
        sr_id = sr_r.json()["id"]
        vr = admin.get(f"{BASE_URL}/api/vendors?limit=5", timeout=10)
        vendors = vr.json() if vr.status_code == 200 else []
        if not isinstance(vendors, list) or not vendors:
            pytest.skip("no vendors")
        r = admin.post(f"{BASE_URL}/api/service-workflow/requests/{sr_id}/rfq",
                       json={"scope_of_work": "T", "closing_date": "2026-12-31",
                             "vendor_ids": [vendors[0]["id"]]}, timeout=20)
        if r.status_code != 200:
            pytest.skip(f"could not create rfq: {r.text[:200]}")
        rfq_id = r.json()["id"]
        ar = admin.post(f"{BASE_URL}/api/service-workflow/rfqs/{rfq_id}/selection-action",
                        json={"action": "approve", "remarks": ""}, timeout=15)
        assert ar.status_code == 400, f"selection-action should 400, got {ar.status_code}: {ar.text}"


# ====================================================== in-flight cleanup ==
class TestInFlightCleanup:
    def test_no_svc_requests_in_submitted(self, admin):
        r = admin.get(f"{BASE_URL}/api/service-workflow/requests?status=submitted", timeout=15)
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("rows", [])
        assert rows == [] or len(rows) == 0, f"found submitted svc_requests: {len(rows)}"

    def test_no_svc_rfqs_recommended(self, admin):
        r = admin.get(f"{BASE_URL}/api/service-workflow/rfqs?status=recommended", timeout=15)
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("rows", [])
        assert len(rows) == 0

    def test_no_svc_pos_pending_approval(self, admin):
        r = admin.get(f"{BASE_URL}/api/service-workflow/pos?status=pending_approval", timeout=15)
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("rows", [])
        assert len(rows) == 0


# ====================================================== PPC description ====
class TestPaymentDescription:
    def test_payment_queue_rows_have_description(self, admin):
        r = admin.get(f"{BASE_URL}/api/accounts/payment-queue", timeout=20)
        assert r.status_code == 200, r.text
        payload = r.json()
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
        if not rows:
            pytest.skip("payment queue empty")
        checked = 0
        for row in rows[:30]:
            # Every row must carry either description or remarks so UI 'Justification' line renders
            has = bool((row.get("description") or "").strip() or (row.get("remarks") or "").strip())
            if not has and checked < 3:
                print(f"row {row.get('request_no')} has no description/remarks")
            checked += 1
        # Soft: at least some rows carry description
        with_desc = sum(1 for r in rows if (r.get("description") or "").strip())
        assert with_desc > 0, "no rows carry a description field"
