"""Iter 160 — Project Request Center merge (Manpower + Cost Center + Item detail fields).

Coverage:
 1. GET /project-requests/types includes 'manpower' with dept=hr, not stockable/payment.
 2. GET /cost-centers?project_id= returns list.
 3. Create PPE request w/ per-item size/make/item_type/tech_details → persists.
 4. Create Manpower request (est value = 0 OK, items = designation lines w/ period).
 5. Manpower approve (super_admin) → status=with_dept, owning_dept=hr.
    - fulfil blocked for a stores role, allowed for hr_executive / super_admin.
 6. Cost-center preference: payment request w/ cost_center_id → fulfil → auto-booked
    project_expense uses THAT cost center (not project default).
 7. Regression: stock-check endpoint, material shortfall→approve→raise-pr, export.xlsx.
"""
from __future__ import annotations
import os
import uuid
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE = ln.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE}/api"

CREDS = {
    "admin": ("admin@erp.com", "Admin@123"),
    "pm": ("test_pm@erp.com", "PM@12345"),
    "store": ("store@erp.com", "Store@1234"),
}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def sess():
    out = {}
    for k, (e, p) in CREDS.items():
        try:
            out[k] = _login(e, p)
        except AssertionError as ex:
            out[k] = None
            print(f"skip {k}: {ex}")
    return out


@pytest.fixture(scope="module")
def project(sess):
    r = sess["admin"].get(f"{API}/projects", timeout=30)
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert rows, "need a seeded project"
    # prefer one with cost_centers (use working endpoint /procurement/master/cost-centers)
    for p in rows:
        r = sess["admin"].get(f"{API}/procurement/master/cost-centers",
                              params={"project_id": p["id"]}, timeout=30)
        if r.status_code == 200:
            cc = r.json()
            if isinstance(cc, list) and cc:
                return {"row": p, "cost_centers": cc}
    return {"row": rows[0], "cost_centers": []}


@pytest.fixture(scope="module")
def state():
    return {}


# ── 1. types includes 'manpower' ──────────────────────────────────
def test_types_includes_manpower(sess):
    r = sess["admin"].get(f"{API}/project-requests/types")
    assert r.status_code == 200, r.text
    types = r.json()
    m = next((t for t in types if t["key"] == "manpower"), None)
    assert m is not None, f"'manpower' missing in types: {[t['key'] for t in types]}"
    assert m["dept"] == "hr"
    assert m["stockable"] is False
    assert m["payment"] is False


# ── 2. cost-centers listing ───────────────────────────────────────
def test_cost_centers_list(sess, project):
    # Try the path the frontend uses (/api/cost-centers) first; fall back to
    # /procurement/master/cost-centers which is the actual mounted path.
    r_short = sess["admin"].get(f"{API}/cost-centers",
                                params={"project_id": project["row"]["id"]})
    r_full = sess["admin"].get(f"{API}/procurement/master/cost-centers",
                               params={"project_id": project["row"]["id"]})
    assert r_full.status_code == 200, r_full.text
    assert isinstance(r_full.json(), list)
    # Alias check — frontend RaiseRequest dialog calls /api/cost-centers
    assert r_short.status_code == 200, (
        f"FRONTEND path /api/cost-centers returns {r_short.status_code}; "
        f"cost-center dropdown in RaiseRequest dialog will be empty. "
        f"Working path is /api/procurement/master/cost-centers.")


