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
from billing_category import (CATEGORY_LABELS, category_label, category_of, contract_months,
                             is_recurring, month_bounds, monthly_amount, scope_value)
from scope import apply_project_scope
from offload import run_blocking

router = APIRouter(tags=["billing-pending"])

BILLING_TYPES = {"annual_rate_contract", "one_time_supply"}
# `month=all` → report every pending month instead of one selected month.
ALL_MONTHS = "all"
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
    q: Dict[str, Any] = {"status": {"$nin": ["completed", "closed", "cancelled", "archived"]},
                         "billing_type": {"$ne": "non_billable"},
                         "internal": {"$ne": True}}
    if user:
        q = await apply_project_scope(user, q, id_field="id", code_field="code")
    projects = await db.projects.find(
        q, {"_id": 0, "id": 1, "code": 1, "name": 1, "client": 1, "status": 1,
            "billing_type": 1, "order_type": 1, "type": 1, "category": 1,
            "monthly_billing_amount": 1, "contract_value": 1, "work_order_value": 1,
            "end_date": 1, "extended_end_date": 1,
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
        category = category_of(p)
        recurring = is_recurring(p)
        effective = "annual_rate_contract" if recurring else "one_time_supply"
        last_gen = max(gen, key=lambda r: r.get("generated_at") or r.get("created_at") or "", default=None)

        if not recurring:
            final_done = any((r.get("bill_type") == "final" or r.get("bill_nature") == "one_time") for r in gen)
            if final_done:
                status = "billed"
            elif gen:
                status = "partially_billed"
            elif open_reqs:
                status = "requested"
            else:
                status = "pending"
        elif month == ALL_MONTHS:  # resolved from the full ledger further below
            status = "pending"
        else:  # monthly cycle (AMC / ARC)
            valid_months = contract_months(p)
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
            elif valid_months and month not in valid_months:
                status = "out_of_period"
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

        # ── Month-wise billing ledger (Iter 206) ──
        # AMC/ARC: one expected bill per month for the whole project validity.
        # Scope projects: a single period (project start → end) with the balance
        # of the contract value still to be billed.
        expected_monthly = monthly_amount(p) if recurring else 0.0
        total_scope = scope_value(p)
        billed_value = round(sum(r.get("expected_amount") or 0 for r in gen), 2)
        month_rows: List[Dict[str, Any]] = []
        if recurring:
            from datetime import date as _date2
            this_month = _date2.today().isoformat()[:7]
            for mth in contract_months(p):
                m_gen = [r for r in gen if _month_overlap(r, mth)]
                m_open = [r for r in open_reqs if _month_overlap(r, mth)]
                if m_gen:
                    m_status = "billed"
                elif m_open:
                    m_status = "requested"
                elif mth > this_month:
                    m_status = "upcoming"
                else:
                    m_status = "pending"
                month_rows.append({
                    "month": mth, "status": m_status,
                    "amount": round(sum(r.get("expected_amount") or 0 for r in m_gen), 2) if m_gen else expected_monthly,
                    "bill_no": (m_gen[0].get("bill_number") or m_gen[0].get("request_no")) if m_gen else
                               ((m_open[0].get("request_no")) if m_open else None),
                })
            pending_months = [m["month"] for m in month_rows if m["status"] == "pending"]
            pending_amount = round(sum(m["amount"] for m in month_rows if m["status"] == "pending"), 2)
            billing_period = month
            if month == ALL_MONTHS:
                billing_period = (f"{month_rows[0]['month']} → {month_rows[-1]['month']}"
                                  if month_rows else "All months")
                status = ("pending" if pending_months
                          else "requested" if any(m["status"] == "requested" for m in month_rows)
                          else "billed" if any(m["status"] == "billed" for m in month_rows)
                          else "out_of_period")
        else:
            pending_months = [] if status == "billed" else [month]
            pending_amount = 0.0 if status == "billed" else round(max(total_scope - billed_value, 0), 2)
            billing_period = " → ".join([x for x in [(p.get("start_date") or "")[:10],
                                                     (p.get("extended_end_date") or p.get("end_date") or "")[:10]] if x]) \
                or ("All months" if month == ALL_MONTHS else month)
        remarks: List[str] = []
        if status == "pending" and pending_days is not None:
            remarks.append(f"Pending {pending_days} day(s)")
        if len(pending_months) > 1:
            remarks.append(f"{len(pending_months)} month(s) pending: " + ", ".join(pending_months))
        if recurring and pending_months and not pending_amount:
            remarks.append("Monthly amount not set in Project Master")
        if not recurring and status == "pending" and not total_scope:
            remarks.append("Contract value not set")
        if status == "out_of_period":
            remarks.append("Outside project validity period")
        if open_req:
            remarks.append(f"Open bill request {open_req.get('request_no')} "
                           f"({(open_req.get('bill_nature') or open_req.get('bill_type') or '—')})")
        if payment_status == "partially_paid":
            remarks.append(f"Part payment received ₹{paid:,.0f}, balance ₹{balance:,.0f}")
        rows.append({
            "project_id": p.get("id"), "project_code": p.get("code"), "project_name": p.get("name"),
            "client": p.get("client"), "project_status": p.get("status"),
            "billing_type": btype, "effective_billing_type": effective,
            "project_category": category, "category_label": category_label(category),
            "billing_mode": "monthly" if recurring else "scope",
            "billing_period": billing_period,
            "expected_monthly": expected_monthly,
            "scope_value": total_scope,
            "months": month_rows,
            "pending_months": pending_months,
            "pending_months_count": len(pending_months),
            "pending_amount": pending_amount,
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
            "remarks": " · ".join(remarks),
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
                         order_type: Optional[str] = None, service_type: Optional[str] = None,
                         category: Optional[str] = None, project_code: Optional[str] = None) -> List[dict]:
    def ok(r):
        if status and r["billing_status"] != status:
            return False
        if category:
            if category == "unset" and r.get("project_category"):
                return False
            if category != "unset" and r.get("project_category") != category:
                return False
        if project_code and r.get("project_code") != project_code:
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
    return {"total": len(rows), **counts, "pending": counts.get("pending", 0),
            "pending_amount": round(sum(r.get("pending_amount") or 0 for r in rows), 2),
            "pending_months_total": sum(r.get("pending_months_count") or 0 for r in rows),
            "amc_arc": sum(1 for r in rows if r.get("project_category") == "amc_arc"),
            "scope": sum(1 for r in rows if r.get("billing_mode") == "scope")}


def month_wise_summary(rows: List[dict]) -> List[Dict[str, Any]]:
    """Overall month-wise pending billing — every pending month across all projects."""
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.get("billing_mode") == "monthly":
            for m in r.get("months") or []:
                if m["status"] != "pending":
                    continue
                b = buckets.setdefault(m["month"], {"month": m["month"], "projects": 0, "pending_amount": 0.0})
                b["projects"] += 1
                b["pending_amount"] = round(b["pending_amount"] + (m.get("amount") or 0), 2)
        elif (r.get("pending_amount") or 0) > 0 or r.get("billing_status") == "pending":
            # Scope projects sit in the month their timeline ends.
            m = ((r.get("billing_period") or "").split("→")[-1].strip()[:7]) or ""
            if len(m) != 7:
                m = (r.get("last_bill_at") or now_iso())[:7]
            b = buckets.setdefault(m, {"month": m, "projects": 0, "pending_amount": 0.0})
            b["projects"] += 1
            b["pending_amount"] = round(b["pending_amount"] + (r.get("pending_amount") or 0), 2)
    return sorted(buckets.values(), key=lambda x: x["month"])


@router.get("/billing/pending-report")
async def pending_report(month: Optional[str] = None, status: Optional[str] = None,
                         q: Optional[str] = None, project_manager: Optional[str] = None,
                         client: Optional[str] = None, billing_type: Optional[str] = None,
                         payment_status: Optional[str] = None, min_pending_days: Optional[int] = None,
                         period_from: Optional[str] = None, period_to: Optional[str] = None,
                         order_type: Optional[str] = None, service_type: Optional[str] = None,
                         category: Optional[str] = None, project_code: Optional[str] = None,
                         user: dict = Depends(require_permission("bill_requests", "read"))):
    month = month or now_iso()[:7]
    report = await build_pending_report(month, user=user, period_from=period_from, period_to=period_to)
    rows = apply_report_filters(report["rows"], status=status, q=q, project_manager=project_manager,
                                client=client, billing_type=billing_type,
                                payment_status=payment_status, min_pending_days=min_pending_days,
                                order_type=order_type, service_type=service_type,
                                category=category, project_code=project_code)
    return {"month": month, "rows": rows, "summary": _summarise(rows),
            "month_wise": month_wise_summary(rows),
            "categories": [{"value": k, "label": v} for k, v in CATEGORY_LABELS.items()],
            "projects": [{"code": r["project_code"], "name": r["project_name"]} for r in report["rows"]],
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
                                category: Optional[str] = None, project_code: Optional[str] = None,
                                user: dict = Depends(require_permission("bill_requests", "read"))):
    from fastapi import Response
    month = month or now_iso()[:7]
    report = await build_pending_report(month, user=user, period_from=period_from, period_to=period_to)
    rows = apply_report_filters(report["rows"], status=status, q=q, project_manager=project_manager,
                                client=client, billing_type=billing_type,
                                payment_status=payment_status, min_pending_days=min_pending_days,
                                order_type=order_type, service_type=service_type,
                                category=category, project_code=project_code)
    summary = _summarise(rows)
    months = month_wise_summary(rows)
    applied = [(lbl, str(val).replace("_", " ")) for lbl, val in [
        ("Billing Month", "All Months" if month == ALL_MONTHS else month),
        ("Search", q), ("Project", project_code), ("Project Category", category),
        ("Project Manager", project_manager), ("Client", client),
        ("Billing Type", billing_type), ("Billing Status", status),
        ("Payment Status", payment_status),
        ("Pending ≥ days", min_pending_days), ("WO/PO Type", order_type),
        ("Service Type", service_type), ("Service Period From", period_from),
        ("Service Period To", period_to)] if val not in (None, "")]
    if fmt == "pdf":
        from pdf_generator import render_billing_pending_pdf
        data = await run_blocking(render_billing_pending_pdf, rows, summary, month, months, applied)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="pending-billing-{month}.pdf"'})
    headers = ["Project Code", "Project Name", "Project Category", "Billing Mode",
               "Billing Month / Period", "Client", "Project Manager", "Pending Billing Status",
               "Pending Months", "Pending Months Count",
               "Pending Amount (₹)", "Expected Monthly (₹)", "Contract / Scope Value (₹)",
               "WO/PO Type", "Service Type",
               "Pending Days", "Last Bill No", "Last Bill Date", "Open Request",
               "Bills Generated", "Billed Basic (₹)", "GST (₹)", "Gross (₹)",
               "Paid (₹)", "Balance Due (₹)", "Payment Status", "Pending Remarks"]

    def line(r):
        return [r["project_code"], r["project_name"], r.get("category_label"),
                "Month-wise" if r.get("billing_mode") == "monthly" else "Scope / timeline",
                r.get("billing_period") or month, r["client"], r["project_manager"],
                r["billing_status"].replace("_", " ").title(),
                ", ".join(r.get("pending_months") or []) if r.get("billing_mode") == "monthly" else "",
                r.get("pending_months_count") or 0,
                r.get("pending_amount") or 0, r.get("expected_monthly") or 0,
                r.get("scope_value") or 0,
                (r.get("order_type") or "").replace("_", " ").title(),
                (r.get("service_type") or "").replace("_", " ").title(),
                r.get("pending_days"), r["last_bill_no"], (r["last_bill_at"] or "")[:10],
                r["open_request_no"], r["bills_generated"],
                r["billed_basic"], r["billed_gst"], r["billed_gross"],
                r["paid_amount"], r["balance_due"],
                (r["payment_status"] or "").replace("_", " ").title(),
                r.get("remarks") or ""]

    if fmt == "csv":
        import csv
        from io import StringIO
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["Pending Billing Report", "All Months" if month == ALL_MONTHS else month])
        w.writerow(["Filters applied"] + [f"{k}: {v}" for k, v in applied])
        w.writerow([])
        w.writerow(headers)
        for r in rows:
            w.writerow(["" if v is None else v for v in line(r)])
        w.writerow([])
        w.writerow(["Month-wise pending billing"])
        w.writerow(["Billing Month", "Projects Pending", "Pending Amount (₹)"])
        for m in months:
            w.writerow([m["month"], m["projects"], m["pending_amount"]])
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="pending-billing-{month}.csv"'})
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from io import BytesIO
    wb = Workbook()
    ws = wb.active
    ws.title = "Pending Billing" if month == ALL_MONTHS else f"Pending Billing {month}"
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F172A")
    for r in rows:
        ws.append(line(r))
    for i, w in enumerate([15, 28, 16, 16, 24, 22, 18, 18, 30, 10, 16, 16, 18, 14, 14,
                           12, 16, 12, 16, 8, 14, 12, 14, 14, 14, 14, 52], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ms = wb.create_sheet("Month-wise Pending")
    ms.append(["Billing Month", "Projects Pending", "Pending Amount (₹)"])
    for c in ms[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F172A")
    for m in months:
        ms.append([m["month"], m["projects"], m["pending_amount"]])
    for col, width in zip("ABC", (18, 18, 20)):
        ms.column_dimensions[col].width = width
    s = wb.create_sheet("Summary")
    s.append(["Billing Month", "All Months" if month == ALL_MONTHS else month])
    for k, v in summary.items():
        s.append([k.replace("_", " ").title(), v])
    s.append([])
    s.append(["Filters Applied"])
    for k, v in applied:
        s.append([k, v])
    s.column_dimensions["A"].width = 24
    s.column_dimensions["B"].width = 32
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
    per_project = await send_project_billing_reminders(
        month, queued_by=user.get("name") or user.get("email"), force=True)
    return {**res, "per_project": per_project}


# ─── Per-project reminder to the responsible Project Manager (Iter 206) ──────
ACCOUNTS_CC_ROLES = ["accounts_executive", "general_manager", "director"]
REMINDER_INTERVAL_DAYS = 7


async def _pm_email(row: Dict[str, Any]) -> Optional[str]:
    """Email of the project's responsible manager — by id, else by name."""
    if row.get("project_manager_id"):
        u = await db.users.find_one({"id": row["project_manager_id"]}, {"_id": 0, "email": 1})
        if (u or {}).get("email"):
            return u["email"]
    name = (row.get("project_manager") or "").strip()
    if name:
        u = await db.users.find_one({"name": name, "active": {"$ne": False}}, {"_id": 0, "email": 1})
        if (u or {}).get("email"):
            return u["email"]
    return None


def _project_reminder_html(row: Dict[str, Any], month: str) -> str:
    months = row.get("pending_months") or []
    monthly = row.get("billing_mode") == "monthly"
    period = ", ".join(months) if monthly and months else (row.get("billing_period") or month)
    rows_html = "".join(
        f"<tr><td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{m}</td>"
        f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right;font-weight:700;'>"
        f"₹ {float(row.get('expected_monthly') or 0):,.0f}</td>"
        f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;color:#b91c1c;font-weight:700;'>PENDING</td></tr>"
        for m in months) if monthly else (
        f"<tr><td style='padding:7px 10px;border-top:1px solid #e2e8f0;'>{period}</td>"
        f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right;font-weight:700;'>"
        f"₹ {float(row.get('pending_amount') or 0):,.0f}</td>"
        f"<td style='padding:7px 10px;border-top:1px solid #e2e8f0;color:#b91c1c;font-weight:700;'>"
        f"{(row.get('billing_status') or '').replace('_', ' ').upper()}</td></tr>")
    return f"""
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:760px;margin:0 auto;color:#0f172a;">
  <div style="background:#0f172a;color:#fff;padding:16px 20px;">
    <div style="font-size:11px;letter-spacing:0.15em;text-transform:uppercase;opacity:0.8;">Indian Trade Links · ERP</div>
    <div style="font-size:20px;font-weight:800;margin-top:4px;">Billing Pending — {row.get('project_name') or row.get('project_code')}</div>
  </div>
  <div style="padding:18px 20px;border:1px solid #e2e8f0;border-top:none;">
    <table style="font-size:13px;line-height:1.7;margin-bottom:12px;">
      <tr><td style="color:#64748b;padding-right:14px;">Project</td><td><b>{row.get('project_code')} — {row.get('project_name') or ''}</b></td></tr>
      <tr><td style="color:#64748b;padding-right:14px;">Project Category</td><td><b>{row.get('category_label') or '—'}</b>
        ({'recurring monthly billing' if monthly else 'scope / timeline billing'})</td></tr>
      <tr><td style="color:#64748b;padding-right:14px;">Client</td><td>{row.get('client') or '—'}</td></tr>
      <tr><td style="color:#64748b;padding-right:14px;">Pending Billing</td>
          <td style="color:#b91c1c;font-weight:800;">₹ {float(row.get('pending_amount') or 0):,.0f}</td></tr>
    </table>
    <table cellspacing="0" cellpadding="0" style="width:100%;border:1px solid #e2e8f0;font-size:12px;">
      <tr style="background:#f1f5f9;text-transform:uppercase;font-size:10px;letter-spacing:0.08em;color:#475569;">
        <th style="padding:8px 10px;text-align:left;">Billing Month / Period</th>
        <th style="padding:8px 10px;text-align:right;">Pending Amount</th>
        <th style="padding:8px 10px;text-align:left;">Status</th>
      </tr>{rows_html}
    </table>
    <p style="font-size:12px;line-height:1.6;margin-top:14px;">Dear {row.get('project_manager') or 'Project Manager'},<br/>
    please raise the Bill Generation Request for the period(s) above so Accounts can complete the billing.
    This reminder repeats every {REMINDER_INTERVAL_DAYS} days until the billing is completed.</p>
  </div>
</div>"""


async def send_project_billing_reminders(month: str, *, queued_by: str = "scheduler",
                                         force: bool = False) -> Dict[str, Any]:
    """One reminder per pending project to its PM, with Accounts + GM/Director in CC.
    Repeats every REMINDER_INTERVAL_DAYS until that project's billing is done."""
    from datetime import datetime, timedelta, timezone
    report = await build_pending_report(month, user=None)
    pending_rows = [r for r in report["rows"]
                    if (r.get("pending_amount") or 0) > 0 or r.get("billing_status") == "pending"]
    out = {"month": month, "projects": len(pending_rows), "sent": 0, "skipped": 0, "no_pm": 0}
    if not pending_rows:
        return out
    cc = sorted({u["email"] async for u in db.users.find(
        {"role": {"$in": ACCOUNTS_CC_ROLES}, "active": {"$ne": False}, "email": {"$ne": None}},
        {"_id": 0, "email": 1}) if u.get("email")})
    from routers.email_router import _queue_outbox, _send_and_log
    cutoff = (datetime.now(timezone.utc) - timedelta(days=REMINDER_INTERVAL_DAYS)).isoformat()
    for row in pending_rows:
        marker = {"project_code": row["project_code"], "month": month}
        last = await db.billing_reminders.find_one(marker, {"_id": 0, "last_sent_at": 1, "sent_count": 1})
        if last and not force and (last.get("last_sent_at") or "") > cutoff:
            out["skipped"] += 1
            continue
        pm = await _pm_email(row)
        to = [pm] if pm else cc
        if not pm:
            out["no_pm"] += 1
        if not to:
            out["skipped"] += 1
            continue
        periods = ", ".join(row.get("pending_months") or []) or (row.get("billing_period") or month)
        subject = (f"⏰ Billing pending — {row['project_code']} · {row.get('category_label')} · "
                   f"{periods} · ₹{float(row.get('pending_amount') or 0):,.0f}")
        outbox_id = await _queue_outbox(
            sender_type="system", sender_purpose="noreply",
            sender_user_id="", sender_email="", sender_display_name="ERP Billing Bot",
            to=to, cc=[e for e in cc if e not in to], bcc=[], subject=subject,
            body_text=f"{row['project_code']} ({row.get('category_label')}) — pending billing for {periods}: "
                      f"₹{float(row.get('pending_amount') or 0):,.0f}. Status: {row.get('billing_status')}.",
            body_html=_project_reminder_html(row, month),
            reply_to=None, attachments_inline=[], file_ids=[],
            related={"type": "billing_reminder_project", "project_code": row["project_code"], "month": month},
            queued_by=queued_by)
        import asyncio
        asyncio.create_task(_send_and_log(outbox_id))
        await db.billing_reminders.update_one(marker, {"$set": {
            **marker, "last_sent_at": now_iso(), "pending_months": row.get("pending_months") or [],
            "pending_amount": row.get("pending_amount"), "project_name": row.get("project_name"),
            "category": row.get("project_category"), "to": to, "cc": cc, "outbox_id": outbox_id,
        }, "$inc": {"sent_count": 1}}, upsert=True)
        out["sent"] += 1
    return out


@router.get("/billing/pending-report/reminder-log")
async def reminder_log(month: Optional[str] = None,
                       user: dict = Depends(require_permission("bill_requests", "read"))):
    q = {"month": month} if month else {}
    rows = await db.billing_reminders.find(q, {"_id": 0}).sort("last_sent_at", -1).to_list(500)
    return {"rows": rows, "total": len(rows)}
