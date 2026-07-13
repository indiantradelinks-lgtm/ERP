"""Pure calculation helpers for the quotation builder.

Kept out of the router so the recalc logic can be unit-tested without spinning
up the API. Operates on plain dicts (the same shape that gets persisted).
"""
from typing import Dict, Tuple


def _r(x: float) -> float:
    """Round to 2 decimals using banker's rounding via standard `round`."""
    return round(float(x or 0), 2)


def recalc_item(item: Dict, tax_mode: str = "intra") -> Dict:
    """Mutates and returns the item with computed fields filled in.

    Fields read:  quantity, rate, discount_pct, gst_pct
    Fields written: amount, discount_amount, taxable, cgst, sgst, igst, gst_amount, total
    """
    qty = float(item.get("quantity") or 0)
    rate = float(item.get("rate") or 0)
    disc_pct = float(item.get("discount_pct") or 0)
    gst_pct = float(item.get("gst_pct") or 0)

    amount = qty * rate
    discount_amount = amount * disc_pct / 100.0
    taxable = amount - discount_amount

    cgst = sgst = igst = 0.0
    if tax_mode == "inter":
        igst = taxable * gst_pct / 100.0
    else:  # intra (default — CGST + SGST split)
        cgst = taxable * (gst_pct / 2.0) / 100.0
        sgst = taxable * (gst_pct / 2.0) / 100.0
    gst_amount = cgst + sgst + igst
    total = taxable + gst_amount

    item["amount"] = _r(amount)
    item["discount_amount"] = _r(discount_amount)
    item["taxable"] = _r(taxable)
    item["cgst"] = _r(cgst)
    item["sgst"] = _r(sgst)
    item["igst"] = _r(igst)
    item["gst_amount"] = _r(gst_amount)
    item["total"] = _r(total)
    return item


def recalc_section(section: Dict, tax_mode: str = "intra") -> Dict:
    items = section.get("items") or []
    for i, it in enumerate(items, start=1):
        it["sno"] = i
        recalc_item(it, tax_mode)
    section["subtotal_basic"] = _r(sum(i.get("amount", 0) for i in items))
    section["subtotal_discount"] = _r(sum(i.get("discount_amount", 0) for i in items))
    section["subtotal_taxable"] = _r(sum(i.get("taxable", 0) for i in items))
    section["subtotal_gst"] = _r(sum(i.get("gst_amount", 0) for i in items))
    section["subtotal_total"] = _r(sum(i.get("total", 0) for i in items))
    return section


def recalc_quotation(quote: Dict) -> Dict:
    """Top-level recalc — fills section subtotals + grand totals.

    Tax mode derivation:
      - If `tax_mode_locked` is True, honor `quote['tax_mode']` as set.
      - Else: always recompute from `company_state` vs `client_state`.
        Same state → intra (CGST + SGST). Different state → inter (IGST).
        Falls back to intra when either state is missing.
    """
    locked = bool(quote.get("tax_mode_locked"))
    if locked:
        tax_mode = (quote.get("tax_mode") or "intra").strip().lower()
        if tax_mode not in ("intra", "inter"):
            tax_mode = "intra"
    else:
        company_state = (quote.get("company_state") or "").strip().lower()
        client_state = (quote.get("client_state") or "").strip().lower()
        if company_state and client_state and company_state != client_state:
            tax_mode = "inter"
        else:
            tax_mode = "intra"
    quote["tax_mode"] = tax_mode

    sections = quote.get("sections") or []
    for s in sections:
        recalc_section(s, tax_mode)

    basic = sum(s.get("subtotal_basic", 0) for s in sections)
    discount = sum(s.get("subtotal_discount", 0) for s in sections)
    taxable = sum(s.get("subtotal_taxable", 0) for s in sections)
    cgst = sum(sum(i.get("cgst", 0) for i in s.get("items") or []) for s in sections)
    sgst = sum(sum(i.get("sgst", 0) for i in s.get("items") or []) for s in sections)
    igst = sum(sum(i.get("igst", 0) for i in s.get("items") or []) for s in sections)
    gst_total = cgst + sgst + igst
    raw_total = taxable + gst_total
    rounded_total = round(raw_total)  # round to nearest rupee
    round_off = rounded_total - raw_total

    # TDS & retention are advisory — applied at RA-bill stage, not deducted from the quotation grand total
    tds_pct = float(quote.get("tds_pct") or 0)
    retention_pct = float(quote.get("retention_pct") or 0)

    quote["totals"] = {
        "basic": _r(basic),
        "discount": _r(discount),
        "taxable": _r(taxable),
        "cgst": _r(cgst),
        "sgst": _r(sgst),
        "igst": _r(igst),
        "gst_total": _r(gst_total),
        "round_off": _r(round_off),
        "grand_total": _r(rounded_total),
        "tds_pct": tds_pct,
        "tds_amount_indicative": _r(taxable * tds_pct / 100.0),
        "retention_pct": retention_pct,
        "retention_amount_indicative": _r(taxable * retention_pct / 100.0),
    }
    quote["total"] = quote["totals"]["grand_total"]  # legacy compatibility (Quotations table)
    return quote


def compute_tax_mode(company_state: str, client_state: str) -> Tuple[str, str]:
    """Returns (tax_mode, reason)."""
    cs = (company_state or "").strip().lower()
    ks = (client_state or "").strip().lower()
    if cs and ks and cs == ks:
        return "intra", f"Same state ({company_state}) — CGST + SGST applies."
    if cs and ks:
        return "inter", f"Inter-state ({company_state} → {client_state}) — IGST applies."
    return "intra", "Tax mode defaulted to intra-state (CGST + SGST). Configure Company Profile to enable auto-detection."
