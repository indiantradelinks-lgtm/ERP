"""Iteration 32 — Procurement Master (categories, items, cost-centers, pr-dropdowns) + PR cost-center stamping."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
E2E_PROJECT_ID = "f2f38e64-fd4a-4b5b-869c-78db3f08be04"


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def sales():
    return _login("sales@erp.com", "Sales@123")


# ─── Categories ─────────────────────────────────────────────────────────────
class TestCategories:
    def test_list_seeded_10(self, admin):
        r = admin.get(f"{API}/procurement/master/categories")
        assert r.status_code == 200
        data = r.json()
        codes = {c["code"] for c in data}
        expected = {"SCAFF", "PAINT", "CONSUM", "PPE", "FAST", "INSUL", "ROOF", "ROPE", "TOOL", "OFFICE"}
        assert expected.issubset(codes), f"missing seeded codes: {expected - codes}"
        for c in data:
            assert "item_count" in c
            assert isinstance(c["item_count"], int)
            assert "_id" not in c

    def test_any_user_can_read(self, sales):
        r = sales.get(f"{API}/procurement/master/categories")
        assert r.status_code == 200

    def test_create_lowercase_code_uppercased(self, admin):
        payload = {"code": "tst32", "name": "TEST_Iter32_Cat", "gst_pct": 12, "default_hsn": "9999"}
        r = admin.post(f"{API}/procurement/master/categories", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == "TST32"
        assert body["name"] == "TEST_Iter32_Cat"
        assert body["gst_pct"] == 12
        assert body["id"]
        pytest.created_cat_id = body["id"]

    def test_duplicate_code_400(self, admin):
        r = admin.post(f"{API}/procurement/master/categories",
                       json={"code": "TST32", "name": "dup"})
        assert r.status_code == 400

    def test_rbac_sales_cannot_write(self, sales):
        r = sales.post(f"{API}/procurement/master/categories",
                       json={"code": "SALESX", "name": "should fail"})
        assert r.status_code in (401, 403), f"sales should not be allowed to write: {r.status_code}"

    def test_update_code_cascade(self, admin):
        cid = pytest.created_cat_id
        # create a linked item
        ir = admin.post(f"{API}/procurement/master/items",
                        json={"code": f"TST32-IT-1", "name": "TEST_iter32_item",
                              "category_id": cid, "unit": "Nos"})
        assert ir.status_code == 200, ir.text
        pytest.created_item_id = ir.json()["id"]
        assert ir.json()["category_code"] == "TST32"
        # rename category
        ur = admin.put(f"{API}/procurement/master/categories/{cid}",
                       json={"code": "tst32r"})
        assert ur.status_code == 200
        assert ur.json()["code"] == "TST32R"
        # verify cascade on item
        itr = admin.get(f"{API}/procurement/master/items", params={"category_id": cid})
        assert itr.status_code == 200
        items = itr.json()
        assert any(i["category_code"] == "TST32R" for i in items), "category_code did not cascade to items"

    def test_delete_with_links_400(self, admin):
        r = admin.delete(f"{API}/procurement/master/categories/{pytest.created_cat_id}")
        assert r.status_code == 400
        assert "Cannot delete" in r.text or "linked" in r.text.lower()

    def test_delete_after_unlink(self, admin):
        # remove the item then delete category
        d = admin.delete(f"{API}/procurement/master/items/{pytest.created_item_id}")
        assert d.status_code == 200
        d2 = admin.delete(f"{API}/procurement/master/categories/{pytest.created_cat_id}")
        assert d2.status_code == 200


# ─── Items ──────────────────────────────────────────────────────────────────
class TestItems:
    def test_create_with_invalid_category_400(self, admin):
        r = admin.post(f"{API}/procurement/master/items",
                       json={"code": "BADCAT-1", "name": "test", "category_id": "does-not-exist"})
        assert r.status_code == 400

    def test_create_autofills_category_meta(self, admin):
        cats = admin.get(f"{API}/procurement/master/categories").json()
        scaff = next(c for c in cats if c["code"] == "SCAFF")
        r = admin.post(f"{API}/procurement/master/items",
                       json={"code": "TST32-SCAFF-X", "name": "TEST_iter32_scaff_item",
                             "category_id": scaff["id"], "unit": "Nos"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["category_code"] == "SCAFF"
        assert b["category_name"] == scaff["name"]
        assert b["hsn_sac"] == scaff["default_hsn"]
        pytest.scaff_item_id = b["id"]

    def test_list_filter_by_category(self, admin):
        cats = admin.get(f"{API}/procurement/master/categories").json()
        scaff = next(c for c in cats if c["code"] == "SCAFF")
        r = admin.get(f"{API}/procurement/master/items", params={"category_id": scaff["id"]})
        assert r.status_code == 200
        for it in r.json():
            assert it["category_id"] == scaff["id"]

    def test_delete_cleanup(self, admin):
        d = admin.delete(f"{API}/procurement/master/items/{pytest.scaff_item_id}")
        assert d.status_code == 200


# ─── Cost Centers ───────────────────────────────────────────────────────────
class TestCostCenters:
    def test_auto_provision_creates_per_category(self, admin):
        r = admin.post(f"{API}/procurement/master/cost-centers/auto-provision/{E2E_PROJECT_ID}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "created" in body and "items" in body
        # could be 0 if already provisioned; verify listing has 10 categories worth
        lr = admin.get(f"{API}/procurement/master/cost-centers",
                       params={"project_id": E2E_PROJECT_ID})
        assert lr.status_code == 200
        rows = lr.json()
        assert len(rows) >= 10
        for r_ in rows:
            assert "committed" in r_ and "actual" in r_ and "remaining" in r_
            assert r_["code"].startswith("CC-")

    def test_auto_provision_idempotent(self, admin):
        r = admin.post(f"{API}/procurement/master/cost-centers/auto-provision/{E2E_PROJECT_ID}")
        assert r.status_code == 200
        assert r.json()["created"] == 0

    def test_manual_create_duplicate_pair_400(self, admin):
        cats = admin.get(f"{API}/procurement/master/categories").json()
        scaff = next(c for c in cats if c["code"] == "SCAFF")
        r = admin.post(f"{API}/procurement/master/cost-centers",
                       json={"project_id": E2E_PROJECT_ID, "category_id": scaff["id"], "budget": 100})
        assert r.status_code == 400


# ─── PR Dropdowns ───────────────────────────────────────────────────────────
class TestPrDropdowns:
    def test_shape(self, admin):
        r = admin.get(f"{API}/procurement/master/pr-dropdowns",
                      params={"project_id": E2E_PROJECT_ID})
        assert r.status_code == 200
        d = r.json()
        for k in ["departments", "projects", "sites", "categories", "items_by_category", "cost_centers"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["departments"], list) and len(d["departments"]) > 0
        assert len(d["projects"]) >= 1
        assert len(d["categories"]) >= 10
        assert isinstance(d["items_by_category"], dict)
        assert len(d["cost_centers"]) >= 10


# ─── PR Create stamps cost_center ───────────────────────────────────────────
class TestPrCostCenterStamp:
    def test_create_pr_stamps_cc(self, admin):
        # Get a category & item to use
        dd = admin.get(f"{API}/procurement/master/pr-dropdowns",
                       params={"project_id": E2E_PROJECT_ID}).json()
        scaff = next(c for c in dd["categories"] if c["code"] == "SCAFF")
        # Need at least one item under SCAFF; create one if missing
        items = dd["items_by_category"].get(scaff["id"], [])
        if not items:
            ir = admin.post(f"{API}/procurement/master/items",
                            json={"code": "TST32-PR-1", "name": "TEST_iter32_pr_item",
                                  "category_id": scaff["id"], "unit": "Nos"})
            assert ir.status_code == 200
            item = ir.json()
        else:
            item = items[0]
        # Find the SCAFF cost center for this project
        cc = next(c for c in dd["cost_centers"] if c["category_code"] == "SCAFF")
        # Now create a PR
        pr_payload = {
            "project_id": E2E_PROJECT_ID,
            "department": "Operations",
            "priority": "medium",
            "required_by": "2026-06-30",
            "items": [{
                "category_id": scaff["id"],
                "item_id": item["id"],
                "item_code": item["code"],
                "name": item["name"],
                "unit": item.get("unit", "Nos"),
                "quantity": 5,
                "estimated_rate": 100,
            }],
        }
        r = admin.post(f"{API}/procurement/prs", json=pr_payload)
        assert r.status_code in (200, 201), f"PR create failed: {r.status_code} {r.text}"
        pr = r.json()
        items_back = pr.get("items", [])
        assert items_back, "PR response has no items"
        it = items_back[0]
        assert it.get("cost_center_id"), f"cost_center_id not stamped: {it}"
        assert it.get("cost_center_code") == cc["code"], \
            f"expected cost_center_code={cc['code']} got {it.get('cost_center_code')}"
