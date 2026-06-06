"""Iteration 19 — Phase D Client Management.

Covers:
  (1) Client onboarding approval workflow
      - POST /api/clients -> pending_approval + auto approval doc with 3-step chain
      - POST /api/approvals/{id}/action three times (super_admin bypass) -> active
      - POST /api/approvals/{id}/action reject -> client.status='rejected' + reason
      - POST /api/clients/{id}/resubmit -> new chain + pending_approval (400 if wrong state)
  (2) Documents
      - POST /api/uploads accepts 'category' Form field
      - clients / client_sites folders enforce CLIENT_DOC_CATEGORIES
      - client_sites in ALLOWED_FOLDERS
  (3) Sites map
      - GET /api/sites/map returns only valid lat/lng rows
"""
import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _make_client(s, name_suffix="", status_pref=None, extra=None):
    ts = int(time.time() * 1000)
    payload = {
        "name": f"TEST_PhaseD_{ts}{name_suffix}",
        "category": "B2B",
        "main_phone": "+919999900000",
        "main_email": f"phase_d_{ts}@test.com",
    }
    if status_pref:
        payload["status"] = status_pref
    if extra:
        payload.update(extra)
    r = s.post(f"{BASE_URL}/api/clients", json=payload, timeout=30)
    return r


# ---------- (1) Onboarding approval workflow ----------
class TestClientOnboardingApproval:
    """POST /api/clients creates pending_approval + auto approval chain."""

    def test_create_client_starts_pending_approval(self, admin_session):
        r = _make_client(admin_session)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        body = r.json()
        # super_admin without status=active should still go through approval
        assert body["status"] == "pending_approval", body
        assert body.get("approval_id"), "approval_id should be set on the client"
        # verify approval doc shape
        appr = admin_session.get(f"{BASE_URL}/api/approvals/{body['approval_id']}", timeout=30)
        assert appr.status_code == 200, appr.text
        adoc = appr.json()
        assert adoc["type"] == "client_onboarding"
        assert adoc["record_id"] == body["id"]
        chain = adoc.get("chain") or []
        assert len(chain) == 3, f"expected 3 steps got {len(chain)}: {chain}"
        roles = [step.get("role") for step in chain]
        assert roles == ["sales_executive", "accounts_executive", "director"], roles
        # cleanup
        admin_session.delete(f"{BASE_URL}/api/clients/{body['id']}", timeout=30)

    def test_super_admin_can_fast_track_active(self, admin_session):
        # super_admin + status='active' bypass
        r = _make_client(admin_session, name_suffix="_FAST", status_pref="active")
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["status"] == "active", body
        assert not body.get("approval_id")
        admin_session.delete(f"{BASE_URL}/api/clients/{body['id']}", timeout=30)

    def test_approve_chain_three_times_flips_to_active(self, admin_session):
        r = _make_client(admin_session, name_suffix="_APPRV")
        assert r.status_code in (200, 201), r.text
        client = r.json()
        cid = client["id"]
        aid = client["approval_id"]
        # super_admin bypass — approve x3 walks through chain
        for i in range(3):
            ra = admin_session.post(
                f"{BASE_URL}/api/approvals/{aid}/action",
                json={"action": "approve", "comment": f"step {i+1}"},
                timeout=30,
            )
            assert ra.status_code in (200, 201), f"step {i+1}: {ra.status_code} {ra.text}"
        # approval should be approved
        ap = admin_session.get(f"{BASE_URL}/api/approvals/{aid}", timeout=30).json()
        assert ap.get("status") == "approved", ap
        # client must now be active
        c = admin_session.get(f"{BASE_URL}/api/clients/by-id/{cid}", timeout=30)
        assert c.status_code == 200, c.text
        cbody = c.json()
        assert cbody["status"] == "active", cbody
        assert cbody.get("approved_at"), "approved_at should be set"
        admin_session.delete(f"{BASE_URL}/api/clients/{cid}", timeout=30)

    def test_reject_sets_rejected_with_reason(self, admin_session):
        r = _make_client(admin_session, name_suffix="_REJ")
        client = r.json()
        cid = client["id"]
        aid = client["approval_id"]
        reason = "Missing trade license"
        rr = admin_session.post(
            f"{BASE_URL}/api/approvals/{aid}/action",
            json={"action": "reject", "comment": reason},
            timeout=30,
        )
        assert rr.status_code in (200, 201), rr.text
        c = admin_session.get(f"{BASE_URL}/api/clients/by-id/{cid}", timeout=30).json()
        # Iter 50: rejection is NOT terminal — record bounces to pending_revision.
        assert c["status"] == "pending_revision", c
        assert c.get("reject_reason") == reason, c
        # cleanup later in resubmit test, save id
        TestClientOnboardingApproval._rejected_id = cid

    def test_resubmit_only_works_on_rejected(self, admin_session):
        # Try resubmit on a pending_approval client -> 400
        r = _make_client(admin_session, name_suffix="_RES_BAD")
        client = r.json()
        cid = client["id"]
        rs = admin_session.post(f"{BASE_URL}/api/clients/{cid}/resubmit", timeout=30)
        assert rs.status_code == 400, f"expected 400 got {rs.status_code} {rs.text}"
        admin_session.delete(f"{BASE_URL}/api/clients/{cid}", timeout=30)

    def test_resubmit_creates_new_chain_and_clears_reason(self, admin_session):
        cid = getattr(TestClientOnboardingApproval, "_rejected_id", None)
        if not cid:
            pytest.skip("no rejected client from previous test")
        rs = admin_session.post(f"{BASE_URL}/api/clients/{cid}/resubmit", timeout=30)
        assert rs.status_code in (200, 201), rs.text
        new_aid = rs.json().get("approval_id")
        assert new_aid
        c = admin_session.get(f"{BASE_URL}/api/clients/by-id/{cid}", timeout=30).json()
        assert c["status"] == "pending_approval", c
        assert c.get("approval_id") == new_aid
        assert not c.get("reject_reason"), c
        # New approval doc shape
        ap = admin_session.get(f"{BASE_URL}/api/approvals/{new_aid}", timeout=30).json()
        assert ap["type"] == "client_onboarding"
        assert len(ap.get("chain") or []) == 3
        admin_session.delete(f"{BASE_URL}/api/clients/{cid}", timeout=30)


