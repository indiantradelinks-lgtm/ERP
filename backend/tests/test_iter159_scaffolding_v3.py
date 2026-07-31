"""Iter 159 — Scaffolding: location-details, extended challan (WO, purpose, addresses, per-line rate/wt),
IC-#### series on receive, location-statement, item-ledger, 3-copy PDF."""
import io
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
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def state():
    return {}


# ── Seed: item, opening stock, transfer, approve ────────────────────
def test_seed(admin, state):
    # locations
    locs = admin.get(f"{API}/scaffolding/locations").json()
    state["store"] = next(l for l in locs if l["type"] == "store")
    state["project"] = next(l for l in locs if l["type"] == "project")

    # item with weight and rate
    r = admin.post(f"{API}/scaffolding/items", json={
        "name": "TEST_Iter159 Cuplock", "unit": "Nos",
        "unit_weight_kg": 17.1, "rate": 500})
    assert r.status_code == 200, r.text
    state["item"] = r.json()

    # opening stock at store
    r = admin.post(f"{API}/scaffolding/opening-stock", json={
        "item_id": state["item"]["id"], "location_id": state["store"]["id"],
        "quantity": 200})
    assert r.status_code == 200

    # create transfer store→project
    r = admin.post(f"{API}/scaffolding/transfers", json={
        "from_location_id": state["store"]["id"], "to_location_id": state["project"]["id"],
        "lines": [{"item_id": state["item"]["id"], "quantity": 30}],
        "remarks": "TEST_Iter159"})
    assert r.status_code == 200, r.text
    state["transfer"] = r.json()

    # approve
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer']['id']}/approve", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


# ── /scaffolding/location-details/{id} ─────────────────────────────
def test_location_details_store(admin, state):
    r = admin.get(f"{API}/scaffolding/location-details/{state['store']['id']}")
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("company", "gstin", "address", "name", "type"):
        assert k in d, f"missing {k} in {d}"
    assert d["type"] == "store"
    assert d["name"] == state["store"]["name"]
    assert isinstance(d["company"], str) and d["company"]


def test_location_details_project(admin, state):
    r = admin.get(f"{API}/scaffolding/location-details/{state['project']['id']}")
    assert r.status_code == 200
    d = r.json()
    assert d["type"] == "project"
    assert d["name"]  # non-empty


def test_location_details_unknown(admin):
    r = admin.get(f"{API}/scaffolding/location-details/does-not-exist-xyz")
    assert r.status_code == 200
    d = r.json()
    assert d["type"] == "unknown"


# ── Create challan with new fields ─────────────────────────────────
def test_create_challan_extended(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer']['id']}/challans", json={
        "vehicle_no": "GJ01AB1234",
        "driver_name": "TEST Driver",
        "eway_bill_no": "EWB159TEST",
        "customer_wo_no": "WO/2026/TEST159",
        "purpose": "returnable_service",
        "lines": [{"item_id": state["item"]["id"], "quantity": 10, "unit_rate": 500}]
    })
    assert r.status_code == 200, r.text
    d = r.json()
    state["challan"] = d
    # numbers
    assert d["challan_no"].startswith("DC-"), d["challan_no"]
    assert d.get("in_challan_no") in (None, ""), d.get("in_challan_no")
    # new fields
    assert d["customer_wo_no"] == "WO/2026/TEST159"
    assert d["purpose"] == "returnable_service"
    assert d["origin_address"], "origin_address should auto-prefill"
    assert d["destination_address"], "destination_address should auto-prefill"
    # gstin: may be blank if company profile has none; presence of key is what matters
    assert "origin_gstin" in d and "destination_gstin" in d
    # per-line
    line = d["lines"][0]
    assert line["quantity"] == 10
    assert float(line["unit_weight_kg"]) == 17.1
    assert float(line["line_weight_kg"]) == 171.0
    assert float(line["unit_rate"]) == 500
    assert float(line["line_value"]) == 5000
    # totals
    assert float(d["total_qty"]) == 10
    assert float(d["total_weight_kg"]) == 171.0
    assert float(d["total_value"]) == 5000


def test_create_challan_purpose_normalized(admin, state):
    # Invalid purpose value should be normalized to returnable_service.
    # First create a second transfer since our transfer only has 30 - 10 = 20 left
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer']['id']}/challans", json={
        "vehicle_no": "GJ01AB0002",
        "purpose": "garbage",
        "lines": [{"item_id": state["item"]["id"], "quantity": 5}]
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["purpose"] == "returnable_service"
    state["challan2"] = d


