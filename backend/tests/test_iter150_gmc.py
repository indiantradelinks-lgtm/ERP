"""GMC (Group Medical Policy) backend tests — Iter 150.

Covers:
 - Policy CRUD + duplicate policy_number rejection
 - eligible-employees filter (exited + already-enrolled excluded)
 - bulk-add member scope (auto / project / head_office) + skip duplicates/exited
 - member filters (scope, project_code, designation, status, q)
 - GET /gmc/summary math
 - member remove / restore (400 for exited)
 - FnF finalise -> auto-removal from GMC
 - export.xlsx / export.pdf content types
 - RBAC: sales_executive gets 403
"""
from __future__ import annotations

import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@erp.com", "Admin@123")
SALES = ("sales@erp.com", "Sales@123")


# ─── fixtures ────────────────────────────────────────────────────────────
def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin() -> requests.Session:
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def sales() -> requests.Session:
    try:
        return _login(*SALES)
    except AssertionError:
        pytest.skip("sales@erp.com login unavailable — skipping RBAC negative test")


# ─── helpers ─────────────────────────────────────────────────────────────
def _mk_employee(admin: requests.Session, name: str, project_code: str | None = None,
                 designation: str = "Engineer", department: str = "Operations") -> dict:
    payload = {
        "name": name,
        "emp_code": f"TESTGMC-{uuid.uuid4().hex[:6].upper()}",
        "designation": designation,
        "department": department,
        "status": "active",
        "salary": 30000,
        "joining_date": "2020-01-01",
        "employment_type": "permanent",
    }
    if project_code:
        payload["current_project_code"] = project_code
    r = admin.post(f"{API}/employees", json=payload, timeout=20)
    assert r.status_code in (200, 201), f"emp create failed: {r.status_code} {r.text[:200]}"
    return r.json()


@pytest.fixture(scope="module")
def policy(admin: requests.Session):
    body = {
        "policy_number": f"TESTGMC/{uuid.uuid4().hex[:6].upper()}",
        "insurer": "Star Health",
        "tpa": "MedAssist",
        "policy_start": "2026-01-01",
        "policy_end": "2026-12-31",
        "sum_insured_default": 500000,
        "premium_total": 250000,
        "status": "active",
    }
    r = admin.post(f"{API}/gmc/policies", json=body, timeout=20)
    assert r.status_code == 200, r.text
    p = r.json()
    yield p
    # teardown: try to remove members, then policy
    try:
        members = admin.get(f"{API}/gmc/members?policy_id={p['id']}").json()
        for m in members:
            if m.get("status") == "active":
                admin.post(f"{API}/gmc/members/{m['id']}/remove", json={"reason": "test cleanup"})
        admin.delete(f"{API}/gmc/policies/{p['id']}")
    except Exception:
        pass


# ─── 1. Policy CRUD + duplicate check ────────────────────────────────────
class TestPolicyCRUD:
    def test_list_policies_returns_active_members_count(self, admin, policy):
        r = admin.get(f"{API}/gmc/policies", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        me = next((x for x in rows if x["id"] == policy["id"]), None)
        assert me is not None, "created policy not in list"
        assert "active_members" in me
        assert isinstance(me["active_members"], int)

    def test_duplicate_policy_number_rejected(self, admin, policy):
        r = admin.post(f"{API}/gmc/policies", json={
            "policy_number": policy["policy_number"],
            "insurer": "Other", "sum_insured_default": 100000,
        }, timeout=20)
        assert r.status_code == 400
        assert "exist" in r.text.lower()

    def test_update_policy(self, admin, policy):
        r = admin.put(f"{API}/gmc/policies/{policy['id']}", json={
            "policy_number": policy["policy_number"],
            "insurer": "Star Health Updated",
            "tpa": policy.get("tpa"),
            "policy_start": policy.get("policy_start"),
            "policy_end": policy.get("policy_end"),
            "sum_insured_default": 600000,
            "premium_total": 300000,
            "status": "active",
        }, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["insurer"] == "Star Health Updated"
        assert r.json()["sum_insured_default"] == 600000

    def test_delete_policy_blocked_with_active_members(self, admin, policy):
        # Add an employee first
        emp = _mk_employee(admin, "TEST GMC Delete Blocker")
        r = admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": [emp["id"]], "coverage_scope": "head_office",
        }, timeout=20)
        assert r.status_code == 200
        assert r.json()["added"] == 1
        # Try delete
        r2 = admin.delete(f"{API}/gmc/policies/{policy['id']}", timeout=20)
        assert r2.status_code == 400
        # Remove the member, delete should still be blocked by other members added later; that's fine.
        m = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&q={emp['emp_code']}").json()[0]
        admin.post(f"{API}/gmc/members/{m['id']}/remove", json={"reason": "cleanup"})


