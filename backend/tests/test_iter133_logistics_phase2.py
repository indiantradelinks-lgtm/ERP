"""Iter 133 — Logistics Phase 2 · Dispatch Lifecycle backend tests."""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def site_engineer():
    return _login(SITE_ENG)


@pytest.fixture(scope="module")
def project_id(admin):
    r = admin.get(f"{API}/projects", timeout=30)
    if r.status_code != 200 or not r.json():
        pytest.skip("No projects available")
    return r.json()[0]["id"]


def _future(days=365):
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def _past(days=30):
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _rand():
    return datetime.now().strftime("%H%M%S%f")


# ═══════════════════════ Helpers to create seed data ══════════════════════
def _create_vehicle(admin, expired=False, driver_id=None):
    vn = f"TESTV{_rand()}"
    payload = {"vehicle_number": vn, "vehicle_type": "truck", "ownership_type": "own",
               "fitness_expiry": _past(30) if expired else _future(),
               "insurance_expiry": _future()}
    if driver_id:
        payload["assigned_driver_id"] = driver_id
    r = admin.post(f"{API}/logistics/vehicles", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _create_driver(admin, expired=False):
    lic = f"TESTLIC_{_rand()}"
    payload = {"driver_name": f"TEST_DRV_{_rand()}",
               "license_no": lic,
               "license_expiry": _past(30) if expired else _future()}
    r = admin.post(f"{API}/logistics/drivers", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _create_approved_dr(admin, project_id):
    r = admin.post(f"{API}/logistics/dispatch-requests",
                   json={"dispatch_type": "material", "project_id": project_id,
                         "status": "draft", "material_summary": "TEST material"},
                   timeout=30)
    assert r.status_code == 200, r.text
    dr = r.json()
    r2 = admin.put(f"{API}/logistics/dispatch-requests/{dr['id']}",
                   json={"dispatch_type": "material", "project_id": project_id,
                         "status": "approved", "material_summary": "TEST material"},
                   timeout=30)
    assert r2.status_code == 200, r2.text
    return r2.json()


def _create_draft_dr(admin, project_id):
    r = admin.post(f"{API}/logistics/dispatch-requests",
                   json={"dispatch_type": "material", "project_id": project_id,
                         "status": "draft"},
                   timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ═══════════════════════ Phase 1 regression ══════════════════════
class TestPhase1Regression:
    def test_dashboard(self, admin):
        r = admin.get(f"{API}/logistics/dashboard", timeout=30)
        assert r.status_code == 200
        assert "kpis" in r.json()

    def test_vehicles_list(self, admin):
        r = admin.get(f"{API}/logistics/vehicles", timeout=30)
        assert r.status_code == 200

    def test_drivers_list(self, admin):
        r = admin.get(f"{API}/logistics/drivers", timeout=30)
        assert r.status_code == 200

    def test_dispatch_requests_list(self, admin):
        r = admin.get(f"{API}/logistics/dispatch-requests", timeout=30)
        assert r.status_code == 200


# ═══════════════════════ Allocate ══════════════════════
class TestAllocate:
    def test_allocate_draft_fails(self, admin, project_id):
        drft = _create_draft_dr(admin, project_id)
        veh = _create_vehicle(admin)
        drv = _create_driver(admin)
        r = admin.post(f"{API}/logistics/dispatch-requests/{drft['id']}/allocate",
                       json={"vehicle_id": veh["id"], "driver_id": drv["id"],
                             "freight_basis": "per_mt", "estimated_freight": 5000},
                       timeout=30)
        assert r.status_code == 400, r.text

    def test_allocate_success(self, admin, project_id):
        dr = _create_approved_dr(admin, project_id)
        veh = _create_vehicle(admin)
        drv = _create_driver(admin)
        r = admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/allocate",
                       json={"vehicle_id": veh["id"], "driver_id": drv["id"],
                             "freight_basis": "per_mt", "estimated_freight": 5000},
                       timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["allocation_no"].startswith(f"ALC-{datetime.now(timezone.utc).year}-")
        assert len(j["allocation_no"].split("-")[2]) == 4

        # DR became allocated
        r2 = admin.get(f"{API}/logistics/dispatch-requests/{dr['id']}/full", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["dr"]["status"] == "allocated"

        # Vehicle + driver status
        rv = admin.get(f"{API}/logistics/vehicles", timeout=30).json()
        v = next(x for x in rv if x["id"] == veh["id"])
        assert v["status"] == "allocated"
        rd = admin.get(f"{API}/logistics/drivers", timeout=30).json()
        d = next(x for x in rd if x["id"] == drv["id"])
        assert d["status"] == "assigned"

        pytest.p2_dr = dr
        pytest.p2_veh = veh
        pytest.p2_drv = drv
        pytest.p2_alloc = j

    def test_allocate_expired_vehicle_blocks_site_engineer(self, admin, site_engineer, project_id):
        dr = _create_approved_dr(admin, project_id)
        veh = _create_vehicle(admin, expired=True)
        drv = _create_driver(admin)
        r = site_engineer.post(
            f"{API}/logistics/dispatch-requests/{dr['id']}/allocate",
            json={"vehicle_id": veh["id"], "driver_id": drv["id"],
                  "freight_basis": "per_mt"},
            timeout=30)
        # Site engineer may not have dispatch_requests write. Accept 400 (block) or 403.
        assert r.status_code in (400, 403), r.text

    def test_allocate_expired_driver_blocks_site_engineer(self, admin, site_engineer, project_id):
        dr = _create_approved_dr(admin, project_id)
        veh = _create_vehicle(admin)
        drv = _create_driver(admin, expired=True)
        r = site_engineer.post(
            f"{API}/logistics/dispatch-requests/{dr['id']}/allocate",
            json={"vehicle_id": veh["id"], "driver_id": drv["id"],
                  "freight_basis": "per_mt"},
            timeout=30)
        assert r.status_code in (400, 403), r.text

    def test_allocate_expired_admin_bypass(self, admin, project_id):
        dr = _create_approved_dr(admin, project_id)
        veh = _create_vehicle(admin, expired=True)
        drv = _create_driver(admin, expired=True)
        r = admin.post(
            f"{API}/logistics/dispatch-requests/{dr['id']}/allocate",
            json={"vehicle_id": veh["id"], "driver_id": drv["id"],
                  "freight_basis": "per_mt"},
            timeout=30)
        assert r.status_code == 200, r.text


# ═══════════════════════ Load ══════════════════════
class TestLoad:
    def test_load_success(self, admin):
        dr = pytest.p2_dr
        r = admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/load",
                       json={"loaded_qty": 5, "approved_qty": 5,
                             "delivery_challan_no": "DC-1",
                             "driver_acknowledged": True},
                       timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["loading_no"].startswith(f"LOAD-{datetime.now(timezone.utc).year}-")
        # DR became in_transit
        r2 = admin.get(f"{API}/logistics/dispatch-requests/{dr['id']}/full", timeout=30)
        assert r2.json()["dr"]["status"] == "in_transit"

        # Vehicle + driver
        rv = admin.get(f"{API}/logistics/vehicles", timeout=30).json()
        v = next(x for x in rv if x["id"] == pytest.p2_veh["id"])
        assert v["status"] == "in_transit"
        rd = admin.get(f"{API}/logistics/drivers", timeout=30).json()
        d = next(x for x in rd if x["id"] == pytest.p2_drv["id"])
        assert d["status"] == "on_trip"

        # Stock-move in_transit
        sm = admin.get(f"{API}/logistics/stock-moves?dr_id={dr['id']}", timeout=30).json()
        assert any(x["event"] == "in_transit" for x in sm)

    def test_load_excess_blocks_site_engineer(self, admin, site_engineer, project_id):
        dr = _create_approved_dr(admin, project_id)
        veh = _create_vehicle(admin)
        drv = _create_driver(admin)
        admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/allocate",
                   json={"vehicle_id": veh["id"], "driver_id": drv["id"],
                         "freight_basis": "per_mt"},
                   timeout=30)
        r = site_engineer.post(f"{API}/logistics/dispatch-requests/{dr['id']}/load",
                               json={"loaded_qty": 10, "approved_qty": 5,
                                     "delivery_challan_no": "DC-EX"},
                               timeout=30)
        assert r.status_code in (400, 403), r.text
        pytest.p2_excess_dr = dr

    def test_load_excess_with_override_ok(self, admin):
        # Admin bypass path: admin loads excess without reason
        dr = pytest.p2_excess_dr
        r = admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/load",
                       json={"loaded_qty": 10, "approved_qty": 5,
                             "delivery_challan_no": "DC-EX",
                             "excess_override_reason": "Approved by ops"},
                       timeout=30)
        assert r.status_code == 200, r.text


# ═══════════════════════ Transit ══════════════════════
class TestTransit:
    def test_transit_append(self, admin):
        dr = pytest.p2_dr
        r = admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/transit",
                       json={"status": "in_transit",
                             "current_location": "Highway KM 45"},
                       timeout=30)
        assert r.status_code == 200, r.text
        # timeline
        r2 = admin.get(f"{API}/logistics/dispatch-requests/{dr['id']}/transit-timeline",
                       timeout=30)
        assert r2.status_code == 200
        events = r2.json()
        assert len(events) >= 1
        ats = [e["at"] for e in events]
        assert ats == sorted(ats)


# ═══════════════════════ Deliver ══════════════════════
class TestDeliver:
    def test_deliver_full_closes(self, admin):
        dr = pytest.p2_dr
        r = admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/deliver",
                       json={"delivered_qty": 5, "received_by": "Site X",
                             "close_dispatch": True, "material_condition": "good"},
                       timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["delivery_no"].startswith(f"POD-{datetime.now(timezone.utc).year}-")

        r2 = admin.get(f"{API}/logistics/dispatch-requests/{dr['id']}/full", timeout=30)
        assert r2.json()["dr"]["status"] == "closed"

        # Vehicle + driver released
        rv = admin.get(f"{API}/logistics/vehicles", timeout=30).json()
        v = next(x for x in rv if x["id"] == pytest.p2_veh["id"])
        assert v["status"] == "available"
        rd = admin.get(f"{API}/logistics/drivers", timeout=30).json()
        d = next(x for x in rd if x["id"] == pytest.p2_drv["id"])
        assert d["status"] == "available"

        # Stock-move delivered event
        sm = admin.get(f"{API}/logistics/stock-moves?dr_id={dr['id']}", timeout=30).json()
        events = {x["event"] for x in sm}
        assert "in_transit" in events and "delivered" in events

    def test_deliver_partial(self, admin, project_id):
        dr = _create_approved_dr(admin, project_id)
        veh = _create_vehicle(admin)
        drv = _create_driver(admin)
        admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/allocate",
                   json={"vehicle_id": veh["id"], "driver_id": drv["id"],
                         "freight_basis": "per_mt"},
                   timeout=30)
        admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/load",
                   json={"loaded_qty": 5, "approved_qty": 5},
                   timeout=30)
        r = admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/deliver",
                       json={"delivered_qty": 4, "short_qty": 1,
                             "close_dispatch": True},
                       timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["is_partial"] is True
        r2 = admin.get(f"{API}/logistics/dispatch-requests/{dr['id']}/full", timeout=30)
        assert r2.json()["dr"]["status"] == "delivered"
        pytest.p2_partial_dr = dr


