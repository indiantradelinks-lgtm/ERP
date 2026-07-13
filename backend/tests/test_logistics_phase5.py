"""Iter 137 · Logistics Phase 5 backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASS = "Admin@123"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# Phase 5: Dashboard v2
def test_dashboard_v2(client):
    r = client.get(f"{BASE_URL}/api/logistics/dashboard-v2", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    cards = d.get("cards", {})
    assert len(cards) >= 27, f"Expected >=27 cards, got {len(cards)}"
    for k in ("fuel_cost_this_month", "vehicle_expense_this_month", "freight_cost_this_month"):
        assert k in cards, f"missing {k}"
        assert isinstance(cards[k], (int, float))
    assert "project_cost_top5" in d
    assert "cost_trend" in d
    assert isinstance(d["project_cost_top5"], list)
    assert isinstance(d["cost_trend"], list)


# Phase 5: Reports list
def test_reports_list_30(client):
    r = client.get(f"{BASE_URL}/api/logistics/reports/list", timeout=30)
    assert r.status_code == 200
    lst = r.json()
    assert len(lst) == 30, f"Expected 30, got {len(lst)}"
    for item in lst:
        assert "key" in item and "label" in item and "columns" in item
        assert isinstance(item["columns"], list)


# Phase 5: Individual reports
@pytest.mark.parametrize("key", ["vehicle_master", "driver_master", "dispatch_requests", "fuel_entries", "freight_cost"])
def test_report_by_key(client, key):
    r = client.get(f"{BASE_URL}/api/logistics/reports/{key}", timeout=30)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert "rows" in d and "count" in d and "columns" in d
    assert isinstance(d["rows"], list)
    assert d["count"] == len(d["rows"])


def test_report_filters(client):
    r = client.get(
        f"{BASE_URL}/api/logistics/reports/dispatch_requests",
        params={"from": "2024-01-01", "to": "2026-12-31", "status": "draft"},
        timeout=30,
    )
    assert r.status_code == 200
    d = r.json()
    for row in d["rows"]:
        assert row.get("status") == "draft"


def test_report_xlsx_export(client):
    r = client.get(f"{BASE_URL}/api/logistics/reports/dispatch_requests/export.xlsx", timeout=60)
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "spreadsheetml" in ct, f"bad content-type: {ct}"
    assert len(r.content) > 3000, f"xlsx too small: {len(r.content)}"
    with open("/tmp/dispatch_requests.xlsx", "wb") as f:
        f.write(r.content)


# Phase 5: Closure workflow
@pytest.fixture(scope="module")
def dr_id(client):
    r = client.get(f"{BASE_URL}/api/logistics/dispatch-requests", timeout=30)
    assert r.status_code == 200
    items = r.json()
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    assert items, "no dispatch requests"
    return items[0]["id"]


def test_closure_checklist(client, dr_id):
    r = client.get(f"{BASE_URL}/api/logistics/dispatch-requests/{dr_id}/closure-checklist", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert len(d["checklist"]) == 15
    assert "can_close" in d and isinstance(d["can_close"], bool)
    for it in d["checklist"]:
        assert "key" in it and "label" in it and isinstance(it["done"], bool)


def test_close_trip_rejects_when_missing(client, dr_id):
    # If can_close is true, we can't test rejection here; but usually not all mandatory items are done.
    check = client.get(f"{BASE_URL}/api/logistics/dispatch-requests/{dr_id}/closure-checklist", timeout=30).json()
    if check.get("can_close"):
        pytest.skip("This DR is actually closable — skipping negative test")
    r = client.post(
        f"{BASE_URL}/api/logistics/dispatch-requests/{dr_id}/close",
        json={"reason": "test"}, timeout=30,
    )
    assert r.status_code == 400
    assert "Cannot close" in r.text or "cannot close" in r.text.lower()


def test_reopen_trip_rejects_non_closed(client, dr_id):
    r = client.post(
        f"{BASE_URL}/api/logistics/dispatch-requests/{dr_id}/reopen",
        json={"reason": "test"}, timeout=30,
    )
    # DR status is not closed → should be 400
    assert r.status_code == 400
    assert "closed" in r.text.lower()


# Phase 4 regression endpoints
@pytest.mark.parametrize("path", [
    "/api/logistics/finance-approvals",
    "/api/logistics/vendor-payable",
    "/api/logistics/cost-allocations",
])
def test_phase4_endpoints(client, path):
    r = client.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"


# Phase 1-4 regression endpoints
@pytest.mark.parametrize("path", [
    "/api/logistics/dashboard",
    "/api/logistics/vehicles",
    "/api/logistics/drivers",
    "/api/logistics/dispatch-requests",
    "/api/logistics/fuel-entries",
    "/api/logistics/vendor-bills",
    "/api/logistics/audit-log",
])
def test_regression_endpoints(client, path):
    r = client.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
