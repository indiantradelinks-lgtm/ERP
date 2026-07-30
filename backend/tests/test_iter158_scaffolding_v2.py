"""Iter 158 — Scaffolding Inventory rectifications: PUT/DELETE items, CSV import/template,
stock-matrix filters+weights, export item_ids/weight columns."""
import io
import os
import csv
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
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def state():
    return {}


# ── PUT /items/{id} — update + sync ────────────────────────────────
def test_locations_and_seed(admin, state):
    locs = admin.get(f"{API}/scaffolding/locations").json()
    state["store"] = next(l for l in locs if l["type"] == "store")
    state["project"] = next(l for l in locs if l["type"] == "project")
    # create a fresh item
    r = admin.post(f"{API}/scaffolding/items",
                   json={"name": "TEST_Iter158 Vertical", "unit": "Nos", "unit_weight_kg": 10.0})
    assert r.status_code == 200, r.text
    state["item"] = r.json()
    # open stock so we can test rename sync
    r = admin.post(f"{API}/scaffolding/opening-stock",
                   json={"item_id": state["item"]["id"], "location_id": state["store"]["id"], "quantity": 50})
    assert r.status_code == 200


def test_put_item_rename_weight_and_sync(admin, state):
    iid = state["item"]["id"]
    r = admin.put(f"{API}/scaffolding/items/{iid}",
                  json={"name": "TEST_Iter158 Vertical EDITED", "unit_weight_kg": 12.5})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "TEST_Iter158 Vertical EDITED"
    assert float(d["unit_weight_kg"]) == 12.5

    # matrix reflects new name + weight totals
    m = admin.get(f"{API}/scaffolding/stock-matrix").json()
    it = next(x for x in m["items"] if x["item_id"] == iid)
    assert it["item_name"] == "TEST_Iter158 Vertical EDITED"
    assert float(it["unit_weight_kg"]) == 12.5
    assert it["total_weight_kg"] == round(50 * 12.5, 2)  # 625.0
    assert it["total_tonnage"] == 0.625


def test_put_item_duplicate_code_409(admin, state):
    # create a second item, then try to rename first to its code
    r2 = admin.post(f"{API}/scaffolding/items", json={"name": "TEST_Iter158 Dup Target", "unit": "Nos"})
    assert r2.status_code == 200
    dup_code = r2.json()["code"]
    state["dup_item_id"] = r2.json()["id"]
    r = admin.put(f"{API}/scaffolding/items/{state['item']['id']}", json={"code": dup_code})
    assert r.status_code == 409, r.text


# ── DELETE guards ─────────────────────────────────────────────────
def test_delete_with_stock_blocked_400(admin, state):
    r = admin.delete(f"{API}/scaffolding/items/{state['item']['id']}")
    assert r.status_code == 400, r.text
    assert "stock" in r.text.lower()


def test_delete_fresh_item_ok(admin, state):
    r = admin.delete(f"{API}/scaffolding/items/{state['dup_item_id']}")
    assert r.status_code == 200, r.text
    assert r.json().get("deleted") is True


# ── Import template + CSV import ──────────────────────────────────
def test_import_template_headers(admin):
    r = admin.get(f"{API}/scaffolding/import-template")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    headers = next(reader)
    expected = ["code", "name", "size", "spec", "unit", "rate",
                "min_stock", "unit_weight_kg", "location", "opening_quantity"]
    assert [h.strip().lower() for h in headers] == expected


def test_import_csv_create_update_openingstock_and_error(admin, state):
    store_name = state["store"]["name"]
    # Row A: create new item; Row B: weight-only update using existing code;
    # Row C: unknown location → error; Row D: new item with opening stock at store
    existing_code = state["item"]["code"]
    csv_body = (
        "code,name,size,spec,unit,rate,min_stock,unit_weight_kg,location,opening_quantity\n"
        f",TEST_Iter158 Imp New1,,,Nos,100,10,5.5,,\n"
        f"{existing_code},,,,,,,20.0,,\n"
        f",TEST_Iter158 Imp Bad,,,Nos,,,1,__DOES_NOT_EXIST_LOC__,10\n"
        f",TEST_Iter158 Imp Opening,,,Nos,50,5,3.0,{store_name},25\n"
    )
    files = {"file": ("import.csv", csv_body, "text/csv")}
    r = admin.post(f"{API}/scaffolding/import.csv", files=files)
    assert r.status_code == 200, r.text
    d = r.json()
    # 2 new items (New1 + Opening); 1 updated (weight-only via code); 1 error row (unknown loc, still created item then failed on stock — creates counted)
    assert d["updated"] >= 1
    assert d["created"] >= 2
    assert d["opening_stock_set"] >= 1
    assert len(d["errors"]) >= 1
    assert any("location" in (e.get("error") or "").lower() for e in d["errors"])

    # verify weight-only sync
    matrix = admin.get(f"{API}/scaffolding/stock-matrix").json()
    it = next(x for x in matrix["items"] if x["item_id"] == state["item"]["id"])
    assert float(it["unit_weight_kg"]) == 20.0

    # verify opening stock created
    it2 = next((x for x in matrix["items"] if x["item_name"] == "TEST_Iter158 Imp Opening"), None)
    assert it2 is not None
    assert it2["by_location"].get(state["store"]["id"]) == 25


# ── Stock matrix filters ──────────────────────────────────────────
def test_stock_matrix_location_and_q_filter(admin, state):
    sid = state["store"]["id"]
    m = admin.get(f"{API}/scaffolding/stock-matrix", params={"location_id": sid}).json()
    assert len(m["locations"]) == 1 and m["locations"][0]["id"] == sid
    for it in m["items"]:
        assert sid in it["by_location"]

    m2 = admin.get(f"{API}/scaffolding/stock-matrix", params={"q": "TEST_Iter158 Vertical"}).json()
    assert all("TEST_Iter158 Vertical".lower() in (i["item_name"] or "").lower() for i in m2["items"])
    assert len(m2["items"]) >= 1
    # grand totals present
    for k in ("grand_total_qty", "grand_total_weight_kg", "grand_total_tonnage"):
        assert k in m2


# ── Export with item_ids + weight columns ─────────────────────────
def test_export_xlsx_with_item_ids(admin, state):
    iid = state["item"]["id"]
    r = admin.get(f"{API}/scaffolding/export.xlsx",
                  params={"kind": "stock", "item_ids": iid})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 500


def test_export_pdf_with_filters(admin, state):
    r = admin.get(f"{API}/scaffolding/export.pdf",
                  params={"kind": "stock", "location_id": state["store"]["id"], "q": "TEST_Iter158"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")


# ── Cleanup best-effort ──────────────────────────────────────────
def test_cleanup(admin, state):
    # remove imported items where possible (no stock)
    items = admin.get(f"{API}/scaffolding/items").json()
    for it in items:
        if (it.get("name") or "").startswith("TEST_Iter158 Imp New1"):
            admin.delete(f"{API}/scaffolding/items/{it['id']}")
