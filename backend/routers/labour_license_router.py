"""Labour License Compliance & Expiry Tracking (HR module).

Flow: HR creates license (project/site, form type, validity) → documents via /api/uploads
(parent_type 'labour_license', sub-doc kinds) → daily job recomputes status + 7-day HR alerts
→ renewal keeps history → project-wise visibility via PM scope.
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id
from audit import audit
from scope import project_filter

router = APIRouter(prefix="/labour-licenses", tags=["labour-licenses"])

HR_WRITE_ROLES = {"super_admin", "hr_executive", "hr_manager", "general_manager", "director"}
FORM_TYPES = {"Form V", "Form VI", "Form XVII"}
ALERT_DAYS = 7


def _ip(request: Request | None) -> str:
    try:
        return request.client.host if request and request.client else ""
    except Exception:
        return ""


def compute_status(expiry_date: str | None) -> tuple[str, int | None]:
    """Returns (status, days_remaining)."""
    if not expiry_date:
        return "active", None
    try:
        exp = datetime.fromisoformat(str(expiry_date)[:10]).date()
    except ValueError:
        return "active", None
    days = (exp - datetime.now(timezone.utc).date()).days
    if days < 0:
        return "expired", days
    if days <= ALERT_DAYS:
        return "expiring_soon", days
    return "active", days


def _decorate(r: dict) -> dict:
    status, days = compute_status(r.get("expiry_date"))
    r["status"] = status
    r["days_remaining"] = days
    r["renewal_count"] = len(r.get("renewal_history") or [])
    if status == "active" and r["renewal_count"] > 0:
        r["status"] = "renewed"
    return r


class LicenseIn(BaseModel):
    project_code: str
    project_name: Optional[str] = ""
    site_location: Optional[str] = ""
    license_number: str
    license_type: Optional[str] = "Labour License"
    form_type: str
    issue_date: Optional[str] = ""
    valid_from: Optional[str] = ""
    expiry_date: str
    remarks: Optional[str] = ""


class RenewIn(BaseModel):
    valid_from: str
    expiry_date: str
    license_number: Optional[str] = None
    remarks: Optional[str] = ""


async def _scope_filter(user: dict) -> dict:
    f = await project_filter(user, project_field="project_code")
    return f or {}


def _require_hr(user: dict):
    if user.get("role") not in HR_WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Only HR/Admin can manage labour licenses")


@router.get("")
async def list_licenses(status: str = "", project_code: str = "", form_type: str = "",
                        user: dict = Depends(get_current_user)):
    q = await _scope_filter(user)
    if project_code:
        q["project_code"] = project_code
    if form_type:
        q["form_type"] = form_type
    rows = [_decorate(r) for r in await db.labour_licenses.find(q, {"_id": 0}).sort("expiry_date", 1).to_list(2000)]
    if status:
        rows = [r for r in rows if r["status"] == status]
    return rows


@router.get("/dashboard")
async def license_dashboard(user: dict = Depends(get_current_user)):
    q = await _scope_filter(user)
    rows = [_decorate(r) for r in await db.labour_licenses.find(q, {"_id": 0}).to_list(2000)]
    by_project: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        p = by_project.setdefault(r.get("project_code") or "—", {
            "project_code": r.get("project_code"), "project_name": r.get("project_name"),
            "total": 0, "active": 0, "expiring_soon": 0, "expired": 0, "renewed": 0})
        p["total"] += 1
        p[r["status"]] = p.get(r["status"], 0) + 1
    return {
        "cards": {
            "total": len(rows),
            "active": sum(1 for r in rows if r["status"] in ("active", "renewed")),
            "expiring_soon": sum(1 for r in rows if r["status"] == "expiring_soon"),
            "expired": sum(1 for r in rows if r["status"] == "expired"),
            "renewed": sum(1 for r in rows if r["renewal_count"] > 0),
        },
        "by_project": sorted(by_project.values(), key=lambda x: x.get("project_code") or ""),
    }


@router.get("/{lid}")
async def get_license(lid: str, user: dict = Depends(get_current_user)):
    q = await _scope_filter(user)
    q["id"] = lid
    row = await db.labour_licenses.find_one(q, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="License not found")
    return _decorate(row)


@router.post("")
async def create_license(p: LicenseIn, request: Request, user: dict = Depends(get_current_user)):
    _require_hr(user)
    if p.form_type not in FORM_TYPES and p.form_type != "Labour License":
        raise HTTPException(status_code=400, detail=f"form_type must be one of {sorted(FORM_TYPES)} or 'Labour License'")
    proj = await db.projects.find_one({"code": p.project_code}, {"_id": 0, "name": 1})
    doc = {
        "id": new_id(),
        **p.model_dump(),
        "project_name": p.project_name or (proj or {}).get("name") or "",
        "alert_sent_for": None,
        "renewal_history": [],
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
        "updated_at": now_iso(), "updated_by": user.get("name") or user.get("email"),
    }
    await db.labour_licenses.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="labour_licenses", record_id=doc["id"], after=doc, ip=_ip(request))
    return _decorate(doc)


@router.put("/{lid}")
async def update_license(lid: str, p: LicenseIn, request: Request, user: dict = Depends(get_current_user)):
    _require_hr(user)
    existing = await db.labour_licenses.find_one({"id": lid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="License not found")
    patch = p.model_dump()
    changes = {k: {"from": existing.get(k), "to": v} for k, v in patch.items() if existing.get(k) != v}
    if patch.get("expiry_date") != existing.get("expiry_date"):
        patch["alert_sent_for"] = None  # reset alert tracking for the new expiry
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.labour_licenses.update_one({"id": lid}, {"$set": patch})
    await audit(user=user, action="update", resource="labour_licenses", record_id=lid,
                before={k: existing.get(k) for k in changes}, after=patch, ip=_ip(request))
    return _decorate({**existing, **patch})


@router.post("/{lid}/renew")
async def renew_license(lid: str, p: RenewIn, request: Request, user: dict = Depends(get_current_user)):
    _require_hr(user)
    existing = await db.labour_licenses.find_one({"id": lid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="License not found")
    hist_entry = {
        "license_number": existing.get("license_number"),
        "valid_from": existing.get("valid_from"),
        "expiry_date": existing.get("expiry_date"),
        "remarks": existing.get("remarks"),
        "renewed_at": now_iso(),
        "renewed_by": user.get("name") or user.get("email"),
        "renewal_remarks": p.remarks or "",
    }
    patch = {
        "valid_from": p.valid_from,
        "expiry_date": p.expiry_date,
        "license_number": p.license_number or existing.get("license_number"),
        "alert_sent_for": None,
        "updated_at": now_iso(),
        "updated_by": user.get("name") or user.get("email"),
        "last_renewed_at": now_iso(),
    }
    await db.labour_licenses.update_one(
        {"id": lid}, {"$set": patch, "$push": {"renewal_history": hist_entry}})
    await audit(user=user, action="renew", resource="labour_licenses", record_id=lid,
                before=hist_entry, after=patch, ip=_ip(request))
    row = await db.labour_licenses.find_one({"id": lid}, {"_id": 0})
    return _decorate(row)


async def run_labour_license_daily_check() -> dict:
    """Daily job: recompute statuses, send 7-day HR alerts (idempotent per expiry date)."""
    from scheduler import _push_inapp_for_role
    rows = await db.labour_licenses.find({}, {"_id": 0}).to_list(5000)
    alerted = expired = 0
    for r in rows:
        status, days = compute_status(r.get("expiry_date"))
        await db.labour_licenses.update_one({"id": r["id"]}, {"$set": {"computed_status": status}})
        if status == "expiring_soon" and r.get("alert_sent_for") != r.get("expiry_date"):
            try:
                exp_disp = datetime.fromisoformat(str(r["expiry_date"])[:10]).strftime("%d-%b-%Y")
            except ValueError:
                exp_disp = r.get("expiry_date")
            msg = (f"Labour License {r.get('license_number')} ({r.get('form_type')}) for "
                   f"{r.get('project_name') or r.get('project_code')} will expire in {days} day(s) "
                   f"on {exp_disp}. Please initiate renewal to avoid compliance lapse.")
            payload = {"type": "labour_license_expiry", "title": "Labour License expiring soon",
                       "message": msg, "link": "/app/hr/labour-licenses",
                       "meta": {"license_id": r["id"], "project_code": r.get("project_code"),
                                "license_number": r.get("license_number"), "form_type": r.get("form_type"),
                                "expiry_date": r.get("expiry_date"), "days_remaining": days,
                                "action": "Renewal action required"}}
            for role in ("hr_executive", "hr_manager", "super_admin"):
                await _push_inapp_for_role(role, payload)
            await db.labour_licenses.update_one(
                {"id": r["id"]}, {"$set": {"alert_sent_for": r.get("expiry_date"), "last_alert_at": now_iso()}})
            alerted += 1
        if status == "expired":
            expired += 1
    return {"checked": len(rows), "alerted": alerted, "expired": expired}


@router.post("/admin/run-daily-check")
async def trigger_daily_check(user: dict = Depends(get_current_user)):
    _require_hr(user)
    return await run_labour_license_daily_check()
