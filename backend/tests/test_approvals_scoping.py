"""Iter 56 — Approvals department scoping regression test."""
import os, re, requests

def _backend_url():
    env_text = open("/app/frontend/.env").read()
    m = re.search(r"^REACT_APP_BACKEND_URL=(.+)$", env_text, re.MULTILINE)
    return os.environ.get("REACT_APP_BACKEND_URL") or m.group(1).strip()

API = _backend_url()
BASE = f"{API}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    return s


def _types(rows):
    from collections import Counter
    return Counter([a.get("type", "?") for a in rows])


def test_super_admin_sees_all_types():
    s = _login("admin@erp.com", "Admin@123")
    rows = s.get(f"{BASE}/approvals").json()
    types = _types(rows)
    # Super admin should see multiple department types
    assert len(types) >= 3, f"super_admin saw only {dict(types)}"


def test_purchase_officer_only_procurement():
    s = _login("purchase@erp.com", "Purchase@123")
    rows = s.get(f"{BASE}/approvals").json()
    types = _types(rows)
    forbidden = {"client_onboarding", "quotation", "enquiry", "leave", "deployment"}
    leaked = forbidden & set(types.keys())
    assert not leaked, f"purchase_officer leaked: {leaked}"
    # Should see at least one procurement type
    assert types  # not empty (there are vendor/PR approvals seeded)
    assert any(t in types for t in ("vendor", "purchase_requisition", "rfq", "purchase_order"))


def test_sales_executive_only_sales():
    s = _login("sales@erp.com", "Sales@123")
    rows = s.get(f"{BASE}/approvals").json()
    types = _types(rows)
    forbidden = {"vendor", "purchase_requisition", "rfq", "grn", "employee_advance"}
    leaked = forbidden & set(types.keys())
    assert not leaked, f"sales_executive leaked: {leaked}"


def test_lanes_endpoint_also_scoped():
    s = _login("purchase@erp.com", "Purchase@123")
    d = s.get(f"{BASE}/approvals/lanes").json()
    all_items = []
    for items in (d.get("lanes") or {}).values():
        all_items.extend(items)
    types = _types(all_items)
    forbidden = {"client_onboarding", "quotation", "enquiry", "leave"}
    leaked = forbidden & set(types.keys())
    assert not leaked, f"lanes leaked: {leaked}"
