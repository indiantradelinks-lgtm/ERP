#!/usr/bin/env python3
"""Focused retest for Project Manager sync from Contract Handovers to Projects Master."""
import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests
from pymongo import MongoClient

API = os.environ.get("API", "http://localhost:8001/api")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "erp_database")

TARGET_HID = "4a16236b-68bd-45d4-b0a3-6b08f54d98ec"
TARGET_PROJECT_ID = "147f9689-ff9d-421a-9f7b-69e5dae8800e"
PM_ID = "f4abf031-9eaa-4fdb-bba8-8828fdc4f467"
PM_NAME = "Test PM"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
PM_LOGIN = {"email": "test_pm@erp.com", "password": "PM@12345"}


def fail(msg: str, evidence: Dict[str, Any]):
    print(json.dumps({"ok": False, "failure": msg, "evidence": evidence}, indent=2, default=str))
    raise SystemExit(1)


def login(creds: Dict[str, str]) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    if r.status_code != 200:
        fail(f"login failed for {creds['email']}", {"status": r.status_code, "body": r.text})
    token = s.cookies.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def get_json(s: requests.Session, path: str):
    r = s.get(f"{API}{path}", timeout=30)
    if r.status_code != 200:
        fail(f"GET {path} failed", {"status": r.status_code, "body": r.text})
    return r.json()


def post_json(s: requests.Session, path: str, payload: Dict[str, Any]):
    r = s.post(f"{API}{path}", json=payload, timeout=30)
    if r.status_code != 200:
        fail(f"POST {path} failed", {"status": r.status_code, "body": r.text, "payload": payload})
    return r.json()


def row_by_id(rows: List[Dict[str, Any]], row_id: str) -> Optional[Dict[str, Any]]:
    return next((r for r in rows if r.get("id") == row_id), None)


