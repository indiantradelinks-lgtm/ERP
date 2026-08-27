"""
Accounts Module · Central Financial Control Engine (Iter 71)
============================================================

Single source of truth for:
  • Chart of Accounts master (db.chart_of_accounts)
  • Double-entry Journal Entries (db.journal_entries — extended)
  • Auto-posting from 5 high-leverage events
  • Trial Balance / P&L / AR / AP aging reports

Design choices:
  • LIVES ALONGSIDE legacy single-amount JEs — every new JE writes BOTH the legacy
    `amount + type + account` fields AND the new `lines[]` double-entry structure
    so existing dashboards, exports, project P&L keep working unchanged.
  • All auto-posting calls are SAFE NO-OPS if the Chart of Accounts isn't seeded
    or if the source record is missing a project / cost centre. We never block
    the originating user action because of an accounting failure — we log and
    move on (the Accounts team can manually reconcile via the Accounts page).
  • Idempotency: every JE carries (source_module, source_id, source_event). Each
  posting helper de-dupes on these three keys to allow safe re-runs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core import db, new_id, now_iso
from sequences import next_sequence

logger = logging.getLogger("erp.accounting")


# ─── Seed Chart of Accounts ──────────────────────────────────────────────
# 30 accounts covering the 8 modules. Standard small-business GST-ready
# Indian taxonomy: A=Asset, L=Liability, E=Equity, R=Revenue, X=Expense.
DEFAULT_COA: List[Dict[str, Any]] = [
    # === Assets ===
    {"code": "1100", "name": "Bank — Operating Account",       "type": "asset",   "subtype": "bank"},
    {"code": "1101", "name": "Bank — Current Account 2",       "type": "asset",   "subtype": "bank"},
    {"code": "1110", "name": "Cash on Hand",                   "type": "asset",   "subtype": "cash"},
    {"code": "1115", "name": "Petty Cash",                     "type": "asset",   "subtype": "cash"},
    {"code": "1200", "name": "Accounts Receivable",            "type": "asset",   "subtype": "ar",        "control": True},
    {"code": "1210", "name": "Retention Receivable",           "type": "asset",   "subtype": "ar",        "control": True},
    {"code": "1220", "name": "TDS Receivable",                 "type": "asset",   "subtype": "tax"},
    {"code": "1300", "name": "Inventory — Stores",             "type": "asset",   "subtype": "inventory", "control": True},
    {"code": "1310", "name": "Inventory — Consumables",        "type": "asset",   "subtype": "inventory"},
    {"code": "1400", "name": "Goods Received Not Invoiced",    "type": "asset",   "subtype": "grni",      "control": True},
    {"code": "1500", "name": "Employee Advances",              "type": "asset",   "subtype": "advance",   "control": True},
    {"code": "1510", "name": "Vendor Advances",                "type": "asset",   "subtype": "advance",   "control": True},
    {"code": "1520", "name": "Security Deposits",              "type": "asset",   "subtype": "deposit"},
    {"code": "1600", "name": "Fixed Assets — Plant & Machinery","type": "asset",  "subtype": "fixed_asset"},
    {"code": "1610", "name": "Fixed Assets — Vehicles",        "type": "asset",   "subtype": "fixed_asset"},
    {"code": "1620", "name": "Fixed Assets — Office Equipment","type": "asset",   "subtype": "fixed_asset"},
    {"code": "1700", "name": "GST Input Credit",               "type": "asset",   "subtype": "tax"},
    {"code": "1800", "name": "Work in Progress",               "type": "asset",   "subtype": "wip",       "control": True},
    # === Liabilities ===
    {"code": "2100", "name": "Accounts Payable",               "type": "liability","subtype": "ap",        "control": True},
    {"code": "2110", "name": "Retention Payable",              "type": "liability","subtype": "ap"},
    {"code": "2200", "name": "Salary Payable",                 "type": "liability","subtype": "payroll"},
    {"code": "2210", "name": "Labour Payable",                 "type": "liability","subtype": "payroll"},
    {"code": "2220", "name": "PF Payable",                     "type": "liability","subtype": "statutory"},
    {"code": "2230", "name": "ESIC Payable",                   "type": "liability","subtype": "statutory"},
    {"code": "2300", "name": "GST Output Payable",             "type": "liability","subtype": "tax"},
    {"code": "2400", "name": "TDS Payable",                    "type": "liability","subtype": "tax"},
    {"code": "2410", "name": "Duties & Taxes Payable",         "type": "liability","subtype": "tax"},
    {"code": "2500", "name": "Customer Advances Received",     "type": "liability","subtype": "advance"},
    {"code": "2600", "name": "Loans — Secured",                "type": "liability","subtype": "loan"},
    {"code": "2610", "name": "Loans — Unsecured",              "type": "liability","subtype": "loan"},
    # === Equity / Capital ===
    {"code": "3100", "name": "Owner's Capital",                "type": "equity",  "subtype": "capital"},
    {"code": "3110", "name": "Drawings",                       "type": "equity",  "subtype": "drawings"},
    {"code": "3200", "name": "Retained Earnings",              "type": "equity",  "subtype": "reserves"},
    # === Revenue (ITL Service-Lines) ===
    {"code": "4100", "name": "Revenue — Services",             "type": "revenue", "subtype": "operating"},
    {"code": "4101", "name": "Income — Scaffolding Service",   "type": "revenue", "subtype": "service"},
    {"code": "4102", "name": "Income — Painting Service",      "type": "revenue", "subtype": "service"},
    {"code": "4103", "name": "Income — Roof Sheeting",         "type": "revenue", "subtype": "service"},
    {"code": "4104", "name": "Income — Rope Access",           "type": "revenue", "subtype": "service"},
    {"code": "4105", "name": "Income — Manpower Supply",       "type": "revenue", "subtype": "service"},
    {"code": "4106", "name": "Income — Material Supply",       "type": "revenue", "subtype": "trading"},
    {"code": "4110", "name": "Revenue — Sales of Goods",       "type": "revenue", "subtype": "trading"},
    {"code": "4800", "name": "Scrap Sale Income",              "type": "revenue", "subtype": "other"},
    {"code": "4900", "name": "Other Income",                   "type": "revenue", "subtype": "other"},
    # === Expenses ===
    {"code": "5100", "name": "Project Cost — Materials",       "type": "expense", "subtype": "direct"},
    {"code": "5105", "name": "Material Purchase",              "type": "expense", "subtype": "direct"},
    {"code": "5110", "name": "Project Cost — Labour / Manpower","type": "expense","subtype": "direct"},
    {"code": "5111", "name": "Labour Cost",                    "type": "expense", "subtype": "direct"},
    {"code": "5120", "name": "Project Cost — Subcontracting",  "type": "expense", "subtype": "direct"},
    {"code": "5121", "name": "Subcontractor Charges",          "type": "expense", "subtype": "direct"},
    {"code": "5130", "name": "Project Cost — Equipment / Hire","type": "expense", "subtype": "direct"},
    {"code": "5135", "name": "Tools & Tackles",                "type": "expense", "subtype": "direct"},
    {"code": "5140", "name": "Project Cost — Logistics",       "type": "expense", "subtype": "direct"},
    {"code": "5141", "name": "Fuel / Diesel",                  "type": "expense", "subtype": "direct"},
    {"code": "5142", "name": "Vehicle Maintenance",            "type": "expense", "subtype": "indirect"},
    {"code": "5143", "name": "Loading / Unloading",            "type": "expense", "subtype": "direct"},
    {"code": "5150", "name": "Site Expense",                   "type": "expense", "subtype": "direct"},
    {"code": "5151", "name": "Accommodation",                  "type": "expense", "subtype": "direct"},
    {"code": "5200", "name": "Salaries & Wages",               "type": "expense", "subtype": "payroll"},
    {"code": "5300", "name": "Safety & PPE Expense",           "type": "expense", "subtype": "indirect"},
    {"code": "5400", "name": "Office & Admin Expense",         "type": "expense", "subtype": "indirect"},
    {"code": "5410", "name": "Rent",                           "type": "expense", "subtype": "indirect"},
    {"code": "5420", "name": "Professional Charges",           "type": "expense", "subtype": "indirect"},
    {"code": "5430", "name": "Bank Charges",                   "type": "expense", "subtype": "indirect"},
    {"code": "5440", "name": "Repair & Maintenance",           "type": "expense", "subtype": "indirect"},
    {"code": "5500", "name": "Depreciation",                   "type": "expense", "subtype": "non_cash"},
    {"code": "5900", "name": "Miscellaneous Expense",          "type": "expense", "subtype": "indirect"},
]


async def ensure_coa_seeded() -> int:
    """Idempotently seed DEFAULT_COA. Returns number of new rows inserted."""
    existing = {c["code"] async for c in db.chart_of_accounts.find({}, {"_id": 0, "code": 1})}
    inserted = 0
    now = now_iso()
    for a in DEFAULT_COA:
        if a["code"] in existing:
            continue
        await db.chart_of_accounts.insert_one({
            "id": new_id(),
            **a,
            "is_active": True,
            "opening_balance": 0,
            "created_at": now,
            "created_by": "system",
        })
        inserted += 1
    return inserted


async def _assert_period_open(date_str: str, source_module: str | None = None) -> None:
    """Phase 5.1 — Period-lock enforcement guard.
    Rejects any voucher whose `date` falls inside a locked month or financial year.
    Skips internal/system events that need to back-fill closed books with auditor approval
    (caller can use voucher_type='REV' or pass source_module='opening_balance' to bypass).
    """
    if not date_str:
        return
    if source_module in {"opening_balance"}:    # year-roll-forward
        return
    try:
        period_month = date_str[:7]              # 'YYYY-MM'
    except Exception:
        return
    lock = await db.period_locks.find_one(
        {"period": period_month, "period_type": "month", "status": "locked"},
        {"_id": 0, "period": 1, "locked_by": 1}
    )
    if lock:
        raise PeriodLockedError(
            f"Period {period_month} is locked (by {lock.get('locked_by')}). "
            "Owner / Finance Head must unlock with reason to backdate entries.")
    # Also check FY locks (financial year Apr-Mar)
    try:
        y = int(date_str[:4]); m = int(date_str[5:7])
        fy = f"FY{y - 1}-{str(y % 100).zfill(2)}" if m <= 3 else f"FY{y}-{str((y + 1) % 100).zfill(2)}"
    except Exception:
        return
    fy_lock = await db.period_locks.find_one(
        {"period": fy, "period_type": "year", "status": "locked"}, {"_id": 0, "period": 1, "locked_by": 1}
    )
    if fy_lock:
        raise PeriodLockedError(
            f"Financial year {fy} is closed (by {fy_lock.get('locked_by')}). "
            "Reopen with reason before posting backdated entries.")


class PeriodLockedError(Exception):
    """Raised when an entry tries to post into a locked month/year.
    Routers should catch and convert to HTTPException(400), or we let FastAPI's
    default handler kick in — server.py registers a global handler too."""


# ─── Account-code resolver (cache for the request lifetime) ───────────────
async def get_account_id_by_code(code: str) -> Optional[str]:
    row = await db.chart_of_accounts.find_one({"code": code}, {"_id": 0, "id": 1})
    return row["id"] if row else None


# ─── Core double-entry posting ────────────────────────────────────────────
class JEUnbalanced(Exception):
    pass


async def post_journal_entry(
    *,
    date: str,
    narration: str,
    lines: List[Dict[str, Any]],           # [{account_code, debit, credit, project_id?, cost_centre?, ...}]
    source_module: str,
    source_id: str,
    source_event: str,
    source_ref: Optional[str] = None,
    project_id: Optional[str] = None,
    department: Optional[str] = None,
    posted_by: Optional[str] = None,
    voucher_type: Optional[str] = None,     # JV / PV / RV / SV / PUV / CV / DN / CN / EV / PYV / ADJ / REV
    voucher_number: Optional[str] = None,   # if provided, use as-is (else falls back to JE-####)
    status: str = "posted",                 # 'draft' | 'pending_approval' | 'posted'
    party_type: Optional[str] = None,       # 'client' | 'vendor' | 'employee'
    party_id: Optional[str] = None,
    party_name: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Create a balanced double-entry JE. Idempotent on (source_module, source_id, source_event).

    Returns the JE doc on success, None when skipped (duplicate or unbalanced).
    """
    existing = await db.journal_entries.find_one({
        "source_module": source_module,
        "source_id": source_id,
        "source_event": source_event,
    }, {"_id": 0, "id": 1, "je_number": 1})
    if existing:
        return existing

    # Validate balance
    total_dr = round(sum(float(ln.get("debit") or 0) for ln in lines), 2)
    total_cr = round(sum(float(ln.get("credit") or 0) for ln in lines), 2)
    if abs(total_dr - total_cr) > 0.01:
        logger.warning(
            f"[accounting] Refusing to post unbalanced JE for {source_module}/{source_id}/{source_event}: "
            f"DR={total_dr} CR={total_cr}"
        )
        return None
    if total_dr == 0:
        logger.warning(
            f"[accounting] Skipping zero-amount JE for {source_module}/{source_id}/{source_event}"
        )
        return None

    # Enrich lines with account-name from CoA so downstream readers don't have to look up
    coa_codes = sorted({ln["account_code"] for ln in lines if ln.get("account_code")})
    coa_rows = await db.chart_of_accounts.find({"code": {"$in": coa_codes}}, {"_id": 0, "code": 1, "name": 1, "type": 1, "id": 1}).to_list(50)
    coa_map = {c["code"]: c for c in coa_rows}
    enriched_lines = []
    for ln in lines:
        c = coa_map.get(ln.get("account_code"), {})
        enriched_lines.append({
            "account_code": ln.get("account_code"),
            "account_id":   c.get("id"),
            "account_name": c.get("name"),
            "account_type": c.get("type"),
            "debit":  round(float(ln.get("debit") or 0), 2),
            "credit": round(float(ln.get("credit") or 0), 2),
            "project_id":   ln.get("project_id") or project_id,
            "cost_centre":  ln.get("cost_centre"),
            "department":   ln.get("department") or department,
            "narration":    ln.get("narration"),
        })

    # Phase 5.1 — Period-lock enforcement (reject backdated posts into locked months)
    await _assert_period_open(date, source_module=source_module)

    je_no = voucher_number or await next_sequence("JE")
    je_doc = {
        "id": new_id(),
        "je_number": je_no,
        "voucher_type": voucher_type or "JV",
        "voucher_number": je_no,
        "date": date,
        "narration": narration,
        "lines": enriched_lines,
        "total_debit": total_dr,
        "total_credit": total_cr,
        # ── Legacy compatibility (departments_router + project_dashboard_legacy
        # use these flat fields). We map the *primary* expense/revenue leg.
        "account":   enriched_lines[0].get("account_name"),
        "type":      _legacy_type_from_lines(enriched_lines),
        "amount":    _legacy_amount_from_lines(enriched_lines),
        "cost_centre": enriched_lines[0].get("cost_centre"),
        "project_id": project_id,
        "department": department,
        # ── Audit / provenance
        "source_module": source_module,
        "source_id":    source_id,
        "source_event": source_event,
        "source_ref":   source_ref,
        "posted_by":    posted_by or "system",
        "is_auto_posted": source_module != "manual",
        "status": status,
        "party_type": party_type,
        "party_id": party_id,
        "party_name": party_name,
        "attachments": attachments or [],
        "created_at": now_iso(),
    }
    await db.journal_entries.insert_one(je_doc)
    je_doc.pop("_id", None)
    logger.info(
        f"[accounting] Posted JE {je_no} for {source_module}/{source_event} "
        f"DR={total_dr} CR={total_cr} project={project_id}"
    )
    return je_doc


