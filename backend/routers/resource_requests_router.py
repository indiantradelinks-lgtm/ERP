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
    category: Optional[str] = None
    designation: Optional[str] = None
    designation_id: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    required_date: Optional[str] = None
    site_location: Optional[str] = None
    priority: Optional[str] = None
    justification: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class BulkLine(BaseModel):
    resource_type: str
    item_name: Optional[str] = None
    category: Optional[str] = None
    designation_id: Optional[str] = None
    designation: Optional[str] = None
    quantity: float = 1
    unit: Optional[str] = None
    justification: Optional[str] = None


class BulkRequestIn(BaseModel):
    project_id: str
    required_date: Optional[str] = None
    site_location: Optional[str] = None
    priority: str = "medium"
    justification: Optional[str] = None
    submit: bool = False
    documents: List[str] = []
    linked_attachments: List[str] = []
    documents_not_required: bool = False
    documents_not_required_reason: Optional[str] = None
    lines: List[BulkLine] = Field(..., min_length=1, max_length=50)


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


async def _submit_rr(rr: Dict[str, Any], user: dict, body: Optional[dict] = None) -> str:
    """Build approval chain, mark pending_approval, notify service owner. Returns approval_id."""
    from approval_engine import insert_approval, copy_approval_doc_fields
    chain = await build_chain("resource_request")
    approval_doc = {
        "id": new_id(),
        "type": "resource_request",
        "module": "resource_requests",
        "record_id": rr["id"],
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
    await db.resource_requests.update_one({"id": rr["id"]}, {"$set": {
        "status": "pending_approval", "approval_id": approval_doc["id"],
        "submitted_at": now_iso(), "submitted_by_id": user.get("id"),
        "updated_at": now_iso(),
    }})
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
    return approval_doc["id"]


@router.get("/ops/resource-requests/meta/designations")
async def rr_designations(user: dict = Depends(require_permission("projects", "read"))):
    """Designation master for manpower request lines (readable by project roles)."""
    return await db.hr_designations.find(
        {"active": {"$ne": False}}, {"_id": 0, "id": 1, "code": 1, "name": 1}
    ).sort("name", 1).to_list(500)


@router.post("/ops/resource-requests/bulk")
async def create_bulk_resource_requests(payload: BulkRequestIn, request: Request,
                                          user: dict = Depends(require_permission("projects", "write"))):
    result = await _bulk_create(payload, user, _ip(request))
    result.pop("created_docs", None)
    return result


async def _bulk_create(payload: BulkRequestIn, user: dict, ip: str) -> Dict[str, Any]:
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.submit:
        has_docs = bool(payload.documents or payload.linked_attachments)
        na_ok = payload.documents_not_required and len((payload.documents_not_required_reason or "").strip()) >= 5
        if not has_docs and not na_ok:
            raise HTTPException(status_code=400, detail="Reference documents are required for approval submission. Attach at least one file or mark 'Not Applicable' with a reason (min 5 chars).")
    desig_by_id = {d["id"]: d for d in await db.hr_designations.find({}, {"_id": 0}).to_list(500)}
    prepared: List[Dict[str, Any]] = []
    for idx, line in enumerate(payload.lines, start=1):
        if line.resource_type not in RESOURCE_TYPES:
            raise HTTPException(status_code=400, detail=f"Line {idx}: invalid resource_type '{line.resource_type}'")
        item_name = (line.item_name or "").strip()
        designation = (line.designation or "").strip()
        if line.resource_type == "manpower":
            if line.designation_id and line.designation_id in desig_by_id:
                designation = desig_by_id[line.designation_id]["name"]
            if not designation:
                raise HTTPException(status_code=400, detail=f"Line {idx}: designation is required for manpower")
            item_name = item_name or designation
        elif not item_name:
            raise HTTPException(status_code=400, detail=f"Line {idx}: item name is required")
        if line.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Line {idx}: quantity must be greater than 0")
        prepared.append({
            "resource_type": line.resource_type,
            "item_name": item_name,
            "category": (line.category or "").strip() or None,
            "designation": designation or None,
            "designation_id": line.designation_id or None,
            "quantity": line.quantity,
            "unit": line.unit or ("Persons" if line.resource_type == "manpower" else "Nos"),
            "justification": line.justification or payload.justification,
        })
    batch_id = new_id()
    created: List[Dict[str, Any]] = []
    for p in prepared:
        doc = {
            **p,
            "id": new_id(),
            "rr_no": await next_sequence("RR"),
            "status": "draft",
            "batch_id": batch_id,
            "project_id": payload.project_id,
            "project_name": proj.get("name"),
            "project_manager_id": proj.get("project_manager_id"),
            "project_coordinator_id": proj.get("project_coordinator_id"),
            "required_date": payload.required_date,
            "site_location": payload.site_location,
            "priority": payload.priority,
            "attachments": [],
            "requested_by": user.get("name") or user.get("email"),
            "requested_by_id": user.get("id"),
            "created_at": now_iso(),
        }
        await db.resource_requests.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)
    submitted = 0
    if payload.submit:
        doc_body = {
            "documents": payload.documents,
            "linked_attachments": payload.linked_attachments,
            "documents_not_required": payload.documents_not_required,
            "documents_not_required_reason": payload.documents_not_required_reason,
        }
        for doc in created:
            await _submit_rr(doc, user, doc_body)
            submitted += 1
    await audit(user=user, action="bulk_create", resource="resource_requests", record_id=batch_id,
                after={"count": len(created), "rr_nos": [c["rr_no"] for c in created], "submitted": submitted},
                ip=ip)
    return {"ok": True, "batch_id": batch_id, "count": len(created), "submitted": submitted,
            "rr_nos": [c["rr_no"] for c in created], "created_docs": created}


