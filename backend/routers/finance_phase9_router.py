"""Finance Phase 9 — Role-Based Access, Data Security & Financial Controls.

Audit-first: rbac.py + role_catalog_router + admin_router (Role Register +
Audit Logs viewer) + approval_engine + closing_router.period_lock all
exist. This phase only fills the documented gaps:

  • Extended action verbs (submit/approve/reject/cancel/export/print/
    reopen/soft_delete/post_to_ledger) mapped to base read/write/delete
  • Sensitive-field masking config endpoint (read-only view)
  • Voucher edit/ledger-delete guards exposed as preview endpoints
  • Export / print activity log viewer
  • Role-wise dashboard tile visibility config
  • Security Center summary (single-payload dashboard)
  • Permission Matrix export (CSV)

Endpoints (mounted under /api/finance/phase9 except where noted):
  GET    /finance/phase9/extended-actions
  GET    /finance/phase9/masking-config
  GET    /finance/phase9/role-tile-visibility
  PUT    /finance/phase9/role-tile-visibility
  GET    /finance/phase9/export-logs
  POST   /finance/phase9/export-logs/log                  (called by export endpoints)
  GET    /finance/phase9/security-summary
  GET    /finance/phase9/permission-matrix.csv
  POST   /finance/phase9/check-voucher-editable           (preview gate)
  POST   /finance/phase9/check-ledger-deletable           (preview gate)
"""
from __future__ import annotations
import io
import csv
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, get_current_user
from audit import audit
from rbac import _resolved, PERMISSIONS_BASE, get_overrides_serializable
from data_masking import masking_config
from finance_guards import (
    assert_voucher_editable,
    assert_ledger_deletable,
    FROZEN_STATUSES,
    EDITABLE_STATUSES,
)

router = APIRouter(prefix="/finance/phase9", tags=["finance-phase9-security"])


# ═════════════════════════════════════════════════════════════════════════
# 1. Extended-actions registry
# ═════════════════════════════════════════════════════════════════════════
EXTENDED_ACTIONS: Dict[str, Dict[str, Any]] = {
    "view":            {"maps_to": "read",   "label": "View",            "icon": "Eye"},
    "create":          {"maps_to": "write",  "label": "Create",          "icon": "Plus"},
    "edit":            {"maps_to": "write",  "label": "Edit",            "icon": "Pencil"},
    "submit":          {"maps_to": "write",  "label": "Submit",          "icon": "Send"},
    "approve":         {"maps_to": "write",  "label": "Approve",         "icon": "CheckCircle"},
    "reject":          {"maps_to": "write",  "label": "Reject",          "icon": "XCircle"},
    "cancel":          {"maps_to": "write",  "label": "Cancel",          "icon": "Ban"},
    "export":          {"maps_to": "read",   "label": "Export",          "icon": "Download"},
    "print":           {"maps_to": "read",   "label": "Print",           "icon": "Printer"},
    "soft_delete":     {"maps_to": "delete", "label": "Soft Delete",     "icon": "Archive"},
    "delete":          {"maps_to": "delete", "label": "Delete",          "icon": "Trash2"},
    "reopen":          {"maps_to": "write",  "label": "Reopen",          "icon": "RotateCcw"},
    "post_to_ledger":  {"maps_to": "write",  "label": "Post to Ledger",  "icon": "BookOpen"},
}


@router.get("/extended-actions")
async def list_extended_actions(_: dict = Depends(get_current_user)):
    return {"actions": EXTENDED_ACTIONS}


# ═════════════════════════════════════════════════════════════════════════
# 2. Masking config (read-only)
# ═════════════════════════════════════════════════════════════════════════
@router.get("/masking-config")
async def get_masking_config(user: dict = Depends(require_permission("role_register", "read"))):
    return masking_config()


