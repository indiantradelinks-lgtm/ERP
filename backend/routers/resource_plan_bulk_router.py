"""Resource Plan bulk tools:
  GET  /api/resource-plan/template?type=material|manpower|tools   → xlsx template per tab
  POST /api/resource-plan/upload/{project_id}?type=...            → xlsx import into project_resources
  POST /api/resource-plan/quick-fill/{project_id}                 → full-list qty entry (0 qty auto-skipped)
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/resource-plan", tags=["resource-plan-bulk"])

PLAN_TYPES = {"material", "manpower", "tools"}

TEMPLATE_COLS = {
    "material": ["category", "item_code_or_name", "quantity", "uom", "unit_rate", "source", "required_by_date", "remarks"],
    "manpower": ["designation", "count_required", "mandays", "daily_rate", "shift", "skill_level", "deploy_from", "deploy_to", "remarks"],
    "tools":    ["tool_category", "tool_code_or_name", "count_required", "days", "daily_rate", "owned_or_rented", "specification", "mobilization_date", "remarks"],
}


def _xlsx_response(wb: Workbook, fname: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/template")
async def plan_template(type: str, user: dict = Depends(require_permission("projects", "read"))):
    if type not in PLAN_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(PLAN_TYPES)}")
    wb = Workbook()
    ws = wb.active
    ws.title = "PLAN"
    ws.append(TEMPLATE_COLS[type])
    inst = wb.create_sheet("INSTRUCTIONS")
    inst.append([f"INDIAN TRADE LINKS ERP — Resource Plan Bulk Upload ({type.title()})"])
    inst.append([])
    inst.append(["1. Fill one row per plan line in the PLAN sheet."])
    inst.append(["2. Rows with quantity/count 0 or blank are automatically skipped."])
    inst.append(["3. Use the REFERENCE sheet for valid categories / items / designations."])
    inst.append(["4. Items not found in the master are added as custom items (material/tools)."])
    inst.append(["5. Save as .xlsx and upload via the Bulk Upload button on the matching tab."])
    ref = wb.create_sheet("REFERENCE")
    if type == "manpower":
        ref.append(["designation_code", "designation_name"])
        for d in await db.hr_designations.find({"active": {"$ne": False}}, {"_id": 0}).sort("name", 1).to_list(500):
            ref.append([d.get("code") or "", d.get("name") or ""])
        ref2 = wb.create_sheet("VALUES")
        ref2.append(["shift", "general / day / night / rotational"])
        ref2.append(["skill_level", "highly_skilled / skilled / semi_skilled / unskilled"])
        ref2.append(["deploy_from / deploy_to", "YYYY-MM-DD"])
    else:
        ref.append(["category", "item_code", "item_name", "uom", "rate"])
        for it in await db.inventory.find({"is_active": {"$ne": False}}, {"_id": 0}).sort([("category", 1), ("code", 1)]).to_list(3000):
            ref.append([it.get("category") or "", it.get("code") or "", it.get("name") or "",
                        it.get("unit") or it.get("uom") or "", it.get("rate") or 0])
        if type == "tools":
            ref2 = wb.create_sheet("VALUES")
            ref2.append(["owned_or_rented", "owned / rented"])
            ref2.append(["mobilization_date", "YYYY-MM-DD"])
    return _xlsx_response(wb, f"resource_plan_{type}_template.xlsx")


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _plan_total(d: dict) -> float:
    from routers.projects_ops_phase2r2_router import _resource_total
    return _resource_total(d)


def _base_doc(project_id: str, rtype: str, user: dict) -> Dict[str, Any]:
    return {
        "id": new_id(), "project_id": project_id, "resource_type": rtype,
        "wbs_id": None, "activity_id": None,
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
    }


@router.post("/upload/{project_id}")
async def plan_upload(project_id: str, type: str, file: UploadFile = File(...),
                       user: dict = Depends(require_permission("projects", "write"))):
    if type not in PLAN_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(PLAN_TYPES)}")
    if not await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read the file — upload a valid .xlsx")
    ws = wb["PLAN"] if "PLAN" in wb.sheetnames else wb.active
    header = [(_s(c.value).lower()) for c in ws[1]]
    col = {name: i for i, name in enumerate(header) if name}
    expected = TEMPLATE_COLS[type]
    if expected[0] not in col and expected[1] not in col:
        raise HTTPException(status_code=400, detail=f"Wrong template — expected columns like: {', '.join(expected[:4])} …")

    cats = {c["name"].lower(): c["name"] for c in await db.inv_categories.find({}, {"_id": 0, "name": 1}).to_list(500)}
    items = await db.inventory.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1, "uom": 1, "rate": 1, "category": 1}).to_list(5000)
    item_by_code = {(_s(i.get("code")).lower()): i for i in items if i.get("code")}
    item_by_name = {(_s(i.get("name")).lower()): i for i in items if i.get("name")}
    desigs = await db.hr_designations.find({}, {"_id": 0}).to_list(500)
    desig_lookup = {}
    for d in desigs:
        for k in (d.get("name"), d.get("code")):
            if k:
                desig_lookup[_s(k).lower()] = d

    def cell(row, name):
        idx = col.get(name)
        return row[idx] if idx is not None and idx < len(row) else None

    created, skipped_zero = 0, 0
    errors: List[Dict[str, Any]] = []
    docs: List[Dict[str, Any]] = []

    for rn, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(v is None or _s(v) == "" for v in row):
            continue
        if type == "manpower":
            qty = _num(cell(row, "count_required"))
            if qty <= 0:
                skipped_zero += 1
                continue
            dname = _s(cell(row, "designation"))
            d = desig_lookup.get(dname.lower())
            if not d:
                errors.append({"row": rn, "error": f"Unknown designation '{dname}'"})
                continue
            doc = _base_doc(project_id, "manpower", user)
            doc.update({
                "designation_id": d["id"], "designation_name": d.get("name"),
                "count_required": qty, "mandays": _num(cell(row, "mandays")),
                "daily_rate": _num(cell(row, "daily_rate")),
                "shift": _s(cell(row, "shift")).lower() or "general",
                "skill_level": _s(cell(row, "skill_level")).lower(),
                "deploy_from": _s(cell(row, "deploy_from")), "deploy_to": _s(cell(row, "deploy_to")),
                "remarks": _s(cell(row, "remarks")),
            })
        elif type == "material":
            qty = _num(cell(row, "quantity"))
            if qty <= 0:
                skipped_zero += 1
                continue
            cat_raw = _s(cell(row, "category"))
            cat = cats.get(cat_raw.lower())
            if not cat:
                errors.append({"row": rn, "error": f"Unknown category '{cat_raw}'"})
                continue
            ref = _s(cell(row, "item_code_or_name"))
            if not ref:
                errors.append({"row": rn, "error": "item_code_or_name is required"})
                continue
            it = item_by_code.get(ref.lower()) or item_by_name.get(ref.lower())
            doc = _base_doc(project_id, "material", user)
            doc.update({
                "category": cat,
                "item_id": it.get("id") if it else None,
                "item_code": (it or {}).get("code") or "",
                "item_name": (it or {}).get("name") or ref,
                "uom": _s(cell(row, "uom")) or (it or {}).get("unit") or (it or {}).get("uom") or "Nos",
                "quantity": qty,
                "unit_rate": _num(cell(row, "unit_rate")) or _num((it or {}).get("rate")),
                "source": _s(cell(row, "source")).lower() or "stock",
                "required_by_date": _s(cell(row, "required_by_date")),
                "remarks": _s(cell(row, "remarks")),
            })
        else:  # tools
            qty = _num(cell(row, "count_required"))
            if qty <= 0:
                skipped_zero += 1
                continue
            ref = _s(cell(row, "tool_code_or_name"))
            if not ref:
                errors.append({"row": rn, "error": "tool_code_or_name is required"})
                continue
            it = item_by_code.get(ref.lower()) or item_by_name.get(ref.lower())
            cat_raw = _s(cell(row, "tool_category"))
            doc = _base_doc(project_id, "tools", user)
            doc.update({
                "tool_item_id": it.get("id") if it else None,
                "tool_name": (it or {}).get("name") or ref,
                "tool_category": cats.get(cat_raw.lower()) or (it or {}).get("category") or cat_raw,
                "count_required": qty, "days": _num(cell(row, "days")),
                "daily_rate": _num(cell(row, "daily_rate")),
                "tool_owned_or_rented": _s(cell(row, "owned_or_rented")).lower() or "owned",
                "specification": _s(cell(row, "specification")),
                "mobilization_date": _s(cell(row, "mobilization_date")),
                "remarks": _s(cell(row, "remarks")),
            })
        doc["total_cost"] = _plan_total(doc)
        docs.append(doc)

    for doc in docs:
        await db.project_resources.insert_one(doc)
        created += 1
    await audit(user=user, action="bulk_upload", resource="project_resources", record_id=project_id,
                after={"type": type, "created": created, "skipped_zero": skipped_zero, "errors": len(errors)}, ip="resource-plan")
    return {"ok": True, "created": created, "skipped_zero": skipped_zero, "errors": errors}


class QuickLine(BaseModel):
    kind: Literal["item", "manpower"]
    ref_id: str
    quantity: float = 0


class QuickFillIn(BaseModel):
    mode: Literal["plan", "request"] = "plan"
    lines: List[QuickLine] = Field(..., min_length=1, max_length=2000)


@router.post("/quick-fill/{project_id}")
async def quick_fill(project_id: str, payload: QuickFillIn,
                      user: dict = Depends(require_permission("projects", "write"))):
    if not await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Project not found")
    active = [l for l in payload.lines if l.quantity > 0]
    skipped_zero = len(payload.lines) - len(active)
    if not active:
        raise HTTPException(status_code=400, detail="All quantities are 0 — nothing to add")
    if len(active) > 50 and payload.mode == "request":
        raise HTTPException(status_code=400, detail="Max 50 request lines at once — reduce non-zero quantities or use Plan mode")

    item_ids = [l.ref_id for l in active if l.kind == "item"]
    desig_ids = [l.ref_id for l in active if l.kind == "manpower"]
    items = {i["id"]: i for i in await db.inventory.find({"id": {"$in": item_ids}}, {"_id": 0}).to_list(2000)}
    desigs = {d["id"]: d for d in await db.hr_designations.find({"id": {"$in": desig_ids}}, {"_id": 0}).to_list(500)}
    missing = [l.ref_id for l in active if (l.kind == "item" and l.ref_id not in items) or (l.kind == "manpower" and l.ref_id not in desigs)]
    if missing:
        raise HTTPException(status_code=404, detail=f"{len(missing)} selected row(s) no longer exist in the master")

    if payload.mode == "plan":
        created = 0
        for l in active:
            if l.kind == "manpower":
                d = desigs[l.ref_id]
                doc = _base_doc(project_id, "manpower", user)
                doc.update({"designation_id": d["id"], "designation_name": d.get("name"),
                             "count_required": l.quantity, "mandays": 0, "daily_rate": 0,
                             "shift": "general", "skill_level": ""})
            else:
                it = items[l.ref_id]
                cat = it.get("category") or ""
                if "tool" in cat.lower():
                    doc = _base_doc(project_id, "tools", user)
                    doc.update({"tool_item_id": it["id"], "tool_name": it.get("name"),
                                 "tool_category": cat, "count_required": l.quantity,
                                 "days": 0, "daily_rate": 0, "tool_owned_or_rented": "owned"})
                else:
                    doc = _base_doc(project_id, "material", user)
                    doc.update({"item_id": it["id"], "item_code": it.get("code") or "",
                                 "item_name": it.get("name"), "category": cat,
                                 "uom": it.get("unit") or it.get("uom") or "Nos",
                                 "quantity": l.quantity, "unit_rate": _num(it.get("rate")), "source": "stock"})
            doc["total_cost"] = _plan_total(doc)
            await db.project_resources.insert_one(doc)
            created += 1
        await audit(user=user, action="quick_fill", resource="project_resources", record_id=project_id,
                    after={"mode": "plan", "created": created, "skipped_zero": skipped_zero}, ip="resource-plan")
        return {"ok": True, "mode": "plan", "created": created, "skipped_zero": skipped_zero}

    # mode == request → draft resource requests via the shared bulk engine
    from routers.resource_requests_router import _bulk_create, BulkRequestIn, BulkLine, _material_rr_type
    lines: List[BulkLine] = []
    for l in active:
        if l.kind == "manpower":
            d = desigs[l.ref_id]
            lines.append(BulkLine(resource_type="manpower", designation_id=d["id"],
                                    designation=d.get("name"), quantity=l.quantity, unit="Persons"))
        else:
            it = items[l.ref_id]
            cat = it.get("category") or ""
            lines.append(BulkLine(resource_type=_material_rr_type(cat), item_name=it.get("name"),
                                    category=cat, quantity=l.quantity,
                                    unit=it.get("unit") or it.get("uom") or "Nos"))
    result = await _bulk_create(BulkRequestIn(project_id=project_id, submit=False, lines=lines), user, "resource-plan")
    result.pop("created_docs", None)
    result.update({"mode": "request", "created": result.get("count", 0), "skipped_zero": skipped_zero})
    return result
