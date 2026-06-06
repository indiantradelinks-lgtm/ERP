"""Iter 63 — Universal Approval Documents Gate
Tests that every approval insertion enforces:
  - at least 1 reference document, OR
  - documents_not_required=True with reason >= 5 chars.

Covers: quotation send, generic /api/approvals, PR submit, resource-request
submit, quotation-builder submit, vendor submit (auto-N/A), client submit
(auto-N/A), and the reject + re-send gate.
"""
import os
import time
import pytest
import requests

def _read_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""

BASE_URL = _read_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}


# ───────────────────────── fixtures ─────────────────────────
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def site_id(admin_session):
    r = admin_session.get(f"{API}/sites", timeout=20)
    assert r.status_code == 200
    sites = r.json()
    sites_list = sites if isinstance(sites, list) else sites.get("items", [])
    assert sites_list, "no sites seeded — cannot generate enquiry"
    return sites_list[0]["id"]


@pytest.fixture
def draft_quote(admin_session, site_id):
    """Create an enquiry which auto-generates a draft quote, then return q_id."""
    body = {
        "site_id": site_id,
        "service_type": "sales",
        "scope_of_work": "TEST_iter63_docs_gate",
        "priority": "medium",
    }
    r = admin_session.post(f"{API}/enquiries", json=body, timeout=20)
    assert r.status_code in (200, 201), f"enquiry create failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    q_id = data.get("quotation_id") or data.get("quote_id")
    if not q_id:
        # fall back: look up by enquiry_no
        enq_no = data.get("enquiry_no") or data.get("enquiry_number")
        qr = admin_session.get(f"{API}/quotations", params={"enquiry_no": enq_no}, timeout=20)
        qs = qr.json() if qr.status_code == 200 else []
        qs_list = qs if isinstance(qs, list) else qs.get("items", [])
        assert qs_list, f"no auto-quote found for enquiry {enq_no}"
        q_id = qs_list[0]["id"]
    return q_id


