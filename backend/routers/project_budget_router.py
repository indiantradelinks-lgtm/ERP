"""Project Budget Planner — category-wise budget lines filled by the project team.

Frequencies: daily | weekly | monthly | yearly | one_time.
Equivalent total is auto-computed from the line period (defaults to project
start/end dates) with a manual override option.

Collection: project_budget_lines. Endpoints under /api/ops/project-budgets.
"""
from __future__ import annotations

import io
import math
from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from scope import apply_project_scope, ensure_project_access
from audit import audit
from exports import to_excel, to_pdf

router = APIRouter(prefix="/ops/project-budgets", tags=["project-budget"])

FREQUENCIES = {"daily", "weekly", "monthly", "yearly", "one_time"}
FREQ_LABELS = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly",
               "yearly": "Yearly", "one_time": "One Time"}


class BudgetLineIn(BaseModel):
    project_id: str
    category_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    description: str = ""
    frequency: str = "monthly"
    amount: float = Field(0, ge=0)
    start_date: Optional[str] = None   # YYYY-MM-DD; defaults to project start
    end_date: Optional[str] = None     # defaults to project end
    total_override: Optional[float] = None
    remarks: Optional[str] = None


def _parse(d: Optional[str]) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(d)[:10]).date() if d else None
    except Exception:
        return None


def compute_total(frequency: str, amount: float, start: Optional[date], end: Optional[date]) -> Dict[str, Any]:
    """Equivalent total for the period. one_time = amount as-is."""
    if frequency == "one_time" or not start or not end or end < start:
        units = 1
    else:
        days = (end - start).days + 1
        if frequency == "daily":
            units = days
        elif frequency == "weekly":
            units = math.ceil(days / 7)
        elif frequency == "monthly":
            units = max(1, round(days / 30.44))
        elif frequency == "yearly":
            units = max(1, math.ceil(days / 365.25))
        else:
            units = 1
    return {"units": units, "computed_total": round(amount * units, 2)}