# ═════════════════════════════════════════════════════════════════════════
# 3. Role × Dashboard-tile visibility (DB-backed)
# ═════════════════════════════════════════════════════════════════════════
DEFAULT_TILE_VISIBILITY: Dict[str, List[str]] = {
    "ar_summary":         ["super_admin", "director", "general_manager", "accounts_executive", "billing_executive"],
    "ap_summary":         ["super_admin", "director", "general_manager", "accounts_executive", "purchase_officer"],
    "cash_position":      ["super_admin", "director", "general_manager", "accounts_executive"],
    "project_pnl":        ["super_admin", "director", "general_manager", "dept_head", "project_manager", "accounts_executive"],
    "payroll_summary":    ["super_admin", "director", "general_manager", "hr_executive", "accounts_executive"],
    "gst_compliance":     ["super_admin", "director", "general_manager", "accounts_executive"],
    "tds_compliance":     ["super_admin", "director", "general_manager", "accounts_executive"],
    "budget_variance":    ["super_admin", "director", "general_manager", "dept_head", "accounts_executive"],
    "alerts_feed":        ["*"],
    "approvals_pending":  ["*"],
}


@router.get("/role-tile-visibility")
async def get_tile_visibility(user: dict = Depends(require_permission("role_register", "read"))):
    row = await db.security_config.find_one({"id": "tile_visibility"}, {"_id": 0})
    vis = (row or {}).get("config") or DEFAULT_TILE_VISIBILITY
    return {"defaults": DEFAULT_TILE_VISIBILITY, "config": vis}


class TileVisibilityIn(BaseModel):
    config: Dict[str, List[str]]


@router.put("/role-tile-visibility")
async def update_tile_visibility(payload: TileVisibilityIn, request: Request,
                                  user: dict = Depends(require_permission("role_register", "write"))):
    await db.security_config.update_one(
        {"id": "tile_visibility"},
        {"$set": {"config": payload.config, "updated_at": now_iso(),
                  "updated_by": user.get("name") or user.get("email")},
         "$setOnInsert": {"id": "tile_visibility"}},
        upsert=True,
    )
    await audit(user=user, action="update_tile_visibility", resource="security_config",
                record_id="tile_visibility", after={"tiles": list(payload.config.keys())},
                ip=request.client.host if request.client else "")
    return {"ok": True, "config": payload.config}


def filter_tiles_for_role(role: str, tiles: Dict[str, Any], vis: Dict[str, List[str]]) -> Dict[str, Any]:
    if role == "super_admin":
        return tiles
    return {k: v for k, v in tiles.items()
            if "*" in vis.get(k, []) or role in vis.get(k, [])}


# ═════════════════════════════════════════════════════════════════════════
# 4. Export / Print activity log
# ═════════════════════════════════════════════════════════════════════════
class ExportLogIn(BaseModel):
    activity: str       # 'export' | 'print'
    resource: str
    format: str = "pdf"
    record_id: Optional[str] = None
    record_label: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


@router.post("/export-logs/log")
async def log_export(payload: ExportLogIn, request: Request,
                     user: dict = Depends(get_current_user)):
    doc = {
        "ts": now_iso(),
        "actor_id": user.get("id"),
        "actor_name": user.get("name") or user.get("email"),
        "actor_role": user.get("role"),
        "activity": payload.activity,
        "resource": payload.resource,
        "format": payload.format,
        "record_id": payload.record_id,
        "record_label": payload.record_label,
        "meta": payload.meta or {},
        "ip": request.client.host if request.client else "",
    }
    await db.export_print_logs.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True}


@router.get("/export-logs")
async def list_export_logs(activity: Optional[str] = None,
                           resource: Optional[str] = None,
                           limit: int = 200,
                           user: dict = Depends(require_permission("role_register", "read"))):
    q: Dict[str, Any] = {}
    if activity:
        q["activity"] = activity
    if resource:
        q["resource"] = resource
    rows = await db.export_print_logs.find(q, {"_id": 0}).sort("ts", -1).to_list(min(limit, 1000))
    return rows


# ═════════════════════════════════════════════════════════════════════════
# 5. Voucher / Ledger guard preview endpoints
# ═════════════════════════════════════════════════════════════════════════
class VoucherCheckIn(BaseModel):
    collection: str    # journal_entries / client_invoices / vendor_bills / ...
    record_id: str


