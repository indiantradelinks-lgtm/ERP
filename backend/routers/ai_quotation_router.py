"""AI-assisted RFQ extraction and quotation suggestions.

Uses Emergent Universal LLM Key via `emergentintegrations.llm.chat.LlmChat`.

  /ai/extract-rfq   — multipart file → structured RFQ JSON (Gemini, supports PDF/DOCX/XLSX/image)
  /ai/suggest-items — JSON {service, basis, scope_text} → AI-suggested line items (Claude)
  /ai/risk-review   — JSON {scope_text, items} → AI risk flags + missing-info hints
"""
from __future__ import annotations

import io
import json
import logging
import os
import tempfile
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field

from core import require_permission, new_id, now_iso
from quotation_data import SERVICES, SERVICE_BASES, PRESET_ITEMS

logger = logging.getLogger("erp.ai_quotation")
router = APIRouter(tags=["ai-quotation"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

# Allowed file MIME map (Gemini supports these via emergentintegrations)
MIME_MAP = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
}


def _check_key():
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="EMERGENT_LLM_KEY not configured")


def _strip_code_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        # remove opening ```json or ``` and closing ```
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _safe_json_load(s: str) -> Dict[str, Any]:
    s = _strip_code_fence(s)
    try:
        return json.loads(s)
    except Exception:
        # Best-effort: find the first { ... } block
        try:
            start = s.find("{"); end = s.rfind("}")
            if 0 <= start < end:
                return json.loads(s[start:end + 1])
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"AI returned non-JSON output (snippet: {s[:200]})")


# ---------- /ai/extract-rfq ----------
RFQ_EXTRACT_SYSTEM = (
    "You are an industrial-services RFQ analyst for INDIAN TRADE LINKS, a contractor "
    "in Scaffolding, Painting, Rope Access, Insulation, and Roof Sheeting. "
    "Read the attached customer RFQ document and return a SINGLE JSON object only — "
    "no prose, no markdown. Use null when a field is not present in the document.\n\n"
    "JSON shape:\n"
    "{\n"
    "  \"customer\": str|null,\n"
    "  \"customer_rfq_no\": str|null,\n"
    "  \"rfq_date\": \"YYYY-MM-DD\"|null,\n"
    "  \"site_location\": str|null,\n"
    "  \"contact_person\": str|null,\n"
    "  \"contact_email\": str|null,\n"
    "  \"contact_phone\": str|null,\n"
    "  \"submission_deadline\": \"YYYY-MM-DD\"|null,\n"
    "  \"service_categories\": [\"scaffolding\"|\"painting\"|\"rope_access\"|\"insulation\"|\"roof_sheeting\", ...],\n"
    "  \"rfq_type\": [\"manpower_only\"|\"material_only\"|\"manpower_material\"|\"volume\"|\"area\"|\"item_rate\"|\"lump_sum\"|\"monthly_rental\"|\"shutdown\", ...],\n"
    "  \"scope_of_work\": str,\n"
    "  \"technical_specifications\": str|null,\n"
    "  \"commercial_terms\": str|null,\n"
    "  \"payment_terms\": str|null,\n"
    "  \"delivery_timeline\": str|null,\n"
    "  \"line_items\": [\n"
    "    { \"description\": str, \"quantity\": number|null, \"unit\": str|null, \"specification\": str|null }\n"
    "  ],\n"
    "  \"required_documents\": [str],\n"
    "  \"missing_information\": [str],\n"
    "  \"risk_points\": [str],\n"
    "  \"clarification_questions\": [str]\n"
    "}"
)


@router.post("/quotation-builder/ai/extract-rfq")
async def extract_rfq(file: UploadFile = File(...),
                      user: dict = Depends(require_permission("quotations", "write"))):
    _check_key()
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename missing")
    ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in file.filename else ""
    mime = MIME_MAP.get(ext)
    if not mime:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {list(MIME_MAP)}")

    # Write to temp file (emergentintegrations expects a file_path)
    suffix = ext or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")
        tmp.write(content)
        tmp.flush()
        tmp.close()

        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"rfq-extract-{new_id()}",
            system_message=RFQ_EXTRACT_SYSTEM,
        ).with_model("gemini", "gemini-2.5-pro")

        fc = FileContentWithMimeType(file_path=tmp.name, mime_type=mime)
        msg = UserMessage(
            text="Extract the RFQ data per the JSON schema in the system message. Return JSON only.",
            file_contents=[fc],
        )
        try:
            response = await chat.send_message(msg)
        except Exception as e:
            logger.exception("Gemini call failed")
            raise HTTPException(status_code=502, detail=f"AI extraction failed: {e}")

        parsed = _safe_json_load(response)
        parsed.setdefault("service_categories", [])
        parsed.setdefault("rfq_type", [])
        parsed.setdefault("line_items", [])
        parsed.setdefault("missing_information", [])
        parsed.setdefault("risk_points", [])
        parsed.setdefault("clarification_questions", [])
        return {"ok": True, "extracted": parsed, "model": "gemini-2.5-pro",
                "file_name": file.filename, "size_bytes": len(content), "extracted_at": now_iso()}
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# ---------- /ai/suggest-items ----------
class SuggestIn(BaseModel):
    service: str
    basis: str
    scope_text: Optional[str] = None
    quantity_hint: Optional[float] = None
    unit_hint: Optional[str] = None
    extra_context: Optional[Dict[str, Any]] = None


