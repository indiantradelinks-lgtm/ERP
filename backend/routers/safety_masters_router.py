"""Safety Master Data · Iter 127
================================

One generic router that provides CRUD for the 13 Safety Master collections
listed in the Phase-1 spec:

    hazard_categories, risk_categories, control_measures,
    ppe_categories, work_permit_types, safety_training_types,
    incident_categories, observation_categories, corrective_action_categories,
    inspection_checklists, legal_compliance_requirements,
    emergency_responses, toolbox_talk_topics

Rather than 13 near-identical routers we keep a single whitelisted router.
Any master not in the whitelist returns 404 — this keeps the surface tight.

Route shape:
    GET    /api/safety/masters/{master}                — list active
    GET    /api/safety/masters/{master}?include_inactive=true
    POST   /api/safety/masters/{master}                — create
    PUT    /api/safety/masters/{master}/{item_id}      — update
    DELETE /api/safety/masters/{master}/{item_id}      — soft-delete (active=false)

Every row carries the same audit fields: id, code (optional), name, description,
active, created_at, created_by, updated_at, updated_by.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, now_iso, new_id, require_permission

router = APIRouter(prefix="/safety/masters", tags=["safety-masters"])

# Whitelisted master → collection name mapping. Add new masters here only.
MASTERS: Dict[str, str] = {
    "hazard-categories":              "safety_hazard_categories",
    "risk-categories":                "safety_risk_categories",
    "control-measures":               "safety_control_measures",
    "ppe-categories":                 "safety_ppe_categories",
    "work-permit-types":              "safety_work_permit_types",
    "safety-training-types":          "safety_training_types_master",
    "incident-categories":            "safety_incident_categories",
    "observation-categories":         "safety_observation_categories",
    "corrective-action-categories":   "safety_corrective_action_categories",
    "inspection-checklists":          "safety_inspection_checklists",
    "legal-compliance-requirements":  "safety_legal_compliance_requirements",
    "emergency-responses":            "safety_emergency_responses",
    "toolbox-talk-topics":            "safety_toolbox_talk_topics",
}


class MasterIn(BaseModel):
    code: Optional[str] = Field(None, max_length=40)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    color: Optional[str] = Field(None, max_length=30)         # optional UI hint (e.g. "danger" for high-risk)
    severity: Optional[str] = Field(None, max_length=20)       # low / medium / high / critical — used by Risk & Incident
    active: bool = True
    metadata: Optional[Dict[str, Any]] = None                  # future-proof escape hatch


def _coll(master: str):
    coll = MASTERS.get(master)
    if not coll:
        raise HTTPException(404, f"Unknown safety master '{master}'")
    return db[coll]


@router.get("")
async def list_all_masters(user: dict = Depends(require_permission("safety_masters", "read"))):
    """Return counts + slugs for every master — powers the tabbed Masters page."""
    out = []
    for slug, coll_name in MASTERS.items():
        total = await db[coll_name].count_documents({"active": True})
        out.append({"slug": slug, "collection": coll_name, "active_count": total})
    return out


@router.get("/{master}")
async def list_master(
    master: str,
    include_inactive: bool = False,
    user: dict = Depends(require_permission("safety_masters", "read")),
):
    q: Dict[str, Any] = {} if include_inactive else {"active": True}
    rows = await _coll(master).find(q, {"_id": 0}).sort("name", 1).to_list(2000)
    return rows


@router.post("/{master}")
async def create_master(
    master: str,
    payload: MasterIn,
    user: dict = Depends(require_permission("safety_masters", "write")),
):
    coll = _coll(master)
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    doc["updated_at"] = doc["created_at"]
    doc["updated_by"] = doc["created_by"]
    await coll.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{master}/{item_id}")
async def update_master(
    master: str,
    item_id: str,
    payload: MasterIn,
    user: dict = Depends(require_permission("safety_masters", "write")),
):
    coll = _coll(master)
    existing = await coll.find_one({"id": item_id})
    if not existing:
        raise HTTPException(404, "Master item not found")
    patch = payload.model_dump()
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await coll.update_one({"id": item_id}, {"$set": patch})
    return await coll.find_one({"id": item_id}, {"_id": 0})


@router.delete("/{master}/{item_id}")
async def delete_master(
    master: str,
    item_id: str,
    user: dict = Depends(require_permission("safety_masters", "delete")),
):
    """Soft-delete: set active=false. Master rows are never hard-deleted so
    that historical HIRA/JSA references remain intact."""
    coll = _coll(master)
    r = await coll.update_one({"id": item_id}, {"$set": {
        "active": False, "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
    }})
    if r.matched_count == 0:
        raise HTTPException(404, "Master item not found")
    return {"ok": True, "soft_deleted": True}


# ─── Seed defaults (idempotent) ────────────────────────────────────────────
DEFAULT_WORK_PERMIT_TYPES: List[Dict[str, Any]] = [
    {"code": "WAH",   "name": "Work at Height Permit",        "severity": "high"},
    {"code": "HOT",   "name": "Hot Work Permit",              "severity": "high"},
    {"code": "CS",    "name": "Confined Space Permit",        "severity": "critical"},
    {"code": "ELEC",  "name": "Electrical Work Permit",       "severity": "high"},
    {"code": "LIFT",  "name": "Lifting Work Permit",          "severity": "high"},
    {"code": "SCF-E", "name": "Scaffold Erection Permit",     "severity": "high"},
    {"code": "SCF-D", "name": "Scaffold Dismantling Permit",  "severity": "high"},
    {"code": "PAINT", "name": "Painting Work Permit",         "severity": "medium"},
    {"code": "ROOF",  "name": "Roof Sheeting Work Permit",    "severity": "high"},
    {"code": "ROPE",  "name": "Rope Access Work Permit",      "severity": "critical"},
    {"code": "GEN",   "name": "General Work Permit",          "severity": "low"},
]

DEFAULT_SAFETY_TRAINING_TYPES: List[Dict[str, Any]] = [
    {"code": "IND",   "name": "Safety Induction"},
    {"code": "WAH",   "name": "Work at Height Training"},
    {"code": "SCF-E", "name": "Scaffold Erector Training"},
    {"code": "SCF-S", "name": "Scaffold Supervisor Training"},
    {"code": "ROPE",  "name": "Rope Access Safety Training"},
    {"code": "FIRE",  "name": "Fire Safety Training"},
    {"code": "FA",    "name": "First Aid Training"},
    {"code": "PPE",   "name": "PPE Awareness"},
    {"code": "TBT",   "name": "Tool Box Talk"},
    {"code": "EMR",   "name": "Emergency Response Training"},
    {"code": "CLIENT","name": "Client Site Safety Training"},
]

DEFAULT_RISK_CATEGORIES: List[Dict[str, Any]] = [
    {"code": "LOW",  "name": "Low",       "severity": "low",      "color": "success"},
    {"code": "MED",  "name": "Medium",    "severity": "medium",   "color": "warning"},
    {"code": "HIGH", "name": "High",      "severity": "high",     "color": "danger"},
    {"code": "CRIT", "name": "Critical",  "severity": "critical", "color": "danger"},
]

DEFAULT_INCIDENT_CATEGORIES: List[Dict[str, Any]] = [
    {"code": "FA",   "name": "First Aid Case",     "severity": "low"},
    {"code": "MTC",  "name": "Medical Treatment",  "severity": "medium"},
    {"code": "RWC",  "name": "Restricted Work Case", "severity": "medium"},
    {"code": "LTI",  "name": "Lost Time Injury",   "severity": "high"},
    {"code": "FAT",  "name": "Fatality",           "severity": "critical"},
    {"code": "NM",   "name": "Near Miss",          "severity": "low"},
    {"code": "PD",   "name": "Property Damage",    "severity": "medium"},
    {"code": "ENV",  "name": "Environmental",      "severity": "medium"},
]


async def _seed_one(coll_name: str, rows: List[Dict[str, Any]]) -> int:
    """Insert rows that don't already exist by (name). Returns count inserted."""
    coll = db[coll_name]
    added = 0
    for r in rows:
        exists = await coll.find_one({"name": r["name"]}, {"_id": 0, "id": 1})
        if exists:
            continue
        doc = {
            **r,
            "id": new_id(),
            "active": True,
            "created_at": now_iso(),
            "created_by": "seed",
            "updated_at": now_iso(),
            "updated_by": "seed",
        }
        await coll.insert_one(doc)
        added += 1
    return added


async def seed_safety_masters() -> Dict[str, int]:
    """Idempotent seed for the mandatory default rows. Called on startup."""
    result = {
        "work_permit_types":     await _seed_one("safety_work_permit_types",         DEFAULT_WORK_PERMIT_TYPES),
        "safety_training_types": await _seed_one("safety_training_types_master",     DEFAULT_SAFETY_TRAINING_TYPES),
        "risk_categories":       await _seed_one("safety_risk_categories",           DEFAULT_RISK_CATEGORIES),
        "incident_categories":   await _seed_one("safety_incident_categories",       DEFAULT_INCIDENT_CATEGORIES),
    }
    return result


@router.post("/-/seed")
async def force_seed(user: dict = Depends(require_permission("safety_masters", "write"))):
    """Admin-triggered idempotent seed of the mandatory default rows."""
    return await seed_safety_masters()