def test_create_challan_sale_purpose(admin, state):
    r = admin.post(f"{API}/scaffolding/transfers/{state['transfer']['id']}/challans", json={
        "vehicle_no": "GJ01AB0003",
        "purpose": "sale",
        "customer_wo_no": "SALE/WO/999",
        "lines": [{"item_id": state["item"]["id"], "quantity": 5, "unit_rate": 650}]
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["purpose"] == "sale"
    assert float(d["total_value"]) == 5 * 650


# ── Receive assigns IC-#### number (different series from DC) ─────
def test_receive_assigns_in_challan_no_ic_series(admin, state):
    cid = state["challan"]["id"]
    r = admin.post(f"{API}/scaffolding/challans/{cid}/receive",
                   json={"receiver_name": "TEST Receiver 159"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "received"
    assert d["in_challan_no"], "in_challan_no must be assigned on receive"
    assert d["in_challan_no"].startswith("IC-"), f"IC series expected, got {d['in_challan_no']}"
    # ensure DC no still starts with DC-, and both series differ
    assert d["challan_no"].startswith("DC-")
    state["received_challan"] = d


# ── Challans filter by location_id (project-wise) ─────────────────
def test_challans_filter_by_project_location(admin, state):
    pid = state["project"]["id"]
    r = admin.get(f"{API}/scaffolding/challans", params={"location_id": pid})
    assert r.status_code == 200
    lst = r.json()
    assert isinstance(lst, list)
    # our created challans go to this project
    ids = [c["id"] for c in lst]
    assert state["challan"]["id"] in ids


# ── location-statement ────────────────────────────────────────────
def test_location_statement_project(admin, state):
    pid = state["project"]["id"]
    r = admin.get(f"{API}/scaffolding/location-statement", params={"location_id": pid})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "items" in d and "totals" in d
    it = next((x for x in d["items"] if x["item_id"] == state["item"]["id"]), None)
    assert it is not None, "seeded item must appear in statement"
    # 10 received into project (from first challan)
    assert it["in_qty"] >= 10
    assert it["in_challans"] >= 1
    assert float(it["unit_weight_kg"]) == 17.1
    assert it["stock_weight_kg"] == round(it["current_stock"] * 17.1, 2)
    for k in ("in_qty", "out_qty", "current_stock", "stock_weight_kg"):
        assert k in d["totals"]


def test_location_statement_store_out(admin, state):
    sid = state["store"]["id"]
    r = admin.get(f"{API}/scaffolding/location-statement", params={"location_id": sid})
    assert r.status_code == 200
    d = r.json()
    it = next((x for x in d["items"] if x["item_id"] == state["item"]["id"]), None)
    assert it is not None
    # 10 + 5 + 5 = 20 out from store
    assert it["out_qty"] >= 20
    assert it["out_challans"] >= 3


def test_location_statement_invalid_400(admin):
    r = admin.get(f"{API}/scaffolding/location-statement", params={"location_id": "nope-xxx"})
    assert r.status_code == 400


# ── item-ledger ────────────────────────────────────────────────────
def test_item_ledger_by_item_and_location(admin, state):
    iid = state["item"]["id"]
    pid = state["project"]["id"]
    r = admin.get(f"{API}/scaffolding/item-ledger", params={"item_id": iid, "location_id": pid})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["item"]["id"] == iid
    assert isinstance(d["rows"], list) and len(d["rows"]) >= 3
    # since project is the 'to' side, direction is 'in' if received else 'in_transit'
    dirs = {r["direction"] for r in d["rows"]}
    assert dirs.issubset({"in", "in_transit", "out"})
    # first challan is received → in_challan_no present
    received_rows = [r for r in d["rows"] if r["status"] == "received"]
    assert any(r.get("in_challan_no", "").startswith("IC-") for r in received_rows)
    assert d["total_moved"] >= 20


def test_item_ledger_bad_item_404(admin):
    r = admin.get(f"{API}/scaffolding/item-ledger", params={"item_id": "bogus-id-xyz"})
    assert r.status_code == 404


# ── 3-copy PDF ─────────────────────────────────────────────────────
def test_challan_pdf_three_copies(admin, state):
    cid = state["challan"]["id"]
    r = admin.get(f"{API}/scaffolding/challans/{cid}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    # inspect page count with pypdf
    try:
        from pypdf import PdfReader
    except ImportError:
        pytest.skip("pypdf not installed")
    reader = PdfReader(io.BytesIO(r.content))
    assert len(reader.pages) == 3, f"expected 3 pages, got {len(reader.pages)}"
    # extract text and assert copy labels + key fields
    all_text = "\n".join((p.extract_text() or "") for p in reader.pages)
    for label in ("ORIGINAL FOR CONSIGNEE", "DUPLICATE FOR TRANSPORTER", "TRIPLICATE FOR CONSIGNOR"):
        assert label in all_text, f"missing copy label {label}"
    # out + in challan numbers
    assert state["challan"]["challan_no"] in all_text
    assert (state["received_challan"]["in_challan_no"]) in all_text
    # WO + purpose declaration
    # PDF may wrap words across lines; normalize whitespace for content checks
    all_text_norm = "".join(all_text.split())
    assert "WO/2026/TEST159" in all_text_norm
    assert "NOTFORSALE" in all_text_norm or "returnable" in all_text.lower()
    assert "UnitWt" in all_text_norm
    assert "UnitPrice" in all_text_norm
    assert "TOTAL" in all_text


# ── Cleanup best-effort (skip if stock remains) ───────────────────
def test_cleanup(admin, state):
    admin.delete(f"{API}/scaffolding/items/{state['item']['id']}")
