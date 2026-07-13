"""Projects & Operations · Service Type Master (Iter 94 — P&O Phase 1, Round 1).

A first-class master for the service categories the company offers (scaffolding,
painting, roof sheeting, rope access, manpower deployment, material supply,
site execution). Previously these existed only as hard-coded tag strings on
enquiries — making it impossible to maintain default rates, billing UOM, or
SLA per service.

Collection: `proj_service_types`
Schema:
    id (str)             — uuid
    code (str)           — short code e.g. SCF, PNT, RTS, RAC, MAN, MAT, EXEC
    name (str)           — display name
    category (str)       — service|material|manpower|safety
    billing_uom (str)    — sqm | lm | manday | MT | LS | nos
    default_rate (float) — per-uom rate (INR)
    description (str)    — free text
    sla_days (int)       — typical lead-time for execution
    parent_id (str)      — optional, for sub-services (e.g., "Rope painting" under "Painting")
    is_active (bool)
    created_at/by, updated_at/by
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id

router = APIRouter(prefix="/proj-masters", tags=["projects-ops-masters"])

# Default seed — pre-populated on first GET if collection is empty
_DEFAULT_SEED = [
    {"code": "SCF",  "name": "Scaffolding Services",    "category": "service",  "billing_uom": "cum",    "default_rate": 0.0, "sla_days": 7,  "description": "Erection / dismantling of scaffolding for height work"},
    {"code": "PNT",  "name": "Painting Services",       "category": "service",  "billing_uom": "sqm",    "default_rate": 0.0, "sla_days": 14, "description": "Industrial painting (epoxy, PU, intumescent, anti-corrosive)"},
    {"code": "RTS",  "name": "Roof Sheeting Services",  "category": "service",  "billing_uom": "sqm",    "default_rate": 0.0, "sla_days": 21, "description": "Roof sheeting installation, replacement, gutter work"},
    {"code": "RAC",  "name": "Rope Access Services",    "category": "service",  "billing_uom": "manday", "default_rate": 0.0, "sla_days": 5,  "description": "IRATA/SOFT certified rope-access execution"},
    {"code": "MAN",  "name": "Manpower Deployment",     "category": "manpower", "billing_uom": "manday", "default_rate": 0.0, "sla_days": 3,  "description": "Skilled / semi-skilled / supervisor deployment on contract"},
    {"code": "MAT",  "name": "Material Supply",         "category": "material", "billing_uom": "MT",     "default_rate": 0.0, "sla_days": 7,  "description": "Steel pipes, couplers, sheets, paint — direct material supply"},
    {"code": "EXEC", "name": "Site Execution Turnkey",  "category": "service",  "billing_uom": "LS",     "default_rate": 0.0, "sla_days": 30, "description": "Turnkey site execution incl. design, supply, install, handover"},
]


class ServiceTypeIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=2, max_length=120)
    category: str = Field("service", description="service|material|manpower|safety")
    billing_uom: str = Field("LS", description="sqm | lm | cum | manday | MT | LS | nos")
    default_rate: float = 0.0
    description: Optional[str] = ""
    sla_days: int = 0
    parent_id: Optional[str] = None
    is_active: bool = True


async def _seed_if_empty():
    n = await db.proj_service_types.count_documents({})
    if n == 0:
        for s in _DEFAULT_SEED:
            await db.proj_service_types.insert_one({
                **s, "id": new_id(), "parent_id": None, "is_active": True,
                "created_at": now_iso(), "created_by": "system",
            })


@router.get("/service-types")
async def list_service_types(active_only: bool = False,
                              user: dict = Depends(require_permission("projects", "read"))) -> List[Dict[str, Any]]:
    await _seed_if_empty()
    q: Dict[str, Any] = {}
    if active_only:
        q["is_active"] = True
    rows = await db.proj_service_types.find(q, {"_id": 0}).sort("code", 1).to_list(2000)
    # Hydrate parent name for sub-categories
    parents = {r["id"]: r.get("name") for r in rows if not r.get("parent_id")}
    for r in rows:
        if r.get("parent_id"):
            r["parent_name"] = parents.get(r["parent_id"])
    return rows


@router.post("/service-types")
async def create_service_type(payload: ServiceTypeIn,
                               user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.proj_service_types.find_one({"code": payload.code.upper().strip()})
    if existing:
        raise HTTPException(409, f"Service type with code '{payload.code}' already exists")
    doc = payload.model_dump()
    doc["code"] = doc["code"].upper().strip()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    await db.proj_service_types.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/service-types/{sid}")
async def update_service_type(sid: str, payload: ServiceTypeIn,
                               user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.proj_service_types.find_one({"id": sid})
    if not existing:
        raise HTTPException(404, "Service type not found")
    patch = payload.model_dump()
    patch["code"] = patch["code"].upper().strip()
    if patch["code"] != existing.get("code"):
        # Check uniqueness on rename
        clash = await db.proj_service_types.find_one({"code": patch["code"], "id": {"$ne": sid}})
        if clash:
            raise HTTPException(409, f"Code '{patch['code']}' already in use")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.proj_service_types.update_one({"id": sid}, {"$set": patch})
    return await db.proj_service_types.find_one({"id": sid}, {"_id": 0})


@router.delete("/service-types/{sid}")
async def delete_service_type(sid: str,
                               user: dict = Depends(require_permission("projects", "delete"))):
    # Refuse delete if any project references this service type
    in_use = await db.projects.find_one({"service_type_id": sid})
    if in_use:
        raise HTTPException(409,
            "Cannot delete — service type is in use by one or more projects. Deactivate it instead.")
    await db.proj_service_types.delete_one({"id": sid})
    return {"ok": True}


# ---------- Excel bulk template + import ----------
@router.get("/service-types/template.xlsx")
async def service_types_template(user: dict = Depends(require_permission("projects", "write"))):
    await _seed_if_empty()
    rows = await db.proj_service_types.find({}, {"_id": 0}).sort("code", 1).to_list(2000)
    wb = Workbook()
    ws = wb.active
    ws.title = "ServiceTypes"
    cols = ["id", "code", "name", "category", "billing_uom", "default_rate",
            "sla_days", "description", "is_active"]
    ws.append(cols)
    for c in ws[1]:
        c.font = c.font.copy(bold=True)
    for r in rows:
        ws.append([r.get(k, "") if r.get(k) is not None else "" for k in cols])
    inst = wb.create_sheet("INSTRUCTIONS")
    inst.append(["INDIAN TRADE LINKS — Service Type Master · Bulk Update"])
    inst.append([])
    inst.append(["1. Edit columns to change values. Empty = no change."])
    inst.append(["2. Add a new row with blank `id` to CREATE a new service type."])
    inst.append(["3. Allowed billing_uom values: sqm, lm, cum, manday, MT, LS, nos"])
    inst.append(["4. category: service / material / manpower / safety"])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="service-types-template-{datetime.now(timezone.utc).date()}.xlsx"'},
    )


# ---------- Stats (for dashboard widgets) ----------
@router.get("/service-types/stats")
async def service_type_stats(user: dict = Depends(require_permission("projects", "read"))):
    """Usage counts of each service type across active projects & enquiries."""
    out: List[Dict[str, Any]] = []
    types = await db.proj_service_types.find({"is_active": True}, {"_id": 0}).to_list(500)
    for t in types:
        proj_count = await db.projects.count_documents({"service_type_id": t["id"]})
        enq_count = await db.enquiries.count_documents({
            "$or": [
                {"service_type_id": t["id"]},
                {"service_categories": {"$in": [t["code"], t["code"].lower()]}},
            ]
        })
        out.append({
            "code": t["code"], "name": t["name"], "category": t.get("category"),
            "project_count": proj_count, "enquiry_count": enq_count,
        })
    return sorted(out, key=lambda x: x["project_count"] + x["enquiry_count"], reverse=True)
