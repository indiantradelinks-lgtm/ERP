"""Seed a realistic walkthrough project end-to-end on the deployed system.

Creates: "Vega Refinery — Tank Farm Scaffolding" with a complete cycle:
  Project → PR (approved) → RFQ (2 vendors) → PO → 2× GRN (60+40)
  → Material Issue 40 → DPR (PC-approved) → Measurement (certified, billing-approved)
  → RA Bill (drafted with retention 5%, TDS 2%, GST 18%) → submitted → approved
  → invoiced → partial payment (~50%)

Run:  cd /app/backend && python scripts/seed_walkthrough_project.py
The script is idempotent-ish: re-running creates a new project suffixed with the
timestamp to avoid duplicate-key errors.
"""
import os
import sys
import time
from typing import Any, Dict

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TS = time.strftime("%Y%m%d-%H%M")

ADMIN_EMAIL = os.environ.get("SEED_EMAIL", "admin@erp.com")
ADMIN_PWD = os.environ.get("SEED_PASSWORD", "Admin@123")


def banner(msg):
    print("\n" + "═" * 72)
    print("  " + msg)
    print("═" * 72)


def step(msg):
    print(f"  ▸ {msg}")


def session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    r.raise_for_status()
    return s


def walk_approval(s, record_id):
    apv = s.get(f"{API}/approvals", params={"record_id": record_id}, timeout=30).json()
    if not (isinstance(apv, list) and apv):
        return
    ap = apv[0]
    for _ in range(len(ap.get("chain") or [])):
        ar = s.post(f"{API}/approvals/{ap['id']}/action", json={"action": "approve", "comment": "Walkthrough auto-approve"}, timeout=30)
        if ar.status_code != 200:
            break


