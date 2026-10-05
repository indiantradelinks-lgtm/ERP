"""Head Office – Delhi as a real (internal) project master record.

Code `HEAD-OFFICE` is the sentinel already used across the ERP for non-project
(HO) bookings, so seeding the master with the same code makes every project
picker — including the id-based ones (Purchase Requisitions, Logistics Dispatch,
Store Issues) — able to book against Head Office without any other change.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core import db

HO_CODE = "HEAD-OFFICE"
HO_ID = "ho-delhi"
HO_NAME = "Head Office – Delhi"


async def ensure_head_office_project() -> bool:
    """Idempotently create the Head Office – Delhi internal project.

    Existing records are only re-stamped with the identity flags — any field an
    admin edits in the Projects master (name, site, status…) is left alone.
    """
    existing = await db.projects.find_one({"code": HO_CODE}, {"_id": 0, "id": 1})
    if existing:
        await db.projects.update_one({"id": existing["id"]},
                                     {"$set": {"is_head_office": True, "internal": True}})
        return False
    now = datetime.now(timezone.utc).isoformat()
    await db.projects.insert_one({
        "id": HO_ID,
        "code": HO_CODE,
        "name": HO_NAME,
        "client": "Indian Trade Links",
        "site": "Head Office, Delhi",
        "type": "internal",
        "status": "active",
        "is_head_office": True,
        "internal": True,
        "billing_type": "non_billable",
        "created_at": now,
        "created_by": "system",
        "updated_at": now,
    })
    return True