SUGGEST_SYSTEM = (
    "You are a senior estimator for INDIAN TRADE LINKS in industrial services "
    "(scaffolding, painting, rope access, insulation, roof sheeting). Given a service "
    "type, a basis (e.g. volume, area, manpower_only), and a free-text scope, return a "
    "ranked list of likely quotation line items. Use realistic Indian construction-services "
    "vocabulary and INR rate ranges. Output JSON ONLY in this shape:\n\n"
    "{\n"
    "  \"items\": [\n"
    "    { \"description\": str, \"specification\": str|null, \"unit\": str, \n"
    "      \"quantity\": number, \"rate\": number, \"hsn_sac\": str, \"gst_pct\": number, "
    "\"remarks\": str|null }\n"
    "  ],\n"
    "  \"assumptions\": [str],\n"
    "  \"flags\": [str]\n"
    "}\n\n"
    "Rules: 5-12 items. Quantity is a placeholder (1 if unknown). Rate is a realistic "
    "midpoint INR. GST defaults to 18 except for raw construction materials (often 18 or 28). "
    "Never include taxes inside rate. Never wrap output in markdown."
)


@router.post("/quotation-builder/ai/suggest-items")
async def suggest_items(payload: SuggestIn,
                        user: dict = Depends(require_permission("quotations", "write"))):
    _check_key()
    if payload.service not in SERVICES:
        raise HTTPException(status_code=400, detail=f"service must be one of {SERVICES}")
    if payload.basis not in (SERVICE_BASES.get(payload.service) or []):
        raise HTTPException(status_code=400, detail=f"basis must be one of {SERVICE_BASES.get(payload.service)}")

    # Build a priors hint from PRESET_ITEMS so Claude stays grounded
    priors = PRESET_ITEMS.get(payload.service, {}).get(payload.basis, [])
    priors_short = [{"description": p["description"], "unit": p["unit"], "hsn_sac": p["hsn_sac"], "gst_pct": p["gst_pct"]} for p in priors[:10]]

    user_text = (
        f"Service: {payload.service}\n"
        f"Basis: {payload.basis}\n"
        f"Scope: {payload.scope_text or '(not provided)'}\n"
        f"Quantity hint: {payload.quantity_hint} {payload.unit_hint or ''}\n"
        f"Existing preset items (priors): {json.dumps(priors_short)}\n"
        f"Extra context: {json.dumps(payload.extra_context or {})}\n\n"
        "Return JSON only as per schema."
    )

    from emergentintegrations.llm.chat import LlmChat, UserMessage

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"qb-suggest-{new_id()}",
        system_message=SUGGEST_SYSTEM,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    try:
        response = await chat.send_message(UserMessage(text=user_text))
    except Exception as e:
        logger.exception("Claude suggest-items failed; falling back to Gemini")
        chat2 = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"qb-suggest-fb-{new_id()}",
            system_message=SUGGEST_SYSTEM,
        ).with_model("gemini", "gemini-2.5-pro")
        try:
            response = await chat2.send_message(UserMessage(text=user_text))
        except Exception as e2:
            raise HTTPException(status_code=502, detail=f"AI suggestion failed: {e2}")

    parsed = _safe_json_load(response)
    items = parsed.get("items") or []
    # Sanitize numeric fields
    clean = []
    for it in items[:20]:
        clean.append({
            "description": str(it.get("description") or "").strip(),
            "specification": it.get("specification") or "",
            "unit": str(it.get("unit") or "Nos"),
            "quantity": float(it.get("quantity") or 1),
            "rate": float(it.get("rate") or 0),
            "hsn_sac": str(it.get("hsn_sac") or "9987"),
            "gst_pct": float(it.get("gst_pct") or 18),
            "discount_pct": 0.0,
            "remarks": it.get("remarks") or "",
        })
    return {
        "items": clean,
        "assumptions": parsed.get("assumptions") or [],
        "flags": parsed.get("flags") or [],
        "model": "claude-sonnet-4-5-20250929",
    }


# ---------- /ai/risk-review ----------
class RiskReviewIn(BaseModel):
    scope_text: str
    service: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


RISK_SYSTEM = (
    "You are reviewing a draft industrial-services quotation. Given the scope and "
    "line items, return a JSON with: `risks` (commercial/safety/scope risks), "
    "`missing_info` (questions to ask the client), and `suggested_conditions` "
    "(technical or commercial clauses worth adding). JSON only. No prose."
)


@router.post("/quotation-builder/ai/risk-review")
async def risk_review(payload: RiskReviewIn,
                      user: dict = Depends(require_permission("quotations", "write"))):
    _check_key()
    user_text = (
        f"Service: {payload.service or '(any)'}\n"
        f"Scope: {payload.scope_text}\n"
        f"Items ({len(payload.items)} total): {json.dumps(payload.items[:30])}\n\n"
        "Return JSON: {risks:[str], missing_info:[str], suggested_conditions:[str]}"
    )
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"qb-risk-{new_id()}",
        system_message=RISK_SYSTEM,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    try:
        resp = await chat.send_message(UserMessage(text=user_text))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI risk review failed: {e}")
    parsed = _safe_json_load(resp)
    return {
        "risks": parsed.get("risks") or [],
        "missing_info": parsed.get("missing_info") or [],
        "suggested_conditions": parsed.get("suggested_conditions") or [],
    }