async def _enrich(p: BudgetLineIn) -> Dict[str, Any]:
    proj = await db.projects.find_one({"id": p.project_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "start_date": 1, "end_date": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    if p.frequency not in FREQUENCIES:
        raise HTTPException(400, f"frequency must be one of {sorted(FREQUENCIES)}")
    cat = await db.inv_categories.find_one({"id": p.category_id}, {"_id": 0, "id": 1, "code": 1, "name": 1}) if p.category_id else None
    cc = await db.cost_centers.find_one({"id": p.cost_center_id}, {"_id": 0, "id": 1, "category_code": 1, "category_name": 1}) if p.cost_center_id else None
    start = _parse(p.start_date) or _parse(proj.get("start_date"))
    end = _parse(p.end_date) or _parse(proj.get("end_date"))
    calc = compute_total(p.frequency, p.amount, start, end)
    total = p.total_override if p.total_override is not None and p.total_override > 0 else calc["computed_total"]
    return {
        "project_id": proj["id"], "project_code": proj.get("code"), "project_name": proj.get("name"),
        "category_id": (cat or {}).get("id"), "category_code": (cat or {}).get("code"),
        "category_name": (cat or {}).get("name") or (cc or {}).get("category_name"),
        "cost_center_id": (cc or {}).get("id"), "cost_center_label": f"{(cc or {}).get('category_code') or ''} · {(cc or {}).get('category_name') or ''}".strip(" ·") if cc else None,
        "description": p.description, "frequency": p.frequency,
        "frequency_label": FREQ_LABELS[p.frequency], "amount": round(p.amount, 2),
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "units": calc["units"], "computed_total": calc["computed_total"],
        "total_override": p.total_override, "total": round(float(total), 2),
        "remarks": p.remarks,
    }


def _list_query(project_id: str = "", category_id: str = "", cost_center_id: str = "",
                frequency: str = "", from_date: str = "", to_date: str = "") -> Dict[str, Any]:
    q: Dict[str, Any] = {}
    if project_id:
        q["project_id"] = project_id
    if category_id:
        q["category_id"] = category_id
    if cost_center_id:
        q["cost_center_id"] = cost_center_id
    if frequency:
        q["frequency"] = frequency
    if from_date or to_date:
        # Overlap: line period intersects [from_date, to_date]
        if to_date:
            q["start_date"] = {"$lte": to_date}
        if from_date:
            q["end_date"] = {"$gte": from_date}
    return q


@router.get("")
async def list_budget_lines(project_id: str = "", category_id: str = "", cost_center_id: str = "",
                            frequency: str = "", from_date: str = "", to_date: str = "",
                            user: dict = Depends(require_permission("projects", "read"))):
    q = _list_query(project_id, category_id, cost_center_id, frequency, from_date, to_date)
    q = await apply_project_scope(user, q, "project_id")
    rows = await db.project_budget_lines.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return rows


async def _sync_cost_center_budget(cost_center_id: Optional[str]):
    """Keep Project Cost Center budget = sum of its Project Planning budget lines."""
    if not cost_center_id:
        return
    rows = await db.project_budget_lines.find({"cost_center_id": cost_center_id}, {"_id": 0, "total": 1}).to_list(2000)
    total = round(sum(float(r.get("total") or 0) for r in rows), 2)
    await db.cost_centers.update_one({"id": cost_center_id}, {"$set": {
        "budget": total, "budget_synced_from": "project_planning", "budget_synced_at": now_iso()}})


@router.post("")
async def create_budget_line(p: BudgetLineIn, request: Request,
                             user: dict = Depends(require_permission("projects", "write"))):
    await ensure_project_access(user, p.project_id)
    doc = await _enrich(p)
    doc.update({"id": new_id(), "created_at": now_iso(), "created_by": user["id"], "created_by_name": user.get("name")})
    await db.project_budget_lines.insert_one(dict(doc))
    doc.pop("_id", None)
    await _sync_cost_center_budget(doc.get("cost_center_id"))
    await audit(user=user, action="create", resource="project_budget_lines", record_id=doc["id"], after=doc,
                ip=request.client.host if request.client else "")
    return doc


@router.put("/{line_id}")
async def update_budget_line(line_id: str, p: BudgetLineIn, request: Request,
                             user: dict = Depends(require_permission("projects", "write"))):
    before = await db.project_budget_lines.find_one({"id": line_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Budget line not found")
    doc = await _enrich(p)
    doc.update({"updated_at": now_iso(), "updated_by": user["id"]})
    await db.project_budget_lines.update_one({"id": line_id}, {"$set": doc})
    out = await db.project_budget_lines.find_one({"id": line_id}, {"_id": 0})
    await _sync_cost_center_budget(doc.get("cost_center_id"))
    if before.get("cost_center_id") and before.get("cost_center_id") != doc.get("cost_center_id"):
        await _sync_cost_center_budget(before.get("cost_center_id"))
    await audit(user=user, action="update", resource="project_budget_lines", record_id=line_id, before=before, after=out,
                ip=request.client.host if request.client else "")
    return out


@router.delete("/{line_id}")
async def delete_budget_line(line_id: str, request: Request,
                             user: dict = Depends(require_permission("projects", "write"))):
    before = await db.project_budget_lines.find_one({"id": line_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Budget line not found")
    await db.project_budget_lines.delete_one({"id": line_id})
    await _sync_cost_center_budget(before.get("cost_center_id"))
    await audit(user=user, action="delete", resource="project_budget_lines", record_id=line_id, before=before,
                ip=request.client.host if request.client else "")
    return {"ok": True}


@router.get("/report")
async def budget_report(project_id: str = "", category_id: str = "", cost_center_id: str = "",
                        frequency: str = "", from_date: str = "", to_date: str = "",
                        group_by: str = "category",
                        user: dict = Depends(require_permission("projects", "read"))):
    """Summary grouped by category | project | frequency + grand total."""
    q = _list_query(project_id, category_id, cost_center_id, frequency, from_date, to_date)
    q = await apply_project_scope(user, q, "project_id")
    rows = await db.project_budget_lines.find(q, {"_id": 0}).to_list(5000)
    key_map = {
        "category": lambda r: r.get("category_name") or r.get("cost_center_label") or "Uncategorised",
        "project": lambda r: f"{r.get('project_code') or ''} · {r.get('project_name') or ''}".strip(" ·"),
        "frequency": lambda r: r.get("frequency_label") or r.get("frequency"),
    }
    keyer = key_map.get(group_by, key_map["category"])
    groups: Dict[str, Dict[str, Any]] = {}
    grand = 0.0
    for r in rows:
        k = keyer(r)
        g = groups.setdefault(k, {"group": k, "lines": 0, "total": 0.0})
        g["lines"] += 1
        g["total"] = round(g["total"] + float(r.get("total") or 0), 2)
        grand += float(r.get("total") or 0)
    return {"group_by": group_by, "count": len(rows), "grand_total": round(grand, 2),
            "groups": sorted(groups.values(), key=lambda g: -g["total"]), "rows": rows}


@router.get("/export.{fmt}")
async def export_budget(fmt: str, project_id: str = "", category_id: str = "", cost_center_id: str = "",
                        frequency: str = "", from_date: str = "", to_date: str = "",
                        user: dict = Depends(require_permission("projects", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "fmt must be xlsx or pdf")
    q = _list_query(project_id, category_id, cost_center_id, frequency, from_date, to_date)
    q = await apply_project_scope(user, q, "project_id")
    raw = await db.project_budget_lines.find(q, {"_id": 0}).sort([("project_code", 1), ("category_name", 1)]).to_list(5000)
    rows = [{
        "Project": f"{r.get('project_code') or ''} · {r.get('project_name') or ''}".strip(" ·"),
        "Category": r.get("category_name") or "—",
        "Cost Center": r.get("cost_center_label") or "—",
        "Description": r.get("description") or "",
        "Frequency": r.get("frequency_label") or r.get("frequency"),
        "Amount": r.get("amount"),
        "From": r.get("start_date"), "To": r.get("end_date"),
        "Units": r.get("units"), "Total Budget": r.get("total"),
        "Remarks": r.get("remarks") or "",
    } for r in raw]
    data = to_excel("project_budget_lines", rows) if fmt == "xlsx" else to_pdf("project_budget_lines", rows)
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if fmt == "xlsx" else "application/pdf")
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="project_budget.{fmt}"'})
