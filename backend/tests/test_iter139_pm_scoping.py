"""
Iteration 139 — PM project scoping + Manager column tests.
Covers:
  - Admin GET /api/projects returns project_manager_name populated for assigned
  - PM /api/projects scoped to their assigned projects only
  - PM /api/projects/{id} 403 on unassigned, 200 on assigned
  - PM cross-module scoping (dprs, measurements, issues, delays, client-instructions,
    extra-works, permits, deployments, purchase_orders, grns)
  - site_engineer projects list does not error (may be empty)
  - Admin regression counts
"""
import os
import requests
import pytest

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def pm_session():
    return _login(PM)


@pytest.fixture(scope="module")
def site_session():
    try:
        return _login(SITE_ENG)
    except AssertionError as e:
        pytest.skip(f"site_engineer login unavailable: {e}")


# -------------------- Manager column / admin baseline --------------------

def test_admin_projects_manager_name_populated(admin_session):
    r = admin_session.get(f"{BASE}/api/projects", timeout=20)
    assert r.status_code == 200
    projects = r.json()
    assert isinstance(projects, list)
    assert len(projects) >= 1, "admin must see at least some projects"
    # Every project that has project_manager_id must also have project_manager_name
    missing = [
        p.get("code")
        for p in projects
        if p.get("project_manager_id") and not p.get("project_manager_name")
    ]
    assert missing == [], f"projects with pm id but no name: {missing}"
    # Spot: at least one project should have a manager name (backfill ran)
    named = [p for p in projects if p.get("project_manager_name")]
    assert len(named) >= 1, "no project with project_manager_name — backfill likely didn't run"
    print(f"admin sees {len(projects)} projects, {len(named)} with PM name")


def test_admin_projects_count_regression(admin_session):
    r = admin_session.get(f"{BASE}/api/projects", timeout=20)
    assert r.status_code == 200
    # sanity: admin should see many; preview had 22
    assert len(r.json()) >= 10


def test_admin_dprs_count_regression(admin_session):
    r = admin_session.get(f"{BASE}/api/dprs", timeout=20)
    assert r.status_code == 200
    print(f"admin dprs count = {len(r.json())}")
    assert len(r.json()) >= 1


# -------------------- PM scoping — projects --------------------

def test_pm_projects_scoped(pm_session, admin_session):
    r = pm_session.get(f"{BASE}/api/projects", timeout=20)
    assert r.status_code == 200
    pm_projects = r.json()
    assert isinstance(pm_projects, list)
    admin_projects = admin_session.get(f"{BASE}/api/projects", timeout=20).json()
    assert len(pm_projects) < len(admin_projects), (
        f"PM should see fewer than admin: pm={len(pm_projects)} admin={len(admin_projects)}"
    )
    codes = {p.get("code") or p.get("project_code") for p in pm_projects}
    print(f"PM sees projects: {codes}")
    # Expect the known assigned project code from the review
    assert "PRJ-2025-01" in codes, f"expected PRJ-2025-01 in PM scope, got {codes}"


def test_pm_project_get_assigned_200_unassigned_403(pm_session, admin_session):
    admin_projects = admin_session.get(f"{BASE}/api/projects", timeout=20).json()
    pm_projects = pm_session.get(f"{BASE}/api/projects", timeout=20).json()
    pm_ids = {p.get("id") for p in pm_projects}
    # Pick an assigned one
    assigned = next(iter(pm_projects), None)
    assert assigned, "PM has no assigned projects — cannot test 200"
    r_ok = pm_session.get(f"{BASE}/api/projects/{assigned['id']}", timeout=15)
    assert r_ok.status_code == 200, f"expected 200 for assigned project, got {r_ok.status_code}"

    # Pick an unassigned one
    unassigned = next((p for p in admin_projects if p.get("id") not in pm_ids), None)
    assert unassigned, "no unassigned project available for 403 check"
    r_forbid = pm_session.get(f"{BASE}/api/projects/{unassigned['id']}", timeout=15)
    assert r_forbid.status_code == 403, (
        f"expected 403 for unassigned project {unassigned.get('project_code')}, got {r_forbid.status_code}"
    )


