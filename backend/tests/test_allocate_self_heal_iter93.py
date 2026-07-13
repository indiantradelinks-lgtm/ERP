"""Iter 93 regression: handover allocation self-heals missing project_id.

A handover created BEFORE its enquiry was converted to Order has no
`project_id` link. The allocate endpoint must:
  1) Look up the project via enquiry/order/quotation links.
  2) Back-fill `project_id` on the handover automatically.
  3) Proceed with the allocation instead of returning the legacy 400.

If no project can be found anywhere in the chain, the original error must
still fire (we don't silently auto-create projects).
"""
import os

import pytest
import requests


API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return s, r.json()


def test_allocate_self_heals_missing_project_id(admin_session):
    """Set up: pick a handover with project_id, blank it out, then allocate again
    and assert the project_id is restored from the enquiry link."""
    s, me = admin_session
    hos = s.get(f"{API_URL}/api/ops/handovers", timeout=10).json()
    # Find an allocated handover whose enquiry HAS a project_id we can use to
    # validate self-heal. We pretend it was created before conversion.
    candidate = None
    for h in hos:
        if not h.get("enquiry_id"):
            continue
        e = s.get(f"{API_URL}/api/enquiries/{h['enquiry_id']}", timeout=10).json()
        if e.get("project_id"):
            candidate = (h, e)
            break
    if not candidate:
        pytest.skip("no handover with a project-linked enquiry available")
    h, e = candidate
    orig_project_id = h.get("project_id")
    orig_status = h.get("status")
    # Simulate the broken state — blank the project_id and reset to submitted
    s.put(f"{API_URL}/api/ops/handovers/{h['id']}",
           json={"project_id": None, "status": "submitted"}, timeout=10)
    try:
        body = {
            "project_manager_id": me["id"],
            "department": "operations",
            "priority": "medium",
            "remarks": "iter-93 self-heal regression",
        }
        r = s.post(f"{API_URL}/api/ops/handovers/{h['id']}/allocate", json=body, timeout=10)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["project_id"] == e["project_id"], out
        # Verify persisted on the handover
        h2 = s.get(f"{API_URL}/api/ops/handovers/{h['id']}", timeout=10).json()
        assert h2["project_id"] == e["project_id"]
    finally:
        s.put(f"{API_URL}/api/ops/handovers/{h['id']}",
               json={"project_id": orig_project_id, "status": orig_status}, timeout=10)


def test_allocate_still_errors_when_no_project_anywhere(admin_session):
    """If neither the handover, enquiry, order, nor quotation can produce a
    project, the original "convert to order first" error must still fire."""
    s, me = admin_session
    # Create a stand-alone handover with no project link of any kind
    import secrets
    from datetime import datetime, timezone
    new_h = {
        "id": f"test-{secrets.token_hex(4)}",
        "handover_no": f"CHO-TEST-{secrets.token_hex(2).upper()}",
        "project_name": "Test orphan handover",
        "client_name": "Orphan",
        "status": "submitted",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "submitted_by_id": me["id"],
    }
    # Insert directly via Mongo Admin (no public endpoint to seed a raw handover);
    # we use the generic crud route if available, else skip.
    r = s.post(f"{API_URL}/api/project_handovers", json=new_h, timeout=10)
    if r.status_code not in (200, 201):
        pytest.skip(f"cannot seed an orphan handover (crud disabled: HTTP {r.status_code})")
    hid = r.json().get("id", new_h["id"])
    try:
        body = {"project_manager_id": me["id"], "priority": "medium"}
        r2 = s.post(f"{API_URL}/api/ops/handovers/{hid}/allocate", json=body, timeout=10)
        assert r2.status_code == 400
        detail = r2.json().get("detail", "")
        assert "Convert to Order" in detail, detail
    finally:
        s.delete(f"{API_URL}/api/project_handovers/{hid}", timeout=10)
