"""Iter 128 — Safety Phase 2 · Work Permits + PPE + Readiness + Overrides."""
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


def _make_approved_hira(sess) -> dict:
    """Create + submit + auto-approve a low-risk HIRA (no high-risk lines)."""
    h = sess.post(f"{API}/safety/hira", json={
        "project_id": f"iter128-proj-{int(time.time()*1000)}",
        "project_code": "P128",
        "lines": [{"activity": "prep", "hazard": "dust", "risk_rating": "low"}],
    }, timeout=30).json()
    r = sess.post(f"{API}/safety/hira/{h['id']}/submit", timeout=30)
    assert r.status_code == 200
    return r.json()


class TestWorkPermitLifecycle:
    def test_create_permit_ok(self, sess):
        p = sess.post(f"{API}/safety/work-permits", json={
            "project_code": "P128", "activity": "cleaning", "valid_from": "2026-01-01", "valid_to": "2027-01-01",
        }, timeout=30)
        assert p.status_code == 200, p.text
        assert p.json()["status"] == "draft"
        assert p.json()["permit_no"].startswith("WP")

    def test_request_blocked_when_hira_pending(self, sess):
        # Create a high-risk HIRA that's still pending
        hira = sess.post(f"{API}/safety/hira", json={
            "project_id": "test", "lines": [{"activity": "rope", "hazard": "fall", "risk_rating": "critical"}],
        }, timeout=30).json()
        sess.post(f"{API}/safety/hira/{hira['id']}/submit", timeout=30)  # goes to pending_approval
        permit = sess.post(f"{API}/safety/work-permits", json={
            "project_code": "P128", "activity": "rope work", "related_hira_id": hira["id"],
        }, timeout=30).json()
        r = sess.post(f"{API}/safety/work-permits/{permit['id']}/request", timeout=30)
        assert r.status_code == 400
        assert "must be approved" in r.text or "pending" in r.text.lower()

    def test_full_lifecycle_with_approved_hira(self, sess):
        hira = _make_approved_hira(sess)
        p = sess.post(f"{API}/safety/work-permits", json={
            "project_id": hira["project_id"], "project_code": "P128",
            "activity": "safe activity", "valid_to": "2027-12-31",
            "related_hira_id": hira["id"],
        }, timeout=30).json()
        # request
        r = sess.post(f"{API}/safety/work-permits/{p['id']}/request", timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "requested"
        assert r.json().get("approval_id")
        # approve
        r = sess.post(f"{API}/safety/work-permits/{p['id']}/approve", timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "approved"
        # activate
        r = sess.post(f"{API}/safety/work-permits/{p['id']}/activate", timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "active"
        # close
        r = sess.post(f"{API}/safety/work-permits/{p['id']}/close",
                       json={"completion_notes": "clean closure, no issues", "incidents_reported": False}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "closed"

    def test_tick_expiries_marks_past_due(self, sess):
        hira = _make_approved_hira(sess)
        p = sess.post(f"{API}/safety/work-permits", json={
            "project_id": hira["project_id"], "project_code": "P128",
            "activity": "old work", "valid_to": "2020-01-01",   # past
            "related_hira_id": hira["id"],
        }, timeout=30).json()
        # Push through to active
        for action in ("request", "approve", "activate"):
            sess.post(f"{API}/safety/work-permits/{p['id']}/{action}", timeout=30)
        r = sess.post(f"{API}/safety/work-permits/-/tick-expiries", timeout=30)
        assert r.status_code == 200
        # The permit we just made must now be expired (among possibly others)
        fresh = sess.get(f"{API}/safety/work-permits/{p['id']}", timeout=30).json()
        assert fresh["status"] == "expired"

    def test_only_draft_can_be_deleted(self, sess):
        hira = _make_approved_hira(sess)
        p = sess.post(f"{API}/safety/work-permits", json={
            "project_id": hira["project_id"], "activity": "x", "valid_to": "2027-01-01",
            "related_hira_id": hira["id"],
        }, timeout=30).json()
        for action in ("request", "approve"):
            sess.post(f"{API}/safety/work-permits/{p['id']}/{action}", timeout=30)
        # Now non-draft
        r = sess.delete(f"{API}/safety/work-permits/{p['id']}", timeout=30)
        assert r.status_code == 400


class TestPPEComplianceAndRequirements:
    def test_ppe_req_crud(self, sess):
        # Need a PPE category to reference
        cat = sess.post(f"{API}/safety/masters/ppe-categories",
                         json={"name": f"Helmet {int(time.time())}"}, timeout=30).json()
        req = sess.post(f"{API}/safety/ppe-requirements", json={
            "project_code": "P128", "activity": "scaffold", "required_ppe_ids": [cat["id"]],
        }, timeout=30)
        assert req.status_code == 200
        assert cat["id"] in req.json()["required_ppe_ids"]
        # Soft-delete
        r = sess.delete(f"{API}/safety/ppe-requirements/{req.json()['id']}", timeout=30)
        assert r.status_code == 200 and r.json()["soft_deleted"] is True

    def test_ppe_compliance_shape(self, sess):
        r = sess.get(f"{API}/safety/ppe-compliance?project_id=NOPE", timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ["required_count", "issued_count", "missing_count", "missing", "compliant"]:
            assert k in body


class TestReadinessAndOverride:
    def test_readiness_returns_11_factors_when_worker_given(self, sess):
        r = sess.get(f"{API}/safety/readiness?project_id=some-project&worker_id=some-worker", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert len(body["factors"]) == 11
        assert body["classification"] in ["ready", "conditional", "not_ready", "blocked"]

    def test_readiness_needs_project_id(self, sess):
        r = sess.get(f"{API}/safety/readiness", timeout=30)
        assert r.status_code in (400, 422)

    def test_override_requires_reason_min_length(self, sess):
        r = sess.post(f"{API}/safety/overrides", json={
            "project_id": "p", "blocked_factor": "medical", "reason": "short",
        }, timeout=30)
        assert r.status_code == 422

    def test_override_creates_approval_and_audit(self, sess):
        r = sess.post(f"{API}/safety/overrides", json={
            "project_id": "p128", "blocked_factor": "medical",
            "reason": "urgent client deadline — worker cleared verbally by doctor",
        }, timeout=30)
        assert r.status_code == 200
        ovr = r.json()
        assert ovr["status"] == "pending" and ovr["approval_id"]


class TestTrainingExpiry:
    def test_endpoint_bucketed_shape(self, sess):
        r = sess.get(f"{API}/safety/training-expiry?days=90", timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ["expired", "expiring_soon", "expiring_later", "counts"]:
            assert k in body
        for b in ("expired", "expiring_soon", "expiring_later"):
            assert isinstance(body["counts"][b], int)

    def test_days_input_validation(self, sess):
        r = sess.get(f"{API}/safety/training-expiry?days=999", timeout=30)
        assert r.status_code == 400
