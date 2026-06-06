"""Iteration 21 — Procurement Phase B (Material Allocations, Asset Lifecycle, Challans).

Tested against the public REACT_APP_BACKEND_URL using super_admin cookie session.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASS = "Admin@123"


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def inv_item(admin_session):
    """Create an inventory item with quantity=20 for allocation testing."""
    body = {
        "name": f"TEST_ALC_ITEM_{uuid.uuid4().hex[:6]}",
        "category": "Material",
        "unit": "Nos",
        "quantity": 20,
        "min_stock": 1,
        "rate": 100,
    }
    r = admin_session.post(f"{BASE_URL}/api/inventory", json=body, timeout=30)
    assert r.status_code in (200, 201), f"inventory create failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def asset(admin_session):
    """Pick or create an asset for lifecycle tests."""
    r = admin_session.get(f"{BASE_URL}/api/assets", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    if rows:
        return rows[0]
    body = {"name": f"TEST_ASSET_{uuid.uuid4().hex[:6]}", "category": "Equipment",
            "purchase_value": 100000, "current_book_value": 100000}
    r = admin_session.post(f"{BASE_URL}/api/assets", json=body, timeout=30)
    assert r.status_code in (200, 201)
    return r.json()


# ─── Material Allocations ────────────────────────────────────────────────────
class TestAllocations:
    def test_list_allocations_ok(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/allocations", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_allocation_decrements_inventory(self, admin_session, inv_item):
        before = admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}", timeout=30).json()
        before_qty = float(before["quantity"])
        body = {"kind": "material", "item_id": inv_item["id"], "item_name": inv_item["name"],
                "quantity": 5, "unit": "Nos", "allocated_to_type": "project",
                "project_code": "TEST_PRJ", "returnable": True}
        r = admin_session.post(f"{BASE_URL}/api/allocations", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc["allocation_no"].startswith("ALC-"), doc
        assert doc["status"] == "issued"
        assert doc["quantity"] == 5
        # Inventory decremented
        after = admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}", timeout=30).json()
        assert float(after["quantity"]) == before_qty - 5
        # Stash for next tests
        pytest.alloc_id = doc["id"]
        pytest.alloc_no = doc["allocation_no"]

    def test_insufficient_stock_returns_400(self, admin_session, inv_item):
        body = {"kind": "material", "item_id": inv_item["id"], "item_name": inv_item["name"],
                "quantity": 9999, "unit": "Nos"}
        r = admin_session.post(f"{BASE_URL}/api/allocations", json=body, timeout=30)
        assert r.status_code == 400
        assert "insufficient" in r.text.lower()

    def test_partial_return_then_full_return(self, admin_session, inv_item):
        aid = pytest.alloc_id
        inv_before = float(admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}").json()["quantity"])
        # Partial return 2
        r = admin_session.post(f"{BASE_URL}/api/allocations/{aid}/return",
                                json={"returned_qty": 2}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "partially_returned"
        assert float(body["returned_qty"]) == 2
        assert float(admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}").json()["quantity"]) == inv_before + 2
        # Over-return → 400
        r = admin_session.post(f"{BASE_URL}/api/allocations/{aid}/return",
                                json={"returned_qty": 50}, timeout=30)
        assert r.status_code == 400
        # Final return 3 → status=returned
        r = admin_session.post(f"{BASE_URL}/api/allocations/{aid}/return",
                                json={"returned_qty": 3}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "returned"

    def test_non_returnable_blocks_return(self, admin_session, inv_item):
        body = {"kind": "consumable", "item_id": inv_item["id"], "item_name": inv_item["name"],
                "quantity": 1, "unit": "Nos", "returnable": False}
        r = admin_session.post(f"{BASE_URL}/api/allocations", json=body, timeout=30)
        assert r.status_code in (200, 201)
        aid = r.json()["id"]
        r = admin_session.post(f"{BASE_URL}/api/allocations/{aid}/return",
                                json={"returned_qty": 1}, timeout=30)
        assert r.status_code == 400
        assert "non-returnable" in r.text.lower() or "non returnable" in r.text.lower()

    def test_delete_allocation_reverses_inventory(self, admin_session, inv_item):
        inv_before = float(admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}").json()["quantity"])
        body = {"kind": "material", "item_id": inv_item["id"], "item_name": inv_item["name"],
                "quantity": 2, "unit": "Nos"}
        r = admin_session.post(f"{BASE_URL}/api/allocations", json=body, timeout=30)
        assert r.status_code in (200, 201)
        aid = r.json()["id"]
        # delete reverses
        r = admin_session.delete(f"{BASE_URL}/api/allocations/{aid}", timeout=30)
        assert r.status_code == 200, r.text
        inv_after = float(admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}").json()["quantity"])
        assert inv_after == inv_before

    def test_delete_after_return_blocked(self, admin_session, inv_item):
        body = {"kind": "material", "item_id": inv_item["id"], "item_name": inv_item["name"],
                "quantity": 1, "unit": "Nos"}
        aid = admin_session.post(f"{BASE_URL}/api/allocations", json=body, timeout=30).json()["id"]
        admin_session.post(f"{BASE_URL}/api/allocations/{aid}/return", json={"returned_qty": 1}, timeout=30)
        r = admin_session.delete(f"{BASE_URL}/api/allocations/{aid}", timeout=30)
        assert r.status_code == 400

    def test_list_filters(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/allocations?status=returned", timeout=30)
        assert r.status_code == 200
        for row in r.json():
            assert row["status"] == "returned"


# ─── Asset Lifecycle ─────────────────────────────────────────────────────────
class TestAssetLifecycle:
    def test_get_lifecycle(self, admin_session, asset):
        r = admin_session.get(f"{BASE_URL}/api/assets/{asset['id']}/lifecycle", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("asset", "depreciation", "amcs", "calibrations", "warranty"):
            assert k in data

    def test_add_depreciation(self, admin_session, asset):
        body = {"period": "2026-01", "method": "straight_line",
                "opening_value": 100000, "depreciation": 1000, "closing_value": 99000}
        r = admin_session.post(f"{BASE_URL}/api/assets/{asset['id']}/depreciation",
                                json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        # Asset updated
        a = admin_session.get(f"{BASE_URL}/api/assets/{asset['id']}/lifecycle", timeout=30).json()["asset"]
        assert float(a.get("current_book_value")) == 99000
        assert a.get("last_dep_period") == "2026-01"

    def test_add_amc(self, admin_session, asset):
        body = {"vendor_name": "TEST_AMC_VENDOR", "start_date": "2026-01-01",
                "end_date": "2026-12-31", "amount": 5000}
        r = admin_session.post(f"{BASE_URL}/api/assets/{asset['id']}/amc", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        a = admin_session.get(f"{BASE_URL}/api/assets/{asset['id']}/lifecycle", timeout=30).json()["asset"]
        assert a.get("amc_active") is True
        assert a.get("amc_expiry") == "2026-12-31"

    def test_add_calibration(self, admin_session, asset):
        body = {"calibrated_by": "TEST_LAB", "calibration_date": "2026-01-15",
                "next_due_date": "2027-01-15", "result": "pass"}
        r = admin_session.post(f"{BASE_URL}/api/assets/{asset['id']}/calibration",
                                json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        a = admin_session.get(f"{BASE_URL}/api/assets/{asset['id']}/lifecycle", timeout=30).json()["asset"]
        assert a.get("last_calibration_date") == "2026-01-15"
        assert a.get("next_calibration_due") == "2027-01-15"

    def test_set_warranty(self, admin_session, asset):
        body = {"warranty_vendor": "TEST_WARR", "warranty_start": "2026-01-01",
                "warranty_expiry": "2027-01-01", "warranty_terms": "Std warranty"}
        r = admin_session.put(f"{BASE_URL}/api/assets/{asset['id']}/warranty",
                               json=body, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["warranty_vendor"] == "TEST_WARR"
        assert data["warranty_expiry"] == "2027-01-01"

    def test_lifecycle_404(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/assets/nope_xxx/lifecycle", timeout=30)
        assert r.status_code == 404


# ─── Challans ────────────────────────────────────────────────────────────────
class TestChallans:
    def test_create_delivery_challan(self, admin_session, inv_item):
        body = {"type": "delivery", "from_location": "Main Store",
                "to_location": "Site A", "vehicle_no": "MH01-1234",
                "driver_name": "Ram", "items": [
                    {"item_id": inv_item["id"], "name": inv_item["name"],
                     "quantity": 1, "unit": "Nos"}]}
        r = admin_session.post(f"{BASE_URL}/api/challans", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc["challan_no"].startswith("CH-")
        assert doc["qr_payload"] == f"CHALLAN:{doc['challan_no']}|{doc['id']}"
        pytest.challan_id = doc["id"]
        pytest.challan_no = doc["challan_no"]

    def test_list_challans_with_filters(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/challans?type=delivery", timeout=30)
        assert r.status_code == 200
        for row in r.json():
            assert row["type"] == "delivery"

    def test_inter_site_transfer_debits_source(self, admin_session, inv_item):
        before = float(admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}").json()["quantity"])
        body = {"type": "inter_site_transfer", "from_location": "Site A",
                "to_location": "Site B", "items": [
                    {"item_id": inv_item["id"], "name": inv_item["name"],
                     "quantity": 2, "unit": "Nos"}]}
        r = admin_session.post(f"{BASE_URL}/api/challans", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
        after = float(admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}").json()["quantity"])
        assert after == before - 2
        # Receive credits destination
        r = admin_session.post(f"{BASE_URL}/api/challans/{cid}/receive",
                                json={"receiver_name": "TEST_Recv"}, timeout=30)
        assert r.status_code == 200, r.text
        rcv = r.json()
        assert rcv["status"] == "received"
        sig = rcv.get("e_signature") or {}
        for k in ("name", "user_id", "user_name", "ip", "signed_at"):
            assert k in sig, f"e_signature missing {k}: {sig}"
        after2 = float(admin_session.get(f"{BASE_URL}/api/inventory/{inv_item['id']}").json()["quantity"])
        assert after2 == before

    def test_receive_captures_esignature(self, admin_session):
        cid = pytest.challan_id
        r = admin_session.post(f"{BASE_URL}/api/challans/{cid}/receive",
                                json={"receiver_name": "TEST_Receiver"}, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "received"
        assert doc["e_signature"]["name"] == "TEST_Receiver"

    def test_delete_received_blocked(self, admin_session):
        cid = pytest.challan_id
        r = admin_session.delete(f"{BASE_URL}/api/challans/{cid}", timeout=30)
        assert r.status_code == 400

    def test_delete_unreceived_ok(self, admin_session, inv_item):
        body = {"type": "delivery", "items": [
            {"name": "TEST_VIRTUAL", "quantity": 1, "unit": "Nos"}]}
        cid = admin_session.post(f"{BASE_URL}/api/challans", json=body, timeout=30).json()["id"]
        r = admin_session.delete(f"{BASE_URL}/api/challans/{cid}", timeout=30)
        assert r.status_code == 200

    def test_bad_challan_type_rejected(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/challans",
                                json={"type": "nope", "items": [{"name": "x", "quantity": 1}]}, timeout=30)
        assert r.status_code in (400, 422)

    def test_empty_items_rejected(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/challans",
                                json={"type": "delivery", "items": []}, timeout=30)
        assert r.status_code == 400