def _legacy_type_from_lines(lines: List[Dict[str, Any]]) -> str:
    """Map a multi-line JE to the legacy {revenue|expense|asset|liability} bucket
    so the existing dashboard aggregates keep working."""
    type_amounts: Dict[str, float] = {}
    for ln in lines:
        t = ln.get("account_type")
        amt = ln.get("debit", 0) + ln.get("credit", 0)
        type_amounts[t] = type_amounts.get(t, 0) + amt
    return max(type_amounts, key=type_amounts.get) if type_amounts else "expense"


def _legacy_amount_from_lines(lines: List[Dict[str, Any]]) -> float:
    return round(sum(float(ln.get("debit") or 0) for ln in lines), 2)


# ╔════════════════════════════════════════════════════════════════════════╗
# ║  AUTO-POSTING HOOKS — invoked from each module's router                ║
# ╚════════════════════════════════════════════════════════════════════════╝

async def post_grn_finalize(grn: Dict[str, Any], user: dict | None = None) -> Optional[Dict[str, Any]]:
    """When stores marks a GRN finalized:
       DR Inventory   (or Project Cost — Materials if GRN is project-charged)
       CR Goods Received Not Invoiced
    """
    amount = float(grn.get("total") or grn.get("amount") or 0)
    if amount <= 0:
        return None
    dr_code = "5100" if grn.get("project_id") else "1300"  # Project material cost vs Inventory
    return await post_journal_entry(
        date=grn.get("grn_date") or grn.get("date") or now_iso()[:10],
        narration=f"GRN {grn.get('grn_number') or grn.get('id')} — {grn.get('vendor_name') or ''}",
        lines=[
            {"account_code": dr_code, "debit":  amount, "credit": 0, "project_id": grn.get("project_id"), "cost_centre": grn.get("cost_centre"), "department": grn.get("department")},
            {"account_code": "1400", "debit": 0, "credit": amount},
        ],
        source_module="grn",
        source_id=grn["id"],
        source_event="finalize",
        source_ref=grn.get("grn_number"),
        project_id=grn.get("project_id"),
        department=grn.get("department"),
        posted_by=(user or {}).get("name") or "system",
    )


