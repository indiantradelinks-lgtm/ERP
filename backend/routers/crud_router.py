"""Generic CRUD factory + module registration."""
import asyncio
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from core import db, require_permission, get_current_user, now_iso, new_id, logger
from approval_engine import build_chain

router = APIRouter(tags=["crud"])

MODULES = [
    ("clients", "clients"),
    ("vendors", "vendors"),
    ("employees", "employees"),
    ("attendance", "attendance"),
    ("projects", "projects"),
    ("inventory", "inventory"),
    ("purchase-orders", "purchase_orders"),
    ("quotations", "quotations"),
    ("journal-entries", "journal_entries"),
    ("safety-reports", "safety_reports"),
    ("assets", "assets"),
    ("payroll", "payroll"),
    ("vehicles", "vehicles"),
    ("documents", "documents"),
    ("approvals", "approvals"),
]


def make_crud(resource: str, collection: str, perm_key: str | None = None) -> None:
    perm = perm_key or collection

    @router.get(f"/{resource}")
    async def list_items(user: dict = Depends(require_permission(perm, "read"))):
        rows = await db[collection].find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
        return rows

    @router.post(f"/{resource}")
    async def create_item(payload: Dict[str, Any], user: dict = Depends(require_permission(perm, "write"))):
        doc = dict(payload)
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        doc["created_by"] = user["id"]
        if perm == "approvals" and not doc.get("chain"):
            doc["chain"] = build_chain(doc.get("type") or "expense")
            doc["current_step"] = 0
            doc["history"] = []
            doc["status"] = doc.get("status") or "pending"
        await db[collection].insert_one(doc)
        doc.pop("_id", None)
        if perm == "approvals":
            # Lazy import to avoid circular import
            from routers.notifications_router import notify_approval_pending
            asyncio.create_task(notify_approval_pending(doc))
        return doc

    @router.get(f"/{resource}/{{item_id}}")
    async def get_item(item_id: str, user: dict = Depends(require_permission(perm, "read"))):
        row = await db[collection].find_one({"id": item_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return row

    @router.put(f"/{resource}/{{item_id}}")
    async def update_item(item_id: str, payload: Dict[str, Any], user: dict = Depends(require_permission(perm, "write"))):
        payload.pop("id", None)
        payload["updated_at"] = now_iso()
        payload["updated_by"] = user["id"]
        result = await db[collection].update_one({"id": item_id}, {"$set": payload})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = await db[collection].find_one({"id": item_id}, {"_id": 0})
        return row

    @router.delete(f"/{resource}/{{item_id}}")
    async def delete_item(item_id: str, user: dict = Depends(require_permission(perm, "delete"))):
        result = await db[collection].delete_one({"id": item_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}


for _r, _c in MODULES:
    make_crud(_r, _c)
