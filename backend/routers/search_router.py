"""Universal ERP search — one query across every module's records, RBAC-filtered.

GET /api/search?q=term&limit=5  → grouped results with direct navigation routes.
"""
from __future__ import annotations

import asyncio
import re
import time
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, Depends, Query

from core import db, get_current_user
from rbac import can

router = APIRouter(prefix="/search", tags=["search"])

# Each entry: collection, label, module, perm (rbac resource), searchable fields,
# title fields (first non-empty wins), subtitle fields (joined with " · "),
# route (list page) and optional detail route template ({id} / {code}).
# `action` (default "read") lets self-scoped collections (read="*") require write access to be searchable.
REGISTRY = [
    # ── Sales ──
    dict(col="enquiries", label="Enquiries", module="Sales", perm="quotations", fields=["enquiry_no", "dept_doc_no", "customer", "service_type", "quotation_no"], title=["enquiry_no"], sub=["customer", "service_type", "status"], route="/app/enquiries"),
    dict(col="quotations", label="Quotations", module="Sales", perm="quotations", fields=["quote_number", "quotation_no", "client", "project", "customer"], title=["quote_number", "quotation_no"], sub=["client", "project", "status"], route="/app/quotations", detail="/app/quotations/{id}/builder"),
    dict(col="orders", label="Orders", module="Sales", perm="quotations", fields=["order_no", "customer", "service_type"], title=["order_no"], sub=["customer", "service_type", "status"], route="/app/orders"),
    dict(col="clients", label="Clients", module="Sales", perm="clients", fields=["name", "code", "customer_code", "contact", "email", "phone", "gst", "address"], title=["name"], sub=["code", "contact", "phone"], route="/app/clients"),
    dict(col="sites", label="Client Sites", module="Sales", perm="clients", fields=["name", "site_code", "client_name", "city", "state", "gst"], title=["name"], sub=["site_code", "client_name", "city"], route="/app/ops/site-master"),
    # ── Projects & Operations ──
    dict(col="projects", label="Projects", module="Projects & Operations", perm="projects", fields=["code", "name", "client", "site", "manager", "type"], title=["name"], sub=["code", "client", "site", "status"], route="/app/projects", detail="/app/project-dashboard/{id}"),
    dict(col="project_handovers", label="Project Handovers", module="Projects & Operations", perm="project_handovers", fields=["handover_no", "project_name", "client_name", "work_order_number", "site_location"], title=["handover_no"], sub=["project_name", "client_name", "status"], route="/app/ops/handovers"),
    dict(col="work_orders", label="Work Orders", module="Projects & Operations", perm="projects", fields=["wo_no", "source_handover_no", "scope"], title=["wo_no"], sub=["source_handover_no", "status"], route="/app/ops/work-orders"),
    dict(col="project_requests", label="Project Requests", module="Projects & Operations", perm="project_requests", fields=["request_no", "project_code", "project_name", "client_name", "description", "request_type_label", "upi_any_name"], title=["request_no"], sub=["project_code", "request_type_label", "status"], route="/app/ops/requests"),
    dict(col="dprs", label="Daily Progress Reports", module="Projects & Operations", perm="dprs", fields=["dpr_number", "dept_doc_no", "supervisor_name", "date"], title=["dpr_number"], sub=["date", "supervisor_name", "status"], route="/app/dprs"),
    dict(col="bill_requests", label="Bill Requests", module="Projects & Operations", perm="bill_requests", fields=["request_no", "project_code", "project_name", "client_name"], title=["request_no"], sub=["project_name", "client_name", "status"], route="/app/ops/bill-requests"),
    dict(col="material_requests", label="Material Requests", module="Projects & Operations", perm="project_requests", fields=["mr_number", "project_code", "remarks", "requested_by_name"], title=["mr_number"], sub=["project_code", "priority", "status"], route="/app/ops/resource-requests"),
    dict(col="safety_work_permits", label="Work Permits", module="Safety", perm="ptws", fields=["permit_no", "project_code", "activity", "work_area"], title=["permit_no"], sub=["project_code", "activity", "status"], route="/app/safety/work-permits"),
    # ── HR ──
    dict(col="employees", label="Employees", module="Human Resources", perm="employees", fields=["emp_code", "name", "email", "phone", "department", "role", "designation"], title=["name"], sub=["emp_code", "department", "role"], route="/app/employees"),
    dict(col="deployments", label="Deployments", module="Human Resources", perm="deployments", fields=["deployment_no", "employee", "project", "site_role"], title=["deployment_no"], sub=["employee", "project", "status"], route="/app/deployments"),
    dict(col="recruitment_requests", label="Recruitment Requests", module="Human Resources", perm="recruitment_requests", fields=["position", "department"], title=["position"], sub=["department", "status"], route="/app/recruitment"),
    dict(col="candidates", label="Candidates", module="Human Resources", perm="candidates", fields=["name", "phone", "position", "email"], title=["name"], sub=["position", "stage"], route="/app/candidates"),
    dict(col="employee_advances", label="Employee Advances", module="Human Resources", perm="hr_advances", action="write", fields=["advance_no", "employee_name", "employee_code", "advance_type"], title=["advance_no"], sub=["employee_name", "advance_type", "status"], route="/app/hr/advances"),
    dict(col="hr_letters", label="HR Letters", module="Human Resources", perm="hr_letters", fields=["employee_name", "template_name", "template_kind"], title=["template_name"], sub=["employee_name", "template_kind"], route="/app/hr/letters"),
    dict(col="payroll", label="Payroll", module="Human Resources", perm="payroll", fields=["employee_name", "month"], title=["employee_name"], sub=["month", "status"], route="/app/hr/payroll"),
    # ── Store & Inventory ──
    dict(col="inventory", label="Inventory Items", module="Store & Inventory", perm="inventory", fields=["code", "name", "category", "uom"], title=["name"], sub=["code", "category", "quantity"], route="/app/inventory"),
    dict(col="material_allocations", label="Material Allocations", module="Store & Inventory", perm="material_allocations", fields=["item_name", "project_code", "employee_name", "allocated_to_type"], title=["item_name"], sub=["project_code", "employee_name", "issue_date"], route="/app/material-allocations"),
    dict(col="challans", label="Challans", module="Store & Inventory", perm="challans", fields=["challan_no", "from_location", "to_location", "vehicle_no", "driver_name"], title=["challan_no"], sub=["from_location", "to_location", "status"], route="/app/challans"),
    dict(col="scaf_challans", label="Scaffolding Challans", module="Store & Inventory", perm="scaffolding", fields=["challan_no", "transfer_no", "from_location", "to_location", "vehicle_no"], title=["challan_no"], sub=["from_location", "to_location", "status"], route="/app/scaffolding"),
    dict(col="assets", label="Assets", module="Store & Inventory", perm="assets", fields=["asset_id", "name", "category", "location", "assigned_to"], title=["name"], sub=["asset_id", "category", "location"], route="/app/assets", detail="/app/asset-lifecycle/{id}"),
    # ── Procurement ──
    dict(col="vendors", label="Vendors", module="Procurement & Vendors", perm="vendors", fields=["name", "code", "contact", "email", "phone", "gst", "category"], title=["name"], sub=["code", "category", "status"], route="/app/vendors"),
    dict(col="purchase_requisitions", label="Purchase Requisitions", module="Procurement & Vendors", perm="purchase_requisitions", fields=["pr_number", "dept_doc_no", "project_code", "department", "requested_by", "remarks"], title=["pr_number"], sub=["project_code", "department", "status"], route="/app/purchase-requisitions"),
    dict(col="rfqs", label="RFQs", module="Procurement & Vendors", perm="rfqs", fields=["rfq_number", "dept_doc_no", "pr_number", "notes"], title=["rfq_number"], sub=["pr_number", "status"], route="/app/rfqs"),
    dict(col="purchase_orders", label="Purchase Orders", module="Procurement & Vendors", perm="purchase_orders", fields=["po_number", "vendor", "rfq_number", "pr_number", "project"], title=["po_number"], sub=["vendor", "project", "status"], route="/app/purchase-orders"),
    dict(col="grn", label="Goods Receipts (GRN)", module="Procurement & Vendors", perm="grn", fields=["grn_number", "po_number", "vendor_name", "store_location"], title=["grn_number"], sub=["po_number", "vendor_name", "inspection_status"], route="/app/grn"),
    dict(col="rate_contracts", label="Rate Contracts", module="Procurement & Vendors", perm="vendors", fields=["rc_number", "vendor_name"], title=["rc_number"], sub=["vendor_name", "status"], route="/app/procurement/rate-contracts"),
    dict(col="service_orders", label="Service Orders", module="Procurement & Vendors", perm="vendors", fields=["so_number", "vendor_name", "service_type", "scope_of_work"], title=["so_number"], sub=["vendor_name", "service_type"], route="/app/procurement/service-orders"),
    # ── Service Workflow ──
    dict(col="svc_requests", label="Service Requests", module="Service Workflow", perm="service_workflow", fields=["sr_no", "service_type", "service_category", "service_description", "project_code", "project_name", "department"], title=["sr_no", "service_type"], sub=["service_category", "department", "status"], route="/app/services/requests", detail="/app/services/requests/{id}"),
    dict(col="svc_pos", label="Service POs", module="Service Workflow", perm="service_workflow", fields=["po_no", "rfq_no", "sr_no", "vendor_name", "project_code"], title=["po_no"], sub=["vendor_name", "sr_no", "status"], route="/app/services/pos"),
    dict(col="svc_invoices", label="Service Invoices", module="Service Workflow", perm="service_workflow", fields=["inv_no", "vendor_invoice_no", "po_no", "srn_no"], title=["inv_no"], sub=["vendor_invoice_no", "po_no", "status"], route="/app/services/invoices"),
    # ── Accounts & Finance ──
    dict(col="client_invoices", label="Client Invoices", module="Accounts", perm="receivables", fields=["invoice_no", "client_name", "project_code", "work_order_no"], title=["invoice_no"], sub=["client_name", "project_code", "status"], route="/app/receivables"),
    dict(col="client_receipts", label="Receipts", module="Accounts", perm="receivables", fields=["receipt_no", "client_name", "txn_reference", "mode"], title=["receipt_no"], sub=["client_name", "mode", "amount"], route="/app/receivables"),
    dict(col="ra_bills", label="RA Bills", module="Accounts", perm="ra_bills", fields=["bill_number", "client_name", "project_code", "site_name", "po_number"], title=["bill_number"], sub=["client_name", "project_code", "status"], route="/app/ra-bills"),
    dict(col="vendor_bills", label="Vendor Bills", module="Accounts", perm="accounting", fields=["bill_no", "vendor_name", "invoice_no", "expense_category"], title=["bill_no"], sub=["vendor_name", "invoice_no", "status"], route="/app/accounts/payment-processing"),
    dict(col="journal_entries", label="Journal Entries", module="Accounts", perm="journal_entries", fields=["je_number", "account", "narration", "cost_centre", "type"], title=["je_number"], sub=["account", "narration", "amount"], route="/app/accounts"),
    dict(col="chart_of_accounts", label="Chart of Accounts", module="Accounts", perm="accounting", fields=["code", "name", "type", "subtype"], title=["name"], sub=["code", "type"], route="/app/accounts"),
    dict(col="cost_centers", label="Cost Centers", module="Accounts", perm="accounting", fields=["code", "name", "project_code", "category_name"], title=["name"], sub=["code", "project_code"], route="/app/admin/cost-centers"),
    # ── Logistics ──
    dict(col="vehicles", label="Vehicles", module="Logistics", perm="vehicles", fields=["reg_number", "type", "driver", "capacity"], title=["reg_number"], sub=["type", "driver", "status"], route="/app/logistics/vehicles"),
    dict(col="drivers", label="Drivers", module="Logistics", perm="drivers", fields=["driver_name", "driver_code", "license_no", "phone"], title=["driver_name"], sub=["driver_code", "license_no", "status"], route="/app/logistics/drivers"),
    dict(col="logistics_dispatch_requests", label="Dispatch Requests", module="Logistics", perm="dispatch_requests", fields=["dr_no", "dispatch_type", "project_code", "project_name"], title=["dr_no"], sub=["dispatch_type", "priority", "status"], route="/app/logistics/dispatch-requests", detail="/app/logistics/dispatch-requests/{id}"),
    # ── Safety ──
    dict(col="safety_incidents", label="Safety Incidents", module="Safety", perm="safety_incidents", fields=["incident_no", "project_code", "incident_type", "description", "site_location"], title=["incident_no", "incident_type"], sub=["project_code", "incident_datetime"], route="/app/safety/incidents"),
    dict(col="safety_capa", label="CAPA", module="Safety", perm="safety_capa", fields=["capa_no", "project_code", "description", "action"], title=["capa_no", "description"], sub=["project_code", "status"], route="/app/safety/capa"),
    # ── Documents & Admin ──
    dict(col="documents", label="Documents", module="Documents", perm="documents", fields=["doc_id", "title", "category", "project"], title=["title"], sub=["doc_id", "category", "project"], route="/app/documents"),
    dict(col="dms_documents", label="DMS Documents", module="Documents", perm="documents", fields=["doc_no", "title", "module", "project_code", "project_name", "category_name"], title=["title"], sub=["doc_no", "project_code", "category_name"], route="/app/dms"),
    dict(col="approvals", label="Approvals", module="Approvals", perm="approvals", fields=["title", "type", "requested_by"], title=["title"], sub=["type", "status"], route="/app/approvals"),
    dict(col="users", label="Users", module="Management & Admin", perm="users", fields=["name", "email", "role", "department", "phone"], title=["name"], sub=["email", "role"], route="/app/admin/users"),
]