def main():
    s = session()
    banner(f"Seeding walkthrough project — {TS}")

    # 1. Project
    project_code = f"PRJ-VEGA-{TS}"
    client_id = f"CL-VEGA-{TS}"
    client_name = "Vega Refinery Ltd"
    s.post(f"{API}/projects", json={
        "code": project_code,
        "name": "Vega Refinery — Tank Farm Scaffolding",
        "client": client_name, "type": "scaffolding",
        "site": "Tank Farm Zone A", "budget": 5_000_000, "status": "active",
        "description": "Erection & dismantling scaffolding for tanks T-401 to T-405 shutdown maintenance.",
    }, timeout=30).raise_for_status()
    step(f"Project created: {project_code}")

    # 2. PR + approval
    pr = s.post(f"{API}/procurement/prs", json={
        "department": "Operations", "priority": "high",
        "project_code": project_code, "submit_for_approval": True,
        "items": [
            {"name": f"Cuplock Vertical 2m {TS}", "quantity": 200, "unit": "Nos", "category": "scaffolding"},
            {"name": f"Ledger 2.5m {TS}", "quantity": 120, "unit": "Nos", "category": "scaffolding"},
        ],
    }, timeout=30).json()
    walk_approval(s, pr["id"])
    step(f"PR approved: {pr['pr_number']}")

    # 3. RFQ + responses + winner
    vendors = s.get(f"{API}/vendors", timeout=30).json()
    if len(vendors) < 2:
        print("Need at least 2 vendors in seed — aborting.")
        return
    v1, v2 = vendors[0]["id"], vendors[1]["id"]
    rfq = s.post(f"{API}/procurement/rfqs", json={
        "pr_id": pr["id"], "vendors": [{"vendor_id": v1}, {"vendor_id": v2}],
    }, timeout=30).json()
    # Vendor A: 95/Nos vertical, 60/Nos ledger (line value 95*200 + 60*120 = 26200)
    # Vendor B: 100/Nos default (line value 100*320 = 32000)  — A wins
    s.post(f"{API}/procurement/rfqs/{rfq['id']}/respond", json={
        "vendor_id": v1, "item_rates": {"0": 95, "1": 60}, "delivery_days": 4, "payment_terms": "30 days", "technical_score": 92,
    }, timeout=30)
    s.post(f"{API}/procurement/rfqs/{rfq['id']}/respond", json={
        "vendor_id": v2, "rate_quoted": 100, "delivery_days": 2, "payment_terms": "Advance", "technical_score": 80,
    }, timeout=30)
    s.post(f"{API}/procurement/rfqs/{rfq['id']}/select-vendor", json={"vendor_id": v1}, timeout=30)
    step(f"RFQ {rfq['rfq_number']} — vendor A selected (per-item: 95 + 60)")

    # 4. Convert to PO
    po = s.post(f"{API}/procurement/rfqs/{rfq['id']}/convert-to-po", timeout=30).json()
    step(f"PO created: {po['po_number']} — ₹{po['amount']:,.0f}")

    # 5. Pre-create inventory items so GRN updates them
    inv1 = s.post(f"{API}/inventory", json={
        "name": f"Cuplock Vertical 2m {TS}", "code": f"INV-VRT-{TS}",
        "category": "scaffolding", "unit": "Nos", "quantity": 0, "rate": 95,
    }, timeout=30).json()
    inv2 = s.post(f"{API}/inventory", json={
        "name": f"Ledger 2.5m {TS}", "code": f"INV-LDR-{TS}",
        "category": "scaffolding", "unit": "Nos", "quantity": 0, "rate": 60,
    }, timeout=30).json()
    step(f"Inventory items created: {inv1['code']}, {inv2['code']}")

    # 6. Two GRNs: partial then balance
    common_line = lambda idx, inv, ordered: {
        "po_item_index": idx, "item_id": inv["id"], "item_name": inv["name"],
        "ordered_qty": ordered, "store_location": "Main Store",
    }
    g1 = s.post(f"{API}/procurement/grns", json={
        "po_id": po["id"],
        "items": [
            {**common_line(0, inv1, 200), "received_qty": 120, "accepted_qty": 120},
            {**common_line(1, inv2, 120), "received_qty": 80, "accepted_qty": 80},
        ],
        "submit_for_approval": True,
    }, timeout=30).json()
    walk_approval(s, g1["id"])
    g2 = s.post(f"{API}/procurement/grns", json={
        "po_id": po["id"],
        "items": [
            {**common_line(0, inv1, 200), "received_qty": 80, "accepted_qty": 80},
            {**common_line(1, inv2, 120), "received_qty": 40, "accepted_qty": 40},
        ],
        "submit_for_approval": True,
    }, timeout=30).json()
    walk_approval(s, g2["id"])
    step(f"GRNs received & approved: {g1['grn_number']} + {g2['grn_number']}")

    # 7. Material allocation to project (issue 80 verticals + 50 ledgers)
    s.post(f"{API}/allocations", json={
        "kind": "material", "item_id": inv1["id"], "item_name": inv1["name"],
        "quantity": 80, "unit": "Nos", "allocated_to_type": "project",
        "project_code": project_code, "returnable": True,
        "remarks": "Tank T-401 west face erection",
    }, timeout=30)
    s.post(f"{API}/allocations", json={
        "kind": "material", "item_id": inv2["id"], "item_name": inv2["name"],
        "quantity": 50, "unit": "Nos", "allocated_to_type": "project",
        "project_code": project_code, "returnable": True,
        "remarks": "Tank T-401 west face erection",
    }, timeout=30)
    step("Material allocated: 80 verticals + 50 ledgers issued to site")

    # 8. DPR (submitted + approved)
    dpr = s.post(f"{API}/dprs", json={
        "date": "2026-04-12", "project_code": project_code,
        "site_name": "Tank Farm Zone A — T-401", "service_type": "scaffolding",
        "manpower": [
            {"role": "scaffolder", "count": 8},
            {"role": "supervisor", "count": 1},
            {"role": "safety_officer", "count": 1},
            {"role": "helper", "count": 4},
        ],
        "work_completed": "Erected scaffolding around T-401 west face up to L3. Final platform handover targeted by EoD tomorrow.",
        "material_used": [
            {"item_name": inv1["name"], "quantity": 80, "unit": "Nos"},
            {"item_name": inv2["name"], "quantity": 50, "unit": "Nos"},
        ],
        "safety_observations": "All PPE compliant. One near-miss reported and logged — falling spanner from L2 to grade. No injury. Toolbox refresh scheduled.",
        "client_instructions": "Client requested additional handrail on east face for upcoming inspector visit.",
        "supervisor_remarks": "Tomorrow: dismantle scaffolding around T-402 east platform.",
        "submit": True,
    }, timeout=30).json()
    s.post(f"{API}/dprs/{dpr['id']}/approve", json={"comment": "Approved — clear day's work"}, timeout=30)
    step(f"DPR {dpr['dpr_number']} submitted + approved")

    # 9. Measurement: 380 m² erected + 90 m² dismantled, all client-certified
    m = s.post(f"{API}/measurements", json={
        "date": "2026-04-13", "project_code": project_code,
        "site_name": "Tank Farm Zone A — T-401", "service_type": "scaffolding",
        "po_id": po["id"], "po_number": po["po_number"],
        "items": [
            {"service": "scaffolding", "activity": "erected", "description": "T-401 W face L1+L2+L3",
             "executed_qty": 400, "certified_qty": 380, "unit": "m²", "rate": 145},
            {"service": "scaffolding", "activity": "dismantled", "description": "T-402 E platform",
             "executed_qty": 95, "certified_qty": 90, "unit": "m²", "rate": 65},
        ],
        "joint_measured_with": "Mr. Anand Iyer", "client_designation": "Maintenance Lead",
        "submit": True,
    }, timeout=30).json()
    s.post(f"{API}/measurements/{m['id']}/certify", json={"signatory_name": "Anand Iyer", "signatory_designation": "Maintenance Lead"}, timeout=30)
    s.post(f"{API}/measurements/{m['id']}/approve-for-billing", timeout=30)
    step(f"Measurement {m['measurement_no']} — billable ₹{m['billable_value']:,.0f} — certified by client & approved")

    # 10. Use admin-configured billing defaults (or fallback)
    defaults = s.get(f"{API}/admin/billing-defaults", timeout=30).json()
    step(f"Using billing defaults: GST {defaults['gst_pct']}% · Retention {defaults['retention_pct']}% · TDS {defaults['tds_pct']}% · Due {defaults['due_days']}d")

    # 11. RA Bill from measurement (with the defaults from settings)
    b = s.post(f"{API}/ra-bills/from-measurements", json={
        "measurement_ids": [m["id"]],
        "client_id": client_id, "client_name": client_name,
        "po_id": po["id"], "po_number": po["po_number"],
        "gst_pct": defaults["gst_pct"],
        "retention_pct": defaults["retention_pct"] or 5,    # demo: walk-through forces 5% retention so retention KPI is visible
        "tds_pct": defaults["tds_pct"] or 2,                # demo: walk-through forces 2% TDS
    }, timeout=30).json()
    s.post(f"{API}/ra-bills/{b['id']}/submit", timeout=30)
    s.post(f"{API}/ra-bills/{b['id']}/approve", timeout=30)
    s.post(f"{API}/ra-bills/{b['id']}/issue-invoice", json={"due_days": defaults["due_days"], "issue_date": "2026-04-15"}, timeout=30)
    step(f"RA Bill {b['bill_number']} invoiced — gross ₹{b['gross_value']:,.0f} · net ₹{b['net_payable']:,.0f}")

    # 12. Partial payment (≈50%)
    half = round(b["net_payable"] / 2)
    s.post(f"{API}/payments-in", json={
        "client_id": client_id, "client_name": client_name,
        "amount": half, "mode": "neft", "reference_no": f"UTR-{TS}",
        "allocations": [{"ra_bill_id": b["id"], "amount": half}],
    }, timeout=30)
    step(f"Partial payment recorded: ₹{half:,.0f} (~50% — balance ₹{b['net_payable']-half:,.0f} pending)")

    banner("Walkthrough seeded ✓")
    print(f"\n  PROJECT CODE:  {project_code}")
    print(f"  CLIENT ID:     {client_id}")
    print(f"  PO #:          {po['po_number']}")
    print(f"  RFQ #:         {rfq['rfq_number']}")
    print(f"  DPR #:         {dpr['dpr_number']}")
    print(f"  MEASUREMENT #: {m['measurement_no']}")
    print(f"  RA BILL #:     {b['bill_number']}")
    print(f"  NET BILLED:    ₹{b['net_payable']:,.0f}")
    print(f"  PAID (~50%):   ₹{half:,.0f}\n")
    print("  Now visit these screens on the deployed app:")
    print(f"   • /app/projects → search '{project_code}'")
    print("   • /app/purchase-requisitions, /app/rfqs, /app/purchase-orders, /app/grn")
    print("   • /app/material-allocations")
    print("   • /app/dprs, /app/measurements")
    print("   • /app/ra-bills, /app/receivables")
    print("   • /app/project-ops → pick this project for snapshot + profitability\n")


if __name__ == "__main__":
    main()
