"""Iter 54 · Phase 2+3+4 — Comparative L1 ranking, justification, stock ledger,
reorder alerts, GRN inspection, procurement reports."""
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


def _approve_chain(admin, ap_id):
    for _ in range(6):
        r = admin.post(f"/approvals/{ap_id}/action", json={"action": "approve", "comment": "ok"})
        if r.json().get("status") == "approved":
            return
    return


@pytest.fixture(scope="module")
def two_vendor_rfq(admin):
    """Create a fresh PR + 2-vendor RFQ + 2 quotations so Comparative can rank L1/L2."""
    ts = int(time.time() * 1000)
    v1 = admin.post("/vendors", json={"name": f"Cheap {ts}", "vendor_code": f"V1-{ts}",
                                        "gst": "27AAAAA0000A1Z5", "status": "active"}).json()
    v2 = admin.post("/vendors", json={"name": f"Pricey {ts}", "vendor_code": f"V2-{ts}",
                                        "gst": "27AAAAA0000A1Z5", "status": "active"}).json()
    pr = admin.post("/procurement/prs", json={
        "department": "QA", "priority": "low",
        "items": [{"name": f"ITR54 Sprocket {ts}", "quantity": 4, "unit": "Nos"}],
        "submit_for_approval": True,
    }).json()
    pr_id, ap_id = pr["id"], pr.get("approval_id")
    if ap_id:
        _approve_chain(admin, ap_id)
    rfq = admin.post("/procurement/rfqs", json={
        "pr_id": pr_id,
        "vendors": [
            {"vendor_id": v1["id"], "vendor_name": v1["name"]},
            {"vendor_id": v2["id"], "vendor_name": v2["name"]},
        ],
    }).json()
    admin.post(f"/procurement/rfqs/{rfq['id']}/respond",
               json={"vendor_id": v1["id"], "rate_quoted": 100.0, "delivery_days": 5})
    admin.post(f"/procurement/rfqs/{rfq['id']}/respond",
               json={"vendor_id": v2["id"], "rate_quoted": 150.0, "delivery_days": 3})

    yield {"pr_id": pr_id, "rfq_id": rfq["id"], "v_cheap": v1["id"], "v_pricey": v2["id"]}

    # cleanup
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.purchase_requisitions.delete_one({"id": pr_id})
        await db.rfqs.delete_one({"id": rfq["id"]})
        await db.purchase_orders.delete_many({"rfq_id": rfq["id"]})
        await db.vendors.delete_one({"id": v1["id"]})
        await db.vendors.delete_one({"id": v2["id"]})
    asyncio.run(_do())


# ─── Phase 2: L1/L2 ranks + justification ───────────────────────────

def test_comparative_assigns_l1_l2_ranks(admin, two_vendor_rfq):
    r = admin.get(f"/procurement/rfqs/{two_vendor_rfq['rfq_id']}/comparative")
    assert r.status_code == 200
    body = r.json()
    assert body["l1_vendor_id"] == two_vendor_rfq["v_cheap"]
    rows = body["rows"]
    assert rows[0]["rank"] == 1 and rows[0]["rank_label"] == "L1"
    assert rows[1]["rank"] == 2 and rows[1]["rank_label"] == "L2"
    # Delta-vs-L1 populated on the pricey row
    assert rows[1]["delta_vs_l1"] == 200.0   # (150 - 100) × 4
    assert rows[1]["delta_pct_vs_l1"] == 50.0


def test_select_l1_does_not_require_justification(admin, two_vendor_rfq):
    r = admin.post(f"/procurement/rfqs/{two_vendor_rfq['rfq_id']}/select-vendor",
                    json={"vendor_id": two_vendor_rfq["v_cheap"]})
    assert r.status_code == 200
    assert r.json()["non_l1_selection"] is False


def test_select_non_l1_requires_justification(admin, two_vendor_rfq):
    # Without justification → 400
    r = admin.post(f"/procurement/rfqs/{two_vendor_rfq['rfq_id']}/select-vendor",
                    json={"vendor_id": two_vendor_rfq["v_pricey"]})
    assert r.status_code == 400
    assert "justification" in r.json()["detail"].lower() or "L1" in r.json()["detail"]
    # Short justification → 400
    r2 = admin.post(f"/procurement/rfqs/{two_vendor_rfq['rfq_id']}/select-vendor",
                     json={"vendor_id": two_vendor_rfq["v_pricey"], "justification": "no"})
    assert r2.status_code == 400
    # Good justification → 200, flagged as non_l1
    r3 = admin.post(f"/procurement/rfqs/{two_vendor_rfq['rfq_id']}/select-vendor",
                     json={"vendor_id": two_vendor_rfq["v_pricey"],
                           "justification": "Cheap vendor cannot meet 3-day delivery deadline."})
    assert r3.status_code == 200
    assert r3.json()["non_l1_selection"] is True


