"""Iter 173 — PO Preview/Edit, PR-mandatory, 4-level approval, amendment cycle, PDF, Service Orders."""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")


@pytest.fixture(scope="session")
def creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    assert "admin@erp.com" in content
    return {"email": "admin@erp.com", "password": "Admin@123"}


@pytest.fixture(scope="session")
def client(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def pr_number(client):
    r = client.get(f"{BASE_URL}/api/procurement/prs", timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert rows, "no PRs available"
    return rows[0]["pr_number"]


@pytest.fixture(scope="session")
def created(client):
    ids = {"pos": [], "sos": []}
    yield ids
    for po_id in ids["pos"]:
        client.delete(f"{BASE_URL}/api/approvals?record_id={po_id}", timeout=30)
        client.delete(f"{BASE_URL}/api/purchase-orders/{po_id}", timeout=30)
    for so_id in ids["sos"]:
        client.delete(f"{BASE_URL}/api/procurement-extras/service-orders/{so_id}", timeout=30)


def _po_payload(pr=None):
    d = {
        "vendor": "TEST_ITER173 VENDOR",
        "items": [{"name": "TEST_ITER173 Item A", "quantity": 2, "rate": 1000, "unit": "Nos", "gst_pct": 18}],
        "amount": 2000,
        "notes": "TEST_ITER173",
    }
    if pr:
        d["pr_number"] = pr
    return d


# ── PR mandatory on PO create ────────────────────────────────────────────────
def test_po_create_without_pr_rejected(client):
    r = client.post(f"{BASE_URL}/api/purchase-orders", json=_po_payload(), timeout=60)
    assert r.status_code == 400, r.text[:300]
    assert "without a PR" in str(r.json().get("detail", ""))


def test_po_create_with_pr_forces_draft(client, pr_number, created):
    r = client.post(f"{BASE_URL}/api/purchase-orders", json=_po_payload(pr_number), timeout=60)
    assert r.status_code in (200, 201), r.text[:400]
    po = r.json()
    assert po["status"] == "draft"
    assert po["pr_number"] == pr_number
    assert po.get("pr_id")
    assert po.get("revision") == 0
    created["pos"].append(po["id"])
    # GET verify persistence
    g = client.get(f"{BASE_URL}/api/purchase-orders/{po['id']}", timeout=60)
    assert g.status_code == 200
    assert g.json()["status"] == "draft"
    assert "_id" not in g.json()


# ── Items edit: GST types, per-item pct, extra fields ─────────────────────────
def test_items_update_cgst_sgst_split(client, created):
    po_id = created["pos"][0]
    payload = {
        "items": [
            {"name": "TEST_ITER173 Item A", "quantity": 2, "rate": 1000, "gst_pct": 18,
             "make": "TATA", "technical_specs": "IS 2062 Grade"},
            {"name": "TEST_ITER173 Item B", "quantity": 4, "rate": 500, "gst_pct": 12},
        ],
        "gst_type": "cgst_sgst",
        "delivery_terms": "Within 10 days",
        "special_terms": "Test special",
        "other_terms": "Test other",
    }
    r = client.put(f"{BASE_URL}/api/procurement/pos/{po_id}/items", json=payload, timeout=60)
    assert r.status_code == 200, r.text[:400]
    po = r.json()
    assert po["amount"] == 4000.0
    assert po["gst_amount"] == 600.0          # 360 + 240
    assert po["total"] == 4600.0
    assert po["cgst_amount"] == 300.0 and po["sgst_amount"] == 300.0
    assert po["igst_amount"] == 0.0
    assert po["items"][0]["gst_amount"] == 360.0 and po["items"][0]["line_total"] == 2360.0
    assert po["items"][0]["make"] == "TATA"
    assert po["items"][0]["technical_specs"] == "IS 2062 Grade"
    assert po["delivery_terms"] == "Within 10 days"
    g = client.get(f"{BASE_URL}/api/purchase-orders/{po_id}", timeout=60).json()
    assert g["total"] == 4600.0 and g["special_terms"] == "Test special" and g["other_terms"] == "Test other"


def test_items_update_igst(client, created):
    po_id = created["pos"][0]
    payload = {"items": [{"name": "TEST_ITER173 Item A", "quantity": 2, "rate": 1000, "gst_pct": 18},
                         {"name": "TEST_ITER173 Item B", "quantity": 4, "rate": 500, "gst_pct": 12}],
               "gst_type": "igst"}
    r = client.put(f"{BASE_URL}/api/procurement/pos/{po_id}/items", json=payload, timeout=60)
    assert r.status_code == 200, r.text[:400]
    po = r.json()
    assert po["igst_amount"] == 600.0
    assert po["cgst_amount"] == 0.0 and po["sgst_amount"] == 0.0
    assert po["total"] == 4600.0


def test_items_zero_qty_or_rate_rejected(client, created):
    po_id = created["pos"][0]
    r = client.put(f"{BASE_URL}/api/procurement/pos/{po_id}/items",
                   json={"items": [{"name": "Zero Qty", "quantity": 0, "rate": 100}]}, timeout=60)
    assert r.status_code == 400 and "Data missing" in str(r.json()["detail"])
    r2 = client.put(f"{BASE_URL}/api/procurement/pos/{po_id}/items",
                    json={"items": [{"name": "Zero Rate", "quantity": 1, "rate": 0}]}, timeout=60)
    assert r2.status_code == 400 and "Data missing" in str(r2.json()["detail"])


def test_submit_with_zero_items_rejected(client, pr_number, created):
    r = client.post(f"{BASE_URL}/api/purchase-orders",
                    json={"vendor": "TEST_ITER173 ZERO", "pr_number": pr_number,
                          "items": [{"name": "Bad", "quantity": 0, "rate": 0}], "amount": 0}, timeout=60)
    assert r.status_code in (200, 201), r.text[:300]
    po_id = r.json()["id"]
    created["pos"].append(po_id)
    s = client.post(f"{BASE_URL}/api/procurement/pos/{po_id}/submit", json={}, timeout=60)
    assert s.status_code == 400, s.text[:300]
    assert "Data missing" in str(s.json()["detail"])


# ── Submit → approval chain ──────────────────────────────────────────────────
def test_submit_creates_approval(client, created):
    po_id = created["pos"][0]
    r = client.post(f"{BASE_URL}/api/procurement/pos/{po_id}/submit", json={}, timeout=60)
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["status"] == "pending_approval"
    approval_id = body["approval_id"]
    assert approval_id
    created["approval_id"] = approval_id
    lst = client.get(f"{BASE_URL}/api/approvals", timeout=60).json()
    rows = lst if isinstance(lst, list) else lst.get("items", [])
    match = [a for a in rows if a["id"] == approval_id]
    assert match, "approval not in GET /api/approvals"
    assert match[0]["type"] == "purchase_order"
    assert len(match[0]["chain"]) == 4, f"expected 4-level chain, got {match[0]['chain']}"


def test_locked_po_edit_blocked(client, created):
    po_id = created["pos"][0]
    r = client.put(f"{BASE_URL}/api/procurement/pos/{po_id}/items",
                   json={"items": [{"name": "X", "quantity": 1, "rate": 10}]}, timeout=60)
    assert r.status_code == 400 and "editing is locked" in str(r.json()["detail"])
    r2 = client.put(f"{BASE_URL}/api/purchase-orders/{po_id}", json={"notes": "hack"}, timeout=60)
    assert r2.status_code == 400 and "editing is locked" in str(r2.json()["detail"])


def _approve_all(client, approval_id, steps=6):
    for _ in range(steps):
        a = client.get(f"{BASE_URL}/api/approvals/{approval_id}", timeout=60)
        assert a.status_code == 200, a.text[:200]
        if a.json().get("status") not in ("pending", "in_progress"):
            return a.json()
        r = client.post(f"{BASE_URL}/api/approvals/{approval_id}/action",
                        json={"action": "approve", "comment": "ok"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
    return client.get(f"{BASE_URL}/api/approvals/{approval_id}", timeout=60).json()


def test_full_approval_sets_po_approved(client, created):
    approval_id = created["approval_id"]
    final = _approve_all(client, approval_id)
    assert final["status"] == "approved", final.get("status")
    po = client.get(f"{BASE_URL}/api/purchase-orders/{created['pos'][0]}", timeout=60).json()
    assert po["status"] == "approved", po["status"]


# ── Amendment cycle ─────────────────────────────────────────────────────────
def test_amendment_short_reason_rejected(client, created):
    po_id = created["pos"][0]
    r = client.post(f"{BASE_URL}/api/procurement/pos/{po_id}/request-amendment",
                    json={"reason": "abc"}, timeout=60)
    assert r.status_code == 400 and "min 5" in str(r.json()["detail"])


def test_amendment_flow_unlocks_and_bumps_revision(client, created):
    po_id = created["pos"][0]
    r = client.post(f"{BASE_URL}/api/procurement/pos/{po_id}/request-amendment",
                    json={"reason": "Rate revision agreed with vendor"}, timeout=60)
    assert r.status_code == 200, r.text[:400]
    am_id = r.json()["approval_id"]
    assert r.json()["amendment_status"] == "requested"
    am = client.get(f"{BASE_URL}/api/approvals/{am_id}", timeout=60).json()
    assert am["type"] == "po_amendment"
    assert len(am["chain"]) == 2, am["chain"]
    final = _approve_all(client, am_id)
    assert final["status"] == "approved"
    po = client.get(f"{BASE_URL}/api/purchase-orders/{po_id}", timeout=60).json()
    assert po["status"] == "amendment_in_progress", po["status"]
    assert po["amendment_status"] == "unlocked", po.get("amendment_status")
    # now editable
    e = client.put(f"{BASE_URL}/api/procurement/pos/{po_id}/items",
                   json={"items": [{"name": "TEST_ITER173 Item A", "quantity": 3, "rate": 1200, "gst_pct": 18}],
                         "gst_type": "cgst_sgst"}, timeout=60)
    assert e.status_code == 200, e.text[:400]
    assert e.json()["amount"] == 3600.0
    # resubmit → rev 1
    s = client.post(f"{BASE_URL}/api/procurement/pos/{po_id}/submit", json={}, timeout=60)
    assert s.status_code == 200, s.text[:400]
    assert s.json()["revision"] == 1
    po2 = client.get(f"{BASE_URL}/api/purchase-orders/{po_id}", timeout=60).json()
    assert po2["status"] == "pending_approval"
    assert po2["revision"] == 1
    assert len(po2.get("amendments") or []) == 1
    assert po2["amendments"][0]["reason"] == "Rate revision agreed with vendor"
    created["rev1_approval_id"] = s.json()["approval_id"]


def test_pdf_shows_amendment_banner(client, created):
    po_id = created["pos"][0]
    r = client.get(f"{BASE_URL}/api/procurement/pos/{po_id}/pdf", timeout=90)
    assert r.status_code == 200, r.text[:200]
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000
    try:
        from pypdf import PdfReader
    except Exception:
        pytest.skip("pypdf not available for text extraction")
    import io
    text = "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages)
    norm = re.sub(r"\s+", " ", text)
    assert "REVISION 1" in norm.upper(), norm[:600]
    assert "AMENDED PURCHASE ORDER" in norm.upper()
    assert "CGST" in norm.upper() or "IGST" in norm.upper()


# ── Service Orders ──────────────────────────────────────────────────────────
def _so_payload(**over):
    d = {"vendor_id": "", "service_type": "manpower", "scope_of_work": "TEST_ITER173 SOW",
         "rate_basis": "per_day", "rate": 1000, "quantity": 5, "unit": "day",
         "start_date": "2026-08-01", "end_date": "2026-08-20"}
    d.update(over)
    return d


@pytest.fixture(scope="session")
def vendor_id(client):
    r = client.get(f"{BASE_URL}/api/vendors", timeout=60)
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    ok = [v for v in rows if v.get("status") not in ("blocked", "inactive", "blacklisted")]
    assert ok, "no active vendor"
    return ok[0]["id"]


def test_so_without_pr_rejected(client, vendor_id):
    r = client.post(f"{BASE_URL}/api/procurement-extras/service-orders",
                    json=_so_payload(vendor_id=vendor_id), timeout=60)
    assert r.status_code == 400, r.text[:300]
    assert "without a PR" in str(r.json()["detail"])


def test_so_zero_qty_rate_rejected(client, vendor_id, pr_number):
    r = client.post(f"{BASE_URL}/api/procurement-extras/service-orders",
                    json=_so_payload(vendor_id=vendor_id, pr_number=pr_number, quantity=0), timeout=60)
    assert r.status_code == 400 and "Data missing" in str(r.json()["detail"])
    r2 = client.post(f"{BASE_URL}/api/procurement-extras/service-orders",
                     json=_so_payload(vendor_id=vendor_id, pr_number=pr_number, rate=0), timeout=60)
    assert r2.status_code == 400 and "Data missing" in str(r2.json()["detail"])


def test_so_valid_creates_with_pr_stamped(client, vendor_id, pr_number, created):
    r = client.post(f"{BASE_URL}/api/procurement-extras/service-orders",
                    json=_so_payload(vendor_id=vendor_id, pr_number=pr_number), timeout=60)
    assert r.status_code in (200, 201), r.text[:400]
    so = r.json()
    created["sos"].append(so["id"])
    assert so["pr_number"] == pr_number and so.get("pr_id")
    assert so["status"] == "draft"
    assert so["base_amount"] == 5000.0
    g = client.get(f"{BASE_URL}/api/procurement-extras/service-orders/{so['id']}", timeout=60)
    assert g.status_code == 200 and g.json()["pr_number"] == pr_number
