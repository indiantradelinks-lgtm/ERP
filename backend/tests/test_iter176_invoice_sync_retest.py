"""Iter 176 — RETEST of the 4 sync gaps from iter 175 (RA bill ↔ client_invoices mirror)."""
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
    r = client.get(f"{API}/billing/invoices", params={"limit": 1000, **params}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _find(rows, invoice_no):
    return next((x for x in rows if x.get("invoice_no") == invoice_no), None)


@pytest.fixture(scope="module")
def project(client):
    r = client.get(f"{API}/projects", params={"limit": 100}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    p = next((x for x in rows if x.get("client_name") or x.get("client")), rows[0] if rows else None)
    if not p:
        pytest.skip("no projects available")
    return p


def _mk_bill(client, project, desc, qty=10, rate=1000, extra=None):
    payload = {
        "bill_type": "running", "bill_date": "2026-07-01",
        "client_id": project.get("client_id"),
        "client_name": project.get("client_name") or project.get("client") or "TEST_ITER176_CLIENT",
        "project_id": project.get("id"),
        "project_code": project.get("project_code") or project.get("code"),
        "items": [{"description": desc, "quantity": qty, "unit": "m2", "rate": rate}],
        "gst_pct": 18, "notes": "TEST_ITER176",
    }
    payload.update(extra or {})
    r = client.post(f"{API}/ra-bills", json=payload, timeout=60)
    assert r.status_code in (200, 201), f"create ra bill failed {r.status_code}: {r.text[:400]}"
    return r.json()


def _cleanup(client, bill_id):
    client.delete(f"{API}/ra-bills/{bill_id}", timeout=60)


# ── Regression: GET /api/billing/invoices ────────────────────────────────
def test_list_invoices_ok_with_mirrored_rows(client):
    rows = _invoices(client)
    assert isinstance(rows, list) and len(rows) > 0
    ra = [r for r in rows if r.get("source") == "ra_bill"]
    assert len(ra) >= 1, "no mirrored ra_bill invoices"
    for r in ra[:10]:
        assert r.get("invoice_no")
        assert "_id" not in r
        assert isinstance((r.get("totals") or {}).get("gross_value"), (int, float))
        assert r.get("status") in ("draft", "approved", "partially_paid", "paid", "cancelled")


# ── Gap 3: outstanding formula on mirrored invoices ─────────────────────
def test_no_paid_ra_bill_invoice_has_outstanding(client):
    rows = [r for r in _invoices(client) if r.get("source") == "ra_bill"]
    bad = [(r["invoice_no"], r.get("outstanding")) for r in rows
           if r.get("status") in ("paid", "cancelled") and float(r.get("outstanding") or 0) > 0.01]
    assert not bad, f"paid/cancelled mirrored invoices with outstanding > 0: {bad}"


def test_outstanding_matches_net_receivable_minus_paid(client):
    rows = [r for r in _invoices(client) if r.get("source") == "ra_bill"]
    mismatches = []
    for r in rows:
        net = float((r.get("totals") or {}).get("net_receivable") or r.get("net_receivable") or 0)
        paid = float(r.get("paid_amount") or 0)
        expected = 0.0 if r.get("status") in ("paid", "cancelled") else max(round(net - paid, 2), 0.0)
        if abs(float(r.get("outstanding") or 0) - expected) > 0.05:
            mismatches.append((r["invoice_no"], r.get("status"), r.get("outstanding"), expected))
    assert not mismatches, f"outstanding formula mismatch: {mismatches}"


# ── Gap 2: PUT /ra-bills/{id} re-syncs the mirror ────────────────────────
def test_edit_draft_bill_resyncs_mirror(client, project):
    b = _mk_bill(client, project, "TEST_ITER176 edit case", qty=5, rate=100)
    try:
        inv0 = _find(_invoices(client), b["bill_number"])
        assert inv0, "mirror not created on POST /ra-bills"
        assert inv0["status"] == "draft"

        r = client.put(f"{API}/ra-bills/{b['id']}", json={
            "items": [{"description": "TEST_ITER176 edit case", "quantity": 20, "unit": "m2", "rate": 100}]}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        up = r.json()
        inv = _find(_invoices(client), b["bill_number"])
        assert inv, "mirror missing after edit"
        assert inv["totals"]["gross_value"] == pytest.approx(float(up["gross_value"]), abs=0.05), \
            f"gross stale: {inv['totals']['gross_value']} vs {up['gross_value']}"
        assert inv["totals"]["taxable_value"] == pytest.approx(float(up["subtotal"]), abs=0.05), \
            f"taxable stale: {inv['totals']['taxable_value']} vs {up['subtotal']}"
        assert inv["outstanding"] == pytest.approx(float(up["net_payable"]), abs=0.05)
    finally:
        _cleanup(client, b["id"])


# ── Gap 1: POST /payments-in updates mirror (partial + full) ─────────────
def test_payment_in_partial_then_full_updates_mirror(client, project):
    b = _mk_bill(client, project, "TEST_ITER176 payment case", qty=10, rate=1000,
                 extra={"retention_pct": 5, "tds_pct": 2})
    bill_id, no = b["id"], b["bill_number"]
    try:
        assert client.post(f"{API}/ra-bills/{bill_id}/submit", timeout=60).status_code == 200
        assert client.post(f"{API}/ra-bills/{bill_id}/approve", timeout=60).status_code == 200
        cur = client.get(f"{API}/ra-bills/{bill_id}", timeout=60).json()
        net = float(cur["net_payable"])
        assert net > 0

        # Partial payment
        half = round(net / 2, 2)
        r = client.post(f"{API}/payments-in", json={
            "client_id": cur.get("client_id"), "client_name": cur.get("client_name") or "TEST_ITER176_CLIENT",
            "payment_date": "2026-07-02", "amount": half, "mode": "neft",
            "reference_no": "TEST_ITER176_P1",
            "allocations": [{"ra_bill_id": bill_id, "amount": half}]}, timeout=60)
        assert r.status_code in (200, 201), f"payments-in partial failed {r.status_code}: {r.text[:400]}"
        inv = _find(_invoices(client), no)
        assert inv, "mirror missing after partial payment"
        assert inv["status"] == "partially_paid", f"expected partially_paid, got {inv['status']}"
        assert float(inv["paid_amount"]) == pytest.approx(half, abs=0.05)
        assert float(inv["outstanding"]) == pytest.approx(round(net - half, 2), abs=0.05)

        # Remaining payment → paid
        rest = round(net - half, 2)
        r = client.post(f"{API}/payments-in", json={
            "client_id": cur.get("client_id"), "client_name": cur.get("client_name") or "TEST_ITER176_CLIENT",
            "payment_date": "2026-07-03", "amount": rest, "mode": "neft",
            "reference_no": "TEST_ITER176_P2",
            "allocations": [{"ra_bill_id": bill_id, "amount": rest}]}, timeout=60)
        assert r.status_code in (200, 201), f"payments-in full failed {r.status_code}: {r.text[:400]}"
        bill = client.get(f"{API}/ra-bills/{bill_id}", timeout=60).json()
        assert bill["status"] == "paid"
        inv = _find(_invoices(client), no)
        assert inv["status"] == "paid", f"mirror status not paid: {inv['status']}"
        assert float(inv["paid_amount"]) == pytest.approx(net, abs=0.05)
        assert float(inv["outstanding"]) == pytest.approx(0.0, abs=0.05), \
            f"paid mirror still has outstanding {inv['outstanding']}"
    finally:
        # paid bills cannot be deleted via API — best effort
        _cleanup(client, bill_id)


# ── Gap 4: POST /billing/receipts rejects source='ra_bill' invoices ──────
def test_receipt_against_ra_bill_invoice_rejected(client, project):
    b = _mk_bill(client, project, "TEST_ITER176 receipt guard", qty=2, rate=500)
    try:
        assert client.post(f"{API}/ra-bills/{b['id']}/submit", timeout=60).status_code == 200
        assert client.post(f"{API}/ra-bills/{b['id']}/approve", timeout=60).status_code == 200
        inv = _find(_invoices(client), b["bill_number"])
        assert inv and inv["status"] == "approved"
        r = client.post(f"{API}/billing/receipts", json={
            "client_id": inv.get("client_id") or "TEST", "client_name": inv.get("client_name") or "TEST_ITER176_CLIENT",
            "receipt_date": "2026-07-04", "amount": 100, "mode": "NEFT",
            "reference_no": "TEST_ITER176_R1",
            "invoice_ids": [inv["id"]]}, timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:400]}"
        detail = (r.json().get("detail") or "").lower()
        assert "ra bill" in detail and "payments in" in detail, f"unhelpful message: {detail}"
        # mirror untouched
        inv2 = _find(_invoices(client), b["bill_number"])
        assert float(inv2.get("paid_amount") or 0) == pytest.approx(0.0, abs=0.01)
        assert inv2["status"] == "approved"
    finally:
        _cleanup(client, b["id"])
