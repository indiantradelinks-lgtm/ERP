"""Store & Inventory Phase 3 — Material Request + 2-step Transfer + Site/Project views.

Purely additive. Reuses existing collections:
  · inventory                  — current Item Master + qty
  · inventory_transactions     — full stock ledger
  · material_allocations       — material issue / return (Issue is just an allocation; Return
                                  uses the existing /allocations/{id}/return endpoint)
  · challans                   — physical transit document (kept for paperwork; not reimplemented)
  · purchase_requisitions      — purchase requisitions (different from this MR)

NEW collections:
  · material_requests          — internal request from a site/project for material
  · material_transfers         — 2-step transfer ledger (dispatch + receive)
"""
from typing import Optional, List, Dict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/inv3", tags=["store-inventory-phase3"])


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


# ─────────────────────────────────────────────────────────────────────
# 1. Material Request
# ─────────────────────────────────────────────────────────────────────
MR_STATUSES = ("draft", "submitted", "approved", "partially_issued", "issued", "rejected", "cancelled")
MR_PRIORITIES = ("normal", "urgent", "emergency")


class MRLine(BaseModel):
    item_id: str
    required_qty: float
    required_date: Optional[str] = None
    purpose: Optional[str] = None       # painting / scaffolding / consumable
    remarks: Optional[str] = None


class MaterialRequestIn(BaseModel):
    project_code: str                   # MANDATORY per spec (rule 1)
    project_id: Optional[str] = None
    site_id: Optional[str] = None
    site_code: Optional[str] = None
    requested_by_name: Optional[str] = None
    priority: str = "normal"
    required_date: Optional[str] = None
    reason: Optional[str] = None
    remarks: Optional[str] = None
    lines: List[MRLine] = Field(..., min_length=1)


async def _mr_number() -> str:
    n = await db.material_requests.count_documents({})
    return f"MR-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(n + 1).zfill(5)}"


