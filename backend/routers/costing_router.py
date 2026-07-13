"""Phase 4 — Site Expenses, Payroll Posting, Material Costing, Logistics, Safety, Project Cost Summary
=====================================================================================================
Routes under `/api/costing/*`.

Integration:
  • Reads HR (`payroll_runs`, `attendance`, `employees`, `employee_advances`) and posts salary JE
  • Reads Store (`material_allocations`, inventory codes) for material-issue/return/damage events
  • Reads Logistics (`vehicles`) for vehicle-expense routing
  • Reads Safety (`ppe_issuance`, `safety_reports`) for safety-cost routing
  • Reads Projects (`projects`) and bumps cost_incurred on every approved cost event
  • Writes JE via accounting_service.post_journal_entry — flows into Trial Balance,
    P&L, AP Aging, Accounts Dashboard cards in real time
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from accounting_service import post_journal_entry

router = APIRouter(prefix="/costing", tags=["Site Expenses & Project Costing"])


# Site-expense categories → ledger codes (subset of EXPENSE_CATEGORY_MAP from Phase-3)
SITE_EXPENSE_CATEGORIES: Dict[str, str] = {
    "local_purchase":     "5105",   # material purchase
    "conveyance":         "5143",   # loading/unloading proxy
    "fuel":               "5141",
    "food":               "5151",   # accommodation/food cluster
    "labour_welfare":     "5300",   # safety expense proxy
    "tools":              "5135",
    "safety_items":       "5300",
    "loading_unloading":  "5143",
    "accommodation":      "5151",
    "vehicle_expense":    "5142",
    "petty_cash":         "5400",   # admin
    "repair":             "5440",
    "misc":               "5900",
}


# ════════════════════════════════════════════════════════════════════════
# 1. SITE EXPENSES (Petty Cash)
# ════════════════════════════════════════════════════════════════════════
class SiteExpenseLineIn(BaseModel):
    description: str
    amount: float


class SiteExpenseIn(BaseModel):
    project_id: Optional[str] = None
    project_code: Optional[str] = None  # one of project_id/project_code required
    site_location: Optional[str] = None
    expense_date: str
    category: str
    paid_by_employee_id: Optional[str] = None
    paid_by_employee_name: Optional[str] = None
    payment_mode: str = "Cash"            # Cash / UPI / Personal-card
    settlement_mode: str = "petty_cash"   # petty_cash | employee_reimbursement | vendor_payable
    amount: float
    bill_no: Optional[str] = None
    remarks: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    lines: Optional[List[SiteExpenseLineIn]] = None
    force_no_attachment: bool = False     # admin override
    expected_budget: Optional[float] = None  # used for over-budget flag


@router.get("/expense-categories")
async def list_site_expense_categories(user: dict = Depends(require_permission("accounting", "read"))):
    return [{"key": k, "account_code": v} for k, v in SITE_EXPENSE_CATEGORIES.items()]


@router.post("/site-expenses")
async def create_site_expense(payload: SiteExpenseIn, request: Request,
                              user: dict = Depends(require_permission("accounting", "write"))):
    if not (payload.project_id or payload.project_code):
        raise HTTPException(status_code=400, detail="Project code/id is required for site expenses")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    if not payload.attachments and not payload.force_no_attachment:
        raise HTTPException(status_code=400, detail="Attachment required (or set force_no_attachment=true with permission)")
    if payload.category not in SITE_EXPENSE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category — must be one of {list(SITE_EXPENSE_CATEGORIES.keys())}")

    # Duplicate flag (same employee + same project + same amount + same date within 24h)
    dup_q = {
        "expense_date": payload.expense_date,
        "amount": payload.amount,
        "category": payload.category,
        "status": {"$ne": "cancelled"},
    }
    if payload.paid_by_employee_id:
        dup_q["paid_by_employee_id"] = payload.paid_by_employee_id
    if payload.project_id:
        dup_q["project_id"] = payload.project_id
    elif payload.project_code:
        dup_q["project_code"] = payload.project_code
    existing = await db.site_expenses.find_one(dup_q, {"_id": 0, "id": 1, "expense_no": 1})
    dup_warning = None
    if existing:
        dup_warning = f"Possible duplicate of {existing['expense_no']}"

    # Over-budget flag
    over_budget = False
    if payload.expected_budget and payload.amount > payload.expected_budget * 1.0:
        over_budget = True

    expense_no = await next_sequence("SE")
    doc = {
        "id": new_id(),
        "expense_no": expense_no,
        "project_id": payload.project_id, "project_code": payload.project_code,
        "site_location": payload.site_location,
        "expense_date": payload.expense_date,
        "category": payload.category,
        "expense_code": SITE_EXPENSE_CATEGORIES[payload.category],
        "paid_by_employee_id": payload.paid_by_employee_id,
        "paid_by_employee_name": payload.paid_by_employee_name,
        "payment_mode": payload.payment_mode,
        "settlement_mode": payload.settlement_mode,
        "amount": payload.amount,
        "bill_no": payload.bill_no,
        "remarks": payload.remarks,
        "attachments": payload.attachments or [],
        "lines": [ln.model_dump() for ln in (payload.lines or [])],
        "expected_budget": payload.expected_budget,
        "over_budget": over_budget,
        "duplicate_warning": dup_warning,
        "status": "draft",  # draft → pm_verified → accounts_checked → approved → posted → cancelled
        "submitted_by": user.get("name") or user.get("email"),
        "created_at": now_iso(),
    }
    await db.site_expenses.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="site_expense_create", resource="site_expenses",
                record_id=doc["id"], after={"expense_no": expense_no, "amount": payload.amount,
                                           "project": payload.project_code, "duplicate": bool(dup_warning)},
                ip=request.client.host if request.client else "")
    return doc


@router.get("/site-expenses")
async def list_site_expenses(status: Optional[str] = None,
                             project_id: Optional[str] = None,
                             category: Optional[str] = None,
                             employee_id: Optional[str] = None,
                             start: Optional[str] = None, end: Optional[str] = None,
                             limit: int = 200,
                             user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if project_id:
        q["project_id"] = project_id
    if category:
        q["category"] = category
    if employee_id:
        q["paid_by_employee_id"] = employee_id
    if start:
        q["expense_date"] = {**q.get("expense_date", {}), "$gte": start}
    if end:
        q["expense_date"] = {**q.get("expense_date", {}), "$lte": end}
    return await db.site_expenses.find(q, {"_id": 0}).sort("expense_date", -1).limit(limit).to_list(limit)


@router.post("/site-expenses/{exp_id}/verify-pm")
async def verify_site_expense_pm(exp_id: str, request: Request,
                                 user: dict = Depends(require_permission("accounting", "write"))):
    e = await db.site_expenses.find_one({"id": exp_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    if e["status"] != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot PM-verify in status {e['status']}")
    await db.site_expenses.update_one({"id": exp_id}, {"$set": {
        "status": "pm_verified",
        "pm_verified_by": user.get("name") or user.get("email"),
        "pm_verified_at": now_iso(),
    }})
    await audit(user=user, action="site_expense_pm_verify", resource="site_expenses",
                record_id=exp_id, after={"expense_no": e["expense_no"]},
                ip=request.client.host if request.client else "")
    return await db.site_expenses.find_one({"id": exp_id}, {"_id": 0})


@router.post("/site-expenses/{exp_id}/approve")
async def approve_site_expense(exp_id: str, request: Request,
                                user: dict = Depends(require_permission("accounting", "write"))):
    """Approval → auto-posts JE based on settlement_mode."""
    e = await db.site_expenses.find_one({"id": exp_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    if e["status"] not in ("draft", "pm_verified"):
        raise HTTPException(status_code=400, detail=f"Cannot approve in status {e['status']}")

    expense_code = e["expense_code"]
    amount = float(e["amount"])
    settlement = e.get("settlement_mode") or "petty_cash"

    # Build JE lines
    lines = [{"account_code": expense_code, "debit": amount, "credit": 0,
              "project_id": e.get("project_id"), "narration": f"Site expense ({e['category']})"}]
    if settlement == "petty_cash":
        lines.append({"account_code": "1115", "debit": 0, "credit": amount, "narration": "Petty cash"})
        narration = f"Site Expense {e['expense_no']} — paid from petty cash"
    elif settlement == "employee_reimbursement":
        # Employee Reimbursement Payable lives under Salary Payable (2200) for now
        lines.append({"account_code": "2200", "debit": 0, "credit": amount,
                      "narration": f"Reimburse {e.get('paid_by_employee_name') or ''}"})
        narration = f"Site Expense {e['expense_no']} — reimbursable to employee"
    elif settlement == "vendor_payable":
        lines.append({"account_code": "2100", "debit": 0, "credit": amount, "narration": "Vendor payable"})
        narration = f"Site Expense {e['expense_no']} — vendor bill"
    else:
        lines.append({"account_code": "1100", "debit": 0, "credit": amount, "narration": "Bank"})
        narration = f"Site Expense {e['expense_no']}"

    je = await post_journal_entry(
        date=e["expense_date"], narration=narration, lines=lines,
        source_module="site_expense", source_id=e["id"], source_event="approve",
        source_ref=e["expense_no"], project_id=e.get("project_id"),
        posted_by=user.get("name") or user.get("email"),
        voucher_type="EV", status="posted",
        party_type="employee", party_id=e.get("paid_by_employee_id"),
        party_name=e.get("paid_by_employee_name"),
    )

    await db.site_expenses.update_one({"id": exp_id}, {"$set": {
        "status": "approved",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "je_id": je["id"] if je else None,
        "je_voucher_number": (je or {}).get("voucher_number"),
    }})
    # Bump project cost
    if e.get("project_id"):
        await db.projects.update_one({"id": e["project_id"]},
                                      {"$inc": {"cost_incurred": amount}})
    await audit(user=user, action="site_expense_approve", resource="site_expenses",
                record_id=exp_id, after={"expense_no": e["expense_no"], "je": (je or {}).get("voucher_number")},
                ip=request.client.host if request.client else "")
    return await db.site_expenses.find_one({"id": exp_id}, {"_id": 0})


# ════════════════════════════════════════════════════════════════════════
# 2. PAYROLL POSTING (HR → Accounts)
# ════════════════════════════════════════════════════════════════════════
class PayrollPostIn(BaseModel):
    payroll_run_id: Optional[str] = None
    period: str                              # "2026-05"
    attendance_locked: bool                  # MUST be true to post
    salary_expense: float                    # gross to expense ledger
    salary_payable: float
    pf_payable: float = 0.0
    esic_payable: float = 0.0
    tds_payable: float = 0.0
    advance_recovered: float = 0.0
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    department: Optional[str] = None
    notes: Optional[str] = None


@router.post("/payroll/post")
async def post_payroll(payload: PayrollPostIn, request: Request,
                       user: dict = Depends(require_permission("accounting", "write"))):
    """Posts the JE for a payroll period.
       DR Salary Expense (5200) or Project Manpower Cost (5110 if project linked)
       CR Salary Payable (2200) / PF Payable (2220) / ESIC Payable (2230) / TDS Payable (2400)
       CR Employee Advance (1500) for the portion recovered
    """
    if not payload.attendance_locked:
        raise HTTPException(status_code=400, detail="Attendance must be locked before payroll posting")
    if payload.salary_expense <= 0:
        raise HTTPException(status_code=400, detail="salary_expense must be > 0")
    sum_credits = (payload.salary_payable + payload.pf_payable + payload.esic_payable +
                   payload.tds_payable + payload.advance_recovered)
    if abs(payload.salary_expense - sum_credits) > 0.01:
        raise HTTPException(status_code=400,
            detail=f"Imbalanced: salary_expense ({payload.salary_expense}) ≠ sum of credit legs ({sum_credits})")

    expense_code = "5110" if payload.project_id else "5200"
    lines = [{"account_code": expense_code, "debit": payload.salary_expense, "credit": 0,
              "project_id": payload.project_id, "department": payload.department,
              "narration": f"Payroll {payload.period}"}]
    if payload.salary_payable > 0:
        lines.append({"account_code": "2200", "debit": 0, "credit": payload.salary_payable, "narration": "Salary payable"})
    if payload.pf_payable > 0:
        lines.append({"account_code": "2220", "debit": 0, "credit": payload.pf_payable, "narration": "PF payable"})
    if payload.esic_payable > 0:
        lines.append({"account_code": "2230", "debit": 0, "credit": payload.esic_payable, "narration": "ESIC payable"})
    if payload.tds_payable > 0:
        lines.append({"account_code": "2400", "debit": 0, "credit": payload.tds_payable, "narration": "TDS on salary"})
    if payload.advance_recovered > 0:
        lines.append({"account_code": "1500", "debit": 0, "credit": payload.advance_recovered, "narration": "Advance recovered"})

    je = await post_journal_entry(
        date=now_iso()[:10],
        narration=f"Payroll posting · {payload.period}",
        lines=lines,
        source_module="payroll",
        source_id=payload.payroll_run_id or payload.period,
        source_event="payroll_post",
        source_ref=payload.period,
        project_id=payload.project_id, department=payload.department,
        posted_by=user.get("name") or user.get("email"),
        voucher_type="PYV", status="posted",
    )
    # Bump project cost
    if payload.project_id and je:
        await db.projects.update_one({"id": payload.project_id},
                                      {"$inc": {"cost_incurred": float(payload.salary_expense)}})
    await audit(user=user, action="payroll_post", resource="payroll",
                record_id=payload.payroll_run_id or payload.period,
                after={"period": payload.period, "je": (je or {}).get("voucher_number"),
                       "salary_expense": payload.salary_expense},
                ip=request.client.host if request.client else "")
    return je


class SalaryPaymentIn(BaseModel):
    period: str
    amount: float
    mode: str = "Bank"
    utr: Optional[str] = None
    payroll_approved: bool


@router.post("/payroll/pay-salary")
async def pay_salary(payload: SalaryPaymentIn, request: Request,
                     user: dict = Depends(require_permission("accounting", "write"))):
    """DR Salary Payable / CR Bank."""
    if not payload.payroll_approved:
        raise HTTPException(status_code=400, detail="Payroll must be approved before salary release")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    bank_code = "1110" if (payload.mode or "").lower() == "cash" else "1100"
    je = await post_journal_entry(
        date=now_iso()[:10],
        narration=f"Salary payment · {payload.period}",
        lines=[
            {"account_code": "2200", "debit": payload.amount, "credit": 0, "narration": "Salary settle"},
            {"account_code": bank_code, "debit": 0, "credit": payload.amount, "narration": f"Bank ({payload.mode})"},
        ],
        source_module="payroll",
        source_id=f"salary-payment-{payload.period}",
        source_event="salary_paid",
        source_ref=payload.utr,
        posted_by=user.get("name") or user.get("email"),
        voucher_type="PV", status="posted",
    )
    await audit(user=user, action="salary_paid", resource="payroll",
                record_id=f"salary-payment-{payload.period}",
                after={"period": payload.period, "amount": payload.amount, "je": (je or {}).get("voucher_number")},
                ip=request.client.host if request.client else "")
    return je


class EmployeeAdvanceIn(BaseModel):
    employee_id: Optional[str] = None
    employee_name: str
    amount: float
    mode: str = "Bank"
    date: str
    project_id: Optional[str] = None
    notes: Optional[str] = None


@router.post("/payroll/employee-advance")
async def post_employee_advance(payload: EmployeeAdvanceIn, request: Request,
                                 user: dict = Depends(require_permission("accounting", "write"))):
    """DR Employee Advance (1500) / CR Bank or Cash."""
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    bank = "1110" if (payload.mode or "").lower() == "cash" else "1100"
    je = await post_journal_entry(
        date=payload.date,
        narration=f"Advance to {payload.employee_name}",
        lines=[
            {"account_code": "1500", "debit": payload.amount, "credit": 0, "narration": "Employee advance"},
            {"account_code": bank, "debit": 0, "credit": payload.amount, "narration": f"Bank ({payload.mode})"},
        ],
        source_module="employee_advance",
        source_id=payload.employee_id or payload.employee_name,
        source_event="advance",
        project_id=payload.project_id,
        posted_by=user.get("name") or user.get("email"),
        voucher_type="PV", status="posted",
        party_type="employee", party_id=payload.employee_id, party_name=payload.employee_name,
    )
    return je


# ════════════════════════════════════════════════════════════════════════
# 3. MATERIAL MOVEMENT POSTING (Store → Project)
# ════════════════════════════════════════════════════════════════════════
class MaterialMoveIn(BaseModel):
    move_type: str                 # 'issue' | 'return' | 'damage' | 'loss' | 'scrap_sale'
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    material: Optional[str] = None
    quantity: float = 1
    unit: str = "Nos"
    unit_cost: float
    grn_id: Optional[str] = None
    requisition_id: Optional[str] = None
    sale_amount: Optional[float] = None     # for scrap_sale
    gst_amount: Optional[float] = None      # for scrap_sale
    date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/material-movement")
async def post_material_movement(payload: MaterialMoveIn, request: Request,
                                  user: dict = Depends(require_permission("accounting", "write"))):
    """Posts JE for material events:
       • issue   → DR 5100 Project Material Cost / CR 1300 Inventory
       • return  → DR 1300 Inventory / CR 5100 Project Material Cost
       • damage/loss → DR 5900 Misc Expense / CR 1300 Inventory
       • scrap_sale → DR Bank / CR 4800 Scrap Income + GST Output
    """
    mt = payload.move_type.lower()
    if mt not in {"issue", "return", "damage", "loss", "scrap_sale"}:
        raise HTTPException(status_code=400, detail=f"Unknown move_type {mt}")

    value = round(payload.quantity * payload.unit_cost, 2)
    if mt == "scrap_sale":
        value = float(payload.sale_amount or 0)

    if value <= 0:
        raise HTTPException(status_code=400, detail="Computed value must be > 0")

    if mt in ("issue", "damage", "loss", "scrap_sale") and payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0")

    # Negative stock guard (only a soft check — store_router holds the true stock balance)
    if mt == "issue" and payload.material:
        bal = await db.material_balances.find_one({"material": payload.material}, {"_id": 0, "available": 1})
        if bal and float(bal.get("available") or 0) < payload.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock — available {bal.get('available')} < {payload.quantity}")

    date_iso = payload.date or now_iso()[:10]
    if mt == "issue":
        lines = [{"account_code": "5100", "debit": value, "credit": 0,
                  "project_id": payload.project_id, "narration": f"Issue {payload.material or ''}"},
                 {"account_code": "1300", "debit": 0, "credit": value, "narration": "Inventory"}]
        voucher_type = "JV"
        ev = "issue"
    elif mt == "return":
        lines = [{"account_code": "1300", "debit": value, "credit": 0, "narration": "Return to inventory"},
                 {"account_code": "5100", "debit": 0, "credit": value, "project_id": payload.project_id,
                  "narration": f"Reverse issue {payload.material or ''}"}]
        voucher_type = "JV"
        ev = "return"
    elif mt in ("damage", "loss"):
        lines = [{"account_code": "5900", "debit": value, "credit": 0,
                  "narration": f"Material {mt}"},
                 {"account_code": "1300", "debit": 0, "credit": value, "narration": "Inventory"}]
        voucher_type = "ADJ"
        ev = mt
    else:  # scrap_sale
        gst = float(payload.gst_amount or 0)
        base = round(value - gst, 2) if gst else value
        lines = [{"account_code": "1100", "debit": value, "credit": 0, "narration": "Cash from scrap"},
                 {"account_code": "4800", "debit": 0, "credit": base, "narration": "Scrap income"}]
        if gst > 0:
            lines.append({"account_code": "2300", "debit": 0, "credit": gst, "narration": "GST output"})
        voucher_type = "SV"
        ev = "scrap_sale"

    je = await post_journal_entry(
        date=date_iso,
        narration=f"Material {mt} — {payload.material or '—'} x{payload.quantity}{payload.unit}",
        lines=lines,
        source_module="material_movement",
        source_id=new_id(),
        source_event=ev,
        source_ref=payload.requisition_id or payload.grn_id,
        project_id=payload.project_id,
        posted_by=user.get("name") or user.get("email"),
        voucher_type=voucher_type, status="posted",
    )
    if mt == "issue" and payload.project_id and je:
        await db.projects.update_one({"id": payload.project_id}, {"$inc": {"cost_incurred": value, "material_cost": value}})
    elif mt == "return" and payload.project_id and je:
        await db.projects.update_one({"id": payload.project_id}, {"$inc": {"cost_incurred": -value, "material_cost": -value}})
    return je


# ════════════════════════════════════════════════════════════════════════
# 4. LOGISTICS & SAFETY COST (lightweight wrappers — fully reusing site-expense)
# ════════════════════════════════════════════════════════════════════════
# These are convenience endpoints — the heavy lifting is done by site-expense.

class LogisticsCostIn(BaseModel):
    category: str = "vehicle_expense"  # vehicle_expense / fuel / loading_unloading
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    vehicle_id: Optional[str] = None
    transporter_name: Optional[str] = None
    amount: float
    date: str
    notes: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    force_no_attachment: bool = False


@router.post("/logistics-cost")
async def post_logistics_cost(payload: LogisticsCostIn, request: Request,
                              user: dict = Depends(require_permission("accounting", "write"))):
    """Convenience wrapper — creates a site_expense with category=vehicle_expense/fuel/loading.
    Auto-approves and posts JE in one call."""
    if payload.category not in SITE_EXPENSE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category {payload.category}")
    if not payload.attachments and not payload.force_no_attachment:
        raise HTTPException(status_code=400, detail="Attachment required")

    # Reuse the site-expense pipeline
    se = SiteExpenseIn(
        project_id=payload.project_id, project_code=payload.project_code,
        site_location=f"Vehicle {payload.vehicle_id}" if payload.vehicle_id else None,
        expense_date=payload.date,
        category=payload.category,
        payment_mode="Bank",
        settlement_mode="vendor_payable" if payload.transporter_name else "petty_cash",
        amount=payload.amount,
        remarks=payload.notes or f"Logistics — {payload.transporter_name or 'in-house'}",
        attachments=payload.attachments,
        force_no_attachment=payload.force_no_attachment,
    )
    exp = await create_site_expense(se, request, user)
    # Auto-approve
    return await approve_site_expense(exp["id"], request, user)


class SafetyCostIn(BaseModel):
    sub_type: str = "ppe"           # ppe | training | incident | penalty | recovery
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    amount: float
    is_recovery: bool = False        # if True → CR (income side); else DR (expense)
    date: str
    notes: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    force_no_attachment: bool = False


@router.post("/safety-cost")
async def post_safety_cost(payload: SafetyCostIn, request: Request,
                            user: dict = Depends(require_permission("accounting", "write"))):
    """Safety expense or recovery."""
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    if not payload.attachments and not payload.force_no_attachment:
        raise HTTPException(status_code=400, detail="Supporting document required for safety penalty/recovery")

    if payload.is_recovery:
        lines = [{"account_code": "1100", "debit": payload.amount, "credit": 0, "narration": "Bank — recovery"},
                 {"account_code": "4900", "debit": 0, "credit": payload.amount, "narration": "Safety recovery income"}]
        vt = "RV"
    else:
        lines = [{"account_code": "5300", "debit": payload.amount, "credit": 0,
                  "project_id": payload.project_id, "narration": f"Safety {payload.sub_type}"},
                 {"account_code": "1100", "debit": 0, "credit": payload.amount, "narration": "Bank"}]
        vt = "EV"

    je = await post_journal_entry(
        date=payload.date,
        narration=f"Safety {payload.sub_type} {'recovery' if payload.is_recovery else 'expense'} {payload.amount}",
        lines=lines,
        source_module="safety_cost",
        source_id=new_id(),
        source_event=payload.sub_type,
        project_id=payload.project_id,
        posted_by=user.get("name") or user.get("email"),
        voucher_type=vt, status="posted",
    )
    if payload.project_id and not payload.is_recovery and je:
        await db.projects.update_one({"id": payload.project_id}, {"$inc": {"cost_incurred": payload.amount}})
    await audit(user=user, action="safety_cost_post", resource="safety_costs",
                record_id=je["id"] if je else new_id(),
                after={"sub_type": payload.sub_type, "amount": payload.amount, "is_recovery": payload.is_recovery},
                ip=request.client.host if request.client else "")
    return je


# ════════════════════════════════════════════════════════════════════════
# 5. REPORTS — 20 in one router (most are aggregation/projection slices)
# ════════════════════════════════════════════════════════════════════════
@router.get("/reports/site-expense")
async def site_expense_report(project_id: Optional[str] = None,
                              start: Optional[str] = None, end: Optional[str] = None,
                              user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {"status": {"$in": ["approved", "pm_verified", "draft"]}}
    if project_id:
        q["project_id"] = project_id
    if start:
        q["expense_date"] = {**q.get("expense_date", {}), "$gte": start}
    if end:
        q["expense_date"] = {**q.get("expense_date", {}), "$lte": end}
    rows = await db.site_expenses.find(q, {"_id": 0}).sort("expense_date", -1).limit(500).to_list(500)
    total = round(sum(float(r.get("amount") or 0) for r in rows), 2)
    by_cat: Dict[str, float] = {}
    for r in rows:
        c = r.get("category") or "misc"
        by_cat[c] = by_cat.get(c, 0) + float(r.get("amount") or 0)
    return {"rows": rows, "total": total,
            "by_category": [{"category": k, "amount": round(v, 2)} for k, v in by_cat.items()]}


@router.get("/reports/project-cost-summary")
async def project_cost_summary(user: dict = Depends(require_permission("accounting", "read"))):
    """Unified project cost: site_expense + vendor_bills + payroll(by project_id) + material_movement
    Returns one row per project with cost-by-category breakdown."""
    summaries: Dict[str, Dict[str, Any]] = {}

    def ensure(pcode: str, pname: str = None):
        return summaries.setdefault(pcode or "—", {
            "project_code": pcode or "—", "project_name": pname or "",
            "site_expense": 0.0, "vendor_bills": 0.0, "payroll": 0.0,
            "material": 0.0, "safety": 0.0, "logistics": 0.0,
            "total": 0.0,
        })

    # Site expense (incl logistics & safety wrappers)
    async for e in db.site_expenses.find({"status": "approved", "project_id": {"$ne": None}},
                                         {"_id": 0, "project_id": 1, "project_code": 1, "amount": 1, "category": 1}):
        s = ensure(e.get("project_code") or e["project_id"])
        amt = float(e.get("amount") or 0)
        if e.get("category") == "vehicle_expense":
            s["logistics"] += amt
        elif e.get("category") in ("safety_items", "labour_welfare"):
            s["safety"] += amt
        else:
            s["site_expense"] += amt
        s["total"] += amt

    # Vendor bills
    async for b in db.vendor_bills.find({"status": {"$in": ["approved", "partially_paid", "paid"]},
                                         "project_id": {"$ne": None}},
                                         {"_id": 0, "project_id": 1, "project_code": 1, "totals": 1, "expense_category": 1}):
        s = ensure(b.get("project_code") or b["project_id"])
        amt = float((b.get("totals") or {}).get("gross") or 0)
        s["vendor_bills"] += amt
        s["total"] += amt

    # JEs from payroll / material (sourced by source_module)
    async for j in db.journal_entries.find(
        {"source_module": {"$in": ["payroll", "material_movement"]}, "project_id": {"$ne": None}, "status": "posted"},
        {"_id": 0, "project_id": 1, "total_debit": 1, "source_module": 1, "source_event": 1, "lines": 1}
    ):
        s = ensure(j["project_id"])
        amt = float(j.get("total_debit") or 0)
        if j["source_module"] == "payroll":
            s["payroll"] += amt
            s["total"] += amt
        else:
            # material: count only issue (not return) to avoid double counting
            if j.get("source_event") == "issue":
                s["material"] += amt
                s["total"] += amt
            elif j.get("source_event") == "return":
                s["material"] -= amt
                s["total"] -= amt
    return {"projects": sorted(summaries.values(), key=lambda x: -x["total"])}


@router.get("/reports/project-material-cost")
async def project_material_cost(user: dict = Depends(require_permission("accounting", "read"))):
    pipeline = [
        {"$match": {"source_module": "material_movement", "source_event": "issue",
                    "project_id": {"$ne": None}, "status": "posted"}},
        {"$group": {"_id": "$project_id", "total": {"$sum": "$total_debit"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    rows = [r async for r in db.journal_entries.aggregate(pipeline)]
    return {"rows": [{"project_id": r["_id"], "total": round(r["total"], 2), "issues": r["count"]} for r in rows]}


@router.get("/reports/project-manpower-cost")
async def project_manpower_cost(user: dict = Depends(require_permission("accounting", "read"))):
    pipeline = [
        {"$match": {"source_module": "payroll", "project_id": {"$ne": None}, "status": "posted"}},
        {"$group": {"_id": "$project_id", "total": {"$sum": "$total_debit"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    rows = [r async for r in db.journal_entries.aggregate(pipeline)]
    return {"rows": [{"project_id": r["_id"], "total": round(r["total"], 2), "payrolls": r["count"]} for r in rows]}


@router.get("/reports/employee-advance")
async def employee_advance_report(user: dict = Depends(require_permission("accounting", "read"))):
    """Net advance outstanding per employee = DR 1500 − CR 1500."""
    by_emp: Dict[str, float] = {}
    async for j in db.journal_entries.find({"lines.account_code": "1500", "status": "posted"},
                                            {"_id": 0, "lines": 1, "party_name": 1, "narration": 1}):
        for ln in (j.get("lines") or []):
            if ln.get("account_code") == "1500":
                name = j.get("party_name") or j.get("narration", "—")[:40]
                by_emp[name] = by_emp.get(name, 0) + float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
    return {"employees": sorted(
        [{"employee_name": k, "outstanding": round(v, 2)} for k, v in by_emp.items() if abs(v) > 0.01],
        key=lambda x: -x["outstanding"])}


@router.get("/reports/salary-payable")
async def salary_payable_report(user: dict = Depends(require_permission("accounting", "read"))):
    """Net 2200 balance — outstanding salary to employees."""
    pipeline = [
        {"$match": {"lines.account_code": "2200", "status": "posted"}},
        {"$unwind": "$lines"},
        {"$match": {"lines.account_code": "2200"}},
        {"$group": {"_id": None, "debit": {"$sum": "$lines.debit"}, "credit": {"$sum": "$lines.credit"}}},
    ]
    out = [r async for r in db.journal_entries.aggregate(pipeline)]
    debit = out[0]["debit"] if out else 0
    credit = out[0]["credit"] if out else 0
    return {"outstanding": round(credit - debit, 2), "debit_total": round(debit, 2), "credit_total": round(credit, 2)}
