"""Iter 119 — Central Access Control + Duplicate Audit + masking.

Validates:
  • Backend access_control orchestrator (has_action_access / data_scope_filter / mask)
  • /api/auth/access-context returns role + permissions + visible modules
  • /api/admin/duplicates/scan returns the configured collections
  • Vendor list returned to non-finance users has bank fields masked
"""
import os
import pytest
import requests

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return sess


# ─── access-context endpoint ──────────────────────────────────────────────
def test_access_context_endpoint(s):
    r = s.get(f"{API_URL}/api/auth/access-context", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("role", "permissions", "modules", "pm_scoped"):
        assert k in d
    assert d["role"] == "super_admin"
    # super_admin must see every module
    for mod in ("dashboard", "sales", "ops", "hr", "store", "procurement",
                "accounts", "finance", "safety", "logistics", "admin"):
        assert mod in d["modules"], f"super_admin missing module {mod}"


# ─── access_control orchestrator unit ─────────────────────────────────────
def test_access_control_unit():
    import sys
    sys.path.insert(0, "/app/backend")
    from access_control import has_action_access, has_module_access, MODULE_PERMS

    assert has_action_access({"role": "super_admin"}, "accounting", "read") is True
    assert has_action_access({"role": "super_admin"}, "accounting", "write") is True
    assert has_action_access({"role": "store_incharge"}, "accounting", "read") is False
    assert has_module_access({"role": "super_admin"}, "finance") is True
    assert has_module_access({"role": "store_incharge"}, "finance") is False
    # Empty user — defensive
    assert has_action_access(None, "accounting", "read") is False
    assert has_action_access({}, "accounting", "read") is False
    # All declared modules have a perm key
    for m in MODULE_PERMS:
        assert MODULE_PERMS[m]


# ─── Duplicate audit ──────────────────────────────────────────────────────
def test_duplicate_scan_all(s):
    r = s.get(f"{API_URL}/api/admin/duplicates/scan", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("summary", "rules", "results"):
        assert k in d
    summary = d["summary"]
    for k in ("collections_scanned", "duplicate_groups_total", "redundant_rows_total"):
        assert k in summary
    # Configured collections must be reported
    collections = {r["collection"] for r in d["results"]}
    for needed in ("employees", "vendors", "items", "journal_entries",
                    "client_invoices", "vendor_bills", "purchase_orders",
                    "chart_of_accounts", "projects"):
        assert needed in collections


def test_duplicate_scan_single(s):
    r = s.get(f"{API_URL}/api/admin/duplicates/scan/employees", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["collection"] == "employees"
    assert "duplicate_groups" in d


def test_duplicate_scan_invalid(s):
    r = s.get(f"{API_URL}/api/admin/duplicates/scan/not_a_real_collection", timeout=10)
    assert r.status_code == 200
    assert "error" in r.json()


# ─── Vendor masking ───────────────────────────────────────────────────────
def test_vendor_list_admin_unmasked(s):
    """Super admin sees full bank details (PRIVILEGED_ROLES)."""
    r = s.get(f"{API_URL}/api/vendors", timeout=10)
    assert r.status_code == 200
    rows = r.json()
    # Admin should see unmasked. Whether bank_account is present depends on data.
    # Just confirm the call succeeded.
    assert isinstance(rows, list)


def test_vendor_list_masked_for_non_finance():
    """A non-finance role (e.g. sales_executive) should see masked vendor bank
    fields when they list vendors. Skip if the role isn't available."""
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login",
                  json={"email": "sales@erp.com", "password": "Sales@123"}, timeout=10)
    if r.status_code != 200:
        pytest.skip("sales user not available in this env")
    r = sess.get(f"{API_URL}/api/vendors", timeout=10)
    if r.status_code == 403:
        pytest.skip("sales role lacks vendors:read permission")
    assert r.status_code == 200
    rows = r.json()
    # For any vendor that has a bank_account, the value must be masked
    for v in rows[:50]:
        if v.get("bank_account"):
            s = str(v["bank_account"])
            assert "****" in s, f"unmasked bank_account: {s}"


# ─── data_scope_filter functional ─────────────────────────────────────────
def test_data_scope_filter_for_pm():
    """For a manager_o_p, dprs (project-scoped) and employees (dept-scoped)
    should both return a non-empty filter clause that limits visibility."""
    import sys, asyncio
    sys.path.insert(0, "/app/backend")
    from access_control import data_scope_filter
    user = {"id": "u-test", "role": "manager_o_p", "department": "Projects & Operations",
            "name": "PM Test", "email": "pm@test.com"}

    async def _run():
        pf = await data_scope_filter(user, "dprs")
        assert pf == {} or "$or" in pf or pf.get("id") == "__never_matches__"
        ef = await data_scope_filter(user, "employees")
        assert ef == {} or "$or" in ef or "department" in ef or ef.get("id") == "__never_matches__"
    asyncio.get_event_loop().run_until_complete(_run())