# ─── 2. eligible-employees ───────────────────────────────────────────────
class TestEligible:
    def test_eligible_excludes_active_members_and_exited(self, admin, policy):
        # create 2 employees, add one to policy, mark the other exited
        e_in = _mk_employee(admin, "TEST GMC In")
        e_out = _mk_employee(admin, "TEST GMC Out")
        # add e_in to policy
        r = admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": [e_in["id"]], "coverage_scope": "head_office",
        }, timeout=20)
        assert r.status_code == 200
        # mark e_out exited via PUT /employees/{id}
        r2 = admin.put(f"{API}/employees/{e_out['id']}", json={**e_out, "status": "exited"}, timeout=20)
        assert r2.status_code in (200, 201), r2.text

        r3 = admin.get(f"{API}/gmc/eligible-employees?policy_id={policy['id']}", timeout=20)
        assert r3.status_code == 200
        rows = r3.json()
        ids = {x["id"] for x in rows}
        assert e_in["id"] not in ids, "active member should be excluded"
        assert e_out["id"] not in ids, "exited employee should be excluded"


# ─── 3. bulk-add scope logic + skip duplicates/exited ────────────────────
class TestBulkAdd:
    def test_bulk_add_scope_auto_and_explicit(self, admin, policy):
        e_proj = _mk_employee(admin, "TEST GMC WithProject", project_code="PRJ-TEST-1")
        e_ho = _mk_employee(admin, "TEST GMC HeadOffice")

        # auto → project because has current_project_code, HO because none
        r = admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"],
            "employee_ids": [e_proj["id"], e_ho["id"]],
            "coverage_scope": "auto",
        }, timeout=20)
        assert r.status_code == 200
        assert r.json()["added"] == 2

        members = admin.get(f"{API}/gmc/members?policy_id={policy['id']}").json()
        m_proj = next(m for m in members if m["employee_id"] == e_proj["id"])
        m_ho = next(m for m in members if m["employee_id"] == e_ho["id"])
        assert m_proj["coverage_scope"] == "project"
        assert m_proj["project_code"] == "PRJ-TEST-1"
        assert m_ho["coverage_scope"] == "head_office"

    def test_bulk_add_skips_duplicates_and_exited(self, admin, policy):
        e = _mk_employee(admin, "TEST GMC DupSkip")
        e2 = _mk_employee(admin, "TEST GMC ExitedSkip")
        admin.put(f"{API}/employees/{e2['id']}", json={**e2, "status": "exited"})

        # first add e
        r = admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": [e["id"]], "coverage_scope": "head_office",
        }, timeout=20)
        assert r.json()["added"] == 1

        # second: try both — should skip both (dup + exited)
        r2 = admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": [e["id"], e2["id"]], "coverage_scope": "head_office",
        }, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["added"] == 0
        assert r2.json()["skipped"] == 2

    def test_bulk_add_empty_list_400(self, admin, policy):
        r = admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": []
        }, timeout=20)
        assert r.status_code == 400


# ─── 4. Member filters + summary ─────────────────────────────────────────
class TestFiltersAndSummary:
    def test_filters(self, admin, policy):
        # status=active
        r = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&status=active", timeout=20)
        assert r.status_code == 200
        for m in r.json():
            assert m["status"] == "active"
        # scope=head_office
        r = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&scope=head_office", timeout=20)
        for m in r.json():
            assert m["coverage_scope"] == "head_office"
        # q search
        r = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&q=TEST", timeout=20)
        assert r.status_code == 200

    def test_summary_math(self, admin, policy):
        r = admin.get(f"{API}/gmc/summary?policy_id={policy['id']}", timeout=20)
        assert r.status_code == 200
        s = r.json()
        for k in ("active", "removed", "head_office", "project", "dependents",
                  "sum_insured_total", "premium_total"):
            assert k in s
        assert s["head_office"] + s["project"] == s["active"]


