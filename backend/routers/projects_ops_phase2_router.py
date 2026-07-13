"""Projects & Operations · Phase 2 — Round 1 (Project Planning + BOQ).

Adds two new first-class artefacts on top of existing `projects` master:

  1. **Project Planning** (`db.project_planning`, 1:1 with `projects.id`)
       Project charter, objectives, scope summary, exclusions, assumptions,
       milestones, key risks, stakeholders, planning status (draft → approved).

  2. **BOQ / Scope Breakdown** (`db.project_boqs` + `db.project_boq_lines`)
       Standard industrial-ERP BOQ: header (project, version, status, totals)
       and lines (sl_no, item_code, description, uom, qty, rate, amount,
       category, wbs_code, scope_type). Excel import/export from day one.

Endpoints (all under `/api/proj-phase2/...`):

    Planning
    ──────────
    GET    /planning/{project_id}            — fetch (create empty if missing)
    PUT    /planning/{project_id}            — upsert
    POST   /planning/{project_id}/approve    — gate to "approved"

    BOQ
    ──────────
    GET    /boqs                              — list (optional ?project_id=)
    POST   /boqs                              — create
    GET    /boqs/{id}                         — header + lines
    PUT    /boqs/{id}                         — update header
    DELETE /boqs/{id}                         — delete header + lines
    POST   /boqs/{id}/approve                 — gate to "approved"
    GET    /boqs/{id}/lines                   — list lines
    POST   /boqs/{id}/lines                   — add one line
    PUT    /boqs/{id}/lines/{line_id}         — update line
    DELETE /boqs/{id}/lines/{line_id}         — delete line
    POST   /boqs/{id}/lines/bulk              — bulk add (JSON)
    GET    /boqs/{id}/export                  — Excel download
    POST   /boqs/{id}/import                  — Excel upload (multipart)
    GET    /boqs/template                     — blank Excel template
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/proj-phase2", tags=["projects-ops-phase2"])


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 · Project Planning
# ═══════════════════════════════════════════════════════════════════════════

class Milestone(BaseModel):
    id: Optional[str] = None
    name: str
    target_date: Optional[str] = ""
    status: str = "pending"   # pending | in_progress | completed | delayed
    remarks: Optional[str] = ""


class RiskItem(BaseModel):
    id: Optional[str] = None
    description: str
    severity: str = "medium"   # low | medium | high | critical
    likelihood: str = "medium" # low | medium | high
    mitigation: Optional[str] = ""
    owner: Optional[str] = ""


class StakeholderItem(BaseModel):
    id: Optional[str] = None
    name: str
    role: Optional[str] = ""
    organization: Optional[str] = ""
    contact: Optional[str] = ""


class PlanningIn(BaseModel):
    kickoff_date: Optional[str] = ""
    charter_summary: Optional[str] = ""
    objectives: Optional[str] = ""
    scope_summary: Optional[str] = ""
    exclusions: Optional[str] = ""
    assumptions: Optional[str] = ""
    constraints: Optional[str] = ""
    target_start_date: Optional[str] = ""
    target_completion_date: Optional[str] = ""
    success_criteria: Optional[str] = ""
    deliverables: Optional[str] = ""
    milestones: List[Milestone] = []
    risks: List[RiskItem] = []
    stakeholders: List[StakeholderItem] = []
    notes: Optional[str] = ""


def _ensure_ids(items: list) -> list:
    out = []
    for it in items or []:
        d = it.model_dump() if hasattr(it, "model_dump") else dict(it)
        if not d.get("id"):
            d["id"] = new_id()
        out.append(d)
    return out


async def _resolve_project(pid: str) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, f"Project '{pid}' not found")
    return p


@router.get("/planning/{project_id}")
async def get_planning(project_id: str,
                       user: dict = Depends(require_permission("projects", "read"))):
    p = await _resolve_project(project_id)
    doc = await db.project_planning.find_one({"project_id": project_id}, {"_id": 0})
    if not doc:
        # Return a transient draft (not persisted until PUT)
        doc = {
            "id": new_id(),
            "project_id": project_id,
            "project_code": p.get("code"),
            "project_name": p.get("name"),
            "kickoff_date": "",
            "charter_summary": "",
            "objectives": "",
            "scope_summary": "",
            "exclusions": "",
            "assumptions": "",
            "constraints": "",
            "target_start_date": p.get("start_date") or "",
            "target_completion_date": p.get("end_date") or "",
            "success_criteria": "",
            "deliverables": "",
            "milestones": [],
            "risks": [],
            "stakeholders": [],
            "notes": "",
            "planning_status": "draft",
            "is_new": True,
        }
    else:
        doc["project_code"] = p.get("code")
        doc["project_name"] = p.get("name")
    return doc


@router.put("/planning/{project_id}")
async def upsert_planning(project_id: str, payload: PlanningIn,
                          user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(project_id)
    body = payload.model_dump()
    body["milestones"]   = _ensure_ids(payload.milestones)
    body["risks"]        = _ensure_ids(payload.risks)
    body["stakeholders"] = _ensure_ids(payload.stakeholders)

    existing = await db.project_planning.find_one({"project_id": project_id}, {"_id": 0})
    if existing:
        body["updated_at"] = now_iso()
        body["updated_by"] = user.get("name") or user.get("email")
        # preserve planning_status & approval metadata across normal saves
        body["planning_status"] = existing.get("planning_status", "draft")
        await db.project_planning.update_one(
            {"project_id": project_id}, {"$set": body},
        )
    else:
        body.update({
            "id": new_id(),
            "project_id": project_id,
            "project_code": p.get("code"),
            "project_name": p.get("name"),
            "planning_status": "draft",
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
        })
        await db.project_planning.insert_one(body)

    await audit(user=user, action="upsert", resource="project_planning",
                record_id=project_id, before=existing or {}, after=body, ip="planning")
    return await db.project_planning.find_one({"project_id": project_id}, {"_id": 0})


@router.post("/planning/{project_id}/approve")
async def approve_planning(project_id: str,
                           user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head", "project_manager"):
        raise HTTPException(403, "Only PM / Ops Head / Director can approve project planning")
    existing = await db.project_planning.find_one({"project_id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "No planning record exists for this project. Save one first.")
    if existing.get("planning_status") == "approved":
        return existing
    patch = {
        "planning_status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }
    await db.project_planning.update_one({"project_id": project_id}, {"$set": patch})
    await audit(user=user, action="approve", resource="project_planning",
                record_id=project_id, before=existing, after={**existing, **patch}, ip="planning")
    return await db.project_planning.find_one({"project_id": project_id}, {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 · BOQ Header + Lines
# ═══════════════════════════════════════════════════════════════════════════

BOQ_STATUSES = ("draft", "in_review", "approved", "revised", "cancelled")

EXCEL_HEADERS = [
    "Sl No", "Item Code", "Description", "Category", "Scope Type",
    "UOM", "Quantity", "Unit Rate", "Amount", "WBS Code", "Remarks",
]


class BoqHeaderIn(BaseModel):
    project_id: str = Field(..., min_length=1)
    boq_no: Optional[str] = ""        # auto-generated if blank
    boq_date: Optional[str] = ""
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = ""
    currency: str = "INR"
    version: str = "1.0"
    tax_rate: float = 18.0            # GST %
    status: str = "draft"
    remarks: Optional[str] = ""


class BoqLineIn(BaseModel):
    sl_no: Optional[int] = None
    item_code: Optional[str] = ""
    description: str = Field(..., min_length=1)
    category: Optional[str] = ""        # Civil / MEP / Painting / Scaffolding / ...
    uom: str = "nos"                    # nos | sqm | cum | lm | MT | manday | LS | kg
    quantity: float = 0.0
    unit_rate: float = 0.0
    wbs_code: Optional[str] = ""        # links to WBS later (Round 2)
    scope_type: Optional[str] = "service"   # service | supply | material | labour
    remarks: Optional[str] = ""


def _line_amount(q: float, r: float) -> float:
    return round(float(q or 0) * float(r or 0), 2)


async def _recompute_totals(boq_id: str) -> dict:
    lines = await db.project_boq_lines.find({"boq_id": boq_id}, {"_id": 0}).to_list(10000)
    subtotal = round(sum(_line_amount(ln.get("quantity"), ln.get("unit_rate")) for ln in lines), 2)
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    tax_rate = float((boq or {}).get("tax_rate") or 0)
    tax_amount = round(subtotal * tax_rate / 100.0, 2)
    total = round(subtotal + tax_amount, 2)
    await db.project_boqs.update_one(
        {"id": boq_id},
        {"$set": {
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total": total,
            "line_count": len(lines),
            "updated_at": now_iso(),
        }},
    )
    return {"subtotal": subtotal, "tax_amount": tax_amount, "total": total, "line_count": len(lines)}


async def _next_boq_no(project_code: str) -> str:
    n = await db.project_boqs.count_documents({})
    return f"BOQ-{project_code or 'GEN'}-{n + 1:04d}"


# ─────────── BOQ Header CRUD ───────────
@router.get("/boqs")
async def list_boqs(project_id: Optional[str] = None,
                    status: Optional[str] = None,
                    user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    rows = await db.project_boqs.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return rows


@router.post("/boqs")
async def create_boq(payload: BoqHeaderIn,
                     user: dict = Depends(require_permission("projects", "write"))):
    p = await _resolve_project(payload.project_id)
    if payload.status not in BOQ_STATUSES:
        raise HTTPException(400, f"Invalid status '{payload.status}'")
    doc = payload.model_dump()
    doc["id"]            = new_id()
    doc["boq_no"]        = (payload.boq_no or "").strip() or await _next_boq_no(p.get("code") or "")
    doc["boq_date"]      = payload.boq_date or now_iso()[:10]
    doc["project_code"]  = p.get("code")
    doc["project_name"]  = p.get("name")
    doc["client_id"]     = p.get("client_id")
    doc["client_name"]   = p.get("client_name") or p.get("client")
    doc["subtotal"]      = 0.0
    doc["tax_amount"]    = 0.0
    doc["total"]         = 0.0
    doc["line_count"]    = 0
    doc["created_at"]    = now_iso()
    doc["created_by"]    = user.get("name") or user.get("email")
    await db.project_boqs.insert_one(doc)
    await audit(user=user, action="create", resource="project_boqs",
                record_id=doc["id"], before={}, after=doc, ip="boq")
    return {k: v for k, v in doc.items() if k != "_id"}


@router.get("/boqs/template")
async def boq_template(user: dict = Depends(require_permission("projects", "read"))):
    """Blank Excel template for BOQ line import."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"
    ws.append(EXCEL_HEADERS)
    ws.append([1, "ITEM-001", "Sample scope description", "Painting", "service",
               "sqm", 100, 250, "=G2*H2", "WBS-1.1", "demo row — delete before import"])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="boq_template.xlsx"'},
    )


