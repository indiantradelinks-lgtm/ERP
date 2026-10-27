"""Procurement Phase B — Material/Asset Allocation, Asset Lifecycle, Challans.

Collections introduced here:
  * material_allocations  — issue/return of materials, tools, consumables and assets
  * asset_depreciations   — depreciation history per asset (any method)
  * asset_amcs            — Annual Maintenance Contracts per asset
  * asset_calibrations    — calibration logs per asset
  * challans              — Delivery / Return / Inter-site Transfer / Vendor Return

Side-effects:
  * Issue creates an `inventory_transactions` outward row and decrements `inventory.quantity`
  * Return creates an `inventory_transactions` inward row and increments `inventory.quantity`
  * Inter-site transfer challans optionally debit src + credit dst inventories
"""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id, logger
from audit import audit
from sequences import next_sequence
from offload import run_blocking

router = APIRouter(tags=["procurement-phase-b"])


def _ip(request: Request) -> str:
    # k8s ingress puts the real client IP in X-Forwarded-For; honour the first
    # hop when present, otherwise fall back to the direct peer.
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Material / Asset allocations
# ──────────────────────────────────────────────────────────────────────────────
ALLOCATION_KINDS = ("material", "tool", "consumable", "asset")
ALLOC_STATUSES = ("issued", "returned", "partially_returned", "written_off")


class AllocateIn(BaseModel):
    kind: str = "material"               # material | tool | consumable | asset
    item_id: Optional[str] = None        # inventory item id (or asset id for kind='asset')
    item_name: str
    quantity: float = 1
    unit: str = "Nos"
    allocated_to_type: str = "project"   # project | site | department | employee
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_id: Optional[str] = None
    site_code: Optional[str] = None
    department: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    issue_date: Optional[str] = None
    expected_return_date: Optional[str] = None
    returnable: bool = True
    condition_on_issue: Optional[str] = None
    remarks: Optional[str] = None


class ReturnIn(BaseModel):
    returned_qty: float
    condition_on_return: Optional[str] = None
    remarks: Optional[str] = None


@router.get("/allocations")
async def list_allocations(status: Optional[str] = None,
                           project_id: Optional[str] = None,
                           employee_id: Optional[str] = None,
                           user: dict = Depends(require_permission("material_allocations", "read"))):
    q: dict = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    if employee_id:
        q["employee_id"] = employee_id
    from scope import allowed_project_ids
    allowed = await allowed_project_ids(user)
    if allowed is not None:
        projs = await db.projects.find({"id": {"$in": allowed}}, {"_id": 0, "code": 1, "name": 1}).to_list(500)
        tokens = [t for p in projs for t in (p.get("code"), p.get("name")) if t]
        clause = {"$or": [{"allocated_to_type": {"$ne": "project"}},
                          {"project_id": {"$in": allowed}},
                          {"project_code": {"$in": tokens}}]}
        q = {"$and": [q, clause]} if q else clause
    rows = await db.material_allocations.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.get("/allocations/export")
