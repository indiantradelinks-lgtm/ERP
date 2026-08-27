"""Pending Billing Report + monthly reminder emails (Iter 181).

- Projects tagged `billing_type`:
    annual_rate_contract  -> monthly billing cycle (one bill expected per month)
    one_time_supply       -> final (or partial) billing once
- Report computes live status per project from bill_requests, so when Accounts
  marks a request bill_generated the report updates automatically.
- Reminder email (after the 5th of each month, once) to all PMs + P&O heads/
  seniors + GM + Director listing projects whose billing is still pending.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, now_iso, require_permission
from scope import apply_project_scope

router = APIRouter(tags=["billing-pending"])

BILLING_TYPES = {"annual_rate_contract", "one_time_supply"}
ORDER_TYPES = {"supply", "service", "one_time_service", "arc", "shutdown", "outage"}
SERVICE_TYPES_STD = ["scaffolding", "painting", "roof_sheeting", "roof_access", "rope_access", "insulation", "services", "shutdown"]


async def get_service_types(active_only: bool = False) -> Dict[str, Dict[str, Any]]:
    """Standard service types merged with super-admin overrides/custom entries."""
    merged: Dict[str, Dict[str, Any]] = {
        k: {"label": k.replace("_", " ").title(), "active": True, "builtin": True} for k in SERVICE_TYPES_STD}
    async for o in db.service_type_options.find({}, {"_id": 0}):
        k = o.get("key")
        if not k:
            continue
        base = merged.get(k, {"label": k.replace("_", " ").title(), "builtin": False})
        if o.get("label"):
            base["label"] = o["label"]
        base["active"] = o.get("active", True)
        merged[k] = base
    if active_only:
        return {k: v for k, v in merged.items() if v.get("active", True)}
    return merged
ACTIVE_PROJECT_STATUSES = {"active", "in_progress", "ongoing", "on_hold", None, ""}
REMINDER_ROLES = ["project_manager", "manager_o_p", "project_coordinator",
                  "dept_head", "general_manager", "director"]


class BillingTypeIn(BaseModel):
    billing_type: Optional[str] = None
    order_type: Optional[str] = None
    service_type: Optional[str] = None


def _month_overlap(req: dict, month: str) -> bool:
    """True when a bill request covers `month` (YYYY-MM)."""
    pf, pt = (req.get("period_from") or "")[:7], (req.get("period_to") or "")[:7]
    if pf or pt:
        return (pf or "0000-00") <= month <= (pt or "9999-99")
    return (req.get("created_at") or "")[:7] == month


def _range_overlap(req: dict, dfrom: str, dto: str) -> bool:
    """True when a bill request's service period overlaps [dfrom, dto] (YYYY-MM-DD)."""
    pf, pt = (req.get("period_from") or "")[:10], (req.get("period_to") or "")[:10]
    if pf or pt:
        return (pf or "0000-00-00") <= dto and (pt or "9999-99-99") >= dfrom
    created = (req.get("created_at") or "")[:10]
    return dfrom <= created <= dto


