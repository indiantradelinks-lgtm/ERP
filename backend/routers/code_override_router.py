"""Admin-only Auto Code Override — central registry of auto-generated reference codes.

Default auto-generation stays untouched everywhere. This router only lets a
super_admin manually override a generated code with uniqueness validation + audit.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, now_iso
from audit import audit
from routers.admin_router import require_super_admin

router = APIRouter()

# key -> collection, code field, label, extra display fields for search results
CODE_REGISTRY = {
    "clients":               {"collection": "clients",               "field": "customer_code",  "label": "Clients — Customer Code",        "display": ["name"]},
    "sites":                 {"collection": "sites",                 "field": "site_code",      "label": "Sites — Site Code",              "display": ["name", "client_name"]},
    "enquiries":             {"collection": "enquiries",             "field": "enquiry_no",     "label": "Enquiries — Enquiry No",         "display": ["customer", "scope_of_work"]},
    "quotations":            {"collection": "quotations",            "field": "quote_number",   "label": "Sales & Quotations — Quote #",   "display": ["client", "project"]},
    "purchase_requisitions": {"collection": "purchase_requisitions", "field": "pr_number",      "label": "Purchase Requisitions — PR #",   "display": ["title", "department"]},
    "purchase_orders":       {"collection": "purchase_orders",       "field": "po_number",      "label": "Purchase Orders — PO #",         "display": ["vendor_name", "title"]},
    "grn":                   {"collection": "grn",                   "field": "grn_number",     "label": "GRN — GRN #",                    "display": ["vendor_name", "po_number"]},
    "projects":              {"collection": "projects",              "field": "code",           "label": "Projects — Project Code",        "display": ["name", "client_name"]},
    "vendors":               {"collection": "vendors",               "field": "code",           "label": "Vendors — Vendor Code",          "display": ["name"]},
    "inventory":             {"collection": "inventory",             "field": "code",           "label": "Item Master — Item Code",        "display": ["name", "category"]},
    "assets":                {"collection": "assets",                "field": "asset_id",       "label": "Assets — Asset ID",              "display": ["name", "category"]},
    "material_allocations":  {"collection": "material_allocations",  "field": "allocation_no",  "label": "Material Allocations — ALC #",   "display": ["item_name", "project_code"]},
    "employees":             {"collection": "employees",             "field": "emp_code",       "label": "Employees — Employee Code",      "display": ["name", "department"]},
    "work_orders":           {"collection": "work_orders",           "field": "wo_no",          "label": "Work Orders — WO #",             "display": ["client_name", "project_code"]},
    "bulk_allocations":      {"collection": "bulk_allocation_requests", "field": "request_no",  "label": "Bulk Allocations — BAL #",       "display": ["category", "requested_by"]},
    "challans":              {"collection": "challans",              "field": "challan_no",     "label": "Challans — Challan #",           "display": ["to_location", "vehicle_no"]},
    "material_requests":     {"collection": "material_requests",     "field": "mr_number",      "label": "Material Requests — MR #",       "display": ["site_code", "requested_by"]},
    "rfqs":                  {"collection": "rfqs",                  "field": "rfq_number",     "label": "RFQs — RFQ #",                   "display": ["title", "vendor_names"]},
}


class OverrideIn(BaseModel):
    resource: str
    record_id: str
    new_code: str


def _entry(resource: str) -> dict:
    e = CODE_REGISTRY.get(resource)
    if not e:
        raise HTTPException(status_code=404, detail=f"Unknown code resource '{resource}'")
    return e


@router.get("/admin/code-override/registry")
async def code_registry(user: dict = Depends(require_super_admin)):
    return [{"key": k, "label": v["label"], "field": v["field"]} for k, v in CODE_REGISTRY.items()]


@router.get("/admin/code-override/records")
async def search_records(resource: str, q: Optional[str] = None,
                         user: dict = Depends(require_super_admin)):
    e = _entry(resource)
    query = {}
    if q:
        ors = [{e["field"]: {"$regex": q, "$options": "i"}}]
        for f in e["display"]:
            ors.append({f: {"$regex": q, "$options": "i"}})
        query = {"$or": ors}
    proj = {"_id": 0, "id": 1, e["field"]: 1, **{f: 1 for f in e["display"]}}
    rows = await db[e["collection"]].find(query, proj).sort(e["field"], -1).to_list(25)
    return [{
        "id": r.get("id"),
        "code": r.get(e["field"]),
        "display": " · ".join(str(r.get(f)) for f in e["display"] if r.get(f)),
    } for r in rows]


@router.post("/admin/code-override")
async def apply_override(payload: OverrideIn, request: Request,
                         user: dict = Depends(require_super_admin)):
    e = _entry(payload.resource)
    new_code = payload.new_code.strip()
    if not new_code:
        raise HTTPException(status_code=400, detail="New code cannot be empty")
    if len(new_code) > 60:
        raise HTTPException(status_code=400, detail="Code too long (max 60 characters)")

    record = await db[e["collection"]].find_one({"id": payload.record_id}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    old_code = record.get(e["field"])
    if old_code == new_code:
        raise HTTPException(status_code=400, detail="New code is identical to the current code")

    # Uniqueness — case-insensitive exact match within the collection
    import re
    dup = await db[e["collection"]].find_one({
        e["field"]: {"$regex": f"^{re.escape(new_code)}$", "$options": "i"},
        "id": {"$ne": payload.record_id},
    }, {"_id": 0, "id": 1, e["field"]: 1})
    if dup:
        raise HTTPException(status_code=400, detail=f"Duplicate — code '{dup.get(e['field'])}' already exists in {e['label']}")

    upd = {
        e["field"]: new_code,
        "code_overridden_by": user.get("name") or user.get("email"),
        "code_overridden_at": now_iso(),
        "code_override_previous": old_code,
        "updated_at": now_iso(),
    }
    await db[e["collection"]].update_one({"id": payload.record_id}, {"$set": upd})
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    await audit(user=user, action="code_override", resource=e["collection"], record_id=payload.record_id,
                after={"field": e["field"], "old": old_code, "new": new_code}, ip=ip)
    return {"ok": True, "resource": payload.resource, "field": e["field"], "old_code": old_code, "new_code": new_code}
