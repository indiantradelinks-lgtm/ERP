"""Delivery challan PDF → item lines, via Gemini (Emergent universal key).

Digital challans are read from the embedded text; scanned ones fall back to the
model's own vision on the PDF pages. The model only transcribes — matching to the
ERP Item Master happens in the router, so nothing invented can reach a transfer.
"""
import asyncio
import json
import logging
import os
import re
import tempfile
import uuid

import pymupdf
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("erp")

MODEL_PROVIDER = "gemini"
MODEL_NAME = "gemini-3.1-pro-preview"

PROMPT = """You are reading a materials DELIVERY CHALLAN / transfer note from a scaffolding company.

Return STRICT JSON only (no markdown, no commentary) shaped exactly like:
{"challan_no": "", "challan_date": "", "vehicle_no": "", "from_location": "", "to_location": "",
 "items": [{"sr": 1, "name": "", "unit": "", "quantity": 0}]}

Rules:
- Transcribe EVERY item row of the material table, in order, including rows that continue on later pages.
- "name" must be the item description exactly as printed; never translate, expand, abbreviate or merge rows.
- "quantity" is the despatched/sent quantity as a number (no commas, no unit suffix).
- Use "" for any header field that is not printed.
- Ignore totals, signatures, terms and any non-item row.
"""


def _text_of(pdf_bytes: bytes) -> str:
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)
    except Exception as e:
        logger.warning("challan text extract failed: %s", e)
        return ""


def _json_of(raw: str) -> dict:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("the reader did not return a readable item list")
    return json.loads(raw[start:end + 1])


async def read_challan(pdf_bytes: bytes) -> dict:
    """Returns {challan_no, challan_date, vehicle_no, from_location, to_location, items[], source}."""
    from emergentintegrations.llm.chat import FileContentWithMimeType, LlmChat, UserMessage
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY is not configured")

    text = _text_of(pdf_bytes)
    chat = LlmChat(api_key=key, session_id=f"challan-{uuid.uuid4().hex[:12]}",
                   system_message=PROMPT).with_model(MODEL_PROVIDER, MODEL_NAME)

    path = os.path.join(tempfile.gettempdir(), f"challan-{uuid.uuid4().hex}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    try:
        msg = UserMessage(
            text=("Read this delivery challan and return the JSON described in your instructions."
                  + (f"\n\nEmbedded text of the PDF for reference:\n{text[:20000]}" if text.strip() else
                     "\n\nThe PDF has no embedded text — read the page images.")),
            file_contents=[FileContentWithMimeType(file_path=path, mime_type="application/pdf")])
        reply = await chat.send_message(msg)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    data = _json_of(reply if isinstance(reply, str) else getattr(reply, "content", str(reply)))
    items = []
    for i, it in enumerate(data.get("items") or [], start=1):
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        qty = str(it.get("quantity") or "").replace(",", "").strip()
        try:
            qty = float(re.sub(r"[^0-9.\-]", "", qty) or 0)
        except ValueError:
            qty = 0.0
        items.append({"sr": it.get("sr") or i, "name": name,
                      "unit": str(it.get("unit") or "").strip(), "quantity": qty})
    return {
        "challan_no": str(data.get("challan_no") or "").strip(),
        "challan_date": str(data.get("challan_date") or "").strip(),
        "vehicle_no": str(data.get("vehicle_no") or "").strip(),
        "from_location": str(data.get("from_location") or "").strip(),
        "to_location": str(data.get("to_location") or "").strip(),
        "items": items,
        "source": "text" if text.strip() else "ocr",
    }


def read_challan_sync(pdf_bytes: bytes) -> dict:
    """Thread-safe wrapper — the LLM client reaches litellm synchronously, so the whole
    read must run off the API event loop (see offload.run_blocking)."""
    return asyncio.run(read_challan(pdf_bytes))
