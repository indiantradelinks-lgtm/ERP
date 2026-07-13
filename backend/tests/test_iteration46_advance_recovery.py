"""Iteration 46 — Employee Advance Recovery (Phase C + D + E) backend tests.

Covers:
- Phase C: recovery dry-run + commit, override, skip, foreclose, settle, RBAC, idempotency
- Phase D: /advances/me/summary, /advances/reports/{outstanding,monthly-recovery,aging}
- Phase E: /advances/bulk-import (multipart CSV)
- Regression (Iter 45 fix): payment endpoint sets outstanding = paid_amount
- Regression: full happy-path AD-####/Salary Advance create → submit → 6-step approve → pay → recovery run
"""
import io
import os
import random
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "super_admin": ("admin@erp.com", "Admin@123"),
    "hr_executive": ("hr.test@erp.com", "HR@12345"),
    "project_manager": ("test_pm@erp.com", "PM@12345"),
    "site_engineer": ("test_site_engineer@erp.com", "TestPass@123"),
}

SESSIONS: dict[str, requests.Session] = {}
USERS: dict[str, dict] = {}
STATE: dict = {}


def _login(email: str, password: str):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        return None, {}
    data = r.json()
    if data.get("access_token"):
        s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    user = data if "role" in data else (data.get("user") or {})
    return s, user


def _sess(role: str) -> requests.Session:
    s = SESSIONS.get(role)
    if not s:
        pytest.skip(f"role {role} not authenticated")
    return s


@pytest.fixture(scope="session", autouse=True)
def authenticate_all_roles():
    for role, (email, pwd) in CREDS.items():
        s, user = _login(email, pwd)
        if s is not None:
            SESSIONS[role] = s
            USERS[role] = user
    if "super_admin" not in SESSIONS:
        pytest.skip("super_admin login failed — cannot run iteration 46 suite")
    yield


