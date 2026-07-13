"""Iteration 49 — Real Payroll Module regression."""
import os
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def admin_client():
    c = httpx.Client(base_url=f"{API}/api", timeout=30.0)
    r = c.post("/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    yield c
    c.close()


@pytest.fixture(scope="module")
def employee_id(admin_client):
    r = admin_client.get("/employees")
    assert r.status_code == 200
    emps = r.json()
    assert len(emps) > 0
    return emps[0]["id"]


def _cleanup(employee_id):
    """Best-effort cleanup of test artefacts."""
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.employee_advances.delete_many({"id": "test-adv-pyr-1"})
        await db.advance_recoveries.delete_many({"advance_id": "test-adv-pyr-1"})
        await db.payslips.delete_many({"month": "2026-05", "employee_id": employee_id})
        await db.payroll_runs.delete_many({"month": "2026-05"})

    asyncio.run(_do())


def test_master_list_returns_200(admin_client):
    r = admin_client.get("/payroll/master")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_runs_list_returns_200(admin_client):
    r = admin_client.get("/payroll/runs")
    assert r.status_code == 200, r.text


def test_payslips_list_returns_200(admin_client):
    r = admin_client.get("/payroll/payslips")
    assert r.status_code == 200, r.text


def test_upsert_master_then_get(admin_client, employee_id):
    body = {
        "employee_id": employee_id, "basic": 25000, "hra": 10000,
        "special_allowance": 5000, "site_allowance": 3000, "conveyance": 1600, "medical": 1250,
        "pf_applicable": True, "esi_applicable": False, "pt_state": "GJ",
        "tds_override_pct": 0, "fixed_other_earnings": [], "fixed_other_deductions": [],
        "pan": "ABCDE1234F", "bank_name": "HDFC", "bank_account": "123456", "bank_ifsc": "HDFC0001",
    }
    r = admin_client.put(f"/payroll/master/{employee_id}", json=body)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["basic"] == 25000
    g = admin_client.get(f"/payroll/master/{employee_id}")
    assert g.status_code == 200 and g.json()["basic"] == 25000


def test_preview_computes_statutory(admin_client, employee_id):
    r = admin_client.post("/payroll/run/preview", json={
        "month": "2026-05", "skip_attendance_check": True, "employee_ids": [employee_id],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preflight_failed"] is False
    assert data["totals"]["count"] == 1
    s = data["payslips"][0]
    assert s["earnings"]["basic"] == 25000
    assert s["total_earnings"] == 45850
    assert s["statutory_deductions"]["pf"] == 1800   # 12% × 15k cap
    assert s["statutory_deductions"]["professional_tax"] == 200
    assert s["net_pay"] == 43850


def test_commit_with_advance_emi_auto_deduction(admin_client, employee_id):
    _cleanup(employee_id)
    # Seed an active advance directly
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.employee_advances.insert_one({
            "id": "test-adv-pyr-1", "advance_no": "HR/ADV/2026/9999",
            "dept_doc_no": "HR/ADV/2026/9999", "employee_id": employee_id,
            "approved_amount": 24000.0, "emi": 4000.0, "outstanding": 24000.0,
            "recovered_amount": 0.0, "remaining_installments": 6, "status": "paid",
            "repayment_start_month": "2026-04", "ownership_department": "hr",
        })
    asyncio.run(_seed())

    # Preview picks EMI
    pv = admin_client.post("/payroll/run/preview", json={
        "month": "2026-05", "skip_attendance_check": True, "employee_ids": [employee_id],
    }).json()
    slip = pv["payslips"][0]
    assert slip["advance_emi"] == 4000
    assert slip["net_pay"] == 39850  # 43850 - 4000

    # Commit
    r = admin_client.post("/payroll/run/commit", json={
        "month": "2026-05", "skip_attendance_check": True,
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["run"]["status"] == "committed"

    # Verify advance updated + recovery row + payslip persisted
    async def _verify():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        adv = await db.employee_advances.find_one({"id": "test-adv-pyr-1"})
        rec = await db.advance_recoveries.find_one({"advance_id": "test-adv-pyr-1", "month": "2026-05"})
        slip_doc = await db.payslips.find_one({"employee_id": employee_id, "month": "2026-05"})
        return adv, rec, slip_doc
    adv, rec, slip_doc = asyncio.run(_verify())
    assert adv["outstanding"] == 20000
    assert adv["recovered_amount"] == 4000
    assert adv["status"] == "under_recovery"
    assert adv["remaining_installments"] == 5
    assert rec is not None
    assert rec["amount"] == 4000
    assert slip_doc is not None
    assert slip_doc["dept_doc_no"].startswith("HR/SAL/2026/05")
    assert slip_doc["ownership_department"] == "hr"

    # Idempotency: re-commit same month returns 400
    r2 = admin_client.post("/payroll/run/commit", json={
        "month": "2026-05", "skip_attendance_check": True,
    })
    assert r2.status_code == 400
    assert "already committed" in r2.json()["detail"]

    _cleanup(employee_id)


def test_non_hr_role_blocked(admin_client):
    """super_admin (HR set member) is allowed, but unauthenticated is blocked."""
    bare = httpx.Client(base_url=f"{API}/api", timeout=10.0)
    r = bare.post("/payroll/run/preview", json={"month": "2026-05"})
    assert r.status_code == 401
    bare.close()
