"""HR · Document Scanner — Gemini 2.5 Pro vision OCR + field extraction + verification.

Pipeline:
  upload → list → POST /scan → extracts structured fields → compares to employee
  record → returns per-field verification status (match/mismatch/no_data) → optionally
  auto-populates empty employee fields → recomputes employees.verification_status.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from core import db, require_permission, now_iso, new_id
from audit import audit
from storage import put_object, get_object, MAX_BYTES
from .common import ip_of

load_dotenv()
logger = logging.getLogger("erp.hr.documents")
router = APIRouter(tags=["hr"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GEMINI_MODEL = "gemini-2.5-pro"

DOC_TYPES = {
    "aadhaar": "Aadhaar Card",
    "pan": "PAN Card",
    "bank_passbook": "Bank Passbook / Statement",
    "uan_passbook": "UAN / EPF Passbook",
    "esic_card": "ESIC Card",
    "educational": "Educational Certificate",
    "experience": "Experience Letter",
    "driving_license": "Driving License",
    "passport": "Passport",
    "voter_id": "Voter ID",
    "police_verification": "Police Verification",
    "medical_fitness": "Medical Fitness Certificate",
    "project_cert": "Project / Safety Certification (PASMA, IRATA, OSHA, NEBOSH, IOSH, etc.)",
    "other": "Other",
}

MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".pdf": "application/pdf",
}

# These are the doc types that drive `verification_status` on the employee record.
KEY_DOCS_FOR_VERIFICATION = {"aadhaar", "pan", "bank_passbook"}


# ════════════════════════ Upload / List / Delete ════════════════════════
async def _gemini_extract(blob: bytes, mime: str, doc_type: str, session_id: str) -> Dict[str, Any]:
    """Shared Gemini OCR + JSON extraction. Returns parsed dict (see SCAN_SYSTEM)."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "EMERGENT_LLM_KEY not configured — AI scan unavailable")
    ext_map = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "application/pdf": ".pdf",
    }
    suffix = ext_map.get(mime, ".bin")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(blob)
        tmp.flush()
        tmp.close()
        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=SCAN_SYSTEM,
        ).with_model("gemini", GEMINI_MODEL)
        fc = FileContentWithMimeType(file_path=tmp.name, mime_type=mime)
        prompt = (
            f"The HR system classifies this document as '{DOC_TYPES.get(doc_type, doc_type)}' "
            f"(doc_kind hint: {doc_type}).\n"
            f"Extract the structured JSON as per the system instructions. "
            f"If the actual document doesn't match this kind, return your best guess for doc_kind."
        )
        try:
            raw = await chat.send_message(UserMessage(text=prompt, file_contents=[fc]))
        except Exception as exc:
            logger.exception("Gemini extraction failed")
            raise HTTPException(502, f"AI scan failed: {exc}")
        return _safe_json_load(raw)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/documents/scan-prefill")
