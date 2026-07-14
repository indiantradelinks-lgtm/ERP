"""One-time migration: unify pr_categories into inv_categories (single category master).

- Maps each referenced pr_category to its inv_categories equivalent (creates FAST/INSUL as new).
- Copies gst_pct/default_hsn onto the inv doc.
- Rewrites references: purchase_requisitions.items[], cost_centers, pr_items, vendors.categories[].
- Backs up pr_categories to pr_categories_backup_unify, then drops pr_categories.
Idempotent: skips if pr_categories collection is already gone.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# pr code -> inv code (None = migrate as NEW inv category)
CODE_MAP = {
    "CONSUM": "CONSUM", "PPE": "PPE", "PAINT": "PAINT", "ROOF": "ROOF",
    "ROPE": "ROPE", "SCAFF": "SCAFFOLD", "TOOL": "TOOLS", "OFFICE": "OFFICE",
    "FAST": None, "INSUL": None,
}
DROP_CODES = {"ABC", "XYZ", "TEST"}  # junk/demo, verified unreferenced


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()

    pr_cats = await db.pr_categories.find({}, {"_id": 0}).to_list(500)
    if not pr_cats:
        print("pr_categories already empty/migrated — nothing to do")
        return

    inv_by_code = {c["code"]: c for c in await db.inv_categories.find({}, {"_id": 0}).to_list(500)}

    id_map, code_map, name_map = {}, {}, {}
    created = 0
    for pc in pr_cats:
        code = pc.get("code")
        if code in DROP_CODES:
            continue
        target_code = CODE_MAP.get(code, None)
        if target_code and target_code in inv_by_code:
            inv = inv_by_code[target_code]
            upd = {}
            if pc.get("gst_pct") is not None and inv.get("gst_pct") is None:
                upd["gst_pct"] = pc["gst_pct"]
            if pc.get("default_hsn") and not inv.get("default_hsn"):
                upd["default_hsn"] = pc["default_hsn"]
            if upd:
                await db.inv_categories.update_one({"id": inv["id"]}, {"$set": upd})
        else:
            inv = {
                "id": str(uuid.uuid4()), "code": code, "name": pc.get("name"),
                "description": pc.get("description"), "sub_categories": [],
                "gst_pct": pc.get("gst_pct"), "default_hsn": pc.get("default_hsn"),
                "active": pc.get("active", True), "created_by": "unify_migration", "created_at": now,
            }
            await db.inv_categories.insert_one(dict(inv))
            inv_by_code[code] = inv
            created += 1
        id_map[pc["id"]] = inv["id"]
        code_map[code] = inv["code"]
        name_map[pc["id"]] = inv["name"]

    # 1. purchase_requisitions.items[]
    pr_updated = 0
    async for doc in db.purchase_requisitions.find({"items.category_id": {"$in": list(id_map)}}):
        items = doc.get("items", [])
        changed = False
        for it in items:
            old = it.get("category_id")
            if old in id_map:
                it["category_id"] = id_map[old]
                it["category"] = name_map[old]
                changed = True
        if changed:
            await db.purchase_requisitions.update_one({"_id": doc["_id"]}, {"$set": {"items": items}})
            pr_updated += 1

    # 2. cost_centers
    cc_updated = 0
    async for cc in db.cost_centers.find({"category_id": {"$in": list(id_map)}}):
        old = cc["category_id"]
        inv = inv_by_code[code_map[[c["code"] for c in pr_cats if c["id"] == old][0]]]
        await db.cost_centers.update_one({"_id": cc["_id"]}, {"$set": {
            "category_id": id_map[old], "category_code": inv["code"], "category_name": inv["name"],
        }})
        cc_updated += 1

    # 3. pr_items
    pi_updated = 0
    async for pi in db.pr_items.find({"category_id": {"$in": list(id_map)}}):
        old = pi["category_id"]
        inv = inv_by_code[code_map[[c["code"] for c in pr_cats if c["id"] == old][0]]]
        await db.pr_items.update_one({"_id": pi["_id"]}, {"$set": {
            "category_id": id_map[old], "category_code": inv["code"], "category_name": inv["name"],
        }})
        pi_updated += 1

    # 4. vendors.categories[] (codes)
    v_updated = 0
    changed_codes = {k: v for k, v in code_map.items() if k != v}
    for old_code, new_code in changed_codes.items():
        r = await db.vendors.update_many({"categories": old_code}, {"$set": {"categories.$[e]": new_code}},
                                         array_filters=[{"e": old_code}])
        v_updated += r.modified_count

    # 5. backup + drop
    await db.pr_categories_backup_unify.delete_many({})
    if pr_cats:
        await db.pr_categories_backup_unify.insert_many([dict(c) for c in pr_cats])
    await db.pr_categories.drop()

    total = await db.inv_categories.count_documents({})
    print(f"Migrated {len(id_map)} pr_categories → inv (new created: {created}, junk dropped: {len(pr_cats) - len(id_map)})")
    print(f"References updated — PRs: {pr_updated}, cost_centers: {cc_updated}, pr_items: {pi_updated}, vendor code fields: {v_updated}")
    print(f"inv_categories now: {total} | pr_categories dropped (backup in pr_categories_backup_unify)")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
