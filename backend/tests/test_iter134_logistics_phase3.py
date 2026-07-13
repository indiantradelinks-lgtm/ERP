"""Iter 134 — Logistics Phase 3 · Manpower Mobilization backend tests."""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


def _rand():
    return datetime.now().strftime("%H%M%S%f")


def _today():
    return datetime.now(timezone.utc).date().isoformat()


# ═══════════════ Mobilization CRUD ═══════════════
class TestMobilization:
    def test_create_mobilization(self, admin):
        r = admin.post(f"{API}/logistics/mobilizations", json={
            "reporting_date": _today(),
            "travel_required": True,
            "workers": [{"name": "W1", "trade": "Fitter"}, {"name": "W2", "trade": "Helper"}],
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mob_no"].startswith(f"MOB-{datetime.now(timezone.utc).year}-")
        assert len(d["workers"]) == 2
        pytest.mob_id = d["id"]

    def test_update_status_to_approved(self, admin):
        r = admin.put(f"{API}/logistics/mobilizations/{pytest.mob_id}", json={
            "reporting_date": _today(),
            "travel_required": True,
            "workers": [{"name": "W1", "trade": "Fitter"}, {"name": "W2", "trade": "Helper"}],
            "status": "approved",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

    def test_delete_approved_returns_400(self, admin):
        r = admin.delete(f"{API}/logistics/mobilizations/{pytest.mob_id}", timeout=30)
        assert r.status_code == 400, r.text


# ═══════════════ Travel ═══════════════
class TestTravel:
    def test_travel_requires_approved_mob(self, admin):
        # Create draft mob
        r = admin.post(f"{API}/logistics/mobilizations", json={
            "reporting_date": _today(), "workers": [{"name": "X"}], "status": "draft"
        }, timeout=30)
        assert r.status_code == 200
        draft_mob = r.json()["id"]
        # Try travel against draft
        r = admin.post(f"{API}/logistics/travel", json={
            "mob_id": draft_mob, "employee_name": "E1", "travel_mode": "flight",
            "from_location": "BLR", "to_location": "DEL", "cost": 8000,
            "project_code": "P1", "status": "confirmed",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_travel_confirmed_requires_project_code(self, admin):
        r = admin.post(f"{API}/logistics/travel", json={
            "mob_id": pytest.mob_id, "employee_name": "E1",
            "travel_mode": "flight", "from_location": "BLR", "to_location": "DEL",
            "cost": 8000, "status": "confirmed"
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_travel_success(self, admin):
        r = admin.post(f"{API}/logistics/travel", json={
            "mob_id": pytest.mob_id, "employee_name": "E1",
            "travel_mode": "flight", "from_location": "BLR", "to_location": "DEL",
            "cost": 8000, "project_code": "P1", "status": "confirmed"
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["travel_no"].startswith("TRV-")
        pytest.travel_id = d["id"]


# ═══════════════ Accommodation ═══════════════
class TestAccommodation:
    def test_create_accommodation(self, admin):
        r = admin.post(f"{API}/logistics/accommodations", json={
            "employee_name": "E1", "acc_type": "hotel",
            "check_in": _today(), "check_out": _today(), "cost": 15000,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["acc_no"].startswith("ACC-")
        pytest.acc_id = d["id"]

    def test_close_without_checkout_400(self, admin):
        # Create fresh
        r = admin.post(f"{API}/logistics/accommodations", json={
            "employee_name": "E2", "acc_type": "hotel", "check_in": _today()
        }, timeout=30)
        aid = r.json()["id"]
        r = admin.put(f"{API}/logistics/accommodations/{aid}", json={
            "employee_name": "E2", "acc_type": "hotel",
            "check_in": _today(), "status": "closed"
        }, timeout=30)
        assert r.status_code == 400, r.text


# ═══════════════ Local Conveyance ═══════════════
def test_local_conveyance(admin):
    r = admin.post(f"{API}/logistics/local-conveyance", json={
        "employee_name": "E1", "amount": 500, "mode": "auto"
    }, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["conv_no"].startswith("CNV-")


# ═══════════════ Site Reporting ═══════════════
def test_site_reporting_updates_mob(admin):
    # Make sure mob is approved (already done) — set to approved (already approved)
    r = admin.post(f"{API}/logistics/site-reporting", json={
        "mob_id": pytest.mob_id, "employee_name": "E1",
        "safety_induction_done": True, "accommodation_confirmed": True,
    }, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sr_no"].startswith("SR-")
    # Verify mob status auto-updated to 'reported'
    lst = admin.get(f"{API}/logistics/mobilizations", timeout=30).json()
    match = [m for m in lst if m["id"] == pytest.mob_id]
    assert match and match[0]["status"] == "reported", f"Expected reported, got {match[0]['status'] if match else 'no mob'}"


# ═══════════════ Demobilization ═══════════════
class TestDemobilization:
    def test_create(self, admin):
        r = admin.post(f"{API}/logistics/demobilizations", json={
            "mob_id": pytest.mob_id, "employee_name": "E1",
            "return_travel_required": True
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["demob_no"].startswith("DMB-")
        pytest.demob_id = d["id"]

    def test_close_missing_return_travel(self, admin):
        r = admin.put(f"{API}/logistics/demobilizations/{pytest.demob_id}", json={
            "mob_id": pytest.mob_id, "employee_name": "E1",
            "return_travel_required": True, "store_clearance_done": True,
            "status": "closed", "travel_id": None,
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_close_missing_store_clearance(self, admin):
        r = admin.put(f"{API}/logistics/demobilizations/{pytest.demob_id}", json={
            "mob_id": pytest.mob_id, "employee_name": "E1",
            "return_travel_required": False, "store_clearance_done": False,
            "status": "closed",
        }, timeout=30)
        assert r.status_code == 400, r.text

    def test_close_success(self, admin):
        r = admin.put(f"{API}/logistics/demobilizations/{pytest.demob_id}", json={
            "mob_id": pytest.mob_id, "employee_name": "E1",
            "return_travel_required": False, "store_clearance_done": True,
            "status": "closed",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "closed"


# ═══════════════ Dashboard ═══════════════
def test_mob_dashboard_has_11_kpis(admin):
    r = admin.get(f"{API}/logistics/mobilization-dashboard", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "as_of" in d and "kpis" in d
    kpis = d["kpis"]
    assert len(kpis) == 11, f"Expected 11 KPIs, got {len(kpis)}: {list(kpis.keys())}"
    for k in ["total_mobilizations", "active_workers", "travel_planned",
              "accommodations_active", "site_reports_today", "demob_pending"]:
        assert k in kpis, f"Missing KPI: {k}"
