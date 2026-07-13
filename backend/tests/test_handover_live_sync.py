"""Regression: Contract Handovers must reflect live Project/Client edits made in Sales & Quotations."""
import os
import secrets

import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200, r.text
    return s


def _pick_linked_handover(session):
    rows = session.get(f"{API_URL}/api/ops/handovers", timeout=10).json()
    for h in rows:
        if h.get("quotation_id"):
            return h
    pytest.skip("no handover with quotation_id available")


def test_handover_reflects_live_quote_project(session):
    target = _pick_linked_handover(session)
    qid = target["quotation_id"]
    quote = session.get(f"{API_URL}/api/quotations/{qid}", timeout=10).json()
    orig_site = quote.get("site_name")
    orig_client = quote.get("client")
    orig_scope = quote.get("scope_of_work")
    new_site = f"LIVE-SITE-{secrets.token_hex(3)}"   # Quotation Builder "Site / project name"
    new_client = f"LIVE-C-{secrets.token_hex(3)}"
    new_scope = f"LIVE-SCOPE-{secrets.token_hex(3)} — verifies the scope_of_work pipeline"
    try:
        # Mutate the quote — note: Project column on Handovers pulls site_name
        r = session.put(f"{API_URL}/api/quotations/{qid}",
                         json={**quote, "site_name": new_site, "client": new_client,
                                "scope_of_work": new_scope}, timeout=10)
        assert r.status_code == 200

        rows = session.get(f"{API_URL}/api/ops/handovers", timeout=10).json()
        h = next(x for x in rows if x["id"] == target["id"])
        assert h["project_name"] == new_site, h
        assert h["client_name"] == new_client, h
        assert h["scope_of_work"] == new_scope, h
        assert h["project_name_source"] == "quotation", h
        assert h["client_name_source"] == "quotation", h
        assert h["scope_of_work_source"] == "quotation", h

        det = session.get(f"{API_URL}/api/ops/handovers/{target['id']}", timeout=10).json()
        assert det["project_name"] == new_site, det
        assert det["client_name"] == new_client, det
        assert det["scope_of_work"] == new_scope, det
    finally:
        session.put(f"{API_URL}/api/quotations/{qid}",
                     json={**quote, "site_name": orig_site, "client": orig_client,
                            "scope_of_work": orig_scope}, timeout=10)


def test_handover_falls_back_to_stored_when_no_link(session):
    """Handovers without a quotation_id should pass through their stored values untouched."""
    rows = session.get(f"{API_URL}/api/ops/handovers", timeout=10).json()
    unlinked = [h for h in rows if not h.get("quotation_id") and not h.get("enquiry_id")]
    if not unlinked:
        pytest.skip("no unlinked handover to verify fallback")
    h = unlinked[0]
    # No hydration → both fields just echo what's stored, no live indicators
    assert h.get("project_name_source") is None
    assert h.get("client_name_source") is None
