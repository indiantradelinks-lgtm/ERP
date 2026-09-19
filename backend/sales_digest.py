"""Monthly Sales Leaderboard email digest (previous month) for sales managers."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from core import db, logger, now_iso, new_id

DIGEST_ROLES = {"sales_manager", "sales_head", "director", "general_manager"}
IST = timezone(timedelta(hours=5, minutes=30))


def prev_month(today: Optional[date] = None) -> str:
    d = (today or datetime.now(IST).date()).replace(day=1) - timedelta(days=1)
    return d.strftime("%Y-%m")


def is_first_working_day(today: Optional[date] = None) -> bool:
    d = today or datetime.now(IST).date()
    if d.weekday() >= 5:
        return False
    first = d.replace(day=1)
    while first.weekday() >= 5:
        first += timedelta(days=1)
    return d == first


async def digest_recipients() -> list[dict]:
    q = {"is_active": {"$ne": False}, "email": {"$exists": True, "$ne": ""},
         "$or": [{"role": {"$in": sorted(DIGEST_ROLES)}},
                 {"role": "dept_head", "department": {"$regex": "sales", "$options": "i"}}]}
    return await db.users.find(q, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).to_list(200)


def _inr(n) -> str:
    return "₹" + f"{float(n or 0):,.0f}"


def build_digest_html(data: dict, app_url: str = "") -> str:
    rows = data.get("rows") or []
    t = data.get("totals") or {}
    label = datetime.strptime(data["month"] + "-01", "%Y-%m-%d").strftime("%B %Y")
    tr = "".join(
        f"<tr style='border-bottom:1px solid #e5e7eb'><td style='padding:6px 10px'>#{r['rank']}</td>"
        f"<td style='padding:6px 10px'><b>{r['name']}</b><br><span style='color:#6b7280;font-size:11px'>{(r.get('role') or '').replace('_', ' ')}</span></td>"
        f"<td style='padding:6px 10px;text-align:center'>{r['enquiries']}</td><td style='padding:6px 10px;text-align:center'>{r['quotes']}</td>"
        f"<td style='padding:6px 10px;text-align:center'>{r['won']} / {r['lost']}</td>"
        f"<td style='padding:6px 10px;text-align:center'>{'—' if r['win_rate'] is None else str(r['win_rate']) + '%'}</td>"
        f"<td style='padding:6px 10px;text-align:right'>{_inr(r.get('quote_value'))}</td></tr>"
        for r in rows) or "<tr><td colspan='7' style='padding:12px;color:#6b7280'>No sales-role users had activity.</td></tr>"
    link = f"<p style='margin-top:16px'><a href='{app_url}/app/sales-reports' style='color:#1d4ed8'>Open the Sales Dashboard →</a></p>" if app_url else ""
    return f"""
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:720px;color:#111827">
  <h2 style="margin:0 0 4px">Sales Leaderboard — {label}</h2>
  <p style="margin:0 0 14px;color:#6b7280;font-size:13px">Monthly digest · INDIAN TRADE LINKS ERP</p>
  <table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:14px">
    <tr>
      <td style="padding:8px;background:#f3f4f6"><b>{t.get('enquiries', 0)}</b><br><span style='color:#6b7280;font-size:11px'>Enquiries raised</span></td>
      <td style="padding:8px;background:#f3f4f6"><b>{t.get('quotes', 0)}</b><br><span style='color:#6b7280;font-size:11px'>Quotes sent</span></td>
      <td style="padding:8px;background:#f3f4f6"><b>{t.get('won', 0)} / {t.get('lost', 0)}</b><br><span style='color:#6b7280;font-size:11px'>Won / Lost</span></td>
      <td style="padding:8px;background:#f3f4f6"><b>{'—' if t.get('win_rate') is None else str(t['win_rate']) + '%'}</b><br><span style='color:#6b7280;font-size:11px'>Team win rate</span></td>
    </tr>
  </table>
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <thead><tr style="background:#111827;color:#fff;text-align:left">
      <th style="padding:6px 10px">Rank</th><th style="padding:6px 10px">Salesperson</th><th style="padding:6px 10px;text-align:center">Enquiries</th>
      <th style="padding:6px 10px;text-align:center">Quotes</th><th style="padding:6px 10px;text-align:center">Won / Lost</th>
      <th style="padding:6px 10px;text-align:center">Win rate</th><th style="padding:6px 10px;text-align:right">Quote value</th>
    </tr></thead>
    <tbody>{tr}</tbody>
  </table>
  {link}
</div>"""


async def _deliver(to: str, subject: str, html: str, month: str) -> str:
    """Prefer the ERP's M365 shared-mailbox outbox (production channel); fall back to Resend."""
    from m365_email import shared_mailbox_configured, SHARED_USERNAME, SHARED_DISPLAY_NAME
    if shared_mailbox_configured():
        from routers.email_router import _queue_outbox, _send_and_log
        outbox_id = await _queue_outbox(
            sender_type="shared", sender_user_id="system", sender_email=SHARED_USERNAME,
            sender_display_name=SHARED_DISPLAY_NAME, to=[to], cc=[], bcc=[], subject=subject,
            body_text="Monthly sales leaderboard digest — open in an HTML-capable mail client.", body_html=html,
            reply_to=None, attachments_inline=[], file_ids=[],
            related={"entity_type": "sales_leaderboard_digest", "entity_id": month}, queued_by="system",
            sender_purpose="sales_digest")
        res = await _send_and_log(outbox_id)
        return "sent" if res.get("ok") else f"failed: {res.get('last_error') or 'smtp error'}"
    from notification_service import send_email, email_enabled
    if not email_enabled():
        return "skipped: no email channel configured"
    return "sent" if await send_email(to, subject, html) else "failed: resend rejected"


async def send_leaderboard_digest(month: Optional[str] = None, triggered_by: str = "scheduler") -> dict:
    from routers.sales_leaderboard_router import compute_leaderboard
    from notification_service import APP_URL

    month = month or prev_month()
    data = await compute_leaderboard(month)
    recipients = await digest_recipients()
    html = build_digest_html(data, APP_URL)
    subject = f"[ERP] Sales Leaderboard — {datetime.strptime(month + '-01', '%Y-%m-%d').strftime('%B %Y')}"
    sent, failed = [], []
    for u in recipients:
        try:
            status = await _deliver(u["email"], subject, html, month)
        except Exception as e:  # noqa: BLE001
            status = f"failed: {e}"
        (sent if status == "sent" else failed).append({"email": u["email"], "status": status})
    log = {"id": new_id(), "month": month, "at": now_iso(), "triggered_by": triggered_by,
           "recipients": [u["email"] for u in recipients], "sent": sent, "failed": failed, "rows": len(data.get("rows") or [])}
    await db.sales_digest_log.insert_one(dict(log))
    logger.info(f"[sales-digest] {month}: {len(sent)} sent / {len(failed)} failed")
    log.pop("_id", None)
    return log


async def scheduled_digest_job():
    if not is_first_working_day():
        return
    month = prev_month()
    if await db.sales_digest_log.find_one({"month": month, "triggered_by": "scheduler"}, {"_id": 1}):
        return
    try:
        await send_leaderboard_digest(month, "scheduler")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[sales-digest] failed: {e}")
