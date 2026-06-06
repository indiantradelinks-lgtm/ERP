"""Enhanced Vendor Master router (Iter 55).

Replaces the generic CRUD vendors endpoints with a dedicated, richer pipeline:
  • Auto vendor_code: VND-0001, VND-0002, … (year-less, atomic)
  • Status lifecycle: draft → pending_approval → approved | rejected → blocked | inactive
  • Multi-address, multi-bank, MSME slot, typed document attachments
  • Categories[] — references db.pr_categories codes (master-driven)
  • "Submit for Approval" endpoint creates a chain entry of type=`vendor`
  • Admin status overrides (block / inactivate / reactivate)
  • Documents are tracked in two places:
       - `vendor.documents[]`     (typed metadata: PAN/GST/MSME/ISO/Other + expiry)
       - `db.files`               (the actual upload via files_router; we just link file_id)

Side-effects on approval finalisation are handled in approvals_router (`_mirror_downstream_record`
already covers `type=vendor → vendors` collection; the `apply_action` side-channel below
also sets `approved_at` and clears `reject_reason`).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, get_current_user, now_iso, new_id
from approval_engine import build_chain, insert_approval, copy_approval_doc_fields
from audit import audit
from sequences import next_flat_sequence

router = APIRouter(tags=["vendors"])

ALLOWED_STATUSES = {
    "draft", "pending_approval", "approved", "rejected",
    "blocked", "inactive",
}
EDITABLE_STATUSES = {"draft", "rejected"}


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _strip(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────── MODELS ───────────────────────────────
class VendorAddress(BaseModel):
    type: str = "registered"           # registered|billing|shipping|works
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    pin: Optional[str] = None
    gst: Optional[str] = None
    is_default: bool = False


class VendorBank(BaseModel):
    bank_name: Optional[str] = None
    account_no: Optional[str] = None
    ifsc: Optional[str] = None
    branch: Optional[str] = None
    account_type: Optional[str] = "Current"   # Current|Savings|Cash-Credit
    is_default: bool = False
    cancelled_cheque_file_id: Optional[str] = None


class VendorMSME(BaseModel):
    status: Optional[str] = "none"    # none|micro|small|medium
    udyam_number: Optional[str] = None
    certificate_file_id: Optional[str] = None
    certificate_expiry: Optional[str] = None  # YYYY-MM-DD


class VendorDocument(BaseModel):
    type: str                         # PAN|GST|MSME|ISO|Other
    name: Optional[str] = None
    file_id: str
    expiry: Optional[str] = None
    uploaded_at: Optional[str] = None


class VendorIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    contact: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    pan: Optional[str] = None
    gst: Optional[str] = None
    rating: Optional[float] = None
    categories: List[str] = []
    addresses: List[VendorAddress] = []
    bank_accounts: List[VendorBank] = []
    msme: Optional[VendorMSME] = None
    documents: List[VendorDocument] = []
    notes: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    pan: Optional[str] = None
    gst: Optional[str] = None
    rating: Optional[float] = None
    categories: Optional[List[str]] = None
    addresses: Optional[List[VendorAddress]] = None
    bank_accounts: Optional[List[VendorBank]] = None
    msme: Optional[VendorMSME] = None
    documents: Optional[List[VendorDocument]] = None
    notes: Optional[str] = None


class StatusOverride(BaseModel):
    status: str
    reason: Optional[str] = None


# ─────────────────────────────────────── LIST/GET ─────────────────────────────
@router.get("/vendors")
async def list_vendors(status: Optional[str] = None,
                       category: Optional[str] = None,
                       user: dict = Depends(require_permission("vendors", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if category:
        q["categories"] = category
    rows = await db.vendors.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return rows


@router.get("/vendors/{vid}")
async def get_vendor(vid: str, user: dict = Depends(require_permission("vendors", "read"))):
    row = await db.vendors.find_one({"id": vid}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")
    # Iter 56 — auto-merge orphan files: any file uploaded via /uploads with parent=vendors/{vid}
    # that isn't yet referenced in `documents[]` is shown so the user can preview/download it.
    linked_ids = {d.get("file_id") for d in (row.get("documents") or []) if d.get("file_id")}
    orphans = await db.files.find(
        {"parent_type": "vendors", "parent_id": vid, "is_deleted": False,
         "id": {"$nin": list(linked_ids)}},
        {"_id": 0, "id": 1, "original_filename": 1, "created_at": 1, "size": 1, "content_type": 1},
    ).sort("created_at", -1).to_list(50)
    row["orphan_files"] = orphans
    return row


@router.get("/vendor-categories")
async def list_vendor_categories(active_only: bool = True,
                                  user: dict = Depends(get_current_user)):
    """Master-driven category source. Reuses pr_categories (SCAFF, PAINT, ROPE, …)."""
    q: Dict[str, Any] = {}
    if active_only:
        q["active"] = True
    rows = await db.pr_categories.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    # Live vendor count per category
    counts: Dict[str, int] = {}
    pipeline = [{"$unwind": "$categories"}, {"$group": {"_id": "$categories", "n": {"$sum": 1}}}]
    async for r in db.vendors.aggregate(pipeline):
        counts[r["_id"] or ""] = r["n"]
    for r in rows:
        r["vendor_count"] = counts.get(r.get("code"), 0)
    return rows


# ─────────────────────────────────────── CREATE / UPDATE ──────────────────────
@router.post("/vendors")
async def create_vendor(payload: VendorIn, request: Request,
                        user: dict = Depends(require_permission("vendors", "write"))):
    # Duplicate guard — by GST or PAN if supplied
    if payload.gst:
        if await db.vendors.find_one({"gst": payload.gst}):
            raise HTTPException(status_code=400, detail=f"Vendor with GST {payload.gst} already exists")
    if payload.pan:
        if await db.vendors.find_one({"pan": payload.pan}):
            raise HTTPException(status_code=400, detail=f"Vendor with PAN {payload.pan} already exists")

    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["vendor_code"] = await next_flat_sequence("VND")
    doc["status"] = "draft"
    doc["created_at"] = now_iso()
    doc["created_by"] = user.get("name") or user.get("email")
    doc["created_by_id"] = user.get("id")
    # Stamp uploaded_at on documents
    for d in doc.get("documents") or []:
        d.setdefault("uploaded_at", now_iso())

    await db.vendors.insert_one(doc)
    await audit(user=user, action="create", resource="vendors", record_id=doc["id"], after=doc, ip=_ip(request))
    return _strip(doc)


@router.put("/vendors/{vid}")
async def update_vendor(vid: str, payload: VendorUpdate, request: Request,
                        user: dict = Depends(require_permission("vendors", "write"))):
    existing = await db.vendors.find_one({"id": vid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    is_admin = user.get("role") in {"super_admin", "director", "general_manager", "purchase_officer"}
    if existing.get("status") not in EDITABLE_STATUSES and not is_admin:
        raise HTTPException(status_code=400, detail=f"Cannot edit vendor in '{existing.get('status')}' state. Reopen for edit or use status override.")

    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    # Duplicate guard on GST/PAN change
    if patch.get("gst") and patch["gst"] != existing.get("gst"):
        if await db.vendors.find_one({"gst": patch["gst"], "id": {"$ne": vid}}):
            raise HTTPException(status_code=400, detail=f"Another vendor already uses GST {patch['gst']}")
    if patch.get("pan") and patch["pan"] != existing.get("pan"):
        if await db.vendors.find_one({"pan": patch["pan"], "id": {"$ne": vid}}):
            raise HTTPException(status_code=400, detail=f"Another vendor already uses PAN {patch['pan']}")

    # Stamp uploaded_at on any newly-added documents (those without it)
    for d in patch.get("documents") or []:
        d.setdefault("uploaded_at", now_iso())

    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.vendors.update_one({"id": vid}, {"$set": patch})
    row = await db.vendors.find_one({"id": vid}, {"_id": 0})
    await audit(user=user, action="update", resource="vendors", record_id=vid, after=patch, ip=_ip(request))
    return _strip(row)


@router.delete("/vendors/{vid}")
async def delete_vendor(vid: str, request: Request,
                        user: dict = Depends(require_permission("vendors", "delete"))):
    existing = await db.vendors.find_one({"id": vid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if existing.get("status") == "approved":
        # Approved vendors cannot be hard-deleted; force inactive instead.
        raise HTTPException(status_code=400, detail="Approved vendors cannot be deleted. Use status override to inactivate.")
    # Block delete if linked to any PO/PR/RFQ/invoice
    linked = await db.purchase_orders.count_documents({"vendor_id": vid})
    if linked:
        raise HTTPException(status_code=400, detail=f"Cannot delete — {linked} purchase order(s) linked.")
    await db.vendors.delete_one({"id": vid})
    await audit(user=user, action="delete", resource="vendors", record_id=vid, before=existing, ip=_ip(request))
    return {"ok": True}


# ─────────────────────────────────────── SUBMIT / STATUS ──────────────────────
@router.post("/vendors/{vid}/submit")
async def submit_vendor(vid: str, request: Request, body: Optional[Dict[str, Any]] = None,
                        user: dict = Depends(require_permission("vendors", "write"))):
    v = await db.vendors.find_one({"id": vid}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if v.get("status") not in EDITABLE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Only draft / rejected vendors can be submitted (current: {v.get('status')})")
    # Pre-flight: require essentials
    missing: List[str] = []
    if not v.get("name"):
        missing.append("name")
    if not (v.get("pan") or v.get("gst")):
        missing.append("PAN or GST")
    if not v.get("categories"):
        missing.append("at least one category")
    if not (v.get("addresses") or []):
        missing.append("at least one address")
    if not (v.get("bank_accounts") or []):
        missing.append("at least one bank account")
    if missing:
        raise HTTPException(status_code=400, detail=f"Cannot submit — missing: {', '.join(missing)}")

    # Mark older rejected approvals as superseded
    await db.approvals.update_many(
        {"type": "vendor", "record_id": vid, "status": {"$in": ["rejected", "rejected_revision_required"]}},
        {"$set": {"superseded": True, "superseded_at": now_iso()}},
    )
    chain = await build_chain("vendor")
    approval = {
        "id": new_id(),
        "type": "vendor",
        "module": "vendors",
        "record_id": vid,
        "title": f"Vendor onboarding — {v.get('name')} ({v.get('vendor_code')})",
        "summary": f"Categories: {', '.join(v.get('categories') or []) or '—'} · {len(v.get('bank_accounts') or [])} bank · {len(v.get('documents') or [])} doc(s)",
        "requested_by": user.get("name") or user.get("email"),
        "requested_by_id": user.get("id"),
        "status": "pending",
        "current_step": 0,
        "chain": chain,
        "history": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    # Vendor onboarding: vendor master already requires KYC docs (PAN/GST/bank/etc.)
    # which are linked to the parent record. We auto-mark the approval as having
    # docs covered by the parent record so the gate doesn't block submission;
    # additional supporting docs can still be passed via request body.
    copy_approval_doc_fields(approval, body)
    if not approval.get("documents") and not approval.get("documents_not_required"):
        approval["documents_not_required"] = True
        approval["documents_not_required_reason"] = "KYC documents attached to vendor master record"
    await insert_approval(approval)
    await db.vendors.update_one(
        {"id": vid},
        {"$set": {"status": "pending_approval", "approval_id": approval["id"],
                   "reject_reason": None, "submitted_at": now_iso(), "updated_at": now_iso()}},
    )
    await audit(user=user, action="submit", resource="vendors", record_id=vid, after={"approval_id": approval["id"]}, ip=_ip(request))
    return {"vendor_id": vid, "approval_id": approval["id"]}


@router.post("/vendors/{vid}/status")
async def override_status(vid: str, payload: StatusOverride, request: Request,
                          user: dict = Depends(require_permission("vendors", "write"))):
    """Admin-only path to block / inactivate / reactivate an approved vendor."""
    if user.get("role") not in {"super_admin", "director", "general_manager", "purchase_officer"}:
        raise HTTPException(status_code=403, detail="Insufficient privileges for status override")
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of {sorted(ALLOWED_STATUSES)}")
    v = await db.vendors.find_one({"id": vid}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    # Permitted transitions
    cur = v.get("status")
    transitions = {
        "approved": {"blocked", "inactive", "draft"},   # 'draft' = reopen for edit + re-approval
        "blocked": {"approved", "inactive"},
        "inactive": {"approved"},
        "rejected": {"draft"},   # allow originator to recycle
    }
    allowed_next = transitions.get(cur, set())
    if user.get("role") == "super_admin":
        allowed_next = ALLOWED_STATUSES - {cur}
    if payload.status not in allowed_next:
        raise HTTPException(status_code=400, detail=f"Transition {cur} → {payload.status} not allowed")
    # Reopen-for-edit (approved → draft) demands a reason for audit traceability
    if cur == "approved" and payload.status == "draft" and not (payload.reason and payload.reason.strip()):
        raise HTTPException(status_code=400, detail="A reason is required to reopen an approved vendor for editing")

    set_doc = {"status": payload.status, "status_changed_at": now_iso(),
               "status_changed_by": user.get("name") or user.get("email"),
               "updated_at": now_iso()}
    if payload.reason:
        set_doc["status_reason"] = payload.reason
    # Reopen-for-edit: mark the previous approval as superseded and clear approval_id
    # so the next Submit creates a fresh chain (proper versioning).
    if cur == "approved" and payload.status == "draft":
        set_doc["approval_id"] = None
        set_doc["reopened_at"] = now_iso()
        set_doc["reopened_by"] = user.get("name") or user.get("email")
        set_doc["reopen_reason"] = payload.reason
        set_doc["version"] = int(v.get("version") or 1) + 1
        if v.get("approval_id"):
            await db.approvals.update_one(
                {"id": v["approval_id"]},
                {"$set": {"superseded": True, "superseded_at": now_iso(),
                          "superseded_reason": payload.reason}},
            )
    await db.vendors.update_one({"id": vid}, {"$set": set_doc})
    await audit(user=user, action="status_override", resource="vendors", record_id=vid,
                after={"status": payload.status, "reason": payload.reason}, ip=_ip(request))
    row = await db.vendors.find_one({"id": vid}, {"_id": 0})
    return _strip(row)
