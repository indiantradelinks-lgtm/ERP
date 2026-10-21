"""Iteration 206 — Project Category (AMC/ARC vs scope) drives the billing workflow.

1. Bill Request auto-fetches the category from Project Master: AMC/ARC projects
   bill month-wise (billing month mandatory, period auto-filled, one request per
   month); every other category bills against the project scope / timeline.
2. Pending Billing Report carries project category, billing month/period, pending
   status and pending amount, with month-wise + project-wise pending totals and
   filters for month, project, category and status.
3. Excel / CSV / PDF downloads.
4. Reminder per project to the responsible PM with Accounts + GM/Director in CC.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}

AMC_MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04"]
MONTHLY_AMOUNT = 120000


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return s


def _mk_project(session, suffix, **extra):
    code = f"TEST-ITER206-{suffix}-{uuid.uuid4().hex[:4].upper()}"
    body = {"code": code, "name": f"Iter206 {suffix} project", "client": "Iter206 Client",
            "status": "active", "start_date": "2026-01-01", "end_date": "2026-04-30", **extra}
    r = session.post(f"{API}/projects", json=body, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return r.json()


@pytest.fixture(scope="module")
def projects(session):
    amc = _mk_project(session, "AMC", category="amc_arc",
                      monthly_billing_amount=MONTHLY_AMOUNT, contract_value=MONTHLY_AMOUNT * 4)
    short = _mk_project(session, "SHORT", category="short_term", contract_value=500000)
    yield {"amc": amc, "short": short}
    # No delete API for bill requests — clear the test rows straight from Mongo.
    try:
        from pymongo import MongoClient
        from dotenv import dotenv_values
        env = dotenv_values("/app/backend/.env")
        db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
        codes = [amc["code"], short["code"]]
        brs = list(db.bill_requests.find({"project_code": {"$in": codes}}, {"_id": 0, "id": 1, "approval_id": 1}))
        db.bill_requests.delete_many({"project_code": {"$in": codes}})
        db.approvals.delete_many({"id": {"$in": [b.get("approval_id") for b in brs if b.get("approval_id")]}})
        db.billing_reminders.delete_many({"project_code": {"$in": codes}})
    except Exception as e:  # noqa: BLE001 — cleanup must not fail the run
        print(f"cleanup skipped: {e}")
    for p in (amc, short):
        session.delete(f"{API}/projects/{p['id']}", timeout=20)


# ───────────────── category auto-fetch into the Bill Request ─────────────────
def test_context_exposes_category_and_month_ledger(session, projects):
    r = session.get(f"{API}/ra-bills/project-context/{projects['amc']['code']}", timeout=30)
    assert r.status_code == 200, r.text[:200]
    ctx = r.json()
    assert ctx["project_category"] == "amc_arc"
    assert ctx["category_label"] == "AMC / ARC"
    assert ctx["billing_mode"] == "monthly"
    assert ctx["monthly_amount"] == MONTHLY_AMOUNT
    assert [m["month"] for m in ctx["month_ledger"]] == AMC_MONTHS
    assert ctx["next_billing_month"] == AMC_MONTHS[0]

    s = session.get(f"{API}/ra-bills/project-context/{projects['short']['code']}", timeout=30).json()
    assert s["project_category"] == "short_term"
    assert s["billing_mode"] == "scope"
    assert s["month_ledger"] == []


def test_amc_request_needs_a_valid_billing_month(session, projects):
    code = projects["amc"]["code"]
    items = [{"description": "AMC monthly service", "quantity": 1, "unit": "month", "rate": MONTHLY_AMOUNT}]

    missing = session.post(f"{API}/bill-requests", json={"project_code": code, "items": items}, timeout=30)
    assert missing.status_code == 400
    assert "Billing Month" in missing.text

    outside = session.post(f"{API}/bill-requests",
                           json={"project_code": code, "billing_month": "2027-05", "items": items}, timeout=30)
    assert outside.status_code == 400
    assert "outside the project validity" in outside.text


def test_amc_request_autofills_period_and_blocks_a_second_one(session, projects):
    code = projects["amc"]["code"]
    items = [{"description": "AMC monthly service", "quantity": 1, "unit": "month", "rate": MONTHLY_AMOUNT}]

    first = session.post(f"{API}/bill-requests",
                         json={"project_code": code, "billing_month": "2026-01", "items": items}, timeout=30)
    assert first.status_code == 200, first.text[:300]
    doc = first.json()
    assert doc["billing_month"] == "2026-01"
    assert doc["period_from"] == "2026-01-01" and doc["period_to"] == "2026-01-31"
    assert doc["project_category"] == "amc_arc" and doc["billing_mode"] == "monthly"
    assert doc["project_category_label"] == "AMC / ARC"

    repeat = session.post(f"{API}/bill-requests",
                          json={"project_code": code, "billing_month": "2026-01",
                                "remarks": "second attempt", "items": items}, timeout=30)
    assert repeat.status_code == 409, repeat.text[:200]
    body = repeat.json()
    assert body["duplicate"] is True and body["existing_no"] == doc["request_no"]

    # The month ledger now shows January as taken.
    ctx = session.get(f"{API}/ra-bills/project-context/{code}", timeout=30).json()
    jan = next(m for m in ctx["month_ledger"] if m["month"] == "2026-01")
    assert jan["taken"] is True and jan["request_no"] == doc["request_no"]
    assert ctx["next_billing_month"] == "2026-02"


def test_scope_project_bills_against_the_timeline(session, projects):
    code = projects["short"]["code"]
    r = session.post(f"{API}/bill-requests", json={
        "project_code": code, "period_from": "2026-01-05", "period_to": "2026-03-20",
        "items": [{"description": "Scope milestone 1", "quantity": 1, "unit": "lot", "rate": 200000}],
    }, timeout=30)
    assert r.status_code == 200, r.text[:300]
    doc = r.json()
    assert doc["billing_mode"] == "scope"
    assert doc["billing_month"] is None
    assert doc["period_from"] == "2026-01-05" and doc["period_to"] == "2026-03-20"


# ───────────────── pending billing report ─────────────────
def test_report_shows_category_months_and_pending_amount(session, projects):
    code = projects["amc"]["code"]
    r = session.get(f"{API}/billing/pending-report?month=2026-04&category=amc_arc&project_code={code}", timeout=40)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert [row["project_code"] for row in data["rows"]] == [code]
    row = data["rows"][0]
    assert row["category_label"] == "AMC / ARC"
    assert row["billing_mode"] == "monthly"
    assert row["expected_monthly"] == MONTHLY_AMOUNT
    # January is already requested, so the remaining three months are pending.
    assert row["pending_months"] == AMC_MONTHS[1:]
    assert row["pending_amount"] == MONTHLY_AMOUNT * 3
    assert data["summary"]["pending_amount"] == MONTHLY_AMOUNT * 3
    assert data["summary"]["pending_months_total"] == 3
    months = {m["month"]: m["pending_amount"] for m in data["month_wise"]}
    assert months == {m: MONTHLY_AMOUNT for m in AMC_MONTHS[1:]}
    assert any(c["value"] == "amc_arc" for c in data["categories"])


def test_report_category_filter_separates_scope_projects(session, projects):
    r = session.get(f"{API}/billing/pending-report?month=2026-04&category=short_term", timeout=40)
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert all(row["project_category"] == "short_term" for row in rows)
    mine = next((row for row in rows if row["project_code"] == projects["short"]["code"]), None)
    assert mine, "short-term project missing from its own category filter"
    assert mine["billing_mode"] == "scope"
    assert "→" in (mine["billing_period"] or "")


@pytest.mark.parametrize("fmt,ctype", [("csv", "text/csv"), ("xlsx", "spreadsheet"), ("pdf", "application/pdf")])
def test_report_downloads(session, fmt, ctype):
    r = session.get(f"{API}/billing/pending-report/export?fmt={fmt}&month=2026-04", timeout=60)
    assert r.status_code == 200, r.text[:200]
    assert ctype in r.headers.get("content-type", "")
    assert len(r.content) > 200
    if fmt == "csv":
        text = r.content.decode("utf-8")
        assert "Project Category" in text and "Billing Month / Period" in text
        assert "Month-wise pending billing" in text


# ───────────────── reminder to the responsible user ─────────────────
def test_reminder_goes_out_per_project_with_cc(session, projects):
    r = session.post(f"{API}/billing/pending-report/send-reminder?month=2026-04", timeout=90)
    assert r.status_code == 200, r.text[:200]
    per = r.json()["per_project"]
    assert per["projects"] >= 1 and per["sent"] >= 1

    log = session.get(f"{API}/billing/pending-report/reminder-log?month=2026-04", timeout=30)
    assert log.status_code == 200
    rows = {row["project_code"]: row for row in log.json()["rows"]}
    mine = rows.get(projects["amc"]["code"])
    assert mine, "no reminder journalled for the AMC project"
    assert mine["category"] == "amc_arc"
    assert mine["pending_amount"] == MONTHLY_AMOUNT * 3
    assert mine["pending_months"] == AMC_MONTHS[1:]
    assert mine["to"] and mine["cc"]
    assert mine["sent_count"] >= 1
