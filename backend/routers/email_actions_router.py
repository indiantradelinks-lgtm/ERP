"""Entity-aware email actions: prefill, AI cover-note draft, and send.

This sits on top of the generic /api/email/* router and adds module-aware
behaviour:

  - Resolves the recipient (client/vendor/employee) from the record.
  - Resolves the sender (shared mailbox vs. user's own M365 mailbox)
    according to SENDER_POLICY below.
  - Auto-attaches a PDF generated on-the-fly for the record.
      * quotation   → existing /api/quotation-builder/{id}/pdf (re-rendered)
      * purchase_order, rfq, ra_bill → document_pdf.* (reportlab)
      * hr_letter   → docx bytes already stored in db.hr_letters[id].binary
  - Optional AI draft via Claude Sonnet 4.5 (Universal LLM Key).

Endpoints (all RBAC-gated on 'email_outbox' write):
  GET  /api/email/entity-context/{module}/{record_id}
  POST /api/email/ai-draft                       — Claude cover-note generator
  POST /api/email/send-entity/{module}/{record_id}
"""
from __future__ import annotations

import base64
import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from core import db, get_current_user, new_id, now_iso, require_permission
from document_pdf import purchase_order_pdf, ra_bill_pdf, rfq_pdf
from m365_email import (
    SHARED_DISPLAY_NAME,
    SHARED_USERNAME,
    shared_mailbox_configured,
)
from routers.email_router import _queue_outbox, _send_and_log

