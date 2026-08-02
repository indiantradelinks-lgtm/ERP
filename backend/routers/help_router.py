"""Page Help Guides — per-page user instructions with super-admin editing.

Resolution order: DB override (page_guides) → built-in seed → longest prefix.
Endpoints under /api/help.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, now_iso
from help_guides_seed import GUIDES
from help_guides_seed2 import GUIDES2

router = APIRouter(prefix="/help", tags=["help"])

ALL_GUIDES = {**GUIDES, **GUIDES2}


class GuideIn(BaseModel):
    path: str
    title: str
    description: str = ""
    steps: List[str] = []
    tips: List[str] = []


def _norm(path: str) -> str:
    return (path or "").split("?")[0].rstrip("/") or "/app"


async def _resolve(path: str) -> Optional[dict]:
    override = await db.page_guides.find_one({"path": path}, {"_id": 0})
    if override:
        return {**override, "source": "custom"}
    if path in ALL_GUIDES:
        return {**ALL_GUIDES[path], "path": path, "source": "builtin"}
    # longest prefix fallback (e.g. /app/hr/employee-360/xyz → /app/hr/employee-360)
    candidates = [p for p in ALL_GUIDES if p != "/app" and path.startswith(p + "/")]
    ov_paths = [d["path"] async for d in db.page_guides.find({}, {"_id": 0, "path": 1})]
    candidates += [p for p in ov_paths if p != "/app" and path.startswith(p + "/")]
    if candidates:
        best = max(candidates, key=len)
        return await _resolve(best)
    return None


@router.get("/guide")
async def get_guide(path: str, user: dict = Depends(get_current_user)):
    key = _norm(path)
    guide = await _resolve(key)
    can_edit = user.get("role") == "super_admin"
    if not guide:
        return {"found": False, "path": key, "can_edit": can_edit,
                "title": "Page Guide", "description": "No guide has been written for this page yet.",
                "steps": [], "tips": []}
    return {"found": True, "can_edit": can_edit, **guide, "path": key}


@router.put("/guide")
async def save_guide(p: GuideIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Only super admin can edit page guides")
    key = _norm(p.path)
    doc = {"path": key, "title": p.title.strip(), "description": p.description.strip(),
           "steps": [s.strip() for s in p.steps if s.strip()],
           "tips": [t.strip() for t in p.tips if t.strip()],
           "updated_at": now_iso(), "updated_by": user.get("name") or user["id"]}
    await db.page_guides.update_one({"path": key}, {"$set": doc}, upsert=True)
    return {**doc, "found": True, "can_edit": True, "source": "custom"}


@router.delete("/guide")
async def reset_guide(path: str, user: dict = Depends(get_current_user)):
    """Remove the custom override — page falls back to the built-in guide."""
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Only super admin can edit page guides")
    await db.page_guides.delete_one({"path": _norm(path)})
    return {"ok": True}