# ── 3. PPE request w/ per-item detail fields ─────────────────────
def test_create_ppe_persists_item_details(sess, project, state):
    if not sess["pm"]:
        pytest.skip("PM login unavailable")
    payload = {
        "project_id": project["row"]["id"],
        "request_type": "ppe",
        "priority": "high",
        "need_by": "2026-12-31",
        "description": "TEST_iter160 PPE with per-item details",
        "site_location": "Site Block A",
        "items": [{
            "name": "TEST_iter160 Helmet",
            "quantity": 5, "unit": "Nos", "rate": 250,
            "size": "L", "make": "Karam",
            "item_type": "Ratchet", "tech_details": "ISI IS 2925 Class-A",
        }],
    }
    if project["cost_centers"]:
        payload["cost_center_id"] = project["cost_centers"][0]["id"]
    r = sess["pm"].post(f"{API}/project-requests", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    state["ppe_id"] = d["id"]
    assert d["request_type"] == "ppe"
    assert d["site_location"] == "Site Block A"
    if project["cost_centers"]:
        assert d["cost_center_id"] == project["cost_centers"][0]["id"]
        assert d.get("cost_center_label")
    it = d["items"][0]
    assert it["size"] == "L"
    assert it["make"] == "Karam"
    assert it["item_type"] == "Ratchet"
    assert it["tech_details"] == "ISI IS 2925 Class-A"

    # verify via GET list
    got = sess["admin"].get(f"{API}/project-requests", params={"project_code": d["project_code"]}).json()
    row = next(r for r in got if r["id"] == d["id"])
    assert row["items"][0]["size"] == "L"


# ── 4. Manpower request — est=0 allowed, items are designation lines ──
def test_create_manpower_request(sess, project, state):
    if not sess["pm"]:
        pytest.skip("PM login unavailable")
    payload = {
        "project_id": project["row"]["id"],
        "request_type": "manpower",
        "priority": "medium",
        "period_from": "2026-02-01",
        "period_to": "2026-03-01",
        "site_location": "Tower B",
        "description": "TEST_iter160 manpower request",
        "items": [
            {"name": "Rigger", "quantity": 4, "unit": "Nos", "rate": 0,
             "specs": "3 yrs experience, height work"},
            {"name": "Foreman", "quantity": 1, "unit": "Nos", "rate": 0},
        ],
    }
    r = sess["pm"].post(f"{API}/project-requests", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    state["manpower_id"] = d["id"]
    assert d["request_type"] == "manpower"
    assert d["owning_dept"] == "hr"
    assert d["is_payment"] is False
    assert d["is_stockable"] is False
    assert float(d["est_value"]) == 0  # zero allowed
    assert d["status"] == "pending_approval"
    assert d["period_from"] == "2026-02-01"
    assert d["site_location"] == "Tower B"


# ── 5. Manpower approve → with_dept; fulfil roles ─────────────────
def test_manpower_approve_and_fulfil_roles(sess, state):
    rid = state.get("manpower_id")
    if not rid:
        pytest.skip("no manpower request")
    # approve as super_admin (satisfies dept_head step)
    r = sess["admin"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "ok"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "with_dept"
    assert d["owning_dept"] == "hr"

    # store role must be blocked
    if sess.get("store"):
        rf = sess["store"].post(f"{API}/project-requests/{rid}/fulfil", json={"remarks": "no"})
        assert rf.status_code == 403, f"store role should NOT fulfil hr request, got {rf.status_code} {rf.text[:200]}"

    # super_admin fulfils (hr allowed)
    rf = sess["admin"].post(f"{API}/project-requests/{rid}/fulfil", json={"remarks": "hired"})
    assert rf.status_code == 200, rf.text
    assert rf.json()["status"] == "fulfilled"
    # manpower is NOT payment → no expense booked
    assert rf.json().get("expense_id") in (None, "")


# ── 6. Cost-center preference on auto-booked expense ──────────────
def test_cost_center_preference_on_payment_fulfil(sess, project, state):
    if not sess["pm"]:
        pytest.skip("PM login unavailable")
    if len(project["cost_centers"]) < 1:
        pytest.skip("project has no cost centers — cannot verify preference")
    # pick a NON-default (last) cost center
    chosen = project["cost_centers"][-1]
    payload = {
        "project_id": project["row"]["id"],
        "request_type": "accommodation",  # payment
        "priority": "medium",
        "amount": 12345,
        "vendor": "TEST_iter160 Hotel",
        "cost_center_id": chosen["id"],
        "site_location": "Camp 1",
        "description": "TEST_iter160 accom w/ chosen CC",
    }
    r = sess["pm"].post(f"{API}/project-requests", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    rid = d["id"]
    assert d["cost_center_id"] == chosen["id"]
    assert d["is_payment"] is True

    # approve (est > threshold likely triggers >1 step; loop while pending)
    for _ in range(4):
        row = sess["admin"].get(f"{API}/project-requests", params={"project_code": d["project_code"]}).json()
        row = next(x for x in row if x["id"] == rid)
        if row["status"] != "pending_approval":
            break
        ra = sess["admin"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "ok"})
        assert ra.status_code == 200, ra.text

    row = sess["admin"].get(f"{API}/project-requests").json()
    row = next(x for x in row if x["id"] == rid)
    assert row["status"] == "with_dept", f"got {row['status']}"

    # fulfil as super_admin → expense created
    rf = sess["admin"].post(f"{API}/project-requests/{rid}/fulfil", json={"remarks": "paid vendor"})
    assert rf.status_code == 200, rf.text
    d2 = rf.json()
    assert d2["status"] == "fulfilled"
    exp_id = d2.get("expense_id")
    assert exp_id, "expense_id should be set for payment type"

    # verify project_expense uses the chosen CC, not project default
    exps = sess["admin"].get(f"{API}/project-expenses").json()
    if isinstance(exps, dict):
        exps = exps.get("items") or exps.get("expenses") or []
    exp = next((e for e in exps if e["id"] == exp_id), None)
    assert exp is not None, "expense not found in list"
    assert exp.get("cost_center_id") == chosen["id"], \
        f"CC mismatch: expected {chosen['id']}, got {exp.get('cost_center_id')}"


# ── 7. Regression: stock-check + material shortfall→raise-pr ─────
def test_stock_check_endpoint(sess, project):
    if not sess["pm"]:
        pytest.skip()
    r = sess["pm"].post(f"{API}/project-requests/stock-check", json={
        "project_id": project["row"]["id"],
        "request_type": "material",
        "items": [{"name": f"NONEXISTENT_{uuid.uuid4().hex[:6]}", "quantity": 100}],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["lines"][0]["shortfall"] == 100
    assert d["any_short"] is True
    assert d["all_in_stock"] is False


def test_material_shortfall_raise_pr(sess, project, state):
    if not sess["pm"]:
        pytest.skip()
    uniq = uuid.uuid4().hex[:6]
    payload = {
        "project_id": project["row"]["id"],
        "request_type": "material",
        "priority": "medium",
        "items": [{"name": f"TEST_iter160_short_{uniq}", "quantity": 25, "rate": 100, "specs": "GI pipe"}],
    }
    r = sess["pm"].post(f"{API}/project-requests", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    rid = d["id"]
    # approve chain to with_dept
    for _ in range(4):
        row = sess["admin"].get(f"{API}/project-requests").json()
        row = next(x for x in row if x["id"] == rid)
        if row["status"] != "pending_approval":
            break
        ra = sess["admin"].post(f"{API}/project-requests/{rid}/approve", json={})
        assert ra.status_code == 200

    row = sess["admin"].get(f"{API}/project-requests").json()
    row = next(x for x in row if x["id"] == rid)
    assert row["status"] == "with_dept"

    # raise-pr
    rp = sess["admin"].post(f"{API}/project-requests/{rid}/raise-pr")
    assert rp.status_code == 200, rp.text
    pr = rp.json()
    assert pr["pr_number"].startswith("PR")
    assert pr["items"] >= 1
    state["pr_number"] = pr["pr_number"]


def test_export_xlsx(sess):
    r = sess["admin"].get(f"{API}/project-requests/export.xlsx")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers.get("content-type", "")
    assert len(r.content) > 200


def test_export_pdf(sess):
    r = sess["admin"].get(f"{API}/project-requests/export.pdf")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
