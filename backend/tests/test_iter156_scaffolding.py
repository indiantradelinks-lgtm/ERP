"""Iter 156 — Scaffolding Inventory & Delivery Challan Center backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def pm():
    return _login("test_pm@erp.com", "PM@12345")


@pytest.fixture(scope="module")
def state():
    return {}


# ── Catalog / locations ────────────────────────────────────────────
def test_locations(admin):
    r = admin.get(f"{API}/scaffolding/locations")
    assert r.status_code == 200
    locs = r.json()
    assert isinstance(locs, list) and len(locs) >= 2
    assert any(l["type"] == "store" for l in locs)
    assert any(l["type"] == "project" for l in locs)


def test_create_item_auto_code(admin, state):
    r = admin.post(f"{API}/scaffolding/items",
                   json={"name": "TEST_Iter156 Coupler", "unit": "Nos"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["code"].startswith("SCF-"), d
    assert d["name"] == "TEST_Iter156 Coupler"
    state["item_id"] = d["id"]
    state["item_code"] = d["code"]


def test_summary(admin):
    r = admin.get(f"{API}/scaffolding/summary")
    assert r.status_code == 200
    d = r.json()
    for k in ("items_tracked", "locations", "total_qty",
              "pending_approvals", "in_transit_challans", "open_transfers"):
        assert k in d


# ── Opening stock ──────────────────────────────────────────────────
def test_opening_stock_and_matrix(admin, state):
    locs = admin.get(f"{API}/scaffolding/locations").json()
    store = next(l for l in locs if l["type"] == "store")
    project = next(l for l in locs if l["type"] == "project")
    state["store_id"] = store["id"]
    state["store_name"] = store["name"]
    state["project_id"] = project["id"]
    state["project_name"] = project["name"]

    r = admin.post(f"{API}/scaffolding/opening-stock",
                   json={"item_id": state["item_id"], "location_id": store["id"], "quantity": 200})
    assert r.status_code == 200, r.text
    assert r.json()["quantity"] == 200

    r = admin.get(f"{API}/scaffolding/stock-matrix")
    assert r.status_code == 200
    m = r.json()
    it = next((x for x in m["items"] if x["item_id"] == state["item_id"]), None)
    assert it is not None
    assert it["by_location"].get(store["id"]) == 200
    assert "in_transit" in it


# ── Transfer create + guards ───────────────────────────────────────
def test_transfer_same_location_400(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers", json={
        "from_location_id": state["store_id"], "to_location_id": state["store_id"],
        "lines": [{"item_id": state["item_id"], "quantity": 5}]})
    assert r.status_code == 400


def test_transfer_insufficient_400(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers", json={
        "from_location_id": state["store_id"], "to_location_id": state["project_id"],
        "lines": [{"item_id": state["item_id"], "quantity": 99999}]})
    assert r.status_code == 400
    assert "insufficient" in r.text.lower() or "stock" in r.text.lower()


def test_create_transfer_ok(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers", json={
        "from_location_id": state["store_id"], "to_location_id": state["project_id"],
        "lines": [{"item_id": state["item_id"], "quantity": 100}],
        "remarks": "TEST_Iter156"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "pending_approval"
    assert d["transfer_no"].startswith("MTN-")
    state["transfer_id"] = d["id"]


# ── Approval role gating ───────────────────────────────────────────
def test_challan_on_pending_400(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer_id']}/challans", json={
        "vehicle_no": "AA00AA0000",
        "lines": [{"item_id": state["item_id"], "quantity": 10}]})
    assert r.status_code == 400


def test_pm_cannot_approve_403(pm, state):
    r = pm.post(f"{API}/scaffolding/transfers/{state['transfer_id']}/approve", json={})
    # 403 forbidden expected (PM has write, not in APPROVE_ROLES)
    assert r.status_code == 403, r.text


def test_admin_approves(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer_id']}/approve",
                   json={"remarks": "ok"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


# ── Challans ───────────────────────────────────────────────────────
def test_challan_over_qty_400(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer_id']}/challans", json={
        "vehicle_no": "AA00AA0001",
        "lines": [{"item_id": state["item_id"], "quantity": 500}]})
    assert r.status_code == 400


def test_first_challan_partial(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer_id']}/challans", json={
        "vehicle_no": "AA00AA1111", "driver_name": "TEST Driver",
        "lines": [{"item_id": state["item_id"], "quantity": 60}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "dispatched"
    assert d["challan_no"].startswith("DC-")
    state["challan1"] = d["id"]

    tr = admin.get(f"{API}/scaffolding/transfers", params={"status": "partially_dispatched"}).json()
    assert any(t["id"] == state["transfer_id"] for t in tr)


def test_stock_matrix_in_transit(admin, state):
    m = admin.get(f"{API}/scaffolding/stock-matrix").json()
    it = next(x for x in m["items"] if x["item_id"] == state["item_id"])
    # Source deducted 60 (200-60=140 left), and 60 in-transit
    assert it["by_location"].get(state["store_id"]) == 140
    assert it["in_transit"] >= 60


def test_second_challan_completes_dispatch(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer_id']}/challans", json={
        "vehicle_no": "AA00AA2222",
        "lines": [{"item_id": state["item_id"], "quantity": 40}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "dispatched"
    state["challan2"] = d["id"]
    tr = admin.get(f"{API}/scaffolding/transfers").json()
    row = next(t for t in tr if t["id"] == state["transfer_id"])
    assert row["status"] == "dispatched"


def test_challan_pdf(admin, state):
    r = admin.get(f"{API}/scaffolding/challans/{state['challan1']}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


def test_receive_first_partial(admin, state):
    r = admin.post(f"{API}/scaffolding/challans/{state['challan1']}/receive",
                   json={"receiver_name": "TEST Receiver"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received"
    tr = next(t for t in admin.get(f"{API}/scaffolding/transfers").json()
              if t["id"] == state["transfer_id"])
    assert tr["status"] == "partially_received"


def test_receive_second_completes(admin, state):
    r = admin.post(f"{API}/scaffolding/challans/{state['challan2']}/receive",
                   json={"receiver_name": "TEST Receiver 2"})
    assert r.status_code == 200
    tr = next(t for t in admin.get(f"{API}/scaffolding/transfers").json()
              if t["id"] == state["transfer_id"])
    assert tr["status"] == "completed"

    m = admin.get(f"{API}/scaffolding/stock-matrix").json()
    it = next(x for x in m["items"] if x["item_id"] == state["item_id"])
    # 200 - 100 dispatched = 100 at store; 100 received at project
    assert it["by_location"].get(state["store_id"]) == 100
    assert it["by_location"].get(state["project_id"]) == 100


# ── Exports ────────────────────────────────────────────────────────
def test_export_stock_xlsx(admin):
    r = admin.get(f"{API}/scaffolding/export.xlsx", params={"kind": "stock"})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_export_challans_pdf(admin):
    r = admin.get(f"{API}/scaffolding/export.pdf", params={"kind": "challans"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")


# ── Migrate main store — role gating ───────────────────────────────
def test_migrate_role_gated(admin):
    # Admin can hit endpoint (idempotent — skips items with existing scaf_stock)
    r = admin.post(f"{API}/scaffolding/migrate-main-store", json={})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "migrated" in d and "skipped" in d


# ── Regression: unrelated pages still respond ──────────────────────
@pytest.mark.parametrize("path", [
    "/store-transactions", "/inventory", "/projects"])
def test_regression_endpoints(admin, path):
    r = admin.get(f"{API}{path}")
    # some may 404 if not GET — just make sure not 500
    assert r.status_code < 500, f"{path} → {r.status_code}"
