"""Iteration 189 — server-side pagination / search / sort / filter tests.

Tests cover:
- Generic CRUD list endpoint pagination contract
- /api/approvals, /api/admin/audit-logs, /api/admin/login-activity, /api/files, /api/onedrive/queue paged
- RBAC still enforced
- CRUD via generic endpoints (inventory)
- Attachments persistence across sessions
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login {creds['email']} -> {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def pm_sess():
    try:
        return _login(PM)
    except AssertionError:
        pytest.skip("PM user not available")


# ---------- Paged contract ----------
PAGED_RESOURCES = [
    "inventory", "projects", "attendance", "purchase-orders",
    "quotations", "safety-reports", "assets", "ptws", "deployments",
]


@pytest.mark.parametrize("res", PAGED_RESOURCES)
def test_paged_contract(admin_sess, res):
    r = admin_sess.get(f"{BASE_URL}/api/{res}?page=1&page_size=50", timeout=30)
    assert r.status_code == 200, f"{res}: {r.status_code} {r.text[:200]}"
    d = r.json()
    assert isinstance(d, dict), f"{res}: expected dict, got {type(d).__name__}"
    for k in ("rows", "total", "page", "page_size", "pages"):
        assert k in d, f"{res}: missing key {k}"
    assert isinstance(d["rows"], list)
    assert len(d["rows"]) <= 50, f"{res}: rows={len(d['rows'])}"
    assert d["page"] == 1 and d["page_size"] == 50


def test_employees_paged_master(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/employees?master=employee&page=1&page_size=50", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, dict) and "rows" in d and len(d["rows"]) <= 50


def test_legacy_list_still_array(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/inventory", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, list), f"legacy inventory should be array, got {type(d).__name__}"


def test_page2_diff_from_page1(admin_sess):
    r1 = admin_sess.get(f"{BASE_URL}/api/inventory?page=1&page_size=5", timeout=30).json()
    r2 = admin_sess.get(f"{BASE_URL}/api/inventory?page=2&page_size=5", timeout=30).json()
    if r1.get("total", 0) < 6:
        pytest.skip("not enough inventory records for page-2 comparison")
    ids1 = {r.get("id") for r in r1["rows"]}
    ids2 = {r.get("id") for r in r2["rows"]}
    assert ids1.isdisjoint(ids2), "page 1 and page 2 overlap"


def test_sort_asc_name(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/inventory?page=1&page_size=50&sort_by=name&sort_dir=asc", timeout=30).json()
    names = [row.get("name") or "" for row in r["rows"] if row.get("name")]
    assert names == sorted(names), "inventory not sorted ascending by name (case-sensitive)"


def test_search_filter(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/inventory?page=1&page_size=50&search=pipe&search_keys=name,code", timeout=30).json()
    for row in r["rows"]:
        blob = f"{row.get('name','')} {row.get('code','')}".lower()
        assert "pipe" in blob, f"row does not match 'pipe': {row.get('name')}/{row.get('code')}"


def test_fields_projection(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/inventory?page=1&page_size=5&fields=id,code,name", timeout=30).json()
    for row in r["rows"]:
        extra = set(row.keys()) - {"id", "code", "name"}
        assert not extra, f"unexpected fields: {extra}"


# ---------- Admin lists ----------
def test_audit_logs_paged(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/admin/audit-logs?page=1&page_size=20", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, dict) and "rows" in d and "total" in d


def test_audit_logs_legacy(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/admin/audit-logs?limit=50", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_login_activity_paged(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/admin/login-activity?page=1&page_size=10", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, dict) and "rows" in d


def test_login_activity_legacy(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/admin/login-activity", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_files_paged(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/files?page=1&page_size=10", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, dict) and "rows" in d


def test_onedrive_queue_paged(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/admin/onedrive/queue?page=1&page_size=10", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, dict) and "rows" in d


def test_onedrive_health(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/admin/onedrive/health", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


# ---------- Approvals ----------
def test_approvals_paged(admin_sess):
    r = admin_sess.get(f"{BASE_URL}/api/approvals?page=1&page_size=10", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, dict) and "rows" in d


# ---------- RBAC ----------
def test_pm_scoped_projects(admin_sess, pm_sess):
    a = admin_sess.get(f"{BASE_URL}/api/projects?page=1&page_size=200", timeout=30).json()
    p = pm_sess.get(f"{BASE_URL}/api/projects?page=1&page_size=200", timeout=30).json()
    # PM should see <= admin total (project-scoped visibility)
    assert p.get("total", 0) <= a.get("total", 0)


def test_pm_forbidden_on_admin(pm_sess):
    r = pm_sess.get(f"{BASE_URL}/api/admin/audit-logs?page=1&page_size=5", timeout=30)
    assert r.status_code in (401, 403), f"PM should not see audit logs; got {r.status_code}"


# ---------- CRUD ----------
def test_inventory_crud(admin_sess):
    payload = {"name": "TEST_iter189_widget", "code": "TEST_I189",
               "category": "material", "unit": "pcs"}
    r = admin_sess.post(f"{BASE_URL}/api/inventory", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create: {r.status_code} {r.text[:200]}"
    created = r.json()
    assert created.get("name") == payload["name"]
    iid = created["id"]
    try:
        g = admin_sess.get(f"{BASE_URL}/api/inventory/{iid}", timeout=30)
        assert g.status_code == 200 and g.json().get("id") == iid

        u = admin_sess.put(f"{BASE_URL}/api/inventory/{iid}",
                           json={"name": "TEST_iter189_widget_v2"}, timeout=30)
        assert u.status_code in (200, 204), f"update: {u.status_code}"

        # Should appear on page 1 sorted by created_at desc
        lst = admin_sess.get(f"{BASE_URL}/api/inventory?page=1&page_size=50&sort_by=created_at&sort_dir=desc",
                             timeout=30).json()
        ids = [row.get("id") for row in lst["rows"]]
        assert iid in ids, "newly created inventory not on page 1"
    finally:
        d = admin_sess.delete(f"{BASE_URL}/api/inventory/{iid}", timeout=30)
        assert d.status_code in (200, 204)


# ---------- Attachments persistence ----------
def test_attachment_persist_reload(admin_sess):
    # Grab any project id
    projs = admin_sess.get(f"{BASE_URL}/api/projects?page=1&page_size=1", timeout=30).json()
    if not projs.get("rows"):
        pytest.skip("no projects")
    pid = projs["rows"][0]["id"]

    files = {"file": ("iter189.txt", io.BytesIO(b"iter189-attach-test"), "text/plain")}
    data = {"folder": "projects", "parent_type": "projects", "parent_id": pid}
    up = admin_sess.post(f"{BASE_URL}/api/uploads", files=files, data=data, timeout=60)
    assert up.status_code in (200, 201), f"upload: {up.status_code} {up.text[:200]}"
    rec = up.json()
    fid = rec.get("id") or rec.get("file_id") or rec.get("_id")
    assert fid, f"upload response missing id: {rec}"

    # Legacy list by parent
    lst = admin_sess.get(f"{BASE_URL}/api/files?parent_type=projects&parent_id={pid}", timeout=30).json()
    assert isinstance(lst, list) and any(f.get("id") == fid for f in lst), "uploaded file not listed"

    # Re-login with fresh cookie jar
    fresh = _login(ADMIN)
    lst2 = fresh.get(f"{BASE_URL}/api/files?parent_type=projects&parent_id={pid}", timeout=30).json()
    assert any(f.get("id") == fid for f in lst2), "attachment lost after re-login"

    # Download
    dl = admin_sess.get(f"{BASE_URL}/api/files/{fid}/download", timeout=30)
    assert dl.status_code == 200 and dl.content, "download failed"

    # Cleanup
    admin_sess.delete(f"{BASE_URL}/api/files/{fid}", timeout=30)
