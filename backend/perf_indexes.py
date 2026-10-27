"""Indexes for the collections the ERP reads on every page load.

Without these the driver falls back to a full collection scan plus an in-memory
sort, which is what makes the app crawl as data grows. Creating an index that
already exists is a no-op, so this runs on every boot.
"""
import logging

from pymongo import ASCENDING, DESCENDING

from core import db

logger = logging.getLogger("erp")

INDEXES = {
    "scaf_stock": [([("item_id", ASCENDING), ("location_id", ASCENDING)], {"name": "item_loc"}),
                   ([("location_id", ASCENDING)], {}),
                   ([("item_name", ASCENDING)], {})],
    "scaf_transfers": [([("status", ASCENDING), ("created_at", DESCENDING)], {}),
                       ([("transfer_no", ASCENDING)], {}),
                       ([("from_location_id", ASCENDING)], {}),
                       ([("to_location_id", ASCENDING)], {})],
    "scaf_challans": [([("created_at", DESCENDING)], {}), ([("challan_no", ASCENDING)], {})],
    "vendor_bills": [([("status", ASCENDING), ("created_at", DESCENDING)], {}),
                     ([("vendor_id", ASCENDING)], {}),
                     ([("invoice_no", ASCENDING)], {}),
                     ([("outstanding", ASCENDING)], {}),
                     ([("bill_no", ASCENDING)], {}),
                     ([("grn_number", ASCENDING)], {})],
    "vendor_payments": [([("bill_ids", ASCENDING)], {}),
                        ([("vendor_id", ASCENDING), ("payment_date", DESCENDING)], {}),
                        ([("created_at", DESCENDING)], {})],
    "material_allocations": [([("status", ASCENDING), ("created_at", DESCENDING)], {}),
                             ([("project_id", ASCENDING)], {}),
                             ([("employee_id", ASCENDING)], {}),
                             ([("item_id", ASCENDING)], {}),
                             ([("allocation_no", ASCENDING)], {})],
    "quotations": [([("quote_number", ASCENDING)], {}), ([("enquiry_no", ASCENDING)], {})],
    "bill_requests": [([("project_id", ASCENDING), ("billing_month", ASCENDING)], {}),
                      ([("status", ASCENDING), ("created_at", DESCENDING)], {}),
                      ([("request_no", ASCENDING)], {})],
    "service_pos": [([("created_at", DESCENDING)], {}), ([("po_number", ASCENDING)], {}),
                    ([("status", ASCENDING)], {}), ([("vendor_id", ASCENDING)], {})],
    "inventory_categories": [([("code", ASCENDING)], {}), ([("name", ASCENDING)], {})],
    "project_requests": [([("created_at", DESCENDING)], {})],
    "enquiries": [([("site_id", ASCENDING)], {}), ([("quotation_id", ASCENDING)], {})],
}


async def ensure_perf_indexes() -> int:
    created = 0
    for coll, specs in INDEXES.items():
        for keys, opts in specs:
            try:
                await db[coll].create_index(keys, background=True, **opts)
                created += 1
            except Exception as e:  # a conflicting legacy index must not block boot
                logger.warning(f"[perf-index] {coll}{keys} skipped: {e}")
    return created
