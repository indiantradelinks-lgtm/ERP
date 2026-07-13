"""Iter 96: P&O Phase 1 extended Project Master + Site Master + WO Mapping."""
import os
import secrets

import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return s


def test_project_extended_fields_persist(admin_session):
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    p = projects[0]
    backup = dict(p)
    patch = {**p,
        "client_code": "ITL-001", "client_contact_person": "Sharma",
        "client_contact_number": "+91 99 0000 1111",
        "client_email": "sharma@itl.in",
        "billing_address": "Mumbai", "site_address": "Hazira",
        "state": "Gujarat", "city": "Surat",
        "priority": "urgent", "category": "shutdown",
        "store_incharge": "Patel", "client_engineer": "Reddy",
        "gst_applicability": "applicable", "tds_applicability": "applicable",
        "retention_percentage": 5, "mobilization_advance": 100000,
        "payment_terms": "30 days net", "actual_completion_date": "2026-04-30",
        "status": "mobilization_pending",
    }
    r = admin_session.put(f"{API_URL}/api/projects/{p['id']}", json=patch, timeout=10)
    assert r.status_code == 200
    try:
        fp = admin_session.get(f"{API_URL}/api/projects/{p['id']}", timeout=10).json()
        for k in ("client_code", "priority", "category", "store_incharge", "client_engineer",
                  "gst_applicability", "tds_applicability", "mobilization_advance",
                  "actual_completion_date"):
            assert fp.get(k) == patch[k], f"{k} did not persist: got {fp.get(k)!r}"
        assert fp["status"] == "mobilization_pending"
        assert fp["retention_percentage"] == 5
    finally:
        admin_session.put(f"{API_URL}/api/projects/{p['id']}", json=backup, timeout=10)


def test_wo_value_change_writes_revision_and_cascades_to_project(admin_session):
    projects = admin_session.get(f"{API_URL}/api/projects", timeout=10).json()
    p = projects[0]
    p_backup_value = p.get("work_order_value")
    p_backup_contract = p.get("contract_value")
    wo_no = f"PO-RT-{secrets.token_hex(3).upper()}"
    r = admin_session.post(f"{API_URL}/api/work-orders", json={
        "wo_no": wo_no, "project_id": p["id"], "value": 500000,
        "status": "received", "quotation_no": "QTN-RT",
    }, timeout=10)
    assert r.status_code == 200
    wo = r.json(); wid = wo["id"]
    try:
        # Change value → expect revision entry + project cascade
        r = admin_session.put(f"{API_URL}/api/work-orders/{wid}",
            json={**wo, "value": 750000, "remarks": "additional scope"}, timeout=10)
        assert r.status_code == 200
        updated = r.json()
        hist = updated.get("revision_history") or []
        assert len(hist) == 1
        assert hist[0]["from_value"] == 500000
        assert hist[0]["to_value"] == 750000
        # Project should have cascaded values
        fp = admin_session.get(f"{API_URL}/api/projects/{p['id']}", timeout=10).json()
        assert fp["work_order_value"] == 750000
        assert fp["contract_value"] == 750000
        # Same-value PUT should NOT add a new revision entry
        r = admin_session.put(f"{API_URL}/api/work-orders/{wid}",
            json={**updated, "remarks": "no value change"}, timeout=10)
        assert r.status_code == 200
        assert len(r.json().get("revision_history") or []) == 1
    finally:
        admin_session.delete(f"{API_URL}/api/work-orders/{wid}", timeout=10)
        admin_session.put(f"{API_URL}/api/projects/{p['id']}",
            json={**p, "work_order_value": p_backup_value, "contract_value": p_backup_contract},
            timeout=10)


def test_wo_sales_linked_fields_persist(admin_session):
    wo_no = f"PO-SL-{secrets.token_hex(3).upper()}"
    body = {
        "wo_no": wo_no, "value": 100000, "status": "received",
        "quotation_no": "QTN-LINK-1", "approved_quotation": True, "boq": "100 m³ pipes",
        "payment_terms": "30D net", "retention_clause": "5%",
        "retention_percentage": 5, "tds_applicability": "applicable",
        "gst_applicability": "applicable",
        "project_start_condition": "Mobilization advance + safety induction",
        "billing_milestone": "M1 erection 30%, M2 final 70%",
        "contractual_completion_date": "2026-12-31",
    }
    r = admin_session.post(f"{API_URL}/api/work-orders", json=body, timeout=10)
    assert r.status_code == 200
    wid = r.json()["id"]
    try:
        fetched = admin_session.get(f"{API_URL}/api/work-orders?status=received", timeout=10).json()
        ours = next(w for w in fetched if w["id"] == wid)
        for k in ("quotation_no", "approved_quotation", "boq", "payment_terms",
                  "retention_clause", "tds_applicability", "gst_applicability",
                  "project_start_condition", "billing_milestone",
                  "contractual_completion_date"):
            assert ours[k] == body[k], f"{k} mismatch: {ours.get(k)!r} vs {body[k]!r}"
    finally:
        admin_session.delete(f"{API_URL}/api/work-orders/{wid}", timeout=10)


def test_site_extended_compliance_fields_persist(admin_session):
    sites = admin_session.get(f"{API_URL}/api/sites", timeout=10).json()
    if not sites:
        pytest.skip("no sites seeded")
    site = sites[0]
    backup = dict(site)
    patch = {**site,
        "safety_induction_required": True,
        "medical_fitness_required": True,
        "work_permit_required": False,
        "ppe_requirement": "Helmet, FBH, Safety shoes",
        "site_working_hours": "08:00 – 17:30",
        "shift_details": "1 shift",
        "accommodation_required": False,
        "local_conveyance_required": True,
        "loading_unloading_requirement": "Hydra available",
        "store_available_at_site": True,
        "remarks": "Iter 96 regression",
    }
    r = admin_session.put(f"{API_URL}/api/sites/{site['id']}", json=patch, timeout=10)
    assert r.status_code == 200
    try:
        # No single-site GET endpoint → fetch from the list and find by id
        all_sites = admin_session.get(f"{API_URL}/api/sites", timeout=10).json()
        fs = next(x for x in all_sites if x["id"] == site["id"])
        for k in ("safety_induction_required", "medical_fitness_required",
                  "work_permit_required", "ppe_requirement",
                  "site_working_hours", "shift_details",
                  "accommodation_required", "local_conveyance_required",
                  "loading_unloading_requirement", "store_available_at_site"):
            assert fs.get(k) == patch[k], f"{k} did not persist"
    finally:
        admin_session.put(f"{API_URL}/api/sites/{site['id']}", json=backup, timeout=10)