async def post_vendor_invoice_verify(inv: Dict[str, Any], user: dict | None = None) -> Optional[Dict[str, Any]]:
    """Phase-3 vendor-bill posting. On approval of a vendor bill:
       DR Purchase / Expense / Inventory / Project-Cost   (taxable, by `expense_code`)
       DR GST Input Credit (1700)                          (if tax > 0)
       CR Accounts Payable (2100)                          (NET of advance)
       CR TDS Payable (2400)                               (if tds > 0)
       CR Vendor Advance (1510)                            (if advance_adjusted > 0)
    Also reduces AP by retention_amount because retention isn't payable yet
    (it accrues to Retention Payable 2110 instead — only crystallizes on payment).
    """
    gross = float(inv.get("amount") or 0)
    if gross <= 0:
        return None
    tax = float(inv.get("tax_amount") or inv.get("gst_amount") or 0)
    base = round(gross - tax, 2) if tax else gross
    tds = float(inv.get("tds_amount") or 0)
    advance = float(inv.get("advance_adjusted") or 0)
    retention = float(inv.get("retention_amount") or 0)
    expense_code = inv.get("expense_code") or ("1300" if inv.get("is_inventory") else
                                              ("5100" if inv.get("project_id") else "5400"))
    ap_credit = round(gross - tds - advance - retention, 2)
    if ap_credit < 0:
        ap_credit = 0  # safety; means bill is fully offset by deductions

    lines = [
        {"account_code": expense_code, "debit": base, "credit": 0,
         "project_id": inv.get("project_id"), "department": inv.get("department"),
         "narration": "Vendor bill — taxable base"},
    ]
    if tax > 0:
        lines.append({"account_code": "1700", "debit": tax, "credit": 0,
                      "narration": "GST Input"})
    if ap_credit > 0:
        lines.append({"account_code": "2100", "debit": 0, "credit": ap_credit,
                      "project_id": inv.get("project_id"), "narration": "AP — net of deductions"})
    if tds > 0:
        lines.append({"account_code": "2400", "debit": 0, "credit": tds,
                      "narration": "TDS Payable"})
    if advance > 0:
        lines.append({"account_code": "1510", "debit": 0, "credit": advance,
                      "narration": "Vendor advance adjusted"})
    if retention > 0:
        lines.append({"account_code": "2110", "debit": 0, "credit": retention,
                      "narration": "Retention Payable"})

    return await post_journal_entry(
        date=inv.get("invoice_date") or now_iso()[:10],
        narration=f"Vendor Bill {inv.get('invoice_no') or inv.get('id')} — {inv.get('vendor_name') or ''}",
        lines=lines,
        source_module="vendor_bill",
        source_id=inv["id"],
        source_event="approve",
        source_ref=inv.get("invoice_no"),
        project_id=inv.get("project_id"),
        department=inv.get("department"),
        posted_by=(user or {}).get("name") or "system",
        voucher_type="PUV",
        party_type="vendor",
        party_id=inv.get("vendor_id"),
        party_name=inv.get("vendor_name"),
    )


