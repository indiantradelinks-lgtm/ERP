"""Iter 116 — Contract Handovers / Project visibility scope for 'Manager O P'.

Validates that:
  • A user with role 'manager_o_p' and department 'Projects & Operations' sees
    ONLY the contract handovers / projects they are assigned to.
  • Admin/super_admin still sees everything.
  • A custom role-label 'Manager O P' with department 'Projects & Operations'
    is also scoped via department fallback in pm_scope.is_pm_scoped.
"""
import os
import uuid
import pytest
import requests
import bcrypt
import asyncio
import re
from pathlib import Path

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


def _mongo_db():
    """Direct DB handle for seeding users without going through admin UI."""
    from pathlib import Path as _P
    import motor.motor_asyncio
    env_path = _P("/app/backend/.env")
    env = {}
    for line in env_path.read_text().splitlines():
        m = re.match(r'^\s*([A-Z_]+)\s*=\s*\"?([^\"]*)\"?\s*$', line)
        if m:
            env[m.group(1)] = m.group(2)
    client = motor.motor_asyncio.AsyncIOMotorClient(env["MONGO_URL"])
    return client[env["DB_NAME"]]


def _hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


@pytest.fixture(scope="module")
def seeded():
    """Create two 'Manager O P' users and two handovers — one per user.
    Returns (user_a, user_b, handover_a_id, handover_b_id, project_a_id, project_b_id).
    """
    db = _mongo_db()

    async def _seed():
        ua = {
            "id": f"u-mop-a-{uuid.uuid4().hex[:8]}",
            "email": f"pm.a.{uuid.uuid4().hex[:6]}@erp.com",
            "name": "Manager OP A",
            "role": "manager_o_p",
            "department": "Projects & Operations",
            "active": True,
            "password_hash": _hash_pw("OpA@12345"),
        }
        ub = {
            "id": f"u-mop-b-{uuid.uuid4().hex[:8]}",
            "email": f"pm.b.{uuid.uuid4().hex[:6]}@erp.com",
            "name": "Manager OP B",
            "role": "manager_o_p",
            "department": "Projects & Operations",
            "active": True,
            "password_hash": _hash_pw("OpB@12345"),
        }
        await db.users.insert_many([ua, ub])

        ha = {
            "id": f"h-mop-a-{uuid.uuid4().hex[:8]}",
            "handover_no": f"CHO-TEST-{uuid.uuid4().hex[:6]}",
            "project_name": "MOP-Test-Project-A",
            "client_name": "Client A",
            "contract_value": 1000000,
            "status": "allocated",
            "project_manager_id": ua["id"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        hb = {
            "id": f"h-mop-b-{uuid.uuid4().hex[:8]}",
            "handover_no": f"CHO-TEST-{uuid.uuid4().hex[:6]}",
            "project_name": "MOP-Test-Project-B",
            "client_name": "Client B",
            "contract_value": 2000000,
            "status": "allocated",
            "project_manager_id": ub["id"],
            "created_at": "2026-01-02T00:00:00+00:00",
        }
        await db.project_handovers.insert_many([ha, hb])

        pa = {
            "id": f"p-mop-a-{uuid.uuid4().hex[:8]}",
            "code": f"PRJ-MOP-A-{uuid.uuid4().hex[:4]}",
            "name": "MOP-Test-Project-A",
            "client": "Client A",
            "status": "active",
            "project_manager_id": ua["id"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        pb = {
            "id": f"p-mop-b-{uuid.uuid4().hex[:8]}",
            "code": f"PRJ-MOP-B-{uuid.uuid4().hex[:4]}",
            "name": "MOP-Test-Project-B",
            "client": "Client B",
            "status": "active",
            "project_manager_id": ub["id"],
            "created_at": "2026-01-02T00:00:00+00:00",
        }
        await db.projects.insert_many([pa, pb])

        return ua, ub, ha["id"], hb["id"], pa["id"], pb["id"]

    ua, ub, hid_a, hid_b, pid_a, pid_b = asyncio.get_event_loop().run_until_complete(_seed())
    yield (ua, ub, hid_a, hid_b, pid_a, pid_b)

    # Cleanup
    async def _cleanup():
        await db.users.delete_many({"id": {"$in": [ua["id"], ub["id"]]}})
        await db.project_handovers.delete_many({"id": {"$in": [hid_a, hid_b]}})
        await db.projects.delete_many({"id": {"$in": [pid_a, pid_b]}})
    asyncio.get_event_loop().run_until_complete(_cleanup())


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, r.text
    return s


# ─── Unit: pm_scope logic ────────────────────────────────────────────────
def test_pm_scope_helper_unit():
    import sys
    sys.path.insert(0, "/app/backend")
    from pm_scope import is_pm_scoped, pm_scope_clause

    # Canonical PM
    assert is_pm_scoped({"role": "project_manager"}) is True
    # New canonical role slug
    assert is_pm_scoped({"role": "manager_o_p"}) is True
    # Manager O P with spaces (normalises)
    assert is_pm_scoped({"role": "Manager O P"}) is True
    # Custom role with department fallback (label contains "engineer")
    assert is_pm_scoped({"role": "site_engineer_lead", "department": "Projects & Operations"}) is True
    # Privileged — bypasses
    assert is_pm_scoped({"role": "super_admin"}) is False
    assert is_pm_scoped({"role": "director"}) is False
    # Unrelated role
    assert is_pm_scoped({"role": "hr_executive"}) is False
    # Department but role label hints "executive" → not scoped
    assert is_pm_scoped({"role": "executive", "department": "Operations"}) is False

    clause = pm_scope_clause({"id": "u-1", "name": "X", "email": "x@y.z", "role": "manager_o_p"})
    assert "$or" in clause
    keys = {list(k.keys())[0] for k in clause["$or"]}
    assert "project_manager_id" in keys


# ─── E2E: Contract Handovers list scoping ────────────────────────────────
def test_admin_sees_both_handovers(seeded):
    _, _, hid_a, hid_b, _, _ = seeded
    s = _login(**ADMIN)
    r = s.get(f"{API_URL}/api/ops/handovers", timeout=10)
    assert r.status_code == 200
    ids = {h["id"] for h in r.json()}
    assert hid_a in ids and hid_b in ids


def test_manager_op_a_sees_only_their_handover(seeded):
    ua, _, hid_a, hid_b, _, _ = seeded
    s = _login(ua["email"], "OpA@12345")
    r = s.get(f"{API_URL}/api/ops/handovers", timeout=10)
    assert r.status_code == 200, r.text
    ids = {h["id"] for h in r.json()}
    assert hid_a in ids, "Manager OP A must see their own handover"
    assert hid_b not in ids, "Manager OP A must NOT see Manager OP B's handover"


def test_manager_op_a_cannot_open_other_handover_by_url(seeded):
    ua, _, _, hid_b, _, _ = seeded
    s = _login(ua["email"], "OpA@12345")
    r = s.get(f"{API_URL}/api/ops/handovers/{hid_b}", timeout=10)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"


def test_manager_op_a_can_open_own_handover(seeded):
    ua, _, hid_a, _, _, _ = seeded
    s = _login(ua["email"], "OpA@12345")
    r = s.get(f"{API_URL}/api/ops/handovers/{hid_a}", timeout=10)
    assert r.status_code == 200


# ─── E2E: Project list scoping ──────────────────────────────────────────
def test_manager_op_b_sees_only_their_project(seeded):
    _, ub, _, _, pid_a, pid_b = seeded
    s = _login(ub["email"], "OpB@12345")
    r = s.get(f"{API_URL}/api/project-dashboard/projects", timeout=10)
    assert r.status_code == 200, r.text
    ids = {p["id"] for p in r.json()}
    assert pid_b in ids
    assert pid_a not in ids


def test_manager_op_dashboard_kpis_scoped(seeded):
    ua, _, _, _, pid_a, pid_b = seeded
    s = _login(ua["email"], "OpA@12345")
    r = s.get(f"{API_URL}/api/proj-masters/dashboard-kpis", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    # Total reflects scoped count — must include pid_a but never pid_b
    total_ids = set(d["total_projects"]["ids"])
    assert pid_a in total_ids
    assert pid_b not in total_ids
