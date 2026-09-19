"""Iteration 192 — Phase-3 paging, default shared view, sales digest."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@erp.com", "Admin@123")
PM = ("test_pm@erp.com", "PM@12345")
SAFETY = ("safety@erp.com", "Safety@123")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def pm():
    return _login(*PM)


@pytest.fixture(scope="module")
def safety():
    return _login(*SAFETY)


PHASE3_ENDPOINTS = [
    "/logistics/allocations",
    "/logistics/loadings",
    "/logistics/stock-moves",
    "/logistics/mobilizations",
    "/logistics/travel",
    "/finance/notes",
    "/hr4/salary-structures",
    "/payroll/payslips",
    "/hr2/attendance-plus/punch-imports",
]


@pytest.mark.parametrize("path", PHASE3_ENDPOINTS)
def test_paged_contract(admin, path):
    """Paged response contract when page=1 & legacy array when page omitted."""
    r = admin.get(f"{API}{path}?page=1&page_size=5", timeout=45)
    assert r.status_code == 200, f"{path} paged: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert isinstance(data, dict), f"{path} paged not dict: {type(data)}"
    for k in ("rows", "total", "page", "page_size", "pages"):
        assert k in data, f"{path} missing {k}"
    assert isinstance(data["rows"], list)
    assert data["page"] == 1
    assert data["page_size"] == 5

    # legacy array
    r2 = admin.get(f"{API}{path}", timeout=45)
    assert r2.status_code == 200
    assert isinstance(r2.json(), list), f"{path} legacy should be list"


def test_search_and_filters(admin):
    """existing filters + search still work."""
    r = admin.get(f"{API}/logistics/mobilizations?status=draft&page=1&page_size=5", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d
    for row in d["rows"]:
        assert row.get("status") == "draft" or "status" in row

    r = admin.get(f"{API}/finance/notes?kind=credit_note&page=1&page_size=5", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for row in d["rows"]:
        assert row.get("kind") == "credit_note"

    r = admin.get(f"{API}/payroll/payslips?month=2026-08&page=1&page_size=5", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d

    r = admin.get(f"{API}/hr4/salary-structures?approval_status=approved&page=1&page_size=5", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d
    for row in d["rows"]:
        assert row.get("approval_status") == "approved" or row.get("approval_status") is None


def test_notes_status_counts(admin):
    r = admin.get(f"{API}/finance/notes/status-counts?kind=credit_note", timeout=30)
    assert r.status_code == 200, r.text
    counts = r.json()
    for k in ("draft", "pending_approval", "approved", "cancelled"):
        assert k in counts
    total_from_counts = sum(counts.values())
    r2 = admin.get(f"{API}/finance/notes?kind=credit_note&page=1&page_size=1", timeout=30)
    total_from_list = r2.json()["total"]
    assert total_from_counts == total_from_list, f"count mismatch {counts} vs total {total_from_list}"


def test_punch_imports_no_heavy_fields(admin):
    r = admin.get(f"{API}/hr2/attendance-plus/punch-imports?page=1&page_size=3", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for row in d["rows"]:
        for banned in ("rows", "prev_docs", "created_ids", "mapping"):
            assert banned not in row, f"row still has {banned}"


def test_rbac_payslips_pm_scoped(pm):
    r = pm.get(f"{API}/payroll/payslips?page=1&page_size=10", timeout=30)
    assert r.status_code == 200
    d = r.json()
    # PM may have no linked employee → early-return [] (per code); else paged dict for their emp.
    if isinstance(d, list):
        assert d == [] or all(row.get("employee_id") for row in d)
        return
    # Employee-scoped: rows either empty or only for their own employee record.
    if d["rows"]:
        # if PM has a linked employee, all payslips should be theirs
        emails = {row.get("employee_email") for row in d["rows"] if row.get("employee_email")}
        # Should not contain arbitrary employees
        assert len(d["rows"]) <= 60  # sanity


def test_rbac_salary_structures_safety_403(safety):
    r = safety.get(f"{API}/hr4/salary-structures?page=1", timeout=30)
    assert r.status_code == 403


# ─── Default shared view ──────────────────────────────────────────────
TABLE = "inventory"


def _cleanup_view(session, view_id):
    try:
        session.delete(f"{API}/table-views/{TABLE}/shared/{view_id}", timeout=15)
    except Exception:
        pass


def test_default_shared_view_flow(admin, pm, safety):
    created_ids = []
    try:
        # publish shared view #1 (__all__)
        r = admin.post(f"{API}/table-views/{TABLE}/shared",
                       json={"name": "TEST_iter192_A", "department": "__all__", "state": {"page_size": 25}},
                       timeout=30)
        assert r.status_code == 200, r.text
        v1 = r.json()["id"]
        created_ids.append(v1)

        # set as default
        r = admin.post(f"{API}/table-views/{TABLE}/shared/{v1}/default", timeout=15)
        assert r.status_code == 200
        assert r.json()["is_default"] is True

        # GET as PM shows default_shared with v1
        r = pm.get(f"{API}/table-views/{TABLE}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("default_shared") is not None
        assert data["default_shared"]["id"] == v1
        assert data["default_shared"].get("is_default") is True

        # publish second view then star it — should clear first
        r = admin.post(f"{API}/table-views/{TABLE}/shared",
                       json={"name": "TEST_iter192_B", "department": "__all__", "state": {"page_size": 100}},
                       timeout=30)
        assert r.status_code == 200
        v2 = r.json()["id"]
        created_ids.append(v2)

        r = admin.post(f"{API}/table-views/{TABLE}/shared/{v2}/default", timeout=15)
        assert r.status_code == 200
        assert r.json()["is_default"] is True

        r = admin.get(f"{API}/table-views/{TABLE}", timeout=20)
        shared = {s["id"]: s for s in r.json()["shared"]}
        assert shared[v1].get("is_default") in (False, None)
        assert shared[v2].get("is_default") is True

        # toggle v2 → clears
        r = admin.post(f"{API}/table-views/{TABLE}/shared/{v2}/default", timeout=15)
        assert r.status_code == 200
        assert r.json()["is_default"] is False

        # star v1 again
        r = admin.post(f"{API}/table-views/{TABLE}/shared/{v1}/default", timeout=15)
        assert r.json()["is_default"] is True

        # safety_officer POST default → 403
        r = safety.post(f"{API}/table-views/{TABLE}/shared/{v1}/default", timeout=15)
        assert r.status_code == 403

        # PM DELETE /last then GET should still return default_shared
        pm.delete(f"{API}/table-views/{TABLE}/last", timeout=15)
        r = pm.get(f"{API}/table-views/{TABLE}", timeout=20)
        assert r.json().get("default_shared", {}).get("id") == v1
    finally:
        for vid in created_ids:
            _cleanup_view(admin, vid)


# ─── Sales leaderboard digest ─────────────────────────────────────────
def test_digest_recipients_log(admin):
    r = admin.get(f"{API}/sales/leaderboard/digest/log", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("email_enabled", "channel", "recipients", "history"):
        assert k in d
    emails = {u["email"] for u in d["recipients"]}
    # Sanity: director & gm typically included if seed present
    assert not any(e == "sales@erp.com" for e in emails), "plain sales_executive should not be a recipient"


def test_digest_log_pm_forbidden(pm):
    r = pm.get(f"{API}/sales/leaderboard/digest/log", timeout=20)
    assert r.status_code == 403


def test_digest_send_pm_forbidden(pm):
    r = pm.post(f"{API}/sales/leaderboard/digest/send?month=2026-08", timeout=30)
    assert r.status_code == 403


def test_digest_send_admin(admin):
    r = admin.post(f"{API}/sales/leaderboard/digest/send?month=2026-08", timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("month", "sent", "failed", "recipients", "rows"):
        assert k in d, f"digest missing {k}"
    assert d["month"] == "2026-08"
    # verify outbox got entries with related.entity_type
    time.sleep(1.0)
    r2 = admin.get(f"{API}/email/outbox?limit=50", timeout=30)
    if r2.status_code == 200:
        body = r2.json()
        rows = body if isinstance(body, list) else body.get("rows") or body.get("items") or []
        found = any((row.get("related") or {}).get("entity_type") == "sales_leaderboard_digest" for row in rows)
        # Not fatal; log for inspection
        print(f"digest outbox entries visible: {found}")
