"""Iteration 205 — ERP-wide duplicate request prevention.

Layer 1 (submission idempotency, every module):
  1. The same POST sent twice in a row creates ONE record; the repeat replays the
     original response (X-Duplicate-Submission: replayed).
  2. Two identical POSTs fired in parallel (double click) create ONE record.

Layer 2 (business-key guards, hard block + clear warning):
  3. Enquiry — same client + same scope within 30 days is refused with the
     existing enquiry number; a different scope still goes through.
  4. Quotation — a second fresh quotation on an enquiry that already has one is
     refused and points at the existing quote number.
  5. Payment Request — same project + payee + amount + type that is still
     open/unpaid is refused with the existing request number.

Layer 3 (audit): every block lands in /api/admin/duplicates/blocks.
"""
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def created(session):
    """Records created by the tests — removed at the end."""
    bucket = {"advance_types": [], "enquiries": []}
    yield bucket
    for code in bucket["advance_types"]:
        rows = session.get(f"{API}/advance-types", timeout=20).json()
        rows = rows if isinstance(rows, list) else rows.get("rows", [])
        for row in [r for r in rows if r.get("code") == code]:
            session.delete(f"{API}/advance-types/{row['id']}", timeout=20)
    for enq_id in bucket["enquiries"]:
        session.delete(f"{API}/enquiries/{enq_id}", timeout=20)


@pytest.fixture(scope="module")
def site(session):
    r = session.get(f"{API}/sites?page=1&page_size=20", timeout=20)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    rows = data if isinstance(data, list) else data.get("rows", [])
    pick = next((s for s in rows if s.get("client_id")), None)
    if not pick:
        pytest.skip("no client site in master")
    return pick


# ───────────────────────── layer 1: submission idempotency ─────────────────────────
def test_repeat_post_replays_instead_of_duplicating(session, created):
    code = f"DUP{uuid.uuid4().hex[:6].upper()}"
    body = {"code": code, "name": f"Dedupe {code}", "max_amount": 1000, "max_installments": 2}
    created["advance_types"].append(code)

    first = session.post(f"{API}/advance-types", json=body, timeout=30)
    assert first.status_code == 200, first.text[:200]
    second = session.post(f"{API}/advance-types", json=body, timeout=30)
    assert second.status_code == 200, second.text[:200]
    assert second.headers.get("X-Duplicate-Submission") == "replayed"
    assert second.headers.get("X-Duplicate-Record") == code  # drives the UI warning
    assert second.json().get("id") == first.json().get("id")

    rows = session.get(f"{API}/advance-types", timeout=20).json()
    rows = rows if isinstance(rows, list) else rows.get("rows", [])
    assert len([r for r in rows if r.get("code") == code]) == 1, "repeat click created a second record"


def test_parallel_double_click_creates_one_record(session, created):
    code = f"DUP{uuid.uuid4().hex[:6].upper()}"
    body = {"code": code, "name": f"Parallel {code}", "max_amount": 500, "max_installments": 1}
    created["advance_types"].append(code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: session.post(f"{API}/advance-types", json=body, timeout=40), range(2)))
    assert all(r.status_code in (200, 409) for r in results), [r.status_code for r in results]

    rows = session.get(f"{API}/advance-types", timeout=20).json()
    rows = rows if isinstance(rows, list) else rows.get("rows", [])
    assert len([r for r in rows if r.get("code") == code]) == 1, "double click created two records"


# ───────────────────────── layer 2: business keys ─────────────────────────
def test_duplicate_enquiry_is_blocked_with_existing_number(session, site, created):
    scope = f"Dedupe scope {uuid.uuid4().hex[:8]} — scaffolding erection at unit 4"
    payload = {"site_id": site["id"], "service_type": "services", "scope_of_work": scope, "expected_value": 50000}

    first = session.post(f"{API}/enquiries", json=payload, timeout=40)
    assert first.status_code == 200, first.text[:300]
    enq = first.json()
    created["enquiries"].append(enq["id"])

    repeat = session.post(f"{API}/enquiries", json={**payload, "notes": "resubmitted"}, timeout=40)
    assert repeat.status_code == 409, f"expected a duplicate block, got {repeat.status_code}: {repeat.text[:200]}"
    data = repeat.json()
    assert data.get("duplicate") is True
    assert data["existing_no"] == enq["enquiry_no"]
    assert enq["enquiry_no"] in data["detail"]

    # Control — a genuinely different scope for the same client is still accepted.
    other = session.post(f"{API}/enquiries",
                         json={**payload, "scope_of_work": f"Different work {uuid.uuid4().hex[:8]} — painting"},
                         timeout=40)
    assert other.status_code == 200, other.text[:300]
    created["enquiries"].append(other.json()["id"])


