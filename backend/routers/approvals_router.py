"""Approval workflow endpoints."""
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, get_current_user
from approval_engine import build_chain, apply_action, APPROVAL_CHAINS

router = APIRouter(tags=["approvals"])


class ApprovalAction(BaseModel):
    action: str  # approve | reject | comment
    comment: Optional[str] = None


@router.post("/approvals/{approval_id}/action")
async def approval_action(approval_id: str, payload: ApprovalAction, user: dict = Depends(get_current_user)):
    approval = await db.approvals.find_one({"id": approval_id}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Not found")
    if not approval.get("chain"):
        approval["chain"] = build_chain(approval.get("type") or "expense")
        approval["current_step"] = 0
        approval["history"] = []
    try:
        updated = apply_action(approval, payload.action, user, payload.comment)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.approvals.update_one(
        {"id": approval_id},
        {"$set": {
            "chain": updated["chain"],
            "current_step": updated["current_step"],
            "history": updated["history"],
            "status": updated["status"],
            "updated_at": updated["updated_at"],
        }},
    )
    from routers.notifications_router import notify_approval_pending, notify_approval_decided
    by = user.get("name") or user.get("email", "")
    if payload.action == "approve":
        if updated["status"] == "approved":
            asyncio.create_task(notify_approval_decided(updated, "approve", by))
        else:
            asyncio.create_task(notify_approval_pending(updated))
    elif payload.action == "reject":
        asyncio.create_task(notify_approval_decided(updated, "reject", by))
    return updated


@router.get("/approvals-config/chains")
async def approval_chains(user: dict = Depends(get_current_user)):
    return APPROVAL_CHAINS


@router.get("/approvals/inbox/mine")
async def my_inbox(user: dict = Depends(get_current_user)):
    """Return approvals currently waiting on the logged-in user's role (or all pending for super_admin)."""
    role = user.get("role")
    rows = await db.approvals.find({"status": {"$in": ["pending", "in_progress", None]}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    out = []
    for r in rows:
        chain = r.get("chain") or []
        idx = r.get("current_step") or 0
        step = chain[idx] if 0 <= idx < len(chain) else None
        if not step:
            continue
        if role == "super_admin" or step.get("role") == role:
            r["_my_step"] = step
            out.append(r)
    return out


async def migrate_approvals_chain():
    """Backfill chain/history/current_step on legacy approval docs that lack them."""
    async for doc in db.approvals.find({"chain": {"$exists": False}}, {"_id": 0, "id": 1, "type": 1}):
        await db.approvals.update_one(
            {"id": doc["id"]},
            {"$set": {
                "chain": build_chain(doc.get("type") or "expense"),
                "current_step": 0,
                "history": [],
            }},
        )