@router.get("/boqs/{boq_id}")
async def get_boq(boq_id: str,
                  user: dict = Depends(require_permission("projects", "read"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    lines = await db.project_boq_lines.find({"boq_id": boq_id}, {"_id": 0}).sort("sl_no", 1).to_list(10000)
    # Hydrate amount on the fly for legacy rows
    for ln in lines:
        ln["amount"] = _line_amount(ln.get("quantity"), ln.get("unit_rate"))
    return {**boq, "lines": lines}


@router.put("/boqs/{boq_id}")
async def update_boq(boq_id: str, payload: BoqHeaderIn,
                     user: dict = Depends(require_permission("projects", "write"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    if boq.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved BOQ cannot be edited (Super Admin / Director override only).")

    patch = payload.model_dump()
    # project_id is immutable after creation
    patch.pop("project_id", None)
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.project_boqs.update_one({"id": boq_id}, {"$set": patch})
    await _recompute_totals(boq_id)
    return await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})


@router.delete("/boqs/{boq_id}")
async def delete_boq(boq_id: str,
                     user: dict = Depends(require_permission("projects", "delete"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    if boq.get("status") == "approved" and user.get("role") != "super_admin":
        raise HTTPException(403, "Approved BOQ can only be deleted by Super Admin.")
    await db.project_boq_lines.delete_many({"boq_id": boq_id})
    await db.project_boqs.delete_one({"id": boq_id})
    await audit(user=user, action="delete", resource="project_boqs",
                record_id=boq_id, before=boq, after={}, ip="boq")
    return {"ok": True}


@router.post("/boqs/{boq_id}/approve")
async def approve_boq(boq_id: str,
                      user: dict = Depends(require_permission("projects", "write"))):
    if user.get("role") not in ("super_admin", "director", "general_manager", "dept_head"):
        raise HTTPException(403, "Only Director / GM / Dept Head can approve a BOQ")
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    patch = {
        "status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.project_boqs.update_one({"id": boq_id}, {"$set": patch})
    await audit(user=user, action="approve", resource="project_boqs",
                record_id=boq_id, before=boq, after={**boq, **patch}, ip="boq")
    return await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})


# ─────────── BOQ Lines CRUD ───────────
@router.get("/boqs/{boq_id}/lines")
async def list_lines(boq_id: str,
                     user: dict = Depends(require_permission("projects", "read"))):
    if not await db.project_boqs.find_one({"id": boq_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "BOQ not found")
    lines = await db.project_boq_lines.find({"boq_id": boq_id}, {"_id": 0}).sort("sl_no", 1).to_list(10000)
    for ln in lines:
        ln["amount"] = _line_amount(ln.get("quantity"), ln.get("unit_rate"))
    return lines


@router.post("/boqs/{boq_id}/lines")
async def add_line(boq_id: str, payload: BoqLineIn,
                   user: dict = Depends(require_permission("projects", "write"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    if boq.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved BOQ is locked. Revise first.")
    # auto sl_no
    sl = payload.sl_no
    if not sl:
        last = await db.project_boq_lines.find({"boq_id": boq_id}).sort("sl_no", -1).limit(1).to_list(1)
        sl = ((last[0].get("sl_no") or 0) + 1) if last else 1
    line = payload.model_dump()
    line.update({
        "id": new_id(),
        "boq_id": boq_id,
        "project_id": boq.get("project_id"),
        "sl_no": sl,
        "amount": _line_amount(payload.quantity, payload.unit_rate),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.project_boq_lines.insert_one(line)
    totals = await _recompute_totals(boq_id)
    return {**{k: v for k, v in line.items() if k != "_id"}, "_totals": totals}


@router.put("/boqs/{boq_id}/lines/{line_id}")
async def update_line(boq_id: str, line_id: str, payload: BoqLineIn,
                      user: dict = Depends(require_permission("projects", "write"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    if boq.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved BOQ is locked. Revise first.")
    line = await db.project_boq_lines.find_one({"id": line_id, "boq_id": boq_id}, {"_id": 0})
    if not line:
        raise HTTPException(404, "Line not found")
    patch = payload.model_dump()
    patch["amount"]     = _line_amount(payload.quantity, payload.unit_rate)
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.project_boq_lines.update_one({"id": line_id, "boq_id": boq_id}, {"$set": patch})
    totals = await _recompute_totals(boq_id)
    line = await db.project_boq_lines.find_one({"id": line_id}, {"_id": 0})
    return {**line, "_totals": totals}


@router.delete("/boqs/{boq_id}/lines/{line_id}")
async def delete_line(boq_id: str, line_id: str,
                      user: dict = Depends(require_permission("projects", "write"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    if boq.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved BOQ is locked. Revise first.")
    res = await db.project_boq_lines.delete_one({"id": line_id, "boq_id": boq_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Line not found")
    totals = await _recompute_totals(boq_id)
    return {"ok": True, "_totals": totals}


class BulkLines(BaseModel):
    lines: List[BoqLineIn]


@router.post("/boqs/{boq_id}/lines/bulk")
async def bulk_lines(boq_id: str, payload: BulkLines,
                     user: dict = Depends(require_permission("projects", "write"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    if boq.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved BOQ is locked. Revise first.")

    # find next sl_no baseline
    last = await db.project_boq_lines.find({"boq_id": boq_id}).sort("sl_no", -1).limit(1).to_list(1)
    next_sl = ((last[0].get("sl_no") or 0) + 1) if last else 1

    docs = []
    for i, ln in enumerate(payload.lines):
        d = ln.model_dump()
        d.update({
            "id": new_id(),
            "boq_id": boq_id,
            "project_id": boq.get("project_id"),
            "sl_no": d.get("sl_no") or (next_sl + i),
            "amount": _line_amount(ln.quantity, ln.unit_rate),
            "created_at": now_iso(),
            "created_by": user.get("name") or user.get("email"),
        })
        docs.append(d)
    if docs:
        await db.project_boq_lines.insert_many(docs)
    totals = await _recompute_totals(boq_id)
    return {"inserted": len(docs), "_totals": totals}


# ─────────── Excel Export / Import ───────────


@router.get("/boqs/{boq_id}/export")
async def boq_export(boq_id: str,
                     user: dict = Depends(require_permission("projects", "read"))):
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    lines = await db.project_boq_lines.find({"boq_id": boq_id}, {"_id": 0}).sort("sl_no", 1).to_list(10000)

    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"
    # Header band
    ws.append([f"BOQ No: {boq.get('boq_no')}"])
    ws.append([f"Project: {boq.get('project_code')} — {boq.get('project_name')}"])
    ws.append([f"Client: {boq.get('client_name') or ''}"])
    ws.append([f"Title: {boq.get('title')}"])
    ws.append([f"Status: {boq.get('status')}    Version: {boq.get('version')}    Currency: {boq.get('currency')}"])
    ws.append([])
    ws.append(EXCEL_HEADERS)
    for ln in lines:
        ws.append([
            ln.get("sl_no"), ln.get("item_code"), ln.get("description"),
            ln.get("category"), ln.get("scope_type"), ln.get("uom"),
            float(ln.get("quantity") or 0), float(ln.get("unit_rate") or 0),
            _line_amount(ln.get("quantity"), ln.get("unit_rate")),
            ln.get("wbs_code"), ln.get("remarks"),
        ])
    ws.append([])
    ws.append(["", "", "", "", "", "", "", "Subtotal", float(boq.get("subtotal") or 0)])
    ws.append(["", "", "", "", "", "", "", f"Tax @ {boq.get('tax_rate') or 0}%", float(boq.get("tax_amount") or 0)])
    ws.append(["", "", "", "", "", "", "", "Total", float(boq.get("total") or 0)])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    filename = f"BOQ_{boq.get('boq_no') or boq_id}.xlsx"
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/boqs/{boq_id}/import")
async def boq_import(boq_id: str, file: UploadFile = File(...),
                     replace: bool = False,
                     user: dict = Depends(require_permission("projects", "write"))):
    """Import BOQ lines from Excel.
    Expected columns (case-insensitive, in order): Sl No, Item Code,
    Description, Category, Scope Type, UOM, Quantity, Unit Rate, [Amount],
    WBS Code, Remarks.

    `replace=true` → delete all existing lines first.
    """
    boq = await db.project_boqs.find_one({"id": boq_id}, {"_id": 0})
    if not boq:
        raise HTTPException(404, "BOQ not found")
    if boq.get("status") == "approved" and user.get("role") not in ("super_admin", "director"):
        raise HTTPException(403, "Approved BOQ is locked. Revise first.")

    data = await file.read()
    try:
        wb = load_workbook(filename=io.BytesIO(data), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Could not read Excel file: {e}")
    ws = wb.active

    # Locate the header row that starts with "Sl No"
    header_row_idx = None
    rows = list(ws.iter_rows(values_only=True))
    for i, row in enumerate(rows):
        if row and str(row[0] or "").strip().lower().replace(" ", "") in ("slno", "sl.no", "sl_no", "s.no", "sno"):
            header_row_idx = i
            break
    if header_row_idx is None:
        raise HTTPException(400, "Excel must contain a header row beginning with 'Sl No'")

    if replace:
        await db.project_boq_lines.delete_many({"boq_id": boq_id})

    last = await db.project_boq_lines.find({"boq_id": boq_id}).sort("sl_no", -1).limit(1).to_list(1)
    next_sl = ((last[0].get("sl_no") or 0) + 1) if last else 1

    inserted = 0
    errors: List[str] = []
    docs: List[dict] = []

    for r_idx, row in enumerate(rows[header_row_idx + 1:], start=header_row_idx + 2):
        if not row or all(c in (None, "", " ") for c in row):
            continue
        try:
            sl_no       = int(row[0]) if row[0] not in (None, "") else next_sl
            item_code   = str(row[1] or "").strip()
            description = str(row[2] or "").strip()
            category    = str(row[3] or "").strip()
            scope_type  = str(row[4] or "service").strip() or "service"
            uom         = str(row[5] or "nos").strip() or "nos"
            qty         = float(row[6] or 0)
            rate        = float(row[7] or 0)
            wbs_code    = str(row[9] or "").strip() if len(row) > 9 else ""
            remarks     = str(row[10] or "").strip() if len(row) > 10 else ""
            if not description:
                errors.append(f"Row {r_idx}: description missing — skipped")
                continue
            docs.append({
                "id": new_id(),
                "boq_id": boq_id,
                "project_id": boq.get("project_id"),
                "sl_no": sl_no, "item_code": item_code, "description": description,
                "category": category, "scope_type": scope_type, "uom": uom,
                "quantity": qty, "unit_rate": rate, "amount": _line_amount(qty, rate),
                "wbs_code": wbs_code, "remarks": remarks,
                "created_at": now_iso(),
                "created_by": user.get("name") or user.get("email"),
            })
            next_sl = max(next_sl, sl_no + 1)
        except Exception as e:
            errors.append(f"Row {r_idx}: {e}")
    if docs:
        await db.project_boq_lines.insert_many(docs)
        inserted = len(docs)
    totals = await _recompute_totals(boq_id)
    await audit(user=user, action="import", resource="project_boqs",
                record_id=boq_id, before={}, after={"inserted": inserted, "errors": errors}, ip="boq")
    return {"inserted": inserted, "errors": errors, "_totals": totals}
