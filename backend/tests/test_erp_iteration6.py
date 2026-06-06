"""Iteration 6 backend tests — dashboard payload shape + CRUD regressions + attachments flow."""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    # Login may return user object directly or nested under 'user'
    user_obj = data.get("user") if isinstance(data.get("user"), dict) else data
    assert user_obj.get("role") == "super_admin", f"Unexpected login payload: {data}"
    # cookies are set httpOnly; bearer fallback if returned
    token = data.get("token") or data.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# --- Auth ---
def test_auth_me(session):
    r = session.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == ADMIN_EMAIL
    assert me["role"] == "super_admin"


# --- Dashboard payload shape regression ---
def test_dashboard_summary_shape(session):
    r = session.get(f"{API}/dashboard/summary", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    # kpis dict with required keys
    assert isinstance(body.get("kpis"), dict)
    for k in ["revenue", "expenses", "profit", "active_projects", "total_projects",
              "employees", "clients", "vendors", "pending_approvals"]:
        assert k in body["kpis"], f"Missing kpi: {k}"
    # chart_revenue_expense: list of dicts with month/revenue/expense
    cre = body.get("chart_revenue_expense")
    assert isinstance(cre, list) and len(cre) >= 1
    for row in cre:
        assert set(["month", "revenue", "expense"]).issubset(row.keys())
    # project_status uses `status` key
    ps = body.get("project_status")
    assert isinstance(ps, list)
    for row in ps:
        assert "status" in row and "count" in row
    # safety_by_severity uses `severity` key
    sbs = body.get("safety_by_severity")
    assert isinstance(sbs, list)
    for row in sbs:
        assert "severity" in row and "count" in row


# --- CRUD regression: ensure each module returns arrays without 500 ---
@pytest.mark.parametrize("resource", [
    "projects", "vendors", "clients", "employees",
    "assets", "purchase-orders", "quotations",
])
def test_list_endpoints(session, resource):
    r = session.get(f"{API}/{resource}", timeout=20)
    assert r.status_code == 200, f"{resource} -> {r.status_code} {r.text[:200]}"
    body = r.json()
    assert isinstance(body, list), f"{resource} did not return a list"


# --- Attachments flow: upload + list scoped by parent_type/parent_id ---
def test_attachments_upload_and_list(session):
    proj_r = session.get(f"{API}/projects", timeout=20)
    assert proj_r.status_code == 200
    projects = proj_r.json()
    if not projects:
        # create a project so test is self-contained
        c = session.post(f"{API}/projects", json={
            "name": "TEST_attachment_proj", "status": "active", "budget": 1000,
        }, timeout=15)
        assert c.status_code in (200, 201), c.text
        project_id = c.json()["id"]
    else:
        project_id = projects[0]["id"]

    # Upload via POST /api/uploads (multipart) with folder/parent_type/parent_id
    payload = io.BytesIO(b"hello iteration6 attachment payload")
    files = {"file": ("iter6_attach.txt", payload, "text/plain")}
    data = {"folder": "projects", "parent_type": "projects", "parent_id": project_id}
    u = session.post(f"{API}/uploads", files=files, data=data, timeout=30)
    assert u.status_code in (200, 201), f"Upload failed: {u.status_code} {u.text}"
    up = u.json()
    assert up.get("parent_type") == "projects"
    assert up.get("parent_id") == project_id
    file_id = up.get("id")
    assert file_id

    # List via GET /api/files?parent_type=projects&parent_id=<id>
    lf = session.get(f"{API}/files", params={"parent_type": "projects", "parent_id": project_id}, timeout=20)
    assert lf.status_code == 200, lf.text
    listing = lf.json()
    assert isinstance(listing, list)
    assert any(f.get("id") == file_id for f in listing), "Uploaded file not found in list"

    # Cleanup uploaded file
    session.delete(f"{API}/files/{file_id}", timeout=15)
