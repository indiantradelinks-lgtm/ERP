"""Phase 7 — one-time cleanup of duplicate projects.

Merges projects that share the same (name, client) into a single canonical
project, re-points all child records (project_id / project_code / project /
proj / project_name) to the canonical, then deletes the redundant projects.

Canonical = the member with the most child references (tie-break: oldest
created_at). A full backup of every deleted project and every child document
(pre-change) is written to scripts/phase7_backup_<ts>.json BEFORE any mutation,
so the operation is reversible.

Usage:
    python scripts/phase7_dedup_merge.py            # backup + plan only (no writes)
    python scripts/phase7_dedup_merge.py --execute  # backup, then perform the merge
"""
import asyncio
import datetime
import json
import sys
from collections import defaultdict

from core import db

CODE_FIELDS = ["project_code"]
NAME_FIELDS = ["project_name"]
ALIAS_FIELDS = ["project", "proj"]  # may hold either a code or a name


def norm(v):
    return str(v or "").strip().lower()


async def ref_total(colls, m):
    rid, rcode, rname = m["id"], m.get("code"), m.get("name")
    tot = 0
    for coll in colls:
        if coll == "projects":
            continue
        tot += await db[coll].count_documents({"project_id": rid})
        for f in CODE_FIELDS:
            tot += await db[coll].count_documents({f: rcode})
        for f in NAME_FIELDS:
            tot += await db[coll].count_documents({f: rname})
        for f in ALIAS_FIELDS:
            tot += await db[coll].count_documents({f: {"$in": [rcode, rname]}})
    return tot


def match_query(m):
    rid, rcode, rname = m["id"], m.get("code"), m.get("name")
    ors = [{"project_id": rid}]
    ors += [{f: rcode} for f in CODE_FIELDS]
    ors += [{f: rname} for f in NAME_FIELDS]
    ors += [{f: {"$in": [rcode, rname]}} for f in ALIAS_FIELDS]
    return {"$or": ors}


async def main(execute=False):
    colls = await db.list_collection_names()
    rows = await db.projects.find({}, {"_id": 0}).to_list(1000)
    groups = defaultdict(list)
    for r in rows:
        groups[(norm(r.get("name")), norm(r.get("client")))].append(r)
    dups = {k: v for k, v in groups.items() if len(v) > 1}

    # Build the merge plan: pick canonical per group.
    plan = []  # (canonical, [redundant, ...])
    for members in dups.values():
        ann = [(m, await ref_total(colls, m)) for m in members]
        ann.sort(key=lambda a: (-a[1], str(a[0].get("created_at") or "")))
        plan.append((ann[0][0], [a[0] for a in ann[1:]]))

    # Backup BEFORE any mutation.
    backup = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "deleted_projects": [],
        "child_before": defaultdict(list),
        "plan": [],
    }
    for canon, reds in plan:
        backup["plan"].append({
            "keep": {"id": canon["id"], "code": canon.get("code"), "name": canon.get("name")},
            "merge": [{"id": m["id"], "code": m.get("code")} for m in reds],
        })
        for m in reds:
            backup["deleted_projects"].append(m)
            for coll in colls:
                if coll == "projects":
                    continue
                async for d in db[coll].find(match_query(m), {"_id": 0}):
                    backup["child_before"][coll].append({"collection": coll, "doc": d})

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = f"/app/backend/scripts/phase7_backup_{stamp}.json"
    with open(path, "w") as f:
        json.dump(backup, f, default=str, indent=1)
    print("BACKUP written:", path)
    print("  deleted_projects:", len(backup["deleted_projects"]))
    print("  child_before:", {k: len(v) for k, v in backup["child_before"].items()})

    if not execute:
        print("\n-- backup/plan only, no changes made (pass --execute to perform the merge) --")
        return

    total_mod = 0
    del_ids = []
    for canon, reds in plan:
        cid, ccode, cname = canon["id"], canon.get("code"), canon.get("name")
        for m in reds:
            del_ids.append(m["id"])
            rid, rcode, rname = m["id"], m.get("code"), m.get("name")
            for coll in colls:
                if coll == "projects":
                    continue
                r = await db[coll].update_many({"project_id": rid}, {"$set": {"project_id": cid}})
                total_mod += r.modified_count
                for f in CODE_FIELDS:
                    r = await db[coll].update_many({f: rcode}, {"$set": {f: ccode}})
                    total_mod += r.modified_count
                for f in NAME_FIELDS:
                    r = await db[coll].update_many({f: rname}, {"$set": {f: cname}})
                    total_mod += r.modified_count
                for f in ALIAS_FIELDS:
                    r = await db[coll].update_many({f: rcode}, {"$set": {f: ccode}})
                    total_mod += r.modified_count
                    r = await db[coll].update_many({f: rname}, {"$set": {f: cname}})
                    total_mod += r.modified_count

    r = await db.projects.delete_many({"id": {"$in": del_ids}})
    print("\nEXECUTED:")
    print("  child field-updates applied:", total_mod)
    print("  projects deleted:", r.deleted_count)

    # Verify.
    rows2 = await db.projects.find({}, {"_id": 0, "name": 1, "client": 1}).to_list(1000)
    g2 = defaultdict(list)
    for x in rows2:
        g2[(norm(x.get("name")), norm(x.get("client")))].append(x)
    remaining = {k: len(v) for k, v in g2.items() if len(v) > 1}
    del_codes = [m.get("code") for _, reds in plan for m in reds]
    del_names = [m.get("name") for _, reds in plan for m in reds]
    orphans = 0
    for coll in colls:
        if coll == "projects":
            continue
        orphans += await db[coll].count_documents({"project_id": {"$in": del_ids}})
        for f in CODE_FIELDS + ALIAS_FIELDS:
            orphans += await db[coll].count_documents({f: {"$in": del_codes}})
        for f in NAME_FIELDS + ALIAS_FIELDS:
            orphans += await db[coll].count_documents({f: {"$in": del_names}})
    print("  projects remaining:", len(rows2))
    print("  remaining duplicate groups:", remaining)
    print("  orphan child refs to deleted projects (expect 0):", orphans)


if __name__ == "__main__":
    asyncio.run(main(execute="--execute" in sys.argv))
