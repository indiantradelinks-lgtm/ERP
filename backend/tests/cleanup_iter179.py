"""One-off cleanup of iter-179 test data (advances / approvals / project_requests)."""
import asyncio
import os
import re

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

RX = re.compile("TEST_iter179", re.I)


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    advs = await db.employee_advances.find(
        {"$or": [{"reason": {"$regex": "TEST_iter179", "$options": "i"}},
                 {"remarks": {"$regex": "TEST_iter179", "$options": "i"}}]}
    ).to_list(500)
    adv_ids = [a["id"] for a in advs]
    batch_nos = list({a.get("batch_no") for a in advs if a.get("batch_no")})
    print(f"advances found: {len(adv_ids)} batches={batch_nos}")

    aps = await db.approvals.find({"$or": [{"batch_no": {"$in": batch_nos}},
                                          {"advance_ids": {"$in": adv_ids}}]}).to_list(500)
    ap_ids = [a["id"] for a in aps]
    print(f"approvals found: {len(ap_ids)}")

    prs = await db.project_requests.find({"source": "advance",
                                          "source_id": {"$in": adv_ids}}).to_list(500)
    print(f"project_requests (payment queue) found: {len(prs)}")

    if adv_ids:
        print("del advances:", (await db.employee_advances.delete_many({"id": {"$in": adv_ids}})).deleted_count)
    if ap_ids:
        print("del approvals:", (await db.approvals.delete_many({"id": {"$in": ap_ids}})).deleted_count)
    if prs:
        print("del project_requests:",
              (await db.project_requests.delete_many({"source": "advance", "source_id": {"$in": adv_ids}})).deleted_count)

    left = await db.employee_advances.count_documents(
        {"reason": {"$regex": "TEST_iter179", "$options": "i"}})
    print("remaining iter179 advances:", left)
    client.close()


asyncio.run(main())
