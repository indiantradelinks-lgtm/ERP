"""Iter 62 — Sales policy: Enquiry-gated Quotation creation,
internal-approval gate on submit, quote↔enquiry status sync,
client+site mandatory on enquiry, PUT field-stripping, reject path.
"""
import os
import pytest
import requests

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # Fallback: read from frontend/.env (test env doesn't export it)
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _load_base_url()
ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    token = r.json().get("token") or r.json().get("access_token")
    if token:
        sess.headers.update({"Authorization": f"Bearer {token}"})
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def a_site_id(s):
    rs = s.get(f"{BASE_URL}/api/sites", timeout=20)
    assert rs.status_code == 200, rs.text
    sites = rs.json()
    assert sites, "Need at least one site seeded"
    return sites[0]["id"]


def _new_enquiry_and_quote(s, site_id, label="reg"):
    payload = {
        "site_id": site_id,
        "service_type": "sales",
        "rfq_type": ["supply"],
        "service_categories": ["scaffolding"],
        "expected_value": 12345.0,
        "scope_of_work": f"TEST_iter62_{label}",
    }
    r = s.post(f"{BASE_URL}/api/enquiries", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["id"] and d["enquiry_no"].startswith("ENQ-")
    assert d.get("quotation_id"), "Auto-quote not linked"
    assert d.get("quotation_no", "").startswith("QTN-")
    return d


# ---------- 1. Direct quotation create blocked ----------
def test_block_direct_quotation_create(s):
    r = s.post(f"{BASE_URL}/api/quotations", json={"client": "TEST_X", "project": "TEST"}, timeout=20)
    assert r.status_code == 400, r.text
    assert "Quotations cannot be created directly" in r.text


# ---------- 2. Enquiry site_id mandatory ----------
def test_enquiry_missing_site_400(s):
    r = s.post(f"{BASE_URL}/api/enquiries", json={"service_type": "sales", "rfq_type": ["supply"]}, timeout=20)
    assert r.status_code == 400
    assert "Site" in r.text


# ---------- 3. Enquiry create auto-generates quote ----------
def test_enquiry_create_auto_quote(s, a_site_id):
    d = _new_enquiry_and_quote(s, a_site_id, "auto")
    assert d.get("client_id"), "client_id must be snapshotted from site"
    assert d.get("customer"), "customer must be resolved"
    # quote visible in list with correct fields
    rq = s.get(f"{BASE_URL}/api/quotations", timeout=20)
    assert rq.status_code == 200
    found = [q for q in rq.json() if q.get("id") == d["quotation_id"]]
    assert found, "Auto-created quote missing in /api/quotations"
    q = found[0]
    assert q.get("status") == "draft"
    assert q.get("enquiry_id") == d["id"]
    assert q.get("enquiry_no") == d["enquiry_no"]
    assert not q.get("approval_status")


# ---------- 4. Submit blocked before approval ----------
def test_submit_blocked_before_approval(s, a_site_id):
    d = _new_enquiry_and_quote(s, a_site_id, "gate")
    r = s.post(f"{BASE_URL}/api/quotations/{d['quotation_id']}/status",
               json={"status": "submitted"}, timeout=20)
    assert r.status_code == 400
    assert "Internal approval is required" in r.text


# ---------- 5,6,7. Send-for-approval + duplicate guard + walk chain + submit + enquiry sync ----------
def test_full_approval_then_submit_and_won_sync(s, a_site_id):
    d = _new_enquiry_and_quote(s, a_site_id, "full")
    qid = d["quotation_id"]
    enq_id = d["id"]

    # Send for approval
    r = s.post(f"{BASE_URL}/api/quotations/{qid}/send-for-approval", json={}, timeout=20)
    assert r.status_code == 200, r.text
    appr = r.json()["approval"]
    aid = appr["id"]
    assert appr["type"] == "quotation"
    assert appr["record_id"] == qid
    assert appr["status"] == "pending"
    assert len(appr["chain"]) >= 2, f"Quotation chain should have ≥2 steps, got {appr['chain']}"

    # Quote reflects pending
    q = s.get(f"{BASE_URL}/api/quotations", timeout=20).json()
    q = next(x for x in q if x["id"] == qid)
    assert q["approval_status"] == "pending"
    assert q["status"] == "under_review"
    assert q.get("approval_id") == aid

    # Duplicate guard
    r2 = s.post(f"{BASE_URL}/api/quotations/{qid}/send-for-approval", json={}, timeout=20)
    assert r2.status_code == 409, r2.text

    # Walk approval chain
    for _ in range(len(appr["chain"]) + 2):
        cur = s.get(f"{BASE_URL}/api/approvals/{aid}", timeout=20).json()
        if cur.get("status") == "approved":
            break
        rr = s.post(f"{BASE_URL}/api/approvals/{aid}/action",
                    json={"action": "approve", "comment": "ok by sdet"}, timeout=20)
        assert rr.status_code == 200, rr.text
    cur = s.get(f"{BASE_URL}/api/approvals/{aid}", timeout=20).json()
    assert cur["status"] == "approved", cur

    # Quote approval_status now approved
    q = next(x for x in s.get(f"{BASE_URL}/api/quotations", timeout=20).json() if x["id"] == qid)
    assert q["approval_status"] == "approved"

    # Now submit succeeds
    r = s.post(f"{BASE_URL}/api/quotations/{qid}/status",
               json={"status": "submitted"}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted"

    # Enquiry should sync to submitted
    enq = s.get(f"{BASE_URL}/api/enquiries/{enq_id}", timeout=20).json()
    assert enq["status"] == "submitted", enq

    # Won transition also syncs
    r = s.post(f"{BASE_URL}/api/quotations/{qid}/status",
               json={"status": "won"}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "won"
    enq = s.get(f"{BASE_URL}/api/enquiries/{enq_id}", timeout=20).json()
    assert enq["status"] == "won"


# ---------- 8. PUT strips server-managed fields ----------
def test_put_strips_server_managed_fields(s, a_site_id):
    d = _new_enquiry_and_quote(s, a_site_id, "put")
    qid = d["quotation_id"]
    before = next(x for x in s.get(f"{BASE_URL}/api/quotations", timeout=20).json() if x["id"] == qid)
    payload = {
        "project": "TEST_iter62 edited project",
        "total": 99999,
        # These must be silently stripped (no error)
        "status": "submitted",
        "approval_status": "approved",
        "enquiry_id": "HACK",
        "enquiry_no": "HACK",
        "root_id": "HACK",
        "revision_no": 99,
    }
    r = s.put(f"{BASE_URL}/api/quotations/{qid}", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["project"] == "TEST_iter62 edited project"
    assert after.get("total") == 99999
    # Server-managed fields untouched
    assert after.get("status") == before.get("status") == "draft"
    assert after.get("approval_status") in (None, before.get("approval_status"))
    assert after.get("enquiry_id") == d["id"]
    assert after.get("enquiry_no") == d["enquiry_no"]
    assert after.get("revision_no") != 99


# ---------- 9. Reject path — quote.approval_status='rejected' but status NOT overwritten to pending_revision ----------
def test_reject_path_quote_status_preserved(s, a_site_id):
    d = _new_enquiry_and_quote(s, a_site_id, "reject")
    qid = d["quotation_id"]
    r = s.post(f"{BASE_URL}/api/quotations/{qid}/send-for-approval", json={}, timeout=20)
    assert r.status_code == 200
    aid = r.json()["approval"]["id"]

    # Reject the FIRST step
    rr = s.post(f"{BASE_URL}/api/approvals/{aid}/action",
                json={"action": "reject", "comment": "Insufficient pricing detail"}, timeout=20)
    assert rr.status_code == 200, rr.text

    appr = s.get(f"{BASE_URL}/api/approvals/{aid}", timeout=20).json()
    # Approval engine terminal-on-reject is 'rejected_revision_required' (creator can resubmit) or 'rejected'
    assert appr["status"] in ("rejected", "rejected_revision_required"), appr

    # Quote.approval_status reflects 'rejected'
    q = next(x for x in s.get(f"{BASE_URL}/api/quotations", timeout=20).json() if x["id"] == qid)
    assert q.get("approval_status") == "rejected", q
    # Pipeline status must NOT be mirrored to 'pending_revision' — should stay under_review
    assert q.get("status") == "under_review", f"Expected status to remain under_review, got {q.get('status')}"
