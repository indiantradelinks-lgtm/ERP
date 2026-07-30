"""Iteration 157 — My Pending Approvals unified inbox tests."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")

ADMIN = ("admin@erp.com", "Admin@123")
PM = ("test_pm@erp.com", "PM@12345")
SALES = ("sales@erp.com", "Sales@123")

ALLOWED_SOURCES = {"approval", "project_request", "expense", "expense_payment",
                   "scaffolding", "dpr", "ra_bill"}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def pm():
    try:
        return _login(*PM)
    except AssertionError:
        pytest.skip("PM login unavailable")


@pytest.fixture(scope="module")
def sales():
    try:
        return _login(*SALES)
    except AssertionError:
        pytest.skip("Sales login unavailable")


# --- shape & admin totals ---
def test_admin_inbox_shape(admin):
    r = admin.get(f"{BASE}/api/my-inbox", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert set(["total", "counts", "items"]).issubset(data.keys())
    assert isinstance(data["items"], list)
    assert data["total"] >= 1
    # source keys allowed
    for k in data["counts"].keys():
        assert k in ALLOWED_SOURCES, f"unexpected source {k}"
    # each item has required fields
    for it in data["items"][:5]:
        assert it.get("source") in ALLOWED_SOURCES
        assert "id" in it and "link" in it


def test_admin_counts_match_items(admin):
    d = admin.get(f"{BASE}/api/my-inbox", timeout=30).json()
    tally = {}
    for it in d["items"]:
        tally[it["source"]] = tally.get(it["source"], 0) + 1
    # counts should equal tally (items list may be capped at 300; counts derived from items)
    for k, v in tally.items():
        assert d["counts"].get(k) == v


# --- role filtering ---
def test_pm_no_forbidden_sources(pm):
    d = pm.get(f"{BASE}/api/my-inbox", timeout=30).json()
    forbidden = {"expense_payment", "ra_bill", "scaffolding"}
    seen = set(d["counts"].keys())
    assert not (seen & forbidden), f"PM saw forbidden sources: {seen & forbidden}"


def test_sales_no_ops_sources(sales):
    d = sales.get(f"{BASE}/api/my-inbox", timeout=30).json()
    forbidden = {"expense_payment", "ra_bill", "scaffolding", "dpr"}
    seen = set(d["counts"].keys())
    assert not (seen & forbidden), f"Sales saw forbidden sources: {seen & forbidden}"


# --- actionable: scaffolding transfer approve loop ---
def test_scaffolding_actionable_end_to_end(admin):
    d = admin.get(f"{BASE}/api/my-inbox", timeout=30).json()
    scaf = [it for it in d["items"] if it["source"] == "scaffolding" and it.get("approve_path")]
    if not scaf:
        pytest.skip("No pending scaffolding transfers in inbox to approve")
    target = scaf[0]
    approve_url = f"{BASE}/api{target['approve_path']}"
    r = admin.post(approve_url, json={"remarks": "iter157 auto-approve"}, timeout=30)
    assert r.status_code in (200, 201), f"approve failed: {r.status_code} {r.text[:200]}"
    # verify disappears
    d2 = admin.get(f"{BASE}/api/my-inbox", timeout=30).json()
    still = [it for it in d2["items"] if it["source"] == "scaffolding" and it["id"] == target["id"]]
    assert not still, "item still in inbox after approve"


def test_unauthenticated_401():
    r = requests.get(f"{BASE}/api/my-inbox", timeout=30)
    assert r.status_code in (401, 403)
