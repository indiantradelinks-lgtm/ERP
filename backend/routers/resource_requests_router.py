"""Resource Request router (Iter 61, Phase 2).

Project Manager / Coordinator raises requests for non-purchase resources:
  Assets / Consumables / PPE / Manpower / Accommodation / Vehicles /
  Admin / Drivers / Tools / Other.

Goes through approval (`resource_request` chain → PM → Dept Head).
On approval, downstream departments service it:
  • Manpower → HR  • Vehicles/Drivers/Accommodation/Admin → admin_executive
  • Tools/Assets   → store_incharge

Endpoints (all under /api):
  POST   /ops/resource-requests
  GET    /ops/resource-requests
  GET    /ops/resource-requests/{id}
  PUT    /ops/resource-requests/{id}
  DELETE /ops/resource-requests/{id}
  POST   /ops/resource-requests/{id}/submit
  POST   /ops/resource-requests/{id}/cancel
  POST   /ops/resource-requests/{id}/service     (departments mark fulfilled)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, get_current_user, now_iso, new_id
from audit import audit
from sequences import next_sequence
from approval_engine import build_chain

logger = logging.getLogger("erp.resource_requests")
router = APIRouter(tags=["resource-requests"])

RESOURCE_TYPES = {
    "asset", "consumable", "ppe", "manpower",
    "accommodation", "vehicle", "admin", "driver",
    "tool", "other",
}

# Which department / role services which resource type once approved
SERVICE_OWNER = {
    "asset": "store_incharge",
    "consumable": "store_incharge",
    "ppe": "store_incharge",
    "tool": "store_incharge",
    "manpower": "hr_executive",
    "accommodation": "admin_executive",
    "vehicle": "admin_executive",
    "admin": "admin_executive",
    "driver": "admin_executive",
    "other": "admin_executive",
}

STATUSES = {
    "draft", "submitted", "pending_approval",
    "approved", "rejected", "in_progress",
    "completed", "cancelled",
}


class ResourceRequestIn(BaseModel):
    project_id: str
    resource_type: str = Field(..., description=f"One of {sorted(RESOURCE_TYPES)}")
    item_name: str = Field(..., min_length=2, max_length=160)
    quantity: float = 1
    unit: Optional[str] = "Nos"
    required_date: Optional[str] = None
    site_location: Optional[str] = None
    priority: str = "medium"
    justification: Optional[str] = None
    attachments: List[Dict[str, Any]] = []


class ResourceRequestUpdate(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    required_date: Optional[str] = None
    site_location: Optional[str] = None
    priority: Optional[str] = None
    justification: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class ServiceIn(BaseModel):
    status: str   # in_progress / completed
    actual_quantity: Optional[float] = None
    cost: Optional[float] = None
    remarks: Optional[str] = None


def _ip(r: Request) -> str:
    return r.client.host if r.client else "unknown"


def _scope(user: dict) -> Dict[str, Any]:
    role = user.get("role")
    if role in {"super_admin", "director", "general_manager", "dept_head", "accounts_executive"}:
        return {}
    uid = user.get("id")
    if role in {"project_manager", "project_coordinator", "site_team"}:
        # Project-context: any request on a project the user is assigned to OR created by user
        return {"$or": [
            {"requested_by_id": uid},
            {"project_manager_id": uid},
            {"project_coordinator_id": uid},
        ]}
    if role == "hr_executive":
        return {"resource_type": "manpower"}
    if role in {"store_incharge", "purchase_officer"}:
        return {"resource_type": {"$in": ["asset", "consumable", "ppe", "tool"]}}
    if role == "admin_executive":
        return {"resource_type": {"$in": ["accommodation", "vehicle", "admin", "driver", "other"]}}
    return {"requested_by_id": uid}


@router.post("/ops/resource-requests")
async def create_resource_request(payload: ResourceRequestIn, request: Request,
                                    user: dict = Depends(require_permission("projects", "write"))):
    if payload.resource_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"resource_type must be one of {sorted(RESOURCE_TYPES)}")
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["rr_no"] = await next_sequence("RR")
    doc["status"] = "draft"
    doc["project_name"] = proj.get("name")
    doc["project_manager_id"] = proj.get("project_manager_id")
    doc["project_coordinator_id"] = proj.get("project_coordinator_id")
    doc["requested_by"] = user.get("name") or user.get("email")
    doc["requested_by_id"] = user.get("id")
    doc["created_at"] = now_iso()
    await db.resource_requests.insert_one(doc)
    await audit(user=user, action="create", resource="resource_requests", record_id=doc["id"], after=doc, ip=_ip(request))
    doc.pop("_id", None)
    return doc


@router.get("/ops/resource-requests")
async def list_resource_requests(project_id: Optional[str] = None,
                                   status: Optional[str] = None,
                                   resource_type: Optional[str] = None,
                                   user: dict = Depends(require_permission("projects", "read"))):
    q: Dict[str, Any] = _scope(user)
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    if resource_type:
        q["resource_type"] = resource_type
    rows = await db.resource_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return rows


@router.get("/ops/resource-requests/{rid}")
async def get_resource_request(rid: str,
                                 user: dict = Depends(require_permission("projects", "read"))):
    row = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.put("/ops/resource-requests/{rid}")
async def update_resource_request(rid: str, payload: ResourceRequestUpdate, request: Request,
                                    user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    if existing.get("status") not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail=f"Cannot edit in '{existing.get('status')}' state")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    patch["updated_at"] = now_iso()
    await db.resource_requests.update_one({"id": rid}, {"$set": patch})
    fresh = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    await audit(user=user, action="update", resource="resource_requests", record_id=rid, after=patch, ip=_ip(request))
    return fresh


@router.delete("/ops/resource-requests/{rid}")
async def delete_resource_request(rid: str, request: Request,
                                    user: dict = Depends(require_permission("projects", "write"))):
    existing = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    if existing.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Only draft resource requests can be deleted")
    await db.resource_requests.delete_one({"id": rid})
    await audit(user=user, action="delete", resource="resource_requests", record_id=rid, before=existing, ip=_ip(request))
    return {"ok": True}


@router.post("/ops/resource-requests/{rid}/submit")
async def submit_resource_request(rid: str, request: Request, body: Optional[dict] = None,
                                    user: dict = Depends(require_permission("projects", "write"))):
    from approval_engine import insert_approval, copy_approval_doc_fields
    rr = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    if not rr:
        raise HTTPException(status_code=404, detail="Not found")
    if rr.get("status") not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail=f"Cannot submit in '{rr.get('status')}' state")
    chain = await build_chain("resource_request")
    approval_doc = {
        "id": new_id(),
        "type": "resource_request",
        "module": "resource_requests",
        "record_id": rid,
        "title": f"Resource Request {rr['rr_no']} — {rr['resource_type']} × {rr.get('quantity')}",
        "summary": f"{rr.get('item_name')} for project {rr.get('project_name')} ({rr.get('priority')} priority)",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    copy_approval_doc_fields(approval_doc, body)
    await insert_approval(approval_doc)
    await db.resource_requests.update_one({"id": rid}, {"$set": {
        "status": "pending_approval", "approval_id": approval_doc["id"],
        "submitted_at": now_iso(), "submitted_by_id": user.get("id"),
        "updated_at": now_iso(),
    }})
    # Notify approvers via existing approval-router fanout (handled in approval_engine on insert).
    # We additionally bell-notify the service owner role so they see what's pending.
    owner_role = SERVICE_OWNER.get(rr["resource_type"])
    if owner_role:
        users = await db.users.find({"role": owner_role, "active": True}, {"_id": 0, "id": 1}).to_list(20)
        for u in users:
            if u.get("id"):
                await db.notifications.insert_one({
                    "id": new_id(), "user_id": u["id"],
                    "kind": "ops.rr.submitted", "title": f"Resource request {rr['rr_no']}",
                    "message": f"{rr['resource_type']} × {rr.get('quantity')} requested for {rr.get('project_name')} — pending approval.",
                    "link": "/app/ops/resource-requests", "read": False, "at": now_iso(),
                })
    await audit(user=user, action="submit", resource="resource_requests", record_id=rid, ip=_ip(request))
    return {"ok": True, "approval_id": approval_doc["id"]}


@router.post("/ops/resource-requests/{rid}/cancel")
async def cancel_resource_request(rid: str, request: Request,
                                    user: dict = Depends(require_permission("projects", "write"))):
    rr = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    if not rr:
        raise HTTPException(status_code=404, detail="Not found")
    if rr.get("status") in {"completed", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Already {rr.get('status')}")
    await db.resource_requests.update_one({"id": rid}, {"$set": {
        "status": "cancelled", "cancelled_at": now_iso(),
        "cancelled_by_id": user.get("id"), "updated_at": now_iso(),
    }})
    await audit(user=user, action="cancel", resource="resource_requests", record_id=rid, ip=_ip(request))
    return {"ok": True}


@router.post("/ops/resource-requests/{rid}/service")
async def service_resource_request(rid: str, payload: ServiceIn, request: Request,
                                     user: dict = Depends(get_current_user)):
    rr = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    if not rr:
        raise HTTPException(status_code=404, detail="Not found")
    if rr.get("status") not in {"approved", "in_progress"}:
        raise HTTPException(status_code=400, detail=f"Cannot service in '{rr.get('status')}' state. Approve first.")
    owner_role = SERVICE_OWNER.get(rr["resource_type"])
    allowed_roles = {owner_role, "super_admin", "director", "general_manager", "dept_head"}
    if user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail=f"Only {owner_role} can service {rr['resource_type']} requests")
    set_doc: Dict[str, Any] = {"status": payload.status, "updated_at": now_iso(),
                                  "serviced_by_id": user.get("id"),
                                  "serviced_by": user.get("name") or user.get("email")}
    if payload.actual_quantity is not None:
        set_doc["actual_quantity"] = payload.actual_quantity
    if payload.cost is not None:
        set_doc["actual_cost"] = payload.cost
    if payload.remarks:
        set_doc["service_remarks"] = payload.remarks
    if payload.status == "completed":
        set_doc["completed_at"] = now_iso()
    await db.resource_requests.update_one({"id": rid}, {"$set": set_doc})
    await audit(user=user, action="service", resource="resource_requests", record_id=rid, after=set_doc, ip=_ip(request))
    return {"ok": True}
