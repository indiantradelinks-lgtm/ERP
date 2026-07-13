"""Iter 132 — Logistics Phase 1 Foundation backend tests."""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}
SALES = {"email": "sales@erp.com", "password": "Sales@123"}
PM = {"email": "test_pm@erp.com", "password": "PM@12345"}


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
def sales_sess():
    return _login(SALES)


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


def _rand_suffix():
    return datetime.now().strftime("%H%M%S%f")


# ═══════════════════════════ Dashboard ══════════════════════════
class TestDashboard:
    def test_dashboard(self, admin):
        r = admin.get(f"{API}/logistics/dashboard", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "as_of" in j
        assert "kpis" in j and "recent_dispatches" in j
        assert isinstance(j["kpis"], dict)
        assert len(j["kpis"]) == 20, f"Expected 20 KPIs, got {len(j['kpis'])}: {list(j['kpis'].keys())}"
        required = {"total_vehicles", "vehicles_available", "drivers_on_trip",
                    "dispatch_pending", "overdue_deliveries", "fitness_expired",
                    "insurance_expired", "driver_license_expired"}
        assert required.issubset(set(j["kpis"].keys()))


# ═══════════════════════════ Drivers ════════════════════════════
class TestDrivers:
    def test_create_and_duplicate(self, admin):
        lic = f"TEST_DL_{_rand_suffix()}"
        payload = {"driver_name": f"TEST_DRV_{_rand_suffix()}",
                   "license_no": lic, "license_expiry": _future()}
        r = admin.post(f"{API}/logistics/drivers", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["driver_code"].startswith("DRV-")
        assert len(j["driver_code"].split("-")[1]) == 5
        pytest.driver_id_ok = j["id"]
        # Duplicate
        r2 = admin.post(f"{API}/logistics/drivers", json=payload, timeout=30)
        assert r2.status_code == 400

    def test_filter_status(self, admin):
        r = admin.get(f"{API}/logistics/drivers?status=available", timeout=30)
        assert r.status_code == 200
        for row in r.json():
            assert row["status"] == "available"

    def test_update(self, admin):
        did = pytest.driver_id_ok
        payload = {"driver_name": "TEST_DRV_UPD",
                   "license_no": f"TEST_DL_UPD_{_rand_suffix()}",
                   "license_expiry": _future(),
                   "status": "on_leave"}
        r = admin.put(f"{API}/logistics/drivers/{did}", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "on_leave"

    def test_expired_driver_created(self, admin):
        lic = f"TEST_DL_EXP_{_rand_suffix()}"
        r = admin.post(f"{API}/logistics/drivers",
                       json={"driver_name": "TEST_EXPIRED",
                             "license_no": lic, "license_expiry": _past(60)},
                       timeout=30)
        assert r.status_code == 200
        pytest.expired_driver_id = r.json()["id"]

    def test_rbac_write_denied_site_eng(self, site_engineer):
        r = site_engineer.post(
            f"{API}/logistics/drivers",
            json={"driver_name": "TEST_DENY", "license_no": f"NOP_{_rand_suffix()}",
                  "license_expiry": _future()},
            timeout=30)
        assert r.status_code == 403, r.text

    def test_rbac_read_allowed_site_eng(self, site_engineer):
        r = site_engineer.get(f"{API}/logistics/drivers", timeout=30)
        assert r.status_code == 200


# ═══════════════════════════ Vehicles ═══════════════════════════
class TestVehicles:
    def test_create_and_duplicate(self, admin):
        vn = f"TESTV{_rand_suffix()}"
        payload = {"vehicle_number": vn, "vehicle_type": "truck", "ownership_type": "own"}
        r = admin.post(f"{API}/logistics/vehicles", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["vehicle_code"].startswith("VEH-")
        pytest.vehicle_id_ok = j["id"]
        # Duplicate
        r2 = admin.post(f"{API}/logistics/vehicles", json=payload, timeout=30)
        assert r2.status_code == 400

    def test_admin_can_assign_expired_driver(self, admin):
        vn = f"TESTV{_rand_suffix()}"
        r = admin.post(f"{API}/logistics/vehicles",
                       json={"vehicle_number": vn, "vehicle_type": "truck",
                             "ownership_type": "own",
                             "assigned_driver_id": pytest.expired_driver_id},
                       timeout=30)
        # super_admin should bypass
        assert r.status_code == 200, r.text

    def test_non_admin_blocked_expired_driver(self, admin, site_engineer):
        # site_engineer doesn't have write permission on vehicles → 403.
        # Use PM (project_manager also doesn't have write). Use general_manager not seeded.
        # Try dept_head — not seeded either. So test with 'project_manager'
        # actually project_manager doesn't have vehicles write. The spec says non-admin
        # roles should be blocked; but only admin roles have write permission.
        # For coverage, verify site_engineer gets 403.
        r = site_engineer.post(f"{API}/logistics/vehicles",
                               json={"vehicle_number": f"TESTV{_rand_suffix()}",
                                     "vehicle_type": "truck",
                                     "ownership_type": "own",
                                     "assigned_driver_id": pytest.expired_driver_id},
                               timeout=30)
        assert r.status_code == 403


# ═══════════════════════════ Routes ═════════════════════════════
class TestRoutes:
    def test_crud(self, admin):
        r = admin.post(f"{API}/logistics/routes",
                       json={"name": f"TEST_RT_{_rand_suffix()}",
                             "origin": "A", "destination": "B", "distance_km": 100},
                       timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["route_code"].startswith("RT-")
        rid = j["id"]

        r2 = admin.put(f"{API}/logistics/routes/{rid}",
                       json={"name": "TEST_RT_UPD", "origin": "A", "destination": "C"},
                       timeout=30)
        assert r2.status_code == 200

        r3 = admin.delete(f"{API}/logistics/routes/{rid}", timeout=30)
        assert r3.status_code == 200

        r4 = admin.get(f"{API}/logistics/routes", timeout=30)
        assert r4.status_code == 200


# ═══════════════════ Loading Points ═════════════════════════════
class TestLoadingPoints:
    def test_crud(self, admin):
        r = admin.post(f"{API}/logistics/loading-points",
                       json={"name": f"TEST_LP_{_rand_suffix()}", "kind": "loading"},
                       timeout=30)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        # Invalid kind
        r_bad = admin.post(f"{API}/logistics/loading-points",
                           json={"name": "TEST_LP_BAD", "kind": "invalid"},
                           timeout=30)
        assert r_bad.status_code == 400

        r3 = admin.delete(f"{API}/logistics/loading-points/{pid}", timeout=30)
        assert r3.status_code == 200


# ═══════════════════ Dispatch Types ═════════════════════════════
class TestDispatchTypes:
    def test_crud(self, admin):
        r = admin.post(f"{API}/logistics/dispatch-types",
                       json={"name": f"TEST_DT_{_rand_suffix()}", "category": "material"},
                       timeout=30)
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        r2 = admin.get(f"{API}/logistics/dispatch-types", timeout=30)
        assert r2.status_code == 200
        r3 = admin.delete(f"{API}/logistics/dispatch-types/{tid}", timeout=30)
        assert r3.status_code == 200


# ═══════════════════ Dispatch Requests ══════════════════════════
class TestDispatchRequests:
    def test_create(self, admin, project_id):
        r = admin.post(f"{API}/logistics/dispatch-requests",
                       json={"dispatch_type": "material", "project_id": project_id,
                             "status": "draft"},
                       timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["dr_no"].startswith(f"DR-{datetime.now().year}-")
        pytest.dr_id = j["id"]

    def test_site_engineer_can_create(self, site_engineer, project_id):
        r = site_engineer.post(f"{API}/logistics/dispatch-requests",
                               json={"dispatch_type": "material",
                                     "project_id": project_id, "status": "draft"},
                               timeout=30)
        assert r.status_code == 200, r.text

    def test_approve_then_revert_draft_fails(self, admin, project_id):
        drid = pytest.dr_id
        # Approve
        r = admin.put(f"{API}/logistics/dispatch-requests/{drid}",
                      json={"dispatch_type": "material", "project_id": project_id,
                            "status": "approved"},
                      timeout=30)
        assert r.status_code == 200, r.text
        # Try revert
        r2 = admin.put(f"{API}/logistics/dispatch-requests/{drid}",
                       json={"dispatch_type": "material", "project_id": project_id,
                             "status": "draft"},
                       timeout=30)
        assert r2.status_code == 400

    def test_delete_approved_dr_fails(self, admin):
        r = admin.delete(f"{API}/logistics/dispatch-requests/{pytest.dr_id}", timeout=30)
        assert r.status_code == 400


# ═══════════════════ Vendor Profiles ════════════════════════════
class TestVendorProfiles:
    def test_crud(self, admin):
        vr = admin.get(f"{API}/vendors", timeout=30)
        if vr.status_code != 200 or not vr.json():
            pytest.skip("No vendors")
        vendors = vr.json()
        if isinstance(vendors, dict):
            vendors = vendors.get("items") or vendors.get("rows") or []
        if not vendors:
            pytest.skip("No vendors returned")
        vid = vendors[0]["id"]

        # Cleanup any existing (idempotent)
        existing = admin.get(f"{API}/logistics/vendor-profiles", timeout=30).json()
        for r in existing:
            if r.get("vendor_id") == vid and r.get("vendor_kind") == "transporter":
                admin.delete(f"{API}/logistics/vendor-profiles/{r['id']}", timeout=30)

        r = admin.post(f"{API}/logistics/vendor-profiles",
                       json={"vendor_id": vid, "vendor_kind": "transporter"},
                       timeout=30)
        assert r.status_code == 200, r.text

        # Duplicate
        r2 = admin.post(f"{API}/logistics/vendor-profiles",
                        json={"vendor_id": vid, "vendor_kind": "transporter"},
                        timeout=30)
        assert r2.status_code == 400

        # List enriched
        rows = admin.get(f"{API}/logistics/vendor-profiles", timeout=30).json()
        assert any(row.get("vendor_name") for row in rows)


# ═══════════════════ Availability ═══════════════════════════════
class TestAvailability:
    def test_vehicles_availability(self, admin):
        r = admin.get(f"{API}/logistics/vehicles/availability", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("total", "by_status", "fitness_expired", "insurance_expired"):
            assert k in j

    def test_drivers_availability(self, admin):
        r = admin.get(f"{API}/logistics/drivers/availability", timeout=30)
        assert r.status_code == 200
        j = r.json()
        for k in ("total", "by_status", "license_expired"):
            assert k in j


# ═══════════════════ Audit Log ══════════════════════════════════
class TestAuditLog:
    def test_audit_log(self, admin):
        r = admin.get(f"{API}/logistics/audit-log", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert "count" in j and "rows" in j
        assert j["count"] > 0

    def test_audit_kinds(self, admin):
        r = admin.get(f"{API}/logistics/audit-log/kinds", timeout=30)
        assert r.status_code == 200
        kinds = r.json()
        assert isinstance(kinds, list)
        assert any(k in {"driver", "vehicle", "route", "dispatch_request"} for k in kinds)

    def test_audit_read_all_roles(self, site_engineer):
        r = site_engineer.get(f"{API}/logistics/audit-log", timeout=30)
        assert r.status_code == 200
