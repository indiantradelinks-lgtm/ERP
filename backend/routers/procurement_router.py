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
from pagination import maybe_paged, paged_or_rows
from audit import audit
from sequences import next_sequence, stamp_dept_doc
from approval_engine import build_chain, insert_approval, copy_approval_doc_fields

# PO lifecycle: statuses where the PO is under approval or finalised — no edits allowed.
PO_LOCKED_STATUSES = frozenset({"pending_approval", "submitted", "approved",
                                "sent_to_vendor", "received", "partially_received"})


def validate_po_items(items: List[Dict[str, Any]]) -> None:
    if not items:
        raise HTTPException(status_code=400, detail="Data missing: PO must have at least one line item")
    for idx, it in enumerate(items, 1):
        name = (it.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail=f"Data missing: Item {idx} has no name/description")
        if float(it.get("quantity") or 0) <= 0:
            raise HTTPException(status_code=400, detail=f"Data missing: '{name}' has zero quantity — enter a valid quantity")
        if float(it.get("rate") or 0) <= 0:
            raise HTTPException(status_code=400, detail=f"Data missing: '{name}' has zero rate/price — enter a valid rate")


def recalc_po_items(items: List[Dict[str, Any]], gst_type: str = "cgst_sgst") -> Dict[str, Any]:
    """Recompute per-line GST + totals. Returns fields to $set on the PO."""
    sub_total = gst_total = 0.0
    for it in items:
        qty = float(it.get("quantity") or 0)
        rate = float(it.get("rate") or 0)
        gst_pct = float(it.get("gst_pct") if it.get("gst_pct") is not None else 18)
        line_value = round(qty * rate, 2)
        gst_amount = round(line_value * gst_pct / 100, 2)
        it.update({"quantity": qty, "rate": rate, "gst_pct": gst_pct,
                   "line_value": line_value, "gst_amount": gst_amount,
                   "line_total": round(line_value + gst_amount, 2)})
        sub_total += line_value
        gst_total += gst_amount
    out = {"items": items, "amount": round(sub_total, 2), "gst_amount": round(gst_total, 2),
           "total": round(sub_total + gst_total, 2), "gst_type": gst_type}
    if gst_type == "igst":
        out.update({"igst_amount": round(gst_total, 2), "cgst_amount": 0.0, "sgst_amount": 0.0})
    else:
        half = round(gst_total / 2, 2)
        out.update({"igst_amount": 0.0, "cgst_amount": half, "sgst_amount": round(gst_total - half, 2)})
    return out


AMEND_SNAPSHOT_FIELDS = ("items", "amount", "gst_amount", "cgst_amount", "sgst_amount",
                         "igst_amount", "total", "gst_type", "delivery_terms",
                         "special_terms", "other_terms", "payment_terms")

_ITEM_DIFF_FIELDS = (("name", "Item name"), ("quantity", "Qty"), ("rate", "Rate"),
                     ("gst_pct", "GST %"), ("unit", "Unit"), ("make", "Make"),
                     ("technical_specs", "Specs"))
_HEADER_DIFF_FIELDS = (("gst_type", "GST Type"), ("delivery_terms", "Delivery Terms"),
                       ("special_terms", "Special Terms"), ("other_terms", "Other Terms"),
                       ("amount", "Sub-total"), ("gst_amount", "Total GST"), ("total", "Grand Total"))


