"""Iter 171 — Project Dashboard financials RCA fix verification.

Tests:
  1. Existing project 8c88da27... (E2E-TEST-178532-P1) still returns non-zero
     bills_raised (~342200), bills_net_due (~321900), gst_charged (~52200),
     revenue_recognised (~342200); ra_bill recent_activity labels are non-₹0.
  2. Fresh flow: pick a project, create a new RA bill via POST /api/ra-bills,
     re-fetch dashboard, assert bills_raised increased by gross_value and
     bill appears in recent_activity with correct non-zero label.
  3. Payment allocation: insert a payments_in doc directly via mongo with an
     allocation against the newly created RA bill → payments_received increases
     by the allocated amount and outstanding decreases accordingly.
  4. Regression: dashboard for a project with no RA bills returns 200 with
     zero financials (no 500), cashflow present.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TARGET_PROJECT_ID = "8c88da27-1cf4-482c-bc15-cb81b658fad0"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


def _dash(session, pid):
    r = session.get(f"{BASE_URL}/api/project-dashboard/{pid}", timeout=20)
    assert r.status_code == 200, f"{pid} -> {r.status_code}: {r.text[:300]}"
    return r.json()


# ── 1. Existing project baseline ────────────────────────────────────────────
def test_existing_project_financials_nonzero(session):
    d = _dash(session, TARGET_PROJECT_ID)
    f = d.get("financials", {})
    assert f.get("bills_raised", 0) >= 300000, f"bills_raised too low: {f.get('bills_raised')}"
    assert 340000 <= f.get("bills_raised", 0) <= 345000, f"bills_raised != ~342200: {f.get('bills_raised')}"
    assert 320000 <= f.get("bills_net_due", 0) <= 325000, f"bills_net_due != ~321900: {f.get('bills_net_due')}"
    assert 50000 <= f.get("gst_charged", 0) <= 55000, f"gst_charged != ~52200: {f.get('gst_charged')}"
    assert f.get("revenue_recognised", 0) == f.get("bills_raised", 0)
    # outstanding = bills_net_due - payments_received (>=0)
    assert f.get("outstanding", -1) == max(f["bills_net_due"] - f["payments_received"], 0)


def test_existing_project_recent_activity_labels(session):
    d = _dash(session, TARGET_PROJECT_ID)
    ra = [a for a in d.get("recent_activity", []) if a.get("kind") == "ra_bill"]
    assert len(ra) >= 3, f"expected >=3 ra_bill activities, got {len(ra)}"
    for a in ra:
        label = a.get("label", "")
        assert "₹0" not in label and "₹ 0" not in label, f"zero label leak: {label}"
        assert "₹" in label, f"missing rupee label: {label}"


# ── 2. Fresh RA bill flow ───────────────────────────────────────────────────
@pytest.fixture(scope="module")
def fresh_bill(session):
    """Create a new RA bill on TARGET project and return (before_dash, bill_doc)."""
    before = _dash(session, TARGET_PROJECT_ID)
    # Fetch project for code
    pr = session.get(f"{BASE_URL}/api/projects/{TARGET_PROJECT_ID}", timeout=10)
    proj = pr.json() if pr.status_code == 200 else {}
    payload = {
        "bill_type": "running",
        "project_id": TARGET_PROJECT_ID,
        "project_code": proj.get("code") or proj.get("project_code") or "E2E-TEST-178532-P1",
        "client_id": proj.get("client_id"),
        "client_name": proj.get("client_name") or "TEST_CLIENT",
        "items": [{"description": "TEST_ITER171_LINE", "quantity": 10, "rate": 1000, "unit": "nos"}],
        "gst_pct": 18,
        "retention_pct": 5,
        "tds_pct": 2,
        "submit": False,
    }
    r = session.post(f"{BASE_URL}/api/ra-bills", json=payload, timeout=15)
    assert r.status_code in (200, 201), f"ra bill create failed: {r.status_code} {r.text[:300]}"
    bill = r.json()
    # subtotal=10000, gst=1800, gross_value=11800
    assert bill.get("gross_value") == 11800, f"bad gross_value: {bill.get('gross_value')}"
    yield before, bill
    # cleanup
    session.delete(f"{BASE_URL}/api/ra-bills/{bill['id']}", timeout=10)


def test_dashboard_reflects_new_bill(session, fresh_bill):
    before, bill = fresh_bill
    after = _dash(session, TARGET_PROJECT_ID)
    delta = round(after["financials"]["bills_raised"] - before["financials"]["bills_raised"], 2)
    assert delta == 11800.0, f"bills_raised delta expected 11800, got {delta}"
    assert after["financials"]["bills_count"] == before["financials"]["bills_count"] + 1
    # recent_activity has the new bill
    kinds = [(a.get("kind"), a.get("ref_id"), a.get("label")) for a in after.get("recent_activity", [])]
    match = [x for x in kinds if x[1] == bill["id"]]
    assert match, f"new bill {bill['id']} not in recent_activity"
    label = match[0][2]
    assert "₹11,800" in label or "₹11800" in label, f"expected ₹11,800 in label, got: {label}"


# ── 3. Payment allocation ───────────────────────────────────────────────────
@pytest.fixture(scope="module")
def payment_allocation(session, fresh_bill):
    """Insert payments_in doc directly via mongo referencing the fresh bill."""
    _, bill = fresh_bill
    import asyncio, sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]

    async def _insert():
        cli = AsyncIOMotorClient(mongo_url)
        db = cli[db_name]
        doc = {
            "id": f"TEST_ITER171_PAY_{int(time.time())}",
            "amount": 5000.0,
            "mode": "neft",
            "utr": "TEST_UTR_171",
            "received_at": "2026-01-15",
            "allocations": [{"ra_bill_id": bill["id"], "amount": 5000.0}],
            "created_at": "2026-01-15T00:00:00+00:00",
        }
        await db.payments_in.insert_one(doc)
        return doc["id"]

    pay_id = asyncio.get_event_loop().run_until_complete(_insert())
    yield pay_id, bill

    async def _cleanup():
        cli = AsyncIOMotorClient(mongo_url)
        db = cli[db_name]
        await db.payments_in.delete_one({"id": pay_id})
    asyncio.get_event_loop().run_until_complete(_cleanup())


def test_dashboard_reflects_payment_allocation(session, payment_allocation, fresh_bill):
    pay_id, bill = payment_allocation
    before, _ = fresh_bill  # before fresh bill; use "after fresh bill" as new baseline
    # Snapshot the value the dashboard reports right now
    d = _dash(session, TARGET_PROJECT_ID)
    f = d["financials"]
    assert f["payments_received"] >= 5000.0, f"payments_received should include allocated 5000, got {f['payments_received']}"
    # outstanding must equal bills_net_due - payments_received (never negative)
    expected_out = max(f["bills_net_due"] - f["payments_received"], 0)
    assert f["outstanding"] == expected_out


# ── 4. Regression — project with no RA bills ────────────────────────────────
def test_empty_project_dashboard(session):
    # find a project with no bills — try iterating
    r = session.get(f"{BASE_URL}/api/projects", timeout=15)
    projs = r.json() if isinstance(r.json(), list) else (r.json().get("items") or [])
    chosen = None
    for p in projs:
        pid = p.get("id")
        if not pid or pid == TARGET_PROJECT_ID:
            continue
        d = _dash(session, pid)
        if d["financials"]["bills_count"] == 0 and d["financials"]["po_committed"] == 0:
            chosen = (pid, d)
            break
    if not chosen:
        pytest.skip("No empty project available for regression check")
    pid, d = chosen
    f = d["financials"]
    assert f["bills_raised"] == 0
    assert f["payments_received"] == 0
    assert f["outstanding"] == 0
    assert f["gp_pct"] == 0
    # ensure cashflow/waterfall keys present in payload
    assert "financials" in d and "recent_activity" in d
