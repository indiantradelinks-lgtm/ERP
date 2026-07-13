"""Iter 135 — Logistics Phase 4 · Fuel/Expense/Maintenance/VendorBill/Cost backend tests."""
import os
from datetime import datetime, timezone

import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code}")
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


def _rand():
    return datetime.now().strftime("%H%M%S%f")


def _today():
    return datetime.now(timezone.utc).date().isoformat()


@pytest.fixture(scope="module")
def vehicle_id(admin):
    vn = f"TESTV4{_rand()}"
    r = admin.post(f"{API}/logistics/vehicles", json={
        "vehicle_number": vn, "vehicle_type": "truck", "ownership_type": "own",
        "fitness_expiry": "2099-01-01", "insurance_expiry": "2099-01-01"
    }, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"vehicle create failed: {r.text}")
    return r.json()["id"]


@pytest.fixture(scope="module")
def vendor_id(admin):
    r = admin.get(f"{API}/vendors", timeout=30)
    if r.status_code == 200 and r.json():
        return r.json()[0]["id"]
    # create a vendor if API allows
    r2 = admin.post(f"{API}/vendors", json={"name": f"TESTVENDOR{_rand()}", "gstin": ""}, timeout=30)
    if r2.status_code in (200, 201):
        return r2.json().get("id")
    pytest.skip("no vendor available")


