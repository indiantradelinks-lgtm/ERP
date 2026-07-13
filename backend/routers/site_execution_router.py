"""Site Execution module — Daily Site Report (DPR) + Measurement / Work Certification.

DPR captures end-of-day site state: manpower present, work completed, material
used/received/returned, safety observations, photos, client instructions, delay
reasons, extra work, supervisor remarks → digitally approved by the Project
Coordinator (project_manager / dept_head / GM / super_admin).

Measurement captures service-wise executed and client-certified quantities that
feed into Running (RA) Bills downstream. Status workflow:
  draft → submitted → client_certified → approved_for_billing → billed

Both modules write to `audit_logs` on every state change.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id, logger
from audit import audit
from sequences import next_sequence, stamp_dept_doc

router = APIRouter(tags=["site-execution"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


PC_ROLES = {"super_admin", "director", "general_manager", "dept_head", "project_manager"}


# ──────────────────────────────────────────────────────────────────────────────
# Daily Site Report (DPR)
# ──────────────────────────────────────────────────────────────────────────────
class DPRManpower(BaseModel):
    role: str                            # site_engineer | supervisor | scaffolder | painter | …
    count: int


class DPRMaterialLine(BaseModel):
    item_id: Optional[str] = None
    item_name: str
    quantity: float
    unit: str = "Nos"


class DPRIn(BaseModel):
    date: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    service_type: Optional[str] = None   # scaffolding | painting | rope_access | insulation | roof_sheeting | combined
    manpower: List[DPRManpower] = Field(default_factory=list)
    work_completed: Optional[str] = None
    material_used: List[DPRMaterialLine] = Field(default_factory=list)
    material_received: List[DPRMaterialLine] = Field(default_factory=list)
    material_returned: List[DPRMaterialLine] = Field(default_factory=list)
    safety_observations: Optional[str] = None
    site_photos: List[str] = Field(default_factory=list)   # file ids
    client_instructions: Optional[str] = None
    delay_reasons: Optional[str] = None
    delay_hours: Optional[float] = None
    extra_work: Optional[str] = None
    supervisor_remarks: Optional[str] = None
    submit: bool = False                  # if true, status → submitted


@router.get("/dprs")
async def list_dprs(project_code: Optional[str] = None,
                    site_id: Optional[str] = None,
                    status: Optional[str] = None,
                    service_type: Optional[str] = None,
                    date: Optional[str] = None,
                    user: dict = Depends(require_permission("dprs", "read"))):
    q: dict = {}
    if project_code:
        q["project_code"] = project_code
    if site_id:
        q["site_id"] = site_id
    if status:
        q["status"] = status
    if service_type:
        q["service_type"] = service_type
    if date:
        q["date"] = date
    rows = await db.dprs.find(q, {"_id": 0}).sort("date", -1).to_list(1000)
    return rows


@router.get("/dprs/dashboard")
async def dpr_dashboard(user: dict = Depends(require_permission("dprs", "read"))):
    today = datetime.now(timezone.utc).date().isoformat()
    week_start = (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()
    total = await db.dprs.count_documents({})
    submitted_today = await db.dprs.count_documents({"date": today, "status": {"$in": ["submitted", "approved"]}})
    approved_week = await db.dprs.count_documents({"date": {"$gte": week_start}, "status": "approved"})
    pending = await db.dprs.count_documents({"status": "submitted"})
    rejected = await db.dprs.count_documents({"status": "rejected"})
    # Last-7-day series for chart
    series_rows = await db.dprs.aggregate([
        {"$match": {"date": {"$gte": week_start}}},
        {"$group": {"_id": {"date": "$date", "status": "$status"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.date": 1}},
    ]).to_list(500)
    return {
        "kpis": {"total": total, "submitted_today": submitted_today,
                 "pending_approval": pending, "approved_last_7d": approved_week, "rejected": rejected},
        "series": series_rows,
    }


@router.get("/dprs/{dpr_id}")
async def get_dpr(dpr_id: str, user: dict = Depends(require_permission("dprs", "read"))):
    row = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="DPR not found")
    return row


@router.post("/dprs")
async def create_dpr(payload: DPRIn, request: Request,
                     user: dict = Depends(require_permission("dprs", "write"))):
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["dpr_number"] = await next_sequence("DPR")
    await stamp_dept_doc(doc, "dpr")
    doc["date"] = doc.get("date") or now_iso()[:10]
    doc["supervisor_id"] = user["id"]
    doc["supervisor_name"] = user.get("name") or user.get("email")
    doc["status"] = "submitted" if payload.submit else "draft"
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    doc.pop("submit", None)
    await db.dprs.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="dprs", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/dprs/{dpr_id}")
async def update_dpr(dpr_id: str, payload: dict, request: Request,
                     user: dict = Depends(require_permission("dprs", "write"))):
    dpr = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not dpr:
        raise HTTPException(status_code=404, detail="DPR not found")
    if dpr.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail=f"DPR in '{dpr.get('status')}' cannot be edited")
    for k in ("id", "dpr_number", "status", "supervisor_id", "created_at", "created_by"):
        payload.pop(k, None)
    payload["updated_at"] = now_iso()
    await db.dprs.update_one({"id": dpr_id}, {"$set": payload})
    row = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    await audit(user=user, action="update", resource="dprs", record_id=dpr_id, after=row, ip=_ip(request))
    return row


@router.post("/dprs/{dpr_id}/submit")
async def submit_dpr(dpr_id: str, request: Request,
                     user: dict = Depends(require_permission("dprs", "write"))):
    dpr = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not dpr:
        raise HTTPException(status_code=404, detail="DPR not found")
    if dpr.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Only draft / rejected DPRs can be submitted")
    await db.dprs.update_one({"id": dpr_id}, {"$set": {"status": "submitted", "submitted_at": now_iso(), "reject_reason": None, "updated_at": now_iso()}})
    return await db.dprs.find_one({"id": dpr_id}, {"_id": 0})


@router.post("/dprs/{dpr_id}/approve")
async def approve_dpr(dpr_id: str, payload: dict | None = None, request: Request = None,
                      user: dict = Depends(require_permission("dprs", "write"))):
    if user.get("role") not in PC_ROLES:
        raise HTTPException(status_code=403, detail="Only Project Coordinator+ can approve DPRs")
    dpr = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not dpr:
        raise HTTPException(status_code=404, detail="DPR not found")
    if dpr.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"DPR in '{dpr.get('status')}' cannot be approved")
    comment = (payload or {}).get("comment")
    await db.dprs.update_one({"id": dpr_id}, {"$set": {
        "status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_by_id": user["id"],
        "approved_at": now_iso(),
        "approval_comment": comment,
        "updated_at": now_iso(),
    }})
    if request is not None:
        await audit(user=user, action="approve", resource="dprs", record_id=dpr_id, after={"status": "approved"}, ip=_ip(request))
    return await db.dprs.find_one({"id": dpr_id}, {"_id": 0})


@router.post("/dprs/{dpr_id}/reject")
async def reject_dpr(dpr_id: str, payload: dict, request: Request,
                     user: dict = Depends(require_permission("dprs", "write"))):
    if user.get("role") not in PC_ROLES:
        raise HTTPException(status_code=403, detail="Only Project Coordinator+ can reject DPRs")
    reason = (payload or {}).get("reason") or "No reason given"
    dpr = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not dpr:
        raise HTTPException(status_code=404, detail="DPR not found")
    if dpr.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"DPR in '{dpr.get('status')}' cannot be rejected")
    await db.dprs.update_one({"id": dpr_id}, {"$set": {
        "status": "rejected", "reject_reason": reason,
        "rejected_by": user.get("name") or user.get("email"),
        "rejected_at": now_iso(), "updated_at": now_iso(),
    }})
    await audit(user=user, action="reject", resource="dprs", record_id=dpr_id, after={"status": "rejected", "reject_reason": reason}, ip=_ip(request))
    return await db.dprs.find_one({"id": dpr_id}, {"_id": 0})


@router.delete("/dprs/{dpr_id}")
async def delete_dpr(dpr_id: str, request: Request,
                     user: dict = Depends(require_permission("dprs", "delete"))):
    dpr = await db.dprs.find_one({"id": dpr_id}, {"_id": 0})
    if not dpr:
        raise HTTPException(status_code=404, detail="DPR not found")
    if dpr.get("status") == "approved":
        raise HTTPException(status_code=400, detail="Cannot delete an approved DPR")
    await db.dprs.delete_one({"id": dpr_id})
    await audit(user=user, action="delete", resource="dprs", record_id=dpr_id, before=dpr, ip=_ip(request))
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Measurement / Work Certification
# ──────────────────────────────────────────────────────────────────────────────
MEAS_STATUSES = ("draft", "submitted", "client_certified", "approved_for_billing", "rejected", "billed")


class MeasurementItem(BaseModel):
    service: str                          # scaffolding | painting | rope_access | insulation | roof_sheeting | other
    activity: str                         # erected | dismantled | painted | insulated | sheeted | …
    description: Optional[str] = None
    executed_qty: float
    certified_qty: float                  # client-certified, ≤ executed_qty typically
    unit: str = "m²"                      # m² | m³ | m | Nos | kg
    rate: Optional[float] = None
    remark: Optional[str] = None


class MeasurementIn(BaseModel):
    date: Optional[str] = None
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    service_type: Optional[str] = None
    po_id: Optional[str] = None
    po_number: Optional[str] = None
    items: List[MeasurementItem]
    joint_measured_with: Optional[str] = None     # client contact name
    client_designation: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)   # file ids
    linked_dpr_ids: List[str] = Field(default_factory=list)
    remarks: Optional[str] = None
    submit: bool = False


def _meas_totals(items: List[Dict[str, Any]]) -> Dict[str, float]:
    executed = sum(float(i.get("executed_qty") or 0) for i in items)
    certified = sum(float(i.get("certified_qty") or 0) for i in items)
    billable_value = sum((float(i.get("rate") or 0) * float(i.get("certified_qty") or 0)) for i in items)
    return {"total_executed": executed, "total_certified": certified, "billable_value": billable_value}


@router.get("/measurements")
async def list_measurements(project_code: Optional[str] = None,
                            status: Optional[str] = None,
                            service: Optional[str] = None,
                            po_id: Optional[str] = None,
                            user: dict = Depends(require_permission("measurements", "read"))):
    q: dict = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    if service:
        q["items.service"] = service
    if po_id:
        q["po_id"] = po_id
    rows = await db.measurements.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.get("/measurements/pending-certification")
async def pending_certification(user: dict = Depends(require_permission("measurements", "read"))):
    """Submitted but not yet client-certified."""
    rows = await db.measurements.find({"status": "submitted"}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"count": len(rows), "rows": rows}


@router.get("/measurements/summary")
async def measurement_summary(project_code: Optional[str] = None,
                              user: dict = Depends(require_permission("measurements", "read"))):
    """Approved-for-billing certified quantities aggregated by (project, service, activity)."""
    match: dict = {"status": {"$in": ["approved_for_billing", "billed"]}}
    if project_code:
        match["project_code"] = project_code
    pipeline = [
        {"$match": match},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"project": "$project_code", "service": "$items.service", "activity": "$items.activity", "unit": "$items.unit"},
            "certified_qty": {"$sum": "$items.certified_qty"},
            "executed_qty": {"$sum": "$items.executed_qty"},
            "billable_value": {"$sum": {"$multiply": [{"$ifNull": ["$items.rate", 0]}, "$items.certified_qty"]}},
            "count": {"$sum": 1},
        }},
        {"$project": {
            "_id": 0,
            "project": "$_id.project", "service": "$_id.service", "activity": "$_id.activity", "unit": "$_id.unit",
            "certified_qty": 1, "executed_qty": 1, "billable_value": 1, "count": 1,
        }},
        {"$sort": {"project": 1, "service": 1, "activity": 1}},
    ]
    rows = await db.measurements.aggregate(pipeline).to_list(500)
    return {"rows": rows}


@router.get("/measurements/{meas_id}")
async def get_measurement(meas_id: str, user: dict = Depends(require_permission("measurements", "read"))):
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return row


def _validate_items(items: List[MeasurementItem]) -> None:
    if not items:
        raise HTTPException(status_code=400, detail="At least one measurement line is required")
    for idx, it in enumerate(items):
        if float(it.certified_qty) < 0 or float(it.executed_qty) < 0:
            raise HTTPException(status_code=400, detail=f"Line {idx + 1}: quantities must be ≥ 0")
        if float(it.certified_qty) > float(it.executed_qty) + 1e-6:
            raise HTTPException(status_code=400, detail=f"Line {idx + 1}: certified_qty cannot exceed executed_qty")


@router.post("/measurements")
async def create_measurement(payload: MeasurementIn, request: Request,
                             user: dict = Depends(require_permission("measurements", "write"))):
    _validate_items(payload.items)
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["measurement_no"] = await next_sequence("MEAS")
    await stamp_dept_doc(doc, "measurement")
    doc["date"] = doc.get("date") or now_iso()[:10]
    doc["status"] = "submitted" if payload.submit else "draft"
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    doc["created_by_name"] = user.get("name") or user.get("email")
    doc.update(_meas_totals(doc["items"]))
    doc.pop("submit", None)
    await db.measurements.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="measurements", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/measurements/{meas_id}")
async def update_measurement(meas_id: str, payload: dict, request: Request,
                             user: dict = Depends(require_permission("measurements", "write"))):
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if row.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail=f"Measurement in '{row.get('status')}' cannot be edited")
    for k in ("id", "measurement_no", "status", "created_at", "created_by"):
        payload.pop(k, None)
    if "items" in payload:
        _validate_items([MeasurementItem(**i) for i in payload["items"]])
        payload.update(_meas_totals(payload["items"]))
    payload["updated_at"] = now_iso()
    await db.measurements.update_one({"id": meas_id}, {"$set": payload})
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    await audit(user=user, action="update", resource="measurements", record_id=meas_id, after=row, ip=_ip(request))
    return row


@router.post("/measurements/{meas_id}/submit")
async def submit_measurement(meas_id: str, request: Request,
                             user: dict = Depends(require_permission("measurements", "write"))):
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if row.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Only draft / rejected measurements can be submitted")
    await db.measurements.update_one({"id": meas_id}, {"$set": {"status": "submitted", "submitted_at": now_iso(), "reject_reason": None, "updated_at": now_iso()}})
    return await db.measurements.find_one({"id": meas_id}, {"_id": 0})


@router.post("/measurements/{meas_id}/certify")
async def certify_measurement(meas_id: str, payload: dict, request: Request,
                              user: dict = Depends(require_permission("measurements", "write"))):
    """Record client certification — client signs off on measured qty."""
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if row.get("status") != "submitted":
        raise HTTPException(status_code=400, detail=f"Measurement in '{row.get('status')}' cannot be certified")
    name = (payload or {}).get("signatory_name") or ""
    if len(name.strip()) < 2:
        raise HTTPException(status_code=400, detail="signatory_name (client representative) is required")
    designation = (payload or {}).get("signatory_designation") or row.get("client_designation")
    await db.measurements.update_one({"id": meas_id}, {"$set": {
        "status": "client_certified",
        "client_signature": {
            "name": name.strip(), "designation": designation,
            "signed_at": now_iso(), "recorded_by": user.get("name") or user.get("email"),
            "ip": _ip(request),
        },
        "certified_at": now_iso(), "updated_at": now_iso(),
    }})
    await audit(user=user, action="certify", resource="measurements", record_id=meas_id, after={"status": "client_certified"}, ip=_ip(request))
    return await db.measurements.find_one({"id": meas_id}, {"_id": 0})


@router.post("/measurements/{meas_id}/approve-for-billing")
async def approve_for_billing(meas_id: str, request: Request,
                              user: dict = Depends(require_permission("measurements", "write"))):
    if user.get("role") not in (PC_ROLES | {"accounts_executive"}):
        raise HTTPException(status_code=403, detail="Only PC or Accounts can release measurement for billing")
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if row.get("status") != "client_certified":
        raise HTTPException(status_code=400, detail=f"Measurement must be client_certified first (was '{row.get('status')}')")
    await db.measurements.update_one({"id": meas_id}, {"$set": {
        "status": "approved_for_billing",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(), "updated_at": now_iso(),
    }})
    await audit(user=user, action="approve_for_billing", resource="measurements", record_id=meas_id, after={"status": "approved_for_billing"}, ip=_ip(request))
    return await db.measurements.find_one({"id": meas_id}, {"_id": 0})


@router.post("/measurements/{meas_id}/reject")
async def reject_measurement(meas_id: str, payload: dict, request: Request,
                             user: dict = Depends(require_permission("measurements", "write"))):
    if user.get("role") not in (PC_ROLES | {"accounts_executive"}):
        raise HTTPException(status_code=403, detail="Only PC or Accounts can reject a measurement")
    reason = (payload or {}).get("reason") or "No reason given"
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if row.get("status") not in ("submitted", "client_certified"):
        raise HTTPException(status_code=400, detail=f"Measurement in '{row.get('status')}' cannot be rejected")
    await db.measurements.update_one({"id": meas_id}, {"$set": {
        "status": "rejected", "reject_reason": reason,
        "rejected_by": user.get("name") or user.get("email"),
        "rejected_at": now_iso(), "updated_at": now_iso(),
    }})
    await audit(user=user, action="reject", resource="measurements", record_id=meas_id, after={"status": "rejected", "reject_reason": reason}, ip=_ip(request))
    return await db.measurements.find_one({"id": meas_id}, {"_id": 0})


@router.delete("/measurements/{meas_id}")
async def delete_measurement(meas_id: str, request: Request,
                             user: dict = Depends(require_permission("measurements", "delete"))):
    row = await db.measurements.find_one({"id": meas_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if row.get("status") in ("approved_for_billing", "billed"):
        raise HTTPException(status_code=400, detail="Cannot delete a measurement past approval")
    await db.measurements.delete_one({"id": meas_id})
    await audit(user=user, action="delete", resource="measurements", record_id=meas_id, before=row, ip=_ip(request))
    return {"ok": True}
