"""Store & Inventory Phase 4 — PPE / Damage-Loss / Scrap / Clearance / Recovery.

Purely additive. Reuses existing collections:
  · material_allocations  — Tool Issue + Return (kind=tool/asset/consumable)
  · ppe_issuance          — PPE register (already used by HR Onboarding & Employee360)
  · inventory             — Item Master + qty
  · inventory_transactions— stock ledger (scrap / write-off entries posted here)
  · assets                — asset register with warranty + AMC
  · material_transfers    — Phase 3 transfers (used for transit exceptions)
  · exit_forms            — HR exit/FNF (clearance gating helper)

NEW collections:
  · ppe_inspections       — periodic inspection of harness/lifeline/lifecycle PPE
  · damage_loss_entries   — damage/loss declarations with approval flow
  · scrap_entries         — scrap declarations (moves stock to scrap)
  · scrap_sale_requests   — scrap sale proposals (creates AR + reduces scrap stock)
  · recoveries            — consolidated recovery register (debits Employee Recoverable)

Endpoints prefixed `/inv4/...`.
"""
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/inv4", tags=["store-inventory-phase4"])


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ─────────────────────────────────────────────────────────────────────
# 1. PPE Issue + Expiry validation (Store-side day-to-day)
# ─────────────────────────────────────────────────────────────────────
PPE_ISSUE_TYPES = ("new", "replacement", "returnable", "non_returnable")


