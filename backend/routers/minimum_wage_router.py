"""Minimum Wage Master — state-wise / skill-wise / designation-wise wage rates.

Rows: {state, zone?, skill_category, designation?, wage_per_day, wage_per_month,
       vda_per_month?, effective_from, notes, active}
Designation rows (optional) override the plain skill-category rate for that state.
"""
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from openpyxl import Workbook

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/hr/minimum-wages", tags=["minimum-wages"])

SKILL_CATEGORIES = ["unskilled", "semi_skilled", "skilled", "highly_skilled", "clerical"]


class WageIn(BaseModel):
    state: str = Field(..., min_length=2)
    zone: str = ""
    skill_category: str = "unskilled"
    designation: str = ""
    wage_per_day: float = 0
    wage_per_month: float = 0
    vda_per_month: float = 0
    effective_from: str = ""
    notes: str = ""
    active: bool = True

    def clean(self) -> dict:
        if self.skill_category not in SKILL_CATEGORIES:
            raise HTTPException(400, f"skill_category must be one of {SKILL_CATEGORIES}")
        if self.wage_per_day <= 0 and self.wage_per_month <= 0:
            raise HTTPException(400, "Provide wage_per_day or wage_per_month")
        d = self.model_dump()
        d["state"] = self.state.strip().title()
        d["designation"] = self.designation.strip()
        # auto-derive the missing figure (26 working days convention)
        if d["wage_per_day"] <= 0:
            d["wage_per_day"] = round(d["wage_per_month"] / 26, 2)
        if d["wage_per_month"] <= 0:
            d["wage_per_month"] = round(d["wage_per_day"] * 26, 2)
        return d


@router.get("")
async def list_wages(state: Optional[str] = None, skill_category: Optional[str] = None,
                     designation: Optional[str] = None, q: Optional[str] = None,
                     active_only: bool = False,
                     user: dict = Depends(require_permission("employees", "read"))):
    query: dict = {}
    if state:
        query["state"] = state
    if skill_category:
        query["skill_category"] = skill_category
    if designation:
        query["designation"] = {"$regex": designation, "$options": "i"}
    if active_only:
        query["active"] = {"$ne": False}
    rows = await db.minimum_wages.find(query, {"_id": 0}).sort([("state", 1), ("skill_category", 1), ("designation", 1)]).to_list(2000)
    if q:
        s = q.lower()
        rows = [r for r in rows if s in (r.get("state") or "").lower()
                or s in (r.get("designation") or "").lower() or s in (r.get("notes") or "").lower()]
    return rows


@router.get("/lookup")
async def lookup_wage(state: str, skill_category: str = "unskilled", designation: Optional[str] = None,
                      user: dict = Depends(require_permission("employees", "read"))):
    """Best-match rate: designation-specific row first, else the skill-category row."""
    base = {"state": state.strip().title(), "active": {"$ne": False}}
    if designation:
        row = await db.minimum_wages.find_one({**base, "designation": {"$regex": f"^{designation.strip()}$", "$options": "i"}}, {"_id": 0})
        if row:
            return row
    row = await db.minimum_wages.find_one({**base, "skill_category": skill_category, "designation": ""}, {"_id": 0})
    if not row:
        raise HTTPException(404, "No minimum wage configured for this state/skill")
    return row


@router.post("")
async def create_wage(payload: WageIn, user: dict = Depends(require_permission("employees", "write"))):
    d = payload.clean()
    dup = await db.minimum_wages.find_one({"state": d["state"], "zone": d["zone"],
                                           "skill_category": d["skill_category"],
                                           "designation": d["designation"]}, {"_id": 0, "id": 1})
    if dup:
        raise HTTPException(409, "A rate for this state/zone/skill/designation already exists — edit it instead")
    doc = {"id": new_id(), **d, "created_at": now_iso(), "created_by": user.get("name"),
           "updated_at": None, "updated_by": None}
    await db.minimum_wages.insert_one({**doc})
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="minimum_wages", record_id=doc["id"], after=d, ip="hr")
    return doc


