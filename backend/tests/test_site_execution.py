"""Site Execution module — DPR + Measurement / Work Certification.

Tests cover:
  * DPR lifecycle (create draft → submit → approve → reject path)
  * DPR edit guards (only draft/rejected)
  * Measurement validation (certified_qty ≤ executed_qty)
  * Measurement lifecycle (draft → submitted → client_certified → approved_for_billing)
  * Reject path
  * Summary aggregation by service
  * Dashboard counters
  * RBAC: site_engineer can create+submit DPR; project_manager can approve
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TS = str(int(time.time()))


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"{email} login failed: {r.text}"
    return s


@pytest.fixture(scope="session")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="session")
def pm():
    return _login("test_pm@erp.com", "PM@12345")


@pytest.fixture(scope="session")
def site_eng():
    return _login("test_site_engineer@erp.com", "TestPass@123")


# ──────────────────────────────────────────────────────────────────────────────
# DPR tests
# ──────────────────────────────────────────────────────────────────────────────
class TestDPR:

    def test_create_draft(self, site_eng):
        payload = {
            "date": "2026-03-01", "project_code": f"PRJ-TEST-{TS}",
            "site_name": "Plant Block A", "service_type": "scaffolding",
            "manpower": [{"role": "scaffolder", "count": 4}, {"role": "supervisor", "count": 1}],
            "work_completed": "Erected level 3 along south face",
            "material_used": [{"item_name": "Cuplock 2m", "quantity": 20, "unit": "Nos"}],
            "supervisor_remarks": "Wind picked up after lunch",
        }
        r = site_eng.post(f"{API}/dprs", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        row = r.json()
        assert row["status"] == "draft"
        assert row["dpr_number"].startswith("DPR-")
        pytest.dpr_id = row["id"]

    def test_update_draft(self, site_eng):
        r = site_eng.put(f"{API}/dprs/{pytest.dpr_id}", json={"client_instructions": "raise barricade height"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["client_instructions"] == "raise barricade height"

    def test_submit(self, site_eng):
        r = site_eng.post(f"{API}/dprs/{pytest.dpr_id}/submit", timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

    def test_edit_blocked_after_submit(self, site_eng):
        r = site_eng.put(f"{API}/dprs/{pytest.dpr_id}", json={"safety_observations": "x"}, timeout=30)
        assert r.status_code == 400

    def test_site_eng_cannot_approve(self, site_eng):
        r = site_eng.post(f"{API}/dprs/{pytest.dpr_id}/approve", json={}, timeout=30)
        assert r.status_code == 403

    def test_pm_approves(self, pm):
        r = pm.post(f"{API}/dprs/{pytest.dpr_id}/approve", json={"comment": "OK"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body.get("approved_at") is not None
        assert body["approval_comment"] == "OK"

    def test_cannot_approve_twice(self, pm):
        r = pm.post(f"{API}/dprs/{pytest.dpr_id}/approve", json={}, timeout=30)
        assert r.status_code == 400

    def test_dashboard_kpis(self, admin):
        r = admin.get(f"{API}/dprs/dashboard", timeout=30)
        assert r.status_code == 200
        kpis = r.json()["kpis"]
        assert "total" in kpis and "submitted_today" in kpis
        assert kpis["total"] >= 1

    def test_delete_approved_blocked(self, admin):
        r = admin.delete(f"{API}/dprs/{pytest.dpr_id}", timeout=30)
        assert r.status_code == 400

    def test_reject_flow(self, admin, pm, site_eng):
        # Fresh DPR
        payload = {"date": "2026-03-02", "project_code": f"PRJ-RJ-{TS}", "service_type": "painting",
                   "manpower": [{"role": "painter", "count": 2}], "submit": True}
        d = site_eng.post(f"{API}/dprs", json=payload, timeout=30).json()
        assert d["status"] == "submitted"
        r = pm.post(f"{API}/dprs/{d['id']}/reject", json={"reason": "Manpower count looks wrong"}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "rejected"
        assert body["reject_reason"] == "Manpower count looks wrong"
        # After rejection, supervisor can edit + resubmit
        r2 = site_eng.put(f"{API}/dprs/{d['id']}", json={"supervisor_remarks": "recount done"}, timeout=30)
        assert r2.status_code == 200
        r3 = site_eng.post(f"{API}/dprs/{d['id']}/submit", timeout=30)
        assert r3.status_code == 200 and r3.json()["status"] == "submitted"


# ──────────────────────────────────────────────────────────────────────────────
# Measurement tests
# ──────────────────────────────────────────────────────────────────────────────
class TestMeasurement:

    def test_create_validates_qty(self, admin):
        # certified > executed → 400
        bad = {"project_code": f"PRJ-M-{TS}", "items": [{"service": "scaffolding", "activity": "erected",
                                                          "executed_qty": 100, "certified_qty": 150, "unit": "m²"}]}
        r = admin.post(f"{API}/measurements", json=bad, timeout=30)
        assert r.status_code == 400 and "exceed" in r.text.lower()

    def test_create_draft(self, admin):
        payload = {
            "date": "2026-03-03", "project_code": f"PRJ-M-{TS}", "site_name": "Tank Farm",
            "service_type": "scaffolding",
            "items": [
                {"service": "scaffolding", "activity": "erected", "executed_qty": 250, "certified_qty": 240, "unit": "m²", "rate": 120},
                {"service": "scaffolding", "activity": "dismantled", "executed_qty": 80, "certified_qty": 80, "unit": "m²", "rate": 60},
            ],
            "joint_measured_with": "Mr. Patel",
        }
        r = admin.post(f"{API}/measurements", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] == "draft"
        assert m["measurement_no"].startswith("MEAS-")
        # billable = 240*120 + 80*60 = 28800 + 4800 = 33600
        assert m["billable_value"] == 33600
        assert m["total_certified"] == 320
        pytest.meas_id = m["id"]

    def test_submit_and_certify(self, admin):
        r = admin.post(f"{API}/measurements/{pytest.meas_id}/submit", timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "submitted"
        # Client certification requires signatory_name
        r2 = admin.post(f"{API}/measurements/{pytest.meas_id}/certify", json={}, timeout=30)
        assert r2.status_code == 400
        r3 = admin.post(f"{API}/measurements/{pytest.meas_id}/certify",
                        json={"signatory_name": "R. Patel", "signatory_designation": "Plant Engineer"}, timeout=30)
        assert r3.status_code == 200, r3.text
        body = r3.json()
        assert body["status"] == "client_certified"
        sig = body.get("client_signature") or {}
        assert sig.get("name") == "R. Patel" and sig.get("signed_at")

    def test_approve_for_billing(self, admin):
        r = admin.post(f"{API}/measurements/{pytest.meas_id}/approve-for-billing", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved_for_billing"

    def test_approve_blocks_unless_certified(self, admin):
        # Try to approve a NEW measurement that is only in draft → 400
        payload = {"project_code": f"PRJ-X-{TS}", "items": [{"service": "painting", "activity": "painted", "executed_qty": 1, "certified_qty": 1, "unit": "m²"}]}
        m = admin.post(f"{API}/measurements", json=payload, timeout=30).json()
        r = admin.post(f"{API}/measurements/{m['id']}/approve-for-billing", timeout=30)
        assert r.status_code == 400

    def test_pending_certification(self, admin):
        # Create a fresh submitted measurement, verify it shows up
        payload = {"project_code": f"PRJ-PC-{TS}", "items": [{"service": "insulation", "activity": "insulated", "executed_qty": 10, "certified_qty": 10, "unit": "m²", "rate": 50}], "submit": True}
        m = admin.post(f"{API}/measurements", json=payload, timeout=30).json()
        r = admin.get(f"{API}/measurements/pending-certification", timeout=30)
        assert r.status_code == 200
        body = r.json()
        ids = [row["id"] for row in body["rows"]]
        assert m["id"] in ids

    def test_summary_aggregation(self, admin):
        r = admin.get(f"{API}/measurements/summary", params={"project_code": f"PRJ-M-{TS}"}, timeout=30)
        assert r.status_code == 200
        rows = r.json()["rows"]
        # Should have at least 2 entries (erected + dismantled) for our test project
        scaffold_rows = [x for x in rows if x["service"] == "scaffolding" and x["project"] == f"PRJ-M-{TS}"]
        assert len(scaffold_rows) == 2
        erected = next(r for r in scaffold_rows if r["activity"] == "erected")
        assert erected["certified_qty"] == 240
        assert erected["billable_value"] == 28800

    def test_delete_approved_blocked(self, admin):
        r = admin.delete(f"{API}/measurements/{pytest.meas_id}", timeout=30)
        assert r.status_code == 400

    def test_reject_flow(self, admin):
        payload = {"project_code": f"PRJ-MR-{TS}", "items": [{"service": "roof_sheeting", "activity": "sheeted", "executed_qty": 50, "certified_qty": 50, "unit": "m²"}], "submit": True}
        m = admin.post(f"{API}/measurements", json=payload, timeout=30).json()
        r = admin.post(f"{API}/measurements/{m['id']}/reject", json={"reason": "Photos missing"}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        # Can re-edit after rejection
        r2 = admin.put(f"{API}/measurements/{m['id']}", json={"remarks": "added photos"}, timeout=30)
        assert r2.status_code == 200
