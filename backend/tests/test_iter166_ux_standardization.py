"""Iter 166 — UI/UX standardization backend verification.

Covers:
  1) GET /api/advances/eligible-employees (admin, PM) — used by Leave.jsx & Advances.jsx
     scoping (Manager O P scoped to PRJ-2025-01).
  2) POST /api/project-requests with material_category_id and empty cost_center_id
     → server auto-resolves cost_center from project cost_centers for that category.
  3) POST/PUT /api/procurement/master/categories accepts new cost_center field
     and persists on GET.
  4) GET /api/sites (Site Master) for SiteLocationSelect + GET /api/procurement/master/categories.
"""
import os
import time
import uuid

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def mop():
    return _login("test_mop@erp.com", "Mop@12345")


# ─── 1) eligible-employees ────────────────────────────────────────────────
class TestEligibleEmployees:
    def test_admin_can_on_behalf_all(self, admin):
        r = admin.get(f"{BASE}/api/advances/eligible-employees", timeout=20)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data.get("can_on_behalf") is True
        assert data.get("scope") == "all"
        assert isinstance(data.get("employees"), list)
        assert len(data["employees"]) > 0

    def test_mop_scoped_to_prj_2025_01(self, mop):
        r = mop.get(f"{BASE}/api/advances/eligible-employees", timeout=20)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data.get("can_on_behalf") is True
        assert data.get("scope") == "projects"
        assert "PRJ-2025-01" in data.get("projects", [])
        emps = data.get("employees") or []
        # Must contain E-1001 Arjun Reddy per credentials note
        codes = [(e.get("employee_id") or e.get("emp_code")) for e in emps]
        names = [e.get("name") for e in emps]
        assert any("Arjun" in (n or "") for n in names) or "E-1001" in codes, \
            f"E-1001/Arjun missing from MOP scoped list: codes={codes[:10]} names={names[:10]}"
        # No employee outside PRJ-2025-01 (self may be included even if not on project)
        for e in emps:
            cp = e.get("current_project_code")
            if cp and e.get("email") != "test_mop@erp.com":
                assert cp == "PRJ-2025-01", f"leak: {e.get('name')} on {cp}"


# ─── 2) project-requests auto-resolve cost_center from material_category ──
class TestProjectRequestCostCenterAutoResolve:
    @pytest.fixture(scope="class")
    def ctx(self, admin):
        # find a project + a category that has a cost_center row
        projects = admin.get(f"{BASE}/api/projects", timeout=20).json()
        assert projects
        project = projects[0]
        pid = project.get("id")

        cats = admin.get(f"{BASE}/api/procurement/master/categories", timeout=20).json()
        assert cats
        # pick a category
        cat = cats[0]

        # ensure a cost center exists for (project, category)
        ccs = admin.get(
            f"{BASE}/api/procurement/master/cost-centers?project_id={pid}",
            timeout=20,
        ).json()
        match = next((c for c in ccs if c.get("category_id") == cat["id"]), None)
        if not match:
            r = admin.post(
                f"{BASE}/api/procurement/master/cost-centers",
                json={"project_id": pid, "category_id": cat["id"]},
                timeout=20,
            )
            assert r.status_code in (200, 201), f"create CC failed: {r.status_code} {r.text[:200]}"
            match = r.json()
        return {"project": project, "cat": cat, "cc": match}

    def test_create_request_auto_resolves_cost_center(self, admin, ctx):
        project = ctx["project"]
        cat = ctx["cat"]
        payload = {
            "project_id": project["id"],
            "request_type": "fuel",
            "priority": "medium",
            "description": f"TEST_iter166 auto-CC {uuid.uuid4().hex[:6]}",
            "amount": 5000,
            "material_category_id": cat["id"],
            # cost_center_id intentionally omitted / empty
            "site_location": "TEST_site",
            "items": [],
        }
        r = admin.post(f"{BASE}/api/project-requests", json=payload, timeout=25)
        assert r.status_code == 200, f"create req failed: {r.status_code} {r.text[:400]}"
        doc = r.json()
        assert doc.get("cost_center_id"), f"cost_center_id not auto-resolved: {doc}"
        assert doc.get("cost_center_id") == ctx["cc"]["id"], \
            f"resolved wrong CC: got={doc.get('cost_center_id')} expected={ctx['cc']['id']}"
        assert doc.get("cost_center_label"), "cost_center_label missing"
        assert doc.get("material_category_id") == cat["id"]

        # Detail GET should also have the resolved CC
        rid = doc["id"]
        rows = admin.get(f"{BASE}/api/project-requests", timeout=20).json()
        found = next((x for x in rows if x["id"] == rid), None)
        assert found and found.get("cost_center_id") == ctx["cc"]["id"]


# ─── 3) Categories master accepts cost_center ─────────────────────────────
class TestCategoryCostCenterField:
    def test_create_and_update_category_cost_center(self, admin):
        code = f"TEST{int(time.time())%100000}"
        # Create
        r = admin.post(
            f"{BASE}/api/procurement/master/categories",
            json={"code": code, "name": f"TEST_cat_{code}", "cost_center": "CC-TEST-1"},
            timeout=20,
        )
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}"
        doc = r.json()
        cid = doc.get("id")
        assert cid
        assert doc.get("cost_center") == "CC-TEST-1", f"cost_center not persisted on POST: {doc}"

        # GET list — verify visible
        rows = admin.get(f"{BASE}/api/procurement/master/categories", timeout=20).json()
        found = next((c for c in rows if c["id"] == cid), None)
        assert found, "category missing from list"
        assert found.get("cost_center") == "CC-TEST-1"

        # PUT update
        r2 = admin.put(
            f"{BASE}/api/procurement/master/categories/{cid}",
            json={"code": code, "name": f"TEST_cat_{code}", "cost_center": "CC-TEST-2"},
            timeout=20,
        )
        assert r2.status_code in (200, 204), f"{r2.status_code} {r2.text[:200]}"
        rows2 = admin.get(f"{BASE}/api/procurement/master/categories", timeout=20).json()
        found2 = next((c for c in rows2 if c["id"] == cid), None)
        assert found2.get("cost_center") == "CC-TEST-2", f"update did not persist: {found2}"

        # cleanup
        admin.delete(f"{BASE}/api/procurement/master/categories/{cid}", timeout=20)


# ─── 4) Site master & inv_categories exist for dropdowns ──────────────────
class TestMastersForDropdowns:
    def test_sites_list(self, admin):
        r = admin.get(f"{BASE}/api/sites", timeout=20)
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        # allow empty (fresh DB) but must not error
        assert isinstance(rows, list)

    def test_inv_categories_list(self, admin):
        r = admin.get(f"{BASE}/api/procurement/master/categories", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) > 0

    def test_project_requests_types(self, admin):
        r = admin.get(f"{BASE}/api/project-requests/types", timeout=20)
        assert r.status_code == 200
        types = {t["key"] for t in r.json()}
        # required for Service/Payment dialog routing selector
        assert {"fuel", "accommodation", "insurance"}.issubset(types)
