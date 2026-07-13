"""Iter 130 — Safety Phase 4 · Audits · Client Compliance · Reviews · Vendor · Costs · Mgmt Review."""
import os
import time
import pytest
import requests

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip() + "/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SAFETY = {"email": "safety@erp.com", "password": "Safety@123"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sess():
    return _login(ADMIN)


# ─── 1. Safety Audits ─────────────────────────────────────
class TestSafetyAudits:
    def test_list_audits(self, sess):
        r = sess.get(f"{API}/safety/audits", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_high_finding_auto_capa_and_close(self, sess):
        r = sess.post(f"{API}/safety/audits", json={
            "audit_date": "2026-02-05",
            "audit_type": "internal",
            "project_code": "TEST",
            "auditor": "QA Bot",
            "findings": [
                {"finding": "Missing scaffold tag on level 2", "risk_level": "high",
                 "corrective_action": "Install tags", "responsible_person": "Site Sup",
                 "target_date": "2026-02-20"},
            ],
        }, timeout=30)
        assert r.status_code == 200, r.text
        audit = r.json()
        assert audit["audit_no"].startswith("AUD")
        assert audit["status"] == "open"
        assert audit["findings"][0].get("capa_id")

        # Verify CAPA created with source_type='audit', auto_created=True
        capas = sess.get(f"{API}/safety/capa", timeout=30).json()
        matches = [c for c in capas if c.get("source_id") == audit["id"]
                   and c.get("source_type") == "audit"
                   and c.get("auto_created") is True]
        assert matches, "Expected auto CAPA linked to audit"

        # Close audit
        r = sess.post(f"{API}/safety/audits/{audit['id']}/close", timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "closed"


# ─── 2. Client Compliance ─────────────────────────────────
class TestClientCompliance:
    def test_create_mandatory_and_blocking(self, sess):
        pid = f"TESTPROJ-{int(time.time())}"
        r = sess.post(f"{API}/safety/client-compliance", json={
            "client_name": "TEST Client",
            "project_id": pid,
            "project_code": "TESTX",
            "requirement": "Safety plan submission",
            "requirement_type": "safety_document",
            "mandatory": True,
        }, timeout=30)
        assert r.status_code == 200, r.text
        row = r.json()
        rid = row["id"]

        listed = sess.get(f"{API}/safety/client-compliance", timeout=30).json()
        me = next((x for x in listed if x["id"] == rid), None)
        assert me and me["status"] in ("pending", "overdue")

        # Update via PUT
        r = sess.put(f"{API}/safety/client-compliance/{rid}", json={
            "client_name": "TEST Client",
            "project_id": pid,
            "project_code": "TESTX",
            "requirement": "Safety plan submission v2",
            "requirement_type": "safety_document",
            "mandatory": True,
        }, timeout=30)
        assert r.status_code == 200
        assert r.json()["requirement"] == "Safety plan submission v2"

        # Blocking API
        r = sess.get(f"{API}/safety/client-compliance/blocking/{pid}", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert b["blocks_closure"] is True
        assert len(b["pending_mandatory"]) >= 1


# ─── 3. Monthly Safety Review ─────────────────────────────
class TestMonthlyReview:
    def test_create_review_auto_capa(self, sess):
        r = sess.post(f"{API}/safety/reviews", json={
            "month": "2026-02",
            "meeting_date": "2026-02-10",
            "project_code": "TEST",
            "action_items": [
                {"description": "Improve toolbox talk attendance"},
                {"description": "Refresh PPE stock at store"},
            ],
        }, timeout=30)
        assert r.status_code == 200, r.text
        rev = r.json()
        assert rev["review_no"].startswith("REV-2026-") or rev["review_no"].startswith("REV")
        assert len(rev["action_items"]) == 2
        for ai in rev["action_items"]:
            assert ai.get("capa_id")
        # Verify CAPAs
        capas = sess.get(f"{API}/safety/capa", timeout=30).json()
        review_capas = [c for c in capas if c.get("source_type") == "review"
                        and c.get("source_no") == rev["review_no"]]
        assert len(review_capas) == 2


# ─── 4. Vendor Safety Compliance ──────────────────────────
class TestVendorCompliance:
    def test_not_approved_when_docs_missing(self, sess):
        r = sess.post(f"{API}/safety/vendor-compliance", json={
            "vendor_id": f"TEST-V-{int(time.time())}",
            "vendor_name": "TEST Vendor A",
            "mandatory_docs_present": False,
        }, timeout=30)
        assert r.status_code == 200
        assert r.json()["safety_approval_state"] == "not_approved"

    def test_approved_when_docs_ok(self, sess):
        r = sess.post(f"{API}/safety/vendor-compliance", json={
            "vendor_id": f"TEST-V-{int(time.time())}-2",
            "vendor_name": "TEST Vendor B",
            "mandatory_docs_present": True,
            "safety_doc_valid_till": "2099-12-31",
            "labour_licence_valid_till": "2099-12-31",
            "insurance_valid_till": "2099-12-31",
            "training_ok": True, "ppe_ok": True, "work_permit_ok": True,
        }, timeout=30)
        assert r.status_code == 200
        assert r.json()["safety_approval_state"] == "approved"

        # List should also report approved
        rows = sess.get(f"{API}/safety/vendor-compliance", timeout=30).json()
        me = next((x for x in rows if x["vendor_name"] == "TEST Vendor B"), None)
        assert me and me["safety_approval_state"] == "approved"


# ─── 5. Safety Costs (with approval routing) ──────────────
class TestSafetyCosts:
    def test_below_threshold_no_approval(self, sess):
        r = sess.post(f"{API}/safety/costs", json={
            "cost_source": "ppe_purchase",
            "amount": 1000,
            "cost_date": "2026-02-05",
            "description": "TEST small ppe cost",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["approval_id"] is None

    def test_above_threshold_auto_approval(self, sess):
        r = sess.post(f"{API}/safety/costs", json={
            "cost_source": "ppe_purchase",
            "amount": 100000,
            "cost_date": "2026-02-05",
            "description": "TEST bulk ppe purchase",
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("approval_id"), "Expected approval routed for >=50000"

    def test_penalty_and_filter(self, sess):
        r = sess.post(f"{API}/safety/costs", json={
            "cost_source": "penalty",
            "amount": 500,
            "cost_date": "2026-02-05",
        }, timeout=30)
        assert r.status_code == 200
        rows = sess.get(f"{API}/safety/costs?cost_source=penalty", timeout=30).json()
        assert all(r.get("cost_source") == "penalty" for r in rows)
        assert len(rows) >= 1


# ─── 6. Management Review Dashboard ───────────────────────
class TestManagementReview:
    def test_kpis_present(self, sess):
        r = sess.get(f"{API}/safety/management-review", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "kpis" in data
        required = {"total_safety_cost", "penalty_cost", "recovery_amount",
                    "open_capas", "overdue_capas", "open_critical_incidents",
                    "open_audits", "pending_mandatory_client_compliance",
                    "vendors_not_safety_approved", "reviews_held_this_year"}
        assert required.issubset(set(data["kpis"].keys())), f"Missing keys: {required - set(data['kpis'].keys())}"


# ─── 7. RBAC negative — site_engineer cannot write audits, safety_officer can ──
class TestRbac:
    def test_site_engineer_forbidden(self):
        try:
            s = _login(SITE_ENG)
        except AssertionError:
            pytest.skip("site_engineer test account unavailable")
        r = s.post(f"{API}/safety/audits", json={
            "audit_date": "2026-02-05", "audit_type": "internal",
            "findings": [],
        }, timeout=30)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_safety_officer_can_write(self):
        try:
            s = _login(SAFETY)
        except AssertionError:
            pytest.skip("safety_officer test account unavailable")
        r = s.post(f"{API}/safety/audits", json={
            "audit_date": "2026-02-05", "audit_type": "internal",
            "auditor": "Safety Officer",
            "findings": [],
        }, timeout=30)
        assert r.status_code == 200, r.text
