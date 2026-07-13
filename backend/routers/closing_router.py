"""Phase 5 — Project Profitability, Balance Sheet, Cash Flow, Period Lock, Alerts, Export
==========================================================================================
Routes under `/api/closing/*`.

Consolidates approved-only data from every Phase 2-4 collection:
  • client_invoices (revenue)            • vendor_bills (cost)
  • client_receipts (collection)         • vendor_payments (payment)
  • site_expenses (project cost)         • journal_entries (payroll + material)
  • projects (budget vs actual)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from io import StringIO
import csv
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit
from accounting_service import trial_balance, profit_and_loss

router = APIRouter(prefix="/closing", tags=["Closing, Profitability & Controls"])


# ════════════════════════════════════════════════════════════════════════
# 1. PROJECT PROFITABILITY
# ════════════════════════════════════════════════════════════════════════
@router.get("/project-profitability")
async def project_profitability(
    user: dict = Depends(require_permission("accounting", "read"))
):
    """One unified row per project with full revenue + cost + P&L breakdown.

    Source-of-truth rules (approved-only):
      • Revenue: client_invoices.status ∈ {approved, partially_paid, paid}
      • Collection: client_receipts (all rows are posted by design)
      • Material/Payroll cost: journal_entries with source_module in (material_movement, payroll), source_event='issue' for material
      • Site expense: site_expenses.status='approved'
      • Vendor cost: vendor_bills.status ∈ {approved, partially_paid, paid}
    """
    proj_map: Dict[str, Dict[str, Any]] = {}

    def ensure(key: str, name: str = "") -> Dict[str, Any]:
        if not key:
            key = "—"
        return proj_map.setdefault(key, {
            "project_id": key, "project_code": key, "project_name": name,
            "wo_value": 0.0, "budget": 0.0,
            "revenue_invoiced": 0.0, "revenue_collected": 0.0,
            "tds_deducted": 0.0, "retention_held": 0.0,
            "outstanding_receivable": 0.0, "unbilled_work": 0.0,
            "extra_work": 0.0, "mobilization_advance": 0.0,
            "cost_material": 0.0, "cost_labour": 0.0, "cost_site": 0.0,
            "cost_vendor": 0.0, "cost_logistics": 0.0, "cost_safety": 0.0,
            "cost_subcontract": 0.0, "cost_other": 0.0,
            "total_cost": 0.0, "gross_profit": 0.0, "net_profit": 0.0,
            "profit_pct": 0.0, "status": "—",
            "pending_billing": 0.0, "pending_vendor_payment": 0.0,
        })

    # Seed from projects collection (budget, name, wo_value if present)
    async for p in db.projects.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1,
                                          "budget": 1, "contract_value": 1, "wo_value": 1}):
        key = p.get("code") or p.get("id")
        row = ensure(key, p.get("name") or "")
        row["project_id"] = p.get("id") or key
        row["wo_value"] = float(p.get("wo_value") or p.get("contract_value") or 0)
        row["budget"] = float(p.get("budget") or row["wo_value"] or 0)

    # Revenue from client_invoices
    async for inv in db.client_invoices.find(
        {"status": {"$in": ["approved", "partially_paid", "paid"]}},
        {"_id": 0, "project_id": 1, "project_code": 1, "totals": 1,
         "outstanding": 1, "invoice_type": 1}
    ):
        key = inv.get("project_code") or inv.get("project_id") or "—"
        if key == "—":
            continue
        row = ensure(key)
        gross = float((inv.get("totals") or {}).get("gross_value") or 0)
        row["revenue_invoiced"] += gross
        row["outstanding_receivable"] += float(inv.get("outstanding") or 0)
        if inv.get("invoice_type") == "EXTRA":
            row["extra_work"] += gross
        elif inv.get("invoice_type") == "MOB":
            row["mobilization_advance"] += gross

    # Collection + TDS + Retention from receipts
    async for r in db.client_receipts.find({}, {"_id": 0, "project_id": 1, "amount": 1,
                                                 "tds_deducted": 1, "retention_deducted": 1,
                                                 "total_adjusted": 1, "client_name": 1}):
        pid = r.get("project_id")
        # Receipts don't always carry project_code, so we resolve via invoices
        if not pid:
            continue
        # Find the project_code for this project_id from existing rows
        key = next((k for k, v in proj_map.items() if v["project_id"] == pid), pid)
        row = ensure(key)
        row["revenue_collected"] += float(r.get("total_adjusted") or 0)
        row["tds_deducted"] += float(r.get("tds_deducted") or 0)
        row["retention_held"] += float(r.get("retention_deducted") or 0)

    # Vendor cost
    async for b in db.vendor_bills.find(
        {"status": {"$in": ["approved", "partially_paid", "paid"]}},
        {"_id": 0, "project_id": 1, "project_code": 1, "totals": 1, "outstanding": 1,
         "expense_category": 1, "is_inventory": 1}
    ):
        key = b.get("project_code") or b.get("project_id") or "—"
        if key == "—":
            continue
        row = ensure(key)
        amt = float((b.get("totals") or {}).get("gross") or 0)
        cat = (b.get("expense_category") or "").lower()
        if cat in {"material", "inventory", "project_material"} or b.get("is_inventory"):
            row["cost_material"] += amt
        elif cat in {"labour", "subcontract"}:
            row["cost_subcontract"] += amt
        elif cat in {"fuel", "vehicle", "loading"}:
            row["cost_logistics"] += amt
        elif cat == "safety":
            row["cost_safety"] += amt
        else:
            row["cost_vendor"] += amt
        row["pending_vendor_payment"] += float(b.get("outstanding") or 0)

    # Site expenses (approved)
    async for e in db.site_expenses.find(
        {"status": "approved"},
        {"_id": 0, "project_id": 1, "project_code": 1, "category": 1, "amount": 1}
    ):
        key = e.get("project_code") or e.get("project_id") or "—"
        if key == "—":
            continue
        row = ensure(key)
        amt = float(e.get("amount") or 0)
        cat = e.get("category") or ""
        if cat == "vehicle_expense":
            row["cost_logistics"] += amt
        elif cat in {"safety_items", "labour_welfare"}:
            row["cost_safety"] += amt
        else:
            row["cost_site"] += amt

    # Payroll + Material from JEs
    async for j in db.journal_entries.find(
        {"source_module": {"$in": ["payroll", "material_movement"]},
         "project_id": {"$ne": None}, "status": "posted"},
        {"_id": 0, "project_id": 1, "total_debit": 1, "source_module": 1, "source_event": 1}
    ):
        pid = j["project_id"]
        key = next((k for k, v in proj_map.items() if v["project_id"] == pid), pid)
        row = ensure(key)
        amt = float(j.get("total_debit") or 0)
        if j["source_module"] == "payroll":
            row["cost_labour"] += amt
        elif j["source_module"] == "material_movement":
            if j.get("source_event") == "issue":
                row["cost_material"] += amt
            elif j.get("source_event") == "return":
                row["cost_material"] -= amt

    # Compute profitability for every row
    for row in proj_map.values():
        row["total_cost"] = round(
            row["cost_material"] + row["cost_labour"] + row["cost_site"] +
            row["cost_vendor"] + row["cost_logistics"] + row["cost_safety"] +
            row["cost_subcontract"] + row["cost_other"], 2)
        row["gross_profit"] = round(row["revenue_invoiced"] - row["total_cost"], 2)
        row["net_profit"] = row["gross_profit"]  # no overhead split in phase-5
        row["profit_pct"] = round(
            (row["net_profit"] / row["revenue_invoiced"] * 100) if row["revenue_invoiced"] else 0, 2)
        row["pending_billing"] = round(max(row["wo_value"] - row["revenue_invoiced"], 0), 2)
        row["unbilled_work"] = row["pending_billing"]

        # Risk classification
        if row["wo_value"] and row["total_cost"] > row["wo_value"] * 1.0:
            row["status"] = "loss"
        elif row["budget"] and row["total_cost"] > row["budget"] * 0.9:
            row["status"] = "at_risk"
        elif row["net_profit"] > 0:
            row["status"] = "profitable"
        elif row["revenue_invoiced"] == 0 and row["total_cost"] == 0:
            row["status"] = "idle"
        else:
            row["status"] = "loss" if row["net_profit"] < 0 else "neutral"

    # Round all monetary fields
    for row in proj_map.values():
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = round(v, 2)

    return {"projects": sorted(proj_map.values(), key=lambda x: -x["net_profit"]),
            "summary": {
                "total_revenue": round(sum(r["revenue_invoiced"] for r in proj_map.values()), 2),
                "total_cost":    round(sum(r["total_cost"] for r in proj_map.values()), 2),
                "total_profit":  round(sum(r["net_profit"] for r in proj_map.values()), 2),
                "projects_count": len(proj_map),
                "profitable_count": sum(1 for r in proj_map.values() if r["status"] == "profitable"),
                "at_risk_count":    sum(1 for r in proj_map.values() if r["status"] == "at_risk"),
                "loss_count":       sum(1 for r in proj_map.values() if r["status"] == "loss"),
            }}


# ════════════════════════════════════════════════════════════════════════
# 2. BALANCE SHEET
# ════════════════════════════════════════════════════════════════════════
@router.get("/reports/balance-sheet")
async def balance_sheet(as_of: Optional[str] = None,
                        user: dict = Depends(require_permission("accounting", "read"))):
    """Balance sheet computed from trial-balance.
    Assets section uses positive balances on asset codes.
    Liabilities use credit balances. Equity is computed implicitly as Δ.
    """
    tb_rows = await trial_balance(end=as_of)
    assets, liabilities, equity = [], [], []
    asset_total = liability_total = equity_total = 0.0
    pl = await profit_and_loss(end=as_of)
    pnl = float(pl.get("net_profit") or 0)

    for r in tb_rows:
        bal = float(r.get("balance") or 0)
        if r["type"] == "asset":
            # Asset: DR balance is positive
            assets.append({"code": r["code"], "name": r["name"], "amount": round(bal, 2)})
            asset_total += bal
        elif r["type"] == "liability":
            liabilities.append({"code": r["code"], "name": r["name"], "amount": round(abs(bal), 2)})
            liability_total += abs(bal)
        elif r["type"] == "equity":
            equity.append({"code": r["code"], "name": r["name"], "amount": round(abs(bal), 2)})
            equity_total += abs(bal)
    equity.append({"code": "PNL", "name": "Current Period P&L", "amount": round(pnl, 2)})
    equity_total += pnl
    return {
        "as_of": as_of or now_iso()[:10],
        "assets": {"rows": assets, "total": round(asset_total, 2)},
        "liabilities": {"rows": liabilities, "total": round(liability_total, 2)},
        "equity": {"rows": equity, "total": round(equity_total, 2)},
        "balanced": abs(asset_total - (liability_total + equity_total)) < 1.0,
        "balance_diff": round(asset_total - (liability_total + equity_total), 2),
    }


# ════════════════════════════════════════════════════════════════════════
# 3. CASH FLOW STATEMENT (simple direct method)
# ════════════════════════════════════════════════════════════════════════
@router.get("/reports/cash-flow")
async def cash_flow(start: Optional[str] = None, end: Optional[str] = None,
                    user: dict = Depends(require_permission("accounting", "read"))):
    """Cash inflows minus outflows on bank/cash codes."""
    cash_codes = {"1100", "1101", "1110", "1115"}
    q: Dict[str, Any] = {"status": "posted"}
    if start:
        q["date"] = {**q.get("date", {}), "$gte": start}
    if end:
        q["date"] = {**q.get("date", {}), "$lte": end}

    inflows = {"operating": 0.0, "investing": 0.0, "financing": 0.0}
    outflows = {"operating": 0.0, "investing": 0.0, "financing": 0.0}
    rows = []

    async for j in db.journal_entries.find(q, {"_id": 0}):
        for ln in (j.get("lines") or []):
            if ln.get("account_code") not in cash_codes:
                continue
            dr = float(ln.get("debit") or 0)
            cr = float(ln.get("credit") or 0)
            sm = j.get("source_module") or "manual"
            cat = ("financing" if sm in {"opening_balance", "loan"}
                   else "investing" if sm in {"fixed_asset"}
                   else "operating")
            if dr > 0:
                inflows[cat] += dr
            if cr > 0:
                outflows[cat] += cr
            rows.append({
                "date": j.get("date"),
                "voucher_number": j.get("voucher_number"),
                "narration": j.get("narration"),
                "source_module": sm,
                "inflow": dr, "outflow": cr,
                "category": cat,
            })
    net_operating = inflows["operating"] - outflows["operating"]
    net_investing = inflows["investing"] - outflows["investing"]
    net_financing = inflows["financing"] - outflows["financing"]
    return {
        "as_of": end or now_iso()[:10],
        "inflows": {k: round(v, 2) for k, v in inflows.items()},
        "outflows": {k: round(v, 2) for k, v in outflows.items()},
        "net_operating": round(net_operating, 2),
        "net_investing": round(net_investing, 2),
        "net_financing": round(net_financing, 2),
        "net_change": round(net_operating + net_investing + net_financing, 2),
        "movements": rows[:200],  # bounded
    }


# ════════════════════════════════════════════════════════════════════════
# 4. PERIOD LOCK (Month-end / Year-end)
# ════════════════════════════════════════════════════════════════════════
class PeriodLockIn(BaseModel):
    period: str                  # "2026-05" for month / "FY2025-26" for year
    period_type: str = "month"   # 'month' | 'year'
    notes: Optional[str] = None


class PeriodUnlockIn(BaseModel):
    period: str
    period_type: str = "month"
    reason: str                   # MUST provide reason


@router.post("/period/lock")
async def lock_period(payload: PeriodLockIn, request: Request,
                      user: dict = Depends(require_permission("accounting", "write"))):
    """Locks a month or financial year. After lock, normal users cannot edit/post in that period
    (enforcement at write-time is the caller's responsibility — UI shows locked indicator;
    a future Phase-6 can add a write-time middleware that rejects backdated edits)."""
    exists = await db.period_locks.find_one({"period": payload.period, "period_type": payload.period_type}, {"_id": 0})
    if exists and exists.get("status") == "locked":
        raise HTTPException(status_code=400, detail=f"Period {payload.period} already locked")
    doc = {
        "id": exists.get("id") if exists else new_id(),
        "period": payload.period,
        "period_type": payload.period_type,
        "status": "locked",
        "locked_by": user.get("name") or user.get("email"),
        "locked_at": now_iso(),
        "notes": payload.notes,
        "unlock_history": (exists or {}).get("unlock_history") or [],
    }
    await db.period_locks.update_one({"period": payload.period, "period_type": payload.period_type},
                                      {"$set": doc}, upsert=True)
    await audit(user=user, action="period_lock", resource="period_locks",
                record_id=doc["id"], after={"period": payload.period, "type": payload.period_type},
                ip=request.client.host if request.client else "")
    return doc


@router.post("/period/unlock")
async def unlock_period(payload: PeriodUnlockIn, request: Request,
                        user: dict = Depends(require_permission("accounting", "write"))):
    """Owner/Finance Head only — requires reason. Recorded in audit + unlock_history."""
    role = (user.get("role") or "").lower()
    # Allowed roles — match what the codebase actually uses (rbac.py role list)
    if role not in {"super_admin", "admin", "owner", "finance_head", "finance"}:
        raise HTTPException(status_code=403,
            detail=f"Only Owner / Finance Head can unlock periods (your role: {user.get('role')})")
    if not payload.reason or len(payload.reason.strip()) < 5:
        raise HTTPException(status_code=400, detail="Unlock reason required (min 5 chars)")
    lock = await db.period_locks.find_one({"period": payload.period, "period_type": payload.period_type}, {"_id": 0})
    if not lock or lock.get("status") != "locked":
        raise HTTPException(status_code=400, detail=f"Period {payload.period} is not currently locked")
    unlock_entry = {"unlocked_by": user.get("name") or user.get("email"),
                    "unlocked_at": now_iso(), "reason": payload.reason}
    await db.period_locks.update_one(
        {"period": payload.period, "period_type": payload.period_type},
        {"$set": {"status": "unlocked", "unlocked_by": unlock_entry["unlocked_by"],
                  "unlocked_at": unlock_entry["unlocked_at"], "unlock_reason": payload.reason},
         "$push": {"unlock_history": unlock_entry}})
    await audit(user=user, action="period_unlock", resource="period_locks",
                record_id=lock.get("id"),
                after={"period": payload.period, "type": payload.period_type, "reason": payload.reason},
                ip=request.client.host if request.client else "")
    return await db.period_locks.find_one({"period": payload.period, "period_type": payload.period_type}, {"_id": 0})


@router.get("/period/status")
async def period_status(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.period_locks.find({}, {"_id": 0}).sort("period", -1).to_list(50)
    return rows


@router.get("/period/checklist")
async def month_end_checklist(period: str,
                              user: dict = Depends(require_permission("accounting", "read"))):
    """Computes the live checklist status for a given month (period='YYYY-MM')."""
    start = f"{period}-01"
    end_d = (datetime.fromisoformat(start).replace(day=28) + timedelta(days=4))
    end = (end_d - timedelta(days=end_d.day)).date().isoformat()

    draft_vouchers = await db.journal_entries.count_documents({"status": "draft", "date": {"$gte": start, "$lte": end}})
    pending_vouchers = await db.journal_entries.count_documents({"status": "pending_approval", "date": {"$gte": start, "$lte": end}})
    draft_invoices = await db.client_invoices.count_documents({"status": "draft", "invoice_date": {"$gte": start, "$lte": end}})
    draft_bills = await db.vendor_bills.count_documents({"status": "draft", "invoice_date": {"$gte": start, "$lte": end}})
    open_site_exp = await db.site_expenses.count_documents({"status": {"$in": ["draft", "pm_verified"]}, "expense_date": {"$gte": start, "$lte": end}})
    locked = await db.period_locks.find_one({"period": period, "period_type": "month"}, {"_id": 0})
    tb = await trial_balance(end=end)
    pnl = await profit_and_loss(start=start, end=end)
    diff = sum(float(r.get("debit_total", 0)) for r in tb) - sum(float(r.get("credit_total", 0)) for r in tb)

    items = [
        {"key": "vouchers_posted",   "label": "All vouchers posted",     "done": draft_vouchers == 0,
         "detail": f"{draft_vouchers} draft vouchers remaining"},
        {"key": "approvals_clear",   "label": "All approvals cleared",   "done": pending_vouchers == 0,
         "detail": f"{pending_vouchers} pending approval"},
        {"key": "invoices_clear",    "label": "Client invoices verified","done": draft_invoices == 0,
         "detail": f"{draft_invoices} draft invoices"},
        {"key": "bills_clear",       "label": "Vendor bills verified",   "done": draft_bills == 0,
         "detail": f"{draft_bills} draft vendor bills"},
        {"key": "site_clear",        "label": "Site expenses cleared",   "done": open_site_exp == 0,
         "detail": f"{open_site_exp} open site expenses"},
        {"key": "tb_balanced",       "label": "Trial Balance balanced",  "done": abs(diff) < 1.0,
         "detail": f"diff {round(diff, 2)}"},
        {"key": "pnl_ready",         "label": "Profit & Loss generated", "done": pnl is not None,
         "detail": f"Revenue {pnl.get('total_revenue', 0)} · Expense {pnl.get('total_expense', 0)}"},
        {"key": "locked",            "label": "Month locked",             "done": bool(locked and locked.get("status") == "locked"),
         "detail": "Locked" if locked and locked.get("status") == "locked" else "Not locked yet"},
    ]
    return {"period": period, "items": items,
            "progress": round(sum(1 for i in items if i["done"]) / len(items) * 100, 1),
            "all_clear": all(i["done"] for i in items[:-1])}  # last item = lock itself


# ════════════════════════════════════════════════════════════════════════
# 5. NOTIFICATIONS / ALERTS
# ════════════════════════════════════════════════════════════════════════
@router.get("/alerts")
async def accounting_alerts(user: dict = Depends(require_permission("accounting", "read"))):
    """Cross-collection scan returning a single alerts payload for the bell."""
    today = datetime.now(timezone.utc).date()
    today_iso = today.isoformat()

    alerts: List[Dict[str, Any]] = []

    # Overdue client invoices
    overdue = await db.client_invoices.count_documents(
        {"status": {"$in": ["approved", "partially_paid"]}, "due_date": {"$lt": today_iso}, "outstanding": {"$gt": 0}}
    )
    if overdue:
        alerts.append({"key": "overdue_client", "severity": "high",
                        "label": f"{overdue} client invoice(s) overdue", "link": "overdue"})

    # Vendor payment due in 7 days
    upcoming = await db.vendor_bills.count_documents(
        {"status": {"$in": ["approved", "partially_paid"]}, "outstanding": {"$gt": 0},
         "due_date": {"$lte": (today + timedelta(days=7)).isoformat()}}
    )
    if upcoming:
        alerts.append({"key": "vendor_due_soon", "severity": "medium",
                        "label": f"{upcoming} vendor payment(s) due in 7 days", "link": "payment_due"})

    # Pending approvals
    pending_inv = await db.client_invoices.count_documents({"status": "draft"})
    pending_bills = await db.vendor_bills.count_documents({"status": {"$in": ["draft", "verified"]}})
    pending_exp = await db.site_expenses.count_documents({"status": {"$in": ["draft", "pm_verified"]}})
    if pending_inv + pending_bills + pending_exp > 0:
        alerts.append({"key": "pending_approvals", "severity": "medium",
                        "label": f"Approvals pending — {pending_inv} invoices, {pending_bills} bills, {pending_exp} expenses",
                        "link": "inbox"})

    # Missing attachments
    posted_no_att = await db.journal_entries.count_documents({
        "status": "posted",
        "$or": [{"attachments": {"$exists": False}}, {"attachments": []}],
        "voucher_type": {"$in": ["PV", "RV", "PUV", "EV"]},
    })
    if posted_no_att:
        alerts.append({"key": "missing_attachments", "severity": "low",
                        "label": f"{posted_no_att} vouchers without proof attachment",
                        "link": "daybook"})

    # Duplicate vendor invoices
    dup_check = []
    async for d in db.vendor_bills.aggregate([
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$group": {"_id": {"v": "$vendor_name", "i": "$invoice_no"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}, {"$limit": 10},
    ]):
        dup_check.append(d)
    if dup_check:
        alerts.append({"key": "duplicate_invoice", "severity": "high",
                        "label": f"{len(dup_check)} duplicate vendor invoice(s) detected",
                        "link": "vendor_bills"})

    # Month-end closing
    last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    last_locked = await db.period_locks.find_one({"period": last_month, "period_type": "month"}, {"_id": 0})
    if not last_locked or last_locked.get("status") != "locked":
        alerts.append({"key": "month_close_pending", "severity": "medium",
                        "label": f"Month-end {last_month} closing pending", "link": "closing"})

    # Projects at risk (loss / over-budget)
    prof = await project_profitability(user)
    at_risk = prof["summary"]["at_risk_count"] + prof["summary"]["loss_count"]
    if at_risk:
        alerts.append({"key": "projects_at_risk", "severity": "high",
                        "label": f"{at_risk} project(s) at financial risk",
                        "link": "proj_profit"})

    return {"alerts": alerts, "count": len(alerts), "as_of": now_iso()}


# ════════════════════════════════════════════════════════════════════════
# 6. CSV EXPORT (universal)
# ════════════════════════════════════════════════════════════════════════
@router.get("/export/{report_key}")
async def export_report(report_key: str, request: Request,
                        user: dict = Depends(require_permission("accounting", "read"))):
    """Export any of the standard reports to CSV. Logged in audit_logs.

    Supported keys: project-profitability, trial-balance, profit-loss, balance-sheet,
                    client-outstanding, vendor-outstanding, gst-sales-register,
                    gst-purchase-register.
    """
    rows: List[Dict[str, Any]] = []
    if report_key == "project-profitability":
        d = await project_profitability(user)
        rows = d["projects"]
    elif report_key == "trial-balance":
        rows = await trial_balance()
    elif report_key == "profit-loss":
        pl = await profit_and_loss()
        rows = (pl.get("revenue") or []) + (pl.get("expense") or [])
    elif report_key == "balance-sheet":
        bs = await balance_sheet(user=user)
        rows = (bs["assets"]["rows"] + bs["liabilities"]["rows"] + bs["equity"]["rows"])
    elif report_key == "client-outstanding":
        rows = await db.client_invoices.find(
            {"status": {"$in": ["approved", "partially_paid"]}, "outstanding": {"$gt": 0}}, {"_id": 0}
        ).to_list(2000)
    elif report_key == "vendor-outstanding":
        rows = await db.vendor_bills.find(
            {"status": {"$in": ["approved", "partially_paid"]}, "outstanding": {"$gt": 0}}, {"_id": 0}
        ).to_list(2000)
    elif report_key == "gst-sales-register":
        rows = await db.client_invoices.find({"status": {"$in": ["approved", "partially_paid", "paid"]}}, {"_id": 0}).to_list(2000)
    elif report_key == "gst-purchase-register":
        rows = await db.vendor_bills.find({"status": {"$in": ["approved", "partially_paid", "paid"]}}, {"_id": 0}).to_list(2000)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown report key {report_key}")

    if not rows:
        return Response(content="(no data)\n", media_type="text/csv")

    # Build CSV — flatten one level for nested dicts
    def flatten(r: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, v in r.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    out[f"{k}.{sk}"] = sv
            elif isinstance(v, list):
                out[k] = f"({len(v)} items)"
            else:
                out[k] = v
        return out

    flat = [flatten(r) for r in rows]
    keys = sorted({k for r in flat for k in r.keys()})
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in flat:
        w.writerow(r)
    csv_data = buf.getvalue()

    await audit(user=user, action="report_export", resource="reports",
                record_id=report_key, after={"rows": len(rows), "report": report_key},
                ip=request.client.host if request.client else "")
    filename = f"{report_key}_{now_iso()[:10]}.csv"
    return Response(content=csv_data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