# ═══════════════ Fuel ═══════════════
class TestFuel:
    def test_create_fuel(self, admin, vehicle_id):
        pytest.fuel_bill = f"F{_rand()}"
        r = admin.post(f"{API}/logistics/fuel-entries", json={
            "vehicle_id": vehicle_id, "quantity_ltrs": 50, "rate": 100,
            "bill_no": pytest.fuel_bill, "fuel_station": "HP",
            "entry_date": _today(), "project_code": "P1",
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["fuel_no"].startswith("FUEL-")
        assert d["amount"] == 5000
        pytest.fuel_id = d["id"]

    def test_duplicate_fuel(self, admin, vehicle_id):
        r = admin.post(f"{API}/logistics/fuel-entries", json={
            "vehicle_id": vehicle_id, "quantity_ltrs": 50, "rate": 100,
            "bill_no": pytest.fuel_bill, "fuel_station": "HP",
            "entry_date": _today(),
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_approve_fuel_emits_cost(self, admin, vehicle_id):
        r = admin.put(f"{API}/logistics/fuel-entries/{pytest.fuel_id}", json={
            "vehicle_id": vehicle_id, "quantity_ltrs": 50, "rate": 100,
            "bill_no": pytest.fuel_bill, "fuel_station": "HP",
            "entry_date": _today(), "project_code": "P1", "status": "approved",
        }, timeout=30)
        assert r.status_code == 200, r.text
        # check cost allocations
        ca = admin.get(f"{API}/logistics/cost-allocations?category=fuel", timeout=30).json()
        assert any(c["source_id"] == pytest.fuel_id for c in ca), "No fuel cost allocation"


# ═══════════════ Vehicle Expense ═══════════════
class TestVehicleExpense:
    def test_invalid_category(self, admin, vehicle_id):
        r = admin.post(f"{API}/logistics/vehicle-expenses", json={
            "vehicle_id": vehicle_id, "category": "bogus", "amount": 500
        }, timeout=30)
        assert r.status_code == 400

    def test_create_and_approve(self, admin, vehicle_id):
        r = admin.post(f"{API}/logistics/vehicle-expenses", json={
            "vehicle_id": vehicle_id, "category": "toll", "amount": 500,
            "project_code": "P1"
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["expense_no"].startswith("EXP-")
        eid = d["id"]
        r = admin.put(f"{API}/logistics/vehicle-expenses/{eid}", json={
            "vehicle_id": vehicle_id, "category": "toll", "amount": 500,
            "project_code": "P1", "status": "approved"
        }, timeout=30)
        assert r.status_code == 200, r.text
        ca = admin.get(f"{API}/logistics/cost-allocations?category=toll", timeout=30).json()
        assert any(c["source_id"] == eid for c in ca), "No toll cost allocation"


# ═══════════════ Maintenance ═══════════════
class TestMaintenance:
    def test_maint_create_moves_vehicle_to_maintenance(self, admin, vehicle_id):
        r = admin.post(f"{API}/logistics/maintenance", json={
            "vehicle_id": vehicle_id, "maintenance_type": "preventive",
            "cost": 5000, "status": "in_progress", "project_code": "P1"
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["maint_no"].startswith("MNT-")
        pytest.maint_id = d["id"]
        # Vehicle status
        v = admin.get(f"{API}/logistics/vehicles/{vehicle_id}", timeout=30)
        if v.status_code == 200:
            assert v.json().get("status") == "maintenance"

    def test_maint_complete_returns_available_and_emits_cost(self, admin, vehicle_id):
        r = admin.put(f"{API}/logistics/maintenance/{pytest.maint_id}", json={
            "vehicle_id": vehicle_id, "maintenance_type": "preventive",
            "cost": 5000, "status": "approved", "project_code": "P1"
        }, timeout=30)
        assert r.status_code == 200, r.text
        v = admin.get(f"{API}/logistics/vehicles/{vehicle_id}", timeout=30)
        if v.status_code == 200:
            assert v.json().get("status") == "available"
        ca = admin.get(f"{API}/logistics/cost-allocations?category=vehicle_maintenance", timeout=30).json()
        assert any(c["source_id"] == pytest.maint_id for c in ca), "No maintenance cost allocation"


# ═══════════════ Vendor Bill ═══════════════
class TestVendorBill:
    def test_create_vb(self, admin, vendor_id):
        pytest.vb_billno = f"VB-{_rand()}"
        r = admin.post(f"{API}/logistics/vendor-bills", json={
            "vendor_id": vendor_id, "bill_no": pytest.vb_billno,
            "freight_amount": 10000, "gst_amount": 1800, "tds_amount": 200,
            "project_code": "P1",
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["vb_no"].startswith("VB-")
        assert d["net_payable"] == 11600
        pytest.vb_id = d["id"]

    def test_duplicate_vb(self, admin, vendor_id):
        r = admin.post(f"{API}/logistics/vendor-bills", json={
            "vendor_id": vendor_id, "bill_no": pytest.vb_billno,
            "freight_amount": 10000
        }, timeout=30)
        assert r.status_code == 400

    def test_approve_vb_emits_cost_and_event(self, admin, vendor_id):
        r = admin.put(f"{API}/logistics/vendor-bills/{pytest.vb_id}", json={
            "vendor_id": vendor_id, "bill_no": pytest.vb_billno,
            "freight_amount": 10000, "gst_amount": 1800, "tds_amount": 200,
            "net_payable": 11600, "project_code": "P1", "status": "approved"
        }, timeout=30)
        assert r.status_code == 200, r.text
        ca = admin.get(f"{API}/logistics/cost-allocations?category=freight", timeout=30).json()
        assert any(c["source_id"] == pytest.vb_id for c in ca), "No freight cost allocation"
        ev = admin.get(f"{API}/logistics/accounts-events?event=vendor_bill_approved", timeout=30).json()
        assert any(e.get("bill_no") == pytest.vb_billno for e in ev), "No vendor_bill_approved event"

    def test_high_value_flag(self, admin, vendor_id):
        bill_no = f"VBHV-{_rand()}"
        r = admin.post(f"{API}/logistics/vendor-bills", json={
            "vendor_id": vendor_id, "bill_no": bill_no,
            "freight_amount": 60000, "project_code": "PH"
        }, timeout=30)
        vid = r.json()["id"]
        r = admin.put(f"{API}/logistics/vendor-bills/{vid}", json={
            "vendor_id": vendor_id, "bill_no": bill_no,
            "freight_amount": 60000, "net_payable": 60000,
            "project_code": "PH", "status": "approved"
        }, timeout=30)
        assert r.status_code == 200, r.text
        ca = admin.get(f"{API}/logistics/cost-allocations?category=freight", timeout=30).json()
        hv = [c for c in ca if c["source_id"] == vid]
        assert hv and hv[0]["high_value"] is True


# ═══════════════ Cost views ═══════════════
def test_cost_summary(admin):
    r = admin.get(f"{API}/logistics/cost-summary", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ["total_cost", "this_month", "high_value_pending", "by_project", "by_category"]:
        assert k in d
    assert len(d["by_category"]) > 0, "by_category should have entries after approvals"


def test_accounts_events_list(admin):
    r = admin.get(f"{API}/logistics/accounts-events", timeout=30)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
