"""Iter 107 — Procurement & Vendors Gap-Fill (Rate Contracts, Service Orders/SRN, QI, Doc Expiry, Notifications, 5-tier).

Backend: /api/procurement-extras/*
"""
import os
import time
import pytest
import requests

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return sess


@pytest.fixture(scope="module")
def vendor(s):
    """Get any approved vendor, or create one."""
    vendors = s.get(f"{API_URL}/api/vendors", timeout=10).json()
    approved = [v for v in vendors if v.get("status") == "approved"]
    if approved:
        return approved[0]
    # create a vendor
    payload = {"name": f"Test Vendor IT107 {int(time.time())}", "gst": f"29AAA{int(time.time())%100000}A1Z5"}
    r = s.post(f"{API_URL}/api/vendors", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    v = r.json()
    # approve by direct status set
    s.post(f"{API_URL}/api/vendors/{v['id']}/status",
           json={"status": "approved"}, timeout=10)
    return v


# ─── Vendor Type ───────────────────────────────────────────────────────────
def test_list_vendor_types(s):
    r = s.get(f"{API_URL}/api/procurement-extras/vendor-types", timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    codes = {row["code"] for row in data}
    for vt in ("material_supplier", "labour_contractor", "transporter", "service_provider"):
        assert vt in codes


def test_set_vendor_type(s, vendor):
    r = s.patch(f"{API_URL}/api/procurement-extras/vendors/{vendor['id']}/type",
                json={"vendor_type": "material_supplier"}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["vendor_type"] == "material_supplier"


def test_invalid_vendor_type_rejected(s, vendor):
    r = s.patch(f"{API_URL}/api/procurement-extras/vendors/{vendor['id']}/type",
                json={"vendor_type": "rocket_ship"}, timeout=10)
    assert r.status_code == 400


# ─── Rate Contracts ────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def rate_contract(s, vendor):
    payload = {
        "vendor_id": vendor["id"],
        "start_date": "2026-01-01",
        "end_date": "2027-01-01",
        "payment_terms": "30 days",
        "lines": [
            {"item_name": "Pipe MS 50mm", "unit": "mt", "rate": 450.0, "gst_percent": 18.0},
            {"item_name": "Coupler", "unit": "Nos", "rate": 95.0, "gst_percent": 18.0},
        ],
    }
    r = s.post(f"{API_URL}/api/procurement-extras/rate-contracts", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def test_rate_contract_created_with_number(rate_contract):
    assert rate_contract["rc_number"].startswith("RC-")
    assert rate_contract["status"] == "draft"
    assert len(rate_contract["lines"]) == 2


def test_rate_contract_activate(s, rate_contract):
    r = s.post(f"{API_URL}/api/procurement-extras/rate-contracts/{rate_contract['id']}/activate", timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


def test_rate_contract_suggest_for_item(s, rate_contract):
    r = s.get(f"{API_URL}/api/procurement-extras/rate-contracts/suggest",
              params={"item_name": "Pipe MS 50mm"}, timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] >= 1
    m = data["matches"][0]
    assert m["vendor_id"] == rate_contract["vendor_id"]
    assert m["rate"] == 450.0


def test_rate_contract_expiring_list(s):
    r = s.get(f"{API_URL}/api/procurement-extras/rate-contracts/expiring/list",
              params={"window_days": 730}, timeout=10)
    assert r.status_code == 200
    assert "rows" in r.json()


def test_rate_contract_bad_dates_rejected(s, vendor):
    r = s.post(f"{API_URL}/api/procurement-extras/rate-contracts", json={
        "vendor_id": vendor["id"], "start_date": "2027-01-01", "end_date": "2026-01-01",
        "lines": [{"item_name": "X", "rate": 10, "unit": "Nos"}],
    }, timeout=10)
    assert r.status_code == 400


# ─── Service Orders + SRN ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def service_order(s, vendor):
    payload = {
        "vendor_id": vendor["id"],
        "service_type": "manpower",
        "scope_of_work": "Supply 5 scaffolders for 30 days",
        "rate_basis": "per_day",
        "rate": 800.0, "quantity": 150, "unit": "manday",
        "start_date": "2026-02-01", "end_date": "2026-02-28",
        "gst_percent": 18.0,
    }
    r = s.post(f"{API_URL}/api/procurement-extras/service-orders", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def test_service_order_created_with_number(service_order):
    assert service_order["so_number"].startswith("SO-")
    assert service_order["status"] == "draft"
    assert service_order["base_amount"] == 800 * 150
    assert service_order["gst_amount"] == round(800 * 150 * 0.18, 2)


def test_service_order_approve(s, service_order):
    r = s.post(f"{API_URL}/api/procurement-extras/service-orders/{service_order['id']}/approve", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_service_order_bad_rate_basis_rejected(s, vendor):
    r = s.post(f"{API_URL}/api/procurement-extras/service-orders", json={
        "vendor_id": vendor["id"], "service_type": "x", "scope_of_work": "x",
        "rate_basis": "per_unicorn", "rate": 100, "start_date": "2026-02-01",
        "end_date": "2026-02-28",
    }, timeout=10)
    assert r.status_code == 400


def test_srn_create_and_so_partial(s, service_order):
    # record SRN for ~50% value
    so_total = service_order["total_amount"]
    half_val = round(so_total * 0.45, 2)
    r = s.post(f"{API_URL}/api/procurement-extras/srns", json={
        "so_id": service_order["id"],
        "service_period_from": "2026-02-01",
        "service_period_to": "2026-02-14",
        "work_completed": "Phase 1: 75 mandays delivered",
        "certified_quantity": 75, "certified_value": half_val,
    }, timeout=10)
    assert r.status_code == 200, r.text
    srn = r.json()
    assert srn["srn_number"].startswith("SRN-")
    # SO should now be partially_received
    so = s.get(f"{API_URL}/api/procurement-extras/service-orders/{service_order['id']}", timeout=10).json()
    assert so["status"] == "partially_received"
    assert so["received_value"] == half_val


def test_srn_excess_rejected(s, service_order):
    """Cannot certify > SO total + 10% tolerance."""
    so_total = service_order["total_amount"]
    r = s.post(f"{API_URL}/api/procurement-extras/srns", json={
        "so_id": service_order["id"],
        "service_period_from": "2026-02-15",
        "service_period_to": "2026-02-28",
        "work_completed": "exceeds",
        "certified_quantity": 999, "certified_value": so_total * 2,
    }, timeout=10)
    assert r.status_code == 400


# ─── Quality Inspection ────────────────────────────────────────────────────
def test_inspections_list(s):
    r = s.get(f"{API_URL}/api/procurement-extras/inspections", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_inspection_invalid_grn_404(s):
    r = s.post(f"{API_URL}/api/procurement-extras/inspections", json={
        "grn_id": "non-existent",
        "rejected_items": [], "overall_status": "accepted",
    }, timeout=10)
    assert r.status_code == 404


def test_pending_replacement_view(s):
    r = s.get(f"{API_URL}/api/procurement-extras/inspections/pending-replacement", timeout=10)
    assert r.status_code == 200
    assert "rows" in r.json()


# ─── Document Expiry + Notifications + Tiers ──────────────────────────────
def test_document_expiry_endpoint(s):
    r = s.get(f"{API_URL}/api/procurement-extras/document-expiry",
              params={"window_days": 60}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "alerts" in d and isinstance(d["alerts"], list)
    assert d["window_days"] == 60


def test_notifications_inbox(s):
    r = s.get(f"{API_URL}/api/procurement-extras/notifications", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "items" in d and "total" in d
    # Every item must have required fields
    for n in d["items"]:
        for k in ("kind", "title", "severity", "count"):
            assert k in n


def test_vendor_performance_tiers(s):
    r = s.get(f"{API_URL}/api/procurement-extras/performance/tiers", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "counts" in d and "rows" in d
    valid_tiers = {"Excellent", "Good", "Average", "Poor", "Blacklisted"}
    for r in d["rows"]:
        assert r["tier"] in valid_tiers
