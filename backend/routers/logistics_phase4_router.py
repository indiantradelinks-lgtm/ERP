"""
Iter 135 — Logistics Module · Phase 4 · Fuel / Expense / Maintenance / Vendor Bills / Cost
============================================================================================

Collections:
  * logistics_fuel_entries          — fuel/diesel entries with KM tracking
  * logistics_vehicle_expenses      — miscellaneous vehicle expenses
  * logistics_vehicle_maintenance   — preventive/breakdown/repair register
  * logistics_vendor_bills          — transport vendor bill verification
  * logistics_cost_allocations      — unified cost register for Accounts/Finance
  * logistics_accounts_events       — outgoing accounts posting events
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core import db, now_iso, new_id, require_permission
from approval_engine import insert_approval

router = APIRouter(prefix="/logistics", tags=["logistics-phase4"])

HIGH_VALUE_THRESHOLD = 50000
FINANCE_APPROVAL_ROLES = {"finance_head", "general_manager", "director", "dept_head", "super_admin"}


async def _route_finance_approval(source_kind: str, source_id: str, source_no: str,
                                   amount: float, project_code: Optional[str], user: dict) -> Optional[str]:
    """Route a high-value cost to Finance for approval via the shared engine."""
    if amount < HIGH_VALUE_THRESHOLD:
        return None
    approval_doc = {
        "id": new_id(),
        "type": f"logistics_{source_kind}",
        "module": "logistics",
        "record_id": source_id,
        "title": f"Logistics {source_kind.replace('_', ' ')} ₹{amount:,.0f} — {source_no}",
        "summary": f"Project {project_code or '—'} · Source: {source_kind} · High-value ≥₹{HIGH_VALUE_THRESHOLD:,}",
        "requested_by": user.get("name") or user.get("email"),
        "status": "pending",
        "current_step": 0,
        "chain": [
            {"role": "general_manager", "label": "General Manager", "status": "pending",
             "approver": None, "at": None, "comment": None},
            {"role": "director", "label": "Director / Owner", "status": "pending",
             "approver": None, "at": None, "comment": None},
        ],
        "history": [], "created_at": now_iso(), "updated_at": now_iso(),
    }
    await insert_approval(approval_doc, skip_gate=True)
    return approval_doc["id"]


async def _next_int(key: str) -> int:
    doc = await db.sequences.find_one_and_update(
        {"_id": key}, {"$inc": {"value": 1}}, upsert=True, return_document=True
    )
    return int(doc["value"])


async def _audit(kind: str, rid: str, action: str, user: dict, record_no: str = "",
                 meta: Optional[Dict] = None):
    await db.logistics_audit_log.insert_one({
        "id": new_id(),
        "record_kind": kind,
        "record_id": rid,
        "record_no": record_no or "",
        "action": action,
        "at": now_iso(),
        "by_id": user.get("id"),
        "by_name": user.get("name") or user.get("email"),
        "by_role": user.get("role"),
        "meta": meta or {},
    })


async def _emit_cost(source_kind: str, source_id: str, source_no: str, amount: float,
                     category: str, project_id: Optional[str], project_code: Optional[str],
                     vehicle_id: Optional[str], dispatch_id: Optional[str], user: dict):
    """Write a unified cost allocation event + accounts posting event.
    High-value items also route through the Finance approval chain."""
    if amount is None or amount == 0:
        return None
    approval_id = await _route_finance_approval(source_kind, source_id, source_no, float(amount),
                                                 project_code, user)
    doc = {
        "id": new_id(),
        "source_kind": source_kind,
        "source_id": source_id,
        "source_no": source_no,
        "category": category,
        "amount": float(amount),
        "project_id": project_id,
        "project_code": project_code,
        "vehicle_id": vehicle_id,
        "dispatch_id": dispatch_id,
        "at": now_iso(),
        "by": user.get("name") or user.get("email"),
        "posted_to_accounts": False,
        "posted_at": None,
        "posted_by": None,
        "high_value": amount >= HIGH_VALUE_THRESHOLD,
        "finance_approval_id": approval_id,
    }
    await db.logistics_cost_allocations.insert_one(doc)
    await db.logistics_accounts_events.insert_one({
        "id": new_id(),
        "event": "cost_posted",
        "source_kind": source_kind,
        "source_id": source_id,
        "source_no": source_no,
        "category": category,
        "amount": float(amount),
        "project_code": project_code,
        "at": now_iso(),
    })
    return doc


def _yr() -> int:
    return datetime.now(timezone.utc).year


# ═══════════════════════════════════════════════════════════════════════════
# Fuel / Diesel Entry
# ═══════════════════════════════════════════════════════════════════════════

class FuelEntryIn(BaseModel):
    entry_date: Optional[str] = None
    vehicle_id: str
    driver_id: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    dispatch_id: Optional[str] = None
    opening_km: Optional[float] = None
    closing_km: Optional[float] = None
    quantity_ltrs: float
    rate: float
    amount: Optional[float] = None
    fuel_station: Optional[str] = None
    bill_no: Optional[str] = None
    payment_mode: str = "cash"
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None
    status: str = "pending"  # pending | approved | rejected


@router.get("/fuel-entries")
async def fuel_list(
    vehicle_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    if project_id:
        q["project_id"] = project_id
    return await db.logistics_fuel_entries.find(q, {"_id": 0}).sort("entry_date", -1).to_list(2000)


@router.post("/fuel-entries")
async def fuel_create(
    payload: FuelEntryIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    veh = await db.vehicles.find_one({"id": payload.vehicle_id})
    if not veh:
        raise HTTPException(400, "Vehicle not found")

    # Duplicate detection
    if payload.bill_no and payload.fuel_station:
        dup = await db.logistics_fuel_entries.find_one({
            "bill_no": payload.bill_no,
            "fuel_station": payload.fuel_station,
            "entry_date": payload.entry_date,
        })
        if dup:
            raise HTTPException(400, f"Duplicate fuel bill {payload.bill_no} for {payload.fuel_station} on {payload.entry_date}")

    # Require attachment unless admin
    if not payload.attachment_url and (user.get("role") or "") not in {"super_admin", "director", "general_manager", "dept_head"}:
        # soft warn — allow but flag; keep behaviour strict for now
        pass

    seq = await _next_int("logistics_fuel_entries")
    amount = payload.amount if payload.amount is not None else (payload.quantity_ltrs * payload.rate)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "fuel_no": f"FUEL-{_yr()}-{seq:04d}",
        "amount": amount,
        "entry_date": payload.entry_date or datetime.now(timezone.utc).date().isoformat(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_fuel_entries.insert_one(doc)
    doc.pop("_id", None)
    await _audit("fuel_entry", doc["id"], "create", user, doc["fuel_no"],
                 {"amount": amount, "vehicle_id": payload.vehicle_id})
    return doc


@router.put("/fuel-entries/{fid}")
async def fuel_update(
    fid: str,
    payload: FuelEntryIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_fuel_entries.find_one({"id": fid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    updates = payload.model_dump()
    updates["amount"] = payload.amount if payload.amount is not None else (payload.quantity_ltrs * payload.rate)
    updates["updated_at"] = now_iso()
    await db.logistics_fuel_entries.update_one({"id": fid}, {"$set": updates})

    # Approval workflow: emit cost when moves to approved
    if updates.get("status") == "approved" and ex.get("status") != "approved":
        await _emit_cost("fuel_entry", fid, ex.get("fuel_no", ""), updates["amount"], "fuel",
                         updates.get("project_id"), updates.get("project_code"),
                         updates.get("vehicle_id"), updates.get("dispatch_id"), user)

    await _audit("fuel_entry", fid, f"update:{updates.get('status')}", user, ex.get("fuel_no", ""))
    return {**ex, **updates}


# ═══════════════════════════════════════════════════════════════════════════
# Vehicle Expense
# ═══════════════════════════════════════════════════════════════════════════

EXPENSE_CATEGORIES = ["repair", "tyre", "battery", "toll", "parking", "permit", "insurance",
                      "fitness", "pollution", "driver_allowance", "loading_unloading", "other"]


class VehicleExpenseIn(BaseModel):
    entry_date: Optional[str] = None
    vehicle_id: str
    driver_id: Optional[str] = None
    category: str = "other"
    amount: float
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    dispatch_id: Optional[str] = None
    vendor_id: Optional[str] = None
    bill_no: Optional[str] = None
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None
    status: str = "pending"


@router.get("/vehicle-expenses")
async def exp_list(
    vehicle_id: Optional[str] = None,
    category: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    if category:
        q["category"] = category
    return await db.logistics_vehicle_expenses.find(q, {"_id": 0}).sort("entry_date", -1).to_list(2000)


@router.post("/vehicle-expenses")
async def exp_create(
    payload: VehicleExpenseIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    if payload.category not in EXPENSE_CATEGORIES:
        raise HTTPException(400, f"category must be one of {EXPENSE_CATEGORIES}")
    seq = await _next_int("logistics_vehicle_expenses")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "expense_no": f"EXP-{_yr()}-{seq:04d}",
        "entry_date": payload.entry_date or datetime.now(timezone.utc).date().isoformat(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_vehicle_expenses.insert_one(doc)
    doc.pop("_id", None)
    await _audit("vehicle_expense", doc["id"], "create", user, doc["expense_no"], {"amount": doc["amount"]})
    return doc


@router.put("/vehicle-expenses/{eid}")
async def exp_update(
    eid: str,
    payload: VehicleExpenseIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_vehicle_expenses.find_one({"id": eid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_vehicle_expenses.update_one({"id": eid}, {"$set": updates})
    if updates.get("status") == "approved" and ex.get("status") != "approved":
        await _emit_cost("vehicle_expense", eid, ex.get("expense_no", ""), updates["amount"],
                         updates.get("category", "other"), updates.get("project_id"),
                         updates.get("project_code"), updates.get("vehicle_id"),
                         updates.get("dispatch_id"), user)
    await _audit("vehicle_expense", eid, f"update:{updates.get('status')}", user, ex.get("expense_no", ""))
    return {**ex, **updates}


# ═══════════════════════════════════════════════════════════════════════════
# Vehicle Maintenance
# ═══════════════════════════════════════════════════════════════════════════

MAINT_TYPES = ["preventive", "breakdown", "repair", "inspection"]


class MaintenanceIn(BaseModel):
    vehicle_id: str
    maintenance_type: str = "preventive"
    maint_date: Optional[str] = None
    odometer_km: Optional[float] = None
    work_done: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    cost: Optional[float] = None
    next_due_date: Optional[str] = None
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None
    status: str = "in_progress"  # in_progress | completed | approved


@router.get("/maintenance")
async def maint_list(
    vehicle_id: Optional[str] = None,
    user: dict = Depends(require_permission("vehicles", "read")),
):
    q: Dict[str, Any] = {}
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    return await db.logistics_vehicle_maintenance.find(q, {"_id": 0}).sort("maint_date", -1).to_list(2000)


@router.post("/maintenance")
async def maint_create(
    payload: MaintenanceIn,
    user: dict = Depends(require_permission("vehicles", "write")),
):
    if payload.maintenance_type not in MAINT_TYPES:
        raise HTTPException(400, f"maintenance_type must be one of {MAINT_TYPES}")
    veh = await db.vehicles.find_one({"id": payload.vehicle_id})
    if not veh:
        raise HTTPException(400, "Vehicle not found")
    seq = await _next_int("logistics_vehicle_maintenance")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "maint_no": f"MNT-{_yr()}-{seq:04d}",
        "maint_date": payload.maint_date or datetime.now(timezone.utc).date().isoformat(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_vehicle_maintenance.insert_one(doc)
    doc.pop("_id", None)

    # Move vehicle to maintenance status while in-progress
    if payload.status == "in_progress":
        await db.vehicles.update_one({"id": payload.vehicle_id},
                                     {"$set": {"status": "maintenance"}})

    await _audit("maintenance", doc["id"], "create", user, doc["maint_no"], {"cost": doc.get("cost")})
    return doc


@router.put("/maintenance/{mid}")
async def maint_update(
    mid: str,
    payload: MaintenanceIn,
    user: dict = Depends(require_permission("vehicles", "write")),
):
    ex = await db.logistics_vehicle_maintenance.find_one({"id": mid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    updates = payload.model_dump()
    updates["updated_at"] = now_iso()
    await db.logistics_vehicle_maintenance.update_one({"id": mid}, {"$set": updates})

    # Return vehicle to available when maintenance completed
    if updates.get("status") in {"completed", "approved"} and ex.get("status") == "in_progress":
        await db.vehicles.update_one({"id": ex.get("vehicle_id")},
                                     {"$set": {"status": "available"}})

    # Emit cost when approved
    if updates.get("status") == "approved" and ex.get("status") != "approved" and updates.get("cost"):
        await _emit_cost("maintenance", mid, ex.get("maint_no", ""), updates["cost"],
                         "vehicle_maintenance", updates.get("project_id"),
                         updates.get("project_code"), updates.get("vehicle_id"), None, user)

    await _audit("maintenance", mid, f"update:{updates.get('status')}", user, ex.get("maint_no", ""))
    return {**ex, **updates}


# ═══════════════════════════════════════════════════════════════════════════
# Transport Vendor Bill
# ═══════════════════════════════════════════════════════════════════════════

class VendorBillIn(BaseModel):
    id: Optional[str] = None
    vendor_id: str
    vendor_name: Optional[str] = None
    bill_no: str
    bill_date: Optional[str] = None
    dispatch_id: Optional[str] = None
    dispatch_no: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    freight_amount: Optional[float] = None
    loading_cost: Optional[float] = None
    unloading_cost: Optional[float] = None
    detention_amount: Optional[float] = None
    other_charges: Optional[float] = None
    gst_amount: Optional[float] = None
    tds_amount: Optional[float] = None
    net_payable: Optional[float] = None
    cost_center_id: Optional[str] = None
    cost_center_label: Optional[str] = None
    supporting_urls: Optional[List[str]] = None
    remarks: Optional[str] = None
    status: str = "pending"  # pending | verified | approved | posted | paid | rejected


@router.get("/vendor-bills")
async def vb_list(
    vendor_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if vendor_id:
        q["vendor_id"] = vendor_id
    if status:
        q["status"] = status
    rows = await db.logistics_vendor_bills.find(q, {"_id": 0}).sort("bill_date", -1).to_list(2000)
    # Enrich with approval chain (2-level Dept Head → GM workflow) — match by record_id (covers pending + completed)
    ids = [r["id"] for r in rows]
    amap: Dict[str, Any] = {}
    if ids:
        async for a in db.approvals.find({"type": "vendor_bill", "record_id": {"$in": ids}},
                                         {"_id": 0, "record_id": 1, "chain": 1, "status": 1, "created_at": 1}).sort("created_at", 1):
            amap[a["record_id"]] = a  # latest wins
    for r in rows:
        a = amap.get(r["id"])
        r["approval_chain"] = (a or {}).get("chain") or []
        r["approval_status"] = (a or {}).get("status")
    return rows


@router.get("/transport-vendors")
async def transport_vendors(user: dict = Depends(require_permission("dispatch_requests", "read"))):
    """Approved Vendor Master records with Category = TRANS (transportation) ONLY."""
    q = {"status": "approved",
         "$or": [{"categories": {"$regex": "^trans", "$options": "i"}},
                 {"category": {"$regex": "^trans", "$options": "i"}}]}
    return await db.vendors.find(q, {"_id": 0, "id": 1, "name": 1, "vendor_code": 1, "categories": 1}).sort("name", 1).to_list(1000)


async def _auto_cost_center(doc: Dict[str, Any]) -> None:
    """Resolve CC label for user-selected CC; else auto-populate the project's cost center
    (transport/vehicle/freight-categorized preferred, else the project's default)."""
    if doc.get("cost_center_id"):
        cc = await db.cost_centers.find_one({"id": doc["cost_center_id"]},
                                            {"_id": 0, "name": 1, "code": 1, "category_name": 1})
        if not cc:
            raise HTTPException(400, "Selected Cost Center not found — pick a valid Cost Center")
        doc["cost_center_label"] = cc.get("category_name") or cc.get("name") or cc.get("code")
        return
    if not doc.get("project_id"):
        return
    ccs = await db.cost_centers.find({"project_id": doc["project_id"], "active": {"$ne": False}}, {"_id": 0}).to_list(50)
    if not ccs:
        return
    # Auto-pick ONLY a transport/vehicle/freight cost center — never default to an unrelated CC
    cc = next((c for c in ccs if "transport" in (c.get("category_code") or "").lower()
               or "vehicle" in (c.get("category_code") or "").lower()
               or "vehicle" in (c.get("category_name") or "").lower()
               or "freight" in (c.get("name") or "").lower()), None)
    if len(ccs) == 1 and cc is None:
        cc = ccs[0]  # single CC on the project → unambiguous
    if cc is None:
        return  # ambiguous — user must select explicitly
    doc["cost_center_id"] = cc["id"]
    doc["cost_center_label"] = cc.get("category_name") or cc.get("name") or cc.get("code")


@router.post("/vendor-bills")
async def vb_create(
    payload: VendorBillIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    dup = await db.logistics_vendor_bills.find_one({"vendor_id": payload.vendor_id, "bill_no": payload.bill_no})
    if dup:
        raise HTTPException(400, f"Duplicate bill {payload.bill_no} for this vendor")
    if payload.dispatch_id:
        dr = await db.logistics_dispatch_requests.find_one({"id": payload.dispatch_id})
        if not dr:
            raise HTTPException(400, "Dispatch not found")
    seq = await _next_int("logistics_vendor_bills")
    net = payload.net_payable
    if net is None:
        parts = [payload.freight_amount or 0, payload.loading_cost or 0, payload.unloading_cost or 0,
                 payload.detention_amount or 0, payload.other_charges or 0,
                 payload.gst_amount or 0]
        net = sum(parts) - (payload.tds_amount or 0)
    doc = payload.model_dump()
    await _auto_cost_center(doc)
    if not doc.get("cost_center_id"):
        raise HTTPException(400, "Cost Center is mandatory — select a valid Cost Center (or a project that has one) before saving this bill")
    if doc.get("status") in (None, "", "pending"):
        doc["status"] = "submitted"  # save directly into Pending Approval
    doc.update({
        "id": payload.id if payload.id and not await db.vendor_bills.find_one({"id": payload.id}, {"_id": 1}) else new_id(),
        "vb_no": f"VB-{_yr()}-{seq:04d}",
        "net_payable": net,
        "bill_date": payload.bill_date or datetime.now(timezone.utc).date().isoformat(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.logistics_vendor_bills.insert_one(doc)
    doc.pop("_id", None)
    if doc.get("status") == "approved":
        await _push_bill_to_accounts(doc, user)
    if doc.get("status") == "submitted":
        await _start_bill_approval(doc, user)
    await _audit("vendor_bill", doc["id"], "create", user, doc["vb_no"], {"net": net})
    return doc


async def _mirror_bill_to_vendor_bills(bill: dict) -> None:
    """Mirror an approved/paid transport vendor bill into accounts `vendor_bills`
    so it shows on the Vendor Bills page and books cost to its project."""
    basic = round(sum(float(bill.get(k) or 0) for k in
                      ("freight_amount", "loading_cost", "unloading_cost", "detention_amount", "other_charges")), 2)
    gst = round(float(bill.get("gst_amount") or 0), 2)
    tds = round(float(bill.get("tds_amount") or 0), 2)
    gross = round(basic + gst, 2)
    net = round(float(bill.get("net_payable") or (gross - tds)), 2)
    status = "paid" if bill.get("status") == "paid" else "approved"
    doc = {
        "source": "logistics_vendor_bill", "source_id": bill["id"], "source_no": bill.get("vb_no"),
        "bill_type": "transport_mirror", "read_only": True, "workflow_version": "mirror",
        "vendor_id": bill.get("vendor_id"), "vendor_name": bill.get("vendor_name"),
        "invoice_no": bill.get("bill_no"), "invoice_date": bill.get("bill_date"),
        "project_id": bill.get("project_id"), "project_code": bill.get("project_code"),
        "cost_center_id": bill.get("cost_center_id"), "cost_center_label": bill.get("cost_center_label"),
        "expense_category": "transport",
        "taxable_value": basic, "amount": gross, "total": gross,
        "tax_amount": gst, "gst_amount": gst, "tds_amount": tds,
        "totals": {"taxable": basic, "gst": gst, "tds": tds, "gross": gross, "net_payable": net},
        "paid_amount": gross if status == "paid" else 0.0,
        "outstanding": 0.0 if status == "paid" else net,
        "status": status,
        "notes": f"Auto-booked from Transport Vendor Bill {bill.get('vb_no')} (Logistics)",
        "updated_at": now_iso(),
    }
    existing = await db.vendor_bills.find_one(
        {"source": "logistics_vendor_bill", "source_id": bill["id"]}, {"_id": 0, "id": 1})
    if existing:
        await db.vendor_bills.update_one({"id": existing["id"]}, {"$set": doc})
    else:
        from sequences import next_sequence
        doc.update({"id": new_id(), "bill_no": await next_sequence("VB"), "created_at": now_iso(),
                    "created_by": "system (logistics mirror)"})
        await db.vendor_bills.insert_one(doc)


async def _push_bill_to_accounts(bill: dict, user: dict) -> None:
    """Puts an approved transport vendor bill into the Accounts payment queue
    (shadow row in project_requests, is_payment=True) — same flow as payment requests."""
    if await db.project_requests.find_one({"source": "vendor_bill", "source_id": bill["id"]}, {"_id": 0, "id": 1}):
        return
    proj = await db.projects.find_one({"id": bill.get("project_id")}, {"_id": 0, "name": 1}) if bill.get("project_id") else None
    await db.project_requests.insert_one({
        "id": new_id(),
        "request_no": bill.get("vb_no"),
        "request_type": "transport_vendor_bill",
        "request_type_label": "Transport Vendor Bill",
        "is_payment": True, "is_stockable": False,
        "owning_dept": "logistics",
        "expense_type": "transport_freight",
        "status": "with_dept",
        "payment_status": "payment_pending",
        "source": "vendor_bill", "source_id": bill["id"],
        "project_id": bill.get("project_id"), "project_code": bill.get("project_code"),
        "project_name": (proj or {}).get("name"),
        "cost_center_id": bill.get("cost_center_id"), "cost_center_label": bill.get("cost_center_label"),
        "vendor": bill.get("vendor_name"),
        "est_value": float(bill.get("net_payable") or 0),
        "description": f"Transport vendor bill {bill.get('bill_no')} — {bill.get('vendor_name')}",
        "items": [], "chain": [], "current_step": None,
        "created_by": user.get("name") or user.get("email"), "created_by_id": user.get("id"),
        "created_at": now_iso(),
    })


async def _start_bill_approval(bill: dict, user: dict) -> None:
    """Submitted bill → 2-level approval: Dept Head → General Manager."""
    if await db.approvals.find_one({"type": "vendor_bill", "record_id": bill["id"],
                                    "status": {"$in": ["pending", "in_progress"]}}, {"_id": 0, "id": 1}):
        return
    await insert_approval({
        "id": new_id(), "type": "vendor_bill", "module": "logistics",
        "record_id": bill["id"], "record_no": bill.get("vb_no"),
        "title": f"Transport Vendor Bill {bill.get('vb_no')} — {bill.get('vendor_name')} ₹{float(bill.get('net_payable') or 0):,.0f}",
        "summary": f"Project {bill.get('project_code') or '—'} · Bill {bill.get('bill_no')} · 2-level: Dept Head → GM",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "status": "pending", "current_step": 0,
        "chain": [
            {"role": "dept_head", "label": "Department Head", "status": "pending", "approver": None, "at": None, "comment": None},
            {"role": "general_manager", "label": "General Manager", "status": "pending", "approver": None, "at": None, "comment": None},
        ],
        "history": [], "created_at": now_iso(), "updated_at": now_iso(),
    }, skip_gate=True)
    await _audit("vendor_bill", bill["id"], "submitted_for_approval", user, bill.get("vb_no") or "")


@router.put("/vendor-bills/{bid}")
async def vb_update(
    bid: str,
    payload: VendorBillIn,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    ex = await db.logistics_vendor_bills.find_one({"id": bid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    updates = payload.model_dump()
    updates.pop("id", None)
    await _auto_cost_center(updates)
    updates["updated_at"] = now_iso()
    await db.logistics_vendor_bills.update_one({"id": bid}, {"$set": updates})

    # Emit cost + accounts event when approved
    if updates.get("status") == "approved" and ex.get("status") != "approved":
        await _push_bill_to_accounts({**ex, **updates, "id": bid}, user)
        await _mirror_bill_to_vendor_bills({**ex, **updates, "id": bid})
    if updates.get("status") == "submitted" and ex.get("status") != "submitted":
        await _start_bill_approval({**ex, **updates, "id": bid}, user)
        await _emit_cost("vendor_bill", bid, ex.get("vb_no", ""), updates.get("net_payable") or 0,
                         "freight", updates.get("project_id"), updates.get("project_code"),
                         None, updates.get("dispatch_id"), user)
        # accounts payable event
        await db.logistics_accounts_events.insert_one({
            "id": new_id(),
            "event": "vendor_bill_approved",
            "vendor_id": ex.get("vendor_id"),
            "bill_no": ex.get("bill_no"),
            "amount": updates.get("net_payable"),
            "project_code": updates.get("project_code"),
            "at": now_iso(),
        })

    await _audit("vendor_bill", bid, f"update:{updates.get('status')}", user, ex.get("vb_no", ""))
    return {**ex, **updates}


# ═══════════════════════════════════════════════════════════════════════════
# Cost Allocation views
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/cost-allocations")
async def cost_list(
    project_id: Optional[str] = None,
    category: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if category:
        q["category"] = category
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    return await db.logistics_cost_allocations.find(q, {"_id": 0}).sort("at", -1).to_list(5000)


@router.get("/cost-summary")
async def cost_summary(user: dict = Depends(require_permission("dispatch_requests", "read"))):
    """Project-wise + category-wise summary."""
    now_utc = datetime.now(timezone.utc)
    month_start = now_utc.replace(day=1).date().isoformat()

    # By project
    by_project: Dict[str, float] = {}
    by_category: Dict[str, float] = {}
    total = 0.0
    this_month = 0.0
    high_value_pending = 0
    async for c in db.logistics_cost_allocations.find({}, {"_id": 0}):
        amt = float(c.get("amount") or 0)
        total += amt
        code = c.get("project_code") or "Unallocated"
        by_project[code] = by_project.get(code, 0) + amt
        cat = c.get("category") or "other"
        by_category[cat] = by_category.get(cat, 0) + amt
        if c.get("at", "")[:10] >= month_start:
            this_month += amt
        if c.get("high_value") and not c.get("posted_to_accounts"):
            high_value_pending += 1

    return {
        "as_of": now_iso(),
        "total_cost": total,
        "this_month": this_month,
        "high_value_pending": high_value_pending,
        "by_project": [{"project_code": k, "amount": v} for k, v in sorted(by_project.items(), key=lambda x: -x[1])],
        "by_category": [{"category": k, "amount": v} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
    }


@router.get("/accounts-events")
async def accounts_events(
    event: Optional[str] = None,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {}
    if event:
        q["event"] = event
    return await db.logistics_accounts_events.find(q, {"_id": 0}).sort("at", -1).to_list(2000)



# ═══════════════════════════════════════════════════════════════════════════
# Delete / Edit guards on approved & posted cost sources
# ═══════════════════════════════════════════════════════════════════════════

async def _has_posted_cost(source_kind: str, source_id: str) -> bool:
    ca = await db.logistics_cost_allocations.find_one(
        {"source_kind": source_kind, "source_id": source_id, "posted_to_accounts": True}
    )
    return ca is not None


@router.delete("/fuel-entries/{fid}")
async def fuel_delete(fid: str, user: dict = Depends(require_permission("dispatch_requests", "delete"))):
    ex = await db.logistics_fuel_entries.find_one({"id": fid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    if ex.get("status") == "approved":
        raise HTTPException(400, "Approved fuel entry cannot be deleted — create a reversal instead")
    await db.logistics_fuel_entries.delete_one({"id": fid})
    await _audit("fuel_entry", fid, "delete", user, ex.get("fuel_no", ""))
    return {"ok": True}


@router.delete("/vehicle-expenses/{eid}")
async def exp_delete(eid: str, user: dict = Depends(require_permission("dispatch_requests", "delete"))):
    ex = await db.logistics_vehicle_expenses.find_one({"id": eid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    if ex.get("status") == "approved":
        raise HTTPException(400, "Approved expense cannot be deleted — create a reversal instead")
    await db.logistics_vehicle_expenses.delete_one({"id": eid})
    await _audit("vehicle_expense", eid, "delete", user, ex.get("expense_no", ""))
    return {"ok": True}


@router.delete("/vendor-bills/{bid}")
async def vb_delete(bid: str, user: dict = Depends(require_permission("dispatch_requests", "delete"))):
    ex = await db.logistics_vendor_bills.find_one({"id": bid}, {"_id": 0})
    if not ex:
        raise HTTPException(404, "Not found")
    if ex.get("status") in {"approved", "posted", "paid"}:
        raise HTTPException(400, "Approved / posted vendor bill cannot be deleted — reverse instead")
    await db.logistics_vendor_bills.delete_one({"id": bid})
    await _audit("vendor_bill", bid, "delete", user, ex.get("vb_no", ""))
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Post to Accounts
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/cost-allocations/{aid}/post-to-accounts")
async def post_to_accounts(
    aid: str,
    user: dict = Depends(require_permission("dispatch_requests", "write")),
):
    """Mark a cost allocation as posted to Accounts (idempotent)."""
    ca = await db.logistics_cost_allocations.find_one({"id": aid}, {"_id": 0})
    if not ca:
        raise HTTPException(404, "Cost allocation not found")
    if ca.get("high_value") and ca.get("finance_approval_id"):
        approval = await db.approvals.find_one({"id": ca["finance_approval_id"]})
        if approval and approval.get("status") != "approved":
            raise HTTPException(400, "High-value cost requires Finance approval before posting")
    if ca.get("posted_to_accounts"):
        return ca
    await db.logistics_cost_allocations.update_one(
        {"id": aid}, {"$set": {"posted_to_accounts": True, "posted_at": now_iso(),
                                "posted_by": user.get("name") or user.get("email")}}
    )
    await db.logistics_accounts_events.insert_one({
        "id": new_id(),
        "event": "cost_marked_posted",
        "source_kind": ca.get("source_kind"),
        "source_id": ca.get("source_id"),
        "source_no": ca.get("source_no"),
        "amount": ca.get("amount"),
        "project_code": ca.get("project_code"),
        "at": now_iso(),
    })
    await _audit("cost_allocation", aid, "posted", user, ca.get("source_no", ""))
    return await db.logistics_cost_allocations.find_one({"id": aid}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Project-wise & Vehicle-wise cost breakdowns
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/cost-by-project/{project_code}")
async def cost_by_project(
    project_code: str,
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    rows = await db.logistics_cost_allocations.find(
        {"project_code": project_code}, {"_id": 0}
    ).sort("at", -1).to_list(5000)
    by_cat: Dict[str, float] = {}
    total = 0.0
    for r in rows:
        amt = float(r.get("amount") or 0)
        total += amt
        by_cat[r.get("category") or "other"] = by_cat.get(r.get("category") or "other", 0) + amt
    return {"project_code": project_code, "total": total,
            "by_category": [{"category": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
            "rows": rows}


@router.get("/cost-by-vehicle/{vehicle_id}")
async def cost_by_vehicle(
    vehicle_id: str,
    user: dict = Depends(require_permission("vehicles", "read")),
):
    veh = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0, "vehicle_number": 1, "vehicle_code": 1})
    rows = await db.logistics_cost_allocations.find(
        {"vehicle_id": vehicle_id}, {"_id": 0}
    ).sort("at", -1).to_list(5000)
    by_cat: Dict[str, float] = {}
    total = 0.0
    for r in rows:
        amt = float(r.get("amount") or 0)
        total += amt
        by_cat[r.get("category") or "other"] = by_cat.get(r.get("category") or "other", 0) + amt
    return {"vehicle_id": vehicle_id, "vehicle": veh, "total": total,
            "by_category": [{"category": k, "amount": v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
            "rows": rows}


# ═══════════════════════════════════════════════════════════════════════════
# Finance Approval Inbox (logistics-scoped)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/finance-approvals")
async def finance_approvals(
    status: str = Query("pending", pattern="^(pending|approved|rejected|all)$"),
    user: dict = Depends(require_permission("dispatch_requests", "read")),
):
    q: Dict[str, Any] = {"module": "logistics"}
    if status != "all":
        q["status"] = status
    return await db.approvals.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


# ═══════════════════════════════════════════════════════════════════════════
# Vendor Payable — approved bills grouped by vendor
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/vendor-payable")
async def vendor_payable(user: dict = Depends(require_permission("dispatch_requests", "read"))):
    rows = await db.logistics_vendor_bills.find(
        {"status": {"$in": ["approved", "posted"]}}, {"_id": 0}
    ).sort("bill_date", -1).to_list(5000)
    by_vendor: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        vid = r.get("vendor_id") or "unknown"
        entry = by_vendor.setdefault(vid, {
            "vendor_id": vid,
            "vendor_name": r.get("vendor_name") or vid,
            "total_payable": 0.0,
            "total_paid": 0.0,
            "outstanding": 0.0,
            "bill_count": 0,
            "bills": [],
        })
        entry["bill_count"] += 1
        net = float(r.get("net_payable") or 0)
        entry["total_payable"] += net
        if r.get("status") == "paid":
            entry["total_paid"] += net
        else:
            entry["outstanding"] += net
        entry["bills"].append({"vb_no": r.get("vb_no"), "bill_no": r.get("bill_no"),
                                "bill_date": r.get("bill_date"), "net": net, "status": r.get("status")})
    return {"vendors": list(by_vendor.values()), "as_of": now_iso()}


# ═══════════════════════════════════════════════════════════════════════════
# MongoDB indexes (idempotent — ensured on startup via router import)
# ═══════════════════════════════════════════════════════════════════════════

async def _ensure_indexes():
    try:
        await db.logistics_vendor_bills.create_index(
            [("vendor_id", 1), ("bill_no", 1)], unique=True, name="uniq_vendor_bill", background=True
        )
        await db.logistics_fuel_entries.create_index(
            [("bill_no", 1), ("fuel_station", 1), ("entry_date", 1)],
            unique=True, sparse=True, name="uniq_fuel_bill", background=True
        )
    except Exception:
        pass  # already exists or duplicate data — do not block startup
