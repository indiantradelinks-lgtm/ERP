"""Iteration 154 — Project Request Center (unified 9-type request workflow) tests."""
from __future__ import annotations
import os
import io
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

CREDS = {
    "admin": ("admin@erp.com", "Admin@123"),
    "pm": ("test_pm@erp.com", "PM@12345"),
    "dh_ops": ("depthead.ops@erp.com", "DeptHead@123"),
    "gm": ("gm@erp.com", "GM@12345"),
    "director": ("director@erp.com", "Director@123"),
    "accounts": ("accounts@erp.com", "Accounts@123"),
    "sales": ("sales@erp.com", "Sales@123"),
}


def login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def sess():
    out = {}
    for k, (e, p) in CREDS.items():
        try:
            out[k] = login(e, p)
        except AssertionError as ex:
            out[k] = None
            print(f"skip login {k}: {ex}")
    return out


@pytest.fixture(scope="module")
def project_code(sess):
    # pick any existing project (prefer PRJ-2025-01 if exists)
    r = sess["admin"].get(f"{API}/projects", timeout=30)
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert rows, "no projects seeded"
    for p in rows:
        if p.get("code") == "PRJ-2025-01":
            return p["code"]
    return rows[0].get("code")


# --- 1. request types ---
def test_types(sess):
    r = sess["admin"].get(f"{API}/project-requests/types", timeout=30)
    assert r.status_code == 200
    data = r.json()
    keys = {d["key"] for d in data}
    assert keys == {"material", "ppe", "it_material", "accommodation", "fuel",
                    "insurance", "vehicle_manpower", "vehicle_material", "one_time_vehicle"}
    by = {d["key"]: d for d in data}
    assert by["material"]["dept"] == "stores" and by["material"]["stockable"] is True and by["material"]["payment"] is False
    assert by["vehicle_manpower"]["dept"] == "logistics" and by["vehicle_manpower"]["payment"] is True
    assert by["fuel"]["dept"] == "admin" and by["fuel"]["payment"] is True
    assert by["ppe"]["stockable"] is True
    assert by["insurance"]["stockable"] is False


# --- 2. stock check ---
def test_stock_check(sess, project_code):
    payload = {"project_code": project_code, "request_type": "material",
               "items": [{"name": "Pen and Paper", "quantity": 5},
                         {"name": "ZZZ_UnknownItemXYZ", "quantity": 3}]}
    r = sess["admin"].post(f"{API}/project-requests/stock-check", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["lines"]) == 2
    l1, l2 = d["lines"]
    # Pen and Paper (qty 75 on hand) should be in stock
    assert l1["in_stock"] is True and l1["shortfall"] == 0 and l1["on_hand"] >= 5
    assert l2["in_stock"] is False and l2["shortfall"] == 3
    assert d["any_short"] is True and d["all_in_stock"] is False


# module-scoped store of created request ids for downstream reuse
STATE = {}


