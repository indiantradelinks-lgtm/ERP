"""Unified 'My Pending Approvals' inbox.

Aggregates every item awaiting the CURRENT user's action across:
central approvals, project requests, daily expenses (+ payments due),
scaffolding transfers, DPRs and RA bills.
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from core import db, get_current_user

router = APIRouter(tags=["my-inbox"])

SCAF_APPROVE = {"super_admin", "store_manager", "inventory_manager", "dept_head",
                "general_manager", "director"}
PAY_ROLES = {"super_admin", "director", "accounts_executive", "billing_executive"}
DPR_ROLES = {"super_admin", "director", "general_manager", "dept_head", "project_manager"}
RA_ROLES = {"super_admin", "director", "general_manager", "dept_head",
            "accounts_executive", "billing_executive"}


def _my_chain_step(row: dict, role: str) -> Optional[dict]:
    chain = row.get("chain") or []
    idx = row.get("current_step") or 0
    step = chain[idx] if 0 <= idx < len(chain) else None
    if not step:
        return None
    aliases = {"manager_log": {"manager_log", "manager_l_o_g"},
               "manager_op": {"manager_op", "manager_o_p"},
               "manager_pnv": {"manager_pnv", "manager_p_n_v"}}
    allowed = set(aliases.get(step.get("role"), {step.get("role")}))
    # `exclusive` steps (e.g. Fuel Payment → Manager Log) exclude Super Admin
    if not step.get("exclusive"):
        allowed.add("super_admin")
    return step if role in allowed else None


def _item(source: str, source_label: str, row: dict, *, ref: str, title: str,
          subtitle: str = "", amount: Optional[float] = None, step_label: str = "",
          link: str = "", approve_path: Optional[str] = None,
          reject_path: Optional[str] = None,
          payment_mode: Optional[str] = None) -> Dict[str, Any]:
    return {
        "source": source, "source_label": source_label, "id": row.get("id"),
        "ref": ref, "title": title, "subtitle": subtitle, "amount": amount,
        "step_label": step_label, "created_at": row.get("created_at") or row.get("updated_at"),
        "created_by": row.get("created_by") or row.get("requested_by"),
        "link": link, "approve_path": approve_path, "reject_path": reject_path,
        "payment_mode": payment_mode,
    }


async def _central_approvals(role: str) -> List[dict]:
    rows = await db.approvals.find(
        {"status": {"$in": ["pending", "in_progress"]}},
        {"_id": 0, "history": 0}).sort("created_at", -1).limit(300).to_list(300)
    out = []
    for r in rows:
        step = _my_chain_step(r, role)
        if not step:
            continue
        out.append(_item("approval", "Approval", r,
                         ref=r.get("number") or (r.get("type") or "").replace("_", " ").title(),
                         title=r.get("title") or r.get("type") or "Approval",
                         subtitle=(r.get("type") or "").replace("_", " "),
                         amount=r.get("amount"), step_label=step.get("label") or step.get("role"),
                         payment_mode=r.get("payment_mode"),
                         link=f"/app/approvals?id={r['id']}"))
    return out


async def _project_requests(role: str, user: dict) -> List[dict]:
    from request_visibility import apply_request_visibility
    q = await apply_request_visibility(user, {"status": "pending_approval"})
    rows = await db.project_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    out = []
    for r in rows:
        step = _my_chain_step(r, role)
        if not step:
            continue
        out.append(_item("project_request", "Project Request", r,
                         ref=r.get("request_no"),
                         title=f"{r.get('request_type_label')} — {r.get('project_code')}",
                         subtitle=r.get("project_name") or "",
                         amount=r.get("est_value"), step_label=step.get("label"),
                         payment_mode=((r.get("payment_mode") or "Accounts") if r.get("is_payment") else None),
                         link="/app/ops/requests",
                         approve_path=f"/project-requests/{r['id']}/approve",
                         reject_path=f"/project-requests/{r['id']}/reject"))
    return out


async def _daily_expenses(role: str) -> List[dict]:
    rows = await db.project_expenses.find(
        {"status": "pending_approval"}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    out = []
    for r in rows:
        step = _my_chain_step(r, role)
        if not step:
            continue
        out.append(_item("expense", "Daily Expense", r,
                         ref=r.get("expense_no"),
                         title=f"{r.get('expense_type_label')} — {r.get('project_code')}",
                         subtitle=r.get("paid_to") or r.get("description") or "",
                         amount=r.get("amount"), step_label=step.get("label"),
                         link="/app/ops/expenses",
                         approve_path=f"/project-expenses/{r['id']}/approve",
                         reject_path=f"/project-expenses/{r['id']}/reject"))
    return out


async def _expense_payments(role: str) -> List[dict]:
    if role not in PAY_ROLES:
        return []
    rows = await db.project_expenses.find(
        {"status": "approved_for_payment"}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return [_item("expense_payment", "Payment Due", r,
                  ref=r.get("expense_no"),
                  title=f"{r.get('expense_type_label')} — {r.get('project_code')}",
                  subtitle=f"Pay to: {r.get('paid_to') or '—'}",
                  amount=r.get("amount"), step_label="Mark Paid (Accounts)",
                  link="/app/ops/expenses") for r in rows]


async def _scaffolding(role: str) -> List[dict]:
    if role not in SCAF_APPROVE:
        return []
    rows = await db.scaf_transfers.find(
        {"status": "pending_approval"}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return [_item("scaffolding", "Scaffolding Transfer", r,
                  ref=r.get("transfer_no"),
                  title=f"{r.get('from_location')} → {r.get('to_location')}",
                  subtitle="; ".join(f"{l['item_name']} ×{l['quantity']}" for l in (r.get("lines") or [])[:3]),
                  step_label="Dispatch Approval",
                  link="/app/scaffolding",
                  approve_path=f"/scaffolding/transfers/{r['id']}/approve",
                  reject_path=f"/scaffolding/transfers/{r['id']}/reject") for r in rows]


async def _dprs(role: str) -> List[dict]:
    if role not in DPR_ROLES:
        return []
    rows = await db.dprs.find(
        {"status": "submitted"}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return [_item("dpr", "Daily Site Report", r,
                  ref=r.get("dpr_number"),
                  title=f"DPR — {r.get('project_code') or r.get('project_id') or ''} · {r.get('date') or ''}",
                  subtitle=(r.get("work_completed") or "")[:80],
                  step_label="DPR Approval",
                  link="/app/dprs") for r in rows]


async def _ra_bills(role: str) -> List[dict]:
    if role not in RA_ROLES:
        return []
    rows = await db.ra_bills.find(
        {"status": "submitted"}, {"_id": 0, "items": 0}).sort("created_at", -1).limit(200).to_list(200)
    return [_item("ra_bill", "RA Bill", r,
                  ref=r.get("bill_number"),
                  title=f"{(r.get('bill_type') or 'running').replace('_', ' ').title()} Bill — {r.get('project_code') or ''}",
                  subtitle=r.get("client_name") or "",
                  amount=r.get("net_payable") or r.get("gross_value"),
                  step_label="Bill Approval",
                  link="/app/ra-bills") for r in rows]


async def _service_requests(role: str, user_id: str) -> List[dict]:
    """Service Requests awaiting the current user's step per the Approval Matrix."""
    rows = await db.svc_requests.find(
        {"status": {"$in": ["submitted", "under_review"]}},
        {"_id": 0, "history": 0}).sort("created_at", -1).limit(200).to_list(200)
    if not rows:
        return []
    from approval_engine import get_chain_template
    default_chain = await get_chain_template("service_request")
    out = []
    for r in rows:
        chain = r.get("approval_chain") or default_chain
        idx = int(r.get("approval_step") or 0)
        step = chain[idx] if 0 <= idx < len(chain) else None
        if not step or not (role == "super_admin" or step.get("role") == role):
            continue
        if r.get("requester_id") == user_id and role != "super_admin":
            continue
        out.append(_item("service_request", "Service Request", r,
                         ref=r.get("sr_no"),
                         title=f"{r.get('service_category') or 'Service'} — {(r.get('service_description') or '')[:70]}",
                         subtitle=" · ".join(x for x in [r.get("project_code"), r.get("site_location"),
                                                         f"Priority: {r.get('priority')}" if r.get("priority") else ""] if x),
                         amount=r.get("estimated_budget"),
                         step_label=step.get("label") or step.get("role"),
                         link=f"/app/services/requests/{r['id']}",
                         approve_path=f"/service-workflow/requests/{r['id']}/inbox-approve",
                         reject_path=f"/service-workflow/requests/{r['id']}/inbox-reject"))
    return out


