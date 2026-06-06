"""Procurement cycle backbone — Phase A.

Flow:  PR (Purchase Requisition) → RFQ → PO → GRN.

Each step is auto-numbered (`PR-YYYY-####`, `RFQ-YYYY-####`, `GRN-YYYY-####`)
and gated by its own approval chain (`purchase_requisition`, `rfq`, `grn`)
defined in `approval_engine.APPROVAL_CHAINS`.

Side-effects:
  * Approving the final step of a PR sets `pr.status = 'approved'` (frontend
    then offers an "Initiate RFQ" action).
  * Converting an RFQ → PO sets `rfq.status = 'converted_to_po'` and stamps
    `pr.status = 'po_generated'`.
  * Approving the final step of a GRN debits `inventory.quantity` (inward).
"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id, logger
from audit import audit
from sequences import next_sequence, stamp_dept_doc
from approval_engine import build_chain, insert_approval, copy_approval_doc_fields

router = APIRouter(tags=["procurement"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Purchase Requisitions
# ──────────────────────────────────────────────────────────────────────────────
PR_STATUSES = ("draft", "pending_approval", "approved", "rejected",
               "pending_revision",
               "rfq_initiated", "po_generated", "partially_fulfilled", "closed")


class PRItem(BaseModel):
    category: Optional[str] = None
    category_id: Optional[str] = None
    name: str
    item_id: Optional[str] = None
    item_code: Optional[str] = None
    description: Optional[str] = None
    quantity: float
    unit: str = "Nos"
    required_date: Optional[str] = None
    technical_specs: Optional[str] = None
    vendor_suggestion: Optional[str] = None
    cost_center_id: Optional[str] = None
    cost_center_code: Optional[str] = None


class PRIn(BaseModel):
    department: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_id: Optional[str] = None
    site_code: Optional[str] = None
    pr_date: Optional[str] = None
    priority: str = "medium"            # high | medium | low
    budget_reference: Optional[str] = None
    remarks: Optional[str] = None
    items: List[PRItem]
    submit_for_approval: bool = False    # if true, status -> pending_approval


@router.get("/procurement/prs")
async def list_prs(status: Optional[str] = None,
                   user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    rows = await db.purchase_requisitions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/procurement/prs/{pr_id}")
async def get_pr(pr_id: str, user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    row = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="PR not found")
    return row


@router.post("/procurement/prs")
async def create_pr(payload: PRIn, request: Request,
                    user: dict = Depends(require_permission("purchase_requisitions", "write"))):
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one item is required")
    if payload.priority not in ("high", "medium", "low"):
        raise HTTPException(status_code=400, detail="priority must be high|medium|low")
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["pr_number"] = await next_sequence("PR")
    await stamp_dept_doc(doc, "purchase_requisition")
    doc["pr_date"] = doc.get("pr_date") or now_iso()[:10]
    doc["requested_by"] = user.get("name") or user.get("email")
    doc["requested_by_id"] = user["id"]
    doc["status"] = "pending_approval" if payload.submit_for_approval else "draft"
    doc["created_at"] = now_iso()

    # Auto-resolve cost_center for each line item from (project_id, category_id)
    if payload.project_id:
        try:
            cc_rows = await db.cost_centers.find(
                {"project_id": payload.project_id, "active": {"$ne": False}}, {"_id": 0}
            ).to_list(500)
            by_cat = {c.get("category_id"): c for c in cc_rows}
            for item in doc.get("items") or []:
                cat_id = item.get("category_id")
                if cat_id and cat_id in by_cat and not item.get("cost_center_id"):
                    item["cost_center_id"] = by_cat[cat_id]["id"]
                    item["cost_center_code"] = by_cat[cat_id]["code"]
        except Exception:
            pass

    # Auto-create approval chain when submitted
    if doc["status"] == "pending_approval":
        chain = await build_chain("purchase_requisition")
        approval = {
            "id": new_id(),
            "type": "purchase_requisition",
            "module": "procurement",
            "record_id": doc["id"],
            "title": f"PR {doc['pr_number']} · {payload.department or 'General'}",
            "summary": f"{len(payload.items)} item(s) · {payload.priority} priority",
            "requested_by": doc["requested_by"],
            "requested_by_id": doc["requested_by_id"],
            "status": "pending",
            "current_step": 0,
            "chain": chain,
            "history": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        copy_approval_doc_fields(approval, payload)
        await insert_approval(approval)
        doc["approval_id"] = approval["id"]

    await db.purchase_requisitions.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="purchase_requisitions", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/procurement/prs/{pr_id}")
async def update_pr(pr_id: str, payload: dict, request: Request,
                    user: dict = Depends(require_permission("purchase_requisitions", "write"))):
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    if pr.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail=f"PR in '{pr.get('status')}' cannot be edited")
    payload.pop("id", None)
    payload.pop("pr_number", None)
    payload.pop("status", None)
    payload["updated_at"] = now_iso()
    await db.purchase_requisitions.update_one({"id": pr_id}, {"$set": payload})
    row = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    await audit(user=user, action="update", resource="purchase_requisitions", record_id=pr_id, after=row, ip=_ip(request))
    return row


@router.post("/procurement/prs/{pr_id}/submit")
async def submit_pr(pr_id: str, request: Request, body: Optional[dict] = None,
                    user: dict = Depends(require_permission("purchase_requisitions", "write"))):
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    if pr.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Only draft / rejected PRs can be submitted")
    # Mark any prior rejected approval for this PR as superseded so the
    # approvals inbox stays clean.
    await db.approvals.update_many(
        {"type": "purchase_requisition", "record_id": pr_id, "status": "rejected"},
        {"$set": {"superseded": True, "superseded_at": now_iso()}},
    )
    chain = await build_chain("purchase_requisition")
    approval = {
        "id": new_id(),
        "type": "purchase_requisition",
        "module": "procurement",
        "record_id": pr_id,
        "title": f"PR {pr['pr_number']} · {pr.get('department') or 'General'}",
        "summary": f"{len(pr.get('items') or [])} item(s) · {pr.get('priority', 'medium')} priority",
        "requested_by": pr.get("requested_by"),
        "requested_by_id": pr.get("requested_by_id"),
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    copy_approval_doc_fields(approval, body)
    await insert_approval(approval)
    await db.purchase_requisitions.update_one(
        {"id": pr_id},
        {"$set": {"status": "pending_approval", "approval_id": approval["id"], "reject_reason": None, "updated_at": now_iso()}},
    )
    return {"pr_id": pr_id, "approval_id": approval["id"]}


@router.delete("/procurement/prs/{pr_id}")
async def delete_pr(pr_id: str, request: Request,
                    user: dict = Depends(require_permission("purchase_requisitions", "delete"))):
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    if pr.get("status") in ("approved", "rfq_initiated", "po_generated"):
        raise HTTPException(status_code=400, detail="Cannot delete a PR that has moved past approval")
    await db.purchase_requisitions.delete_one({"id": pr_id})
    await audit(user=user, action="delete", resource="purchase_requisitions", record_id=pr_id, before=pr, ip=_ip(request))
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# RFQs
# ──────────────────────────────────────────────────────────────────────────────
class RFQVendorIn(BaseModel):
    vendor_id: str
    vendor_name: Optional[str] = None


class RFQIn(BaseModel):
    pr_id: str
    vendors: List[RFQVendorIn]
    notes: Optional[str] = None
    response_due_date: Optional[str] = None


class RFQResponse(BaseModel):
    vendor_id: str
    rate_quoted: Optional[float] = None       # Legacy single-rate fallback applied across all items
    item_rates: Optional[Dict[str, float]] = None   # Per-item rates keyed by stringified po_item_index
    delivery_days: Optional[int] = None
    payment_terms: Optional[str] = None
    technical_score: Optional[float] = None     # 0-100
    note: Optional[str] = None


@router.get("/procurement/rfqs")
async def list_rfqs(user: dict = Depends(require_permission("rfqs", "read"))):
    rows = await db.rfqs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/procurement/rfqs/{rfq_id}")
async def get_rfq(rfq_id: str, user: dict = Depends(require_permission("rfqs", "read"))):
    row = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return row


@router.post("/procurement/rfqs")
async def create_rfq(payload: RFQIn, request: Request,
                     user: dict = Depends(require_permission("rfqs", "write"))):
    pr = await db.purchase_requisitions.find_one({"id": payload.pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    if pr.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Only approved PRs can be turned into an RFQ")
    if not payload.vendors:
        raise HTTPException(status_code=400, detail="Pick at least one vendor")

    vendor_rows: List[Dict[str, Any]] = []
    for v in payload.vendors:
        vendor = await db.vendors.find_one({"id": v.vendor_id}, {"_id": 0})
        if not vendor:
            raise HTTPException(status_code=404, detail=f"Vendor {v.vendor_id} not found")
        vendor_rows.append({
            "vendor_id": v.vendor_id,
            "vendor_name": v.vendor_name or vendor.get("name"),
            "status": "sent",
            "rate_quoted": None,
            "delivery_days": None,
            "payment_terms": None,
            "technical_score": None,
            "response_at": None,
            "note": None,
        })
    doc = {
        "id": new_id(),
        "rfq_number": await next_sequence("RFQ"),
        "pr_id": payload.pr_id,
        "pr_number": pr.get("pr_number"),
        "items": pr.get("items") or [],
        "vendors": vendor_rows,
        "status": "response_pending",
        "notes": payload.notes,
        "response_due_date": payload.response_due_date,
        "selected_vendor_id": None,
        "created_by": user["id"],
        "created_at": now_iso(),
    }
    await stamp_dept_doc(doc, "rfq")
    await db.rfqs.insert_one(doc)
    doc.pop("_id", None)
    await db.purchase_requisitions.update_one({"id": payload.pr_id}, {"$set": {"status": "rfq_initiated", "rfq_id": doc["id"], "rfq_number": doc["rfq_number"]}})
    await audit(user=user, action="create", resource="rfqs", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.post("/procurement/rfqs/{rfq_id}/respond")
async def record_rfq_response(rfq_id: str, payload: RFQResponse, request: Request,
                              user: dict = Depends(require_permission("rfqs", "write"))):
    rfq = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if payload.rate_quoted is None and not payload.item_rates:
        raise HTTPException(status_code=400, detail="Provide either rate_quoted or item_rates")
    # Sanitise item_rates: keys stringified, non-negative floats
    item_rates_clean: Dict[str, float] = {}
    if payload.item_rates:
        for k, v in payload.item_rates.items():
            if v is None or v == "":
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"item_rates[{k}] must be numeric")
            if fv < 0:
                raise HTTPException(status_code=400, detail=f"item_rates[{k}] must be >= 0")
            item_rates_clean[str(k)] = fv
    vendors = list(rfq.get("vendors") or [])
    found = False
    for v in vendors:
        if v["vendor_id"] == payload.vendor_id:
            v.update({
                "rate_quoted": payload.rate_quoted,
                "item_rates": item_rates_clean or None,
                "delivery_days": payload.delivery_days,
                "payment_terms": payload.payment_terms,
                "technical_score": payload.technical_score,
                "note": payload.note,
                "status": "responded",
                "response_at": now_iso(),
            })
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Vendor not part of this RFQ")
    next_status = "under_evaluation" if any(v.get("status") == "responded" for v in vendors) else "response_pending"
    await db.rfqs.update_one({"id": rfq_id}, {"$set": {"vendors": vendors, "status": next_status, "updated_at": now_iso()}})
    return {"rfq_id": rfq_id, "status": next_status}


@router.get("/procurement/rfqs/{rfq_id}/comparative")
async def comparative_statement(rfq_id: str, user: dict = Depends(require_permission("rfqs", "read"))):
    rfq = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    vendors = rfq.get("vendors") or []
    items = rfq.get("items") or []
    total_qty = sum(float(i.get("quantity") or 0) for i in items)
    units = {str(i.get("unit") or "Nos") for i in items}
    heterogeneous = len(units) > 1

    rows = []
    for v in vendors:
        rate = v.get("rate_quoted")
        item_rates = v.get("item_rates") or {}
        item_breakdown = []
        line_total = 0.0
        any_priced = False
        for idx, it in enumerate(items):
            qty = float(it.get("quantity") or 0)
            ir = item_rates.get(str(idx))
            r = float(ir) if ir is not None else (float(rate) if rate is not None else None)
            if r is None:
                item_breakdown.append({
                    "index": idx, "name": it.get("name"), "unit": it.get("unit"),
                    "quantity": qty, "rate": None, "value": None, "source": "missing",
                })
                continue
            any_priced = True
            value = r * qty
            line_total += value
            item_breakdown.append({
                "index": idx, "name": it.get("name"), "unit": it.get("unit"),
                "quantity": qty, "rate": r, "value": value,
                "source": "item_rate" if ir is not None else "fallback_rate",
            })
        landed = line_total if any_priced else None
        rows.append({
            "vendor_id": v["vendor_id"],
            "vendor_name": v.get("vendor_name"),
            "rate_quoted": rate,
            "item_rates": item_rates or None,
            "item_breakdown": item_breakdown,
            "delivery_days": v.get("delivery_days"),
            "payment_terms": v.get("payment_terms"),
            "technical_score": v.get("technical_score"),
            "landed_value": landed,
            "status": v.get("status"),
            "is_selected": v["vendor_id"] == rfq.get("selected_vendor_id"),
        })
    rows.sort(key=lambda r: (r["landed_value"] is None, r["landed_value"] or 0))
    # Iter 54 · Phase 2 — assign L1/L2/L3 rank badges (lowest landed = L1).
    rank_count = 0
    for r in rows:
        if r["landed_value"] is None:
            r["rank"] = None
            r["rank_label"] = None
        else:
            rank_count += 1
            r["rank"] = rank_count
            r["rank_label"] = f"L{rank_count}" if rank_count <= 3 else f"L{rank_count}"
    l1 = next((r for r in rows if r.get("rank") == 1), None)
    if l1:
        # Compute savings vs L1 for non-L1 rows so the UI can show "+₹2,300 above L1".
        l1_value = l1["landed_value"]
        for r in rows:
            if r["landed_value"] is not None and r["rank"] != 1:
                r["delta_vs_l1"] = round(r["landed_value"] - l1_value, 2)
                r["delta_pct_vs_l1"] = round((r["landed_value"] - l1_value) / l1_value * 100, 2) if l1_value else 0
    return {
        "rfq_id": rfq_id,
        "items": items,
        "rows": rows,
        "total_qty": total_qty,
        "heterogeneous_uom": heterogeneous,
        "units": sorted(units),
        "l1_vendor_id": l1["vendor_id"] if l1 else None,
        "l1_landed_value": l1["landed_value"] if l1 else None,
    }


@router.post("/procurement/rfqs/{rfq_id}/select-vendor")
async def select_rfq_vendor(rfq_id: str, payload: dict, request: Request,
                            user: dict = Depends(require_permission("rfqs", "write"))):
    vendor_id = payload.get("vendor_id")
    justification = (payload.get("justification") or "").strip()
    if not vendor_id:
        raise HTTPException(status_code=400, detail="vendor_id required")
    rfq = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if not any(v["vendor_id"] == vendor_id for v in rfq.get("vendors") or []):
        raise HTTPException(status_code=400, detail="Vendor not part of this RFQ")

    # Iter 54 · Phase 2 — when the selected vendor is not the lowest landed price
    # (L1), require a written justification + log approver. The Comparative
    # Statement endpoint marks the cheapest vendor as L1; anything else needs
    # a 20-char explanation, recorded on the RFQ for audit.
    comp = await comparative_statement(rfq_id, user)
    l1_id = comp.get("l1_vendor_id")
    is_non_l1 = l1_id is not None and l1_id != vendor_id
    if is_non_l1 and len(justification) < 20:
        raise HTTPException(
            status_code=400,
            detail="Selected vendor is not L1 (lowest landed cost). "
                   "A justification of at least 20 characters is required.",
        )

    set_doc = {
        "selected_vendor_id": vendor_id,
        "status": "vendor_selected",
        "updated_at": now_iso(),
    }
    if is_non_l1:
        set_doc["non_l1_selection"] = True
        set_doc["non_l1_justification"] = justification
        set_doc["non_l1_approved_by"] = user.get("name") or user.get("email")
        set_doc["non_l1_approved_at"] = now_iso()
        set_doc["l1_vendor_id_at_select"] = l1_id
    await db.rfqs.update_one({"id": rfq_id}, {"$set": set_doc})
    return {"rfq_id": rfq_id, "selected_vendor_id": vendor_id,
            "non_l1_selection": is_non_l1}


@router.post("/procurement/rfqs/{rfq_id}/convert-to-po")
async def convert_rfq_to_po(rfq_id: str, request: Request,
                            user: dict = Depends(require_permission("rfqs", "write"))):
    rfq = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if not rfq.get("selected_vendor_id"):
        raise HTTPException(status_code=400, detail="Select a vendor before converting to PO")
    vendor_row = next(v for v in rfq["vendors"] if v["vendor_id"] == rfq["selected_vendor_id"])
    vendor = await db.vendors.find_one({"id": rfq["selected_vendor_id"]}, {"_id": 0})
    pr = await db.purchase_requisitions.find_one({"id": rfq["pr_id"]}, {"_id": 0}) or {}

    item_rates = vendor_row.get("item_rates") or {}
    fallback_rate = vendor_row.get("rate_quoted")
    po_items: List[Dict[str, Any]] = []
    amount = 0.0
    for idx, it in enumerate(rfq.get("items") or []):
        qty = float(it.get("quantity") or 0)
        ir = item_rates.get(str(idx))
        r = float(ir) if ir is not None else (float(fallback_rate) if fallback_rate is not None else 0.0)
        line_value = r * qty
        amount += line_value
        po_items.append({**it, "rate": r, "line_value": line_value})

    po = {
        "id": new_id(),
        "po_number": await next_sequence("PO"),
        "vendor_id": rfq["selected_vendor_id"],
        "vendor": (vendor or {}).get("name") or vendor_row.get("vendor_name"),
        "rfq_id": rfq_id,
        "rfq_number": rfq.get("rfq_number"),
        "pr_id": rfq.get("pr_id"),
        "pr_number": rfq.get("pr_number"),
        "items": po_items,
        "rate": fallback_rate,
        "item_rates": item_rates or None,
        "delivery_days": vendor_row.get("delivery_days"),
        "payment_terms": vendor_row.get("payment_terms"),
        "amount": amount,
        "status": "approved",     # already vetted via PR + RFQ
        "project": pr.get("project_code"),
        "site": pr.get("site_code"),
        "department": pr.get("department"),
        "created_by": user["id"],
        "created_at": now_iso(),
        "source": "rfq_conversion",
    }
    await stamp_dept_doc(po, "purchase_order")
    await db.purchase_orders.insert_one(po)
    po.pop("_id", None)
    await db.rfqs.update_one({"id": rfq_id}, {"$set": {"status": "converted_to_po", "po_id": po["id"], "po_number": po["po_number"], "updated_at": now_iso()}})
    await db.purchase_requisitions.update_one({"id": rfq["pr_id"]}, {"$set": {"status": "po_generated", "po_id": po["id"], "po_number": po["po_number"], "updated_at": now_iso()}})
    await audit(user=user, action="create", resource="purchase_orders", record_id=po["id"], after=po, ip=_ip(request))
    return po


# ──────────────────────────────────────────────────────────────────────────────
# GRN — Goods Receipt Note
# ──────────────────────────────────────────────────────────────────────────────
class GRNItemIn(BaseModel):
    po_item_index: int
    item_id: Optional[str] = None
    item_name: str
    ordered_qty: float
    received_qty: float
    accepted_qty: float
    rejected_qty: float = 0
    unit: str = "Nos"
    inspection_status: str = "approved"   # approved | rejected | partial_accepted
    damage_notes: Optional[str] = None
    batch: Optional[str] = None


class GRNIn(BaseModel):
    po_id: str
    store_location: Optional[str] = None
    site_id: Optional[str] = None
    received_at: Optional[str] = None
    items: List[GRNItemIn]
    remarks: Optional[str] = None


@router.get("/procurement/grns")
async def list_grns(user: dict = Depends(require_permission("grn", "read"))):
    rows = await db.grn.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/procurement/grns/{grn_id}")
async def get_grn(grn_id: str, user: dict = Depends(require_permission("grn", "read"))):
    row = await db.grn.find_one({"id": grn_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="GRN not found")
    return row


@router.post("/procurement/grns")
async def create_grn(payload: GRNIn, request: Request,
                     user: dict = Depends(require_permission("grn", "write"))):
    po = await db.purchase_orders.find_one({"id": payload.po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.get("status") not in (None, "approved", "sent_to_vendor", "partially_received"):
        raise HTTPException(status_code=400, detail=f"PO in '{po.get('status')}' cannot receive material")

    # Over-receipt guard — cumulative accepted across all GRNs for this PO must
    # never exceed the ordered quantity per line.
    prev_grns = await db.grn.find({"po_id": payload.po_id}, {"_id": 0, "items": 1}).to_list(500)
    cum_by_idx: Dict[int, float] = {}
    for g in prev_grns:
        for it in g.get("items") or []:
            cum_by_idx[int(it.get("po_item_index") or 0)] = cum_by_idx.get(int(it.get("po_item_index") or 0), 0.0) + float(it.get("accepted_qty") or 0)
    po_items = po.get("items") or []
    for it in payload.items:
        idx = int(it.po_item_index)
        ordered = float((po_items[idx] if idx < len(po_items) else {}).get("quantity") or 0)
        if ordered > 0 and (cum_by_idx.get(idx, 0.0) + float(it.accepted_qty or 0)) > ordered + 1e-6:
            raise HTTPException(status_code=400,
                                detail=f"Line {idx + 1} over-receipt: accepted ({cum_by_idx.get(idx, 0.0) + float(it.accepted_qty or 0):g}) exceeds ordered ({ordered:g})")

    total_recv = sum(i.accepted_qty for i in payload.items)
    total_rej = sum(i.rejected_qty for i in payload.items)
    any_rejected = any(i.inspection_status == "rejected" for i in payload.items)
    any_partial = any(i.inspection_status == "partial_accepted" for i in payload.items)
    grn_status = "rejected" if any_rejected and total_recv == 0 else ("partial_accepted" if any_partial or any_rejected else "approved")

    doc = {
        "id": new_id(),
        "grn_number": await next_sequence("GRN"),
        "po_id": payload.po_id,
        "po_number": po.get("po_number"),
        "vendor_id": po.get("vendor_id"),
        "vendor_name": po.get("vendor"),
        "items": [i.model_dump() for i in payload.items],
        "store_location": payload.store_location,
        "site_id": payload.site_id,
        "received_at": payload.received_at or now_iso()[:10],
        "received_by": user.get("name") or user.get("email"),
        "received_by_id": user["id"],
        "remarks": payload.remarks,
        "total_accepted": total_recv,
        "total_rejected": total_rej,
        "inspection_status": grn_status,
        "status": grn_status,
        "created_at": now_iso(),
    }
    await stamp_dept_doc(doc, "grn")
    await db.grn.insert_one(doc)
    doc.pop("_id", None)

    # Inward each accepted line into inventory.
    #
    # Iter 55 fix — earlier this loop silently skipped any line whose `item_id`
    # was null, which is the normal case for POs created from free-text RFQs
    # (item carries only a `name` + `unit`). Result: "material not moving to
    # inventory after GRN". We now AUTO-MATCH by name (case-insensitive) and
    # AUTO-CREATE an inventory row when no match exists, so every accepted
    # line ends up in stock.
    for it in payload.items:
        if it.accepted_qty <= 0:
            continue
        item_id = it.item_id
        if not item_id and it.item_name:
            existing = await db.inventory.find_one(
                {"name": {"$regex": f"^{it.item_name.strip()}$", "$options": "i"}},
                {"_id": 0, "id": 1},
            )
            if existing:
                item_id = existing["id"]
            else:
                # Auto-create with zero opening qty — the $inc below adds the
                # accepted quantity. UOM falls back to "Nos" if blank.
                item_id = new_id()
                await db.inventory.insert_one({
                    "id": item_id,
                    "code": f"AUTO-{item_id[:6].upper()}",
                    "name": it.item_name.strip(),
                    "uom": it.unit or "Nos",
                    "unit": it.unit or "Nos",
                    "quantity": 0,
                    "category": "auto-grn",
                    "rate": 0,
                    "min_stock": 0,
                    "ownership_department": "store",
                    "created_at": now_iso(),
                    "created_by": user["id"],
                    "auto_created_from_grn": doc["id"],
                })
        if not item_id:
            continue
        await db.inventory.update_one({"id": item_id}, {"$inc": {"quantity": it.accepted_qty},
                                                          "$set": {"updated_at": now_iso()}})
        await db.inventory_transactions.insert_one({
            "id": new_id(),
            "txn_type": "inward",
            "item_id": item_id,
            "item_name": it.item_name,
            "quantity": it.accepted_qty,
            "delta": it.accepted_qty,
            "unit": it.unit,
            "received_from": po.get("vendor"),
            "note": f"GRN {doc['grn_number']} · PO {po.get('po_number')}",
            "ref_no": doc["grn_number"],
            "batch": it.batch,
            "ref_type": "grn",
            "ref_id": doc["id"],
            "status": "posted",
            "store_location": payload.store_location,
            "created_by": user["id"],
            "created_by_name": user.get("name") or user.get("email"),
            "created_at": now_iso(),
        })
        # Also write the resolved item_id back onto the GRN line so a later
        # delete / inspection knows which inventory row to undo.
        for grn_line in doc["items"]:
            if (grn_line.get("po_item_index") == it.po_item_index
                and grn_line.get("item_name") == it.item_name
                and not grn_line.get("item_id")):
                grn_line["item_id"] = item_id
                break

    # Persist the back-filled item_ids on the GRN doc so subsequent inspection /
    # delete actions operate on the correct inventory rows.
    if any(line.get("item_id") for line in doc["items"]):
        await db.grn.update_one({"id": doc["id"]}, {"$set": {"items": doc["items"]}})

    # Update PO status — compare cumulative accepted across ALL GRNs against
    # ordered quantity, not just whether this GRN had any partial line.
    cum_after: Dict[int, float] = dict(cum_by_idx)
    for it in payload.items:
        idx = int(it.po_item_index)
        cum_after[idx] = cum_after.get(idx, 0.0) + float(it.accepted_qty or 0)
    fully_received = bool(po_items) and all(
        cum_after.get(i, 0.0) + 1e-6 >= float((po_items[i] or {}).get("quantity") or 0)
        for i in range(len(po_items))
    )
    new_po_status = "received" if fully_received else "partially_received"
    await db.purchase_orders.update_one({"id": payload.po_id}, {"$set": {"status": new_po_status, "last_grn_id": doc["id"], "last_grn_number": doc["grn_number"], "updated_at": now_iso()}})

    # Iter 53 · Phase 1 — push the receipt event back to the originating PR so
    # the user sees `partially_fulfilled` → `closed` as receipts roll in.
    if po.get("pr_id"):
        await _refresh_pr_fulfilment(po["pr_id"])

    await audit(user=user, action="create", resource="grn", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.delete("/procurement/grns/{grn_id}")
async def delete_grn(grn_id: str, request: Request,
                     user: dict = Depends(require_permission("grn", "delete"))):
    """Reverses inventory inward for the GRN, then deletes it."""
    grn = await db.grn.find_one({"id": grn_id}, {"_id": 0})
    if not grn:
        raise HTTPException(status_code=404, detail="GRN not found")
    for it in grn.get("items") or []:
        if it.get("item_id") and float(it.get("accepted_qty") or 0) > 0:
            await db.inventory.update_one({"id": it["item_id"]}, {"$inc": {"quantity": -float(it["accepted_qty"])}})
    await db.grn.delete_one({"id": grn_id})
    await audit(user=user, action="delete", resource="grn", record_id=grn_id, before=grn, ip=_ip(request))
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Iter 53 · Phase 1 — End-to-end Lineage Trail
# ──────────────────────────────────────────────────────────────────────────────
def _node(kind: str, doc: dict, *, status_field: str = "status") -> dict:
    """Shape a single chain node for the lineage response."""
    if not doc:
        return None  # type: ignore
    no_field = {
        "pr": "pr_number", "rfq": "rfq_number", "po": "po_number", "grn": "grn_number",
        "inventory_txn": "id",
    }[kind]
    return {
        "kind": kind,
        "id": doc.get("id"),
        "doc_no": doc.get(no_field) or doc.get("dept_doc_no") or doc.get("id"),
        "dept_doc_no": doc.get("dept_doc_no"),
        "status": doc.get(status_field) or doc.get("inspection_status"),
        "created_at": doc.get("created_at"),
        "amount": doc.get("amount") or doc.get("total_accepted"),
        "vendor": doc.get("vendor") or doc.get("vendor_name"),
        "department": doc.get("department"),
        "project": doc.get("project") or doc.get("project_code"),
    }


@router.get("/procurement/lineage/{kind}/{record_id}")
async def lineage(kind: str, record_id: str,
                  user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    """Return the complete PR → RFQ → PO → GRN(s) → inventory-txn chain for any
    record in the procurement cycle.

    `kind` must be one of: pr | rfq | po | grn.
    The endpoint walks the chain both backwards (toward the originating PR)
    and forwards (toward fulfilment), and returns:

      {
        "chain": [ {kind, id, doc_no, status, ...}, ... ],   // top-down PR → GRN
        "fulfilment": { "ordered": N, "received": M, "rejected": K, "pct": .. },
        "anchor": "pr|rfq|po|grn"
      }
    """
    kind = kind.lower()
    if kind not in {"pr", "rfq", "po", "grn"}:
        raise HTTPException(status_code=400, detail="kind must be pr|rfq|po|grn")

    # Resolve the anchor doc + find the originating PR.
    pr = rfq = po = grns = None
    grns = []

    if kind == "pr":
        pr = await db.purchase_requisitions.find_one({"id": record_id}, {"_id": 0})
    elif kind == "rfq":
        rfq = await db.rfqs.find_one({"id": record_id}, {"_id": 0})
        if rfq and rfq.get("pr_id"):
            pr = await db.purchase_requisitions.find_one({"id": rfq["pr_id"]}, {"_id": 0})
    elif kind == "po":
        po = await db.purchase_orders.find_one({"id": record_id}, {"_id": 0})
        if po and po.get("rfq_id"):
            rfq = await db.rfqs.find_one({"id": po["rfq_id"]}, {"_id": 0})
        if po and po.get("pr_id"):
            pr = await db.purchase_requisitions.find_one({"id": po["pr_id"]}, {"_id": 0})
    elif kind == "grn":
        grn_doc = await db.grn.find_one({"id": record_id}, {"_id": 0})
        if grn_doc:
            grns = [grn_doc]
            if grn_doc.get("po_id"):
                po = await db.purchase_orders.find_one({"id": grn_doc["po_id"]}, {"_id": 0})
                if po and po.get("rfq_id"):
                    rfq = await db.rfqs.find_one({"id": po["rfq_id"]}, {"_id": 0})
                if po and po.get("pr_id"):
                    pr = await db.purchase_requisitions.find_one({"id": po["pr_id"]}, {"_id": 0})

    if not (pr or rfq or po or grns):
        raise HTTPException(status_code=404, detail="record not found")

    # Walk forward to fill anything we don't already have.
    if pr and not rfq and pr.get("rfq_id"):
        rfq = await db.rfqs.find_one({"id": pr["rfq_id"]}, {"_id": 0})
    if rfq and not po and rfq.get("po_id"):
        po = await db.purchase_orders.find_one({"id": rfq["po_id"]}, {"_id": 0})
    elif pr and not po and pr.get("po_id"):
        po = await db.purchase_orders.find_one({"id": pr["po_id"]}, {"_id": 0})
    # Pull ALL GRNs for the PO (not just the last one) so users see every receipt
    if po and not grns:
        grns = await db.grn.find({"po_id": po["id"]}, {"_id": 0}).sort("created_at", 1).to_list(50)

    # Fulfilment summary — ordered vs accepted vs rejected across all GRNs
    fulfilment = {"ordered": 0.0, "received": 0.0, "rejected": 0.0, "pct": 0.0}
    if po:
        for it in po.get("items") or []:
            fulfilment["ordered"] += float(it.get("quantity") or 0)
        for g in grns:
            for it in g.get("items") or []:
                fulfilment["received"] += float(it.get("accepted_qty") or 0)
                fulfilment["rejected"] += float(it.get("rejected_qty") or 0)
        if fulfilment["ordered"] > 0:
            fulfilment["pct"] = round(min(100.0, fulfilment["received"] / fulfilment["ordered"] * 100), 1)

    chain = [_node("pr", pr) if pr else None,
             _node("rfq", rfq) if rfq else None,
             _node("po", po) if po else None]
    for g in grns:
        chain.append(_node("grn", g, status_field="inspection_status"))
    chain = [c for c in chain if c]
    return {"chain": chain, "fulfilment": fulfilment, "anchor": kind}


async def _refresh_pr_fulfilment(pr_id: str) -> None:
    """Walk PR → PO → GRNs and update PR status to partially_fulfilled / closed
    once the cumulative accepted qty meets the requested qty across all line
    items. Called from GRN create."""
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        return
    po_id = pr.get("po_id")
    if not po_id:
        return
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        return
    grns = await db.grn.find({"po_id": po_id}, {"_id": 0}).to_list(200)
    received_total = 0.0
    for g in grns:
        for it in g.get("items") or []:
            received_total += float(it.get("accepted_qty") or 0)
    requested_total = sum(float(i.get("quantity") or 0) for i in pr.get("items") or [])
    if requested_total <= 0:
        return
    pct = received_total / requested_total
    new_status = pr.get("status") or "po_generated"
    if pct >= 1.0:
        new_status = "closed"
    elif pct > 0:
        new_status = "partially_fulfilled"
    if new_status != pr.get("status"):
        await db.purchase_requisitions.update_one(
            {"id": pr_id},
            {"$set": {"status": new_status, "fulfilment_pct": round(pct * 100, 1),
                       "updated_at": now_iso()}},
        )


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/procurement/dashboard")
async def procurement_dashboard(user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    pr_total = await db.purchase_requisitions.count_documents({})
    pr_pending = await db.purchase_requisitions.count_documents({"status": "pending_approval"})
    pr_approved = await db.purchase_requisitions.count_documents({"status": "approved"})
    pr_rejected = await db.purchase_requisitions.count_documents({"status": "rejected"})

    rfq_total = await db.rfqs.count_documents({})
    rfq_open = await db.rfqs.count_documents({"status": {"$in": ["response_pending", "under_evaluation"]}})

    po_total = await db.purchase_orders.count_documents({})
    po_open = await db.purchase_orders.count_documents({"status": {"$in": ["approved", "sent_to_vendor", "partially_received"]}})

    grn_total = await db.grn.count_documents({})
    grn_partial = await db.grn.count_documents({"status": "partial_accepted"})

    # Cycle time — for converted PRs, calculate days between PR created_at and PO created_at
    pipeline_pr = [
        {"$match": {"status": "po_generated", "po_id": {"$exists": True}}},
        {"$lookup": {"from": "purchase_orders", "localField": "po_id", "foreignField": "id", "as": "po"}},
        {"$unwind": "$po"},
        {"$project": {
            "pr_created": "$created_at",
            "po_created": "$po.created_at",
        }},
    ]
    cycle_rows = await db.purchase_requisitions.aggregate(pipeline_pr).to_list(500)
    cycle_days = []
    for r in cycle_rows:
        try:
            d1 = datetime.fromisoformat(str(r["pr_created"]).replace("Z", "+00:00"))
            d2 = datetime.fromisoformat(str(r["po_created"]).replace("Z", "+00:00"))
            cycle_days.append((d2 - d1).total_seconds() / 86400.0)
        except Exception:
            continue
    avg_cycle = round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else None

    return {
        "kpis": {
            "pr_total": pr_total, "pr_pending": pr_pending, "pr_approved": pr_approved, "pr_rejected": pr_rejected,
            "rfq_total": rfq_total, "rfq_open": rfq_open,
            "po_total": po_total, "po_open": po_open,
            "grn_total": grn_total, "grn_partial": grn_partial,
            "avg_cycle_days": avg_cycle,
        },
    }



# ─────────────────────────────────────────────────────────────────────
# Iter 54 · Phase 4 — Procurement reports (registers + analytics)
# ─────────────────────────────────────────────────────────────────────
@router.get("/procurement/reports/register/{kind}")
async def register_report(kind: str,
                           from_date: Optional[str] = None,
                           to_date: Optional[str] = None,
                           department: Optional[str] = None,
                           project: Optional[str] = None,
                           vendor_id: Optional[str] = None,
                           limit: int = 1000,
                           user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    """Flat register report for any of: pr | rfq | po | grn.
    Returns `{rows: [...], totals: {count, value}}` ready for CSV export."""
    kind = kind.lower()
    coll_map = {"pr": "purchase_requisitions", "rfq": "rfqs",
                 "po": "purchase_orders", "grn": "grn"}
    if kind not in coll_map:
        raise HTTPException(status_code=400, detail="kind must be pr | rfq | po | grn")

    q: dict = {}
    if from_date:
        q.setdefault("created_at", {})["$gte"] = from_date
    if to_date:
        q.setdefault("created_at", {})["$lte"] = to_date + "T23:59:59"
    if department:
        q["department"] = department
    if project:
        q["project"] = project
    if vendor_id:
        q["vendor_id"] = vendor_id

    rows = await db[coll_map[kind]].find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    total_value = sum(float(r.get("amount") or r.get("total") or 0) for r in rows)
    return {"kind": kind, "count": len(rows), "total_value": round(total_value, 2),
            "rows": rows}


@router.get("/procurement/reports/pending-pos")
async def pending_po_report(user: dict = Depends(require_permission("purchase_orders", "read"))):
    """POs that have NOT been fully received. Each row carries delay-days
    (today - po.created_at) so the UI can flag delayed deliveries."""
    rows = await db.purchase_orders.find(
        {"status": {"$in": ["approved", "sent_to_vendor", "partially_received"]}},
        {"_id": 0},
    ).sort("created_at", 1).to_list(1000)
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        try:
            d = datetime.fromisoformat(str(r.get("created_at")).replace("Z", "+00:00"))
            delay = (now - d).days
        except Exception:
            delay = None
        out.append({**r, "delay_days": delay})
    return {"count": len(out), "rows": out}


@router.get("/procurement/reports/by-dimension")
async def by_dimension(dim: str = "department",
                        from_date: Optional[str] = None, to_date: Optional[str] = None,
                        user: dict = Depends(require_permission("purchase_orders", "read"))):
    """Aggregate procurement value by dimension. dim ∈ {department, project, vendor}.
    Returns one row per group with `{label, po_count, total_value}`."""
    if dim not in {"department", "project", "vendor"}:
        raise HTTPException(status_code=400, detail="dim must be department | project | vendor")

    match: dict = {}
    if from_date:
        match.setdefault("created_at", {})["$gte"] = from_date
    if to_date:
        match.setdefault("created_at", {})["$lte"] = to_date + "T23:59:59"

    group_field = {"department": "$department", "project": "$project", "vendor": "$vendor"}[dim]
    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {"_id": group_field,
                     "po_count": {"$sum": 1},
                     "total_value": {"$sum": {"$ifNull": ["$amount", "$total"]}}}},
        {"$sort": {"total_value": -1}},
        {"$limit": 50},
    ]
    rows = await db.purchase_orders.aggregate(pipeline).to_list(50)
    out = [{"label": r.get("_id") or "—", "po_count": r["po_count"],
            "total_value": round(float(r.get("total_value") or 0), 2)} for r in rows]
    return {"dimension": dim, "rows": out}


@router.get("/procurement/reports/rejected-material")
async def rejected_material_report(user: dict = Depends(require_permission("grn", "read"))):
    """Every GRN line where rejected_qty > 0. Drives the Phase-4
    'Rejected Material' report."""
    cursor = db.grn.find(
        {"total_rejected": {"$gt": 0}},
        {"_id": 0},
    ).sort("created_at", -1).limit(500)
    out = []
    async for g in cursor:
        for it in g.get("items") or []:
            if float(it.get("rejected_qty") or 0) > 0:
                out.append({
                    "grn_id": g["id"], "grn_number": g.get("grn_number"),
                    "dept_doc_no": g.get("dept_doc_no"),
                    "vendor": g.get("vendor") or g.get("vendor_name"),
                    "po_number": g.get("po_number"),
                    "received_at": g.get("created_at"),
                    "item": it.get("item_name"),
                    "received_qty": it.get("received_qty"),
                    "rejected_qty": it.get("rejected_qty"),
                    "reject_reason": it.get("reject_reason"),
                    "inspection_status": it.get("inspection_status"),
                })
    return {"count": len(out), "rows": out}



# ─────────────────────────────────── PDF EXPORTS (Iter 55) ───────────────────────────────────
from fastapi.responses import Response
from pdf_generator import (
    render_pr_pdf, render_rfq_pdf, render_comparative_pdf,
    render_po_pdf, render_grn_pdf,
)


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/procurement/prs/{pr_id}/pdf")
async def pr_pdf(pr_id: str, user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    pdf = render_pr_pdf(pr)
    return _pdf_response(pdf, f"{pr.get('pr_number') or pr_id}.pdf")


@router.get("/procurement/rfqs/{rfq_id}/pdf")
async def rfq_pdf(rfq_id: str, user: dict = Depends(require_permission("rfqs", "read"))):
    rfq = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    pr = None
    if rfq.get("pr_id"):
        pr = await db.purchase_requisitions.find_one({"id": rfq["pr_id"]}, {"_id": 0})
    pdf = render_rfq_pdf(rfq, pr)
    return _pdf_response(pdf, f"{rfq.get('rfq_number') or rfq_id}.pdf")


@router.get("/procurement/rfqs/{rfq_id}/comparative/pdf")
async def comparative_pdf(rfq_id: str, user: dict = Depends(require_permission("rfqs", "read"))):
    rfq = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    comp = await comparative_statement(rfq_id, user)  # reuse
    # Reshape rows→vendors+items.vendor_quotes for the PDF helper
    items_for_pdf = []
    for idx, it in enumerate(comp.get("items") or []):
        vq = {}
        for r in comp.get("rows") or []:
            ib = next((b for b in (r.get("item_breakdown") or []) if b.get("index") == idx), None)
            if ib and ib.get("rate") is not None:
                vq[r["vendor_id"]] = {"rate": ib["rate"], "amount": ib["value"]}
        items_for_pdf.append({**it, "vendor_quotes": vq})
    vendors_for_pdf = []
    for r in comp.get("rows") or []:
        vendors_for_pdf.append({
            "vendor_id": r["vendor_id"],
            "vendor_name": r["vendor_name"],
            "total": r.get("landed_value") or 0,
            "rank": r.get("rank"),
            "delta_vs_l1": r.get("delta_vs_l1"),
            "delta_pct_vs_l1": r.get("delta_pct_vs_l1"),
            "selected": r.get("is_selected"),
            "non_l1_justification": r.get("non_l1_justification") or rfq.get("non_l1_justification"),
        })
    pdf = render_comparative_pdf(rfq, {
        "items": items_for_pdf,
        "vendors": vendors_for_pdf,
        "non_l1_justification": rfq.get("non_l1_justification"),
    })
    return _pdf_response(pdf, f"Comparative-{rfq.get('rfq_number') or rfq_id}.pdf")


@router.get("/procurement/pos/{po_id}/pdf")
async def po_pdf(po_id: str, user: dict = Depends(require_permission("purchase_orders", "read"))):
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    vendor = None
    if po.get("vendor_id"):
        vendor = await db.vendors.find_one({"id": po["vendor_id"]}, {"_id": 0})
    pdf = render_po_pdf(po, vendor)
    return _pdf_response(pdf, f"{po.get('po_number') or po_id}.pdf")


@router.get("/procurement/grns/{grn_id}/pdf")
async def grn_pdf(grn_id: str, user: dict = Depends(require_permission("grns", "read"))):
    grn = await db.grn.find_one({"id": grn_id}, {"_id": 0})
    if not grn:
        raise HTTPException(status_code=404, detail="GRN not found")
    po = None
    if grn.get("po_id"):
        po = await db.purchase_orders.find_one({"id": grn["po_id"]}, {"_id": 0})
    vendor = None
    if (po or {}).get("vendor_id") or grn.get("vendor_id"):
        vid = (po or {}).get("vendor_id") or grn.get("vendor_id")
        vendor = await db.vendors.find_one({"id": vid}, {"_id": 0})
    pdf = render_grn_pdf(grn, po, vendor)
    return _pdf_response(pdf, f"{grn.get('grn_number') or grn_id}.pdf")