async def build_pending_report(month: str, user: Optional[dict] = None,
                               period_from: Optional[str] = None,
                               period_to: Optional[str] = None) -> Dict[str, Any]:
    q: Dict[str, Any] = {"status": {"$nin": ["completed", "closed", "cancelled", "archived"]}}
    if user:
        q = await apply_project_scope(user, q, id_field="id", code_field="code")
    projects = await db.projects.find(
        q, {"_id": 0, "id": 1, "code": 1, "name": 1, "client": 1, "status": 1,
            "billing_type": 1, "order_type": 1, "type": 1,
            "project_manager_name": 1, "manager": 1,
            "project_manager_id": 1, "start_date": 1, "created_at": 1}).sort("code", 1).to_list(2000)
    codes = [p["code"] for p in projects if p.get("code")]
    reqs_by_proj: Dict[str, List[dict]] = {}
    async for r in db.bill_requests.find(
            {"project_code": {"$in": codes}},
            {"_id": 0, "project_code": 1, "status": 1, "bill_type": 1, "bill_nature": 1,
             "period_from": 1, "period_to": 1, "created_at": 1, "bill_number": 1,
             "expected_amount": 1, "generated_at": 1, "request_no": 1}):
        reqs_by_proj.setdefault(r["project_code"], []).append(r)
    bills_by_proj: Dict[str, List[dict]] = {}
    async for b in db.ra_bills.find(
            {"project_code": {"$in": codes}, "status": {"$nin": ["cancelled", "rejected"]}},
            {"_id": 0, "project_code": 1, "subtotal": 1, "gst_amount": 1, "gross_value": 1,
             "paid_amount": 1, "balance_due": 1, "status": 1}):
        bills_by_proj.setdefault(b["project_code"], []).append(b)

    rows: List[Dict[str, Any]] = []
    for p in projects:
        reqs = reqs_by_proj.get(p.get("code") or "", [])
        gen = [r for r in reqs if r.get("status") == "bill_generated"]
        open_reqs = [r for r in reqs if r.get("status") not in ("bill_generated", "rejected")]
        btype = p.get("billing_type") or None
        effective = btype or "annual_rate_contract"
        last_gen = max(gen, key=lambda r: r.get("generated_at") or r.get("created_at") or "", default=None)

        if effective == "one_time_supply":
            final_done = any((r.get("bill_type") == "final" or r.get("bill_nature") == "one_time") for r in gen)
            if final_done:
                status = "billed"
            elif gen:
                status = "partially_billed"
            elif open_reqs:
                status = "requested"
            else:
                status = "pending"
        else:  # monthly cycle (ARC)
            if period_from and period_to:
                month_gen = [r for r in gen if _range_overlap(r, period_from, period_to)]
                month_open = [r for r in open_reqs if _range_overlap(r, period_from, period_to)]
            else:
                month_gen = [r for r in gen if _month_overlap(r, month)]
                month_open = [r for r in open_reqs if _month_overlap(r, month)]
            if month_gen:
                status = "billed"
            elif month_open:
                status = "requested"
            else:
                status = "pending"

        open_req = max(open_reqs, key=lambda r: r.get("created_at") or "", default=None)
        bills = bills_by_proj.get(p.get("code") or "", [])
        basic = round(sum(b.get("subtotal") or 0 for b in bills), 2)
        gst = round(sum(b.get("gst_amount") or 0 for b in bills), 2)
        gross = round(sum(b.get("gross_value") or ((b.get("subtotal") or 0) + (b.get("gst_amount") or 0)) for b in bills), 2)
        paid = round(sum(b.get("paid_amount") or 0 for b in bills), 2)
        balance = round(sum(b.get("balance_due") if b.get("balance_due") is not None
                            else (b.get("gross_value") or 0) - (b.get("paid_amount") or 0) for b in bills), 2)
        if not bills and gen:
            basic = round(sum(r.get("expected_amount") or 0 for r in gen), 2)
        if not bills and not gen:
            payment_status = "not_billed"
        elif bills and all(b.get("status") == "paid" or (b.get("balance_due") is not None and b["balance_due"] <= 0) for b in bills):
            payment_status = "paid"
        elif paid > 0:
            payment_status = "partially_paid"
        else:
            payment_status = "unpaid"
        anchor = (last_gen or {}).get("generated_at") or (last_gen or {}).get("created_at") \
            or p.get("start_date") or p.get("created_at")
        try:
            from datetime import date as _date
            pending_days = (_date.today() - _date.fromisoformat(str(anchor)[:10])).days
        except Exception:
            pending_days = None
        rows.append({
            "project_id": p.get("id"), "project_code": p.get("code"), "project_name": p.get("name"),
            "client": p.get("client"), "project_status": p.get("status"),
            "billing_type": btype, "effective_billing_type": effective,
            "order_type": p.get("order_type"), "service_type": p.get("type"),
            "project_manager": p.get("project_manager_name") or p.get("manager"),
            "project_manager_id": p.get("project_manager_id"),
            "billing_status": status,
            "last_bill_no": (last_gen or {}).get("bill_number") or (last_gen or {}).get("request_no"),
            "last_bill_at": (last_gen or {}).get("generated_at") or (last_gen or {}).get("created_at"),
            "open_request_no": (open_req or {}).get("request_no"),
            "open_request_nature": (open_req or {}).get("bill_nature") or (open_req or {}).get("bill_type"),
            "bills_generated": len(gen),
            "billed_amount": round(sum(r.get("expected_amount") or 0 for r in gen), 2),
            "billed_basic": basic, "billed_gst": gst, "billed_gross": gross,
            "paid_amount": paid, "balance_due": balance,
            "payment_status": payment_status,
            "pending_days": pending_days,
        })

    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["billing_status"]] = counts.get(r["billing_status"], 0) + 1
    return {"month": month, "rows": rows,
            "summary": {"total": len(rows), **counts,
                        "pending": counts.get("pending", 0)}}