class PPEIssueIn(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    project_code: Optional[str] = None
    site_code: Optional[str] = None
    item_id: str
    quantity: float = 1.0
    size: Optional[str] = None
    issue_type: str = "new"           # new | replacement | returnable | non_returnable
    expiry_date: Optional[str] = None
    inspection_due_date: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/ppe-issues")
async def ppe_issue(payload: PPEIssueIn, request: Request,
                    user: dict = Depends(require_permission("inventory", "write"))):
    """Issue a PPE item to an employee. Validates:
       · Item exists
       · Item has no expired stock (item.expiry_date <= today → 400)
       · Item.condition is not 'damaged' / 'unfit'
       · Race-safe stock decrement
    Persists into the existing `ppe_issuance` collection.
    """
    if payload.issue_type not in PPE_ISSUE_TYPES:
        raise HTTPException(status_code=400, detail=f"issue_type must be in {PPE_ISSUE_TYPES}")
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0")
    item = await db.inventory.find_one({"id": payload.item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="PPE item not found")
    # Rule 1: expired PPE cannot be issued
    item_expiry = item.get("expiry_date")
    if item_expiry and item_expiry <= _today():
        raise HTTPException(status_code=400, detail=f"PPE item expired on {item_expiry} — cannot issue")
    # Rule 2: damaged / unfit safety item cannot be issued
    if item.get("condition") in ("damaged", "scrap", "unfit"):
        raise HTTPException(status_code=400, detail=f"PPE item is {item.get('condition')} — cannot issue")
    # Race-safe debit
    res = await db.inventory.update_one(
        {"id": payload.item_id, "quantity": {"$gte": payload.quantity}},
        {"$inc": {"quantity": -payload.quantity}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=400, detail=f"Insufficient PPE stock — only {float(item.get('quantity') or 0):g} available")

    issue_no = f"PPE-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(await db.ppe_issuance.count_documents({})).zfill(5)}"
    doc = {
        "id": new_id(),
        "issue_no": issue_no,
        "issue_date": _today(),
        "employee_id": payload.employee_id,
        "employee_name": payload.employee_name,
        "project_code": payload.project_code,
        "site_code": payload.site_code,
        "item_id": payload.item_id,
        "item_name": item.get("name"),
        "item_code": item.get("code"),
        "quantity": payload.quantity,
        "size": payload.size,
        "issue_type": payload.issue_type,
        "expiry_date": payload.expiry_date or item.get("expiry_date"),
        "inspection_due_date": payload.inspection_due_date,
        "rate": float(item.get("rate") or 0),
        "value": round(float(item.get("rate") or 0) * payload.quantity, 2),
        "remarks": payload.remarks,
        "status": "issued",
        "issued_by_id": user["id"],
        "issued_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.ppe_issuance.insert_one(doc)
    doc.pop("_id", None)
    # Ledger
    await db.inventory_transactions.insert_one({
        "id": new_id(), "txn_type": "outward",
        "item_id": payload.item_id, "item_name": item.get("name"),
        "quantity": payload.quantity, "delta": -payload.quantity,
        "unit": item.get("unit"), "rate": float(item.get("rate") or 0),
        "issued_to": payload.employee_name or payload.employee_id,
        "employee_id": payload.employee_id,
        "project_code": payload.project_code,
        "ref_type": "ppe_issuance", "ref_id": doc["id"], "ref_no": issue_no,
        "note": f"PPE → {payload.employee_name or payload.employee_id} · {item.get('name')}",
        "status": "posted", "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    })
    await audit(user=user, action="ppe_issue", resource="ppe_issuance", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/ppe-issues")
async def list_ppe_issues(employee_id: Optional[str] = None, project_code: Optional[str] = None,
                          status: Optional[str] = None,
                          user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {}
    if employee_id:
        q["employee_id"] = employee_id
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    return await db.ppe_issuance.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.get("/ppe-expiry-register")
async def ppe_expiry_register(within_days: int = 90,
                              user: dict = Depends(require_permission("inventory", "read"))):
    """Active PPE issues whose expiry_date / inspection_due_date falls within `within_days`."""
    today = _today()
    from datetime import timedelta
    horizon = (datetime.now(timezone.utc).date() + timedelta(days=within_days)).isoformat()
    rows = await db.ppe_issuance.find({
        "$or": [
            {"expiry_date": {"$ne": None, "$lte": horizon}},
            {"inspection_due_date": {"$ne": None, "$lte": horizon}},
        ],
        "status": {"$in": ["issued", "active"]},
    }, {"_id": 0}).sort("expiry_date", 1).to_list(2000)
    enriched = []
    for r in rows:
        exp = r.get("expiry_date")
        insp = r.get("inspection_due_date")
        days_to_expiry = None
        if exp:
            try:
                days_to_expiry = (datetime.fromisoformat(exp).date() - datetime.now(timezone.utc).date()).days
            except Exception:
                pass
        enriched.append({**r, "days_to_expiry": days_to_expiry,
                         "expired": bool(exp and exp <= today)})
    enriched.sort(key=lambda r: (r["expired"] is False, r.get("days_to_expiry") or 9999))
    return {"count": len(enriched), "rows": enriched, "as_of": today, "horizon": horizon}


# ─────────────────────────────────────────────────────────────────────
# 2. Safety Equipment Inspection Register
# ─────────────────────────────────────────────────────────────────────
INSPECTION_RESULTS = ("pass", "fail", "conditional")


class PPEInspectionIn(BaseModel):
    ppe_issue_id: Optional[str] = None        # if inspecting an issued PPE
    item_id: Optional[str] = None             # or inspecting stock-on-shelf
    inspection_date: str
    inspector_name: str
    result: str = "pass"
    findings: Optional[str] = None
    next_due_date: Optional[str] = None
    attachment_url: Optional[str] = None


@router.get("/ppe-inspections")
async def list_inspections(result: Optional[str] = None, item_id: Optional[str] = None,
                            user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {}
    if result:
        q["result"] = result
    if item_id:
        q["item_id"] = item_id
    return await db.ppe_inspections.find(q, {"_id": 0}).sort("inspection_date", -1).to_list(1000)


@router.post("/ppe-inspections")
async def create_inspection(payload: PPEInspectionIn, request: Request,
                            user: dict = Depends(require_permission("inventory", "write"))):
    if payload.result not in INSPECTION_RESULTS:
        raise HTTPException(status_code=400, detail=f"result must be in {INSPECTION_RESULTS}")
    if not (payload.ppe_issue_id or payload.item_id):
        raise HTTPException(status_code=400, detail="Provide either ppe_issue_id or item_id")
    doc = {
        "id": new_id(),
        **payload.model_dump(),
        "inspector_id": user["id"],
        "created_at": now_iso(),
    }
    await db.ppe_inspections.insert_one(doc)
    doc.pop("_id", None)
    # If the inspection failed, mark the underlying PPE record as 'failed' so it can't be reissued
    if payload.result == "fail" and payload.ppe_issue_id:
        await db.ppe_issuance.update_one({"id": payload.ppe_issue_id},
                                            {"$set": {"inspection_status": "failed",
                                                       "last_inspection_date": payload.inspection_date}})
    elif payload.ppe_issue_id:
        await db.ppe_issuance.update_one({"id": payload.ppe_issue_id},
                                            {"$set": {"inspection_status": payload.result,
                                                       "last_inspection_date": payload.inspection_date,
                                                       "next_inspection_due": payload.next_due_date}})
    await audit(user=user, action="create", resource="ppe_inspections", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


# ─────────────────────────────────────────────────────────────────────
# 3. Damage / Loss Entry with Approval Workflow
# ─────────────────────────────────────────────────────────────────────
DL_STATUSES = ("draft", "submitted", "approved", "rejected", "cancelled")
HIGH_VALUE_THRESHOLD = 25000.0


class DamageLossIn(BaseModel):
    date: str
    item_id: str
    quantity: float
    reason: str
    recoverable: bool = False
    recovery_amount: Optional[float] = None
    project_code: Optional[str] = None
    site_code: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None
    kind: str = "damage"               # damage | loss


@router.get("/damage-loss")
async def list_damage_loss(status: Optional[str] = None, project_code: Optional[str] = None,
                            user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    if project_code:
        q["project_code"] = project_code
    return await db.damage_loss_entries.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/damage-loss")
async def create_damage_loss(payload: DamageLossIn, request: Request,
                              user: dict = Depends(require_permission("inventory", "write"))):
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0")
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="reason is mandatory")
    if not payload.attachment_url:
        raise HTTPException(status_code=400, detail="attachment_url is mandatory for damage/loss (photo/document)")
    item = await db.inventory.find_one({"id": payload.item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    rate = float(item.get("rate") or 0)
    value = round(payload.quantity * rate, 2)
    needs_finance = value >= HIGH_VALUE_THRESHOLD

    no = f"DL-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(await db.damage_loss_entries.count_documents({})).zfill(5)}"
    doc = {
        "id": new_id(),
        "dl_number": no,
        **payload.model_dump(),
        "item_code": item.get("code"),
        "item_name": item.get("name"),
        "unit": item.get("unit"),
        "rate": rate,
        "value": value,
        "needs_finance_approval": needs_finance,
        "status": "submitted",
        "reported_by_id": user["id"],
        "reported_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.damage_loss_entries.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="damage_loss_entries", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.post("/damage-loss/{dl_id}/approve")
async def approve_damage_loss(dl_id: str, request: Request,
                                user: dict = Depends(require_permission("inventory", "write"))):
    dl = await db.damage_loss_entries.find_one({"id": dl_id}, {"_id": 0})
    if not dl:
        raise HTTPException(status_code=404, detail="Damage/Loss entry not found")
    if dl.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"Cannot approve — status {dl.get('status')}")
    # High-value entries require Finance/Owner
    if dl.get("needs_finance_approval") and user.get("role") not in {"super_admin", "director", "finance_head", "general_manager"}:
        raise HTTPException(status_code=403, detail=f"This entry exceeds ₹{HIGH_VALUE_THRESHOLD:,.0f} — requires Director / Finance Head / GM approval")
    # Self-approve guard
    if dl.get("reported_by_id") == user["id"] and user.get("role") not in {"super_admin", "director"}:
        raise HTTPException(status_code=403, detail="Cannot approve your own damage/loss entry")
    # Post-approve: race-safe debit inventory + write_off ledger entry
    qty = float(dl["quantity"])
    res = await db.inventory.update_one(
        {"id": dl["item_id"], "quantity": {"$gte": qty}},
        {"$inc": {"quantity": -qty}},
    )
    if res.matched_count == 0:
        item = await db.inventory.find_one({"id": dl["item_id"]}, {"_id": 0}) or {}
        raise HTTPException(status_code=400,
                            detail=f"Insufficient stock — only {float(item.get('quantity') or 0):g} available; cannot write off {qty:g}")
    await db.inventory_transactions.insert_one({
        "id": new_id(), "txn_type": "write_off",
        "item_id": dl["item_id"], "item_name": dl["item_name"],
        "quantity": qty, "delta": -qty, "unit": dl.get("unit"), "rate": dl.get("rate"),
        "project_code": dl.get("project_code"), "site_id": dl.get("site_code"),
        "ref_type": dl.get("kind", "damage"), "ref_id": dl_id, "ref_no": dl["dl_number"],
        "note": f"{dl.get('kind', 'damage').title()} write-off · {dl['reason']}",
        "status": "posted", "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    })
    # Create recovery row if recoverable
    if dl.get("recoverable") and float(dl.get("recovery_amount") or 0) > 0:
        await db.recoveries.insert_one({
            "id": new_id(),
            "source_type": "damage_loss",
            "source_id": dl_id, "source_no": dl["dl_number"],
            "employee_id": dl.get("employee_id"), "employee_name": dl.get("employee_name"),
            "project_code": dl.get("project_code"),
            "item_name": dl["item_name"],
            "amount": float(dl["recovery_amount"]),
            "status": "pending",
            "raised_by": user["id"], "raised_at": now_iso(),
            "created_at": now_iso(),
        })
    # Accounts hook (best-effort)
    try:
        from accounting_service import post_stock_write_off
        await post_stock_write_off({
            "id": dl_id, "item_name": dl["item_name"],
            "quantity": qty, "unit_cost": dl.get("rate"),
            "project_code": dl.get("project_code"),
        }, user)
    except Exception:
        pass
    await db.damage_loss_entries.update_one({"id": dl_id}, {"$set": {
        "status": "approved",
        "approved_by_id": user["id"], "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
    }})
    row = await db.damage_loss_entries.find_one({"id": dl_id}, {"_id": 0})
    await audit(user=user, action="approve", resource="damage_loss_entries", record_id=dl_id, after=row, ip=_ip(request))
    return row


@router.post("/damage-loss/{dl_id}/reject")
async def reject_damage_loss(dl_id: str, payload: dict, request: Request,
                              user: dict = Depends(require_permission("inventory", "write"))):
    dl = await db.damage_loss_entries.find_one({"id": dl_id}, {"_id": 0})
    if not dl:
        raise HTTPException(status_code=404, detail="Not found")
    await db.damage_loss_entries.update_one({"id": dl_id}, {"$set": {
        "status": "rejected", "rejected_by": user["id"],
        "rejected_at": now_iso(), "reject_reason": payload.get("reason"),
    }})
    row = await db.damage_loss_entries.find_one({"id": dl_id}, {"_id": 0})
    await audit(user=user, action="reject", resource="damage_loss_entries", record_id=dl_id, after=row, ip=_ip(request))
    return row


# ─────────────────────────────────────────────────────────────────────
# 4. Scrap Management
# ─────────────────────────────────────────────────────────────────────
class ScrapEntryIn(BaseModel):
    date: str
    item_id: str
    quantity: float
    project_code: Optional[str] = None
    site_code: Optional[str] = None
    reason: str
    estimated_value: Optional[float] = None
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None


@router.get("/scrap-entries")
async def list_scrap(status: Optional[str] = None,
                      user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {"status": status} if status else {}
    return await db.scrap_entries.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/scrap-entries")
async def create_scrap(payload: ScrapEntryIn, request: Request,
                        user: dict = Depends(require_permission("inventory", "write"))):
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0")
    if not payload.reason:
        raise HTTPException(status_code=400, detail="reason is mandatory")
    item = await db.inventory.find_one({"id": payload.item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    no = f"SCR-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(await db.scrap_entries.count_documents({})).zfill(5)}"
    doc = {
        "id": new_id(),
        "scrap_no": no,
        **payload.model_dump(),
        "item_code": item.get("code"),
        "item_name": item.get("name"),
        "unit": item.get("unit"),
        "rate": float(item.get("rate") or 0),
        "value": round(payload.quantity * float(item.get("rate") or 0), 2),
        "status": "submitted",
        "reported_by_id": user["id"],
        "created_at": now_iso(),
    }
    await db.scrap_entries.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="scrap_entries", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.post("/scrap-entries/{scrap_id}/approve")
async def approve_scrap(scrap_id: str, request: Request,
                         user: dict = Depends(require_permission("inventory", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager", "store_incharge", "finance_head"}:
        raise HTTPException(status_code=403, detail="Insufficient role to approve scrap")
    sc = await db.scrap_entries.find_one({"id": scrap_id}, {"_id": 0})
    if not sc:
        raise HTTPException(status_code=404, detail="Scrap entry not found")
    if sc.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"Cannot approve — status {sc.get('status')}")
    if sc.get("reported_by_id") == user["id"] and user.get("role") not in {"super_admin", "director"}:
        raise HTTPException(status_code=403, detail="Cannot approve your own scrap entry")
    qty = float(sc["quantity"])
    # Move stock to scrap (debit normal inventory + increment scrap_qty field)
    await db.inventory.update_one({"id": sc["item_id"]},
                                     {"$inc": {"quantity": -qty, "scrap_qty": qty}})
    await db.inventory_transactions.insert_one({
        "id": new_id(), "txn_type": "scrap",
        "item_id": sc["item_id"], "item_name": sc["item_name"],
        "quantity": qty, "delta": -qty, "unit": sc.get("unit"),
        "rate": sc.get("rate"), "project_code": sc.get("project_code"),
        "ref_type": "scrap_entry", "ref_id": scrap_id, "ref_no": sc["scrap_no"],
        "note": f"Scrap · {sc['reason']}",
        "status": "posted", "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    })
    await db.scrap_entries.update_one({"id": scrap_id}, {"$set": {
        "status": "approved", "approved_by_id": user["id"],
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
    }})
    return await db.scrap_entries.find_one({"id": scrap_id}, {"_id": 0})


class ScrapSaleIn(BaseModel):
    scrap_entry_ids: List[str]
    buyer_name: str
    sale_rate: float
    quantity: float
    gst_applicable: bool = True
    gst_rate: float = 18.0
    payment_status: str = "pending"
    attachment_url: Optional[str] = None
    remarks: Optional[str] = None


@router.get("/scrap-sales")
async def list_scrap_sales(user: dict = Depends(require_permission("inventory", "read"))):
    return await db.scrap_sale_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/scrap-sales")
async def create_scrap_sale(payload: ScrapSaleIn, request: Request,
                              user: dict = Depends(require_permission("inventory", "write"))):
    if payload.quantity <= 0 or payload.sale_rate < 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0 and rate must be >= 0")
    if not payload.scrap_entry_ids:
        raise HTTPException(status_code=400, detail="Pick at least one approved scrap entry")
    # Verify all scrap entries are approved
    entries = await db.scrap_entries.find({"id": {"$in": payload.scrap_entry_ids}}, {"_id": 0}).to_list(500)
    if len(entries) != len(payload.scrap_entry_ids):
        raise HTTPException(status_code=404, detail="One or more scrap entries not found")
    for e in entries:
        if e.get("status") != "approved":
            raise HTTPException(status_code=400, detail=f"Scrap entry {e.get('scrap_no')} is not approved")
    no = f"SCS-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(await db.scrap_sale_requests.count_documents({})).zfill(5)}"
    taxable = round(payload.quantity * payload.sale_rate, 2)
    gst = round(taxable * payload.gst_rate / 100, 2) if payload.gst_applicable else 0
    doc = {
        "id": new_id(),
        "sale_no": no,
        **payload.model_dump(),
        "taxable_value": taxable,
        "gst_amount": gst,
        "total_value": taxable + gst,
        "status": "submitted",
        "raised_by_id": user["id"],
        "raised_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.scrap_sale_requests.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="scrap_sale_requests", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.post("/scrap-sales/{sale_id}/approve")
async def approve_scrap_sale(sale_id: str, request: Request,
                              user: dict = Depends(require_permission("inventory", "write"))):
    if user.get("role") not in {"super_admin", "director", "general_manager", "finance_head", "accounts_executive"}:
        raise HTTPException(status_code=403, detail="Insufficient role to approve scrap sale")
    s = await db.scrap_sale_requests.find_one({"id": sale_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Scrap sale not found")
    if s.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"Cannot approve — status {s.get('status')}")
    # Reduce scrap stock for each linked scrap entry proportionally
    # Simple approach: deduct from the FIRST entry until quantity satisfied
    remaining = float(s["quantity"])
    for sid in s["scrap_entry_ids"]:
        if remaining <= 0:
            break
        e = await db.scrap_entries.find_one({"id": sid}, {"_id": 0})
        if not e:
            continue
        take = min(remaining, float(e.get("quantity") or 0))
        if take > 0:
            await db.inventory.update_one({"id": e["item_id"]},
                                            {"$inc": {"scrap_qty": -take}})
            remaining -= take
    await db.scrap_sale_requests.update_one({"id": sale_id}, {"$set": {
        "status": "approved", "approved_by_id": user["id"],
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
    }})
    # Notify Accounts — best-effort
    try:
        from accounting_service import post_scrap_sale_income
        await post_scrap_sale_income({
            "id": sale_id, "buyer_name": s["buyer_name"],
            "taxable_value": s["taxable_value"], "gst_amount": s["gst_amount"],
            "total_value": s["total_value"], "sale_no": s["sale_no"],
        }, user)
    except Exception:
        pass
    return await db.scrap_sale_requests.find_one({"id": sale_id}, {"_id": 0})


# ─────────────────────────────────────────────────────────────────────
# 5. Employee Inventory Clearance
# ─────────────────────────────────────────────────────────────────────
@router.get("/employee-clearance/{employee_id}")
async def employee_clearance(employee_id: str,
                             user: dict = Depends(require_permission("material_allocations", "read"))):
    """One-shot view of everything an employee still owes the Store before exit clearance.
    Aggregates: tools, PPE, assets, materials issued, pending recovery."""
    pending_allocs = await db.material_allocations.find(
        {"employee_id": employee_id, "status": {"$in": ["issued", "partially_returned"]}},
        {"_id": 0},
    ).to_list(2000)
    by_kind: dict = {"tool": [], "asset": [], "material": [], "consumable": []}
    total_out_value = 0.0
    for a in pending_allocs:
        kind = a.get("kind") or "material"
        out_qty = float(a.get("quantity") or 0) - float(a.get("returned_qty") or 0)
        if out_qty <= 0:
            continue
        rate = float(a.get("rate") or 0)
        val = out_qty * rate
        total_out_value += val
        by_kind.setdefault(kind, []).append({
            "allocation_no": a.get("allocation_no"),
            "item_name": a.get("item_name"),
            "outstanding_qty": out_qty,
            "rate": rate,
            "value": round(val, 2),
            "issue_date": a.get("issue_date"),
            "returnable": a.get("returnable"),
            "expected_return_date": a.get("expected_return_date"),
        })

    pending_ppe = await db.ppe_issuance.find(
        {"employee_id": employee_id, "issue_type": "returnable", "status": "issued"},
        {"_id": 0},
    ).to_list(500)
    ppe_value = sum(float(p.get("value") or 0) for p in pending_ppe)

    recoveries = await db.recoveries.find(
        {"employee_id": employee_id, "status": "pending"}, {"_id": 0},
    ).to_list(500)
    recovery_amount = sum(float(r.get("amount") or 0) for r in recoveries)

    total_blockers = sum(len(v) for v in by_kind.values()) + len(pending_ppe) + len(recoveries)
    can_clear = total_blockers == 0
    return {
        "employee_id": employee_id,
        "can_clear": can_clear,
        "total_blockers": total_blockers,
        "outstanding_value": round(total_out_value + ppe_value + recovery_amount, 2),
        "pending_by_kind": by_kind,
        "pending_ppe": pending_ppe,
        "ppe_value": round(ppe_value, 2),
        "pending_recoveries": recoveries,
        "recovery_amount": round(recovery_amount, 2),
        "as_of": now_iso(),
    }


# ─────────────────────────────────────────────────────────────────────
# 6. Recovery Register
# ─────────────────────────────────────────────────────────────────────
@router.get("/recoveries")
async def list_recoveries(status: Optional[str] = None, employee_id: Optional[str] = None,
                          user: dict = Depends(require_permission("inventory", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    rows = await db.recoveries.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    total = sum(float(r.get("amount") or 0) for r in rows if r.get("status") == "pending")
    return {"count": len(rows), "total_pending": round(total, 2), "rows": rows}


class RecoveryActionIn(BaseModel):
    note: Optional[str] = None
    reason: Optional[str] = None


@router.post("/recoveries/{rec_id}/mark-recovered")
async def mark_recovered(rec_id: str, payload: RecoveryActionIn, request: Request,
                          user: dict = Depends(require_permission("inventory", "write"))):
    r = await db.recoveries.find_one({"id": rec_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Recovery not found")
    if r.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Status is {r.get('status')}")
    await db.recoveries.update_one({"id": rec_id}, {"$set": {
        "status": "recovered", "recovered_at": now_iso(),
        "recovered_by_id": user["id"], "recovery_note": payload.note,
    }})
    row = await db.recoveries.find_one({"id": rec_id}, {"_id": 0})
    await audit(user=user, action="mark_recovered", resource="recoveries", record_id=rec_id, after=row, ip=_ip(request))
    return row


@router.post("/recoveries/{rec_id}/waive")
async def waive_recovery(rec_id: str, payload: RecoveryActionIn, request: Request,
                          user: dict = Depends(require_permission("inventory", "write"))):
    """Waiving requires elevated role (Finance Head / Director)."""
    if user.get("role") not in {"super_admin", "director", "finance_head", "general_manager"}:
        raise HTTPException(status_code=403, detail="Recovery waiver requires Finance Head / Director / GM approval")
    r = await db.recoveries.find_one({"id": rec_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Recovery not found")
    if r.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Status is {r.get('status')}")
    if not payload.reason:
        raise HTTPException(status_code=400, detail="Waiver reason is mandatory")
    await db.recoveries.update_one({"id": rec_id}, {"$set": {
        "status": "waived", "waived_at": now_iso(),
        "waived_by_id": user["id"], "waiver_reason": payload.reason,
    }})
    row = await db.recoveries.find_one({"id": rec_id}, {"_id": 0})
    await audit(user=user, action="waive", resource="recoveries", record_id=rec_id, after=row, ip=_ip(request))
    return row


# ─────────────────────────────────────────────────────────────────────
# 7. Transit Exception Register
# ─────────────────────────────────────────────────────────────────────
@router.get("/transit-exceptions")
async def transit_exceptions(user: dict = Depends(require_permission("inventory", "read"))):
    """Material transfers received with shortage / damage. Surfaces the exceptions
    captured by Phase 3 `material_transfers.status=received_with_exception`."""
    rows = await db.material_transfers.find(
        {"status": "received_with_exception"}, {"_id": 0},
    ).sort("received_at", -1).to_list(1000)
    enriched = []
    total_shortage_value = 0.0
    total_damaged_value = 0.0
    for t in rows:
        shortage_value = 0.0
        damaged_value = 0.0
        for ln in t.get("lines") or []:
            rate = float(ln.get("rate") or 0)
            shortage_value += float(ln.get("shortage_qty") or 0) * rate
            damaged_value += float(ln.get("damaged_qty") or 0) * rate
        total_shortage_value += shortage_value
        total_damaged_value += damaged_value
        enriched.append({
            **t,
            "shortage_value": round(shortage_value, 2),
            "damaged_value": round(damaged_value, 2),
            "exception_value": round(shortage_value + damaged_value, 2),
        })
    return {"count": len(enriched), "total_shortage_value": round(total_shortage_value, 2),
            "total_damaged_value": round(total_damaged_value, 2), "rows": enriched}


# ─────────────────────────────────────────────────────────────────────
# 8. Tool Issue/Return Registers (filtered views on material_allocations)
# ─────────────────────────────────────────────────────────────────────
@router.get("/tool-issue-register")
async def tool_issue_register(employee_id: Optional[str] = None,
                              project_code: Optional[str] = None,
                              status: Optional[str] = None,
                              user: dict = Depends(require_permission("material_allocations", "read"))):
    """Read-only view of `material_allocations` where kind in (tool, asset)."""
    q: dict = {"kind": {"$in": ["tool", "asset"]}}
    if employee_id:
        q["employee_id"] = employee_id
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    rows = await db.material_allocations.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    pending = sum(1 for r in rows if r.get("status") in ("issued", "partially_returned"))
    total_value = sum(
        (float(r.get("quantity") or 0) - float(r.get("returned_qty") or 0)) * float(r.get("rate") or 0)
        for r in rows if r.get("status") in ("issued", "partially_returned")
    )
    return {"count": len(rows), "pending_count": pending,
            "pending_value": round(total_value, 2), "rows": rows}


@router.get("/employee-pending-tools/{employee_id}")
async def employee_pending_tools(employee_id: str,
                                  user: dict = Depends(require_permission("material_allocations", "read"))):
    """Tools (and assets) issued to the employee that are still out."""
    rows = await db.material_allocations.find({
        "employee_id": employee_id, "kind": {"$in": ["tool", "asset"]},
        "status": {"$in": ["issued", "partially_returned"]},
    }, {"_id": 0}).to_list(500)
    enriched = []
    total = 0.0
    for r in rows:
        out = float(r.get("quantity") or 0) - float(r.get("returned_qty") or 0)
        if out <= 0:
            continue
        val = out * float(r.get("rate") or 0)
        total += val
        enriched.append({**r, "outstanding_qty": out, "outstanding_value": round(val, 2)})
    return {"employee_id": employee_id, "count": len(enriched),
            "total_value": round(total, 2), "rows": enriched}
