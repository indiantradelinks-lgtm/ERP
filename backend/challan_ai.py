"""Delivery challan PDF → item lines, via Gemini (Emergent universal key).

Digital challans are read from the embedded text; scanned ones fall back to the
model's own vision on the PDF pages. The model only transcribes — matching to the
ERP Item Master happens in the router, so nothing invented can reach a transfer.

Both the PDF text extraction (PyMuPDF, ~30 MB) and the LLM call (litellm, ~160 MB)
run in short-lived child processes so the API process keeps a flat memory profile.
"""
import asyncio
import json
import logging
import os
import re
import sys
import tempfile
import uuid

from ai_worker import llm_send

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

_TEXT_SNIPPET = ("import sys,pymupdf;d=pymupdf.open(sys.argv[1]);"
                 "sys.stdout.write('\\n'.join(p.get_text() for p in d))")


async def _text_of(path: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", _TEXT_SNIPPET, path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            logger.warning("challan text extract failed: %s", err.decode(errors="ignore")[-300:])
            return ""
        return out.decode(errors="ignore")
    except Exception as e:  # noqa: BLE001
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
    path = os.path.join(tempfile.gettempdir(), f"challan-{uuid.uuid4().hex}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    try:
        text = await _text_of(path)
        reply = await llm_send(
            MODEL_PROVIDER, MODEL_NAME, PROMPT,
            "Read this delivery challan and return the JSON described in your instructions."
            + (f"\n\nEmbedded text of the PDF for reference:\n{text[:20000]}" if text.strip() else
               "\n\nThe PDF has no embedded text — read the page images."),
            files=[{"path": path, "mime": "application/pdf"}],
            session_id=f"challan-{uuid.uuid4().hex[:12]}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    data = _json_of(reply)
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