async def export_allocations(fmt: str = "xlsx", status: Optional[str] = None,
                             project_id: Optional[str] = None, employee_id: Optional[str] = None,
                             q: Optional[str] = None, kind: Optional[str] = None,
                             user: dict = Depends(require_permission("material_allocations", "read"))):
    """Project-wise material / asset allocation report (xlsx | csv | pdf).
    Honours exactly the filters the list screen is showing."""
    if fmt not in ("xlsx", "csv", "pdf"):
        raise HTTPException(status_code=400, detail="fmt must be xlsx, csv or pdf")
    rows = await list_allocations(status=status, project_id=project_id, employee_id=employee_id, user=user)
    if kind:
        rows = [r for r in rows if (r.get("kind") or "") == kind]
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if any(needle in str(r.get(f) or "").lower() for f in
                                       ("allocation_no", "item_name", "kind", "project_code", "site_code",
                                        "employee_name", "department", "status"))]

    names: Dict[str, str] = {}
    async for p in db.projects.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1}):
        if p.get("id"):
            names[p["id"]] = p.get("name") or p.get("code") or ""
        if p.get("code"):
            names.setdefault(f"code::{p['code']}", p.get("name") or p["code"])

    groups: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if (r.get("allocated_to_type") or "project") == "project":
            code = r.get("project_code") or ""
            name = names.get(r.get("project_id") or "") or names.get(f"code::{code}") or code or "Unassigned Project"
        else:
            tgt = r.get("employee_name") or r.get("department") or r.get("site_code") or "—"
            name = f"Non-project — {(r.get('allocated_to_type') or '').title()}: {tgt}"
            code = ""
        g = groups.setdefault(name, {"project_name": name, "project_code": code, "items": {},
                                     "issued": 0.0, "returned": 0.0, "net": 0.0, "allocations": 0})
        if code and not g["project_code"]:
            g["project_code"] = code
        issued = float(r.get("quantity") or 0)
        returned = float(r.get("returned_qty") or 0)
        key = f"{r.get('item_name')}|{r.get('kind')}|{r.get('unit')}"
        it = g["items"].setdefault(key, {"item_name": r.get("item_name") or "—", "kind": r.get("kind") or "material",
                                         "unit": r.get("unit") or "Nos", "issued": 0.0, "returned": 0.0,
                                         "net": 0.0, "allocations": 0})
        for tgt_ in (it, g):
            tgt_["issued"] = round(tgt_["issued"] + issued, 3)
            tgt_["returned"] = round(tgt_["returned"] + returned, 3)
            tgt_["net"] = round(tgt_["net"] + issued - returned, 3)
            tgt_["allocations"] += 1

    ordered = sorted(groups.values(), key=lambda g: (-g["net"], g["project_name"]))
    for g in ordered:
        g["items"] = sorted(g["items"].values(), key=lambda i: (-i["net"], i["item_name"]))
    summary = {
        "projects": len(ordered), "allocations": len(rows),
        "issued": round(sum(g["issued"] for g in ordered), 3),
        "returned": round(sum(g["returned"] for g in ordered), 3),
        "net": round(sum(g["net"] for g in ordered), 3),
    }
    applied = [(k, v) for k, v in [("Status", status), ("Kind", kind), ("Search", q),
                                   ("Project", project_id), ("Employee", employee_id)] if v]

    if fmt == "pdf":
        from pdf_generator import render_allocation_report_pdf
        from fastapi.responses import Response
        pdf = await run_blocking(render_allocation_report_pdf, ordered, summary, applied)
        return Response(content=pdf,
                        media_type="application/pdf",
                        headers={"Content-Disposition": 'inline; filename="material-allocations-projectwise.pdf"'})

    headers = ["Project Name", "Project Code", "Material / Asset Name", "Kind", "Unit",
               "Quantity Issued", "Quantity Returned", "Net Issued", "Allocations"]

    if fmt == "csv":
        import csv as _csv
        from io import StringIO
        from fastapi.responses import StreamingResponse
        buf = StringIO()
        w = _csv.writer(buf)
        w.writerow(["Material / Asset Allocations — Project-wise Report"])
        w.writerow(["Filters applied"] + [f"{k}: {v}" for k, v in applied])
        w.writerow([])
        w.writerow(headers)
        for g in ordered:
            for it in g["items"]:
                w.writerow([g["project_name"], g["project_code"], it["item_name"], (it["kind"] or "").title(),
                            it["unit"], it["issued"], it["returned"], it["net"], it["allocations"]])
            w.writerow([f"Total — {g['project_name']}", "", "", "", "", g["issued"], g["returned"], g["net"],
                        g["allocations"]])
        w.writerow(["Grand Total", "", "", "", "", summary["issued"], summary["returned"], summary["net"],
                    summary["allocations"]])
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          'attachment; filename="material-allocations-projectwise.csv"'})

    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from fastapi.responses import Response
    wb = Workbook()

    def _head(ws, hdrs):
        ws.append(hdrs)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="0F172A")
        ws.freeze_panes = "A2"

    ws = wb.active
    ws.title = "Project-wise Allocations"
    _head(ws, headers)
    for g in ordered:
        for it in g["items"]:
            ws.append([g["project_name"], g["project_code"], it["item_name"], (it["kind"] or "").title(),
                       it["unit"], it["issued"], it["returned"], it["net"], it["allocations"]])
        ws.append([f"Total — {g['project_name']}", "", "", "", "", g["issued"], g["returned"], g["net"],
                   g["allocations"]])
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
    ws.append(["Grand Total", "", "", "", "", summary["issued"], summary["returned"], summary["net"],
               summary["allocations"]])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F172A")
    for i, wd in enumerate([34, 16, 34, 14, 10, 16, 18, 14, 12], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = wd

    s2 = wb.create_sheet("Project Summary")
    _head(s2, ["Project Name", "Project Code", "Distinct Items", "Total Quantity Issued",
               "Total Returned", "Net Issued", "Allocations"])
    for g in ordered:
        s2.append([g["project_name"], g["project_code"], len(g["items"]), g["issued"], g["returned"],
                   g["net"], g["allocations"]])
    s2.append(["Grand Total", "", "", summary["issued"], summary["returned"], summary["net"],
               summary["allocations"]])
    for c in s2[s2.max_row]:
        c.font = Font(bold=True)
    for i, wd in enumerate([34, 16, 14, 20, 16, 14, 12], start=1):
        s2.column_dimensions[s2.cell(row=1, column=i).column_letter].width = wd

    s3 = wb.create_sheet("Allocation Detail")
    _head(s3, ["ALC #", "Issue Date", "Project Name", "Project Code", "Allocated To", "Material / Asset Name",
               "Kind", "Unit", "Quantity Issued", "Quantity Returned", "Status", "Return Due", "Remarks"])
    for r in rows:
        code = r.get("project_code") or ""
        pname = (names.get(r.get("project_id") or "") or names.get(f"code::{code}") or code
                 if (r.get("allocated_to_type") or "project") == "project" else "")
        s3.append([r.get("allocation_no"), (r.get("issue_date") or "")[:10], pname, code,
                   r.get("employee_name") or r.get("department") or r.get("site_code") or
                   (r.get("allocated_to_type") or "").title(),
                   r.get("item_name"), (r.get("kind") or "").title(), r.get("unit") or "Nos",
                   float(r.get("quantity") or 0), float(r.get("returned_qty") or 0),
                   (r.get("status") or "").replace("_", " ").title(),
                   (r.get("expected_return_date") or "")[:10], r.get("remarks") or ""])
    for i, wd in enumerate([18, 12, 30, 14, 22, 30, 12, 8, 16, 18, 18, 12, 30], start=1):
        s3.column_dimensions[s3.cell(row=1, column=i).column_letter].width = wd

    s4 = wb.create_sheet("Filters")
    s4.append(["Report", "Material / Asset Allocations — Project-wise"])
    for k, v in applied or [("Filters", "None — all allocations")]:
        s4.append([k, str(v)])
    s4.column_dimensions["A"].width = 22
    s4.column_dimensions["B"].width = 40

    buf = BytesIO()
    wb.save(buf)
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition":
                             'attachment; filename="material-allocations-projectwise.xlsx"'})


