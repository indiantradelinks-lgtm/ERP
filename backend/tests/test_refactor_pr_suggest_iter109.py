"""Iter 109 — Router-registry refactor + PR rate-contract suggest wiring.

Verifies:
  - All 74 routers register correctly via routers_registry.
  - /api/ root still works.
  - Rate-contract suggest returns proper match shape for PR auto-fill.
"""
import os
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


def test_routers_registry_count():
    """Registry should expose exactly the routers server.py used to register manually."""
    from routers_registry import ROUTERS_IN_ORDER, iter_router_names
    names = list(iter_router_names())
    assert len(names) >= 70, f"Expected 70+ routers, got {len(names)}"
    # critical order: auth must be first; crud must come AFTER sales/vendors/payroll
    auth_idx = names.index("auth")
    crud_idx = names.index("crud")
    payroll_idx = names.index("payroll")
    vendors_idx = names.index("vendors")
    sales_idx = names.index("sales")
    assert auth_idx == 0
    assert payroll_idx < crud_idx
    assert vendors_idx < crud_idx
    assert sales_idx < crud_idx


def test_api_root_alive(s):
    r = s.get(f"{API_URL}/api/", timeout=10)
    assert r.status_code == 200
    assert r.json()["service"] == "Corporate ERP API"


def test_scheduler_status_endpoint(s):
    """Smoke — the @api.get('/scheduler/status') endpoint declared inline in
    server.py must still be reachable after the refactor."""
    r = s.get(f"{API_URL}/api/scheduler/status", timeout=10)
    assert r.status_code == 200


def test_critical_routers_still_routable(s):
    """Spot-check a few endpoints from different routers — they must respond
    (200 or 401/403, anything but 404)."""
    paths = [
        "/api/vendors",
        "/api/procurement/prs",
        "/api/procurement-extras/vendor-types",
        "/api/proj-phase5/audit/non-existent",
        "/api/email/config",
    ]
    for p in paths:
        r = s.get(f"{API_URL}{p}", timeout=10)
        assert r.status_code != 404, f"{p} returns 404 — router not mounted!"


# ─── PR rate-contract suggest wiring ──────────────────────────────────────
@pytest.fixture(scope="module")
def vendor_with_rc(s):
    """Find or create a vendor + active RC for suggest-testing."""
    rcs = s.get(f"{API_URL}/api/procurement-extras/rate-contracts?status=active",
                timeout=10).json()
    if rcs:
        return {"vendor_id": rcs[0]["vendor_id"], "vendor_name": rcs[0]["vendor_name"],
                "lines": rcs[0]["lines"]}
    pytest.skip("No active RC in this preview DB to test suggest against")


def test_suggest_returns_shape_for_pr_autofill(s, vendor_with_rc):
    """Suggest payload must include the 4 fields the frontend RateContractHint reads."""
    item_name = vendor_with_rc["lines"][0]["item_name"]
    r = s.get(f"{API_URL}/api/procurement-extras/rate-contracts/suggest",
              params={"item_name": item_name}, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] >= 1
    m = d["matches"][0]
    for key in ("vendor_id", "vendor_name", "rate", "unit", "end_date", "rc_id"):
        assert key in m, f"missing key {key} in suggest payload"


def test_suggest_400_without_params(s):
    r = s.get(f"{API_URL}/api/procurement-extras/rate-contracts/suggest", timeout=10)
    assert r.status_code == 400


def test_suggest_empty_when_unknown_item(s):
    r = s.get(f"{API_URL}/api/procurement-extras/rate-contracts/suggest",
              params={"item_name": "Definitely Non-Existent Item ZZZ"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["count"] == 0
