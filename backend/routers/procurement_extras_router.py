"""Procurement & Vendors — Gap-Fill Router (Iteration 107)

Extends the existing Procurement & Vendors module with the pieces that were
NOT yet implemented in earlier iterations:

  • Vendor Type taxonomy (Material Supplier · Labour Contractor · Transporter
    · Equipment Rental · Service Provider · Fabrication · Safety-PPE · …)
    -- top-level enum field on vendors, distinct from item-level categories.

  • Rate Contracts          (db.rate_contracts)
        Approved vendor + item + period + locked rate; surfaces a
        "suggest vendor" hint when a PR is raised for a covered item.
        Expiry alerts (T-30 by default).

  • Service Orders (SO)     (db.service_orders)
        Counterpart of PO for service vendors / labour contractors /
        subcontractors. Captures rate_basis (per_day / per_month / per_qty /
        lump_sum / per_manpower / per_shift) + service period.

  • Service Receipt Notes   (db.service_receipt_notes)
        Counterpart of GRN for SOs — captures certified value, site-incharge
        approval, optional link to measurement_sheet.

  • Quality Inspection      (db.quality_inspections)
        Extends GRN with structured inspection data + rejection-with-reason +
        replacement tracking + auto-draft debit note.

  • Document Expiry Alerts  (read-only view over vendors[].documents)
        Surfaces vendor documents expiring within the configured window.

  • Procurement Notifications (db.procurement_notifications)
        Unified inbox: PR pending, RFQ pending, PO overdue, GRN pending bill,
        bill awaiting approval, payment due, contract/document expiring …

  • Vendor performance 5-tier label  (Excellent / Good / Average / Poor /
        Blacklisted)  derived from the existing rolling score.

  • Stock-availability check    (helper endpoint used during PR raise/approval
        flow — returns on-hand stock vs requested qty per line).

All collections are lazy-created. No migrations required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core import db, require_permission, get_current_user, now_iso, new_id
from audit import audit
from sequences import next_sequence
from offload import run_blocking

router = APIRouter(prefix="/procurement-extras", tags=["procurement-extras"])

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
VENDOR_TYPES = [
    "material_supplier", "labour_contractor", "subcontractor",
    "transporter", "equipment_rental", "service_provider",
    "fabrication", "safety_ppe", "tools_tackles",
    "paint_supplier", "scaffolding_supplier", "rope_access_supplier",
    "roofing_material_supplier", "admin_vendor", "other",
]

RATE_BASIS = ("per_day", "per_month", "per_qty", "lump_sum", "per_manpower", "per_shift")

RC_STATUSES = ("draft", "active", "expired", "cancelled")
SO_STATUSES = ("draft", "pending_approval", "approved", "in_progress", "partially_received", "closed", "cancelled")
SRN_STATUSES = ("draft", "approved", "rejected")
QI_STATUSES = ("draft", "accepted", "partially_accepted", "rejected", "hold")

DEFAULT_EXPIRY_WINDOW_DAYS = 30

PERF_TIER_LABELS = [
    ("Excellent", 90.0),
    ("Good", 75.0),
    ("Average", 60.0),
    ("Poor", 40.0),
    ("Blacklisted", 0.0),  # forced if vendor.status == 'blocked'/'inactive'
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ip(req: Request) -> str:
    return req.client.host if req.client else "unknown"


def _strip(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return d
    d.pop("_id", None)
    return d


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _grade_to_tier(score: float, vendor_status: Optional[str]) -> str:
    if vendor_status in ("blocked", "inactive", "blacklisted"):
        return "Blacklisted"
    for label, threshold in PERF_TIER_LABELS:
        if label == "Blacklisted":
            continue
        if score >= threshold:
            return label
    return "Poor"


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR TYPE — extend the vendor doc (in-place patch endpoint)
# ─────────────────────────────────────────────────────────────────────────────
class VendorTypePatch(BaseModel):
    vendor_type: str = Field(..., description="One of VENDOR_TYPES")


@router.get("/vendor-types")
async def list_vendor_types(_: dict = Depends(get_current_user)):
    """Return the canonical list of vendor types with vendor counts."""
    counts: Dict[str, int] = {}
    pipeline = [{"$group": {"_id": "$vendor_type", "n": {"$sum": 1}}}]
    async for row in db.vendors.aggregate(pipeline):
        counts[row["_id"] or "unset"] = row["n"]
    types = [{"code": vt, "label": vt.replace("_", " ").title(), "count": counts.get(vt, 0)} for vt in VENDOR_TYPES]
    types.append({"code": "unset", "label": "(Unset)", "count": counts.get("unset", 0)})
    return types


@router.patch("/vendors/{vendor_id}/type")
async def set_vendor_type(vendor_id: str, payload: VendorTypePatch, request: Request,
                          user: dict = Depends(require_permission("vendors", "write"))):
    if payload.vendor_type not in VENDOR_TYPES:
        raise HTTPException(400, f"vendor_type must be one of {VENDOR_TYPES}")
    existing = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Vendor not found")
    await db.vendors.update_one(
        {"id": vendor_id},
        {"$set": {"vendor_type": payload.vendor_type, "updated_at": now_iso(),
                  "updated_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="set_vendor_type", resource="vendors",
                record_id=vendor_id, before={"vendor_type": existing.get("vendor_type")},
                after={"vendor_type": payload.vendor_type}, ip=_ip(request))
    return {"ok": True, "vendor_id": vendor_id, "vendor_type": payload.vendor_type}


# ─────────────────────────────────────────────────────────────────────────────
# RATE CONTRACTS
# ─────────────────────────────────────────────────────────────────────────────
class RateContractLine(BaseModel):
    item_id: Optional[str] = None
    item_code: Optional[str] = None
    item_name: str
    unit: str = "Nos"
    rate: float
    gst_percent: float = 18.0
    min_order_qty: Optional[float] = None
    remarks: Optional[str] = None


class RateContractIn(BaseModel):
    vendor_id: str
    vendor_name: Optional[str] = None
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    payment_terms: Optional[str] = None
    delivery_terms: Optional[str] = None
    freight_terms: Optional[str] = None
    escalation_clause: Optional[str] = None
    applicable_projects: List[str] = []
    contract_value_limit: Optional[float] = None
    document_file_id: Optional[str] = None
    notes: Optional[str] = None
    lines: List[RateContractLine] = []


@router.get("/rate-contracts")
async def list_rate_contracts(vendor_id: Optional[str] = None, status: Optional[str] = None,
                              user: dict = Depends(require_permission("vendors", "read"))):
    q: Dict[str, Any] = {}
    if vendor_id:
        q["vendor_id"] = vendor_id
    if status:
        q["status"] = status
    rows = await db.rate_contracts.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    # auto-flip to expired if past end_date
    today = _today_str()
    for r in rows:
        if r.get("status") == "active" and (r.get("end_date") or "9999-12-31") < today:
            await db.rate_contracts.update_one({"id": r["id"]}, {"$set": {"status": "expired"}})
            r["status"] = "expired"
    return rows


@router.get("/rate-contracts/expiring/list")
async def list_expiring_contracts(window_days: int = Query(DEFAULT_EXPIRY_WINDOW_DAYS),
                                  user: dict = Depends(require_permission("vendors", "read"))):
    """Active rate contracts expiring within the window (default 30 days)."""
    today = datetime.now(timezone.utc).date()
    horizon = (today + timedelta(days=window_days)).strftime("%Y-%m-%d")
    q = {"status": "active", "end_date": {"$lte": horizon}}
    rows = await db.rate_contracts.find(q, {"_id": 0}).sort("end_date", 1).to_list(500)
    for r in rows:
        end = _parse_date(r.get("end_date"))
        r["days_to_expiry"] = (end.date() - today).days if end else None
    return {"window_days": window_days, "count": len(rows), "rows": rows}


@router.get("/rate-contracts/suggest")
async def suggest_rate_contract(item_id: Optional[str] = None, item_name: Optional[str] = None,
                                user: dict = Depends(require_permission("vendors", "read"))):
    """For a given PR line item, return active rate contracts that cover it."""
    if not item_id and not item_name:
        raise HTTPException(400, "Provide item_id or item_name")
    today = _today_str()
    q: Dict[str, Any] = {
        "status": "active",
        "start_date": {"$lte": today},
        "end_date": {"$gte": today},
    }
    if item_id:
        q["lines.item_id"] = item_id
    else:
        q["lines.item_name"] = item_name
    rows = await db.rate_contracts.find(q, {"_id": 0}).to_list(50)
    matches = []
    for rc in rows:
        for line in rc.get("lines", []):
            if (item_id and line.get("item_id") == item_id) or \
               (item_name and line.get("item_name") == item_name):
                matches.append({
                    "rc_id": rc["id"], "rc_number": rc.get("rc_number"),
                    "vendor_id": rc.get("vendor_id"), "vendor_name": rc.get("vendor_name"),
                    "rate": line.get("rate"), "unit": line.get("unit"),
                    "gst_percent": line.get("gst_percent"),
                    "end_date": rc.get("end_date"),
                })
    return {"count": len(matches), "matches": matches}


@router.get("/rate-contracts/{rc_id}")
async def get_rate_contract(rc_id: str, user: dict = Depends(require_permission("vendors", "read"))):
    row = await db.rate_contracts.find_one({"id": rc_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Rate contract not found")
    return row


@router.post("/rate-contracts")
async def create_rate_contract(payload: RateContractIn, request: Request,
                               user: dict = Depends(require_permission("vendors", "write"))):
    vendor = await db.vendors.find_one({"id": payload.vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    if vendor.get("status") in ("blocked", "inactive", "blacklisted"):
        raise HTTPException(400, f"Vendor is {vendor.get('status')} — cannot create rate contract")
    if not _parse_date(payload.start_date) or not _parse_date(payload.end_date):
        raise HTTPException(400, "Invalid start/end date (YYYY-MM-DD)")
    if payload.end_date <= payload.start_date:
        raise HTTPException(400, "end_date must be after start_date")

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["rc_number"] = await next_sequence("RC")
    doc["vendor_name"] = doc.get("vendor_name") or vendor.get("name")
    doc["status"] = "draft"
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    await db.rate_contracts.insert_one(doc)
    await audit(user=user, action="create", resource="rate_contracts",
                record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.post("/rate-contracts/{rc_id}/activate")
async def activate_rate_contract(rc_id: str, request: Request,
                                 user: dict = Depends(require_permission("vendors", "write"))):
    rc = await db.rate_contracts.find_one({"id": rc_id}, {"_id": 0})
    if not rc:
        raise HTTPException(404, "Rate contract not found")
    if rc.get("status") != "draft":
        raise HTTPException(400, f"Cannot activate — current status is {rc.get('status')}")
    if not rc.get("lines"):
        raise HTTPException(400, "Cannot activate — at least one line item required")
    await db.rate_contracts.update_one(
        {"id": rc_id},
        {"$set": {"status": "active", "activated_at": now_iso(),
                  "activated_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="activate", resource="rate_contracts",
                record_id=rc_id, after={"status": "active"}, ip=_ip(request))
    return {"ok": True, "rc_id": rc_id, "status": "active"}


@router.post("/rate-contracts/{rc_id}/cancel")
async def cancel_rate_contract(rc_id: str, reason: str = Query(..., min_length=3), request: Request = None,
                               user: dict = Depends(require_permission("vendors", "write"))):
    rc = await db.rate_contracts.find_one({"id": rc_id}, {"_id": 0})
    if not rc:
        raise HTTPException(404, "Rate contract not found")
    await db.rate_contracts.update_one(
        {"id": rc_id},
        {"$set": {"status": "cancelled", "cancel_reason": reason,
                  "cancelled_at": now_iso(),
                  "cancelled_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="cancel", resource="rate_contracts",
                record_id=rc_id, after={"status": "cancelled", "reason": reason},
                ip=_ip(request) if request else "")
    return {"ok": True, "rc_id": rc_id, "status": "cancelled"}


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE ORDERS (SO) — counterpart of PO for service vendors
# ─────────────────────────────────────────────────────────────────────────────
class ServiceOrderIn(BaseModel):
    vendor_id: str
    pr_id: Optional[str] = None
    pr_number: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_id: Optional[str] = None
    service_type: str       # scaffolding/painting/manpower/transport/...
    scope_of_work: str
    rate_basis: str         # one of RATE_BASIS
    rate: float
    quantity: float = 1
    unit: str = "Lump"      # e.g. day / month / mt / nos / shift
    start_date: str
    end_date: str
    gst_percent: float = 18.0
    tds_applicable: bool = False
    tds_percent: float = 1.0
    payment_terms: Optional[str] = None
    attendance_required: bool = False
    safety_compliance_required: bool = False
    hr_compliance_required: bool = False
    notes: Optional[str] = None


@router.get("/service-orders")
async def list_service_orders(project_id: Optional[str] = None, vendor_id: Optional[str] = None,
                              status: Optional[str] = None,
                              user: dict = Depends(require_permission("purchase_orders", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if vendor_id:
        q["vendor_id"] = vendor_id
    if status:
        q["status"] = status
    rows = await db.service_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.get("/service-orders/{so_id}")
async def get_service_order(so_id: str, user: dict = Depends(require_permission("purchase_orders", "read"))):
    row = await db.service_orders.find_one({"id": so_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Service order not found")
    # attach SRNs
    row["receipts"] = await db.service_receipt_notes.find(
        {"so_id": so_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return row


@router.post("/service-orders")
async def create_service_order(payload: ServiceOrderIn, request: Request,
                               user: dict = Depends(require_permission("purchase_orders", "write"))):
    if payload.rate_basis not in RATE_BASIS:
        raise HTTPException(400, f"rate_basis must be one of {RATE_BASIS}")
    if not (payload.pr_id or payload.pr_number):
        raise HTTPException(400, "No Service Order can be raised without a PR — enter a valid PR Number")
    pr = await db.purchase_requisitions.find_one(
        {"$or": [{"id": payload.pr_id or ""}, {"pr_number": payload.pr_number or ""}]}, {"_id": 0})
    if not pr:
        raise HTTPException(400, f"PR '{payload.pr_number or payload.pr_id}' not found — a valid PR is mandatory to raise an SO")
    if float(payload.quantity or 0) <= 0:
        raise HTTPException(400, "Data missing: quantity is zero — enter a valid quantity")
    if float(payload.rate or 0) <= 0:
        raise HTTPException(400, "Data missing: rate/price is zero — enter a valid rate")
    vendor = await db.vendors.find_one({"id": payload.vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    if vendor.get("status") in ("blocked", "inactive", "blacklisted"):
        raise HTTPException(400, f"Vendor is {vendor.get('status')}")
    if payload.end_date <= payload.start_date:
        raise HTTPException(400, "end_date must be after start_date")

    base = float(payload.quantity) * float(payload.rate)
    gst_amt = round(base * float(payload.gst_percent) / 100.0, 2)
    tds_amt = round(base * float(payload.tds_percent) / 100.0, 2) if payload.tds_applicable else 0.0
    total = round(base + gst_amt, 2)

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["pr_id"] = pr["id"]
    doc["pr_number"] = pr.get("pr_number")
    doc["so_number"] = await next_sequence("SO")
    doc["vendor_name"] = vendor.get("name")
    doc["base_amount"] = round(base, 2)
    doc["gst_amount"] = gst_amt
    doc["tds_amount"] = tds_amt
    doc["total_amount"] = total
    doc["status"] = "draft"
    doc["received_value"] = 0.0
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    await db.service_orders.insert_one(doc)
    await audit(user=user, action="create", resource="service_orders",
                record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.post("/service-orders/{so_id}/approve")
async def approve_service_order(so_id: str, request: Request,
                                user: dict = Depends(require_permission("purchase_orders", "write"))):
    so = await db.service_orders.find_one({"id": so_id}, {"_id": 0})
    if not so:
        raise HTTPException(404, "Service order not found")
    if so.get("status") not in ("draft", "pending_approval"):
        raise HTTPException(400, f"Cannot approve — status is {so.get('status')}")
    if user.get("role") not in ("super_admin", "director", "general_manager", "purchase_officer", "project_manager"):
        raise HTTPException(403, "Insufficient role to approve service order")
    await db.service_orders.update_one(
        {"id": so_id},
        {"$set": {"status": "approved", "approved_at": now_iso(),
                  "approved_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="approve", resource="service_orders",
                record_id=so_id, after={"status": "approved"}, ip=_ip(request))
    return {"ok": True, "so_id": so_id, "status": "approved"}


@router.post("/service-orders/{so_id}/cancel")
async def cancel_service_order(so_id: str, reason: str = Query(..., min_length=3), request: Request = None,
                               user: dict = Depends(require_permission("purchase_orders", "write"))):
    so = await db.service_orders.find_one({"id": so_id}, {"_id": 0})
    if not so:
        raise HTTPException(404, "Service order not found")
    if so.get("status") == "closed":
        raise HTTPException(400, "Cannot cancel a closed SO")
    await db.service_orders.update_one(
        {"id": so_id},
        {"$set": {"status": "cancelled", "cancel_reason": reason,
                  "cancelled_at": now_iso(),
                  "cancelled_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="cancel", resource="service_orders",
                record_id=so_id, after={"status": "cancelled", "reason": reason},
                ip=_ip(request) if request else "")
    return {"ok": True, "so_id": so_id, "status": "cancelled"}


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE RECEIPT NOTES (SRN)
# ─────────────────────────────────────────────────────────────────────────────
class SRNIn(BaseModel):
    so_id: str
    service_period_from: str
    service_period_to: str
    work_completed: str
    certified_quantity: float
    certified_value: float
    measurement_sheet_id: Optional[str] = None
    attendance_ref: Optional[str] = None
    attachments: List[str] = []  # file_ids
    notes: Optional[str] = None


@router.get("/srns")
async def list_srns(so_id: Optional[str] = None, project_id: Optional[str] = None,
                    user: dict = Depends(require_permission("purchase_orders", "read"))):
    q: Dict[str, Any] = {}
    if so_id:
        q["so_id"] = so_id
    if project_id:
        q["project_id"] = project_id
    rows = await db.service_receipt_notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


TERMS_SEED = [
    {"category": "payment", "title": "Payment 30 Days", "body": "Payment within 30 days from date of GRN acceptance and receipt of correct tax invoice.", "is_default": True, "sort_order": 1},
    {"category": "payment", "title": "Payment 45 Days", "body": "Payment within 45 days from date of GRN acceptance and receipt of correct tax invoice.", "is_default": False, "sort_order": 2},
    {"category": "advance", "title": "No Advance", "body": "No advance payment. 100% against delivery and acceptance.", "is_default": True, "sort_order": 1},
    {"category": "advance", "title": "Advance Against PI", "body": "Advance released only against Proforma Invoice and approved advance request; adjusted in first bill.", "is_default": False, "sort_order": 2},
    {"category": "tds", "title": "TDS As Applicable", "body": "TDS shall be deducted at applicable rates under the Income Tax Act (194C/194J etc.) at the time of payment.", "is_default": True, "sort_order": 1},
    {"category": "delivery", "title": "Delivery Schedule", "body": "Material/services to be delivered as per delivery schedule mentioned in the PO. Delays to be intimated in writing in advance.", "is_default": True, "sort_order": 1},
    {"category": "inclusions", "title": "Freight & Packing Included", "body": "Rates are inclusive of freight, packing, forwarding and unloading at site unless stated otherwise.", "is_default": True, "sort_order": 1},
    {"category": "exclusions", "title": "GST Extra", "body": "GST extra as applicable at actuals against valid tax invoice.", "is_default": True, "sort_order": 1},
    {"category": "warranty", "title": "Replacement Warranty", "body": "Defective/damaged material to be replaced free of cost within 7 days of intimation.", "is_default": True, "sort_order": 1},
    {"category": "penalty", "title": "LD Clause", "body": "Liquidated damages @0.5% per week of delay subject to a maximum of 5% of PO value.", "is_default": False, "sort_order": 1},
    {"category": "general", "title": "Quality & Spec", "body": "Supply strictly as per agreed specifications/approved samples. Rejections to be lifted back at vendor's cost.", "is_default": True, "sort_order": 1},
]


@router.get("/terms-templates")
async def list_terms_templates(user: dict = Depends(require_permission("purchase_orders", "read"))):
    if await db.po_terms_templates.count_documents({}) == 0:
        for t in TERMS_SEED:
            await db.po_terms_templates.insert_one({**t, "id": new_id(), "created_at": now_iso(), "created_by": "system"})
    return [t async for t in db.po_terms_templates.find({}, {"_id": 0}).sort([("category", 1), ("sort_order", 1), ("title", 1)])]


@router.post("/terms-templates")
async def create_terms_template(payload: dict, user: dict = Depends(require_permission("purchase_orders", "write"))):
    if not payload.get("title") or not payload.get("body"):
        raise HTTPException(400, "title and body required")
    doc = {"id": new_id(), "category": payload.get("category") or "general",
           "title": payload["title"], "body": payload["body"],
           "is_default": bool(payload.get("is_default")), "sort_order": int(payload.get("sort_order") or 99),
           "created_at": now_iso(), "created_by": user.get("name") or user.get("email")}
    await db.po_terms_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/terms-templates/{tid}")
async def update_terms_template(tid: str, payload: dict, user: dict = Depends(require_permission("purchase_orders", "write"))):
    upd = {k: payload[k] for k in ("category", "title", "body", "is_default", "sort_order") if k in payload}
    upd["updated_at"] = now_iso()
    r = await db.po_terms_templates.update_one({"id": tid}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Template not found")
    return await db.po_terms_templates.find_one({"id": tid}, {"_id": 0})


@router.delete("/terms-templates/{tid}")
async def delete_terms_template(tid: str, user: dict = Depends(require_permission("purchase_orders", "write"))):
    r = await db.po_terms_templates.delete_one({"id": tid})
    if not r.deleted_count:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


@router.put("/pos/{po_id}/terms")
async def set_po_terms(po_id: str, payload: dict, user: dict = Depends(require_permission("purchase_orders", "write"))):
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0, "id": 1})
    if not po:
        raise HTTPException(404, "PO not found")
    terms_structured = payload.get("terms_structured") or []
    text = "  ".join(f"{i + 1}. {t.get('title')}: {t.get('body')}" for i, t in enumerate(terms_structured))
    await db.purchase_orders.update_one({"id": po_id}, {"$set": {
        "terms_structured": terms_structured, "terms": text or payload.get("terms"),
        "updated_at": now_iso()}})
    return await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})


@router.get("/srns/{srn_id}/pdf")
async def srn_pdf(srn_id: str, user: dict = Depends(require_permission("purchase_orders", "read"))):
    srn = await db.service_receipt_notes.find_one({"id": srn_id}, {"_id": 0})
    if not srn:
        raise HTTPException(404, "SRN not found")
    so = await db.service_orders.find_one({"id": srn.get("so_id")}, {"_id": 0})
    vendor = await db.vendors.find_one({"id": srn.get("vendor_id")}, {"_id": 0}) if srn.get("vendor_id") else None
    from pdf_generator import render_srn_pdf
    pdf = await run_blocking(render_srn_pdf, srn, so, vendor)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{srn.get("srn_number") or srn_id}.pdf"'})


@router.post("/srns")
async def create_srn(payload: SRNIn, request: Request,
                     user: dict = Depends(require_permission("purchase_orders", "write"))):
    so = await db.service_orders.find_one({"id": payload.so_id}, {"_id": 0})
    if not so:
        raise HTTPException(404, "Service order not found")
    if so.get("status") not in ("approved", "in_progress", "partially_received"):
        raise HTTPException(400, f"Cannot record receipt — SO status is {so.get('status')}")
    if payload.certified_value <= 0:
        raise HTTPException(400, "certified_value must be > 0")

    existing_received = float(so.get("received_value") or 0.0)
    so_total = float(so.get("total_amount") or 0.0)
    new_received = existing_received + float(payload.certified_value)
    if new_received > so_total * 1.10:  # 10% tolerance
        raise HTTPException(400, f"Certified value {new_received} exceeds SO total {so_total} by >10%")

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["srn_number"] = await next_sequence("SRN")
    doc["so_number"] = so.get("so_number")
    doc["vendor_id"] = so.get("vendor_id")
    doc["vendor_name"] = so.get("vendor_name")
    doc["project_id"] = so.get("project_id")
    doc["project_code"] = so.get("project_code")
    doc["status"] = "approved"  # SRN issued by PM = auto-approved
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    await db.service_receipt_notes.insert_one(doc)

    # update SO
    new_status = "closed" if new_received >= so_total * 0.99 else "partially_received"
    await db.service_orders.update_one(
        {"id": payload.so_id},
        {"$set": {"received_value": round(new_received, 2), "status": new_status,
                  "last_srn_at": now_iso()}},
    )
    await audit(user=user, action="create", resource="service_receipt_notes",
                record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


# ─────────────────────────────────────────────────────────────────────────────
# QUALITY INSPECTION (QI) — extends GRN flow
# ─────────────────────────────────────────────────────────────────────────────
class QIRejectedItem(BaseModel):
    item_name: str
    rejected_qty: float
    reason: str
    replacement_required: bool = True
    debit_note_required: bool = False


class QIIn(BaseModel):
    grn_id: str
    inspected_by: Optional[str] = None
    inspection_date: Optional[str] = None
    technical_spec_match: bool = True
    test_certificate_received: bool = False
    safety_compliance_ok: bool = True
    inspection_remarks: Optional[str] = None
    rejected_items: List[QIRejectedItem] = []
    attachments: List[str] = []
    overall_status: str = "accepted"  # accepted / partially_accepted / rejected / hold


@router.get("/inspections")
async def list_inspections(grn_id: Optional[str] = None, status: Optional[str] = None,
                           user: dict = Depends(require_permission("grn", "read"))):
    q: Dict[str, Any] = {}
    if grn_id:
        q["grn_id"] = grn_id
    if status:
        q["overall_status"] = status
    rows = await db.quality_inspections.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.post("/inspections")
async def create_inspection(payload: QIIn, request: Request,
                            user: dict = Depends(require_permission("grn", "write"))):
    grn = await db.goods_receipt_notes.find_one({"id": payload.grn_id}, {"_id": 0})
    if not grn:
        # fallback collection name used in earlier iterations
        grn = await db.grns.find_one({"id": payload.grn_id}, {"_id": 0})
    if not grn:
        raise HTTPException(404, "GRN not found")
    if payload.overall_status not in QI_STATUSES:
        raise HTTPException(400, f"overall_status must be one of {QI_STATUSES}")

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["qi_number"] = await next_sequence("QI")
    doc["grn_number"] = grn.get("grn_number") or grn.get("number")
    doc["vendor_id"] = grn.get("vendor_id")
    doc["vendor_name"] = grn.get("vendor_name")
    doc["po_id"] = grn.get("po_id")
    doc["project_id"] = grn.get("project_id")
    doc["inspection_date"] = doc.get("inspection_date") or _today_str()
    doc["inspected_by"] = doc.get("inspected_by") or user.get("name") or user.get("email")
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")

    # Auto-draft debit note if any item flagged
    debit_lines = [
        {"item_name": ri["item_name"], "qty": ri["rejected_qty"], "reason": ri["reason"]}
        for ri in doc["rejected_items"] if ri.get("debit_note_required")
    ]
    if debit_lines:
        debit_doc = {
            "id": new_id(),
            "qi_id": doc["id"],
            "vendor_id": doc["vendor_id"],
            "vendor_name": doc["vendor_name"],
            "grn_id": payload.grn_id,
            "lines": debit_lines,
            "status": "draft",
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
        }
        await db.debit_notes.insert_one(debit_doc)
        doc["debit_note_id"] = debit_doc["id"]

    await db.quality_inspections.insert_one(doc)

    # mark replacement-pending count on GRN
    pending_replacement = sum(1 for ri in doc["rejected_items"] if ri.get("replacement_required"))
    if pending_replacement:
        await db.goods_receipt_notes.update_one(
            {"id": payload.grn_id},
            {"$set": {"pending_replacement_count": pending_replacement,
                      "last_inspection_id": doc["id"]}},
        )

    await audit(user=user, action="create", resource="quality_inspections",
                record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.get("/inspections/pending-replacement")
async def list_pending_replacement(user: dict = Depends(require_permission("grn", "read"))):
    """All open rejected items awaiting vendor replacement."""
    rows = await db.quality_inspections.find(
        {"overall_status": {"$in": ["rejected", "partially_accepted"]},
         "rejected_items.replacement_required": True},
        {"_id": 0},
    ).sort("created_at", -1).to_list(1000)
    # flatten
    flat = []
    for qi in rows:
        for ri in qi.get("rejected_items", []):
            if ri.get("replacement_required"):
                flat.append({
                    "qi_id": qi["id"], "qi_number": qi.get("qi_number"),
                    "vendor_id": qi.get("vendor_id"), "vendor_name": qi.get("vendor_name"),
                    "grn_id": qi.get("grn_id"),
                    "item_name": ri["item_name"],
                    "rejected_qty": ri["rejected_qty"],
                    "reason": ri.get("reason"),
                    "inspection_date": qi.get("inspection_date"),
                })
    return {"count": len(flat), "rows": flat}


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT EXPIRY ALERTS
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/document-expiry")
async def document_expiry(window_days: int = Query(DEFAULT_EXPIRY_WINDOW_DAYS),
                          include_expired: bool = True,
                          user: dict = Depends(require_permission("vendors", "read"))):
    """Scan vendor.documents[] + vendor.msme + bank_accounts for expiring docs."""
    today = datetime.now(timezone.utc).date()
    rows = await db.vendors.find(
        {"status": {"$nin": ["inactive", "blocked"]}},
        {"_id": 0, "id": 1, "name": 1, "vendor_code": 1, "vendor_type": 1,
         "documents": 1, "msme": 1, "status": 1},
    ).to_list(2000)

    alerts: List[Dict[str, Any]] = []
    for v in rows:
        for d in v.get("documents") or []:
            exp = d.get("expiry")
            if not exp:
                continue
            exp_date = _parse_date(exp)
            if not exp_date:
                continue
            days = (exp_date.date() - today).days
            if days <= window_days and (include_expired or days >= 0):
                alerts.append({
                    "vendor_id": v["id"], "vendor_code": v.get("vendor_code"),
                    "vendor_name": v.get("name"), "vendor_type": v.get("vendor_type"),
                    "doc_type": d.get("type"), "doc_name": d.get("name"),
                    "expiry": exp, "days_to_expiry": days,
                    "severity": "expired" if days < 0 else ("critical" if days <= 7 else "warning"),
                })
        msme = v.get("msme") or {}
        if msme.get("certificate_expiry"):
            exp_date = _parse_date(msme["certificate_expiry"])
            if exp_date:
                days = (exp_date.date() - today).days
                if days <= window_days and (include_expired or days >= 0):
                    alerts.append({
                        "vendor_id": v["id"], "vendor_code": v.get("vendor_code"),
                        "vendor_name": v.get("name"), "vendor_type": v.get("vendor_type"),
                        "doc_type": "MSME", "doc_name": "MSME Certificate",
                        "expiry": msme["certificate_expiry"], "days_to_expiry": days,
                        "severity": "expired" if days < 0 else ("critical" if days <= 7 else "warning"),
                    })
    alerts.sort(key=lambda a: a["days_to_expiry"])
    return {"window_days": window_days, "count": len(alerts), "alerts": alerts}


# ─────────────────────────────────────────────────────────────────────────────
# PROCUREMENT NOTIFICATIONS — unified inbox
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/notifications")
async def procurement_notifications(unread_only: bool = False,
                                    user: dict = Depends(require_permission("vendors", "read"))):
    """Aggregated inbox computed live from procurement collections."""
    today_str = _today_str()
    notif: List[Dict[str, Any]] = []

    # 1. PR pending approval
    cnt = await db.purchase_requisitions.count_documents({"status": "pending_approval"})
    if cnt:
        notif.append({"kind": "pr_pending_approval", "title": f"{cnt} PR(s) pending approval",
                      "severity": "warning", "count": cnt, "link": "/app/purchase-requisitions"})
    # 2. RFQ awaiting quotations
    cnt = await db.rfqs.count_documents({"status": {"$in": ["sent", "partially_received"]}})
    if cnt:
        notif.append({"kind": "rfq_pending", "title": f"{cnt} RFQ(s) awaiting quotations",
                      "severity": "info", "count": cnt, "link": "/app/rfqs"})
    # 3. PO partially received
    cnt = await db.purchase_orders.count_documents({"status": "partially_received"})
    if cnt:
        notif.append({"kind": "po_partially_received", "title": f"{cnt} PO(s) partially received",
                      "severity": "info", "count": cnt, "link": "/app/purchase-orders"})
    # 4. GRN pending invoice
    cnt = await db.goods_receipt_notes.count_documents({"invoice_received": {"$ne": True}})
    if cnt:
        notif.append({"kind": "grn_pending_invoice", "title": f"{cnt} GRN(s) pending vendor invoice",
                      "severity": "info", "count": cnt, "link": "/app/grn"})
    # 5. Vendor bills pending verification
    cnt = await db.vendor_bills.count_documents({"status": "pending_verification"})
    if cnt:
        notif.append({"kind": "vendor_bills_pending", "title": f"{cnt} vendor bill(s) pending verification",
                      "severity": "warning", "count": cnt, "link": "/app/vendor-bills"})
    # 6. Vendor bills overdue payment
    cnt = await db.vendor_bills.count_documents({
        "status": "approved", "payment_status": {"$ne": "paid"},
        "due_date": {"$lt": today_str},
    })
    if cnt:
        notif.append({"kind": "payment_overdue", "title": f"{cnt} vendor payment(s) overdue",
                      "severity": "critical", "count": cnt, "link": "/app/vendor-bills"})
    # 7. Document expiry
    exp = await document_expiry(window_days=DEFAULT_EXPIRY_WINDOW_DAYS, include_expired=True, user=user)
    if exp["count"]:
        notif.append({"kind": "doc_expiry", "title": f"{exp['count']} vendor document(s) expiring/expired",
                      "severity": "warning", "count": exp["count"],
                      "link": "/app/procurement/compliance"})
    # 8. Rate contracts expiring
    rc = await list_expiring_contracts(window_days=DEFAULT_EXPIRY_WINDOW_DAYS, user=user)
    if rc["count"]:
        notif.append({"kind": "rc_expiring", "title": f"{rc['count']} rate contract(s) expiring soon",
                      "severity": "warning", "count": rc["count"],
                      "link": "/app/procurement/rate-contracts"})
    # 9. Pending replacements
    pr = await list_pending_replacement(user=user)
    if pr["count"]:
        notif.append({"kind": "pending_replacement", "title": f"{pr['count']} item(s) awaiting vendor replacement",
                      "severity": "warning", "count": pr["count"],
                      "link": "/app/grn"})
    # 10. Service orders partially received
    cnt = await db.service_orders.count_documents({"status": "partially_received"})
    if cnt:
        notif.append({"kind": "so_partially_received", "title": f"{cnt} service order(s) partially received",
                      "severity": "info", "count": cnt,
                      "link": "/app/procurement/service-orders"})
    return {"total": sum(n["count"] for n in notif), "items": notif}


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR PERFORMANCE — 5-tier label overlay
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/performance/tiers")
async def vendor_performance_tiers(user: dict = Depends(require_permission("vendors", "read"))):
    """Map every vendor to a 5-tier label using the existing rolling-avg score."""
    vendors = await db.vendors.find({}, {"_id": 0, "id": 1, "name": 1, "vendor_code": 1,
                                          "vendor_type": 1, "status": 1, "rating": 1}).to_list(2000)
    out = []
    for v in vendors:
        # rating is 0..5 OR percentage; normalise to 0..100
        raw = v.get("rating")
        if raw is None:
            score = 0.0
        elif raw <= 5:
            score = float(raw) * 20.0
        else:
            score = float(raw)
        tier = _grade_to_tier(score, v.get("status"))
        out.append({
            "vendor_id": v["id"], "vendor_code": v.get("vendor_code"),
            "vendor_name": v.get("name"), "vendor_type": v.get("vendor_type"),
            "status": v.get("status"), "score": round(score, 1), "tier": tier,
        })
    # tier counts
    from collections import Counter
    counts = dict(Counter(o["tier"] for o in out))
    return {"counts": counts, "rows": out}


# ─────────────────────────────────────────────────────────────────────────────
# STOCK-AVAILABILITY CHECK (PR helper)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/stock-availability/{pr_id}")
async def stock_availability_for_pr(pr_id: str,
                                    user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    """Check on-hand stock for every PR line item — surfaces transfer suggestions."""
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(404, "PR not found")

    out_rows = []
    for line in pr.get("items") or pr.get("lines") or []:
        name = line.get("name") or line.get("item_name")
        qty = float(line.get("quantity") or 0.0)
        item_id = line.get("item_id")
        q: Dict[str, Any] = {}
        if item_id:
            q["item_id"] = item_id
        else:
            q["item_name"] = name
        stock_doc = await db.inventory.find_one(q, {"_id": 0}) or \
                    await db.store_inventory.find_one(q, {"_id": 0}) or {}
        on_hand = float(stock_doc.get("on_hand") or stock_doc.get("quantity") or 0.0)
        out_rows.append({
            "item_name": name, "required_qty": qty, "unit": line.get("unit") or "Nos",
            "on_hand": on_hand,
            "shortfall": max(qty - on_hand, 0.0),
            "transfer_suggested": on_hand >= qty,
        })
    fully_covered = all(r["transfer_suggested"] for r in out_rows) and bool(out_rows)
    return {"pr_id": pr_id, "pr_number": pr.get("pr_number"),
            "fully_covered_by_stock": fully_covered,
            "lines": out_rows}