@router.post("/allocations")
async def create_allocation(payload: AllocateIn, request: Request,
                            user: dict = Depends(require_permission("material_allocations", "write"))):
    if payload.kind not in ALLOCATION_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {ALLOCATION_KINDS}")
    if payload.allocated_to_type not in ("project", "site", "department", "employee"):
        raise HTTPException(status_code=400, detail="allocated_to_type must be project|site|department|employee")
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0")
    if payload.allocated_to_type == "project" and payload.project_id:
        from scope import ensure_project_access
        await ensure_project_access(user, payload.project_id)

    # Stock guard (skip when no item_id — virtual line)
    # Race-safe: conditional update that requires quantity to be sufficient.
    if payload.item_id and payload.kind in ("material", "tool", "consumable"):
        item = await db.inventory.find_one({"id": payload.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail="Inventory item not found")
        res = await db.inventory.update_one(
            {"id": payload.item_id, "quantity": {"$gte": payload.quantity}},
            {"$inc": {"quantity": -payload.quantity}},
        )
        if res.matched_count == 0:
            avail = float(item.get("quantity") or 0)
            raise HTTPException(status_code=400, detail=f"Insufficient stock — only {avail:g} {item.get('unit') or ''} available")

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["allocation_no"] = await next_sequence("ALC")
    doc["issue_date"] = payload.issue_date or now_iso()[:10]
    doc["status"] = "issued"
    doc["returned_qty"] = 0.0
    doc["actual_return_date"] = None
    doc["issued_by"] = user.get("name") or user.get("email")
    doc["issued_by_id"] = user["id"]
    doc["created_at"] = now_iso()
    await db.material_allocations.insert_one(doc)
    doc.pop("_id", None)

    # Inventory outward (decrement already applied in guard above for race-safety)
    if payload.item_id and payload.kind in ("material", "tool", "consumable"):
        await db.inventory_transactions.insert_one({
            "id": new_id(),
            "txn_type": "outward",
            "item_id": payload.item_id,
            "item_name": payload.item_name,
            "quantity": payload.quantity,
            "unit": payload.unit,
            "issued_to": payload.employee_name or payload.project_code or payload.site_code or payload.department,
            "note": f"Allocation {doc['allocation_no']}",
            "ref_type": "material_allocation",
            "ref_id": doc["id"],
            "status": "posted",
            "created_by": user["id"],
            "created_at": now_iso(),
        })
    # Asset linkage — stamp on asset
    if payload.kind == "asset" and payload.item_id:
        await db.assets.update_one(
            {"id": payload.item_id},
            {"$set": {"allocated_to_type": payload.allocated_to_type,
                      "allocated_to": payload.employee_name or payload.project_code or payload.site_code or payload.department,
                      "allocation_id": doc["id"], "allocation_no": doc["allocation_no"]}},
        )

    await audit(user=user, action="issue", resource="material_allocations", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


class BulkAllocLine(BaseModel):
    item_id: Optional[str] = None
    item_name: str
    kind: str = "material"
    category: Optional[str] = None
    quantity: float = 1
    unit: str = "Nos"
    condition_on_issue: Optional[str] = None


class BulkAllocateIn(BaseModel):
    """Issue many stock items to one project / site / department / employee in one go."""
    lines: List[BulkAllocLine] = Field(default_factory=list)
    allocated_to_type: str = "project"
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_id: Optional[str] = None
    site_code: Optional[str] = None
    department: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    issue_date: Optional[str] = None
    expected_return_date: Optional[str] = None
    returnable: bool = True
    remarks: Optional[str] = None


@router.post("/allocations/bulk")
async def create_allocations_bulk(payload: BulkAllocateIn, request: Request,
                                  user: dict = Depends(require_permission("material_allocations", "write"))):
    if not payload.lines:
        raise HTTPException(status_code=400, detail="Select at least one item to issue")
    if payload.allocated_to_type not in ("project", "site", "department", "employee"):
        raise HTTPException(status_code=400, detail="allocated_to_type must be project|site|department|employee")
    if payload.allocated_to_type == "project":
        if not (payload.project_id or payload.project_code):
            raise HTTPException(status_code=400, detail="Select the project to issue against")
        if payload.project_id:
            from scope import ensure_project_access
            await ensure_project_access(user, payload.project_id)

    # 1) Validate every line up-front so nothing is issued on a bad batch
    errors: List[str] = []
    for ln in payload.lines:
        if ln.kind not in ALLOCATION_KINDS:
            errors.append(f"{ln.item_name}: kind must be one of {ALLOCATION_KINDS}")
            continue
        if ln.quantity <= 0:
            errors.append(f"{ln.item_name}: quantity must be > 0")
            continue
        if ln.item_id and ln.kind in ("material", "tool", "consumable"):
            item = await db.inventory.find_one({"id": ln.item_id}, {"_id": 0, "quantity": 1, "unit": 1})
            if not item:
                errors.append(f"{ln.item_name}: inventory item not found")
            elif float(item.get("quantity") or 0) < ln.quantity:
                errors.append(f"{ln.item_name}: only {float(item.get('quantity') or 0):g} "
                              f"{item.get('unit') or ''} in stock")
    if errors:
        raise HTTPException(status_code=400, detail=" · ".join(errors[:8]))

    batch_id = new_id()
    batch_no = await next_sequence("BIS")
    target = (payload.employee_name or payload.project_code or payload.site_code or payload.department)
    by_name = user.get("name") or user.get("email")
    created: List[dict] = []
    decremented: List[tuple[str, float]] = []
    try:
        for ln in payload.lines:
            if ln.item_id and ln.kind in ("material", "tool", "consumable"):
                res = await db.inventory.update_one(
                    {"id": ln.item_id, "quantity": {"$gte": ln.quantity}},
                    {"$inc": {"quantity": -ln.quantity}})
                if res.matched_count == 0:
                    raise HTTPException(status_code=400,
                                        detail=f"{ln.item_name}: stock changed while issuing — batch cancelled")
                decremented.append((ln.item_id, ln.quantity))

            doc = {
                "id": new_id(), "allocation_no": await next_sequence("ALC"),
                "kind": ln.kind, "item_id": ln.item_id, "item_name": ln.item_name,
                "category": ln.category, "quantity": ln.quantity, "unit": ln.unit,
                "allocated_to_type": payload.allocated_to_type,
                "project_id": payload.project_id, "project_code": payload.project_code,
                "site_id": payload.site_id, "site_code": payload.site_code,
                "department": payload.department,
                "employee_id": payload.employee_id, "employee_name": payload.employee_name,
                "issue_date": payload.issue_date or now_iso()[:10],
                "expected_return_date": payload.expected_return_date,
                "returnable": payload.returnable,
                "condition_on_issue": ln.condition_on_issue,
                "remarks": payload.remarks,
                "status": "issued", "returned_qty": 0.0, "actual_return_date": None,
                "bulk_batch_id": batch_id, "bulk_issue_no": batch_no,
                "issued_by": by_name, "issued_by_id": user["id"], "created_at": now_iso(),
            }
            await db.material_allocations.insert_one(dict(doc))
            created.append(doc)

            if ln.item_id and ln.kind in ("material", "tool", "consumable"):
                await db.inventory_transactions.insert_one({
                    "id": new_id(), "txn_type": "outward", "item_id": ln.item_id,
                    "item_name": ln.item_name, "quantity": ln.quantity, "unit": ln.unit,
                    "issued_to": target, "note": f"Bulk issue {batch_no} · {doc['allocation_no']}",
                    "ref_type": "material_allocation", "ref_id": doc["id"], "status": "posted",
                    "created_by": user["id"], "created_at": now_iso()})
            if ln.kind == "asset" and ln.item_id:
                await db.assets.update_one({"id": ln.item_id}, {"$set": {
                    "allocated_to_type": payload.allocated_to_type, "allocated_to": target,
                    "allocation_id": doc["id"], "allocation_no": doc["allocation_no"]}})
    except Exception:
        for item_id, qty in decremented:            # give the stock back
            await db.inventory.update_one({"id": item_id}, {"$inc": {"quantity": qty}})
        if created:
            await db.material_allocations.delete_many({"bulk_batch_id": batch_id})
            await db.inventory_transactions.delete_many({"ref_id": {"$in": [c["id"] for c in created]}})
        raise

    await audit(user=user, action="bulk_issue", resource="material_allocations", record_id=batch_id,
                after={"bulk_issue_no": batch_no, "lines": len(created), "allocated_to": target,
                       "allocation_nos": [c["allocation_no"] for c in created]}, ip=_ip(request))
    return {"bulk_issue_no": batch_no, "batch_id": batch_id, "count": len(created),
            "allocations": created}


@router.post("/allocations/{alloc_id}/return")
async def record_return(alloc_id: str, payload: ReturnIn, request: Request,
                        user: dict = Depends(require_permission("material_allocations", "write"))):
    alloc = await db.material_allocations.find_one({"id": alloc_id}, {"_id": 0})
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")
    if not alloc.get("returnable"):
        raise HTTPException(status_code=400, detail="This allocation was issued as non-returnable")
    if alloc.get("status") in ("returned", "written_off"):
        raise HTTPException(status_code=400, detail=f"Allocation already {alloc.get('status')}")
    if payload.returned_qty <= 0:
        raise HTTPException(status_code=400, detail="returned_qty must be > 0")
    remaining = float(alloc.get("quantity") or 0) - float(alloc.get("returned_qty") or 0)
    if payload.returned_qty > remaining + 1e-6:
        raise HTTPException(status_code=400, detail=f"Cannot return more than outstanding ({remaining:g})")
    # Asset is a single-unit entity — partial returns are nonsensical.
    if alloc.get("kind") == "asset" and abs(payload.returned_qty - float(alloc.get("quantity") or 0)) > 1e-6:
        raise HTTPException(status_code=400, detail="Asset allocations must be returned in full (single unit)")

    new_returned = float(alloc.get("returned_qty") or 0) + payload.returned_qty
    new_status = "returned" if abs(new_returned - float(alloc["quantity"])) < 1e-6 else "partially_returned"
    update = {
        "returned_qty": new_returned,
        "status": new_status,
        "condition_on_return": payload.condition_on_return,
        "return_remarks": payload.remarks,
        "actual_return_date": now_iso()[:10] if new_status == "returned" else alloc.get("actual_return_date"),
        "updated_at": now_iso(),
    }
    await db.material_allocations.update_one({"id": alloc_id}, {"$set": update})

    if alloc.get("item_id") and alloc.get("kind") in ("material", "tool", "consumable"):
        await db.inventory.update_one({"id": alloc["item_id"]}, {"$inc": {"quantity": payload.returned_qty}})
        await db.inventory_transactions.insert_one({
            "id": new_id(),
            "txn_type": "inward",
            "item_id": alloc["item_id"],
            "item_name": alloc.get("item_name"),
            "quantity": payload.returned_qty,
            "unit": alloc.get("unit"),
            "received_from": alloc.get("employee_name") or alloc.get("project_code"),
            "note": f"Return of {alloc['allocation_no']}",
            "ref_type": "material_allocation_return",
            "ref_id": alloc_id,
            "status": "posted",
            "created_by": user["id"],
            "created_at": now_iso(),
        })
    # Reset asset linkage when fully returned
    if alloc.get("kind") == "asset" and new_status == "returned" and alloc.get("item_id"):
        await db.assets.update_one(
            {"id": alloc["item_id"]},
            {"$set": {"allocated_to_type": None, "allocated_to": None, "allocation_id": None, "allocation_no": None}},
        )

    row = await db.material_allocations.find_one({"id": alloc_id}, {"_id": 0})
    await audit(user=user, action="return", resource="material_allocations", record_id=alloc_id, after=row, ip=_ip(request))
    return row


@router.delete("/allocations/{alloc_id}")
async def delete_allocation(alloc_id: str, request: Request,
                            user: dict = Depends(require_permission("material_allocations", "delete"))):
    alloc = await db.material_allocations.find_one({"id": alloc_id}, {"_id": 0})
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")
    if alloc.get("status") not in ("issued",):
        raise HTTPException(status_code=400, detail="Cannot delete an allocation that has return activity")
    # Reverse stock if inventory item
    if alloc.get("item_id") and alloc.get("kind") in ("material", "tool", "consumable"):
        await db.inventory.update_one({"id": alloc["item_id"]}, {"$inc": {"quantity": float(alloc.get("quantity") or 0)}})
    await db.material_allocations.delete_one({"id": alloc_id})
    await audit(user=user, action="delete", resource="material_allocations", record_id=alloc_id, before=alloc, ip=_ip(request))
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Asset Lifecycle — depreciation, AMC, calibration, warranty
# ──────────────────────────────────────────────────────────────────────────────
class DepreciationIn(BaseModel):
    period: str                  # YYYY-MM (one entry per period)
    method: str = "straight_line"  # straight_line | wdv | units_of_use
    opening_value: float
    depreciation: float
    closing_value: float
    note: Optional[str] = None


class AmcIn(BaseModel):
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    start_date: str
    end_date: str
    amount: float = 0
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    coverage: Optional[str] = None
    note: Optional[str] = None


class CalibrationIn(BaseModel):
    calibrated_by: str
    calibration_date: str
    next_due_date: Optional[str] = None
    result: str = "pass"           # pass | fail | conditional
    certificate_file_id: Optional[str] = None
    note: Optional[str] = None


class WarrantyIn(BaseModel):
    warranty_vendor: Optional[str] = None
    warranty_start: Optional[str] = None
    warranty_expiry: Optional[str] = None
    warranty_terms: Optional[str] = None


@router.get("/assets/{asset_id}/lifecycle")
async def asset_lifecycle(asset_id: str, user: dict = Depends(require_permission("asset_lifecycle", "read"))):
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    dep = await db.asset_depreciations.find({"asset_id": asset_id}, {"_id": 0}).sort("period", 1).to_list(120)
    amcs = await db.asset_amcs.find({"asset_id": asset_id}, {"_id": 0}).sort("start_date", -1).to_list(50)
    cal = await db.asset_calibrations.find({"asset_id": asset_id}, {"_id": 0}).sort("calibration_date", -1).to_list(50)
    return {
        "asset": asset,
        "depreciation": dep,
        "amcs": amcs,
        "calibrations": cal,
        "warranty": {
            "vendor": asset.get("warranty_vendor"),
            "start": asset.get("warranty_start"),
            "expiry": asset.get("warranty_expiry"),
            "terms": asset.get("warranty_terms"),
        },
    }


@router.post("/assets/{asset_id}/depreciation")
async def add_depreciation(asset_id: str, payload: DepreciationIn, request: Request,
                           user: dict = Depends(require_permission("asset_lifecycle", "write"))):
    if not await db.assets.find_one({"id": asset_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Asset not found")
    # Upsert by (asset_id, period) so duplicates can't accumulate.
    existing = await db.asset_depreciations.find_one({"asset_id": asset_id, "period": payload.period}, {"_id": 0})
    doc = payload.model_dump()
    if existing:
        doc["id"] = existing["id"]
        doc["asset_id"] = asset_id
        doc["created_by"] = existing.get("created_by") or user["id"]
        doc["created_at"] = existing.get("created_at") or now_iso()
        doc["updated_at"] = now_iso()
        await db.asset_depreciations.update_one({"asset_id": asset_id, "period": payload.period}, {"$set": doc})
    else:
        doc["id"] = new_id()
        doc["asset_id"] = asset_id
        doc["created_by"] = user["id"]
        doc["created_at"] = now_iso()
        await db.asset_depreciations.insert_one(doc)
    doc.pop("_id", None)
    await db.assets.update_one({"id": asset_id},
                               {"$set": {"current_book_value": payload.closing_value, "last_dep_period": payload.period}})
    await audit(user=user, action="depreciate", resource="asset_lifecycle", record_id=asset_id, after=doc, ip=_ip(request))
    return doc


@router.post("/assets/{asset_id}/amc")
async def add_amc(asset_id: str, payload: AmcIn, request: Request,
                  user: dict = Depends(require_permission("asset_lifecycle", "write"))):
    if not await db.assets.find_one({"id": asset_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Asset not found")
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["asset_id"] = asset_id
    doc["status"] = "active"
    doc["created_by"] = user["id"]
    doc["created_at"] = now_iso()
    await db.asset_amcs.insert_one(doc)
    doc.pop("_id", None)
    await db.assets.update_one({"id": asset_id}, {"$set": {"amc_active": True, "amc_expiry": payload.end_date}})
    await audit(user=user, action="amc", resource="asset_lifecycle", record_id=asset_id, after=doc, ip=_ip(request))
    return doc


@router.post("/assets/{asset_id}/calibration")
async def add_calibration(asset_id: str, payload: CalibrationIn, request: Request,
                          user: dict = Depends(require_permission("asset_lifecycle", "write"))):
    if not await db.assets.find_one({"id": asset_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Asset not found")
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["asset_id"] = asset_id
    doc["created_by"] = user["id"]
    doc["created_at"] = now_iso()
    await db.asset_calibrations.insert_one(doc)
    doc.pop("_id", None)
    await db.assets.update_one({"id": asset_id},
                               {"$set": {"last_calibration_date": payload.calibration_date,
                                         "next_calibration_due": payload.next_due_date}})
    await audit(user=user, action="calibrate", resource="asset_lifecycle", record_id=asset_id, after=doc, ip=_ip(request))
    return doc


@router.put("/assets/{asset_id}/warranty")
async def set_warranty(asset_id: str, payload: WarrantyIn, request: Request,
                       user: dict = Depends(require_permission("asset_lifecycle", "write"))):
    if not await db.assets.find_one({"id": asset_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Asset not found")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    update["updated_at"] = now_iso()
    await db.assets.update_one({"id": asset_id}, {"$set": update})
    row = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    await audit(user=user, action="warranty", resource="asset_lifecycle", record_id=asset_id, after=row, ip=_ip(request))
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Challans
# ──────────────────────────────────────────────────────────────────────────────
CHALLAN_TYPES = ("delivery", "return", "inter_site_transfer", "vendor_return")
CHALLAN_STATUSES = ("draft", "dispatched", "in_transit", "received", "cancelled")


class ChallanItemIn(BaseModel):
    item_id: Optional[str] = None
    name: str
    quantity: float
    unit: str = "Nos"
    serial_no: Optional[str] = None
    batch: Optional[str] = None


class ChallanIn(BaseModel):
    type: str                      # delivery | return | inter_site_transfer | vendor_return
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    from_site_id: Optional[str] = None
    to_site_id: Optional[str] = None
    vendor_id: Optional[str] = None
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    transporter: Optional[str] = None
    eway_bill_no: Optional[str] = None
    dispatch_at: Optional[str] = None
    items: List[ChallanItemIn]
    remarks: Optional[str] = None


class ChallanReceiveIn(BaseModel):
    receiver_name: str = Field(..., min_length=1)
    received_at: Optional[str] = None
    received_remarks: Optional[str] = None


@router.get("/challans")
async def list_challans(type: Optional[str] = None, status: Optional[str] = None,
                        user: dict = Depends(require_permission("challans", "read"))):
    q: dict = {}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    rows = await db.challans.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/challans/{challan_id}")
async def get_challan(challan_id: str, user: dict = Depends(require_permission("challans", "read"))):
    row = await db.challans.find_one({"id": challan_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Challan not found")
    return row


@router.post("/challans")
async def create_challan(payload: ChallanIn, request: Request,
                         user: dict = Depends(require_permission("challans", "write"))):
    if payload.type not in CHALLAN_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {CHALLAN_TYPES}")
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["challan_no"] = await next_sequence("CH")
    doc["status"] = "dispatched" if payload.dispatch_at else "draft"
    doc["dispatched_at"] = payload.dispatch_at
    doc["received_at"] = None
    doc["receiver_name"] = None
    doc["created_by"] = user["id"]
    doc["created_by_name"] = user.get("name") or user.get("email")
    doc["created_at"] = now_iso()
    # QR payload — the frontend renders this as an actual QR code image
    doc["qr_payload"] = f"CHALLAN:{doc['challan_no']}|{doc['id']}"
    await db.challans.insert_one(doc)
    doc.pop("_id", None)

    # Inter-site transfer — race-safe debit of source inventory immediately.
    if payload.type == "inter_site_transfer":
        for it in payload.items:
            if it.item_id:
                res = await db.inventory.update_one(
                    {"id": it.item_id, "quantity": {"$gte": it.quantity}},
                    {"$inc": {"quantity": -it.quantity}},
                )
                if res.matched_count == 0:
                    # Rollback: delete the challan and any partial transfer_out rows.
                    await db.challans.delete_one({"id": doc["id"]})
                    await db.inventory_transactions.delete_many({"ref_id": doc["id"]})
                    item = await db.inventory.find_one({"id": it.item_id}, {"_id": 0}) or {}
                    raise HTTPException(status_code=400, detail=f"Insufficient stock for {it.name} — only {float(item.get('quantity') or 0):g} available")
                await db.inventory_transactions.insert_one({
                    "id": new_id(),
                    "txn_type": "transfer_out",
                    "item_id": it.item_id,
                    "item_name": it.name,
                    "quantity": it.quantity,
                    "unit": it.unit,
                    "note": f"Challan {doc['challan_no']} → {payload.to_location or 'site'}",
                    "ref_type": "challan",
                    "ref_id": doc["id"],
                    "status": "posted",
                    "created_by": user["id"],
                    "created_at": now_iso(),
                })
    await audit(user=user, action="create", resource="challans", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.post("/challans/{challan_id}/receive")
async def receive_challan(challan_id: str, payload: ChallanReceiveIn, request: Request,
                          user: dict = Depends(require_permission("challans", "write"))):
    """Mark a challan as received — records a lightweight e-signature stamp
    (signer name + user_id + IP + timestamp). On inter-site transfers also
    credits the destination inventory.
    """
    challan = await db.challans.find_one({"id": challan_id}, {"_id": 0})
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")
    if challan.get("status") in ("received", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Challan already {challan.get('status')}")

    sig = {
        "name": payload.receiver_name,
        "user_id": user["id"],
        "user_name": user.get("name") or user.get("email"),
        "ip": _ip(request),
        "signed_at": now_iso(),
    }
    await db.challans.update_one(
        {"id": challan_id},
        {"$set": {
            "status": "received",
            "receiver_name": payload.receiver_name,
            "received_at": payload.received_at or now_iso(),
            "received_remarks": payload.received_remarks,
            "e_signature": sig,
            "updated_at": now_iso(),
        }},
    )

    if challan.get("type") == "inter_site_transfer":
        for it in challan.get("items") or []:
            if it.get("item_id"):
                await db.inventory.update_one({"id": it["item_id"]}, {"$inc": {"quantity": float(it["quantity"])}})
                await db.inventory_transactions.insert_one({
                    "id": new_id(),
                    "txn_type": "transfer_in",
                    "item_id": it["item_id"],
                    "item_name": it.get("name"),
                    "quantity": float(it["quantity"]),
                    "unit": it.get("unit"),
                    "note": f"Challan {challan['challan_no']} received",
                    "ref_type": "challan_receive",
                    "ref_id": challan_id,
                    "status": "posted",
                    "created_by": user["id"],
                    "created_at": now_iso(),
                })

    row = await db.challans.find_one({"id": challan_id}, {"_id": 0})
    await audit(user=user, action="receive", resource="challans", record_id=challan_id, after=row, ip=_ip(request))
    return row


@router.delete("/challans/{challan_id}")
async def delete_challan(challan_id: str, request: Request,
                         user: dict = Depends(require_permission("challans", "delete"))):
    challan = await db.challans.find_one({"id": challan_id}, {"_id": 0})
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")
    if challan.get("status") == "received":
        raise HTTPException(status_code=400, detail="Cannot delete a received challan")
    await db.challans.delete_one({"id": challan_id})
    await audit(user=user, action="delete", resource="challans", record_id=challan_id, before=challan, ip=_ip(request))
    return {"ok": True}