def test_create_material_small_pm(sess, project_code):
    if not sess.get("pm"):
        pytest.skip("no pm")
    payload = {"project_code": project_code, "request_type": "material",
               "description": "TEST_iter154 small material",
               "items": [{"name": "Pen and Paper", "quantity": 2, "rate": 100},
                         {"name": "ZZZ_UnknownItemXYZ", "quantity": 3, "rate": 50}]}
    r = sess["pm"].post(f"{API}/project-requests", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["owning_dept"] == "stores"
    assert d["status"] == "pending_approval"
    assert len(d["chain"]) == 1 and d["chain"][0]["role"] == "dept_head"
    assert d["is_stockable"] is True
    assert d["stock_lines"] and any(l["shortfall"] > 0 for l in d["stock_lines"])
    STATE["material_id"] = d["id"]


def test_create_vehicle_large_pm(sess, project_code):
    if not sess.get("pm"):
        pytest.skip("no pm")
    payload = {"project_code": project_code, "request_type": "vehicle_manpower",
               "description": "TEST_iter154 monthly car",
               "vendor": "TEST_VENDOR_X", "vehicle_ref": "Car",
               "monthly_rate": 8000, "months": 6}
    r = sess["pm"].post(f"{API}/project-requests", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["est_value"] == 48000
    assert d["owning_dept"] == "logistics"
    assert d["is_large_value"] is True
    roles = [c["role"] for c in d["chain"]]
    assert roles == ["dept_head", "general_manager", "director"]
    STATE["vehicle_id"] = d["id"]


def test_create_fuel(sess, project_code):
    if not sess.get("pm"):
        pytest.skip("no pm")
    r = sess["pm"].post(f"{API}/project-requests", json={
        "project_code": project_code, "request_type": "fuel", "vehicle_ref": "HR26DK8337",
        "description": "TEST_iter154 fuel", "amount": 5000, "vendor": "TEST_FUEL_STN"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["owning_dept"] == "admin"
    assert d["est_value"] == 5000
    assert len(d["chain"]) == 1  # 5000 < 10000
    STATE["fuel_id"] = d["id"]


def test_non_pm_forbidden(sess, project_code):
    if not sess.get("sales"):
        pytest.skip("no sales")
    r = sess["sales"].post(f"{API}/project-requests", json={
        "project_code": project_code, "request_type": "material",
        "description": "should fail",
        "items": [{"name": "Pen and Paper", "quantity": 1, "rate": 10}]}, timeout=30)
    assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"


# --- 3. approval ---
def test_wrong_role_approve(sess):
    rid = STATE.get("material_id")
    if not rid or not sess.get("gm"):
        pytest.skip("prereq missing")
    r = sess["gm"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "wrong role"}, timeout=30)
    assert r.status_code == 403


def test_approve_small_by_ph(sess):
    rid = STATE.get("material_id")
    if not rid or not sess.get("dh_ops"):
        pytest.skip("prereq missing")
    r = sess["dh_ops"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "ok"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "with_dept"
    assert d["chain"][0]["status"] == "approved"


def test_approve_large_3steps(sess):
    rid = STATE.get("vehicle_id")
    if not rid or not sess.get("dh_ops") or not sess.get("gm") or not sess.get("director"):
        pytest.skip("prereq missing")
    # step 1: dh_ops
    r = sess["dh_ops"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "s1"}, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "pending_approval"
    assert r.json()["current_step"] == 1
    # step 2: gm
    r = sess["gm"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "s2"}, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "pending_approval"
    assert r.json()["current_step"] == 2
    # step 3: director
    r = sess["director"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "s3"}, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "with_dept"


def test_reject_flow(sess, project_code):
    if not sess.get("pm") or not sess.get("dh_ops"):
        pytest.skip("no pm/dh")
    # Raise a temp request to reject
    r = sess["pm"].post(f"{API}/project-requests", json={
        "project_code": project_code, "request_type": "fuel", "vehicle_ref": "HR26DK8337", "amount": 300,
        "description": "TEST_iter154 to_reject"}, timeout=30)
    assert r.status_code == 200
    rid = r.json()["id"]
    r2 = sess["dh_ops"].post(f"{API}/project-requests/{rid}/reject", json={"remarks": "not needed"}, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["status"] == "rejected"
    # cleanup: delete rejected
    d = sess["admin"].delete(f"{API}/project-requests/{rid}", timeout=30)
    assert d.status_code == 200


# --- 4. raise-pr ---
def test_raise_pr(sess):
    rid = STATE.get("material_id")
    if not rid:
        pytest.skip("no material")
    r = sess["admin"].post(f"{API}/project-requests/{rid}/raise-pr", timeout=30)
    assert r.status_code == 200, r.text
    pr_no = r.json()["pr_number"]
    STATE["pr_no"] = pr_no
    # verify PR listed
    prs = sess["admin"].get(f"{API}/procurement/prs", timeout=30).json()
    if isinstance(prs, dict):
        prs = prs.get("items", [])
    found = [p for p in prs if p.get("pr_number") == pr_no]
    assert found and found[0].get("source") == "project_request"


def test_raise_pr_no_shortfall(sess, project_code):
    # Create a request with only in-stock items → raise-pr should 400
    if not sess.get("pm") or not sess.get("dh_ops"):
        pytest.skip()
    r = sess["pm"].post(f"{API}/project-requests", json={
        "project_code": project_code, "request_type": "material",
        "description": "TEST_iter154 no shortfall",
        "items": [{"name": "Pen and Paper", "quantity": 1, "rate": 10}]}, timeout=30)
    assert r.status_code == 200
    rid = r.json()["id"]
    sess["dh_ops"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "ok"}, timeout=30)
    r2 = sess["admin"].post(f"{API}/project-requests/{rid}/raise-pr", timeout=30)
    assert r2.status_code == 400
    STATE["no_short_id"] = rid  # to fulfil later


def test_raise_pr_non_stockable(sess):
    rid = STATE.get("fuel_id")
    if not rid:
        pytest.skip()
    r = sess["admin"].post(f"{API}/project-requests/{rid}/raise-pr", timeout=30)
    assert r.status_code == 400


# --- 5. fulfil ---
def test_fulfil_material_pr_raised(sess):
    rid = STATE.get("material_id")
    if not rid:
        pytest.skip()
    r = sess["admin"].post(f"{API}/project-requests/{rid}/fulfil", json={"remarks": "issued"}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "fulfilled"


def test_fulfil_payment_creates_expense(sess):
    # Approve fuel first (small — one step by dh_ops)
    rid = STATE.get("fuel_id")
    if not rid or not sess.get("dh_ops"):
        pytest.skip()
    a = sess["dh_ops"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "ok"}, timeout=30)
    assert a.status_code == 200 and a.json()["status"] == "with_dept"
    # fulfil as admin (fallback for admin dept — accounts_executive also allowed)
    f = sess["admin"].post(f"{API}/project-requests/{rid}/fulfil", json={"remarks": "paid"}, timeout=30)
    assert f.status_code == 200, f.text
    body = f.json()
    assert body["status"] == "fulfilled"
    assert body.get("expense_id")
    # verify project_expenses row exists
    time.sleep(0.5)
    exps = sess["admin"].get(f"{API}/project-expenses", timeout=30).json()
    if isinstance(exps, dict):
        exps = exps.get("items", exps.get("rows", []))
    match = [e for e in exps if e.get("source_request_id") == rid]
    assert match, "expense from fuel request not found"
    assert match[0]["source"] == "project_request"
    assert match[0]["status"] == "approved_for_payment"
    STATE["fuel_exp_no"] = match[0].get("expense_no")


def test_wrong_dept_role_fulfil(sess, project_code):
    # accounts user (admin dept role) trying to fulfil a STORES material request → 403
    if not sess.get("pm") or not sess.get("dh_ops") or not sess.get("accounts"):
        pytest.skip()
    r = sess["pm"].post(f"{API}/project-requests", json={
        "project_code": project_code, "request_type": "material",
        "description": "TEST_iter154 wrong-dept-fulfil",
        "items": [{"name": "Pen and Paper", "quantity": 1, "rate": 5}]}, timeout=30)
    rid = r.json()["id"]
    sess["dh_ops"].post(f"{API}/project-requests/{rid}/approve", json={"remarks": "ok"}, timeout=30)
    bad = sess["accounts"].post(f"{API}/project-requests/{rid}/fulfil", json={"remarks": "should fail"}, timeout=30)
    assert bad.status_code == 403, f"got {bad.status_code}"
    # cleanup: admin fulfils then close then leave (no delete on fulfilled)
    STATE["cleanup_ids"] = STATE.get("cleanup_ids", []) + [rid]


# --- 6. close & delete ---
def test_close_material(sess):
    rid = STATE.get("material_id")
    if not rid:
        pytest.skip()
    r = sess["admin"].post(f"{API}/project-requests/{rid}/close", timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_delete_only_pending_or_rejected(sess):
    rid = STATE.get("material_id")  # now closed
    if not rid:
        pytest.skip()
    r = sess["admin"].delete(f"{API}/project-requests/{rid}", timeout=30)
    assert r.status_code == 400


# --- 7. filters, summary, exports ---
def test_filters(sess, project_code):
    r = sess["admin"].get(f"{API}/project-requests",
                          params={"project_code": project_code, "request_type": "fuel"}, timeout=30)
    assert r.status_code == 200
    for row in r.json():
        assert row["project_code"] == project_code and row["request_type"] == "fuel"


def test_summary(sess):
    r = sess["admin"].get(f"{API}/project-requests/summary", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for k in ("total", "pending_approval", "with_dept", "fulfilled", "pr_raised", "est_value"):
        assert k in d


def test_exports(sess):
    for fmt in ("xlsx", "pdf"):
        r = sess["admin"].get(f"{API}/project-requests/export.{fmt}", timeout=60)
        assert r.status_code == 200
        assert len(r.content) > 100
        if fmt == "xlsx":
            assert "spreadsheet" in r.headers.get("content-type", "")
        else:
            assert "pdf" in r.headers.get("content-type", "")


# --- 8. notifications for stores after approval ---
def test_notification_created_on_approval(sess):
    # material request path created a notification for stores roles or fallback super_admin
    r = sess["admin"].get(f"{API}/notifications/mine", timeout=30)
    if r.status_code != 200:
        pytest.skip("no notifications endpoint")
    items = r.json()
    if isinstance(items, dict):
        items = items.get("items", [])
    kinds = [n.get("kind") for n in items]
    assert "project_request" in kinds or any("Request" in (n.get("title") or "") for n in items)


def test_payment_notification_accounts(sess):
    if not sess.get("accounts"):
        pytest.skip()
    r = sess["accounts"].get(f"{API}/notifications/mine", timeout=30)
    if r.status_code != 200:
        pytest.skip()
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    exp_no = STATE.get("fuel_exp_no")
    if not exp_no:
        pytest.skip()
    match = [n for n in items if exp_no in (n.get("title") or "") + (n.get("message") or "")]
    assert match, f"no Request For Payment notification for {exp_no}"


# --- 9. cleanup no-shortfall / wrong-dept temp requests: try to close chain to avoid dangling with_dept ---
def test_cleanup(sess):
    for rid in [STATE.get("no_short_id")] + STATE.get("cleanup_ids", []):
        if not rid:
            continue
        sess["admin"].post(f"{API}/project-requests/{rid}/fulfil", json={"remarks": "cleanup"}, timeout=30)
        sess["admin"].post(f"{API}/project-requests/{rid}/close", timeout=30)
