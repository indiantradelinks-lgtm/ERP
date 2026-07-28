"""HR · Group Medical (GMC) Policy management.

Policies (insurer/policy no/period) + member enrolment pulled from the
Employee Master (single source of truth). Members can be filtered
project-wise, designation-wise or head-office-wise. When an employee's
exit/FNF is finalised the member row is auto-removed (see hr/exit_fnf.py).
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from exports import to_excel, to_pdf

router = APIRouter(tags=["gmc"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


class PolicyIn(BaseModel):
    policy_number: str
    insurer: str
    tpa: Optional[str] = None
    policy_start: Optional[str] = None
    policy_end: Optional[str] = None
    sum_insured_default: float = 0
    premium_total: float = 0
    notes: Optional[str] = None
    status: str = "active"


class BulkAddIn(BaseModel):
    policy_id: str
    employee_ids: list[str]
    coverage_scope: str = "auto"     # auto | project | head_office
    project_code: Optional[str] = None
    sum_insured: Optional[float] = None
    premium: Optional[float] = None
    dependents: int = 0


class MemberPatch(BaseModel):
    coverage_scope: Optional[str] = None
    project_code: Optional[str] = None
    sum_insured: Optional[float] = None
    premium: Optional[float] = None
    dependents: Optional[int] = None
    designation: Optional[str] = None


class RemoveIn(BaseModel):
    reason: Optional[str] = None


# ─── Policies ────────────────────────────────────────────────────────────
@router.get("/gmc/policies")
async def list_policies(user: dict = Depends(require_permission("hr_gmc", "read"))):
    rows = await db.gmc_policies.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for p in rows:
        p["active_members"] = await db.gmc_members.count_documents({"policy_id": p["id"], "status": "active"})
    return rows


@router.post("/gmc/policies")
async def create_policy(p: PolicyIn, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    if await db.gmc_policies.find_one({"policy_number": p.policy_number}, {"_id": 0, "id": 1}):
        raise HTTPException(400, "Policy number already exists")
    doc = {"id": new_id(), **p.model_dump(), "created_at": now_iso(),
           "created_by": user.get("name") or user.get("email")}
    await db.gmc_policies.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="gmc_policies", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/gmc/policies/{pid}")
async def update_policy(pid: str, p: PolicyIn, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_policies.find_one({"id": pid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    await db.gmc_policies.update_one({"id": pid}, {"$set": {**p.model_dump(), "updated_at": now_iso()}})
    await audit(user=user, action="update", resource="gmc_policies", record_id=pid, before=row, after=p.model_dump(), ip=_ip(request))
    return await db.gmc_policies.find_one({"id": pid}, {"_id": 0})


@router.delete("/gmc/policies/{pid}")
async def delete_policy(pid: str, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "delete"))):
    if await db.gmc_members.count_documents({"policy_id": pid, "status": "active"}):
        raise HTTPException(400, "Policy has active members — remove them first")
    await db.gmc_policies.delete_one({"id": pid})
    await db.gmc_members.delete_many({"policy_id": pid})
    await audit(user=user, action="delete", resource="gmc_policies", record_id=pid, ip=_ip(request))
    return {"deleted": True}


# ─── Members ─────────────────────────────────────────────────────────────
def _member_query(policy_id: Optional[str], scope: Optional[str], project_code: Optional[str],
                  designation: Optional[str], status: Optional[str], q: Optional[str]) -> dict:
    query: dict = {}
    if policy_id:
        query["policy_id"] = policy_id
    if scope:
        query["coverage_scope"] = scope
    if project_code:
        query["project_code"] = project_code
    if designation:
        query["designation"] = designation
    if status:
        query["status"] = status
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                        {"emp_code": {"$regex": q, "$options": "i"}}]
    return query


@router.get("/gmc/members")
async def list_members(policy_id: Optional[str] = None, scope: Optional[str] = None,
                       project_code: Optional[str] = None, designation: Optional[str] = None,
                       status: Optional[str] = None, q: Optional[str] = None,
                       user: dict = Depends(require_permission("hr_gmc", "read"))):
    query = _member_query(policy_id, scope, project_code, designation, status, q)
    return await db.gmc_members.find(query, {"_id": 0}).sort("name", 1).to_list(3000)


@router.get("/gmc/summary")
async def gmc_summary(policy_id: Optional[str] = None,
                      user: dict = Depends(require_permission("hr_gmc", "read"))):
    q: dict = {"policy_id": policy_id} if policy_id else {}
    active = await db.gmc_members.find({**q, "status": "active"}, {"_id": 0, "sum_insured": 1, "premium": 1, "coverage_scope": 1, "dependents": 1}).to_list(5000)
    removed = await db.gmc_members.count_documents({**q, "status": "removed"})
    return {
        "active": len(active),
        "removed": removed,
        "head_office": sum(1 for m in active if m.get("coverage_scope") == "head_office"),
        "project": sum(1 for m in active if m.get("coverage_scope") == "project"),
        "dependents": sum(int(m.get("dependents") or 0) for m in active),
        "sum_insured_total": sum(float(m.get("sum_insured") or 0) for m in active),
        "premium_total": sum(float(m.get("premium") or 0) for m in active),
    }


@router.get("/gmc/eligible-employees")
async def eligible_employees(policy_id: str, q: Optional[str] = None,
                             user: dict = Depends(require_permission("hr_gmc", "read"))):
    enrolled = await db.gmc_members.distinct("employee_id", {"policy_id": policy_id, "status": "active"})
    query: dict = {"status": {"$nin": ["exited", "inactive"]}, "id": {"$nin": enrolled}}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                        {"emp_code": {"$regex": q, "$options": "i"}}]
    rows = await db.employees.find(query, {"_id": 0, "id": 1, "emp_code": 1, "name": 1,
                                           "designation": 1, "department": 1,
                                           "current_project_code": 1}).sort("name", 1).to_list(2000)
    return rows


@router.post("/gmc/members/bulk-add")
async def bulk_add_members(p: BulkAddIn, request: Request,
                           user: dict = Depends(require_permission("hr_gmc", "write"))):
    policy = await db.gmc_policies.find_one({"id": p.policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy not found")
    if not p.employee_ids:
        raise HTTPException(400, "Select at least one employee")
    added, skipped = [], []
    for eid in p.employee_ids:
        emp = await db.employees.find_one({"id": eid}, {"_id": 0})
        if not emp or emp.get("status") in ("exited", "inactive"):
            skipped.append(eid); continue
        if await db.gmc_members.find_one({"policy_id": p.policy_id, "employee_id": eid, "status": "active"}, {"_id": 0, "id": 1}):
            skipped.append(eid); continue
        proj = p.project_code or emp.get("current_project_code") or ""
        scope = p.coverage_scope if p.coverage_scope in ("project", "head_office") else ("project" if proj else "head_office")
        doc = {
            "id": new_id(), "policy_id": p.policy_id, "employee_id": eid,
            "emp_code": emp.get("emp_code") or "", "name": emp.get("name") or "",
            "designation": emp.get("designation") or "", "department": emp.get("department") or "",
            "coverage_scope": scope, "project_code": proj if scope == "project" else "",
            "sum_insured": p.sum_insured if p.sum_insured is not None else float(policy.get("sum_insured_default") or 0),
            "premium": p.premium if p.premium is not None else 0,
            "dependents": p.dependents, "status": "active",
            "added_at": now_iso(), "added_by": user.get("name") or user.get("email"),
            "removed_at": None, "removed_by": None, "removal_reason": None,
        }
        await db.gmc_members.insert_one(doc); doc.pop("_id", None)
        added.append(doc)
    await audit(user=user, action="gmc_bulk_add", resource="gmc_members",
                record_id=p.policy_id, after={"added": len(added), "skipped": len(skipped)}, ip=_ip(request))
    return {"added": len(added), "skipped": len(skipped)}


@router.put("/gmc/members/{mid}")
async def update_member(mid: str, p: MemberPatch, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_members.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    patch = {k: v for k, v in p.model_dump().items() if v is not None}
    if patch.get("coverage_scope") == "head_office":
        patch["project_code"] = ""
    await db.gmc_members.update_one({"id": mid}, {"$set": {**patch, "updated_at": now_iso()}})
    await audit(user=user, action="update", resource="gmc_members", record_id=mid, before=row, after=patch, ip=_ip(request))
    return await db.gmc_members.find_one({"id": mid}, {"_id": 0})


@router.post("/gmc/members/{mid}/remove")
async def remove_member(mid: str, p: RemoveIn, request: Request,
                        user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_members.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row.get("status") == "removed":
        raise HTTPException(400, "Already removed")
    await db.gmc_members.update_one({"id": mid}, {"$set": {
        "status": "removed", "removed_at": now_iso(),
        "removed_by": user.get("name") or user.get("email"),
        "removal_reason": p.reason or "Removed manually"}})
    await audit(user=user, action="gmc_remove", resource="gmc_members", record_id=mid,
                after={"reason": p.reason}, ip=_ip(request))
    return await db.gmc_members.find_one({"id": mid}, {"_id": 0})


@router.post("/gmc/members/{mid}/restore")
async def restore_member(mid: str, request: Request,
                         user: dict = Depends(require_permission("hr_gmc", "write"))):
    row = await db.gmc_members.find_one({"id": mid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    emp = await db.employees.find_one({"id": row["employee_id"]}, {"_id": 0, "status": 1})
    if not emp or emp.get("status") in ("exited", "inactive"):
        raise HTTPException(400, "Employee is exited/inactive — cannot restore cover")
    await db.gmc_members.update_one({"id": mid}, {"$set": {
        "status": "active", "removed_at": None, "removed_by": None, "removal_reason": None}})
    await audit(user=user, action="gmc_restore", resource="gmc_members", record_id=mid, ip=_ip(request))
    return await db.gmc_members.find_one({"id": mid}, {"_id": 0})


@router.get("/gmc/export.{fmt}")
async def export_members(fmt: str, policy_id: Optional[str] = None, scope: Optional[str] = None,
                         project_code: Optional[str] = None, designation: Optional[str] = None,
                         status: Optional[str] = None,
                         user: dict = Depends(require_permission("hr_gmc", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "Format must be xlsx or pdf")
    query = _member_query(policy_id, scope, project_code, designation, status, None)
    rows = await db.gmc_members.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    fname = f"group_medical_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.{fmt}"
    if fmt == "xlsx":
        data = to_excel("gmc_members", rows)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = to_pdf("gmc_members", rows)
        media = "application/pdf"
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