def apply_report_filters(rows: List[dict], *, status: Optional[str] = None, q: Optional[str] = None,
                         project_manager: Optional[str] = None, client: Optional[str] = None,
                         billing_type: Optional[str] = None, payment_status: Optional[str] = None,
                         min_pending_days: Optional[int] = None,
                         order_type: Optional[str] = None, service_type: Optional[str] = None) -> List[dict]:
    def ok(r):
        if status and r["billing_status"] != status:
            return False
        if q and q.lower() not in f"{r['project_code']} {r['project_name']}".lower():
            return False
        if project_manager and project_manager.lower() not in (r["project_manager"] or "").lower():
            return False
        if client and client.lower() not in (r["client"] or "").lower():
            return False
        if billing_type:
            if billing_type == "unset" and r["billing_type"]:
                return False
            if billing_type != "unset" and r["effective_billing_type"] != billing_type:
                return False
        if payment_status and r["payment_status"] != payment_status:
            return False
        if order_type and (r.get("order_type") or "") != order_type:
            return False
        if service_type and (r.get("service_type") or "") != service_type:
            return False
        if min_pending_days and (r.get("pending_days") or 0) < int(min_pending_days):
            return False
        return True
    return [r for r in rows if ok(r)]


def _summarise(rows: List[dict]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["billing_status"]] = counts.get(r["billing_status"], 0) + 1
    return {"total": len(rows), **counts, "pending": counts.get("pending", 0)}


@router.get("/billing/pending-report")
async def pending_report(month: Optional[str] = None, status: Optional[str] = None,
                         q: Optional[str] = None, project_manager: Optional[str] = None,
                         client: Optional[str] = None, billing_type: Optional[str] = None,
                         payment_status: Optional[str] = None, min_pending_days: Optional[int] = None,
                         period_from: Optional[str] = None, period_to: Optional[str] = None,
                         order_type: Optional[str] = None, service_type: Optional[str] = None,
                         user: dict = Depends(require_permission("bill_requests", "read"))):
    month = month or now_iso()[:7]
    report = await build_pending_report(month, user=user, period_from=period_from, period_to=period_to)
    rows = apply_report_filters(report["rows"], status=status, q=q, project_manager=project_manager,
                                client=client, billing_type=billing_type,
                                payment_status=payment_status, min_pending_days=min_pending_days,
                                order_type=order_type, service_type=service_type)
    return {"month": month, "rows": rows, "summary": _summarise(rows),
            "managers": sorted({r["project_manager"] for r in report["rows"] if r["project_manager"]}),
            "clients": sorted({r["client"] for r in report["rows"] if r["client"]}),
            "service_types": sorted({r["service_type"] for r in report["rows"] if r.get("service_type")}
                                    | set((await get_service_types(active_only=True)).keys())),
            "order_types": sorted(ORDER_TYPES)}


@router.put("/billing/projects/{code}/billing-type")
async def set_billing_type(code: str, payload: BillingTypeIn,
                           user: dict = Depends(require_permission("bill_requests", "write"))):
    update: Dict[str, Any] = {}
    if payload.billing_type:
        if payload.billing_type not in BILLING_TYPES:
            raise HTTPException(400, f"billing_type must be one of {sorted(BILLING_TYPES)}")
        update["billing_type"] = payload.billing_type
    if payload.order_type:
        if payload.order_type not in ORDER_TYPES:
            raise HTTPException(400, f"order_type must be one of {sorted(ORDER_TYPES)}")
        update["order_type"] = payload.order_type
    if payload.service_type:
        update["type"] = payload.service_type.strip().lower().replace(" ", "_")
    if not update:
        raise HTTPException(400, "nothing to update")
    update["billing_type_updated_by"] = user.get("name") or user.get("email")
    update["billing_type_updated_at"] = now_iso()
    res = await db.projects.update_one({"code": code}, {"$set": update})
    if not res.matched_count:
        raise HTTPException(404, "Project not found")
    return {"ok": True, "code": code, **update}


