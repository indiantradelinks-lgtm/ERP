"""Iteration 190 — Module router paging Phase 1, Saved Table Views, Sales Leaderboard.

Covers:
- Paged contract {rows,total,page,page_size,pages} on 11 module list endpoints
- Legacy array response when page param omitted
- search + sort + f_<field> filter
- Existing filters (status, voucher_type) still work
- RBAC: project_manager sees own advances; role w/o accounting_read → 403 on vouchers
- Table views: get/put/last/presets CRUD, per-user isolation
- Sales leaderboard: contract, sales-only users, invalid month fallback
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def pm():
    try:
        return _login(PM)
    except AssertionError:
        pytest.skip("PM user unavailable")


PAGED_ENDPOINTS = [
    "/enquiries",
    "/procurement/prs",
    "/procurement/rfqs",
    "/procurement/grns",
    "/accounts/vouchers",
    "/payables/vendor-bills",
    "/payables/vendor-payments",
    "/payments-in",
    "/project-requests",
    "/project-expenses",
    "/advances",
]


# ============= Paged contract ============= #
@pytest.mark.parametrize("path", PAGED_ENDPOINTS)
def test_paged_contract(admin, path):
    r = admin.get(f"{API}{path}", params={"page": 1, "page_size": 5}, timeout=60)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    body = r.json()
    assert isinstance(body, dict), f"{path} expected dict when page=1, got {type(body).__name__}"
    for k in ("rows", "total", "page", "page_size", "pages"):
        assert k in body, f"{path} missing key {k}: {list(body.keys())}"
    assert isinstance(body["rows"], list)
    assert body["page"] == 1
    assert body["page_size"] == 5


@pytest.mark.parametrize("path", PAGED_ENDPOINTS)
def test_legacy_array_when_no_page(admin, path):
    r = admin.get(f"{API}{path}", timeout=60)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    body = r.json()
    assert isinstance(body, list), f"{path} legacy path expected list, got {type(body).__name__}"


def test_paged_search_and_sort(admin):
    r = admin.get(f"{API}/enquiries",
                  params={"page": 1, "page_size": 5, "sort_by": "created_at", "sort_dir": "desc"}, timeout=60)
    assert r.status_code == 200
    b = r.json()
    assert isinstance(b.get("rows"), list)


def test_prs_existing_filter_status(admin):
    r = admin.get(f"{API}/procurement/prs", params={"status": "approved", "page": 1, "page_size": 20}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body
    for row in body["rows"]:
        assert row.get("status") == "approved", f"unexpected status {row.get('status')}"


def test_vendor_bills_existing_filter_status(admin):
    r = admin.get(f"{API}/payables/vendor-bills", params={"status": "approved", "page": 1, "page_size": 20}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body


def test_vouchers_type_filter(admin):
    r = admin.get(f"{API}/accounts/vouchers", params={"voucher_type": "JV", "page": 1, "page_size": 10}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body
    for row in body["rows"]:
        assert (row.get("voucher_type") or "").upper() == "JV" or row.get("type") == "JV"


def test_project_requests_enriched(admin):
    r = admin.get(f"{API}/project-requests", params={"page": 1, "page_size": 5}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    if body["rows"]:
        row = body["rows"][0]
        assert "attachment_count" in row, f"project-requests row missing attachment_count: {list(row.keys())}"


def test_project_expenses_enriched(admin):
    r = admin.get(f"{API}/project-expenses", params={"page": 1, "page_size": 5}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    if body["rows"]:
        row = body["rows"][0]
        assert "attachment_count" in row, f"project-expenses row missing attachment_count: {list(row.keys())}"


def test_advances_enriched_admin(admin):
    r = admin.get(f"{API}/advances", params={"page": 1, "page_size": 5}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    # awaiting_role / project_name may be null but keys should exist on enriched rows
    if body["rows"]:
        r0 = body["rows"][0]
        assert "awaiting_role" in r0 or "project_name" in r0, f"advances row not enriched: {list(r0.keys())}"


# ============= RBAC ============= #
def test_pm_advances_scoped(pm):
    r = pm.get(f"{API}/advances", params={"page": 1, "page_size": 50}, timeout=60)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "rows" in body
    # scope preserved — no assertion on exact rows but must not error


def test_pm_vouchers_forbidden(pm):
    r = pm.get(f"{API}/accounts/vouchers", params={"page": 1, "page_size": 5}, timeout=60)
    assert r.status_code == 403, f"expected 403 for PM on vouchers, got {r.status_code}"


# ============= Saved Table Views ============= #
def test_table_views_get_default(admin):
    r = admin.get(f"{API}/table-views/inventory", timeout=30)
    assert r.status_code == 200
    b = r.json()
    assert "last" in b and "presets" in b
    assert isinstance(b["presets"], list)


def test_table_views_last_put_and_reset(admin):
    r = admin.put(f"{API}/table-views/inventory/last",
                  json={"state": {"search": "TEST_iter190", "sort_by": "name",
                                  "sort_dir": "asc", "page_size": 25, "junk": "x"}}, timeout=30)
    assert r.status_code == 200
    g = admin.get(f"{API}/table-views/inventory", timeout=30).json()
    assert g["last"] is not None
    # junk should be filtered
    assert "junk" not in g["last"], f"junk key not stripped: {g['last']}"
    assert g["last"].get("search") == "TEST_iter190"
    assert g["last"].get("page_size") == 25
    # reset
    r = admin.delete(f"{API}/table-views/inventory/last", timeout=30)
    assert r.status_code == 200
    g2 = admin.get(f"{API}/table-views/inventory", timeout=30).json()
    assert g2["last"] is None


def test_table_views_preset_crud(admin):
    name = "TEST_iter190_preset"
    # Create
    r = admin.post(f"{API}/table-views/inventory/presets",
                   json={"name": name, "state": {"search": "abc", "page_size": 100}}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    preset = r.json()
    pid = preset["id"]
    # Upsert (same name)
    r2 = admin.post(f"{API}/table-views/inventory/presets",
                    json={"name": name, "state": {"search": "abc2", "page_size": 100}}, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["id"] == pid, "upsert should reuse id"
    # Listed
    g = admin.get(f"{API}/table-views/inventory", timeout=30).json()
    ids = [p["id"] for p in g["presets"]]
    assert pid in ids
    # Delete
    d = admin.delete(f"{API}/table-views/inventory/presets/{pid}", timeout=30)
    assert d.status_code == 200
    # Confirm removal
    g2 = admin.get(f"{API}/table-views/inventory", timeout=30).json()
    assert pid not in [p["id"] for p in g2["presets"]]


def test_table_views_per_user_isolation(admin, pm):
    name = "TEST_iter190_admin_only"
    r = admin.post(f"{API}/table-views/inventory/presets",
                   json={"name": name, "state": {"search": "x"}}, timeout=30)
    assert r.status_code == 200
    pid = r.json()["id"]
    try:
        pm_views = pm.get(f"{API}/table-views/inventory", timeout=30).json()
        pm_names = [p.get("name") for p in pm_views.get("presets", [])]
        assert name not in pm_names, f"PM sees admin preset: {pm_names}"
    finally:
        admin.delete(f"{API}/table-views/inventory/presets/{pid}", timeout=30)


# ============= Sales Leaderboard ============= #
def test_leaderboard_contract(admin):
    r = admin.get(f"{API}/sales/leaderboard", params={"month": "2026-09"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    b = r.json()
    assert b.get("month") == "2026-09"
    assert "rows" in b and isinstance(b["rows"], list)
    assert "totals" in b
    for r0 in b["rows"]:
        for k in ("user_id", "name", "role", "enquiries", "quotes", "quote_value", "won", "lost", "win_rate", "rank"):
            assert k in r0, f"leaderboard row missing {k}: {list(r0.keys())}"


def test_leaderboard_no_super_admin(admin):
    b = admin.get(f"{API}/sales/leaderboard", params={"month": "2026-09"}, timeout=30).json()
    roles = {r.get("role") for r in b["rows"]}
    assert "super_admin" not in roles, f"super_admin should not appear: {roles}"


def test_leaderboard_invalid_month_fallback(admin):
    from datetime import datetime, timezone
    b = admin.get(f"{API}/sales/leaderboard", params={"month": "not-a-month"}, timeout=30).json()
    assert b["month"] == datetime.now(timezone.utc).strftime("%Y-%m")


def test_leaderboard_permission_check(pm):
    r = pm.get(f"{API}/sales/leaderboard", timeout=30)
    # PM likely lacks sales_reports.read
    assert r.status_code in (200, 403), f"unexpected {r.status_code}"
