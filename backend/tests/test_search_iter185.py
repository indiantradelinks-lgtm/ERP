"""Iteration 185 — Universal ERP Search (GET /api/search, GET /api/search/scope)

Covers:
- Auth-required behaviour
- Empty / short query
- Grouped result shape + timing
- Detail route templates (quotations, projects, assets, service_requests, dispatch_requests)
- Purchase Orders route (list + hl fallback)
- Regex-safety with special characters
- RBAC: sales_executive should NOT see restricted groups (users, payroll, employee_advances)
- /search/scope returns fewer collections for sales than for super_admin
"""
from __future__ import annotations

import os
import re
import time
from urllib.parse import urlparse, parse_qs, unquote

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SALES = {"email": "sales@erp.com", "password": "Sales@123"}


def _session(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _session(ADMIN)


@pytest.fixture(scope="module")
def sales_session():
    return _session(SALES)


# ── Auth ─────────────────────────────────────────────────────────────
class TestAuth:
    def test_search_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/search", params={"q": "reliance"}, timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code}"

    def test_scope_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/search/scope", timeout=15)
        assert r.status_code == 401


# ── Basic shape & short query ───────────────────────────────────────
class TestBasicShape:
    def test_short_query_returns_empty(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": "r"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["groups"] == []
        assert data["total"] == 0
        assert data["query"] == "r"

    def test_reliance_returns_grouped_results(self, admin_session):
        t0 = time.time()
        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": "reliance"}, timeout=20)
        elapsed_ms = (time.time() - t0) * 1000
        assert r.status_code == 200
        data = r.json()
        assert set(["query", "groups", "total", "took_ms"]).issubset(data.keys())
        assert data["query"] == "reliance"
        # server-reported timing should be reasonable
        assert data["took_ms"] < 3000, f"server took_ms too high: {data['took_ms']}"
        # network-side sanity
        assert elapsed_ms < 8000
        # each group shape
        for g in data["groups"]:
            assert set(["key", "label", "module", "route", "items"]).issubset(g.keys())
            for item in g["items"]:
                assert set(["id", "title", "subtitle", "status", "route"]).issubset(item.keys())
        # total == sum of item counts
        assert data["total"] == sum(len(g["items"]) for g in data["groups"])
        print(f"reliance → {len(data['groups'])} groups, {data['total']} items, {data['took_ms']}ms")

    def test_limit_capping(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": "a", "limit": 5}, timeout=15)
        # short "a" (1 char) still empty
        assert r.status_code == 200
        assert r.json()["total"] == 0

        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": "re", "limit": 3}, timeout=20)
        assert r.status_code == 200
        for g in r.json()["groups"]:
            assert len(g["items"]) <= 3


# ── Detail route templates ──────────────────────────────────────────
class TestRouteTemplates:
    def _find_group(self, data, key):
        for g in data["groups"]:
            if g["key"] == key:
                return g
        return None

    def test_quotation_detail_route(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": "QUO"}, timeout=20)
        assert r.status_code == 200
        g = self._find_group(r.json(), "quotations")
        if not g or not g["items"]:
            pytest.skip("no quotations matched — cannot verify detail route")
        for it in g["items"]:
            assert re.match(r"^/app/quotations/[^/]+/builder$", it["route"]), f"bad quotation route: {it['route']}"

    def test_project_detail_route(self, admin_session):
        # Try a couple of common tokens; skip if nothing found
        for term in ("project", "reliance", "site"):
            r = admin_session.get(f"{BASE_URL}/api/search", params={"q": term}, timeout=20)
            g = self._find_group(r.json(), "projects")
            if g and g["items"]:
                for it in g["items"]:
                    assert it["route"].startswith("/app/project-dashboard/"), f"bad project route: {it['route']}"
                return
        pytest.skip("no projects found")

    def test_asset_detail_route(self, admin_session):
        for term in ("asset", "laptop", "vehicle", "scaffolding"):
            r = admin_session.get(f"{BASE_URL}/api/search", params={"q": term}, timeout=20)
            g = self._find_group(r.json(), "assets")
            if g and g["items"]:
                for it in g["items"]:
                    assert it["route"].startswith("/app/asset-lifecycle/"), f"bad asset route: {it['route']}"
                return
        pytest.skip("no assets found")

    def test_service_request_detail_route(self, admin_session):
        for term in ("service", "sr", "maintenance"):
            r = admin_session.get(f"{BASE_URL}/api/search", params={"q": term}, timeout=20)
            g = self._find_group(r.json(), "svc_requests")
            if g and g["items"]:
                for it in g["items"]:
                    assert it["route"].startswith("/app/services/requests/"), f"bad svc route: {it['route']}"
                return
        pytest.skip("no service requests found")

    def test_dispatch_request_detail_route(self, admin_session):
        for term in ("DR", "dispatch", "delivery"):
            r = admin_session.get(f"{BASE_URL}/api/search", params={"q": term}, timeout=20)
            g = self._find_group(r.json(), "logistics_dispatch_requests")
            if g and g["items"]:
                for it in g["items"]:
                    assert it["route"].startswith("/app/logistics/dispatch-requests/"), f"bad DR route: {it['route']}"
                return
        pytest.skip("no dispatch requests found")

    def test_purchase_order_list_route(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": "PO-2026"}, timeout=20)
        assert r.status_code == 200
        g = None
        for grp in r.json()["groups"]:
            if grp["key"] == "purchase_orders":
                g = grp
                break
        if not g or not g["items"]:
            pytest.skip("no PO-2026 purchase orders found")
        for it in g["items"]:
            parsed = urlparse(it["route"])
            assert parsed.path == "/app/purchase-orders", f"expected list route, got {it['route']}"
            qs = parse_qs(parsed.query)
            assert "q" in qs and "hl" in qs, f"missing q/hl params: {it['route']}"
            # URL-decoded q should contain the searched term
            assert "PO-2026" in unquote(qs["q"][0])


# ── Regex safety ────────────────────────────────────────────────────
class TestRegexSafety:
    @pytest.mark.parametrize("term", ["PO-2026(", "a.b*", "test[", "foo+", "^abc", "a|b", "x$"])
    def test_special_chars_do_not_500(self, admin_session, term):
        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": term}, timeout=20)
        assert r.status_code == 200, f"term={term!r} returned {r.status_code}: {r.text[:200]}"


# ── RBAC ───────────────────────────────────────────────────────────
class TestRBAC:
    RESTRICTED_FOR_SALES = {"users", "payroll", "employee_advances"}

    def test_sales_cannot_see_restricted_groups_admin(self, sales_session):
        r = sales_session.get(f"{BASE_URL}/api/search", params={"q": "admin"}, timeout=20)
        assert r.status_code == 200
        keys = {g["key"] for g in r.json()["groups"]}
        overlap = keys & self.RESTRICTED_FOR_SALES
        assert not overlap, f"sales role saw restricted groups: {overlap}"

    def test_sales_cannot_see_restricted_groups_arjun(self, sales_session):
        r = sales_session.get(f"{BASE_URL}/api/search", params={"q": "arjun"}, timeout=20)
        assert r.status_code == 200
        keys = {g["key"] for g in r.json()["groups"]}
        overlap = keys & self.RESTRICTED_FOR_SALES
        assert not overlap, f"sales role saw restricted groups: {overlap}"

    def test_super_admin_sees_users_group_for_admin_query(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/search", params={"q": "admin"}, timeout=20)
        assert r.status_code == 200
        keys = {g["key"] for g in r.json()["groups"]}
        assert "users" in keys, f"super_admin should see 'users' group; got {keys}"

    def test_scope_differs_between_roles(self, admin_session, sales_session):
        ra = admin_session.get(f"{BASE_URL}/api/search/scope", timeout=15)
        rs = sales_session.get(f"{BASE_URL}/api/search/scope", timeout=15)
        assert ra.status_code == 200
        assert rs.status_code == 200
        admin_keys = {e["key"] for e in ra.json()}
        sales_keys = {e["key"] for e in rs.json()}
        assert len(sales_keys) < len(admin_keys), f"sales scope should be smaller: sales={len(sales_keys)} admin={len(admin_keys)}"
        # Sales must not include restricted collections
        assert not (sales_keys & self.RESTRICTED_FOR_SALES), f"sales scope leaked: {sales_keys & self.RESTRICTED_FOR_SALES}"
        # Admin should include them
        assert self.RESTRICTED_FOR_SALES.issubset(admin_keys), f"admin scope missing: {self.RESTRICTED_FOR_SALES - admin_keys}"
        print(f"scope: admin={len(admin_keys)} sales={len(sales_keys)}")