logger = logging.getLogger("erp.email_actions")
router = APIRouter(prefix="/email", tags=["email"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")


# ─────────────────────────────────────────────────────────────────────────────
# Sender policy — per user's choice 3c
# ─────────────────────────────────────────────────────────────────────────────
SENDER_POLICY: Dict[str, str] = {
    "quotation": "user",
    "purchase_order": "user",
    "rfq": "user",
    "ra_bill": "user",
    "hr_letter": "shared",
}

# Mongo collection per supported module
MODULE_COLLECTION: Dict[str, str] = {
    "quotation": "quotations",
    "purchase_order": "purchase_orders",
    "rfq": "rfqs",
    "ra_bill": "ra_bills",
    "hr_letter": "hr_letters",
}

MODULE_LABEL = {
    "quotation": "Quotation",
    "purchase_order": "Purchase Order",
    "rfq": "Request for Quotation",
    "ra_bill": "Running Account Bill",
    "hr_letter": "Letter",
}


async def _fetch_record(module: str, record_id: str) -> Dict[str, Any]:
    if module not in MODULE_COLLECTION:
        raise HTTPException(400, f"Unsupported module: {module}. Allowed: {list(MODULE_COLLECTION)}")
    coll = MODULE_COLLECTION[module]
    rec = await db[coll].find_one({"id": record_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, f"{MODULE_LABEL[module]} not found")
    return rec


async def _resolve_recipients(module: str, rec: Dict[str, Any]) -> Dict[str, Any]:
    """Returns {to: [...], to_label, party, party_id}."""
    to: List[str] = []
    label = ""
    party = ""
    party_id = ""

    if module == "quotation":
        party_id = rec.get("client_id") or ""
        party = rec.get("client") or ""
        if rec.get("contact_email"):
            to.append(rec["contact_email"])
        if party_id:
            c = await db.clients.find_one({"id": party_id}, {"_id": 0, "email": 1, "name": 1, "contact_email": 1})
            if c:
                party = c.get("name") or party
                for k in ("email", "contact_email"):
                    e = c.get(k)
                    if e and e not in to:
                        to.append(e)
        label = f"Client · {party}"

    elif module in ("purchase_order", "rfq"):
        party_id = rec.get("vendor_id") or ""
        party = rec.get("vendor") or ""
        if not party_id and module == "rfq":
            # RFQs have a vendors[] list — pick the first vendor by default; the
            # frontend can pass ?vendor_id=… to scope to a specific one.
            vlist = rec.get("vendors") or []
            if vlist:
                party_id = vlist[0].get("vendor_id") or ""
                party = vlist[0].get("vendor_name") or ""
        if party_id:
            v = await db.vendors.find_one({"id": party_id}, {"_id": 0, "email": 1, "name": 1, "contact_email": 1})
            if v:
                party = v.get("name") or party
                for k in ("email", "contact_email"):
                    e = v.get(k)
                    if e and e not in to:
                        to.append(e)
        label = f"Vendor · {party}"

    elif module == "ra_bill":
        party_id = rec.get("client_id") or ""
        party = rec.get("client_name") or ""
        if party_id:
            c = await db.clients.find_one({"id": party_id}, {"_id": 0, "email": 1, "name": 1, "contact_email": 1})
            if c:
                party = c.get("name") or party
                for k in ("email", "contact_email"):
                    e = c.get(k)
                    if e and e not in to:
                        to.append(e)
        label = f"Client · {party}"

    elif module == "hr_letter":
        party_id = rec.get("employee_id") or ""
        party = rec.get("employee_name") or ""
        if party_id:
            emp = await db.employees.find_one({"id": party_id}, {"_id": 0, "email": 1, "name": 1})
            if emp:
                party = emp.get("name") or party
                if emp.get("email"):
                    to.append(emp["email"])
        label = f"Employee · {party}"

    return {"to": to, "to_label": label, "party": party, "party_id": party_id}


def _subject_template(module: str, rec: Dict[str, Any], party: str) -> str:
    if module == "quotation":
        return f"Quotation {rec.get('quote_number', '')} — {rec.get('project') or party}".strip()
    if module == "purchase_order":
        return f"Purchase Order {rec.get('po_number', '')} — INDIAN TRADE LINKS"
    if module == "rfq":
        return f"Request for Quotation {rec.get('rfq_number', '')} — INDIAN TRADE LINKS"
    if module == "ra_bill":
        return f"RA Bill {rec.get('bill_number', '')} — {rec.get('project_code') or party}"
    if module == "hr_letter":
        kind = (rec.get("template_kind") or "letter").replace("_", " ").title()
        return f"{kind} — {rec.get('employee_name') or party}"
    return f"{MODULE_LABEL.get(module, 'Document')} from INDIAN TRADE LINKS"


def _default_body(module: str, rec: Dict[str, Any], party: str) -> str:
    greeting = f"Dear {party.split()[0] if party else 'Sir/Madam'},"
    if module == "quotation":
        return (
            f"{greeting}\n\nPlease find attached our quotation "
            f"{rec.get('quote_number', '')} for {rec.get('project') or 'the referenced scope of work'}. "
            f"We look forward to your kind review.\n\nFor any clarification, please feel free to revert.\n\n"
            f"Best regards,\nINDIAN TRADE LINKS"
        )
    if module == "purchase_order":
        return (
            f"{greeting}\n\nPlease find attached Purchase Order {rec.get('po_number', '')} "
            f"against your acknowledged offer. Kindly acknowledge receipt at the earliest "
            f"and confirm the delivery schedule.\n\nBest regards,\nINDIAN TRADE LINKS"
        )
    if module == "rfq":
        return (
            f"{greeting}\n\nWe invite your most competitive offer against the attached RFQ "
            f"{rec.get('rfq_number', '')}. Kindly submit your sealed bid on or before the "
            f"closing date mentioned in the document.\n\nBest regards,\nINDIAN TRADE LINKS"
        )
    if module == "ra_bill":
        return (
            f"{greeting}\n\nPlease find attached our Running Account Bill {rec.get('bill_number', '')} "
            f"for the work executed at {rec.get('project_code') or 'the referenced project'}. "
            f"Request you to process the payment as per the agreed commercial terms.\n\n"
            f"Best regards,\nINDIAN TRADE LINKS"
        )
    if module == "hr_letter":
        return (
            f"{greeting}\n\nPlease find attached the {(rec.get('template_kind') or 'letter').replace('_', ' ')} "
            f"as discussed.\n\nKindly acknowledge receipt and revert in case of any clarification.\n\n"
            f"With regards,\nHuman Resources · INDIAN TRADE LINKS"
        )
    return f"{greeting}\n\nPlease find the attached document.\n\nRegards,\nINDIAN TRADE LINKS"


# ─────────────────────────────────────────────────────────────────────────────
# Attachment builders
# ─────────────────────────────────────────────────────────────────────────────
async def _build_attachment(module: str, rec: Dict[str, Any], party: str) -> Optional[Dict[str, Any]]:
    """Returns {filename, content_type, content_b64} or None."""
    try:
        if module == "quotation":
            # Use the existing PDF builder directly (avoid StreamingResponse wrapper).
            from routers.quotation_builder_router import _get_company
            from quotation_calc import recalc_quotation
            from quotation_pdf import render_quotation_pdf
            company = await _get_company()
            rec = dict(rec)
            rec["company_state"] = company.get("state")
            recalc_quotation(rec)
            pdf = render_quotation_pdf(rec, company)
            return {
                "filename": f"Quotation-{rec.get('quote_number', rec['id'][:8])}.pdf",
                "content_type": "application/pdf",
                "content_b64": base64.b64encode(pdf).decode("ascii"),
            }
        if module == "purchase_order":
            v = await db.vendors.find_one({"id": rec.get("vendor_id")}, {"_id": 0}) if rec.get("vendor_id") else None
            pdf = purchase_order_pdf(rec, v)
            return {
                "filename": f"PO-{rec.get('po_number', rec['id'][:8])}.pdf",
                "content_type": "application/pdf",
                "content_b64": base64.b64encode(pdf).decode("ascii"),
            }
        if module == "rfq":
            v = await db.vendors.find_one({"id": rec.get("vendor_id")}, {"_id": 0}) if rec.get("vendor_id") else None
            pdf = rfq_pdf(rec, v)
            return {
                "filename": f"RFQ-{rec.get('rfq_number', rec['id'][:8])}.pdf",
                "content_type": "application/pdf",
                "content_b64": base64.b64encode(pdf).decode("ascii"),
            }
        if module == "ra_bill":
            c = await db.clients.find_one({"id": rec.get("client_id")}, {"_id": 0}) if rec.get("client_id") else None
            pdf = ra_bill_pdf(rec, c)
            return {
                "filename": f"RA-Bill-{rec.get('bill_number', rec['id'][:8])}.pdf",
                "content_type": "application/pdf",
                "content_b64": base64.b64encode(pdf).decode("ascii"),
            }
        if module == "hr_letter":
            # hr_letters stores binary DOCX directly
            full = await db.hr_letters.find_one({"id": rec["id"]}, {"_id": 0})
            if full and full.get("binary"):
                kind = full.get("template_kind", "letter")
                emp_code = (full.get("employee_name") or "")[:24].replace(" ", "_") or rec["id"][:8]
                return {
                    "filename": f"{kind}_{emp_code}.docx",
                    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "content_b64": base64.b64encode(full["binary"]).decode("ascii"),
                }
    except Exception as e:
        logger.exception(f"[{module}] attachment build failed for {rec.get('id')}: {e}")
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 1 — entity context (used by the frontend dialog to prefill fields)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/entity-context/{module}/{record_id}")
async def get_entity_context(
    module: str,
    record_id: str,
    user: dict = Depends(require_permission("email_outbox", "write")),
):
    rec = await _fetch_record(module, record_id)
    recip = await _resolve_recipients(module, rec)
    sender_type = SENDER_POLICY.get(module, "shared")

    # If user-mode but the user hasn't configured their SMTP, fall back to shared
    sender_fallback_reason = None
    if sender_type == "user":
        u_creds = await db.smtp_user_credentials.find_one({"user_id": user["id"]}, {"_id": 0, "smtp_username": 1})
        if not u_creds:
            sender_type = "shared"
            sender_fallback_reason = "Per-user mailbox not configured — falling back to shared. Visit /app/me/email to set up your own."

    if sender_type == "shared" and not shared_mailbox_configured():
        raise HTTPException(503, "No sender available — shared mailbox not configured and user has no personal SMTP set up.")

    subject = _subject_template(module, rec, recip["party"])
    body = _default_body(module, rec, recip["party"])

    return {
        "module": module,
        "module_label": MODULE_LABEL.get(module, module),
        "record_id": record_id,
        "record_no": rec.get("quote_number") or rec.get("po_number") or rec.get("rfq_number") or rec.get("bill_number") or rec.get("template_name") or record_id[:8],
        "to": recip["to"],
        "to_label": recip["to_label"],
        "party": recip["party"],
        "party_id": recip["party_id"],
        "subject": subject,
        "body": body,
        "sender_type": sender_type,
        "sender_fallback_reason": sender_fallback_reason,
        "auto_attachment": {
            "filename_hint": _filename_hint(module, rec),
            "content_type_hint": "application/pdf" if module != "hr_letter" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    }


def _filename_hint(module: str, rec: Dict[str, Any]) -> str:
    if module == "quotation":
        return f"Quotation-{rec.get('quote_number', '')}.pdf"
    if module == "purchase_order":
        return f"PO-{rec.get('po_number', '')}.pdf"
    if module == "rfq":
        return f"RFQ-{rec.get('rfq_number', '')}.pdf"
    if module == "ra_bill":
        return f"RA-Bill-{rec.get('bill_number', '')}.pdf"
    if module == "hr_letter":
        return f"{rec.get('template_kind', 'letter')}.docx"
    return "document.pdf"


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 2 — AI cover-note draft (Claude Sonnet 4.5 via Universal Key)
# ─────────────────────────────────────────────────────────────────────────────
class AiDraftIn(BaseModel):
    module: str
    record_id: str
    tone: str = "professional"  # professional | friendly | firm | concise


@router.post("/ai-draft")
async def ai_draft(
    payload: AiDraftIn,
    user: dict = Depends(require_permission("email_outbox", "write")),
):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "EMERGENT_LLM_KEY not configured")

    rec = await _fetch_record(payload.module, payload.record_id)
    recip = await _resolve_recipients(payload.module, rec)

    summary = _summarise_record(payload.module, rec, recip["party"])

    system_msg = (
        "You are a senior business correspondence specialist at INDIAN TRADE LINKS, an Indian "
        "industrial services company (scaffolding, painting, rope access, insulation, roof "
        "sheeting). You draft polished, culturally-appropriate business emails. "
        "Always:\n"
        "  • Write in English, with Indian business etiquette (Mr./Ms., Sir/Madam, regards).\n"
        "  • Keep the subject crisp (max 80 chars).\n"
        "  • Keep the body 3-6 short paragraphs, no longer.\n"
        "  • Reference attached document explicitly.\n"
        "  • Sign off as 'INDIAN TRADE LINKS' (do NOT invent a person's name unless the "
        "sender_name is provided in the context).\n"
        "  • Return ONLY a JSON object: {\"subject\": \"…\", \"body\": \"…\"}\n"
        "  • body should be plain text with \\n line breaks (no HTML).\n"
        f"Tone: {payload.tone}."
    )
    user_msg = (
        f"Draft a cover email for:\n"
        f"Module: {MODULE_LABEL[payload.module]}\n"
        f"Recipient (party): {recip['party'] or 'the recipient'}\n"
        f"Recipient first name to greet: "
        f"{(recip['party'].split()[0] if recip['party'] else 'Sir/Madam')}\n"
        f"Sender name: {user.get('name') or 'INDIAN TRADE LINKS'}\n"
        f"Sender role: {user.get('role', '').replace('_', ' ').title()}\n\n"
        f"Record summary:\n{summary}\n\n"
        "Return JSON only."
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"email-draft-{new_id()}",
            system_message=system_msg,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        resp = await chat.send_message(UserMessage(text=user_msg))
    except Exception:
        logger.exception("AI draft failed; falling back to Gemini")
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"email-draft-fb-{new_id()}",
                system_message=system_msg,
            ).with_model("gemini", "gemini-2.5-pro")
            resp = await chat.send_message(UserMessage(text=user_msg))
        except Exception as e2:
            raise HTTPException(502, f"AI draft failed: {e2}")

    subject, body = _parse_ai_json(resp)
    if not subject:
        subject = _subject_template(payload.module, rec, recip["party"])
    if not body:
        body = _default_body(payload.module, rec, recip["party"])

    return {"subject": subject[:200], "body": body, "tone": payload.tone}


def _summarise_record(module: str, rec: Dict[str, Any], party: str) -> str:
    if module == "quotation":
        return (
            f"Quotation No.: {rec.get('quote_number', '—')}\n"
            f"Project: {rec.get('project', '—')}\n"
            f"Client: {party}\n"
            f"Scope: {(rec.get('scope_of_work') or '—')[:300]}\n"
            f"Total Value: ₹ {float(rec.get('total') or rec.get('amount') or 0):,.2f}"
        )
    if module == "purchase_order":
        return (
            f"PO No.: {rec.get('po_number', '—')}\n"
            f"Vendor: {party}\n"
            f"Project: {rec.get('project', '—')}\n"
            f"Value: ₹ {float(rec.get('amount') or 0):,.2f}\n"
            f"Delivery in: {rec.get('delivery_days', '—')} days\n"
            f"Payment terms: {rec.get('payment_terms', '—')}"
        )
    if module == "rfq":
        return (
            f"RFQ No.: {rec.get('rfq_number', '—')}\n"
            f"Project: {rec.get('project', '—')}\n"
            f"Vendor: {party}\n"
            f"Closing date: {rec.get('closing_date') or rec.get('submission_deadline') or '—'}\n"
            f"# of items: {len(rec.get('items') or [])}"
        )
    if module == "ra_bill":
        return (
            f"Bill No.: {rec.get('bill_number', '—')}\n"
            f"Project: {rec.get('project_code', '—')}\n"
            f"Client: {party}\n"
            f"Bill Type: {rec.get('bill_type', '—')}\n"
            f"Net Payable: ₹ {float(rec.get('net_payable') or 0):,.2f}"
        )
    if module == "hr_letter":
        return (
            f"Letter Type: {rec.get('template_kind', '—').replace('_', ' ').title()}\n"
            f"Employee: {rec.get('employee_name') or party}\n"
            f"Rendered on: {rec.get('rendered_at', '—')[:10]}"
        )
    return f"Module: {module}, party: {party}"


def _parse_ai_json(raw: str) -> tuple[str, str]:
    import json
    text = (raw or "").strip()
    if text.startswith("```"):
        # strip code fences
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    # Try direct parse
    try:
        d = json.loads(text)
        return d.get("subject", ""), d.get("body", "")
    except Exception:
        pass
    # Find first { … last }
    try:
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            d = json.loads(text[i: j + 1])
            return d.get("subject", ""), d.get("body", "")
    except Exception:
        pass
    return "", text


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 3 — send the entity by email
# ─────────────────────────────────────────────────────────────────────────────
class SendEntityIn(BaseModel):
    to: List[EmailStr]
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    subject: str = Field(..., min_length=1, max_length=300)
    body_text: str = Field(..., min_length=1)
    body_html: Optional[str] = None
    reply_to: Optional[EmailStr] = None
    attach_pdf: bool = True
    sender_override: Optional[str] = None  # "shared" | "user"


@router.post("/send-entity/{module}/{record_id}")
async def send_entity(
    module: str,
    record_id: str,
    payload: SendEntityIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_permission("email_outbox", "write")),
):
    rec = await _fetch_record(module, record_id)
    recip = await _resolve_recipients(module, rec)

    sender_type = payload.sender_override or SENDER_POLICY.get(module, "shared")
    if sender_type == "user":
        u_creds = await db.smtp_user_credentials.find_one({"user_id": user["id"]}, {"_id": 0})
        if not u_creds:
            # graceful fallback
            sender_type = "shared"

    if sender_type == "shared":
        if not shared_mailbox_configured():
            raise HTTPException(503, "Shared mailbox not configured. Configure /app/admin/email-settings first.")
        sender_email = SHARED_USERNAME
        sender_display = SHARED_DISPLAY_NAME
    else:
        u = await db.smtp_user_credentials.find_one({"user_id": user["id"]}, {"_id": 0})
        sender_email = u["smtp_username"]
        sender_display = u.get("display_name") or user.get("name")

    attachments_inline: List[Dict[str, Any]] = []
    if payload.attach_pdf:
        att = await _build_attachment(module, rec, recip["party"])
        if att:
            attachments_inline.append(att)

    outbox_id = await _queue_outbox(
        sender_type=sender_type,
        sender_user_id=user["id"],
        sender_email=sender_email,
        sender_display_name=sender_display,
        to=[str(e) for e in payload.to],
        cc=[str(e) for e in (payload.cc or [])],
        bcc=[str(e) for e in (payload.bcc or [])],
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
        reply_to=str(payload.reply_to) if payload.reply_to else None,
        attachments_inline=attachments_inline,
        file_ids=[],
        related={"entity_type": module, "entity_id": record_id, "entity_ref": recip.get("party_id")},
        queued_by=user["id"],
    )
    background_tasks.add_task(_send_and_log, outbox_id)
    return {
        "outbox_id": outbox_id,
        "status": "queued",
        "sender_type": sender_type,
        "attached": [a["filename"] for a in attachments_inline],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler hook — retry queued/failed older than retry_after_minutes
# ─────────────────────────────────────────────────────────────────────────────
async def retry_pending_outbox(max_attempts: int = 3, retry_after_minutes: int = 10) -> Dict[str, Any]:
    """Find queued/failed outbox rows past the retry window (attempts < cap)
    and re-trigger sending. Designed to be invoked by APScheduler every 10 min.
    """
    cutoff = datetime.now(timezone.utc).timestamp() - retry_after_minutes * 60
    candidates = await db.email_outbox.find(
        {
            "status": {"$in": ["queued", "failed", "sending"]},
            "attempts": {"$lt": max_attempts},
        },
        {"_id": 0, "id": 1, "attempts": 1, "updated_at": 1, "status": 1, "error_type": 1},
    ).sort("created_at", 1).limit(50).to_list(50)

    # Skip rows whose error is auth/permanent — those will never recover via retry.
    retried: List[str] = []
    skipped_auth: List[str] = []
    for row in candidates:
        ts = row.get("updated_at", "")
        try:
            row_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else 0
        except Exception:
            row_ts = 0
        if row_ts > cutoff:
            continue
        # Re-check error_type from full doc
        full = await db.email_outbox.find_one({"id": row["id"]}, {"_id": 0, "error_type": 1})
        if full and full.get("error_type") in ("auth", "permanent"):
            skipped_auth.append(row["id"])
            continue
        try:
            await _send_and_log(row["id"])
            retried.append(row["id"])
        except Exception as e:
            logger.warning(f"Retry failed for outbox {row['id']}: {e}")
    return {
        "retried": len(retried),
        "skipped_auth_or_permanent": len(skipped_auth),
        "considered": len(candidates),
    }