async def _direct_payments(role: str) -> List[dict]:
    if role != "super_admin":
        return []
    rows = await db.svc_direct_payments.find(
        {"status": "pending_approval"}, {"_id": 0, "history": 0}).sort("created_at", -1).limit(200).to_list(200)
    return [_item("service_direct_payment", "Direct Payment", r,
                  ref=r.get("dp_no"),
                  title=f"{r.get('vendor_name') or 'Vendor'} — {r.get('service_period') or r.get('vendor_invoice_no') or 'repeat payment'}",
                  subtitle=" · ".join(x for x in [r.get("project_code"), f"ref PO {r['ref_po_no']}" if r.get("ref_po_no") else "",
                                                  "; ".join(r.get("warnings") or [])] if x),
                  amount=r.get("payment_amount"),
                  step_label="Super Admin Approval",
                  link=f"/app/services/direct-payments?id={r['id']}",
                  approve_path=f"/service-direct-payments/{r['id']}/inbox-approve",
                  reject_path=f"/service-direct-payments/{r['id']}/inbox-reject") for r in rows]


@router.get("/my-inbox")
async def my_inbox(user: dict = Depends(get_current_user)):
    role = user.get("role")
    results = await asyncio.gather(
        _central_approvals(role), _project_requests(role, user), _daily_expenses(role),
        _expense_payments(role), _scaffolding(role), _dprs(role), _ra_bills(role),
        _service_requests(role, user.get("id")), _direct_payments(role))
    items: List[dict] = [it for group in results for it in group]
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    counts: Dict[str, int] = {}
    for it in items:
        counts[it["source"]] = counts.get(it["source"], 0) + 1
    return {"total": len(items), "counts": counts, "items": items[:300]}
