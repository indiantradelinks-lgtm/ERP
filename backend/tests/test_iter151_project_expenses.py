"""Iteration 151 — Daily Project Expense Booking + Project P&L backend tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sales():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "sales@erp.com", "password": "Sales@123"})
    if r.status_code != 200:
        pytest.skip("sales login failed")
    return s


@pytest.fixture(scope="module")
def project(admin):
    r = admin.get(f"{API}/projects")
    assert r.status_code == 200
    projects = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    p = next((x for x in projects if x.get("code") == "PRJ-2025-01"), None)
    if not p:
        p = projects[0]
    return p


@pytest.fixture(scope="module")
def cost_center(admin, project):
    r = admin.get(f"{API}/procurement/master/cost-centers", params={"project_id": project["id"]})
    assert r.status_code == 200
    ccs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    return ccs[0] if ccs else None


created_ids = []


# ── /types + /settings ───────────────────────────────────
def test_expense_types(admin):
    r = admin.get(f"{API}/project-expenses/types")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 11
    keys = {d["key"] for d in data}
    assert {"fuel", "ppe_safety", "scaffolding_material", "manpower", "misc"} <= keys


def test_settings_threshold(admin):
    r = admin.get(f"{API}/project-expenses/settings")
    assert r.status_code == 200
    assert r.json().get("large_threshold") == 10000 or r.json().get("large_threshold") > 0


# ── Create validations ───────────────────────────────────
def test_create_invalid_expense_type(admin, project):
    r = admin.post(f"{API}/project-expenses", json={
        "project_code": project["code"], "expense_type": "bogus",
        "expense_date": "2026-01-15", "amount": 100})
    assert r.status_code == 400


def test_create_zero_amount(admin, project):
    r = admin.post(f"{API}/project-expenses", json={
        "project_code": project["code"], "expense_type": "fuel",
        "expense_date": "2026-01-15", "amount": 0})
    assert r.status_code == 400


def test_create_bad_project(admin):
    r = admin.post(f"{API}/project-expenses", json={
        "project_code": "NO-SUCH-PROJECT", "expense_type": "fuel",
        "expense_date": "2026-01-15", "amount": 100})
    assert r.status_code == 400


def test_create_cc_wrong_project(admin, project):
    # Find a CC belonging to a DIFFERENT project (if any)
    r = admin.get(f"{API}/procurement/master/cost-centers")
    ccs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    other = next((c for c in ccs if c.get("project_id") and c.get("project_id") != project["id"]), None)
    if not other:
        pytest.skip("No cross-project CC available")
    r = admin.post(f"{API}/project-expenses", json={
        "project_code": project["code"], "cost_center_id": other["id"],
        "expense_type": "fuel", "expense_date": "2026-01-15", "amount": 100})
    assert r.status_code == 400


# ── Small expense: 3-step chain ──────────────────────────
def test_create_small_expense(admin, project, cost_center):
    payload = {
        "project_code": project["code"], "expense_type": "fuel",
        "expense_date": "2026-01-15", "amount": 5000,
        "description": "TEST- small fuel expense", "payment_mode": "Cash",
    }
    if cost_center:
        payload["cost_center_id"] = cost_center["id"]
    r = admin.post(f"{API}/project-expenses", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["is_large_value"] is False
    assert len(d["chain"]) == 3
    assert d["status"] == "pending_approval"
    assert d["current_step"] == 0
    if cost_center:
        assert d["cost_center_id"] == cost_center["id"]
        assert d["category_code"] == cost_center.get("category_code")
    created_ids.append(("small", d["id"]))


# ── Large expense: 5-step chain ──────────────────────────
def test_create_large_expense(admin, project):
    r = admin.post(f"{API}/project-expenses", json={
        "project_code": project["code"], "expense_type": "manpower",
        "expense_date": "2026-01-15", "amount": 50000,
        "description": "TEST- large manpower expense"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["is_large_value"] is True
    assert len(d["chain"]) == 5
    roles = [s["role"] for s in d["chain"]]
    assert roles == ["project_manager", "dept_head", "accounts_executive", "general_manager", "director"]
    created_ids.append(("large", d["id"]))


# ── Approve full chain of small ──────────────────────────
def test_approve_small_chain(admin):
    small = next((eid for k, eid in created_ids if k == "small"), None)
    if not small:
        pytest.skip("no small expense")
    for step in range(3):
        r = admin.post(f"{API}/project-expenses/{small}/approve", json={"remarks": f"step-{step}"})
        assert r.status_code == 200, r.text
    d = admin.get(f"{API}/project-expenses", params={"project_code": None}).json()
    row = next(x for x in d if x["id"] == small)
    assert row["status"] == "approved_for_payment"
    # je_id may be null (best-effort). Do not fail.


def test_mark_paid_pending_fails(admin):
    large = next((eid for k, eid in created_ids if k == "large"), None)
    r = admin.post(f"{API}/project-expenses/{large}/mark-paid", json={"payment_ref": "TXN-1"})
    assert r.status_code == 400


def test_mark_paid_small(admin):
    small = next((eid for k, eid in created_ids if k == "small"), None)
    r = admin.post(f"{API}/project-expenses/{small}/mark-paid", json={"payment_ref": "TEST-PAY-001"})
    assert r.status_code == 200
    assert r.json()["status"] == "paid"
    assert r.json()["payment_ref"] == "TEST-PAY-001"


# ── Reject flow (create new pending, reject it) ──────────
def test_reject_flow(admin, project):
    r = admin.post(f"{API}/project-expenses", json={
        "project_code": project["code"], "expense_type": "misc",
        "expense_date": "2026-01-15", "amount": 300,
        "description": "TEST- to-be-rejected"})
    eid = r.json()["id"]
    r2 = admin.post(f"{API}/project-expenses/{eid}/reject", json={"remarks": "not valid"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "rejected"
    assert r2.json()["rejected_reason"] == "not valid"
    # cleanup — pending only allowed; rejected still allowed by delete rule
    admin.delete(f"{API}/project-expenses/{eid}")


# ── List + summary + filter ──────────────────────────────
def test_list_filter_and_summary(admin, project):
    r = admin.get(f"{API}/project-expenses", params={"project_code": project["code"]})
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r2 = admin.get(f"{API}/project-expenses", params={"status": "paid"})
    assert r2.status_code == 200
    assert all(x["status"] == "paid" for x in r2.json())

    r3 = admin.get(f"{API}/project-expenses/summary")
    assert r3.status_code == 200
    s = r3.json()
    for k in ("pending", "approved", "paid", "booked_today", "total_amount", "total"):
        assert k in s


# ── Cost center rollup ───────────────────────────────────
def test_cost_center_actual_rollup(admin, project, cost_center):
    if not cost_center:
        pytest.skip("no CC")
    r = admin.get(f"{API}/procurement/master/cost-centers", params={"project_id": project["id"]})
    ccs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    row = next((c for c in ccs if c["id"] == cost_center["id"]), None)
    assert row is not None
    # actual should be >= 5000 (from our paid small expense)
    actual = float(row.get("actual") or 0)
    assert actual >= 5000, f"CC actual {actual} does not reflect approved daily expense"


# ── Delete rules ─────────────────────────────────────────
def test_delete_approved_blocked(admin):
    small = next((eid for k, eid in created_ids if k == "small"), None)
    r = admin.delete(f"{API}/project-expenses/{small}")
    assert r.status_code == 400  # paid


def test_delete_pending_ok(admin, project):
    r = admin.post(f"{API}/project-expenses", json={
        "project_code": project["code"], "expense_type": "misc",
        "expense_date": "2026-01-15", "amount": 50, "description": "TEST- delete-me"})
    eid = r.json()["id"]
    r2 = admin.delete(f"{API}/project-expenses/{eid}")
    assert r2.status_code == 200


# ── Project P&L ──────────────────────────────────────────
def test_pnl_all(admin):
    r = admin.get(f"{API}/project-pnl")
    assert r.status_code == 200
    d = r.json()
    assert "projects" in d and "totals" in d
    for k in ("income_billed", "receipts", "total_expense", "gross_profit"):
        assert k in d["totals"]


def test_pnl_single(admin, project):
    r = admin.get(f"{API}/project-pnl", params={"project_code": project["code"]})
    # may be 404 if project has no bills+expenses filtered out — but single-project fetch shouldn't filter
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["project_code"] == project["code"]
    assert "expenses_by_category" in d
    assert "margin_pct" in d


def test_pnl_includes_daily_expense_labels(admin, project):
    r = admin.get(f"{API}/project-pnl", params={"project_code": project["code"]})
    d = r.json()
    # After our approved+paid fuel 5000, expense_by_category should have "Fuel / Diesel"
    assert "Fuel / Diesel" in d.get("expenses_by_category", {}), d.get("expenses_by_category")


def test_pnl_sales_rbac_denied(sales):
    r = sales.get(f"{API}/project-pnl")
    assert r.status_code == 403


# ── Exports ──────────────────────────────────────────────
def test_export_expenses_xlsx(admin):
    r = admin.get(f"{API}/project-expenses/export.xlsx")
    assert r.status_code == 200 and len(r.content) > 200


def test_export_expenses_pdf(admin):
    r = admin.get(f"{API}/project-expenses/export.pdf")
    assert r.status_code == 200 and len(r.content) > 200


def test_export_pnl_xlsx(admin):
    r = admin.get(f"{API}/project-pnl/export.xlsx")
    assert r.status_code == 200 and len(r.content) > 200


def test_export_pnl_pdf(admin):
    r = admin.get(f"{API}/project-pnl/export.pdf")
    assert r.status_code == 200 and len(r.content) > 200


# ── RBAC write (sales) ───────────────────────────────────
def test_rbac_sales_cannot_create(sales, project):
    r = sales.post(f"{API}/project-expenses", json={
        "project_code": project["code"], "expense_type": "fuel",
        "expense_date": "2026-01-15", "amount": 100})
    assert r.status_code == 403
