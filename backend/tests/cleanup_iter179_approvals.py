"""Find/delete approvals whose advance_ids no longer exist (iter179 leftovers)."""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    aps = await db.approvals.find({"type": "employee_advance",
                                   "advance_ids": {"$exists": True}}).to_list(1000)
    dangling = []
    for a in aps:
        ids = a.get("advance_ids") or []
        if not ids:
            continue
        cnt = await db.employee_advances.count_documents({"id": {"$in": ids}})
        if cnt == 0:
            dangling.append(a)
    print("dangling bulk approvals:", [(a.get("batch_no"), a.get("title", "")[:50]) for a in dangling])
    if dangling:
        res = await db.approvals.delete_many({"id": {"$in": [a["id"] for a in dangling]}})
        print("deleted approvals:", res.deleted_count)
    client.close()


asyncio.run(main())
