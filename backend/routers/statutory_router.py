"""Phase 6 — Bank Reconciliation, GSTR-1/3B Export, TDS 26AS Matching, Fixed Asset Register
==============================================================================================
Routes under `/api/statutory/*`.
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

router = APIRouter(prefix="/statutory", tags=["Statutory: Bank Rec, GSTR, TDS, Fixed Assets"])


# ════════════════════════════════════════════════════════════════════════
# 1. BANK RECONCILIATION
# ════════════════════════════════════════════════════════════════════════
class BankStatementLineIn(BaseModel):
    date: str
    description: str
    amount: float                          # positive=credit (inflow), negative=debit (outflow)
    bank_ref: Optional[str] = None         # UTR / cheque #
    bank_account_code: str = "1100"


class BankStatementBatchIn(BaseModel):
    bank_account_code: str = "1100"
    statement_date: str
    lines: List[BankStatementLineIn]


@router.post("/bank-rec/upload")
async def upload_bank_statement(payload: BankStatementBatchIn, request: Request,
                                user: dict = Depends(require_permission("accounting", "write"))):
    """Upload a bank statement (CSV row-by-row from caller). Stores unmatched lines."""
    batch_id = new_id()
    rows = []
    for ln in payload.lines:
        rows.append({
            "id": new_id(),
            "batch_id": batch_id,
            "bank_account_code": ln.bank_account_code or payload.bank_account_code,
            "date": ln.date,
            "description": ln.description,
            "amount": ln.amount,
            "bank_ref": ln.bank_ref,
            "matched_je_id": None,
            "matched_je_number": None,
            "matched_at": None,
            "matched_by": None,
            "status": "unmatched",
            "uploaded_at": now_iso(),
            "uploaded_by": user.get("name") or user.get("email"),
        })
    if rows:
        await db.bank_statement_lines.insert_many(rows)
    await audit(user=user, action="bank_statement_upload", resource="bank_reconciliation",
                record_id=batch_id, after={"count": len(rows), "account": payload.bank_account_code},
                ip=request.client.host if request.client else "")
    return {"batch_id": batch_id, "uploaded": len(rows)}


@router.get("/bank-rec/unmatched")
async def list_unmatched(bank_account_code: str = "1100",
                          user: dict = Depends(require_permission("accounting", "read"))):
    """Returns:
       - bank statement lines NOT yet matched
       - JE lines on the same bank code NOT yet matched
       - auto-suggested matches (same date + same absolute amount, fuzzy ref)
    """
    bank_rows = await db.bank_statement_lines.find(
        {"bank_account_code": bank_account_code, "status": "unmatched"},
        {"_id": 0}
    ).sort("date", -1).to_list(500)

    # JE lines on this bank code
    je_rows = []
    async for j in db.journal_entries.find(
        {"lines.account_code": bank_account_code, "status": "posted", "rec_status": {"$ne": "matched"}},
        {"_id": 0, "id": 1, "voucher_number": 1, "date": 1, "narration": 1,
         "source_ref": 1, "lines": 1, "rec_status": 1}
    ).sort("date", -1).limit(500):
        for ln in (j.get("lines") or []):
            if ln.get("account_code") == bank_account_code:
                je_rows.append({
                    "je_id": j["id"], "voucher_number": j.get("voucher_number"),
                    "date": j.get("date"), "narration": j.get("narration"),
                    "ref": j.get("source_ref"),
                    "debit": float(ln.get("debit") or 0),
                    "credit": float(ln.get("credit") or 0),
                    "amount": float(ln.get("debit") or 0) - float(ln.get("credit") or 0),
                })

    # Auto-suggest matches: same date, equal absolute amount
    suggestions = []
    for b in bank_rows:
        for j in je_rows:
            if (b["date"] == j["date"]
                and abs(abs(b["amount"]) - abs(j["amount"])) < 0.01):
                suggestions.append({"bank_line_id": b["id"], "je_id": j["je_id"],
                                    "confidence": "high"})
                break
    return {"bank_lines": bank_rows, "je_lines": je_rows,
            "suggestions": suggestions, "summary": {
                "unmatched_bank": len(bank_rows), "unmatched_je": len(je_rows),
                "auto_match_candidates": len(suggestions)}}


class BankMatchIn(BaseModel):
    bank_line_id: str
    je_id: str


@router.post("/bank-rec/match")
async def match_bank_line(payload: BankMatchIn, request: Request,
                          user: dict = Depends(require_permission("accounting", "write"))):
    bl = await db.bank_statement_lines.find_one({"id": payload.bank_line_id}, {"_id": 0})
    je = await db.journal_entries.find_one({"id": payload.je_id}, {"_id": 0, "id": 1, "voucher_number": 1})
    if not bl or not je:
        raise HTTPException(status_code=404, detail="Bank line or JE not found")
    await db.bank_statement_lines.update_one({"id": payload.bank_line_id}, {"$set": {
        "status": "matched", "matched_je_id": je["id"], "matched_je_number": je.get("voucher_number"),
        "matched_at": now_iso(), "matched_by": user.get("name") or user.get("email"),
    }})
    await db.journal_entries.update_one({"id": je["id"]}, {"$set": {
        "rec_status": "matched", "rec_at": now_iso(), "rec_bank_line": payload.bank_line_id,
    }})
    await audit(user=user, action="bank_match", resource="bank_reconciliation",
                record_id=payload.bank_line_id, after={"je": je.get("voucher_number")},
                ip=request.client.host if request.client else "")
    return {"ok": True}


@router.post("/bank-rec/auto-match")
async def auto_match(bank_account_code: str = "1100", request: Request = None,
                     user: dict = Depends(require_permission("accounting", "write"))):
    """Runs the high-confidence matcher and applies all suggestions in one go."""
    payload = await list_unmatched(bank_account_code, user)
    applied = 0
    for sug in payload["suggestions"]:
        try:
            await match_bank_line(BankMatchIn(**sug), request, user)
            applied += 1
        except Exception:
            continue
    return {"applied": applied, "remaining_bank": payload["summary"]["unmatched_bank"] - applied}


# ════════════════════════════════════════════════════════════════════════
# 2. GSTR-1 (Outward Supplies) + GSTR-3B (Summary)
# ════════════════════════════════════════════════════════════════════════
@router.get("/gst/gstr-1")
async def gstr_1(period: str,
                  user: dict = Depends(require_permission("accounting", "read"))):
    """GSTR-1 outward-supplies data for a month (period='YYYY-MM').
    Returns Tables: B2B, B2C, HSN summary."""
    start = f"{period}-01"
    end_d = datetime.fromisoformat(start).replace(day=28) + timedelta(days=4)
    end = (end_d - timedelta(days=end_d.day)).date().isoformat()

    invoices = await db.client_invoices.find(
        {"status": {"$in": ["approved", "partially_paid", "paid"]},
         "invoice_date": {"$gte": start, "$lte": end}},
        {"_id": 0}
    ).to_list(2000)

    b2b, b2c = [], []
    hsn_summary: Dict[str, Dict[str, float]] = {}
    totals = {"taxable": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "gross": 0.0}

    for inv in invoices:
        t = inv.get("totals") or {}
        row = {
            "invoice_no": inv["invoice_no"], "invoice_date": inv["invoice_date"],
            "client_name": inv["client_name"], "client_gstin": inv.get("client_gstin"),
            "service_type": inv.get("service_type"),
            "gst_rate": inv.get("gst_rate"),
            "taxable_value": t.get("taxable_value", 0),
            "cgst": t.get("cgst", 0), "sgst": t.get("sgst", 0), "igst": t.get("igst", 0),
            "gross_value": t.get("gross_value", 0),
        }
        # B2B if customer has GSTIN, else B2C
        if inv.get("client_gstin"):
            b2b.append(row)
        else:
            b2c.append(row)
        # HSN summary by service_type (proxy for HSN)
        st = inv.get("service_type") or "other"
        h = hsn_summary.setdefault(st, {"taxable": 0, "cgst": 0, "sgst": 0, "igst": 0, "qty": 0})
        h["taxable"] += float(t.get("taxable_value") or 0)
        h["cgst"] += float(t.get("cgst") or 0)
        h["sgst"] += float(t.get("sgst") or 0)
        h["igst"] += float(t.get("igst") or 0)
        h["qty"] += 1
        for k in totals:
            totals[k] += float(t.get(k) or t.get(k + "_value") or 0) if k != "gross" else float(t.get("gross_value") or 0)

    return {
        "period": period,
        "b2b": {"rows": b2b, "count": len(b2b)},
        "b2c": {"rows": b2c, "count": len(b2c)},
        "hsn_summary": [{"hsn_or_service": k, **{kk: round(vv, 2) for kk, vv in v.items()}}
                        for k, v in hsn_summary.items()],
        "totals": {k: round(v, 2) for k, v in totals.items()},
    }


@router.get("/gst/gstr-3b")
async def gstr_3b(period: str,
                   user: dict = Depends(require_permission("accounting", "read"))):
    """GSTR-3B summary — output liability (sales) vs input credit (purchase) → net payable."""
    start = f"{period}-01"
    end_d = datetime.fromisoformat(start).replace(day=28) + timedelta(days=4)
    end = (end_d - timedelta(days=end_d.day)).date().isoformat()

    # Output (sales)
    out_pipe = [
        {"$match": {"status": {"$in": ["approved", "partially_paid", "paid"]},
                    "invoice_date": {"$gte": start, "$lte": end}}},
        {"$group": {"_id": None,
                    "taxable": {"$sum": "$totals.taxable_value"},
                    "cgst": {"$sum": "$totals.cgst"},
                    "sgst": {"$sum": "$totals.sgst"},
                    "igst": {"$sum": "$totals.igst"}}}
    ]
    out_r = [r async for r in db.client_invoices.aggregate(out_pipe)]
    out = out_r[0] if out_r else {"taxable": 0, "cgst": 0, "sgst": 0, "igst": 0}

    # Input (purchase)
    in_pipe = [
        {"$match": {"status": {"$in": ["approved", "partially_paid", "paid"]},
                    "invoice_date": {"$gte": start, "$lte": end}}},
        {"$group": {"_id": None,
                    "taxable": {"$sum": "$totals.taxable"},
                    "cgst": {"$sum": "$totals.cgst"},
                    "sgst": {"$sum": "$totals.sgst"},
                    "igst": {"$sum": "$totals.igst"}}}
    ]
    in_r = [r async for r in db.vendor_bills.aggregate(in_pipe)]
    inp = in_r[0] if in_r else {"taxable": 0, "cgst": 0, "sgst": 0, "igst": 0}

    net = {
        "cgst": round(float(out.get("cgst") or 0) - float(inp.get("cgst") or 0), 2),
        "sgst": round(float(out.get("sgst") or 0) - float(inp.get("sgst") or 0), 2),
        "igst": round(float(out.get("igst") or 0) - float(inp.get("igst") or 0), 2),
    }
    net["total_payable"] = round(sum(max(v, 0) for v in net.values()), 2)

    return {"period": period,
            "outward_supplies": {k: round(float(v or 0), 2) for k, v in out.items() if k != "_id"},
            "input_tax_credit": {k: round(float(v or 0), 2) for k, v in inp.items() if k != "_id"},
            "net_liability": net}


# ════════════════════════════════════════════════════════════════════════
# 3. TDS 26AS MATCHING
# ════════════════════════════════════════════════════════════════════════
class TDS26ASEntryIn(BaseModel):
    client_gstin_or_pan: Optional[str] = None
    client_name: str
    deductor_tan: Optional[str] = None
    section: str = "194C"
    amount_credited: float
    tds_deducted: float
    date_of_credit: str
    quarter: str = "Q1"


@router.post("/tds/26as/upload")
async def upload_26as(entries: List[TDS26ASEntryIn], request: Request,
                       user: dict = Depends(require_permission("accounting", "write"))):
    """Upload 26AS data (typically from CSV download of TRACES). Stores as separate collection."""
    docs = [{
        "id": new_id(),
        **e.model_dump(),
        "matched_receipt_id": None,
        "matched_at": None,
        "status": "unmatched",
        "uploaded_at": now_iso(),
        "uploaded_by": user.get("name") or user.get("email"),
    } for e in entries]
    if docs:
        await db.tds_26as.insert_many(docs)
    return {"uploaded": len(docs)}


@router.get("/tds/26as/match")
async def tds_26as_match(user: dict = Depends(require_permission("accounting", "read"))):
    """Returns ledger TDS receivable vs 26AS reported, per client."""
    # From our books (receipts)
    book_tds: Dict[str, float] = {}
    async for r in db.client_receipts.find({"tds_deducted": {"$gt": 0}}, {"_id": 0}):
        book_tds[r["client_name"]] = book_tds.get(r["client_name"], 0) + float(r.get("tds_deducted") or 0)

    # From 26AS upload
    reported: Dict[str, float] = {}
    async for r in db.tds_26as.find({}, {"_id": 0}):
        reported[r["client_name"]] = reported.get(r["client_name"], 0) + float(r.get("tds_deducted") or 0)

    all_clients = set(book_tds) | set(reported)
    matches = []
    for c in sorted(all_clients):
        b = round(book_tds.get(c, 0), 2)
        a = round(reported.get(c, 0), 2)
        matches.append({
            "client_name": c, "in_books": b, "in_26as": a,
            "diff": round(b - a, 2),
            "status": "matched" if abs(b - a) < 1 else "mismatch",
        })
    summary = {
        "matched": sum(1 for m in matches if m["status"] == "matched"),
        "mismatch": sum(1 for m in matches if m["status"] == "mismatch"),
        "total_books": round(sum(book_tds.values()), 2),
        "total_26as": round(sum(reported.values()), 2),
    }
    return {"matches": matches, "summary": summary}


# ════════════════════════════════════════════════════════════════════════
# 4. FIXED ASSET REGISTER + DEPRECIATION
# ════════════════════════════════════════════════════════════════════════
class FixedAssetIn(BaseModel):
    asset_code: Optional[str] = None      # auto-generate FA-####
    asset_name: str
    category: str = "plant_machinery"     # plant_machinery | vehicle | office_equipment
    purchase_date: str
    purchase_cost: float
    useful_life_years: int = 10
    salvage_value: float = 0
    location: Optional[str] = None
    project_id: Optional[str] = None
    serial_no: Optional[str] = None
    vendor_bill_id: Optional[str] = None  # links to vendor_bills if bought via PO
    method: str = "straight_line"
    notes: Optional[str] = None


@router.post("/fixed-assets")
async def create_fixed_asset(payload: FixedAssetIn, request: Request,
                              user: dict = Depends(require_permission("accounting", "write"))):
    if payload.purchase_cost <= 0:
        raise HTTPException(status_code=400, detail="purchase_cost must be > 0")
    if payload.useful_life_years <= 0:
        raise HTTPException(status_code=400, detail="useful_life_years must be > 0")
    code = payload.asset_code or await next_sequence("FA")
    annual_dep = round((payload.purchase_cost - (payload.salvage_value or 0)) / payload.useful_life_years, 2)
    monthly_dep = round(annual_dep / 12, 2)
    cat_to_code = {"plant_machinery": "1600", "vehicle": "1610", "office_equipment": "1620"}
    doc = {
        "id": new_id(),
        "asset_code": code,
        "asset_name": payload.asset_name,
        "category": payload.category,
        "ledger_code": cat_to_code.get(payload.category, "1600"),
        "purchase_date": payload.purchase_date,
        "purchase_cost": payload.purchase_cost,
        "salvage_value": payload.salvage_value,
        "useful_life_years": payload.useful_life_years,
        "annual_depreciation": annual_dep,
        "monthly_depreciation": monthly_dep,
        "accumulated_depreciation": 0.0,
        "book_value": payload.purchase_cost,
        "method": payload.method,
        "location": payload.location,
        "project_id": payload.project_id,
        "serial_no": payload.serial_no,
        "vendor_bill_id": payload.vendor_bill_id,
        "status": "active",
        "notes": payload.notes,
        "created_at": now_iso(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.fixed_assets.insert_one(doc)
    doc.pop("_id", None)
    await audit(user=user, action="fixed_asset_create", resource="fixed_assets",
                record_id=doc["id"], after={"code": code, "cost": payload.purchase_cost},
                ip=request.client.host if request.client else "")
    return doc


@router.get("/fixed-assets")
async def list_fixed_assets(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.fixed_assets.find({}, {"_id": 0}).sort("purchase_date", -1).to_list(500)
    total_cost = round(sum(float(r.get("purchase_cost") or 0) for r in rows), 2)
    total_accum = round(sum(float(r.get("accumulated_depreciation") or 0) for r in rows), 2)
    total_book = round(sum(float(r.get("book_value") or 0) for r in rows), 2)
    return {"rows": rows, "summary": {"count": len(rows), "total_cost": total_cost,
                                       "accumulated_depreciation": total_accum, "book_value": total_book}}


@router.post("/fixed-assets/depreciation/run")
async def run_depreciation(period: str, request: Request,
                           user: dict = Depends(require_permission("accounting", "write"))):
    """Posts one month of depreciation for all active assets. Idempotent per (asset, period)."""
    today = datetime.now(timezone.utc).date().isoformat()
    period_date = f"{period}-28"
    posted = 0
    skipped = 0
    async for a in db.fixed_assets.find({"status": "active"}, {"_id": 0}):
        # Idempotency: skip if already posted for this period
        already = await db.fixed_asset_depreciation_runs.find_one(
            {"asset_id": a["id"], "period": period}, {"_id": 0, "id": 1})
        if already:
            skipped += 1
            continue
        amt = float(a.get("monthly_depreciation") or 0)
        if amt <= 0:
            skipped += 1
            continue
        if float(a.get("book_value") or 0) <= float(a.get("salvage_value") or 0):
            skipped += 1
            continue

        je = await post_journal_entry(
            date=period_date,
            narration=f"Depreciation · {a['asset_name']} ({a['asset_code']}) · {period}",
            lines=[
                {"account_code": "5500", "debit": amt, "credit": 0, "project_id": a.get("project_id"),
                 "narration": f"Depreciation {period}"},
                {"account_code": a.get("ledger_code", "1600"), "debit": 0, "credit": amt,
                 "narration": "Accumulated depreciation"},
            ],
            source_module="depreciation",
            source_id=a["id"],
            source_event="run",
            source_ref=period,
            project_id=a.get("project_id"),
            posted_by=user.get("name") or user.get("email"),
            voucher_type="ADJ", status="posted",
        )
        await db.fixed_assets.update_one({"id": a["id"]}, {"$inc": {
            "accumulated_depreciation": amt, "book_value": -amt,
        }, "$set": {"last_depreciation_period": period, "last_depreciation_at": today}})
        await db.fixed_asset_depreciation_runs.insert_one({
            "id": new_id(), "asset_id": a["id"], "asset_code": a["asset_code"],
            "period": period, "amount": amt, "je_id": (je or {}).get("id"),
            "je_voucher_number": (je or {}).get("voucher_number"),
            "posted_at": now_iso(), "posted_by": user.get("name") or user.get("email"),
        })
        posted += 1

    await audit(user=user, action="depreciation_run", resource="fixed_assets",
                record_id=period, after={"period": period, "posted": posted, "skipped": skipped},
                ip=request.client.host if request.client else "")
    return {"period": period, "posted": posted, "skipped": skipped}


@router.get("/fixed-assets/depreciation/runs")
async def list_depreciation_runs(user: dict = Depends(require_permission("accounting", "read"))):
    rows = await db.fixed_asset_depreciation_runs.find({}, {"_id": 0}).sort("posted_at", -1).limit(500).to_list(500)
    by_period: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        p = r["period"]
        bp = by_period.setdefault(p, {"period": p, "total": 0.0, "count": 0})
        bp["total"] += float(r.get("amount") or 0)
        bp["count"] += 1
    return {"runs": rows[:200],
            "by_period": [{"period": k, **{kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()}}
                          for k, v in sorted(by_period.items(), reverse=True)]}
