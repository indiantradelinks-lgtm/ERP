"""Projects & Ops · Project Request Center.

One unified request workflow per project for 9 request types:
  material, ppe, accommodation, fuel, vehicle_manpower, vehicle_material,
  insurance, it_material, one_time_vehicle

Process:
  1. PM / Project Coordinator raises a request (type-specific fields + items).
  2. For stockable types (material/ppe/it_material) the system auto-checks Store
     stock per item; shortfall can be pushed to Procurement as a Purchase Request.
  3. Project Head approves (+ GM → Director when value > threshold).
  4. On approval the request routes to the owning department queue:
        material/ppe/it_material -> Stores (then Procurement if short)
        vehicle_* / one_time_vehicle -> Logistics
        accommodation/fuel/insurance -> Admin/Accounts (payment types)
  5. Department fulfils; payment-types create a Daily Expense booking (cost
     center hit + Accounts payment-with-proof flow).
  6. Branded Excel / PDF reports.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, get_current_user, now_iso, new_id
from scope import apply_project_scope, ensure_project_access
from datetime import datetime, timezone
from audit import audit
from routers.project_expenses_router import EXPENSE_TYPES as PEX_TYPES
from routers.project_expenses_router import get_expense_types as _pex_types
from sequences import next_sequence
from exports import to_excel, to_pdf

router = APIRouter(tags=["project-requests"])
logger = logging.getLogger("erp")

# type -> (label, owning department, is_stockable, is_payment, expense_type)
REQUEST_TYPES: Dict[str, Dict[str, Any]] = {
    "material":         {"label": "Material (Scaffolding etc.)", "dept": "stores", "stockable": True, "payment": False, "expense_type": "scaffolding_material"},
    "ppe":              {"label": "PPE for Manpower", "dept": "stores", "stockable": True, "payment": False, "expense_type": "ppe_safety"},
    "it_material":      {"label": "IT Material (Laptop, Printer…)", "dept": "stores", "stockable": True, "payment": False, "expense_type": "office_admin"},
    "accommodation":    {"label": "Accommodation / Room Rent", "dept": "admin", "stockable": False, "payment": True, "expense_type": "accommodation"},
    "fuel":             {"label": "Fuel Payment", "dept": "admin", "stockable": False, "payment": True, "expense_type": "fuel"},
    "insurance":        {"label": "Insurance", "dept": "admin", "stockable": False, "payment": True, "expense_type": "office_admin"},
    "vehicle_manpower": {"label": "Monthly Vehicle — Manpower (Car/Bus/Winger)", "dept": "logistics", "stockable": False, "payment": True, "expense_type": "vehicle"},
    "vehicle_material": {"label": "Monthly Vehicle — Material (Truck)", "dept": "logistics", "stockable": False, "payment": True, "expense_type": "vehicle"},
    "one_time_vehicle": {"label": "One-Time Vehicle (Site-to-Site / Godown)", "dept": "logistics", "stockable": False, "payment": True, "expense_type": "vehicle"},
    "manpower":         {"label": "Manpower / Site Staff", "dept": "hr", "stockable": False, "payment": False, "expense_type": None},
    "other":            {"label": "Other", "dept": "admin", "stockable": False, "payment": True, "expense_type": "misc"},
    "self_expense":     {"label": "User Expense / Self Expense", "dept": "admin", "stockable": False, "payment": True, "expense_type": "head_office"},
}


async def get_request_types(active_only: bool = False) -> Dict[str, Dict[str, Any]]:
    """Built-in REQUEST_TYPES merged with super-admin overrides/custom entries."""
    merged: Dict[str, Dict[str, Any]] = {k: {**v, "active": True, "builtin": True} for k, v in REQUEST_TYPES.items()}
    async for o in db.request_type_options.find({}, {"_id": 0}):
        k = o.get("key")
        if not k:
            continue
        base = merged.get(k, {"label": k, "dept": "admin", "stockable": False, "payment": True,
                              "expense_type": "misc", "builtin": False})
        for f in ("label", "dept", "expense_type"):
            if o.get(f):
                base[f] = o[f]
        for f in ("stockable", "payment"):
            if o.get(f) is not None:
                base[f] = bool(o[f])
        base["active"] = o.get("active", True)
        merged[k] = base
    if active_only:
        return {k: v for k, v in merged.items() if v.get("active", True)}
    return merged
RAISE_ROLES = {"project_coordinator", "project_manager", "super_admin"}
FULFIL_ROLES = {
    "stores": {"super_admin", "store_manager", "storekeeper", "inventory_manager", "procurement_executive"},
    "logistics": {"super_admin", "logistics_executive", "logistics_manager", "dept_head"},
    "admin": {"super_admin", "accounts_executive", "hr_executive", "admin_executive", "director"},
    "hr": {"super_admin", "hr_executive", "hr_manager", "dept_head", "director"},
}


HO_CC_SEED = [
    ("HEADOFF", "Head Office Expense"),
    ("HO-RENT", "Office Rent & Utilities"),
    ("HO-ADMIN", "Office Supplies & Admin"),
    ("HO-TRAVEL", "Travel & Conveyance"),
    ("HO-WELFARE", "Staff Welfare"),
    ("HO-IT", "IT & Communication"),
]


@router.get("/head-office-cost-centers")
async def head_office_cost_centers(user: dict = Depends(require_permission("project_requests", "read"))):
    """Head Office (non-project) cost centers for self/HO expenses. Seeds standard set once."""
    q = {"project_id": None, "active": {"$ne": False}}
    proj = {"_id": 0, "id": 1, "code": 1, "name": 1, "category_code": 1, "category_name": 1}
    rows = [c async for c in db.cost_centers.find(q, proj)]
    existing = {c.get("category_code") for c in rows}
    seeded = False
    for code, name in HO_CC_SEED:
        if code not in existing:
            await db.cost_centers.insert_one({
                "id": new_id(), "code": f"CC-{code}", "name": name,
                "category_code": code, "category_name": name,
                "project_id": None, "project_code": None, "head_office": True,
                "active": True, "created_at": now_iso(), "created_by": "system (HO seed)"})
            seeded = True
    if seeded:
        rows = [c async for c in db.cost_centers.find(q, proj)]
    return sorted(rows, key=lambda c: c.get("category_name") or "")


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def _large_threshold() -> float:
    doc = await db.proj_settings.find_one({"id": "global"}, {"_id": 0, "daily_expense_large_threshold": 1})
    return float((doc or {}).get("daily_expense_large_threshold") or 10000)


class ReqItem(BaseModel):
    name: str
    item_id: Optional[str] = None
    item_code: Optional[str] = None
    category: Optional[str] = None
    quantity: float = 1
    unit: str = "Nos"
    rate: float = 0
    specs: Optional[str] = None
    # category-specific detail fields (PPE / IT / Manpower / Scaffolding)
    size: Optional[str] = None
    make: Optional[str] = None
    item_type: Optional[str] = None
    tech_details: Optional[str] = None
    designation_id: Optional[str] = None
    material: Optional[str] = None
    coating: Optional[str] = None
    unit_weight_kg: Optional[float] = None


class RequestIn(BaseModel):
    id: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    request_type: str
    need_by: Optional[str] = None
    priority: str = "medium"
    description: Optional[str] = ""
    items: List[ReqItem] = []
    # payment / vehicle / accommodation fields
    vendor: Optional[str] = None
    vehicle_ref: Optional[str] = None
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    monthly_rate: Optional[float] = None
    months: Optional[float] = None
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    amount: Optional[float] = None
    remarks: Optional[str] = None
    cost_center_id: Optional[str] = None
    site_location: Optional[str] = None
    material_category_id: Optional[str] = None
    employee_id: Optional[str] = None      # HR master employee (service/payment requests)
    expense_type: Optional[str] = None     # override (defaults to routing meta)
    expense_date: Optional[str] = None
    beneficiaries: Optional[List[Dict[str, Any]]] = None  # [{employee_id?, employee_code?, employee_name, amount, remarks?}]
    settlement_mode: Optional[str] = None  # petty_cash | employee_reimbursement | vendor_payable
    paid_to_type: Optional[str] = None     # vendor | person
    payment_mode: Optional[str] = None     # UPI | Accounts (mandatory when priority=high on payment requests)
    upi_any_name: Optional[str] = None     # manual payee name for UPI mode (not in DB)


class ActionIn(BaseModel):
    remarks: Optional[str] = None


def _estimate_value(p: RequestIn) -> float:
    if p.amount:
        return float(p.amount)
    if p.monthly_rate:
        return float(p.monthly_rate) * float(p.months or 1)
    items_total = sum(float(i.quantity or 0) * float(i.rate or 0) for i in p.items)
    if p.request_type == "manpower" and p.months:
        return items_total * float(p.months)
    return items_total


@router.get("/project-requests/types")
async def request_types(user: dict = Depends(require_permission("project_requests", "read"))):
    merged = await get_request_types(active_only=True)
    return [{"key": k, **{x: v.get(x) for x in ("label", "dept", "stockable", "payment")}} for k, v in merged.items()]


async def _stock_for_item(item: ReqItem) -> Dict[str, Any]:
    doc = None
    if item.item_id:
        doc = await db.inventory.find_one({"id": item.item_id}, {"_id": 0, "quantity": 1, "name": 1, "code": 1})
    if not doc and item.item_code:
        doc = await db.inventory.find_one({"code": item.item_code}, {"_id": 0, "quantity": 1, "name": 1, "code": 1})
    if not doc and item.name:
        doc = await db.inventory.find_one({"name": {"$regex": f"^{item.name.strip()}$", "$options": "i"}},
                                          {"_id": 0, "quantity": 1, "name": 1, "code": 1})
    on_hand = float((doc or {}).get("quantity") or 0)
    req = float(item.quantity or 0)
    return {"name": item.name, "item_code": (doc or {}).get("code") or item.item_code,
            "requested": req, "on_hand": on_hand, "shortfall": max(req - on_hand, 0),
            "in_stock": on_hand >= req, "matched": bool(doc)}


async def _manpower_availability(item: ReqItem) -> Dict[str, Any]:
    """Check the internal pool: available workers + active employees matching the designation/skill."""
    name = (item.name or "").strip()
    rx = {"$regex": re.escape(name), "$options": "i"} if name else None
    workers = 0
    employees = 0
    if rx:
        workers = await db.hr_workers.count_documents({
            "active": {"$ne": False}, "availability": "available",
            "$or": [{"skill_name": rx}, {"name": rx}, {"worker_type": rx}]})
        employees = await db.employees.count_documents({
            "status": {"$nin": ["exited", "inactive"]}, "designation": rx})
    req = float(item.quantity or 0)
    available = workers + employees
    return {"name": name, "requested": req, "available_workers": workers,
            "matching_employees": employees, "available": available,
            "shortfall": max(req - available, 0), "in_pool": available >= req}


@router.post("/project-requests/stock-check")
async def stock_check(p: RequestIn, user: dict = Depends(require_permission("project_requests", "read"))):
    lines = [await _stock_for_item(i) for i in p.items]
    return {"lines": lines, "any_short": any(l["shortfall"] > 0 for l in lines),
            "all_in_stock": bool(lines) and all(l["in_stock"] for l in lines)}


@router.get("/project-requests")
async def list_requests(project_code: Optional[str] = None, request_type: Optional[str] = None,
                        status: Optional[str] = None, dept: Optional[str] = None,
                        user: dict = Depends(require_permission("project_requests", "read"))):
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if request_type:
        q["request_type"] = request_type
    if status:
        q["status"] = status
    if dept:
        q["owning_dept"] = dept
    base = dict(q)
    scoped = await apply_project_scope(user, q, "project_id")
    # Users must always see requests THEY raised (e.g. self/expense payments routed
    # to Head Office with no project scope) with live status.
    q = scoped if scoped is q else {"$or": [scoped, {**base, "created_by_id": user.get("id")}]}
    q["source"] = {"$ne": "vendor_bill"}  # vendor-bill shadow rows live only in the Accounts queue
    rows = await db.project_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    pay_ids = [r["id"] for r in rows if r.get("is_payment")]
    vmap: Dict[str, Any] = {}
    if pay_ids:
        vmap = {v["request_id"]: v async for v in db.payment_verifications.find(
            {"request_id": {"$in": pay_ids}},
            {"_id": 0, "request_id": 1, "stage": 1, "verified_by": 1, "verified_at": 1,
             "utr_no": 1, "paid_date": 1, "bank_file_no": 1, "vendor_name": 1, "remarks": 1})}
    for r in rows:
        r["attachment_count"] = await db.files.count_documents({"parent_type": "project_requests", "parent_id": r["id"]})
        if r.get("is_payment") and r.get("status") in ("with_dept", "pr_raised", "sourcing", "fulfilled"):
            v = vmap.get(r["id"])
            r["pay_stage"] = (v or {}).get("stage") or "pending_verification"
            r["pay_info"] = v
    return rows


@router.get("/project-requests/summary")
async def summary(project_code: Optional[str] = None,
                  user: dict = Depends(require_permission("project_requests", "read"))):
    q: Dict[str, Any] = {"project_code": project_code} if project_code else {}
    base = dict(q)
    scoped = await apply_project_scope(user, q, "project_id")
    q = scoped if scoped is q else {"$or": [scoped, {**base, "created_by_id": user.get("id")}]}
    rows = await db.project_requests.find(q, {"_id": 0, "status": 1, "est_value": 1}).to_list(5000)
    return {
        "total": len(rows),
        "pending_approval": sum(1 for r in rows if r["status"] == "pending_approval"),
        "with_dept": sum(1 for r in rows if r["status"] == "with_dept"),
        "fulfilled": sum(1 for r in rows if r["status"] in ("fulfilled", "closed")),
        "pr_raised": sum(1 for r in rows if r["status"] in ("pr_raised", "sourcing")),
        "est_value": round(sum(float(r.get("est_value") or 0) for r in rows if r["status"] != "rejected"), 2),
    }


@router.post("/project-requests")
async def create_request(p: RequestIn, request: Request,
                         user: dict = Depends(require_permission("project_requests", "write"))):
    from pm_scope import is_pm_scoped
    if (p.request_type != "self_expense"
            and user.get("role") not in RAISE_ROLES and not is_pm_scoped(user)):
        raise HTTPException(403, "Only Project Coordinator / Project Manager can raise project requests")
    _rtypes = await get_request_types(active_only=True)
    if p.request_type not in _rtypes:
        raise HTTPException(400, f"request_type must be one of {sorted(_rtypes)}")
    meta = _rtypes[p.request_type]
    if meta.get("payment") and (p.priority or "").lower() == "high":
        if p.payment_mode not in ("UPI", "Accounts"):
            raise HTTPException(400, "Payment Mode (UPI or Accounts) is mandatory for HIGH priority payment requests")
    beneficiaries = None
    if p.beneficiaries:
        beneficiaries = []
        for i, b in enumerate(p.beneficiaries, 1):
            name = str(b.get("employee_name") or "").strip()
            try:
                amt = float(b.get("amount") or 0)
            except (TypeError, ValueError):
                amt = 0
            if not name or amt <= 0:
                raise HTTPException(400, f"Beneficiary row {i}: employee name and a positive amount are required")
            beneficiaries.append({"employee_id": b.get("employee_id"), "employee_code": b.get("employee_code"),
                                  "employee_name": name, "amount": round(amt, 2),
                                  "remarks": str(b.get("remarks") or "").strip()})
        p.amount = round(sum(x["amount"] for x in beneficiaries), 2)
    project = None
    if p.project_id:
        project = await db.projects.find_one({"id": p.project_id}, {"_id": 0})
    elif p.project_code:
        project = await db.projects.find_one({"code": p.project_code}, {"_id": 0})
    if not project:
        if p.request_type == "self_expense":
            project = {"id": None, "code": "HEAD-OFFICE", "name": "Head Office", "client": None}
        else:
            raise HTTPException(400, "Select a valid project")
    if project.get("id") and p.request_type != "self_expense":
        await ensure_project_access(user, project["id"])
    est = _estimate_value(p)

    stock_lines: List[Dict[str, Any]] = []
    if meta["stockable"] and p.items:
        stock_lines = [await _stock_for_item(i) for i in p.items]
    availability_lines: List[Dict[str, Any]] = []
    if p.request_type == "manpower" and p.items:
        availability_lines = [await _manpower_availability(i) for i in p.items]

    threshold = await _large_threshold()
    cc = None
    if p.cost_center_id:
        cc = await db.cost_centers.find_one({"id": p.cost_center_id},
                                            {"_id": 0, "id": 1, "category_code": 1, "category_name": 1, "project_id": 1})
        if cc and cc.get("project_id") and cc["project_id"] != project["id"]:
            raise HTTPException(400, "Selected cost center belongs to a different project")
    mcat = None
    if p.material_category_id:
        mcat = await db.inv_categories.find_one({"id": p.material_category_id}, {"_id": 0, "id": 1, "code": 1, "name": 1})
    if not cc and mcat:
        cc = await db.cost_centers.find_one(
            {"project_id": project["id"],
             "$or": [{"category_id": mcat["id"]}, {"category_code": mcat.get("code")}]},
            {"_id": 0, "id": 1, "category_code": 1, "category_name": 1, "project_id": 1})
    if p.request_type == "self_expense":
        if project.get("id"):
            # Project-linked self expense — must book against that project's cost center
            if not p.cost_center_id or not cc:
                raise HTTPException(400, "Select the project's Cost Center for this project-linked self expense")
            if not cc.get("project_id"):
                raise HTTPException(400, "This expense is for a project — select a project cost center, not a Head Office one")
        else:
            # Mandatory HEAD OFFICE cost center selection (non-project CC)
            if not p.cost_center_id or not cc:
                raise HTTPException(400, "Select a Head Office Cost Center before submitting this self expense")
            if cc.get("project_id"):
                raise HTTPException(400, "Self expense must be booked against a Head Office cost center (not a project cost center)")
    if not cc:
        raise HTTPException(400, "Cost Center is mandatory — select a valid Cost Center before submitting this request")
    steps = [("dept_head", "Project Head")]
    if est > threshold:
        steps += [("general_manager", "GM"), ("director", "Director")]
    chain = [{"role": r, "label": l, "status": "pending", "by": None, "at": None, "remarks": None} for r, l in steps]

    emp = None
    if p.employee_id:
        emp = await db.employees.find_one({"id": p.employee_id},
                                          {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "emp_code": 1})
        if not emp:
            raise HTTPException(404, "Employee not found in HR master")
    if p.request_type == "self_expense" and not emp and user.get("email"):
        # Self expense — payee is the requester (auto-link HR record by email)
        emp = await db.employees.find_one({"email": user.get("email")},
                                          {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "emp_code": 1})
    doc = {
        "id": p.id or new_id(),
        "request_no": await next_sequence("REQ"),
        "project_id": project["id"], "project_code": project.get("code"),
        "project_name": project.get("name"), "client_name": project.get("client"),
        "request_type": p.request_type, "request_type_label": meta["label"],
        "owning_dept": meta["dept"], "is_payment": meta["payment"], "is_stockable": meta["stockable"],
        "expense_type": (p.expense_type if p.expense_type in (await _pex_types()) else None) or meta.get("expense_type"),
        "expense_date": p.expense_date,
        "settlement_mode": p.settlement_mode,
        "paid_to_type": ("person" if p.request_type == "self_expense" else p.paid_to_type),
        "need_by": p.need_by, "priority": p.priority, "description": p.description or "",
        "payment_mode": p.payment_mode if meta["payment"] else None,
        "upi_any_name": (p.upi_any_name.strip() if p.upi_any_name else None) if (meta["payment"] and p.payment_mode == "UPI") else None,
        "employee_id": (emp or {}).get("id"),
        "employee_code": (emp or {}).get("employee_id") or (emp or {}).get("emp_code"),
        "employee_name": (emp or {}).get("name") or ((user.get("name") or user.get("email")) if p.request_type == "self_expense" else None),
        "cost_center_id": (cc or {}).get("id"),
        "cost_center_label": f"{(cc or {}).get('category_code') or ''} · {(cc or {}).get('category_name') or ''}".strip(" ·") if cc else None,
        "site_location": p.site_location,
        "material_category_id": (mcat or {}).get("id"),
        "material_category_code": (mcat or {}).get("code"),
        "material_category": (mcat or {}).get("name"),
        "items": [{**i.model_dump(), "fulfil_status": "pending", "fulfil_mode": None,
                   "total_weight_kg": round(float(i.quantity or 0) * float(i.unit_weight_kg or 0), 2)} for i in p.items],
        "total_weight_kg": round(sum(float(i.quantity or 0) * float(i.unit_weight_kg or 0) for i in p.items), 2),
        "stock_lines": stock_lines,
        "availability_lines": availability_lines,
        "vendor": p.vendor, "vehicle_ref": p.vehicle_ref,
        "period_from": p.period_from, "period_to": p.period_to,
        "monthly_rate": p.monthly_rate, "months": p.months,
        "from_location": p.from_location, "to_location": p.to_location,
        "amount": p.amount, "est_value": round(est, 2), "remarks": p.remarks,
        "beneficiaries": beneficiaries, "beneficiary_count": len(beneficiaries) if beneficiaries else 0,
        "is_large_value": est > threshold,
        "status": "pending_approval", "chain": chain, "current_step": 0,
        "pr_id": None, "pr_number": None, "expense_id": None,
        "fulfilled_at": None, "fulfilled_by": None, "fulfil_note": None,
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
    }
    await db.project_requests.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="project_requests", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


def _can_act(user: dict, role: str) -> bool:
    return user.get("role") in (role, "super_admin")


async def _split_beneficiaries(row: dict, patch: Dict[str, Any]) -> None:
    """On final approval of a multi-beneficiary payment request, spawn one child
    payment request per beneficiary so each employee is processed separately in
    the Payment Processing Center. Parent is excluded from the queue."""
    bens = row.get("beneficiaries") or []
    if not row.get("is_payment") or len(bens) < 2:
        return
    child_ids, child_nos = [], []
    for i, b in enumerate(bens, 1):
        child_no = f"{row['request_no']}-B{i:02d}"
        child = {**row,
                 "id": new_id(), "request_no": child_no,
                 "amount": float(b.get("amount") or 0), "est_value": float(b.get("amount") or 0),
                 "employee_id": b.get("employee_id"), "employee_code": b.get("employee_code"),
                 "employee_name": b.get("employee_name"),
                 "description": " — ".join(x for x in [row.get("description"), b.get("remarks")] if x),
                 "beneficiaries": None, "beneficiary_count": 0,
                 "items": [], "stock_lines": [], "availability_lines": [],
                 "parent_request_id": row["id"], "parent_request_no": row["request_no"],
                 "status": patch.get("status") or "with_dept", "chain": patch.get("chain") or row.get("chain"),
                 "approved_at": patch.get("approved_at") or now_iso(),
                 "split_at": now_iso()}
        child.pop("_id", None)
        await db.project_requests.insert_one(child)
        child_ids.append(child["id"]); child_nos.append(child_no)
    patch["split_into_children"] = child_ids
    patch["split_child_nos"] = child_nos


@router.post("/project-requests/{rid}/approve")
async def approve_request(rid: str, p: ActionIn, request: Request,
                          user: dict = Depends(require_permission("project_requests", "write"))):
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] != "pending_approval":
        raise HTTPException(400, f"Cannot approve in status {row['status']}")
    idx = row["current_step"]
    step = row["chain"][idx]
    if not _can_act(user, step["role"]):
        raise HTTPException(403, f"This step requires {step['label']} ({step['role']})")
    row["chain"][idx] = {**step, "status": "approved", "by": user.get("name") or user.get("email"),
                         "at": now_iso(), "remarks": p.remarks}
    patch: Dict[str, Any] = {"chain": row["chain"]}
    if idx + 1 < len(row["chain"]):
        patch["current_step"] = idx + 1
    else:
        patch["status"] = "with_dept"
        patch["approved_at"] = now_iso()
        await _notify_dept(row)
        # Auto-raise recruitment so manpower shortfall lines appear on the
        # HR Manpower Requirement page immediately for the recruitment team.
        if row.get("request_type") == "manpower":
            try:
                fresh = {**row, "status": "with_dept"}
                created = await _do_raise_recruitment(fresh, "System (auto on approval)")
                if created:
                    patch["status"] = "sourcing"
                    patch["recruitment_nos"] = created
            except Exception as exc:  # noqa: BLE001
                logger.warning("auto raise recruitment failed: %s", exc)
        try:
            await _split_beneficiaries(row, patch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("beneficiary split failed: %s", exc)
    await db.project_requests.update_one({"id": rid}, {"$set": patch})
    await audit(user=user, action="req_approve", resource="project_requests", record_id=rid,
                after={"step": step["label"]}, ip=_ip(request))
    return await db.project_requests.find_one({"id": rid}, {"_id": 0})


async def _notify_dept(row: dict) -> None:
    try:
        roles = list(FULFIL_ROLES.get(row["owning_dept"], {"super_admin"}))
        users = await db.users.find({"role": {"$in": roles}}, {"_id": 0, "id": 1}).to_list(100)
        if not users:
            users = await db.users.find({"role": "super_admin"}, {"_id": 0, "id": 1}).to_list(10)
        for u in users:
            await db.notifications.insert_one({
                "id": new_id(), "user_id": u["id"], "kind": "project_request",
                "title": f"New {row['request_type_label']} request — {row['request_no']}",
                "message": f"{row['project_code']} · est ₹{float(row['est_value']):,.0f}. Please review and fulfil.",
                "link": "/app/ops/requests", "read": False, "at": now_iso()})
    except Exception as exc:  # noqa: BLE001
        logger.warning("project-request dept notify failed: %s", exc)


@router.post("/project-requests/{rid}/reject")
async def reject_request(rid: str, p: ActionIn, request: Request,
                         user: dict = Depends(require_permission("project_requests", "write"))):
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] != "pending_approval":
        raise HTTPException(400, f"Cannot reject in status {row['status']}")
    idx = row["current_step"]
    step = row["chain"][idx]
    if not _can_act(user, step["role"]):
        raise HTTPException(403, f"This step requires {step['label']} ({step['role']})")
    row["chain"][idx] = {**step, "status": "rejected", "by": user.get("name") or user.get("email"),
                         "at": now_iso(), "remarks": p.remarks}
    await db.project_requests.update_one({"id": rid}, {"$set": {
        "chain": row["chain"], "status": "rejected", "rejected_reason": p.remarks}})
    await audit(user=user, action="req_reject", resource="project_requests", record_id=rid,
                after={"reason": p.remarks}, ip=_ip(request))
    return await db.project_requests.find_one({"id": rid}, {"_id": 0})


@router.post("/project-requests/{rid}/raise-pr")
async def raise_pr(rid: str, request: Request,
                   user: dict = Depends(require_permission("project_requests", "write"))):
    """Convert the short-stock lines into a Purchase Request (Procurement)."""
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if not row.get("is_stockable"):
        raise HTTPException(400, "Only material / PPE / IT requests can raise a PR")
    if row["status"] != "with_dept":
        raise HTTPException(400, f"Cannot raise PR in status {row['status']} — Project Head must approve first")
    short = [l for l in (row.get("stock_lines") or []) if l.get("shortfall", 0) > 0]
    if not short:
        raise HTTPException(400, "No shortfall — stock is available for all items")
    pr_items = [{
        "name": l["name"], "item_code": l.get("item_code"),
        "quantity": l["shortfall"], "unit": "Nos",
        "description": f"Shortfall for project request {row['request_no']}",
    } for l in short]
    pr_doc = {
        "id": new_id(), "pr_number": await next_sequence("PR"),
        "project_id": row.get("project_id"), "project_code": row.get("project_code"),
        "pr_date": now_iso()[:10], "priority": row.get("priority") or "medium",
        "remarks": f"Auto-raised from project request {row['request_no']} ({row['request_type_label']})",
        "items": pr_items, "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"), "status": "draft",
        "source": "project_request", "source_request_id": rid, "created_at": now_iso(),
    }
    await db.purchase_requisitions.insert_one(pr_doc); pr_doc.pop("_id", None)
    await db.project_requests.update_one({"id": rid}, {"$set": {
        "status": "pr_raised", "pr_id": pr_doc["id"], "pr_number": pr_doc["pr_number"],
        "pr_raised_at": now_iso()}})
    await audit(user=user, action="req_raise_pr", resource="project_requests", record_id=rid,
                after={"pr_number": pr_doc["pr_number"]}, ip=_ip(request))
    return {"pr_number": pr_doc["pr_number"], "pr_id": pr_doc["id"], "items": len(pr_items)}


class FromPlanIn(BaseModel):
    project_id: str
    resource_ids: List[str]
    required_date: Optional[str] = None
    site_location: Optional[str] = None
    priority: str = "medium"
    justification: Optional[str] = None
    submit: Optional[bool] = True


@router.post("/project-requests/from-plan")
async def create_from_plan(p: FromPlanIn, request: Request,
                           user: dict = Depends(require_permission("project_requests", "write"))):
    """Convert Resource Planning lines into unified Project Requests
    (manpower lines → one manpower request; material/tool lines → one material request)."""
    rows = await db.project_resources.find(
        {"id": {"$in": p.resource_ids}, "project_id": p.project_id}, {"_id": 0}).to_list(100)
    found = {r["id"]: r for r in rows}
    missing = [rid for rid in p.resource_ids if rid not in found]
    if missing:
        raise HTTPException(404, f"{len(missing)} plan line(s) not found for this project")
    already = [r for r in rows if r.get("converted_request_no") or r.get("rr_batch_id")]
    if already:
        raise HTTPException(400, "Some lines were already converted to requests")
    mp_items: List[ReqItem] = []
    mat_items: List[ReqItem] = []
    for r in [found[rid] for rid in p.resource_ids]:
        rt = r.get("resource_type")
        if rt == "manpower":
            mp_items.append(ReqItem(name=r.get("designation_name") or "Manpower",
                                    designation_id=r.get("designation_id"),
                                    quantity=float(r.get("count_required") or 1), unit="Persons",
                                    specs=r.get("skill_requirements") or r.get("specification")))
        elif rt == "material":
            mat_items.append(ReqItem(name=r.get("item_name") or "Material", category=r.get("category"),
                                     quantity=float(r.get("quantity") or 1), unit=r.get("uom") or "Nos"))
        elif rt == "tools":
            mat_items.append(ReqItem(name=r.get("tool_name") or "Tool", category=r.get("tool_category"),
                                     quantity=float(r.get("count_required") or 1), unit="Nos",
                                     specs=r.get("specification")))
        else:
            raise HTTPException(400, f"Plan line type '{rt}' cannot be converted (sub-contract goes via vendor/PO flow)")
    created = []
    type_req: Dict[str, str] = {}
    for rtype, items in (("manpower", mp_items), ("material", mat_items)):
        if not items:
            continue
        req_in = RequestIn(project_id=p.project_id, request_type=rtype, items=items,
                           need_by=p.required_date, priority=p.priority,
                           site_location=p.site_location, remarks=p.justification,
                           description=f"Raised from Resource Planning ({len(items)} line(s))")
        doc = await create_request(req_in, request, user)
        created.append(doc["request_no"])
        type_req[rtype] = doc["request_no"]
    if not created:
        raise HTTPException(400, "Nothing to convert")
    for rid in p.resource_ids:
        line = found[rid]
        rtype = "manpower" if line.get("resource_type") == "manpower" else "material"
        await db.project_resources.update_one(
            {"id": rid},
            {"$set": {"converted_request_no": type_req.get(rtype), "converted_at": now_iso()}})
    return {"count": len(created), "request_nos": created}


async def migrate_legacy_resource_requests() -> int:
    """One-time migration: legacy resource_requests → unified project_requests."""
    type_map = {"manpower": "manpower", "consumable": "material", "material": "material",
                "tool": "material", "ppe": "ppe", "asset": "material", "it": "it_material"}
    status_map = {"draft": "pending_approval", "pending_approval": "pending_approval",
                  "approved": "with_dept", "completed": "fulfilled",
                  "cancelled": "cancelled", "rejected": "rejected"}
    n = 0
    async for old in db.resource_requests.find({"migrated_to": {"$exists": False}}, {"_id": 0}):
        try:
            rtype = type_map.get(old.get("resource_type"), "material")
            meta = REQUEST_TYPES[rtype]
            status = status_map.get(old.get("status"), "pending_approval")
            project = await db.projects.find_one({"id": old.get("project_id")}, {"_id": 0}) or {}
            approved = status in ("with_dept", "fulfilled")
            chain = [{"role": "dept_head", "label": "Project Head",
                      "status": "approved" if approved else "pending",
                      "by": "Migrated from legacy module" if approved else None,
                      "at": old.get("updated_at") if approved else None, "remarks": None}]
            item_name = old.get("item_name") or old.get("designation") or old.get("resource_type") or "Item"
            fulfilled = status == "fulfilled"
            doc = {
                "id": new_id(), "request_no": old.get("rr_no") or f"RR-MIG-{(old.get('id') or '')[:6]}",
                "project_id": old.get("project_id"), "project_code": project.get("code"),
                "project_name": project.get("name") or old.get("project_name"),
                "client_name": project.get("client"),
                "request_type": rtype, "request_type_label": meta["label"],
                "owning_dept": meta["dept"], "is_payment": meta["payment"], "is_stockable": meta["stockable"],
                "expense_type": meta["expense_type"],
                "need_by": old.get("required_date"), "priority": old.get("priority") or "medium",
                "description": old.get("justification") or "", "site_location": old.get("site_location"),
                "items": [{"name": item_name, "quantity": float(old.get("quantity") or 1),
                           "unit": old.get("unit") or ("Persons" if rtype == "manpower" else "Nos"),
                           "rate": 0, "fulfil_status": "fulfilled" if fulfilled else "pending",
                           "fulfil_mode": "bulk" if fulfilled else None}],
                "stock_lines": [], "availability_lines": [],
                "est_value": 0, "is_large_value": False,
                "status": status, "chain": chain, "current_step": 0,
                "pr_id": None, "pr_number": None, "expense_id": None,
                "recruitment_ids": [], "recruitment_nos": [],
                "fulfilled_at": old.get("updated_at") if fulfilled else None,
                "fulfilled_by": None, "fulfil_note": "Migrated from legacy module" if fulfilled else None,
                "approved_at": old.get("updated_at") if approved else None,
                "created_at": old.get("created_at") or now_iso(),
                "created_by": old.get("requested_by") or "Legacy",
                "created_by_id": old.get("requested_by_id"),
                "migrated_from": old.get("id"), "migrated_from_rr_no": old.get("rr_no"),
            }
            await db.project_requests.insert_one(doc)
            await db.resource_requests.update_one({"id": old["id"]}, {"$set": {"migrated_to": doc["id"]}})
            n += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("legacy RR migration failed for %s: %s", old.get("id"), exc)
    return n


@router.get("/project-requests/hr-queue")
async def hr_queue(user: dict = Depends(get_current_user)):
    """HR fulfilment lane: manpower requests awaiting sourcing, with ageing."""
    allowed = FULFIL_ROLES["hr"] | {"general_manager", "director", "project_manager"}
    if user.get("role") not in allowed:
        raise HTTPException(403, "HR / leadership only")
    q: Dict[str, Any] = {"request_type": "manpower", "status": {"$in": ["with_dept", "sourcing"]}}
    q = await apply_project_scope(user, q, "project_id")
    rows = await db.project_requests.find(q, {"_id": 0}).sort("approved_at", 1).to_list(500)
    now = datetime.now(timezone.utc)
    for r in rows:
        ref = r.get("approved_at") or r.get("created_at")
        try:
            r["ageing_days"] = max((now - datetime.fromisoformat(str(ref))).days, 0)
        except Exception:
            r["ageing_days"] = 0
        r["headcount"] = sum(float(i.get("quantity") or 0) for i in r.get("items") or [])
        r["lines_pending"] = sum(1 for i in r.get("items") or [] if i.get("fulfil_status") != "fulfilled")
        r["pool_shortfall"] = sum(float(a.get("shortfall") or 0) for a in r.get("availability_lines") or [])
    return {"count": len(rows), "rows": rows}


async def recruitment_link_back(rec: dict, actor: str = "System") -> None:
    """Sync hire progress from a recruitment request onto the source manpower line.
    Updates hired_count; marks the line fulfilled only when fully hired (or status=filled/closed)."""
    rid = rec.get("source_request_id")
    if not rid:
        return
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row or row["status"] not in ("with_dept", "sourcing", "pr_raised"):
        return
    items = row.get("items") or []
    target = (rec.get("source_line_name") or rec.get("position") or "").strip().lower()
    vacancies = int(float(rec.get("vacancies") or 0))
    hired = int(float(rec.get("hired") or 0))
    status_done = rec.get("status") in ("filled", "closed")
    fully_hired = vacancies > 0 and hired >= vacancies
    changed = False
    line_fulfilled = False
    for it in items:
        if (it.get("name") or "").strip().lower() != target or it.get("fulfil_status") == "fulfilled":
            continue
        it["vacancy_count"] = vacancies or it.get("vacancy_count")
        it["hired_count"] = min(hired, vacancies) if vacancies else hired
        changed = True
        if status_done or fully_hired:
            it.update({"fulfil_status": "fulfilled", "fulfil_mode": "sourced",
                       "fulfil_remarks": f"Recruitment {rec.get('req_no')}: {it['hired_count']} of {vacancies} hired",
                       "fulfilled_by": f"System (recruitment via {actor})", "fulfilled_at": now_iso()})
            line_fulfilled = True
        break
    if not changed:
        return
    patch: Dict[str, Any] = {"items": items}
    if all(i.get("fulfil_status") == "fulfilled" for i in items):
        patch.update({"status": "fulfilled", "fulfilled_at": now_iso(),
                      "fulfilled_by": f"System (recruitment {rec.get('status')})",
                      "fulfil_note": "All line items fulfilled (recruitment link-back)"})
    await db.project_requests.update_one({"id": rid}, {"$set": patch})
    try:
        creator_id = row.get("created_by_id")
        if creator_id:
            if line_fulfilled:
                msg = f"Recruitment {rec.get('req_no')} ({rec.get('position')}) complete — line marked done."
            else:
                msg = f"Recruitment {rec.get('req_no')} ({rec.get('position')}): {min(hired, vacancies)} of {vacancies} hired so far."
            await db.notifications.insert_one({
                "id": new_id(), "user_id": creator_id, "kind": "project_request",
                "title": f"Manpower hire update — {row['request_no']}",
                "message": msg, "link": "/app/ops/requests", "read": False, "at": now_iso()})
    except Exception as exc:  # noqa: BLE001
        logger.warning("recruitment link-back notify failed: %s", exc)


async def _do_raise_recruitment(row: dict, actor: str) -> List[str]:
    """Create recruitment requisitions for manpower shortfall lines; returns REQ numbers."""
    avail = {a["name"]: a for a in (row.get("availability_lines") or [])}
    created = []
    items = row.get("items") or []
    for it in items:
        if it.get("recruitment_no"):  # already sourced
            continue
        a = avail.get(it.get("name"))
        vac = int(a["shortfall"]) if a else int(float(it.get("quantity") or 0))
        if vac <= 0:
            continue
        proj = None
        if row.get("project_code"):
            proj = await db.projects.find_one({"code": row["project_code"]},
                                              {"_id": 0, "name": 1, "project_manager_name": 1, "manager": 1})
        rec = {
            "id": new_id(), "req_no": await next_sequence("REQ"),
            "position": it.get("name"), "department": "Operations",
            "vacancies": vac, "hired": 0, "needed_by": row.get("period_from") or row.get("need_by"),
            "project_code": row.get("project_code"), "site": row.get("site_location"),
            "project_name": (proj or {}).get("name"),
            "project_manager": (proj or {}).get("project_manager_name") or (proj or {}).get("manager"),
            "budget_monthly_per_head": float(it.get("rate") or 0),
            "deployment_from": row.get("period_from"), "deployment_to": row.get("period_to"),
            "skills": it.get("specs"), "status": "open",
            "source": "project_request", "source_request_id": row["id"], "source_line_name": it.get("name"),
            "remarks": f"Auto-raised from manpower request {row['request_no']} — pool shortfall",
            "created_at": now_iso(), "created_by": actor,
        }
        await db.recruitment_requests.insert_one(rec)
        created.append(rec["req_no"])
        it["recruitment_no"] = rec["req_no"]
        it["vacancy_count"] = vac
        it["hired_count"] = 0
    if created:
        await db.project_requests.update_one({"id": row["id"]}, {"$set": {
            "status": "sourcing", "recruitment_ids": created, "recruitment_nos": created,
            "items": items, "sourcing_raised_at": now_iso()}})
    return created


async def backfill_manpower_recruitment() -> int:
    """Startup backfill: approved manpower requests that never got recruitment
    requisitions (approved before auto-raise existed) are raised now."""
    n = 0
    async for row in db.project_requests.find(
            {"request_type": "manpower", "status": "with_dept",
             "$or": [{"recruitment_nos": {"$exists": False}}, {"recruitment_nos": []}, {"recruitment_nos": None}]},
            {"_id": 0}):
        try:
            created = await _do_raise_recruitment(row, "System (backfill)")
            if created:
                n += 1
                logger.info("backfilled recruitment for %s: %s", row.get("request_no"), created)
        except Exception as exc:  # noqa: BLE001
            logger.warning("recruitment backfill failed for %s: %s", row.get("id"), exc)
    return n


@router.post("/project-requests/{rid}/raise-recruitment")
async def raise_recruitment(rid: str, request: Request,
                            user: dict = Depends(require_permission("project_requests", "write"))):
    """HR sourcing: convert manpower shortfall lines into Recruitment Requests."""
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row.get("request_type") != "manpower":
        raise HTTPException(400, "Only manpower requests can raise recruitment")
    if row["status"] not in ("with_dept", "sourcing"):
        raise HTTPException(400, f"Cannot raise recruitment in status {row['status']} — Project Head must approve first")
    allowed = FULFIL_ROLES.get("hr", {"super_admin"})
    if user.get("role") not in allowed and user.get("role") != "super_admin":
        raise HTTPException(403, "Only the HR team can raise recruitment for this request")
    created = await _do_raise_recruitment(row, user.get("name") or user.get("email") or "HR")
    if not created:
        raise HTTPException(400, "No shortfall — the internal pool covers all requested manpower")
    await audit(user=user, action="req_raise_recruitment", resource="project_requests", record_id=rid,
                after={"recruitment_nos": created}, ip=_ip(request))
    return {"recruitment_nos": created, "count": len(created)}


class RecruitHrActionIn(BaseModel):
    status: str  # approved | rejected | shortlisting | interview | offer | filled | completed | closed
    pm_info_received: Optional[bool] = None
    hired: Optional[int] = None
    remarks: str = ""


RECRUIT_HR_STATUSES = {"open", "approved", "rejected", "shortlisting", "interview", "offer",
                       "filled", "completed", "closed"}


@router.post("/recruitment-requests/{rid}/hr-action")
async def recruitment_hr_action(rid: str, p: RecruitHrActionIn, request: Request,
                                user: dict = Depends(require_permission("recruitment_requests", "write"))):
    """HR updates recruitment outcome/status with a full status history trail."""
    row = await db.recruitment_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Recruitment request not found")
    if p.status not in RECRUIT_HR_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(RECRUIT_HR_STATUSES)}")
    if p.status == "rejected" and not p.remarks.strip():
        raise HTTPException(400, "Remarks are required when rejecting a recruitment request")
    patch: Dict[str, Any] = {"status": p.status, "updated_at": now_iso(),
                             "hr_actioned_by": user.get("name") or user.get("email"),
                             "hr_actioned_at": now_iso()}
    if p.pm_info_received is not None:
        patch["pm_info_received"] = p.pm_info_received
    if p.hired is not None:
        if p.hired < 0:
            raise HTTPException(400, "Hired count cannot be negative")
        patch["hired"] = int(p.hired)
    if p.remarks.strip():
        patch["hr_outcome_remarks"] = p.remarks.strip()
    entry = {"at": now_iso(), "by": user.get("name") or user.get("email"), "role": user.get("role"),
             "from": row.get("status"), "to": p.status,
             "pm_info_received": p.pm_info_received, "hired": patch.get("hired", row.get("hired")),
             "remarks": p.remarks}
    await db.recruitment_requests.update_one({"id": rid}, {"$set": patch, "$push": {"history": entry}})
    await audit(user=user, action=f"recruitment_hr_{p.status}", resource="recruitment_requests",
                record_id=rid, after={"req_no": row.get("req_no"), "position": row.get("position"),
                                      "status": p.status, "pm_info_received": p.pm_info_received,
                                      "remarks": p.remarks}, ip=_ip(request))
    return await db.recruitment_requests.find_one({"id": rid}, {"_id": 0})


class LineFulfilIn(BaseModel):
    mode: str = "stock"          # stock (from internal pool/store) | sourced (procured/recruited)
    remarks: Optional[str] = None


@router.post("/project-requests/{rid}/items/{idx}/fulfil")
async def fulfil_line(rid: str, idx: int, p: LineFulfilIn, request: Request,
                      user: dict = Depends(require_permission("project_requests", "write"))):
    """Department marks a single line item fulfilled; request auto-completes when all lines are done."""
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] not in ("with_dept", "pr_raised", "sourcing"):
        raise HTTPException(400, f"Cannot fulfil lines in status {row['status']}")
    allowed = FULFIL_ROLES.get(row["owning_dept"], {"super_admin"})
    if user.get("role") not in allowed and user.get("role") != "super_admin":
        raise HTTPException(403, f"Only the {row['owning_dept']} team can fulfil this request")
    items = row.get("items") or []
    if idx < 0 or idx >= len(items):
        raise HTTPException(404, "Line item not found")
    if items[idx].get("fulfil_status") == "fulfilled":
        raise HTTPException(400, "Line already fulfilled")
    items[idx].update({"fulfil_status": "fulfilled", "fulfil_mode": p.mode,
                       "fulfil_remarks": p.remarks,
                       "fulfilled_by": user.get("name") or user.get("email"),
                       "fulfilled_at": now_iso()})
    patch: Dict[str, Any] = {"items": items}
    if all(i.get("fulfil_status") == "fulfilled" for i in items):
        patch.update({"status": "fulfilled", "fulfilled_at": now_iso(),
                      "fulfilled_by": user.get("name") or user.get("email"),
                      "fulfil_note": "All line items fulfilled"})
        if row.get("is_payment"):
            expense_id = await _book_expense(row, user)
            if expense_id:
                patch["expense_id"] = expense_id
    await db.project_requests.update_one({"id": rid}, {"$set": patch})
    await audit(user=user, action="req_fulfil_line", resource="project_requests", record_id=rid,
                after={"line": idx, "mode": p.mode}, ip=_ip(request))
    return await db.project_requests.find_one({"id": rid}, {"_id": 0})


@router.post("/project-requests/{rid}/fulfil")
async def fulfil_request(rid: str, p: ActionIn, request: Request,
                         user: dict = Depends(require_permission("project_requests", "write"))):
    """Department marks the request fulfilled. For payment types this books a
    Daily Expense (cost-center linked) which Accounts then pays with proof."""
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] not in ("with_dept", "pr_raised", "sourcing"):
        raise HTTPException(400, f"Cannot fulfil in status {row['status']}")
    allowed = FULFIL_ROLES.get(row["owning_dept"], {"super_admin"})
    if user.get("role") not in allowed and user.get("role") != "super_admin":
        raise HTTPException(403, f"Only the {row['owning_dept']} team can fulfil this request")
    patch: Dict[str, Any] = {"status": "fulfilled", "fulfilled_at": now_iso(),
                             "fulfilled_by": user.get("name") or user.get("email"),
                             "fulfil_note": p.remarks}
    if row.get("items"):
        patch["items"] = [{**i, "fulfil_status": "fulfilled",
                           "fulfil_mode": i.get("fulfil_mode") or "bulk"} for i in row["items"]]
    expense_id = None
    if row.get("is_payment"):
        expense_id = await _book_expense(row, user)
        if expense_id:
            patch["expense_id"] = expense_id
    await db.project_requests.update_one({"id": rid}, {"$set": patch})
    await audit(user=user, action="req_fulfil", resource="project_requests", record_id=rid,
                after={"expense_id": expense_id}, ip=_ip(request))
    return await db.project_requests.find_one({"id": rid}, {"_id": 0})


async def _book_expense(row: dict, user: dict) -> Optional[str]:
    """Create a Daily Expense (approved_for_payment) from a fulfilled payment request."""
    try:
        cc = None
        if row.get("cost_center_id"):
            cc = await db.cost_centers.find_one({"id": row["cost_center_id"]},
                                                {"_id": 0, "id": 1, "category_code": 1, "category_name": 1})
        if not cc:
            cc = await db.cost_centers.find_one(
                {"project_id": row["project_id"], "active": {"$ne": False}}, {"_id": 0, "id": 1, "category_code": 1, "category_name": 1})
        threshold = await _large_threshold()
        exp = {
            "id": new_id(), "expense_no": await next_sequence("PEX"),
            "project_id": row["project_id"], "project_code": row["project_code"],
            "project_name": row.get("project_name"), "client_name": row.get("client_name"),
            "cost_center_id": (cc or {}).get("id"), "category_code": (cc or {}).get("category_code"),
            "category_name": (cc or {}).get("category_name"),
            "expense_type": row["expense_type"],
            "expense_type_label": row["request_type_label"],
            "expense_date": row.get("expense_date") or now_iso()[:10], "amount": round(float(row.get("est_value") or 0), 2),
            "description": f"From request {row['request_no']} — {row.get('description') or row['request_type_label']}",
            "bill_no": None, "paid_to": row.get("vendor") or row.get("employee_name"), "payment_mode": "Bank",
            "settlement_mode": row.get("settlement_mode") or "vendor_payable",
            "paid_to_type": row.get("paid_to_type"),
            "employee_id": row.get("employee_id"), "employee_code": row.get("employee_code"),
            "employee_name": row.get("employee_name"),
            "remarks": f"Auto-booked from project request {row['request_no']}",
            "is_large_value": float(row.get("est_value") or 0) > threshold, "large_threshold": threshold,
            "status": "approved_for_payment",
            "chain": [{"role": "dept_head", "label": "Project Head", "status": "approved",
                       "by": "System (request approved)", "at": now_iso(), "remarks": None}],
            "current_step": 0, "approved_at": now_iso(),
            "je_id": None, "payment_ref": None, "paid_at": None, "paid_by": None,
            "source": "project_request", "source_request_id": row["id"],
            "created_at": now_iso(), "created_by": f"{user.get('name') or user.get('email')} (request fulfil)",
            "created_by_id": user.get("id"),
        }
        await db.project_expenses.insert_one(exp)
        # notify accounts for payment
        acct = await db.users.find({"role": {"$in": ["accounts_executive", "billing_executive"]}}, {"_id": 0, "id": 1}).to_list(100)
        if not acct:
            acct = await db.users.find({"role": "super_admin"}, {"_id": 0, "id": 1}).to_list(10)
        for u in acct:
            await db.notifications.insert_one({
                "id": new_id(), "user_id": u["id"], "kind": "expense_payment_request",
                "title": f"Request For Payment — {exp['expense_no']}",
                "message": f"{exp['expense_type_label']} · {exp['project_code']} · ₹{exp['amount']:,.0f} from request {row['request_no']}.",
                "link": "/app/ops/expenses", "read": False, "at": now_iso()})
        return exp["id"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("project-request expense booking failed: %s", exc)
        return None


@router.post("/project-requests/{rid}/close")
async def close_request(rid: str, user: dict = Depends(require_permission("project_requests", "write"))):
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0, "status": 1})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] not in ("fulfilled", "with_dept", "pr_raised", "sourcing"):
        raise HTTPException(400, f"Cannot close a request in status {row['status']}")
    await db.project_requests.update_one({"id": rid}, {"$set": {"status": "closed", "closed_at": now_iso()}})
    return await db.project_requests.find_one({"id": rid}, {"_id": 0})


@router.delete("/project-requests/{rid}")
async def delete_request(rid: str, request: Request,
                         user: dict = Depends(require_permission("project_requests", "delete"))):
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0, "status": 1})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] not in ("pending_approval", "rejected"):
        raise HTTPException(400, "Only pending/rejected requests can be deleted")
    await db.project_requests.delete_one({"id": rid})
    await audit(user=user, action="delete", resource="project_requests", record_id=rid, ip=_ip(request))
    return {"deleted": True}


MAT_HEADERS = ["name", "code", "size", "material", "make", "coating", "item_type",
               "quantity", "unit", "unit_weight_kg", "rate", "specs"]


@router.get("/project-requests/material-template")
async def material_template(user: dict = Depends(require_permission("project_requests", "read"))):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(MAT_HEADERS)
    w.writerow(["Cuplock Vertical 3m", "SCF-STD-001", "3.0 m", "MS", "Apex", "Painted", "Vertical", "120", "Nos", "17.1", "1540", "48.3mm OD with cups"])
    w.writerow(["Fixed Coupler", "", "48.3mm", "MS", "", "Galvanised", "Coupler", "500", "Nos", "1.1", "95", ""])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="material_request_template.csv"'})


def _rows_from_upload(filename: str, raw: bytes) -> List[List[str]]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
        rows: List[List[str]] = []
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                if any(c is not None and str(c).strip() for c in r):
                    rows.append(["" if c is None else str(c).strip() for c in r])
        return rows
    text = raw.decode("utf-8-sig", errors="replace")
    return [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0


@router.post("/project-requests/import-items")
async def import_items(request: Request, file: UploadFile = File(...), mode: str = "template",
                       user: dict = Depends(require_permission("project_requests", "write"))):
    """Parse an uploaded Excel/CSV into request item lines. mode=template (strict headers) or mode=ai (LLM extraction)."""
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 5 MB)")
    rows = _rows_from_upload(file.filename or "upload.csv", raw)
    if not rows:
        raise HTTPException(400, "No data rows found in the file")

    if mode == "ai":
        items = await _ai_extract_items(rows)
        return {"items": items, "count": len(items), "source": "ai"}

    headers = [str(h).strip().lower().replace(" ", "_") for h in rows[0]]
    if "name" not in headers:
        raise HTTPException(400, f"Template must have a 'name' column. Expected headers: {', '.join(MAT_HEADERS)}. Use AI mode for free-format files.")
    items = []
    for r in rows[1:]:
        d = {headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))}
        if not (d.get("name") or "").strip():
            continue
        items.append({"name": d.get("name", "").strip(), "item_code": (d.get("code") or "").strip(),
                      "size": d.get("size") or "", "material": d.get("material") or "",
                      "make": d.get("make") or "", "coating": d.get("coating") or "",
                      "item_type": d.get("item_type") or d.get("type") or "",
                      "quantity": _num(d.get("quantity") or d.get("qty") or 1) or 1,
                      "unit": (d.get("unit") or "Nos").strip() or "Nos",
                      "unit_weight_kg": _num(d.get("unit_weight_kg") or d.get("weight")),
                      "rate": _num(d.get("rate")), "specs": d.get("specs") or ""})
    return {"items": items, "count": len(items), "source": "template"}


async def _ai_extract_items(rows: List[List[str]]) -> List[dict]:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")
    sheet = "\n".join("\t".join(r) for r in rows[:300])[:24000]
    chat = LlmChat(
        api_key=key, session_id=f"req-import-{new_id()[:8]}",
        system_message=("You extract material requirement lines from messy spreadsheets for a scaffolding/construction ERP. "
                        "Return ONLY a JSON array (no markdown). Each element: "
                        '{"name": str, "item_code": str, "size": str, "material": str (MOC like MS/GI/Aluminium), '
                        '"make": str, "coating": str, "item_type": str, "quantity": number, "unit": str, '
                        '"unit_weight_kg": number, "rate": number, "specs": str}. '
                        "Skip headers/totals/empty rows. Use empty string or 0 when unknown. Infer sensible units (Nos, Kg, Mtr, Set).")
    ).with_model("openai", "gpt-5.4")
    try:
        resp = await chat.send_message(UserMessage(text=f"Extract the requirement items from this sheet:\n\n{sheet}"))
    except Exception as e:
        logger.exception("AI extraction failed")
        raise HTTPException(502, f"AI extraction failed: {e}")
    text = str(resp).strip()
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise HTTPException(422, "AI could not find requirement lines in this file")
    try:
        parsed = json.loads(m.group(0))
    except Exception:
        raise HTTPException(422, "AI returned unparseable data — try the template upload instead")
    items = []
    for d in parsed:
        if not isinstance(d, dict) or not str(d.get("name") or "").strip():
            continue
        items.append({"name": str(d.get("name")).strip()[:150], "item_code": str(d.get("item_code") or "")[:40],
                      "size": str(d.get("size") or "")[:60], "material": str(d.get("material") or "")[:40],
                      "make": str(d.get("make") or "")[:60], "coating": str(d.get("coating") or "")[:40],
                      "item_type": str(d.get("item_type") or "")[:60],
                      "quantity": _num(d.get("quantity")) or 1, "unit": str(d.get("unit") or "Nos")[:20],
                      "unit_weight_kg": _num(d.get("unit_weight_kg")), "rate": _num(d.get("rate")),
                      "specs": str(d.get("specs") or "")[:200]})
    return items


@router.get("/project-requests/export.{fmt}")
async def export_requests(fmt: str, project_code: Optional[str] = None, status: Optional[str] = None,
                          request_type: Optional[str] = None,
                          user: dict = Depends(require_permission("project_requests", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "Format must be xlsx or pdf")
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    q = await apply_project_scope(user, q, "project_id")
    if request_type:
        q["request_type"] = request_type
    rows = await db.project_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    data = to_excel("project_requests", rows) if fmt == "xlsx" else to_pdf("project_requests", rows)
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if fmt == "xlsx" else "application/pdf")
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="project_requests.{fmt}"'})


# ─── Multi-employee beneficiaries: template / excel parse / AI parse (Iter 189) ───
async def _match_employees(rows: List[dict]) -> Dict[str, Any]:
    """Attach employee_id/code by matching name or code against Employee Master."""
    emp_by_key: Dict[str, dict] = {}
    async for e in db.employees.find({}, {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "emp_code": 1}):
        for k in (e.get("employee_id"), e.get("emp_code")):
            if k:
                emp_by_key[str(k).strip().lower()] = e
        if e.get("name"):
            emp_by_key.setdefault(e["name"].strip().lower(), e)
    out, errors = [], []
    for i, r in enumerate(rows, 1):
        name = str(r.get("employee_name") or "").strip()
        code = str(r.get("employee_code") or "").strip()
        try:
            amt = float(str(r.get("amount") or 0).replace(",", ""))
        except ValueError:
            amt = 0
        if not name and not code:
            continue
        if amt <= 0:
            errors.append({"row": i, "name": name or code, "error": "Amount must be a positive number"})
            continue
        emp = emp_by_key.get(code.lower()) or emp_by_key.get(name.lower())
        out.append({"employee_id": (emp or {}).get("id"),
                    "employee_code": code or (emp or {}).get("employee_id") or (emp or {}).get("emp_code"),
                    "employee_name": (emp or {}).get("name") or name,
                    "amount": round(amt, 2),
                    "remarks": str(r.get("remarks") or "").strip(),
                    "matched": bool(emp)})
    return {"beneficiaries": out, "errors": errors,
            "total": round(sum(x["amount"] for x in out), 2),
            "matched": sum(1 for x in out if x["matched"]),
            "unmatched": sum(1 for x in out if not x["matched"])}


@router.get("/project-requests/beneficiaries/template")
async def beneficiaries_template(user: dict = Depends(require_permission("project_requests", "read"))):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from io import BytesIO
    from fastapi import Response
    wb = Workbook()
    ws = wb.active
    ws.title = "Beneficiaries"
    ws.append(["Employee Code", "Employee Name", "Amount", "Remarks"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F172A")
    for i, w in enumerate([16, 30, 14, 40], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ref = wb.create_sheet("Employee Master (reference)")
    ref.append(["Employee Code", "Employee Name"])
    async for e in db.employees.find({"active": {"$ne": False}}, {"_id": 0, "name": 1, "employee_id": 1, "emp_code": 1}).sort("name", 1):
        ref.append([e.get("employee_id") or e.get("emp_code") or "", e.get("name") or ""])
    ref.column_dimensions["A"].width = 16
    ref.column_dimensions["B"].width = 32
    buf = BytesIO()
    wb.save(buf)
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="payment-beneficiaries-template.xlsx"'})


@router.post("/project-requests/beneficiaries/parse")
async def beneficiaries_parse(file: UploadFile = File(...),
                              user: dict = Depends(require_permission("project_requests", "write"))):
    from openpyxl import load_workbook
    from io import BytesIO
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Upload an .xlsx file (download the template)")
    try:
        wb = load_workbook(BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(400, "Could not read the Excel file")
    ws = wb.worksheets[0]
    header = [str(c.value or "").strip().lower() for c in ws[1]]

    def col(names):
        for n in names:
            if n in header:
                return header.index(n)
        return None
    ci_code = col(["employee code", "emp code", "code"])
    ci_name = col(["employee name", "name", "employee"])
    ci_amt = col(["amount", "amount (₹)", "amt"])
    ci_rem = col(["remarks", "remark", "purpose"])
    if ci_name is None and ci_code is None:
        raise HTTPException(400, "Unrecognized format — first sheet needs 'Employee Name' (or Code) and 'Amount' columns")
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        rows.append({"employee_code": r[ci_code] if ci_code is not None and ci_code < len(r) else "",
                     "employee_name": r[ci_name] if ci_name is not None and ci_name < len(r) else "",
                     "amount": r[ci_amt] if ci_amt is not None and ci_amt < len(r) else 0,
                     "remarks": r[ci_rem] if ci_rem is not None and ci_rem < len(r) else ""})
    return await _match_employees(rows)


class AiBeneficiariesIn(BaseModel):
    text: str


@router.post("/project-requests/beneficiaries/ai-parse")
async def beneficiaries_ai_parse(p: AiBeneficiariesIn,
                                 user: dict = Depends(require_permission("project_requests", "write"))):
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")
    if not (p.text or "").strip():
        raise HTTPException(400, "Paste the employee payment list first")
    chat = LlmChat(
        api_key=key, session_id=f"benef-{new_id()[:8]}",
        system_message=("You extract employee payment lists (e.g. medical reimbursements) from messy pasted text or tables. "
                        "Return ONLY a JSON array (no markdown). Each element: "
                        '{"employee_code": str, "employee_name": str, "amount": number, "remarks": str}. '
                        "Skip headers/totals. Amounts are INR numbers (strip ₹, Rs, commas). Use empty string when unknown.")
    ).with_model("openai", "gpt-5.4")
    try:
        resp = await chat.send_message(UserMessage(text=f"Extract the employee payment list:\n\n{p.text[:20000]}"))
    except Exception as e:
        raise HTTPException(502, f"AI extraction failed: {e}")
    m = re.search(r"\[.*\]", str(resp).strip(), re.S)
    if not m:
        raise HTTPException(422, "AI could not find an employee payment list in the pasted text")
    try:
        rows = json.loads(m.group(0))
    except Exception:
        raise HTTPException(422, "AI returned unparseable data — try the Excel template instead")
    return await _match_employees(rows)
