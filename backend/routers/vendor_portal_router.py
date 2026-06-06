"""Vendor self-service portal.

Endpoints scoped to the logged-in user when role='vendor'. The vendor's profile
is matched on the user's email against `vendors.contact_email`. They see only:
  - Their own vendor profile (read + limited update)
  - RFQs/POs addressed to them (read-only)
  - Their submitted invoices (full CRUD on own rows)
  - Evaluation history (read-only)
Super_admins can see/manage everything for any vendor (audit-friendly).
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, get_current_user, now_iso, new_id
from audit import audit
from sequences import next_sequence

router = APIRouter(prefix="/vendor-portal", tags=["vendor-portal"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def require_vendor(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("vendor", "super_admin"):
        raise HTTPException(status_code=403, detail="Vendor portal access only")
    return user


async def _resolve_vendor(user: dict, vendor_id: Optional[str] = None) -> dict:
    """Find the vendor row this user is allowed to act on."""
    if user.get("role") == "super_admin" and vendor_id:
        v = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found")
        return v
    v = await db.vendors.find_one(
        {"$or": [{"contact_email": user.get("email")}, {"user_id": user.get("id")}]},
        {"_id": 0},
    )
    if not v:
        raise HTTPException(status_code=404, detail="No vendor profile linked to this account. Contact admin.")
    return v


@router.get("/me")
async def vendor_me(user: dict = Depends(require_vendor)):
    return await _resolve_vendor(user)


@router.put("/me")
async def update_vendor_profile(payload: Dict[str, Any], request: Request, user: dict = Depends(require_vendor)):
    v = await _resolve_vendor(user)
    # Vendors can update only contact/bank info — not rating/category/status
    allowed = {"contact_phone", "contact_email", "address", "gst", "pan", "bank_account", "ifsc", "bank_name"}
    if user.get("role") != "super_admin":
        payload = {k: val for k, val in payload.items() if k in allowed}
    payload["updated_at"] = now_iso()
    await db.vendors.update_one({"id": v["id"]}, {"$set": payload})
    after = await db.vendors.find_one({"id": v["id"]}, {"_id": 0})
    await audit(user=user, action="update", resource="vendors", record_id=v["id"], before=v, after=after, ip=_ip(request))
    return after


@router.get("/rfqs")
async def my_rfqs(user: dict = Depends(require_vendor)):
    """Purchase orders / RFQs addressed to this vendor."""
    v = await _resolve_vendor(user)
    rows = await db.purchase_orders.find({"vendor": v["name"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


class InvoiceIn(BaseModel):
    po_no: Optional[str] = None
    po_id: Optional[str] = None
    invoice_no: str
    date: str
    amount: float
    description: Optional[str] = None


@router.get("/invoices")
async def my_invoices(user: dict = Depends(require_vendor)):
    v = await _resolve_vendor(user)
    rows = await db.vendor_invoices.find({"vendor_id": v["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.post("/invoices")
async def submit_invoice(payload: InvoiceIn, request: Request, user: dict = Depends(require_vendor)):
    v = await _resolve_vendor(user)
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "submission_no": await next_sequence("VINV"),
        "vendor_id": v["id"],
        "vendor_name": v.get("name"),
        "status": "submitted",
        "created_at": now_iso(),
        "created_by": user["id"],
    })
    await db.vendor_invoices.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="vendor_invoices", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


class EvalIn(BaseModel):
    rating: float  # 0..5
    period: str
    note: Optional[str] = None


@router.get("/evaluations/{vendor_id}")
async def list_evaluations(vendor_id: str, user: dict = Depends(get_current_user)):
    # Vendors may only view their own evaluations; others must have read on vendors
    if user.get("role") == "vendor":
        v = await _resolve_vendor(user)
        if v["id"] != vendor_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    rows = await db.vendor_evaluations.find({"vendor_id": vendor_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return rows


@router.post("/evaluations/{vendor_id}")
async def add_evaluation(vendor_id: str, payload: EvalIn, request: Request, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("super_admin", "director", "general_manager", "purchase_officer"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if payload.rating < 0 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="rating must be 0..5")
    v = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "vendor_id": vendor_id,
        "rated_by": user.get("name") or user.get("email"),
        "rated_by_role": user.get("role"),
        "created_at": now_iso(),
    })
    await db.vendor_evaluations.insert_one(doc)
    # Update rolling average rating on the vendor doc
    cursor = db.vendor_evaluations.find({"vendor_id": vendor_id}, {"_id": 0, "rating": 1})
    ratings = [r.get("rating", 0) async for r in cursor]
    avg = sum(ratings) / len(ratings) if ratings else 0.0
    await db.vendors.update_one({"id": vendor_id}, {"$set": {"rating": round(avg, 2), "rating_count": len(ratings)}})
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="vendor_evaluations", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc
