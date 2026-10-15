"""Mirror document links between related records.

Used so Accounts automatically gets the documents attached to a Service Invoice
when the payment reaches the Payment Processing Center — no manual re-upload.
The stored object is shared; only the link row is duplicated.
"""
import logging
from typing import List, Optional

from core import db, new_id, now_iso

logger = logging.getLogger("erp")


async def mirror_files(src_type: str, src_id: str, dst_type: str, dst_id: str,
                       by: str = "System (auto-linked)",
                       only_file_id: Optional[str] = None) -> int:
    """Copy file links from one parent record to another. Idempotent by sha256."""
    if not (src_id and dst_id):
        return 0
    q = {"parent_type": src_type, "parent_id": src_id, "is_deleted": False}
    if only_file_id:
        q["id"] = only_file_id
    src_rows = await db.files.find(q, {"_id": 0}).to_list(200)
    if not src_rows:
        return 0
    existing = set(await db.files.distinct(
        "sha256", {"parent_type": dst_type, "parent_id": dst_id, "is_deleted": False}))
    new_rows: List[dict] = []
    for f in src_rows:
        if f.get("sha256") in existing:
            continue
        new_rows.append({**f, "id": new_id(), "parent_type": dst_type, "parent_id": dst_id,
                         "auto_linked": True, "linked_from": {"type": src_type, "id": src_id,
                                                              "file_id": f.get("id")},
                         "uploaded_by": f.get("uploaded_by") or by, "created_at": now_iso()})
        existing.add(f.get("sha256"))
    if new_rows:
        await db.files.insert_many(new_rows)
        logger.info("[files] auto-linked %s doc(s) %s:%s → %s:%s", len(new_rows), src_type, src_id,
                    dst_type, dst_id)
    return len(new_rows)


async def mirror_service_invoice_docs(inv_id: str, only_file_id: Optional[str] = None) -> int:
    """Service Invoice attachments → its payment-queue row (project_requests)."""
    pr = await db.project_requests.find_one(
        {"source": "service_invoice", "source_id": inv_id}, {"_id": 0, "id": 1})
    if not pr:
        return 0
    return await mirror_files("service_invoices", inv_id, "project_requests", pr["id"],
                               only_file_id=only_file_id)


async def backfill_service_invoice_docs() -> int:
    """One-time: link documents for invoices already sitting in the Accounts queue."""
    rows = await db.project_requests.find({"source": "service_invoice"},
                                          {"_id": 0, "id": 1, "source_id": 1}).to_list(5000)
    n = 0
    for r in rows:
        n += await mirror_files("service_invoices", r.get("source_id"), "project_requests", r["id"])
    if n:
        logger.info("[files] Backfilled %s service-invoice document link(s) for Accounts", n)
    return n
