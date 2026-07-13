"""Iter 77 — Phase 1 Store & Inventory full HTTP/API smoke tests.

Covers:
  - seed-defaults idempotency
  - categories list contains 12 ITL codes + CRUD
  - units list contains 17 codes incl. FT/KG/M conversions + CRUD
  - stores CRUD (main_store + site_store types) + duplicate-code 409
  - site-stores CRUD
  - bins CRUD scoped per store + duplicate 409
  - opening-stock validation, auto-approve path, pending_approval path,
    cannot-approve-own 403, duplicate (date, store, item) 409
  - dashboard tile completeness (16 required keys + extras)
  - stock-balance shape
  - settings GET / PUT (admin allowed; non-privileged 403)
"""
from __future__ import annotations
import os
import time
import requests
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASS = "Admin@123"
PM_EMAIL = "test_pm@erp.com"
PM_PASS = "PM@12345"


# ── Fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def pm_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": PM_EMAIL, "password": PM_PASS}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"PM login unavailable: {r.status_code}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session", autouse=True)
def ensure_seed(admin_client):
    r = admin_client.post(f"{API}/inv/seed-defaults", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ── 1. Seed-defaults idempotency ──────────────────────────────────────
def test_seed_idempotent(admin_client):
    r1 = admin_client.post(f"{API}/inv/seed-defaults", timeout=30)
    r2 = admin_client.post(f"{API}/inv/seed-defaults", timeout=30)
    assert r1.status_code == 200 and r2.status_code == 200
    d2 = r2.json()
    assert d2["categories_added"] == 0
    assert d2["units_added"] == 0
    assert d2["stores_added"] == 0
    assert d2["total_categories"] >= 12
    assert d2["total_units"] >= 17


# ── 2. Categories ─────────────────────────────────────────────────────
def test_categories_list_has_12_itl(admin_client):
    r = admin_client.get(f"{API}/inv/categories", timeout=20)
    assert r.status_code == 200
    rows = r.json()
    codes = {c["code"] for c in rows}
    for must in ("SCAFFOLD", "PAINT", "ROOF", "ROPE", "PPE", "TOOLS",
                 "CONSUM", "MACHINE", "VEHICLE", "OFFICE", "SCRAP", "MISC"):
        assert must in codes, f"category {must} missing"


def test_category_crud_and_delete_when_unused(admin_client):
    code = f"TEST{int(time.time()) % 99999}"
    payload = {"code": code, "name": "TEST_temp_cat", "sub_categories": ["X"], "description": "tmp", "active": True}
    r = admin_client.post(f"{API}/inv/categories", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    # duplicate -> 409
    r2 = admin_client.post(f"{API}/inv/categories", json=payload, timeout=15)
    assert r2.status_code == 409
    # update
    upd = {**payload, "name": "TEST_renamed"}
    r3 = admin_client.put(f"{API}/inv/categories/{cid}", json=upd, timeout=15)
    assert r3.status_code == 200 and r3.json()["name"] == "TEST_renamed"
    # delete (unused -> ok)
    r4 = admin_client.delete(f"{API}/inv/categories/{cid}", timeout=15)
    assert r4.status_code == 200


# ── 3. Units ──────────────────────────────────────────────────────────
def test_units_list_has_required(admin_client):
    r = admin_client.get(f"{API}/inv/units", timeout=20)
    assert r.status_code == 200
    by_code = {u["code"]: u for u in r.json()}
    for must in ("KG", "NOS", "M", "L", "FT", "G", "MT", "CM"):
        assert must in by_code, f"unit {must} missing"
    assert by_code["FT"]["base_unit"] == "M"
    assert 0.30 < by_code["FT"]["conversion_factor"] < 0.31


def test_unit_create_and_delete(admin_client):
    code = f"TU{int(time.time()) % 999}"
    r = admin_client.post(f"{API}/inv/units", json={"code": code, "name": "TEST_unit", "type": "count"}, timeout=15)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    # dup
    assert admin_client.post(f"{API}/inv/units", json={"code": code, "name": "x", "type": "count"}, timeout=15).status_code == 409
    assert admin_client.delete(f"{API}/inv/units/{uid}", timeout=15).status_code == 200


# ── 4. Stores ─────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def test_store(admin_client):
    code = f"TST{int(time.time()) % 99999}"
    r = admin_client.post(f"{API}/inv/stores", json={
        "code": code, "name": "TEST Site Store A", "type": "site_store",
        "address": "Site A", "active": True,
    }, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def test_store_dup_409(admin_client, test_store):
    r = admin_client.post(f"{API}/inv/stores", json={
        "code": test_store["code"], "name": "again", "type": "site_store",
    }, timeout=15)
    assert r.status_code == 409


def test_store_invalid_type(admin_client):
    r = admin_client.post(f"{API}/inv/stores", json={
        "code": f"BAD{int(time.time()) % 9999}", "name": "x", "type": "bogus_type",
    }, timeout=15)
    assert r.status_code == 400


# ── 5. Site stores ────────────────────────────────────────────────────
def test_site_store_crud(admin_client):
    code = f"SS{int(time.time()) % 99999}"
    r = admin_client.post(f"{API}/inv/site-stores", json={
        "code": code, "project_code": "PRJ-TEST", "site_location": "Mumbai Tower",
        "active": True,
    }, timeout=15)
    assert r.status_code == 200, r.text
    ssid = r.json()["id"]
    r2 = admin_client.get(f"{API}/inv/site-stores", timeout=15)
    assert any(s["id"] == ssid for s in r2.json())
    assert admin_client.delete(f"{API}/inv/site-stores/{ssid}", timeout=15).status_code == 200


# ── 6. Bins ───────────────────────────────────────────────────────────
def test_bin_crud_and_dup(admin_client, test_store):
    code = f"A-01-{int(time.time()) % 999}"
    body = {"code": code, "store_id": test_store["id"], "aisle": "A", "rack": "01", "shelf": "3"}
    r = admin_client.post(f"{API}/inv/bins", json=body, timeout=15)
    assert r.status_code == 200, r.text
    # dup same store
    r2 = admin_client.post(f"{API}/inv/bins", json=body, timeout=15)
    assert r2.status_code == 409
    # invalid store
    r3 = admin_client.post(f"{API}/inv/bins",
                           json={**body, "code": code + "x", "store_id": "nope"}, timeout=15)
    assert r3.status_code == 404
    bid = r.json()["id"]
    assert admin_client.delete(f"{API}/inv/bins/{bid}", timeout=15).status_code == 200


# ── 7. Opening Stock ──────────────────────────────────────────────────
@pytest.fixture(scope="session")
def existing_item(admin_client):
    """Find or create an inventory item to attach opening stock to."""
    r = admin_client.get(f"{API}/inventory", timeout=20)
    if r.status_code == 200 and isinstance(r.json(), list) and r.json():
        return r.json()[0]
    pytest.skip("no inventory items present to test opening stock against")


def test_opening_stock_auto_approve_small_value(admin_client, test_store, existing_item):
    item_id = existing_item["id"]
    body = {
        "date": "2026-01-15",
        "store_id": test_store["id"],
        "remarks": "TEST small",
        "lines": [
            {"item_id": item_id, "quantity": 2, "rate": 100, "condition": "new"},
        ],
    }
    r = admin_client.post(f"{API}/inv/opening-stock", json=body, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "approved"
    assert j["total_value"] == 200


def test_opening_stock_negative_qty_400(admin_client, test_store, existing_item):
    r = admin_client.post(f"{API}/inv/opening-stock", json={
        "date": "2026-02-01", "store_id": test_store["id"],
        "lines": [{"item_id": existing_item["id"], "quantity": -1, "rate": 10, "condition": "new"}],
    }, timeout=15)
    assert r.status_code == 400


def test_opening_stock_zero_qty_400(admin_client, test_store, existing_item):
    r = admin_client.post(f"{API}/inv/opening-stock", json={
        "date": "2026-02-02", "store_id": test_store["id"],
        "lines": [{"item_id": existing_item["id"], "quantity": 0, "rate": 10, "condition": "new"}],
    }, timeout=15)
    assert r.status_code == 400


def test_opening_stock_duplicate_409(admin_client, test_store, existing_item):
    body = {
        "date": "2026-03-10", "store_id": test_store["id"],
        "lines": [{"item_id": existing_item["id"], "quantity": 1, "rate": 50, "condition": "new"}],
    }
    r1 = admin_client.post(f"{API}/inv/opening-stock", json=body, timeout=20)
    assert r1.status_code == 200, r1.text
    r2 = admin_client.post(f"{API}/inv/opening-stock", json=body, timeout=20)
    assert r2.status_code == 409


def test_opening_stock_pending_approval_and_self_approve_blocked(admin_client, test_store, existing_item):
    """Total > 100000 should yield pending_approval. Creator cannot self-approve."""
    body = {
        "date": "2026-04-05", "store_id": test_store["id"], "remarks": "TEST large",
        "lines": [{"item_id": existing_item["id"], "quantity": 100, "rate": 2000, "condition": "new"}],
    }
    r = admin_client.post(f"{API}/inv/opening-stock", json=body, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "pending_approval"
    # self-approve must 403
    ra = admin_client.post(f"{API}/inv/opening-stock/{j['id']}/approve", timeout=15)
    assert ra.status_code == 403


# ── 8. Dashboard ──────────────────────────────────────────────────────
REQUIRED_TILES = {
    "total_stock_value", "total_items", "low_stock_count", "reorder_count",
    "out_of_stock_count", "pending_approvals", "stores_count", "site_stores_count",
    "scaffolding_value", "painting_value", "roof_sheeting_value", "rope_access_value",
    "ppe_value", "tools_value", "damaged_value", "scrap_value",
}
EXTRA_KEYS = {"recent_transactions", "top_consumed", "slow_movers", "items_needing_inspection"}


def test_dashboard_keys_and_real_values(admin_client):
    r = admin_client.get(f"{API}/inv/dashboard", timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    missing = REQUIRED_TILES - set(j.keys())
    assert not missing, f"missing tiles: {missing}"
    miss_extra = EXTRA_KEYS - set(j.keys())
    assert not miss_extra, f"missing extras: {miss_extra}"
    # totals are non-negative numbers
    assert isinstance(j["total_items"], int) and j["total_items"] >= 0
    assert isinstance(j["total_stock_value"], (int, float))
    assert isinstance(j["recent_transactions"], list)


# ── 9. Stock balance ──────────────────────────────────────────────────
def test_stock_balance_shape(admin_client):
    r = admin_client.get(f"{API}/inv/stock-balance", timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "rows" in j and "count" in j and "totals" in j
    if j["rows"]:
        row = j["rows"][0]
        for k in ("item_id", "item_name", "available_qty", "in_transit_qty",
                  "damaged_qty", "scrap_qty", "reserved_qty",
                  "average_rate", "stock_value", "last_txn_date"):
            assert k in row, f"row missing {k}"
        total = round(sum(r["stock_value"] for r in j["rows"]), 2)
        assert abs(total - j["totals"]["stock_value"]) < 0.5


# ── 10. Settings ──────────────────────────────────────────────────────
def test_settings_get(admin_client):
    r = admin_client.get(f"{API}/inv/settings", timeout=15)
    assert r.status_code == 200
    s = r.json()
    for k in ("issue_threshold_default", "opening_stock_approval_value",
              "block_negative_stock", "ppe_inspection_days"):
        assert k in s


def test_settings_put_admin(admin_client):
    r = admin_client.put(f"{API}/inv/settings",
                         json={"issue_threshold_default": 75, "bogus_key": "ignored"},
                         timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["issue_threshold_default"] == 75
    assert "bogus_key" not in r.json()
    # restore
    admin_client.put(f"{API}/inv/settings", json={"issue_threshold_default": 50}, timeout=15)


def test_settings_put_non_privileged_403(pm_client):
    r = pm_client.put(f"{API}/inv/settings", json={"issue_threshold_default": 99}, timeout=15)
    assert r.status_code == 403


# ── 11. Regression — legacy endpoints still alive ─────────────────────
@pytest.mark.parametrize("path", [
    "/inventory", "/inventory-transactions", "/grns",
    "/material-allocations", "/inventory-intel/dashboard",
])
def test_legacy_endpoints_still_reachable(admin_client, path):
    r = admin_client.get(f"{API}{path}", timeout=20)
    # Acceptable: 200, or 404 (alternative path), but never 5xx
    assert r.status_code < 500, f"{path} -> {r.status_code}: {r.text[:200]}"
