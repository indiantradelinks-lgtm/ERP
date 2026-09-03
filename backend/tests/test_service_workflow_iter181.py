"""Iteration 181 — Service Request → Payment workflow module.
Covers: RBAC scoping/403s, guard rails (400s), full chain E2E via API and
payment-queue integration (verify → mark-paid → invoice paid / SR closed).
"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"
TAG = uuid.uuid4().hex[:6].upper()


def _login(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    tok = body.get("access_token") or body.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def admin():
    return _login("admin@erp.com", "Admin@123")


@pytest.fixture(scope="session")
def sales():
    return _login("sales@erp.com", "Sales@123")


@pytest.fixture(scope="session")
def meta(admin):
    r = admin.get(f"{API}/service-workflow/meta", timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ───────────────────────── meta / dashboard ─────────────────────────
class TestMetaDashboard:
    def test_meta_shape(self, meta):
        assert isinstance(meta.get("service_categories"), list) and meta["service_categories"]
        assert len(meta.get("vendors") or []) >= 2, "need >=2 vendors for RFQ tests"
        caps = meta.get("role_caps") or {}
        assert caps.get("sr_approver") is True and caps.get("procurement") is True and caps.get("accounts") is True

    def test_dashboard(self, admin):
        r = admin.get(f"{API}/service-workflow/dashboard", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d, dict) and d
        cards = d.get("cards")
        assert isinstance(cards, (dict, list)) and cards, f"no KPI cards: {list(d)}"
        vals = list(cards.values()) if isinstance(cards, dict) else [c.get("value") for c in cards]
        assert len([v for v in vals if isinstance(v, (int, float))]) >= 10, f"expected >=10 KPI tiles, got {len(vals)}"
        assert isinstance(d.get("recent"), list)

    def test_no_mongo_id_leak(self, admin):
        for ep in ("requests", "rfqs", "pos", "srns", "invoices", "payments"):
            r = admin.get(f"{API}/service-workflow/{ep}", timeout=60)
            assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"
            rows = r.json()
            rows = rows if isinstance(rows, list) else rows.get("rows", [])
            for row in rows[:5]:
                assert "_id" not in row, f"{ep} leaks _id"


# ───────────────────────── RBAC ─────────────────────────
class TestRbac:
    def test_sales_meta_caps_false(self, sales):
        r = sales.get(f"{API}/service-workflow/meta", timeout=60)
        assert r.status_code == 200, r.text[:300]
        caps = r.json().get("role_caps") or {}
        assert caps.get("sr_approver") is False
        assert caps.get("procurement") is False
        assert caps.get("accounts") is False

    def test_sales_can_create_own_sr_and_scoped_list(self, admin, sales):
        # admin SR
        a = admin.post(f"{API}/service-workflow/requests", json={
            "service_category": (admin.get(f"{API}/service-workflow/meta").json()["service_categories"][0]),
            "service_description": f"TEST_{TAG} admin scoped SR", "priority": "Medium",
            "estimated_budget": 50000, "submit": True}, timeout=60)
        assert a.status_code in (200, 201), a.text[:300]
        admin_sr = a.json()

        s = sales.post(f"{API}/service-workflow/requests", json={
            "service_category": "Manpower Supply",
            "service_description": f"TEST_{TAG} sales own SR", "priority": "Low",
            "estimated_budget": 10000, "submit": True}, timeout=60)
        assert s.status_code in (200, 201), s.text[:300]
        sales_sr = s.json()
        assert sales_sr["sr_no"].startswith("SVC-")
        assert sales_sr["status"] == "submitted"

        rows = sales.get(f"{API}/service-workflow/requests", timeout=60).json()
        srnos = {r["sr_no"] for r in rows}
        assert sales_sr["sr_no"] in srnos
        assert admin_sr["sr_no"] not in srnos, "sales sees other users' SRs (scoping broken)"

        # 403 on approval action
        act = sales.post(f"{API}/service-workflow/requests/{sales_sr['id']}/action",
                         json={"action": "approve", "remarks": "self"}, timeout=60)
        assert act.status_code == 403, f"expected 403, got {act.status_code} {act.text[:200]}"

        # 403 viewing someone else's SR detail
        det = sales.get(f"{API}/service-workflow/requests/{admin_sr['id']}", timeout=60)
        assert det.status_code == 403, f"expected 403 detail, got {det.status_code}"
        TestRbac.admin_sr = admin_sr
        TestRbac.sales_sr = sales_sr

    def test_sales_cannot_create_rfq(self, admin, sales):
        sr = getattr(TestRbac, "admin_sr", None)
        assert sr, "dependency test did not run"
        admin.post(f"{API}/service-workflow/requests/{sr['id']}/action",
                   json={"action": "approve", "remarks": "ok"}, timeout=60)
        vend = admin.get(f"{API}/service-workflow/meta").json()["vendors"][0]["id"]
        r = sales.post(f"{API}/service-workflow/requests/{sr['id']}/rfq",
                       json={"vendor_ids": [vend]}, timeout=60)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"


# ───────────────────────── Guard rails ─────────────────────────
class TestGuardRails:
    def test_rfq_from_non_approved_sr(self, admin, meta):
        r = admin.post(f"{API}/service-workflow/requests", json={
            "service_category": meta["service_categories"][0],
            "service_description": f"TEST_{TAG} guard draft SR", "submit": False}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        sr = r.json()
        assert sr["status"] == "draft"
        g = admin.post(f"{API}/service-workflow/requests/{sr['id']}/rfq",
                       json={"vendor_ids": [meta["vendors"][0]["id"]]}, timeout=60)
        assert g.status_code == 400, f"expected 400, got {g.status_code} {g.text[:200]}"
        assert "APPROVED" in g.text or "approved" in g.text

    def test_rfq_requires_vendor(self, admin, meta):
        sr = admin.post(f"{API}/service-workflow/requests", json={
            "service_category": meta["service_categories"][0],
            "service_description": f"TEST_{TAG} guard novendor", "submit": True}, timeout=60).json()
        admin.post(f"{API}/service-workflow/requests/{sr['id']}/action",
                   json={"action": "approve", "remarks": "ok"}, timeout=60)
        g = admin.post(f"{API}/service-workflow/requests/{sr['id']}/rfq", json={"vendor_ids": []}, timeout=60)
        assert g.status_code == 400, g.text[:200]

    def test_sr_action_send_back_requires_remarks(self, admin, meta):
        sr = admin.post(f"{API}/service-workflow/requests", json={
            "service_category": meta["service_categories"][0],
            "service_description": f"TEST_{TAG} sendback", "submit": True}, timeout=60).json()
        g = admin.post(f"{API}/service-workflow/requests/{sr['id']}/action",
                       json={"action": "send_back", "remarks": ""}, timeout=60)
        assert g.status_code == 400, g.text[:200]
        ok = admin.post(f"{API}/service-workflow/requests/{sr['id']}/action",
                        json={"action": "send_back", "remarks": "need scope"}, timeout=60)
        assert ok.status_code == 200, ok.text[:200]
        assert ok.json()["status"] == "sent_back"


# ───────────────────────── Full chain + payment integration ─────────────────────────
@pytest.fixture(scope="module")
def chain(request):
    """Build a fresh SR→RFQ→PO→SRN(50%)→Invoice chain as admin."""
    adm = _login("admin@erp.com", "Admin@123")
    m = adm.get(f"{API}/service-workflow/meta", timeout=60).json()
    v1, v2 = m["vendors"][0], m["vendors"][1]
    sr = adm.post(f"{API}/service-workflow/requests", json={
        "service_category": m["service_categories"][0],
        "service_description": f"TEST_{TAG} chain SR", "priority": "High",
        "estimated_budget": 100000, "submit": True}, timeout=60).json()
    adm.post(f"{API}/service-workflow/requests/{sr['id']}/action",
             json={"action": "approve", "remarks": "approved"}, timeout=60)
    rfq = adm.post(f"{API}/service-workflow/requests/{sr['id']}/rfq",
                   json={"vendor_ids": [v1["id"], v2["id"]], "scope_of_work": "chain test"}, timeout=60).json()
    adm.post(f"{API}/service-workflow/rfqs/{rfq['id']}/issue", timeout=60)
    adm.post(f"{API}/service-workflow/rfqs/{rfq['id']}/quotation",
             json={"vendor_id": v1["id"], "amount": 100000, "tax_pct": 18, "timeline_days": 10}, timeout=60)
    adm.post(f"{API}/service-workflow/rfqs/{rfq['id']}/quotation",
             json={"vendor_id": v2["id"], "amount": 120000, "tax_pct": 18, "timeline_days": 8}, timeout=60)
    adm.post(f"{API}/service-workflow/rfqs/{rfq['id']}/recommend",
             json={"vendor_id": v1["id"], "remarks": "L1"}, timeout=60)
    return {"s": adm, "meta": m, "sr": sr, "rfq": rfq, "v1": v1, "v2": v2}


class TestChainAndPayment:
    def test_comparison_l1(self, chain):
        s, rfq = chain["s"], chain["rfq"]
        r = s.get(f"{API}/service-workflow/rfqs/{rfq['id']}/comparison", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["lowest_vendor_id"] == chain["v1"]["id"]
        assert len(d["rows"]) == 2
        assert all(x["has_quote"] for x in d["rows"])

    def test_po_requires_selection_approval(self, chain):
        s, rfq = chain["s"], chain["rfq"]
        r = s.post(f"{API}/service-workflow/rfqs/{rfq['id']}/po",
                   json={"rate": 100000, "quantity": 1, "tax_pct": 18}, timeout=60)
        assert r.status_code == 400, f"expected 400 before selection approval, got {r.status_code}"

    def test_selection_approve_then_po(self, chain):
        s, rfq = chain["s"], chain["rfq"]
        a = s.post(f"{API}/service-workflow/rfqs/{rfq['id']}/selection-action",
                   json={"action": "approve", "remarks": "ok"}, timeout=60)
        assert a.status_code == 200, a.text[:300]
        assert a.json()["status"] == "selection_approved"
        p = s.post(f"{API}/service-workflow/rfqs/{rfq['id']}/po",
                   json={"rate": 100000, "quantity": 1, "tax_pct": 18, "unit": "Lot"}, timeout=60)
        assert p.status_code in (200, 201), p.text[:300]
        po = p.json()
        assert po["status"] == "draft"
        assert round(po["total_value"], 2) == 118000.0, po["total_value"]
        assert s.post(f"{API}/service-workflow/pos/{po['id']}/submit", timeout=60).status_code == 200
        act = s.post(f"{API}/service-workflow/pos/{po['id']}/action",
                     json={"action": "approve", "remarks": "ok"}, timeout=60)
        assert act.status_code == 200, act.text[:300]
        assert act.json()["status"] == "approved"
        iss = s.post(f"{API}/service-workflow/pos/{po['id']}/issue", timeout=60)
        assert iss.status_code == 200 and iss.json()["status"] == "issued"
        chain["po"] = iss.json()
        # SR should have moved to service_in_progress
        det = s.get(f"{API}/service-workflow/requests/{chain['sr']['id']}", timeout=60).json()
        sr = det.get("request", det)
        assert sr["status"] == "service_in_progress", sr["status"]

    def test_partial_srn_50pct(self, chain):
        s, po = chain["s"], chain["po"]
        r = s.post(f"{API}/service-workflow/pos/{po['id']}/srn",
                   json={"completed_pct": 50, "accepted_pct": 50, "receipt_type": "partial",
                         "service_details": f"TEST_{TAG} 50%", "submit": True}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        srn = r.json()
        assert srn["status"] == "submitted"
        a = s.post(f"{API}/service-workflow/srns/{srn['id']}/action",
                   json={"action": "approve", "remarks": "verified"}, timeout=60)
        assert a.status_code == 200 and a.json()["status"] == "approved", a.text[:200]
        chain["srn"] = a.json()
        pos = s.get(f"{API}/service-workflow/pos", timeout=60).json()
        row = next(x for x in pos if x["id"] == po["id"])
        assert round(float(row.get("accepted_pct_total") or 0), 1) == 50.0, row.get("accepted_pct_total")

    def test_srn_over_100_rejected(self, chain):
        s, po = chain["s"], chain["po"]
        r = s.post(f"{API}/service-workflow/pos/{po['id']}/srn",
                   json={"completed_pct": 90, "accepted_pct": 90, "submit": True}, timeout=60)
        assert r.status_code == 400, f"cumulative cap not enforced: {r.status_code} {r.text[:200]}"

    def test_invoice_matched(self, chain):
        s, po, srn = chain["s"], chain["po"], chain["srn"]
        r = s.post(f"{API}/service-workflow/invoices", json={
            "po_id": po["id"], "srn_id": srn["id"], "vendor_invoice_no": f"TEST-{TAG}-A",
            "invoice_amount": 50000, "tax_amount": 9000}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        inv = r.json()
        assert inv["match"]["ok"] is True, inv["match"]["mismatches"]
        assert inv["status"] == "pending_approval"
        assert round(inv["net_payable"], 2) == 59000.0
        chain["inv"] = inv

    def test_duplicate_invoice_no_rejected(self, chain):
        s, po, srn = chain["s"], chain["po"], chain["srn"]
        r = s.post(f"{API}/service-workflow/invoices", json={
            "po_id": po["id"], "srn_id": srn["id"], "vendor_invoice_no": f"TEST-{TAG}-A",
            "invoice_amount": 1000, "tax_amount": 180}, timeout=60)
        assert r.status_code == 400, f"duplicate not blocked: {r.status_code}"

    def test_invoice_over_accepted_goes_exception(self, chain):
        s, po, srn = chain["s"], chain["po"], chain["srn"]
        r = s.post(f"{API}/service-workflow/invoices", json={
            "po_id": po["id"], "srn_id": srn["id"], "vendor_invoice_no": f"TEST-{TAG}-B",
            "invoice_amount": 90000, "tax_amount": 16200}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        inv2 = r.json()
        assert inv2["status"] == "exception_review", inv2["status"]
        assert inv2["match"]["ok"] is False and inv2["match"]["mismatches"]
        # cannot approve while in exception
        bad = s.post(f"{API}/service-workflow/invoices/{inv2['id']}/action",
                     json={"action": "approve", "remarks": "x"}, timeout=60)
        assert bad.status_code == 400
        # resolve requires remarks
        nr = s.post(f"{API}/service-workflow/invoices/{inv2['id']}/resolve-exception",
                    json={"action": "resolve", "remarks": ""}, timeout=60)
        assert nr.status_code == 400
        # reject it to release the invoiced_total reservation
        rj = s.post(f"{API}/service-workflow/invoices/{inv2['id']}/action",
                    json={"action": "reject", "remarks": "over-invoiced"}, timeout=60)
        assert rj.status_code == 200 and rj.json()["status"] == "rejected"
        chain["inv2"] = inv2

    def test_invoice_approve_pushes_to_payment_queue(self, chain):
        s, inv = chain["s"], chain["inv"]
        a = s.post(f"{API}/service-workflow/invoices/{inv['id']}/action",
                   json={"action": "approve", "remarks": "ok to pay"}, timeout=60)
        assert a.status_code == 200, a.text[:300]
        assert a.json()["status"] == "payment_pending"
        q = s.get(f"{API}/accounts/payment-queue", timeout=60)
        assert q.status_code == 200, q.text[:300]
        rows = q.json()
        rows = rows if isinstance(rows, list) else rows.get("rows", [])
        pr = next((r for r in rows if r.get("source") == "service_invoice" and r.get("source_id") == inv["id"]), None)
        assert pr, f"invoice {inv['inv_no']} not found in payment queue (source=service_invoice)"
        assert round(float(pr.get("amount") or pr.get("est_value") or 0), 2) == 59000.0
        chain["pr"] = pr
        pay = s.get(f"{API}/service-workflow/payments", timeout=60).json()
        row = next((x for x in pay if x["id"] == inv["id"]), None)
        assert row and row.get("queue_stage") == "pending_verification", row and row.get("queue_stage")

    def test_verify_and_mark_paid_flows_back(self, chain):
        s, inv, pr = chain["s"], chain["inv"], chain["pr"]
        v = s.post(f"{API}/accounts/payment-queue/{pr['id']}/verify", json={
            "decision": "verified", "vendor_name": inv["vendor_name"], "vendor_account_no": "1234567890",
            "ifsc": "HDFC0000123", "bank_name": "HDFC", "invoice_no": inv["vendor_invoice_no"],
            "invoice_date": inv["invoice_date"], "verified_amount": inv["net_payable"],
            "remarks": f"TEST_{TAG} verify"}, timeout=90)
        assert v.status_code == 200, v.text[:400]
        mp = s.post(f"{API}/accounts/payment-queue/{pr['id']}/mark-paid",
                    json={"utr_no": f"UTR{TAG}001", "paid_date": "2026-07-01"}, timeout=90)
        assert mp.status_code == 200, mp.text[:400]
        pay = s.get(f"{API}/service-workflow/payments", timeout=60).json()
        row = next((x for x in pay if x["id"] == inv["id"]), None)
        assert row, "invoice missing from module payments view"
        assert row["status"] == "paid", row["status"]
        assert row.get("utr_no") == f"UTR{TAG}001", row.get("utr_no")
        # PO payment status + SR timeline
        pos = s.get(f"{API}/service-workflow/pos", timeout=60).json()
        po_row = next(x for x in pos if x["id"] == chain["po"]["id"])
        assert po_row.get("payment_status") in ("partially_paid", "paid", "payment_completed"), po_row.get("payment_status")
        det = s.get(f"{API}/service-workflow/requests/{chain['sr']['id']}", timeout=60).json()
        tl = det.get("timeline") or det.get("history") or []
        acts = " ".join(str(e.get("action", "")) for e in tl)
        assert "invoice_paid" in acts or "paid" in acts, acts[:300]
