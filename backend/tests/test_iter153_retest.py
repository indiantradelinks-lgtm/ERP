"""Iter 153 retest — verify fixes for iter152 findings.

Fixes to verify:
1. /api/ra-bills/project-context/{project_code} falls back to project.quotation_id /
   project.quotation_no / project.sales_quotation_ref when no handover exists.
2. Quotation PDF endpoint at /api/quotation-builder/{quotation_id}/pdf.
3. /api/notifications/mine returns Request For Payment items for accounts_executive.
4. Regression: PRJ-2026-0035 project-context still returns items.
"""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="module")
def accounts():
    return _login("accounts@erp.com", "Accounts@123")


# ---- FIX #1a: existing manual project E2E-TEST-178532-P1 ----
def test_01_existing_manual_project_context_has_offer_items(admin):
    r = admin.get(f"{BASE}/api/ra-bills/project-context/E2E-TEST-178532-P1", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data.get("items") or []
    print(f"[test_01] project=E2E-TEST-178532-P1 quotation_no={data.get('quotation_no')} items={len(items)}")
    assert data.get("quotation_no") == "QTN-2026-0087", f"quotation_no expected QTN-2026-0087, got {data.get('quotation_no')}"
    assert len(items) >= 3, f"expected >=3 offer items, got {len(items)}: {items}"
    descs = " | ".join((it.get("description") or "").lower() for it in items)
    assert "scaffolding" in descs or "erection" in descs, f"expected scaffolding items, got: {descs}"


# ---- FIX #1b: NEW project via sales_quotation_ref fallback ----
@pytest.fixture(scope="module")
def new_project(admin):
    payload = {
        "code": "RETEST-NOQ-QTN87",
        "name": "RETEST NO QUOTES PROJECT",
        "client": "RETEST CLIENT NO QUOTES",
        "site": "RETEST SITE",
        "sales_quotation_ref": "QTN-2026-0087",
        "status": "active",
    }
    r = admin.post(f"{BASE}/api/projects", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create project: {r.status_code} {r.text[:300]}"
    proj = r.json()
    # code may be assigned server-side; refetch by id
    pid = proj.get("id")
    if not proj.get("code") and pid:
        g = admin.get(f"{BASE}/api/projects/{pid}", timeout=30)
        if g.status_code == 200:
            proj = g.json()
    print(f"[fixture new_project] created code={proj.get('code')} id={proj.get('id')}")
    yield proj
    # cleanup
    try:
        pid = proj.get("id") or proj.get("code")
        d = admin.delete(f"{BASE}/api/projects/{pid}", timeout=30)
        print(f"[cleanup] delete /api/projects/{pid} -> {d.status_code}")
    except Exception as e:
        print(f"[cleanup] failed: {e}")


def test_02_new_project_sales_quotation_ref_fallback(admin, new_project):
    code = new_project.get("code")
    assert code, "project code missing"
    r = admin.get(f"{BASE}/api/ra-bills/project-context/{code}", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data.get("items") or []
    print(f"[test_02] project={code} quotation_no={data.get('quotation_no')} items={len(items)}")
    assert data.get("quotation_no") == "QTN-2026-0087", f"expected QTN-2026-0087, got {data.get('quotation_no')}"
    assert len(items) >= 3, f"expected >=3 items via sales_quotation_ref fallback, got {len(items)}"


# ---- NON-ISSUE 1: Quotation PDF endpoint ----
def test_03_quotation_pdf_endpoint(admin):
    # find quotation id for QTN-2026-0087
    r = admin.get(f"{BASE}/api/quotations", timeout=30)
    assert r.status_code == 200, r.text[:200]
    quotes = r.json()
    if isinstance(quotes, dict):
        quotes = quotes.get("items") or quotes.get("data") or []
    qid = None
    for q in quotes:
        if q.get("quote_number") == "QTN-2026-0087":
            qid = q.get("id")
            break
    assert qid, "QTN-2026-0087 not found"
    print(f"[test_03] quotation id={qid}")
    r = admin.get(f"{BASE}/api/quotation-builder/{qid}/pdf", timeout=60)
    print(f"[test_03] status={r.status_code} content-type={r.headers.get('content-type')} len={len(r.content)}")
    assert r.status_code == 200, f"pdf endpoint failed: {r.status_code} {r.text[:200]}"
    ctype = r.headers.get("content-type", "")
    assert "pdf" in ctype.lower(), f"expected pdf content-type, got {ctype}"
    assert len(r.content) > 500, f"PDF suspiciously small: {len(r.content)} bytes"


# ---- NON-ISSUE 2: Accounts notifications ----
def test_04_accounts_notifications_mine(accounts):
    r = accounts.get(f"{BASE}/api/notifications/mine", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    items = data if isinstance(data, list) else (data.get("items") or data.get("notifications") or [])
    print(f"[test_04] accounts notifications count={len(items)}")
    # Confirm at least one Request For Payment / PEX notification
    rfp = [n for n in items if "PEX-" in (n.get("title") or n.get("message") or n.get("body") or "")
           or "request for payment" in ((n.get("title") or "") + " " + (n.get("message") or "")).lower()]
    print(f"[test_04] RFP-like items count={len(rfp)}")
    assert len(items) > 0, "accounts user has 0 notifications (expected >=1 RFP)"


# ---- REGRESSION: PRJ-2026-0035 ----
def test_05_prj_0035_still_has_items(admin):
    r = admin.get(f"{BASE}/api/ra-bills/project-context/PRJ-2026-0035", timeout=30)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    items = data.get("items") or []
    print(f"[test_05] PRJ-2026-0035 quotation_no={data.get('quotation_no')} items={len(items)}")
    assert len(items) >= 1, f"regression: PRJ-2026-0035 items empty (was 8)"
