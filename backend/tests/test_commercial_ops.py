"""Modules E + F + G — PO commercials, Project ops, Service-rate master."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TS = str(int(time.time()))


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, r.text
    return s


def _seed_order(admin):
    """Seed an order row directly via Mongo (skips the full enquiry→won→convert flow)."""
    import os as _os
    from pymongo import MongoClient
    from dotenv import load_dotenv as _ld
    _ld('/app/backend/.env')
    c = MongoClient(_os.environ['MONGO_URL'])
    dbc = c[_os.environ['DB_NAME']]
    doc = {
        "id": f"ord-test-{TS}-" + str(time.time_ns()),
        "order_no": f"ORD-TEST-{TS}-{time.time_ns()}",
        "customer": f"TEST-{TS}",
        "service_type": "services",
        "contract_value": 500000,
        "status": "active",
        "created_at": "2026-04-01T00:00:00+00:00",
    }
    dbc.orders.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# E. PO commercials
# ──────────────────────────────────────────────────────────────────────────────
class TestPOCommercials:
    def _make_order(self, admin):
        return _seed_order(admin)

    def test_patch_and_utilization(self, admin):
        order = self._make_order(admin)
        # Patch commercials
        r = admin.patch(f"{API}/orders/{order['id']}/commercials", json={
            "retention_pct": 5, "security_deposit_amount": 25000,
            "penalty_clause": "0.5% per week delay capped at 5%",
            "validity_date": "2027-03-31", "start_date": "2026-04-01", "end_date": "2027-03-31",
            "billing_terms": "monthly running bills", "payment_terms": "Net 30",
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["retention_pct"] == 5
        assert body["validity_date"] == "2027-03-31"
        # Utilization (no RA bills yet → all zeros)
        u = admin.get(f"{API}/orders/{order['id']}/utilization", timeout=30).json()
        assert u["contract_value"] == 500000
        assert u["billed_gross"] == 0
        assert u["balance_po_value"] == 500000
        assert u["days_to_expiry"] is not None and u["days_to_expiry"] > 0

    def test_patch_empty_body_400(self, admin):
        order = self._make_order(admin)
        r = admin.patch(f"{API}/orders/{order['id']}/commercials", json={}, timeout=30)
        assert r.status_code == 400

    def test_expiring_soon(self, admin):
        order = self._make_order(admin)
        # Set validity to 10 days from today
        import datetime as dt
        soon = (dt.date.today() + dt.timedelta(days=10)).isoformat()
        admin.patch(f"{API}/orders/{order['id']}/commercials", json={"validity_date": soon}, timeout=30)
        r = admin.get(f"{API}/orders/expiring-soon?days=30", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        ids = [o["id"] for o in body["rows"]]
        assert order["id"] in ids


# ──────────────────────────────────────────────────────────────────────────────
# F. Project Ops
# ──────────────────────────────────────────────────────────────────────────────
class TestProjectOps:
    @pytest.fixture(scope="class")
    def project_code(self, admin):
        # Re-use an existing project, or create a quick one
        ps = admin.get(f"{API}/projects", timeout=30).json()
        if ps:
            return ps[0]["code"]
        p = admin.post(f"{API}/projects", json={"name": f"P-OPS-{TS}", "client": "Acme", "budget": 100000}, timeout=30).json()
        return p["code"]

    def test_delay_extra_lifecycle(self, admin, project_code):
        d = admin.post(f"{API}/projects/{project_code}/ops/delay-events", json={
            "hours": 4, "category": "weather", "reason": "Heavy rain blocked tank-top work",
        }, timeout=30).json()
        assert d["id"] and d["hours"] == 4
        e = admin.post(f"{API}/projects/{project_code}/ops/extra-works", json={
            "description": "Repaint after client request", "estimated_value": 12000, "client_approved": True,
        }, timeout=30).json()
        assert e["id"] and e["estimated_value"] == 12000

        snap = admin.get(f"{API}/projects/{project_code}/ops/snapshot", timeout=30).json()
        assert snap["delay_hours"] >= 4
        assert snap["extras_value"] >= 12000
        assert any(de["id"] == d["id"] for de in snap["delay_events"])
        assert any(ew["id"] == e["id"] for ew in snap["extra_works"])

        # Delete events
        del_r = admin.delete(f"{API}/projects/{project_code}/ops/delay-events/{d['id']}", timeout=30)
        assert del_r.status_code == 200

    def test_snapshot_404_for_unknown_project(self, admin):
        r = admin.get(f"{API}/projects/NO_SUCH_PROJ_{TS}/ops/snapshot", timeout=30)
        assert r.status_code == 404

    def test_profitability_returns_zeros_or_calculated(self, admin, project_code):
        r = admin.get(f"{API}/projects/{project_code}/ops/profitability", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "revenue" in body and "cost" in body and "gross_margin" in body
        assert body["revenue"]["gross"] >= 0


# ──────────────────────────────────────────────────────────────────────────────
# G. Service-rate master
# ──────────────────────────────────────────────────────────────────────────────
class TestServiceRates:
    def test_create_and_lookup(self, admin):
        r = admin.post(f"{API}/service-rates", json={
            "service": "scaffolding", "activity": f"erected-test-{TS}", "unit": "m²",
            "standard_rate": 120, "effective_from": "2026-01-01",
        }, timeout=30)
        assert r.status_code == 200, r.text
        rate = r.json()
        pytest.rate_id = rate["id"]

        # Lookup the active rate
        l = admin.get(f"{API}/service-rates/lookup",
                      params={"service": "scaffolding", "activity": f"erected-test-{TS}", "unit": "m²"},
                      timeout=30)
        assert l.status_code == 200, l.text
        assert l.json()["standard_rate"] == 120

    def test_lookup_404_for_missing(self, admin):
        l = admin.get(f"{API}/service-rates/lookup",
                      params={"service": "scaffolding", "activity": "definitely-not-a-real-act"},
                      timeout=30)
        assert l.status_code == 404

    def test_list_active_only(self, admin):
        # Add an expired one
        admin.post(f"{API}/service-rates", json={
            "service": "painting", "activity": f"expired-test-{TS}", "unit": "m²",
            "standard_rate": 50, "effective_from": "2020-01-01", "effective_until": "2020-12-31",
        }, timeout=30)
        r = admin.get(f"{API}/service-rates?active_only=true", timeout=30)
        assert r.status_code == 200
        active_acts = [x["activity"] for x in r.json()]
        assert f"expired-test-{TS}" not in active_acts
        assert f"erected-test-{TS}" in active_acts

    def test_update_and_delete(self, admin):
        u = admin.put(f"{API}/service-rates/{pytest.rate_id}", json={"standard_rate": 135}, timeout=30)
        assert u.status_code == 200 and u.json()["standard_rate"] == 135
        d = admin.delete(f"{API}/service-rates/{pytest.rate_id}", timeout=30)
        assert d.status_code == 200
