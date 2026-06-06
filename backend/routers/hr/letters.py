"""HR · Letters & Templates.

Upload DOCX templates with Jinja-style placeholders. The merge engine fills
employee + company + user + custom-variable context and returns a generated
DOCX. Templates are stored in `db.letter_templates` with the binary in
`db.letter_template_files` (gridfs-style chunked blob).

Supported placeholders (out-of-the-box, ALL flat — easier merge):
  employee:  {{name}} {{emp_code}} {{designation}} {{department}} {{role}}
             {{joining_date}} {{email}} {{phone}} {{salary}}
  company:   {{company_name}} {{company_address}} {{company_gst}}
  user:      {{user_name}} {{user_email}} {{user_role}}
  meta:      {{today}} {{today_long}}  (e.g. 23 May 2026)
  custom:    any extra key sent in payload.variables {} at render time
"""
from __future__ import annotations

import base64
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from .common import ip_of, strip_id

logger = logging.getLogger("erp.hr.letters")
router = APIRouter(tags=["hr"])

ALLOWED_KINDS = {
    "offer", "appointment", "confirmation", "experience", "relieving",
    "warning", "transfer", "promotion", "increment", "salary_slip", "custom",
}


@router.get("/letter-templates")
async def list_templates(kind: Optional[str] = None,
                         user: dict = Depends(require_permission("hr_letters", "read"))):
    q: Dict[str, Any] = {}
    if kind:
        q["kind"] = kind
    return await db.letter_templates.find(q, {"_id": 0, "binary": 0}) \
        .sort([("created_at", -1)]).to_list(200)


@router.get("/letter-templates/{tid}")
async def get_template(tid: str,
                       user: dict = Depends(require_permission("hr_letters", "read"))):
    row = await db.letter_templates.find_one({"id": tid}, {"_id": 0, "binary": 0})
    if not row:
        raise HTTPException(404, "Template not found")
    return row