class FromPlanIn(BaseModel):
    project_id: str
    resource_ids: List[str] = Field(..., min_length=1, max_length=50)
    required_date: Optional[str] = None
    site_location: Optional[str] = None
    priority: str = "medium"
    justification: Optional[str] = None
    submit: bool = False
    documents: List[str] = []
    linked_attachments: List[str] = []
    documents_not_required: bool = False
    documents_not_required_reason: Optional[str] = None


def _material_rr_type(category: str) -> str:
    c = (category or "").lower()
    if "ppe" in c or "safety" in c:
        return "ppe"
    if "tool" in c:
        return "tool"
    return "consumable"


@router.post("/ops/resource-requests/from-plan")
async def create_requests_from_plan(payload: FromPlanIn, request: Request,
                                      user: dict = Depends(require_permission("projects", "write"))):
    """Convert Resource Planning lines (project_resources) into resource requests."""
    rows = await db.project_resources.find(
        {"id": {"$in": payload.resource_ids}, "project_id": payload.project_id}, {"_id": 0}
    ).to_list(100)
    found = {r["id"]: r for r in rows}
    missing = [rid for rid in payload.resource_ids if rid not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"{len(missing)} plan line(s) not found for this project")
    already = [r for r in rows if r.get("rr_batch_id")]
    if already:
        raise HTTPException(status_code=400, detail=f"Already converted to requests: {', '.join(r.get('rr_no') or r['id'][:8] for r in already)}")
    ordered = [found[rid] for rid in payload.resource_ids]
    lines: List[BulkLine] = []
    for r in ordered:
        rt = r.get("resource_type")
        if rt == "manpower":
            lines.append(BulkLine(
                resource_type="manpower",
                designation_id=r.get("designation_id"),
                designation=r.get("designation_name"),
                quantity=float(r.get("count_required") or 1),
                unit="Persons",
            ))
        elif rt == "material":
            lines.append(BulkLine(
                resource_type=_material_rr_type(r.get("category")),
                item_name=r.get("item_name"),
                category=r.get("category"),
                quantity=float(r.get("quantity") or 1),
                unit=r.get("uom") or "Nos",
            ))
        elif rt == "tools":
            lines.append(BulkLine(
                resource_type="tool",
                item_name=r.get("tool_name"),
                category=r.get("tool_category"),
                quantity=float(r.get("count_required") or 1),
                unit="Nos",
                justification=r.get("specification") or None,
            ))
        else:
            raise HTTPException(status_code=400, detail=f"Plan line type '{rt}' cannot be converted to a resource request (sub-contract goes via vendor/PO flow)")
    bulk = BulkRequestIn(
        project_id=payload.project_id,
        required_date=payload.required_date or (ordered[0].get("required_by_date") or None),
        site_location=payload.site_location,
        priority=payload.priority,
        justification=payload.justification,
        submit=payload.submit,
        documents=payload.documents,
        linked_attachments=payload.linked_attachments,
        documents_not_required=payload.documents_not_required,
        documents_not_required_reason=payload.documents_not_required_reason,
        lines=lines,
    )
    result = await _bulk_create(bulk, user, _ip(request))
    created = result.pop("created_docs", [])
    for plan_row, rr_doc in zip(ordered, created):
        await db.project_resources.update_one({"id": plan_row["id"]}, {"$set": {
            "rr_batch_id": result["batch_id"], "rr_id": rr_doc["id"], "rr_no": rr_doc["rr_no"],
            "rr_requested_at": now_iso(), "rr_requested_by": user.get("name") or user.get("email"),
        }})
    return result


@router.post("/ops/resource-requests/{rid}/submit")
async def submit_resource_request(rid: str, request: Request, body: Optional[dict] = None,
                                    user: dict = Depends(require_permission("projects", "write"))):
    rr = await db.resource_requests.find_one({"id": rid}, {"_id": 0})
    if not rr:
        raise HTTPException(status_code=404, detail="Not found")
    if rr.get("status") not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail=f"Cannot submit in '{rr.get('status')}' state")
    approval_id = await _submit_rr(rr, user, body)
    await audit(user=user, action="submit", resource="resource_requests", record_id=rid, ip=_ip(request))
    return {"ok": True, "approval_id": approval_id}


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