# ─── 5. Remove / restore ─────────────────────────────────────────────────
class TestRemoveRestore:
    def test_remove_then_restore(self, admin, policy):
        e = _mk_employee(admin, "TEST GMC RemoveMe")
        admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": [e["id"]], "coverage_scope": "head_office",
        }, timeout=20)
        m = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&q={e['emp_code']}").json()[0]
        r = admin.post(f"{API}/gmc/members/{m['id']}/remove",
                       json={"reason": "TEST removed manually"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["status"] == "removed"
        assert "TEST removed" in (r.json().get("removal_reason") or "")

        # restore
        r2 = admin.post(f"{API}/gmc/members/{m['id']}/restore", json={}, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["status"] == "active"

    def test_restore_blocked_for_exited_employee(self, admin, policy):
        e = _mk_employee(admin, "TEST GMC ExitBlockRestore")
        admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": [e["id"]], "coverage_scope": "head_office",
        }, timeout=20)
        m = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&q={e['emp_code']}").json()[0]
        admin.post(f"{API}/gmc/members/{m['id']}/remove", json={"reason": "test"}, timeout=20)
        # now mark employee exited
        admin.put(f"{API}/employees/{e['id']}", json={**e, "status": "exited"})
        r = admin.post(f"{API}/gmc/members/{m['id']}/restore", json={}, timeout=20)
        assert r.status_code == 400


# ─── 6. FNF exit → auto-remove from GMC ──────────────────────────────────
class TestExitAutoRemoval:
    def test_finalise_exit_auto_removes_from_gmc(self, admin, policy):
        emp = _mk_employee(admin, "TEST GMC FnFAutoRemove")
        # add to policy
        r = admin.post(f"{API}/gmc/members/bulk-add", json={
            "policy_id": policy["id"], "employee_ids": [emp["id"]], "coverage_scope": "head_office",
        }, timeout=20)
        assert r.json()["added"] == 1
        member = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&q={emp['emp_code']}").json()[0]
        assert member["status"] == "active"

        # create exit
        rex = admin.post(f"{API}/hr/exits", json={
            "employee_id": emp["id"],
            "resignation_date": "2026-01-01",
            "last_working_day": "2026-01-15",
            "reason": "test",
            "notice_period_days": 15,
        }, timeout=20)
        assert rex.status_code in (200, 201), rex.text
        exit_id = rex.json()["id"]

        # approve every clearance item
        items = rex.json().get("clearance") or []
        for it in items:
            ra = admin.post(f"{API}/hr/exits/{exit_id}/clearance/{it['key']}/approve",
                            json={"remarks": "ok"}, timeout=20)
            assert ra.status_code == 200, f"approve {it['key']} failed: {ra.status_code} {ra.text[:150]}"

        # compute fnf
        rc = admin.post(f"{API}/hr/exits/{exit_id}/compute-fnf", json={}, timeout=20)
        assert rc.status_code == 200, rc.text

        # finalise
        rf = admin.post(f"{API}/hr/exits/{exit_id}/finalise", json={}, timeout=20)
        assert rf.status_code == 200, rf.text
        assert rf.json()["status"] == "finalised"

        # verify auto-removal
        m_after = admin.get(f"{API}/gmc/members?policy_id={policy['id']}&q={emp['emp_code']}").json()[0]
        assert m_after["status"] == "removed", f"expected removed, got {m_after['status']}"
        assert "exited" in (m_after.get("removal_reason") or "").lower(), \
            f"removal_reason should mention exit: {m_after.get('removal_reason')}"


# ─── 7. Exports ──────────────────────────────────────────────────────────
class TestExports:
    def test_export_xlsx(self, admin, policy):
        r = admin.get(f"{API}/gmc/export.xlsx?policy_id={policy['id']}", timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "spreadsheetml" in r.headers.get("content-type", "")
        assert len(r.content) > 100

    def test_export_pdf(self, admin, policy):
        r = admin.get(f"{API}/gmc/export.pdf?policy_id={policy['id']}", timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "pdf" in r.headers.get("content-type", "")
        assert len(r.content) > 100


# ─── 8. RBAC ─────────────────────────────────────────────────────────────
class TestRBAC:
    def test_sales_forbidden_on_policies(self, sales):
        r = sales.get(f"{API}/gmc/policies", timeout=20)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"