# ---------- (2) Documents / uploads ----------
class TestUploadsCategory:
    """POST /api/uploads category Form field + validation."""

    def _upload(self, s, folder, category=None, parent_id="x"):
        files = {"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")}
        data = {"folder": folder, "parent_type": folder, "parent_id": parent_id, "title": "TEST_doc"}
        if category is not None:
            data["category"] = category
        return s.post(f"{BASE_URL}/api/uploads", files=files, data=data, timeout=30)

    def test_clients_folder_with_valid_category_PAN(self, admin_session):
        r = self._upload(admin_session, "clients", category="PAN")
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("category") == "PAN", body
        assert body.get("folder") == "clients"
        # cleanup
        if body.get("id"):
            admin_session.delete(f"{BASE_URL}/api/files/{body['id']}", timeout=30)

    def test_client_sites_folder_allowed_and_category_GST(self, admin_session):
        r = self._upload(admin_session, "client_sites", category="GST")
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("category") == "GST", body
        assert body.get("folder") == "client_sites"
        if body.get("id"):
            admin_session.delete(f"{BASE_URL}/api/files/{body['id']}", timeout=30)

    def test_clients_folder_with_invalid_category_returns_400(self, admin_session):
        r = self._upload(admin_session, "clients", category="INVALID_XYZ")
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        # error message must include allowed list
        for cat in ["PAN", "GST", "MSA"]:
            assert cat in detail, f"allowed list missing {cat} in {detail}"

    def test_client_sites_folder_with_invalid_category_returns_400(self, admin_session):
        r = self._upload(admin_session, "client_sites", category="bogus")
        assert r.status_code == 400, r.text

    def test_upload_without_category_still_allowed(self, admin_session):
        # category optional — empty string accepted
        r = self._upload(admin_session, "clients", category=None)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        # category should be None (or empty)
        assert not body.get("category")
        if body.get("id"):
            admin_session.delete(f"{BASE_URL}/api/files/{body['id']}", timeout=30)


# ---------- (3) Sites map ----------
class TestSitesMap:
    """GET /api/sites/map only returns sites with valid geo coordinates."""

    @pytest.fixture(scope="class")
    def seeded(self, admin_session):
        # Create an active client (fast-track) then add 3 sites with varying geo
        ts = int(time.time() * 1000)
        cr = admin_session.post(
            f"{BASE_URL}/api/clients",
            json={
                "name": f"TEST_PhaseD_MAP_{ts}",
                "category": "B2B",
                "main_phone": "+919999900111",
                "main_email": f"map_{ts}@test.com",
                "status": "active",
            },
            timeout=30,
        )
        assert cr.status_code in (200, 201), cr.text
        client = cr.json()
        client_id = client["id"]

        site_ids = []
        sites_url = f"{BASE_URL}/api/clients/{client_id}/sites"
        # Good site
        s1 = admin_session.post(
            sites_url,
            json={"name": "Good Geo Site", "city": "Dubai",
                  "geo_lat": "25.276", "geo_lng": "55.296", "status": "active"},
            timeout=30,
        )
        assert s1.status_code in (200, 201), s1.text
        site_ids.append(s1.json()["id"])
        # Out-of-range
        s2 = admin_session.post(
            sites_url,
            json={"name": "Out Of Range", "city": "Nowhere",
                  "geo_lat": "999", "geo_lng": "0", "status": "active"},
            timeout=30,
        )
        if s2.status_code in (200, 201):
            site_ids.append(s2.json()["id"])
        # Empty geo
        s3 = admin_session.post(
            sites_url,
            json={"name": "No Geo", "city": "Nowhere",
                  "geo_lat": "", "geo_lng": "", "status": "active"},
            timeout=30,
        )
        if s3.status_code in (200, 201):
            site_ids.append(s3.json()["id"])
        yield {"client_id": client_id, "site_ids": site_ids, "good_id": site_ids[0]}
        # teardown
        for sid in site_ids:
            admin_session.delete(f"{BASE_URL}/api/sites/{sid}", timeout=30)
        admin_session.delete(f"{BASE_URL}/api/clients/{client_id}", timeout=30)

    def test_sites_map_returns_valid_only(self, admin_session, seeded):
        r = admin_session.get(f"{BASE_URL}/api/sites/map", timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        ids = {row["id"] for row in rows}
        # Good site present
        assert seeded["good_id"] in ids, f"good geo site missing in map response (got {len(rows)} rows)"
        # All rows must have valid lat/lng floats in range
        for row in rows:
            lat = row.get("geo_lat")
            lng = row.get("geo_lng")
            assert isinstance(lat, (int, float))
            assert isinstance(lng, (int, float))
            assert -90 <= lat <= 90
            assert -180 <= lng <= 180

    def test_sites_map_excludes_out_of_range_and_empty(self, admin_session, seeded):
        r = admin_session.get(f"{BASE_URL}/api/sites/map", timeout=30)
        rows = {row["id"]: row for row in r.json()}
        # Out-of-range and empty geo sites should NOT appear
        for sid in seeded["site_ids"][1:]:
            assert sid not in rows, f"invalid-geo site {sid} should be excluded"