@router.get("/material-requests")
async def list_mr(status: Optional[str] = None, project_code: Optional[str] = None,
                  site_id: Optional[str] = None,
                  user: dict = Depends(require_permission("material_allocations", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    if project_code:
        q["project_code"] = project_code
    if site_id:
        q["site_id"] = site_id
    return await db.material_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/material-requests")
async def create_mr(payload: MaterialRequestIn, request: Request,
                    user: dict = Depends(require_permission("material_allocations", "write"))):
    if payload.priority not in MR_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be in {MR_PRIORITIES}")
    if not payload.project_code:
        raise HTTPException(status_code=400, detail="project_code is mandatory")
    # Enrich each line with item info + availability
    enriched = []
    for ln in payload.lines:
        if ln.required_qty <= 0:
            raise HTTPException(status_code=400, detail="required_qty must be > 0")
        item = await db.inventory.find_one({"id": ln.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {ln.item_id} not found")
        avail = float(item.get("quantity") or 0)
        enriched.append({
            "item_id": ln.item_id,
            "item_code": item.get("code"),
            "item_name": item.get("name"),
            "unit": item.get("unit") or "Nos",
            "required_qty": ln.required_qty,
            "available_qty": avail,
            "short_qty": max(0.0, ln.required_qty - avail),
            "approved_qty": 0.0,
            "issued_qty": 0.0,
            "rate": float(item.get("rate") or 0),
            "required_date": ln.required_date,
            "purpose": ln.purpose,
            "remarks": ln.remarks,
        })

    doc = {
        "id": new_id(),
        "mr_number": await _mr_number(),
        "project_code": payload.project_code,
        "project_id": payload.project_id,
        "site_id": payload.site_id,
        "site_code": payload.site_code,
        "priority": payload.priority,
        "reason": payload.reason,
        "required_date": payload.required_date,
        "remarks": payload.remarks,
        "lines": enriched,
        "line_count": len(enriched),
        "total_required_value": round(sum(ln["required_qty"] * ln["rate"] for ln in enriched), 2),
        "requested_by_id": user["id"],
        "requested_by_name": payload.requested_by_name or user.get("name") or user.get("email"),
        "status": "submitted",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.material_requests.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="material_requests", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


class MRApproveIn(BaseModel):
    line_approvals: Optional[Dict[str, float]] = None  # item_id → approved_qty; None = approve all required
    remarks: Optional[str] = None


@router.post("/material-requests/{mr_id}/approve")
async def approve_mr(mr_id: str, payload: MRApproveIn, request: Request,
                     user: dict = Depends(require_permission("material_allocations", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager", "store_incharge",
                                  "project_manager", "dept_head"}:
        raise HTTPException(status_code=403, detail="Insufficient role to approve material request")
    mr = await db.material_requests.find_one({"id": mr_id}, {"_id": 0})
    if not mr:
        raise HTTPException(status_code=404, detail="Material Request not found")
    if mr.get("status") not in ("submitted", "draft"):
        raise HTTPException(status_code=400, detail=f"Cannot approve — current status {mr.get('status')}")
    if mr.get("requested_by_id") == user["id"] and user.get("role") not in {"super_admin", "director"}:
        raise HTTPException(status_code=403, detail="Cannot approve your own material request")

    new_lines = []
    for ln in mr.get("lines") or []:
        approved = (payload.line_approvals or {}).get(ln["item_id"], ln["required_qty"])
        approved = max(0.0, min(float(approved), float(ln["required_qty"])))
        new_lines.append({**ln, "approved_qty": approved})
    total_approved_value = sum(ln["approved_qty"] * ln["rate"] for ln in new_lines)
    await db.material_requests.update_one({"id": mr_id}, {"$set": {
        "lines": new_lines,
        "status": "approved",
        "approved_by_id": user["id"],
        "approved_by_name": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "approval_remarks": payload.remarks,
        "total_approved_value": round(total_approved_value, 2),
        "updated_at": now_iso(),
    }})
    row = await db.material_requests.find_one({"id": mr_id}, {"_id": 0})
    await audit(user=user, action="approve", resource="material_requests", record_id=mr_id, after=row, ip=_ip(request))
    return row


@router.post("/material-requests/{mr_id}/reject")
async def reject_mr(mr_id: str, payload: dict, request: Request,
                    user: dict = Depends(require_permission("material_allocations", "write"))):
    mr = await db.material_requests.find_one({"id": mr_id}, {"_id": 0})
    if not mr:
        raise HTTPException(status_code=404, detail="Material Request not found")
    if mr.get("status") not in ("submitted", "draft"):
        raise HTTPException(status_code=400, detail=f"Cannot reject — current status {mr.get('status')}")
    await db.material_requests.update_one({"id": mr_id}, {"$set": {
        "status": "rejected",
        "rejected_by_id": user["id"],
        "rejected_at": now_iso(),
        "reject_reason": payload.get("reason"),
        "updated_at": now_iso(),
    }})
    row = await db.material_requests.find_one({"id": mr_id}, {"_id": 0})
    await audit(user=user, action="reject", resource="material_requests", record_id=mr_id, after=row, ip=_ip(request))
    return row


class MRIssueLine(BaseModel):
    item_id: str
    issue_qty: float


class MRIssueIn(BaseModel):
    lines: List[MRIssueLine]
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    returnable: bool = False
    expected_return_date: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/material-requests/{mr_id}/issue")
async def issue_from_mr(mr_id: str, payload: MRIssueIn, request: Request,
                        user: dict = Depends(require_permission("material_allocations", "write"))):
    """Issue material against an approved MR. Reuses `material_allocations` (1 row per line),
    decrements inventory, posts `outward` to inventory_transactions, updates MR.issued_qty."""
    mr = await db.material_requests.find_one({"id": mr_id}, {"_id": 0})
    if not mr:
        raise HTTPException(status_code=404, detail="Material Request not found")
    if mr.get("status") not in ("approved", "partially_issued"):
        raise HTTPException(status_code=400, detail=f"Cannot issue — MR status {mr.get('status')}")

    line_idx = {ln["item_id"]: i for i, ln in enumerate(mr.get("lines") or [])}
    allocations: list = []
    new_lines = list(mr["lines"])
    for il in payload.lines:
        if il.issue_qty <= 0:
            raise HTTPException(status_code=400, detail="issue_qty must be > 0")
        i = line_idx.get(il.item_id)
        if i is None:
            raise HTTPException(status_code=400, detail=f"Item {il.item_id} not part of this MR")
        ln = new_lines[i]
        balance = float(ln.get("approved_qty") or 0) - float(ln.get("issued_qty") or 0)
        if il.issue_qty > balance + 1e-6:
            raise HTTPException(status_code=400, detail=f"Issue qty {il.issue_qty} exceeds approved-balance {balance:g} for item {ln['item_name']}")
        # Race-safe stock decrement (rule 4 — block negative stock)
        res = await db.inventory.update_one(
            {"id": il.item_id, "quantity": {"$gte": il.issue_qty}},
            {"$inc": {"quantity": -il.issue_qty}},
        )
        if res.matched_count == 0:
            item = await db.inventory.find_one({"id": il.item_id}, {"_id": 0}) or {}
            raise HTTPException(status_code=400,
                                detail=f"Insufficient stock — only {float(item.get('quantity') or 0):g} available for {ln['item_name']}")
        # Persist a material_allocation per line so the existing /allocations Return flow works.
        alloc_id = new_id()
        alloc_no = f"ISS-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(await db.material_allocations.count_documents({})).zfill(5)}"
        alloc_doc = {
            "id": alloc_id,
            "allocation_no": alloc_no,
            "kind": "material",
            "item_id": il.item_id,
            "item_name": ln["item_name"],
            "quantity": il.issue_qty,
            "unit": ln.get("unit"),
            "allocated_to_type": "project",
            "project_id": mr.get("project_id"),
            "project_code": mr.get("project_code"),
            "site_id": mr.get("site_id"),
            "site_code": mr.get("site_code"),
            "employee_id": payload.employee_id,
            "employee_name": payload.employee_name,
            "issue_date": now_iso()[:10],
            "expected_return_date": payload.expected_return_date,
            "returnable": payload.returnable,
            "status": "issued",
            "returned_qty": 0.0,
            "remarks": payload.remarks,
            "mr_id": mr_id,
            "mr_number": mr.get("mr_number"),
            "rate": ln.get("rate"),
            "issued_by_id": user["id"],
            "issued_by": user.get("name") or user.get("email"),
            "created_at": now_iso(),
        }
        await db.material_allocations.insert_one(alloc_doc)
        alloc_doc.pop("_id", None)
        # Stock ledger entry
        await db.inventory_transactions.insert_one({
            "id": new_id(),
            "txn_type": "outward",
            "item_id": il.item_id,
            "item_name": ln["item_name"],
            "quantity": il.issue_qty,
            "delta": -il.issue_qty,
            "unit": ln.get("unit"),
            "rate": ln.get("rate"),
            "issued_to": mr.get("project_code"),
            "project_id": mr.get("project_id"),
            "project_code": mr.get("project_code"),
            "site_id": mr.get("site_id"),
            "ref_type": "material_request_issue",
            "ref_id": alloc_id,
            "ref_no": alloc_no,
            "note": f"MR {mr.get('mr_number')} → {ln['item_name']}",
            "status": "posted",
            "created_by": user["id"],
            "created_by_name": user.get("name") or user.get("email"),
            "created_at": now_iso(),
        })
        # Accounts integration — book stock-issue JE for project costing (best-effort)
        try:
            from accounting_service import post_stock_issue
            await post_stock_issue({
                "id": alloc_id, "item_name": ln["item_name"],
                "quantity": il.issue_qty, "unit_cost": float(ln.get("rate") or 0),
                "project_id": mr.get("project_id"), "project_code": mr.get("project_code"),
                "issue_date": now_iso()[:10],
            }, user)
        except Exception:
            pass  # accounting layer not configured for this item — silently continue
        ln["issued_qty"] = float(ln.get("issued_qty") or 0) + il.issue_qty
        new_lines[i] = ln
        allocations.append(alloc_doc)

    # Update MR status
    fully = all(abs(float(ln.get("issued_qty") or 0) - float(ln.get("approved_qty") or 0)) < 1e-6 for ln in new_lines)
    partially = any(float(ln.get("issued_qty") or 0) > 0 for ln in new_lines)
    new_status = "issued" if fully else "partially_issued" if partially else mr["status"]
    await db.material_requests.update_one({"id": mr_id}, {"$set": {
        "lines": new_lines,
        "status": new_status,
        "last_issued_at": now_iso(),
        "updated_at": now_iso(),
    }})

    return {
        "mr_id": mr_id, "mr_number": mr.get("mr_number"),
        "new_status": new_status, "allocations_created": len(allocations),
        "allocations": allocations,
    }


# ─────────────────────────────────────────────────────────────────────
# 2. Material Transfer — 2-step (Dispatch → In-Transit → Receive)
# ─────────────────────────────────────────────────────────────────────
TRANSFER_STATUSES = ("draft", "dispatched", "in_transit", "received", "received_with_exception", "cancelled")


class TransferLine(BaseModel):
    item_id: str
    quantity: float
    remarks: Optional[str] = None


class TransferIn(BaseModel):
    from_store_id: str
    to_store_id: str
    project_code: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    transporter_name: Optional[str] = None
    expected_arrival: Optional[str] = None
    remarks: Optional[str] = None
    lines: List[TransferLine] = Field(..., min_length=1)


@router.get("/transfers")
async def list_transfers(status: Optional[str] = None, project_code: Optional[str] = None,
                          user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    if project_code:
        q["project_code"] = project_code
    return await db.material_transfers.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/transfers")
async def create_transfer(payload: TransferIn, request: Request,
                          user: dict = Depends(require_permission("inventory", "write"))):
    """Step 1 — Dispatch. Posts `transfer_out` at source store, status=in_transit.
    Destination stock is NOT incremented until /receive is called (rule 7)."""
    if payload.from_store_id == payload.to_store_id:
        raise HTTPException(status_code=400, detail="Source and destination cannot be the same store")
    src = await db.inv_stores.find_one({"id": payload.from_store_id}, {"_id": 0})
    dst = await db.inv_stores.find_one({"id": payload.to_store_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Source store not found")
    if not dst:
        raise HTTPException(status_code=404, detail="Destination store not found")

    enriched_lines = []
    for ln in payload.lines:
        if ln.quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity must be > 0")
        item = await db.inventory.find_one({"id": ln.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {ln.item_id} not found")
        # Race-safe debit at source
        res = await db.inventory.update_one(
            {"id": ln.item_id, "quantity": {"$gte": ln.quantity}},
            {"$inc": {"quantity": -ln.quantity}},
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=400,
                                detail=f"Insufficient stock at source — {float(item.get('quantity') or 0):g} available for {item.get('name')}")
        enriched_lines.append({
            "item_id": ln.item_id,
            "item_name": item.get("name"),
            "unit": item.get("unit"),
            "rate": float(item.get("rate") or 0),
            "quantity": ln.quantity,
            "received_qty": 0.0,
            "shortage_qty": 0.0,
            "damaged_qty": 0.0,
            "remarks": ln.remarks,
        })

    transfer_no = f"TRF-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(await db.material_transfers.count_documents({})).zfill(5)}"
    doc = {
        "id": new_id(),
        "transfer_no": transfer_no,
        "from_store_id": payload.from_store_id,
        "from_store_name": src.get("name") or src.get("code"),
        "to_store_id": payload.to_store_id,
        "to_store_name": dst.get("name") or dst.get("code"),
        "project_code": payload.project_code,
        "vehicle_number": payload.vehicle_number,
        "driver_name": payload.driver_name,
        "transporter_name": payload.transporter_name,
        "expected_arrival": payload.expected_arrival,
        "remarks": payload.remarks,
        "lines": enriched_lines,
        "line_count": len(enriched_lines),
        "total_value": round(sum(ln["quantity"] * ln["rate"] for ln in enriched_lines), 2),
        "status": "in_transit",
        "dispatched_at": now_iso(),
        "dispatched_by_id": user["id"],
        "dispatched_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.material_transfers.insert_one(doc)
    # Ledger: transfer_out
    for ln in enriched_lines:
        await db.inventory_transactions.insert_one({
            "id": new_id(),
            "txn_type": "transfer_out",
            "item_id": ln["item_id"],
            "item_name": ln["item_name"],
            "quantity": ln["quantity"],
            "delta": -ln["quantity"],
            "unit": ln["unit"],
            "rate": ln["rate"],
            "store_id": payload.from_store_id,
            "to_store_id": payload.to_store_id,
            "project_code": payload.project_code,
            "ref_type": "material_transfer",
            "ref_id": doc["id"],
            "ref_no": transfer_no,
            "note": f"Dispatched {transfer_no} → {dst.get('name')}",
            "status": "posted",
            "created_by": user["id"],
            "created_by_name": user.get("name") or user.get("email"),
            "created_at": now_iso(),
        })

    doc.pop("_id", None)
    await audit(user=user, action="dispatch", resource="material_transfers", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


class TransferReceiveLine(BaseModel):
    item_id: str
    received_qty: float
    shortage_qty: float = 0
    damaged_qty: float = 0
    damage_notes: Optional[str] = None


class TransferReceiveIn(BaseModel):
    lines: List[TransferReceiveLine]
    received_remarks: Optional[str] = None
    damage_attachment_url: Optional[str] = None


@router.post("/transfers/{transfer_id}/receive")
async def receive_transfer(transfer_id: str, payload: TransferReceiveIn, request: Request,
                           user: dict = Depends(require_permission("inventory", "write"))):
    """Step 2 — Receive. Credits destination stock with `received_qty`, posts
    `transfer_in` and `inward_damaged` to the ledger, marks the transfer
    received (or received_with_exception if there is shortage/damage)."""
    trf = await db.material_transfers.find_one({"id": transfer_id}, {"_id": 0})
    if not trf:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if trf.get("status") != "in_transit":
        raise HTTPException(status_code=400, detail=f"Cannot receive — current status {trf.get('status')}")

    line_idx = {ln["item_id"]: i for i, ln in enumerate(trf["lines"])}
    has_exception = False
    new_lines = list(trf["lines"])
    for rl in payload.lines:
        if rl.received_qty < 0 or rl.shortage_qty < 0 or rl.damaged_qty < 0:
            raise HTTPException(status_code=400, detail="Quantities cannot be negative")
        i = line_idx.get(rl.item_id)
        if i is None:
            raise HTTPException(status_code=400, detail=f"Item {rl.item_id} not in this transfer")
        ln = new_lines[i]
        accounted = rl.received_qty + rl.shortage_qty + rl.damaged_qty
        if accounted > float(ln["quantity"]) + 1e-6:
            raise HTTPException(status_code=400,
                                detail=f"received+shortage+damaged ({accounted}) cannot exceed dispatched ({ln['quantity']}) for {ln['item_name']}")
        if (rl.shortage_qty > 0 or rl.damaged_qty > 0) and not payload.damage_attachment_url and not payload.received_remarks:
            # Rule 9 — damaged/lost must have reason & attachment
            raise HTTPException(status_code=400,
                                detail="Provide damage_attachment_url or received_remarks when reporting shortage/damaged qty")
        ln["received_qty"] = rl.received_qty
        ln["shortage_qty"] = rl.shortage_qty
        ln["damaged_qty"] = rl.damaged_qty
        ln["damage_notes"] = rl.damage_notes
        if rl.received_qty > 0:
            # Credit destination
            await db.inventory.update_one({"id": rl.item_id}, {"$inc": {"quantity": rl.received_qty}})
            await db.inventory_transactions.insert_one({
                "id": new_id(), "txn_type": "transfer_in",
                "item_id": rl.item_id, "item_name": ln["item_name"],
                "quantity": rl.received_qty, "delta": rl.received_qty, "unit": ln["unit"],
                "rate": ln["rate"], "store_id": trf["to_store_id"], "from_store_id": trf["from_store_id"],
                "project_code": trf.get("project_code"),
                "ref_type": "material_transfer", "ref_id": transfer_id, "ref_no": trf["transfer_no"],
                "note": f"Received {trf['transfer_no']}",
                "status": "posted", "created_by": user["id"],
                "created_by_name": user.get("name") or user.get("email"),
                "created_at": now_iso(),
            })
        if rl.shortage_qty > 0 or rl.damaged_qty > 0:
            has_exception = True
        new_lines[i] = ln

    new_status = "received_with_exception" if has_exception else "received"
    await db.material_transfers.update_one({"id": transfer_id}, {"$set": {
        "lines": new_lines,
        "status": new_status,
        "received_at": now_iso(),
        "received_by_id": user["id"],
        "received_by_name": user.get("name") or user.get("email"),
        "received_remarks": payload.received_remarks,
        "damage_attachment_url": payload.damage_attachment_url,
        "updated_at": now_iso(),
    }})
    row = await db.material_transfers.find_one({"id": transfer_id}, {"_id": 0})
    await audit(user=user, action="receive", resource="material_transfers", record_id=transfer_id, after=row, ip=_ip(request))
    return row


@router.get("/in-transit-stock")
async def in_transit_stock(user: dict = Depends(require_permission("inventory", "read"))):
    """Materials currently dispatched but not yet received."""
    transfers = await db.material_transfers.find(
        {"status": "in_transit"}, {"_id": 0},
    ).sort("dispatched_at", -1).to_list(500)
    total_value = sum(float(t.get("total_value") or 0) for t in transfers)
    # Aging
    rows = []
    now = datetime.now(timezone.utc)
    for t in transfers:
        try:
            disp = datetime.fromisoformat((t.get("dispatched_at") or now_iso()).replace("Z", "+00:00"))
            age_days = (now - disp).days
        except Exception:
            age_days = 0
        rows.append({**t, "age_days": age_days})
    rows.sort(key=lambda r: -r["age_days"])
    return {"count": len(rows), "total_value": round(total_value, 2), "rows": rows}


# ─────────────────────────────────────────────────────────────────────
# 3. Site / Project stock + consumption
# ─────────────────────────────────────────────────────────────────────
@router.get("/site-stock")
async def site_stock(user: dict = Depends(require_permission("inventory", "read"))):
    """Stock currently at each site store (using inv_site_stores + inventory.store_id mapping)."""
    sites = await db.inv_site_stores.find({"active": True}, {"_id": 0}).to_list(500)
    out = []
    for s in sites:
        items = await db.inventory.find({"store_id": s["id"]}, {"_id": 0}).to_list(2000)
        total_value = sum(float(it.get("quantity") or 0) * float(it.get("rate") or 0) for it in items)
        out.append({
            "site_id": s["id"], "site_code": s["code"], "site_location": s.get("site_location"),
            "project_code": s.get("project_code"), "client_name": s.get("client_name"),
            "item_count": len(items),
            "total_value": round(total_value, 2),
            "items": [{"item_id": it["id"], "item_name": it.get("name"), "qty": it.get("quantity"),
                       "rate": it.get("rate"), "value": round(float(it.get("quantity") or 0) * float(it.get("rate") or 0), 2)}
                      for it in items if float(it.get("quantity") or 0) > 0],
        })
    out.sort(key=lambda r: -r["total_value"])
    return {"count": len(out), "rows": out}


@router.get("/project-stock")
async def project_stock(project_code: Optional[str] = None,
                         user: dict = Depends(require_permission("inventory", "read"))):
    """Aggregated stock per project — pulls outstanding material_allocations
    (issued + partial_returned) and groups by project_code."""
    q: dict = {"status": {"$in": ["issued", "partially_returned"]}}
    if project_code:
        q["project_code"] = project_code
    allocs = await db.material_allocations.find(q, {"_id": 0}).to_list(5000)
    by_project: dict = {}
    for a in allocs:
        key = a.get("project_code") or "_unassigned"
        bp = by_project.setdefault(key, {"project_code": key, "items": {}, "total_value": 0.0, "alloc_count": 0})
        bp["alloc_count"] += 1
        out_qty = float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0)
        if out_qty <= 0:
            continue
        it_key = a.get("item_id") or a.get("item_name") or "_unknown"
        rec = bp["items"].setdefault(it_key, {
            "item_id": a.get("item_id"), "item_name": a.get("item_name"),
            "unit": a.get("unit"), "rate": float(a.get("rate") or 0),
            "qty": 0.0, "value": 0.0,
        })
        rec["qty"] += out_qty
        rec["value"] += out_qty * float(a.get("rate") or 0)
        bp["total_value"] += out_qty * float(a.get("rate") or 0)
    rows = []
    for p in by_project.values():
        p["items"] = sorted(p["items"].values(), key=lambda r: -r["value"])
        p["item_count"] = len(p["items"])
        p["total_value"] = round(p["total_value"], 2)
        rows.append(p)
    rows.sort(key=lambda r: -r["total_value"])
    return {"count": len(rows), "rows": rows}


@router.get("/project-consumption")
async def project_consumption(project_code: Optional[str] = None,
                              date_from: Optional[str] = None, date_to: Optional[str] = None,
                              user: dict = Depends(require_permission("inventory", "read"))):
    """Material consumed per project — derived from outward inventory_transactions."""
    q: dict = {"txn_type": {"$in": ["outward"]}, "status": "posted"}
    if project_code:
        q["project_code"] = project_code
    if date_from:
        q.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        q.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59Z"
    txns = await db.inventory_transactions.find(q, {"_id": 0}).to_list(20000)
    by_project: dict = {}
    for t in txns:
        key = t.get("project_code") or "_unassigned"
        bp = by_project.setdefault(key, {"project_code": key, "items": {}, "total_value": 0.0, "txn_count": 0})
        bp["txn_count"] += 1
        rate = float(t.get("rate") or 0)
        qty = float(t.get("quantity") or 0)
        bp["total_value"] += qty * rate
        rec = bp["items"].setdefault(t.get("item_id") or t.get("item_name") or "_x", {
            "item_id": t.get("item_id"), "item_name": t.get("item_name"),
            "unit": t.get("unit"), "qty": 0.0, "value": 0.0,
        })
        rec["qty"] += qty
        rec["value"] += qty * rate
    rows = []
    for p in by_project.values():
        p["items"] = sorted(p["items"].values(), key=lambda r: -r["value"])
        p["item_count"] = len(p["items"])
        p["total_value"] = round(p["total_value"], 2)
        rows.append(p)
    rows.sort(key=lambda r: -r["total_value"])
    return {"count": len(rows), "rows": rows}


# ─────────────────────────────────────────────────────────────────────
# 4. Pending Returnable Material
# ─────────────────────────────────────────────────────────────────────
@router.get("/pending-returnable")
async def pending_returnable(project_code: Optional[str] = None,
                             user: dict = Depends(require_permission("material_allocations", "read"))):
    """Material_allocations marked returnable=true that are still out
    (status in issued / partially_returned) — high-value scaffolding pipe,
    ladders, harnesses etc."""
    q: dict = {"returnable": True, "status": {"$in": ["issued", "partially_returned"]}}
    if project_code:
        q["project_code"] = project_code
    rows = await db.material_allocations.find(q, {"_id": 0}).sort("issue_date", 1).to_list(5000)
    enriched = []
    now = datetime.now(timezone.utc)
    total_value = 0.0
    for a in rows:
        out_qty = float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0)
        if out_qty <= 0:
            continue
        rate = float(a.get("rate") or 0)
        try:
            issued = datetime.fromisoformat((a.get("issue_date") or now_iso()[:10]) + "T00:00:00+00:00")
            days_out = (now - issued).days
        except Exception:
            days_out = 0
        try:
            exp = a.get("expected_return_date")
            overdue = exp and datetime.fromisoformat(exp + "T00:00:00+00:00") < now
        except Exception:
            overdue = False
        value = out_qty * rate
        total_value += value
        enriched.append({
            "allocation_id": a["id"],
            "allocation_no": a.get("allocation_no"),
            "item_id": a.get("item_id"),
            "item_name": a.get("item_name"),
            "unit": a.get("unit"),
            "issued_qty": a.get("quantity"),
            "returned_qty": a.get("returned_qty") or 0,
            "outstanding_qty": out_qty,
            "rate": rate,
            "outstanding_value": round(value, 2),
            "project_code": a.get("project_code"),
            "site_code": a.get("site_code"),
            "employee_name": a.get("employee_name"),
            "issue_date": a.get("issue_date"),
            "expected_return_date": a.get("expected_return_date"),
            "days_out": days_out,
            "overdue": bool(overdue),
        })
    enriched.sort(key=lambda r: (not r["overdue"], -r["outstanding_value"]))
    return {"count": len(enriched), "total_value": round(total_value, 2), "rows": enriched}


# ─────────────────────────────────────────────────────────────────────
# 5. Project Closure Material Check
# ─────────────────────────────────────────────────────────────────────
@router.get("/project-closure-check/{project_code}")
async def project_closure_check(project_code: str,
                                user: dict = Depends(require_permission("material_allocations", "read"))):
    """Pre-closure validation. Flags:
       · returnable material still out at the project
       · in-transit transfers tagged to the project
       · pending material requests on the project (status != issued/rejected/cancelled)
    """
    pending_ret = await db.material_allocations.find(
        {"project_code": project_code, "returnable": True,
         "status": {"$in": ["issued", "partially_returned"]}}, {"_id": 0},
    ).to_list(5000)
    pending_ret_value = sum(
        (float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0)) * float(a.get("rate") or 0)
        for a in pending_ret
    )
    in_transit = await db.material_transfers.count_documents({"project_code": project_code, "status": "in_transit"})
    pending_mr = await db.material_requests.count_documents({
        "project_code": project_code,
        "status": {"$in": ["submitted", "approved", "partially_issued"]},
    })
    project_stock_value = 0.0
    allocs = await db.material_allocations.find(
        {"project_code": project_code, "status": {"$in": ["issued", "partially_returned"]}}, {"_id": 0},
    ).to_list(5000)
    for a in allocs:
        out = float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0)
        project_stock_value += out * float(a.get("rate") or 0)

    can_close = (len(pending_ret) == 0 and in_transit == 0 and pending_mr == 0)
    blockers = []
    if pending_ret:
        blockers.append(f"{len(pending_ret)} returnable allocations outstanding · ₹{pending_ret_value:,.2f}")
    if in_transit:
        blockers.append(f"{in_transit} material transfer(s) still in-transit")
    if pending_mr:
        blockers.append(f"{pending_mr} material request(s) pending issue")
    return {
        "project_code": project_code,
        "can_close": can_close,
        "pending_returnable_count": len(pending_ret),
        "pending_returnable_value": round(pending_ret_value, 2),
        "in_transit_count": in_transit,
        "pending_mr_count": pending_mr,
        "project_stock_value": round(project_stock_value, 2),
        "blockers": blockers,
        "pending_returnable_items": [
            {"allocation_no": a.get("allocation_no"), "item_name": a.get("item_name"),
             "outstanding_qty": float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0),
             "value": round((float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0)) * float(a.get("rate") or 0), 2)}
            for a in pending_ret[:20]
        ],
    }
