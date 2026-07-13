"""Iter 127 — Safety Foundation Phase 1.

Covers:
  * Safety masters CRUD + seed idempotency
  * HIRA lifecycle: create → submit (low-risk auto-approves, high-risk goes
    to pending_approval) → revise (preserves history) → approved is locked
  * JSA same lifecycle
  * Safety Plan uniqueness per project
  * Safety Document expiry_status is computed
  * Safety Dashboard returns 20 real cards
"""
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
    assert r.status_code == 200, r.text
    return s


class TestSafetyMasters:
    def test_list_all_returns_13_masters(self, sess):
        r = sess.get(f"{API}/safety/masters", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        slugs = {r["slug"] for r in rows}
        assert len(slugs) == 13

    def test_seed_populated_defaults(self, sess):
        wpt = sess.get(f"{API}/safety/masters/work-permit-types", timeout=30).json()
        stt = sess.get(f"{API}/safety/masters/safety-training-types", timeout=30).json()
        names_wpt = {x["name"] for x in wpt}
        names_stt = {x["name"] for x in stt}
        assert "Work at Height Permit" in names_wpt
        assert "Rope Access Work Permit" in names_wpt
        assert "Safety Induction" in names_stt
        assert "Rope Access Safety Training" in names_stt
        assert len(wpt) >= 11
        assert len(stt) >= 11

    def test_crud_master(self, sess):
        # create
        r = sess.post(f"{API}/safety/masters/hazard-categories",
                      json={"code": f"HZ-{int(time.time())}", "name": f"Test Hazard {int(time.time())}", "severity": "high"}, timeout=30)
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["active"] is True
        assert item["severity"] == "high"
        # update
        r = sess.put(f"{API}/safety/masters/hazard-categories/{item['id']}",
                     json={**item, "description": "updated"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["description"] == "updated"
        # delete (soft)
        r = sess.delete(f"{API}/safety/masters/hazard-categories/{item['id']}", timeout=30)
        assert r.status_code == 200
        assert r.json()["soft_deleted"] is True

    def test_seed_is_idempotent(self, sess):
        r = sess.post(f"{API}/safety/masters/-/seed", timeout=30)
        assert r.status_code == 200
        # Second run should insert zero
        r2 = sess.post(f"{API}/safety/masters/-/seed", timeout=30)
        assert all(v == 0 for v in r2.json().values()), f"Seed not idempotent: {r2.json()}"

    def test_unknown_master_404(self, sess):
        r = sess.get(f"{API}/safety/masters/not-a-real-master", timeout=30)
        assert r.status_code == 404


class TestHIRALifecycle:
    def test_create_submit_low_risk_auto_approves(self, sess):
        payload = {
            "project_code": "TEST-PRJ",
            "site_location": "Site A",
            "service_type": "painting",
            "lines": [{"activity": "prep", "hazard": "dust", "risk_rating": "low"}],
        }
        r = sess.post(f"{API}/safety/hira", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        hira = r.json()
        assert hira["status"] == "draft"
        assert hira["high_risk"] is False
        # Submit → auto-approved (no high-risk lines)
        r2 = sess.post(f"{API}/safety/hira/{hira['id']}/submit", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "approved"

    def test_create_submit_high_risk_pending(self, sess):
        payload = {
            "project_code": "TEST-PRJ-HIGH",
            "lines": [{"activity": "rope access", "hazard": "fall from height", "risk_rating": "critical"}],
        }
        hira = sess.post(f"{API}/safety/hira", json=payload, timeout=30).json()
        assert hira["high_risk"] is True
        r = sess.post(f"{API}/safety/hira/{hira['id']}/submit", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "pending_approval"
        assert body["approval_id"]  # created in approvals collection

    def test_approved_cannot_be_deleted(self, sess):
        payload = {"project_code": "TEST", "lines": [{"activity": "a", "hazard": "b", "risk_rating": "low"}]}
        hira = sess.post(f"{API}/safety/hira", json=payload, timeout=30).json()
        sess.post(f"{API}/safety/hira/{hira['id']}/submit", timeout=30)  # → approved
        r = sess.delete(f"{API}/safety/hira/{hira['id']}", timeout=30)
        assert r.status_code == 400

    def test_revise_preserves_history(self, sess):
        payload = {"project_code": "TEST-REV", "lines": [{"activity": "a", "hazard": "b", "risk_rating": "low"}]}
        hira = sess.post(f"{API}/safety/hira", json=payload, timeout=30).json()
        # Approve first (locks it)
        sess.post(f"{API}/safety/hira/{hira['id']}/submit", timeout=30)
        # Revise
        r = sess.post(f"{API}/safety/hira/{hira['id']}/revise", timeout=30)
        assert r.status_code == 200
        revised = r.json()
        assert revised["rev"] == 1
        assert len(revised["revisions"]) == 1
        assert revised["status"] == "draft"
        # audit log captured revised action
        audit = sess.get(f"{API}/safety/audit-log?record_id={hira['id']}", timeout=30).json()
        actions = {a["action"] for a in audit}
        assert {"created", "submitted", "revised"}.issubset(actions) or {"created", "approved", "revised"}.issubset(actions)

    def test_submit_without_lines_400(self, sess):
        hira = sess.post(f"{API}/safety/hira", json={"project_code": "TEST-EMPTY"}, timeout=30).json()
        r = sess.post(f"{API}/safety/hira/{hira['id']}/submit", timeout=30)
        assert r.status_code == 400


class TestJSALifecycle:
    def test_create_and_submit_high_risk(self, sess):
        jsa = sess.post(f"{API}/safety/jsa", json={
            "activity": "scaffold erection",
            "lines": [{"step_no": 1, "step": "climb", "risk": "high"}],
        }, timeout=30).json()
        assert jsa["high_risk"] is True
        r = sess.post(f"{API}/safety/jsa/{jsa['id']}/submit", timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "pending_approval"

    def test_activity_is_required(self, sess):
        r = sess.post(f"{API}/safety/jsa", json={"lines": []}, timeout=30)
        assert r.status_code == 422  # pydantic validation

    def test_submit_needs_lines(self, sess):
        jsa = sess.post(f"{API}/safety/jsa", json={"activity": "empty"}, timeout=30).json()
        r = sess.post(f"{API}/safety/jsa/{jsa['id']}/submit", timeout=30)
        assert r.status_code == 400


class TestSafetyPlanUniqueness:
    def test_one_plan_per_project(self, sess):
        pid = f"iter127-plan-{int(time.time())}"
        r = sess.post(f"{API}/safety/plans", json={"project_id": pid, "status": "draft"}, timeout=30)
        assert r.status_code == 200, r.text
        # Second attempt → 409
        r2 = sess.post(f"{API}/safety/plans", json={"project_id": pid, "status": "draft"}, timeout=30)
        assert r2.status_code == 409


class TestSafetyDocumentExpiry:
    def test_expiry_status_computed(self, sess):
        r = sess.post(f"{API}/safety/documents", json={
            "title": "PF Registration", "doc_type": "statutory",
            "expires_on": "2020-01-01",   # long past
        }, timeout=30)
        assert r.status_code == 200
        rows = sess.get(f"{API}/safety/documents", timeout=30).json()
        row = next(x for x in rows if x["id"] == r.json()["id"])
        assert row["expiry_status"] == "expired"


class TestSafetyDashboard:
    def test_returns_20_real_cards(self, sess):
        r = sess.get(f"{API}/safety/dashboard", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "as_of" in body
        cards = body["cards"]
        assert len(cards) == 20
        for c in cards:
            assert "key" in c and "label" in c and "value" in c
            assert isinstance(c["value"], int)
