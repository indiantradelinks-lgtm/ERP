"""Per-user saved table views: auto-remembered last state + named presets."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id

router = APIRouter(prefix="/table-views", tags=["table-views"])

STATE_KEYS = {"search", "sort_by", "sort_dir", "page_size", "filters"}


def _clean_state(state: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in (state or {}).items() if k in STATE_KEYS}
    if "page_size" in out:
        out["page_size"] = max(1, min(int(out["page_size"] or 50), 200))
    return out


class ViewState(BaseModel):
    state: Dict[str, Any]


class PresetIn(BaseModel):
    name: str
    state: Dict[str, Any]


@router.get("/{table}")
async def get_views(table: str, user: dict = Depends(get_current_user)):
    rows = await db.table_views.find({"user_id": user["id"], "table": table}, {"_id": 0}).to_list(100)
    last = next((r for r in rows if r.get("kind") == "last"), None)
    presets = sorted([r for r in rows if r.get("kind") == "preset"], key=lambda r: r.get("name", ""))
    return {"last": (last or {}).get("state"), "presets": presets}


@router.put("/{table}/last")
async def save_last(table: str, body: ViewState, user: dict = Depends(get_current_user)):
    await db.table_views.update_one(
        {"user_id": user["id"], "table": table, "kind": "last"},
        {"$set": {"state": _clean_state(body.state), "updated_at": now_iso()},
         "$setOnInsert": {"id": new_id(), "user_id": user["id"], "table": table, "kind": "last"}},
        upsert=True,
    )
    return {"ok": True}


@router.delete("/{table}/last")
async def reset_last(table: str, user: dict = Depends(get_current_user)):
    await db.table_views.delete_one({"user_id": user["id"], "table": table, "kind": "last"})
    return {"ok": True}


@router.post("/{table}/presets")
async def create_preset(table: str, body: PresetIn, user: dict = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Preset name is required")
    doc = {"id": new_id(), "user_id": user["id"], "table": table, "kind": "preset", "name": name,
           "state": _clean_state(body.state), "updated_at": now_iso()}
    existing: Optional[dict] = await db.table_views.find_one(
        {"user_id": user["id"], "table": table, "kind": "preset", "name": name}, {"_id": 0, "id": 1})
    if existing:
        await db.table_views.update_one({"id": existing["id"]}, {"$set": {"state": doc["state"], "updated_at": doc["updated_at"]}})
        doc["id"] = existing["id"]
    else:
        await db.table_views.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.delete("/{table}/presets/{preset_id}")
async def delete_preset(table: str, preset_id: str, user: dict = Depends(get_current_user)):
    r = await db.table_views.delete_one({"id": preset_id, "user_id": user["id"], "table": table, "kind": "preset"})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"ok": True}
