"""Iter 55 — GRN must auto-create / auto-match inventory rows so accepted qty
actually shows up in stores even when the PO item had no item_id link."""
import os
import time
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def admin():
    c = httpx.Client(base_url=f"{API}/api", timeout=30.0)
    r = c.post("/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200
    yield c
    c.close()


def _approve_all(admin, ap_id):
    for _ in range(6):
        r = admin.post(f"/approvals/{ap_id}/action", json={"action": "approve", "comment": "ok"})
        if r.json().get("status") == "approved":
            return


def _build_cycle(admin, item_name: str):
    """Helper: build PR → RFQ → vendor selected → PO. Returns IDs."""
    ts = int(time.time() * 1000)
    v = admin.post("/vendors", json={"name": f"AutoVen-{ts}", "vendor_code": f"AV-{ts}",
                                       "gst": "27AAAAA0000A1Z5", "status": "active"}).json()
    pr = admin.post("/procurement/prs", json={
        "department": "QA", "priority": "low",
        "items": [{"name": item_name, "quantity": 8, "unit": "Nos"}],
        "submit_for_approval": True,
    }).json()
    if pr.get("approval_id"):
        _approve_all(admin, pr["approval_id"])
    rfq = admin.post("/procurement/rfqs", json={
        "pr_id": pr["id"],
        "vendors": [{"vendor_id": v["id"], "vendor_name": v["name"]}],
    }).json()
    admin.post(f"/procurement/rfqs/{rfq['id']}/respond",
               json={"vendor_id": v["id"], "rate_quoted": 50.0, "delivery_days": 7})
    admin.post(f"/procurement/rfqs/{rfq['id']}/select-vendor", json={"vendor_id": v["id"]})
    po = admin.post(f"/procurement/rfqs/{rfq['id']}/convert-to-po").json()
    return {"pr_id": pr["id"], "rfq_id": rfq["id"], "po_id": po["id"], "vendor_id": v["id"]}


def _cleanup(ids: dict, item_name: str):
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.purchase_requisitions.delete_one({"id": ids["pr_id"]})
        await db.rfqs.delete_one({"id": ids["rfq_id"]})
        await db.purchase_orders.delete_one({"id": ids["po_id"]})
        await db.grn.delete_many({"po_id": ids["po_id"]})
        await db.vendors.delete_one({"id": ids["vendor_id"]})
        await db.inventory_transactions.delete_many({"item_name": item_name})
        await db.inventory.delete_many({"name": item_name})
    asyncio.run(_do())


def test_grn_auto_creates_inventory_when_item_id_missing(admin):
    """The fix for "material not moving to inventory after GRN" — when a PO has
    a free-text item (no item_id), the GRN must auto-create the inventory row
    and inward the accepted qty so the user sees stock."""
    name = f"AutoCreate-{int(time.time())}"
    ids = _build_cycle(admin, name)
    try:
        # Verify NO inventory row exists yet
        load_dotenv("/app/backend/.env")
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        async def _pre():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            row = await db.inventory.find_one({"name": name})
            return row
        assert asyncio.run(_pre()) is None, "Pre-state: no inventory row should exist"

        # Create GRN WITHOUT item_id → previously this silently dropped the inward
        g = admin.post("/procurement/grns", json={
            "po_id": ids["po_id"], "store_location": "STORE-A",
            "items": [{
                "po_item_index": 0, "item_name": name,
                "ordered_qty": 8, "received_qty": 8, "accepted_qty": 8, "rejected_qty": 0,
                "unit": "Nos", "inspection_status": "approved",
                # NO item_id here — this is the regression case
            }],
        })
        assert g.status_code == 200, g.text
        grn = g.json()

        # Inventory row should now exist with quantity=8
        async def _post():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            row = await db.inventory.find_one({"name": name}, {"_id": 0})
            txn = await db.inventory_transactions.find_one(
                {"item_name": name, "ref_type": "grn"}, {"_id": 0})
            return row, txn
        row, txn = asyncio.run(_post())
        assert row is not None, "Inventory row must be auto-created"
        assert row["quantity"] == 8, f"Expected qty=8, got {row['quantity']}"
        assert row.get("auto_created_from_grn") == grn["id"]
        assert row["code"].startswith("AUTO-")

        # Inventory transaction must also be written
        assert txn is not None, "inventory_transactions entry must be written"
        assert txn["txn_type"] == "inward"
        assert txn["quantity"] == 8
        assert txn["store_location"] == "STORE-A"
        assert txn["ref_no"] == grn["grn_number"]

        # GRN line should have been back-filled with the new item_id
        refreshed = admin.get(f"/procurement/grns/{grn['id']}").json()
        assert refreshed["items"][0].get("item_id") == row["id"]
    finally:
        _cleanup(ids, name)


def test_grn_reuses_existing_inventory_by_case_insensitive_name(admin):
    """If an inventory row with the same name already exists, GRN must add to
    it rather than creating a duplicate."""
    name_lower = f"reusetest-{int(time.time())}"
    name_mixed = name_lower.replace("r", "R", 1)
    ids = _build_cycle(admin, name_mixed)
    # Seed inventory with the lowercase variant
    seed = admin.post("/inventory", json={
        "code": f"SEED-{int(time.time())}", "name": name_lower, "uom": "Nos",
        "quantity": 5, "min_stock": 0, "rate": 100, "category": "test",
    }).json()
    try:
        admin.post("/procurement/grns", json={
            "po_id": ids["po_id"], "store_location": "STORE-A",
            "items": [{
                "po_item_index": 0, "item_name": name_mixed,
                "ordered_qty": 8, "received_qty": 8, "accepted_qty": 8, "rejected_qty": 0,
                "unit": "Nos", "inspection_status": "approved",
            }],
        })
        load_dotenv("/app/backend/.env")
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        async def _check():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            rows = await db.inventory.find(
                {"name": {"$regex": f"^{name_lower}$", "$options": "i"}}, {"_id": 0}
            ).to_list(10)
            return rows
        rows = asyncio.run(_check())
        assert len(rows) == 1, f"Expected exactly 1 inventory row (case-insensitive reuse), got {len(rows)}"
        assert rows[0]["quantity"] == 13   # 5 existing + 8 inwarded
    finally:
        _cleanup(ids, name_mixed)
        # Also drop the seeded row
        load_dotenv("/app/backend/.env")
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        async def _drop():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            await db.inventory.delete_one({"id": seed["id"]})
        asyncio.run(_drop())