# ───────────────────────── Quotation gate ─────────────────────────
class TestQuotationSendForApprovalGate:
    def test_a_block_when_empty_body(self, admin_session, draft_quote):
        r = admin_session.post(f"{API}/quotations/{draft_quote}/send-for-approval",
                                json={}, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        assert "Reference documents are required" in r.text or "Attach at least one" in r.text

    def test_b_block_when_na_reason_too_short(self, admin_session, draft_quote):
        r = admin_session.post(f"{API}/quotations/{draft_quote}/send-for-approval",
                                json={"documents_not_required": True,
                                      "documents_not_required_reason": "no"}, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        assert "min 5 characters" in r.text or "short reason" in r.text

    def test_c_accept_when_na_with_valid_reason(self, admin_session, draft_quote):
        r = admin_session.post(f"{API}/quotations/{draft_quote}/send-for-approval",
                                json={"documents_not_required": True,
                                      "documents_not_required_reason": "Internal allocation, no external docs needed"},
                                timeout=20)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
        body = r.json()
        ap = body.get("approval") or body
        assert ap.get("documents_not_required") is True
        assert (ap.get("documents_not_required_reason") or "").startswith("Internal allocation")
        assert ap.get("documents") == []

    def test_d_accept_when_documents_provided(self, admin_session, draft_quote):
        r = admin_session.post(f"{API}/quotations/{draft_quote}/send-for-approval",
                                json={"documents": ["file_abc", "file_def"]},
                                timeout=20)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
        body = r.json()
        ap = body.get("approval") or body
        docs = ap.get("documents") or []
        assert len(docs) == 2
        assert {d["file_id"] for d in docs} == {"file_abc", "file_def"}
        for d in docs:
            assert d.get("source") == "upload"
        assert ap.get("documents_not_required") in (False, None)


# ───────────────────────── Generic /api/approvals gate ─────────────────────────
class TestGenericApprovalsCreateGate:
    def test_block_without_docs(self, admin_session):
        r = admin_session.post(
            f"{API}/approvals",
            json={"type": "expense", "title": "TEST_iter63 expense", "amount": 500},
            timeout=20,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
        # tolerant: should mention either docs required or NA reason
        msg = r.text
        assert ("Reference documents are required" in msg) or ("Attach at least one" in msg)

    def test_accept_with_na_reason(self, admin_session):
        r = admin_session.post(
            f"{API}/approvals",
            json={"type": "expense", "title": "TEST_iter63 expense ok", "amount": 500,
                  "documents_not_required": True,
                  "documents_not_required_reason": "Petty cash, no invoices yet"},
            timeout=20,
        )
        # accept either 200 or 201 depending on router
        assert r.status_code in (200, 201), f"got {r.status_code}: {r.text[:300]}"


# ───────────────────────── Purchase Requisition gate ─────────────────────────
class TestPurchaseRequisitionSubmitGate:
    def _create_pr(self, sess):
        body = {
            "department": "Procurement",
            "priority": "medium",
            "items": [{
                "name": "TEST_iter63 bolts", "quantity": 10, "uom": "pcs",
                "unit_price": 12,
            }],
            "submit_for_approval": False,
        }
        r = sess.post(f"{API}/procurement/prs", json=body, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"PR create unavailable: {r.status_code} {r.text[:200]}")
        return r.json().get("id") or r.json().get("pr_id")

    def test_pr_submit_blocks_without_docs(self, admin_session):
        pr_id = self._create_pr(admin_session)
        r = admin_session.post(f"{API}/procurement/prs/{pr_id}/submit", json={}, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

    def test_pr_submit_accepts_with_na(self, admin_session):
        pr_id = self._create_pr(admin_session)
        r = admin_session.post(
            f"{API}/procurement/prs/{pr_id}/submit",
            json={"documents_not_required": True,
                  "documents_not_required_reason": "Internal stock replenishment"},
            timeout=20,
        )
        assert r.status_code in (200, 201), f"got {r.status_code}: {r.text[:300]}"


# ───────────────────────── Resource Request gate ─────────────────────────
class TestResourceRequestSubmitGate:
    def _create_rr(self, sess):
        # need a real project_id
        pr = sess.get(f"{API}/projects", timeout=20)
        if pr.status_code != 200:
            pytest.skip(f"projects list unavailable: {pr.status_code}")
        items = pr.json() if isinstance(pr.json(), list) else pr.json().get("items", [])
        if not items:
            pytest.skip("no projects seeded for RR test")
        body = {
            "project_id": items[0]["id"],
            "resource_type": "manpower",
            "item_name": "TEST_iter63 RR helper",
            "quantity": 2,
            "priority": "medium",
        }
        r = sess.post(f"{API}/ops/resource-requests", json=body, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"RR create unavailable: {r.status_code} {r.text[:200]}")
        return r.json().get("id") or r.json().get("request_id")

    def test_rr_submit_blocks_without_docs(self, admin_session):
        rid = self._create_rr(admin_session)
        r = admin_session.post(f"{API}/ops/resource-requests/{rid}/submit", json={}, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

    def test_rr_submit_accepts_with_na(self, admin_session):
        rid = self._create_rr(admin_session)
        r = admin_session.post(
            f"{API}/ops/resource-requests/{rid}/submit",
            json={"documents_not_required": True,
                  "documents_not_required_reason": "Verbal request from site"},
            timeout=20,
        )
        assert r.status_code in (200, 201), f"got {r.status_code}: {r.text[:300]}"


# ───────────────────────── Quotation Builder gate ─────────────────────────
class TestQuotationBuilderSubmitGate:
    def _create_qb(self, sess):
        body = {
            "client_name": "TEST_iter63 client",
            "project_name": "TEST_iter63 project",
            "items": [{"description": "Scaffolding 100 sqm", "qty": 1, "unit_price": 1000}],
        }
        r = sess.post(f"{API}/quotation-builder", json=body, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"QB create unavailable: {r.status_code} {r.text[:200]}")
        return r.json().get("id")

    def test_qb_submit_blocks_without_docs(self, admin_session):
        qid = self._create_qb(admin_session)
        if not qid:
            pytest.skip("QB id missing in response")
        r = admin_session.post(f"{API}/quotation-builder/{qid}/submit-for-approval",
                                json={}, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"


# ───────────────────────── Vendor auto-N/A ─────────────────────────
class TestVendorAutoNA:
    def test_vendor_submit_auto_marks_na(self, admin_session):
        # Vendor master requires: name, PAN/GST, at least one category, address, bank account
        ts = int(time.time() * 1000) % 10_000_000
        # PAN format: 5 letters + 4 digits + 1 letter, must be globally unique
        pan = f"TEST{ts:07d}X"[:10].upper()
        # Ensure first 5 chars are letters (replace digits with letters if any leaked)
        pan = "ZIT" + pan[3:]
        vbody = {
            "name": f"TEST_iter63 Vendor {ts}",
            "categories": ["scaffolding"],
            "contact_email": f"test_iter63_v{ts}@example.com",
            "contact_phone": "9999999999",
            "pan": pan,
            "addresses": [{
                "label": "HQ", "line1": "TEST address line 1",
                "city": "Mumbai", "state": "Maharashtra", "country": "India",
                "postal_code": "400001",
            }],
            "bank_accounts": [{
                "bank_name": "TEST Bank", "account_name": "TEST Vendor",
                "account_number": "1234567890", "ifsc": "TEST0001234",
            }],
        }
        r = admin_session.post(f"{API}/vendors", json=vbody, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"Vendor create unavailable: {r.status_code} {r.text[:200]}")
        vid = r.json().get("id") or r.json().get("vendor_id")
        r2 = admin_session.post(f"{API}/vendors/{vid}/submit", timeout=20)
        assert r2.status_code in (200, 201), f"got {r2.status_code}: {r2.text[:300]}"
        approval_id = r2.json().get("approval_id")
        assert approval_id
        # verify approval doc reflects auto-N/A
        ar = admin_session.get(f"{API}/approvals/{approval_id}", timeout=20)
        assert ar.status_code == 200, ar.text[:200]
        ad = ar.json()
        assert ad.get("documents_not_required") is True
        assert ad.get("documents_not_required_reason") == "KYC documents attached to vendor master record"


# ───────────────────────── Client auto-N/A ─────────────────────────
class TestClientAutoNA:
    def test_client_submit_auto_marks_na(self, admin_session):
        cbody = {
            "name": f"TEST_iter63 Client {int(time.time())}",
            "contact_email": "test_iter63_client@example.com",
            "contact_phone": "9988776655",
        }
        r = admin_session.post(f"{API}/clients", json=cbody, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"Client create unavailable: {r.status_code} {r.text[:200]}")
        cid = r.json().get("id") or r.json().get("client_id")
        r2 = admin_session.post(f"{API}/clients/{cid}/submit", timeout=20)
        if r2.status_code == 404:
            pytest.skip("Client submit endpoint not present")
        assert r2.status_code in (200, 201), f"got {r2.status_code}: {r2.text[:300]}"
        approval_id = r2.json().get("approval_id")
        if not approval_id:
            pytest.skip("No approval_id on client submit response")
        ar = admin_session.get(f"{API}/approvals/{approval_id}", timeout=20)
        ad = ar.json()
        assert ad.get("documents_not_required") is True
        assert ad.get("documents_not_required_reason") == "KYC documents attached to client master record"


# ───────────────────────── Reject + re-send gate (iter 62.1) ─────────────────────────
class TestRejectAndResendGate:
    def test_reject_then_resend_enforces_gate(self, admin_session, draft_quote):
        # 1. send with N/A reason
        r = admin_session.post(
            f"{API}/quotations/{draft_quote}/send-for-approval",
            json={"documents_not_required": True,
                  "documents_not_required_reason": "Initial submission, docs pending"},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:200]
        approval_id = (r.json().get("approval") or {}).get("id") or r.json().get("approval_id")
        assert approval_id

        # 2. approve step 1 (super_admin can act)
        r1 = admin_session.post(
            f"{API}/approvals/{approval_id}/action",
            json={"action": "approve", "comment": "step1 ok"}, timeout=20,
        )
        assert r1.status_code in (200, 201), f"step1 approve failed: {r1.status_code} {r1.text[:200]}"

        # 3. reject step 2
        r2 = admin_session.post(
            f"{API}/approvals/{approval_id}/action",
            json={"action": "reject", "comment": "Needs more info"}, timeout=20,
        )
        assert r2.status_code in (200, 201), f"step2 reject failed: {r2.status_code} {r2.text[:200]}"

        # 4. re-send WITHOUT docs → must 400
        rr = admin_session.post(
            f"{API}/quotations/{draft_quote}/send-for-approval",
            json={}, timeout=20,
        )
        assert rr.status_code == 400, f"expected 400 on re-send, got {rr.status_code}: {rr.text[:200]}"

        # 5. re-send WITH docs → must succeed and produce new approval
        rr2 = admin_session.post(
            f"{API}/quotations/{draft_quote}/send-for-approval",
            json={"documents": ["file_resend_1"]},
            timeout=20,
        )
        assert rr2.status_code == 200, f"expected 200 on re-send, got {rr2.status_code}: {rr2.text[:200]}"
        new_id = (rr2.json().get("approval") or {}).get("id")
        assert new_id and new_id != approval_id, "expected a NEW approval id after re-send"
