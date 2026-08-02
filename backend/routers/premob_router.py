"""Pre-Mobilization checklist — simple item-wise material & manpower plan.

Each line: item type (material|manpower|other), name, qty, target completion
date, status. Delayed = past target date and not completed (computed on read).
Concerns: needs_extension (with proposed date) | on_hold | other.

Collection: premob_items. Endpoints under /api/ops/premob-items.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

router = APIRouter(prefix="/ops/premob-items", tags=["pre-mobilization"])

STATUSES = {"pending", "in_progress", "completed"}
CONCERN_TYPES = {"needs_extension", "on_hold", "other"}
CONCERN_LABELS = {"needs_extension": "Needs Date Extension", "on_hold": "On Hold", "other": "Other Problem"}


class PremobItemIn(BaseModel):
    project_id: str
    item_type: str = "material"          # material | manpower | other
    name: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    target_date: Optional[str] = None    # YYYY-MM-DD
    status: str = "pending"
    remarks: Optional[str] = None


class ConcernIn(BaseModel):
    type: str
    note: str = ""
    proposed_date: Optional[str] = None  # for needs_extension


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _notify_pms(item: dict, title: str, message: str) -> None:
    """Notify the item creator + all project managers."""
    try:
        pm_users = await db.users.find({"role": {"$in": ["project_manager"]}, "active": {"$ne": False}},
                                       {"_id": 0, "id": 1}).to_list(100)
        ids = {u["id"] for u in pm_users}
        if item.get("created_by"):
            ids.add(item["created_by"])
        for uid in ids:
            await db.notifications.insert_one({
                "id": new_id(), "user_id": uid, "kind": "premob",
                "title": title, "message": message,
                "link": "/app/ops/planning-hub?tab=premob", "read": False, "at": now_iso()})
    except Exception:
        pass


async def premob_delay_scan() -> int:
    """Daily scan: notify PMs about newly-delayed pre-mobilization items."""
    q = {"target_date": {"$lt": _today()}, "status": {"$ne": "completed"},
         "delayed_notified": {"$ne": True}}
    count = 0
    async for r in db.premob_items.find(q, {"_id": 0}):
        await _notify_pms(r, f"Pre-mobilization DELAYED — {r.get('name')}",
                          f"{r.get('project_code')} · {r.get('item_type')} '{r.get('name')}' missed target {r.get('target_date')}. Review or raise a concern.")
        await db.premob_items.update_one({"id": r["id"]}, {"$set": {"delayed_notified": True}})
        count += 1
    return count


def _flag(r: dict) -> dict:
    r["is_delayed"] = bool(r.get("target_date") and r["target_date"] < _today() and r.get("status") != "completed")
    return r


@router.get("")
async def list_items(project_id: str = "", item_type: str = "", status: str = "",
                     flagged: bool = False,
                     user: dict = Depends(require_permission("projects", "read"))):
    q: dict = {}
    if project_id:
        q["project_id"] = project_id
    if item_type:
        q["item_type"] = item_type
    if status:
        q["status"] = status
    rows = [_flag(r) for r in await db.premob_items.find(q, {"_id": 0}).sort("target_date", 1).to_list(2000)]
    if flagged:
        rows = [r for r in rows if r["is_delayed"] or r.get("concern")]
    return rows


@router.post("")
async def create_item(p: PremobItemIn, request: Request,
                      user: dict = Depends(require_permission("projects", "write"))):
    if p.item_type not in {"material", "manpower", "other"}:
        raise HTTPException(400, "item_type must be material | manpower | other")
    if p.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(STATUSES)}")
    proj = await db.projects.find_one({"id": p.project_id}, {"_id": 0, "id": 1, "code": 1, "name": 1})
    if not proj:
        raise HTTPException(404, "Project not found")
    doc = {**p.model_dump(), "id": new_id(),
           "project_code": proj.get("code"), "project_name": proj.get("name"),
           "concern": None, "concern_log": [], "completed_on": None,
           "created_at": now_iso(), "created_by": user["id"], "created_by_name": user.get("name")}
    if doc["status"] == "completed":
        doc["completed_on"] = _today()
    await db.premob_items.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="premob_items", record_id=doc["id"], after=doc,
                ip=request.client.host if request.client else "")
    return _flag(doc)


@router.put("/{item_id}")
async def update_item(item_id: str, p: PremobItemIn, request: Request,
                      user: dict = Depends(require_permission("projects", "write"))):
    before = await db.premob_items.find_one({"id": item_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Item not found")
    if p.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(STATUSES)}")
    patch = p.model_dump()
    patch.update({"updated_at": now_iso(), "updated_by": user["id"]})
    if p.status == "completed" and before.get("status") != "completed":
        patch["completed_on"] = _today()
    elif p.status != "completed":
        patch["completed_on"] = None
    await db.premob_items.update_one({"id": item_id}, {"$set": patch})
    out = await db.premob_items.find_one({"id": item_id}, {"_id": 0})
    await audit(user=user, action="update", resource="premob_items", record_id=item_id, before=before, after=out,
                ip=request.client.host if request.client else "")
    return _flag(out)


@router.delete("/{item_id}")
async def delete_item(item_id: str, request: Request,
                      user: dict = Depends(require_permission("projects", "write"))):
    before = await db.premob_items.find_one({"id": item_id}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Item not found")
    await db.premob_items.delete_one({"id": item_id})
    await audit(user=user, action="delete", resource="premob_items", record_id=item_id, before=before,
                ip=request.client.host if request.client else "")
    return {"ok": True}


@router.post("/{item_id}/concern")
async def raise_concern(item_id: str, c: ConcernIn, request: Request,
                        user: dict = Depends(require_permission("projects", "write"))):
    if c.type not in CONCERN_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(CONCERN_TYPES)}")
    row = await db.premob_items.find_one({"id": item_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Item not found")
    concern = {"type": c.type, "type_label": CONCERN_LABELS[c.type], "note": c.note,
               "proposed_date": c.proposed_date if c.type == "needs_extension" else None,
               "raised_by": user.get("name") or user["id"], "raised_at": now_iso()}
    await db.premob_items.update_one({"id": item_id}, {"$set": {"concern": concern},
                                                       "$push": {"concern_log": {**concern, "event": "raised"}}})
    out = await db.premob_items.find_one({"id": item_id}, {"_id": 0})
    await _notify_pms(row, f"Concern raised — {row.get('name')}",
                      f"{row.get('project_code')} · {CONCERN_LABELS[c.type]}"
                      + (f" (proposed {c.proposed_date})" if c.proposed_date and c.type == "needs_extension" else "")
                      + (f" — {c.note}" if c.note else "") + f" · raised by {user.get('name') or ''}")
    await audit(user=user, action="premob_concern_raised", resource="premob_items", record_id=item_id, after=concern,
                ip=request.client.host if request.client else "")
    return _flag(out)


@router.post("/{item_id}/concern/resolve")
async def resolve_concern(item_id: str, request: Request,
                          user: dict = Depends(require_permission("projects", "write"))):
    row = await db.premob_items.find_one({"id": item_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Item not found")
    if not row.get("concern"):
        raise HTTPException(400, "No open concern on this item")
    resolution = {"event": "resolved", "resolved_by": user.get("name") or user["id"], "resolved_at": now_iso()}
    update: dict = {"$set": {"concern": None}, "$push": {"concern_log": resolution}}
    # Extension approved: adopt proposed date as new target
    if row["concern"].get("type") == "needs_extension" and row["concern"].get("proposed_date"):
        update["$set"]["target_date"] = row["concern"]["proposed_date"]
    await db.premob_items.update_one({"id": item_id}, update)
    out = await db.premob_items.find_one({"id": item_id}, {"_id": 0})
    await audit(user=user, action="premob_concern_resolved", resource="premob_items", record_id=item_id,
                ip=request.client.host if request.client else "")
    return _flag(out)


@router.get("/summary")
async def summary(project_id: str = "",
                  user: dict = Depends(require_permission("projects", "read"))):
    q = {"project_id": project_id} if project_id else {}
    rows = [_flag(r) for r in await db.premob_items.find(q, {"_id": 0}).to_list(2000)]
    return {
        "total": len(rows),
        "completed": sum(1 for r in rows if r.get("status") == "completed"),
        "pending": sum(1 for r in rows if r.get("status") == "pending"),
        "in_progress": sum(1 for r in rows if r.get("status") == "in_progress"),
        "delayed": sum(1 for r in rows if r["is_delayed"]),
        "concerns": sum(1 for r in rows if r.get("concern")),
    }
