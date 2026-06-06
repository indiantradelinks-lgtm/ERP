"""Backend tests for AI Quotation Builder module (iteration_27).

Covers:
 - Presets catalogue (services / bases / basis fields / preset items)
 - Conditions library (list / filter / CRUD)
 - Company profile (GET/PUT)
 - Quotation CRUD (create / get / update)
 - Recalc tax_mode intra (CGST+SGST) vs inter (IGST)
 - PDF generation, preview JSON
 - Submit-for-approval, send-to-client, status-change flow
 - AI: suggest-items (Claude) and extract-rfq (Gemini)
 - RBAC: sales_executive vs super_admin
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SALES = {"email": "sales@erp.com", "password": "Sales@123"}


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def sales_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=SALES, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"sales login failed: {r.status_code} {r.text}")
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def created_quote(admin_session):
    payload = {
        "client": "TEST_Client Pvt Ltd",
        "client_state": "Gujarat",
        "project": "TEST_Refinery Maintenance",
        "service_categories": ["scaffolding"],
        "rfq_type": ["volume"],
        "sections": [{
            "title": "Cuplock Scaffolding",
            "service": "scaffolding",
            "basis": "volume",
            "items": [
                {"description": "Cuplock erection & dismantling",
                 "quantity": 500, "unit": "Cum", "rate": 250,
                 "discount_pct": 0, "gst_pct": 18, "hsn_sac": "9987"},
                {"description": "Material rental for 30 days",
                 "quantity": 500, "unit": "Cum", "rate": 50,
                 "discount_pct": 5, "gst_pct": 18, "hsn_sac": "9987"},
            ],
        }],
        "technical_conditions": ["Working hours: 8 AM – 6 PM"],
        "commercial_conditions": ["50% advance"],
        "advance_pct": 50,
        "retention_pct": 5,
    }
    r = admin_session.post(f"{API}/quotation-builder", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    return r.json()


# ---------- Presets ----------
class TestPresets:
    def test_presets_payload(self, admin_session):
        r = admin_session.get(f"{API}/quotation-builder/presets", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("services", "bases", "basis_labels", "basis_fields", "preset_items"):
            assert k in data, f"missing key {k}"
        bases = data["bases"]
        # Per spec: scaffolding 9, painting 6, rope_access 6, insulation 7, roof_sheeting 7
        assert len(bases.get("scaffolding", [])) == 9, f"scaffolding bases = {bases.get('scaffolding')}"
        assert len(bases.get("painting", [])) == 6
        assert len(bases.get("rope_access", [])) == 6
        assert len(bases.get("insulation", [])) == 7
        assert len(bases.get("roof_sheeting", [])) == 7


# ---------- Conditions library ----------
class TestConditions:
    def test_seeded_conditions_count(self, admin_session):
        r = admin_session.get(f"{API}/quotation-builder/conditions", timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) >= 51, f"expected >=51 seeded conditions, got {len(rows)}"
        # 4 categories present
        cats = {x.get("category") for x in rows}
        assert {"technical", "commercial", "inclusion", "exclusion"}.issubset(cats), cats

    def test_filter_category_service(self, admin_session):
        r = admin_session.get(
            f"{API}/quotation-builder/conditions",
            params={"category": "technical", "service": "scaffolding"}, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert all(x["category"] == "technical" for x in rows)
        assert all(x["service"] in ("scaffolding", "common") for x in rows)

    def test_condition_crud_admin(self, admin_session):
        payload = {"category": "technical", "service": "common",
                   "text": "TEST_condition automated", "order": 99, "active": True}
        r = admin_session.post(f"{API}/quotation-builder/conditions", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
        # Update
        r2 = admin_session.put(f"{API}/quotation-builder/conditions/{cid}",
                               json={"text": "TEST_condition updated"}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["text"] == "TEST_condition updated"
        # Delete
        r3 = admin_session.delete(f"{API}/quotation-builder/conditions/{cid}", timeout=15)
        assert r3.status_code == 200, r3.text

    def test_sales_cannot_delete_condition(self, sales_session, admin_session):
        # admin creates
        r = admin_session.post(f"{API}/quotation-builder/conditions",
                               json={"category": "inclusion", "service": "common",
                                     "text": "TEST_sales delete", "order": 99}, timeout=15)
        assert r.status_code in (200, 201)
        cid = r.json()["id"]
        # sales attempts delete
        rd = sales_session.delete(f"{API}/quotation-builder/conditions/{cid}", timeout=15)
        assert rd.status_code in (401, 403), f"expected sales to be blocked, got {rd.status_code}"
        # cleanup
        admin_session.delete(f"{API}/quotation-builder/conditions/{cid}", timeout=15)


# ---------- Company profile ----------
class TestCompanyProfile:
    def test_get_company_profile(self, admin_session):
        r = admin_session.get(f"{API}/admin/company-profile", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "INDIAN TRADE LINKS"
        assert data["state"]  # at least set

    def test_update_company_profile(self, admin_session):
        original = admin_session.get(f"{API}/admin/company-profile", timeout=15).json()
        new_city = "TEST_Ahmedabad"
        r = admin_session.put(f"{API}/admin/company-profile",
                              json={**original, "city": new_city}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["city"] == new_city
        # GET to verify persistence
        r2 = admin_session.get(f"{API}/admin/company-profile", timeout=15)
        assert r2.json()["city"] == new_city
        # restore
        admin_session.put(f"{API}/admin/company-profile",
                          json={**original, "city": original.get("city", "")}, timeout=15)

    def test_sales_cannot_write_company_profile(self, sales_session):
        # PUT should be blocked for sales_executive
        rr = sales_session.get(f"{API}/admin/company-profile", timeout=15)
        # read may or may not be allowed; the key is write
        payload = rr.json() if rr.status_code == 200 else {"name": "X"}
        r = sales_session.put(f"{API}/admin/company-profile",
                              json={**payload, "city": "TEST_blocked"}, timeout=15)
        assert r.status_code in (401, 403), f"sales should not write company profile, got {r.status_code}"


# ---------- Quotation CRUD + recalc + PDF ----------
class TestQuotation:
    def test_create_returns_quote_number(self, created_quote):
        q = created_quote
        assert q["id"]
        assert q["quote_number"].startswith("QTN-2026-"), q["quote_number"]
        assert q["status"] == "draft"
        assert "totals" in q and q["totals"].get("grand_total", 0) > 0

    def test_get_full_quotation(self, admin_session, created_quote):
        r = admin_session.get(f"{API}/quotation-builder/{created_quote['id']}", timeout=15)
        assert r.status_code == 200, r.text
        row = r.json()
        assert row["id"] == created_quote["id"]
        assert isinstance(row["sections"], list) and len(row["sections"]) >= 1

    def test_update_recalcs(self, admin_session, created_quote):
        # Add a new section item, expect total to change
        sections = created_quote["sections"]
        sections[0]["items"].append({
            "description": "Extra Item", "quantity": 10, "unit": "Nos",
            "rate": 100, "discount_pct": 0, "gst_pct": 18, "hsn_sac": "9987",
        })
        r = admin_session.put(f"{API}/quotation-builder/{created_quote['id']}",
                              json={"sections": sections}, timeout=20)
        assert r.status_code == 200, r.text
        new_total = r.json()["totals"]["grand_total"]
        assert new_total > created_quote["totals"]["grand_total"]

    def test_recalc_intra_vs_inter(self, admin_session, created_quote):
        # intra: client_state == company_state (Gujarat in our seed and quote)
        r = admin_session.post(f"{API}/quotation-builder/{created_quote['id']}/recalc", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["tax_mode"] == "intra"
        assert data["totals"].get("cgst", 0) > 0 and data["totals"].get("sgst", 0) > 0
        assert data["totals"].get("igst", 0) == 0
        # Switch to inter by changing client_state
        r2 = admin_session.put(f"{API}/quotation-builder/{created_quote['id']}",
                               json={"client_state": "Maharashtra"}, timeout=15)
        assert r2.status_code == 200
        r3 = admin_session.post(f"{API}/quotation-builder/{created_quote['id']}/recalc", timeout=15)
        d3 = r3.json()
        assert d3["tax_mode"] == "inter", d3
        assert d3["totals"].get("igst", 0) > 0
        assert d3["totals"].get("cgst", 0) == 0 and d3["totals"].get("sgst", 0) == 0
        # restore
        admin_session.put(f"{API}/quotation-builder/{created_quote['id']}",
                          json={"client_state": "Gujarat"}, timeout=15)

    def test_tax_mode_locked_honored(self, admin_session, created_quote):
        """When tax_mode_locked=true is sent, recalc must honor stored tax_mode
        even if states would suggest the other mode."""
        qid = created_quote["id"]
        # Set tax_mode explicitly to 'inter' with lock, while client_state=Gujarat (intra by states)
        r = admin_session.put(f"{API}/quotation-builder/{qid}",
                              json={"client_state": "Gujarat", "tax_mode": "inter",
                                    "tax_mode_locked": True}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["tax_mode"] == "inter", f"locked tax_mode not honored: {data.get('tax_mode')}"
        assert data["totals"].get("igst", 0) > 0
        assert data["totals"].get("cgst", 0) == 0
        # Now unlock — should auto-detect intra
        r2 = admin_session.put(f"{API}/quotation-builder/{qid}",
                               json={"tax_mode_locked": False}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["tax_mode"] == "intra", r2.json()

    def test_preview_endpoint(self, admin_session, created_quote):
        r = admin_session.get(f"{API}/quotation-builder/{created_quote['id']}/preview", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "quotation" in data and "company" in data

    def test_pdf_endpoint(self, admin_session, created_quote):
        r = admin_session.get(f"{API}/quotation-builder/{created_quote['id']}/pdf", timeout=30)
        assert r.status_code == 200, r.text
        body = r.content
        assert len(body) > 2048, f"PDF too small: {len(body)} bytes"
        assert body[:4] == b"%PDF", body[:10]


# ---------- Approval + send-to-client + status ----------
class TestWorkflow:
    def test_submit_for_approval(self, admin_session, created_quote):
        r = admin_session.post(f"{API}/quotation-builder/{created_quote['id']}/submit-for-approval", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "under_review"
        assert data.get("approval_id")
        # Verify quote state
        q = admin_session.get(f"{API}/quotation-builder/{created_quote['id']}", timeout=15).json()
        assert q["status"] == "under_review"

    def test_send_to_client(self, admin_session, created_quote):
        payload = {"to_email": "test_recipient@example.com",
                   "subject": "TEST_Subject", "attach_pdf": True}
        r = admin_session.post(f"{API}/quotation-builder/{created_quote['id']}/send-to-client",
                               json=payload, timeout=60)
        # Allow 200 (email sent / queued) OR 502 (email not configured) — should NOT crash
        assert r.status_code in (200, 502), f"unexpected: {r.status_code} {r.text}"
        if r.status_code == 200:
            q = admin_session.get(f"{API}/quotation-builder/{created_quote['id']}", timeout=15).json()
            assert q["status"] == "submitted"

    def test_status_change_won(self, admin_session, created_quote):
        r = admin_session.post(f"{API}/quotation-builder/{created_quote['id']}/status",
                               json={"status": "won", "note": "TEST_awarded"}, timeout=15)
        assert r.status_code == 200, r.text
        # Edit must now be rejected
        r2 = admin_session.put(f"{API}/quotation-builder/{created_quote['id']}",
                               json={"notes": "should fail"}, timeout=15)
        assert r2.status_code == 400, f"expected lock on won quote, got {r2.status_code}"


# ---------- AI endpoints ----------
class TestAI:
    def test_suggest_items(self, admin_session):
        payload = {"service": "scaffolding", "basis": "volume",
                   "scope_text": "Erect 500 m3 of cuplock scaffolding at refinery shutdown"}
        r = admin_session.post(f"{API}/quotation-builder/ai/suggest-items",
                               json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items") or []
        assert len(items) >= 5, f"expected >=5 items, got {len(items)}"
        for it in items[:3]:
            assert "description" in it and it["description"]
            assert "rate" in it and "unit" in it and "gst_pct" in it

    def test_extract_rfq_text(self, admin_session):
        # Build a tiny txt RFQ file in-memory
        text = (
            "M/s ACME Refinery Pvt Ltd\n"
            "RFQ No: ACM/RFQ/2026/0042\n"
            "Date: 2026-01-10\n"
            "Site: Jamnagar Refinery, Gujarat\n"
            "Contact: Mr. Patel, +91-9876543210, patel@acme.in\n"
            "Submission Deadline: 2026-01-25\n\n"
            "Scope of Work:\n"
            "1. Erect 500 m3 of cuplock scaffolding for shutdown maintenance.\n"
            "2. Provide painting of 2000 sqm at heat exchanger surfaces.\n"
            "3. Insulation works as per specifications.\n\n"
            "Payment Terms: 30 days from invoice. Validity: 30 days.\n"
        )
        files = {"file": ("rfq.txt", io.BytesIO(text.encode("utf-8")), "text/plain")}
        # Remove Content-Type so requests sets multipart boundary
        s = requests.Session()
        s.headers.update({k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"})
        r = s.post(f"{API}/quotation-builder/ai/extract-rfq",
                   files=files, cookies=admin_session.cookies, timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
        data = r.json()
        assert data.get("ok") is True
        ext = data.get("extracted") or {}
        assert "scope_of_work" in ext
        assert isinstance(ext.get("line_items"), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
