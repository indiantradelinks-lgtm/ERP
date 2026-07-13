"""Finance write-time guards (Phase 9 — Role-Based Access & Security).

Centralised helpers that other finance routers can call to enforce:
  • No voucher edit after approval (must reopen first)
  • No ledger deletion if transactions reference it
  • No payment without approval
  • Backdated entry — already enforced via accounting_service._assert_period_open

Each helper raises HTTPException so callers don't need to translate.
"""
from __future__ import annotations
from typing import Optional
from fastapi import HTTPException

from core import db

# Statuses that mean the document is "frozen" — no edits without reopen.
FROZEN_STATUSES = {"approved", "posted", "paid", "closed", "locked"}

# Statuses an originator can edit
EDITABLE_STATUSES = {"draft", "pending_approval", "rejected_revision_required",
                     "additional_info_required", "reopened"}


async def assert_voucher_editable(collection: str, record_id: str, *, allow_reopen_roles: set | None = None,
                                    user: dict | None = None) -> dict:
    """Fetch the voucher and ensure it isn't frozen.

    Raises 404 if not found, 409 if frozen. Returns the doc on success.
    """
    doc = await db[collection].find_one({"id": record_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, f"{collection.rstrip('s')} not found")
    status = (doc.get("status") or "").lower()
    if status in FROZEN_STATUSES:
        role = (user or {}).get("role", "")
        if allow_reopen_roles and role in allow_reopen_roles:
            return doc  # privileged user may edit
        raise HTTPException(
            409,
            f"This {collection.rstrip('s')} is {status}; reopen it (with reason) before editing.",
        )
    return doc


async def assert_ledger_deletable(account_id: str) -> None:
    """Block CoA deletion when transactions reference the account."""
    coa = await db.chart_of_accounts.find_one({"id": account_id}, {"_id": 0, "code": 1})
    if not coa:
        raise HTTPException(404, "Ledger account not found")
    code = coa.get("code")
    # Journal line referencing this code or id
    has_je = await db.journal_entries.find_one({
        "$or": [
            {"lines.account_code": code},
            {"lines.account_id": account_id},
        ]
    }, {"_id": 0, "id": 1})
    if has_je:
        raise HTTPException(
            409,
            f"Cannot delete ledger '{code}' — transactions reference it. "
            f"Deactivate it instead (set active=False).",
        )


async def assert_payment_approvable(payment_id: str) -> dict:
    """Ensure a payment record has a corresponding approved approval row."""
    pay = await db.payments.find_one({"id": payment_id}, {"_id": 0})
    if not pay:
        raise HTTPException(404, "Payment not found")
    appr = await db.approvals.find_one({
        "source_id": payment_id, "type": "expense", "status": "approved"
    }, {"_id": 0, "id": 1})
    if not appr and (pay.get("status") or "").lower() != "approved":
        raise HTTPException(409, "Payment requires approved request before release.")
    return pay


async def assert_invoice_has_client(invoice: dict) -> None:
    """An invoice without a client cannot be posted to ledger."""
    if not invoice.get("client_id") and not invoice.get("client_name"):
        raise HTTPException(400, "Invoice must be linked to a client before posting.")


async def assert_bill_has_vendor(bill: dict) -> None:
    if not bill.get("vendor_id") and not bill.get("vendor_name"):
        raise HTTPException(400, "Vendor bill must be linked to a vendor before posting.")


async def assert_voucher_balanced(lines: list) -> None:
    total_dr = round(sum(float(ln.get("debit") or 0) for ln in lines), 2)
    total_cr = round(sum(float(ln.get("credit") or 0) for ln in lines), 2)
    if abs(total_dr - total_cr) > 0.01:
        raise HTTPException(400, f"Voucher unbalanced: DR={total_dr} CR={total_cr}")
    if total_dr == 0:
        raise HTTPException(400, "Voucher has zero amount")