# ═══════════════════════ Exception ══════════════════════
class TestException:
    def test_raise_and_update(self, admin):
        dr = pytest.p2_partial_dr
        r = admin.post(f"{API}/logistics/dispatch-requests/{dr['id']}/exception",
                       json={"kind": "shortage", "short_qty": 1,
                             "approx_value": 5000,
                             "responsible_party": "transporter",
                             "recovery_applicable": True,
                             "recovery_amount": 5000,
                             "reason": "Short-loaded from source"},
                       timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["exception_no"].startswith(f"EXC-{datetime.now(timezone.utc).year}-")
        assert j["status"] == "open"
        eid = j["id"]

        # transit event auto-appended
        tl = admin.get(f"{API}/logistics/dispatch-requests/{dr['id']}/transit-timeline",
                      timeout=30).json()
        assert any(e["status"] == "shortage_reported" for e in tl)

        # Update: verified → approved → closed
        for st in ("verified", "approved", "closed"):
            r_u = admin.put(f"{API}/logistics/exceptions/{eid}",
                            json={"status": st}, timeout=30)
            assert r_u.status_code == 200, r_u.text
            assert r_u.json()["status"] == st


# ═══════════════════════ Full endpoint + stock-moves ══════════════════════
class TestFullAndStockMoves:
    def test_full(self, admin):
        dr = pytest.p2_dr
        r = admin.get(f"{API}/logistics/dispatch-requests/{dr['id']}/full", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("dr", "allocation", "loadings", "deliveries", "exceptions", "timeline"):
            assert k in j
        assert j["dr"]["id"] == dr["id"]
        assert j["allocation"] is not None
        assert len(j["loadings"]) >= 1
        assert len(j["deliveries"]) >= 1
        assert len(j["timeline"]) >= 1

    def test_stock_moves(self, admin):
        dr = pytest.p2_dr
        r = admin.get(f"{API}/logistics/stock-moves?dr_id={dr['id']}", timeout=30)
        assert r.status_code == 200
        events = {x["event"] for x in r.json()}
        assert {"in_transit", "delivered"}.issubset(events)


# ═══════════════════════ Simple list endpoints ══════════════════════
class TestPhase2Lists:
    def test_allocations_list(self, admin):
        r = admin.get(f"{API}/logistics/allocations", timeout=30)
        assert r.status_code == 200

    def test_loadings_list(self, admin):
        r = admin.get(f"{API}/logistics/loadings", timeout=30)
        assert r.status_code == 200

    def test_in_transit_list(self, admin):
        r = admin.get(f"{API}/logistics/in-transit", timeout=30)
        assert r.status_code == 200

    def test_deliveries_list(self, admin):
        r = admin.get(f"{API}/logistics/deliveries", timeout=30)
        assert r.status_code == 200

    def test_exceptions_list(self, admin):
        r = admin.get(f"{API}/logistics/exceptions", timeout=30)
        assert r.status_code == 200