def main():
    admin = login(ADMIN)

    # Baseline list must hydrate the previous failing target row.
    handovers_before = get_json(admin, "/ops/handovers")
    target_before = row_by_id(handovers_before, TARGET_HID)
    if not target_before:
        fail("target handover missing from admin list", {"count": len(handovers_before)})
    if target_before.get("project_manager_id") != PM_ID:
        fail("target handover has unexpected PM id before reallocation", {
            "project_manager_id": target_before.get("project_manager_id"),
            "expected": PM_ID,
            "row": target_before,
        })
    if target_before.get("project_manager_label") != PM_NAME:
        fail("target handover list does not include project_manager_label Test PM before reallocation", {
            "project_manager_id": target_before.get("project_manager_id"),
            "project_manager_label": target_before.get("project_manager_label"),
            "allocation_cell_would_render": target_before.get("project_manager_label") or (target_before.get("project_manager_id") or "")[:6],
        })

    # Re-allocate to the same PM to prove labels are persisted by allocate_handover.
    payload = {
        "project_manager_id": PM_ID,
        "project_coordinator_id": target_before.get("project_coordinator_id"),
        "reporting_manager_id": target_before.get("reporting_manager_id"),
        "department": target_before.get("department") or "Operations",
        "priority": target_before.get("priority") or "medium",
        "expected_start_date": target_before.get("expected_start_date"),
        "expected_completion_date": target_before.get("expected_completion_date"),
        "remarks": "Bug verification 141: re-allocating to confirm PM label persistence",
    }
    alloc = post_json(admin, f"/ops/handovers/{TARGET_HID}/allocate", payload)
    if alloc.get("project_id") != TARGET_PROJECT_ID:
        fail("allocation returned unexpected project id", {"response": alloc, "expected_project_id": TARGET_PROJECT_ID})

    # List response after allocation.
    handovers_after = get_json(admin, "/ops/handovers")
    target_after = row_by_id(handovers_after, TARGET_HID)
    if not target_after:
        fail("target handover missing after reallocation", {"count": len(handovers_after)})
    if target_after.get("project_manager_label") != PM_NAME:
        fail("target handover list does not include project_manager_label Test PM after reallocation", {
            "project_manager_id": target_after.get("project_manager_id"),
            "project_manager_label": target_after.get("project_manager_label"),
            "allocation_cell_would_render": target_after.get("project_manager_label") or (target_after.get("project_manager_id") or "")[:6],
        })

    # Legacy hydration check: every current handover with an existing user assignee id must have a label.
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    users_by_id = {u["id"]: (u.get("name") or u.get("email")) for u in db.users.find({}, {"_id": 0, "id": 1, "name": 1, "email": 1}) if u.get("id")}
    missing_labels = []
    for h in handovers_after:
        for key in ("project_manager_id", "project_coordinator_id", "reporting_manager_id"):
            uid = h.get(key)
            label_key = key.replace("_id", "_label")
            if uid and users_by_id.get(uid) and not h.get(label_key):
                missing_labels.append({"handover_id": h.get("id"), "field": key, "uid": uid, "expected_user_label": users_by_id[uid]})
    if missing_labels:
        fail("legacy hydration failed: existing assignee ids missing labels in GET /ops/handovers", {"missing_labels": missing_labels[:20], "count": len(missing_labels)})

    # Direct persistence checks in Mongo.
    doc = db.project_handovers.find_one({"id": TARGET_HID}, {"_id": 0})
    proj_doc = db.projects.find_one({"id": TARGET_PROJECT_ID}, {"_id": 0})
    if not doc:
        fail("target handover missing in Mongo", {})
    if not proj_doc:
        fail("target project missing in Mongo", {})
    if doc.get("project_manager_label") != PM_NAME:
        fail("handover doc did not persist project_manager_label", {"project_manager_label": doc.get("project_manager_label"), "doc_subset": {k: doc.get(k) for k in ("id", "project_id", "project_manager_id", "project_manager_label")}})
    if proj_doc.get("project_manager_id") != PM_ID or proj_doc.get("project_manager_name") != PM_NAME:
        fail("project doc did not keep synced PM id/name", {"project_manager_id": proj_doc.get("project_manager_id"), "project_manager_name": proj_doc.get("project_manager_name")})

    # Projects Master API: admin should see target project and no assigned project should lack project_manager_name.
    admin_projects = get_json(admin, "/projects")
    target_project = row_by_id(admin_projects, TARGET_PROJECT_ID)
    if not target_project:
        fail("admin /api/projects does not include target project", {"admin_project_count": len(admin_projects)})
    if target_project.get("project_manager_name") != PM_NAME:
        fail("admin /api/projects target row manager name is incorrect", {"project_manager_name": target_project.get("project_manager_name"), "row": target_project})
    assigned_without_name = [
        {"id": p.get("id"), "code": p.get("code"), "project_manager_id": p.get("project_manager_id"), "project_manager_name": p.get("project_manager_name")}
        for p in admin_projects
        if p.get("project_manager_id") and not p.get("project_manager_name")
    ]
    if assigned_without_name:
        fail("admin /api/projects has assigned project(s) without project_manager_name", {"rows": assigned_without_name[:20], "count": len(assigned_without_name)})

    pm = login(PM_LOGIN)
    pm_me = get_json(pm, "/auth/me")
    pm_projects = get_json(pm, "/projects")
    if row_by_id(pm_projects, TARGET_PROJECT_ID) is None:
        fail("test_pm /api/projects does not include assigned target project", {"pm_project_count": len(pm_projects), "pm_id": pm_me.get("id")})
    not_assigned_to_pm = [
        {"id": p.get("id"), "code": p.get("code"), "pm": p.get("project_manager_id"), "pc": p.get("project_coordinator_id"), "rm": p.get("reporting_manager_id")}
        for p in pm_projects
        if PM_ID not in (p.get("project_manager_id"), p.get("project_coordinator_id"), p.get("reporting_manager_id"))
    ]
    if not_assigned_to_pm:
        fail("test_pm sees projects not assigned to that PM/coordinator/reporting manager", {"unexpected": not_assigned_to_pm[:20], "count": len(not_assigned_to_pm)})

    evidence = {
        "api": API,
        "target_handover_before": {k: target_before.get(k) for k in ("id", "handover_no", "project_id", "project_code", "project_manager_id", "project_manager_label")},
        "target_handover_after": {k: target_after.get(k) for k in ("id", "handover_no", "project_id", "project_code", "project_manager_id", "project_manager_label")},
        "allocation_response": alloc,
        "mongo_handover_persisted": {k: doc.get(k) for k in ("id", "project_id", "project_manager_id", "project_manager_label", "project_coordinator_label", "reporting_manager_label")},
        "mongo_project_synced": {k: proj_doc.get(k) for k in ("id", "code", "name", "project_manager_id", "project_manager_name")},
        "admin_projects_count": len(admin_projects),
        "target_project_api": {k: target_project.get(k) for k in ("id", "code", "name", "project_manager_id", "project_manager_name")},
        "pm_user": {"id": pm_me.get("id"), "email": pm_me.get("email"), "role": pm_me.get("role")},
        "pm_projects_count": len(pm_projects),
        "pm_project_ids": [p.get("id") for p in pm_projects],
        "legacy_hydration_missing_label_count": 0,
    }
    print(json.dumps({"ok": True, "evidence": evidence}, indent=2, default=str))


if __name__ == "__main__":
    main()
