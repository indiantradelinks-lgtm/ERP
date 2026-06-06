"""Phase A debt fix #1 — heterogeneous-UoM comparative in RFQ.

Verifies that:
  1. /respond accepts per-item rates via `item_rates` dict
  2. /comparative computes landed_value as Σ(per-item rate × per-item qty)
     using item_rates first and falling back to rate_quoted for missing items
  3. /comparative flags `heterogeneous_uom=True` and lists `units`
  4. /convert-to-po uses the same per-item-rate math for PO amount
  5. Default-rate-only legacy responses still work (backward compat)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TS = str(int(time.time()))


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def two_vendors(admin):
    r = admin.get(f"{API}/vendors", timeout=30)
    assert r.status_code == 200
    vs = r.json()
    assert len(vs) >= 2
    return [vs[0]["id"], vs[1]["id"]]


@pytest.fixture(scope="session")
def heterogeneous_rfq(admin, two_vendors):
    """Create a PR with 2 items of DIFFERENT UoMs, get it approved, raise an RFQ."""
    # Create PR
    pr_payload = {
        "department": "Operations",
        "priority": "high",
        "submit_for_approval": True,
        "items": [
            {"name": f"Steel Pipe HET-{TS}", "quantity": 100, "unit": "m"},        # metres
            {"name": f"Coupler HET-{TS}", "quantity": 500, "unit": "Nos"},          # pieces
        ],
    }
    r = admin.post(f"{API}/procurement/prs", json=pr_payload, timeout=30)
    assert r.status_code == 200, r.text
    pr = r.json()

    # Approve the PR via the approvals chain (super_admin bypasses each step)
    apv = admin.get(f"{API}/approvals", params={"record_id": pr["id"]}, timeout=30).json()
    if isinstance(apv, list) and apv:
        ap = apv[0]
        for _ in range(len(ap.get("chain") or [])):
            ar = admin.post(f"{API}/approvals/{ap['id']}/action", json={"action": "approve", "comment": "ok"}, timeout=30)
            assert ar.status_code in (200, 400), ar.text
            if ar.status_code == 400:
                break
    # Re-fetch PR
    pr = admin.get(f"{API}/procurement/prs/{pr['id']}", timeout=30).json()
    assert pr.get("status") == "approved", f"PR not approved: {pr.get('status')}"

    # Create RFQ
    rfq_payload = {"pr_id": pr["id"], "vendors": [{"vendor_id": vid} for vid in two_vendors]}
    r = admin.post(f"{API}/procurement/rfqs", json=rfq_payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_respond_with_item_rates(admin, heterogeneous_rfq, two_vendors):
    rfq_id = heterogeneous_rfq["id"]
    # Vendor 0: per-item rates (100/m for steel pipe, 20/Nos for coupler)
    r = admin.post(f"{API}/procurement/rfqs/{rfq_id}/respond", json={
        "vendor_id": two_vendors[0],
        "item_rates": {"0": 100, "1": 20},
        "delivery_days": 7,
    }, timeout=30)
    assert r.status_code == 200, r.text

    # Vendor 1: legacy single rate_quoted (50 applied to BOTH items — heterogeneous bug repro)
    r = admin.post(f"{API}/procurement/rfqs/{rfq_id}/respond", json={
        "vendor_id": two_vendors[1],
        "rate_quoted": 50,
        "delivery_days": 5,
    }, timeout=30)
    assert r.status_code == 200, r.text


def test_comparative_returns_per_item_breakdown(admin, heterogeneous_rfq, two_vendors):
    rfq_id = heterogeneous_rfq["id"]
    r = admin.get(f"{API}/procurement/rfqs/{rfq_id}/comparative", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heterogeneous_uom"] is True, "must flag heterogeneous UoM"
    assert sorted(data["units"]) == ["Nos", "m"]
    rows_by_vendor = {row["vendor_id"]: row for row in data["rows"]}

    # Vendor 0: item_rates → landed = 100*100 + 20*500 = 20000
    v0 = rows_by_vendor[two_vendors[0]]
    assert v0["landed_value"] == 20000, f"v0 landed mismatch: {v0['landed_value']}"
    assert len(v0["item_breakdown"]) == 2
    assert v0["item_breakdown"][0]["source"] == "item_rate"
    assert v0["item_breakdown"][1]["source"] == "item_rate"

    # Vendor 1: fallback rate 50 → landed = 50*100 + 50*500 = 30000
    v1 = rows_by_vendor[two_vendors[1]]
    assert v1["landed_value"] == 30000, f"v1 landed mismatch: {v1['landed_value']}"
    assert v1["item_breakdown"][0]["source"] == "fallback_rate"
    assert v1["item_breakdown"][1]["source"] == "fallback_rate"

    # Vendor 0 should rank ahead (lower landed value)
    assert data["rows"][0]["vendor_id"] == two_vendors[0]


def test_convert_to_po_uses_per_item_rates(admin, heterogeneous_rfq, two_vendors):
    rfq_id = heterogeneous_rfq["id"]
    # Select vendor 0 (the per-item-rate winner)
    r = admin.post(f"{API}/procurement/rfqs/{rfq_id}/select-vendor", json={"vendor_id": two_vendors[0]}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("selected_vendor_id") == two_vendors[0]

    # Convert to PO
    r = admin.post(f"{API}/procurement/rfqs/{rfq_id}/convert-to-po", timeout=30)
    assert r.status_code == 200, r.text
    po = r.json()
    # 100*100 + 20*500 = 20000
    assert po["amount"] == 20000, f"PO amount mismatch: {po['amount']}"
    # PO items must have per-line rates and line_value
    assert po["items"][0]["rate"] == 100 and po["items"][0]["line_value"] == 10000
    assert po["items"][1]["rate"] == 20 and po["items"][1]["line_value"] == 10000
    assert po.get("item_rates") == {"0": 100, "1": 20}


def test_respond_rejects_both_empty(admin, heterogeneous_rfq, two_vendors):
    """Backward-compat: providing neither rate_quoted nor item_rates must 400."""
    # New RFQ for clean state
    pr_payload = {
        "priority": "medium", "submit_for_approval": True,
        "items": [{"name": f"Sanity {TS}", "quantity": 1, "unit": "Nos"}],
    }
    pr = admin.post(f"{API}/procurement/prs", json=pr_payload, timeout=30).json()
    apv = admin.get(f"{API}/approvals", params={"record_id": pr["id"]}, timeout=30).json()
    if isinstance(apv, list) and apv:
        ap = apv[0]
        for _ in range(len(ap.get("chain") or [])):
            ar = admin.post(f"{API}/approvals/{ap['id']}/action", json={"action": "approve"}, timeout=30)
            if ar.status_code == 400:
                break
    rfq = admin.post(f"{API}/procurement/rfqs", json={"pr_id": pr["id"], "vendors": [{"vendor_id": two_vendors[0]}]}, timeout=30).json()
    r = admin.post(f"{API}/procurement/rfqs/{rfq['id']}/respond", json={"vendor_id": two_vendors[0]}, timeout=30)
    assert r.status_code == 400
    assert "rate_quoted" in r.text or "item_rates" in r.text
