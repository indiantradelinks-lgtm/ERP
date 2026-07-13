"""Billing defaults — single document in `settings` collection keyed by id='billing'.

Exposes:
  GET  /api/admin/billing-defaults
  PUT  /api/admin/billing-defaults

Consumed by the RA Bill form on the frontend. Falls back to hard-coded defaults
when the doc is absent.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso
from audit import audit

router = APIRouter(tags=["billing-defaults"])

DEFAULTS = {
    "id": "billing",
    "gst_pct": 18.0,
    "retention_pct": 0.0,
    "tds_pct": 0.0,
    "due_days": 30,
    "currency_code": "INR",
    "currency_symbol": "₹",
    "locale": "en-IN",
}


class BillingDefaults(BaseModel):
    gst_pct: Optional[float] = Field(default=None, ge=0, le=100)
    retention_pct: Optional[float] = Field(default=None, ge=0, le=100)
    tds_pct: Optional[float] = Field(default=None, ge=0, le=100)
    due_days: Optional[int] = Field(default=None, ge=0, le=365)
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    locale: Optional[str] = None


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/admin/billing-defaults")
async def get_billing_defaults(user: dict = Depends(require_permission("ra_bills", "read"))):
    row = await db.settings.find_one({"id": "billing"}, {"_id": 0})
    return {**DEFAULTS, **(row or {})}


@router.put("/admin/billing-defaults")
async def update_billing_defaults(payload: BillingDefaults, request: Request,
                                  user: dict = Depends(require_permission("ra_bills", "write"))):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        # Nothing to change → return current
        row = await db.settings.find_one({"id": "billing"}, {"_id": 0})
        return {**DEFAULTS, **(row or {})}
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.settings.update_one({"id": "billing"}, {"$set": patch, "$setOnInsert": {"id": "billing"}}, upsert=True)
    await audit(user=user, action="update", resource="settings", record_id="billing", after=patch, ip=_ip(request))
    row = await db.settings.find_one({"id": "billing"}, {"_id": 0})
    return {**DEFAULTS, **(row or {})}
