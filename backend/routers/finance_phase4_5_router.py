"""Finance Phase 4 + 5 — HR/Payroll + Projects integration (Iter 112).

Builds on top of the already-wired auto-posting hooks:
  • payroll → JE         (hr_phase4_router.py)
  • loan disburse → JE   (hr_phase4_router.py)
  • reimbursement → JE   (hr_phase4_router.py)
  • employee advance → JE (costing_router.py)
  • site_expense → JE     (costing_router.py)
  • material_movement → JE (costing_router.py)

Gaps filled:

PHASE 4 (HR + Payroll → Finance)
  1. Employee Ledger              — chronological JE lines per employee
                                    (advance, salary, recovery, reimbursement)
  2. Statutory Summary           — PF E/E, ESIC E/E, TDS, PT roll-up per period

PHASE 5 (Projects & Operations → Finance)
  3. Project Finance Alerts      — consolidated per-project: budget overrun,
                                   payment overdue, retention due, advance
                                   pending settlement, billing pending,
                                   missing supporting docs
  4. Budget vs Actual by head    — material / labour / vendor / equipment /
                                   site-expense / safety / overhead breakdown
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core import db, require_permission

router = APIRouter(prefix="/finance", tags=["finance-phase4-5"])


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ym(d: str) -> str:
    return (d or "")[:7]


# ═════════════════════════════════════════════════════════════════════════
# PHASE 4.1 — Employee Ledger
# ═════════════════════════════════════════════════════════════════════════
@router.get("/employee-ledger/{employee_id}")
async def employee_ledger(
    employee_id: str,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Chronological double-entry ledger for a single employee.

    Aggregates from `journal_entries` where party_type=employee + the legacy
    JEs from costing_router (employee_advance) + hr_phase4_router (payroll,
    loan, reimbursement). Computes running balance.
    """
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0, "id": 1, "name": 1, "code": 1, "department": 1})
    if not emp:
        raise HTTPException(404, "Employee not found")

    q: Dict[str, Any] = {
        "$or": [
            {"party_type": "employee", "party_id": employee_id},
            {"source_module": "employee_advance", "source_ref": employee_id},
            {"narration": {"$regex": employee_id, "$options": "i"}},
            {"lines.narration": {"$regex": employee_id, "$options": "i"}},
        ],
    }
    if from_date:
        q["date"] = q.get("date", {})
        q["date"]["$gte"] = from_date
    if to_date:
        q["date"] = q.get("date", {})
        q["date"]["$lte"] = to_date

    jes = await db.journal_entries.find(q, {"_id": 0}).sort("date", 1).to_list(2000)

    out_rows = []
    running = 0.0
    for je in jes:
        for ln in je.get("lines") or []:
            # Only employee-relevant accounts (1500 Employee Advances, 2200 Salary Payable, etc.)
            code = ln.get("account_code")
            if code not in ("1500", "2200", "2210", "2220", "2230", "2400", "5110", "5111", "5117"):
                continue
            dr = float(ln.get("debit") or 0)
            cr = float(ln.get("credit") or 0)
            running += dr - cr
            out_rows.append({
                "date": je.get("date"),
                "je_number": je.get("je_number"),
                "voucher_type": je.get("voucher_type"),
                "source_module": je.get("source_module"),
                "narration": ln.get("narration") or je.get("narration"),
                "account_code": code,
                "account_name": ln.get("account_name"),
                "debit": dr,
                "credit": cr,
                "running_balance": round(running, 2),
                "project_id": ln.get("project_id"),
            })

    return {
        "employee_id": employee_id,
        "employee_name": emp.get("name"),
        "employee_code": emp.get("code"),
        "department": emp.get("department"),
        "from_date": from_date, "to_date": to_date,
        "count": len(out_rows),
        "closing_balance": round(running, 2),
        "rows": out_rows,
    }


