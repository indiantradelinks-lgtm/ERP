"""Iter 225 — Challan PDF → Material Lines (AI extraction + Item Master mapping)."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
PDF = os.path.join(os.path.dirname(__file__), "fixtures", "challan_sample.pdf")
TAG = uuid.uuid4().hex[:6]

# Names taken verbatim from the sample challan, except the last two which are
# deliberately spelled differently (fuzzy) and absent (unmatched).
SEED_ITEMS = [
    ("RINGLOCK BASE JACK 0.5M", 500),
    ("RINGLOCK BEAM CLAMP", 10),            # challan asks 44 → short
    ("RINGLOCK DOUBLE COUPLER", 1000),
    ("RINGLOCK SWIVEL COUPLER", 1000),
    ("RINGLOCK GALV SCAFFOLD TUBE 3.0 M", 500),
    ("RINGLOCK HORIZONTAL SPIGOT 1.0 MTR", 200),   # challan says "1.0m" → fuzzy/normalised
]


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def locs(s):
    rows = s.get(f"{API}/scaffolding/locations", timeout=60).json()
    if len(rows) < 2:
        pytest.skip("need two scaffolding locations")
    return rows


@pytest.fixture(scope="module")
def seeded(db, locs):
    """Item Master rows + stock at the From location, so matching has something to hit."""
    ids = []
    src = locs[0]
    for name, qty in SEED_ITEMS:
        iid = f"it225-{TAG}-{len(ids)}"
        db.inventory.insert_one({"id": iid, "name": name, "code": f"SC225-{TAG}-{len(ids)}",
                                 "category": "scaffolding", "unit": "Nos", "uom": "Nos", "quantity": qty})
        db.scaf_stock.insert_one({"id": f"st225-{TAG}-{len(ids)}", "item_id": iid, "item_name": name,
                                  "location_id": src["id"], "location_name": src["name"], "quantity": qty})
        ids.append(iid)
    yield {"ids": ids, "src": src, "dst": locs[1]}
    db.scaf_stock.delete_many({"item_id": {"$in": ids}})
    db.inventory.delete_many({"id": {"$in": ids}})


@pytest.fixture(scope="module")
def extracted(s, seeded):
    with open(PDF, "rb") as fh:
        r = s.post(f"{API}/scaffolding/transfers/challan-extract",
                   params={"from_location_id": seeded["src"]["id"]},
                   files={"file": ("CHALLAN.pdf", fh, "application/pdf")}, timeout=240)
    assert r.status_code == 200, r.text
    return r.json()


def test_every_item_row_is_read(extracted):
    assert extracted["total_items"] == 29, "the sample challan has 29 item rows"
    assert extracted["challan_no"] == "ITL/27-28/TSLU/005"
    assert extracted["vehicle_no"] == "RJ11GC5617"
    assert extracted["total_quantity"] == 3767.0


def test_quantities_come_through_exactly(extracted):
    by_name = {r["challan_name"].upper(): r["quantity"] for r in extracted["rows"]}
    assert by_name["RINGLOCK BASE JACK 0.5M"] == 115
    assert by_name["RINGLOCK DOUBLE COUPLER"] == 875
    assert by_name["RINGLOCK SWIVEL COUPLER"] == 400


def test_known_items_are_mapped_to_the_item_master(extracted, seeded):
    mapped = {r["challan_name"].upper(): r for r in extracted["rows"] if r["item_id"]}
    assert "RINGLOCK BASE JACK 0.5M" in mapped
    assert mapped["RINGLOCK BASE JACK 0.5M"]["item_id"] in seeded["ids"]
    assert mapped["RINGLOCK BASE JACK 0.5M"]["match"] == "exact"
    assert extracted["matched"] >= 5


def test_differently_spelled_item_is_still_matched(extracted):
    row = next(r for r in extracted["rows"] if r["challan_name"].upper().startswith("RINGLOCK HORIZONTAL SPIGOT 1.0"))
    assert row["item_id"], "1.0m vs 1.0 MTR must still resolve to the same item"
    assert row["item_name"] == "RINGLOCK HORIZONTAL SPIGOT 1.0 MTR"


def test_items_absent_from_the_master_are_flagged(extracted):
    unmatched = [r for r in extracted["rows"] if not r["item_id"]]
    assert unmatched, "the sample has items that are not in the master"
    assert extracted["unmatched"] == len(unmatched)
    for r in unmatched:
        assert r["status"] == "unmatched" and r["note"]
        assert r["challan_name"], "the challan text is kept so the user can map it"


def test_only_valid_items_reach_the_loadable_lines(extracted, seeded):
    ids = {l["item_id"] for l in extracted["lines"]}
    assert ids and ids <= set(seeded["ids"]), "no invented items may reach a transfer"
    assert all(l["quantity"] > 0 for l in extracted["lines"])


def test_stock_shortage_is_flagged_not_hidden(extracted):
    row = next(r for r in extracted["rows"] if r["challan_name"].upper() == "RINGLOCK BEAM CLAMP")
    assert row["available"] == 10 and row["quantity"] == 44
    assert row.get("short") is True and "available" in (row["note"] or "")


def test_the_pdf_is_kept_for_the_transfer(extracted):
    att = extracted["attachment"]
    assert att and att["storage_path"].endswith(".pdf") and att["size"] > 1000


def test_transfer_keeps_the_challan_and_serves_it_back(s, seeded, extracted, db):
    line = next(l for l in extracted["lines"] if l["item_id"] == seeded["ids"][0])
    body = {"from_location_id": seeded["src"]["id"], "to_location_id": seeded["dst"]["id"],
            "lines": [{"item_id": line["item_id"], "quantity": 5}],
            "remarks": f"iter225 {TAG}",
            "challan_attachment": {**extracted["attachment"],
                                   "challan_no": extracted["challan_no"],
                                   "challan_date": extracted["challan_date"],
                                   "vehicle_no": extracted["vehicle_no"]}}
    r = s.post(f"{API}/scaffolding/transfers", json=body, timeout=90)
    assert r.status_code == 200, r.text
    t = r.json()
    try:
        assert t["challan_attachment"]["challan_no"] == "ITL/27-28/TSLU/005"
        pdf = s.get(f"{API}/scaffolding/transfers/{t['id']}/challan-file", timeout=120)
        assert pdf.status_code == 200 and pdf.content[:5].startswith(b"%PDF")
    finally:
        db.scaf_transfers.delete_one({"id": t["id"]})


def test_a_non_pdf_upload_is_rejected(s):
    r = s.post(f"{API}/scaffolding/transfers/challan-extract",
               files={"file": ("notes.txt", b"not a pdf at all", "text/plain")}, timeout=60)
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]
