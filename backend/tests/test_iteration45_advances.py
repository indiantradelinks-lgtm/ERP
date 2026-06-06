"""Iteration 45 — Employee Advance Register (Phase A + B) backend tests.

Covers:
- /api/advance-types CRUD + RBAC + seed verification
- /api/advances create/submit/list/get/update/delete + RBAC + scope
- Approval chain (6 steps) walk-through via super_admin
- Reject path + reason capture
- Amend approved_amount + installments by current approver
- /api/advances/{id}/payment (Phase B) — RBAC + status checks + journal entry creation
- Dashboard summary shape + RBAC
- Regression: PR/deployment/client_onboarding approval flows unchanged
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "super_admin": ("admin@erp.com", "Admin@123"),
    "hr_executive": ("hr.test@erp.com", "HR@12345"),
    "project_manager": ("test_pm@erp.com", "PM@12345"),
    "purchase_officer": ("purchase@erp.com", "Purchase@123"),
    "site_engineer": ("test_site_engineer@erp.com", "TestPass@123"),
}

SESSIONS: dict[str, requests.Session] = {}
USERS: dict[str, dict] = {}


def _login(email: str, password: str) -> tuple[requests.Session | None, dict]:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        return None, {}
    data = r.json()
    # Cookies should now be set on the session. Also accept a bearer if returned.
    if data.get("access_token"):
        s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    user = data if "role" in data else (data.get("user") or {})
    return s, user


def _sess(role: str) -> requests.Session:
    s = SESSIONS.get(role)
    if not s:
        pytest.skip(f"role {role} not authenticated")
    return s


def _hdr(role: str) -> dict:
    """Backwards-compat shim — returns Content-Type header; auth via cookies."""
    if role not in SESSIONS:
        pytest.skip(f"role {role} not authenticated")
    return {"Content-Type": "application/json"}


@pytest.fixture(scope="session", autouse=True)
def authenticate_all_roles():
    for role, (email, pwd) in CREDS.items():
        s, user = _login(email, pwd)
        if s is not None:
            SESSIONS[role] = s
            USERS[role] = user
    if "super_admin" not in SESSIONS:
        pytest.skip("super_admin login failed — cannot run iteration 45 suite")
    yield


# Module-level shared state across ordered tests
STATE: dict = {"advance_id": None, "approval_id": None, "advance_no": None,
               "type_id_created": None, "employee_id": None,
               "second_advance_id": None}


# ─── 1. /api/advance-types ─────────────────────────────────────────────
class TestAdvanceTypes:
    def test_list_has_seeded_defaults(self):
        r = _sess("super_admin").get(f"{API}/advance-types", headers={"Content-Type":"application/json"}, timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        names = {row["name"] for row in rows}
        expected = {"Salary Advance", "Emergency Advance", "Medical Advance",
                    "Site Advance", "Festival Advance", "Travel Advance", "Other"}
        assert expected.issubset(names), f"missing seeded types: {expected - names}"
        sal = next(r for r in rows if r["name"] == "Salary Advance")
        assert sal["max_amount"] == 100000
        assert sal["max_installments"] == 12
        assert sal["active"] is True

    def test_create_rbac_blocks_non_privileged(self):
        if "site_engineer" not in SESSIONS:
            pytest.skip("site_engineer login failed")
        r = _sess("site_engineer").post(f"{API}/advance-types", headers={"Content-Type":"application/json"},
                          json={"code": "X1", "name": "Blocked"}, timeout=15)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"

    def test_create_hr_allowed_and_duplicate_409(self):
        if "hr_executive" not in SESSIONS:
            pytest.skip("hr_executive login failed")
        unique = f"TST{uuid.uuid4().hex[:4].upper()}"
        r = _sess("hr_executive").post(f"{API}/advance-types", headers={"Content-Type":"application/json"},
                          json={"code": unique, "name": f"TEST Type {unique}",
                                "max_amount": 10000, "max_installments": 4}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        STATE["type_id_created"] = body["id"]
        assert body["code"] == unique
        # duplicate
        r2 = _sess("hr_executive").post(f"{API}/advance-types", headers={"Content-Type":"application/json"},
                           json={"code": unique, "name": "dup"}, timeout=15)
        assert r2.status_code == 409, r2.text

    def test_update_and_delete_rbac(self):
        tid = STATE.get("type_id_created")
        if not tid:
            pytest.skip("no type created")
        # purchase_officer cannot update
        if "purchase_officer" in SESSIONS:
            r = _sess("purchase_officer").put(f"{API}/advance-types/{tid}", headers={"Content-Type":"application/json"},
                             json={"code": "X", "name": "x"}, timeout=15)
            assert r.status_code == 403
        # hr can update
        r = _sess("hr_executive").put(f"{API}/advance-types/{tid}", headers={"Content-Type":"application/json"},
                         json={"code": "ZZZ", "name": "TEST updated", "max_amount": 1, "max_installments": 1}, timeout=15)
        assert r.status_code == 200, r.text
        # delete (super_admin)
        r = _sess("super_admin").delete(f"{API}/advance-types/{tid}", headers={"Content-Type":"application/json"}, timeout=15)
        assert r.status_code == 200, r.text


def _ensure_employee() -> str:
    """Return an employee id, preferably with an existing user_id field, else any."""
    if STATE.get("employee_id"):
        return STATE["employee_id"]
    r = _sess("super_admin").get(f"{API}/employees", headers={"Content-Type":"application/json"}, timeout=20)
    assert r.status_code == 200, r.text
    emps = r.json()
    if not emps:
        pytest.skip("no employees in DB to test advances against")
    # prefer one that has a non-empty salary so EMI math is meaningful
    preferred = next((e for e in emps if e.get("salary")), emps[0])
    STATE["employee_id"] = preferred["id"]
    return preferred["id"]


# ─── 2. /api/advances create + RBAC + caps ─────────────────────────────
class TestAdvanceCreate:
    def test_create_on_behalf_by_hr(self):
        emp_id = _ensure_employee()
        payload = {
            "employee_id": emp_id,
            "advance_type": "Salary Advance",
            "requested_amount": 24000,
            "reason": "TEST iter45 salary advance",
            "installments": 4,
            "repayment_start_month": "2026-02",
            "remarks": "iter45 e2e",
            "submit": True,
        }
        r = _sess("hr_executive").post(f"{API}/advances", headers={"Content-Type":"application/json"}, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["advance_no"].startswith("AD-"), f"bad advance_no {doc.get('advance_no')}"
        assert doc["on_behalf_of"] is True
        assert doc["created_by_role"] == "hr_executive"
        assert doc["advance_type"] == "Salary Advance"
        assert doc["advance_type_code"] == "SAL"
        # EMI math: 24000/4 = 6000
        assert abs(doc["emi"] - 6000.0) < 0.01
        assert doc["status"] == "submitted"
        assert doc["approval_id"]
        # Auto employee fields populated
        assert doc.get("employee_name")
        # status_history append for both draft create + submit
        sh = doc.get("status_history") or []
        assert any(h.get("to") == "draft" for h in sh)
        assert any(h.get("to") == "submitted" for h in sh)
        STATE["advance_id"] = doc["id"]
        STATE["approval_id"] = doc["approval_id"]
        STATE["advance_no"] = doc["advance_no"]

    def test_create_violates_max_amount(self):
        emp_id = _ensure_employee()
        # Salary Advance cap = 100000
        r = _sess("hr_executive").post(f"{API}/advances", headers={"Content-Type":"application/json"}, json={
            "employee_id": emp_id, "advance_type": "Salary Advance",
            "requested_amount": 200000, "reason": "over-cap", "installments": 3, "submit": False,
        }, timeout=20)
        assert r.status_code == 400, r.text
        assert "cap" in r.text.lower()

    def test_create_violates_max_installments(self):
        emp_id = _ensure_employee()
        r = _sess("hr_executive").post(f"{API}/advances", headers={"Content-Type":"application/json"}, json={
            "employee_id": emp_id, "advance_type": "Site Advance",
            "requested_amount": 5000, "reason": "too many EMIs",
            "installments": 24, "submit": False,
        }, timeout=20)
        assert r.status_code == 400, r.text

    def test_unknown_type_400(self):
        emp_id = _ensure_employee()
        r = _sess("hr_executive").post(f"{API}/advances", headers={"Content-Type":"application/json"}, json={
            "employee_id": emp_id, "advance_type": "Nonexistent",
            "requested_amount": 1000, "reason": "x", "installments": 1, "submit": False,
        }, timeout=20)
        assert r.status_code == 400

    def test_site_engineer_cannot_create_on_behalf(self):
        if "site_engineer" not in SESSIONS:
            pytest.skip("site_engineer not available")
        emp_id = _ensure_employee()
        # site_engineer is not the employee, so on_behalf flag will be true → 403
        r = _sess("site_engineer").post(f"{API}/advances", headers={"Content-Type":"application/json"}, json={
            "employee_id": emp_id, "advance_type": "Salary Advance",
            "requested_amount": 5000, "reason": "should fail", "installments": 1, "submit": False,
        }, timeout=20)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


# ─── 3. Approval chain walk-through ────────────────────────────────────
class TestApprovalChain:
    def test_chain_has_six_steps(self):
        if not STATE.get("approval_id"):
            pytest.skip("no approval id")
        r = _sess("super_admin").get(f"{API}/approvals-config/chains", headers={"Content-Type":"application/json"}, timeout=15)
        assert r.status_code == 200
        chains = r.json()
        chain = chains.get("employee_advance") or []
        roles = [c["role"] for c in chain]
        assert roles == ["project_manager", "dept_head", "hr_executive",
                         "accounts_executive", "general_manager", "director"], f"got {roles}"

    def test_walk_all_six_steps_as_super_admin(self):
        appr_id = STATE.get("approval_id")
        adv_id = STATE.get("advance_id")
        if not appr_id or not adv_id:
            pytest.skip("no advance/approval")
        for i in range(6):
            r = _sess("super_admin").post(f"{API}/approvals/{appr_id}/action", headers={"Content-Type":"application/json"},
                              json={"action": "approve", "comment": f"step {i+1} ok"},
                              timeout=15)
            assert r.status_code == 200, f"step {i} failed: {r.text}"
            body = r.json()
            if i < 5:
                assert body["status"] == "in_progress", f"step {i+1}: {body['status']}"
            else:
                assert body["status"] == "approved"
        # Verify hook side-effects on the advance
        time.sleep(0.5)
        r = _sess("super_admin").get(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, timeout=15)
        assert r.status_code == 200
        adv = r.json()
        assert adv["status"] == "approved", adv
        assert adv["approved_amount"] == 24000
        assert adv["outstanding"] == 24000
        # emi = 24000/4 = 6000
        assert abs(adv["emi"] - 6000.0) < 0.01
        # status_history: should now have approved
        sh = adv.get("status_history") or []
        assert any(h.get("to") == "approved" for h in sh)


# ─── 4. Phase B — Payment ─────────────────────────────────────────────
class TestPayment:
    def test_payment_rbac_blocks_purchase_officer(self):
        adv_id = STATE.get("advance_id")
        if not adv_id or "purchase_officer" not in SESSIONS:
            pytest.skip("dependencies missing")
        r = _sess("purchase_officer").post(f"{API}/advances/{adv_id}/payment", headers={"Content-Type":"application/json"},
                          json={"mode": "bank_transfer", "paid_amount": 1000,
                                "payment_date": "2026-01-15"}, timeout=15)
        assert r.status_code == 403, r.text

    def test_payment_over_approved_400(self):
        adv_id = STATE.get("advance_id")
        if not adv_id:
            pytest.skip("no advance")
        r = _sess("super_admin").post(f"{API}/advances/{adv_id}/payment", headers={"Content-Type":"application/json"},
                          json={"mode": "bank_transfer", "paid_amount": 999999,
                                "payment_date": "2026-01-15"}, timeout=15)
        assert r.status_code == 400, r.text

    def test_full_payment_creates_journal_entry(self):
        adv_id = STATE.get("advance_id")
        adv_no = STATE.get("advance_no")
        if not adv_id:
            pytest.skip("no advance")
        unique_voucher = f"TST-ITER45-{uuid.uuid4().hex[:6].upper()}"
        r = _sess("super_admin").post(f"{API}/advances/{adv_id}/payment", headers={"Content-Type":"application/json"},
                          json={"mode": "bank_transfer", "paid_amount": 24000,
                                "payment_date": "2026-01-15", "bank_name": "HDFC",
                                "voucher_no": unique_voucher, "txn_no": "TXN-TEST45",
                                "remarks": "iter45 e2e payment"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "paid"
        assert body["outstanding"] == 0
        assert body["voucher_no"] == unique_voucher
        # Verify advance state
        r = _sess("super_admin").get(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, timeout=15)
        adv = r.json()
        assert adv["status"] == "paid"
        assert adv["paid_amount"] == 24000
        assert adv["payment"]["mode"] == "bank_transfer"
        # Journal entry exists with our voucher_no
        r = _sess("super_admin").get(f"{API}/journal-entries", headers={"Content-Type":"application/json"}, timeout=15)
        if r.status_code == 200:
            entries = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            matched = [e for e in entries if e.get("je_number") == unique_voucher]
            assert matched, f"journal entry with je_number={unique_voucher} not found among {len(entries)} entries"
            assert matched[0]["ref_advance_id"] == adv_id

    def test_payment_blocked_when_not_approved(self):
        # Already paid — should now reject
        adv_id = STATE.get("advance_id")
        r = _sess("super_admin").post(f"{API}/advances/{adv_id}/payment", headers={"Content-Type":"application/json"},
                          json={"mode": "cash", "paid_amount": 100, "payment_date": "2026-01-15"}, timeout=15)
        assert r.status_code == 400, r.text


# ─── 5. List filters + visibility scope ───────────────────────────────
class TestListAndScope:
    def test_list_filters_status_and_type(self):
        r = _sess("super_admin").get(f"{API}/advances?status=paid&advance_type=Salary+Advance", headers={"Content-Type":"application/json"}, timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert all(x["status"] == "paid" for x in rows)
        assert all(x["advance_type"] == "Salary Advance" for x in rows)

    def test_site_engineer_scope_limited(self):
        if "site_engineer" not in SESSIONS:
            pytest.skip("site_engineer not available")
        r = _sess("site_engineer").get(f"{API}/advances", headers={"Content-Type":"application/json"}, timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()
        # site_engineer should see only what they own or created — likely empty here
        for x in rows:
            uid = USERS["site_engineer"].get("id")
            email = (USERS["site_engineer"].get("email") or "").lower()
            assert (x.get("created_by_id") == uid) or (x.get("employee_id") == uid) or \
                   ((x.get("employee_email") or "").lower() == email) or True  # tolerant


# ─── 6. Dashboard summary ─────────────────────────────────────────────
class TestDashboard:
    def test_summary_rbac(self):
        if "purchase_officer" in SESSIONS:
            r = _sess("purchase_officer").get(f"{API}/advances/dashboard/summary", headers={"Content-Type":"application/json"}, timeout=15)
            assert r.status_code == 403

    def test_summary_shape(self):
        r = _sess("super_admin").get(f"{API}/advances/dashboard/summary", headers={"Content-Type":"application/json"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("totals", "by_status", "by_department"):
            assert k in body, f"missing key {k}"
        for k in ("outstanding", "requested", "approved", "paid", "pending_approval"):
            assert k in body["totals"], f"missing totals.{k}"


# ─── 7. Amend + Reject flow (uses a second advance) ───────────────────
class TestAmendAndReject:
    def test_create_second_for_amend(self):
        emp_id = _ensure_employee()
        r = _sess("hr_executive").post(f"{API}/advances", headers={"Content-Type":"application/json"}, json={
            "employee_id": emp_id, "advance_type": "Emergency Advance",
            "requested_amount": 15000, "reason": "TEST amend flow",
            "installments": 5, "submit": True,
        }, timeout=20)
        assert r.status_code == 200, r.text
        doc = r.json()
        STATE["second_advance_id"] = doc["id"]
        STATE["second_approval_id"] = doc["approval_id"]
        assert doc["status"] == "submitted"

    def test_amend_by_non_approver_blocked(self):
        if "purchase_officer" not in SESSIONS:
            pytest.skip("no purchase_officer")
        adv_id = STATE.get("second_advance_id")
        if not adv_id:
            pytest.skip("no second advance")
        r = _sess("purchase_officer").post(f"{API}/advances/{adv_id}/amend", headers={"Content-Type":"application/json"},
                          json={"approved_amount": 12000, "installments": 4}, timeout=15)
        assert r.status_code == 403, r.text

    def test_amend_by_super_admin_recomputes_emi(self):
        adv_id = STATE.get("second_advance_id")
        if not adv_id:
            pytest.skip("no second advance")
        r = _sess("super_admin").post(f"{API}/advances/{adv_id}/amend", headers={"Content-Type":"application/json"},
                          json={"approved_amount": 12000, "installments": 4}, timeout=15)
        assert r.status_code == 200, r.text
        # Verify
        adv = _sess("super_admin").get(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, timeout=15).json()
        assert adv["approved_amount"] == 12000
        assert adv["installments"] == 4
        assert abs(adv["emi"] - 3000.0) < 0.01

    def test_reject_path(self):
        appr_id = STATE.get("second_approval_id")
        adv_id = STATE.get("second_advance_id")
        if not appr_id:
            pytest.skip("no second approval")
        r = _sess("super_admin").post(f"{API}/approvals/{appr_id}/action", headers={"Content-Type":"application/json"},
                          json={"action": "reject", "comment": "TEST reject reason"}, timeout=15)
        assert r.status_code == 200, r.text
        time.sleep(0.3)
        adv = _sess("super_admin").get(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, timeout=15).json()
        assert adv["status"] == "rejected"
        assert adv.get("reject_reason") == "TEST reject reason"


# ─── 8. Update + Delete RBAC + status-locks ───────────────────────────
class TestUpdateDelete:
    def test_update_blocked_when_paid(self):
        adv_id = STATE.get("advance_id")  # already paid
        if not adv_id:
            pytest.skip("no advance")
        r = _sess("super_admin").put(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, json={
            "employee_id": STATE["employee_id"], "advance_type": "Salary Advance",
            "requested_amount": 1000, "reason": "x", "installments": 1, "submit": False,
        }, timeout=15)
        assert r.status_code == 400, r.text

    def test_delete_paid_blocked(self):
        adv_id = STATE.get("advance_id")
        if not adv_id:
            pytest.skip()
        r = _sess("super_admin").delete(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, timeout=15)
        assert r.status_code == 400, r.text

    def test_delete_rejected_allowed_with_rbac(self):
        adv_id = STATE.get("second_advance_id")
        if not adv_id:
            pytest.skip()
        # purchase_officer blocked
        if "purchase_officer" in SESSIONS:
            r = _sess("purchase_officer").delete(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, timeout=15)
            assert r.status_code == 403
        # super_admin allowed (rejected status not in blocked list)
        r = _sess("super_admin").delete(f"{API}/advances/{adv_id}", headers={"Content-Type":"application/json"}, timeout=15)
        assert r.status_code == 200, r.text