async def post_vendor_payment(payment: Dict[str, Any], invoice: Dict[str, Any] | None = None, user: dict | None = None) -> Optional[Dict[str, Any]]:
    """Phase-3 vendor-payment posting:
       DR Accounts Payable (2100)               (gross amount being settled)
       CR Bank / Cash                           (net cash actually paid)
       CR Retention Payable (2110) [optional]   (retention withheld during payment)
       CR Other deduction (5900) [optional]
    """
    paid = float(payment.get("amount") or 0)
    retention = float(payment.get("retention_held") or 0)
    other = float(payment.get("other_deduction") or 0)
    total_dr = round(paid + retention + other, 2)
    if total_dr <= 0:
        return None
    bank_code = "1110" if (payment.get("mode") or "").lower() == "cash" else "1100"
    lines = [
        {"account_code": "2100", "debit": total_dr, "credit": 0,
         "project_id": payment.get("project_id") or (invoice or {}).get("project_id"),
         "narration": "AP settle"},
        {"account_code": bank_code, "debit": 0, "credit": paid,
         "narration": f"Payment via {payment.get('mode') or 'Bank'}"},
    ]
    if retention > 0:
        lines.append({"account_code": "2110", "debit": 0, "credit": retention, "narration": "Retention withheld"})
    if other > 0:
        lines.append({"account_code": "5900", "debit": 0, "credit": other, "narration": "Other deduction"})

    return await post_journal_entry(
        date=payment.get("payment_date") or payment.get("date") or now_iso()[:10],
        narration=f"Payment to {(invoice or payment).get('vendor_name') or ''} "
                  f"({(invoice or {}).get('invoice_no') or payment.get('reference') or ''})".strip(),
        lines=lines,
        source_module="vendor_payment",
        source_id=payment["id"],
        source_event="released",
        source_ref=payment.get("reference") or payment.get("utr"),
        project_id=payment.get("project_id") or (invoice or {}).get("project_id"),
        department=payment.get("department") or (invoice or {}).get("department"),
        posted_by=(user or {}).get("name") or "system",
        voucher_type="PV",
        party_type="vendor",
        party_id=payment.get("vendor_id") or (invoice or {}).get("vendor_id"),
        party_name=payment.get("vendor_name") or (invoice or {}).get("vendor_name"),
    )


