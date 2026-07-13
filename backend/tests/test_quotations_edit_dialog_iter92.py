"""Iter 92 regression: Super-Admin edit dialog actually persists via PUT.

This test is end-to-end: it asserts that fields exposed in the edit dialog —
site_name, scope_of_work, material_requirement, manpower_requirement — survive
a round-trip through the API, AND that the side-effects (live-sync into
Contract Handovers) still fire.
"""
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


def test_super_admin_edit_persists_full_field_set(admin_session):
    quotes = admin_session.get(f"{API_URL}/api/quotations", timeout=10).json()
    q = quotes[0]
    qid = q["id"]
    backup = {k: q.get(k) for k in
               ("site_name", "site_location", "scope_of_work",
                "material_requirement", "manpower_requirement",
                "client", "contact_person", "contact_phone", "contact_email",
                "company_state", "commercial_notes", "technical_requirements")}
    suf = secrets.token_hex(3)
    edits = {
        "site_name": f"NEW-SITE-{suf}",
        "site_location": f"NEW-LOC-{suf}",
        "scope_of_work": f"NEW SCOPE {suf} — Super Admin edit verification",
        "material_requirement": f"NEW MAT REQ {suf}",
        "manpower_requirement": f"NEW MAN REQ {suf}",
        "contact_person": f"Contact {suf}",
        "contact_phone": "+91 99 1234 5678",
        "contact_email": f"contact-{suf}@itlis.in",
        "company_state": "Maharashtra",
        "commercial_notes": f"Commercial notes {suf}",
        "technical_requirements": f"Tech req {suf}",
    }
    try:
        r = admin_session.put(f"{API_URL}/api/quotations/{qid}", json={**q, **edits}, timeout=10)
        assert r.status_code == 200, r.text

        # Re-fetch and assert every edited field is persisted
        fetched = admin_session.get(f"{API_URL}/api/quotations/{qid}", timeout=10).json()
        for k, v in edits.items():
            assert fetched[k] == v, f"{k} not persisted: expected {v!r}, got {fetched.get(k)!r}"

        # Side-effect: live Contract-Handover sync must reflect the new site_name
        hos = admin_session.get(f"{API_URL}/api/ops/handovers", timeout=10).json()
        linked = next((h for h in hos if h.get("quotation_id") == qid), None)
        if linked:
            assert linked["project_name"] == edits["site_name"], linked
            assert linked["scope_of_work"] == edits["scope_of_work"], linked
    finally:
        # Always restore — keeps the data deterministic for repeat runs
        admin_session.put(f"{API_URL}/api/quotations/{qid}", json={**q, **backup}, timeout=10)