@router.get("/billing/pending-report/export")
async def pending_report_export(fmt: str = "xlsx", month: Optional[str] = None,
                                status: Optional[str] = None, q: Optional[str] = None,
                                project_manager: Optional[str] = None, client: Optional[str] = None,
                                billing_type: Optional[str] = None, payment_status: Optional[str] = None,
                                min_pending_days: Optional[int] = None,
                                period_from: Optional[str] = None, period_to: Optional[str] = None,
                                order_type: Optional[str] = None, service_type: Optional[str] = None,
                                user: dict = Depends(require_permission("bill_requests", "read"))):
    from fastapi import Response
    month = month or now_iso()[:7]
    report = await build_pending_report(month, user=user, period_from=period_from, period_to=period_to)
    rows = apply_report_filters(report["rows"], status=status, q=q, project_manager=project_manager,
                                client=client, billing_type=billing_type,
                                payment_status=payment_status, min_pending_days=min_pending_days,
                                order_type=order_type, service_type=service_type)
    summary = _summarise(rows)
    if fmt == "pdf":
        from pdf_generator import render_billing_pending_pdf
        data = render_billing_pending_pdf(rows, summary, month)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="pending-billing-{month}.pdf"'})
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from io import BytesIO
    wb = Workbook()
    ws = wb.active
    ws.title = f"Pending Billing {month}"
    ws.append(["Project Code", "Project Name", "Client", "Project Manager", "Billing Type",
               "WO/PO Type", "Service Type",
               f"Billing Status ({month})", "Pending Days", "Last Bill No", "Last Bill Date", "Open Request",
               "Bills Generated", "Billed Basic (₹)", "GST (₹)", "Gross (₹)",
               "Paid (₹)", "Balance Due (₹)", "Payment Status"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F172A")
    for r in rows:
        ws.append([r["project_code"], r["project_name"], r["client"], r["project_manager"],
                   (r["effective_billing_type"] or "").replace("_", " ").title(),
                   (r.get("order_type") or "").replace("_", " ").title(),
                   (r.get("service_type") or "").replace("_", " ").title(),
                   r["billing_status"].replace("_", " ").title(),
                   r.get("pending_days"),
                   r["last_bill_no"], (r["last_bill_at"] or "")[:10],
                   r["open_request_no"], r["bills_generated"],
                   r["billed_basic"], r["billed_gst"], r["billed_gross"],
                   r["paid_amount"], r["balance_due"],
                   (r["payment_status"] or "").replace("_", " ").title()])
    for i, w in enumerate([15, 28, 20, 18, 24, 14, 14, 16, 12, 16, 12, 14, 8, 14, 12, 14, 14, 14, 14], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    s = wb.create_sheet("Summary")
    for k, v in summary.items():
        s.append([k.replace("_", " ").title(), v])
    s.column_dimensions["A"].width = 24
    buf = BytesIO()
    wb.save(buf)
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="pending-billing-{month}.xlsx"'})


# ─── Reminder email ──────────────────────────────────────────────────────────
def _reminder_html(month: str, pending: List[dict]) -> str:
    trs = ""
    for i, r in enumerate(pending, 1):
        trs += (f"<tr><td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{i}</td>"
                f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;font-weight:700;'>{r.get('project_code') or ''}</td>"
                f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{r.get('project_name') or ''}</td>"
                f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{r.get('client') or '—'}</td>"
                f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{(r.get('effective_billing_type') or '').replace('_', ' ').title()}</td>"
                f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{r.get('project_manager') or '—'}</td>"
                f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{(r.get('last_bill_at') or '—')[:10]}</td></tr>")
    return f"""
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:0 auto;color:#0f172a;">
  <div style="background:#0f172a;color:#fff;padding:16px 20px;">
    <div style="font-size:11px;letter-spacing:0.15em;text-transform:uppercase;opacity:0.8;">Indian Trade Links · ERP</div>
    <div style="font-size:20px;font-weight:800;margin-top:4px;">Pending Billing Reminder — {month}</div>
  </div>
  <div style="padding:18px 20px;border:1px solid #e2e8f0;border-top:none;">
    <p style="font-size:13px;line-height:1.6;">Dear Team,<br/>
    Billing for the following <b>{len(pending)} project(s)</b> is still <b style="color:#b91c1c;">PENDING</b> for {month}.
    Project Managers are requested to raise the Bill Generation Request at the earliest; Accounts will process it on approval.</p>
    <table cellspacing="0" cellpadding="0" style="width:100%;border:1px solid #e2e8f0;font-size:12px;">
      <tr style="background:#f1f5f9;text-transform:uppercase;font-size:10px;letter-spacing:0.08em;color:#475569;">
        <th style="padding:8px 10px;text-align:left;">#</th><th style="padding:8px 10px;text-align:left;">Project</th>
        <th style="padding:8px 10px;text-align:left;">Name</th><th style="padding:8px 10px;text-align:left;">Client</th>
        <th style="padding:8px 10px;text-align:left;">Billing Type</th><th style="padding:8px 10px;text-align:left;">Project Manager</th>
        <th style="padding:8px 10px;text-align:left;">Last Bill</th>
      </tr>{trs}
    </table>
    <p style="font-size:11px;color:#64748b;margin-top:14px;">Annual rate contract projects require one bill every month.
    One-time supply projects require final (or partial) billing. This is an automated reminder sent after the 5th of every month.</p>
  </div>
</div>"""


async def send_billing_reminder(month: str, *, queued_by: str = "scheduler",
                                background: bool = False) -> Dict[str, Any]:
    """Builds the pending list and queues one email to PMs + P&O seniors + GM + Director."""
    report = await build_pending_report(month, user=None)
    pending = [r for r in report["rows"] if r["billing_status"] == "pending"]
    if not pending:
        return {"ok": True, "sent": False, "reason": "no pending projects", "pending": 0}
    recipients = sorted({
        u["email"] async for u in db.users.find(
            {"role": {"$in": REMINDER_ROLES}, "active": {"$ne": False}, "email": {"$ne": None}},
            {"_id": 0, "email": 1})
        if u.get("email")
    })
    if not recipients:
        return {"ok": False, "sent": False, "reason": "no recipients found", "pending": len(pending)}
    from routers.email_router import _queue_outbox, _send_and_log
    subject = f"⏰ Pending Billing Reminder — {len(pending)} project(s) awaiting billing for {month}"
    html = _reminder_html(month, pending)
    text = f"Billing pending for {len(pending)} project(s) in {month}: " + \
        ", ".join(f"{r['project_code']} ({r.get('project_manager') or 'PM —'})" for r in pending)
    outbox_id = await _queue_outbox(
        sender_type="system", sender_purpose="noreply",
        sender_user_id="", sender_email="", sender_display_name="ERP Billing Bot",
        to=recipients, cc=[], bcc=[], subject=subject, body_text=text, body_html=html,
        reply_to=None, attachments_inline=[], file_ids=[],
        related={"type": "billing_reminder", "month": month}, queued_by=queued_by)
    if background:
        import asyncio
        asyncio.create_task(_send_and_log(outbox_id))
        return {"ok": True, "sent": True, "queued": True, "pending": len(pending),
                "recipients": len(recipients), "outbox_id": outbox_id}
    result = await _send_and_log(outbox_id)
    return {"ok": result.get("ok", False), "sent": result.get("ok", False),
            "pending": len(pending), "recipients": len(recipients),
            "outbox_id": outbox_id, "error": result.get("last_error")}


@router.post("/billing/pending-report/send-reminder")
async def manual_reminder(month: Optional[str] = None, user: dict = Depends(get_current_user)):
    if user.get("role") not in {"super_admin", "director", "general_manager"}:
        raise HTTPException(403, "not allowed")
    month = month or now_iso()[:7]
    res = await send_billing_reminder(month, queued_by=user.get("name") or user.get("email"), background=True)
    return res