# -------------------- PM scoping — cross-module list endpoints --------------------

@pytest.mark.parametrize("path", [
    "/api/dprs",
    "/api/proj-phase3/measurements",
    "/api/proj-phase3/issues",
    "/api/proj-phase3/delays",
    "/api/proj-phase3/client-instructions",
    "/api/proj-phase3/extra-works",
    "/api/proj-phase3/permits",
])
def test_pm_dedicated_list_endpoints_scoped(pm_session, admin_session, path):
    r_pm = pm_session.get(f"{BASE}{path}", timeout=20)
    assert r_pm.status_code == 200, f"PM {path} -> {r_pm.status_code} {r_pm.text[:200]}"
    pm_rows = r_pm.json() if isinstance(r_pm.json(), list) else r_pm.json().get("items", [])
    assert isinstance(pm_rows, list)

    # PM's allowed project ids
    pm_projects = pm_session.get(f"{BASE}/api/projects", timeout=15).json()
    allowed_ids = {p.get("id") for p in pm_projects}

    bad = [
        row for row in pm_rows
        if row.get("project_id") and row["project_id"] not in allowed_ids
    ]
    assert bad == [], f"{path}: PM sees rows outside scope: {[r.get('id') for r in bad][:5]}"

    r_admin = admin_session.get(f"{BASE}{path}", timeout=20)
    if r_admin.status_code == 200:
        admin_rows = r_admin.json() if isinstance(r_admin.json(), list) else r_admin.json().get("items", [])
        print(f"{path}: admin={len(admin_rows)} pm={len(pm_rows)}")
        assert len(pm_rows) <= len(admin_rows)


@pytest.mark.parametrize("path", [
    "/api/deployments",
    "/api/purchase-orders",
    "/api/grn",
])
def test_pm_crud_scoped_lists(pm_session, admin_session, path):
    r_pm = pm_session.get(f"{BASE}{path}", timeout=20)
    if r_pm.status_code == 404:
        pytest.skip(f"{path} not found")
    assert r_pm.status_code == 200, f"PM {path} -> {r_pm.status_code} {r_pm.text[:200]}"
    body = r_pm.json()
    pm_rows = body if isinstance(body, list) else body.get("items", [])
    assert isinstance(pm_rows, list)

    r_admin = admin_session.get(f"{BASE}{path}", timeout=20)
    admin_body = r_admin.json()
    admin_rows = admin_body if isinstance(admin_body, list) else admin_body.get("items", [])
    print(f"{path}: admin={len(admin_rows)} pm={len(pm_rows)}")
    # PM must see <= admin
    assert len(pm_rows) <= len(admin_rows), f"{path}: PM saw more rows than admin"

    # Verify each row's 'project' string matches PM's allowed codes/names (when non-empty)
    if pm_rows:
        pm_projects = pm_session.get(f"{BASE}/api/projects", timeout=15).json()
        allowed_tokens = set()
        for p in pm_projects:
            for k in ("code", "project_code", "project_name", "name", "id"):
                if p.get(k):
                    allowed_tokens.add(str(p[k]))
        for row in pm_rows:
            proj = row.get("project") or row.get("project_id") or row.get("project_code")
            if proj:
                assert str(proj) in allowed_tokens or any(t in str(proj) for t in allowed_tokens), (
                    f"{path}: row project {proj!r} not in PM scope tokens"
                )


# -------------------- site_engineer must not error --------------------

def test_site_engineer_projects_no_error(site_session):
    r = site_session.get(f"{BASE}/api/projects", timeout=20)
    assert r.status_code == 200, f"site_engineer /api/projects returned {r.status_code}"
    data = r.json()
    assert isinstance(data, list)
    print(f"site_engineer sees {len(data)} projects (empty ok)")