async def scan_prefill(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    request: Request = None,
    user: dict = Depends(require_permission("hr_employee_360", "write")),
):
    """Scan a doc WITHOUT attaching it to any employee.
    Returns extracted fields mapped to employee-form keys so a New Employee
    dialog can prefill in-memory before the row is saved. Designed for the
    'AI Auto-fill' UX at the time of creating a new employee."""
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"Unknown doc_type '{doc_type}'. Allowed: {sorted(DOC_TYPES)}")
    ext = ("." + (file.filename or "").rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    mime = MIME_MAP.get(ext)
    if not mime:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {sorted(MIME_MAP)}")
    blob = await file.read()
    if not blob:
        raise HTTPException(400, "Empty file")
    if len(blob) > MAX_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_BYTES // (1024 * 1024)} MB)")

    parsed = await _gemini_extract(blob, mime, doc_type, session_id="hr-prefill")
    fields = parsed.get("fields") or {}
    detected_kind = parsed.get("doc_kind") or doc_type
    map_kind = doc_type if doc_type in DOC_FIELD_MAP else detected_kind

    # Map extracted fields → employee form field names (so frontend can spread)
    field_map = DOC_FIELD_MAP.get(map_kind) or {}
    employee_fields: Dict[str, Any] = {}
    for ext_key, (emp_key, _kind) in field_map.items():
        v = fields.get(ext_key)
        if v not in (None, "", []):
            # Normalise IDs the same way validators do
            if _kind == "id":
                v = re.sub(r"[\s\-_/]+", "", str(v)).upper()
            employee_fields.setdefault(emp_key, v)

    # If PAN/Aadhaar/IFSC are auto-derived, also flip the corresponding "applicable" flags
    if employee_fields.get("uan"):
        employee_fields.setdefault("is_pf_applicable", True)
    if employee_fields.get("esic_number"):
        employee_fields.setdefault("is_esic_applicable", True)

    await audit(user=user, action="hr_doc_prefill_scan", resource="files",
                record_id=None,
                after={"doc_type": doc_type, "detected_kind": detected_kind,
                       "fields_extracted": list(fields.keys()),
                       "fields_mapped": list(employee_fields.keys())},
                ip=ip_of(request))

    return {
        "doc_type": doc_type,
        "detected_kind": detected_kind,
        "confidence": parsed.get("confidence"),
        "raw_fields": fields,
        "employee_fields": employee_fields,
        "raw_text_preview": (parsed.get("raw_text") or "")[:500],
    }


@router.post("/employees/{employee_id}/documents")
async def upload_employee_document(
    employee_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    label: str = Form(""),
    scan_result_json: str = Form(""),  # Optional — pre-scanned result from /documents/scan-prefill
    request: Request = None,
    user: dict = Depends(require_permission("hr_employee_360", "write")),
):
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"Unknown doc_type '{doc_type}'. Allowed: {sorted(DOC_TYPES)}")
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0, "id": 1, "name": 1})
    if not emp:
        raise HTTPException(404, "Employee not found")
    ext = ("." + (file.filename or "").rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    mime = MIME_MAP.get(ext)
    if not mime:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {sorted(MIME_MAP)}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_BYTES // (1024 * 1024)} MB)")
    try:
        result = put_object(folder="employees", filename=file.filename or "doc.bin", data=data, content_type=mime)
    except Exception as exc:
        logger.exception("upload failed")
        raise HTTPException(503, str(exc))
    record = {
        "id": new_id(),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": result.get("content_type") or mime,
        "size": result.get("size") or len(data),
        "title": label or DOC_TYPES[doc_type],
        "folder": "employees",
        "parent_type": "employees",
        "parent_id": employee_id,
        "category": None,
        "doc_type": doc_type,
        "doc_type_label": DOC_TYPES[doc_type],
        "scan_status": "not_scanned",
        "scan_result": None,
        "verification": None,
        "uploaded_by": user.get("name") or user.get("email"),
        "uploaded_by_id": user["id"],
        "is_deleted": False,
        "created_at": now_iso(),
    }

    # If the caller passed a pre-scanned result (from /documents/scan-prefill),
    # attach it without burning another Gemini call.
    if scan_result_json:
        try:
            pre = json.loads(scan_result_json)
        except Exception:
            pre = None
        if pre and isinstance(pre, dict):
            fields = pre.get("raw_fields") or pre.get("fields") or {}
            detected_kind = pre.get("detected_kind") or doc_type
            emp_doc = await db.employees.find_one({"id": employee_id}, {"_id": 0}) or {}
            map_kind = doc_type if doc_type in DOC_FIELD_MAP else detected_kind
            verification = _build_verification(map_kind, fields, emp_doc)
            record["scan_status"] = "scanned"
            record["scan_result"] = {
                "scanned_at": now_iso(),
                "scanned_by": user.get("name") or user.get("email"),
                "model": GEMINI_MODEL,
                "detected_kind": detected_kind,
                "confidence": pre.get("confidence"),
                "fields": fields,
                "raw_text_preview": (pre.get("raw_text_preview") or "")[:500],
                "from_prefill": True,
            }
            record["verification"] = verification

    await db.files.insert_one(record)
    record.pop("_id", None)
    if record["scan_status"] == "scanned":
        # Recompute employee verification status now that this doc has a verdict
        await _recompute_employee_verification(employee_id)
    await audit(user=user, action="hr_doc_upload", resource="files",
                record_id=record["id"],
                after={"doc_type": doc_type, "employee_id": employee_id,
                       "had_prescan": bool(scan_result_json)},
                ip=ip_of(request))
    return record


@router.get("/employees/{employee_id}/documents")
async def list_employee_documents(
    employee_id: str,
    user: dict = Depends(require_permission("hr_employee_360", "read")),
):
    rows = await db.files.find(
        {"parent_type": "employees", "parent_id": employee_id, "is_deleted": False},
        {"_id": 0},
    ).sort([("created_at", -1)]).to_list(500)
    return rows


@router.get("/document-types")
async def list_doc_types(user: dict = Depends(require_permission("hr_employee_360", "read"))):
    return [{"key": k, "label": v, "is_key_doc": k in KEY_DOCS_FOR_VERIFICATION}
            for k, v in DOC_TYPES.items()]


# ═══════════════════════ AI Scan & Verification ════════════════════════
SCAN_SYSTEM = """You are an expert Indian HR documents OCR & extractor.
Given ONE document image or PDF page, identify the document and extract structured fields.
Return JSON ONLY (no commentary, no markdown code fences).

The JSON MUST have this exact shape:
{
  "doc_kind": "aadhaar|pan|bank_passbook|uan_passbook|esic_card|educational|experience|driving_license|passport|voter_id|police_verification|medical_fitness|project_cert|other",
  "confidence": 0.0-1.0,
  "fields": { ...key/value pairs extracted from the document, see examples... },
  "raw_text": "all visible text on the document"
}

Document-specific field schemas (use the ones relevant; only include keys you actually find):

aadhaar:        {"name": "...", "aadhaar_number": "12-digit string", "dob": "YYYY-MM-DD", "gender": "Male|Female|Other", "address": "..."}
pan:            {"name": "...", "pan_number": "AAAAA9999A", "father_name": "...", "dob": "YYYY-MM-DD"}
bank_passbook:  {"account_holder": "...", "account_number": "...", "bank_name": "...", "ifsc": "AAAA0999999", "branch": "..."}
uan_passbook:   {"name": "...", "uan": "12-digit string", "pf_account": "...", "establishment": "..."}
esic_card:      {"name": "...", "esic_number": "10 or 17-digit string", "dob": "YYYY-MM-DD"}
educational:    {"name": "...", "qualification": "...", "institution": "...", "year_of_passing": "YYYY", "grade_or_percentage": "..."}
experience:     {"name": "...", "employer": "...", "designation": "...", "from_date": "YYYY-MM-DD", "to_date": "YYYY-MM-DD"}
driving_license:{"name": "...", "dl_number": "...", "dob": "YYYY-MM-DD", "valid_till": "YYYY-MM-DD", "categories": ["LMV","MCWG","..."]}
passport:       {"name": "...", "passport_number": "...", "dob": "YYYY-MM-DD", "expiry_date": "YYYY-MM-DD", "nationality": "..."}
voter_id:       {"name": "...", "epic_number": "...", "father_name": "...", "dob": "YYYY-MM-DD"}
police_verification: {"name": "...", "issuing_authority": "...", "issued_on": "YYYY-MM-DD", "report": "clear|adverse"}
medical_fitness:{"name": "...", "issued_by": "...", "issued_on": "YYYY-MM-DD", "fit_for": "...", "valid_till": "YYYY-MM-DD"}
project_cert:   {"name": "...", "cert_name": "PASMA/IRATA/OSHA/NEBOSH/IOSH/etc", "issuer": "...", "cert_number": "...", "issue_date": "YYYY-MM-DD", "expiry_date": "YYYY-MM-DD", "level": "..."}
other:          {"title": "..."}

Rules:
- Use ISO-8601 dates (YYYY-MM-DD). If only year+month, use "YYYY-MM-01".
- Strip spaces/hyphens from PAN/Aadhaar/UAN/ESIC/IFSC numbers.
- If you cannot read a field, OMIT it (do not write null or empty string).
- If the document type is ambiguous, set doc_kind to your best guess and lower confidence.
"""


def _safe_json_load(raw: str) -> Dict[str, Any]:
    if raw is None:
        return {}
    s = raw.strip()
    if s.startswith("```"):
        # strip ```json ... ```
        s = re.sub(r"^```(json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        # Try last-resort: extract first {...} block
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"_raw": raw[:2000]}


# ────────────── Field comparison helpers ──────────────
def _norm_str(v: Any) -> str:
    return re.sub(r"[\s\-_/]+", "", str(v or "")).upper()


def _norm_name(v: Any) -> str:
    return re.sub(r"[^A-Z]", "", str(v or "").upper())


def _norm_date(v: Any) -> str:
    if not v:
        return ""
    s = str(v).strip()
    # try ISO
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return s


# Map (doc_type, extracted_field_key) → (employee_field_key, comparator)
DOC_FIELD_MAP: Dict[str, Dict[str, Tuple[str, str]]] = {
    "aadhaar": {
        "name": ("name", "name"),
        "aadhaar_number": ("aadhaar_number", "id"),
        "dob": ("dob", "date"),
        "gender": ("gender", "str_ci"),
        "address": ("permanent_address", "name"),
    },
    "pan": {
        "name": ("name", "name"),
        "pan_number": ("pan_number", "id"),
        "father_name": ("father_name", "name"),
        "dob": ("dob", "date"),
    },
    "bank_passbook": {
        "account_holder": ("name", "name"),
        "account_number": ("bank_account_no", "id"),
        "ifsc": ("bank_ifsc", "id"),
        "bank_name": ("bank_name", "name"),
    },
    "uan_passbook": {
        "name": ("name", "name"),
        "uan": ("uan", "id"),
        "pf_account": ("pf_account", "id"),
    },
    "esic_card": {
        "name": ("name", "name"),
        "esic_number": ("esic_number", "id"),
        "dob": ("dob", "date"),
    },
    "driving_license": {"name": ("name", "name"), "dob": ("dob", "date")},
    "passport": {"name": ("name", "name"), "dob": ("dob", "date")},
    "voter_id": {"name": ("name", "name"), "father_name": ("father_name", "name"), "dob": ("dob", "date")},
    # certificates don't have stored counterparts on the employee — handled separately
}


def _compare(extracted: Any, emp_value: Any, kind: str) -> str:
    """Return 'match' | 'mismatch' | 'no_data'."""
    if not extracted:
        return "no_data"
    if emp_value is None or str(emp_value).strip() == "":
        return "no_data"
    if kind == "id":
        return "match" if _norm_str(extracted) == _norm_str(emp_value) else "mismatch"
    if kind == "name":
        a, b = _norm_name(extracted), _norm_name(emp_value)
        if not a or not b:
            return "no_data"
        # token overlap
        toks_a = set(re.findall(r"[A-Z]+", str(extracted).upper()))
        toks_b = set(re.findall(r"[A-Z]+", str(emp_value).upper()))
        if a == b or (toks_a and toks_b and len(toks_a & toks_b) >= max(1, min(len(toks_a), len(toks_b)) - 1)):
            return "match"
        return "mismatch"
    if kind == "date":
        da, db_ = _norm_date(extracted), _norm_date(emp_value)
        if not da or not db_:
            return "no_data"
        return "match" if da == db_ else "mismatch"
    if kind == "str_ci":
        return "match" if str(extracted).strip().lower() == str(emp_value).strip().lower() else "mismatch"
    return "no_data"


def _build_verification(doc_type: str, fields: Dict[str, Any], emp: Dict[str, Any]) -> Dict[str, Any]:
    field_map = DOC_FIELD_MAP.get(doc_type) or {}
    items = []
    counts = {"match": 0, "mismatch": 0, "no_data": 0}
    autofill: Dict[str, Any] = {}
    for ext_key, (emp_key, kind) in field_map.items():
        ext_val = fields.get(ext_key)
        emp_val = emp.get(emp_key)
        status = _compare(ext_val, emp_val, kind)
        # Auto-populate empty employee fields
        if status == "no_data" and ext_val and (emp_val is None or str(emp_val).strip() == ""):
            autofill[emp_key] = ext_val
        counts[status] = counts.get(status, 0) + 1
        items.append({
            "extracted_key": ext_key,
            "employee_key": emp_key,
            "kind": kind,
            "extracted_value": ext_val,
            "employee_value": emp_val,
            "status": status,
        })
    overall = "verified" if (counts["mismatch"] == 0 and counts["match"] > 0) else (
        "mismatch" if counts["mismatch"] > 0 else "no_data"
    )
    # Doc types with no employee-side counterpart (educational/experience/etc.)
    # still upload + scan; flag overall as 'no_data' (visible "—" badge in UI).
    if not items:
        overall = "no_data"
    return {"items": items, "counts": counts, "overall": overall, "autofill_candidates": autofill}


async def _recompute_employee_verification(employee_id: str) -> str:
    """Mark employee.verification_status = 'verified' if Aadhaar + PAN + Bank are
    all key-docs uploaded with `verification.overall='verified'`. Else 'pending'."""
    docs = await db.files.find(
        {"parent_type": "employees", "parent_id": employee_id, "is_deleted": False,
         "doc_type": {"$in": list(KEY_DOCS_FOR_VERIFICATION)}},
        {"_id": 0, "doc_type": 1, "verification": 1},
    ).to_list(50)
    have = {}
    for d in docs:
        ov = (d.get("verification") or {}).get("overall")
        if ov == "verified":
            have[d["doc_type"]] = True
    status = "verified" if all(k in have for k in KEY_DOCS_FOR_VERIFICATION) else "pending"
    await db.employees.update_one(
        {"id": employee_id},
        {"$set": {"verification_status": status, "verification_updated_at": now_iso()}},
    )
    return status


class ScanIn(BaseModel):
    apply_autofill: bool = True


@router.post("/employees/{employee_id}/documents/{doc_id}/scan")
async def scan_document(
    employee_id: str,
    doc_id: str,
    payload: ScanIn,
    request: Request,
    user: dict = Depends(require_permission("hr_employee_360", "write")),
):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "EMERGENT_LLM_KEY not configured — AI scan unavailable")
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    rec = await db.files.find_one(
        {"id": doc_id, "parent_id": employee_id, "parent_type": "employees", "is_deleted": False},
        {"_id": 0},
    )
    if not rec:
        raise HTTPException(404, "Document not found")
    doc_type = rec.get("doc_type") or "other"
    mime = rec.get("content_type") or "application/pdf"

    # Fetch object bytes
    try:
        blob, fetched_ct = get_object(rec["storage_path"])
    except Exception as exc:
        logger.exception("storage fetch failed")
        raise HTTPException(500, f"Storage fetch failed: {exc}")
    if not mime or mime == "application/octet-stream":
        mime = fetched_ct or "application/pdf"

    parsed = await _gemini_extract(blob, mime, doc_type, session_id=f"hr-doc-scan-{doc_id}")

    fields = parsed.get("fields") or {}
    detected_kind = parsed.get("doc_kind") or doc_type
    # If user-supplied doc_type doesn't match detected_kind for certs, prefer detected for verification mapping
    map_kind = doc_type if doc_type in DOC_FIELD_MAP else detected_kind
    verification = _build_verification(map_kind, fields, emp)

    autofill_applied: Dict[str, Any] = {}
    if payload.apply_autofill and verification["autofill_candidates"]:
        # Re-validate via india_compliance before writing
        from india_compliance import validate_employee_compliance
        merged = {**emp, **verification["autofill_candidates"]}
        errs = validate_employee_compliance(merged)
        if not errs:
            await db.employees.update_one(
                {"id": employee_id}, {"$set": verification["autofill_candidates"]}
            )
            autofill_applied = verification["autofill_candidates"]
        else:
            verification["autofill_skipped_reason"] = " · ".join(errs)

    scan_doc = {
        "scanned_at": now_iso(),
        "scanned_by": user.get("name") or user.get("email"),
        "model": GEMINI_MODEL,
        "detected_kind": detected_kind,
        "confidence": parsed.get("confidence"),
        "fields": fields,
        "raw_text_preview": (parsed.get("raw_text") or "")[:500],
    }
    await db.files.update_one(
        {"id": doc_id},
        {"$set": {
            "scan_status": "scanned",
            "scan_result": scan_doc,
            "verification": verification,
        }},
    )
    overall_emp = await _recompute_employee_verification(employee_id)
    await audit(user=user, action="hr_doc_scan", resource="files", record_id=doc_id,
                after={"doc_type": doc_type, "overall": verification["overall"],
                       "autofill": list(autofill_applied.keys())}, ip=ip_of(request))
    return {
        "ok": True,
        "scan": scan_doc,
        "verification": verification,
        "autofill_applied": autofill_applied,
        "employee_verification_status": overall_emp,
    }


@router.delete("/employees/{employee_id}/documents/{doc_id}")
async def delete_employee_document(
    employee_id: str, doc_id: str, request: Request,
    user: dict = Depends(require_permission("hr_employee_360", "write")),
):
    r = await db.files.update_one(
        {"id": doc_id, "parent_id": employee_id, "parent_type": "employees"},
        {"$set": {"is_deleted": True, "deleted_at": now_iso()}},
    )
    if not r.matched_count:
        raise HTTPException(404, "Document not found")
    await _recompute_employee_verification(employee_id)
    await audit(user=user, action="hr_doc_delete", resource="files",
                record_id=doc_id, ip=ip_of(request))
    return {"deleted": True}
