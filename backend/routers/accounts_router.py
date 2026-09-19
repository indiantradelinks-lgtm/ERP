"""
Accounts Router · /api/accounts/...  (Iter 71)

Endpoints:
  GET  /accounts/chart-of-accounts          List CoA
  POST /accounts/chart-of-accounts          Create a CoA row (admin)
  PUT  /accounts/chart-of-accounts/{id}     Update CoA row
  DELETE /accounts/chart-of-accounts/{id}   Soft-disable (is_active=False)
  POST /accounts/chart-of-accounts/seed     Seed default 30 accounts (idempotent)

  POST /accounts/journal-entries            Manual double-entry JE (admin/accountant)
  GET  /accounts/journal-entries            Filterable JE list (date/project/department/account)

  GET  /accounts/reports/trial-balance      Trial Balance
  GET  /accounts/reports/profit-and-loss    P&L
  GET  /accounts/reports/ar-aging           AR aging buckets
  GET  /accounts/reports/ap-aging           AP aging buckets
  GET  /accounts/reports/general-ledger     GL by account (drill-down)
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, require_permission, now_iso, new_id
from pagination import maybe_paged, paged_or_rows
from audit import audit
from sequences import next_sequence
from accounting_service import (
    DEFAULT_COA, ensure_coa_seeded, post_journal_entry,
    trial_balance, profit_and_loss, ar_aging, ap_aging,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


# ─── Chart of Accounts ────────────────────────────────────────────────────
class CoAIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=2, max_length=120)
    type: str = Field(..., pattern="^(asset|liability|equity|revenue|expense)$")
    subtype: Optional[str] = None
    parent_code: Optional[str] = None
    opening_balance: float = 0
    is_active: bool = True


@router.get("/chart-of-accounts")
async def list_coa(active_only: bool = True,
                   user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if active_only:
        q["is_active"] = {"$ne": False}
    rows = await db.chart_of_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    return rows


@router.post("/chart-of-accounts/seed")
async def seed_coa(user: dict = Depends(require_permission("accounting", "write"))):
    inserted = await ensure_coa_seeded()
    return {"inserted": inserted, "total": len(DEFAULT_COA)}


@router.post("/chart-of-accounts")
async def create_coa(payload: CoAIn, request: Request,
                     user: dict = Depends(require_permission("accounting", "write"))):
    existing = await db.chart_of_accounts.find_one({"code": payload.code}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=409, detail=f"Account code {payload.code} already exists")
    doc = {
        "id": new_id(),
        **payload.model_dump(),
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.chart_of_accounts.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="create", resource="chart_of_accounts",
                record_id=doc["id"], after=doc, ip=request.client.host if request.client else "")
    return doc


@router.put("/chart-of-accounts/{coa_id}")
async def update_coa(coa_id: str, payload: dict, request: Request,
                     user: dict = Depends(require_permission("accounting", "write"))):
    payload.pop("id", None)
    payload.pop("code", None)  # code immutable
    payload["updated_at"] = now_iso()
    res = await db.chart_of_accounts.update_one({"id": coa_id}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="CoA row not found")
    return await db.chart_of_accounts.find_one({"id": coa_id}, {"_id": 0})


@router.delete("/chart-of-accounts/{coa_id}")
async def delete_coa(coa_id: str, user: dict = Depends(require_permission("accounting", "write"))):
    """Soft-disable. We never hard-delete because historical JEs reference the code."""
    await db.chart_of_accounts.update_one({"id": coa_id}, {"$set": {"is_active": False, "updated_at": now_iso()}})
    return {"ok": True}


# ─── Manual Journal Entries ───────────────────────────────────────────────
class JELineIn(BaseModel):
    account_code: str
    debit: float = 0
    credit: float = 0
    project_id: Optional[str] = None
    cost_centre: Optional[str] = None
    department: Optional[str] = None
    narration: Optional[str] = None


class JEIn(BaseModel):
    date: str
    narration: str
    lines: List[JELineIn]
    project_id: Optional[str] = None
    department: Optional[str] = None


@router.post("/journal-entries")
async def post_manual_je(payload: JEIn, request: Request,
                         user: dict = Depends(require_permission("accounting", "write"))):
    je = await post_journal_entry(
        date=payload.date,
        narration=payload.narration,
        lines=[ln.model_dump() for ln in payload.lines],
        source_module="manual",
        source_id=new_id(),
        source_event="manual_post",
        project_id=payload.project_id,
        department=payload.department,
        posted_by=user.get("name") or user.get("email"),
    )
    if not je:
        raise HTTPException(status_code=400, detail="Journal entry is unbalanced — debit must equal credit and be > 0.")
    await audit(user=user, action="create", resource="journal_entries",
                record_id=je["id"], after={"je_number": je["je_number"], "total": je["total_debit"]},
                ip=request.client.host if request.client else "")
    return je


@router.get("/journal-entries")
async def list_je(start: Optional[str] = None, end: Optional[str] = None,
                  project_id: Optional[str] = None, department: Optional[str] = None,
                  account_code: Optional[str] = None, source_module: Optional[str] = None,
                  limit: int = 500,
                  user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if start:
        q["date"] = {**q.get("date", {}), "$gte": start}
    if end:
        q["date"] = {**q.get("date", {}), "$lte": end}
    if project_id:
        q["project_id"] = project_id
    if department:
        q["department"] = department
    if source_module:
        q["source_module"] = source_module
    if account_code:
        q["$or"] = [
            {"lines.account_code": account_code},
            {"account": {"$regex": f"^{account_code}", "$options": "i"}},  # legacy
        ]
    rows = await db.journal_entries.find(q, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
    return rows


# ─── Reports ──────────────────────────────────────────────────────────────
@router.get("/reports/trial-balance")
async def report_trial_balance(start: Optional[str] = None, end: Optional[str] = None,
                                project_id: Optional[str] = None, department: Optional[str] = None,
                                user: dict = Depends(require_permission("accounting", "read"))):
    rows = await trial_balance(start, end, project_id, department)
    total_dr = round(sum(r["debit_total"] for r in rows), 2)
    total_cr = round(sum(r["credit_total"] for r in rows), 2)
    return {
        "filters": {"start": start, "end": end, "project_id": project_id, "department": department},
        "rows": rows,
        "totals": {"debit": total_dr, "credit": total_cr, "diff": round(total_dr - total_cr, 2)},
    }


@router.get("/reports/profit-and-loss")
async def report_pl(start: Optional[str] = None, end: Optional[str] = None,
                    project_id: Optional[str] = None, department: Optional[str] = None,
                    user: dict = Depends(require_permission("accounting", "read"))):
    return await profit_and_loss(start, end, project_id, department)


@router.get("/reports/ar-aging")
async def report_ar(asof: Optional[str] = None,
                    user: dict = Depends(require_permission("accounting", "read"))):
    return await ar_aging(asof)


@router.get("/reports/ap-aging")
async def report_ap(asof: Optional[str] = None,
                    user: dict = Depends(require_permission("accounting", "read"))):
    return await ap_aging(asof)


@router.get("/reports/general-ledger")
async def report_gl(account_code: str, start: Optional[str] = None, end: Optional[str] = None,
                    project_id: Optional[str] = None,
                    user: dict = Depends(require_permission("accounting", "read"))):
    """GL drill-down: every line touching an account, with running balance."""
    coa = await db.chart_of_accounts.find_one({"code": account_code}, {"_id": 0})
    if not coa:
        raise HTTPException(status_code=404, detail=f"Account {account_code} not found")
    q: Dict[str, Any] = {"lines.account_code": account_code}
    if start:
        q["date"] = {**q.get("date", {}), "$gte": start}
    if end:
        q["date"] = {**q.get("date", {}), "$lte": end}
    jes = await db.journal_entries.find(q, {"_id": 0}).sort("date", 1).to_list(5000)

    opening = float(coa.get("opening_balance") or 0)
    is_debit_normal = coa["type"] in {"asset", "expense"}
    running = opening if is_debit_normal else -opening

    rows: List[Dict[str, Any]] = []
    for je in jes:
        for ln in (je.get("lines") or []):
            if ln.get("account_code") != account_code:
                continue
            if project_id and ln.get("project_id") and ln.get("project_id") != project_id:
                continue
            debit = float(ln.get("debit") or 0)
            credit = float(ln.get("credit") or 0)
            running += (debit - credit) if is_debit_normal else (credit - debit)
            rows.append({
                "date":     je.get("date"),
                "je_number": je.get("je_number"),
                "narration": je.get("narration"),
                "debit":  debit, "credit": credit,
                "project_id": ln.get("project_id") or je.get("project_id"),
                "department": ln.get("department") or je.get("department"),
                "source":   f"{je.get('source_module', 'manual')}:{je.get('source_event', 'manual')}",
                "running":  round(running, 2),
            })
    return {
        "account": {"code": coa["code"], "name": coa["name"], "type": coa["type"], "opening_balance": opening},
        "filters": {"start": start, "end": end, "project_id": project_id},
        "rows": rows,
        "closing_balance": round(running, 2),
    }


# ════════════════════════════════════════════════════════════════════════
# PHASE 1 ── Vouchers, Dashboard, Day Book, Opening Balance, Audit, Inbox
# ════════════════════════════════════════════════════════════════════════

VOUCHER_TYPES: Dict[str, str] = {
    "SV":  "Sales Voucher",
    "PUV": "Purchase Voucher",
    "PV":  "Payment Voucher",
    "RV":  "Receipt Voucher",
    "JV":  "Journal Voucher",
    "CV":  "Contra Voucher",
    "DN":  "Debit Note",
    "CN":  "Credit Note",
    "EV":  "Expense Voucher",
    "PYV": "Payroll Voucher",
    "ADJ": "Adjustment Voucher",
    "REV": "Reversal Voucher",
}

# Voucher-type → JE source_module bucket. Drives dashboard breakdowns.
VOUCHER_SOURCE_MAP = {
    "SV": "sales_voucher", "PUV": "purchase_voucher",
    "PV": "payment_voucher", "RV": "receipt_voucher",
    "JV": "manual", "CV": "contra_voucher",
    "DN": "debit_note", "CN": "credit_note",
    "EV": "expense_voucher", "PYV": "payroll_voucher",
    "ADJ": "adjustment_voucher", "REV": "reversal_voucher",
}


class VoucherLineIn(BaseModel):
    account_code: str
    debit: float = 0
    credit: float = 0
    project_id: Optional[str] = None
    cost_centre: Optional[str] = None
    narration: Optional[str] = None


class VoucherIn(BaseModel):
    voucher_type: str = Field(..., description="One of SV/PUV/PV/RV/JV/CV/DN/CN/EV/PYV/ADJ/REV")
    date: str
    narration: str
    lines: List[VoucherLineIn]
    project_id: Optional[str] = None
    department: Optional[str] = None
    party_type: Optional[str] = None
    party_id: Optional[str] = None
    party_name: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = "posted"  # 'draft' | 'pending_approval' | 'posted'


@router.get("/voucher-types")
async def list_voucher_types(user: dict = Depends(require_permission("accounting", "read"))):
    """Static metadata: code → label. Drives Voucher Type dropdown on UI."""
    return [{"code": k, "label": v} for k, v in VOUCHER_TYPES.items()]


@router.post("/vouchers")
async def create_voucher(payload: VoucherIn, request: Request,
                         user: dict = Depends(require_permission("accounting", "write"))):
    """Create a voucher.

    Rules enforced:
      • DR total must equal CR total before posting (status='posted')
      • Drafts/pending allowed unbalanced (will be re-validated on post)
      • Amount > 0 enforced via balanced check
      • Auto-generates voucher_number per type series, e.g. PV-2026-0001
      • Audit-logged in audit_logs
    """
    vt = payload.voucher_type.upper()
    if vt not in VOUCHER_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown voucher_type {vt}")
    total_dr = round(sum(ln.debit for ln in payload.lines), 2)
    total_cr = round(sum(ln.credit for ln in payload.lines), 2)
    status = (payload.status or "posted").lower()

    if status == "posted":
        if abs(total_dr - total_cr) > 0.01 or total_dr <= 0:
            raise HTTPException(status_code=400,
                detail=f"Cannot post {vt}: debit ({total_dr}) must equal credit ({total_cr}) and be > 0")

    vno = await next_sequence(vt)  # PV-2026-0001 etc.

    if status == "posted":
        je = await post_journal_entry(
            date=payload.date, narration=payload.narration,
            lines=[ln.model_dump() for ln in payload.lines],
            source_module=VOUCHER_SOURCE_MAP.get(vt, "manual"),
            source_id=new_id(), source_event=f"{vt.lower()}_post",
            project_id=payload.project_id, department=payload.department,
            posted_by=user.get("name") or user.get("email"),
            voucher_type=vt, voucher_number=vno, status="posted",
            party_type=payload.party_type, party_id=payload.party_id, party_name=payload.party_name,
            attachments=payload.attachments,
        )
        if not je:
            raise HTTPException(status_code=400, detail="Voucher rejected — unbalanced or zero-amount")
        await audit(user=user, action="voucher_post", resource="vouchers",
                    record_id=je["id"], after={"voucher_number": vno, "voucher_type": vt, "total": total_dr},
                    ip=request.client.host if request.client else "")
        return je

    # Draft / pending_approval — stored in same collection but with status flag and NO JE side-effects
    doc = {
        "id": new_id(),
        "je_number": vno, "voucher_number": vno, "voucher_type": vt,
        "date": payload.date, "narration": payload.narration,
        "lines": [ln.model_dump() for ln in payload.lines],
        "total_debit": total_dr, "total_credit": total_cr,
        "project_id": payload.project_id, "department": payload.department,
        "party_type": payload.party_type, "party_id": payload.party_id, "party_name": payload.party_name,
        "attachments": payload.attachments or [],
        "source_module": VOUCHER_SOURCE_MAP.get(vt, "manual"),
        "source_id": new_id(), "source_event": f"{vt.lower()}_draft",
        "posted_by": user.get("name") or user.get("email"),
        "is_auto_posted": False, "status": status,
        "created_at": now_iso(),
    }
    await db.journal_entries.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="voucher_create", resource="vouchers",
                record_id=doc["id"], after={"voucher_number": vno, "voucher_type": vt, "status": status},
                ip=request.client.host if request.client else "")
    return doc


@router.get("/vouchers")
async def list_vouchers(request: Request, voucher_type: Optional[str] = None,
                        status: Optional[str] = None,
                        start: Optional[str] = None, end: Optional[str] = None,
                        limit: int = 200,
                        user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if voucher_type:
        q["voucher_type"] = voucher_type.upper()
    if status:
        q["status"] = status
    if start:
        q["date"] = {**q.get("date", {}), "$gte": start}
    if end:
        q["date"] = {**q.get("date", {}), "$lte": end}
    paged = await maybe_paged(request, "journal_entries", q, "date",
                              ["voucher_no", "narration", "description", "status", "source_module", "project_code", "lines.account_name"])
    if paged:
        return paged
    rows = await db.journal_entries.find(q, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
    return rows


@router.post("/vouchers/{voucher_id}/approve")
async def approve_voucher(voucher_id: str, request: Request,
                          user: dict = Depends(require_permission("accounting", "write"))):
    v = await db.journal_entries.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Voucher not found")
    if v.get("status") == "posted":
        raise HTTPException(status_code=400, detail="Voucher already posted")
    # Re-validate balance
    total_dr = round(sum(float(ln.get("debit") or 0) for ln in (v.get("lines") or [])), 2)
    total_cr = round(sum(float(ln.get("credit") or 0) for ln in (v.get("lines") or [])), 2)
    if abs(total_dr - total_cr) > 0.01 or total_dr <= 0:
        raise HTTPException(status_code=400,
            detail=f"Cannot post — debit ({total_dr}) must equal credit ({total_cr}) and be > 0")
    await db.journal_entries.update_one({"id": voucher_id}, {"$set": {
        "status": "posted",
        "approved_by": user.get("name") or user.get("email"),
        "approved_at": now_iso(),
        "is_auto_posted": False,
    }})
    await audit(user=user, action="voucher_approve", resource="vouchers",
                record_id=voucher_id, after={"voucher_number": v.get("voucher_number")},
                ip=request.client.host if request.client else "")
    return await db.journal_entries.find_one({"id": voucher_id}, {"_id": 0})


@router.post("/vouchers/{voucher_id}/reverse")
async def reverse_voucher(voucher_id: str, request: Request,
                          user: dict = Depends(require_permission("accounting", "write"))):
    """Create a Reversal Voucher (REV-####) flipping DR/CR of the source voucher.
    Both rows stay in the ledger — DOES NOT delete the original."""
    src = await db.journal_entries.find_one({"id": voucher_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Source voucher not found")
    if src.get("status") != "posted":
        raise HTTPException(status_code=400, detail="Only posted vouchers can be reversed")
    if src.get("reversed_by"):
        raise HTTPException(status_code=409, detail=f"Already reversed by {src.get('reversed_by')}")

    flipped_lines = [{
        "account_code": ln.get("account_code"),
        "debit":  float(ln.get("credit") or 0),
        "credit": float(ln.get("debit") or 0),
        "project_id": ln.get("project_id"),
        "cost_centre": ln.get("cost_centre"),
        "narration": ln.get("narration"),
    } for ln in (src.get("lines") or [])]

    rev_no = await next_sequence("REV")
    rev = await post_journal_entry(
        date=now_iso()[:10],
        narration=f"Reversal of {src.get('voucher_number')} — {src.get('narration')}",
        lines=flipped_lines,
        source_module="reversal_voucher", source_id=new_id(),
        source_event="reversal_post", source_ref=src.get("voucher_number"),
        project_id=src.get("project_id"), department=src.get("department"),
        posted_by=user.get("name") or user.get("email"),
        voucher_type="REV", voucher_number=rev_no, status="posted",
    )
    await db.journal_entries.update_one({"id": voucher_id}, {"$set": {
        "reversed_by": rev_no, "reversed_at": now_iso(), "reversed_by_user": user.get("name") or user.get("email"),
    }})
    await audit(user=user, action="voucher_reverse", resource="vouchers",
                record_id=voucher_id, after={"reversal_no": rev_no},
                ip=request.client.host if request.client else "")
    return rev


@router.get("/vouchers/{voucher_id}")
async def get_voucher(voucher_id: str,
                      user: dict = Depends(require_permission("accounting", "read"))):
    v = await db.journal_entries.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Voucher not found")
    return v


# ─── Opening Balance ──────────────────────────────────────────────────────
class OpeningBalanceIn(BaseModel):
    entries: List[Dict[str, Any]]  # [{account_code, debit, credit}]
    date: str
    narration: Optional[str] = "Opening balance"


@router.post("/opening-balance")
async def post_opening_balance(payload: OpeningBalanceIn, request: Request,
                                user: dict = Depends(require_permission("accounting", "write"))):
    """Post opening balances. Creates a single balanced JE with the supplied lines.

    Also updates the `opening_balance` field on each touched CoA row so reports
    that read opening_balance directly (e.g. GL drill-down) stay consistent.
    """
    lines = [{
        "account_code": e["account_code"],
        "debit":  float(e.get("debit") or 0),
        "credit": float(e.get("credit") or 0),
    } for e in payload.entries if e.get("account_code")]
    if not lines:
        raise HTTPException(status_code=400, detail="At least one line required")

    je = await post_journal_entry(
        date=payload.date, narration=payload.narration or "Opening balance",
        lines=lines, source_module="opening_balance", source_id=new_id(),
        source_event="opening_post", voucher_type="JV", status="posted",
        posted_by=user.get("name") or user.get("email"),
    )
    if not je:
        raise HTTPException(status_code=400, detail="Opening balance unbalanced — debit must equal credit")

    # Mirror onto CoA.opening_balance for legacy readers
    for ln in lines:
        bal = float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
        if abs(bal) > 0.001:
            await db.chart_of_accounts.update_one(
                {"code": ln["account_code"]},
                {"$set": {"opening_balance": bal, "opening_balance_date": payload.date}},
            )
    await audit(user=user, action="opening_balance_post", resource="opening_balance",
                record_id=je["id"], after={"je": je["je_number"], "lines": len(lines)},
                ip=request.client.host if request.client else "")
    return je


# ─── Day Book ─────────────────────────────────────────────────────────────
@router.get("/reports/day-book")
async def report_day_book(date: Optional[str] = None,
                          start: Optional[str] = None, end: Optional[str] = None,
                          user: dict = Depends(require_permission("accounting", "read"))):
    """Day Book — all vouchers for a given date or range, grouped by date desc."""
    q: Dict[str, Any] = {}
    if date:
        q["date"] = date
    else:
        if start:
            q["date"] = {**q.get("date", {}), "$gte": start}
        if end:
            q["date"] = {**q.get("date", {}), "$lte": end}
    rows = await db.journal_entries.find(q, {"_id": 0}).sort("date", -1).limit(1000).to_list(1000)
    # Group by date
    grouped: Dict[str, List[Any]] = {}
    for r in rows:
        d = r.get("date") or "—"
        grouped.setdefault(d, []).append(r)
    return {
        "days": [{"date": d, "entries": grouped[d],
                  "total_debit":  round(sum(float(e.get("total_debit")  or e.get("amount") or 0) for e in grouped[d]), 2),
                  "total_credit": round(sum(float(e.get("total_credit") or e.get("amount") or 0) for e in grouped[d]), 2)}
                 for d in sorted(grouped.keys(), reverse=True)],
        "filters": {"date": date, "start": start, "end": end},
    }


# ─── Audit Trail ──────────────────────────────────────────────────────────
@router.get("/audit-trail")
async def list_audit(resource: Optional[str] = None,
                     record_id: Optional[str] = None,
                     actor_id: Optional[str] = None,
                     limit: int = 200,
                     user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if resource:
        q["resource"] = resource
    if record_id:
        q["record_id"] = record_id
    if actor_id:
        q["actor_id"] = actor_id
    # By default, scope to accounting-related resources
    if not (resource or record_id or actor_id):
        q["resource"] = {"$in": ["vouchers", "journal_entries", "chart_of_accounts", "opening_balance"]}
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("ts", -1).limit(limit).to_list(limit)
    return rows


# ─── Approval Inbox ───────────────────────────────────────────────────────
@router.get("/approval-inbox")
async def approval_inbox(user: dict = Depends(require_permission("accounting", "read"))):
    """Vouchers awaiting approval (status='pending_approval' or 'draft')."""
    rows = await db.journal_entries.find(
        {"status": {"$in": ["pending_approval", "draft"]}}, {"_id": 0}
    ).sort("created_at", -1).limit(200).to_list(200)
    return rows


# ─── Dashboard ────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def accounts_dashboard(user: dict = Depends(require_permission("accounting", "read"))):
    """Real-time financial control-centre snapshot. 20 metric cards.

    Pulls live data from CoA + journal_entries (preferring `lines` aggregation).
    Falls back to legacy `amount` fields where lines absent.
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    # Trial-balance style balance per code (whole period for opening-snapshot accounts)
    tb_all = await trial_balance()
    tb_by_code = {r["code"]: r for r in tb_all}

    def balance_for(code: str, signed: bool = False) -> float:
        r = tb_by_code.get(code)
        if not r:
            return 0.0
        if signed:
            return float(r.get("debit_total", 0)) - float(r.get("credit_total", 0))
        return abs(float(r.get("balance") or 0))

    # Month-to-date P&L for the income/expense cards
    pl_mtd = await profit_and_loss(start=month_start, end=today)

    # AR / AP outstanding from existing aging logic
    ar_buckets = await ar_aging()
    ap_buckets = await ap_aging()

    # Pending / unposted voucher counts
    pending_vouchers = await db.journal_entries.count_documents({"status": "pending_approval"})
    draft_vouchers   = await db.journal_entries.count_documents({"status": "draft"})
    posted_no_att    = await db.journal_entries.count_documents({
        "status": "posted",
        "$or": [{"attachments": {"$exists": False}}, {"attachments": []}],
        "voucher_type": {"$in": ["PV", "RV", "PUV", "EV"]},  # vouchers that should have proof
    })

    recent_tx = await db.journal_entries.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)

    retention_recv = balance_for("1210")
    if not retention_recv:
        agg = await db.client_invoices.aggregate([
            {"$match": {"status": {"$nin": ["draft", "cancelled", "rejected"]}}},
            {"$project": {"pending": {"$subtract": [
                {"$ifNull": ["$totals.retention_amount", 0]},
                {"$ifNull": ["$retention_received", 0]}]}}},
            {"$group": {"_id": None, "total": {"$sum": "$pending"}}},
        ]).to_list(1)
        retention_recv = round(float(agg[0]["total"]), 2) if agg else 0.0

    # Revenue fallback: when no revenue journal entries exist for the month,
    # derive MTD income from client invoices raised this month.
    monthly_income = pl_mtd.get("total_revenue", 0)
    if not monthly_income:
        agg = await db.client_invoices.aggregate([
            {"$match": {"status": {"$nin": ["draft", "cancelled", "rejected"]},
                        "invoice_date": {"$gte": month_start, "$lte": today}}},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$amount", 0]}}}},
        ]).to_list(1)
        monthly_income = round(float(agg[0]["total"]), 2) if agg else 0.0

    # Expense fallback: vendor bills booked this month when no expense JEs exist.
    monthly_expenses = pl_mtd.get("total_expense", 0)
    if not monthly_expenses:
        agg = await db.vendor_bills.aggregate([
            {"$match": {"status": {"$nin": ["draft", "cancelled", "rejected"]},
                        "invoice_date": {"$gte": month_start, "$lte": today}}},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$amount", 0]}}}},
        ]).to_list(1)
        monthly_expenses = round(float(agg[0]["total"]), 2) if agg else 0.0

    return {
        "as_of": now_iso(),
        "cards": {
            # Receivables / Payables
            "total_receivables":   ar_buckets.get("total_outstanding", 0),
            "total_payables":      ap_buckets.get("total_outstanding", 0),
            "retention_receivable": retention_recv,
            "retention_payable":    balance_for("2110"),
            "vendor_payable":      balance_for("2100"),
            "client_advances":     balance_for("2500"),
            # Cash & bank
            "bank_balance":  balance_for("1100", signed=True) + balance_for("1101", signed=True),
            "cash_balance":  balance_for("1110", signed=True),
            "petty_cash":    balance_for("1115", signed=True),
            # Statutory
            "gst_payable":    balance_for("2300"),
            "tds_payable":    balance_for("2400"),
            "salary_payable": balance_for("2200"),
            "labour_payable": balance_for("2210"),
            # Advances
            "employee_advances": balance_for("1500", signed=True),
            "vendor_advances":   balance_for("1510", signed=True),
            # Month-to-date P&L
            "monthly_income":   monthly_income,
            "monthly_expenses": monthly_expenses,
            "net_cash_flow":    round(monthly_income - monthly_expenses, 2),
            # Operational counters
            "pending_vouchers": pending_vouchers + draft_vouchers,
            "missing_attachment_alerts": posted_no_att,
            "unposted_vouchers": draft_vouchers,
        },
        "recent_transactions": recent_tx,
    }

