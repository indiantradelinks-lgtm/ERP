"""Backend tests for Enquiry Follow-Up Tracker (iteration 144 bugfix)."""
import os, requests, datetime
BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")


def _login():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


def test_inbox_all_returns_rows_with_bucket():
    s = _login()
    r = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] > 0, "expected open enquiries in preview DB"
    for row in data["rows"][:5]:
        assert "_bucket" in row
        assert row["_bucket"] in ("no_date", "today", "upcoming", "overdue")


def test_dashboard_consistent():
    s = _login()
    r = s.get(f"{BASE}/api/enquiry-followups/dashboard")
    assert r.status_code == 200
    d = r.json()
    for k in ("open", "due_today", "overdue"):
        assert k in d and isinstance(d[k], int)
    inbox = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()
    # open should match inbox count (both count open enquiries)
    assert d["open"] == inbox["count"], f"open kpi {d['open']} vs inbox count {inbox['count']}"


def test_upcoming_view_after_scheduling():
    s = _login()
    inbox = s.get(f"{BASE}/api/enquiry-followups/inbox?view=all").json()
    assert inbox["count"] > 0
    enq = inbox["rows"][0]
    future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    r = s.post(f"{BASE}/api/enquiries/{enq['id']}/followups", json={
        "mode": "Call", "remarks": "TEST_backend regression schedule", "next_followup_date": future
    })
    assert r.status_code in (200, 201), r.text[:200]
    up = s.get(f"{BASE}/api/enquiry-followups/inbox?view=upcoming").json()
    assert up["count"] >= 1
    assert any(row["id"] == enq["id"] for row in up["rows"]), "scheduled enquiry not in upcoming"


def test_export_xlsx_ok():
    s = _login()
    r = s.get(f"{BASE}/api/enquiry-followups/export.xlsx?view=all")
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "octet-stream" in ct or "excel" in ct.lower(), ct