async def post_sales_invoice_issued(inv: Dict[str, Any], user: dict | None = None) -> Optional[Dict[str, Any]]:
    """When a customer invoice is issued / approved:
       DR Accounts Receivable    (gross = base + tax)
       CR Service-line Revenue   (base, mapped by service_type)
       CR GST Output Payable     (tax, split CGST/SGST/IGST under one code 2300)

    `inv.service_type` (case-insensitive) drives the income leg:
      scaffolding → 4101  ·  painting → 4102  ·  roof_sheeting → 4103
      rope_access → 4104  ·  manpower → 4105  ·  material → 4106
      goods → 4110        ·  scrap → 4800     ·  other/None → 4100
    """
    gross = float(inv.get("amount") or inv.get("total") or 0)
    if gross <= 0:
        return None
    tax_amount = float(inv.get("tax_amount") or inv.get("gst_amount") or 0)
    base = round(gross - tax_amount, 2) if tax_amount else gross

    service_map = {
        "scaffolding": "4101", "painting": "4102", "roof_sheeting": "4103", "roof sheeting": "4103",
        "rope_access": "4104", "rope access": "4104", "manpower": "4105", "manpower_supply": "4105",
        "material": "4106", "material_supply": "4106", "goods": "4110",
        "scrap": "4800", "other": "4900",
    }
    st = (inv.get("service_type") or "").strip().lower()
    revenue_code = service_map.get(st) or ("4110" if inv.get("type") == "goods" else "4100")

    lines = [
        {"account_code": "1200", "debit": gross, "credit": 0,
         "project_id": inv.get("project_id"), "narration": "Receivable"},
        {"account_code": revenue_code, "debit": 0, "credit": base,
         "project_id": inv.get("project_id"), "department": inv.get("department"),
         "narration": f"Service income ({st or 'services'})"},
    ]
    if tax_amount > 0:
        lines.append({"account_code": "2300", "debit": 0, "credit": tax_amount, "narration": "GST output"})
    return await post_journal_entry(
        date=inv.get("invoice_date") or now_iso()[:10],
        narration=f"Sales Invoice {inv.get('invoice_no') or inv.get('id')} — {inv.get('client_name') or inv.get('customer') or ''}",
        lines=lines,
        source_module="sales_invoice",
        source_id=inv["id"],
        source_event="issued",
        source_ref=inv.get("invoice_no"),
        project_id=inv.get("project_id"),
        department=inv.get("department"),
        posted_by=(user or {}).get("name") or "system",
        voucher_type="SV",
        party_type="client",
        party_id=inv.get("client_id"),
        party_name=inv.get("client_name"),
    )


