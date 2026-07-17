"""One-time repair: backfill record_id on legacy quotation approvals and
re-sync quotations.approval_status from the latest approval per quotation."""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

STATUS_MAP = {
    "approved": "approved",
    "rejected": "rejected",
    "rejected_revision_required": "rejected",
    "additional_info_required": "info_required",
    "pending": "pending",
    "in_progress": "pending",
}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # 1. Backfill record_id from reference (quote_number)
    fixed_rid = 0
    async for a in db.approvals.find({"type": "quotation", "record_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "reference": 1}):
        if not a.get("reference"):
            continue
        q = await db.quotations.find_one({"quote_number": a["reference"]}, {"_id": 0, "id": 1})
        if q:
            await db.approvals.update_one({"id": a["id"]}, {"$set": {"record_id": q["id"]}})
            fixed_rid += 1

    # 2. Re-sync approval_status on each quotation from its LATEST approval
    latest: dict = {}
    async for a in db.approvals.find({"type": "quotation", "record_id": {"$nin": [None, ""]}},
                                     {"_id": 0, "record_id": 1, "status": 1, "updated_at": 1, "created_at": 1,
                                      "chain": 1, "current_step": 1, "last_reject_reason": 1}):
        key = a["record_id"]
        ts = a.get("updated_at") or a.get("created_at") or ""
        if key not in latest or ts > (latest[key].get("updated_at") or latest[key].get("created_at") or ""):
            latest[key] = a

    synced = 0
    for qid, a in latest.items():
        mapped = STATUS_MAP.get(a.get("status"))
        if not mapped:
            continue
        q = await db.quotations.find_one({"id": qid}, {"_id": 0, "approval_status": 1})
        if not q or q.get("approval_status") == mapped:
            continue
        upd = {"approval_status": mapped}
        chain = a.get("chain") or []
        cidx = a.get("current_step") or 0
        if mapped == "approved":
            upd["approval_current_step_label"] = "Approved"
            upd["approval_current_step_index"] = len(chain)
        elif mapped == "rejected":
            step = chain[cidx] if 0 <= cidx < len(chain) else None
            upd["approval_current_step_label"] = f"Rejected at {step.get('label')}" if step else "Rejected"
            if a.get("last_reject_reason"):
                upd["approval_reject_reason"] = a["last_reject_reason"]
        elif mapped == "pending":
            step = chain[cidx] if 0 <= cidx < len(chain) else None
            upd["approval_current_step_label"] = step.get("label") if step else None
            upd["approval_current_step_index"] = cidx
            upd["approval_total_steps"] = len(chain)
        await db.quotations.update_one({"id": qid}, {"$set": upd})
        synced += 1

    print(f"record_id backfilled: {fixed_rid} | quotations re-synced: {synced}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