# ─── Phase 3: Stock Ledger + reorder ────────────────────────────────

def test_stock_ledger_shape(admin):
    # Use any existing inventory item if available, else seed one
    inv = admin.get("/inventory").json()
    if not inv:
        seed = admin.post("/inventory", json={
            "code": f"ITR54-{int(time.time())}", "name": "Ledger Test", "uom": "Nos",
            "quantity": 10, "min_stock": 5, "rate": 100, "category": "test",
        }).json()
        item_id = seed["id"]
    else:
        item_id = inv[0]["id"]
    r = admin.get(f"/store/ledger/{item_id}")
    assert r.status_code == 200
    body = r.json()
    assert "item" in body and "opening" in body and "closing" in body
    assert "totals" in body and set(body["totals"]).issuperset({"receipt", "issue"})


def test_reorder_alerts_endpoint(admin):
    r = admin.get("/store/alerts/reorder")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body and "items" in body
    for it in body["items"]:
        assert it["severity"] in ("critical", "low", "warning")
        assert it["shortfall"] >= 0


# ─── Phase 3: GRN inspection workflow ───────────────────────────────

def test_grn_inspect_400_when_qty_overflows(admin, two_vendor_rfq):
    """Build a fresh GRN then try to inspect with accepted+rejected > received."""
    # Convert the (now-selected pricey) RFQ to PO
    po = admin.post(f"/procurement/rfqs/{two_vendor_rfq['rfq_id']}/convert-to-po").json()
    g = admin.post("/procurement/grns", json={
        "po_id": po["id"], "store_location": "STORE-INSP",
        "items": [{
            "po_item_index": 0, "item_name": "ITR54 Sprocket",
            "ordered_qty": 4, "received_qty": 4, "accepted_qty": 4, "rejected_qty": 0,
            "unit": "Nos", "inspection_status": "approved",
        }],
    }).json()

    # Overflow
    bad = admin.post(f"/procurement/grns/{g['id']}/inspect", json={
        "items": [{"index": 0, "accepted_qty": 3, "rejected_qty": 2, "reject_reason": "x"}],
    })
    assert bad.status_code == 400
    # Valid inspection: 3 accepted + 1 rejected = 4
    ok = admin.post(f"/procurement/grns/{g['id']}/inspect", json={
        "items": [{"index": 0, "accepted_qty": 3, "rejected_qty": 1,
                    "reject_reason": "Damaged threads"}],
        "overall_remarks": "Partially accepted",
    })
    assert ok.status_code == 200
    body = ok.json()
    assert body["total_accepted"] == 3
    assert body["total_rejected"] == 1
    assert body["inspection_status"] == "partial_accepted"
    assert body["items"][0]["reject_reason"] == "Damaged threads"

    # Cleanup
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.grn.delete_one({"id": g["id"]})
    asyncio.run(_do())


# ─── Phase 4: Reports ──────────────────────────────────────────────

def test_register_pr_returns_shape(admin):
    r = admin.get("/procurement/reports/register/pr?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "pr"
    assert "rows" in body and "count" in body and "total_value" in body


def test_register_invalid_kind_400(admin):
    r = admin.get("/procurement/reports/register/banana")
    assert r.status_code == 400


def test_pending_po_report_has_delay_days(admin):
    r = admin.get("/procurement/reports/pending-pos")
    assert r.status_code == 200
    rows = r.json()["rows"]
    for row in rows[:5]:
        assert "delay_days" in row


def test_by_dimension_aggregates(admin):
    for dim in ("department", "project", "vendor"):
        r = admin.get(f"/procurement/reports/by-dimension?dim={dim}")
        assert r.status_code == 200
        assert r.json()["dimension"] == dim
        for row in r.json()["rows"]:
            assert "label" in row and "po_count" in row and "total_value" in row


def test_by_dimension_400_for_bad_dim(admin):
    r = admin.get("/procurement/reports/by-dimension?dim=banana")
    assert r.status_code == 400


def test_rejected_material_report(admin):
    r = admin.get("/procurement/reports/rejected-material")
    assert r.status_code == 200
    assert "rows" in r.json() and "count" in r.json()