def test_second_quotation_on_same_enquiry_is_blocked(session, site, created):
    scope = f"Quote guard {uuid.uuid4().hex[:8]} — insulation at unit 7"
    first = session.post(f"{API}/enquiries",
                         json={"site_id": site["id"], "service_type": "services", "scope_of_work": scope},
                         timeout=40)
    assert first.status_code == 200, first.text[:300]
    enq = first.json()
    created["enquiries"].append(enq["id"])
    assert enq.get("quotation_no"), "enquiry should auto-create its draft quotation"

    blocked = session.post(f"{API}/quotation-builder",
                           json={"enquiry_id": enq["id"], "client": enq.get("customer"), "project": scope},
                           timeout=40)
    assert blocked.status_code == 409, f"expected 409, got {blocked.status_code}: {blocked.text[:200]}"
    assert blocked.json()["existing_no"] == enq["quotation_no"]


def test_duplicate_payment_request_is_blocked(session):
    """Re-raising a payment request that is already open/unpaid is refused."""
    r = session.get(f"{API}/project-requests?page=1&page_size=50", timeout=30)
    assert r.status_code == 200, r.text[:200]
    rows = r.json().get("rows", [])
    live = next((x for x in rows
                 if x.get("is_payment") and x.get("project_id") and x.get("cost_center_id")
                 and x.get("vendor") and x.get("request_type") == "fuel"
                 and x.get("status") not in ("rejected", "cancelled", "closed", "fulfilled", "paid")), None)
    if not live:
        pytest.skip("no live fuel payment request to duplicate")

    attempt = session.post(f"{API}/project-requests", json={
        "request_type": live["request_type"], "project_id": live["project_id"],
        "cost_center_id": live["cost_center_id"], "vendor": live["vendor"],
        "amount": live.get("est_value") or live.get("amount"),
        "description": f"duplicate guard check {uuid.uuid4().hex[:6]}", "priority": "medium",
    }, timeout=40)
    assert attempt.status_code == 409, f"expected 409, got {attempt.status_code}: {attempt.text[:200]}"
    data = attempt.json()
    assert data.get("duplicate") is True
    assert data.get("existing_no")


# ───────────────────────── layer 3: admin audit ─────────────────────────
def test_blocked_attempts_are_journalled_for_admin(session):
    time.sleep(1)
    r = session.get(f"{API}/admin/duplicates/blocks?page=1&page_size=50", timeout=30)
    assert r.status_code == 200, r.text[:200]
    rows = r.json().get("rows", [])
    assert rows, "no blocked duplicate attempts journalled"
    kinds = {row.get("kind") for row in rows}
    assert "business_key" in kinds
    sample = next(row for row in rows if row["kind"] == "business_key")
    for field in ("module", "message", "user_name", "at"):
        assert sample.get(field), f"block row missing {field}"

    s = session.get(f"{API}/admin/duplicates/blocks/summary", timeout=30)
    assert s.status_code == 200, s.text[:200]
    assert s.json()["total"] >= len(rows)


def test_admin_filters_narrow_the_list(session):
    only_business = session.get(f"{API}/admin/duplicates/blocks?page=1&page_size=50&kind=business_key", timeout=30)
    assert only_business.status_code == 200, only_business.text[:200]
    assert {r["kind"] for r in only_business.json()["rows"]} <= {"business_key"}

    by_module = session.get(f"{API}/admin/duplicates/blocks?page=1&page_size=50&module=enquir", timeout=30)
    assert by_module.status_code == 200, by_module.text[:200]
    assert all("enquir" in (r.get("module") or "").lower() for r in by_module.json()["rows"])
