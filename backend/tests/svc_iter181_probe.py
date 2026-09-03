"""Probe: exception-review invoice reserving invoiced_total + pay UI invoice SVI-2026-0006."""
import json
import requests
from dotenv import dotenv_values

API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)

pos = s.get(f"{API}/service-workflow/pos", timeout=60).json()
po = next(p for p in pos if p["po_no"] == "SPO-2026-0003")
print("PO:", po["po_no"], "total", po["total_value"], "accepted%", po.get("accepted_pct_total"),
      "invoiced_total", po.get("invoiced_total"), "status", po["status"], "payment", po.get("payment_status"))

# entitlement math check
entitled = po["total_value"] * (po.get("accepted_pct_total") or 0) / 100 - (po.get("invoiced_total") or 0)
print("entitled now:", round(entitled, 2), "(negative/blocked means exception invoice reserved value)")

# 2nd SRN for remaining 50%
r = s.post(f"{API}/service-workflow/pos/{po['id']}/srn",
           json={"completed_pct": 50, "accepted_pct": 50, "receipt_type": "full",
                 "service_details": "probe remaining 50", "submit": True}, timeout=60)
print("srn2 create:", r.status_code, r.text[:150])
srn2 = r.json()
a = s.post(f"{API}/service-workflow/srns/{srn2['id']}/action", json={"action": "approve", "remarks": "ok"}, timeout=60)
print("srn2 approve:", a.status_code)

inv = s.post(f"{API}/service-workflow/invoices", json={
    "po_id": po["id"], "srn_id": srn2["id"], "vendor_invoice_no": "PROBE-INV-C-181",
    "invoice_amount": 50000, "tax_amount": 9000}, timeout=60)
print("legit 2nd invoice status:", inv.status_code)
print("match:", json.dumps(inv.json().get("match", {}), indent=1)[:500] if inv.status_code < 400 else inv.text[:300])

# --- pay the UI-created invoice SVI-2026-0006 through payment queue ---
invs = s.get(f"{API}/service-workflow/invoices", timeout=60).json()
target = next(i for i in invs if i["inv_no"] == "SVI-2026-0006")
q = s.get(f"{API}/accounts/payment-queue", timeout=60).json()
q = q if isinstance(q, list) else q.get("rows", [])
pr = next((x for x in q if x.get("source_id") == target["id"]), None)
print("queue row found:", bool(pr), "amount", pr and pr.get("amount"))
v = s.post(f"{API}/accounts/payment-queue/{pr['id']}/verify", json={
    "decision": "verified", "vendor_name": target["vendor_name"], "vendor_account_no": "9988776655",
    "ifsc": "ICIC0000456", "bank_name": "ICICI", "invoice_no": target["vendor_invoice_no"],
    "invoice_date": target["invoice_date"], "verified_amount": target["net_payable"],
    "remarks": "UI-flow verify iter181"}, timeout=90)
print("verify:", v.status_code, v.text[:200])
m = s.post(f"{API}/accounts/payment-queue/{pr['id']}/mark-paid",
           json={"utr_no": "UTRUI181006", "paid_date": "2026-07-02"}, timeout=90)
print("mark-paid:", m.status_code, m.text[:200])

pay = s.get(f"{API}/service-workflow/payments", timeout=60).json()
row = next(x for x in pay if x["inv_no"] == "SVI-2026-0006")
print("module payment row:", row["status"], row.get("utr_no"), row.get("paid_date"))

det = s.get(f"{API}/service-workflow/requests/{target['sr_id']}", timeout=60).json()
tl = det.get("timeline") or []
print("SR status:", (det.get("request") or {}).get("status"))
print("timeline actions:", [e.get("action") for e in tl])
