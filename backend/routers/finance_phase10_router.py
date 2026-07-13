"""Finance Phase 10 — Testing, Migration & Go-Live.

Read-only audit endpoints that aggregate over EXISTING finance data to
produce migration-completeness checks, reconciliation reports and a
go-live readiness scorecard. No new business logic introduced; this
phase is purely **observational** over previously-built modules.

Endpoints (all under /api/finance/phase10):
  GET  /migration/coverage            data coverage across modules
  GET  /reconciliation/summary        AR/AP/Cash/GST/TDS/Advances/Payroll
  GET  /reconciliation/ledger-tie-out trial-balance vs sub-ledger
  GET  /negative-tests/run            runs the documented negative tests
  GET  /go-live/checklist             single payload scorecard
  GET  /go-live/pending-approvals     list of opens to clear
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from core import db, require_permission

router = APIRouter(prefix="/finance/phase10", tags=["finance-phase10-golive"])


# ═════════════════════════════════════════════════════════════════════════
# 1. Migration coverage
# ═════════════════════════════════════════════════════════════════════════
@router.get("/migration/coverage")
async def migration_coverage(user: dict = Depends(require_permission("accounting", "read"))):
    """Counts existing finance entities. A go-live can proceed only when these
    align with the source-of-truth provided by the user.
    """
    coa = await db.chart_of_accounts.count_documents({})
    coa_active = await db.chart_of_accounts.count_documents({"active": {"$ne": False}})

    invs = await db.client_invoices.count_documents({})
    bills = await db.vendor_bills.count_documents({})
    receipts = await db.receipts.count_documents({}) if "receipts" in await db.list_collection_names() else 0
    payments = await db.payments.count_documents({})
    journals = await db.journal_entries.count_documents({})
    advances = await db.employee_advances.count_documents({})
    payslips = await db.payslips.count_documents({}) if "payslips" in await db.list_collection_names() else 0
    ra_bills = await db.ra_bills.count_documents({}) if "ra_bills" in await db.list_collection_names() else 0
    project_costs = await db.project_costs.count_documents({}) if "project_costs" in await db.list_collection_names() else 0
    vouchers_draft = await db.journal_entries.count_documents({"status": "draft"})

    return {
        "ledgers": {"total": coa, "active": coa_active},
        "client_invoices": invs,
        "vendor_bills": bills,
        "receipts": receipts,
        "payments": payments,
        "journal_entries": journals,
        "vouchers_in_draft": vouchers_draft,
        "advances": advances,
        "payslips": payslips,
        "ra_bills": ra_bills,
        "project_costs": project_costs,
    }


# ═════════════════════════════════════════════════════════════════════════
# 2. Reconciliation summary
# ═════════════════════════════════════════════════════════════════════════
async def _sum(coll: str, q: Dict[str, Any], field: str) -> float:
    pipeline = [{"$match": q}, {"$group": {"_id": None, "s": {"$sum": f"${field}"}}}]
    async for d in db[coll].aggregate(pipeline):
        return round(float(d.get("s") or 0), 2)
    return 0.0


@router.get("/reconciliation/summary")
async def reconciliation_summary(user: dict = Depends(require_permission("accounting", "read"))):
    # AR
    ar_total = await _sum("client_invoices", {"status": {"$in": ["approved", "sent"]}}, "total_amount")
    ar_received = await _sum("client_invoices", {"status": {"$in": ["approved", "sent"]}}, "amount_received")
    ar_outstanding = round(ar_total - ar_received, 2)

    # AP
    ap_total = await _sum("vendor_bills", {"status": {"$in": ["approved", "posted"]}}, "total_amount")
    ap_paid = await _sum("vendor_bills", {"status": {"$in": ["approved", "posted"]}}, "amount_paid")
    ap_outstanding = round(ap_total - ap_paid, 2)

    # Cash / Bank — from journal entries against CoA cash/bank accounts
    cash_codes_rows = await db.chart_of_accounts.find(
        {"$or": [{"sub_type": "cash"}, {"sub_type": "bank"}]},
        {"_id": 0, "code": 1, "sub_type": 1}
    ).to_list(50)
    cash_codes = [r["code"] for r in cash_codes_rows]
    cash_balance = 0.0
    if cash_codes:
        pipeline = [
            {"$unwind": "$lines"},
            {"$match": {"lines.account_code": {"$in": cash_codes}, "status": "posted"}},
            {"$group": {"_id": None,
                        "dr": {"$sum": "$lines.debit"},
                        "cr": {"$sum": "$lines.credit"}}},
        ]
        async for d in db.journal_entries.aggregate(pipeline):
            cash_balance = round(float(d.get("dr") or 0) - float(d.get("cr") or 0), 2)

    # GST output / input
    gst_out = await _sum("client_invoices", {}, "gst_amount")
    gst_in = await _sum("vendor_bills", {}, "gst_amount")

    # TDS
    tds_deducted = await _sum("client_invoices", {}, "tds_amount")
    tds_payable = await _sum("vendor_bills", {}, "tds_amount")

    # Advances outstanding
    adv_total = await _sum("employee_advances", {"status": {"$ne": "settled"}}, "amount")
    adv_recovered = await _sum("employee_advances", {"status": {"$ne": "settled"}}, "recovered_amount")
    adv_outstanding = round(adv_total - adv_recovered, 2)

    # Payroll payable
    payroll_payable = await _sum("payslips", {"status": {"$ne": "paid"}}, "net_pay") \
        if "payslips" in await db.list_collection_names() else 0.0

    return {
        "ar": {"total": ar_total, "received": ar_received, "outstanding": ar_outstanding},
        "ap": {"total": ap_total, "paid": ap_paid, "outstanding": ap_outstanding},
        "cash_bank_balance": cash_balance,
        "gst": {"output": gst_out, "input": gst_in, "net": round(gst_out - gst_in, 2)},
        "tds": {"deducted": tds_deducted, "payable": tds_payable},
        "advances": {"total": adv_total, "recovered": adv_recovered, "outstanding": adv_outstanding},
        "payroll_payable": payroll_payable,
    }


# ═════════════════════════════════════════════════════════════════════════
# 3. Ledger tie-out: trial balance vs sub-ledger totals
# ═════════════════════════════════════════════════════════════════════════
@router.get("/reconciliation/ledger-tie-out")
async def ledger_tie_out(user: dict = Depends(require_permission("accounting", "read"))):
    pipeline = [
        {"$match": {"status": "posted"}},
        {"$unwind": "$lines"},
        {"$group": {"_id": None,
                    "dr": {"$sum": "$lines.debit"},
                    "cr": {"$sum": "$lines.credit"}}},
    ]
    dr = cr = 0.0
    async for d in db.journal_entries.aggregate(pipeline):
        dr = round(float(d.get("dr") or 0), 2)
        cr = round(float(d.get("cr") or 0), 2)
    return {
        "total_debit": dr,
        "total_credit": cr,
        "difference": round(dr - cr, 2),
        "balanced": abs(dr - cr) < 0.01,
    }


# ═════════════════════════════════════════════════════════════════════════
# 4. Negative tests — runs each documented invariant against live data
# ═════════════════════════════════════════════════════════════════════════
@router.get("/negative-tests/run")
async def negative_tests(user: dict = Depends(require_permission("accounting", "read"))):
    """Each test returns {key, label, passed, count, sample?} — a 'pass' means
    NO offending rows were found. Counts let auditors zero-in on data issues.
    """
    tests: List[Dict[str, Any]] = []

    # 1) Unbalanced posted vouchers
    unbal = 0
    samples = []
    async for je in db.journal_entries.find({"status": "posted"}, {"_id": 0, "id": 1, "je_number": 1, "lines": 1}):
        dr = sum(float(ln.get("debit") or 0) for ln in (je.get("lines") or []))
        cr = sum(float(ln.get("credit") or 0) for ln in (je.get("lines") or []))
        if abs(dr - cr) > 0.01:
            unbal += 1
            if len(samples) < 5:
                samples.append({"je_number": je.get("je_number"), "dr": round(dr, 2), "cr": round(cr, 2)})
    tests.append({"key": "unbalanced_vouchers", "label": "All posted vouchers balanced",
                  "passed": unbal == 0, "count": unbal, "sample": samples})

    # 2) Duplicate invoice numbers
    dup_inv = 0
    dups = []
    async for d in db.client_invoices.aggregate([
        {"$group": {"_id": "$invoice_number", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}, "_id": {"$ne": None}}},
    ]):
        dup_inv += 1
        if len(dups) < 5:
            dups.append({"invoice_number": d["_id"], "occurrences": d["n"]})
    tests.append({"key": "duplicate_invoices", "label": "No duplicate invoice numbers",
                  "passed": dup_inv == 0, "count": dup_inv, "sample": dups})

    # 3) Payments without approval
    unapproved_pay = await db.payments.count_documents({"status": {"$nin": ["approved", "paid", "cancelled"]}})
    tests.append({"key": "payment_without_approval", "label": "No payments without approval",
                  "passed": unapproved_pay == 0, "count": unapproved_pay})

    # 4) Bills without vendor
    bill_no_vendor = await db.vendor_bills.count_documents({
        "$and": [{"vendor_id": {"$in": [None, ""]}}, {"vendor_name": {"$in": [None, ""]}}]
    })
    tests.append({"key": "bills_without_vendor", "label": "No bills without vendor",
                  "passed": bill_no_vendor == 0, "count": bill_no_vendor})

    # 5) Invoices without client
    inv_no_client = await db.client_invoices.count_documents({
        "$and": [{"client_id": {"$in": [None, ""]}}, {"client_name": {"$in": [None, ""]}}]
    })
    tests.append({"key": "invoices_without_client", "label": "No invoices without client",
                  "passed": inv_no_client == 0, "count": inv_no_client})

    # 6) Posted JE lines with missing account_code
    bad_lines = await db.journal_entries.count_documents({
        "status": "posted", "lines.account_code": {"$in": [None, ""]}
    })
    tests.append({"key": "posting_without_ledger", "label": "All posted JE lines have a ledger",
                  "passed": bad_lines == 0, "count": bad_lines})

    # 7) Backdated posts into a currently-locked period
    locked_periods: List[str] = []
    async for d in db.period_locks.find({"status": "locked", "period_type": "month"}, {"_id": 0, "period": 1}):
        locked_periods.append(d["period"])
    leaked = 0
    if locked_periods:
        for p in locked_periods:
            leaked += await db.journal_entries.count_documents({
                "status": "posted", "date": {"$regex": f"^{p}-"}, "created_at": {"$gt": p}
            })
    tests.append({"key": "backdated_into_locked", "label": "No backdated posts into locked periods",
                  "passed": leaked == 0, "count": leaked})

    # 8) Tax mismatch — invoice gst_amount vs computed
    tax_mismatch = 0
    async for inv in db.client_invoices.find({"status": {"$in": ["approved", "sent"]}},
                                              {"_id": 0, "id": 1, "subtotal": 1, "gst_rate": 1,
                                               "gst_amount": 1, "invoice_number": 1}).limit(2000):
        sub = float(inv.get("subtotal") or 0)
        rate = float(inv.get("gst_rate") or 0)
        gst = float(inv.get("gst_amount") or 0)
        if sub and rate and abs((sub * rate / 100) - gst) > 1:
            tax_mismatch += 1
    tests.append({"key": "tax_mismatch", "label": "Invoice GST matches subtotal × rate",
                  "passed": tax_mismatch == 0, "count": tax_mismatch})

    # 9) Inactive ledger with transactions
    inactive_with_txn = 0
    async for coa in db.chart_of_accounts.find({"active": False}, {"_id": 0, "code": 1}).limit(500):
        n = await db.journal_entries.count_documents({"lines.account_code": coa["code"]})
        if n > 0:
            inactive_with_txn += 1
    tests.append({"key": "inactive_ledger_with_txn", "label": "No inactive ledger has live transactions",
                  "passed": inactive_with_txn == 0, "count": inactive_with_txn})

    passed_n = sum(1 for t in tests if t["passed"])
    return {"total": len(tests), "passed": passed_n, "failed": len(tests) - passed_n, "tests": tests}


# ═════════════════════════════════════════════════════════════════════════
# 5. Go-live checklist
# ═════════════════════════════════════════════════════════════════════════
@router.get("/go-live/checklist")
async def go_live_checklist(user: dict = Depends(require_permission("accounting", "read"))):
    coverage = await migration_coverage(user)
    recon = await reconciliation_summary(user)
    tie = await ledger_tie_out(user)
    neg = await negative_tests(user)

    # Pending counts
    pending_approvals = await db.approvals.count_documents({"status": {"$in": ["pending", "in_progress"]}})
    pending_invoices = await db.client_invoices.count_documents({"status": "pending_approval"})
    pending_bills = await db.vendor_bills.count_documents({"status": {"$in": ["pending_verification", "pending_approval"]}})
    pending_advances = await db.employee_advances.count_documents({"status": "pending_approval"})
    cutoff_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    overdue_compliance = await db.compliance_items.count_documents({
        "status": {"$ne": "paid"}, "due_date": {"$lt": cutoff_today}
    }) if "compliance_items" in await db.list_collection_names() else 0

    # Active users
    active_users = await db.users.count_documents({"active": {"$ne": False}})

    items = [
        {"key": "ledgers_loaded", "label": "Chart of Accounts loaded",
         "ok": coverage["ledgers"]["total"] > 0, "detail": f"{coverage['ledgers']['total']} ledgers"},
        {"key": "users_active", "label": "Active users configured",
         "ok": active_users > 1, "detail": f"{active_users} active"},
        {"key": "trial_balance_tied", "label": "Trial balance ties out",
         "ok": tie["balanced"], "detail": f"diff ₹{tie['difference']}"},
        {"key": "no_draft_vouchers", "label": "No draft vouchers pending",
         "ok": coverage["vouchers_in_draft"] == 0, "detail": f"{coverage['vouchers_in_draft']} drafts"},
        {"key": "no_pending_approvals", "label": "Approval queue clear",
         "ok": pending_approvals == 0, "detail": f"{pending_approvals} open"},
        {"key": "no_pending_invoices", "label": "Invoices approved",
         "ok": pending_invoices == 0, "detail": f"{pending_invoices} pending"},
        {"key": "no_pending_bills", "label": "Vendor bills approved",
         "ok": pending_bills == 0, "detail": f"{pending_bills} pending"},
        {"key": "no_pending_advances", "label": "Advances approved",
         "ok": pending_advances == 0, "detail": f"{pending_advances} pending"},
        {"key": "compliance_clear", "label": "Compliance items current",
         "ok": overdue_compliance == 0, "detail": f"{overdue_compliance} overdue"},
        {"key": "negative_tests_pass", "label": "Negative-test suite passes",
         "ok": neg["failed"] == 0, "detail": f"{neg['failed']} failures of {neg['total']}"},
    ]
    score = round(100 * sum(1 for i in items if i["ok"]) / len(items), 1)
    return {
        "score": score,
        "ready_for_go_live": score >= 90,
        "items": items,
        "reconciliation": recon,
        "coverage": coverage,
        "negative_tests": {"passed": neg["passed"], "failed": neg["failed"], "total": neg["total"]},
    }


@router.get("/go-live/pending-approvals")
async def pending_approvals_list(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.approvals.find(
        {"status": {"$in": ["pending", "in_progress"]}},
        {"_id": 0, "id": 1, "type": 1, "subject": 1, "amount": 1, "current_step": 1,
         "created_at": 1, "created_by": 1, "status": 1},
    ).sort("created_at", 1).to_list(200)
    return {"count": len(rows), "rows": rows}
