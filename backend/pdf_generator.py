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


BRAND = "INDIAN TRADE LINKS · Industrial Services Pvt. Ltd."
FOOTER_NOTE = "System-generated · Not valid without approval signatures"

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
          padding-top: 4px; display: flex; justify-content: space-between; }
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
<div class="title-row">
  <div>
    <div class="brand">{_esc(BRAND)}</div>
    <h1>{_esc(title)}</h1>
  </div>
  <div class="meta">Generated: <b>{_now_str()}</b></div>
</div>
{body_html}
<div class="footer"><div>{_esc(FOOTER_NOTE)}</div><div>{_esc(BRAND)}</div></div>
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
    for i, it in enumerate(po.get("items") or [], 1):
        qty = float(it.get("quantity") or 0)
        rate = float(it.get("rate") or 0)
        amt = float(it.get("amount") or it.get("total") or (qty * rate))
        sub_total += amt
        items_html += f"""<tr>
<td>{i}</td>
<td><b>{_esc(it.get('name'))}</b><div class="note">HSN/SAC: {_esc(it.get('hsn_sac') or '—')}</div></td>
<td class="num">{_money(qty)}</td>
<td>{_esc(it.get('unit') or 'Nos')}</td>
<td class="num">{_money(rate)}</td>
<td class="num">{_money(amt)}</td>
</tr>"""
    gst_pct = float(po.get("gst_pct") or 18)
    gst_amt = sub_total * gst_pct / 100
    grand = sub_total + gst_amt
    v = vendor or {}
    addr_lines: List[str] = []
    for a in (v.get("addresses") or [])[:1]:
        addr_lines += [a.get("line1"), a.get("line2"), f"{a.get('city','')} {a.get('pin','')}", a.get("state")]
    addr_html = "<br/>".join([_esc(x) for x in addr_lines if x]) or _esc(v.get("address") or "—")
    body = f"""
<div class="kv">
  <div><b>PO Number</b></div><div>{_esc(po.get('po_number') or po.get('po_no'))}</div>
  <div><b>PO Date</b></div><div>{_esc(po.get('po_date') or po.get('created_at','')[:10])}</div>
  <div><b>PR Reference</b></div><div>{_esc(po.get('pr_number') or '—')}</div>
  <div><b>RFQ Reference</b></div><div>{_esc(po.get('rfq_number') or '—')}</div>
  <div><b>Project</b></div><div>{_esc(po.get('project_code') or '—')}</div>
  <div><b>Delivery Date</b></div><div>{_esc(po.get('delivery_date') or '—')}</div>
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
<table><thead><tr><th>#</th><th>Item</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead>
<tbody>{items_html or '<tr><td colspan=6>No items</td></tr>'}</tbody></table>
<table class="totals">
<tr><td>Sub-total</td><td class="num">₹ {_money(sub_total)}</td></tr>
<tr><td>GST @ {gst_pct:.1f}%</td><td class="num">₹ {_money(gst_amt)}</td></tr>
<tr class="grand"><td>Grand Total</td><td class="num">₹ {_money(grand)}</td></tr>
</table>
<div class="section-title" style="clear:both;">Terms & Conditions</div>
<div class="note">{_esc(po.get('terms') or '1. Goods to be delivered as per delivery schedule.  2. Payment 30 days after GRN acceptance.  3. Quality as per agreed spec — defects to be replaced free of cost.')}</div>
<div class="signs">
  <div class="box">For {_esc(BRAND)}</div>
  <div class="box">Vendor Acknowledgement</div>
</div>
"""
    return _render(_wrap(f"Purchase Order — {po.get('po_number') or po.get('po_no','')}", body))


# ─────────────────────────────────── GRN ───────────────────────────────────
def render_grn_pdf(grn: Dict[str, Any], po: Optional[Dict[str, Any]] = None,
                    vendor: Optional[Dict[str, Any]] = None) -> bytes:
    items_html = ""
    for i, it in enumerate(grn.get("items") or [], 1):
        rec = float(it.get("received") or it.get("quantity") or 0)
        acc = float(it.get("accepted") or 0)
        rej = float(it.get("rejected") or 0)
        tag = '<span class="tag green">ACCEPTED</span>' if rej == 0 else (
              '<span class="tag amber">PARTIAL</span>' if acc > 0 else '<span class="tag red">REJECTED</span>')
        items_html += f"""<tr>
<td>{i}</td>
<td><b>{_esc(it.get('name'))}</b><div class="note">{_esc(it.get('description') or '')}</div></td>
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
  <div><b>Vehicle / Challan</b></div><div>{_esc(grn.get('vehicle_no') or '—')} · {_esc(grn.get('challan_no') or '—')}</div>
  <div><b>Inspection Status</b></div><div><span class="tag slate">{_esc(grn.get('inspection_status') or 'pending').upper()}</span></div>
</div>
<div class="section-title">Items Received</div>
<table><thead><tr>
<th>#</th><th>Item</th><th class="num">Received</th><th class="num">Accepted</th>
<th class="num">Rejected</th><th>Unit</th><th>Status</th>
</tr></thead><tbody>{items_html or '<tr><td colspan=7>No items</td></tr>'}</tbody></table>
<div class="section-title">Inspection Remarks</div>
<div class="note">{_esc(grn.get('inspection_remarks') or grn.get('remarks') or '—')}</div>
<div class="signs">
  <div class="box">Received by Store</div>
  <div class="box">Inspected by QC</div>
  <div class="box">Approved by Procurement</div>
</div>
"""
    return _render(_wrap(f"Goods Receipt Note — {grn.get('grn_number') or grn.get('grn_no','')}", body))


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