def _diff_eq(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return (a or "") == (b or "")


def po_amendment_changes(before: Dict[str, Any], after: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Structured old→new diff between two PO snapshots (items + header)."""
    changes: List[Dict[str, Any]] = []
    b_items = before.get("items") or []
    a_items = after.get("items") or []
    for i in range(max(len(b_items), len(a_items))):
        b = b_items[i] if i < len(b_items) else None
        a = a_items[i] if i < len(a_items) else None
        if b is None:
            changes.append({"kind": "item_added", "index": i, "item": (a or {}).get("name")})
            continue
        if a is None:
            changes.append({"kind": "item_removed", "index": i, "item": b.get("name")})
            continue
        for f, label in _ITEM_DIFF_FIELDS:
            if not _diff_eq(b.get(f), a.get(f)):
                changes.append({"kind": "item_field", "index": i, "item": a.get("name") or b.get("name"),
                                "field": label, "old": b.get(f), "new": a.get(f)})
    for f, label in _HEADER_DIFF_FIELDS:
        if not _diff_eq(before.get(f), after.get(f)):
            changes.append({"kind": "header", "field": label, "old": before.get(f), "new": after.get(f)})
    return changes


async def create_po_approval(po: Dict[str, Any], user: dict) -> str:
    chain = await build_chain("purchase_order")
    rev = int(po.get("revision") or 0)
    last_amend = (po.get("amendments") or [])[-1] if po.get("amendments") else {}
    n_changes = len(last_amend.get("changes") or [])
    approval = {
        "id": new_id(),
        "type": "purchase_order",
        "module": "procurement",
        "record_id": po["id"],
        "reference": po.get("po_number"),
        "title": f"PO {po.get('po_number')}{f' (Rev {rev})' if rev else ''} · {po.get('vendor') or ''}",
        "summary": f"{len(po.get('items') or [])} item(s) · ₹ {float(po.get('total') or po.get('amount') or 0):,.2f}"
                   + (f" · AMENDED — {n_changes} change(s)" if rev else ""),
        "amendment_changes": (last_amend.get("changes") or [])[:30] if rev else [],
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "documents_not_required": True,
        "documents_not_required_reason": "PO generated from approved PR/RFQ — source documents on record",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await insert_approval(approval)
    return approval["id"]

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
async def list_prs(request: Request, status: Optional[str] = None,
                   user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    paged = await maybe_paged(request, "purchase_requisitions", q, "created_at",
                              ["pr_number", "project_code", "project_name", "department", "status", "requested_by", "purpose"])
    if paged:
        return paged
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


@router.get("/procurement/prs/{pr_id}/coverage")
async def pr_coverage(pr_id: str, user: dict = Depends(require_permission("purchase_requisitions", "read"))):
    """Per-item release map: which RFQ each PR item went into, which PO it landed
    in, and which items are still pending RFQ release."""
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    pr_items = pr.get("items") or []
    rfqs = await db.rfqs.find({"pr_id": pr_id, "status": {"$ne": "cancelled"}},
                              {"_id": 0, "id": 1, "rfq_number": 1, "status": 1,
                                                 "item_indexes": 1, "po_id": 1, "po_number": 1,
                                                 "selected_vendor_id": 1, "vendors": 1}).to_list(100)
    po_ids = [r["po_id"] for r in rfqs if r.get("po_id")]
    pos = {p["id"]: p async for p in db.purchase_orders.find(
        {"id": {"$in": po_ids}}, {"_id": 0, "id": 1, "po_number": 1, "status": 1, "total": 1, "vendor": 1, "revision": 1})}
    out_items = []
    released = po_covered = 0
    for i, it in enumerate(pr_items):
        releases = []
        for r in rfqs:
            idxs = r.get("item_indexes") if r.get("item_indexes") is not None else list(range(len(pr_items)))
            if i not in idxs:
                continue
            sel = next((v for v in (r.get("vendors") or []) if v.get("vendor_id") == r.get("selected_vendor_id")), None)
            po = pos.get(r.get("po_id"))
            releases.append({
                "rfq_id": r["id"], "rfq_number": r.get("rfq_number"), "rfq_status": r.get("status"),
                "vendor": (po or {}).get("vendor") or (sel or {}).get("vendor_name"),
                "po_id": (po or {}).get("id"), "po_number": (po or {}).get("po_number"),
                "po_status": (po or {}).get("status"), "po_revision": (po or {}).get("revision"),
            })
        state = "pending_release"
        if any(x.get("po_number") for x in releases):
            state = "po_created"
            po_covered += 1
            released += 1
        elif releases:
            state = "in_rfq"
            released += 1
        out_items.append({"index": i, "name": it.get("name"), "quantity": it.get("quantity"),
                          "unit": it.get("unit") or "Nos", "state": state, "releases": releases})
    return {
        "pr_number": pr.get("pr_number"), "status": pr.get("status"),
        "summary": {"total_items": len(pr_items), "released": released,
                    "po_created": po_covered, "pending": len(pr_items) - released},
        "items": out_items,
    }


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
    item_indexes: Optional[List[int]] = None   # subset of PR item indexes for this RFQ


class RFQResponse(BaseModel):
    vendor_id: str
    rate_quoted: Optional[float] = None       # Legacy single-rate fallback applied across all items
    item_rates: Optional[Dict[str, float]] = None   # Per-item rates keyed by stringified po_item_index
    delivery_days: Optional[int] = None
    payment_terms: Optional[str] = None
    technical_score: Optional[float] = None     # 0-100
    note: Optional[str] = None


@router.get("/procurement/rfqs")
async def list_rfqs(request: Request, user: dict = Depends(require_permission("rfqs", "read"))):
    paged = await maybe_paged(request, "rfqs", {}, "created_at", ["rfq_number", "pr_number", "project_code", "status", "title"])
    if paged:
        return paged
    rows = await db.rfqs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/procurement/rfqs/{rfq_id}")
async def get_rfq(rfq_id: str, user: dict = Depends(require_permission("rfqs", "read"))):
    row = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return row


async def _recompute_pr_release_status(pr_id: str) -> str:
    """Re-derive PR status from its active (non-cancelled) RFQs and converted POs."""
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0, "items": 1, "status": 1})
    if not pr:
        return ""
    n = len(pr.get("items") or [])
    rfqs = await db.rfqs.find({"pr_id": pr_id, "status": {"$ne": "cancelled"}},
                              {"_id": 0, "item_indexes": 1, "po_id": 1}).to_list(200)
    po_covered: set = set()
    for r in rfqs:
        if r.get("po_id"):
            po_covered |= set(r.get("item_indexes") if r.get("item_indexes") is not None else range(n))
    if po_covered >= set(range(n)) and n:
        status = "po_generated"
    elif po_covered:
        status = "partially_fulfilled"
    elif rfqs:
        status = "rfq_initiated"
    else:
        status = "approved"
    await db.purchase_requisitions.update_one({"id": pr_id}, {"$set": {"status": status, "updated_at": now_iso()}})
    return status


@router.post("/procurement/rfqs")
async def create_rfq(payload: RFQIn, request: Request,
                     user: dict = Depends(require_permission("rfqs", "write"))):
    pr = await db.purchase_requisitions.find_one({"id": payload.pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    if pr.get("status") not in ("approved", "rfq_initiated", "partially_fulfilled"):
        raise HTTPException(status_code=400, detail="Only approved PRs (or PRs with pending items) can be turned into an RFQ")
    if not payload.vendors:
        raise HTTPException(status_code=400, detail="Pick at least one vendor")
    pr_items = pr.get("items") or []
    # Items already in a live (non-cancelled) RFQ cannot go into another one — only balance items
    active_covered: set = set()
    async for r in db.rfqs.find({"pr_id": payload.pr_id, "status": {"$ne": "cancelled"}}, {"_id": 0, "item_indexes": 1}):
        active_covered |= set(r.get("item_indexes") if r.get("item_indexes") is not None else range(len(pr_items)))
    if payload.item_indexes is not None:
        idxs = sorted(set(int(i) for i in payload.item_indexes))
        if not idxs:
            raise HTTPException(status_code=400, detail="Select at least one item for this RFQ")
        if any(i < 0 or i >= len(pr_items) for i in idxs):
            raise HTTPException(status_code=400, detail="Invalid item selection for this PR")
        dup = [pr_items[i].get("name") or f"Item {i + 1}" for i in idxs if i in active_covered]
        if dup:
            raise HTTPException(status_code=400,
                                detail=f"Already released in a live RFQ: {', '.join(dup)}. Cancel that RFQ first or pick only balance items.")
        rfq_items = [{**pr_items[i], "pr_item_index": i} for i in idxs]
    else:
        if active_covered:
            raise HTTPException(status_code=400, detail="Some items are already in a live RFQ — select only the balance items")
        idxs = list(range(len(pr_items)))
        rfq_items = [{**it, "pr_item_index": i} for i, it in enumerate(pr_items)]

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
        "items": rfq_items,
        "item_indexes": idxs,
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
    await db.purchase_requisitions.update_one(
        {"id": payload.pr_id},
        {"$set": {"rfq_id": doc["id"], "rfq_number": doc["rfq_number"]},
         "$push": {"rfq_ids": doc["id"]}})
    await _recompute_pr_release_status(payload.pr_id)
    await audit(user=user, action="create", resource="rfqs", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


class RFQCancelIn(BaseModel):
    reason: str


@router.post("/procurement/rfqs/{rfq_id}/cancel")
async def cancel_rfq(rfq_id: str, payload: RFQCancelIn, request: Request,
                     user: dict = Depends(require_permission("rfqs", "write"))):
    """Reject/withdraw a wrongly-sent RFQ with a mandatory reason. The RFQ stays on
    record (status 'cancelled'); its items are freed for a fresh RFQ."""
    if len((payload.reason or "").strip()) < 5:
        raise HTTPException(status_code=400, detail="Rejection reason is required (min 5 characters)")
    rfq = await db.rfqs.find_one({"id": rfq_id}, {"_id": 0})
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if rfq.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="RFQ is already cancelled")
    if rfq.get("status") == "converted_to_po":
        raise HTTPException(status_code=400, detail="RFQ already converted to a PO — amend/cancel the PO instead")
    upd = {"status": "cancelled", "cancel_reason": payload.reason.strip(),
           "cancelled_by": user.get("name") or user.get("email"),
           "cancelled_by_id": user["id"], "cancelled_at": now_iso(), "updated_at": now_iso()}
    await db.rfqs.update_one({"id": rfq_id}, {"$set": upd})
    pr_status = await _recompute_pr_release_status(rfq["pr_id"]) if rfq.get("pr_id") else None
    await audit(user=user, action="cancel", resource="rfqs", record_id=rfq_id,
                before=rfq, after={**rfq, **upd}, ip=_ip(request))
    return {**rfq, **upd, "pr_status": pr_status}


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
    for idx, it in enumerate(rfq.get("items") or []):
        qty = float(it.get("quantity") or 0)
        ir = item_rates.get(str(idx))
        r = float(ir) if ir is not None else (float(fallback_rate) if fallback_rate is not None else 0.0)
        po_items.append({**it, "rate": r, "gst_pct": float(it.get("gst_pct") if it.get("gst_pct") is not None else 18)})
    validate_po_items(po_items)
    calc = recalc_po_items(po_items, "cgst_sgst")

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
        **calc,
        "status": "draft",   # purchase team edits the draft, then submits into the approval chain
        "revision": 0,
        "item_indexes": rfq.get("item_indexes"),
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
    await db.purchase_requisitions.update_one(
        {"id": rfq["pr_id"]},
        {"$set": {"po_id": po["id"], "po_number": po["po_number"], "updated_at": now_iso()},
         "$push": {"po_ids": po["id"]}})
    await _recompute_pr_release_status(rfq["pr_id"])
    await audit(user=user, action="create", resource="purchase_orders", record_id=po["id"], after=po, ip=_ip(request))
    return po


class POItemsUpdateIn(BaseModel):
    items: List[Dict[str, Any]]
    gst_type: Optional[str] = None          # igst | cgst_sgst
    delivery_terms: Optional[str] = None
    special_terms: Optional[str] = None
    other_terms: Optional[str] = None
    payment_terms: Optional[str] = None
    tds_pct: Optional[float] = None         # TDS on basic (informational)
    retention_pct: Optional[float] = None   # retention on grand total (informational)
    advance_pct: Optional[float] = None     # advance on grand total (informational)


@router.put("/procurement/pos/{po_id}/items")
async def update_po_items(po_id: str, payload: POItemsUpdateIn, request: Request,
                          user: dict = Depends(require_permission("purchase_orders", "write"))):
    """Edit PO line items (qty, rate, item-wise GST %, make, tech specs) + GST type
    and delivery/special terms. Recalculates all totals. Blocked once the PO is
    under approval or final-approved (use amendment flow)."""
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.get("status") in PO_LOCKED_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"PO is {po.get('status')} — editing is locked. Raise an amendment request to modify an approved PO.")
    gst_type = (payload.gst_type or po.get("gst_type") or "cgst_sgst").lower()
    if gst_type not in ("igst", "cgst_sgst"):
        raise HTTPException(status_code=400, detail="gst_type must be 'igst' or 'cgst_sgst'")
    existing = po.get("items") or []
    default_gst = float(po.get("gst_pct") or 18)
    allowed = ("name", "description", "quantity", "unit", "rate", "gst_pct", "hsn_sac", "make", "technical_specs")
    new_items: List[Dict[str, Any]] = []
    for idx, incoming in enumerate(payload.items):
        base = dict(existing[idx]) if idx < len(existing) else {}
        base.update({k: v for k, v in incoming.items() if k in allowed and v is not None})
        gst_pct = float(base.get("gst_pct") if base.get("gst_pct") is not None else default_gst)
        if gst_pct < 0 or gst_pct > 100:
            raise HTTPException(status_code=400, detail=f"Item {idx + 1}: GST % must be between 0 and 100")
        new_items.append(base)
    validate_po_items(new_items)
    upd = recalc_po_items(new_items, gst_type)
    for f in ("delivery_terms", "special_terms", "other_terms", "payment_terms"):
        v = getattr(payload, f)
        if v is not None:
            upd[f] = v
    for f, base_key in (("tds_pct", "amount"), ("retention_pct", "total"), ("advance_pct", "total")):
        v = getattr(payload, f)
        if v is None:
            v = po.get(f)
        if v is not None:
            v = float(v)
            if v < 0 or v > 100:
                raise HTTPException(status_code=400, detail=f"{f.replace('_pct', '').upper()} % must be between 0 and 100")
            upd[f] = v
            upd[f.replace("_pct", "_amount")] = round(upd[base_key] * v / 100, 2)
    upd.update({"updated_at": now_iso(), "updated_by": user["id"]})
    await db.purchase_orders.update_one({"id": po_id}, {"$set": upd})
    await audit(user=user, action="update", resource="purchase_orders", record_id=po_id,
                before=po, after={**po, **upd}, ip=_ip(request))
    return {**po, **upd}


@router.post("/procurement/pos/{po_id}/submit")
async def submit_po(po_id: str, request: Request,
                    user: dict = Depends(require_permission("purchase_orders", "write"))):
    """Submit a draft / revision-required / amendment-unlocked PO into the
    multi-level PO approval chain. Amended POs get a bumped revision number."""
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.get("status") not in ("draft", "pending_revision", "amendment_in_progress", "rejected"):
        raise HTTPException(status_code=400, detail=f"PO in '{po.get('status')}' cannot be submitted for approval")
    if not (po.get("pr_id") or po.get("pr_number")):
        raise HTTPException(status_code=400, detail="No PO can be raised without a PR — link a Purchase Requisition first")
    validate_po_items(po.get("items") or [])
    upd: Dict[str, Any] = {"status": "pending_approval", "updated_at": now_iso()}
    if po.get("status") == "amendment_in_progress":
        rev = int(po.get("revision") or 0) + 1
        upd["revision"] = rev
        upd["amendment_status"] = "completed"
        before = po.get("pre_amendment_snapshot")
        after = {k: po.get(k) for k in AMEND_SNAPSHOT_FIELDS}
        amendments = list(po.get("amendments") or [])
        amendments.append({"revision": rev, "reason": po.get("amendment_reason") or "",
                           "amended_by": user.get("name") or user.get("email"), "at": now_iso(),
                           "before": before, "after": after,
                           "changes": po_amendment_changes(before or {}, after) if before else []})
        upd["amendments"] = amendments
        upd["pre_amendment_snapshot"] = None
        po = {**po, **upd}
    await db.approvals.update_many(
        {"type": "purchase_order", "record_id": po_id,
         "status": {"$in": ["rejected", "rejected_revision_required", "approved"]}},
        {"$set": {"superseded": True, "superseded_at": now_iso()}})
    upd["approval_id"] = await create_po_approval(po, user)
    await db.purchase_orders.update_one({"id": po_id}, {"$set": upd})
    await audit(user=user, action="submit_for_approval", resource="purchase_orders", record_id=po_id,
                after={**po, **upd}, ip=_ip(request))
    return {"po_id": po_id, "approval_id": upd["approval_id"], "status": "pending_approval",
            "revision": upd.get("revision", po.get("revision") or 0)}


class POAmendmentIn(BaseModel):
    reason: str


@router.post("/procurement/pos/{po_id}/request-amendment")
async def request_po_amendment(po_id: str, payload: POAmendmentIn, request: Request,
                               user: dict = Depends(require_permission("purchase_orders", "write"))):
    """Purchase team raises an amendment request (with justification) on a
    final-approved PO. Editing unlocks only after this request is approved."""
    if len((payload.reason or "").strip()) < 5:
        raise HTTPException(status_code=400, detail="Amendment reason / justification is required (min 5 characters)")
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if po.get("status") not in ("approved", "sent_to_vendor", "received", "partially_received"):
        raise HTTPException(status_code=400, detail="Only final-approved POs can be amended — this PO is not approved yet")
    if po.get("amendment_status") == "requested":
        raise HTTPException(status_code=400, detail="An amendment request is already pending approval for this PO")
    chain = await build_chain("po_amendment")
    approval = {
        "id": new_id(),
        "type": "po_amendment",
        "module": "procurement",
        "record_id": po_id,
        "reference": po.get("po_number"),
        "title": f"PO Amendment — {po.get('po_number')} (Rev {int(po.get('revision') or 0)} → {int(po.get('revision') or 0) + 1})",
        "summary": f"Reason: {payload.reason.strip()[:180]}",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "documents_not_required": True,
        "documents_not_required_reason": "Amendment justification captured in request",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await insert_approval(approval)
    await db.purchase_orders.update_one({"id": po_id}, {"$set": {
        "amendment_status": "requested", "amendment_reason": payload.reason.strip(),
        "amendment_requested_by": user.get("name") or user.get("email"),
        "amendment_requested_at": now_iso(), "amendment_approval_id": approval["id"],
        "updated_at": now_iso()}})
    await audit(user=user, action="request_amendment", resource="purchase_orders", record_id=po_id,
                after={"reason": payload.reason}, ip=_ip(request))
    return {"po_id": po_id, "approval_id": approval["id"], "amendment_status": "requested"}


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
    # ── Phase 2 enrichment (all optional & backward-compatible) ──────────
    vendor_invoice_no: Optional[str] = None
    vendor_invoice_date: Optional[str] = None
    vendor_invoice_value: Optional[float] = None
    vehicle_number: Optional[str] = None
    transporter_name: Optional[str] = None
    transporter_lr_no: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_urls: Optional[List[str]] = None
    project_code: Optional[str] = None
    inspection_required: Optional[bool] = None
    manual_grn: bool = False     # if true, allows GRN against non-approved PO (caller must have permission)


@router.get("/procurement/grns")
async def list_grns(request: Request, user: dict = Depends(require_permission("grn", "read"))):
    paged = await maybe_paged(request, "grn", {}, "created_at", ["grn_number", "po_number", "vendor_name", "project_code", "status"])
    if paged:
        return paged
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
        if not payload.manual_grn:
            raise HTTPException(status_code=400, detail=f"PO in '{po.get('status')}' cannot receive material. Set manual_grn=true with appropriate authority to override.")
        # Manual GRN is only allowed for elevated roles
        if user.get("role") not in {"super_admin", "director", "general_manager", "store_incharge", "purchase_officer"}:
            raise HTTPException(status_code=403, detail="manual_grn override requires elevated role")

    # Phase 2 — duplicate vendor invoice guard
    if payload.vendor_invoice_no:
        dup = await db.grn.find_one({
            "po_id": payload.po_id,
            "vendor_invoice_no": payload.vendor_invoice_no,
            "status": {"$ne": "deleted"},
        }, {"_id": 0, "grn_number": 1})
        if dup:
            raise HTTPException(status_code=409,
                                detail=f"Vendor invoice {payload.vendor_invoice_no} already received via {dup.get('grn_number')}")

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
        # Phase 2 enrichment
        "vendor_invoice_no": payload.vendor_invoice_no,
        "vendor_invoice_date": payload.vendor_invoice_date,
        "vendor_invoice_value": payload.vendor_invoice_value,
        "vehicle_number": payload.vehicle_number,
        "transporter_name": payload.transporter_name,
        "transporter_lr_no": payload.transporter_lr_no,
        "attachment_url": payload.attachment_url,
        "attachment_urls": payload.attachment_urls or ([payload.attachment_url] if payload.attachment_url else []),
        "project_code": payload.project_code or po.get("project"),
        "manual_grn": payload.manual_grn,
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
    if not po.get("project_name"):
        code = po.get("project_code") or po.get("project")
        q = {"id": po["project_id"]} if po.get("project_id") else ({"code": code} if code else None)
        if q:
            proj = await db.projects.find_one(q, {"_id": 0, "name": 1, "code": 1})
            if proj:
                po["project_name"] = proj.get("name")
                po["project_code"] = po.get("project_code") or proj.get("code") or code
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


# ─────────────────────────── Vendor Acknowledgement (public, token-based) ───────────────────────────
import base64 as _b64

_TRACK_GIF = _b64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


async def _po_by_ack_token(token: str) -> Dict[str, Any]:
    po = await db.purchase_orders.find_one({"vendor_ack.token": token}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Invalid or expired acknowledgement link")
    return po


@router.get("/public/po-track/{token}/open.gif")
async def po_track_open(token: str):
    """1×1 tracking pixel embedded in the PO email — records first open."""
    po = await db.purchase_orders.find_one({"vendor_ack.token": token}, {"_id": 0, "id": 1, "vendor_ack": 1})
    if po and not (po.get("vendor_ack") or {}).get("opened_at"):
        await db.purchase_orders.update_one({"id": po["id"]}, {"$set": {"vendor_ack.opened_at": now_iso()}})
    return Response(content=_TRACK_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.get("/public/po-ack/{token}")
async def po_ack_info(token: str):
    po = await _po_by_ack_token(token)
    if not (po.get("vendor_ack") or {}).get("opened_at"):
        await db.purchase_orders.update_one({"id": po["id"]}, {"$set": {"vendor_ack.opened_at": now_iso()}})
    ack = po.get("vendor_ack") or {}
    return {
        "po_number": po.get("po_number"),
        "revision": int(po.get("revision") or 0),
        "vendor": po.get("vendor"),
        "project": po.get("project"),
        "date": (po.get("date") or po.get("created_at") or "")[:10],
        "total": po.get("total") or po.get("amount") or 0,
        "items": [{"name": i.get("name"), "quantity": i.get("quantity"), "unit": i.get("unit"),
                   "rate": i.get("rate"), "gst_pct": i.get("gst_pct"), "line_total": i.get("line_total")}
                  for i in (po.get("items") or [])],
        "delivery_terms": po.get("delivery_terms"),
        "sent_at": ack.get("sent_at"),
        "acknowledged_at": ack.get("acknowledged_at"),
        "acknowledged_by": ack.get("acknowledged_by"),
    }


class POAckIn(BaseModel):
    name: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/public/po-ack/{token}")
async def po_acknowledge(token: str, payload: POAckIn, request: Request):
    po = await _po_by_ack_token(token)
    ack = po.get("vendor_ack") or {}
    if ack.get("acknowledged_at"):
        return {"po_number": po.get("po_number"), "acknowledged_at": ack["acknowledged_at"],
                "acknowledged_by": ack.get("acknowledged_by"), "already": True}
    now = now_iso()
    who = (payload.name or "").strip() or po.get("vendor") or "Vendor"
    set_doc = {"vendor_ack.acknowledged_at": now, "vendor_ack.acknowledged_by": who,
               "vendor_ack.ack_ip": _ip(request), "updated_at": now}
    if payload.remarks:
        set_doc["vendor_ack.remarks"] = payload.remarks.strip()[:500]
    if not ack.get("opened_at"):
        set_doc["vendor_ack.opened_at"] = now
    await db.purchase_orders.update_one({"id": po["id"]}, {"$set": set_doc})
    return {"po_number": po.get("po_number"), "acknowledged_at": now, "acknowledged_by": who, "already": False}