async def post_customer_receipt(receipt: Dict[str, Any], user: dict | None = None) -> Optional[Dict[str, Any]]:
    """When a customer payment is received:
       DR Bank / Cash             (net cash received)
       DR TDS Receivable          (tds_deducted, optional)
       DR Retention Receivable    (retention_deducted, optional)
       DR Other Deduction         (other_deduction, optional — booked to 5900)
       CR Accounts Receivable     (gross adjusted = sum of DR side)

    `mode` chooses bank vs cash leg:
       cash → 1110     ·   anything else (bank/upi/neft/rtgs/imps/cheque) → 1100
    """
    amt_net = float(receipt.get("amount") or 0)
    tds = float(receipt.get("tds_deducted") or 0)
    retn = float(receipt.get("retention_deducted") or 0)
    other = float(receipt.get("other_deduction") or 0)
    total_credit = round(amt_net + tds + retn + other, 2)
    if total_credit <= 0:
        return None

    bank_code = "1110" if (receipt.get("mode") or "").lower() == "cash" else "1100"
    lines = [{"account_code": bank_code, "debit": amt_net, "credit": 0,
              "narration": f"Receipt via {receipt.get('mode') or 'Bank'}"}]
    if tds > 0:
        lines.append({"account_code": "1220", "debit": tds, "credit": 0, "narration": "TDS deducted by client"})
    if retn > 0:
        lines.append({"account_code": "1210", "debit": retn, "credit": 0, "narration": "Retention withheld"})
    if other > 0:
        lines.append({"account_code": "5900", "debit": other, "credit": 0, "narration": "Other deduction"})
    lines.append({"account_code": "1200", "debit": 0, "credit": total_credit,
                  "project_id": receipt.get("project_id"), "narration": "AR settle"})

    return await post_journal_entry(
        date=receipt.get("receipt_date") or receipt.get("date") or now_iso()[:10],
        narration=f"Receipt from {receipt.get('client_name') or receipt.get('customer') or ''} "
                  f"({receipt.get('reference') or receipt.get('utr') or ''})".strip(),
        lines=lines,
        source_module="customer_receipt",
        source_id=receipt["id"],
        source_event="received",
        source_ref=receipt.get("reference") or receipt.get("utr"),
        project_id=receipt.get("project_id"),
        department=receipt.get("department"),
        posted_by=(user or {}).get("name") or "system",
        voucher_type="RV",
        party_type="client",
        party_id=receipt.get("client_id"),
        party_name=receipt.get("client_name"),
    )


async def post_stock_issue(issue: Dict[str, Any], user: dict | None = None) -> Optional[Dict[str, Any]]:
    """When stores issues materials to a project (MIS):
       DR Project Cost — Materials
       CR Inventory — Stores
    """
    amount = float(issue.get("total") or issue.get("amount") or 0)
    if amount <= 0:
        return None
    return await post_journal_entry(
        date=issue.get("issue_date") or now_iso()[:10],
        narration=f"MIS {issue.get('mis_number') or issue.get('id')} to project {issue.get('project_name') or ''}",
        lines=[
            {"account_code": "5100", "debit": amount, "credit": 0, "project_id": issue.get("project_id"), "cost_centre": issue.get("cost_centre"), "department": issue.get("department")},
            {"account_code": "1300", "debit": 0, "credit": amount},
        ],
        source_module="material_issue",
        source_id=issue["id"],
        source_event="issued",
        source_ref=issue.get("mis_number"),
        project_id=issue.get("project_id"),
        department=issue.get("department"),
        posted_by=(user or {}).get("name") or "system",
    )


# ╔════════════════════════════════════════════════════════════════════════╗
# ║  REPORTS                                                                ║
# ╚════════════════════════════════════════════════════════════════════════╝

