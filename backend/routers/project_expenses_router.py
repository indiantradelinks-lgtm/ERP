"""Projects & Ops · Daily Project Expense Booking + Project P&L.

Project team books ALL daily expenses (fuel, PPE, scaffolding material,
manpower, accommodation, travelling, tools, local purchase, misc…) against
the project's Cost Centers. Workflow:
    PM Verify → Dept Head → Accounts → (GM → Director when amount > threshold)
    → approved_for_payment → paid
On full approval a Journal Entry is posted (best-effort) so the expense flows
into Trial Balance / P&L. Cost center 'actual' rollups include these bookings
(see procurement_master_router._cc_actuals).

P&L: Sales = RA bills billed value (subtotal, ex-GST) with receipts shown
separately; Expenses = GRN actuals + approved daily expenses + site expenses.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import db, require_permission, now_iso, new_id
from audit import audit
from sequences import next_sequence
from exports import to_excel, to_pdf

router = APIRouter(tags=["project-expenses"])

EXPENSE_TYPES: Dict[str, Dict[str, str]] = {
    "fuel":                 {"label": "Fuel / Diesel", "account": "5141"},
    "ppe_safety":           {"label": "PPE & Safety Items", "account": "5300"},
    "scaffolding_material": {"label": "Scaffolding Material", "account": "5105"},
    "manpower":             {"label": "Manpower / Labour", "account": "5110"},
    "accommodation":        {"label": "Room / Accommodation", "account": "5151"},
    "travelling":           {"label": "Travelling / Conveyance", "account": "5140"},
    "tools":                {"label": "Tools & Tackles", "account": "5135"},
    "local_purchase":       {"label": "Local Purchase / Consumables", "account": "5105"},
    "vehicle":              {"label": "Vehicle Expense", "account": "5142"},
    "office_admin":         {"label": "Office / Admin", "account": "5400"},
    "misc":                 {"label": "Miscellaneous", "account": "5900"},
    "other":                {"label": "Other", "account": "5900"},
}

RAISE_ROLES = {"project_coordinator", "project_manager", "super_admin"}
BASE_CHAIN = [("dept_head", "Project Head")]
LARGE_CHAIN_EXTRA = [("general_manager", "GM"), ("director", "Director")]
ACCOUNTS_STEP = ("accounts_executive", "Accounts Review")
PAY_ROLES = {"super_admin", "director", "accounts_executive", "billing_executive"}


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def _large_threshold() -> float:
    doc = await db.proj_settings.find_one({"id": "global"}, {"_id": 0, "daily_expense_large_threshold": 1})
    return float((doc or {}).get("daily_expense_large_threshold") or 10000)


class ExpenseIn(BaseModel):
    id: Optional[str] = None            # pre-generated for attachments
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    cost_center_id: Optional[str] = None
    expense_type: str
    expense_date: str
    amount: float
    description: Optional[str] = ""
    bill_no: Optional[str] = None
    paid_to: Optional[str] = None
    paid_to_type: Optional[str] = None   # vendor | person
    employee_id: Optional[str] = None
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    payment_mode: str = "Cash"
    settlement_mode: str = "petty_cash"  # petty_cash | employee_reimbursement | vendor_payable
    remarks: Optional[str] = None


class ActionIn(BaseModel):
    remarks: Optional[str] = None


class PaidIn(BaseModel):
    payment_ref: Optional[str] = None


@router.get("/project-expenses/types")
async def expense_types(user: dict = Depends(require_permission("project_expenses", "read"))):
    return [{"key": k, **v} for k, v in EXPENSE_TYPES.items()]


@router.get("/project-expenses/settings")
async def expense_settings(user: dict = Depends(require_permission("project_expenses", "read"))):
    return {"large_threshold": await _large_threshold()}


@router.get("/project-expenses")
async def list_expenses(project_code: Optional[str] = None, status: Optional[str] = None,
                        expense_type: Optional[str] = None, cost_center_id: Optional[str] = None,
                        from_date: Optional[str] = None, to_date: Optional[str] = None,
                        user: dict = Depends(require_permission("project_expenses", "read"))):
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    if expense_type:
        q["expense_type"] = expense_type
    if cost_center_id:
        q["cost_center_id"] = cost_center_id
    if from_date or to_date:
        rng: Dict[str, str] = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date
        q["expense_date"] = rng
    rows = await db.project_expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    for r in rows:
        r["attachment_count"] = await db.files.count_documents({"parent_type": "project_expenses", "parent_id": r["id"]})
    return rows


@router.get("/project-expenses/summary")
async def expense_summary(project_code: Optional[str] = None,
                          user: dict = Depends(require_permission("project_expenses", "read"))):
    q: Dict[str, Any] = {"project_code": project_code} if project_code else {}
    rows = await db.project_expenses.find(q, {"_id": 0, "status": 1, "amount": 1, "expense_date": 1}).to_list(5000)
    today = now_iso()[:10]
    return {
        "total": len(rows),
        "pending": sum(1 for r in rows if r["status"] == "pending_approval"),
        "approved": sum(1 for r in rows if r["status"] == "approved_for_payment"),
        "paid": sum(1 for r in rows if r["status"] == "paid"),
        "booked_today": round(sum(float(r["amount"]) for r in rows if r.get("expense_date") == today and r["status"] != "rejected"), 2),
        "total_amount": round(sum(float(r["amount"]) for r in rows if r["status"] in ("approved_for_payment", "paid")), 2),
    }


@router.post("/project-expenses")
async def create_expense(p: ExpenseIn, request: Request,
                         user: dict = Depends(require_permission("project_expenses", "write"))):
    if user.get("role") not in RAISE_ROLES:
        raise HTTPException(403, "Expense requests can only be raised by the Project Coordinator or Project Manager")
    if p.expense_type not in EXPENSE_TYPES:
        raise HTTPException(400, f"expense_type must be one of {sorted(EXPENSE_TYPES)}")
    if p.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    project = None
    if p.project_id:
        project = await db.projects.find_one({"id": p.project_id}, {"_id": 0})
    elif p.project_code:
        project = await db.projects.find_one({"code": p.project_code}, {"_id": 0})
    if not project:
        raise HTTPException(400, "Select a valid project")
    cc = None
    if p.cost_center_id:
        cc = await db.cost_centers.find_one({"id": p.cost_center_id}, {"_id": 0})
        if not cc or cc.get("project_id") != project["id"]:
            raise HTTPException(400, "Cost center does not belong to the selected project")
    threshold = await _large_threshold()
    steps = BASE_CHAIN + (LARGE_CHAIN_EXTRA if p.amount > threshold else []) + [ACCOUNTS_STEP]
    chain = [{"role": r, "label": l, "status": "pending", "by": None, "at": None, "remarks": None} for r, l in steps]
    doc = {
        "id": p.id or new_id(),
        "expense_no": await next_sequence("PEX"),
        "project_id": project["id"], "project_code": project.get("code"),
        "project_name": project.get("name"), "client_name": project.get("client"),
        "cost_center_id": (cc or {}).get("id"), "category_code": (cc or {}).get("category_code"),
        "category_name": (cc or {}).get("category_name"),
        "expense_type": p.expense_type, "expense_type_label": EXPENSE_TYPES[p.expense_type]["label"],
        "expense_date": p.expense_date, "amount": round(float(p.amount), 2),
        "description": p.description or "", "bill_no": p.bill_no, "paid_to": p.paid_to,
        "paid_to_type": p.paid_to_type,
        "employee_id": p.employee_id, "employee_code": p.employee_code, "employee_name": p.employee_name,
        "payment_mode": p.payment_mode, "settlement_mode": p.settlement_mode,
        "remarks": p.remarks,
        "is_large_value": p.amount > threshold, "large_threshold": threshold,
        "status": "pending_approval", "chain": chain, "current_step": 0,
        "je_id": None, "payment_ref": None, "paid_at": None, "paid_by": None,
        "created_at": now_iso(), "created_by": user.get("name") or user.get("email"),
        "created_by_id": user.get("id"),
    }
    await db.project_expenses.insert_one(doc); doc.pop("_id", None)
    await audit(user=user, action="create", resource="project_expenses", record_id=doc["id"], after=doc, ip=_ip(request))
    return doc


def _can_act(user: dict, step_role: str) -> bool:
    return user.get("role") in (step_role, "super_admin")


@router.post("/project-expenses/{eid}/approve")
async def approve_expense(eid: str, p: ActionIn, request: Request,
                          user: dict = Depends(require_permission("project_expenses", "write"))):
    row = await db.project_expenses.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] != "pending_approval":
        raise HTTPException(400, f"Cannot approve in status {row['status']}")
    idx = row["current_step"]
    step = row["chain"][idx]
    if not _can_act(user, step["role"]):
        raise HTTPException(403, f"This step requires {step['label']} ({step['role']})")
    row["chain"][idx] = {**step, "status": "approved", "by": user.get("name") or user.get("email"),
                         "at": now_iso(), "remarks": p.remarks}
    patch: Dict[str, Any] = {"chain": row["chain"]}
    if idx + 1 < len(row["chain"]):
        patch["current_step"] = idx + 1
        # When the next step is Accounts Review, notify Accounts: Request For Payment
        if row["chain"][idx + 1]["role"] == "accounts_executive":
            await _notify_accounts(row)
    else:
        patch["status"] = "approved_for_payment"
        patch["approved_at"] = now_iso()
        patch["je_id"] = await _post_expense_je(row, user)
    await db.project_expenses.update_one({"id": eid}, {"$set": patch})
    await audit(user=user, action="pex_approve", resource="project_expenses", record_id=eid,
                after={"step": step["label"]}, ip=_ip(request))
    return await db.project_expenses.find_one({"id": eid}, {"_id": 0})


async def _notify_accounts(row: dict) -> None:
    """In-app 'Request For Payment' notification to Accounts users."""
    try:
        acct_users = await db.users.find({"role": {"$in": ["accounts_executive", "billing_executive"]}},
                                         {"_id": 0, "id": 1}).to_list(100)
        if not acct_users:
            acct_users = await db.users.find({"role": "super_admin"}, {"_id": 0, "id": 1}).to_list(10)
        for u in acct_users:
            await db.notifications.insert_one({
                "id": new_id(), "user_id": u["id"], "kind": "expense_payment_request",
                "title": f"Request For Payment — {row['expense_no']}",
                "message": f"{row['expense_type_label']} · {row['project_code']} · ₹{float(row['amount']):,.0f} "
                           f"approved by project authorities. Please review and process payment.",
                "link": "/app/ops/expenses", "read": False, "at": now_iso()})
    except Exception:
        pass


async def _post_expense_je(row: dict, user: dict) -> Optional[str]:
    try:
        from accounting_service import post_journal_entry
        account = EXPENSE_TYPES[row["expense_type"]]["account"]
        amount = float(row["amount"])
        lines = [{"account_code": account, "debit": amount, "credit": 0,
                  "project_id": row.get("project_id"),
                  "narration": f"Project expense ({row['expense_type_label']})"}]
        settlement = row.get("settlement_mode") or "petty_cash"
        credit_code = {"petty_cash": "1115", "employee_reimbursement": "2200", "vendor_payable": "2100"}.get(settlement, "1115")
        lines.append({"account_code": credit_code, "debit": 0, "credit": amount, "narration": settlement.replace("_", " ")})
        je = await post_journal_entry(
            date=row["expense_date"], narration=f"Daily Project Expense {row['expense_no']} — {row['expense_type_label']}",
            lines=lines, source_module="project_expense", source_id=row["id"], source_event="approve",
            source_ref=row["expense_no"], project_id=row.get("project_id"),
            posted_by=user.get("name") or user.get("email"), voucher_type="EV", status="posted")
        return (je or {}).get("id")
    except Exception:
        return None


@router.post("/project-expenses/{eid}/reject")
async def reject_expense(eid: str, p: ActionIn, request: Request,
                         user: dict = Depends(require_permission("project_expenses", "write"))):
    row = await db.project_expenses.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] != "pending_approval":
        raise HTTPException(400, f"Cannot reject in status {row['status']}")
    idx = row["current_step"]
    step = row["chain"][idx]
    if not _can_act(user, step["role"]):
        raise HTTPException(403, f"This step requires {step['label']} ({step['role']})")
    row["chain"][idx] = {**step, "status": "rejected", "by": user.get("name") or user.get("email"),
                         "at": now_iso(), "remarks": p.remarks}
    await db.project_expenses.update_one({"id": eid}, {"$set": {
        "chain": row["chain"], "status": "rejected", "rejected_reason": p.remarks}})
    await audit(user=user, action="pex_reject", resource="project_expenses", record_id=eid,
                after={"reason": p.remarks}, ip=_ip(request))
    return await db.project_expenses.find_one({"id": eid}, {"_id": 0})


@router.post("/project-expenses/{eid}/mark-paid")
async def mark_paid(eid: str, p: PaidIn, request: Request,
                    user: dict = Depends(require_permission("project_expenses", "write"))):
    if user.get("role") not in PAY_ROLES:
        raise HTTPException(403, "Only Accounts / Director can mark expenses as paid")
    row = await db.project_expenses.find_one({"id": eid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] != "approved_for_payment":
        raise HTTPException(400, "Expense must be fully approved before payment")
    proof_count = await db.files.count_documents({"parent_type": "project_expenses", "parent_id": eid,
                                                  "category": "payment_proof"})
    if proof_count == 0:
        raise HTTPException(400, "Attach the payment proof (UTR screenshot / voucher) before marking paid")
    await db.project_expenses.update_one({"id": eid}, {"$set": {
        "status": "paid", "payment_ref": p.payment_ref, "paid_at": now_iso(),
        "paid_by": user.get("name") or user.get("email"), "payment_proof_count": proof_count}})
    await audit(user=user, action="pex_paid", resource="project_expenses", record_id=eid,
                after={"payment_ref": p.payment_ref}, ip=_ip(request))
    return await db.project_expenses.find_one({"id": eid}, {"_id": 0})


@router.delete("/project-expenses/{eid}")
async def delete_expense(eid: str, request: Request,
                         user: dict = Depends(require_permission("project_expenses", "delete"))):
    row = await db.project_expenses.find_one({"id": eid}, {"_id": 0, "status": 1})
    if not row:
        raise HTTPException(404, "Not found")
    if row["status"] in ("approved_for_payment", "paid"):
        raise HTTPException(400, "Cannot delete an approved/paid expense")
    await db.project_expenses.delete_one({"id": eid})
    await audit(user=user, action="delete", resource="project_expenses", record_id=eid, ip=_ip(request))
    return {"deleted": True}


@router.get("/project-expenses/export.{fmt}")
async def export_expenses(fmt: str, project_code: Optional[str] = None, status: Optional[str] = None,
                          user: dict = Depends(require_permission("project_expenses", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "Format must be xlsx or pdf")
    q: Dict[str, Any] = {}
    if project_code:
        q["project_code"] = project_code
    if status:
        q["status"] = status
    rows = await db.project_expenses.find(q, {"_id": 0}).sort("expense_date", -1).to_list(5000)
    data = to_excel("project_expenses", rows) if fmt == "xlsx" else to_pdf("project_expenses", rows)
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if fmt == "xlsx" else "application/pdf")
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="project_expenses.{fmt}"'})


# ═══════════════ PROJECT P&L ═══════════════
async def _project_pnl(project: dict) -> dict:
    code = project.get("code")
    pid = project.get("id")
    bills = await db.ra_bills.find({"project_code": code, "status": {"$nin": ["cancelled", "draft_cancelled"]}},
                                   {"_id": 0, "subtotal": 1, "gross_value": 1, "paid_amount": 1}).to_list(1000)
    income_billed = round(sum(float(b.get("subtotal") or 0) for b in bills), 2)
    income_gross = round(sum(float(b.get("gross_value") or 0) for b in bills), 2)
    receipts = round(sum(float(b.get("paid_amount") or 0) for b in bills), 2)

    expenses: Dict[str, float] = {}
    grn_rows = await db.grn.find({"project_id": pid}, {"_id": 0, "items": 1}).to_list(2000)
    grn_total = sum(float(it.get("amount") or it.get("total") or 0)
                    for g in grn_rows for it in (g.get("items") or []))
    if grn_total:
        expenses["Material / Procurement (GRN)"] = round(grn_total, 2)
    pex = await db.project_expenses.find({"project_id": pid, "status": {"$in": ["approved_for_payment", "paid"]}},
                                         {"_id": 0, "expense_type_label": 1, "amount": 1}).to_list(3000)
    for e in pex:
        key = e.get("expense_type_label") or "Daily Expense"
        expenses[key] = round(expenses.get(key, 0) + float(e.get("amount") or 0), 2)
    se = await db.site_expenses.find({"$or": [{"project_id": pid}, {"project_code": code}], "status": "approved"},
                                     {"_id": 0, "amount": 1}).to_list(2000)
    se_total = sum(float(x.get("amount") or 0) for x in se)
    if se_total:
        expenses["Site Expenses (petty cash)"] = round(se_total, 2)

    total_expense = round(sum(expenses.values()), 2)
    gross_profit = round(income_billed - total_expense, 2)
    margin = round(gross_profit / income_billed * 100, 1) if income_billed else 0.0
    return {
        "project_id": pid, "project_code": code, "project_name": project.get("name"),
        "client": project.get("client"), "status": project.get("status"),
        "income_billed": income_billed, "income_gross": income_gross, "receipts": receipts,
        "expenses_by_category": expenses, "total_expense": total_expense,
        "gross_profit": gross_profit, "margin_pct": margin, "bills_count": len(bills),
    }


@router.get("/project-pnl")
async def project_pnl(project_code: Optional[str] = None,
                      user: dict = Depends(require_permission("project_pnl", "read"))):
    if project_code:
        project = await db.projects.find_one({"code": project_code}, {"_id": 0})
        if not project:
            raise HTTPException(404, "Project not found")
        return await _project_pnl(project)
    projects = await db.projects.find({}, {"_id": 0}).sort("code", -1).to_list(300)
    rows = [await _project_pnl(p) for p in projects]
    rows = [r for r in rows if r["income_billed"] or r["total_expense"]]
    return {
        "projects": rows,
        "totals": {
            "income_billed": round(sum(r["income_billed"] for r in rows), 2),
            "receipts": round(sum(r["receipts"] for r in rows), 2),
            "total_expense": round(sum(r["total_expense"] for r in rows), 2),
            "gross_profit": round(sum(r["gross_profit"] for r in rows), 2),
        },
    }


@router.get("/project-pnl/export.{fmt}")
async def export_pnl(fmt: str, user: dict = Depends(require_permission("project_pnl", "read"))):
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "Format must be xlsx or pdf")
    data_all = await project_pnl(None, user)  # type: ignore[arg-type]
    rows = [{
        "project_code": r["project_code"], "project_name": r["project_name"], "client": r["client"],
        "income_billed": r["income_billed"], "receipts": r["receipts"],
        "total_expense": r["total_expense"], "gross_profit": r["gross_profit"], "margin_pct": r["margin_pct"],
    } for r in data_all["projects"]]
    data = to_excel("project_pnl", rows) if fmt == "xlsx" else to_pdf("project_pnl", rows)
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if fmt == "xlsx" else "application/pdf")
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="project_pnl.{fmt}"'})
