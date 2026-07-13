"""Iter 53 · Phase 1 — End-to-end procurement lineage + auto PR fulfilment."""
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


@pytest.fixture(scope="module")
def cycle(admin):
    """Build a complete PR → approved → RFQ → vendor select → PO → GRN cycle
    and yield all the IDs. Cleans up at module teardown."""
    ts = int(time.time() * 1000)

    # 1. Create vendor
    v = admin.post("/vendors", json={
        "name": f"Test Vendor {ts}",
        "vendor_code": f"V-ITR53-{ts}",
        "gst": "27AAAAA0000A1Z5",
        "phone": "9999999999",
        "status": "active",
    })
    assert v.status_code in (200, 201), v.text
    vendor_id = v.json()["id"]

    # 2. Create PR (auto-submit for approval)
    pr = admin.post("/procurement/prs", json={
        "department": "QA",
        "priority": "medium",
        "items": [{"name": f"ITR53 Bolts {ts}", "quantity": 10, "unit": "Nos"}],
        "submit_for_approval": True,
    })
    assert pr.status_code == 200, pr.text
    pr_id = pr.json()["id"]
    ap_id = pr.json().get("approval_id")
    # Approve every step (chain has 2 steps for purchase_requisition)
    if ap_id:
        for _ in range(6):
            r = admin.post(f"/approvals/{ap_id}/action",
                            json={"action": "approve", "comment": "ok for ITR53"})
            if r.json().get("status") == "approved":
                break

    # 3. Create RFQ
    rfq_res = admin.post("/procurement/rfqs", json={
        "pr_id": pr_id, "vendors": [{"vendor_id": vendor_id, "vendor_name": f"Test Vendor {ts}"}],
    })
    assert rfq_res.status_code == 200, rfq_res.text
    rfq_id = rfq_res.json()["id"]

    # 4. Vendor responds
    admin.post(f"/procurement/rfqs/{rfq_id}/respond", json={
        "vendor_id": vendor_id, "rate_quoted": 150.0,
        "delivery_days": 7, "payment_terms": "30 days",
    })

    # 5. Select vendor
    admin.post(f"/procurement/rfqs/{rfq_id}/select-vendor", json={"vendor_id": vendor_id})

    # 6. Convert to PO
    po_res = admin.post(f"/procurement/rfqs/{rfq_id}/convert-to-po")
    assert po_res.status_code == 200, po_res.text
    po_id = po_res.json()["id"]

    yield {"pr_id": pr_id, "rfq_id": rfq_id, "po_id": po_id, "vendor_id": vendor_id}

    # Teardown — best effort
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _cleanup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.purchase_requisitions.delete_one({"id": pr_id})
        await db.rfqs.delete_one({"id": rfq_id})
        await db.purchase_orders.delete_one({"id": po_id})
        await db.grn.delete_many({"po_id": po_id})
        await db.vendors.delete_one({"id": vendor_id})
        await db.inventory_transactions.delete_many({"ref_type": "grn"})
    asyncio.run(_cleanup())


# ─── Lineage endpoint ──────────────────────────────────────────────