async def trial_balance(start: Optional[str] = None, end: Optional[str] = None,
                        project_id: Optional[str] = None, department: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns one row per account: {code, name, type, debit_total, credit_total, balance}.

    Includes opening balances. Always falls back to legacy `journal_entries` (single-amount)
    when the new `lines` array is absent so historical data still shows up.
    """
    coa = await db.chart_of_accounts.find({"is_active": {"$ne": False}}, {"_id": 0}).sort("code", 1).to_list(500)
    if not coa:
        return []
    tb: Dict[str, Dict[str, Any]] = {
        a["code"]: {
            "code": a["code"], "name": a.get("name") or a["code"], "type": a.get("type") or "expense",
            "debit_total":  float(a.get("opening_balance") or 0) if (a.get("type") or "expense") in {"asset", "expense"} else 0.0,
            "credit_total": float(a.get("opening_balance") or 0) if (a.get("type") or "expense") in {"liability", "equity", "revenue"} else 0.0,
        } for a in coa if a.get("code")
    }
    # Filter
    je_filter: Dict[str, Any] = {}
    if start:
        je_filter["date"] = {**je_filter.get("date", {}), "$gte": start}
    if end:
        je_filter["date"] = {**je_filter.get("date", {}), "$lte": end}
    if project_id:
        je_filter["project_id"] = project_id
    if department:
        je_filter["department"] = department

    async for je in db.journal_entries.find(je_filter, {"_id": 0}):
        lines = je.get("lines") or []
        if lines:
            for ln in lines:
                code = ln.get("account_code")
                if not code or code not in tb:
                    continue
                # Honour per-line filters if the entire-JE filter didn't catch them
                if project_id and ln.get("project_id") and ln.get("project_id") != project_id:
                    continue
                tb[code]["debit_total"]  += float(ln.get("debit")  or 0)
                tb[code]["credit_total"] += float(ln.get("credit") or 0)
        else:
            # Legacy single-amount JE — map onto a sensible default account
            legacy_type = je.get("type")
            legacy_amount = float(je.get("amount") or 0)
            default_code = {
                "revenue": "4100", "expense": "5400",
                "asset": "1100", "liability": "2100",
            }.get(legacy_type)
            if not default_code or default_code not in tb:
                continue
            if legacy_type in {"asset", "expense"}:
                tb[default_code]["debit_total"] += legacy_amount
            else:
                tb[default_code]["credit_total"] += legacy_amount

    rows: List[Dict[str, Any]] = []
    for code in sorted(tb.keys()):
        r = tb[code]
        r["balance"] = round(r["debit_total"] - r["credit_total"], 2)
        if r["debit_total"] != 0 or r["credit_total"] != 0:
            rows.append(r)
    return rows


async def profit_and_loss(start: Optional[str] = None, end: Optional[str] = None,
                          project_id: Optional[str] = None, department: Optional[str] = None) -> Dict[str, Any]:
    tb = await trial_balance(start, end, project_id, department)
    revenue = [r for r in tb if r["type"] == "revenue"]
    expense = [r for r in tb if r["type"] == "expense"]
    total_revenue = round(sum(r["credit_total"] - r["debit_total"] for r in revenue), 2)
    total_expense = round(sum(r["debit_total"] - r["credit_total"] for r in expense), 2)
    return {
        "filters": {"start": start, "end": end, "project_id": project_id, "department": department},
        "revenue": [{**r, "amount": round(r["credit_total"] - r["debit_total"], 2)} for r in revenue],
        "expense": [{**r, "amount": round(r["debit_total"] - r["credit_total"], 2)} for r in expense],
        "total_revenue": total_revenue,
        "total_expense": total_expense,
        "net_profit": round(total_revenue - total_expense, 2),
        "margin_pct": round((total_revenue - total_expense) / total_revenue * 100, 2) if total_revenue else None,
    }


def _bucket_age(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


async def ar_aging(asof: Optional[str] = None) -> Dict[str, Any]:
    """Aged Accounts Receivable. Uses db.invoices for outstanding amount,
    db.payments_received to subtract receipts. Buckets by invoice date."""
    asof_dt = datetime.fromisoformat(asof) if asof else datetime.now(timezone.utc)
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(5000)
    client_invoices = await db.client_invoices.find(
        {"status": {"$nin": ["draft", "cancelled", "rejected"]}}, {"_id": 0}).to_list(5000)
    receipts = await db.payments_received.find({}, {"_id": 0}).to_list(10000)
    rcpt_by_inv: Dict[str, float] = {}
    for r in receipts:
        key = r.get("invoice_id") or r.get("invoice_no")
        if key:
            rcpt_by_inv[key] = rcpt_by_inv.get(key, 0) + float(r.get("amount") or 0)

    rows: List[Dict[str, Any]] = []
    bucket_totals = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for inv in invoices:
        gross = float(inv.get("amount") or inv.get("total") or 0)
        if gross <= 0:
            continue
        paid = rcpt_by_inv.get(inv.get("id"), 0) + rcpt_by_inv.get(inv.get("invoice_no"), 0)
        outstanding = round(gross - paid, 2)
        if outstanding <= 0.01:
            continue
        inv_date = inv.get("invoice_date") or inv.get("date") or asof_dt.date().isoformat()
        try:
            dt = datetime.fromisoformat(inv_date[:10])
            days = max(0, (asof_dt.date() - dt.date()).days)
        except Exception:
            days = 0
        bucket = _bucket_age(days)
        bucket_totals[bucket] += outstanding
        rows.append({
            "invoice_id": inv.get("id"),
            "invoice_no": inv.get("invoice_no"),
            "date": inv_date[:10],
            "client": inv.get("client_name") or inv.get("customer") or inv.get("client"),
            "project_id": inv.get("project_id"),
            "gross": gross, "paid": round(paid, 2), "outstanding": outstanding,
            "days_overdue": days, "bucket": bucket,
        })
    for inv in client_invoices:
        gross = float(inv.get("amount") or 0)
        outstanding = inv.get("outstanding")
        outstanding = round(float(outstanding), 2) if outstanding is not None else round(gross - float(inv.get("paid_amount") or 0), 2)
        if outstanding <= 0.01:
            continue
        inv_date = inv.get("invoice_date") or inv.get("created_at") or asof_dt.date().isoformat()
        try:
            dt = datetime.fromisoformat(inv_date[:10])
            days = max(0, (asof_dt.date() - dt.date()).days)
        except Exception:
            days = 0
        bucket = _bucket_age(days)
        bucket_totals[bucket] += outstanding
        rows.append({
            "invoice_id": inv.get("id"),
            "invoice_no": inv.get("invoice_no"),
            "date": inv_date[:10],
            "client": inv.get("client_name"),
            "project_id": inv.get("project_id"),
            "gross": gross, "paid": round(float(inv.get("paid_amount") or 0), 2), "outstanding": outstanding,
            "days_overdue": days, "bucket": bucket,
        })
    rows.sort(key=lambda x: x["days_overdue"], reverse=True)
    return {
        "asof": asof_dt.date().isoformat(),
        "total_outstanding": round(sum(bucket_totals.values()), 2),
        "buckets": {k: round(v, 2) for k, v in bucket_totals.items()},
        "rows": rows,
    }


async def ap_aging(asof: Optional[str] = None) -> Dict[str, Any]:
    """Aged Accounts Payable from vendor_invoices vs vendor_payments."""
    asof_dt = datetime.fromisoformat(asof) if asof else datetime.now(timezone.utc)
    invoices = await db.vendor_invoices.find({}, {"_id": 0}).to_list(5000)
    vendor_bills = await db.vendor_bills.find(
        {"status": {"$nin": ["draft", "cancelled", "rejected"]}}, {"_id": 0}).to_list(5000)
    payments = await db.vendor_payments.find({}, {"_id": 0}).to_list(10000)
    pay_by_inv: Dict[str, float] = {}
    for p in payments:
        key = p.get("invoice_id") or p.get("invoice_no")
        if key:
            pay_by_inv[key] = pay_by_inv.get(key, 0) + float(p.get("amount") or 0)

    rows: List[Dict[str, Any]] = []
    bucket_totals = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for inv in invoices:
        gross = float(inv.get("amount") or 0)
        if gross <= 0:
            continue
        paid = pay_by_inv.get(inv.get("id"), 0) + pay_by_inv.get(inv.get("invoice_no"), 0)
        outstanding = round(gross - paid, 2)
        if outstanding <= 0.01:
            continue
        inv_date = inv.get("invoice_date") or inv.get("date") or asof_dt.date().isoformat()
        try:
            dt = datetime.fromisoformat(inv_date[:10])
            days = max(0, (asof_dt.date() - dt.date()).days)
        except Exception:
            days = 0
        bucket = _bucket_age(days)
        bucket_totals[bucket] += outstanding
        rows.append({
            "invoice_id": inv.get("id"),
            "invoice_no": inv.get("invoice_no"),
            "date": inv_date[:10],
            "vendor": inv.get("vendor_name") or inv.get("vendor"),
            "project_id": inv.get("project_id"),
            "gross": gross, "paid": round(paid, 2), "outstanding": outstanding,
            "days_overdue": days, "bucket": bucket,
        })
    for vb in vendor_bills:
        gross = float((vb.get("totals") or {}).get("net_payable") or vb.get("amount") or 0)
        outstanding = vb.get("outstanding")
        outstanding = round(float(outstanding), 2) if outstanding is not None else round(gross - float(vb.get("paid_amount") or 0), 2)
        if outstanding <= 0.01:
            continue
        inv_date = vb.get("invoice_date") or vb.get("created_at") or asof_dt.date().isoformat()
        try:
            dt = datetime.fromisoformat(inv_date[:10])
            days = max(0, (asof_dt.date() - dt.date()).days)
        except Exception:
            days = 0
        bucket = _bucket_age(days)
        bucket_totals[bucket] += outstanding
        rows.append({
            "invoice_id": vb.get("id"),
            "invoice_no": vb.get("invoice_no") or vb.get("bill_number") or vb.get("bill_no"),
            "date": inv_date[:10],
            "vendor": vb.get("vendor_name"),
            "project_id": vb.get("project_id"),
            "gross": gross, "paid": round(float(vb.get("paid_amount") or 0), 2), "outstanding": outstanding,
            "days_overdue": days, "bucket": bucket,
        })
    rows.sort(key=lambda x: x["days_overdue"], reverse=True)
    return {
        "asof": asof_dt.date().isoformat(),
        "total_outstanding": round(sum(bucket_totals.values()), 2),
        "buckets": {k: round(v, 2) for k, v in bucket_totals.items()},
        "rows": rows,
    }
