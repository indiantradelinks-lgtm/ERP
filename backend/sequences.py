"""Atomic per-prefix sequence generator for auto-numbering (ENQ-2026-0001 etc.)."""
from datetime import datetime, timezone

from core import db


async def next_sequence(prefix: str, *, padding: int = 4, year: int | None = None) -> str:
    """Return next sequential code for a given prefix+year using findOneAndUpdate atomicity.

    Example: prefix='ENQ', year=2026 -> 'ENQ-2026-0001', then 'ENQ-2026-0002', ...
    """
    y = year or datetime.now(timezone.utc).year
    key = f"{prefix}-{y}"
    doc = await db.sequences.find_one_and_update(
        {"_id": key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True,  # type: ignore[arg-type]
    )
    if not doc or "value" not in doc:
        doc = await db.sequences.find_one({"_id": key})
    n = int((doc or {}).get("value", 1))
    return f"{prefix}-{y}-{str(n).zfill(padding)}"


async def next_flat_sequence(prefix: str, *, padding: int = 4) -> str:
    """Year-less sequential code. Example: prefix='VND' -> 'VND-0001', 'VND-0002', ..."""
    key = f"{prefix}-FLAT"
    doc = await db.sequences.find_one_and_update(
        {"_id": key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True,  # type: ignore[arg-type]
    )
    if not doc or "value" not in doc:
        doc = await db.sequences.find_one({"_id": key})
    n = int((doc or {}).get("value", 1))
    return f"{prefix}-{str(n).zfill(padding)}"


# ────────────────────────────────────────────────────────────────────────
# Department-prefixed document numbers (Iter 47)
# Format: <DEPT>/<TYPE>/<YYYY>/<NNNN> e.g. HR/ADV/2026/0001, STO/GRN/2026/0042
# Stamped onto every NEW record in a `dept_doc_no` field — does NOT touch
# legacy numbering keys (advance_no, po_number etc. stay for compatibility).
# ────────────────────────────────────────────────────────────────────────

# DOC TYPE → (DEPT, TYPE, owner_dept_slug)
DEPT_DOC_MAP: dict[str, tuple[str, str, str]] = {
    # HR
    "advance": ("HR", "ADV", "hr"),
    "hr_letter": ("HR", "LTR", "hr"),
    "leave": ("HR", "LV", "hr"),
    "exit": ("HR", "EXIT", "hr"),
    "deployment": ("HR", "DEP", "hr"),
    "overtime": ("HR", "OT", "hr"),
    "onboarding": ("HR", "ONB", "hr"),
    # Procurement / Vendors
    "purchase_order": ("PRO", "PO", "procurement"),
    "purchase_requisition": ("PRO", "PR", "procurement"),
    "rfq": ("PRO", "RFQ", "procurement"),
    "vendor": ("PRO", "VND", "procurement"),
    # Store
    "grn": ("STO", "GRN", "store"),
    "material_outward": ("STO", "OUT", "store"),
    "stock_adjustment": ("STO", "ADJ", "store"),
    # Sales
    "enquiry": ("SAL", "ENQ", "sales"),
    "quotation": ("SAL", "QT", "sales"),
    "order": ("SAL", "SO", "sales"),
    # Accounts
    "ra_bill": ("ACC", "RAB", "accounts"),
    "vendor_invoice": ("ACC", "VIN", "accounts"),
    "credit_note": ("ACC", "CN", "accounts"),
    "debit_note": ("ACC", "DN", "accounts"),
    # Finance
    "payment_in": ("FIN", "RCT", "finance"),
    "payment_out": ("FIN", "PAY", "finance"),
    "journal_entry": ("FIN", "JV", "finance"),
    # Operations / Projects
    "project": ("OPS", "PRJ", "projects"),
    "dpr": ("OPS", "DPR", "projects"),
    "measurement": ("OPS", "MES", "projects"),
    "joint_measurement": ("OPS", "JMR", "projects"),
    # Safety
    "safety_report": ("SAF", "RPT", "safety"),
    "incident": ("SAF", "INC", "safety"),
    "ptw": ("SAF", "PTW", "safety"),
    # Logistics
    "challan": ("LOG", "CH", "logistics"),
    "vehicle_log": ("LOG", "VL", "logistics"),
    "dispatch": ("LOG", "DSP", "logistics"),
}


async def next_dept_doc(doc_type: str, *, year: int | None = None, padding: int = 4) -> dict:
    """Generate the new dept-prefixed doc number for a known doc_type.
    Returns {"dept_doc_no": "HR/ADV/2026/0001", "department": "HR", "doc_type": "ADV", "owner_dept": "hr"}.
    Raises ValueError for unknown doc_type."""
    if doc_type not in DEPT_DOC_MAP:
        raise ValueError(f"unknown doc_type for dept numbering: {doc_type}")
    dept, type_code, owner = DEPT_DOC_MAP[doc_type]
    y = year or datetime.now(timezone.utc).year
    key = f"{dept}/{type_code}/{y}"
    doc = await db.sequences.find_one_and_update(
        {"_id": key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True,  # type: ignore[arg-type]
    )
    if not doc or "value" not in doc:
        doc = await db.sequences.find_one({"_id": key})
    n = int((doc or {}).get("value", 1))
    return {
        "dept_doc_no": f"{dept}/{type_code}/{y}/{str(n).zfill(padding)}",
        "department": dept,
        "doc_type": type_code,
        "owner_dept": owner,
    }


async def stamp_dept_doc(doc: dict, doc_type: str) -> dict:
    """Convenience: mutate `doc` in-place adding `dept_doc_no` + `ownership_department`."""
    info = await next_dept_doc(doc_type)
    doc["dept_doc_no"] = info["dept_doc_no"]
    doc.setdefault("ownership_department", info["owner_dept"])
    return doc

