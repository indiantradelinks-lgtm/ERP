"""Iteration 193 tests: Phase-4 server-side paging (7 endpoints) + digest recipients settings + leaderboard extras."""
import os
import pytest
import requests

def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        # fallback: read frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")

BASE = _base()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def pm():
    return _login("test_pm@erp.com", "PM@12345")


# ─────────── Phase-4 paging: 7 endpoints ───────────
PHASE4 = [
    ("/api/inv2/stock-inward-report", "total_value", True),
    ("/api/inv3/material-requests", None, False),  # list endpoint; legacy = plain array
    ("/api/inv3/transfers", None, False),
    ("/api/inv3/pending-returnable", None, True),   # report-shaped
    ("/api/finance/reports/po-commitment", "total_open_commitment", True),
    ("/api/finance/reports/grn-not-billed", "total_open_grni", True),
    ("/api/finance/reports/bill-without-grn", "audit_risk_count", True),
]


@pytest.mark.parametrize("path,summary_key,is_report", PHASE4)
def test_phase4_paging(admin, path, summary_key, is_report):
    # paged call
    r = admin.get(f"{BASE}{path}?page=1&page_size=2", timeout=60)
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
    j = r.json()
    if is_report:
        assert isinstance(j, dict) and "rows" in j and "total" in j and "page" in j and "pages" in j, f"{path}: {list(j)[:10]}"
        assert len(j["rows"]) <= 2
        assert "count" in j
        if summary_key:
            assert summary_key in j, f"{path} missing {summary_key}"
        # un-paged report
        r2 = admin.get(f"{BASE}{path}", timeout=60)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j["count"] == j2["count"], f"{path} count mismatch paged={j['count']} unpaged={j2['count']}"
        if summary_key:
            assert j.get(summary_key) == j2.get(summary_key), f"{path} summary mismatch"
    else:
        # list endpoints: paged returns dict; legacy returns list
        assert isinstance(j, dict) and "rows" in j and "total" in j
        assert len(j["rows"]) <= 2
        r2 = admin.get(f"{BASE}{path}", timeout=60)
        assert r2.status_code == 200
        j2 = r2.json()
        assert isinstance(j2, list), f"{path} legacy expected list got {type(j2)}"


def test_mr_search_narrows(admin):
    """Search narrows totals when a keyword is passed."""
    r = admin.get(f"{BASE}/api/inv3/material-requests?page=1&page_size=2", timeout=60)
    j = r.json()
    total_full = j["total"]
    if total_full == 0:
        pytest.skip("no MRs to search")
    # pick any mr_no from rows if available
    sample = j["rows"][0].get("mr_no") or j["rows"][0].get("request_no") or j["rows"][0].get("project_code")
    if not sample:
        pytest.skip("no sample search key")
    r2 = admin.get(f"{BASE}/api/inv3/material-requests?page=1&page_size=5&search={sample}", timeout=60)
    j2 = r2.json()
    assert j2["total"] <= total_full


def test_mr_status_filter_paging(admin):
    r = admin.get(f"{BASE}/api/inv3/material-requests?status=pending&page=1&page_size=2", timeout=60)
    assert r.status_code == 200
    j = r.json()
    assert isinstance(j, dict) and "rows" in j and "total" in j
    for row in j["rows"]:
        assert row.get("status") == "pending"


def test_inward_date_filter_paging(admin):
    r = admin.get(f"{BASE}/api/inv2/stock-inward-report?date_from=2026-01-01&page=1&page_size=2", timeout=60)
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j and "total" in j and "count" in j


# ─────────── Digest settings ───────────
def test_digest_settings_admin_get(admin):
    r = admin.get(f"{BASE}/api/sales/leaderboard/digest/settings", timeout=30)
    assert r.status_code == 200
    j = r.json()
    for k in ("settings", "roles", "users", "resolved"):
        assert k in j, f"missing {k}"


def test_digest_settings_pm_forbidden(pm):
    r = pm.get(f"{BASE}/api/sales/leaderboard/digest/settings", timeout=30)
    assert r.status_code == 403
    r2 = pm.put(f"{BASE}/api/sales/leaderboard/digest/settings", json={"roles": [], "include_sales_dept_head": False, "user_ids": [], "extra_emails": []}, timeout=30)
    assert r2.status_code == 403


def test_digest_settings_put_and_send(admin):
    # pick any sales-role user id
    getr = admin.get(f"{BASE}/api/sales/leaderboard/digest/settings", timeout=30).json()
    users = getr.get("users") or []
    pick_uid = users[0]["id"] if users else None
    payload = {
        "roles": ["director"],
        "include_sales_dept_head": False,
        "user_ids": [pick_uid] if pick_uid else [],
        "extra_emails": ["ops@example.com", "not-an-email"],
    }
    r = admin.put(f"{BASE}/api/sales/leaderboard/digest/settings", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    saved = j["settings"]
    assert "not-an-email" not in (saved.get("extra_emails") or []), "invalid email should be dropped"
    assert "ops@example.com" in (saved.get("extra_emails") or [])
    resolved = j["resolved"]
    # resolved may be list of emails OR list of dicts with email key
    def _emails(r):
        return [x if isinstance(x, str) else x.get("email") for x in (r or [])]
    remails = _emails(resolved)
    assert "director@erp.com" in remails
    assert "ops@example.com" in remails

    # digest send uses these recipients
    r2 = admin.post(f"{BASE}/api/sales/leaderboard/digest/send?month=2026-08", timeout=60)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert "recipients" in j2
    rec_emails = [x if isinstance(x, str) else x.get("email") for x in (j2["recipients"] or [])]
    assert "director@erp.com" in rec_emails
    assert "ops@example.com" in rec_emails

    # RESTORE defaults
    restore = {"roles": ["sales_manager", "sales_head", "director", "general_manager"],
               "include_sales_dept_head": True, "user_ids": [], "extra_emails": []}
    r3 = admin.put(f"{BASE}/api/sales/leaderboard/digest/settings", json=restore, timeout=30)
    assert r3.status_code == 200


# ─────────── Leaderboard extras ───────────
def test_leaderboard_extras_shape(admin):
    r = admin.get(f"{BASE}/api/sales/leaderboard?month=2026-09", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j
    for row in j["rows"]:
        assert "top_won" in row
        assert "biggest_open_quote" in row
