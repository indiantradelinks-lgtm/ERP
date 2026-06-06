"""Store/Inventory transaction ledger.

Every movement of stock (inward, outward, transfer, return, scrap) is journalled
in `inventory_transactions` and the corresponding `inventory.quantity` is
adjusted atomically. Outward issues above the per-item `issue_threshold`
auto-create a pending approval using the standard approval engine.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from approval_engine import build_chain, insert_approval, copy_approval_doc_fields

router = APIRouter(tags=["store"])

TXN_TYPES = ("inward", "outward", "transfer", "return", "scrap")
DEFAULT_ISSUE_THRESHOLD = 50  # qty above which outward auto-triggers approval


class StoreTxnIn(BaseModel):
    txn_type: str  # inward | outward | transfer | return | scrap
    item_id: str
    quantity: float
    unit: Optional[str] = None
    project: Optional[str] = None
    to_location: Optional[str] = None      # for transfer
    from_location: Optional[str] = None
    received_from: Optional[str] = None    # vendor / supplier for inward
    issued_to: Optional[str] = None        # employee / project for outward
    note: Optional[str] = None
    batch: Optional[str] = None
    needs_approval: Optional[bool] = None
    # Iter 48 — Cross-dept dependency: outward MUST reference an approved PR / allocation
    pr_id: Optional[str] = None             # ref to purchase_requisitions
    allocation_id: Optional[str] = None     # ref to material_allocations
    force_unlinked: Optional[bool] = False  # only super_admin can bypass


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _delta(txn_type: str, qty: float) -> float:
    if txn_type in ("outward", "scrap", "transfer"):
        return -abs(qty)
    return abs(qty)


@router.get("/store/transactions")
async def list_txns(
    item_id: Optional[str] = None,
    txn_type: Optional[str] = None,
    limit: int = 200,
    user: dict = Depends(require_permission("inventory", "read")),
):
    q = {}
    if item_id:
        q["item_id"] = item_id
    if txn_type:
        q["txn_type"] = txn_type
    rows = await db.inventory_transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(max(1, min(limit, 1000)))
    return rows


@router.post("/store/transactions")
async def create_txn(payload: StoreTxnIn, request: Request, user: dict = Depends(require_permission("inventory", "write"))):
    if payload.txn_type not in TXN_TYPES:
        raise HTTPException(status_code=400, detail=f"txn_type must be one of {TXN_TYPES}")
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    item = await db.inventory.find_one({"id": payload.item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    # Iter 48 — Cross-dept dependency rule: outward issuances MUST be backed by an
    # approved Purchase Requisition or Material Allocation. Super_admin can bypass.
    if payload.txn_type == "outward":
        bypass = (payload.force_unlinked and user.get("role") == "super_admin")
        if not bypass:
            linked_ok = False
            note_link = ""
            if payload.pr_id:
                pr = await db.purchase_requisitions.find_one(
                    {"id": payload.pr_id}, {"_id": 0, "status": 1, "pr_number": 1, "dept_doc_no": 1},
                )
                if pr and pr.get("status") in {"approved", "issued", "po_created", "completed"}:
                    linked_ok = True
                    note_link = pr.get("dept_doc_no") or pr.get("pr_number") or payload.pr_id
            if not linked_ok and payload.allocation_id:
                alloc = await db.material_allocations.find_one(
                    {"id": payload.allocation_id}, {"_id": 0, "status": 1, "allocation_no": 1},
                )
                if alloc and alloc.get("status") in {"approved", "issued"}:
                    linked_ok = True
                    note_link = alloc.get("allocation_no") or payload.allocation_id
            if not linked_ok:
                raise HTTPException(
                    status_code=400,
                    detail=("Material outward requires a linked APPROVED Purchase Requisition or "
                            "Material Allocation. Provide `pr_id` or `allocation_id` whose status is approved/issued."),
                )

    delta = _delta(payload.txn_type, payload.quantity)
    new_qty = float(item.get("quantity", 0) or 0) + delta
    if new_qty < 0:
        raise HTTPException(status_code=400, detail=f"Insufficient stock: available {item.get('quantity', 0)}, requested {payload.quantity}")

    txn_no = await next_sequence("INV")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "txn_no": txn_no,
        "item_name": item.get("name") or item.get("title"),
        "item_sku": item.get("sku"),
        "delta": delta,
        "balance_after": new_qty,
        "status": "posted",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    })

    threshold = float(item.get("issue_threshold") or DEFAULT_ISSUE_THRESHOLD)
    needs_approval = bool(payload.needs_approval) or (payload.txn_type == "outward" and payload.quantity > threshold)
    if needs_approval:
        chain = await build_chain("expense")
        approval_doc = {
            "id": new_id(),
            "type": "material_issue",
            "title": f"Material Issue — {doc['item_name']} × {payload.quantity}",
            "reference": txn_no,
            "amount": payload.quantity * float(item.get("unit_price") or 0),
            "requested_by": user.get("name") or user.get("email"),
            "module": "inventory",
            "record_id": doc["id"],
            "status": "pending",
            "chain": chain,
            "current_step": 0,
            "history": [],
            "created_at": now_iso(),
            "created_by": user["id"],
        }
        copy_approval_doc_fields(approval_doc, payload)
        await insert_approval(approval_doc)
        doc["approval_id"] = approval_doc["id"]
        doc["status"] = "awaiting_approval"
        # Don't adjust stock until approved
    else:
        await db.inventory.update_one({"id": payload.item_id}, {"$set": {"quantity": new_qty, "updated_at": now_iso()}})

    await db.inventory_transactions.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="inventory_transactions", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/store/lookup/{code}")
async def lookup_by_code(code: str, user: dict = Depends(require_permission("inventory", "read"))):
    """Barcode/QR scanner endpoint — resolve a code (sku or id) to an inventory item."""
    row = await db.inventory.find_one(
        {"$or": [{"id": code}, {"sku": code}, {"barcode": code}]},
        {"_id": 0},
    )
    if not row:
        raise HTTPException(status_code=404, detail="No inventory item matches that code")
    return row



# ─────────────────────────────────────────────────────────────────────
# Iter 54 · Phase 3 — Stock ledger drilldown + Reorder alerts
# ─────────────────────────────────────────────────────────────────────
@router.get("/store/ledger/{item_id}")
async def stock_ledger(item_id: str,
                        from_date: Optional[str] = None,
                        to_date: Optional[str] = None,
                        user: dict = Depends(require_permission("inventory", "read"))):
    """Item-wise stock ledger showing opening · receipt · issue · return · closing.

    Returns one row per transaction PLUS aggregated totals. ``from_date`` and
    ``to_date`` (YYYY-MM-DD) are inclusive bounds. ``opening`` is the running
    balance just before the window; ``closing`` is the running balance at the
    end of the window.
    """
    item = await db.inventory.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    q: dict = {"item_id": item_id, "status": {"$ne": "awaiting_approval"}}
    range_q: dict = {}
    if from_date:
        range_q["$gte"] = from_date
    if to_date:
        range_q["$lte"] = to_date + "T23:59:59"
    if range_q:
        q["created_at"] = range_q

    txns = await db.inventory_transactions.find(q, {"_id": 0}).sort("created_at", 1).to_list(2000)

    # Compute opening balance — sum of all deltas BEFORE the window start.
    opening = 0.0
    if from_date:
        pre = db.inventory_transactions.find(
            {"item_id": item_id, "status": {"$ne": "awaiting_approval"},
             "created_at": {"$lt": from_date}},
            {"_id": 0, "delta": 1},
        )
        async for d in pre:
            opening += float(d.get("delta") or 0)

    running = opening
    rows = []
    totals = {"receipt": 0.0, "issue": 0.0, "return": 0.0, "transfer": 0.0, "scrap": 0.0}
    for t in txns:
        delta = float(t.get("delta") or 0)
        running += delta
        kind = t.get("txn_type") or "other"
        if kind in totals:
            totals[kind if kind != "outward" else "issue"] += abs(delta) if kind != "inward" else delta
        if kind == "inward":
            totals["receipt"] += abs(delta)
        elif kind == "outward":
            totals["issue"] += abs(delta)
        elif kind == "return":
            totals["return"] += delta
        elif kind == "transfer":
            totals["transfer"] += abs(delta)
        elif kind == "scrap":
            totals["scrap"] += abs(delta)
        rows.append({
            "at": t.get("created_at"),
            "txn_no": t.get("txn_no"),
            "txn_type": kind,
            "delta": delta,
            "qty": abs(delta),
            "balance_after": round(running, 3),
            "received_from": t.get("received_from"),
            "issued_to": t.get("issued_to"),
            "project": t.get("project"),
            "by": t.get("created_by_name"),
            "ref_no": t.get("ref_no") or t.get("note"),
        })
    return {
        "item": {
            "id": item["id"], "name": item.get("name"), "sku": item.get("sku"),
            "uom": item.get("uom") or item.get("unit"),
            "current_quantity": item.get("quantity"),
            "min_stock": item.get("min_stock") or item.get("reorder_level"),
        },
        "from_date": from_date, "to_date": to_date,
        "opening": round(opening, 3),
        "closing": round(running, 3),
        "totals": {k: round(v, 3) for k, v in totals.items()},
        "rows": rows,
    }


@router.get("/store/alerts/reorder")
async def reorder_alerts(user: dict = Depends(require_permission("inventory", "read"))):
    """Iter 54 · Phase 3 — items at or below their reorder level. Drives the
    "Stock Alerts" tile on the procurement dashboard."""
    cursor = db.inventory.find(
        {}, {"_id": 0, "id": 1, "name": 1, "sku": 1, "uom": 1, "unit": 1,
              "quantity": 1, "min_stock": 1, "reorder_level": 1,
              "location": 1, "category": 1},
    )
    alerts = []
    async for item in cursor:
        qty = float(item.get("quantity") or 0)
        rl = float(item.get("min_stock") or item.get("reorder_level") or 0)
        if rl > 0 and qty <= rl:
            alerts.append({
                **item,
                "shortfall": round(rl - qty, 3),
                "severity": "critical" if qty == 0 else ("low" if qty < rl * 0.5 else "warning"),
            })
    alerts.sort(key=lambda a: (a["severity"] != "critical", a.get("shortfall", 0) * -1))
    return {"count": len(alerts), "items": alerts}


# ─────────────────────────────────────────────────────────────────────
# Iter 54 · Phase 3 — GRN Quality inspection workflow
# ─────────────────────────────────────────────────────────────────────
@router.post("/procurement/grns/{grn_id}/inspect")
async def inspect_grn(grn_id: str, payload: dict, request: Request,
                       user: dict = Depends(require_permission("grn", "write"))):
    """Quality role marks a GRN line as inspected. Body:

      {
        items: [
          {index: 0, accepted_qty: 7, rejected_qty: 1, reject_reason: "...", batch: "..."}
        ],
        overall_remarks: "..."
      }

    The accepted_qty must NOT exceed the received_qty on file. Inventory is
    NOT re-adjusted here (already inwarded at GRN-create); rejected qty is
    tracked separately for the Rejected Material report (Phase 4)."""
    if user.get("role") not in {"super_admin", "quality_executive", "store_keeper",
                                  "store_user", "purchase_executive"}:
        raise HTTPException(status_code=403,
                            detail="Only Quality / Stores / Purchase / Admin can inspect a GRN")
    grn = await db.grn.find_one({"id": grn_id}, {"_id": 0})
    if not grn:
        raise HTTPException(status_code=404, detail="GRN not found")
    items = list(grn.get("items") or [])
    incoming = {int(i["index"]): i for i in (payload.get("items") or []) if "index" in i}

    total_accepted = 0.0
    total_rejected = 0.0
    for idx, it in enumerate(items):
        upd = incoming.get(idx)
        if upd:
            recv = float(it.get("received_qty") or 0)
            acc = float(upd.get("accepted_qty") or 0)
            rej = float(upd.get("rejected_qty") or 0)
            if acc + rej > recv:
                raise HTTPException(status_code=400,
                    detail=f"Line {idx + 1}: accepted+rejected ({acc + rej}) exceeds received ({recv}).")
            it["accepted_qty"] = acc
            it["rejected_qty"] = rej
            it["reject_reason"] = upd.get("reject_reason")
            it["batch"] = upd.get("batch") or it.get("batch")
            it["inspection_status"] = "approved" if rej == 0 else ("rejected" if acc == 0 else "partial_accepted")
        total_accepted += float(it.get("accepted_qty") or 0)
        total_rejected += float(it.get("rejected_qty") or 0)

    # Overall status
    if total_rejected == 0 and total_accepted > 0:
        overall = "approved"
    elif total_accepted == 0 and total_rejected > 0:
        overall = "rejected"
    else:
        overall = "partial_accepted"

    await db.grn.update_one({"id": grn_id}, {"$set": {
        "items": items,
        "total_accepted": total_accepted,
        "total_rejected": total_rejected,
        "inspection_status": overall,
        "inspected_by": user.get("name") or user.get("email"),
        "inspected_at": now_iso(),
        "overall_remarks": payload.get("overall_remarks"),
        "updated_at": now_iso(),
    }})

    # Refresh PR fulfilment downstream (in case Quality changes accepted qty).
    from routers.procurement_router import _refresh_pr_fulfilment
    if grn.get("pr_id"):
        await _refresh_pr_fulfilment(grn["pr_id"])

    await audit(user=user, action="inspect", resource="grn", record_id=grn_id,
                after={"inspection_status": overall, "total_accepted": total_accepted,
                       "total_rejected": total_rejected}, ip=_ip(request))
    fresh = await db.grn.find_one({"id": grn_id}, {"_id": 0})
    return fresh



# ─────────────────────────── PDF EXPORT (Iter 55) ───────────────────────────
from fastapi.responses import Response
from pdf_generator import render_material_issue_pdf


@router.get("/store/transactions/{txn_id}/pdf")
async def material_issue_pdf(txn_id: str,
                              user: dict = Depends(require_permission("inventory", "read"))):
    """Material Issue Slip PDF for any outward / transfer / return inventory txn."""
    txn = await db.inventory_transactions.find_one({"id": txn_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    # Hydrate item name/code/unit for display
    item = await db.inventory.find_one({"id": txn.get("item_id")}, {"_id": 0}) or {}
    slip = {
        **txn,
        "item_name": txn.get("item_name") or item.get("name"),
        "item_code": txn.get("item_code") or item.get("code"),
        "unit": txn.get("unit") or item.get("unit") or "Nos",
        "type": txn.get("txn_type"),
        "purpose": txn.get("note") or txn.get("purpose"),
        "issued_to": txn.get("issued_to") or txn.get("to_location"),
        "issue_date": (txn.get("created_at") or "")[:10],
        "slip_no": txn.get("txn_no") or txn.get("id"),
    }
    pdf = render_material_issue_pdf(slip)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="MIS-{txn.get("txn_no") or txn_id}.pdf"'},
    )