def test_lineage_from_pr_anchor(admin, cycle):
    r = admin.get(f"/procurement/lineage/pr/{cycle['pr_id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["anchor"] == "pr"
    kinds = [n["kind"] for n in body["chain"]]
    assert kinds[:3] == ["pr", "rfq", "po"]  # PR + RFQ + PO present (no GRN yet)


def test_lineage_from_po_anchor_walks_backwards(admin, cycle):
    r = admin.get(f"/procurement/lineage/po/{cycle['po_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["anchor"] == "po"
    kinds = [n["kind"] for n in body["chain"]]
    assert "pr" in kinds and "rfq" in kinds and "po" in kinds


def test_lineage_404_for_missing(admin):
    r = admin.get("/procurement/lineage/pr/does-not-exist")
    assert r.status_code == 404


def test_lineage_400_for_invalid_kind(admin):
    r = admin.get("/procurement/lineage/banana/x")
    assert r.status_code == 400


# ─── GRN auto-fulfilment of PR ─────────────────────────────────────

def test_partial_grn_marks_pr_partially_fulfilled(admin, cycle):
    # Create a GRN receiving only 3 of 10 units
    g = admin.post("/procurement/grns", json={
        "po_id": cycle["po_id"], "store_location": "STORE-A",
        "items": [{
            "po_item_index": 0, "item_name": "ITR53 Bolts",
            "ordered_qty": 10, "received_qty": 3, "accepted_qty": 3, "rejected_qty": 0,
            "unit": "Nos", "inspection_status": "approved",
        }],
    })
    assert g.status_code == 200, g.text

    # PR should now be partially_fulfilled
    pr = admin.get(f"/procurement/prs/{cycle['pr_id']}").json()
    assert pr["status"] == "partially_fulfilled"
    assert pr["fulfilment_pct"] == 30.0

    # Lineage should now include the GRN
    lin = admin.get(f"/procurement/lineage/pr/{cycle['pr_id']}").json()
    grn_nodes = [n for n in lin["chain"] if n["kind"] == "grn"]
    assert len(grn_nodes) == 1
    assert lin["fulfilment"]["ordered"] == 10
    assert lin["fulfilment"]["received"] == 3
    assert lin["fulfilment"]["pct"] == 30.0


def test_full_grn_marks_pr_closed(admin, cycle):
    # Receive remaining 7 units
    g = admin.post("/procurement/grns", json={
        "po_id": cycle["po_id"], "store_location": "STORE-A",
        "items": [{
            "po_item_index": 0, "item_name": "ITR53 Bolts",
            "ordered_qty": 10, "received_qty": 7, "accepted_qty": 7, "rejected_qty": 0,
            "unit": "Nos", "inspection_status": "approved",
        }],
    })
    assert g.status_code == 200, g.text

    pr = admin.get(f"/procurement/prs/{cycle['pr_id']}").json()
    assert pr["status"] == "closed"
    assert pr["fulfilment_pct"] == 100.0

    lin = admin.get(f"/procurement/lineage/pr/{cycle['pr_id']}").json()
    assert lin["fulfilment"]["pct"] == 100.0
    grn_nodes = [n for n in lin["chain"] if n["kind"] == "grn"]
    assert len(grn_nodes) == 2  # both partial + final


def test_rejected_qty_does_not_inward_to_inventory(admin):
    """Independent test: create a fresh cycle and reject some qty. The accepted
    qty must inward to inventory; the rejected qty must NOT."""
    ts = int(time.time() * 1000)
    v = admin.post("/vendors", json={"name": f"RejTest {ts}", "vendor_code": f"V-REJ-{ts}",
                                       "gst": "27AAAAA0000A1Z5", "status": "active"}).json()
    vendor_id = v["id"]

    pr = admin.post("/procurement/prs", json={
        "department": "QA", "priority": "low",
        "items": [{"name": f"REJ-{ts}", "quantity": 5, "unit": "Nos"}],
        "submit_for_approval": True,
    }).json()
    pr_id, ap_id = pr["id"], pr.get("approval_id")
    for _ in range(6):
        if not ap_id: break
        rr = admin.post(f"/approvals/{ap_id}/action", json={"action": "approve", "comment": "ok"})
        if rr.json().get("status") == "approved": break

    rfq = admin.post("/procurement/rfqs", json={
        "pr_id": pr_id, "vendors": [{"vendor_id": vendor_id, "vendor_name": f"RejTest {ts}"}],
    }).json()
    admin.post(f"/procurement/rfqs/{rfq['id']}/respond",
               json={"vendor_id": vendor_id, "rate_quoted": 200.0, "delivery_days": 5})
    admin.post(f"/procurement/rfqs/{rfq['id']}/select-vendor", json={"vendor_id": vendor_id})
    po = admin.post(f"/procurement/rfqs/{rfq['id']}/convert-to-po").json()

    # GRN: 5 received, 2 accepted, 3 rejected — only 2 should inward
    g = admin.post("/procurement/grns", json={
        "po_id": po["id"], "store_location": "STORE-REJ",
        "items": [{
            "po_item_index": 0, "item_name": f"REJ-{ts}",
            "ordered_qty": 5, "received_qty": 5, "accepted_qty": 2, "rejected_qty": 3,
            "unit": "Nos", "inspection_status": "partial_accepted",
        }],
    })
    assert g.status_code == 200, g.text
    grn = g.json()
    assert grn["total_accepted"] == 2
    assert grn["total_rejected"] == 3
    assert grn["status"] in ("partial_accepted", "rejected")

    # Cleanup
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.purchase_requisitions.delete_one({"id": pr_id})
        await db.rfqs.delete_one({"id": rfq["id"]})
        await db.purchase_orders.delete_one({"id": po["id"]})
        await db.grn.delete_one({"id": grn["id"]})
        await db.vendors.delete_one({"id": vendor_id})
    asyncio.run(_do())
