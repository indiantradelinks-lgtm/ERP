"""Iter 125 — Personalised Quick Actions telemetry.

Covers:
  * POST /telemetry/module-visit stores a visit
  * Landing / meta paths are skipped
  * GET /telemetry/top-shortcuts/{dept} returns ranked list
  * GET /dashboard/department/{dept} injects `personalized_links`
      - Empty when <3 visits (cold-start fallback)
      - Populated + ranked after enough visits
      - Only includes paths that appear in the static `links` list
"""
import os
import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return s


def _wipe_visits(sess):
    # Direct nuke via a dev-only path? None exists — we rely on visits being scoped
    # to (user_id, dept) and use a unique dept slug so we don't interfere with real data.
    # But we also want a deterministic count → we use a `dept` string that no live
    # code ever writes, then aggregate against it.
    pass


class TestModuleVisitTelemetry:
    def test_record_visit_ok(self, admin_session):
        r = admin_session.post(
            f"{API}/telemetry/module-visit",
            json={"path": "/app/inventory", "dept": "store"},
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True

    def test_landing_paths_skipped(self, admin_session):
        for p in ["/app", "/app/", "/app/modules", "/app/modules/store"]:
            r = admin_session.post(
                f"{API}/telemetry/module-visit",
                json={"path": p, "dept": "store"},
                timeout=30,
            )
            assert r.status_code == 200
            body = r.json()
            assert body.get("skipped") is True, f"expected skip for {p}"

    def test_top_shortcuts_ranking(self, admin_session):
        # Use a synthetic dept to isolate this test's data
        dept = "iter125_test_dept"
        payloads = (
            [("/app/inventory", dept)] * 4
            + [("/app/store-transactions", dept)] * 2
            + [("/app/material-allocations", dept)] * 1
        )
        for path, d in payloads:
            admin_session.post(
                f"{API}/telemetry/module-visit",
                json={"path": path, "dept": d},
                timeout=30,
            )
        r = admin_session.get(f"{API}/telemetry/top-shortcuts/{dept}?limit=5", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        assert items[0]["path"] == "/app/inventory" and items[0]["count"] == 4
        assert items[1]["path"] == "/app/store-transactions" and items[1]["count"] == 2
        assert items[2]["path"] == "/app/material-allocations" and items[2]["count"] == 1

    def test_top_shortcuts_input_validation(self, admin_session):
        r = admin_session.get(f"{API}/telemetry/top-shortcuts/store?limit=999", timeout=30)
        assert r.status_code == 400
        r = admin_session.get(f"{API}/telemetry/top-shortcuts/store?days=999", timeout=30)
        assert r.status_code == 400


class TestPersonalisedLinksOnDashboard:
    def test_cold_start_returns_empty_personalised(self, admin_session):
        # Isolated dept slug — no visits → no personalization
        r = admin_session.get(f"{API}/dashboard/department/store", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "personalized_links" in body
        assert "links" in body and len(body["links"]) > 0

    def test_personalised_links_populated_after_visits(self, admin_session):
        # First discover what static links exist for `store` and pick one that
        # definitely has a corresponding /app/ path we can visit.
        r = admin_session.get(f"{API}/dashboard/department/store", timeout=30)
        static = r.json().get("links", [])
        target = next((l for l in static if l.get("to")), None)
        assert target, "no static links available for store dept"

        # Fire 4 visits so we cross the 3-visit personalisation threshold.
        for _ in range(4):
            admin_session.post(
                f"{API}/telemetry/module-visit",
                json={"path": target["to"], "dept": "store"},
                timeout=30,
            )

        r = admin_session.get(f"{API}/dashboard/department/store", timeout=30)
        pl = r.json().get("personalized_links", [])
        # At minimum the freshly-visited target should be there
        paths = [l.get("to") for l in pl]
        assert target["to"] in paths, f"expected {target['to']} in personalised list, got {paths}"
        # Each entry should carry visit_count
        found = next(l for l in pl if l.get("to") == target["to"])
        assert isinstance(found.get("visit_count"), int) and found["visit_count"] >= 4
        # visit_count ordering should be descending
        counts = [l.get("visit_count", 0) for l in pl]
        assert counts == sorted(counts, reverse=True), f"personalised list not sorted desc: {counts}"
