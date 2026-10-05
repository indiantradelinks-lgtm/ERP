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
    """Idempotently create/refresh the Head Office – Delhi internal project."""
    existing = await db.projects.find_one({"code": HO_CODE}, {"_id": 0, "id": 1})
    doc = {
        "id": (existing or {}).get("id") or HO_ID,
        "code": HO_CODE,
        "name": HO_NAME,
        "client": "Indian Trade Links",
        "site": "Head Office, Delhi",
        "type": "internal",
        "status": "active",
        "is_head_office": True,
        "internal": True,
        "billing_type": "non_billable",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db.projects.update_one({"id": doc["id"]}, {"$set": doc})
        return False
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = "system"
    await db.projects.insert_one(doc)
    return True