@router.post("/check-voucher-editable")
async def check_voucher_editable(payload: VoucherCheckIn,
                                  user: dict = Depends(require_permission("accounting", "read"))):
    try:
        doc = await assert_voucher_editable(payload.collection, payload.record_id, user=user)
        return {"editable": True, "status": doc.get("status")}
    except HTTPException as e:
        return {"editable": False, "reason": e.detail, "status_code": e.status_code}


class LedgerCheckIn(BaseModel):
    account_id: str


@router.post("/check-ledger-deletable")
async def check_ledger_deletable(payload: LedgerCheckIn,
                                  user: dict = Depends(require_permission("accounting", "read"))):
    try:
        await assert_ledger_deletable(payload.account_id)
        return {"deletable": True}
    except HTTPException as e:
        return {"deletable": False, "reason": e.detail, "status_code": e.status_code}


# ═════════════════════════════════════════════════════════════════════════
# 6. Security Center — single-payload summary
# ═════════════════════════════════════════════════════════════════════════
@router.get("/security-summary")
async def security_summary(user: dict = Depends(require_permission("role_register", "read"))):
    # Role counts
    role_counts: Dict[str, int] = {}
    async for d in db.users.aggregate([{"$group": {"_id": "$role", "count": {"$sum": 1}}}]):
        if d.get("_id"):
            role_counts[d["_id"]] = int(d["count"])

    # Active vs inactive users
    total_users = await db.users.count_documents({})
    active_users = await db.users.count_documents({"active": {"$ne": False}})

    # Permission overrides
    overrides = get_overrides_serializable()
    override_count = sum(len(rules) for rules in overrides.values())

    # Audit volume — last 7 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    audit_7d = await db.audit_logs.count_documents({"ts": {"$gte": cutoff}})

    # Export logs — last 7 days
    exports_7d = await db.export_print_logs.count_documents({"ts": {"$gte": cutoff}})

    # Period locks
    locks_active = await db.period_locks.count_documents({"status": "locked"})

    # Pending approvals
    pending_appr = await db.approvals.count_documents({"status": {"$in": ["pending", "in_progress"]}})

    # Failed login attempts (last 24h)
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    failed_logins = await db.login_attempts.count_documents({"ts": {"$gte": cutoff_24h}, "success": False}) \
        if "login_attempts" in await db.list_collection_names() else 0

    resolved = _resolved()
    return {
        "users": {"total": total_users, "active": active_users, "by_role": role_counts},
        "permissions": {
            "resources": len(resolved),
            "overrides": override_count,
            "base_count": len(PERMISSIONS_BASE),
        },
        "audit": {"events_7d": audit_7d},
        "exports": {"events_7d": exports_7d},
        "period_locks": {"active": locks_active},
        "approvals": {"pending": pending_appr},
        "security_events": {"failed_logins_24h": failed_logins},
        "masking_resources": list(masking_config()["rules"].keys()),
        "frozen_statuses": sorted(FROZEN_STATUSES),
        "editable_statuses": sorted(EDITABLE_STATUSES),
        "extended_actions": list(EXTENDED_ACTIONS.keys()),
    }


# ═════════════════════════════════════════════════════════════════════════
# 7. Permission matrix CSV export
# ═════════════════════════════════════════════════════════════════════════
@router.get("/permission-matrix.csv")
async def export_matrix_csv(request: Request,
                             user: dict = Depends(require_permission("role_register", "read"))):
    resolved = _resolved()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Resource", "Action", "Roles Allowed"])
    for resource in sorted(resolved.keys()):
        for action in ("read", "write", "delete"):
            roles = sorted(resolved[resource].get(action, []))
            writer.writerow([resource, action, "; ".join(roles)])
    buf.seek(0)

    # Log the export
    await db.export_print_logs.insert_one({
        "ts": now_iso(),
        "actor_id": user.get("id"),
        "actor_name": user.get("name") or user.get("email"),
        "actor_role": user.get("role"),
        "activity": "export",
        "resource": "permission_matrix",
        "format": "csv",
        "ip": request.client.host if request.client else "",
    })

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=permission-matrix.csv"},
    )
