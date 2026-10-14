"""One-time cleanups for the approval-policy changes.

1. Service Procurement — all internal approval gates (Service Request chain,
   Vendor Selection approval, PO approval) were removed; only the Accounts
   payment approval remains. Anything stuck in those queues is cleared forward.
2. Project Requests — "Fuel Payment" is approved exclusively by the Manager Log
   role, so pending fuel requests are re-routed to a single Manager Log step.
"""
import logging

from core import db, now_iso

logger = logging.getLogger("erp")

FUEL_STEP = {"role": "manager_log", "label": "Manager Log", "status": "pending",
             "by": None, "at": None, "remarks": None, "exclusive": True}


def _auto(remarks: str) -> dict:
    return {"action": "auto", "by": "System (no approval required)", "role": "system",
            "at": now_iso(), "remarks": remarks}


async def clear_removed_service_approvals() -> dict:
    sr = await db.svc_requests.update_many(
        {"status": {"$in": ["submitted", "under_review"]}},
        {"$set": {"status": "approved", "approval_chain": [], "approval_step": 0,
                  "current_owner": "Logistics / Procurement", "updated_at": now_iso(),
                  "approval": _auto("Service Request approval stage removed")}})
    rfq = await db.svc_rfqs.update_many(
        {"status": "recommended"},
        {"$set": {"status": "selection_approved", "updated_at": now_iso(),
                  "selection_approval": _auto("Vendor selection approval stage removed")}})
    po = await db.svc_pos.update_many(
        {"status": "pending_approval"},
        {"$set": {"status": "approved", "updated_at": now_iso(),
                  "po_approval": _auto("PO approval stage removed")}})
    out = {"service_requests": sr.modified_count, "rfqs": rfq.modified_count, "pos": po.modified_count}
    if any(out.values()):
        logger.info("[approval-policy] Cleared removed Service Procurement gates: %s", out)
    return out


async def ensure_fuel_approver_permissions() -> bool:
    """Manager Log approves Fuel Payment requests — make sure the Role Register
    grants that role read+write on project_requests."""
    row = await db.rbac_overrides.find_one({"id": "default"}, {"_id": 0})
    if not row:
        return False
    overrides = row.get("overrides") or {}
    pr = overrides.get("project_requests")
    if not pr:
        return False
    changed = False
    for action in ("read", "write"):
        lst = list(pr.get(action) or [])
        if "manager_log" not in lst:
            pr[action] = sorted(lst + ["manager_log"])
            changed = True
    if not changed:
        return False
    overrides["project_requests"] = pr
    await db.rbac_overrides.update_one({"id": "default"},
                                       {"$set": {"overrides": overrides, "updated_at": now_iso(),
                                                 "updated_by": "System (fuel approval policy)"}})
    from rbac import set_overrides
    set_overrides(overrides)
    logger.info("[approval-policy] Granted Manager Log read+write on project_requests (fuel approvals)")
    return True


async def reroute_pending_fuel_requests() -> int:
    res = await db.project_requests.update_many(
        {"request_type": "fuel", "status": "pending_approval"},
        {"$set": {"chain": [dict(FUEL_STEP)], "current_step": 0, "updated_at": now_iso()}})
    if res.modified_count:
        logger.info("[approval-policy] Re-routed %s pending fuel request(s) to Manager Log", res.modified_count)
    return res.modified_count
