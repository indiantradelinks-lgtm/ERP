"""Admin tool — dedupe Projects that were incorrectly auto-created from
Quotations/Handovers before the bug fix.

Strategy
--------
A "canonical" project is one that came from the Enquiry→Order conversion
path. Duplicates are projects that:
  • carry `source == "auto_from_quote"` (created by the buggy quote-handover
    path), AND
  • share the same `enquiry_id` (or, failing that, `quotation_id`) with a
    canonical project that already exists.

For each duplicate we:
  1. Re-point every child record (orders, project_handovers, deployments,
     manpower allocations, DPRs, invoices, project_documents, tasks, etc.)
     from the duplicate `project_id`/`project_code` to the canonical one.
  2. Archive the duplicate doc into `projects_archive` (full snapshot + audit
     metadata).
  3. Delete the duplicate from `projects`.

Endpoints
---------
  POST /api/admin/projects/dedupe-from-quote?dry_run=true   ← default safety
  POST /api/admin/projects/dedupe-from-quote?dry_run=false  ← actually do it
  GET  /api/admin/projects/dedupe-from-quote/preview        ← read-only

Only super_admin can call.
"""
from __future__ import annotations
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from core import db, get_current_user, now_iso, new_id


router = APIRouter(prefix="/admin/projects", tags=["admin"])


CHILD_COLLECTIONS = [
    # (collection, field_name)
    ("orders", "project_id"),
    ("project_handovers", "project_id"),
    ("deployments", "project_id"),
    ("material_allocations", "project_id"),
    ("dprs", "project_id"),
    ("invoices", "project_id"),
    ("ra_bills", "project_id"),
    ("receivables", "project_id"),
    ("payment_invoices", "project_id"),
    ("project_documents", "project_id"),
    ("tasks", "project_id"),
    ("hr_manpower_requirements", "project_code"),
    ("attendance", "project_code"),
    ("overtime", "project_code"),
    ("hr_loans", "project_code"),
    ("hr_reimbursements", "project_code"),
    ("hr_store_recoveries", "project_code"),
    ("payslips", "project_code"),
    ("journal_entries", "project_id"),
]


def _require_superadmin(user: dict):
    if user.get("role") != "super_admin":
        raise HTTPException(403, "super_admin only")


async def _find_duplicates() -> List[Dict[str, Any]]:
    """Return [(canonical, duplicate)] pairs."""
    pairs = []
    cur = db.projects.find(
        {"source": "auto_from_quote",
         "$or": [{"enquiry_id": {"$ne": None}}, {"quotation_id": {"$ne": None}}]},
        {"_id": 0},
    )
    async for dup in cur:
        # Prefer canonical via order conversion: a project that is NOT
        # source=auto_from_quote and shares the same enquiry_id.
        canonical = None
        if dup.get("enquiry_id"):
            canonical = await db.projects.find_one({
                "enquiry_id": dup["enquiry_id"],
                "id": {"$ne": dup["id"]},
                "$or": [{"source": {"$ne": "auto_from_quote"}}, {"source": {"$exists": False}}],
            }, {"_id": 0})
        if not canonical and dup.get("quotation_id"):
            canonical = await db.projects.find_one({
                "quotation_id": dup["quotation_id"],
                "id": {"$ne": dup["id"]},
                "$or": [{"source": {"$ne": "auto_from_quote"}}, {"source": {"$exists": False}}],
            }, {"_id": 0})
        if not canonical:
            continue   # no duplicate — duplicate IS the only one, keep
        pairs.append({"canonical": canonical, "duplicate": dup})
    return pairs


@router.get("/dedupe-from-quote/preview")
async def preview_duplicates(user: dict = Depends(get_current_user)):
    _require_superadmin(user)
    pairs = await _find_duplicates()
    return {
        "as_of": now_iso(),
        "duplicate_count": len(pairs),
        "pairs": [{
            "canonical": {"id": p["canonical"]["id"], "code": p["canonical"].get("code"),
                          "name": p["canonical"].get("name"), "source": p["canonical"].get("source")},
            "duplicate": {"id": p["duplicate"]["id"], "code": p["duplicate"].get("code"),
                          "name": p["duplicate"].get("name"), "source": p["duplicate"].get("source"),
                          "quotation_id": p["duplicate"].get("quotation_id"),
                          "enquiry_id": p["duplicate"].get("enquiry_id")},
        } for p in pairs],
    }


@router.post("/dedupe-from-quote")
async def dedupe_projects(
    dry_run: bool = Query(True, description="Set to false to actually execute"),
    user: dict = Depends(get_current_user),
):
    _require_superadmin(user)
    pairs = await _find_duplicates()
    cols = await db.list_collection_names()
    actions: List[Dict[str, Any]] = []

    for pair in pairs:
        dup = pair["duplicate"]
        canon = pair["canonical"]
        repointed: Dict[str, int] = {}

        for coll, field in CHILD_COLLECTIONS:
            if coll not in cols:
                continue
            # Build a match using whatever identifier the field expects
            if field == "project_code":
                key, val_dup, val_canon = "project_code", dup.get("code"), canon.get("code")
            else:
                key, val_dup, val_canon = field, dup.get("id"), canon.get("id")
            if not val_dup or not val_canon:
                continue
            n = await db[coll].count_documents({key: val_dup})
            if n == 0:
                continue
            repointed[coll] = n
            if not dry_run:
                await db[coll].update_many({key: val_dup}, {"$set": {
                    key: val_canon,
                    "deduped_from": val_dup,
                    "deduped_at": now_iso(),
                    "deduped_by": user.get("name") or user.get("email"),
                }})

        action = {
            "duplicate_id": dup["id"], "duplicate_code": dup.get("code"),
            "canonical_id": canon["id"], "canonical_code": canon.get("code"),
            "child_repoints": repointed,
            "total_repointed": sum(repointed.values()),
        }
        if not dry_run:
            # Snapshot the duplicate into projects_archive (audit-grade backup)
            await db.projects_archive.insert_one({
                "id": new_id(),
                "archived_at": now_iso(),
                "archived_by_id": user.get("id"),
                "archived_by_name": user.get("name") or user.get("email"),
                "reason": "auto_from_quote dedupe — Phase-bugfix",
                "original_project": {**dup, "deduped_to": canon["id"]},
                "child_repoints": repointed,
            })
            await db.projects.delete_one({"id": dup["id"]})
            action["archived"] = True
            action["deleted"] = True
        actions.append(action)

    return {
        "as_of": now_iso(),
        "dry_run": dry_run,
        "duplicate_count": len(pairs),
        "actions": actions,
        "summary": {
            "total_duplicates_found": len(pairs),
            "total_child_records_repointed": sum(a.get("total_repointed", 0) for a in actions),
            "deleted": 0 if dry_run else len(pairs),
            "next_step": ("Re-run with dry_run=false to apply" if dry_run
                          else "Done. Backups in `projects_archive` collection."),
        },
    }
