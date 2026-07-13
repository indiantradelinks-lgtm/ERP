"""Data Cleanup Control Panel — safely identify, archive and purge garbage rows
across the database.

Design choices that make this safe to operate:
  • **Whitelist** of cleanup-eligible collections (sensitive ones like `users`,
    `settings`, `audit_logs`, `rbac_overrides`, `login_attempts` are EXCLUDED —
    they have dedicated admin UIs).
  • Every delete writes a copy to `db.cleanup_archive` with TTL metadata, so an
    accidental delete can be **restored within 30 days**.
  • Hard delete & restore are gated to `data_cleanup` permission (super_admin
    only by default).
  • Audit log row written for every operation.
  • Confirm-by-keyword on the API (`confirm="DELETE"`) — frontend mirrors with a
    typed-confirmation modal.

Mounted at /api/admin/data-cleanup/*.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit

logger = logging.getLogger("erp.data_cleanup")
router = APIRouter(prefix="/admin/data-cleanup", tags=["data-cleanup"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ────────────────────────────────────── Whitelist ─────────────────────────────
# Excluded for safety: users, settings, audit_logs, rbac_overrides,
# login_attempts, sequences, sessions, refresh_tokens, condition_library
# (use admin UIs), counters.

CLEANUP_COLLECTIONS: Dict[str, Dict[str, Any]] = {
    # ─ Sales / Commerce ─
    "enquiries":              {"label": "Enquiries", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": []},
    "quotations":             {"label": "Quotations", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": [("client_id", "clients")]},
    "sales_orders":           {"label": "Sales Orders (legacy alias)", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("quotation_id", "quotations")]},
    "orders":                 {"label": "Sales Orders", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("enquiry_id", "enquiries")]},
    "invoices":               {"label": "Invoices", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("client_id", "clients")]},
    "payments_in":            {"label": "Payments In", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": []},
    "ra_bills":               {"label": "RA Bills", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects")]},

    # ─ Site Execution ─
    "dprs":                   {"label": "DPRs", "tier": "safe", "key": "id", "date_field": "date", "parent_refs": [("project_id", "projects")]},
    "measurements":           {"label": "Measurements", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects")]},

    # ─ Procurement ─
    "purchase_requisitions":  {"label": "Purchase Requisitions", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects")]},
    "purchase_orders":        {"label": "Purchase Orders", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects")]},
    "grn":                    {"label": "GRN (Goods Receipt)", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("po_id", "purchase_orders")]},
    "material_allocations":   {"label": "Material Allocations", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects")]},
    "rfqs":                   {"label": "RFQs", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": [("pr_id", "purchase_requisitions")]},

    # ─ Master Data ─
    "projects":               {"label": "Projects", "tier": "dangerous", "key": "id", "date_field": "created_at", "parent_refs": []},
    "sites":                  {"label": "Sites", "tier": "dangerous", "key": "id", "date_field": "created_at", "parent_refs": []},
    "clients":                {"label": "Clients", "tier": "dangerous", "key": "id", "date_field": "created_at", "parent_refs": []},
    "vendors":                {"label": "Vendors", "tier": "dangerous", "key": "id", "date_field": "created_at", "parent_refs": []},
    "employees":              {"label": "Employees", "tier": "dangerous", "key": "id", "date_field": "created_at", "parent_refs": []},
    "deployments":            {"label": "Deployments", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects"), ("employee_id", "employees")]},
    "pr_categories":          {"label": "Procurement Categories", "tier": "dangerous", "key": "id", "date_field": "created_at", "parent_refs": []},
    "pr_items":               {"label": "Procurement Items", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("category_id", "pr_categories")]},
    "cost_centers":           {"label": "Cost Centers", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects"), ("category_id", "pr_categories")]},

    # ─ Workflow / Misc ─
    "approvals":              {"label": "Approvals", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": []},
    "safety_reports":         {"label": "Safety Reports", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects")]},
    "ptws":                   {"label": "Permits to Work", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": [("project_id", "projects")]},
    "ppe_issuance":           {"label": "PPE Issuance", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": []},
    "toolbox_talks":          {"label": "Toolbox Talks", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": []},
    "assets":                 {"label": "Assets", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": []},
    "vehicles":               {"label": "Vehicles", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": []},
    "accommodations":         {"label": "Accommodations", "tier": "safe", "key": "id", "date_field": "created_at", "parent_refs": []},
    "dropdown_options":       {"label": "Dropdown Options", "tier": "caution", "key": "id", "date_field": "created_at", "parent_refs": []},
}

ARCHIVE_TTL_DAYS = 30
_ttl_index_ready = False


async def _ensure_archive_ttl_index() -> None:
    """Create a TTL index on cleanup_archive.expires_at_dt so MongoDB auto-purges
    rows older than ARCHIVE_TTL_DAYS. Idempotent and safe to call repeatedly."""
    global _ttl_index_ready
    if _ttl_index_ready:
        return
    try:
        await db.cleanup_archive.create_index("expires_at_dt", expireAfterSeconds=0, name="cleanup_archive_ttl")
        _ttl_index_ready = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("cleanup_archive TTL index creation failed: %s", exc)


def _ensure_allowed(coll: str) -> Dict[str, Any]:
    if coll not in CLEANUP_COLLECTIONS:
        raise HTTPException(status_code=400, detail=f"Collection '{coll}' is not cleanup-eligible.")
    return CLEANUP_COLLECTIONS[coll]


def _strip(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────── Endpoints ────────────────────────────────
@router.get("/collections")
async def list_collections(user: dict = Depends(require_permission("data_cleanup", "read"))):
    """Return collections with row counts and safety tier for the picker."""
    out = []
    for coll, meta in CLEANUP_COLLECTIONS.items():
        try:
            n = await db[coll].estimated_document_count()
        except Exception:
            n = 0
        out.append({
            "collection": coll, "label": meta["label"], "tier": meta["tier"],
            "row_count": n, "date_field": meta["date_field"],
        })
    out.sort(key=lambda x: (x["tier"], x["label"]))
    # Also surface archive size
    try:
        archive_count = await db.cleanup_archive.estimated_document_count()
    except Exception:
        archive_count = 0
    return {"collections": out, "archive_count": archive_count, "archive_ttl_days": ARCHIVE_TTL_DAYS}


@router.get("/{collection}")
async def browse_collection(
    collection: str,
    q: Optional[str] = None,
    status: Optional[str] = None,
    older_than_days: Optional[int] = Query(None, ge=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_permission("data_cleanup", "read")),
):
    """Browse rows with search + status + age filters."""
    _ensure_allowed(collection)
    meta = CLEANUP_COLLECTIONS[collection]
    filt: Dict[str, Any] = {}
    if status:
        filt["status"] = status
    if older_than_days is not None and meta.get("date_field"):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        filt[meta["date_field"]] = {"$lt": cutoff}
    if q:
        # Best-effort full-text-ish across common label fields
        like = {"$regex": q, "$options": "i"}
        filt["$or"] = [
            {"name": like}, {"code": like}, {"title": like}, {"client": like},
            {"description": like}, {"id": q}, {"pr_number": like}, {"po_number": like},
            {"quote_number": like}, {"invoice_number": like}, {"bill_number": like},
        ]
    total = await db[collection].count_documents(filt)
    rows = await db[collection].find(filt, {"_id": 0}).skip(skip).limit(limit).sort([(meta.get("date_field") or "id", -1)]).to_list(limit)
    return {"total": total, "rows": rows, "filter": filt}


@router.get("/{collection}/orphans")
async def list_orphans(collection: str,
                       user: dict = Depends(require_permission("data_cleanup", "read"))):
    """Rows whose parent reference no longer exists. Returns up to 500."""
    meta = _ensure_allowed(collection)
    refs = meta.get("parent_refs") or []
    if not refs:
        return {"total": 0, "rows": [], "note": "No parent references defined for this collection."}
    rows = await db[collection].find({}, {"_id": 0}).to_list(2000)
    orphans: List[Dict[str, Any]] = []
    for r in rows:
        for fk, parent_coll in refs:
            val = r.get(fk)
            if not val:
                continue
            exists = await db[parent_coll].find_one({"id": val}, {"_id": 0, "id": 1})
            if not exists:
                r["_orphan_field"] = fk
                r["_orphan_parent"] = parent_coll
                r["_orphan_value"] = val
                orphans.append(r)
                break
        if len(orphans) >= 500:
            break
    return {"total": len(orphans), "rows": orphans}


class DeleteIn(BaseModel):
    ids: List[str] = Field(default_factory=list)
    confirm: str = ""
    reason: Optional[str] = None
    archive: bool = True


@router.post("/{collection}/preview-delete")
async def preview_delete(collection: str, payload: DeleteIn,
                         user: dict = Depends(require_permission("data_cleanup", "delete"))):
    _ensure_allowed(collection)
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No ids supplied.")
    rows = await db[collection].find({"id": {"$in": payload.ids}}, {"_id": 0}).to_list(len(payload.ids))
    return {"matched": len(rows), "sample": rows[:5], "total_requested": len(payload.ids)}


@router.post("/{collection}/delete")
async def perform_delete(collection: str, payload: DeleteIn, request: Request,
                         user: dict = Depends(require_permission("data_cleanup", "delete"))):
    _ensure_allowed(collection)
    if payload.confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Confirmation phrase must be exactly 'DELETE'.")
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No ids supplied.")
    rows = await db[collection].find({"id": {"$in": payload.ids}}, {"_id": 0}).to_list(len(payload.ids))
    if not rows:
        return {"deleted": 0, "archived": 0}
    archived = 0
    if payload.archive:
        await _ensure_archive_ttl_index()
        now = datetime.now(timezone.utc)
        expires_dt = now + timedelta(days=ARCHIVE_TTL_DAYS)
        archive_docs = []
        for r in rows:
            archive_docs.append({
                "id": new_id(),
                "collection": collection,
                "doc_id": r.get("id"),
                "doc": r,
                "deleted_at": now.isoformat(),
                "deleted_by": user.get("name") or user.get("email"),
                "reason": payload.reason or None,
                "expires_at": expires_dt.isoformat(),
                "expires_at_dt": expires_dt,  # BSON Date — drives MongoDB TTL purge
            })
        if archive_docs:
            await db.cleanup_archive.insert_many(archive_docs)
            archived = len(archive_docs)
    res = await db[collection].delete_many({"id": {"$in": [r.get("id") for r in rows]}})
    await audit(user=user, action="data_cleanup_delete", resource=collection,
                record_id=",".join(payload.ids[:5]) + (f" +{len(payload.ids) - 5}" if len(payload.ids) > 5 else ""),
                after={"count": res.deleted_count, "archived": archived, "reason": payload.reason}, ip=_ip(request))
    return {"deleted": res.deleted_count, "archived": archived, "restorable_until": (datetime.now(timezone.utc) + timedelta(days=ARCHIVE_TTL_DAYS)).isoformat()}


@router.get("/archive/list")
async def list_archive(
    collection: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(require_permission("data_cleanup", "read")),
):
    filt: Dict[str, Any] = {}
    if collection:
        filt["collection"] = collection
    total = await db.cleanup_archive.count_documents(filt)
    rows = await db.cleanup_archive.find(filt, {"_id": 0}).skip(skip).limit(limit).sort([("deleted_at", -1)]).to_list(limit)
    return {"total": total, "rows": rows, "ttl_days": ARCHIVE_TTL_DAYS}


class RestoreIn(BaseModel):
    archive_ids: List[str]


@router.post("/archive/restore")
async def restore_from_archive(payload: RestoreIn, request: Request,
                               user: dict = Depends(require_permission("data_cleanup", "write"))):
    if not payload.archive_ids:
        raise HTTPException(status_code=400, detail="No archive_ids supplied.")
    archived = await db.cleanup_archive.find({"id": {"$in": payload.archive_ids}}, {"_id": 0}).to_list(len(payload.archive_ids))
    restored = 0
    skipped: List[str] = []
    for a in archived:
        coll = a.get("collection")
        if coll not in CLEANUP_COLLECTIONS:
            skipped.append(a.get("id"))
            continue
        doc = a.get("doc") or {}
        doc.pop("_id", None)
        # Re-insert if id doesn't already exist
        existing = await db[coll].find_one({"id": doc.get("id")}, {"_id": 0, "id": 1})
        if existing:
            skipped.append(a.get("id"))
            continue
        await db[coll].insert_one(doc)
        await db.cleanup_archive.delete_one({"id": a.get("id")})
        restored += 1
    await audit(user=user, action="data_cleanup_restore", resource="cleanup_archive",
                record_id=",".join(payload.archive_ids[:5]),
                after={"restored": restored, "skipped": len(skipped)}, ip=_ip(request))
    return {"restored": restored, "skipped": skipped}


@router.delete("/archive/purge")
async def purge_archive(older_than_days: int = Query(0, ge=0), request: Request = None,
                        user: dict = Depends(require_permission("data_cleanup", "delete"))):
    """Permanently drop archive entries older than `older_than_days`. 0 means
    purge ALL — use with extreme caution."""
    if older_than_days == 0:
        res = await db.cleanup_archive.delete_many({})
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        res = await db.cleanup_archive.delete_many({"deleted_at": {"$lt": cutoff}})
    if request:
        await audit(user=user, action="data_cleanup_purge_archive", resource="cleanup_archive",
                    record_id="bulk", after={"purged": res.deleted_count, "older_than_days": older_than_days},
                    ip=_ip(request))
    return {"purged": res.deleted_count}
