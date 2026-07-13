"""Finance Phase 2 — Core finance backbone extensions (Iter 110).

Builds on the existing Finance/Accounts module (~6,300 LoC) by filling
3 concrete gaps from the user's Phase 2 spec:

  1. **CoA policy fields**  — extends chart_of_accounts with
       gst_applicable / gst_rate / tds_applicable / tds_section / tds_rate /
       cost_center_required / party_type / pan
     Allows downstream automation (e.g. auto-derive GST/TDS from CoA
     selection on a JE) without hand-coding rules into each helper.

  2. **Debit Notes + Credit Notes as first-class records** — currently the
     ERP has no dedicated DN/CN with approval workflow. The `db.debit_notes`
     collection already exists (created in iter 107 for QI auto-drafts);
     this module formalises both DN and CN with a unified approve path that
     auto-posts the reversal JE via `accounting_service.post_journal_entry`.

  3. **Voucher PDF export** — every JE / voucher can now download as a
     branded PDF (matches the look of PO / RFQ / RA Bill PDFs).

Reuses (no duplication):
  • `audit()` helper
  • `next_sequence()` for DN/CN numbering
  • `post_journal_entry()` for the auto-JE on approval
  • `require_permission("accounting", ...)` RBAC
  • `document_pdf.voucher_pdf` and `dn_cn_pdf` (added to document_pdf.py)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core import db, require_permission, new_id, now_iso
from audit import audit
from sequences import next_sequence
from accounting_service import post_journal_entry
from document_pdf import voucher_pdf, dn_cn_pdf

router = APIRouter(prefix="/finance", tags=["finance-phase2"])


# ─── Constants ───────────────────────────────────────────────────────────
DN_CN_REASON_CODES = {
    "price_difference":  "Price difference / commercial revision",
    "quality":           "Quality issue / partial acceptance",
    "quantity":          "Quantity short / excess",
    "gst_correction":    "GST rate or category correction",
    "tds_adjustment":    "TDS-related adjustment",
    "scope_change":      "Scope / measurement variation",
    "retention_release": "Retention release",
    "other":             "Other (see narration)",
}

DN_CN_STATUSES = ("draft", "pending_approval", "approved", "cancelled")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _strip(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if d:
        d.pop("_id", None)
    return d


# ═════════════════════════════════════════════════════════════════════════
# 1.  CoA Policy fields
# ═════════════════════════════════════════════════════════════════════════
class CoAPolicyPatch(BaseModel):
    gst_applicable: Optional[bool] = None
    gst_rate: Optional[float] = None             # default 0..28
    tds_applicable: Optional[bool] = None
    tds_section: Optional[str] = None            # e.g. "194C", "194I", "194J"
    tds_rate: Optional[float] = None
    cost_center_required: Optional[bool] = None
    party_type: Optional[str] = None             # client / vendor / employee / project / site / none
    pan: Optional[str] = None
    is_sub_ledger: Optional[bool] = None         # true → individual client/vendor sub-ledgers underneath


@router.patch("/coa/{coa_id}/policy")
async def set_coa_policy(coa_id: str, payload: CoAPolicyPatch, request: Request,
                         user: dict = Depends(require_permission("accounting", "write"))):
    """Set/extend policy flags on a Chart-of-Accounts row."""
    existing = await db.chart_of_accounts.find_one({"id": coa_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "CoA not found")
    if payload.party_type and payload.party_type not in ("client", "vendor", "employee", "project", "site", "none"):
        raise HTTPException(400, "Invalid party_type")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields to update")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = user.get("name") or user.get("email")
    await db.chart_of_accounts.update_one({"id": coa_id}, {"$set": patch})
    await audit(user=user, action="patch_policy", resource="chart_of_accounts",
                record_id=coa_id, before={k: existing.get(k) for k in patch},
                after=patch, ip=request.client.host if request.client else "")
    return {"ok": True, "coa_id": coa_id, "updated": patch}


@router.post("/coa/migrate-policy-defaults")
async def migrate_coa_policy_defaults(user: dict = Depends(require_permission("accounting", "write"))):
    """One-shot helper: stamp sensible default policy flags on every CoA row
    based on subtype, so existing 30 seed accounts get policy data without
    manual editing.  Idempotent — only touches rows missing the flag."""
    defaults_by_subtype = {
        "bank":        {"party_type": "none", "gst_applicable": False, "tds_applicable": False, "cost_center_required": False},
        "cash":        {"party_type": "none", "gst_applicable": False, "tds_applicable": False, "cost_center_required": False},
        "ar":          {"party_type": "client", "is_sub_ledger": True, "gst_applicable": True, "gst_rate": 18.0, "tds_applicable": False, "cost_center_required": False},
        "ap":          {"party_type": "vendor", "is_sub_ledger": True, "gst_applicable": True, "gst_rate": 18.0, "tds_applicable": True, "tds_section": "194C", "tds_rate": 2.0, "cost_center_required": False},
        "tax":         {"party_type": "none", "gst_applicable": False, "tds_applicable": False, "cost_center_required": False},
        "advance":     {"party_type": "employee", "is_sub_ledger": True, "cost_center_required": False, "tds_applicable": False},
        "payroll":     {"party_type": "employee", "is_sub_ledger": True, "tds_applicable": False, "cost_center_required": False},
        "statutory":   {"party_type": "none", "gst_applicable": False, "tds_applicable": False, "cost_center_required": False},
        "direct":      {"party_type": "project", "gst_applicable": True, "gst_rate": 18.0, "tds_applicable": True, "tds_section": "194C", "tds_rate": 2.0, "cost_center_required": True},
        "indirect":    {"party_type": "none", "gst_applicable": True, "gst_rate": 18.0, "tds_applicable": False, "cost_center_required": True},
        "operating":   {"party_type": "client", "gst_applicable": True, "gst_rate": 18.0, "tds_applicable": False, "cost_center_required": True},
        "service":     {"party_type": "client", "gst_applicable": True, "gst_rate": 18.0, "tds_applicable": False, "cost_center_required": True},
        "trading":     {"party_type": "client", "gst_applicable": True, "gst_rate": 18.0, "tds_applicable": False, "cost_center_required": True},
        "fixed_asset": {"party_type": "none", "gst_applicable": True, "gst_rate": 18.0, "cost_center_required": False},
        "wip":         {"party_type": "project", "cost_center_required": True},
        "grni":        {"party_type": "vendor", "cost_center_required": False},
        "inventory":   {"party_type": "none", "cost_center_required": True},
    }
    updated = 0
    async for row in db.chart_of_accounts.find({}, {"_id": 0}):
        st = row.get("subtype")
        d = defaults_by_subtype.get(st, {})
        if not d:
            continue
        patch = {k: v for k, v in d.items() if k not in row}
        if patch:
            patch["updated_at"] = now_iso()
            patch["updated_by"] = "policy-migration"
            await db.chart_of_accounts.update_one({"id": row["id"]}, {"$set": patch})
            updated += 1
    return {"updated": updated}


# ═════════════════════════════════════════════════════════════════════════
# 2.  Debit Notes + Credit Notes
# ═════════════════════════════════════════════════════════════════════════
class DebitCreditNoteIn(BaseModel):
    kind: str = Field(..., pattern="^(debit_note|credit_note)$")
    against_type: str = Field(..., pattern="^(invoice|vendor_bill|po|other)$")
    against_id: Optional[str] = None
    against_number: Optional[str] = None
    party_id: str
    party_name: Optional[str] = None
    party_type: str = Field(..., pattern="^(client|vendor)$")
    date: str = Field(default_factory=_today)
    project_id: Optional[str] = None
    project_code: Optional[str] = None
    reason_code: str = Field(..., pattern="^(price_difference|quality|quantity|gst_correction|tds_adjustment|scope_change|retention_release|other)$")
    reason: str = Field(..., min_length=3, max_length=500)
    taxable_value: float = Field(..., gt=0)
    gst_percent: float = 18.0
    tds_percent: float = 0.0
    attachments: List[Dict[str, Any]] = []


def _compute_amounts(payload: DebitCreditNoteIn) -> Dict[str, float]:
    base = round(payload.taxable_value, 2)
    gst = round(base * payload.gst_percent / 100.0, 2)
    tds = round(base * payload.tds_percent / 100.0, 2) if payload.tds_percent else 0.0
    return {"taxable_value": base, "gst_amount": gst, "tds_amount": tds,
            "total_amount": round(base + gst - tds, 2)}


@router.get("/notes")
async def list_notes(kind: Optional[str] = None, party_id: Optional[str] = None,
                     status: Optional[str] = None,
                     user: dict = Depends(require_permission("accounting", "read"))):
    q: Dict[str, Any] = {}
    if kind:
        q["kind"] = kind
    if party_id:
        q["party_id"] = party_id
    if status:
        q["status"] = status
    rows = await db.finance_notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.get("/notes/reason-codes")
async def list_reason_codes(_: dict = Depends(require_permission("accounting", "read"))):
    return [{"code": k, "label": v} for k, v in DN_CN_REASON_CODES.items()]


@router.get("/notes/{note_id}")
async def get_note(note_id: str, user: dict = Depends(require_permission("accounting", "read"))):
    row = await db.finance_notes.find_one({"id": note_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Note not found")
    return row


@router.get("/notes/{note_id}/pdf")
async def note_pdf(note_id: str, user: dict = Depends(require_permission("accounting", "read"))):
    n = await db.finance_notes.find_one({"id": note_id}, {"_id": 0})
    if not n:
        raise HTTPException(404, "Note not found")
    party_collection = db.clients if n["party_type"] == "client" else db.vendors
    party = await party_collection.find_one({"id": n["party_id"]}, {"_id": 0}) or {}
    pdf = dn_cn_pdf(n, party)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{n.get("note_number") or note_id}.pdf"'})


@router.post("/notes")
async def create_note(payload: DebitCreditNoteIn, request: Request,
                      user: dict = Depends(require_permission("accounting", "write"))):
    # Validate party
    party_collection = db.clients if payload.party_type == "client" else db.vendors
    party = await party_collection.find_one({"id": payload.party_id}, {"_id": 0})
    if not party:
        raise HTTPException(404, f"{payload.party_type.title()} not found")
    if (party.get("status") in ("blocked", "blacklisted")):
        raise HTTPException(400, f"{payload.party_type.title()} is blocked")

    # Validate "against" record exists (if specified)
    if payload.against_id and payload.against_type in ("invoice", "vendor_bill"):
        coll = db.client_invoices if payload.against_type == "invoice" else db.vendor_bills
        ref = await coll.find_one({"id": payload.against_id}, {"_id": 0, "id": 1, "number": 1, "invoice_number": 1, "bill_number": 1})
        if not ref:
            raise HTTPException(404, f"{payload.against_type} not found")

    amounts = _compute_amounts(payload)
    prefix = "DN" if payload.kind == "debit_note" else "CN"
    doc: Dict[str, Any] = {
        "id": new_id(),
        "note_number": await next_sequence(prefix),
        **payload.model_dump(),
        **amounts,
        "party_name": payload.party_name or party.get("name"),
        "status": "draft",
        "approved_by": None,
        "approved_at": None,
        "auto_je_id": None,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.finance_notes.insert_one(doc)
    await audit(user=user, action="create", resource="finance_notes",
                record_id=doc["id"], after=doc,
                ip=request.client.host if request.client else "")
    return _strip(doc)


@router.post("/notes/{note_id}/submit")
async def submit_note(note_id: str, request: Request,
                      user: dict = Depends(require_permission("accounting", "write"))):
    n = await db.finance_notes.find_one({"id": note_id}, {"_id": 0})
    if not n:
        raise HTTPException(404, "Note not found")
    if n.get("status") != "draft":
        raise HTTPException(400, f"Cannot submit — status is {n.get('status')}")
    await db.finance_notes.update_one(
        {"id": note_id},
        {"$set": {"status": "pending_approval", "submitted_at": now_iso(),
                  "submitted_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="submit", resource="finance_notes",
                record_id=note_id, before={"status": "draft"},
                after={"status": "pending_approval"},
                ip=request.client.host if request.client else "")
    return {"ok": True, "note_id": note_id, "status": "pending_approval"}


@router.post("/notes/{note_id}/approve")
async def approve_note(note_id: str, request: Request,
                       user: dict = Depends(require_permission("accounting", "write"))):
    """Approve + auto-post the reversal JE.
       • Credit Note (against client invoice): reduces AR & Revenue.
       • Debit Note (against vendor bill): reduces AP & Expense.
    """
    if user.get("role") not in ("super_admin", "director", "general_manager", "accounts_manager"):
        raise HTTPException(403, "Insufficient role to approve")
    n = await db.finance_notes.find_one({"id": note_id}, {"_id": 0})
    if not n:
        raise HTTPException(404, "Note not found")
    if n.get("status") not in ("draft", "pending_approval"):
        raise HTTPException(400, f"Cannot approve — status is {n.get('status')}")

    # Build double-entry lines
    kind = n["kind"]
    base = float(n["taxable_value"])
    gst = float(n["gst_amount"])
    total = float(n["total_amount"])

    if kind == "credit_note":
        # Client refund/discount → reverses revenue + AR.
        # DR Revenue (4100), DR GST Output (2300), CR Accounts Receivable (1200)
        lines = [
            {"account_code": "4100", "debit": base,  "credit": 0,    "project_id": n.get("project_id")},
            {"account_code": "2300", "debit": gst,   "credit": 0},
            {"account_code": "1200", "debit": 0,     "credit": total},
        ]
        voucher_type = "CN"
        party_type_je = "client"
    else:
        # Debit Note to vendor → reduces expense + AP.
        # DR Accounts Payable (2100), CR Expense (5100 default), CR GST Input (1700)
        lines = [
            {"account_code": "2100", "debit": total, "credit": 0},
            {"account_code": "5100", "debit": 0,     "credit": base, "project_id": n.get("project_id")},
            {"account_code": "1700", "debit": 0,     "credit": gst},
        ]
        voucher_type = "DN"
        party_type_je = "vendor"

    je = await post_journal_entry(
        source_module="finance_notes",
        source_id=n["id"],
        source_event="approved",
        source_ref=n.get("note_number"),
        date=n.get("date") or _today(),
        narration=f"{voucher_type} {n.get('note_number')} — {n.get('reason')}",
        lines=lines,
        voucher_type=voucher_type,
        voucher_number=n.get("note_number"),
        project_id=n.get("project_id"),
        posted_by=user.get("name") or user.get("email"),
        status="posted",
        party_type=party_type_je, party_id=n.get("party_id"), party_name=n.get("party_name"),
    )

    await db.finance_notes.update_one(
        {"id": note_id},
        {"$set": {"status": "approved",
                  "approved_at": now_iso(),
                  "approved_by": user.get("name") or user.get("email"),
                  "auto_je_id": (je or {}).get("id"),
                  "auto_je_number": (je or {}).get("je_number")}},
    )
    await audit(user=user, action="approve", resource="finance_notes",
                record_id=note_id, before={"status": n["status"]},
                after={"status": "approved", "je": (je or {}).get("je_number")},
                ip=request.client.host if request.client else "")
    return {"ok": True, "note_id": note_id, "status": "approved",
            "je_id": (je or {}).get("id"), "je_number": (je or {}).get("je_number")}


@router.post("/notes/{note_id}/cancel")
async def cancel_note(note_id: str, reason: str, request: Request,
                      user: dict = Depends(require_permission("accounting", "write"))):
    n = await db.finance_notes.find_one({"id": note_id}, {"_id": 0})
    if not n:
        raise HTTPException(404, "Note not found")
    if n.get("status") == "cancelled":
        return {"ok": True, "note_id": note_id, "status": "cancelled"}
    if n.get("status") == "approved":
        raise HTTPException(400, "Cannot cancel an approved note — post a reversing note instead")
    if not reason or len(reason) < 3:
        raise HTTPException(400, "Cancellation reason required (min 3 chars)")
    await db.finance_notes.update_one(
        {"id": note_id},
        {"$set": {"status": "cancelled", "cancel_reason": reason,
                  "cancelled_at": now_iso(),
                  "cancelled_by": user.get("name") or user.get("email")}},
    )
    await audit(user=user, action="cancel", resource="finance_notes",
                record_id=note_id, before={"status": n.get("status")},
                after={"status": "cancelled", "reason": reason},
                ip=request.client.host if request.client else "")
    return {"ok": True, "note_id": note_id, "status": "cancelled"}


@router.get("/notes/{note_id}/pdf")


# ═════════════════════════════════════════════════════════════════════════
# 3.  Voucher / JE PDF export
# ═════════════════════════════════════════════════════════════════════════
@router.get("/vouchers/{voucher_id}/pdf")
async def voucher_pdf_export(voucher_id: str,
                             user: dict = Depends(require_permission("accounting", "read"))):
    """Branded PDF for any JE / voucher."""
    v = await db.journal_entries.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher / JE not found")
    pdf = voucher_pdf(v)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{v.get("je_number") or voucher_id}.pdf"'})
