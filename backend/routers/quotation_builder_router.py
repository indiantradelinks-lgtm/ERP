"""AI Quotation Builder — rich quotation document with sections, items, conditions,
totals, PDF, AI extraction, approval, and client submission.

Extends the existing `db.quotations` schema with `sections`, `totals`, `conditions`,
`status` ∈ {draft, under_review, approved, submitted, revised, won, lost, cancelled}.

All routes are mounted under `/api`.
"""
from __future__ import annotations

import io
import os
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from quotation_calc import recalc_quotation, compute_tax_mode
from quotation_data import (
    SERVICES, SERVICE_BASES, BASIS_LABELS, BASIS_FIELDS, PRESET_ITEMS,
    DEFAULT_CONDITIONS, all_presets_payload,
)
from quotation_pdf import render_quotation_pdf
from notification_service import send_email, email_enabled, _shell

logger = logging.getLogger("erp.quotation_builder")
router = APIRouter(tags=["quotation-builder"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- Pydantic models ----------
class ItemIn(BaseModel):
    description: str
    specification: Optional[str] = None
    hsn_sac: Optional[str] = "9987"
    quantity: float = 0.0
    unit: str = "Nos"
    rate: float = 0.0
    discount_pct: float = 0.0
    gst_pct: float = 18.0
    remarks: Optional[str] = None


class SectionIn(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    service: str
    basis: str
    notes: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


class QuotationUpdate(BaseModel):
    client: Optional[str] = None
    client_id: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    client_state: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    project: Optional[str] = None
    scope_of_work: Optional[str] = None
    date: Optional[str] = None
    valid_until: Optional[str] = None
    service_categories: Optional[List[str]] = None
    rfq_type: Optional[List[str]] = None
    sections: Optional[List[Dict[str, Any]]] = None
    tax_mode: Optional[str] = None  # intra | inter
    tax_mode_locked: Optional[bool] = None
    technical_conditions: Optional[List[str]] = None
    commercial_conditions: Optional[List[str]] = None
    inclusions: Optional[List[str]] = None
    exclusions: Optional[List[str]] = None
    payment_terms: Optional[str] = None
    validity_days: Optional[int] = None
    advance_pct: Optional[float] = None
    retention_pct: Optional[float] = None
    tds_pct: Optional[float] = None
    warranty: Optional[str] = None
    delivery_timeline: Optional[str] = None
    submission_deadline: Optional[str] = None
    notes: Optional[str] = None


# ---------- Catalogues / presets ----------
@router.get("/quotation-builder/presets")
async def get_presets(user: dict = Depends(require_permission("quotations", "read"))):
    return all_presets_payload()


# ---------- Condition library ----------
class ConditionIn(BaseModel):
    category: str = Field(..., pattern=r"^(technical|commercial|inclusion|exclusion)$")
    service: str = "common"  # common | scaffolding | painting | rope_access | insulation | roof_sheeting
    text: str
    order: int = 99
    active: bool = True


@router.get("/quotation-builder/conditions")
async def list_conditions(
    category: Optional[str] = None,
    service: Optional[str] = None,
    user: dict = Depends(require_permission("condition_library", "read")),
):
    q: dict = {"active": True}
    if category:
        q["category"] = category
    if service:
        # include "common" + the service-specific ones
        q["service"] = {"$in": [service, "common"]}
    rows = await db.condition_library.find(q, {"_id": 0}).sort([("category", 1), ("service", 1), ("order", 1)]).to_list(2000)
    return rows


@router.post("/quotation-builder/conditions")
async def create_condition(payload: ConditionIn, request: Request,
                           user: dict = Depends(require_permission("quotations", "write"))):
    doc = {"id": new_id(), **payload.model_dump(), "created_at": now_iso(), "created_by": user["id"]}
    await db.condition_library.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="condition_library", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.put("/quotation-builder/conditions/{cid}")
async def update_condition(cid: str, payload: dict, request: Request,
                           user: dict = Depends(require_permission("condition_library", "write"))):
    for k in ("id", "created_at", "created_by"):
        payload.pop(k, None)
    payload["updated_at"] = now_iso()
    await db.condition_library.update_one({"id": cid}, {"$set": payload})
    row = await db.condition_library.find_one({"id": cid}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.delete("/quotation-builder/conditions/{cid}")
async def delete_condition(cid: str, request: Request,
                           user: dict = Depends(require_permission("condition_library", "delete"))):
    res = await db.condition_library.delete_one({"id": cid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ---------- Company Profile ----------
COMPANY_DEFAULTS = {
    "id": "company",
    "name": "INDIAN TRADE LINKS",
    "gstin": "",
    "pan": "",
    "state": "Gujarat",
    "state_code": "24",
    "address": "",
    "city": "",
    "pincode": "",
    "phone": "",
    "email": "",
    "website": "",
    "bank_name": "",
    "account_no": "",
    "ifsc": "",
    "authorized_signatory": "",
    "designation": "Authorised Signatory",
}


@router.get("/admin/company-profile")
async def get_company_profile(user: dict = Depends(require_permission("company_profile", "read"))):
    row = await db.settings.find_one({"id": "company"}, {"_id": 0})
    return {**COMPANY_DEFAULTS, **(row or {})}


@router.put("/admin/company-profile")
async def update_company_profile(payload: dict, request: Request,
                                 user: dict = Depends(require_permission("company_profile", "write"))):
    for k in ("_id", "id"):
        payload.pop(k, None)
    payload["updated_at"] = now_iso()
    payload["updated_by"] = user.get("name") or user.get("email")
    await db.settings.update_one(
        {"id": "company"},
        {"$set": payload, "$setOnInsert": {"id": "company"}},
        upsert=True,
    )
    await audit(user=user, action="update", resource="settings", record_id="company", after=payload, ip=_ip(request))
    row = await db.settings.find_one({"id": "company"}, {"_id": 0})
    return {**COMPANY_DEFAULTS, **(row or {})}


# ---------- Quotation CRUD (Builder) ----------
async def _get_company() -> Dict:
    row = await db.settings.find_one({"id": "company"}, {"_id": 0}) or {}
    return {**COMPANY_DEFAULTS, **row}


@router.post("/quotation-builder")
async def create_quotation_full(payload: dict, request: Request,
                                user: dict = Depends(require_permission("quotations", "write"))):
    """Create a new quotation directly in builder mode (without an enquiry).

    Typically called when the sales team starts a fresh quote. The enquiry-driven
    path continues to use `POST /api/enquiries` which auto-creates a draft.
    """
    quote_no = await next_sequence("QTN")
    doc = {
        "id": new_id(),
        "quote_number": quote_no,
        "revision_no": 0,
        "client": payload.get("client") or "—",
        "client_id": payload.get("client_id"),
        "site_id": payload.get("site_id"),
        "site_name": payload.get("site_name"),
        "client_state": payload.get("client_state"),
        "project": payload.get("project") or "",
        "service_categories": payload.get("service_categories") or [],
        "rfq_type": payload.get("rfq_type") or [],
        "sections": payload.get("sections") or [],
        "technical_conditions": payload.get("technical_conditions") or [],
        "commercial_conditions": payload.get("commercial_conditions") or [],
        "inclusions": payload.get("inclusions") or [],
        "exclusions": payload.get("exclusions") or [],
        "tax_mode": payload.get("tax_mode"),
        "tax_mode_locked": bool(payload.get("tax_mode_locked")),
        "date": payload.get("date") or now_iso()[:10],
        "valid_until": payload.get("valid_until"),
        "validity_days": payload.get("validity_days") or 30,
        "payment_terms": payload.get("payment_terms"),
        "advance_pct": payload.get("advance_pct") or 0,
        "retention_pct": payload.get("retention_pct") or 0,
        "tds_pct": payload.get("tds_pct") or 0,
        "delivery_timeline": payload.get("delivery_timeline"),
        "warranty": payload.get("warranty"),
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_via": "builder",
    }
    company = await _get_company()
    doc["company_state"] = company.get("state")
    recalc_quotation(doc)
    await db.quotations.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="quotations", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


@router.get("/quotation-builder/{q_id}")
async def get_full_quotation(q_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    row = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    # Ensure sections / totals are present even on legacy quotes
    row.setdefault("sections", [])
    row.setdefault("technical_conditions", [])
    row.setdefault("commercial_conditions", [])
    row.setdefault("inclusions", [])
    row.setdefault("exclusions", [])
    # Iter 66/67 — backfill site_name from enquiry/legacy fields so the Quotation
    # Builder's "Site / project name" field is populated for older auto-quotes
    # created before site_name was being saved.
    # Priority (Iter 67): the master Customer Site's name as snapshotted on the
    # enquiry → site_location → legacy `project` → enquiry.scope_of_work.
    if not row.get("site_name"):
        enq = None
        if row.get("enquiry_id"):
            enq = await db.enquiries.find_one(
                {"id": row["enquiry_id"]},
                {"_id": 0, "site_name": 1, "site_location": 1, "scope_of_work": 1, "project": 1},
            )
        fallback = (
            (enq or {}).get("site_name")
            or row.get("site_location")
            or (enq or {}).get("site_location")
            or row.get("project")
            or (enq or {}).get("scope_of_work")
            or ""
        )
        if fallback:
            row["site_name"] = fallback
    company = await _get_company()
    row.setdefault("company_state", company.get("state"))
    recalc_quotation(row)  # in-memory recompute so totals reflect latest
    return row


@router.put("/quotation-builder/{q_id}")
async def update_full_quotation(q_id: str, payload: QuotationUpdate, request: Request,
                                user: dict = Depends(require_permission("quotations", "write"))):
    existing = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    if existing.get("status") in ("won", "lost", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot edit quotation in {existing['status']} state")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    merged = {**existing, **patch}
    company = await _get_company()
    merged["company_state"] = company.get("state")
    recalc_quotation(merged)
    merged["updated_at"] = now_iso()
    merged["updated_by"] = user["id"]
    await db.quotations.update_one({"id": q_id}, {"$set": merged})
    await audit(user=user, action="update", resource="quotations", record_id=q_id, after=patch, ip=_ip(request))
    merged.pop("_id", None)
    return merged


@router.post("/quotation-builder/{q_id}/recalc")
async def recalc_only(q_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    row = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    company = await _get_company()
    row["company_state"] = company.get("state")
    recalc_quotation(row)
    await db.quotations.update_one({"id": q_id}, {"$set": {"sections": row["sections"], "totals": row["totals"], "total": row["total"], "tax_mode": row["tax_mode"]}})
    return {"totals": row["totals"], "tax_mode": row["tax_mode"]}


@router.get("/quotation-builder/{q_id}/preview")
async def preview_html(q_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    """Lightweight JSON preview — frontend renders the on-screen preview from this."""
    row = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    company = await _get_company()
    row.setdefault("company_state", company.get("state"))
    recalc_quotation(row)
    return {"quotation": row, "company": company}


@router.get("/quotation-builder/{q_id}/pdf")
async def quotation_pdf(q_id: str, user: dict = Depends(require_permission("quotations", "read"))):
    row = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    company = await _get_company()
    row["company_state"] = company.get("state")
    recalc_quotation(row)
    pdf = render_quotation_pdf(row, company)
    filename = f"{row.get('quote_number', 'Quotation')}.pdf".replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Approval ----------
@router.post("/quotation-builder/{q_id}/submit-for-approval")
async def submit_for_approval(q_id: str, request: Request, body: Optional[dict] = None,
                              user: dict = Depends(require_permission("quotations", "write"))):
    from approval_engine import insert_approval, copy_approval_doc_fields
    row = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row.get("status") not in ("draft", "revised"):
        raise HTTPException(status_code=400, detail=f"Cannot submit for approval from {row.get('status')}")
    company = await _get_company()
    row["company_state"] = company.get("state")
    recalc_quotation(row)
    # Reuse generic approvals
    approval = {
        "id": new_id(),
        "type": "quotation",
        "title": f"Quotation {row.get('quote_number')} — {row.get('client') or ''}",
        "reference": row.get("quote_number"),
        "amount": row.get("totals", {}).get("grand_total") or 0,
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user["id"],
        "status": "pending",
        "linked_resource": "quotations",
        "linked_id": q_id,
        "created_at": now_iso(),
        "history": [{"status": "pending", "by": user.get("name") or user.get("email"),
                     "role": user.get("role"), "at": now_iso(),
                     "comment": "Submitted for approval"}],
    }
    copy_approval_doc_fields(approval, body)
    await insert_approval(approval)
    await db.quotations.update_one(
        {"id": q_id},
        {"$set": {"status": "under_review", "approval_id": approval["id"],
                  "totals": row["totals"], "total": row["total"], "sections": row["sections"],
                  "updated_at": now_iso()}},
    )
    await audit(user=user, action="submit_for_approval", resource="quotations", record_id=q_id,
                after={"approval_id": approval["id"]}, ip=_ip(request))
    return {"approval_id": approval["id"], "status": "under_review"}


# ---------- Submit to client (email via Resend) ----------
class SubmitToClientIn(BaseModel):
    to_email: str
    cc_emails: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    body: Optional[str] = None
    attach_pdf: bool = True


@router.post("/quotation-builder/{q_id}/send-to-client")
async def send_to_client(q_id: str, payload: SubmitToClientIn, request: Request,
                         user: dict = Depends(require_permission("quotations", "write"))):
    row = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row.get("status") in ("won", "lost", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot send from {row['status']} state")
    company = await _get_company()
    row["company_state"] = company.get("state")
    recalc_quotation(row)

    subj = payload.subject or f"Quotation {row.get('quote_number')} from {company.get('name')}"
    body_html = payload.body or (
        f"Dear {row.get('contact_person') or 'Sir/Madam'},<br/><br/>"
        f"Please find attached our quotation <b>{row.get('quote_number')}</b> dated <b>{row.get('date')}</b> "
        f"for <b>{row.get('project') or 'the requested scope of work'}</b>. "
        f"The quoted grand total is <b>Rs. {row.get('totals', {}).get('grand_total', 0):,.2f}</b> "
        f"(inclusive of GST @ applicable rate)."
        f"<br/><br/>This quotation is valid until <b>{row.get('valid_until') or 'as per terms'}</b>. "
        f"Should you require any clarification, please get in touch.<br/><br/>"
        f"Best regards,<br/><b>{user.get('name')}</b><br/>{company.get('name')}"
    )
    html = _shell("Quotation Submission", subj, body_html, "View Quotation", os.environ.get("FRONTEND_URL", ""))

    # Build attachments (PDF inline)
    attachments = []
    if payload.attach_pdf:
        pdf = render_quotation_pdf(row, company)
        # Resend supports content base64
        import base64
        attachments.append({
            "filename": f"{(row.get('quote_number') or 'Quotation').replace(' ', '_')}.pdf",
            "content": base64.b64encode(pdf).decode("ascii"),
        })

    sent_ok = False
    if email_enabled():
        try:
            import resend
            import asyncio
            params = {
                "from": f"{company.get('name') or 'WorkSite Command'} <{os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')}>",
                "to": [payload.to_email],
                "cc": payload.cc_emails or [],
                "subject": subj,
                "html": html,
                "attachments": attachments,
            }
            result = await asyncio.to_thread(resend.Emails.send, params)
            sent_ok = bool(result and result.get("id"))
        except Exception as e:
            logger.error(f"Send-to-client failed: {e}")
            raise HTTPException(status_code=502, detail=f"Email send failed: {e}")
    else:
        # Without email configured, still mark as submitted but flag it
        logger.warning("Email not configured — submission recorded but not actually delivered.")

    submission = {
        "to": payload.to_email, "cc": payload.cc_emails or [],
        "subject": subj, "at": now_iso(),
        "by": user.get("name") or user.get("email"),
        "delivered": sent_ok,
    }
    submissions = list(row.get("submissions") or []) + [submission]
    await db.quotations.update_one(
        {"id": q_id},
        {"$set": {
            "status": "submitted",
            "submitted_to_client_at": now_iso(),
            "submitted_via": "email",
            "submissions": submissions,
            "totals": row["totals"], "total": row["total"], "sections": row["sections"],
            "updated_at": now_iso(),
        }},
    )
    await audit(user=user, action="send_to_client", resource="quotations", record_id=q_id, after=submission, ip=_ip(request))
    return {"delivered": sent_ok, "submission": submission, "status": "submitted"}


# ---------- Status change ----------
class StatusChangeIn(BaseModel):
    status: str  # won | lost | cancelled
    note: Optional[str] = None


@router.post("/quotation-builder/{q_id}/status")
async def change_status(q_id: str, payload: StatusChangeIn, request: Request,
                        user: dict = Depends(require_permission("quotations", "write"))):
    allowed = {"won", "lost", "cancelled", "submitted", "under_review", "draft"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    row = await db.quotations.find_one({"id": q_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    await db.quotations.update_one(
        {"id": q_id},
        {"$set": {"status": payload.status, "status_note": payload.note,
                  "status_changed_at": now_iso(),
                  "status_changed_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="status_change", resource="quotations", record_id=q_id,
                after={"status": payload.status}, ip=_ip(request))
    return {"ok": True, "status": payload.status}


# ---------- Seed conditions on first startup ----------
async def seed_conditions_if_empty() -> int:
    """Returns number of conditions inserted. Idempotent (skip if any rows exist)."""
    n = await db.condition_library.count_documents({})
    if n > 0:
        return 0
    docs = []
    for c in DEFAULT_CONDITIONS:
        docs.append({"id": new_id(), **c, "active": True, "created_at": now_iso(), "created_via": "seed"})
    if docs:
        await db.condition_library.insert_many(docs)
    return len(docs)
