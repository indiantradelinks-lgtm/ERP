"""HR Phase 4 — Salary/Wage Structure approval, Loans, Reimbursements,
Store-recoveries, Payroll finance-approval, Posting to Accounts, Statutory
liability reports, Project-wise manpower cost.

Extends the existing `payroll_router` (preview/override/commit) — does NOT
replace it. The existing /api/payroll/* endpoints remain authoritative for the
preview→override→commit cycle. Phase 4 adds the *governance* (structure
approval), *post-commit workflow* (finance approval, accounts posting),
*ancillary requests* (loans, reimbursements, store recoveries) and *statutory
reports* required by the spec.

All endpoints prefixed `/api/hr4`.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, get_current_user, require_permission, now_iso, new_id
from pagination import maybe_paged, paged_or_rows
from accounting_service import post_journal_entry
from audit import audit


router = APIRouter(prefix="/hr4", tags=["hr-phase4"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
HR_ROLES = {"super_admin", "hr_executive", "general_manager", "director"}
FIN_ROLES = {"super_admin", "accounts_executive", "general_manager", "director"}
ACC_CODES = {
    "salary_expense": "5101",
    "salary_payable": "2201",
    "pf_payable": "2202",
    "esic_payable": "2203",
    "tds_payable": "2204",
    "pt_payable": "2205",
    "employee_advance": "1301",
    "employee_loan": "1302",
    "reimbursement_payable": "2206",
    "reimbursement_expense": "5102",
    "store_recovery_income": "4201",
    "bank": "1101",
}


def _ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request and request.client else "unknown"


async def _seq(prefix: str) -> str:
    doc = await db.counters.find_one_and_update(
        {"id": f"seq_{prefix.rstrip('-')}"},
        {"$inc": {"n": 1}, "$setOnInsert": {"id": f"seq_{prefix.rstrip('-')}"}},
        upsert=True, return_document=True,
    )
    n = (doc or {}).get("n", 1)
    return f"{prefix}{datetime.now(timezone.utc).year}-{n:04d}"


async def _ensure_coa():
    """Ensure required chart-of-accounts rows exist (idempotent)."""
    seed = [
        ("5101", "Salary & Wages Expense", "expense"),
        ("5102", "Employee Reimbursement Expense", "expense"),
        ("2201", "Salary Payable", "liability"),
        ("2202", "PF Payable", "liability"),
        ("2203", "ESIC Payable", "liability"),
        ("2204", "TDS Payable", "liability"),
        ("2205", "Professional Tax Payable", "liability"),
        ("2206", "Employee Reimbursement Payable", "liability"),
        ("1301", "Employee Advance", "asset"),
        ("1302", "Employee Loan", "asset"),
        ("4201", "Store Recovery Income", "income"),
    ]
    for code, name, typ in seed:
        if not await db.chart_of_accounts.find_one({"code": code}, {"_id": 0, "id": 1}):
            await db.chart_of_accounts.insert_one({
                "id": new_id(), "code": code, "name": name,
                "account_type": typ, "is_active": True,
                "is_system": True, "created_at": now_iso(),
            })


# ──────────────────────────────────────────────────────────────────────────────
# 1.  SALARY / WAGE STRUCTURE  (approval-gated, effective-dated)
# ──────────────────────────────────────────────────────────────────────────────
class SalaryStructureIn(BaseModel):
    employee_id: str
    wage_type: str = "monthly"   # monthly | daily | hourly | shift | piece_rate
    basic: float = 0
    hra: float = 0
    da: float = 0
    conveyance: float = 0
    site_allowance: float = 0
    food_allowance: float = 0
    other_allowance: float = 0
    attendance_bonus_applicable: bool = False
    attendance_bonus_amount: float = 0
    overtime_rate: float = 0
    pf_applicable: bool = True
    esic_applicable: bool = False
    tds_applicable: bool = False
    professional_tax: float = 0
    effective_from: str          # YYYY-MM-DD
    effective_to: Optional[str] = None
    remarks: Optional[str] = None


@router.post("/salary-structures")
async def create_structure(p: SalaryStructureIn, request: Request,
                           user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if p.wage_type not in {"monthly", "daily", "hourly", "shift", "piece_rate"}:
        raise HTTPException(400, "invalid wage_type")
    emp = await db.employees.find_one({"id": p.employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    try:
        datetime.fromisoformat(p.effective_from)
    except Exception:
        raise HTTPException(400, "effective_from must be YYYY-MM-DD")
    doc = {
        "id": new_id(),
        "structure_no": await _seq("SS-"),
        **p.model_dump(),
        "employee_name": emp.get("name"),
        "employee_code": emp.get("employee_id"),
        "department": (emp.get("departments") or [None])[0] or emp.get("department"),
        "approval_status": "pending",
        "approved_by_id": None, "approved_by_name": None, "approved_at": None,
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    }
    await db.hr_salary_structures.insert_one(doc)
    doc.pop("_id", None)
    await db.hr_salary_structure_audit.insert_one({
        "id": new_id(), "structure_id": doc["id"], "action": "create",
        "before": None, "after": doc, "by_id": user["id"],
        "by_name": user.get("name") or user.get("email"),
        "ip": _ip(request), "at": now_iso(),
    })
    return doc


@router.get("/salary-structures")
async def list_structures(request: Request, employee_id: Optional[str] = None,
                          approval_status: Optional[str] = None,
                          user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if employee_id:
        q["employee_id"] = employee_id
    if approval_status:
        q["approval_status"] = approval_status
    paged = await maybe_paged(request, "hr_salary_structures", q, "effective_from",
                              ["employee_name", "employee_code", "employee_id", "department", "designation", "approval_status", "status", "grade"])
    if paged:
        return paged
    return await db.hr_salary_structures.find(q, {"_id": 0}) \
        .sort("effective_from", -1).limit(500).to_list(500)


class ApprovalIn(BaseModel):
    decision: str = "approve"   # approve | reject
    remarks: Optional[str] = None


@router.post("/salary-structures/{sid}/approve")
async def approve_structure(sid: str, p: ApprovalIn, request: Request,
                            user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Only HR/Manager+ can approve salary structure")
    row = await db.hr_salary_structures.find_one({"id": sid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Salary structure not found")
    if p.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve | reject")
    upd = {
        "approval_status": "approved" if p.decision == "approve" else "rejected",
        "status": "active" if p.decision == "approve" else "rejected",
        "approved_by_id": user["id"],
        "approved_by_name": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "approval_remarks": p.remarks,
    }
    await db.hr_salary_structures.update_one({"id": sid}, {"$set": upd})
    after = await db.hr_salary_structures.find_one({"id": sid}, {"_id": 0})
    await db.hr_salary_structure_audit.insert_one({
        "id": new_id(), "structure_id": sid, "action": f"approval_{p.decision}",
        "before": row, "after": after, "by_id": user["id"],
        "by_name": user.get("name") or user.get("email"),
        "ip": _ip(request), "at": now_iso(),
    })
    # When approved, sync into payroll_master so existing run engine picks it up
    if p.decision == "approve":
        await sync_structure_to_payroll_master(row, sid)
    return after


async def sync_structure_to_payroll_master(row: Dict[str, Any], sid: str):
    """Push an approved salary structure into `payroll_master` (the payroll run engine source)."""
    await db.payroll_master.update_one(
        {"employee_id": row["employee_id"]},
        {"$setOnInsert": {"id": new_id(), "created_at": now_iso()},
         "$set": {
            "employee_id": row["employee_id"],
            "basic": row.get("basic", 0), "hra": row.get("hra", 0),
            "da": row.get("da", 0),
            "conveyance": row.get("conveyance", 0),
            "site_allowance": row.get("site_allowance", 0),
            "food_allowance": row.get("food_allowance", 0),
            "other_allowance": row.get("other_allowance", 0),
            "attendance_bonus_applicable": row.get("attendance_bonus_applicable", False),
            "attendance_bonus_amount": row.get("attendance_bonus_amount", 0),
            "overtime_rate": row.get("overtime_rate", 0),
            "pf_applicable": row.get("pf_applicable", True),
            "esi_applicable": row.get("esic_applicable", False),
            "tds_applicable": row.get("tds_applicable", False),
            "wage_type": row.get("wage_type", "monthly"),
            "effective_from": row.get("effective_from"),
            "synced_structure_id": sid,
            "updated_at": now_iso(),
        }}, upsert=True)


@router.get("/salary-structures/{sid}/audit")
async def structure_audit(sid: str,
                          user: dict = Depends(require_permission("hr_onboarding", "read"))):
    return await db.hr_salary_structure_audit.find(
        {"structure_id": sid}, {"_id": 0}).sort("at", -1).to_list(200)


# ──────────────────────────────────────────────────────────────────────────────
# 2.  EMPLOYEE LOAN
# ──────────────────────────────────────────────────────────────────────────────
class LoanIn(BaseModel):
    employee_id: str
    loan_amount: float
    reason: str
    emi_amount: float
    recovery_start_month: str    # YYYY-MM
    tenure_months: int = 12


@router.post("/loans")
async def create_loan(p: LoanIn, request: Request,
                      user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if p.loan_amount <= 0 or p.emi_amount <= 0:
        raise HTTPException(400, "loan_amount and emi_amount must be > 0")
    try:
        datetime.strptime(p.recovery_start_month, "%Y-%m")
    except Exception:
        raise HTTPException(400, "recovery_start_month must be YYYY-MM")
    emp = await db.employees.find_one({"id": p.employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    doc = {
        "id": new_id(),
        "loan_no": await _seq("LN-"),
        **p.model_dump(),
        "employee_name": emp.get("name"),
        "balance_amount": p.loan_amount,
        "recovered_amount": 0.0,
        "remaining_installments": p.tenure_months,
        "approval_status": "pending",
        "payment_status": "unpaid",
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    }
    await db.hr_loans.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/loans/{lid}/approve")
async def approve_loan(lid: str, p: ApprovalIn,
                       user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "HR Manager+ only")
    row = await db.hr_loans.find_one({"id": lid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Loan not found")
    upd = {
        "approval_status": "approved" if p.decision == "approve" else "rejected",
        "status": "active" if p.decision == "approve" else "rejected",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "approval_remarks": p.remarks,
    }
    await db.hr_loans.update_one({"id": lid}, {"$set": upd})
    return await db.hr_loans.find_one({"id": lid}, {"_id": 0})


@router.post("/loans/{lid}/mark-paid")
async def mark_loan_paid(lid: str,
                         user: dict = Depends(require_permission("accounting", "write"))):
    """Finance marks the loan disbursement payment as done."""
    if user.get("role") not in FIN_ROLES:
        raise HTTPException(403, "Finance only")
    row = await db.hr_loans.find_one({"id": lid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Loan not found")
    if row.get("approval_status") != "approved":
        raise HTTPException(400, "Loan not approved")
    # Post JV — Dr Employee Loan, Cr Bank
    await _ensure_coa()
    await post_journal_entry(
        date=now_iso()[:10],
        narration=f"Loan disbursement to {row.get('employee_name')} ({row.get('loan_no')})",
        lines=[
            {"account_code": ACC_CODES["employee_loan"], "debit": row["loan_amount"], "credit": 0,
             "narration": "Loan to employee"},
            {"account_code": ACC_CODES["bank"], "debit": 0, "credit": row["loan_amount"],
             "narration": "Bank disbursement"},
        ],
        source_module="hr_loan", source_id=lid, source_event="disburse",
        voucher_type="PV", posted_by=user.get("name") or user.get("email"),
    )
    await db.hr_loans.update_one({"id": lid}, {"$set": {
        "payment_status": "paid", "paid_at": now_iso(),
        "paid_by": user.get("name") or user.get("email"),
    }})
    return await db.hr_loans.find_one({"id": lid}, {"_id": 0})


@router.get("/loans")
async def list_loans(employee_id: Optional[str] = None,
                     status: Optional[str] = None,
                     user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if employee_id:
        q["employee_id"] = employee_id
    if status:
        q["status"] = status
    return await db.hr_loans.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


# ──────────────────────────────────────────────────────────────────────────────
# 3.  REIMBURSEMENTS
# ──────────────────────────────────────────────────────────────────────────────
class ReimbursementIn(BaseModel):
    employee_id: str
    project_code: Optional[str] = None
    expense_type: str
    amount: float
    bill_attachment_url: Optional[str] = None
    description: Optional[str] = None
    expense_date: Optional[str] = None


@router.post("/reimbursements")
async def create_reimbursement(p: ReimbursementIn, request: Request,
                               user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if p.amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    emp = await db.employees.find_one({"id": p.employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    doc = {
        "id": new_id(),
        "reimbursement_no": await _seq("RMB-"),
        **p.model_dump(),
        "employee_name": emp.get("name"),
        "approval_status": "pending",
        "payment_status": "unpaid",
        "status": "draft",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    }
    await db.hr_reimbursements.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/reimbursements/{rid}/approve")
async def approve_reimbursement(rid: str, p: ApprovalIn,
                                user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "HR Manager+ only")
    row = await db.hr_reimbursements.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Reimbursement not found")
    upd = {
        "approval_status": "approved" if p.decision == "approve" else "rejected",
        "status": "approved" if p.decision == "approve" else "rejected",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "approval_remarks": p.remarks,
    }
    await db.hr_reimbursements.update_one({"id": rid}, {"$set": upd})
    # Post JV when approved — Dr Reimbursement Expense, Cr Reimbursement Payable
    if p.decision == "approve":
        await _ensure_coa()
        await post_journal_entry(
            date=now_iso()[:10],
            narration=f"Reimbursement approved for {row.get('employee_name')} ({row['reimbursement_no']})",
            lines=[
                {"account_code": ACC_CODES["reimbursement_expense"], "debit": row["amount"], "credit": 0,
                 "narration": row.get("expense_type"),
                 "project_id": row.get("project_code")},
                {"account_code": ACC_CODES["reimbursement_payable"], "debit": 0, "credit": row["amount"],
                 "narration": f"Payable to {row.get('employee_name')}"},
            ],
            source_module="hr_reimbursement", source_id=rid, source_event="approve",
            voucher_type="JV", posted_by=user.get("name") or user.get("email"),
        )
    return await db.hr_reimbursements.find_one({"id": rid}, {"_id": 0})


@router.post("/reimbursements/{rid}/mark-paid")
async def mark_reimbursement_paid(rid: str,
                                  user: dict = Depends(require_permission("accounting", "write"))):
    if user.get("role") not in FIN_ROLES:
        raise HTTPException(403, "Finance only")
    row = await db.hr_reimbursements.find_one({"id": rid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Reimbursement not found")
    if row.get("approval_status") != "approved":
        raise HTTPException(400, "Reimbursement not approved")
    # Post JV — Dr Reimbursement Payable, Cr Bank
    await _ensure_coa()
    await post_journal_entry(
        date=now_iso()[:10],
        narration=f"Reimbursement paid {row['reimbursement_no']}",
        lines=[
            {"account_code": ACC_CODES["reimbursement_payable"], "debit": row["amount"], "credit": 0},
            {"account_code": ACC_CODES["bank"], "debit": 0, "credit": row["amount"]},
        ],
        source_module="hr_reimbursement", source_id=rid, source_event="pay",
        voucher_type="PV", posted_by=user.get("name") or user.get("email"),
    )
    await db.hr_reimbursements.update_one({"id": rid}, {"$set": {
        "payment_status": "paid", "status": "paid", "paid_at": now_iso(),
        "paid_by": user.get("name") or user.get("email"),
    }})
    return await db.hr_reimbursements.find_one({"id": rid}, {"_id": 0})


@router.get("/reimbursements")
async def list_reimbursements(employee_id: Optional[str] = None,
                              status: Optional[str] = None,
                              user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if employee_id:
        q["employee_id"] = employee_id
    if status:
        q["status"] = status
    return await db.hr_reimbursements.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


# ──────────────────────────────────────────────────────────────────────────────
# 4.  STORE RECOVERY
# ──────────────────────────────────────────────────────────────────────────────
class StoreRecoveryIn(BaseModel):
    employee_id: str
    project_code: Optional[str] = None
    item: str
    reason: str   # lost | damaged | unreturned
    amount: float
    recovery_month: str  # YYYY-MM


@router.post("/store-recoveries")
async def create_store_recovery(p: StoreRecoveryIn,
                                user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if p.amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    try:
        datetime.strptime(p.recovery_month, "%Y-%m")
    except Exception:
        raise HTTPException(400, "recovery_month must be YYYY-MM")
    emp = await db.employees.find_one({"id": p.employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    doc = {
        "id": new_id(),
        "recovery_no": await _seq("STR-"),
        **p.model_dump(),
        "employee_name": emp.get("name"),
        "approval_status": "pending",
        "recovery_status": "not_recovered",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name") or user.get("email"),
    }
    await db.hr_store_recoveries.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/store-recoveries/{rid}/approve")
async def approve_store_recovery(rid: str, p: ApprovalIn,
                                 user: dict = Depends(require_permission("hr_onboarding", "write"))):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "HR Manager+ only")
    upd = {
        "approval_status": "approved" if p.decision == "approve" else "rejected",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "approval_remarks": p.remarks,
    }
    await db.hr_store_recoveries.update_one({"id": rid}, {"$set": upd})
    return await db.hr_store_recoveries.find_one({"id": rid}, {"_id": 0})


@router.get("/store-recoveries")
async def list_store_recoveries(employee_id: Optional[str] = None,
                                recovery_month: Optional[str] = None,
                                user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if employee_id:
        q["employee_id"] = employee_id
    if recovery_month:
        q["recovery_month"] = recovery_month
    return await db.hr_store_recoveries.find(q, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)


# ──────────────────────────────────────────────────────────────────────────────
# 5.  PAYROLL → FINANCE APPROVAL → POSTING TO ACCOUNTS
# ──────────────────────────────────────────────────────────────────────────────
class PayrollFinanceIn(BaseModel):
    month: str
    decision: str = "approve"   # approve | reject
    remarks: Optional[str] = None


@router.post("/payroll/finance-approve")
async def finance_approve_payroll(p: PayrollFinanceIn,
                                  user: dict = Depends(require_permission("accounting", "write"))):
    """Finance gate between HR-commit and actual payment release."""
    if user.get("role") not in FIN_ROLES:
        raise HTTPException(403, "Finance approval requires accounts/finance role")
    run = await db.payroll_runs.find_one({"month": p.month, "status": "committed"}, {"_id": 0})
    if not run:
        raise HTTPException(404, f"No committed payroll run for {p.month}. Commit first via /api/payroll/run/commit.")
    upd = {
        "finance_approval_status": "approved" if p.decision == "approve" else "rejected",
        "finance_approved_by": user.get("name") or user.get("email"),
        "finance_approved_at": now_iso(),
        "finance_remarks": p.remarks,
    }
    await db.payroll_runs.update_one({"id": run["id"]}, {"$set": upd})
    return await db.payroll_runs.find_one({"id": run["id"]}, {"_id": 0})


@router.post("/payroll/post-to-accounts")
async def post_payroll_to_accounts(p: PayrollFinanceIn,
                                   user: dict = Depends(require_permission("accounting", "write"))):
    """Posts committed + finance-approved payroll into journal_entries."""
    if user.get("role") not in FIN_ROLES:
        raise HTTPException(403, "Finance only")
    run = await db.payroll_runs.find_one({"month": p.month, "status": "committed"}, {"_id": 0})
    if not run:
        raise HTTPException(404, "No committed run found")
    if run.get("finance_approval_status") != "approved":
        raise HTTPException(400, "Finance approval required before posting")
    if run.get("accounts_posting_status") == "posted":
        return {"ok": True, "already_posted": True, "run": run}

    await _ensure_coa()
    slips = await db.payslips.find({"month": p.month}, {"_id": 0}).to_list(5000)
    if not slips:
        raise HTTPException(400, "No payslips found for the month")

    # Aggregate totals per project for cost-centre tagging
    by_project: Dict[str, float] = {}
    tot_gross = tot_pf = tot_esi = tot_tds = tot_pt = tot_advance = 0.0
    for s in slips:
        gross = float(s.get("total_earnings") or 0)
        stat = s.get("statutory_deductions") or {}
        tot_gross += gross
        tot_pf += float(stat.get("pf") or 0)
        tot_esi += float(stat.get("esi") or 0)
        tot_tds += float(stat.get("tds") or 0)
        tot_pt += float(stat.get("professional_tax") or 0)
        tot_advance += float(s.get("advance_emi") or 0)
        pc = s.get("project_code") or "_UNALLOCATED_"
        by_project[pc] = by_project.get(pc, 0) + gross

    # Build JV lines
    lines: List[Dict[str, Any]] = []
    for proj_code, amt in by_project.items():
        lines.append({
            "account_code": ACC_CODES["salary_expense"],
            "debit": round(amt, 2), "credit": 0,
            "project_id": proj_code if proj_code != "_UNALLOCATED_" else None,
            "narration": f"Manpower cost — {proj_code}",
        })
    net_payable = round(tot_gross - tot_pf - tot_esi - tot_tds - tot_pt - tot_advance, 2)
    lines.extend([
        {"account_code": ACC_CODES["salary_payable"], "debit": 0, "credit": net_payable,
         "narration": f"Net salary payable {p.month}"},
        {"account_code": ACC_CODES["pf_payable"], "debit": 0, "credit": round(tot_pf, 2),
         "narration": "PF payable (employee)"},
        {"account_code": ACC_CODES["esic_payable"], "debit": 0, "credit": round(tot_esi, 2),
         "narration": "ESIC payable (employee)"},
        {"account_code": ACC_CODES["tds_payable"], "debit": 0, "credit": round(tot_tds, 2),
         "narration": "TDS payable"},
        {"account_code": ACC_CODES["pt_payable"], "debit": 0, "credit": round(tot_pt, 2),
         "narration": "Professional Tax payable"},
        {"account_code": ACC_CODES["employee_advance"], "debit": 0, "credit": round(tot_advance, 2),
         "narration": "Advance recovery from payroll"},
    ])
    # Drop zero lines (post_journal_entry rejects them only if total=0)
    lines = [ln for ln in lines if abs(ln.get("debit", 0)) > 0.001 or abs(ln.get("credit", 0)) > 0.001]

    je = await post_journal_entry(
        date=now_iso()[:10],
        narration=f"Salary & Wage posting for {p.month}",
        lines=lines,
        source_module="payroll", source_id=run["id"], source_event="post",
        voucher_type="PYV", posted_by=user.get("name") or user.get("email"),
    )
    if not je:
        raise HTTPException(400, "JE failed — likely unbalanced")
    await db.payroll_runs.update_one({"id": run["id"]}, {"$set": {
        "accounts_posting_status": "posted",
        "accounts_je_id": je["id"],
        "accounts_je_number": je["je_number"],
        "posted_at": now_iso(),
        "posted_by": user.get("name") or user.get("email"),
    }})
    # Mark payslips posted
    await db.payslips.update_many({"month": p.month}, {"$set": {"posting_status": "posted"}})
    return {"ok": True, "je": je, "month": p.month,
            "lines": len(lines), "totals": {
                "gross": round(tot_gross, 2), "net_payable": net_payable,
                "pf": round(tot_pf, 2), "esi": round(tot_esi, 2),
                "tds": round(tot_tds, 2), "pt": round(tot_pt, 2),
                "advance": round(tot_advance, 2),
            }}


@router.post("/payroll/mark-paid")
async def mark_payroll_paid(p: PayrollFinanceIn,
                            user: dict = Depends(require_permission("accounting", "write"))):
    """Finance triggers actual bank disbursement → posts Dr Salary Payable / Cr Bank."""
    if user.get("role") not in FIN_ROLES:
        raise HTTPException(403, "Finance only")
    run = await db.payroll_runs.find_one({"month": p.month, "status": "committed"}, {"_id": 0})
    if not run or run.get("accounts_posting_status") != "posted":
        raise HTTPException(400, "Payroll must be posted to accounts first")
    if run.get("payment_status") == "paid":
        return {"ok": True, "already_paid": True}
    slips = await db.payslips.find({"month": p.month}, {"_id": 0, "net_pay": 1}).to_list(5000)
    net = round(sum(float(s.get("net_pay") or 0) for s in slips), 2)
    await _ensure_coa()
    je = await post_journal_entry(
        date=now_iso()[:10],
        narration=f"Salary payment for {p.month}",
        lines=[
            {"account_code": ACC_CODES["salary_payable"], "debit": net, "credit": 0},
            {"account_code": ACC_CODES["bank"], "debit": 0, "credit": net},
        ],
        source_module="payroll", source_id=run["id"], source_event="pay",
        voucher_type="PV", posted_by=user.get("name") or user.get("email"),
    )
    await db.payroll_runs.update_one({"id": run["id"]}, {"$set": {
        "payment_status": "paid", "payment_je_id": (je or {}).get("id"),
        "paid_at": now_iso(),
        "paid_by": user.get("name") or user.get("email"),
    }})
    await db.payslips.update_many({"month": p.month}, {"$set": {"payment_status": "paid"}})
    return {"ok": True, "je": je, "amount": net}


# ──────────────────────────────────────────────────────────────────────────────
# 6.  STATUTORY DASHBOARDS
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/statutory/pf")
async def statutory_pf(month: str,
                       user: dict = Depends(require_permission("accounting", "read"))):
    slips = await db.payslips.find({"month": month}, {"_id": 0}).to_list(5000)
    rows, total_emp, total_ee = [], 0.0, 0.0
    for s in slips:
        emp_pf = float((s.get("statutory_deductions") or {}).get("pf") or 0)
        basic = float((s.get("earnings") or {}).get("basic") or 0)
        # Employer contribution mirrors employee (12% on basic capped 15k)
        employer_pf = emp_pf
        rows.append({
            "employee_id": s.get("employee_id"),
            "employee_name": s.get("employee_name"),
            "employee_code": s.get("employee_code"),
            "wage_for_pf": min(basic, 15000),
            "employee_contribution": emp_pf,
            "employer_contribution": employer_pf,
            "pf_payable": round(emp_pf + employer_pf, 2),
        })
        total_emp += emp_pf
        total_ee += employer_pf
    return {"month": month, "rows": rows,
            "totals": {"employee_total": round(total_emp, 2),
                       "employer_total": round(total_ee, 2),
                       "grand_total": round(total_emp + total_ee, 2)}}


@router.get("/statutory/esic")
async def statutory_esic(month: str,
                         user: dict = Depends(require_permission("accounting", "read"))):
    slips = await db.payslips.find({"month": month}, {"_id": 0}).to_list(5000)
    rows, total_emp, total_ee = [], 0.0, 0.0
    for s in slips:
        emp_esi = float((s.get("statutory_deductions") or {}).get("esi") or 0)
        gross = float(s.get("total_earnings") or 0)
        # Employer ESI 3.25% on gross (when applicable)
        employer_esi = round(gross * 0.0325, 2) if emp_esi > 0 else 0
        rows.append({
            "employee_id": s.get("employee_id"),
            "employee_name": s.get("employee_name"),
            "wage_for_esic": gross,
            "employee_contribution": emp_esi,
            "employer_contribution": employer_esi,
            "esic_payable": round(emp_esi + employer_esi, 2),
        })
        total_emp += emp_esi
        total_ee += employer_esi
    return {"month": month, "rows": rows,
            "totals": {"employee_total": round(total_emp, 2),
                       "employer_total": round(total_ee, 2),
                       "grand_total": round(total_emp + total_ee, 2)}}


@router.get("/statutory/tds")
async def statutory_tds(month: str,
                        user: dict = Depends(require_permission("accounting", "read"))):
    slips = await db.payslips.find({"month": month}, {"_id": 0}).to_list(5000)
    rows, total = [], 0.0
    for s in slips:
        tds = float((s.get("statutory_deductions") or {}).get("tds") or 0)
        if tds <= 0:
            continue
        # Get PAN from payroll_master
        pm = await db.payroll_master.find_one(
            {"employee_id": s.get("employee_id")}, {"_id": 0, "pan": 1}) or {}
        rows.append({
            "employee_id": s.get("employee_id"),
            "employee_name": s.get("employee_name"),
            "pan": pm.get("pan", ""),
            "tds_amount": tds,
        })
        total += tds
    return {"month": month, "rows": rows, "total_tds": round(total, 2)}


# ──────────────────────────────────────────────────────────────────────────────
# 7.  PROJECT MANPOWER COST
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/project-cost")
async def project_manpower_cost(month: Optional[str] = None,
                                project_code: Optional[str] = None,
                                user: dict = Depends(require_permission("hr_onboarding", "read"))):
    q: Dict[str, Any] = {}
    if month:
        q["month"] = month
    slips = await db.payslips.find(q, {"_id": 0}).to_list(5000)
    by_project: Dict[str, Dict[str, Any]] = {}
    for s in slips:
        pc = s.get("project_code") or "_UNALLOCATED_"
        if project_code and pc != project_code:
            continue
        agg = by_project.setdefault(pc, {"project_code": pc, "headcount": 0,
                                          "gross": 0.0, "net_pay": 0.0,
                                          "employee_ids": set()})
        agg["employee_ids"].add(s.get("employee_id"))
        agg["gross"] += float(s.get("total_earnings") or 0)
        agg["net_pay"] += float(s.get("net_pay") or 0)
    rows = []
    for v in by_project.values():
        v["headcount"] = len(v.pop("employee_ids"))
        v["gross"] = round(v["gross"], 2)
        v["net_pay"] = round(v["net_pay"], 2)
        rows.append(v)
    rows.sort(key=lambda x: -x["gross"])
    return rows


@router.get("/dashboard")
async def hr4_dashboard(user: dict = Depends(require_permission("hr_onboarding", "read"))):
    today = datetime.now(timezone.utc).date().isoformat()
    month = today[:7]
    structures_pending = await db.hr_salary_structures.count_documents({"approval_status": "pending"})
    loans_open = await db.hr_loans.count_documents({"status": "active"})
    reimb_pending = await db.hr_reimbursements.count_documents({"approval_status": "pending"})
    str_recoveries_pending = await db.hr_store_recoveries.count_documents({"approval_status": "pending"})
    last_run = await db.payroll_runs.find_one({}, {"_id": 0}, sort=[("month", -1)]) or {}
    return {
        "as_of": now_iso(), "month": month,
        "salary_structures_pending": structures_pending,
        "loans_active": loans_open,
        "reimbursements_pending": reimb_pending,
        "store_recoveries_pending": str_recoveries_pending,
        "last_payroll_month": last_run.get("month"),
        "last_payroll_status": last_run.get("status"),
        "last_finance_approval": last_run.get("finance_approval_status"),
        "last_accounts_posting": last_run.get("accounts_posting_status"),
        "last_payment_status": last_run.get("payment_status"),
        "last_payslip_count": last_run.get("payslip_count"),
        "last_total_net": last_run.get("total_net"),
    }