# ────────────────────────────────────────────────────────────────────────
# Setup: create a fresh advance and walk it through full approval + payment
# (regression of Iter 45 payment outstanding bug)
# ────────────────────────────────────────────────────────────────────────
class TestSetupFreshAdvance:
    """Creates fresh AD-####/Salary Advance for the whole iteration-46 suite."""

    def test_pick_employee(self):
        s = _sess("super_admin")
        r = s.get(f"{API}/employees", timeout=30)
        assert r.status_code == 200, r.text
        emps = r.json()
        if isinstance(emps, dict):
            emps = emps.get("rows") or emps.get("employees") or []
        emp = next((e for e in emps if e.get("salary")), None)
        if not emp:
            pytest.skip("no employee with salary in DB")
        STATE["employee"] = emp

    def test_create_advance(self):
        s = _sess("super_admin")
        emp = STATE.get("employee")
        if not emp:
            pytest.skip("no employee fixture")
        # Use Salary Advance (caps: 100k / 12 EMIs); 12000 / 4 = 3000 EMI
        payload = {
            "employee_id": emp["id"],
            "advance_type": "Salary Advance",
            "advance_type_code": "SAL",
            "requested_amount": 12000,
            "installments": 4,
            "reason": "Iter46 recovery test",
            "repayment_start_month": "2026-01",
        }
        r = s.post(f"{API}/advances", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        adv = r.json()
        STATE["advance_id"] = adv["id"]
        STATE["advance_no"] = adv["advance_no"]

    def test_submit_and_full_approve(self):
        s = _sess("super_admin")
        adv_id = STATE.get("advance_id")
        if not adv_id:
            pytest.skip("no advance fixture")
        adv = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        if adv["status"] == "draft":
            r = s.post(f"{API}/advances/{adv_id}/submit", json={}, timeout=30)
            assert r.status_code == 200, r.text
            adv = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        approval_id = adv.get("approval_id")
        assert approval_id, "approval_id missing after submit"
        # Walk all 6 steps via super_admin
        for i in range(6):
            r = s.post(
                f"{API}/approvals/{approval_id}/action",
                json={"action": "approve", "comment": f"iter46 step {i + 1}"},
                timeout=30,
            )
            assert r.status_code == 200, f"approve step {i + 1}: {r.text}"
        adv = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        assert adv["status"] == "approved", f"expected approved, got {adv['status']}"
        assert adv["approved_amount"] == 12000

    def test_pay_full_and_regression_outstanding(self):
        """REGRESSION: outstanding must equal paid_amount (NOT zero, NOT approved-paid)."""
        s = _sess("super_admin")
        adv_id = STATE["advance_id"]
        voucher = f"ITER46-{uuid.uuid4().hex[:8].upper()}"
        r = s.post(
            f"{API}/advances/{adv_id}/payment",
            json={
                "mode": "bank_transfer",
                "paid_amount": 12000,
                "payment_date": "2026-01-05",
                "bank_name": "HDFC",
                "voucher_no": voucher,
                "txn_no": f"TXN-{voucher}",
                "remarks": "iter46",
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "paid"
        assert out["outstanding"] == 12000, f"REGRESSION: outstanding should equal paid_amount=12000, got {out['outstanding']}"
        # GET to verify persistence
        adv = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        assert adv["outstanding"] == 12000
        assert adv["paid_amount"] == 12000


# ────────────────────────────────────────────────────────────────────────
# Phase C — Recovery dry-run + commit + idempotency
# ────────────────────────────────────────────────────────────────────────
class TestRecoveryDryRunCommit:
    def test_rbac_project_manager_blocked(self):
        s = _sess("project_manager")
        r = s.post(f"{API}/advances/recovery/run", json={"month": "2026-01", "dry_run": True}, timeout=30)
        assert r.status_code == 403, f"expected 403 for project_manager, got {r.status_code}"

    def test_invalid_month(self):
        s = _sess("hr_executive")
        r = s.post(f"{API}/advances/recovery/run", json={"month": "BAD", "dry_run": True}, timeout=30)
        assert r.status_code == 400

    def test_dry_run_includes_our_advance(self):
        s = _sess("hr_executive")
        r = s.post(f"{API}/advances/recovery/run", json={"month": "2026-01", "dry_run": True}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dry_run"] is True
        assert "proposals" in data and "skipped" in data and "total_emi" in data
        proposals = data["proposals"]
        adv_no = STATE.get("advance_no")
        if adv_no:
            mine = next((p for p in proposals if p["advance_no"] == adv_no), None)
            assert mine is not None, f"our advance {adv_no} not in dry-run proposals"
            assert mine["emi"] == 3000
            assert mine["outstanding_before"] == 12000
            assert mine["outstanding_after"] == 9000
        # Dry-run must NOT have mutated outstanding
        s2 = _sess("super_admin")
        adv = s2.get(f"{API}/advances/{STATE['advance_id']}", timeout=30).json()
        assert adv["outstanding"] == 12000, "dry-run should NOT mutate balances"

    def test_commit_run(self):
        s = _sess("hr_executive")
        r = s.post(f"{API}/advances/recovery/run", json={"month": "2026-01", "dry_run": False}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dry_run"] is False
        assert data["committed"] >= 1
        # Verify our advance got EMI deduction
        s2 = _sess("super_admin")
        adv = s2.get(f"{API}/advances/{STATE['advance_id']}", timeout=30).json()
        assert adv["outstanding"] == 9000
        assert adv["recovered_amount"] == 3000
        assert adv["remaining_installments"] == 3
        assert adv["status"] == "under_recovery"

    def test_idempotency_rerun_same_month(self):
        """Re-running the same month must skip our advance with reason 'already processed'."""
        s = _sess("hr_executive")
        r = s.post(f"{API}/advances/recovery/run", json={"month": "2026-01", "dry_run": False}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        adv_no = STATE["advance_no"]
        skipped_nos = [x["advance_no"] for x in data.get("skipped", [])]
        assert adv_no in skipped_nos, f"expected {adv_no} skipped on re-run"
        skip_row = next(x for x in data["skipped"] if x["advance_no"] == adv_no)
        assert "already processed" in skip_row["reason"]
        # Balance unchanged
        adv = _sess("super_admin").get(f"{API}/advances/{STATE['advance_id']}", timeout=30).json()
        assert adv["outstanding"] == 9000
        assert adv["recovered_amount"] == 3000


# ────────────────────────────────────────────────────────────────────────
# Phase C — Override / Skip / Foreclose / Settle
# ────────────────────────────────────────────────────────────────────────
class TestRecoveryActions:
    def test_override_replaces_row(self):
        """Override Jan emi from 3000 → 2000. recovered must be recomputed."""
        s = _sess("hr_executive")
        r = s.post(
            f"{API}/advances/recovery/override",
            json={"advance_id": STATE["advance_id"], "month": "2026-01", "amount": 2000, "note": "iter46 override"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        adv = _sess("super_admin").get(f"{API}/advances/{STATE['advance_id']}", timeout=30).json()
        # Approved was 12000, recovered now should be 2000 (since prior 3000 emi was replaced)
        assert abs(adv["recovered_amount"] - 2000) < 0.01, f"recovered: {adv['recovered_amount']}"
        assert abs(adv["outstanding"] - 10000) < 0.01, f"outstanding: {adv['outstanding']}"
        assert adv["status"] == "under_recovery"

    def test_skip_writes_audit_row_no_balance_change(self):
        s = _sess("hr_executive")
        adv_before = _sess("super_admin").get(f"{API}/advances/{STATE['advance_id']}", timeout=30).json()
        r = s.post(
            f"{API}/advances/{STATE['advance_id']}/recovery/skip",
            json={"amount": 1, "month": "2026-02", "note": "iter46 skip Feb"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["type"] == "skipped"
        adv_after = _sess("super_admin").get(f"{API}/advances/{STATE['advance_id']}", timeout=30).json()
        assert adv_after["outstanding"] == adv_before["outstanding"]
        assert adv_after["remaining_installments"] == adv_before["remaining_installments"]

    def test_foreclose_must_equal_outstanding(self):
        # Build a 2nd small advance so we can foreclose it cleanly
        s = _sess("super_admin")
        emp = STATE.get("employee")
        if not emp:
            pytest.skip("no employee")
        r = s.post(f"{API}/advances", json={
            "employee_id": emp["id"], "advance_type": "Emergency Advance",
            "advance_type_code": "EMG", "requested_amount": 6000, "installments": 2,
            "reason": "iter46 foreclose target", "repayment_start_month": "2026-03",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        adv_id = r.json()["id"]
        s.post(f"{API}/advances/{adv_id}/submit", json={}, timeout=30)
        adv = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        for _ in range(6):
            s.post(f"{API}/approvals/{adv['approval_id']}/action",
                   json={"action": "approve", "comment": "ok"}, timeout=30)
        s.post(f"{API}/advances/{adv_id}/payment", json={
            "mode": "bank_transfer", "paid_amount": 6000, "payment_date": "2026-03-05",
            "bank_name": "HDFC", "voucher_no": f"ITER46FC-{uuid.uuid4().hex[:6].upper()}",
            "txn_no": "FC1", "remarks": "fc"
        }, timeout=30)
        adv = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        assert adv["outstanding"] == 6000
        STATE["foreclose_id"] = adv_id

        # wrong amount → 400
        r = s.post(f"{API}/advances/{adv_id}/recovery/foreclose",
                   json={"amount": 5999, "month": "2026-04"}, timeout=30)
        assert r.status_code == 400
        # correct amount → 200 + status closed
        r = s.post(f"{API}/advances/{adv_id}/recovery/foreclose",
                   json={"amount": 6000, "month": "2026-04", "note": "iter46 foreclose"}, timeout=30)
        assert r.status_code == 200, r.text
        adv_after = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        assert adv_after["status"] == "closed"
        assert adv_after["outstanding"] == 0
        assert adv_after["recovered_amount"] == 6000

    def test_settle_requires_gm_director(self):
        """hr_executive should be blocked, super_admin allowed (acts as GM/Director surrogate)."""
        # Build another advance to settle
        s = _sess("super_admin")
        emp = STATE.get("employee")
        if not emp:
            pytest.skip("no employee")
        r = s.post(f"{API}/advances", json={
            "employee_id": emp["id"], "advance_type": "Emergency Advance",
            "advance_type_code": "EMG", "requested_amount": 4000, "installments": 2,
            "reason": "iter46 settle target", "repayment_start_month": "2026-05",
        }, timeout=30)
        adv_id = r.json()["id"]
        s.post(f"{API}/advances/{adv_id}/submit", json={}, timeout=30)
        adv = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        for _ in range(6):
            s.post(f"{API}/approvals/{adv['approval_id']}/action",
                   json={"action": "approve", "comment": "ok"}, timeout=30)
        s.post(f"{API}/advances/{adv_id}/payment", json={
            "mode": "bank_transfer", "paid_amount": 4000, "payment_date": "2026-05-05",
            "bank_name": "HDFC", "voucher_no": f"ITER46ST-{uuid.uuid4().hex[:6].upper()}",
            "txn_no": "ST1", "remarks": "st"
        }, timeout=30)
        STATE["settle_id"] = adv_id

        # hr_executive forbidden
        sh = _sess("hr_executive")
        r = sh.post(f"{API}/advances/{adv_id}/recovery/settle",
                    json={"waived_amount": 4000, "month": "2026-06"}, timeout=30)
        assert r.status_code == 403, f"hr_executive should be 403 on settle, got {r.status_code}"
        # super_admin allowed
        r = s.post(f"{API}/advances/{adv_id}/recovery/settle",
                   json={"waived_amount": 4000, "month": "2026-06", "note": "iter46 waive"}, timeout=30)
        assert r.status_code == 200, r.text
        adv_after = s.get(f"{API}/advances/{adv_id}", timeout=30).json()
        assert adv_after["status"] == "closed"
        assert adv_after["outstanding"] == 0
        assert adv_after.get("settlement_waived") == 4000

    def test_skip_foreclose_blocked_for_pm(self):
        s = _sess("project_manager")
        r = s.post(f"{API}/advances/{STATE['advance_id']}/recovery/skip",
                   json={"amount": 1, "month": "2026-07"}, timeout=30)
        assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# Phase D — Self-service + reports
# ────────────────────────────────────────────────────────────────────────
class TestSelfServiceAndReports:
    def test_me_summary_hr_executive(self):
        s = _sess("hr_executive")
        r = s.get(f"{API}/advances/me/summary", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "linked" in data
        # If linked, must have outstanding_total numeric + active_advances list
        if data["linked"]:
            assert "active_advances" in data
            assert isinstance(data.get("outstanding_total", 0), (int, float))

    def test_me_summary_site_engineer_no_crash(self):
        s = _sess("site_engineer")
        r = s.get(f"{API}/advances/me/summary", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "linked" in data
        # site_engineer may or may not be linked; just must not crash
        assert isinstance(data.get("outstanding_total", 0), (int, float))

    def test_report_outstanding_rbac_and_shape(self):
        # project_manager forbidden
        rpm = _sess("project_manager").get(f"{API}/advances/reports/outstanding", timeout=30)
        assert rpm.status_code == 403
        # hr allowed
        s = _sess("hr_executive")
        r = s.get(f"{API}/advances/reports/outstanding", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rows" in data and "total_outstanding" in data
        assert isinstance(data["rows"], list)
        # Our recovering advance must appear
        ours = next((x for x in data["rows"] if x["advance_no"] == STATE.get("advance_no")), None)
        assert ours is not None, "our advance should appear in outstanding report"
        assert ours["outstanding"] == 10000

    def test_report_monthly_recovery_jan(self):
        s = _sess("hr_executive")
        r = s.get(f"{API}/advances/reports/monthly-recovery", params={"month": "2026-01"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["month"] == "2026-01"
        assert "rows" in data and "total_recovered" in data
        adv_no = STATE.get("advance_no")
        ours = next((x for x in data["rows"] if x.get("advance_no") == adv_no), None)
        assert ours is not None, "Jan should contain our recovery"
        # After override → manual row of 2000 (the original emi row was deleted)
        assert abs(ours["amount"] - 2000) < 0.01

    def test_report_aging_shape(self):
        s = _sess("hr_executive")
        r = s.get(f"{API}/advances/reports/aging", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "buckets" in data and "total" in data
        for k in ["0-30", "30-60", "60-90", "90+"]:
            assert k in data["buckets"]
        assert data["total"] == sum(data["buckets"].values())


# ────────────────────────────────────────────────────────────────────────
# Phase E — CSV bulk import
# ────────────────────────────────────────────────────────────────────────
class TestBulkImport:
    def test_bulk_import_rbac_pm_blocked(self):
        s = _sess("project_manager")
        csv_data = "employee_code,advance_type,approved_amount,installments,emi,repayment_start_month\n"
        files = {"file": ("test.csv", csv_data, "text/csv")}
        r = s.post(f"{API}/advances/bulk-import", files=files, timeout=30)
        assert r.status_code == 403

    def test_bulk_import_valid_and_invalid_rows(self):
        s = _sess("hr_executive")
        emp = STATE.get("employee")
        if not emp:
            pytest.skip("no employee")
        emp_code = emp.get("employee_id") or emp.get("emp_code") or emp.get("email")
        csv_data = (
            "employee_code,advance_type,approved_amount,paid_amount,recovered_amount,installments,emi,repayment_start_month\n"
            f"{emp_code},Salary Advance,10000,10000,2000,5,2000,2025-12\n"
            "DOESNOTEXIST123,Salary Advance,5000,5000,0,2,2500,2025-12\n"
        )
        files = {"file": ("import.csv", csv_data, "text/csv")}
        r = s.post(f"{API}/advances/bulk-import", files=files, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] >= 1, data
        assert len(data["errors"]) >= 1
        assert "DOESNOTEXIST123" in str(data["errors"])
        # Verify the imported advance is queryable + has imported=True + status under_recovery
        if data["samples"]:
            adv_no = data["samples"][0]["advance_no"]
            ss = _sess("super_admin")
            rows = ss.get(f"{API}/advances", timeout=30).json()
            if isinstance(rows, dict):
                rows = rows.get("rows") or rows.get("advances") or []
            imp = next((x for x in rows if x.get("advance_no") == adv_no), None)
            assert imp is not None, f"imported {adv_no} not in /advances"
            assert imp.get("imported") is True
            assert imp.get("status") in {"under_recovery", "closed"}
            assert imp.get("outstanding") == 8000  # 10000 paid - 2000 recovered

    def test_bulk_import_closed_when_fully_recovered(self):
        s = _sess("hr_executive")
        emp = STATE.get("employee")
        if not emp:
            pytest.skip("no employee")
        emp_code = emp.get("employee_id") or emp.get("emp_code") or emp.get("email")
        csv_data = (
            "employee_code,advance_type,approved_amount,paid_amount,recovered_amount,installments,emi,repayment_start_month\n"
            f"{emp_code},Other,5000,5000,5000,2,2500,2025-06\n"
        )
        files = {"file": ("closed.csv", csv_data, "text/csv")}
        r = s.post(f"{API}/advances/bulk-import", files=files, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 1
        adv_no = data["samples"][0]["advance_no"]
        rows = _sess("super_admin").get(f"{API}/advances", timeout=30).json()
        if isinstance(rows, dict):
            rows = rows.get("rows") or rows.get("advances") or []
        imp = next((x for x in rows if x.get("advance_no") == adv_no), None)
        assert imp is not None
        assert imp.get("status") == "closed"
        assert imp.get("outstanding") == 0
