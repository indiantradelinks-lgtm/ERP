"""Iteration 191 — Phase-2 paging, shared table views, leaderboard drill-down."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345"}
SAFETY = {"email": "safety@erp.com", "password": "Safety@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def pm():
    try:
        return _login(PM)
    except AssertionError:
        pytest.skip("PM unavailable")


@pytest.fixture(scope="module")
def safety():
    try:
        return _login(SAFETY)
    except AssertionError:
        pytest.skip("Safety officer unavailable")


PAGED_ENDPOINTS = [
    "/store/transactions",
    "/logistics/dispatch-requests",
    "/safety/incidents",
    "/safety/work-permits",
    "/hr/leave-applications",
    "/ra-bills",
]


# ===================== Paged Contract ===================== #
@pytest.mark.parametrize("path", PAGED_ENDPOINTS)
def test_paged_contract(admin, path):
    r = admin.get(f"{API}{path}", params={"page": 1, "page_size": 5}, timeout=60)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    body = r.json()
    assert isinstance(body, dict), f"{path} expected dict got {type(body).__name__}"
    for k in ("rows", "total", "page", "page_size", "pages"):
        assert k in body, f"{path} missing {k}"
    assert body["page"] == 1
    assert body["page_size"] == 5


@pytest.mark.parametrize("path", PAGED_ENDPOINTS)
def test_legacy_array_when_no_page(admin, path):
    r = admin.get(f"{API}{path}", timeout=60)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    body = r.json()
    assert isinstance(body, list), f"{path} legacy path expected list got {type(body).__name__}"


def test_store_txns_filter_inward(admin):
    r = admin.get(f"{API}/store/transactions", params={"txn_type": "inward", "page": 1, "page_size": 10}, timeout=60)
    assert r.status_code == 200
    b = r.json()
    for row in b["rows"]:
        assert (row.get("txn_type") or "").lower() == "inward"


def test_incidents_search(admin):
    r = admin.get(f"{API}/safety/incidents", params={"page": 1, "page_size": 5, "search": "xzzq"}, timeout=60)
    assert r.status_code == 200
    b = r.json()
    assert isinstance(b["rows"], list)


def test_leave_status_filter(admin):
    r = admin.get(f"{API}/hr/leave-applications", params={"status": "pending", "page": 1, "page_size": 20}, timeout=60)
    assert r.status_code == 200
    b = r.json()
    for row in b["rows"]:
        assert row.get("status") == "pending"


def test_ra_bills_status_filter_enrichment(admin):
    r = admin.get(f"{API}/ra-bills", params={"status": "draft", "page": 1, "page_size": 10}, timeout=60)
    assert r.status_code == 200
    b = r.json()
    assert "rows" in b
    for row in b["rows"]:
        assert row.get("status") == "draft"
        # enrichment field must exist (may be null)
        assert "project_manager_name" in row, f"ra-bill row missing project_manager_name: {list(row.keys())}"


def test_work_permit_search(admin):
    r = admin.get(f"{API}/safety/work-permits", params={"page": 1, "page_size": 5, "search": "unlikely_zzz"}, timeout=60)
    assert r.status_code == 200
    b = r.json()
    assert isinstance(b["rows"], list)


def test_dispatch_requests_paged(admin):
    r = admin.get(f"{API}/logistics/dispatch-requests", params={"page": 1, "page_size": 5}, timeout=60)
    assert r.status_code == 200
    b = r.json()
    assert "rows" in b


# ===================== Shared Table Views ===================== #
def test_can_publish_flags(admin, pm, safety):
    a = admin.get(f"{API}/table-views/inventory", timeout=30).json()
    assert a.get("can_publish") is True
    p = pm.get(f"{API}/table-views/inventory", timeout=30).json()
    assert p.get("can_publish") is True
    s = safety.get(f"{API}/table-views/safety_incidents", timeout=30).json()
    assert s.get("can_publish") is False


def test_admin_publish_all_depts_visible_to_pm(admin, pm):
    body = {"name": "TEST_iter191_all", "state": {"search": "abc", "page_size": 25}, "department": "__all__"}
    r = admin.post(f"{API}/table-views/inventory/shared", json=body, timeout=30)
    assert r.status_code == 200, r.text[:200]
    vid = r.json()["id"]
    try:
        pv = pm.get(f"{API}/table-views/inventory", timeout=30).json()
        shared_ids = [s["id"] for s in pv.get("shared", [])]
        assert vid in shared_ids, f"PM should see admin's __all__ shared view: {shared_ids}"
        pm_view = next(s for s in pv["shared"] if s["id"] == vid)
        assert pm_view.get("can_delete") is False
        # PM cannot delete admin's shared view
        d = pm.delete(f"{API}/table-views/inventory/shared/{vid}", timeout=30)
        assert d.status_code == 404
    finally:
        admin.delete(f"{API}/table-views/inventory/shared/{vid}", timeout=30)


def test_pm_publish_uses_own_department(pm):
    body = {"name": "TEST_iter191_pm", "state": {"page_size": 50}}
    r = pm.post(f"{API}/table-views/inventory/shared", json=body, timeout=30)
    assert r.status_code == 200, r.text[:300]
    doc = r.json()
    vid = doc["id"]
    try:
        assert doc.get("department") not in (None, "__all__")
    finally:
        d = pm.delete(f"{API}/table-views/inventory/shared/{vid}", timeout=30)
        assert d.status_code == 200


def test_safety_publish_forbidden(safety):
    r = safety.post(f"{API}/table-views/safety_incidents/shared",
                    json={"name": "TEST_iter191_sf", "state": {}}, timeout=30)
    assert r.status_code == 403


def test_non_super_admin_all_depts_forbidden(pm):
    r = pm.post(f"{API}/table-views/inventory/shared",
                json={"name": "TEST_iter191_all_pm", "state": {}, "department": "__all__"}, timeout=30)
    assert r.status_code == 403


# ===================== Leaderboard Details ===================== #
def test_leaderboard_details_contract(admin):
    lb = admin.get(f"{API}/sales/leaderboard", params={"month": "2026-09"}, timeout=30).json()
    if not lb["rows"]:
        pytest.skip("No sales users to test details for")
    uid = lb["rows"][0]["user_id"]
    r = admin.get(f"{API}/sales/leaderboard/{uid}/details", params={"month": "2026-09"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    b = r.json()
    for k in ("month", "user", "enquiries", "decided_earlier", "quotes"):
        assert k in b, f"missing {k}"
    assert b["month"] == "2026-09"
    for e in b["enquiries"]:
        assert "decided_in_month" in e


def test_leaderboard_details_unknown_user(admin):
    r = admin.get(f"{API}/sales/leaderboard/nonexistent-uid-xxx/details",
                  params={"month": "2026-09"}, timeout=30)
    assert r.status_code == 200
    b = r.json()
    assert b["user"] is None
    assert b["enquiries"] == []
    assert b["quotes"] == []
    assert b["decided_earlier"] == []


def test_leaderboard_details_permission(pm):
    r = pm.get(f"{API}/sales/leaderboard/any-uid/details", params={"month": "2026-09"}, timeout=30)
    assert r.status_code in (200, 403)