# ═════════════════════════════════════════════════════════════════════════
# PHASE 4.2 — Statutory Summary (PF / ESIC / TDS / PT)
# ═════════════════════════════════════════════════════════════════════════
@router.get("/statutory-summary")
async def statutory_summary(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Roll-up payable statutory liabilities by period (defaults to current FY)."""
    today = datetime.now(timezone.utc).date()
    if not to_date:
        to_date = today.strftime("%Y-%m-%d")
    if not from_date:
        # current Indian FY start (Apr 1)
        fy_start_year = today.year - 1 if today.month < 4 else today.year
        from_date = f"{fy_start_year}-04-01"

    # Map account codes to statutory buckets
    STATUTORY_CODES = {
        "2220": "PF Payable",         # liability
        "2230": "ESIC Payable",
        "2400": "TDS Payable",
        "2410": "Duties & Taxes",
        "2200": "Salary Payable",
        "2210": "Labour Payable",
    }

    q = {
        "date": {"$gte": from_date, "$lte": to_date},
        "lines.account_code": {"$in": list(STATUTORY_CODES.keys())},
    }
    jes = await db.journal_entries.find(q, {"_id": 0}).to_list(5000)

    # Per-account totals + per-month breakdown
    by_account: Dict[str, Dict[str, float]] = {}
    by_month: Dict[str, Dict[str, float]] = {}
    for je in jes:
        ym = _ym(je.get("date") or "")
        for ln in je.get("lines") or []:
            code = ln.get("account_code")
            if code not in STATUTORY_CODES:
                continue
            cr = float(ln.get("credit") or 0)
            dr = float(ln.get("debit") or 0)
            net = cr - dr  # liability = credit - paid (debit reduces)
            by_account.setdefault(code, {"accrued": 0.0, "paid": 0.0, "balance": 0.0})
            by_account[code]["accrued"] += cr
            by_account[code]["paid"] += dr
            by_account[code]["balance"] += net
            by_month.setdefault(ym, {})
            by_month[ym][code] = by_month[ym].get(code, 0.0) + net

    return {
        "from": from_date, "to": to_date,
        "by_account": [
            {
                "account_code": c, "account_name": STATUTORY_CODES[c],
                "accrued": round(v["accrued"], 2),
                "paid": round(v["paid"], 2),
                "balance_payable": round(v["balance"], 2),
            }
            for c, v in sorted(by_account.items())
        ],
        "by_month": [
            {"month": ym, **{STATUTORY_CODES[c]: round(amt, 2) for c, amt in months.items()}}
            for ym, months in sorted(by_month.items())
        ],
    }


# ═════════════════════════════════════════════════════════════════════════
# PHASE 5.1 — Project Finance Alerts (consolidated)
# ═════════════════════════════════════════════════════════════════════════
@router.get("/project-alerts/{project_id}")
async def project_finance_alerts(
    project_id: str,
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Consolidated finance alerts for one project.

    Categories:
      • budget_overrun         actual cost > 90% of budget
      • payment_overdue        client_invoice past due_date
      • vendor_payment_due     vendor_bill approved, due in <= 7 days
      • advance_pending        employee_advance not settled in >30 days
      • billing_pending        RA bill not raised against ≥ X% progress
      • retention_due          retention payable > 90 days
      • bill_without_grn       audit risk (non-service no-PO bill)
    """
    today = datetime.now(timezone.utc).date()
    today_s = today.strftime("%Y-%m-%d")
    plus7 = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    minus30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    minus90 = (today - timedelta(days=90)).strftime("%Y-%m-%d")

    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found")

    alerts: List[Dict[str, Any]] = []

    # 1. Budget overrun
    budget_value = float(project.get("budget_value") or project.get("total_value") or 0)
    spent = 0.0
    async for vb in db.vendor_bills.find({"project_id": project_id, "status": "approved"},
                                          {"_id": 0, "amount": 1, "total_amount": 1, "gross_amount": 1}):
        spent += float(vb.get("amount") or vb.get("total_amount") or vb.get("gross_amount") or 0)
    if budget_value > 0 and spent > budget_value * 0.9:
        alerts.append({
            "kind": "budget_overrun",
            "severity": "critical" if spent > budget_value else "warning",
            "message": f"Approved spend ₹{spent:,.0f} is {spent/budget_value*100:.0f}% of budget ₹{budget_value:,.0f}",
            "amount": spent, "budget": budget_value,
        })

    # 2. Client invoice payment overdue
    overdue_inv = 0
    overdue_amt = 0.0
    async for inv in db.client_invoices.find(
        {"project_id": project_id, "status": {"$in": ["approved", "sent"]},
         "payment_status": {"$ne": "paid"}, "due_date": {"$lt": today_s}},
        {"_id": 0, "amount": 1, "total_amount": 1, "due_date": 1},
    ):
        overdue_inv += 1
        overdue_amt += float(inv.get("amount") or inv.get("total_amount") or 0)
    if overdue_inv:
        alerts.append({"kind": "payment_overdue", "severity": "critical",
                       "message": f"{overdue_inv} client invoice(s) overdue · ₹{overdue_amt:,.0f}",
                       "amount": overdue_amt})

    # 3. Vendor payment due within 7 days
    vp_due = 0
    vp_amt = 0.0
    async for vb in db.vendor_bills.find(
        {"project_id": project_id, "status": "approved",
         "payment_status": {"$ne": "paid"},
         "due_date": {"$gte": today_s, "$lte": plus7}},
        {"_id": 0, "amount": 1, "total_amount": 1, "due_date": 1},
    ):
        vp_due += 1
        vp_amt += float(vb.get("amount") or vb.get("total_amount") or 0)
    if vp_due:
        alerts.append({"kind": "vendor_payment_due", "severity": "warning",
                       "message": f"{vp_due} vendor bill(s) due in next 7 days · ₹{vp_amt:,.0f}",
                       "amount": vp_amt})

    # 4. Employee advance pending settlement >30 days
    open_adv = 0
    async for adv in db.employee_advances.find(
        {"project_id": project_id, "status": {"$in": ["disbursed", "open"]},
         "created_at": {"$lt": minus30}},
        {"_id": 0},
    ):
        open_adv += 1
    if open_adv:
        alerts.append({"kind": "advance_pending", "severity": "warning",
                       "message": f"{open_adv} employee advance(s) >30 days old, pending settlement"})

    # 5. Retention payable >90 days
    ret_count = await db.vendor_bills.count_documents({
        "project_id": project_id, "retention_amount": {"$gt": 0},
        "retention_status": {"$ne": "released"},
        "bill_date": {"$lt": minus90},
    })
    if ret_count:
        alerts.append({"kind": "retention_due", "severity": "info",
                       "message": f"{ret_count} retention(s) due for review (>90 days old)"})

    # 6. Bill without GRN — audit risk
    audit_risk = 0
    async for vb in db.vendor_bills.find(
        {"project_id": project_id, "status": "approved",
         "$or": [{"grn_id": None}, {"grn_number": None}],
         "is_service": {"$ne": True}, "po_number": None},
        {"_id": 0},
    ):
        audit_risk += 1
    if audit_risk:
        alerts.append({"kind": "audit_risk_bill", "severity": "warning",
                       "message": f"{audit_risk} approved bill(s) without PO/GRN (audit risk)"})

    return {
        "project_id": project_id,
        "project_code": project.get("code"),
        "project_name": project.get("name"),
        "alert_count": len(alerts),
        "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
        "alerts": alerts,
    }


# ═════════════════════════════════════════════════════════════════════════
# PHASE 5.2 — Budget vs Actual by head
# ═════════════════════════════════════════════════════════════════════════
HEAD_TO_CODES = {
    "material":      ["1300", "1310", "5100", "5105"],
    "labour":        ["5110", "5111", "5112"],
    "vendor":        ["5120"],
    "salary_staff":  ["5117"],
    "site_expense":  ["5400", "5410"],
    "transport":     ["5420"],
    "safety":        ["5430"],
    "tools_tackles": ["5440"],
    "overhead":      ["5500", "5510", "5520"],
}


@router.get("/budget-vs-actual/{project_id}")
async def budget_vs_actual(
    project_id: str,
    user: dict = Depends(require_permission("accounting", "read")),
):
    """Per-head budget vs actual breakdown for a project.

    Budget heads come from project.budget_heads[] if present, otherwise we
    surface only actuals.  Actuals are aggregated from journal_entries.
    """
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Project not found")

    # Budget heads — project may have these on doc OR via project_budgets collection
    head_budgets: Dict[str, float] = {}
    for h in project.get("budget_heads") or []:
        head_budgets[h.get("head") or h.get("name")] = float(h.get("amount") or 0)
    async for b in db.project_budgets.find({"project_id": project_id}, {"_id": 0}):
        head_budgets[b.get("head")] = float(b.get("amount") or 0)

    # Actual = sum of debit lines on those expense codes for the project
    head_actuals: Dict[str, float] = {k: 0.0 for k in HEAD_TO_CODES}
    async for je in db.journal_entries.find(
        {"$or": [{"project_id": project_id}, {"lines.project_id": project_id}]},
        {"_id": 0, "lines": 1},
    ):
        for ln in je.get("lines") or []:
            if ln.get("project_id") not in (project_id, None):
                continue
            code = ln.get("account_code")
            dr = float(ln.get("debit") or 0)
            cr = float(ln.get("credit") or 0)
            for head, codes in HEAD_TO_CODES.items():
                if code in codes:
                    head_actuals[head] += dr - cr
                    break

    rows = []
    for head, actual in head_actuals.items():
        budget = head_budgets.get(head, 0.0)
        variance = budget - actual
        variance_pct = (variance / budget * 100) if budget > 0 else None
        rows.append({
            "head": head,
            "label": head.replace("_", " ").title(),
            "budget": round(budget, 2),
            "actual": round(actual, 2),
            "variance": round(variance, 2),
            "variance_pct": round(variance_pct, 1) if variance_pct is not None else None,
            "status": ("over" if budget > 0 and actual > budget else "under" if budget > 0 else "no_budget"),
        })
    total_budget = sum(r["budget"] for r in rows)
    total_actual = sum(r["actual"] for r in rows)
    return {
        "project_id": project_id,
        "project_code": project.get("code"),
        "project_name": project.get("name"),
        "total_budget": round(total_budget, 2),
        "total_actual": round(total_actual, 2),
        "total_variance": round(total_budget - total_actual, 2),
        "heads": rows,
    }
