"""Iter 129 — Safety Phase 3 · Inspections + Observations + Incidents + CAPA + Escalations."""
import os
import time
import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200
    return s


class TestInspections:
    def test_create_close_lifecycle(self, sess):
        r = sess.post(f"{API}/safety/inspections", json={
            "inspection_date": "2026-02-01", "inspection_type": "daily_site",
            "project_code": "TEST", "inspector": "QA",
            "lines": [{"checklist_item": "PPE worn", "compliant": True, "risk_level": "low"}],
        }, timeout=30)
        assert r.status_code == 200, r.text
        insp = r.json()
        assert insp["inspection_no"].startswith("INSP")
        assert insp["status"] == "draft"
        # Close
        r = sess.post(f"{API}/safety/inspections/{insp['id']}/close", timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "closed"
        # Cannot edit closed
        r = sess.put(f"{API}/safety/inspections/{insp['id']}", json={
            "inspection_date": "2026-02-02", "inspection_type": "daily_site", "lines": [],
        }, timeout=30)
        assert r.status_code == 400


class TestObservationAutoCapa:
    def test_high_risk_observation_auto_creates_capa(self, sess):
        r = sess.post(f"{API}/safety/observations-v2", json={
            "observation_date": "2026-02-01",
            "project_code": "TEST",
            "kind": "unsafe_condition",
            "description": "Unguarded scaffold edge on level 3",
            "risk_level": "high",
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["capa_id"]         # auto-CAPA linked
        # Verify escalation was created
        escs = sess.get(f"{API}/safety/escalations?status=open", timeout=30).json()
        assert any(e.get("ref_id") == body["id"] and e["kind"] == "high_risk_observation" for e in escs)

    def test_low_risk_no_auto_capa(self, sess):
        r = sess.post(f"{API}/safety/observations-v2", json={
            "observation_date": "2026-02-01", "kind": "ofi",
            "description": "Consider adding a signboard near stairs",
            "risk_level": "low",
        }, timeout=30)
        assert r.status_code == 200
        assert not r.json().get("capa_id")


class TestIncidentsFlow:
    def test_critical_incident_creates_escalation(self, sess):
        r = sess.post(f"{API}/safety/incidents", json={
            "incident_datetime": "2026-02-01T14:00:00",
            "project_code": "TEST",
            "incident_type": "lost_time_injury",
            "description": "Worker slipped on wet floor, hospitalised for observation",
            "medical_cost": 10000,
        }, timeout=30)
        assert r.status_code == 200, r.text
        inc = r.json()
        assert inc["is_critical"] is True
        assert inc["escalation_id"]
        # Escalation row should exist with kind=critical_incident, level=critical
        escs = sess.get(f"{API}/safety/escalations?status=open", timeout=30).json()
        assert any(e.get("ref_id") == inc["id"] and e["kind"] == "critical_incident" and e["level"] == "critical" for e in escs)

    def test_high_cost_incident_creates_finance_approval(self, sess):
        r = sess.post(f"{API}/safety/incidents", json={
            "incident_datetime": "2026-02-01T15:00:00",
            "incident_type": "property_damage",
            "description": "Scaffold collapse, no personal injuries but heavy equipment damaged",
            "medical_cost": 20000, "penalty_cost": 60000,   # total 80k >= 50k threshold
        }, timeout=30)
        assert r.status_code == 200
        assert r.json()["cost_approval_id"]

    def test_investigation_needs_root_cause(self, sess):
        inc = sess.post(f"{API}/safety/incidents", json={
            "incident_datetime": "2026-02-01T16:00:00",
            "incident_type": "near_miss",
            "description": "Object fell but nobody was injured",
        }, timeout=30).json()
        # Close investigation without root_cause → 400
        r = sess.post(f"{API}/safety/incidents/{inc['id']}/close-investigation", timeout=30)
        assert r.status_code == 400
        # Add root cause and retry
        sess.put(f"{API}/safety/incidents/{inc['id']}", json={
            "incident_datetime": inc["incident_datetime"], "incident_type": "near_miss",
            "description": inc["description"], "root_cause": "Loose tool left overhead",
            "corrective_action": "Enforce housekeeping",
        }, timeout=30)
        r = sess.post(f"{API}/safety/incidents/{inc['id']}/close-investigation", timeout=30)
        assert r.status_code == 200
        assert r.json()["capa_id"]  # auto-CAPA

    def test_incident_description_min_length(self, sess):
        r = sess.post(f"{API}/safety/incidents", json={
            "incident_datetime": "2026-02-01T17:00:00", "incident_type": "near_miss",
            "description": "short",
        }, timeout=30)
        assert r.status_code == 422


class TestCapaClosure:
    def test_close_without_evidence_fails(self, sess):
        c = sess.post(f"{API}/safety/capa", json={
            "source_type": "audit", "corrective_action": "Fix housekeeping SOP",
        }, timeout=30).json()
        r = sess.post(f"{API}/safety/capa/{c['id']}/close", json={
            "evidence_ids": [], "override_reason": ""
        }, timeout=30)
        assert r.status_code == 400

    def test_close_with_override_reason_ok(self, sess):
        c = sess.post(f"{API}/safety/capa", json={
            "source_type": "audit", "corrective_action": "another fix",
        }, timeout=30).json()
        r = sess.post(f"{API}/safety/capa/{c['id']}/close", json={
            "evidence_ids": [], "override_reason": "Verbal client sign-off recorded in meeting notes"
        }, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "closed"

    def test_close_with_evidence_ok(self, sess):
        c = sess.post(f"{API}/safety/capa", json={
            "source_type": "audit", "corrective_action": "yet another fix",
        }, timeout=30).json()
        r = sess.post(f"{API}/safety/capa/{c['id']}/close", json={
            "evidence_ids": ["file123", "file456"], "override_reason": "",
        }, timeout=30)
        assert r.status_code == 200
        assert r.json()["verified_by_safety"] is True

    def test_tick_overdue_flags_and_escalates(self, sess):
        c = sess.post(f"{API}/safety/capa", json={
            "source_type": "audit", "corrective_action": "past-due CAPA",
            "target_date": "2020-01-01",
        }, timeout=30).json()
        r = sess.post(f"{API}/safety/capa/-/tick-overdue", timeout=30)
        assert r.status_code == 200
        fresh = sess.get(f"{API}/safety/capa", timeout=30).json()
        row = next(x for x in fresh if x["id"] == c["id"])
        assert row["status"] == "overdue"
        # Escalation exists
        escs = sess.get(f"{API}/safety/escalations?status=open", timeout=30).json()
        assert any(e.get("ref_id") == c["id"] and e["kind"] == "overdue_capa" for e in escs)


class TestEscalationDashboard:
    def test_list_and_close(self, sess):
        r = sess.get(f"{API}/safety/escalations?status=open", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        if rows:
            eid = rows[0]["id"]
            r2 = sess.post(f"{API}/safety/escalations/{eid}/close", timeout=30)
            assert r2.status_code == 200 and r2.json()["status"] == "closed"
