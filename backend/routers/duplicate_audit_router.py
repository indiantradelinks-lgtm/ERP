"""Duplicate Audit Router — read-only detection across high-risk collections.

Returns a report of duplicate records grouped by their natural business key.
Admin reviews the report before deciding on cleanup (no destructive ops here).

Mount: /api/admin/duplicates
"""
from __future__ import annotations
from typing import Dict, List, Any

from fastapi import APIRouter, Depends

from core import db, require_permission

router = APIRouter(prefix="/admin/duplicates", tags=["duplicate-audit"])


# Collection → list of fields that together form the "natural key" we expect
# to be unique. Records sharing a key are flagged as duplicates.
DUPLICATE_RULES: Dict[str, List[str]] = {
    "employees":        ["employee_id"],
    "vendors":          ["gstin"],
    "clients":          ["gstin"],
    "items":            ["code"],
    "chart_of_accounts": ["code"],
    "journal_entries":  ["je_number"],
    "client_invoices":  ["invoice_number"],
    "vendor_bills":     ["bill_number", "vendor_id"],
    "vendor_invoices":  ["invoice_number", "vendor_id"],
    "purchase_orders":  ["po_number"],
    "purchase_requisitions": ["pr_number"],
    "ra_bills":         ["ra_number"],
    "dprs":             ["dpr_number"],
    "projects":         ["code"],
    "project_handovers": ["handover_no"],
    "approvals":        ["source_id", "type"],
}


async def _detect(coll: str, fields: List[str]) -> Dict[str, Any]:
    """Aggregate duplicates for one collection."""
    # Build $group _id from non-empty fields
    group_id = {f: f"${f}" for f in fields}
    match = {f: {"$nin": [None, ""]} for f in fields}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": group_id, "count": {"$sum": 1},
                     "ids": {"$push": "$id"}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 100},
    ]
    samples = []
    total_dups = 0
    async for row in db[coll].aggregate(pipeline):
        total_dups += row["count"] - 1  # one of each is the "good" copy
        samples.append({
            "key": row["_id"],
            "count": row["count"],
            "ids": row["ids"][:10],
        })
    return {
        "collection": coll,
        "fields": fields,
        "duplicate_groups": len(samples),
        "redundant_rows": total_dups,
        "samples": samples[:25],
    }


@router.get("/scan")
async def scan_all(user: dict = Depends(require_permission("role_register", "read"))):
    """Run duplicate detection across all configured collections."""
    out: List[Dict[str, Any]] = []
    grand_redundant = 0
    grand_groups = 0
    for coll, fields in DUPLICATE_RULES.items():
        try:
            r = await _detect(coll, fields)
        except Exception as e:  # noqa: BLE001
            r = {"collection": coll, "fields": fields, "error": str(e)[:120]}
        out.append(r)
        grand_redundant += r.get("redundant_rows", 0) or 0
        grand_groups += r.get("duplicate_groups", 0) or 0
    return {
        "summary": {
            "collections_scanned": len(DUPLICATE_RULES),
            "duplicate_groups_total": grand_groups,
            "redundant_rows_total": grand_redundant,
        },
        "rules": DUPLICATE_RULES,
        "results": out,
    }


@router.get("/scan/{collection}")
async def scan_one(collection: str,
                    user: dict = Depends(require_permission("role_register", "read"))):
    if collection not in DUPLICATE_RULES:
        return {"collection": collection, "error": "Not a known collection for duplicate audit"}
    return await _detect(collection, DUPLICATE_RULES[collection])
