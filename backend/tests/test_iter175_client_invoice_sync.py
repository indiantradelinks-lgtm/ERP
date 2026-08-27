"""Iter 175 — RA bill → client_invoices mirror sync (bug: Client Invoices page not updating)."""
import os
import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _invoices(client, **params):
    r = client.get(f"{API}/billing/invoices", params={"limit": 500, **params}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _find(rows, invoice_no):
    return next((x for x in rows if x.get("invoice_no") == invoice_no), None)


# ── Module: billing_router GET /billing/invoices ─────────────────────────
def test_list_invoices_ok_and_has_ra_bill_rows(client):
    rows = _invoices(client)
    assert isinstance(rows, list) and len(rows) > 0
    ra = [r for r in rows if r.get("source") == "ra_bill"]
    assert len(ra) >= 1, "no mirrored ra_bill invoices found (backfill missing)"
    for r in ra[:5]:
        assert r.get("invoice_no")
        assert r.get("client_name") is not None
        assert isinstance((r.get("totals") or {}).get("gross_value"), (int, float))
        assert r.get("status") in ("draft", "approved", "partially_paid", "paid", "cancelled")
        assert "_id" not in r


# ── Module: ra_bills_router lifecycle → mirror ───────────────────────────
@pytest.fixture(scope="module")
def project(client):
    r = client.get(f"{API}/projects", params={"limit": 100}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    p = next((x for x in rows if x.get("client_name") or x.get("client")), rows[0] if rows else None)
    if not p:
        pytest.skip("no projects available")
    return p


@pytest.fixture(scope="module")
def bill(client, project):
    payload = {
        "bill_type": "running",
        "bill_date": "2026-07-01",
        "client_id": project.get("client_id"),
        "client_name": project.get("client_name") or project.get("client") or "TEST_CLIENT_ITER175",
        "project_id": project.get("id"),
        "project_code": project.get("project_code") or project.get("code"),
        "items": [{"description": "TEST_ITER175 scaffolding work", "quantity": 10, "unit": "m2", "rate": 1000}],
        "gst_pct": 18,
        "notes": "TEST_ITER175",
    }
    r = client.post(f"{API}/ra-bills", json=payload, timeout=60)
    assert r.status_code in (200, 201), f"create ra bill failed {r.status_code}: {r.text[:400]}"
    b = r.json()
    yield b
    client.delete(f"{API}/ra-bills/{b['id']}", timeout=60)


def test_create_ra_bill_mirrors_invoice(client, bill):
    inv = _find(_invoices(client), bill["bill_number"])
    assert inv, f"no mirrored client invoice for {bill['bill_number']}"
    assert inv["source"] == "ra_bill" and inv["source_bill_id"] == bill["id"]
    assert inv["status"] == "draft"
    assert inv["totals"]["gross_value"] == pytest.approx(bill["gross_value"])
    assert inv["totals"]["taxable_value"] == pytest.approx(bill["subtotal"])
    assert inv["outstanding"] == pytest.approx(bill["gross_value"])
    assert inv["invoice_type"] == "RA"


def test_submit_then_approve_updates_mirror_status(client, bill):
    r = client.post(f"{API}/ra-bills/{bill['id']}/submit", timeout=60)
    assert r.status_code == 200, r.text[:300]
    inv = _find(_invoices(client), bill["bill_number"])
    assert inv["status"] == "approved", f"after submit mirror status={inv['status']}"

    r = client.post(f"{API}/ra-bills/{bill['id']}/approve", timeout=60)
    assert r.status_code == 200, r.text[:300]
    inv = _find(_invoices(client), bill["bill_number"])
    assert inv["status"] == "approved"


def test_issue_invoice_updates_mirror(client, bill):
    r = client.post(f"{API}/ra-bills/{bill['id']}/issue-invoice", json={"due_days": 30}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    inv = _find(_invoices(client), bill["bill_number"])
    assert inv and inv["status"] == "approved"


def test_payment_in_updates_mirror_to_paid(client, bill):
    net = float(bill["net_payable"])
    r = client.post(f"{API}/payments-in", json={
        "client_id": bill.get("client_id"), "client_name": bill.get("client_name") or "TEST_CLIENT_ITER175",
        "payment_date": "2026-07-02", "amount": net, "mode": "neft",
        "reference_no": "TEST_ITER175",
        "allocations": [{"ra_bill_id": bill["id"], "amount": net}],
    }, timeout=60)
    assert r.status_code in (200, 201), f"payments-in failed {r.status_code}: {r.text[:400]}"
    b = client.get(f"{API}/ra-bills/{bill['id']}", timeout=60).json()
    assert b["status"] == "paid" and float(b["paid_amount"]) == pytest.approx(net)
    inv = _find(_invoices(client), bill["bill_number"])
    assert inv, "mirror missing"
    assert inv["status"] in ("paid", "partially_paid"), f"mirror status not updated after payment: {inv['status']}"
    assert float(inv["paid_amount"]) == pytest.approx(net), f"mirror paid_amount stale: {inv['paid_amount']}"
    assert float(inv["outstanding"]) == pytest.approx(round(float(b["gross_value"]) - net, 2))


def test_edit_ra_bill_amount_updates_mirror(client, project):
    payload = {
        "bill_type": "running", "bill_date": "2026-07-01",
        "client_id": project.get("client_id"),
        "client_name": project.get("client_name") or project.get("client") or "TEST_CLIENT_ITER175",
        "project_id": project.get("id"),
        "project_code": project.get("project_code") or project.get("code"),
        "items": [{"description": "TEST_ITER175 edit case", "quantity": 5, "unit": "m2", "rate": 100}],
        "gst_pct": 18, "notes": "TEST_ITER175",
    }
    b = client.post(f"{API}/ra-bills", json=payload, timeout=60).json()
    try:
        r = client.put(f"{API}/ra-bills/{b['id']}", json={
            "items": [{"description": "TEST_ITER175 edit case", "quantity": 20, "unit": "m2", "rate": 100}]}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        updated = r.json()
        inv = _find(_invoices(client), b["bill_number"])
        assert inv, "mirror missing after edit"
        assert inv["totals"]["gross_value"] == pytest.approx(updated["gross_value"]), \
            f"mirror gross stale after edit: {inv['totals']['gross_value']} vs {updated['gross_value']}"
    finally:
        client.delete(f"{API}/ra-bills/{b['id']}", timeout=60)


def test_delete_draft_ra_bill_removes_mirror(client, project):
    payload = {
        "bill_type": "running", "bill_date": "2026-07-01",
        "client_id": project.get("client_id"),
        "client_name": project.get("client_name") or project.get("client") or "TEST_CLIENT_ITER175",
        "project_id": project.get("id"),
        "project_code": project.get("project_code") or project.get("code"),
        "items": [{"description": "TEST_ITER175 delete case", "quantity": 1, "unit": "m2", "rate": 500}],
        "gst_pct": 18, "notes": "TEST_ITER175",
    }
    b = client.post(f"{API}/ra-bills", json=payload, timeout=60).json()
    assert _find(_invoices(client), b["bill_number"]), "mirror not created"
    r = client.delete(f"{API}/ra-bills/{b['id']}", timeout=60)
    assert r.status_code in (200, 204), r.text[:300]
    assert _find(_invoices(client), b["bill_number"]) is None, "mirror not deleted"