@router.post("/letter-templates")
async def upload_template(
    file: UploadFile = File(...),
    name: str = Form(...),
    kind: str = Form("custom"),
    description: str = Form(""),
    request: Request = None,
    user: dict = Depends(require_permission("hr_letters", "write"))
):
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "Only .docx templates are supported")
    if kind not in ALLOWED_KINDS:
        raise HTTPException(400, f"Unknown kind '{kind}'. Allowed: {sorted(ALLOWED_KINDS)}")
    blob = await file.read()
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10 MB)")
    # Validate parseable docx
    try:
        from docx import Document
        Document(io.BytesIO(blob))
    except Exception as e:
        raise HTTPException(400, f"Invalid DOCX file: {e}")
    doc = {
        "id": new_id(),
        "name": name.strip(),
        "kind": kind,
        "description": description.strip() or None,
        "filename": file.filename,
        "size_bytes": len(blob),
        "binary": blob,  # stored as BSON Binary; never returned via list endpoints
        "active": True,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.letter_templates.insert_one(doc)
    await audit(user=user, action="hr_letter_template_upload", resource="letter_templates",
                record_id=doc["id"], after={"name": name, "kind": kind, "size_bytes": len(blob)},
                ip=ip_of(request))
    # Strip binary before returning
    out = dict(doc); out.pop("binary", None); out.pop("_id", None)
    return out


@router.delete("/letter-templates/{tid}")
async def delete_template(tid: str, request: Request,
                          user: dict = Depends(require_permission("hr_letters", "delete"))):
    r = await db.letter_templates.delete_one({"id": tid})
    if not r.deleted_count:
        raise HTTPException(404, "Template not found")
    await audit(user=user, action="hr_letter_template_delete", resource="letter_templates",
                record_id=tid, ip=ip_of(request))
    return {"deleted": True}


@router.get("/letter-templates/{tid}/download")
async def download_template(tid: str,
                            user: dict = Depends(require_permission("hr_letters", "read"))):
    row = await db.letter_templates.find_one({"id": tid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Template not found")
    return StreamingResponse(
        io.BytesIO(row["binary"]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{row.get("filename", "template.docx")}"'},
    )


# ────────────────────────────────────── Merge ────────────────────────────────
async def _company_context() -> Dict[str, Any]:
    profile = await db.company_profile.find_one({}, {"_id": 0}) or {}
    return {
        "company_name": profile.get("name") or "Indian Trade Links",
        "company_address": profile.get("address") or "",
        "company_gst": profile.get("gst") or "",
        "company_email": profile.get("email") or "",
        "company_phone": profile.get("phone") or "",
    }


def _employee_context(emp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": emp.get("name", ""),
        "emp_code": emp.get("emp_code", ""),
        "designation": emp.get("designation") or emp.get("role", ""),
        "department": emp.get("department", "") or "",
        "role": emp.get("role", ""),
        "joining_date": emp.get("joining_date", "") or "",
        "email": emp.get("email", "") or "",
        "phone": emp.get("phone", "") or "",
        "salary": emp.get("salary") or 0,
    }


def _meta_context() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "today": now.strftime("%Y-%m-%d"),
        "today_long": now.strftime("%d %B %Y"),
    }


class RenderIn(BaseModel):
    employee_id: str
    variables: Optional[Dict[str, Any]] = None


@router.post("/letter-templates/{tid}/render")
async def render_letter(tid: str, payload: RenderIn, request: Request,
                        user: dict = Depends(require_permission("hr_letters", "write"))):
    """Merge template with employee + company + user + custom context and return DOCX."""
    tpl = await db.letter_templates.find_one({"id": tid}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Template not found")
    emp = await db.employees.find_one({"id": payload.employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")

    context = {
        **_employee_context(emp),
        **(await _company_context()),
        "user_name": user.get("name") or "",
        "user_email": user.get("email") or "",
        "user_role": user.get("role") or "",
        **_meta_context(),
        **(payload.variables or {}),
    }

    try:
        from docxtpl import DocxTemplate
        src = io.BytesIO(tpl["binary"])
        doc = DocxTemplate(src)
        doc.render(context)
        out = io.BytesIO()
        doc.save(out)
        out.seek(0)
        merged = out.getvalue()
    except Exception as e:
        logger.exception("Letter render failed")
        raise HTTPException(500, f"Render failed: {e}")

    # Persist letter generation record (without the heavy binary, keep base64 only if you want — we omit it here)
    letter_doc = {
        "id": new_id(),
        "template_id": tid,
        "template_name": tpl.get("name"),
        "template_kind": tpl.get("kind"),
        "employee_id": emp["id"],
        "employee_name": emp.get("name"),
        "variables": payload.variables or {},
        "size_bytes": len(merged),
        "rendered_at": now_iso(),
        "rendered_by": user.get("name") or user.get("email"),
        "binary": merged,
    }
    await db.hr_letters.insert_one(letter_doc)
    await audit(user=user, action="hr_letter_render", resource="hr_letters",
                record_id=letter_doc["id"],
                after={"template_id": tid, "employee_id": emp["id"]}, ip=ip_of(request))
    filename = f"{tpl.get('kind', 'letter')}_{emp.get('emp_code') or emp['id'][:8]}.docx"
    return StreamingResponse(
        io.BytesIO(merged),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "X-Letter-Id": letter_doc["id"]},
    )


@router.get("/letters")
async def list_letters(employee_id: Optional[str] = None,
                       kind: Optional[str] = None,
                       user: dict = Depends(require_permission("hr_letters", "read"))):
    q: Dict[str, Any] = {}
    if employee_id: q["employee_id"] = employee_id
    if kind: q["template_kind"] = kind
    rows = await db.hr_letters.find(q, {"_id": 0, "binary": 0}) \
        .sort([("rendered_at", -1)]).to_list(500)
    return rows


@router.get("/letters/{lid}/download")
async def download_letter(lid: str,
                          user: dict = Depends(require_permission("hr_letters", "read"))):
    row = await db.hr_letters.find_one({"id": lid}, {"_id": 0})
    if not row or "binary" not in row:
        raise HTTPException(404, "Letter not found")
    filename = f"{row.get('template_kind', 'letter')}_{row.get('employee_name', 'emp')}.docx"
    return StreamingResponse(
        io.BytesIO(row["binary"]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/letters/placeholders")
async def list_placeholders(user: dict = Depends(require_permission("hr_letters", "read"))):
    """Helpful reference list of every placeholder the merge engine understands."""
    return {
        "employee": ["name", "emp_code", "designation", "department", "role",
                     "joining_date", "email", "phone", "salary"],
        "company": ["company_name", "company_address", "company_gst",
                    "company_email", "company_phone"],
        "user": ["user_name", "user_email", "user_role"],
        "meta": ["today", "today_long"],
        "custom": "Any additional key passed in 'variables' at render time. "
                  "Example: {{ increment_amount }}, {{ new_designation }}.",
    }
