"""Iter 224 — HR Attendance Summary: Location / Project filter.

Attendance rows are frequently saved without a project tag (biometric import,
auto-derive, quick mark). The filter must therefore fall back to the employee's
HR posting / deployment, otherwise picking a project shows nothing.
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
MONTH = "2026-04"
TAG = uuid.uuid4().hex[:6]
PROJ_A = f"PRJ-ITER224-A-{TAG}"
PROJ_B = f"PRJ-ITER224-B-{TAG}"


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def seed(db):
    """Three employees: posted to A, deployed to B, and unposted (Head Office).
    Every attendance row is written WITHOUT a project tag, as the importers do."""
    emps = {
        "posted": {"id": f"e224-posted-{TAG}", "name": f"ITER224 Posted {TAG}",
                   "emp_code": f"E224P{TAG}", "current_project_code": PROJ_A},
        "deployed": {"id": f"e224-deployed-{TAG}", "name": f"ITER224 Deployed {TAG}",
                     "emp_code": f"E224D{TAG}"},
        "ho": {"id": f"e224-ho-{TAG}", "name": f"ITER224 HeadOffice {TAG}",
               "emp_code": f"E224H{TAG}"},
    }
    for e in emps.values():
        db.employees.insert_one({**e, "status": "active", "department": "ITER224",
                                 "designation": "Fitter"})
    db.deployments.insert_one({"id": f"dep224-{TAG}", "deployment_no": f"DEP-224-{TAG}",
                               "employee_id": emps["deployed"]["id"], "project": PROJ_B,
                               "status": "active", "start_date": f"{MONTH}-01", "end_date": None})
    att = []
    for key, emp in emps.items():
        for day in ("01", "02", "03"):
            att.append({"id": f"a224-{key}-{day}-{TAG}", "employee_id": emp["id"],
                        "employee_name": emp["name"], "employee_code": emp["emp_code"],
                        "date": f"{MONTH}-{day}", "status": "present", "department": "ITER224",
                        "project_code": None, "total_hours": 8, "overtime_hours": 0})
    # one row explicitly tagged to project A for the Head Office employee
    att.append({"id": f"a224-ho-tagged-{TAG}", "employee_id": emps["ho"]["id"],
                "employee_name": emps["ho"]["name"], "employee_code": emps["ho"]["emp_code"],
                "date": f"{MONTH}-04", "status": "present", "department": "ITER224",
                "project_code": PROJ_A, "total_hours": 8, "overtime_hours": 0})
    db.attendance.insert_many(att)
    yield emps
    db.attendance.delete_many({"id": {"$regex": f"a224-.*{TAG}"}})
    db.deployments.delete_one({"id": f"dep224-{TAG}"})
    db.employees.delete_many({"id": {"$in": [e["id"] for e in emps.values()]}})


def _summary(s, project=None, **extra):
    params = {"month": MONTH, "q": "ITER224", **extra}
    if project:
        params["project_code"] = project
    r = s.get(f"{API}/hr2/attendance-plus/summary", params=params, timeout=90)
    assert r.status_code == 200, r.text
    return r.json()


def _names(data):
    return sorted(e["employee_name"] for e in data["employees"])


def test_no_filter_shows_everyone(s, seed):
    assert len(_names(_summary(s))) == 3


def test_posted_employee_appears_under_their_project(s, seed):
    d = _summary(s, PROJ_A)
    names = _names(d)
    assert seed["posted"]["name"] in names, "HR posting must drive the project filter"
    # plus the employee whose row is explicitly tagged to A
    assert seed["ho"]["name"] in names
    assert seed["deployed"]["name"] not in names


def test_untagged_attendance_still_counts_for_the_project(s, seed):
    d = _summary(s, PROJ_A)
    row = next(e for e in d["employees"] if e["employee_name"] == seed["posted"]["name"])
    assert row["P"] == 3, "all three untagged present days belong to the posted project"


def test_deployed_employee_appears_under_the_deployment_project(s, seed):
    names = _names(_summary(s, PROJ_B))
    assert names == [seed["deployed"]["name"]]


def test_head_office_excludes_project_mapped_employees(s, seed):
    names = _names(_summary(s, "HEAD-OFFICE"))
    assert seed["ho"]["name"] in names
    assert seed["posted"]["name"] not in names
    assert seed["deployed"]["name"] not in names


def test_unknown_project_returns_nothing(s, seed):
    assert _summary(s, f"PRJ-NOPE-{TAG}")["employees"] == []


def test_project_filter_combines_with_department(s, seed):
    assert len(_names(_summary(s, PROJ_A, department="ITER224"))) == 2
    assert _summary(s, PROJ_A, department="NoSuchDept")["employees"] == []


def test_breakdown_export_uses_the_same_filter(s, seed):
    r = s.get(f"{API}/hr2/attendance-plus/summary/breakdown/export",
              params={"fmt": "xlsx", "month": MONTH, "project_code": PROJ_B, "q": "ITER224"}, timeout=120)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd")
    assert len(r.content) > 1000


def test_summary_export_uses_the_same_filter(s, seed):
    r = s.get(f"{API}/hr2/attendance-plus/summary/export",
              params={"fmt": "csv", "month": MONTH, "project_code": PROJ_A, "q": "ITER224"}, timeout=120)
    assert r.status_code == 200
    body = r.content.decode("utf-8", "ignore")
    assert f"ITER224 Posted {TAG}" in body
    assert f"ITER224 Deployed {TAG}" not in body
