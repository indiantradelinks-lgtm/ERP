"""Iter 215 — Scaffolding bulk stock adjustment & bulk transfer via Excel."""
import io
import os

import pytest
import requests
from openpyxl import Workbook, load_workbook

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def locs(s):
    rows = s.get(f"{API}/scaffolding/locations", timeout=60).json()
    rows = rows if isinstance(rows, list) else rows.get("rows", [])
    store = next((l for l in rows if l["type"] == "store"), None)
    assert store, "no store location"
    return {"store": store, "all": rows}


@pytest.fixture(scope="module")
def stocked_item(s, locs):
    """An item with stock on hand at the store, used for both suites."""
    m = s.get(f"{API}/scaffolding/stock-matrix", timeout=90).json()
    sid = locs["store"]["id"]
    it = next((i for i in m["items"] if float(i.get("by_location", {}).get(sid) or 0) > 0), None)
    if not it:
        pytest.skip("no stocked item at the store")
    return {**it, "on_hand": float(it["by_location"][sid])}


def _book(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(s, url, data, params=None):
    return s.post(url, params=params or {},
                  files={"file": ("sheet.xlsx", data, XLSX)}, timeout=120)


# ── Bulk stock adjustment ───────────────────────────────────────────────
def test_adjust_template_has_current_stock(s):
    r = s.get(f"{API}/scaffolding/stock-adjust-template.xlsx", timeout=90)
    assert r.status_code == 200 and r.headers["content-type"].startswith(XLSX)
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Stock Adjustment", "How to use"]
    rows = list(wb["Stock Adjustment"].iter_rows(values_only=True))
    assert list(rows[0]) == ["item_code", "item_name", "location", "current_quantity", "new_quantity", "remarks"]
    assert len(rows) > 1


def test_adjust_validate_reports_every_error(s, locs, stocked_item):
    store = locs["store"]["name"]
    code, name = stocked_item["item_code"], stocked_item["item_name"]
    data = _book(["item_code", "item_name", "location", "current_quantity", "new_quantity", "remarks"], [
        [code, name, store, "", stocked_item["on_hand"] + 3, "raise"],              # row 2 ok
        [code, name, store, "", stocked_item["on_hand"] + 9, "dupe"],               # row 3 duplicate
        ["ZZZ-NOPE", "Unknown Widget", store, "", 5, "bad item"],                   # row 4 unknown item
        [code, name, "Nowhere Store", "", 5, "bad location"],                       # row 5 unknown location
        [code, name, store, "", -4, "negative"],                                    # row 6 (dupe wins first)
        [code, name, store, "", "", "blank"],                                       # row 7
    ])
    r = _upload(s, f"{API}/scaffolding/stock-adjust/validate", data)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 6 and d["valid"] == 1 and d["errors"] == 5
    by_row = {x["row"]: x for x in d["rows"]}
    assert by_row[2]["status"] == "ok" and by_row[2]["delta"] == 3
    assert "duplicate of row 2" in by_row[3]["error"]
    assert "unknown item" in by_row[4]["error"]
    assert "unknown location" in by_row[5]["error"]


def test_adjust_import_applies_only_valid_rows(s, locs, stocked_item):
    store_name, store_id = locs["store"]["name"], locs["store"]["id"]
    target = stocked_item["on_hand"] + 7
    data = _book(["item_code", "item_name", "location", "current_quantity", "new_quantity", "remarks"], [
        [stocked_item["item_code"], stocked_item["item_name"], store_name, "", target, "bulk set"],
        ["ZZZ-NOPE", "Unknown Widget", store_name, "", 5, "bad"],
    ])
    r = _upload(s, f"{API}/scaffolding/stock-adjust/import", data)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["applied"] == 1 and len(d["errors"]) == 1
    m = s.get(f"{API}/scaffolding/stock-matrix", timeout=90).json()
    row = next(i for i in m["items"] if i["item_code"] == stocked_item["item_code"])
    assert float(row["by_location"][store_id]) == target
    # restore
    back = _book(["item_code", "item_name", "location", "new_quantity"],
                 [[stocked_item["item_code"], stocked_item["item_name"], store_name, stocked_item["on_hand"]]])
    assert _upload(s, f"{API}/scaffolding/stock-adjust/import", back).json()["applied"] == 1


def test_adjust_rejects_a_sheet_without_template_columns(s):
    data = _book(["foo", "bar"], [["a", "b"]])
    r = _upload(s, f"{API}/scaffolding/stock-adjust/validate", data)
    assert r.status_code == 400
    assert "template columns" in r.json()["detail"]


# ── Bulk transfer ───────────────────────────────────────────────────────
def test_transfer_template_carries_available_stock(s, locs):
    r = s.get(f"{API}/scaffolding/transfer-template.xlsx",
              params={"from_location_id": locs["store"]["id"]}, timeout=90)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    rows = list(wb["Bulk Transfer"].iter_rows(values_only=True))
    assert list(rows[0]) == ["item_code", "item_name", "available_qty", "quantity"]
    assert len(rows) > 1


def test_transfer_bulk_validate(s, locs, stocked_item):
    sid = locs["store"]["id"]
    data = _book(["item_code", "item_name", "available_qty", "quantity"], [
        [stocked_item["item_code"], stocked_item["item_name"], stocked_item["on_hand"], 1],
        [stocked_item["item_code"], stocked_item["item_name"], stocked_item["on_hand"], 1],       # duplicate
        ["ZZZ-NOPE", "Unknown Widget", 0, 1],                                                    # unknown item
        [stocked_item["item_code"], stocked_item["item_name"], 0, ""],                            # skipped
    ])
    r = _upload(s, f"{API}/scaffolding/transfers/bulk-validate", data, {"from_location_id": sid})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["valid"] == 1 and d["errors"] == 2 and d["skipped"] == 1
    assert d["lines"] == [{"item_id": stocked_item["item_id"], "quantity": 1}]
    by_row = {x["row"]: x for x in d["rows"]}
    assert "duplicate of row 2" in by_row[3]["error"]
    assert "unknown item" in by_row[4]["error"]


def test_transfer_bulk_validate_blocks_quantity_above_stock(s, locs, stocked_item):
    data = _book(["item_code", "item_name", "available_qty", "quantity"],
                 [[stocked_item["item_code"], stocked_item["item_name"],
                   stocked_item["on_hand"], stocked_item["on_hand"] + 100]])
    d = _upload(s, f"{API}/scaffolding/transfers/bulk-validate", data,
                {"from_location_id": locs["store"]["id"]}).json()
    assert d["valid"] == 0 and d["errors"] == 1
    assert "available at" in d["rows"][0]["error"]
    assert d["lines"] == []


def test_transfer_bulk_validate_needs_a_valid_source(s):
    data = _book(["item_code", "item_name", "available_qty", "quantity"], [["X", "Y", 1, 1]])
    r = _upload(s, f"{API}/scaffolding/transfers/bulk-validate", data, {"from_location_id": "nope"})
    assert r.status_code == 400
