"""Iter 196 backend tests: Manpower → Recruitment auto-raise, HR link-back, tracking.

Covers:
  * Manpower request approval chain auto-raises recruitment requisitions
  * Pool-covered lines still create a requisition flagged pool_covered
  * Manpower request without line items still creates a requisition
  * POST /api/project-requests/sync-recruitment (idempotent HR one-click)
  * Recruitment list carries source_request_no + requested_by
  * HR action (interview → filled) mirrors onto source request line + status
  * recruitment_summary appears on GET /api/project-requests
  * Non-manpower requests are unaffected (regression)
"""
import os
import pytest
import requests


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")


BASE = _base()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def project(admin):
    r = admin.get(f"{BASE}/api/projects", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
    proj = next((p for p in rows if p.get("code") == "PRJ-2025-01"), rows[0])
    return proj


# ── Head Office cost center (mandatory for HO requests, but manpower on project uses project CC) ──
@pytest.fixture(scope="module")
def project_cc(admin, project):
    r = admin.get(f"{BASE}/api/procurement/master/cost-centers?project_id={project['id']}", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
    cc = next((c for c in rows if c.get("project_id") == project["id"]), None)
    assert cc, "no project cost center found"
    return cc


# ---------------------------------------------------------------------------
# 1) Approval-time auto-raise (real end-to-end)
# ---------------------------------------------------------------------------
def _create_manpower(admin, project, cc, items, description="TEST_iter196 manpower"):
    body = {
        "project_id": project["id"], "project_code": project["code"],
        "request_type": "manpower",
        "priority": "medium", "description": description,
        "items": items,
        "period_from": "2026-02-01", "period_to": "2026-04-30",
        "months": 3,
        "cost_center_id": cc["id"],
        "site_location": project.get("name"),
        "remarks": "iter196 auto test",
    }
    r = admin.post(f"{BASE}/api/project-requests", json=body, timeout=60)
    assert r.status_code == 200, f"create manpower: {r.status_code} {r.text[:400]}"
    return r.json()


def _get_request(admin, rid):
    r = admin.get(f"{BASE}/api/project-requests?date_from=2020-01-01&date_to=2099-12-31",
                  timeout=30).json()
    rows = r.get("rows", r) if isinstance(r, dict) else r
    for row in rows:
        if row["id"] == rid:
            return row
    return None


def _approve_all(admin, rid):
    """Walk the entire pending approval chain by calling approve until with_dept/sourcing."""
    for _ in range(6):
        row = _get_request(admin, rid)
        assert row, f"request {rid} not found"
        if row.get("status") != "pending_approval":
            return row
        r = admin.post(f"{BASE}/api/project-requests/{rid}/approve",
                       json={"remarks": "approve for iter196"}, timeout=30)
        assert r.status_code == 200, f"approve step failed: {r.status_code} {r.text[:400]}"
    return _get_request(admin, rid)


class TestApprovalTimeAutoRaise:
    def test_manpower_line_creates_requisition(self, admin, project, project_cc):
        items = [{
            "name": "TEST_iter196_Scaffolder", "quantity": 3, "unit": "Persons",
            "rate": 20000, "specs": "certified rope access"
        }]
        req = _create_manpower(admin, project, project_cc, items)
        rid = req["id"]
        row = _approve_all(admin, rid)
        assert row["status"] == "sourcing", f"expected sourcing, got {row['status']} — chain: {row.get('chain')}"
        assert row.get("recruitment_nos"), "recruitment_nos missing on source request after approval"
        req_no = row["recruitment_nos"][0]

        # Recruitment row present in HR list
        r = admin.get(f"{BASE}/api/recruitment-requests", timeout=30)
        assert r.status_code == 200
        rows = r.json(); rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        rec = next((x for x in rows if x.get("req_no") == req_no), None)
        assert rec, f"{req_no} not visible on Recruitment Requests"
        assert rec["source"] == "project_request"
        assert rec["source_request_no"] == row["request_no"]
        assert rec["requested_by"], "requested_by must be populated for tracking column"
        assert rec["vacancies"] == 3
        assert rec["status"] == "open"

    def test_pool_covered_line_still_raises(self, admin, project, project_cc):
        # Requesting 0.001 quantity of a very obscure skill guarantees availability_lines
        # exists — but we drive pool_covered by using a designation likely to have workers.
        # Simpler: rely on _do_raise_recruitment behaviour — a line still yields a rec
        # even when shortfall==0 provided availability_lines matched.
        # Use quantity=1 with a common skill name that may have available workers.
        items = [{"name": "TEST_iter196_Helper", "quantity": 1, "unit": "Persons", "rate": 15000}]
        req = _create_manpower(admin, project, project_cc, items,
                               description="TEST_iter196 pool-covered probe")
        row = _approve_all(admin, req["id"])
        assert row["status"] == "sourcing"
        assert row.get("recruitment_nos")
        req_no = row["recruitment_nos"][0]
        r = admin.get(f"{BASE}/api/recruitment-requests", timeout=30).json()
        rows = r.get("rows", r) if isinstance(r, dict) else r
        rec = next((x for x in rows if x.get("req_no") == req_no), None)
        assert rec, "pool-covered requisition should still be on Recruitment page"
        # pool_covered may be True or False depending on live worker pool — assert key exists
        assert "pool_covered" in rec

    def test_manpower_without_items_still_raises(self, admin, project, project_cc):
        req = _create_manpower(admin, project, project_cc, [],
                               description="TEST_iter196 header-only manpower request")
        row = _approve_all(admin, req["id"])
        assert row["status"] == "sourcing", f"header-only manpower must move to sourcing, got {row['status']}"
        assert row.get("recruitment_nos"), "header-only manpower must create at least one requisition"


# ---------------------------------------------------------------------------
# 2) Sync endpoint idempotency
# ---------------------------------------------------------------------------
class TestSyncEndpoint:
    def test_sync_is_idempotent(self, admin):
        r1 = admin.post(f"{BASE}/api/project-requests/sync-recruitment", json={}, timeout=60)
        assert r1.status_code == 200, r1.text[:400]
        body1 = r1.json()
        assert "count" in body1 and "created" in body1
        # Second call should report zero — everything already sourced.
        r2 = admin.post(f"{BASE}/api/project-requests/sync-recruitment", json={}, timeout=60)
        assert r2.status_code == 200
        assert r2.json()["count"] == 0, f"expected idempotent 0, got {r2.json()}"


# ---------------------------------------------------------------------------
# 3) HR action link-back + summary + fulfilment
# ---------------------------------------------------------------------------
class TestHrActionLinkBack:
    def test_full_lifecycle(self, admin, project, project_cc):
        items = [{"name": "TEST_iter196_Rigger", "quantity": 2, "unit": "Persons", "rate": 22000}]
        req = _create_manpower(admin, project, project_cc, items,
                               description="TEST_iter196 lifecycle")
        row = _approve_all(admin, req["id"])
        req_no = row["recruitment_nos"][0]
        rec_list = admin.get(f"{BASE}/api/recruitment-requests", timeout=30).json()
        rec_list = rec_list.get("rows", rec_list) if isinstance(rec_list, dict) else rec_list
        rec = next(x for x in rec_list if x["req_no"] == req_no)
        rec_id = rec["id"]

        # HR: interview + partial hire
        r = admin.post(f"{BASE}/api/recruitment-requests/{rec_id}/hr-action",
                       json={"status": "interview", "pm_info_received": True,
                             "hired": 1, "remarks": "shortlisted 4 for interview"}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        after = r.json()
        assert after["status"] == "interview"
        assert after["hired"] == 1
        assert after.get("history") and after["history"][-1]["to"] == "interview"

        # source request line reflects partial hire
        src = _get_request(admin, req['id'])
        line = src["items"][0]
        assert line.get("hired_count") == 1
        assert line.get("recruitment_status") == "interview"
        assert src["status"] == "sourcing"  # not yet fulfilled

        # HR: filled — fully hire all vacancies
        r = admin.post(f"{BASE}/api/recruitment-requests/{rec_id}/hr-action",
                       json={"status": "filled", "hired": 2,
                             "remarks": "all positions closed"}, timeout=30)
        assert r.status_code == 200
        after = r.json()
        assert after["status"] == "filled"
        assert after["hired"] == 2

        # source request should flip to fulfilled and line marked done
        src = _get_request(admin, req['id'])
        assert src["status"] == "fulfilled", f"expected fulfilled, got {src['status']}"
        line = src["items"][0]
        assert line.get("fulfil_status") == "fulfilled"
        assert line.get("hired_count") == 2

    def test_recruitment_summary_on_list(self, admin, project):
        r = admin.get(f"{BASE}/api/project-requests?project_code={project['code']}", timeout=30)
        assert r.status_code == 200
        rows = r.json(); rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        mp = [x for x in rows if x.get("request_type") == "manpower" and x.get("recruitment_summary")]
        assert mp, "no manpower request carries recruitment_summary"
        s = mp[0]["recruitment_summary"]
        for k in ("requisitions", "vacancies", "hired", "latest_status", "by_status", "lines"):
            assert k in s, f"recruitment_summary.{k} missing"

    def test_reject_requires_remarks(self, admin, project, project_cc):
        req = _create_manpower(admin, project, project_cc,
                               [{"name": "TEST_iter196_RejectProbe", "quantity": 1, "unit": "Persons", "rate": 10000}],
                               description="TEST_iter196 reject probe")
        row = _approve_all(admin, req["id"])
        rec_no = row["recruitment_nos"][0]
        rec_list = admin.get(f"{BASE}/api/recruitment-requests", timeout=30).json()
        rec_list = rec_list.get("rows", rec_list) if isinstance(rec_list, dict) else rec_list
        rec = next(x for x in rec_list if x["req_no"] == rec_no)
        r = admin.post(f"{BASE}/api/recruitment-requests/{rec['id']}/hr-action",
                       json={"status": "rejected", "remarks": ""}, timeout=30)
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 4) Regression: non-manpower unaffected
# ---------------------------------------------------------------------------
class TestNonManpowerRegression:
    def test_material_request_no_recruitment_summary(self, admin, project, project_cc):
        body = {
            "project_id": project["id"], "project_code": project["code"],
            "request_type": "material", "priority": "medium",
            "description": "TEST_iter196 regression material",
            "items": [{"name": "TEST_iter196 nuts", "quantity": 10, "unit": "Nos", "rate": 5}],
            "cost_center_id": project_cc["id"],
            "site_location": project.get("name"),
        }
        r = admin.post(f"{BASE}/api/project-requests", json=body, timeout=60)
        assert r.status_code == 200, r.text[:400]
        row = r.json()
        # Approve chain
        row = _approve_all(admin, row["id"])
        assert row["status"] in ("with_dept", "pr_raised", "sourcing", "fulfilled")
        assert not row.get("recruitment_nos"), "material request must not raise recruitment"
        # list-level summary
        r = admin.get(f"{BASE}/api/project-requests?project_code={project['code']}", timeout=30).json()
        rows = r.get("rows", r) if isinstance(r, dict) else r
        me = next(x for x in rows if x["id"] == row["id"])
        assert "recruitment_summary" not in me

    def test_summary_and_date_range_filter_still_work(self, admin, project):
        r = admin.get(f"{BASE}/api/project-requests/summary?project_code={project['code']}", timeout=30)
        assert r.status_code == 200
        s = r.json()
        for k in ("total", "pending_approval", "with_dept", "fulfilled", "pr_raised", "est_value"):
            assert k in s
        r = admin.get(f"{BASE}/api/project-requests?date_from=2026-01-01&date_to=2026-12-31", timeout=30)
        assert r.status_code == 200
