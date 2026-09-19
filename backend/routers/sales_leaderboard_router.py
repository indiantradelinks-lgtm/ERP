"""Sales leaderboard — per sales-user monthly activity (enquiries, quotes, win rate)."""
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from core import db, require_permission, get_current_user

router = APIRouter(prefix="/sales", tags=["sales-leaderboard"])

SALES_ROLES = {"sales_executive", "sales_manager", "sales_head", "sales_coordinator"}
QUOTE_SENT_STATUSES = {"sent", "submitted", "under_review", "won", "lost", "invoiced", "approved", "revised"}


def _month_bounds(month: Optional[str]) -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)
    try:
        y, m = (int(x) for x in (month or now.strftime("%Y-%m")).split("-")[:2])
        datetime(y, m, 1)
    except Exception:
        y, m = now.year, now.month
    start = f"{y:04d}-{m:02d}-01"
    end = f"{y:04d}-{m:02d}-{monthrange(y, m)[1]:02d}T23:59:59.999999"
    return f"{y:04d}-{m:02d}", start, end


async def _sales_users() -> List[Dict[str, Any]]:
    q = {"$or": [{"role": {"$in": sorted(SALES_ROLES)}},
                 {"role": {"$regex": "^sales", "$options": "i"}},
                 {"department": {"$regex": "sales", "$options": "i"}}]}
    return await db.users.find(q, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "department": 1}).to_list(500)


async def compute_leaderboard(month: Optional[str] = None) -> dict:
    label, start, end = _month_bounds(month)
    users = await _sales_users()
    ids = [u["id"] for u in users]
    if not ids:
        return {"month": label, "rows": [], "totals": {"enquiries": 0, "quotes": 0, "won": 0, "lost": 0, "win_rate": None}}
    in_month = {"$gte": start, "$lte": end}

    enq_counts = {r["_id"]: r["n"] async for r in db.enquiries.aggregate([
        {"$match": {"created_by": {"$in": ids}, "created_at": in_month}},
        {"$group": {"_id": "$created_by", "n": {"$sum": 1}}}])}
    quote_counts = {r["_id"]: r["n"] async for r in db.quotations.aggregate([
        {"$match": {"created_by": {"$in": ids}, "created_at": in_month, "status": {"$in": sorted(QUOTE_SENT_STATUSES)}}},
        {"$group": {"_id": "$created_by", "n": {"$sum": 1}}}])}
    quote_value = {r["_id"]: r["v"] async for r in db.quotations.aggregate([
        {"$match": {"created_by": {"$in": ids}, "created_at": in_month, "status": {"$in": sorted(QUOTE_SENT_STATUSES)}}},
        {"$group": {"_id": "$created_by", "v": {"$sum": {"$toDouble": {"$ifNull": ["$total", {"$ifNull": ["$grand_total", {"$ifNull": ["$amount", 0]}]}]}}}}}])}
    decided: Dict[str, Dict[str, int]] = {}
    async for r in db.enquiries.aggregate([
        {"$match": {"created_by": {"$in": ids}, "status_history.status": {"$in": ["won", "lost"]}}},
        {"$unwind": "$status_history"},
        {"$match": {"status_history.status": {"$in": ["won", "lost"]}, "status_history.at": in_month}},
        {"$group": {"_id": {"u": "$created_by", "s": "$status_history.status"}, "n": {"$sum": 1}}}]):
        decided.setdefault(r["_id"]["u"], {}).setdefault(r["_id"]["s"], 0)
        decided[r["_id"]["u"]][r["_id"]["s"]] += r["n"]

    rows = []
    for u in users:
        won = decided.get(u["id"], {}).get("won", 0)
        lost = decided.get(u["id"], {}).get("lost", 0)
        rows.append({
            "user_id": u["id"], "name": u.get("name") or u.get("email"), "role": u.get("role"),
            "enquiries": enq_counts.get(u["id"], 0), "quotes": quote_counts.get(u["id"], 0),
            "quote_value": round(quote_value.get(u["id"], 0.0), 2),
            "won": won, "lost": lost,
            "win_rate": round(100 * won / (won + lost), 1) if (won + lost) else None,
        })
    rows.sort(key=lambda r: (-(r["won"]), -(r["quotes"]), -(r["enquiries"]), r["name"].lower()))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    tw, tl = sum(r["won"] for r in rows), sum(r["lost"] for r in rows)
    return {"month": label, "rows": rows,
            "totals": {"enquiries": sum(r["enquiries"] for r in rows), "quotes": sum(r["quotes"] for r in rows),
                       "won": tw, "lost": tl, "win_rate": round(100 * tw / (tw + tl), 1) if (tw + tl) else None}}


@router.get("/leaderboard")
async def leaderboard(month: Optional[str] = None,
                      user: dict = Depends(require_permission("sales_reports", "read"))):
    return await compute_leaderboard(month)


@router.post("/leaderboard/digest/send")
async def send_digest_now(month: Optional[str] = None, user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can send the digest manually")
    from sales_digest import send_leaderboard_digest
    return await send_leaderboard_digest(month, triggered_by=user.get("email") or "manual")


@router.get("/leaderboard/digest/log")
async def digest_log(user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin only")
    from sales_digest import digest_recipients
    from notification_service import email_enabled
    from m365_email import shared_mailbox_configured
    rows = await db.sales_digest_log.find({}, {"_id": 0}).sort("at", -1).to_list(12)
    return {"email_enabled": shared_mailbox_configured() or email_enabled(),
            "channel": "m365_shared_mailbox" if shared_mailbox_configured() else ("resend" if email_enabled() else None),
            "recipients": await digest_recipients(), "history": rows}


@router.get("/leaderboard/{user_id}/details")
async def leaderboard_details(user_id: str, month: Optional[str] = None,
                              user: dict = Depends(require_permission("sales_reports", "read"))):
    label, start, end = _month_bounds(month)
    in_month = {"$gte": start, "$lte": end}
    proj = {"_id": 0, "id": 1, "enquiry_no": 1, "customer": 1, "client_name": 1, "site_name": 1, "status": 1,
            "created_at": 1, "expected_value": 1, "status_history": 1, "quotation_id": 1}
    enquiries = await db.enquiries.find({"created_by": user_id, "created_at": in_month}, proj).sort("created_at", -1).to_list(500)
    decided = await db.enquiries.find(
        {"created_by": user_id, "created_at": {"$lt": start}, "status_history": {"$elemMatch": {"status": {"$in": ["won", "lost"]}, "at": in_month}}},
        proj).sort("created_at", -1).to_list(500)
    qproj = {"_id": 0, "id": 1, "quote_no": 1, "quotation_no": 1, "client": 1, "client_name": 1, "customer": 1, "title": 1,
             "status": 1, "created_at": 1, "total": 1, "grand_total": 1, "amount": 1, "enquiry_no": 1, "enquiry_id": 1, "revision_no": 1}
    quotes = await db.quotations.find({"created_by": user_id, "created_at": in_month, "status": {"$in": sorted(QUOTE_SENT_STATUSES)}},
                                      qproj).sort("created_at", -1).to_list(500)
    for e in enquiries + decided:
        hist = [h for h in (e.pop("status_history", None) or []) if h.get("status") in ("won", "lost") and start <= (h.get("at") or "") <= end]
        e["decided_in_month"] = hist[-1]["status"] if hist else None
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1})
    return {"month": label, "user": u, "enquiries": enquiries, "decided_earlier": decided, "quotes": quotes}
