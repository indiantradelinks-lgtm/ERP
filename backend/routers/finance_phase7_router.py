"""Finance Phase 7 — Management Dashboard + Cash Flow Forecast (Iter 114).

Audit-first finding: receivables dashboard, project profitability, approval
inbox, AR/AP aging — all already exist as scattered endpoints.  Missing is
the unified CFO landing page + 30-day forward cash-flow forecast.

Endpoints added:
  GET /finance/dashboard/summary
  GET /finance/dashboard/cashflow?days=30
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from core import db, require_permission

router = APIRouter(prefix="/finance/dashboard", tags=["finance-phase7"])


def _today():
    return datetime.now(timezone.utc).date()


def _to_str(d):
    return d.strftime("%Y-%m-%d") if d else None


# ═════════════════════════════════════════════════════════════════════════
# 1. UNIFIED SUMMARY KPIs
# ═════════════════════════════════════════════════════════════════════════
@router.get("/summary")
async def dashboard_summary(user: dict = Depends(require_permission("accounting", "read"))):
    today = _today()
    today_s = today.strftime("%Y-%m-%d")
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    next_m = today.replace(day=1) + timedelta(days=32)
    month_end = (next_m.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")

    # ─ Receivable ─
    ar_total = 0.0
    ar_overdue = 0.0
    async for inv in db.client_invoices.find(
        {"status": {"$in": ["approved", "sent"]}, "payment_status": {"$ne": "paid"}},
        {"_id": 0, "amount": 1, "total_amount": 1, "outstanding": 1, "due_date": 1},
    ):
        amt = float(inv.get("outstanding") or inv.get("amount") or inv.get("total_amount") or 0)
        ar_total += amt
        if (inv.get("due_date") or "9999-12-31") < today_s:
            ar_overdue += amt

    # ─ Payable ─
    ap_total = 0.0
    ap_overdue = 0.0
    async for vb in db.vendor_bills.find(
        {"status": "approved", "payment_status": {"$ne": "paid"}},
        {"_id": 0, "amount": 1, "total_amount": 1, "outstanding": 1, "due_date": 1},
    ):
        amt = float(vb.get("outstanding") or vb.get("amount") or vb.get("total_amount") or 0)
        ap_total += amt
        if (vb.get("due_date") or "9999-12-31") < today_s:
            ap_overdue += amt

    # ─ Bank + Cash balance (sum of bank/cash account balances from journal entries) ─
    bank_codes = ["1100", "1110", "1120", "1130", "1140", "1150"]  # bank
    cash_codes = ["1000"]
    bank_balance = 0.0
    cash_balance = 0.0
    async for je in db.journal_entries.find(
        {"lines.account_code": {"$in": bank_codes + cash_codes}},
        {"_id": 0, "lines": 1},
    ):
        for ln in je.get("lines") or []:
            c = ln.get("account_code")
            net = float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
            if c in bank_codes:
                bank_balance += net
            elif c in cash_codes:
                cash_balance += net

    # ─ This month billing/collection/expense ─
    this_billing = 0.0
    async for inv in db.client_invoices.find(
        {"status": {"$in": ["approved", "sent", "paid"]},
         "invoice_date": {"$gte": month_start, "$lte": month_end}},
        {"_id": 0, "amount": 1, "total_amount": 1},
    ):
        this_billing += float(inv.get("amount") or inv.get("total_amount") or 0)

    this_collection = 0.0
    async for je in db.journal_entries.find(
        {"date": {"$gte": month_start, "$lte": month_end},
         "source_module": {"$in": ["customer_receipt", "client_receipt", "receivable_payment"]}},
        {"_id": 0, "total_debit": 1},
    ):
        this_collection += float(je.get("total_debit") or 0)

    this_expense = 0.0
    async for vb in db.vendor_bills.find(
        {"status": "approved",
         "bill_date": {"$gte": month_start, "$lte": month_end}},
        {"_id": 0, "amount": 1, "total_amount": 1, "gross_amount": 1},
    ):
        this_expense += float(vb.get("amount") or vb.get("total_amount") or vb.get("gross_amount") or 0)

    # ─ Pending approvals ─
    pending_approvals = {
        "client_invoices": await db.client_invoices.count_documents({"status": {"$in": ["pending_approval", "draft"]}}),
        "vendor_bills": await db.vendor_bills.count_documents({"status": {"$in": ["pending_verification", "pending_approval", "submitted"]}}),
        "journal_entries": await db.journal_entries.count_documents({"status": "pending_approval"}),
        "advances": await db.employee_advances.count_documents({"status": {"$in": ["pending_approval", "submitted"]}}),
        "credit_debit_notes": await db.finance_notes.count_documents({"status": "pending_approval"}),
    }
    pending_total = sum(pending_approvals.values())

    # ─ Statutory payable (current period) ─
    last_period_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d")
    last_period_end = today.replace(day=1).strftime("%Y-%m-%d")
    stat_codes = {"2220": "pf", "2230": "esic", "2400": "tds", "2300": "gst_output", "1700": "gst_input"}
    stat = {v: 0.0 for v in set(stat_codes.values()) | {"gst_payable"}}
    async for je in db.journal_entries.find(
        {"date": {"$gte": last_period_start, "$lt": last_period_end}, "lines.account_code": {"$in": list(stat_codes.keys())}},
        {"_id": 0, "lines": 1},
    ):
        for ln in je.get("lines") or []:
            code = ln.get("account_code")
            if code in stat_codes:
                key = stat_codes[code]
                stat[key] += float(ln.get("credit") or 0) - float(ln.get("debit") or 0)
    stat["gst_payable"] = round(stat.get("gst_output", 0) - stat.get("gst_input", 0), 2)
    for k in stat:
        stat[k] = round(stat[k], 2)

    net_cash = round(bank_balance + cash_balance - ap_overdue, 2)

    return {
        "as_of": today_s,
        "receivable": {"total": round(ar_total, 2), "overdue": round(ar_overdue, 2)},
        "payable": {"total": round(ap_total, 2), "overdue": round(ap_overdue, 2)},
        "balances": {"bank": round(bank_balance, 2), "cash": round(cash_balance, 2),
                     "total": round(bank_balance + cash_balance, 2)},
        "this_month": {"billing": round(this_billing, 2), "collection": round(this_collection, 2),
                       "expense": round(this_expense, 2),
                       "start": month_start, "end": month_end},
        "net_cash_position": net_cash,
        "pending_approvals": {**pending_approvals, "total": pending_total},
        "statutory_payable": stat,
    }


# ═════════════════════════════════════════════════════════════════════════
# 2. 30-DAY CASH FLOW FORECAST
# ═════════════════════════════════════════════════════════════════════════
@router.get("/cashflow")
async def cashflow_forecast(
    days: int = Query(30, ge=7, le=180),
    user: dict = Depends(require_permission("accounting", "read")),
):
    today = _today()
    end_date = today + timedelta(days=days)
    today_s = today.strftime("%Y-%m-%d")
    end_s = end_date.strftime("%Y-%m-%d")

    # ─ Expected inflow: client invoices due in range ─
    inflows: List[Dict[str, Any]] = []
    async for inv in db.client_invoices.find(
        {"status": {"$in": ["approved", "sent"]},
         "payment_status": {"$ne": "paid"},
         "due_date": {"$gte": today_s, "$lte": end_s}},
        {"_id": 0, "invoice_number": 1, "client_name": 1, "due_date": 1, "amount": 1,
         "outstanding": 1, "total_amount": 1, "project_id": 1},
    ):
        amt = float(inv.get("outstanding") or inv.get("amount") or inv.get("total_amount") or 0)
        if amt > 0:
            inflows.append({
                "date": inv.get("due_date"),
                "kind": "client_receipt",
                "party": inv.get("client_name"),
                "ref": inv.get("invoice_number"),
                "amount": round(amt, 2),
            })

    # ─ Expected outflow: vendor bills + salary + statutory + advances ─
    outflows: List[Dict[str, Any]] = []
    async for vb in db.vendor_bills.find(
        {"status": "approved", "payment_status": {"$ne": "paid"},
         "due_date": {"$gte": today_s, "$lte": end_s}},
        {"_id": 0, "invoice_no": 1, "bill_number": 1, "vendor_name": 1,
         "due_date": 1, "amount": 1, "outstanding": 1, "total_amount": 1, "project_id": 1},
    ):
        amt = float(vb.get("outstanding") or vb.get("amount") or vb.get("total_amount") or 0)
        if amt > 0:
            outflows.append({
                "date": vb.get("due_date"),
                "kind": "vendor_payment",
                "party": vb.get("vendor_name"),
                "ref": vb.get("invoice_no") or vb.get("bill_number"),
                "amount": round(amt, 2),
            })

    # ─ Salary due (next 1st of every month within window) ─
    cursor = today.replace(day=1)
    while cursor <= end_date:
        if cursor >= today:
            # Estimate salary = last paid payroll run total (or projection)
            last_run = await db.payroll_runs.find_one({"status": "paid"}, {"_id": 0, "total_net": 1, "total_payable": 1, "total_amount": 1}, sort=[("created_at", -1)])
            est = float((last_run or {}).get("total_net") or (last_run or {}).get("total_payable") or (last_run or {}).get("total_amount") or 0)
            if est > 0:
                outflows.append({
                    "date": cursor.strftime("%Y-%m-%d"),
                    "kind": "salary",
                    "party": "All employees",
                    "ref": f"Monthly payroll ~ {cursor.strftime('%b %Y')}",
                    "amount": round(est, 2),
                })
        # next month
        nxt = cursor.replace(day=28) + timedelta(days=4)
        cursor = nxt.replace(day=1)

    # ─ Statutory due (next due dates from compliance calendar) ─
    async for ci in db.compliance_items.find(
        {"status": {"$ne": "paid"}, "due_date": {"$gte": today_s, "$lte": end_s}, "amount": {"$gt": 0}},
        {"_id": 0, "kind": 1, "label": 1, "due_date": 1, "amount": 1},
    ):
        outflows.append({
            "date": ci["due_date"],
            "kind": "statutory",
            "party": ci.get("label") or ci.get("kind"),
            "ref": ci.get("kind"),
            "amount": float(ci.get("amount") or 0),
        })

    inflows.sort(key=lambda x: x["date"])
    outflows.sort(key=lambda x: x["date"])

    total_in = round(sum(r["amount"] for r in inflows), 2)
    total_out = round(sum(r["amount"] for r in outflows), 2)

    # ─ Net by day (for chart) ─
    by_day: Dict[str, Dict[str, float]] = {}
    for r in inflows:
        d = r["date"]
        by_day.setdefault(d, {"in": 0, "out": 0})
        by_day[d]["in"] += r["amount"]
    for r in outflows:
        d = r["date"]
        by_day.setdefault(d, {"in": 0, "out": 0})
        by_day[d]["out"] += r["amount"]
    timeline = [{"date": d, "in": round(v["in"], 2), "out": round(v["out"], 2),
                 "net": round(v["in"] - v["out"], 2)}
                for d, v in sorted(by_day.items())]

    return {
        "from": today_s, "to": end_s, "days": days,
        "total_expected_inflow": total_in,
        "total_expected_outflow": total_out,
        "net_projected": round(total_in - total_out, 2),
        "inflows": inflows,
        "outflows": outflows,
        "timeline": timeline,
    }