STATUS_KEYS = ("status", "stage", "inspection_status")


def _first(doc: dict, keys: list[str]) -> str:
    for k in keys:
        v = doc.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def _fmt_sub(doc: dict, keys: list[str]) -> str:
    return " · ".join(str(doc[k]) for k in keys if doc.get(k) not in (None, ""))


async def _search_one(entry: dict, rx: re.Pattern, limit: int) -> Optional[dict]:
    fields = entry["fields"]
    proj = {"_id": 0, "id": 1, "code": 1}
    for k in fields + entry["title"] + entry["sub"] + list(STATUS_KEYS):
        proj[k] = 1
    try:
        docs = await db[entry["col"]].find({"$or": [{f: rx} for f in fields]}, proj).limit(limit).to_list(limit)
    except Exception:
        return None
    if not docs:
        return None
    items = []
    for d in docs:
        rid = d.get("id") or ""
        title = _first(d, entry["title"]) or rid
        detail = entry.get("detail")
        route = detail.replace("{id}", rid).replace("{code}", str(d.get("code") or "")) if detail and rid else f"{entry['route']}?q={quote(title[:80])}&hl={quote(rid)}"
        items.append({
            "id": rid,
            "title": title,
            "subtitle": _fmt_sub(d, entry["sub"]),
            "status": _first(d, list(STATUS_KEYS)),
            "route": route,
        })
    return {"key": entry["col"], "label": entry["label"], "module": entry["module"], "route": entry["route"], "items": items}


@router.get("")
async def universal_search(
    q: str = Query("", min_length=0),
    limit: int = Query(5, ge=1, le=20),
    user: dict = Depends(get_current_user),
):
    term = (q or "").strip()
    if len(term) < 2:
        return {"query": term, "groups": [], "total": 0, "took_ms": 0}
    t0 = time.perf_counter()
    rx = re.compile(re.escape(term), re.IGNORECASE)
    role = user.get("role")
    allowed = [e for e in REGISTRY if can(role, e["perm"], e.get("action", "read"))]
    results = await asyncio.gather(*[_search_one(e, rx, limit) for e in allowed])
    groups = [g for g in results if g]
    total = sum(len(g["items"]) for g in groups)
    return {"query": term, "groups": groups, "total": total, "took_ms": round((time.perf_counter() - t0) * 1000)}


@router.get("/scope")
async def search_scope(user: dict = Depends(get_current_user)):
    role = user.get("role")
    return [{"key": e["col"], "label": e["label"], "module": e["module"]} for e in REGISTRY if can(role, e["perm"], e.get("action", "read"))]
