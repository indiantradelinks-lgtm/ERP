"""Per-user saved table views: auto-remembered last state + named presets."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id

router = APIRouter(prefix="/table-views", tags=["table-views"])

STATE_KEYS = {"search", "sort_by", "sort_dir", "page_size", "filters"}
PUBLISH_ROLES = {"super_admin", "director", "general_manager", "dept_head", "project_manager"}
ALL_DEPTS = "__all__"


def _shared_filter(user: dict) -> Dict[str, Any]:
    depts = [ALL_DEPTS]
    if user.get("department"):
        depts.append(user["department"])
    return {"kind": "shared", "table_any": True, "department": {"$in": depts}}


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


class SharedIn(BaseModel):
    name: str
    state: Dict[str, Any]
    department: Optional[str] = None  # publisher's dept by default; super_admin may pass "__all__"


@router.get("/{table}")
async def get_views(table: str, user: dict = Depends(get_current_user)):
    rows = await db.table_views.find({"user_id": user["id"], "table": table}, {"_id": 0}).to_list(100)
    last = next((r for r in rows if r.get("kind") == "last"), None)
    presets = sorted([r for r in rows if r.get("kind") == "preset"], key=lambda r: r.get("name", ""))
    sf = _shared_filter(user)
    sf.pop("table_any")
    sf["table"] = table
    shared = await db.table_views.find(sf, {"_id": 0}).sort("name", 1).to_list(100)
    for sh in shared:
        sh["can_delete"] = user.get("role") == "super_admin" or sh.get("user_id") == user["id"]
    # Department default: own-department default wins over an all-departments default
    defaults = [sh for sh in shared if sh.get("is_default")]
    default_shared = next((d for d in defaults if d.get("department") != ALL_DEPTS), None) or (defaults[0] if defaults else None)
    return {"last": (last or {}).get("state"), "presets": presets, "shared": shared,
            "default_shared": default_shared, "can_publish": user.get("role") in PUBLISH_ROLES}


@router.post("/{table}/shared/{view_id}/default")
async def set_default_shared(table: str, view_id: str, user: dict = Depends(get_current_user)):
    """Star one team view per table+department as the department default (toggle)."""
    view = await db.table_views.find_one({"id": view_id, "table": table, "kind": "shared"}, {"_id": 0})
    if not view:
        raise HTTPException(status_code=404, detail="Shared view not found")
    if user.get("role") != "super_admin" and view.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the publisher or super_admin can set the department default")
    make_default = not view.get("is_default")
    if make_default:
        await db.table_views.update_many({"table": table, "kind": "shared", "department": view.get("department")},
                                         {"$set": {"is_default": False}})
    await db.table_views.update_one({"id": view_id}, {"$set": {"is_default": make_default, "updated_at": now_iso()}})
    return {"ok": True, "is_default": make_default}


@router.post("/{table}/shared")
async def publish_shared(table: str, body: SharedIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in PUBLISH_ROLES:
        raise HTTPException(status_code=403, detail="Only department heads / managers can publish team views")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="View name is required")
    dept = body.department or user.get("department")
    if dept == ALL_DEPTS and user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can publish to all departments")
    if not dept:
        raise HTTPException(status_code=400, detail="Your user has no department set — ask admin to assign one")
    doc = {"id": new_id(), "user_id": user["id"], "published_by": user.get("name") or user.get("email"),
           "table": table, "kind": "shared", "department": dept, "name": name,
           "state": _clean_state(body.state), "updated_at": now_iso()}
    existing = await db.table_views.find_one({"table": table, "kind": "shared", "department": dept, "name": name}, {"_id": 0, "id": 1})
    if existing:
        await db.table_views.update_one({"id": existing["id"]}, {"$set": {k: doc[k] for k in ("state", "updated_at", "user_id", "published_by")}})
        doc["id"] = existing["id"]
    else:
        await db.table_views.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["can_delete"] = True
    return doc


@router.delete("/{table}/shared/{view_id}")
async def unpublish_shared(table: str, view_id: str, user: dict = Depends(get_current_user)):
    q: Dict[str, Any] = {"id": view_id, "table": table, "kind": "shared"}
    if user.get("role") != "super_admin":
        q["user_id"] = user["id"]
    r = await db.table_views.delete_one(q)
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Shared view not found (or not yours)")
    return {"ok": True}


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
