#!/usr/bin/env python3
"""Focused verification for Contract Handover PM -> Projects Master manager sync."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import requests

BACKEND_BASE = os.environ.get("TEST_API_BASE", "http://localhost:8001/api")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"
PM_EMAIL = "test_pm@erp.com"
PM_PASSWORD = "PM@12345"
REAL_HID = "4a16236b-68bd-45d4-b0a3-6b08f54d98ec"
REAL_PROJECT_ID = "147f9689-ff9d-421a-9f7b-69e5dae8800e"
REAL_PM_ID = "f4abf031-9eaa-4fdb-bba8-8828fdc4f467"
REAL_PROJECT_CODE = "PRJ-2026-0035"
EXPECTED_PM_NAME = "Test PM"
INVALID_PM_ID = "missing-user-for-pm-sync-test"


def fail(msg, details=None):
    print(f"FAIL: {msg}")
    if details is not None:
        print(json.dumps(details, indent=2, default=str))
    sys.exit(1)


def ok(msg, details=None):
    print(f"PASS: {msg}")
    if details is not None:
        print(json.dumps(details, indent=2, default=str))


def login(email, password):
    s = requests.Session()
    r = s.post(f"{BACKEND_BASE}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        fail(f"login failed for {email}: {r.status_code}", safe_json(r))
    access = s.cookies.get("access_token")
    # Backend sets Secure cookies; when tests call localhost over http, requests will not send them.
    # Use Bearer fallback from the same cookie value for API checks.
    if access:
        s.headers.update({"Authorization": f"Bearer {access}"})
    return s, r.json().get("user") or r.json()


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text[:1000]}


def post_json(session, path, payload):
    return session.post(f"{BACKEND_BASE}{path}", json=payload, timeout=30)


def get_json(session, path, expected=200):
    r = session.get(f"{BACKEND_BASE}{path}", timeout=30)
    if r.status_code != expected:
        fail(f"GET {path} returned {r.status_code}, expected {expected}", safe_json(r))
    return r.json()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    try:
        from pymongo import MongoClient
        from dotenv import dotenv_values
    except Exception as e:
        fail("pymongo/python-dotenv unavailable for disposable first-allocation seed", {"error": str(e)})
    env = dotenv_values("/app/backend/.env")
    mongo_url = (env.get("MONGO_URL") or "mongodb://localhost:27017").strip('"')
    db_name = (env.get("DB_NAME") or "erp_database").strip('"')
    return MongoClient(mongo_url)[db_name]


def allocation_payload(pm_id=REAL_PM_ID, remarks="Focused PM sync verification"):
    return {
        "project_manager_id": pm_id,
        "project_coordinator_id": None,
        "reporting_manager_id": None,
        "department": "Projects & Operations",
        "priority": "medium",
        "expected_start_date": "2026-07-22",
        "expected_completion_date": "2026-08-22",
        "remarks": remarks,
    }


def verify_real_reallocation(admin):
    # Capture current state for invalid-id guard comparison.
    before = get_json(admin, f"/projects/{REAL_PROJECT_ID}")
    before_pm_id = before.get("project_manager_id")
    before_pm_name = before.get("project_manager_name")

    r = post_json(admin, f"/ops/handovers/{REAL_HID}/allocate", allocation_payload())
    if r.status_code != 200:
        fail("real handover allocation endpoint failed", {"status": r.status_code, "body": safe_json(r)})
    body = r.json()
    if not body.get("ok") or body.get("project_id") != REAL_PROJECT_ID:
        fail("real handover allocation response missing ok/project_id", body)
    ok("real handover reallocation returned ok:true", body)

    project = get_json(admin, f"/projects/{REAL_PROJECT_ID}")
    if project.get("project_manager_id") != REAL_PM_ID:
        fail("project_manager_id was not synced to Projects Master", project)
    if not project.get("project_manager_name") or EXPECTED_PM_NAME.lower() not in project.get("project_manager_name", "").lower():
        fail("project_manager_name was not populated on Projects Master", project)
    ok("Projects Master API has synced project_manager_id and project_manager_name", {
        "code": project.get("code"),
        "project_manager_id": project.get("project_manager_id"),
        "project_manager_name": project.get("project_manager_name"),
    })

    handover = get_json(admin, f"/ops/handovers/{REAL_HID}")
    if EXPECTED_PM_NAME.lower() not in (handover.get("project_manager_label") or "").lower():
        fail("handover detail did not show PM label", handover)
    ok("handover detail shows PM label", {"project_manager_label": handover.get("project_manager_label")})

    # Invalid PM id must return clean 400 and not overwrite project manager fields.
    bad = post_json(admin, f"/ops/handovers/{REAL_HID}/allocate", allocation_payload(INVALID_PM_ID, "Invalid id guard check"))
    bad_body = safe_json(bad)
    if bad.status_code != 400:
        fail("invalid project_manager_id did not return 400", {"status": bad.status_code, "body": bad_body})
    expected_msg = "Project Manager user not found — refresh the user list and pick again"
    if bad_body.get("detail") != expected_msg:
        fail("invalid project_manager_id 400 message mismatch", bad_body)
    after_bad = get_json(admin, f"/projects/{REAL_PROJECT_ID}")
    if after_bad.get("project_manager_id") != REAL_PM_ID or after_bad.get("project_manager_name") != project.get("project_manager_name"):
        fail("invalid project_manager_id mutated Projects Master assignment", after_bad)
    ok("invalid PM id returns guarded 400 and leaves project manager fields intact", bad_body)

    return project


def verify_backfill_health(admin):
    projects = get_json(admin, "/projects")
    broken = [
        {"id": p.get("id"), "code": p.get("code"), "project_manager_id": p.get("project_manager_id"), "project_manager_name": p.get("project_manager_name")}
        for p in projects
        if p.get("project_manager_id") and not str(p.get("project_manager_name") or "").strip()
    ]
    if broken:
        fail("some projects still have project_manager_id but blank project_manager_name", {"broken": broken[:20], "count": len(broken)})
    ok("all admin-visible projects with project_manager_id have non-empty project_manager_name", {"checked_projects": len(projects)})


def verify_pm_scoped_views(pm):
    pm_projects = get_json(pm, "/projects")
    codes = [p.get("code") for p in pm_projects]
    if REAL_PROJECT_CODE not in codes:
        fail("test_pm /api/projects does not include assigned project", {"codes": codes})
    if any(not (p.get("project_manager_id") == REAL_PM_ID or p.get("project_coordinator_id") == REAL_PM_ID or p.get("reporting_manager_id") == REAL_PM_ID) for p in pm_projects):
        fail("test_pm /api/projects includes unassigned project(s)", pm_projects)
    ok("test_pm /api/projects includes PRJ-2026-0035 and only assigned projects", {"codes": codes})

    my_projects = get_json(pm, "/ops/my-projects")
    handover_ids = [h.get("id") for h in my_projects]
    if REAL_HID not in handover_ids:
        fail("test_pm /api/ops/my-projects does not include assigned real handover", {"handover_ids": handover_ids})
    real = next(h for h in my_projects if h.get("id") == REAL_HID)
    if EXPECTED_PM_NAME.lower() not in (real.get("project_manager_label") or "").lower():
        fail("test_pm /api/ops/my-projects real handover missing PM label", real)
    ok("test_pm /api/ops/my-projects includes assigned handover with PM label", {"id": REAL_HID, "label": real.get("project_manager_label")})


def verify_first_allocation_path(admin):
    db = get_db()
    project_id = f"pm-sync-firstalloc-project-{uuid.uuid4()}"
    handover_id = f"pm-sync-firstalloc-handover-{uuid.uuid4()}"
    code = f"PM-SYNC-{uuid.uuid4().hex[:8].upper()}"
    project_doc = {
        "id": project_id,
        "code": code,
        "name": "PM Sync First Allocation Disposable Project",
        "client": "QA Client",
        "site": "QA Site",
        "status": "planned",
        "created_at": now_iso(),
        "created_by": "bug-verification-script",
        "_test_marker": "pm_sync_bug_verification",
    }
    handover_doc = {
        "id": handover_id,
        "handover_no": f"CHO-QA-{uuid.uuid4().hex[:8].upper()}",
        "project_id": project_id,
        "project_code": code,
        "project_name": project_doc["name"],
        "client_name": project_doc["client"],
        "site_location": project_doc["site"],
        "contract_value": 12345,
        "status": "submitted",
        "created_at": now_iso(),
        "created_by": "bug-verification-script",
        "submitted_at": now_iso(),
        "submitted_by": "bug-verification-script",
        "_test_marker": "pm_sync_bug_verification",
    }
    try:
        db.projects.insert_one(project_doc)
        db.project_handovers.insert_one(handover_doc)
        r = post_json(admin, f"/ops/handovers/{handover_id}/allocate", allocation_payload(REAL_PM_ID, "First allocation path check"))
        if r.status_code != 200:
            fail("first allocation disposable linked handover failed", {"status": r.status_code, "body": safe_json(r)})
        body = r.json()
        if body.get("status") != "active" or body.get("project_id") != project_id:
            fail("first allocation response did not activate linked handover", body)
        project = get_json(admin, f"/projects/{project_id}")
        if project.get("project_manager_id") != REAL_PM_ID or EXPECTED_PM_NAME.lower() not in (project.get("project_manager_name") or "").lower():
            fail("first allocation did not sync PM id/name to linked project", project)
        h = get_json(admin, f"/ops/handovers/{handover_id}")
        if h.get("status") != "active" or EXPECTED_PM_NAME.lower() not in (h.get("project_manager_label") or "").lower():
            fail("first allocation handover did not become active with PM label", h)
        ok("first allocation path synced PM id/name to linked project", {
            "handover_id": handover_id,
            "project_id": project_id,
            "project_manager_name": project.get("project_manager_name"),
            "status": h.get("status"),
        })
    finally:
        db.project_handovers.delete_one({"id": handover_id, "_test_marker": "pm_sync_bug_verification"})
        db.projects.delete_one({"id": project_id, "_test_marker": "pm_sync_bug_verification"})


def main():
    print(f"Using API base: {BACKEND_BASE}")
    admin, admin_user = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if admin_user.get("role") != "super_admin":
        fail("admin account is not super_admin", admin_user)
    ok("admin login succeeded", {"id": admin_user.get("id"), "role": admin_user.get("role")})

    # Verify requested PM id is a real account by successful PM login and id match.
    pm, pm_user = login(PM_EMAIL, PM_PASSWORD)
    if pm_user.get("id") != REAL_PM_ID or pm_user.get("role") != "project_manager":
        fail("test_pm credential/id/role mismatch", pm_user)
    ok("test_pm login succeeded and id matches requested PM", {"id": pm_user.get("id"), "name": pm_user.get("name"), "role": pm_user.get("role")})

    verify_real_reallocation(admin)
    verify_first_allocation_path(admin)
    verify_backfill_health(admin)
    verify_pm_scoped_views(pm)

    print("ALL_BACKEND_PM_SYNC_CHECKS_PASSED")


if __name__ == "__main__":
    main()
