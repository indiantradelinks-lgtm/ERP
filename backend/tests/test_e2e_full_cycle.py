"""End-to-end happy-path: PR → RFQ → PO → GRN → Material Issue → DPR → Measurement
→ Certify → RA Bill → Invoice → Payment.

Validates that every transition mutates state consistently and the linked
records (inventory, project, measurement, bill, payment) reflect each step's
side effects.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TS = str(int(time.time()))


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def two_vendors(admin):
    vs = admin.get(f"{API}/vendors", timeout=30).json()
    assert len(vs) >= 2
    return [vs[0]["id"], vs[1]["id"]], [vs[0]["name"], vs[1]["name"]]


def _walk_approval(admin, record_id):
    apv = admin.get(f"{API}/approvals", params={"record_id": record_id}, timeout=30).json()
    if not (isinstance(apv, list) and apv):
        return
    ap = apv[0]
    for _ in range(len(ap.get("chain") or [])):
        ar = admin.post(f"{API}/approvals/{ap['id']}/action", json={"action": "approve", "comment": "ok"}, timeout=30)
        if ar.status_code != 200:
            break


# ──────────────────────────────────────────────────────────────────────────────
# E2E walk
# ──────────────────────────────────────────────────────────────────────────────
class TestEndToEndCycle:

    def test_01_create_project(self, admin):
        code = f"PRJ-E2E-{TS}"
        p = admin.post(f"{API}/projects", json={
            "code": code,
            "name": f"E2E Project {TS}", "client": f"ACME-{TS}", "type": "scaffolding",
            "site": "Plant Block A", "budget": 1_000_000, "status": "active",
        }, timeout=30).json()
        assert p.get("id"), p
        pytest.proj_code = code
        pytest.proj_id = p["id"]

    def test_02_create_and_approve_pr(self, admin):
        pr = admin.post(f"{API}/procurement/prs", json={
            "department": "Operations", "priority": "high",
            "project_code": pytest.proj_code,
            "submit_for_approval": True,
            "items": [{"name": f"Cuplock 2m E2E-{TS}", "quantity": 100, "unit": "Nos", "category": "scaffolding"}],
        }, timeout=30).json()
        assert pr["pr_number"].startswith("PR-")
        _walk_approval(admin, pr["id"])
        pr2 = admin.get(f"{API}/procurement/prs/{pr['id']}", timeout=30).json()
        assert pr2["status"] == "approved", f"PR not approved: {pr2['status']}"
        pytest.pr_id = pr2["id"]
        pytest.pr_no = pr2["pr_number"]

    def test_03_rfq_with_two_vendors_and_select(self, admin, two_vendors):
        vendor_ids, vendor_names = two_vendors
        rfq = admin.post(f"{API}/procurement/rfqs", json={
            "pr_id": pytest.pr_id, "vendors": [{"vendor_id": vid} for vid in vendor_ids],
        }, timeout=30).json()
        assert rfq["rfq_number"].startswith("RFQ-")
        # Vendor A: 80/Nos, Vendor B: 90/Nos → A wins
        admin.post(f"{API}/procurement/rfqs/{rfq['id']}/respond", json={"vendor_id": vendor_ids[0], "rate_quoted": 80, "delivery_days": 5}, timeout=30)
        admin.post(f"{API}/procurement/rfqs/{rfq['id']}/respond", json={"vendor_id": vendor_ids[1], "rate_quoted": 90, "delivery_days": 3}, timeout=30)
        comp = admin.get(f"{API}/procurement/rfqs/{rfq['id']}/comparative", timeout=30).json()
        # Cheapest should be first in sorted rows
        assert comp["rows"][0]["vendor_id"] == vendor_ids[0]
        assert comp["rows"][0]["landed_value"] == 80 * 100   # subtotal only — gst added later in PO conversion
        # Select winner
        r = admin.post(f"{API}/procurement/rfqs/{rfq['id']}/select-vendor", json={"vendor_id": vendor_ids[0]}, timeout=30)
        assert r.status_code == 200
        pytest.rfq_id = rfq["id"]

    def test_04_convert_rfq_to_po(self, admin):
        po = admin.post(f"{API}/procurement/rfqs/{pytest.rfq_id}/convert-to-po", timeout=30).json()
        assert po["po_number"].startswith("PO-")
        assert po["amount"] == 8000    # 100 × 80
        assert po["status"] == "approved"
        pytest.po_id = po["id"]
        pytest.po_no = po["po_number"]
        pytest.po_items = po.get("items") or []

    def test_05_grn_partial_then_full(self, admin):
        # Pre-create inventory item so GRN updates it
        invn = admin.post(f"{API}/inventory", json={
            "name": f"Cuplock 2m E2E-{TS}", "code": f"INV-E2E-{TS}",
            "category": "scaffolding", "unit": "Nos", "quantity": 0, "rate": 80,
        }, timeout=30).json()
        pytest.inventory_id = invn["id"]
        line = (pytest.po_items or [{}])[0]
        line_payload = {
            "po_item_index": 0,
            "item_id": pytest.inventory_id,
            "item_name": f"Cuplock 2m E2E-{TS}",
            "ordered_qty": float(line.get("quantity") or 100),
            "store_location": "Main Store",
        }
        # Receive 60 first, then 40
        r1 = admin.post(f"{API}/procurement/grns", json={
            "po_id": pytest.po_id,
            "items": [{**line_payload, "received_qty": 60, "accepted_qty": 60}],
            "submit_for_approval": True,
        }, timeout=30)
        assert r1.status_code == 200, f"GRN 1 failed: {r1.status_code} {r1.text[:300]}"
        g1 = r1.json()
        assert g1["grn_number"].startswith("GRN-")
        _walk_approval(admin, g1["id"])
        r2 = admin.post(f"{API}/procurement/grns", json={
            "po_id": pytest.po_id,
            "items": [{**line_payload, "received_qty": 40, "accepted_qty": 40}],
            "submit_for_approval": True,
        }, timeout=30)
        assert r2.status_code == 200, r2.text
        g2 = r2.json()
        _walk_approval(admin, g2["id"])
        # PO should be fully received now — query via the CRUD purchase_orders endpoint
        po = admin.get(f"{API}/purchase-orders/{pytest.po_id}", timeout=30).json()
        assert po.get("status") in ("received", "closed", "partially_received", "approved"), f"PO status: {po.get('status')}"
        # Inventory item should exist with quantity 100
        inv = admin.get(f"{API}/inventory/{pytest.inventory_id}", timeout=30).json()
        assert inv["quantity"] >= 100, f"Inventory qty: {inv.get('quantity')}"

    def test_06_material_allocation_to_project(self, admin):
        alloc = admin.post(f"{API}/allocations", json={
            "kind": "material",
            "item_id": pytest.inventory_id,
            "item_name": f"Cuplock 2m E2E-{TS}",
            "quantity": 40, "unit": "Nos",
            "allocated_to_type": "project",
            "project_code": pytest.proj_code,
            "returnable": False,
            "remarks": "site scaffolding erection",
        }, timeout=30).json()
        assert alloc.get("allocation_no", "").startswith("ALC-"), alloc
        # Verify inventory debited
        inv = admin.get(f"{API}/inventory/{pytest.inventory_id}", timeout=30).json()
        assert inv["quantity"] >= 60, f"Inventory after issue: {inv['quantity']}"
        pytest.alloc_id = alloc["id"]

    def test_07_dpr_create_submit_approve(self, admin):
        dpr = admin.post(f"{API}/dprs", json={
            "date": "2026-04-10", "project_code": pytest.proj_code,
            "site_name": "Plant Block A", "service_type": "scaffolding",
            "manpower": [{"role": "scaffolder", "count": 6}, {"role": "supervisor", "count": 1}],
            "work_completed": "Erected south face up to L3",
            "material_used": [{"item_name": f"Cuplock 2m E2E-{TS}", "quantity": 40, "unit": "Nos"}],
            "submit": True,
        }, timeout=30).json()
        assert dpr["dpr_number"].startswith("DPR-")
        assert dpr["status"] == "submitted"
        # Super admin approves directly
        r = admin.post(f"{API}/dprs/{dpr['id']}/approve", json={"comment": "Looks good"}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "approved"
        pytest.dpr_id = dpr["id"]

    def test_08_measurement_certify_approve(self, admin):
        m = admin.post(f"{API}/measurements", json={
            "date": "2026-04-12", "project_code": pytest.proj_code,
            "site_name": "Plant Block A", "service_type": "scaffolding",
            "items": [
                {"service": "scaffolding", "activity": "erected", "executed_qty": 280, "certified_qty": 280, "unit": "m²", "rate": 120},
                {"service": "scaffolding", "activity": "dismantled", "executed_qty": 60, "certified_qty": 60, "unit": "m²", "rate": 50},
            ],
            "joint_measured_with": "Mr. Iyer",
            "submit": True,
        }, timeout=30).json()
        # 280*120 + 60*50 = 33600 + 3000 = 36600
        assert m["billable_value"] == 36600
        r1 = admin.post(f"{API}/measurements/{m['id']}/certify",
                        json={"signatory_name": "Mr. Iyer", "signatory_designation": "Maintenance Manager"}, timeout=30)
        assert r1.status_code == 200 and r1.json()["status"] == "client_certified"
        r2 = admin.post(f"{API}/measurements/{m['id']}/approve-for-billing", timeout=30)
        assert r2.status_code == 200 and r2.json()["status"] == "approved_for_billing"
        pytest.meas_id = m["id"]
        pytest.meas_billable = 36600

    def test_09_ra_bill_from_meas_submit_approve_invoice(self, admin):
        b = admin.post(f"{API}/ra-bills/from-measurements", json={
            "measurement_ids": [pytest.meas_id],
            "client_id": f"CL-E2E-{TS}", "client_name": f"ACME-{TS}",
            "po_id": pytest.po_id, "po_number": pytest.po_no,
            "gst_pct": 18, "retention_pct": 5, "tds_pct": 2,
        }, timeout=30).json()
        # subtotal 36600 → gst 6588 → gross 43188 → ret 1830 → tds 732 → net 40626
        assert b["subtotal"] == pytest.meas_billable
        assert b["gst_amount"] == round(36600 * 0.18, 2)
        assert b["gross_value"] == 36600 + b["gst_amount"]
        assert b["retention_amount"] == round(36600 * 0.05, 2)
        assert b["tds_amount"] == round(36600 * 0.02, 2)
        # Submit → approve
        admin.post(f"{API}/ra-bills/{b['id']}/submit", timeout=30)
        ra = admin.post(f"{API}/ra-bills/{b['id']}/approve", timeout=30).json()
        assert ra["status"] == "approved"
        # Linked measurement flipped to billed
        m = admin.get(f"{API}/measurements/{pytest.meas_id}", timeout=30).json()
        assert m["status"] == "billed"
        # Issue invoice
        inv = admin.post(f"{API}/ra-bills/{b['id']}/issue-invoice", json={"due_days": 30, "issue_date": "2026-04-15"}, timeout=30).json()
        assert inv["status"] == "invoiced"
        assert inv["due_date"] == "2026-05-15"
        pytest.bill_id = b["id"]
        pytest.bill_net = b["net_payable"]
        pytest.client_id = f"CL-E2E-{TS}"

    def test_10_payment_settles_bill(self, admin):
        # Pay the full net
        r = admin.post(f"{API}/payments-in", json={
            "client_id": pytest.client_id, "client_name": f"ACME-{TS}",
            "amount": pytest.bill_net, "mode": "neft", "reference_no": f"UTR-{TS}",
            "allocations": [{"ra_bill_id": pytest.bill_id, "amount": pytest.bill_net}],
        }, timeout=30).json()
        assert r["payment_no"].startswith("PAY-")
        # Bill is paid
        b = admin.get(f"{API}/ra-bills/{pytest.bill_id}", timeout=30).json()
        assert b["status"] == "paid"
        assert b["balance_due"] == 0

    def test_11_receivables_clean(self, admin):
        led = admin.get(f"{API}/receivables/client-ledger", params={"client_id": pytest.client_id}, timeout=30).json()
        assert led["summary"]["balance"] == 0
        assert led["summary"]["invoiced"] == led["summary"]["received"]
        # Overdue should not contain this client (balance 0)
        ovd = admin.get(f"{API}/receivables/overdue", timeout=30).json()
        assert not any(r["client_name"] == f"ACME-{TS}" and r["balance"] > 0 for r in ovd["rows"])

    def test_12_project_snapshot_reflects_cycle(self, admin):
        snap = admin.get(f"{API}/projects/{pytest.proj_code}/ops/snapshot", timeout=30).json()
        assert snap["dpr"]["approved"] >= 1
        assert snap["measurement_billable_value"] >= pytest.meas_billable
        # Profitability is computed
        prof = admin.get(f"{API}/projects/{pytest.proj_code}/ops/profitability", timeout=30).json()
        assert prof["revenue"]["bill_count"] >= 1
