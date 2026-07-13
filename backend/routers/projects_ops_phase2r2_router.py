"""Projects & Operations · Phase 2 — Round 2.

Adds the planning bedrock for execution:

  1. **Work Breakdown Structure (WBS)** (`db.project_wbs`)
        Hierarchical tree of project work. Each node = {id, project_id, code,
        name, description, parent_id, level, scope_type, weight_pct,
        estimated_hours, status}. Codes are dot-notation (1, 1.1, 1.1.2 …).

  2. **Activity Schedule** (`db.project_activities`)
        Time-phased activities mapped to a WBS node (or free-floating).
        Fields: code, name, wbs_id, start_date, end_date, duration_days,
        predecessor_ids[], status, progress_pct, responsible.

  3. **Resource Plan** (`db.project_resources`)
        Unified collection discriminated by `resource_type`:
            • manpower   — designation_id/name, count_required, mandays, daily_rate
            • material   — pr_item_id/name, uom, quantity, unit_rate
            • tools      — name, owned_or_rented, count, days, daily_rate
            • subcontract — vendor_id/name, scope, value, basis (lumpsum|unit)
        All four expose `total_cost` (derived) and optional WBS / activity link.

Endpoints (all under `/api/proj-phase2/...`)
─────────────────────────────────────────────
  WBS
    GET    /wbs/{project_id}                 — flat list (sorted by code)
    GET    /wbs/{project_id}/tree            — nested tree (children[] embedded)
    POST   /wbs/{project_id}                 — create node
    PUT    /wbs/nodes/{node_id}              — update node
    DELETE /wbs/nodes/{node_id}              — delete node + descendants

  Activities
    GET    /activities/{project_id}          — list (sorted by start_date)
    POST   /activities/{project_id}          — create
    PUT    /activities/{activity_id}         — update (recomputes duration)
    DELETE /activities/{activity_id}         — delete

  Resources
    GET    /resources/{project_id}?type=     — list (optionally filtered)
    POST   /resources/{project_id}           — create row
    PUT    /resources/{resource_id}          — update
    DELETE /resources/{resource_id}          — delete
    GET    /resources/{project_id}/summary   — totals per resource_type
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit


router = APIRouter(prefix="/proj-phase2", tags=["projects-ops-phase2-r2"])


async def _resolve_project(pid: str) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, f"Project '{pid}' not found")
    return p


# ═══════════════════════════════════════════════════════════════════════════
# Section 1 · Work Breakdown Structure
# ═══════════════════════════════════════════════════════════════════════════

WBS_STATUS = ("not_started", "in_progress", "completed", "on_hold", "cancelled")


class WbsIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)         # "1", "1.1", "1.1.2"
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = ""
    parent_id: Optional[str] = None
    scope_type: Optional[str] = ""                              # Civil / MEP / Painting / …
    weight_pct: float = 0.0                                     # 0–100
    estimated_hours: float = 0.0
    status: str = "not_started"
    boq_id: Optional[str] = None                                # optional cross-link to BOQ header
    remarks: Optional[str] = ""


def _wbs_level(code: str) -> int:
    return code.count(".") + 1 if code else 1


@router.get("/wbs/{project_id}")
async def list_wbs(project_id: str,
                   user: dict = Depends(require_permission("projects", "read"))):
    await _resolve_project(project_id)
    rows = await db.project_wbs.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    # natural sort by code (1, 1.1, 1.1.2, 1.2 …)
    rows.sort(key=lambda r: [int(x) if x.isdigit() else 9999 for x in str(r.get("code", "")).split(".")])
    return rows


@router.get("/wbs/{project_id}/tree")
async def wbs_tree(project_id: str,
                   user: dict = Depends(require_permission("projects", "read"))):
    nodes = await list_wbs(project_id, user)
    by_id: Dict[str, dict] = {n["id"]: {**n, "children": []} for n in nodes}
    roots: List[dict] = []
    for n in nodes:
        node = by_id[n["id"]]
        pid = n.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.post("/wbs/{project_id}")
async def create_wbs(project_id: str, payload: WbsIn,
                     user: dict = Depends(require_permission("projects", "write"))):
    await _resolve_project(project_id)
    if payload.status not in WBS_STATUS:
        raise HTTPException(400, f"Invalid status '{payload.status}'")
    # duplicate code guard within project
    if await db.project_wbs.find_one({"project_id": project_id, "code": payload.code}, {"_id": 0, "id": 1}):
        raise HTTPException(409, f"WBS code '{payload.code}' already exists in this project")
    if payload.parent_id:
        parent = await db.project_wbs.find_one({"id": payload.parent_id, "project_id": project_id}, {"_id": 0})
        if not parent:
            raise HTTPException(404, "Parent WBS node not found in this project")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "project_id": project_id,
        "level": _wbs_level(payload.code),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.project_wbs.insert_one(doc)
    await audit(user=user, action="create", resource="project_wbs",
                record_id=doc["id"], before={}, after=doc, ip="wbs")
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/wbs/nodes/{node_id}")
async def update_wbs(node_id: str, payload: WbsIn,
                     user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.project_wbs.find_one({"id": node_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "WBS node not found")
    # if code changed, recheck duplicates
    if payload.code != existing.get("code"):
        dup = await db.project_wbs.find_one(
            {"project_id": existing["project_id"], "code": payload.code, "id": {"$ne": node_id}},
            {"_id": 0, "id": 1},
        )
        if dup:
            raise HTTPException(409, f"WBS code '{payload.code}' already in use")
    patch = payload.model_dump()
    patch["level"] = _wbs_level(payload.code)
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.project_wbs.update_one({"id": node_id}, {"$set": patch})
    return await db.project_wbs.find_one({"id": node_id}, {"_id": 0})


@router.delete("/wbs/nodes/{node_id}")
async def delete_wbs(node_id: str,
                     user: dict = Depends(require_permission("projects", "delete"))):
    existing = await db.project_wbs.find_one({"id": node_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "WBS node not found")
    # cascade descendants by parent walk
    to_delete = {node_id}
    frontier = {node_id}
    while frontier:
        children = await db.project_wbs.find(
            {"parent_id": {"$in": list(frontier)}}, {"_id": 0, "id": 1}
        ).to_list(2000)
        next_ids = {c["id"] for c in children} - to_delete
        to_delete.update(next_ids)
        frontier = next_ids
    await db.project_wbs.delete_many({"id": {"$in": list(to_delete)}})
    # unlink any activities / resources tied to deleted WBS nodes
    await db.project_activities.update_many({"wbs_id": {"$in": list(to_delete)}}, {"$set": {"wbs_id": None}})
    await db.project_resources.update_many({"wbs_id": {"$in": list(to_delete)}}, {"$set": {"wbs_id": None}})
    await audit(user=user, action="delete", resource="project_wbs",
                record_id=node_id, before=existing, after={"deleted": list(to_delete)}, ip="wbs")
    return {"ok": True, "deleted": len(to_delete)}


# ═══════════════════════════════════════════════════════════════════════════
# Section 2 · Activity Schedule
# ═══════════════════════════════════════════════════════════════════════════

ACTIVITY_STATUS = ("not_started", "in_progress", "completed", "on_hold", "cancelled", "delayed")


class ActivityIn(BaseModel):
    code: Optional[str] = ""                  # auto if blank
    name: str = Field(..., min_length=1, max_length=200)
    wbs_id: Optional[str] = None
    start_date: Optional[str] = ""            # YYYY-MM-DD
    end_date: Optional[str] = ""
    duration_days: Optional[int] = None       # auto-derived if start+end
    predecessor_ids: List[str] = []           # other activity ids
    responsible: Optional[str] = ""           # name or designation
    status: str = "not_started"
    progress_pct: float = 0.0
    remarks: Optional[str] = ""


def _duration(start: str, end: str) -> Optional[int]:
    try:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        return max((e - s).days, 0)
    except Exception:
        return None


async def _next_activity_code(project_id: str) -> str:
    n = await db.project_activities.count_documents({"project_id": project_id})
    return f"ACT-{n + 1:04d}"


@router.get("/activities/{project_id}")
async def list_activities(project_id: str,
                          user: dict = Depends(require_permission("projects", "read"))):
    await _resolve_project(project_id)
    rows = await db.project_activities.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    # sort: start_date asc, then code
    rows.sort(key=lambda r: (r.get("start_date") or "9999-99-99", r.get("code") or ""))
    return rows


@router.post("/activities/{project_id}")
async def create_activity(project_id: str, payload: ActivityIn,
                          user: dict = Depends(require_permission("projects", "write"))):
    await _resolve_project(project_id)
    if payload.status not in ACTIVITY_STATUS:
        raise HTTPException(400, f"Invalid status '{payload.status}'")
    if payload.wbs_id and not await db.project_wbs.find_one({"id": payload.wbs_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Linked WBS node not found")

    doc = payload.model_dump()
    doc["code"] = (payload.code or "").strip() or await _next_activity_code(project_id)
    if payload.start_date and payload.end_date and payload.duration_days is None:
        doc["duration_days"] = _duration(payload.start_date, payload.end_date)
    doc.update({
        "id": new_id(),
        "project_id": project_id,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await db.project_activities.insert_one(doc)
    await audit(user=user, action="create", resource="project_activities",
                record_id=doc["id"], before={}, after=doc, ip="activities")
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/activities/{activity_id}")
async def update_activity(activity_id: str, payload: ActivityIn,
                          user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.project_activities.find_one({"id": activity_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Activity not found")
    if payload.status not in ACTIVITY_STATUS:
        raise HTTPException(400, f"Invalid status '{payload.status}'")
    if payload.wbs_id and not await db.project_wbs.find_one({"id": payload.wbs_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Linked WBS node not found")

    patch = payload.model_dump()
    # preserve auto-code on update if blank
    if not patch.get("code"):
        patch["code"] = existing.get("code")
    if payload.start_date and payload.end_date and payload.duration_days is None:
        patch["duration_days"] = _duration(payload.start_date, payload.end_date)
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.project_activities.update_one({"id": activity_id}, {"$set": patch})
    return await db.project_activities.find_one({"id": activity_id}, {"_id": 0})


@router.delete("/activities/{activity_id}")
async def delete_activity(activity_id: str,
                          user: dict = Depends(require_permission("projects", "delete"))):
    existing = await db.project_activities.find_one({"id": activity_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Activity not found")
    # unlink predecessor references that point to this activity
    await db.project_activities.update_many(
        {"predecessor_ids": activity_id},
        {"$pull": {"predecessor_ids": activity_id}},
    )
    await db.project_activities.delete_one({"id": activity_id})
    await db.project_resources.update_many({"activity_id": activity_id}, {"$set": {"activity_id": None}})
    await audit(user=user, action="delete", resource="project_activities",
                record_id=activity_id, before=existing, after={}, ip="activities")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Section 3 · Resource Plan (manpower / material / tools / subcontract)
# ═══════════════════════════════════════════════════════════════════════════

ResourceType = Literal["manpower", "material", "tools", "subcontract"]


class ResourceIn(BaseModel):
    resource_type: ResourceType
    # cross-cutting
    wbs_id: Optional[str] = None
    activity_id: Optional[str] = None
    required_by_date: Optional[str] = ""
    remarks: Optional[str] = ""

    # ---- manpower ----
    designation_id: Optional[str] = None
    designation_name: Optional[str] = ""
    count_required: Optional[float] = 0
    mandays: Optional[float] = 0
    daily_rate: Optional[float] = 0

    # ---- material ----
    item_id: Optional[str] = None
    item_code: Optional[str] = ""
    item_name: Optional[str] = ""
    uom: Optional[str] = ""
    quantity: Optional[float] = 0
    unit_rate: Optional[float] = 0
    source: Optional[str] = "stock"           # stock | purchase | client_supply

    # ---- tools / equipment ----
    tool_name: Optional[str] = ""
    tool_owned_or_rented: Optional[str] = "owned"   # owned | rented
    days: Optional[float] = 0

    # ---- subcontract ----
    vendor_id: Optional[str] = None
    vendor_code: Optional[str] = ""
    vendor_name: Optional[str] = ""
    scope: Optional[str] = ""
    basis: Optional[str] = "lumpsum"           # lumpsum | unit_rate
    value: Optional[float] = 0


def _resource_total(d: dict) -> float:
    rt = d.get("resource_type")
    if rt == "manpower":
        # priority: mandays * daily_rate ; else count * mandays * daily_rate ; else count * daily_rate
        mandays = float(d.get("mandays") or 0)
        rate = float(d.get("daily_rate") or 0)
        count = float(d.get("count_required") or 0)
        if mandays and rate:
            return round(mandays * rate, 2)
        return round(count * mandays * rate, 2) if (count and mandays) else round(count * rate, 2)
    if rt == "material":
        return round(float(d.get("quantity") or 0) * float(d.get("unit_rate") or 0), 2)
    if rt == "tools":
        return round(float(d.get("count_required") or 1) * float(d.get("days") or 0) * float(d.get("daily_rate") or 0), 2)
    if rt == "subcontract":
        return float(d.get("value") or 0)
    return 0.0


async def _enrich_resource(doc: dict) -> dict:
    """Backfill names from referenced collections so the UI can show clean labels."""
    rt = doc.get("resource_type")
    if rt == "manpower" and doc.get("designation_id") and not doc.get("designation_name"):
        d = await db.hr_designations.find_one({"id": doc["designation_id"]}, {"_id": 0, "name": 1, "code": 1})
        if d:
            doc["designation_name"] = d.get("name") or d.get("code") or ""
    elif rt == "material" and doc.get("item_id") and not doc.get("item_name"):
        d = await db.pr_items.find_one({"id": doc["item_id"]}, {"_id": 0, "name": 1, "code": 1, "unit": 1, "last_rate": 1})
        if d:
            doc["item_name"] = d.get("name") or ""
            doc["item_code"] = d.get("code") or doc.get("item_code") or ""
            if not doc.get("uom"):
                doc["uom"] = d.get("unit") or ""
            if not doc.get("unit_rate"):
                doc["unit_rate"] = d.get("last_rate") or 0
    elif rt == "subcontract" and doc.get("vendor_id") and not doc.get("vendor_name"):
        d = await db.vendors.find_one({"id": doc["vendor_id"]}, {"_id": 0, "name": 1, "vendor_code": 1})
        if d:
            doc["vendor_name"] = d.get("name") or ""
            doc["vendor_code"] = d.get("vendor_code") or ""
    return doc


@router.get("/resources/{project_id}")
async def list_resources(project_id: str,
                         type: Optional[str] = None,
                         user: dict = Depends(require_permission("projects", "read"))):
    await _resolve_project(project_id)
    q: Dict[str, Any] = {"project_id": project_id}
    if type:
        q["resource_type"] = type
    rows = await db.project_resources.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    for r in rows:
        r["total_cost"] = _resource_total(r)
    return rows


@router.get("/resources/{project_id}/summary")
async def resources_summary(project_id: str,
                            user: dict = Depends(require_permission("projects", "read"))):
    await _resolve_project(project_id)
    rows = await db.project_resources.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    summary = {"manpower": 0.0, "material": 0.0, "tools": 0.0, "subcontract": 0.0,
                "manpower_count": 0, "material_count": 0, "tools_count": 0, "subcontract_count": 0,
                "grand_total": 0.0}
    for r in rows:
        rt = r.get("resource_type")
        if rt not in ("manpower", "material", "tools", "subcontract"):
            continue
        amt = _resource_total(r)
        summary[rt] = round(summary[rt] + amt, 2)
        summary[f"{rt}_count"] = summary[f"{rt}_count"] + 1
        summary["grand_total"] = round(summary["grand_total"] + amt, 2)
    return summary


@router.post("/resources/{project_id}")
async def create_resource(project_id: str, payload: ResourceIn,
                          user: dict = Depends(require_permission("projects", "write"))):
    await _resolve_project(project_id)
    if payload.wbs_id and not await db.project_wbs.find_one({"id": payload.wbs_id, "project_id": project_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "WBS node not found for this project")
    if payload.activity_id and not await db.project_activities.find_one({"id": payload.activity_id, "project_id": project_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Activity not found for this project")

    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "project_id": project_id,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    })
    await _enrich_resource(doc)
    doc["total_cost"] = _resource_total(doc)
    await db.project_resources.insert_one(doc)
    await audit(user=user, action="create", resource="project_resources",
                record_id=doc["id"], before={}, after=doc, ip="resources")
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/resources/{resource_id}")
async def update_resource(resource_id: str, payload: ResourceIn,
                          user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.project_resources.find_one({"id": resource_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Resource not found")
    patch = payload.model_dump()
    patch.update({
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    })
    await _enrich_resource(patch)
    patch["total_cost"] = _resource_total({**existing, **patch})
    await db.project_resources.update_one({"id": resource_id}, {"$set": patch})
    return await db.project_resources.find_one({"id": resource_id}, {"_id": 0})


@router.delete("/resources/{resource_id}")
async def delete_resource(resource_id: str,
                          user: dict = Depends(require_permission("projects", "delete"))):
    existing = await db.project_resources.find_one({"id": resource_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Resource not found")
    await db.project_resources.delete_one({"id": resource_id})
    await audit(user=user, action="delete", resource="project_resources",
                record_id=resource_id, before=existing, after={}, ip="resources")
    return {"ok": True}
