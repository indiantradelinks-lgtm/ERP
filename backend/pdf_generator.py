"""PDF generators for procurement & store documents (Iter 55).

Uses WeasyPrint primarily — falls back to ReportLab if WeasyPrint cannot render.

Public API (all return ``bytes``):
  • render_pr_pdf(pr)
  • render_rfq_pdf(rfq, pr)
  • render_comparative_pdf(rfq, vendors_table, l1_data)
  • render_po_pdf(po, vendor, pr)
  • render_grn_pdf(grn, po, vendor)
  • render_material_issue_pdf(slip, project)

Templates are inline HTML to avoid any extra file deps. Branding stays minimal +
professional — slate header, table grid, footer with system note.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from weasyprint import HTML  # type: ignore
    _WP_OK = True
except Exception:  # pragma: no cover
    _WP_OK = False

# Reportlab fallback
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    _RL_OK = True
except Exception:  # pragma: no cover
    _RL_OK = False


BRAND = "INDIAN TRADE LINKS"
FOOTER_NOTE = "System-generated · Not valid without approval signatures"
CORPORATE_ADDRESS = ("Corporate Address - Tower-1, Office No. 605-606, 6th Floor, "
                     "Pearl Omaxe Building, Netaji Subhash Place, Pitampura, Delhi - 110034.")
WATERMARK_FILE = "file:///app/backend/assets/itl-watermark.png"

CSS_BASE = """
<style>
@page { size: A4; margin: 18mm 16mm 22mm 16mm; }
* { box-sizing: border-box; font-family: 'Helvetica','Arial',sans-serif; }
body { color: #0f172a; font-size: 10.5pt; }
.brand { font-size: 8.5pt; color: #475569; letter-spacing: 0.5px; text-transform: uppercase; }
h1 { font-size: 18pt; margin: 0 0 4px 0; color: #0f172a; }
.title-row { display: flex; justify-content: space-between; align-items: flex-end;
             border-bottom: 2px solid #0f172a; padding-bottom: 6px; margin-bottom: 14px; }
.meta { font-size: 9.5pt; color: #334155; }
.meta b { color: #0f172a; }
.section-title { font-size: 11pt; font-weight: 700; color: #1e293b;
                 border-bottom: 1px solid #cbd5e1; padding: 8px 0 4px; margin: 14px 0 6px; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin-top: 4px; }
th { background: #f1f5f9; color: #0f172a; text-align: left; padding: 6px 8px;
     border: 1px solid #cbd5e1; font-weight: 700; }
td { padding: 5px 8px; border: 1px solid #e2e8f0; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.totals { margin-top: 10px; float: right; min-width: 280px; }
.totals td { border: none; padding: 3px 0; }
.totals tr.grand td { border-top: 2px solid #0f172a; font-weight: 700; font-size: 11pt; padding-top: 6px; }
.kv { display: grid; grid-template-columns: 140px 1fr; gap: 4px 12px; font-size: 9.5pt; }
.kv b { color: #0f172a; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px;
       font-size: 8pt; font-weight: 700; letter-spacing: 0.3px; }
.tag.green { background: #dcfce7; color: #166534; }
.tag.amber { background: #fef3c7; color: #92400e; }
.tag.red   { background: #fee2e2; color: #991b1b; }
.tag.slate { background: #e2e8f0; color: #334155; }
.footer { position: fixed; bottom: 6mm; left: 16mm; right: 16mm;
          font-size: 8pt; color: #64748b; border-top: 1px solid #e2e8f0;
          padding-top: 4px; }
.footer .frow { display: flex; justify-content: space-between; }
.footer .faddr { text-align: center; font-size: 7.5pt; margin-top: 2px; }
.wm { position: fixed; top: 38%; left: 0; right: 0; text-align: center; z-index: -1; }
.wm img { width: 130mm; }
.signs { margin-top: 28px; display: flex; gap: 24px; }
.signs .box { flex: 1; border-top: 1px solid #0f172a; padding-top: 4px; font-size: 9pt; color: #475569; }
.note { font-size: 9pt; color: #64748b; margin-top: 6px; }
.justify { background: #fef3c7; border-left: 3px solid #f59e0b; padding: 6px 8px; font-size: 9pt; }
</style>
"""


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M UTC")


def _money(v: Any) -> str:
    try:
        n = float(v or 0)
        return f"{n:,.2f}"
    except Exception:
        return "0.00"


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _wrap(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{CSS_BASE}</head><body>
<div class="wm"><img src="{WATERMARK_FILE}" /></div>
<div class="title-row">
  <div>
    <div class="brand">{_esc(BRAND)}</div>
    <h1>{_esc(title)}</h1>
  </div>
  <div class="meta">Generated: <b>{_now_str()}</b></div>
</div>
{body_html}
<div class="footer">
  <div class="frow"><div>{_esc(FOOTER_NOTE)}</div><div>{_esc(BRAND)}</div></div>
  <div class="faddr">{_esc(CORPORATE_ADDRESS)}</div>
</div>
</body></html>"""


def _render(html: str) -> bytes:
    if _WP_OK:
        try:
            return HTML(string=html).write_pdf()
        except Exception:
            pass
    # Fallback: very basic text PDF via ReportLab
    if _RL_OK:
        from io import BytesIO
        import re
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        text = re.sub(r"<[^>]+>", " ", html)
        y = 280 * mm
        for line in text.splitlines():
            if not line.strip():
                continue
            c.drawString(15 * mm, y, line.strip()[:110])
            y -= 4 * mm
            if y < 15 * mm:
                c.showPage()
                y = 280 * mm
        c.showPage()
        c.save()
        return buf.getvalue()
    raise RuntimeError("No PDF backend available")


# ─────────────────────────────────── PR ───────────────────────────────────
def render_pr_pdf(pr: Dict[str, Any]) -> bytes:
    items_html = ""
    total = 0.0
    for i, it in enumerate(pr.get("items") or [], 1):
        qty = float(it.get("quantity") or 0)
        rate = float(it.get("rate") or 0)
        amt = qty * rate
        total += amt
        items_html += f"""<tr>
<td>{i}</td>
<td><b>{_esc(it.get('name'))}</b><div class="note">{_esc(it.get('description') or '')}</div></td>
<td>{_esc(it.get('category') or '—')}</td>
<td class="num">{_money(qty)}</td>
<td>{_esc(it.get('unit') or 'Nos')}</td>
<td>{_esc(it.get('required_date') or '—')}</td>
<td class="num">{_money(rate) if rate else '—'}</td>
<td class="num">{_money(amt) if amt else '—'}</td>
</tr>"""
    status = pr.get("status", "draft")
    tone = {"approved": "green", "pending_approval": "amber", "rejected": "red"}.get(status, "slate")
    body = f"""
<div class="kv">
  <div><b>PR Number</b></div><div>{_esc(pr.get('pr_number') or pr.get('dept_doc_no'))}</div>
  <div><b>Date</b></div><div>{_esc(pr.get('pr_date'))}</div>
  <div><b>Department</b></div><div>{_esc(pr.get('department') or '—')}</div>
  <div><b>Project</b></div><div>{_esc(pr.get('project_code') or pr.get('project_id') or '—')}</div>
  <div><b>Site</b></div><div>{_esc(pr.get('site_code') or '—')}</div>
  <div><b>Priority</b></div><div>{_esc(pr.get('priority', 'medium')).upper()}</div>
  <div><b>Requested by</b></div><div>{_esc(pr.get('requested_by'))}</div>
  <div><b>Status</b></div><div><span class="tag {tone}">{_esc(status).upper()}</span></div>
</div>
<div class="section-title">Items Requested</div>
<table>
<thead><tr>
<th>#</th><th>Item</th><th>Category</th><th class="num">Qty</th><th>Unit</th>
<th>Need by</th><th class="num">Est. Rate</th><th class="num">Est. Amount</th>
</tr></thead><tbody>{items_html or '<tr><td colspan=8>No items</td></tr>'}</tbody></table>
<table class="totals"><tr class="grand"><td>Estimated Total (₹)</td><td class="num">{_money(total)}</td></tr></table>
<div class="section-title" style="clear:both;">Remarks</div>
<div class="note">{_esc(pr.get('remarks') or '—')}</div>
<div class="signs">
  <div class="box">Requested by<br/><b>{_esc(pr.get('requested_by'))}</b></div>
  <div class="box">Dept. Head Approval</div>
  <div class="box">Procurement Head Approval</div>
</div>
"""
    return _render(_wrap(f"Purchase Requisition — {pr.get('pr_number','')}", body))


# ─────────────────────────────────── RFQ ───────────────────────────────────
def render_rfq_pdf(rfq: Dict[str, Any], pr: Optional[Dict[str, Any]] = None) -> bytes:
    items_html = ""
    for i, it in enumerate(rfq.get("items") or [], 1):
        items_html += f"""<tr>
<td>{i}</td>
<td><b>{_esc(it.get('name'))}</b><div class="note">{_esc(it.get('description') or '')}</div></td>
<td class="num">{_money(it.get('quantity'))}</td>
<td>{_esc(it.get('unit') or 'Nos')}</td>
<td>{_esc(it.get('technical_specs') or '—')}</td>
</tr>"""
    vendors_html = ""
    for v in (rfq.get("vendors") or []):
        responded = v.get("response_at") is not None
        tag = '<span class="tag green">RESPONDED</span>' if responded else '<span class="tag amber">PENDING</span>'
        vendors_html += f"<tr><td>{_esc(v.get('vendor_name'))}</td><td>{_esc(v.get('email') or '—')}</td><td>{tag}</td></tr>"
    body = f"""
<div class="kv">
  <div><b>RFQ Number</b></div><div>{_esc(rfq.get('rfq_number'))}</div>
  <div><b>RFQ Date</b></div><div>{_esc(rfq.get('rfq_date') or rfq.get('created_at','')[:10])}</div>
  <div><b>PR Reference</b></div><div>{_esc((pr or {}).get('pr_number') or rfq.get('pr_number') or '—')}</div>
  <div><b>Response Deadline</b></div><div>{_esc(rfq.get('response_deadline') or '—')}</div>
  <div><b>Status</b></div><div><span class="tag slate">{_esc(rfq.get('status','open')).upper()}</span></div>
</div>
<div class="section-title">Items</div>
<table><thead><tr><th>#</th><th>Item</th><th class="num">Qty</th><th>Unit</th><th>Technical Specs</th></tr></thead>
<tbody>{items_html or '<tr><td colspan=5>No items</td></tr>'}</tbody></table>
<div class="section-title">Vendors Invited</div>
<table><thead><tr><th>Vendor</th><th>Email</th><th>Response</th></tr></thead>
<tbody>{vendors_html or '<tr><td colspan=3>None</td></tr>'}</tbody></table>
<div class="section-title">Terms & Conditions</div>
<div class="note">{_esc(rfq.get('terms') or '1. Quote validity 30 days · 2. Delivery as per schedule · 3. Payment 30 days after GRN.')}</div>
"""
    return _render(_wrap(f"Request for Quotation — {rfq.get('rfq_number','')}", body))


# ────────────────────────────── COMPARATIVE ──────────────────────────────
def render_comparative_pdf(rfq: Dict[str, Any], comparative: Dict[str, Any]) -> bytes:
    """`comparative` is the output shape from /api/procurement/rfqs/{id}/comparative."""
    items = comparative.get("items") or []
    vendors = comparative.get("vendors") or []
    # Header row of vendor names
    head = "<th>Item</th><th class='num'>Qty</th>"
    for v in vendors:
        rank = v.get("rank")
        rank_tag = f"<div class='tag green'>L{rank}</div>" if rank == 1 else (
            f"<div class='tag amber'>L{rank}</div>" if rank == 2 else f"<div class='tag slate'>L{rank}</div>"
        )
        head += f"<th class='num'>{_esc(v.get('vendor_name'))}<br/>{rank_tag}</th>"
    # Body rows
    rows = ""
    for it in items:
        row = f"<td><b>{_esc(it.get('name'))}</b></td><td class='num'>{_money(it.get('quantity'))}</td>"
        for v in vendors:
            cell = it.get("vendor_quotes", {}).get(v.get("vendor_id"))
            if cell:
                row += f"<td class='num'>₹ {_money(cell.get('rate'))}<br/><span class='note'>= {_money(cell.get('amount'))}</span></td>"
            else:
                row += "<td class='num'>—</td>"
        rows += f"<tr>{row}</tr>"
    # Vendor summary row
    sum_row = "<tr style='background:#f8fafc;font-weight:700;'><td>TOTAL</td><td></td>"
    for v in vendors:
        sum_row += f"<td class='num'>₹ {_money(v.get('total'))}</td>"
    sum_row += "</tr>"
    # Delta vs L1 row
    delta_row = "<tr><td>Delta vs L1</td><td></td>"
    for v in vendors:
        d = v.get("delta_vs_l1")
        if v.get("rank") == 1:
            delta_row += "<td class='num'><span class='tag green'>L1 BASE</span></td>"
        elif d is not None:
            pct = v.get("delta_pct_vs_l1") or 0
            delta_row += f"<td class='num'>+ ₹ {_money(d)}<br/><span class='note'>+{pct:.1f}%</span></td>"
        else:
            delta_row += "<td class='num'>—</td>"
    delta_row += "</tr>"

    selected = next((v for v in vendors if v.get("selected")), None)
    selected_html = ""
    if selected:
        if selected.get("rank") == 1:
            selected_html = f"<div class='tag green'>SELECTED — L1: {_esc(selected.get('vendor_name'))} (₹ {_money(selected.get('total'))})</div>"
        else:
            just = selected.get("non_l1_justification") or comparative.get("non_l1_justification") or "—"
            selected_html = (f"<div class='tag amber'>SELECTED — L{selected.get('rank')}: "
                             f"{_esc(selected.get('vendor_name'))} (₹ {_money(selected.get('total'))})</div>"
                             f"<div class='justify' style='margin-top:6px;'><b>Non-L1 Justification:</b> {_esc(just)}</div>")

    body = f"""
<div class="kv">
  <div><b>RFQ Number</b></div><div>{_esc(rfq.get('rfq_number'))}</div>
  <div><b>PR Reference</b></div><div>{_esc(rfq.get('pr_number') or '—')}</div>
  <div><b>Date</b></div><div>{_esc(rfq.get('rfq_date') or rfq.get('created_at','')[:10])}</div>
</div>
<div class="section-title">Vendor Quotation Comparison</div>
<table><thead><tr>{head}</tr></thead>
<tbody>{rows}{sum_row}{delta_row}</tbody></table>
<div class="section-title">Selection</div>
{selected_html or '<div class="note">No vendor selected yet.</div>'}
<div class="signs">
  <div class="box">Prepared by Procurement</div>
  <div class="box">Reviewed by Finance</div>
  <div class="box">Approved by Director</div>
</div>
"""
    return _render(_wrap(f"Comparative Statement — {rfq.get('rfq_number','')}", body))


# ─────────────────────────────────── PO ───────────────────────────────────
def render_po_pdf(po: Dict[str, Any], vendor: Optional[Dict[str, Any]] = None) -> bytes:
    items_html = ""
    sub_total = 0.0
    gst_amt = 0.0
    default_gst = float(po.get("gst_pct") or 18)
    for i, it in enumerate(po.get("items") or [], 1):
        qty = float(it.get("quantity") or 0)
        rate = float(it.get("rate") or 0)
        amt = float(it.get("line_value") if it.get("line_value") is not None else (qty * rate))
        item_gst_pct = float(it.get("gst_pct") if it.get("gst_pct") is not None else default_gst)
        item_gst_amt = float(it.get("gst_amount") if it.get("gst_amount") is not None else round(amt * item_gst_pct / 100, 2))
        line_total = float(it.get("line_total") if it.get("line_total") is not None else round(amt + item_gst_amt, 2))
        sub_total += amt
        gst_amt += item_gst_amt
        meta = []
        if it.get("make"):
            meta.append(f"Make: {_esc(it['make'])}")
        if it.get("technical_specs"):
            meta.append(f"Specs: {_esc(it['technical_specs'])}")
        meta.append(f"HSN/SAC: {_esc(it.get('hsn_sac') or '—')}")
        items_html += f"""<tr>
<td>{i}</td>
<td><b>{_esc(it.get('name'))}</b><div class="note">{' · '.join(meta)}</div></td>
<td class="num">{_money(qty)}</td>
<td>{_esc(it.get('unit') or 'Nos')}</td>
<td class="num">{_money(rate)}</td>
<td class="num">{_money(amt)}</td>
<td class="num">{item_gst_pct:g}%</td>
<td class="num">{_money(item_gst_amt)}</td>
<td class="num">{_money(line_total)}</td>
</tr>"""
    grand = sub_total + gst_amt
    gst_type = (po.get("gst_type") or "cgst_sgst").lower()
    if gst_type == "igst":
        gst_rows = f"<tr><td>IGST</td><td class='num'>₹ {_money(gst_amt)}</td></tr>"
    else:
        half = gst_amt / 2
        gst_rows = (f"<tr><td>CGST</td><td class='num'>₹ {_money(half)}</td></tr>"
                    f"<tr><td>SGST</td><td class='num'>₹ {_money(gst_amt - half)}</td></tr>")
    revision = int(po.get("revision") or 0)
    extra_rows = ""
    if float(po.get("advance_pct") or 0) > 0:
        extra_rows += f"<tr><td>Advance @ {float(po['advance_pct']):g}%</td><td class='num'>₹ {_money(po.get('advance_amount') or 0)}</td></tr>"
    if float(po.get("tds_pct") or 0) > 0:
        extra_rows += f"<tr><td>TDS @ {float(po['tds_pct']):g}% (on basic)</td><td class='num'>₹ {_money(po.get('tds_amount') or 0)}</td></tr>"
    if float(po.get("retention_pct") or 0) > 0:
        extra_rows += f"<tr><td>Retention @ {float(po['retention_pct']):g}%</td><td class='num'>₹ {_money(po.get('retention_amount') or 0)}</td></tr>"
    rev_banner = ""
    amendments = po.get("amendments") or []
    if revision > 0:
        amend_rows = "".join(
            f"<div class='note'><b>Rev {a.get('revision')}</b> — {_esc(a.get('reason') or '—')} "
            f"<span style='color:#888'>(by {_esc(a.get('amended_by') or '—')} on {_esc(str(a.get('at') or '')[:10])})</span></div>"
            for a in amendments)
        rev_banner = f"""<div style="border:1.5px solid #b45309;background:#fef3c7;padding:6px 10px;margin:8px 0;">
<b>AMENDED PURCHASE ORDER — REVISION {revision}</b>{amend_rows}</div>"""
    v = vendor or {}
    addr_lines: List[str] = []
    for a in (v.get("addresses") or [])[:1]:
        addr_lines += [a.get("line1"), a.get("line2"), f"{a.get('city','')} {a.get('pin','')}", a.get("state")]
    addr_html = "<br/>".join([_esc(x) for x in addr_lines if x]) or _esc(v.get("address") or "—")
    body = f"""
{rev_banner}
<div class="kv">
  <div><b>PO Number</b></div><div>{_esc(po.get('po_number') or po.get('po_no'))}{f" — <b>Rev {revision}</b>" if revision else ""}</div>
  <div><b>PO Date</b></div><div>{_esc(po.get('po_date') or po.get('created_at','')[:10])}</div>
  <div><b>PR Reference</b></div><div>{_esc(po.get('pr_number') or '—')}</div>
  <div><b>RFQ Reference</b></div><div>{_esc(po.get('rfq_number') or '—')}</div>
  <div><b>Project</b></div><div>{_esc(po.get('project_code') or '—')}</div>
  <div><b>Delivery Date</b></div><div>{_esc(po.get('delivery_date') or '—')}</div>
  <div><b>Payment Terms</b></div><div>{_esc(po.get('payment_terms') or '—')}</div>
</div>
<div class="section-title">Vendor</div>
<div class="kv">
  <div><b>Name</b></div><div>{_esc(v.get('name') or po.get('vendor_name') or '—')}</div>
  <div><b>Vendor Code</b></div><div>{_esc(v.get('vendor_code') or '—')}</div>
  <div><b>Address</b></div><div>{addr_html}</div>
  <div><b>GSTIN</b></div><div>{_esc(v.get('gst') or '—')}</div>
  <div><b>PAN</b></div><div>{_esc(v.get('pan') or '—')}</div>
  <div><b>Contact</b></div><div>{_esc(v.get('phone') or '—')} · {_esc(v.get('email') or '')}</div>
</div>
<div class="section-title">Items</div>
<table><thead><tr><th>#</th><th>Item</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate</th><th class="num">Amount</th><th class="num">GST %</th><th class="num">GST Amt</th><th class="num">Total</th></tr></thead>
<tbody>{items_html or '<tr><td colspan=9>No items</td></tr>'}</tbody></table>
<table class="totals">
<tr><td>Sub-total</td><td class="num">₹ {_money(sub_total)}</td></tr>
{gst_rows}
<tr><td>Total GST</td><td class="num">₹ {_money(gst_amt)}</td></tr>
<tr class="grand"><td>Grand Total</td><td class="num">₹ {_money(grand)}</td></tr>
{extra_rows}
</table>
{f'<div class="section-title" style="clear:both;">Delivery Terms</div><div class="note">{_esc(po.get("delivery_terms"))}</div>' if po.get('delivery_terms') else ''}
{f'<div class="section-title" style="clear:both;">Special Terms</div><div class="note">{_esc(po.get("special_terms"))}</div>' if po.get('special_terms') else ''}
{f'<div class="section-title" style="clear:both;">Other Terms</div><div class="note">{_esc(po.get("other_terms"))}</div>' if po.get('other_terms') else ''}
<div class="section-title" style="clear:both;">Terms & Conditions</div>
{"".join(f"<div class='note'><b>{i + 1}. {_esc(t.get('title'))}</b> <span style='color:#888'>[{_esc((t.get('category') or 'general').upper())}]</span> — {_esc(t.get('body'))}</div>" for i, t in enumerate(po.get('terms_structured') or [])) or f"<div class='note'>{_esc(po.get('terms') or '1. Goods to be delivered as per delivery schedule.  2. Payment 30 days after GRN acceptance.  3. Quality as per agreed spec — defects to be replaced free of cost.')}</div>"}
<div class="signs">
  <div class="box">For {_esc(BRAND)}</div>
  <div class="box">Vendor Acknowledgement</div>
</div>
"""
    return _render(_wrap(f"Purchase Order — {po.get('po_number') or po.get('po_no','')}{f' (Rev {revision})' if revision else ''}", body))


# ─────────────────────────────────── GRN ───────────────────────────────────
def render_grn_pdf(grn: Dict[str, Any], po: Optional[Dict[str, Any]] = None,
                    vendor: Optional[Dict[str, Any]] = None) -> bytes:
    items_html = ""
    for i, it in enumerate(grn.get("items") or [], 1):
        rec = float(it.get("received_qty") or it.get("received") or it.get("quantity") or 0)
        acc = float(it.get("accepted_qty") or it.get("accepted") or 0)
        rej = float(it.get("rejected_qty") or it.get("rejected") or 0)
        item_st = (it.get("inspection_status") or "").lower()
        if item_st in ("approved", "accepted"):
            tag = '<span class="tag green">ACCEPTED</span>'
        elif item_st in ("rejected",):
            tag = '<span class="tag red">REJECTED</span>'
        elif item_st in ("partial", "partially_accepted"):
            tag = '<span class="tag amber">PARTIAL</span>'
        else:
            tag = '<span class="tag green">ACCEPTED</span>' if rej == 0 and acc > 0 else (
                  '<span class="tag amber">PARTIAL</span>' if acc > 0 else '<span class="tag red">REJECTED</span>')
        items_html += f"""<tr>
<td>{i}</td>
<td><b>{_esc(it.get('item_name') or it.get('name'))}</b><div class="note">{_esc(it.get('description') or '')}</div></td>
<td class="num">{_money(it.get('ordered_qty') or 0)}</td>
<td class="num">{_money(rec)}</td>
<td class="num">{_money(acc)}</td>
<td class="num">{_money(rej)}</td>
<td>{_esc(it.get('unit') or 'Nos')}</td>
<td>{tag}</td>
</tr>"""
    v = vendor or {}
    body = f"""
<div class="kv">
  <div><b>GRN Number</b></div><div>{_esc(grn.get('grn_number') or grn.get('grn_no'))}</div>
  <div><b>GRN Date</b></div><div>{_esc(grn.get('grn_date') or grn.get('created_at','')[:10])}</div>
  <div><b>PO Reference</b></div><div>{_esc(grn.get('po_number') or (po or {}).get('po_number') or '—')}</div>
  <div><b>Vendor</b></div><div>{_esc(v.get('name') or grn.get('vendor_name') or '—')}</div>
  <div><b>Vehicle / Challan</b></div><div>{_esc(grn.get('vehicle_no') or grn.get('vehicle_number') or '—')} · {_esc(grn.get('challan_no') or grn.get('transporter_lr_no') or '—')}</div>
  <div><b>GRN Status</b></div><div><span class="tag slate">{_esc(grn.get('status') or 'pending').upper()}</span></div>
  <div><b>Inspection Status</b></div><div><span class="tag slate">{_esc(grn.get('inspection_status') or 'pending').upper()}</span></div>
  <div><b>Total Accepted / Rejected</b></div><div>{_money(grn.get('total_accepted') or 0)} / {_money(grn.get('total_rejected') or 0)}</div>
</div>
<div class="section-title">Items Received</div>
<table><thead><tr>
<th>#</th><th>Item</th><th class="num">Ordered</th><th class="num">Received</th><th class="num">Accepted</th>
<th class="num">Rejected</th><th>Unit</th><th>Status</th>
</tr></thead><tbody>{items_html or '<tr><td colspan=8>No items</td></tr>'}</tbody></table>
<div class="section-title">Inspection Remarks</div>
<div class="note">{_esc(grn.get('inspection_remarks') or grn.get('remarks') or '—')}</div>
<div class="signs">
  <div class="box">Received by Store</div>
  <div class="box">Inspected by QC</div>
  <div class="box">Approved by Procurement</div>
</div>
"""
    return _render(_wrap(f"Goods Receipt Note — {grn.get('grn_number') or grn.get('grn_no','')}", body))


# ─────────────────────────────────── SRN ───────────────────────────────────
def render_srn_pdf(srn: Dict[str, Any], so: Optional[Dict[str, Any]] = None,
                   vendor: Optional[Dict[str, Any]] = None) -> bytes:
    v = vendor or {}
    s = so or {}
    st = (srn.get("status") or "approved").upper()
    tag_cls = "green" if st in ("APPROVED", "ACCEPTED") else "amber"
    body = f"""
<div class="kv">
  <div><b>SRN Number</b></div><div>{_esc(srn.get('srn_number'))}</div>
  <div><b>SRN Date</b></div><div>{_esc((srn.get('created_at') or '')[:10])}</div>
  <div><b>Service Order</b></div><div>{_esc(srn.get('so_number') or s.get('so_number') or '—')}</div>
  <div><b>Vendor</b></div><div>{_esc(v.get('name') or srn.get('vendor_name') or '—')}</div>
  <div><b>Project</b></div><div>{_esc(srn.get('project_code') or s.get('project_code') or '—')}</div>
  <div><b>Service Period</b></div><div>{_esc(srn.get('service_period_from') or '—')} → {_esc(srn.get('service_period_to') or '—')}</div>
  <div><b>Status</b></div><div><span class="tag {tag_cls}">{_esc(st)}</span></div>
</div>
<div class="section-title">Certified Work</div>
<table><thead><tr>
<th>Work Completed</th><th class="num">Certified Quantity</th><th class="num">Certified Value (₹)</th>
</tr></thead><tbody><tr>
<td>{_esc(srn.get('work_completed') or '—')}</td>
<td class="num">{_money(srn.get('certified_quantity') or 0)}</td>
<td class="num">{_money(srn.get('certified_value') or 0)}</td>
</tr></tbody></table>
<div class="section-title">SO Progress</div>
<div class="note">SO Total: ₹ {_money(s.get('total_amount') or 0)} · Cumulative Received: ₹ {_money(s.get('received_value') or 0)} · SO Status: {_esc((s.get('status') or '—').replace('_',' ').title())}</div>
<div class="section-title">Notes</div>
<div class="note">{_esc(srn.get('notes') or '—')}</div>
<div class="signs">
  <div class="box">Certified by (PM / Site)</div>
  <div class="box">Vendor Acknowledgement</div>
  <div class="box">Approved by Accounts</div>
</div>
"""
    return _render(_wrap(f"Service Receipt Note — {srn.get('srn_number') or ''}", body))


# ─────────────────────────── Vendor Bills Register ──────────────────────────
def render_vendor_bills_report(rows: list, status_label: str = "All") -> bytes:
    body_rows = ""
    tot_gross = tot_out = 0.0
    for i, r in enumerate(rows, 1):
        t = r.get("totals") or {}
        gross = float(t.get("gross") or r.get("amount") or 0)
        out = float(r.get("outstanding") or 0)
        tot_gross += gross
        tot_out += out
        st = (r.get("status") or "").replace("_", " ").upper()
        body_rows += f"""<tr>
<td>{i}</td>
<td><b>{_esc(r.get('bill_no'))}</b><div class="note">{_esc(r.get('invoice_no') or '')}</div></td>
<td>{_esc((r.get('invoice_date') or '')[:10])}</td>
<td>{_esc(r.get('vendor_name'))}</td>
<td>{_esc(r.get('po_number') or '—')}<div class="note">{_esc(r.get('grn_number') or r.get('service_confirmation_no') or '')}</div></td>
<td class="num">{_money(gross)}</td>
<td class="num">{_money(out)}</td>
<td>{_esc(r.get('due_date') or '—')}</td>
<td><span class="tag slate">{_esc(st)}</span></td>
</tr>"""
    body = f"""
<div class="kv">
  <div><b>Filter</b></div><div>{_esc(status_label)}</div>
  <div><b>Bills</b></div><div>{len(rows)}</div>
  <div><b>Total Gross</b></div><div>₹ {_money(tot_gross)}</div>
  <div><b>Total Outstanding</b></div><div>₹ {_money(tot_out)}</div>
</div>
<div class="section-title">Vendor Bills Register</div>
<table><thead><tr>
<th>#</th><th>Bill / Inv</th><th>Inv Date</th><th>Vendor</th><th>PO / GRN</th>
<th class="num">Gross (₹)</th><th class="num">Outstanding (₹)</th><th>Due Date</th><th>Status</th>
</tr></thead><tbody>{body_rows or '<tr><td colspan=9>No bills</td></tr>'}</tbody></table>
"""
    return _render(_wrap("Vendor Bills Register", body))


# ─────────────────────────── Single Vendor Bill ─────────────────────────────
def render_vendor_bill_pdf(b: Dict[str, Any]) -> bytes:
    t = b.get("totals") or {}
    lines_html = ""
    for i, ln in enumerate(b.get("lines") or [], 1):
        qty = float(ln.get("quantity") or 0)
        rate = float(ln.get("rate") or 0)
        lines_html += f"""<tr><td>{i}</td><td>{_esc(ln.get('description'))}</td>
<td class="num">{_money(qty)}</td><td>{_esc(ln.get('unit') or 'Nos')}</td>
<td class="num">{_money(rate)}</td><td class="num">{_money(qty * rate)}</td></tr>"""
    wf_html = ""
    for e in b.get("workflow_log") or []:
        wf_html += f"<div class='note'>✓ <b>{_esc(e.get('stage'))}</b> — {_esc(e.get('by'))} ({_esc(e.get('role'))}) · {_esc((e.get('at') or '')[:16].replace('T', ' '))}</div>"
    for e in b.get("control_log") or []:
        wf_html += f"<div class='note'>⚙ <b>{_esc((e.get('action') or '').replace('_', ' ').upper())}</b> — {_esc(e.get('by'))} · {_esc((e.get('at') or '')[:16].replace('T', ' '))}{(' · ' + _esc(e.get('remarks'))) if e.get('remarks') else ''}</div>"
    hold_tag = '<span class="tag red">PAYMENT ON HOLD</span>' if b.get("payment_hold") else ""
    body = f"""
<div class="kv">
  <div><b>Bill No</b></div><div>{_esc(b.get('bill_no'))} {hold_tag}</div>
  <div><b>Status</b></div><div><span class="tag slate">{_esc((b.get('status') or '').replace('_', ' ').upper())}</span></div>
  <div><b>Vendor</b></div><div>{_esc(b.get('vendor_name'))}</div>
  <div><b>GSTIN / PAN</b></div><div>{_esc(b.get('vendor_gstin') or '—')} / {_esc(b.get('vendor_pan') or '—')}</div>
  <div><b>Invoice</b></div><div>{_esc(b.get('invoice_no'))} · {_esc(b.get('invoice_date'))}</div>
  <div><b>PO / GRN</b></div><div>{_esc(b.get('po_number') or '—')} / {_esc(b.get('grn_number') or b.get('service_confirmation_no') or '—')}</div>
  <div><b>Project</b></div><div>{_esc(b.get('project_code') or '—')}</div>
  <div><b>Due / Payment Date</b></div><div>{_esc(b.get('payment_release_date') or b.get('due_date') or '—')} ({b.get('due_days') or 30} days)</div>
  <div><b>TDS</b></div><div>{_esc(b.get('tds_section') or '—')} @ {b.get('tds_rate') or 0}%</div>
</div>
<div class="section-title">Bill Lines</div>
<table><thead><tr><th>#</th><th>Description</th><th class="num">Qty</th><th>Unit</th>
<th class="num">Rate (₹)</th><th class="num">Amount (₹)</th></tr></thead>
<tbody>{lines_html or '<tr><td colspan=6>No lines</td></tr>'}</tbody></table>
<div class="section-title">Totals</div>
<table><tbody>
<tr><td>Taxable</td><td class="num">{_money(t.get('taxable') or 0)}</td></tr>
<tr><td>GST ({b.get('gst_rate') or 0}%)</td><td class="num">{_money(t.get('gst') or 0)}</td></tr>
<tr><td><b>Gross</b></td><td class="num"><b>{_money(t.get('gross') or b.get('amount') or 0)}</b></td></tr>
<tr><td>TDS</td><td class="num">−{_money(t.get('tds') or 0)}</td></tr>
<tr><td>Advance Adjusted</td><td class="num">−{_money(b.get('advance_adjusted') or 0)}</td></tr>
<tr><td>Retention</td><td class="num">−{_money(b.get('retention_amount') or 0)}</td></tr>
<tr><td><b>Net Payable</b></td><td class="num"><b>{_money(t.get('net_payable') or b.get('outstanding') or 0)}</b></td></tr>
<tr><td>Outstanding</td><td class="num">{_money(b.get('outstanding') or 0)}</td></tr>
</tbody></table>
<div class="section-title">Approval & Payment Control Trail</div>
{wf_html or '<div class="note">No workflow entries.</div>'}
<div class="signs">
  <div class="box">Department</div>
  <div class="box">Accounts</div>
  <div class="box">Admin / Final</div>
</div>
"""
    return _render(_wrap(f"Vendor Bill — {b.get('bill_no') or ''}", body))


# ─────────────────────────── MATERIAL ISSUE SLIP ──────────────────────────
def render_material_issue_pdf(slip: Dict[str, Any]) -> bytes:
    items_html = ""
    for i, it in enumerate(slip.get("items") or [], 1):
        items_html += f"""<tr>
<td>{i}</td>
<td><b>{_esc(it.get('name') or it.get('item_name'))}</b><div class="note">{_esc(it.get('item_code') or '')}</div></td>
<td class="num">{_money(it.get('quantity'))}</td>
<td>{_esc(it.get('unit') or 'Nos')}</td>
<td>{_esc(it.get('purpose') or '—')}</td>
</tr>"""
    # Single-item slip support (legacy shape from /store outward endpoints)
    if not items_html and slip.get("item_id"):
        items_html = f"""<tr>
<td>1</td>
<td><b>{_esc(slip.get('item_name'))}</b><div class="note">{_esc(slip.get('item_code') or '')}</div></td>
<td class="num">{_money(slip.get('quantity'))}</td>
<td>{_esc(slip.get('unit') or 'Nos')}</td>
<td>{_esc(slip.get('purpose') or slip.get('reason') or '—')}</td>
</tr>"""
    body = f"""
<div class="kv">
  <div><b>Slip Number</b></div><div>{_esc(slip.get('txn_no') or slip.get('slip_no') or slip.get('id'))}</div>
  <div><b>Issue Date</b></div><div>{_esc(slip.get('issue_date') or slip.get('created_at','')[:10])}</div>
  <div><b>Project</b></div><div>{_esc(slip.get('project_code') or slip.get('project_id') or '—')}</div>
  <div><b>Site</b></div><div>{_esc(slip.get('site_code') or '—')}</div>
  <div><b>Issued To</b></div><div>{_esc(slip.get('issued_to') or slip.get('to') or '—')}</div>
  <div><b>Type</b></div><div><span class="tag slate">{_esc(slip.get('type') or slip.get('kind') or 'outward').upper()}</span></div>
</div>
<div class="section-title">Items Issued</div>
<table><thead><tr><th>#</th><th>Item</th><th class="num">Qty</th><th>Unit</th><th>Purpose</th></tr></thead>
<tbody>{items_html or '<tr><td colspan=5>No items</td></tr>'}</tbody></table>
<div class="signs">
  <div class="box">Issued by Store</div>
  <div class="box">Received by Site Engineer</div>
  <div class="box">Approved by Project Manager</div>
</div>
"""
    return _render(_wrap(f"Material Issue Slip — {slip.get('txn_no') or slip.get('slip_no','')}", body))
