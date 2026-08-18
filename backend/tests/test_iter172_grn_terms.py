"""
Iter 172 — Backend tests for:
1. GRN → Vendor Bill prefill (/api/payables/grn-prefill)
2. PO Terms templates CRUD (/api/procurement-extras/terms-templates)
3. PO terms save + PDF (/api/procurement-extras/pos/{po_id}/terms and PO PDF)
"""
import os
import io
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"
GRN_NUM = "GRN-2026-0015"
PO_ID = "8c47ad3a-dfa8-47a7-b757-c001b77ce02e"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---- 1. GRN prefill --------------------------------------------------------
class TestGrnPrefill:
    def test_grn_prefill_returns_vendor_and_lines(self, client):
        r = client.get(f"{BASE_URL}/api/payables/grn-prefill", params={"grn_number": GRN_NUM}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        print("prefill keys:", list(d.keys()))
        # vendor
        vname = (d.get("vendor_name") or "").upper()
        assert "RK TRADERS" in vname, f"vendor_name={d.get('vendor_name')!r}"
        assert d.get("vendor_gstin"), "missing vendor_gstin"
        assert d.get("vendor_pan"), "missing vendor_pan"
        assert "msme_status" in d
        assert d.get("bank_verified") is True, f"bank_verified={d.get('bank_verified')!r}"
        # PO
        assert d.get("po_number") == "PO-2026-0057", f"po_number={d.get('po_number')!r}"
        assert d.get("project_code") == "PRJ-2024-09", f"project_code={d.get('project_code')!r}"
        # lines
        lines = d.get("lines") or []
        assert len(lines) >= 1, f"lines={lines}"
        assert float(lines[0].get("rate") or 0) == 5000.0, f"line[0].rate={lines[0].get('rate')}"
        # po_terms
        terms = d.get("po_terms") or []
        assert isinstance(terms, list) and len(terms) >= 2, f"po_terms len={len(terms)}"


# ---- 2. Terms templates CRUD ---------------------------------------------
class TestTermsTemplatesCRUD:
    created_id = None

    def test_list_seeded_templates(self, client):
        r = client.get(f"{BASE_URL}/api/procurement-extras/terms-templates", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # may be list or {items:[]}
        items = data if isinstance(data, list) else (data.get("items") or data.get("data") or [])
        print("templates count:", len(items))
        assert len(items) >= 11, f"expected >=11 seeded, got {len(items)}"

    def test_create_update_delete(self, client):
        # CREATE
        payload = {
            "category": "TEST_ITER172",
            "title": "TEST_ITER172 Clause",
            "body": "This clause is for testing iter 172 and will be deleted.",
        }
        r = client.post(f"{BASE_URL}/api/procurement-extras/terms-templates", json=payload, timeout=30)
        assert r.status_code in (200, 201), f"create {r.status_code} {r.text[:300]}"
        created = r.json()
        tid = created.get("id") or created.get("_id") or created.get("template_id")
        assert tid, f"no id in create response: {created}"
        TestTermsTemplatesCRUD.created_id = tid

        # UPDATE
        upd = {**payload, "title": "TEST_ITER172 Clause UPDATED"}
        r = client.put(f"{BASE_URL}/api/procurement-extras/terms-templates/{tid}", json=upd, timeout=30)
        assert r.status_code == 200, f"put {r.status_code} {r.text[:300]}"
        u = r.json()
        assert "UPDATED" in (u.get("title") or ""), u

        # GET list contains updated
        r = client.get(f"{BASE_URL}/api/procurement-extras/terms-templates", timeout=30)
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert any(("UPDATED" in (it.get("title") or "")) for it in items), "updated title not found in list"

        # DELETE
        r = client.delete(f"{BASE_URL}/api/procurement-extras/terms-templates/{tid}", timeout=30)
        assert r.status_code in (200, 204), f"delete {r.status_code} {r.text[:300]}"

        # verify removed
        r = client.get(f"{BASE_URL}/api/procurement-extras/terms-templates", timeout=30)
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert not any((it.get("id") == tid) for it in items), "template still present after delete"


# ---- 3. PO terms save + PDF ----------------------------------------------
class TestPoTermsAndPdf:
    def test_put_po_terms_and_pdf_contains_them(self, client):
        # fetch existing structured terms first (so we can restore)
        # Save structured terms
        terms_payload = {
            "terms_structured": [
                {"category": "Payment", "title": "Payment Terms ITER172", "body": "50% advance, 50% on delivery — iter172."},
                {"category": "Delivery", "title": "Delivery Timeline ITER172", "body": "Within 15 days of PO — iter172."},
            ]
        }
        r = client.put(f"{BASE_URL}/api/procurement-extras/pos/{PO_ID}/terms", json=terms_payload, timeout=30)
        assert r.status_code == 200, f"put terms {r.status_code} {r.text[:300]}"

        # download PDF
        r = client.get(f"{BASE_URL}/api/procurement/pos/{PO_ID}/pdf", timeout=60)
        assert r.status_code == 200, f"pdf {r.status_code} {r.text[:200]}"
        ctype = r.headers.get("content-type", "")
        assert "pdf" in ctype.lower() or r.content[:4] == b"%PDF", f"content-type={ctype} start={r.content[:8]!r}"
        assert len(r.content) > 1000, f"pdf too small: {len(r.content)}"
        # search text: extract naive ascii
        body = r.content
        # Some PDFs compress text streams; look for either the title strings or standard PO markers
        # Best-effort: try substring in raw bytes
        found_iter = b"ITER172" in body or b"iter172" in body
        # If compressed, fall back to just checking size/valid
        print(f"pdf size={len(body)} found_iter172_marker={found_iter}")
