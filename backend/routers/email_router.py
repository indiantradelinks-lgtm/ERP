"""Email module router — Microsoft 365 SMTP send + Outbox.

Exposes:
  Admin:
    GET    /api/email/config              — system status (shared mailbox configured? fernet ready?)
    POST   /api/email/config/test         — send a test from the shared mailbox

  User (per-user M365 mailbox):
    GET    /api/email/me/smtp             — get my saved SMTP username (no password)
    PUT    /api/email/me/smtp             — save my mailbox + app password (encrypted)
    DELETE /api/email/me/smtp             — clear my SMTP credentials
    POST   /api/email/me/test             — send a test from my mailbox

  Generic send (any authenticated user, RBAC-gated):
    POST   /api/email/send                — queue an email (multipart/form-data with files)

  Outbox:
    GET    /api/email/outbox              — paginated list with filters
    GET    /api/email/outbox/{id}         — outbox detail
    POST   /api/email/outbox/{id}/retry   — re-attempt a failed/queued email
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, EmailStr, Field

from core import db, get_current_user, new_id, now_iso, require_permission
from storage import get_object
from m365_email import (
    Attachment,
    SHARED_DISPLAY_NAME,
    SHARED_PASSWORD,
    SHARED_USERNAME,
    build_email_message,
    decrypt_secret,
    encrypt_secret,
    fernet_ready,
    friendly_error_message,
    send_email,
    shared_mailbox_configured,
)

logger = logging.getLogger("erp.email_router")
router = APIRouter(prefix="/email", tags=["email"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class UserSmtpUpdate(BaseModel):
    smtp_username: EmailStr
    app_password: str = Field(..., min_length=8, max_length=200)
    display_name: Optional[str] = None


class SendTestRequest(BaseModel):
    to: EmailStr
    subject: Optional[str] = "ERP — SMTP test email"
    body: Optional[str] = "If you can read this, M365 SMTP from your ERP is working ✅"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _redact(addr: str) -> str:
    if not addr or "@" not in addr:
        return ""
    name, dom = addr.split("@", 1)
    if len(name) <= 2:
        return f"{name[0]}***@{dom}"
    return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}@{dom}"


async def _get_user_creds(user_id: str) -> Optional[dict]:
    doc = await db.smtp_user_credentials.find_one({"user_id": user_id}, {"_id": 0})
    return doc


async def _persist_outbox_record(
    record: dict,
    result: dict,
    sent_via: str,
) -> None:
    update: Dict[str, Any] = {
        "attempts": result.get("attempts", 1),
        "smtp_response": result.get("smtp_response", ""),
        "updated_at": now_iso(),
        "sent_via": sent_via,
    }
    if result.get("ok"):
        update["status"] = "sent"
        update["sent_at"] = now_iso()
        update["error_type"] = None
        update["last_error"] = None
        if result.get("partial_failures"):
            update["partial_failures"] = result["partial_failures"]
    else:
        update["status"] = "failed"
        update["error_type"] = result.get("error_type", "unknown")
        update["last_error"] = friendly_error_message(
            result.get("error_type", "unknown"), result.get("last_error", "")
        )
        update["raw_error"] = result.get("last_error", "")
    await db.email_outbox.update_one({"id": record["id"]}, {"$set": update})


async def _send_and_log(outbox_id: str) -> dict:
    """Reads the outbox record, builds MIME, sends, updates status. Returns the result dict."""
    rec = await db.email_outbox.find_one({"id": outbox_id}, {"_id": 0})
    if not rec:
        return {"ok": False, "error_type": "permanent", "last_error": "Outbox record missing"}

    await db.email_outbox.update_one({"id": outbox_id}, {"$set": {"status": "sending", "updated_at": now_iso()}})

    # Resolve credentials
    sender_type = rec.get("sender_type", "shared")
    if sender_type == "user":
        creds = await _get_user_creds(rec.get("sender_user_id"))
        if not creds:
            result = {"ok": False, "error_type": "auth", "last_error": "User SMTP credentials missing"}
            await _persist_outbox_record(rec, result, sent_via="user")
            return result
        try:
            password = decrypt_secret(creds["encrypted_app_password"])
        except Exception as e:
            result = {"ok": False, "error_type": "auth", "last_error": f"Could not decrypt: {e}"}
            await _persist_outbox_record(rec, result, sent_via="user")
            return result
        username = creds["smtp_username"]
        from_name = creds.get("display_name") or None
    else:
        if not shared_mailbox_configured():
            result = {"ok": False, "error_type": "auth", "last_error": "Shared mailbox not configured (.env)"}
            await _persist_outbox_record(rec, result, sent_via="shared")
            return result
        username = SHARED_USERNAME
        password = SHARED_PASSWORD
        from_name = rec.get("from_name") or SHARED_DISPLAY_NAME

    # Resolve attachments
    attachments: List[Attachment] = []
    for att in rec.get("attachments_inline", []) or []:
        try:
            content = base64.b64decode(att["content_b64"])
            attachments.append(Attachment(att.get("filename", "file.bin"), content, att.get("content_type", "application/octet-stream")))
        except Exception as e:
            logger.warning(f"Bad inline attachment in {outbox_id}: {e}")
    for fid in rec.get("file_ids", []) or []:
        f = await db.files.find_one({"id": fid, "is_deleted": False}, {"_id": 0})
        if not f:
            continue
        try:
            data, ct = get_object(f["storage_path"])
            attachments.append(Attachment(f.get("original_filename") or "file.bin", data, f.get("content_type") or ct or "application/octet-stream"))
        except Exception as e:
            logger.warning(f"Could not fetch attachment {fid}: {e}")

    try:
        msg, envelope = build_email_message(
            from_email=username,
            from_name=from_name,
            to=rec.get("to", []),
            cc=rec.get("cc", []),
            bcc=rec.get("bcc", []),
            reply_to=rec.get("reply_to") or None,
            subject=rec.get("subject", ""),
            text_body=rec.get("body_text", ""),
            html_body=rec.get("body_html") or None,
            attachments=attachments,
        )
    except Exception as e:
        result = {"ok": False, "error_type": "permanent", "last_error": f"Compose error: {e}"}
        await _persist_outbox_record(rec, result, sent_via=sender_type)
        return result

    result = await send_email(msg=msg, recipients=envelope, username=username, password=password)
    await _persist_outbox_record(rec, result, sent_via=sender_type)
    return result


# ---------------------------------------------------------------------------
# Admin: configuration & shared mailbox test
# ---------------------------------------------------------------------------
@router.get("/config")
async def get_email_config(user: dict = Depends(require_permission("email_outbox", "read"))):
    return {
        "shared_mailbox_configured": shared_mailbox_configured(),
        "shared_mailbox": _redact(SHARED_USERNAME) if SHARED_USERNAME else "",
        "shared_display_name": SHARED_DISPLAY_NAME,
        "fernet_ready": fernet_ready(),
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
    }


@router.post("/config/test")
async def send_shared_test(
    body: SendTestRequest,
    user: dict = Depends(require_permission("email_outbox", "write")),
):
    if not shared_mailbox_configured():
        raise HTTPException(status_code=400, detail="Shared mailbox not configured in .env (M365_SMTP_SHARED_USERNAME / _PASSWORD)")
    outbox_id = await _queue_outbox(
        sender_type="shared",
        sender_user_id=user["id"],
        sender_email=SHARED_USERNAME,
        sender_display_name=SHARED_DISPLAY_NAME,
        to=[body.to],
        cc=[],
        bcc=[],
        subject=body.subject or "ERP — SMTP test",
        body_text=body.body or "",
        body_html=None,
        reply_to=None,
        attachments_inline=[],
        file_ids=[],
        related={"entity_type": "test", "entity_id": "shared"},
        queued_by=user["id"],
    )
    result = await _send_and_log(outbox_id)
    rec = await db.email_outbox.find_one({"id": outbox_id}, {"_id": 0})
    return {"outbox_id": outbox_id, "result": result, "record": rec}


# ---------------------------------------------------------------------------
# Per-user M365 credentials
# ---------------------------------------------------------------------------
@router.get("/me/smtp")
async def get_my_smtp(user: dict = Depends(get_current_user)):
    doc = await _get_user_creds(user["id"])
    if not doc:
        return {"configured": False}
    return {
        "configured": True,
        "smtp_username": doc.get("smtp_username", ""),
        "display_name": doc.get("display_name") or "",
        "updated_at": doc.get("updated_at"),
        "last_test_status": doc.get("last_test_status"),
        "last_test_at": doc.get("last_test_at"),
    }


@router.put("/me/smtp")
async def update_my_smtp(payload: UserSmtpUpdate, user: dict = Depends(get_current_user)):
    if not fernet_ready():
        raise HTTPException(status_code=500, detail="Server-side encryption key (M365_FERNET_KEY) is not configured")
    encrypted = encrypt_secret(payload.app_password)
    doc = {
        "user_id": user["id"],
        "smtp_username": str(payload.smtp_username),
        "encrypted_app_password": encrypted,
        "display_name": (payload.display_name or user.get("name") or "").strip() or None,
        "updated_at": now_iso(),
    }
    await db.smtp_user_credentials.update_one(
        {"user_id": user["id"]},
        {"$set": doc, "$setOnInsert": {"created_at": now_iso()}},
        upsert=True,
    )
    return {"ok": True, "smtp_username": doc["smtp_username"]}


@router.delete("/me/smtp")
async def delete_my_smtp(user: dict = Depends(get_current_user)):
    await db.smtp_user_credentials.delete_one({"user_id": user["id"]})
    return {"ok": True}


@router.post("/me/test")
async def send_my_test(body: SendTestRequest, user: dict = Depends(get_current_user)):
    creds = await _get_user_creds(user["id"])
    if not creds:
        raise HTTPException(status_code=400, detail="No SMTP credentials saved. Configure them in Profile → Email Settings first.")
    outbox_id = await _queue_outbox(
        sender_type="user",
        sender_user_id=user["id"],
        sender_email=creds["smtp_username"],
        sender_display_name=creds.get("display_name") or user.get("name"),
        to=[body.to],
        cc=[],
        bcc=[],
        subject=body.subject or "ERP — SMTP test",
        body_text=body.body or "",
        body_html=None,
        reply_to=None,
        attachments_inline=[],
        file_ids=[],
        related={"entity_type": "test", "entity_id": "user"},
        queued_by=user["id"],
    )
    result = await _send_and_log(outbox_id)
    await db.smtp_user_credentials.update_one(
        {"user_id": user["id"]},
        {"$set": {
            "last_test_status": "sent" if result.get("ok") else "failed",
            "last_test_at": now_iso(),
            "last_test_error": None if result.get("ok") else result.get("last_error"),
        }},
    )
    rec = await db.email_outbox.find_one({"id": outbox_id}, {"_id": 0})
    return {"outbox_id": outbox_id, "result": result, "record": rec}


# ---------------------------------------------------------------------------
# Generic send (supports file uploads)
# ---------------------------------------------------------------------------
async def _queue_outbox(
    *,
    sender_type: str,
    sender_user_id: str,
    sender_email: str,
    sender_display_name: Optional[str],
    to: List[str],
    cc: List[str],
    bcc: List[str],
    subject: str,
    body_text: str,
    body_html: Optional[str],
    reply_to: Optional[str],
    attachments_inline: List[dict],
    file_ids: List[str],
    related: Optional[dict],
    queued_by: str,
) -> str:
    rec = {
        "id": new_id(),
        "sender_type": sender_type,
        "sender_user_id": sender_user_id,
        "sender_email": sender_email,
        "sender_display_name": sender_display_name,
        "from_name": sender_display_name,
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "reply_to": reply_to,
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "attachments_inline": attachments_inline,
        "attachments_summary": [
            {"filename": a.get("filename"), "content_type": a.get("content_type"), "size": len(base64.b64decode(a["content_b64"]) if a.get("content_b64") else b"")}
            for a in (attachments_inline or [])
        ],
        "file_ids": file_ids,
        "related": related or {},
        "status": "queued",
        "attempts": 0,
        "queued_by": queued_by,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.email_outbox.insert_one(rec)
    return rec["id"]


@router.post("/send")
async def queue_email(
    background_tasks: BackgroundTasks,
    to: str = Form(...),
    subject: str = Form(...),
    body_text: str = Form(""),
    body_html: str = Form(""),
    cc: str = Form(""),
    bcc: str = Form(""),
    reply_to: str = Form(""),
    sender: str = Form("shared"),  # "shared" | "user"
    related_type: str = Form(""),
    related_id: str = Form(""),
    file_ids: str = Form(""),  # comma-separated
    files: List[UploadFile] = File(default_factory=list),
    user: dict = Depends(require_permission("email_outbox", "write")),
):
    to_list = [a.strip() for a in to.split(",") if a.strip()]
    cc_list = [a.strip() for a in cc.split(",") if a.strip()]
    bcc_list = [a.strip() for a in bcc.split(",") if a.strip()]
    file_id_list = [f.strip() for f in file_ids.split(",") if f.strip()]
    if not to_list:
        raise HTTPException(status_code=400, detail="`to` is required")

    sender = sender.lower().strip()
    if sender not in {"shared", "user"}:
        raise HTTPException(status_code=400, detail="sender must be 'shared' or 'user'")
    if sender == "shared" and not shared_mailbox_configured():
        raise HTTPException(status_code=400, detail="Shared mailbox not configured (.env)")
    sender_email = SHARED_USERNAME
    sender_display = SHARED_DISPLAY_NAME
    if sender == "user":
        creds = await _get_user_creds(user["id"])
        if not creds:
            raise HTTPException(status_code=400, detail="You have no per-user SMTP credentials. Configure them in Profile → Email Settings.")
        sender_email = creds["smtp_username"]
        sender_display = creds.get("display_name") or user.get("name")

    inline: List[dict] = []
    for f in files:
        data = await f.read()
        if not data:
            continue
        inline.append({
            "filename": f.filename or "file.bin",
            "content_type": f.content_type or "application/octet-stream",
            "content_b64": base64.b64encode(data).decode("ascii"),
        })

    outbox_id = await _queue_outbox(
        sender_type=sender,
        sender_user_id=user["id"],
        sender_email=sender_email,
        sender_display_name=sender_display,
        to=to_list,
        cc=cc_list,
        bcc=bcc_list,
        subject=subject,
        body_text=body_text,
        body_html=body_html or None,
        reply_to=reply_to or None,
        attachments_inline=inline,
        file_ids=file_id_list,
        related={"entity_type": related_type, "entity_id": related_id} if (related_type or related_id) else {},
        queued_by=user["id"],
    )
    background_tasks.add_task(_send_and_log, outbox_id)
    return {"outbox_id": outbox_id, "status": "queued"}


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------
@router.get("/outbox")
async def list_outbox(
    status: str = Query("", description="Filter by status (queued/sending/sent/failed)"),
    sender: str = Query("", description="shared | user | me (own only)"),
    q: str = Query("", description="Search subject / recipients"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    user: dict = Depends(require_permission("email_outbox", "read")),
):
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if sender == "me":
        query["queued_by"] = user["id"]
    elif sender in ("shared", "user"):
        query["sender_type"] = sender
    if q:
        query["$or"] = [
            {"subject": {"$regex": q, "$options": "i"}},
            {"to": {"$elemMatch": {"$regex": q, "$options": "i"}}},
            {"sender_email": {"$regex": q, "$options": "i"}},
        ]

    total = await db.email_outbox.count_documents(query)
    rows = await db.email_outbox.find(query, {"_id": 0, "attachments_inline": 0, "body_html": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "skip": skip, "limit": limit, "rows": rows}


@router.get("/outbox/{outbox_id}")
async def get_outbox(outbox_id: str, user: dict = Depends(require_permission("email_outbox", "read"))):
    rec = await db.email_outbox.find_one({"id": outbox_id}, {"_id": 0, "attachments_inline": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    return rec


@router.post("/outbox/{outbox_id}/retry")
async def retry_outbox(
    outbox_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_permission("email_outbox", "write")),
):
    rec = await db.email_outbox.find_one({"id": outbox_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    if rec.get("status") == "sent":
        raise HTTPException(status_code=400, detail="Already sent — cannot retry")
    await db.email_outbox.update_one(
        {"id": outbox_id},
        {"$set": {"status": "queued", "updated_at": now_iso(), "last_error": None}},
    )
    background_tasks.add_task(_send_and_log, outbox_id)
    return {"ok": True, "status": "queued"}


# ---------------------------------------------------------------------------
# Startup: indexes
# ---------------------------------------------------------------------------
async def ensure_email_indexes() -> None:
    await db.smtp_user_credentials.create_index("user_id", unique=True)
    await db.email_outbox.create_index("id", unique=True)
    await db.email_outbox.create_index([("status", 1), ("created_at", -1)])
    await db.email_outbox.create_index([("sender_type", 1), ("created_at", -1)])
    await db.email_outbox.create_index([("queued_by", 1), ("created_at", -1)])
    await db.email_outbox.create_index("created_at")
