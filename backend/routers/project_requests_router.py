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

import io
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
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
}
RAISE_ROLES = {"project_coordinator", "project_manager", "super_admin"}
FULFIL_ROLES = {
    "stores": {"super_admin", "store_manager", "storekeeper", "inventory_manager", "procurement_executive"},
    "logistics": {"super_admin", "logistics_executive", "logistics_manager", "dept_head"},
    "admin": {"super_admin", "accounts_executive", "hr_executive", "admin_executive", "director"},
    "hr": {"super_admin", "hr_executive", "hr_manager", "dept_head", "director"},
}


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
    # category-specific detail fields (PPE / IT / Manpower)
    size: Optional[str] = None
    make: Optional[str] = None
    item_type: Optional[str] = None
    tech_details: Optional[str] = None
    designation_id: Optional[str] = None


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


class ActionIn(BaseModel):
    remarks: Optional[str] = None


def _estimate_value(p: RequestIn) -> float:
    if p.amount:
        return float(p.amount)
    if p.monthly_rate:
        return float(p.monthly_rate) * float(p.months or 1)
    return sum(float(i.quantity or 0) * float(i.rate or 0) for i in p.items)


@router.get("/project-requests/types")
async def request_types(user: dict = Depends(require_permission("project_requests", "read"))):
    return [{"key": k, **{x: v[x] for x in ("label", "dept", "stockable", "payment")}} for k, v in REQUEST_TYPES.items()]


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
    rows = await db.project_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    for r in rows:
        r["attachment_count"] = await db.files.count_documents({"parent_type": "project_requests", "parent_id": r["id"]})
    return rows


@router.get("/project-requests/summary")
async def summary(project_code: Optional[str] = None,
                  user: dict = Depends(require_permission("project_requests", "read"))):
    q: Dict[str, Any] = {"project_code": project_code} if project_code else {}
    rows = await db.project_requests.find(q, {"_id": 0, "status": 1, "est_value": 1}).to_list(5000)
    return {
        "total": len(rows),
        "pending_approval": sum(1 for r in rows if r["status"] == "pending_approval"),
        "with_dept": sum(1 for r in rows if r["status"] == "with_dept"),
        "fulfilled": sum(1 for r in rows if r["status"] in ("fulfilled", "closed")),
        "pr_raised": sum(1 for r in rows if r["status"] == "pr_raised"),
        "est_value": round(sum(float(r.get("est_value") or 0) for r in rows if r["status"] != "rejected"), 2),
    }


@router.post("/project-requests")
async def create_request(p: RequestIn, request: Request,
                         user: dict = Depends(require_permission("project_requests", "write"))):
    if user.get("role") not in RAISE_ROLES:
        raise HTTPException(403, "Only Project Coordinator / Project Manager can raise project requests")
    if p.request_type not in REQUEST_TYPES:
        raise HTTPException(400, f"request_type must be one of {sorted(REQUEST_TYPES)}")
    meta = REQUEST_TYPES[p.request_type]
    project = None
    if p.project_id:
        project = await db.projects.find_one({"id": p.project_id}, {"_id": 0})
    elif p.project_code:
        project = await db.projects.find_one({"code": p.project_code}, {"_id": 0})
    if not project:
        raise HTTPException(400, "Select a valid project")
    est = _estimate_value(p)

    stock_lines: List[Dict[str, Any]] = []
    if meta["stockable"] and p.items:
        stock_lines = [await _stock_for_item(i) for i in p.items]

    threshold = await _large_threshold()
    cc = None
    if p.cost_center_id:
        cc = await db.cost_centers.find_one({"id": p.cost_center_id},
                                            {"_id": 0, "id": 1, "category_code": 1, "category_name": 1, "project_id": 1})
        if cc and cc.get("project_id") and cc["project_id"] != project["id"]:
            raise HTTPException(400, "Selected cost center belongs to a different project")
    steps = [("dept_head", "Project Head")]
    if est > threshold:
        steps += [("general_manager", "GM"), ("director", "Director")]
    chain = [{"role": r, "label": l, "status": "pending", "by": None, "at": None, "remarks": None} for r, l in steps]

    doc = {
        "id": p.id or new_id(),
        "request_no": await next_sequence("REQ"),
        "project_id": project["id"], "project_code": project.get("code"),
        "project_name": project.get("name"), "client_name": project.get("client"),
        "request_type": p.request_type, "request_type_label": meta["label"],
        "owning_dept": meta["dept"], "is_payment": meta["payment"], "is_stockable": meta["stockable"],
        "expense_type": meta["expense_type"],
        "need_by": p.need_by, "priority": p.priority, "description": p.description or "",
        "cost_center_id": (cc or {}).get("id"),
        "cost_center_label": f"{(cc or {}).get('category_code') or ''} · {(cc or {}).get('category_name') or ''}".strip(" ·") if cc else None,
        "site_location": p.site_location,
        "items": [i.model_dump() for i in p.items],
        "stock_lines": stock_lines,
        "vendor": p.vendor, "vehicle_ref": p.vehicle_ref,
        "period_from": p.period_from, "period_to": p.period_to,
        "monthly_rate": p.monthly_rate, "months": p.months,
        "from_location": p.from_location, "to_location": p.to_location,
        "amount": p.amount, "est_value": round(est, 2), "remarks": p.remarks,
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


@router.post("/project-requests/{rid}/fulfil")
async def fulfil_request(rid: str, p: ActionIn, request: Request,
                         user: dict = Depends(require_permission("project_requests", "write"))):
    """Department marks the request fulfilled. For payment types this books a
    Daily Expense (cost-center linked) which Accounts then pays with proof."""
    row = await db.project_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] not in ("with_dept", "pr_raised"):
        raise HTTPException(400, f"Cannot fulfil in status {row['status']}")
    allowed = FULFIL_ROLES.get(row["owning_dept"], {"super_admin"})
    if user.get("role") not in allowed and user.get("role") != "super_admin":
        raise HTTPException(403, f"Only the {row['owning_dept']} team can fulfil this request")
    patch: Dict[str, Any] = {"status": "fulfilled", "fulfilled_at": now_iso(),
                             "fulfilled_by": user.get("name") or user.get("email"),
                             "fulfil_note": p.remarks}
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
            "expense_date": now_iso()[:10], "amount": round(float(row.get("est_value") or 0), 2),
            "description": f"From request {row['request_no']} — {row.get('description') or row['request_type_label']}",
            "bill_no": None, "paid_to": row.get("vendor"), "payment_mode": "Bank",
            "settlement_mode": "vendor_payable", "remarks": f"Auto-booked from project request {row['request_no']}",
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
    if row["status"] not in ("fulfilled", "with_dept", "pr_raised"):
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
    if request_type:
        q["request_type"] = request_type
    rows = await db.project_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    data = to_excel("project_requests", rows) if fmt == "xlsx" else to_pdf("project_requests", rows)
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if fmt == "xlsx" else "application/pdf")
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="project_requests.{fmt}"'})
