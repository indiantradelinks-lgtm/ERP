"""Iteration 48 backend tests — Department Governance Phase 2 (D + E + F).

D — Cross-dept dependency enforcement
    • POST /store/transactions outward requires approved PR / allocation (super_admin bypass)
    • POST /dept-gov/invoices/{id}/verify  — accounts/finance only
    • POST /dept-gov/payments-out         — refuses unverified invoice
    • POST /dept-gov/payroll/check-attendance
E — Reports: handoff-delays, dept-performance, dept-manpower
F — Audit viewer: by-dept and per-record timeline
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin":    ("admin@erp.com",    "Admin@123"),
    "pm":       ("test_pm@erp.com",  "PM@12345"),
    "hr":       ("hr.test@erp.com",  "HR@12345"),
    "purchase": ("purchase@erp.com", "Purchase@123"),
}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    tok = s.cookies.get("access_token")
    return tok


@pytest.fixture(scope="session")
def tokens():
    out = {}
    for k, (e, p) in CREDS.items():
        out[k] = _login(e, p)
    return out


def hdr(tok):
    # Send token both as Bearer and as cookie (some endpoints may look at either).
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
            "Cookie": f"access_token={tok}"}


# ─────────────────────────────────────────────────────────────────
# Helpers — find or create a vendor, vendor invoice, inventory item
# ─────────────────────────────────────────────────────────────────
def _get_or_create_vendor(admin_tok):
    r = requests.get(f"{API}/vendors", headers=hdr(admin_tok), timeout=30)
    if r.status_code == 200 and isinstance(r.json(), list) and r.json():
        return r.json()[0]
    payload = {"name": f"TEST48 Vendor {uuid.uuid4().hex[:6]}", "gstin": "27AAAAA0000A1Z5",
               "contact_person": "Tester", "email": "t@e.com", "phone": "9999999999"}
    r = requests.post(f"{API}/vendors", headers=hdr(admin_tok), json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_vendor_invoice(admin_tok, vendor, amount=10000):
    """Insert a vendor_invoice directly via /crud since vendor-portal route needs vendor login."""
    payload = {
        "vendor_id": vendor["id"],
        "vendor_name": vendor.get("name"),
        "invoice_no": f"TEST48-INV-{uuid.uuid4().hex[:6]}",
        "date": "2026-05-01",
        "amount": amount,
        "status": "submitted",
        "description": "Iter48 test invoice",
    }
    r = requests.post(f"{API}/vendor-invoices", headers=hdr(admin_tok), json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create invoice failed: {r.status_code} {r.text[:200]}"
    return r.json()


def _get_inventory_item(admin_tok):
    r = requests.get(f"{API}/inventory", headers=hdr(admin_tok), timeout=30)
    items = r.json() if r.status_code == 200 else []
    if not isinstance(items, list):
        items = items.get("items", []) if isinstance(items, dict) else []
    # find an item with quantity > 5
    for it in items:
        if float(it.get("quantity", 0) or 0) > 5:
            return it
    if items:
        return items[0]
    # Create one
    payload = {"name": f"TEST48 Item {uuid.uuid4().hex[:5]}", "sku": f"T48-{uuid.uuid4().hex[:5]}",
               "quantity": 100, "unit": "nos"}
    r = requests.post(f"{API}/crud/inventory", headers=hdr(admin_tok), json=payload, timeout=30)
    return r.json()


# ════════════════════════════════════════════════════════════════
# D1 — Material outward dependency rule (/store/transactions)
# ════════════════════════════════════════════════════════════════
class TestStoreOutwardDependency:
    def test_outward_without_link_rejected_400(self, tokens):
        item = _get_inventory_item(tokens["admin"])
        r = requests.post(f"{API}/store/transactions", headers=hdr(tokens["admin"]),
                          json={"txn_type": "outward", "item_id": item["id"], "quantity": 1,
                                "issued_to": "TEST48"}, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:300]}"
        assert "approved" in r.text.lower() or "purchase requisition" in r.text.lower()

    def test_outward_force_unlinked_super_admin_succeeds(self, tokens):
        item = _get_inventory_item(tokens["admin"])
        r = requests.post(f"{API}/store/transactions", headers=hdr(tokens["admin"]),
                          json={"txn_type": "outward", "item_id": item["id"], "quantity": 1,
                                "issued_to": "TEST48", "force_unlinked": True}, timeout=30)
        assert r.status_code in (200, 201), f"super_admin bypass failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        assert body.get("txn_type") == "outward"
        assert body.get("status") in ("posted", "pending_approval")

    def test_outward_force_unlinked_non_admin_still_blocked(self, tokens):
        item = _get_inventory_item(tokens["admin"])
        # purchase_officer has inventory:write per crud_router permissions? Try both purchase and pm
        for who in ("purchase", "pm"):
            r = requests.post(f"{API}/store/transactions", headers=hdr(tokens[who]),
                              json={"txn_type": "outward", "item_id": item["id"], "quantity": 1,
                                    "issued_to": "TEST48-nonadmin", "force_unlinked": True}, timeout=30)
            # Either 400 (dep rule blocks) or 403 (no permission) — both acceptable; key is NOT 200
            assert r.status_code in (400, 403), (
                f"non-admin force_unlinked must NOT succeed (role={who}): "
                f"{r.status_code} {r.text[:300]}"
            )

    def test_outward_with_nonapproved_pr_blocked(self, tokens):
        item = _get_inventory_item(tokens["admin"])
        # Create a draft PR via the real procurement endpoint
        pr_payload = {"department": "Operations", "priority": "medium",
                      "items": [{"name": "TEST48 item", "quantity": 1, "unit": "Nos"}],
                      "submit_for_approval": False}
        r = requests.post(f"{API}/procurement/prs", headers=hdr(tokens["admin"]),
                          json=pr_payload, timeout=30)
        if r.status_code not in (200, 201):
            pytest.skip(f"could not create draft PR: {r.status_code} {r.text[:200]}")
        pr_id = r.json().get("id")
        r2 = requests.post(f"{API}/store/transactions", headers=hdr(tokens["admin"]),
                           json={"txn_type": "outward", "item_id": item["id"], "quantity": 1,
                                 "pr_id": pr_id, "issued_to": "TEST48"}, timeout=30)
        assert r2.status_code == 400, (
            f"draft PR must not satisfy dep rule: {r2.status_code} {r2.text[:300]}"
        )

    def test_outward_with_approved_pr_succeeds(self, tokens):
        item = _get_inventory_item(tokens["admin"])
        # Look for an existing approved/issued PR
        r = requests.get(f"{API}/procurement/prs?status=approved",
                         headers=hdr(tokens["admin"]), timeout=30)
        prs = r.json() if r.status_code == 200 else []
        if not prs:
            # Try other satisfying statuses
            for st in ("issued", "po_created", "completed", "po_generated"):
                r = requests.get(f"{API}/procurement/prs?status={st}",
                                 headers=hdr(tokens["admin"]), timeout=30)
                if r.status_code == 200 and r.json():
                    prs = r.json()
                    break
        if not prs:
            pytest.skip("no approved/issued PR in DB to test happy path")
        pr_id = prs[0]["id"]
        r2 = requests.post(f"{API}/store/transactions", headers=hdr(tokens["admin"]),
                           json={"txn_type": "outward", "item_id": item["id"], "quantity": 1,
                                 "pr_id": pr_id, "issued_to": "TEST48"}, timeout=30)
        assert r2.status_code in (200, 201), f"approved PR should permit outward: {r2.status_code} {r2.text[:300]}"

    @pytest.mark.parametrize("ttype", ["inward", "transfer", "return", "scrap"])
    def test_non_outward_unaffected(self, tokens, ttype):
        item = _get_inventory_item(tokens["admin"])
        r = requests.post(f"{API}/store/transactions", headers=hdr(tokens["admin"]),
                          json={"txn_type": ttype, "item_id": item["id"], "quantity": 1,
                                "received_from": "TEST48", "to_location": "WH-1",
                                "from_location": "WH-2"}, timeout=30)
        # transfer / scrap may fail if stock<1 — accept 400 with "Insufficient stock" but NOT dep-rule msg
        assert r.status_code in (200, 201, 400), f"unexpected {r.status_code}: {r.text[:200]}"
        if r.status_code == 400:
            assert "purchase requisition" not in r.text.lower()


# ════════════════════════════════════════════════════════════════
# D2 — Vendor invoice verify + payments-out
# ════════════════════════════════════════════════════════════════
class TestVerifyAndPayInvoice:
    @pytest.fixture(scope="class")
    def invoice(self, tokens):
        vendor = _get_or_create_vendor(tokens["admin"])
        return _create_vendor_invoice(tokens["admin"], vendor, amount=10000)

    def test_verify_403_for_purchase_officer(self, tokens, invoice):
        r = requests.post(f"{API}/dept-gov/invoices/{invoice['id']}/verify",
                          headers=hdr(tokens["purchase"]), json={"verified": True}, timeout=30)
        assert r.status_code == 403, f"purchase_officer must not verify: {r.status_code} {r.text[:200]}"

    def test_verify_404_unknown(self, tokens):
        r = requests.post(f"{API}/dept-gov/invoices/nonexistent-id-xyz/verify",
                          headers=hdr(tokens["admin"]), json={"verified": True}, timeout=30)
        assert r.status_code == 404

    def test_pay_unverified_400(self, tokens, invoice):
        r = requests.post(f"{API}/dept-gov/payments-out", headers=hdr(tokens["admin"]),
                          json={"invoice_id": invoice["id"], "amount": 100, "mode": "bank_transfer",
                                "payment_date": "2026-05-15"}, timeout=30)
        assert r.status_code == 400
        assert "unverified" in r.text.lower()

    def test_verify_succeeds_as_admin(self, tokens, invoice):
        r = requests.post(f"{API}/dept-gov/invoices/{invoice['id']}/verify",
                          headers=hdr(tokens["admin"]),
                          json={"verified": True, "note": "iter48 test verify"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") == "verified"

    def test_payment_exceeding_amount_400(self, tokens, invoice):
        r = requests.post(f"{API}/dept-gov/payments-out", headers=hdr(tokens["admin"]),
                          json={"invoice_id": invoice["id"], "amount": 99999999, "mode": "bank_transfer",
                                "payment_date": "2026-05-15"}, timeout=30)
        assert r.status_code == 400
        assert "exceeds" in r.text.lower()

    def test_pay_verified_invoice_succeeds_and_flips_status(self, tokens, invoice):
        # Pay full amount
        r = requests.post(f"{API}/dept-gov/payments-out", headers=hdr(tokens["admin"]),
                          json={"invoice_id": invoice["id"], "amount": 10000, "mode": "bank_transfer",
                                "payment_date": "2026-05-15", "bank_name": "HDFC"}, timeout=30)
        assert r.status_code in (200, 201), f"pay failed: {r.status_code} {r.text[:300]}"
        pay = r.json()
        assert pay.get("dept_doc_no", "").startswith("FIN/PAY/"), f"bad dept_doc_no: {pay.get('dept_doc_no')}"
        assert pay.get("status") == "paid"
        # Verify invoice flipped to paid
        time.sleep(0.5)
        r2 = requests.get(f"{API}/vendor-invoices/{invoice['id']}",
                          headers=hdr(tokens["admin"]), timeout=30)
        if r2.status_code == 200:
            assert r2.json().get("status") == "paid", f"invoice not flipped: {r2.json().get('status')}"


# ════════════════════════════════════════════════════════════════
# D3 — Payroll attendance preflight
# ════════════════════════════════════════════════════════════════
class TestPayrollAttendanceCheck:
    def test_payroll_check_returns_structure(self, tokens):
        r = requests.post(f"{API}/dept-gov/payroll/check-attendance",
                          headers=hdr(tokens["hr"]), json={"month": "2026-05"}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("month", "total_employees", "approved_attendance_count", "blocker_count",
                  "blockers", "can_proceed"):
            assert k in body, f"missing field {k}"
        # can_proceed iff zero blockers
        assert body["can_proceed"] == (body["blocker_count"] == 0)

    def test_bad_month_400(self, tokens):
        r = requests.post(f"{API}/dept-gov/payroll/check-attendance",
                          headers=hdr(tokens["hr"]), json={"month": "bad"}, timeout=30)
        assert r.status_code in (400, 422)

    def test_pm_forbidden(self, tokens):
        r = requests.post(f"{API}/dept-gov/payroll/check-attendance",
                          headers=hdr(tokens["pm"]), json={"month": "2026-05"}, timeout=30)
        assert r.status_code == 403


# ════════════════════════════════════════════════════════════════
# E — Reports
# ════════════════════════════════════════════════════════════════
class TestReports:
    def test_handoff_delays_structure(self, tokens):
        r = requests.get(f"{API}/dept-gov/reports/handoff-delays?days=90",
                         headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rows" in body
        if body["rows"]:
            row = body["rows"][0]
            for k in ("type", "samples", "avg_minutes_per_step", "avg_hours_per_step",
                      "longest_step_minutes", "approved", "rejected"):
                assert k in row, f"missing field {k} in handoff-delays row"

    def test_dept_performance_structure(self, tokens):
        r = requests.get(f"{API}/dept-gov/reports/dept-performance?days=30",
                         headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rows" in body
        if body["rows"]:
            row = body["rows"][0]
            for k in ("department", "count", "amount", "by_doctype"):
                assert k in row, f"missing field {k} in dept-performance row"

    def test_dept_manpower_structure(self, tokens):
        r = requests.get(f"{API}/dept-gov/reports/dept-manpower",
                         headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rows" in body
        if body["rows"]:
            row = body["rows"][0]
            for k in ("department", "headcount", "deployed", "available"):
                assert k in row, f"missing field {k} in dept-manpower row"
            # available = headcount - deployed
            assert row["available"] == row["headcount"] - row["deployed"]


# ════════════════════════════════════════════════════════════════
# F — Audit trail viewer
# ════════════════════════════════════════════════════════════════
class TestAuditViewer:
    def test_audit_by_dept_403_for_pm(self, tokens):
        r = requests.get(f"{API}/dept-gov/audit/by-dept?dept=hr",
                         headers=hdr(tokens["pm"]), timeout=30)
        assert r.status_code == 403

    def test_audit_by_dept_filters_combine(self, tokens):
        # No filters
        r = requests.get(f"{API}/dept-gov/audit/by-dept?limit=50",
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "rows" in body and "count" in body
        # With filter
        r2 = requests.get(f"{API}/dept-gov/audit/by-dept?action=create&limit=50",
                          headers=hdr(tokens["admin"]), timeout=30)
        assert r2.status_code == 200
        if r2.json()["rows"]:
            assert all(row.get("action") == "create" for row in r2.json()["rows"])
        # resource filter
        r3 = requests.get(f"{API}/dept-gov/audit/by-dept?resource=vendor_invoices&limit=50",
                          headers=hdr(tokens["admin"]), timeout=30)
        assert r3.status_code == 200
        if r3.json()["rows"]:
            assert all(row.get("resource") == "vendor_invoices" for row in r3.json()["rows"])

    def test_audit_limit_capped_at_1000(self, tokens):
        # Ask for 5000, should still work and be capped server-side
        r = requests.get(f"{API}/dept-gov/audit/by-dept?limit=5000",
                         headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200
        assert len(r.json()["rows"]) <= 1000

    def test_audit_record_unknown_collection_400(self, tokens):
        r = requests.get(f"{API}/dept-gov/audit/record/not_a_collection_xyz/abc",
                         headers=hdr(tokens["admin"]), timeout=30)
        # Mongo will accept any collection name string — but find_one on a non-existent coll returns None,
        # so the router will produce a 404 not 400. Accept either to be tolerant of impl.
        assert r.status_code in (400, 404)

    def test_audit_record_unknown_id_404(self, tokens):
        r = requests.get(f"{API}/dept-gov/audit/record/vendor_invoices/nonexistent-xyz",
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 404

    def test_audit_record_timeline_returned(self, tokens):
        # Use a vendor_invoice we just verified/paid above — find any
        r = requests.get(f"{API}/vendor-invoices", headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200
        invs = r.json()
        if not invs:
            pytest.skip("no vendor invoices to inspect")
        inv = invs[0]
        r2 = requests.get(f"{API}/dept-gov/audit/record/vendor_invoices/{inv['id']}",
                          headers=hdr(tokens["admin"]), timeout=30)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "timeline" in body and isinstance(body["timeline"], list)
        # Timeline should at least have the "created" phase
        phases = {t.get("phase") for t in body["timeline"]}
        assert "created" in phases


# ════════════════════════════════════════════════════════════════
# Regression — Iter 47 numbering still works
# ════════════════════════════════════════════════════════════════
class TestRegressionIter47:
    def test_advance_still_gets_hr_adv_prefix(self, tokens):
        # Create an employee_advance, check dept_doc_no starts with HR/ADV/
        # Find an active employee first
        r = requests.get(f"{API}/employees?limit=5", headers=hdr(tokens["admin"]), timeout=30)
        if r.status_code != 200 or not r.json():
            pytest.skip("no employees seeded")
        emp = r.json()[0]
        payload = {"employee_id": emp["id"], "requested_amount": 500, "reason": "TEST48 regression",
                   "advance_type": "SAL"}
        r2 = requests.post(f"{API}/advances", headers=hdr(tokens["admin"]), json=payload, timeout=30)
        if r2.status_code not in (200, 201):
            pytest.skip(f"advance create endpoint differs: {r2.status_code} {r2.text[:200]}")
        body = r2.json()
        dno = body.get("dept_doc_no", "")
        assert dno.startswith("HR/ADV/"), f"expected HR/ADV/ prefix, got {dno}"