@router.put("/{wid}")
async def update_wage(wid: str, payload: WageIn, user: dict = Depends(require_permission("employees", "write"))):
    d = payload.clean()
    before = await db.minimum_wages.find_one({"id": wid}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Not found")
    await db.minimum_wages.update_one({"id": wid}, {"$set": {**d, "updated_at": now_iso(), "updated_by": user.get("name")}})
    await audit(user=user, action="update", resource="minimum_wages", record_id=wid, before=before, after=d, ip="hr")
    return await db.minimum_wages.find_one({"id": wid}, {"_id": 0})


@router.delete("/{wid}")
async def delete_wage(wid: str, user: dict = Depends(require_permission("employees", "delete"))):
    before = await db.minimum_wages.find_one({"id": wid}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Not found")
    await db.minimum_wages.delete_one({"id": wid})
    await audit(user=user, action="delete", resource="minimum_wages", record_id=wid, before=before, ip="hr")
    return {"ok": True}


@router.get("/export")
async def export_wages(user: dict = Depends(require_permission("employees", "read"))):
    rows = await db.minimum_wages.find({}, {"_id": 0}).sort([("state", 1), ("skill_category", 1)]).to_list(2000)
    wb = Workbook()
    ws = wb.active
    ws.title = "MINIMUM WAGES"
    ws.append(["State", "Zone", "Skill Category", "Designation", "Wage / Day (₹)", "Wage / Month (₹)",
               "VDA / Month (₹)", "Effective From", "Active", "Notes"])
    for r in rows:
        ws.append([r.get("state"), r.get("zone"), r.get("skill_category"), r.get("designation"),
                   r.get("wage_per_day"), r.get("wage_per_month"), r.get("vda_per_month"),
                   r.get("effective_from"), "Yes" if r.get("active", True) else "No", r.get("notes")])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="minimum_wage_master.xlsx"'})


# Indicative published rates — HR must verify against the latest state notification.
_DEFAULTS = [
    ("Delhi", "unskilled", 18066), ("Delhi", "semi_skilled", 19929),
    ("Delhi", "skilled", 21917), ("Delhi", "clerical", 19929),
    ("Haryana", "unskilled", 11001), ("Haryana", "semi_skilled", 11551),
    ("Haryana", "skilled", 12736), ("Haryana", "highly_skilled", 13416),
    ("Uttar Pradesh", "unskilled", 10648), ("Uttar Pradesh", "semi_skilled", 11713),
    ("Uttar Pradesh", "skilled", 13121),
    ("Gujarat", "unskilled", 11752), ("Gujarat", "semi_skilled", 12064),
    ("Gujarat", "skilled", 12428),
    ("Maharashtra", "unskilled", 13748), ("Maharashtra", "semi_skilled", 14892),
    ("Maharashtra", "skilled", 16036),
]


@router.post("/seed-defaults")
async def seed_defaults(user: dict = Depends(require_permission("employees", "write"))):
    """Idempotent — inserts indicative standard rates only for state/skill combos not present."""
    created = 0
    for state, skill, monthly in _DEFAULTS:
        if await db.minimum_wages.find_one({"state": state, "skill_category": skill, "designation": ""}, {"_id": 0, "id": 1}):
            continue
        await db.minimum_wages.insert_one({
            "id": new_id(), "state": state, "zone": "", "skill_category": skill, "designation": "",
            "wage_per_day": round(monthly / 26, 2), "wage_per_month": float(monthly), "vda_per_month": 0,
            "effective_from": "", "active": True,
            "notes": "Indicative seeded rate — verify against latest state notification",
            "created_at": now_iso(), "created_by": user.get("name"), "updated_at": None, "updated_by": None,
        })
        created += 1
    await audit(user=user, action="seed_defaults", resource="minimum_wages", record_id="seed",
                after={"created": created}, ip="hr")
    return {"ok": True, "created": created}
