"""Iteration 15 — Phase 4 allocation tests.

Covers:
- GET /api/allocation/shortages   (total_shortfall + rows shape)
- GET /api/allocation/calendar    (current month + ?year/&month)
- GET /api/scheduler/status       (shortage_scan present @ 07:30 UTC)
- POST /api/attendance with geo_lat/geo_lng/geo_accuracy persisted
- Regression: Phase 3 endpoints still respond 200
"""
import os
from datetime import date

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PWD = "Admin@123"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Phase 4: shortages ----------
class TestShortages:
    def test_shortages_shape(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/allocation/shortages", timeout=20)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "total_shortfall" in data and isinstance(data["total_shortfall"], int)
        assert "rows" in data and isinstance(data["rows"], list)
        for row in data["rows"]:
            for k in ["req_no", "position", "department", "project", "vacancies", "deployed", "shortfall"]:
                assert k in row, f"missing {k} in shortage row"
            assert row["shortfall"] > 0
            assert row["vacancies"] - row["deployed"] == row["shortfall"]


# ---------- Phase 4: calendar ----------
class TestCalendar:
    def test_calendar_current(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/allocation/calendar", timeout=20)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        today = date.today()
        assert data["year"] == today.year
        assert data["month"] == today.month
        assert isinstance(data["days"], int) and 28 <= data["days"] <= 31
        assert isinstance(data["projects"], list)
        for p in data["projects"]:
            assert "project" in p and isinstance(p["deployments"], list)
            for d in p["deployments"]:
                for k in ["id", "employee", "site_role", "shift", "status", "start_offset", "end_offset"]:
                    assert k in d, f"missing {k} in calendar deployment"
                assert 1 <= d["start_offset"] <= data["days"]
                assert 1 <= d["end_offset"] <= data["days"]

    def test_calendar_future_month(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/allocation/calendar?year=2026&month=6", timeout=20)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data["year"] == 2026
        assert data["month"] == 6
        assert data["days"] == 30
        assert isinstance(data["projects"], list)


# ---------- Phase 4: scheduler ----------
class TestScheduler:
    def test_scheduler_includes_shortage_scan(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/scheduler/status", timeout=20)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data.get("running") is True
        ids = [j["id"] for j in data.get("jobs", [])]
        assert "shortage_scan" in ids, f"shortage_scan missing from jobs: {ids}"
        shortage = next(j for j in data["jobs"] if j["id"] == "shortage_scan")
        # next_run_time should land at 07:30 UTC
        nrt = shortage.get("next_run_time", "")
        assert "07:30" in nrt or "T07:30" in nrt, f"unexpected next_run_time: {nrt}"


# ---------- Phase 4: geo-tagged attendance ----------
class TestGeoAttendance:
    def test_create_attendance_with_geo_persists(self, admin_session):
        today = date.today().isoformat()
        payload = {
            "employee_name": "TEST_GEO_EMP",
            "date": today,
            "check_in": "08:00",
            "status": "present",
            "geo_lat": 19.0760,
            "geo_lng": 72.8777,
            "geo_accuracy": 18,
        }
        r = admin_session.post(f"{BASE_URL}/api/attendance", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text[:200]
        created = r.json()
        assert created.get("geo_lat") == pytest.approx(19.0760, rel=1e-3)
        assert created.get("geo_lng") == pytest.approx(72.8777, rel=1e-3)
        assert created.get("geo_accuracy") == 18
        rec_id = created.get("id")
        assert rec_id

        # GET to verify persistence
        rg = admin_session.get(f"{BASE_URL}/api/attendance", timeout=20)
        assert rg.status_code == 200
        rows = rg.json()
        match = [x for x in rows if x.get("id") == rec_id]
        assert match, "created attendance row not present in listing"
        row = match[0]
        assert row.get("geo_lat") == pytest.approx(19.0760, rel=1e-3)
        assert row.get("geo_lng") == pytest.approx(72.8777, rel=1e-3)
        assert row.get("geo_accuracy") == 18

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/attendance/{rec_id}", timeout=20)


# ---------- Regression: Phase 3 endpoints still work ----------
class TestPhase3Regression:
    @pytest.mark.parametrize("path", [
        "/api/me/scope",
        "/api/allocation/by-department",
        "/api/allocation/by-project",
        "/api/allocation/idle-employees",
        "/api/allocation/resource-utilization",
        "/api/allocation/site-attendance",
        "/api/allocation/transfer-history",
        "/api/allocation/history",
    ])
    def test_endpoint_ok(self, admin_session, path):
        r = admin_session.get(f"{BASE_URL}{path}", timeout=20)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
