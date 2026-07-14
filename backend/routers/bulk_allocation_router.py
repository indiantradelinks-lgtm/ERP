"""Category-wise bulk material allocation (matrix: items × projects) with approval gate."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence

router = APIRouter()

APPROVER_ROLES = {"super_admin", "general_manager", "director", "dept_head"}


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


class ProjectAllocIn(BaseModel):
    project_id: str
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    qty: float


class BulkLineIn(BaseModel):
    item_id: str
    item_name: str
    unit: str = "Nos"
    allocations: List[ProjectAllocIn]


class BulkRequestIn(BaseModel):
    category: str
    remarks: Optional[str] = None
    lines: List[BulkLineIn]


class RejectIn(BaseModel):
    reason: Optional[str] = None


@router.get("/bulk-alloc/projects")
async def running_projects(all: bool = False,
                           user: dict = Depends(require_permission("material_allocations", "read"))):
    q = {} if all else {"status": {"$in": ["active", "planned"]}}
    rows = await db.projects.find(q, {"_id": 0, "id": 1, "code": 1, "name": 1, "status": 1}).sort("code", 1).to_list(500)
    return rows


@router.get("/bulk-alloc/items")
async def category_items(category: str,
                         user: dict = Depends(require_permission("material_allocations", "read"))):
    rows = await db.inventory.find(
        {"category": category},
        {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1, "uom": 1, "quantity": 1, "min_stock": 1},
    ).sort("code", 1).to_list(1000)
    return rows


async def _validate_lines(lines: List[BulkLineIn]):
    """Strict stock check. Returns {item_id: (item_doc, total_qty)} or raises 400."""
    if not lines:
        raise HTTPException(status_code=400, detail="At least one line with quantities is required")
    result = {}
    for line in lines:
        total = sum(a.qty for a in line.allocations if a.qty)
        if total <= 0:
            raise HTTPException(status_code=400, detail=f"'{line.item_name}': total quantity must be > 0")
        if any(a.qty < 0 for a in line.allocations):
            raise HTTPException(status_code=400, detail=f"'{line.item_name}': negative quantity not allowed")
        item = await db.inventory.find_one({"id": line.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail=f"Inventory item not found: {line.item_name}")
        avail = float(item.get("quantity") or 0)
        if total > avail:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{line.item_name}' — requested {total:g}, available {avail:g}",
            )
        result[line.item_id] = (item, total)
    return result


@router.post("/bulk-alloc/requests")
async def create_bulk_request(payload: BulkRequestIn, request: Request,
                              user: dict = Depends(require_permission("material_allocations", "write"))):
    lines = [l for l in payload.lines if any(a.qty > 0 for a in l.allocations)]
    payload.lines = [
        BulkLineIn(item_id=l.item_id, item_name=l.item_name, unit=l.unit,
                   allocations=[a for a in l.allocations if a.qty > 0])
        for l in lines
    ]
    await _validate_lines(payload.lines)

    doc = {
        "id": new_id(),
        "request_no": await next_sequence("BAL"),
        "category": payload.category,
        "remarks": payload.remarks,
        "lines": [l.model_dump() for l in payload.lines],
        "total_items": len(payload.lines),
        "total_qty": sum(a.qty for l in payload.lines for a in l.allocations),
        "project_ids": sorted({a.project_id for l in payload.lines for a in l.allocations}),
        "status": "pending_approval",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user["id"],
        "created_at": now_iso(),
        "decided_by": None,
        "decided_at": None,
        "decision_reason": None,
        "allocation_ids": [],
    }
    await db.bulk_allocation_requests.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="bulk_allocation_requests", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/bulk-alloc/requests")
async def list_bulk_requests(status: Optional[str] = None,
                             user: dict = Depends(require_permission("material_allocations", "read"))):
    q = {"status": status} if status else {}
    return await db.bulk_allocation_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/bulk-alloc/requests/{req_id}/approve")
async def approve_bulk_request(req_id: str, request: Request,
                               user: dict = Depends(require_permission("material_allocations", "write"))):
    if user.get("role") not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="Only Dept Head / GM / Director / Super Admin can approve bulk allocations")
    req = await db.bulk_allocation_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Request already {req['status']}")

    lines = [BulkLineIn(**l) for l in req["lines"]]
    await _validate_lines(lines)

    # Race-safe conditional decrement per item; rollback all on any failure
    deducted = []
    for line in lines:
        total = sum(a.qty for a in line.allocations)
        res = await db.inventory.update_one(
            {"id": line.item_id, "quantity": {"$gte": total}},
            {"$inc": {"quantity": -total}},
        )
        if res.matched_count == 0:
            for item_id, qty in deducted:
                await db.inventory.update_one({"id": item_id}, {"$inc": {"quantity": qty}})
            raise HTTPException(status_code=400, detail=f"Stock changed — insufficient stock for '{line.item_name}'")
        deducted.append((line.item_id, total))

    issue_date = now_iso()[:10]
    alloc_ids = []
    for line in lines:
        for a in line.allocations:
            alloc = {
                "id": new_id(),
                "allocation_no": await next_sequence("ALC"),
                "kind": "material",
                "item_id": line.item_id,
                "item_name": line.item_name,
                "quantity": a.qty,
                "unit": line.unit,
                "allocated_to_type": "project",
                "project_id": a.project_id,
                "project_code": a.project_code,
                "site_id": None, "site_code": None, "department": None,
                "employee_id": None, "employee_name": None,
                "issue_date": issue_date,
                "expected_return_date": None,
                "returnable": False,
                "condition_on_issue": None,
                "remarks": f"Bulk allocation {req['request_no']} ({req['category']})",
                "status": "issued",
                "returned_qty": 0.0,
                "actual_return_date": None,
                "issued_by": user.get("name") or user.get("email"),
                "issued_by_id": user["id"],
                "bulk_request_id": req_id,
                "created_at": now_iso(),
            }
            await db.material_allocations.insert_one(alloc)
            alloc_ids.append(alloc["id"])
            await db.inventory_transactions.insert_one({
                "id": new_id(),
                "txn_type": "outward",
                "item_id": line.item_id,
                "item_name": line.item_name,
                "quantity": a.qty,
                "unit": line.unit,
                "issued_to": a.project_code or a.project_name or a.project_id,
                "note": f"Bulk allocation {req['request_no']} · {alloc['allocation_no']}",
                "ref_type": "bulk_allocation",
                "ref_id": req_id,
                "status": "posted",
                "created_by": user["id"],
                "created_at": now_iso(),
            })

    upd = {
        "status": "approved",
        "decided_by": user.get("name") or user.get("email"),
        "decided_by_id": user["id"],
        "decided_at": now_iso(),
        "allocation_ids": alloc_ids,
    }
    await db.bulk_allocation_requests.update_one({"id": req_id}, {"$set": upd})
    await audit(user=user, action="approve", resource="bulk_allocation_requests", record_id=req_id, after=upd, ip=_ip(request))
    return {**req, **upd}


@router.post("/bulk-alloc/requests/{req_id}/reject")
async def reject_bulk_request(req_id: str, payload: RejectIn, request: Request,
                              user: dict = Depends(require_permission("material_allocations", "write"))):
    if user.get("role") not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="Only Dept Head / GM / Director / Super Admin can reject bulk allocations")
    req = await db.bulk_allocation_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Request already {req['status']}")
    upd = {
        "status": "rejected",
        "decided_by": user.get("name") or user.get("email"),
        "decided_by_id": user["id"],
        "decided_at": now_iso(),
        "decision_reason": payload.reason,
    }
    await db.bulk_allocation_requests.update_one({"id": req_id}, {"$set": upd})
    await audit(user=user, action="reject", resource="bulk_allocation_requests", record_id=req_id, after=upd, ip=_ip(request))
    return {**req, **upd}


# ─── Project Material Register ───────────────────────────────────────────────

async def _build_register(project_id: str) -> dict:
    project = await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "status": 1, "client_name": 1})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    allocs = await db.material_allocations.find(
        {"allocated_to_type": "project", "project_id": project_id}, {"_id": 0}
    ).to_list(5000)

    item_ids = [a["item_id"] for a in allocs if a.get("item_id")]
    inv = {i["id"]: i for i in await db.inventory.find(
        {"id": {"$in": item_ids}}, {"_id": 0, "id": 1, "code": 1, "category": 1, "rate": 1}
    ).to_list(5000)}

    by_cat: dict = {}
    dates = []
    for a in allocs:
        item = inv.get(a.get("item_id"), {})
        cat = item.get("category") or "Uncategorized"
        key = (a.get("item_id") or a.get("item_name"), a.get("item_name"))
        bucket = by_cat.setdefault(cat, {})
        row = bucket.setdefault(key, {
            "code": item.get("code") or "-", "item_name": a.get("item_name"),
            "unit": a.get("unit") or "Nos", "rate": float(item.get("rate") or 0),
            "issued_qty": 0.0, "returned_qty": 0.0, "allocations": 0, "last_issue_date": "",
        })
        row["issued_qty"] += float(a.get("quantity") or 0)
        row["returned_qty"] += float(a.get("returned_qty") or 0)
        row["allocations"] += 1
        d = a.get("issue_date") or ""
        row["last_issue_date"] = max(row["last_issue_date"], d)
        if d:
            dates.append(d)

    categories = []
    grand_value = grand_issued = 0.0
    for cat in sorted(by_cat):
        items = []
        cat_value = cat_issued = 0.0
        for row in sorted(by_cat[cat].values(), key=lambda r: r["code"]):
            row["net_qty"] = row["issued_qty"] - row["returned_qty"]
            row["value"] = round(row["net_qty"] * row["rate"], 2)
            cat_value += row["value"]
            cat_issued += row["issued_qty"]
            items.append(row)
        categories.append({"category": cat, "items": items,
                           "total_value": round(cat_value, 2), "total_issued": cat_issued})
        grand_value += cat_value
        grand_issued += cat_issued

    return {
        "project": project,
        "categories": categories,
        "grand_total_value": round(grand_value, 2),
        "grand_total_issued": grand_issued,
        "total_allocations": len(allocs),
        "date_from": min(dates) if dates else None,
        "date_to": max(dates) if dates else None,
    }


@router.get("/bulk-alloc/project-register/{project_id}")
async def project_material_register(project_id: str,
                                    user: dict = Depends(require_permission("material_allocations", "read"))):
    return await _build_register(project_id)


@router.get("/bulk-alloc/project-register/{project_id}/export")
async def project_material_register_export(project_id: str,
                                           user: dict = Depends(require_permission("material_allocations", "read"))):
    import io
    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    reg = await _build_register(project_id)
    p = reg["project"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Material Register"

    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="1E3A8A")
    head_font = Font(bold=True, color="FFFFFF")
    cat_fill = PatternFill("solid", fgColor="E2E8F0")

    ws.append(["INDIAN TRADE LINKS — Project Material Register"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Project: {p.get('code')} · {p.get('name')}   |   Status: {p.get('status')}   |   Period: {reg['date_from'] or '-'} to {reg['date_to'] or '-'}"])
    ws.append([])
    header = ["Category", "Code", "Item", "Unit", "Issued Qty", "Returned Qty", "Net Qty", "Rate (INR)", "Value (INR)"]
    ws.append(header)
    for c in ws[ws.max_row]:
        c.font = head_font
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center")

    for cat in reg["categories"]:
        for it in cat["items"]:
            ws.append([cat["category"], it["code"], it["item_name"], it["unit"],
                       it["issued_qty"], it["returned_qty"], it["net_qty"], it["rate"], it["value"]])
        ws.append([f"{cat['category']} — Subtotal", "", "", "", cat["total_issued"], "", "", "", cat["total_value"]])
        for c in ws[ws.max_row]:
            c.font = bold
            c.fill = cat_fill

    ws.append([])
    ws.append(["GRAND TOTAL", "", "", "", reg["grand_total_issued"], "", "", "", reg["grand_total_value"]])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True, size=12)

    widths = [26, 12, 40, 8, 12, 13, 10, 12, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=4, column=i).column_letter].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"material_register_{p.get('code', project_id)}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
