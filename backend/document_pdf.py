"""Reportlab one-page PDF generators for PO / RFQ / RA Bill.

Used by email_actions_router to auto-attach a clean PDF when sending the
record by email. Quotations have their own richer PDF endpoint; HR letters
have a DOCX render. These three (PO/RFQ/RA Bill) didn't have a per-record
PDF until now — this module fills the gap with a tight, professional layout.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from pdf_watermark import attach_watermark

BRAND_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "itl-logo.jpg")
BRAND_NAME = "INDIAN TRADE LINKS"
BRAND_SUB = ""


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=20, leading=24, textColor=colors.HexColor("#0f172a"), spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#1e293b")),
        "meta": ParagraphStyle("meta", parent=base["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#475569")),
        "label": ParagraphStyle("label", parent=base["Normal"], fontSize=8, leading=11, textColor=colors.HexColor("#64748b"), fontName="Helvetica-Bold"),
        "value": ParagraphStyle("value", parent=base["Normal"], fontSize=10, leading=13, textColor=colors.HexColor("#0f172a")),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8, leading=10, textColor=colors.HexColor("#64748b")),
    }


def _header(s):
    logo = None
    try:
        if os.path.exists(BRAND_LOGO_PATH):
            logo = RLImage(BRAND_LOGO_PATH, width=24 * mm, height=8.1 * mm)
    except Exception:
        logo = None
    brand = [
        Paragraph(f"<b>{BRAND_NAME}</b>", s["h2"]),
    ]
    cells = [[logo or "", brand]] if logo else [["", brand]]
    t = Table(cells, colWidths=[28 * mm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#2563eb")),
    ]))
    return t


def _kv_grid(rows: List[List[Any]], s) -> Table:
    """rows = [[label, value], ...]"""
    data = [[Paragraph(str(lbl).upper(), s["label"]), Paragraph(str(val) if val is not None else "—", s["value"])] for lbl, val in rows]
    t = Table(data, colWidths=[35 * mm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _items_table(items: List[Dict[str, Any]], columns: List[Dict[str, str]], s) -> Table:
    header = [Paragraph(f"<b>{c['label']}</b>", s["label"]) for c in columns]
    data: List[List[Any]] = [header]
    for it in items:
        row = []
        for c in columns:
            v = it.get(c["key"], "")
            if isinstance(v, (int, float)) and c.get("kind") == "money":
                v = f"₹ {v:,.2f}"
            elif isinstance(v, float):
                v = f"{v:g}"
            row.append(Paragraph(str(v) if v != "" else "—", s["body"]))
        data.append(row)
    t = Table(data, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _footer(s):
    return Paragraph(
        f"Generated {datetime.utcnow().strftime('%d %b %Y · %H:%M UTC')} · This is a computer-generated document.",
        s["small"],
    )


def _build_pdf(elements: List[Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)
    attach_watermark(doc, width_mm=120.0)
    doc.build(elements)
    return buf.getvalue()


# ────────────────────────────────────────────────────────────────────────────
# Purchase Order
# ────────────────────────────────────────────────────────────────────────────
def purchase_order_pdf(po: Dict[str, Any], vendor: Dict[str, Any] | None) -> bytes:
    s = _styles()
    elements: List[Any] = []
    elements.append(_header(s))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"PURCHASE ORDER · {po.get('po_number', po.get('id', '—'))}", s["title"]))
    elements.append(Spacer(1, 6))

    meta_rows = [
        ["PO Number", po.get("po_number") or "—"],
        ["Date", po.get("created_at", "—")[:10] if po.get("created_at") else "—"],
        ["Project", po.get("project") or "—"],
        ["Site", po.get("site") or "—"],
        ["Department", po.get("department") or "—"],
        ["RFQ Ref", po.get("rfq_number") or "—"],
        ["PR Ref", po.get("pr_number") or "—"],
        ["Status", (po.get("status") or "—").upper()],
    ]
    elements.append(_kv_grid(meta_rows, s))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph("<b>Vendor</b>", s["h2"]))
    vname = (vendor or {}).get("name") or po.get("vendor") or "—"
    vrows = [
        ["Vendor", vname],
        ["Code", (vendor or {}).get("code") or "—"],
        ["Contact", (vendor or {}).get("contact") or "—"],
        ["Phone", (vendor or {}).get("phone") or "—"],
        ["Email", (vendor or {}).get("email") or "—"],
        ["GST", (vendor or {}).get("gst") or "—"],
    ]
    elements.append(_kv_grid(vrows, s))
    elements.append(Spacer(1, 8))

    items = po.get("items") or []
    if items and isinstance(items, list):
        cols = [
            {"key": "description", "label": "Description"},
            {"key": "qty", "label": "Qty"},
            {"key": "unit", "label": "Unit"},
            {"key": "rate", "label": "Rate", "kind": "money"},
            {"key": "amount", "label": "Amount", "kind": "money"},
        ]
        norm = []
        for it in items:
            if isinstance(it, dict):
                amount = it.get("amount") or ((it.get("qty") or 1) * (it.get("rate") or 0))
                norm.append({**it, "amount": amount})
            else:
                norm.append({"description": str(it)})
        elements.append(_items_table(norm, cols, s))
        elements.append(Spacer(1, 4))

    elements.append(Paragraph(f"<b>Total: ₹ {float(po.get('amount') or 0):,.2f}</b>", s["h2"]))
    elements.append(Spacer(1, 8))
    if po.get("delivery_days"):
        elements.append(Paragraph(f"<b>Delivery:</b> within {po.get('delivery_days')} days", s["body"]))
    if po.get("payment_terms"):
        elements.append(Paragraph(f"<b>Payment terms:</b> {po.get('payment_terms')}", s["body"]))
    elements.append(Spacer(1, 14))
    elements.append(_footer(s))
    return _build_pdf(elements)


# ────────────────────────────────────────────────────────────────────────────
# RFQ
# ────────────────────────────────────────────────────────────────────────────
def rfq_pdf(rfq: Dict[str, Any], vendor: Dict[str, Any] | None = None) -> bytes:
    s = _styles()
    elements: List[Any] = []
    elements.append(_header(s))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"REQUEST FOR QUOTATION · {rfq.get('rfq_number', rfq.get('id', '—'))}", s["title"]))
    elements.append(Spacer(1, 6))

    elements.append(_kv_grid([
        ["RFQ Number", rfq.get("rfq_number") or "—"],
        ["Issued", rfq.get("created_at", "—")[:10] if rfq.get("created_at") else "—"],
        ["Closing date", rfq.get("closing_date") or rfq.get("submission_deadline") or "—"],
        ["Project", rfq.get("project") or "—"],
        ["Department", rfq.get("department") or "—"],
        ["PR Ref", rfq.get("pr_number") or "—"],
    ], s))
    elements.append(Spacer(1, 6))

    if vendor:
        elements.append(Paragraph("<b>To Vendor</b>", s["h2"]))
        elements.append(_kv_grid([
            ["Vendor", vendor.get("name") or "—"],
            ["Contact", vendor.get("contact") or "—"],
            ["Email", vendor.get("email") or "—"],
            ["Phone", vendor.get("phone") or "—"],
        ], s))
        elements.append(Spacer(1, 6))

    items = rfq.get("items") or []
    if items:
        cols = [
            {"key": "description", "label": "Description / Specification"},
            {"key": "qty", "label": "Qty"},
            {"key": "unit", "label": "Unit"},
        ]
        elements.append(_items_table(items, cols, s))
        elements.append(Spacer(1, 6))

    if rfq.get("terms"):
        elements.append(Paragraph(f"<b>Terms:</b> {rfq.get('terms')}", s["body"]))

    elements.append(Spacer(1, 14))
    elements.append(_footer(s))
    return _build_pdf(elements)


# ────────────────────────────────────────────────────────────────────────────
# RA Bill
# ────────────────────────────────────────────────────────────────────────────
def ra_bill_pdf(bill: Dict[str, Any], client: Dict[str, Any] | None = None) -> bytes:
    s = _styles()
    elements: List[Any] = []
    elements.append(_header(s))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"RUNNING ACCOUNT BILL · {bill.get('bill_number', bill.get('id', '—'))}", s["title"]))
    elements.append(Spacer(1, 6))

    elements.append(_kv_grid([
        ["Bill Number", bill.get("bill_number") or "—"],
        ["Bill Type", (bill.get("bill_type") or "—").upper()],
        ["Bill Date", bill.get("bill_date") or "—"],
        ["Project", bill.get("project_code") or "—"],
        ["Site", bill.get("site_name") or "—"],
        ["PO Reference", bill.get("po_number") or "—"],
        ["Status", (bill.get("status") or "—").upper()],
    ], s))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph("<b>Bill To</b>", s["h2"]))
    elements.append(_kv_grid([
        ["Client", (client or {}).get("name") or bill.get("client_name") or "—"],
        ["Address", (client or {}).get("address") or "—"],
        ["GST", (client or {}).get("gst") or "—"],
        ["Contact", (client or {}).get("contact") or "—"],
    ], s))
    elements.append(Spacer(1, 6))

    items = bill.get("items") or []
    if items:
        cols = [
            {"key": "description", "label": "Description"},
            {"key": "qty", "label": "Qty"},
            {"key": "unit", "label": "Unit"},
            {"key": "rate", "label": "Rate", "kind": "money"},
            {"key": "amount", "label": "Amount", "kind": "money"},
        ]
        elements.append(_items_table(items, cols, s))
        elements.append(Spacer(1, 6))

    money_rows = [
        ["Subtotal", f"₹ {float(bill.get('subtotal') or 0):,.2f}"],
        [f"GST @ {bill.get('gst_pct', 18)}%", f"₹ {float(bill.get('gst_amount') or 0):,.2f}"],
        ["Gross", f"₹ {float(bill.get('gross_value') or 0):,.2f}"],
        [f"Retention @ {bill.get('retention_pct', 0)}%", f"₹ {float(bill.get('retention_amount') or 0):,.2f}"],
        [f"TDS @ {bill.get('tds_pct', 0)}%", f"₹ {float(bill.get('tds_amount') or 0):,.2f}"],
        ["Other Deductions", f"₹ {float(bill.get('other_deductions_total') or 0):,.2f}"],
        ["Advance Recovery", f"₹ {float(bill.get('advance_recovery') or 0):,.2f}"],
    ]
    elements.append(_kv_grid(money_rows, s))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"<b>Net Payable: ₹ {float(bill.get('net_payable') or 0):,.2f}</b>", s["h2"]))
    elements.append(Spacer(1, 14))
    elements.append(_footer(s))
    return _build_pdf(elements)


# ────────────────────────────────────────────────────────────────────────────
# Voucher / Journal Entry (Iter 110)
# ────────────────────────────────────────────────────────────────────────────
def voucher_pdf(voucher: Dict[str, Any]) -> bytes:
    """Branded one-page PDF for any JE / voucher (Contra · Payment · Receipt ·
    Journal · Sales · Purchase · Debit Note · Credit Note · Advance · Salary).
    Accepts the normalised db.journal_entries shape with lines[] (preferred)
    or a single-amount legacy JE (renders as a single-line voucher)."""
    s = _styles()
    elements: List[Any] = []
    elements.append(_header(s))

    voucher_type = (voucher.get("voucher_type") or "JV").upper()
    label_map = {
        "PV": "Payment Voucher", "RV": "Receipt Voucher",
        "CV": "Contra Voucher",  "JV": "Journal Voucher",
        "SV": "Sales Voucher",   "BV": "Purchase / Bill Voucher",
        "DN": "Debit Note",      "CN": "Credit Note",
        "AV": "Advance Voucher", "SAL": "Salary Voucher",
        "REV": "Reversal Voucher",
    }
    title = label_map.get(voucher_type, f"Voucher · {voucher_type}")
    elements.append(Paragraph(title, s["title"]))
    elements.append(Spacer(1, 6))

    elements.append(_kv_grid([
        ["Voucher #", voucher.get("voucher_number") or voucher.get("je_number") or "—"],
        ["Type", f"{voucher_type} — {label_map.get(voucher_type, '')}"],
        ["Date", voucher.get("date") or "—"],
        ["Source", f"{voucher.get('source_module') or 'manual'} · {voucher.get('source_event') or '—'}"],
        ["Project", voucher.get("project_id") or "—"],
        ["Posted by", voucher.get("posted_by") or voucher.get("created_by") or "—"],
        ["Status", (voucher.get("status") or "posted").upper()],
        ["Approved by", voucher.get("approved_by") or "—"],
    ], s))
    elements.append(Spacer(1, 8))

    # Narration
    narration = voucher.get("narration") or voucher.get("reason") or ""
    if narration:
        elements.append(Paragraph(f"<b>Narration:</b> {narration}", s["value"]))
        elements.append(Spacer(1, 6))

    # Lines (multi-line double entry) — preferred
    lines = voucher.get("lines") or []
    if lines:
        rows = [["Account Code", "Account Name", "Debit (₹)", "Credit (₹)", "Cost Centre / Project"]]
        total_dr = 0.0
        total_cr = 0.0
        for ln in lines:
            dr = float(ln.get("debit") or 0)
            cr = float(ln.get("credit") or 0)
            total_dr += dr
            total_cr += cr
            cc_project = " · ".join(filter(None, [ln.get("cost_centre"), ln.get("project_id"), ln.get("department")]))
            rows.append([
                str(ln.get("account_code") or "—"),
                str(ln.get("account_name") or "—"),
                f"{dr:,.2f}" if dr else "",
                f"{cr:,.2f}" if cr else "",
                cc_project or "—",
            ])
        rows.append(["", "Total", f"{total_dr:,.2f}", f"{total_cr:,.2f}", ""])
        tbl = Table(rows, hAlign="LEFT", repeatRows=1,
                    colWidths=[22 * mm, 60 * mm, 26 * mm, 26 * mm, 40 * mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (2, 1), (3, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#0f172a")),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#0f172a")),
            ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(tbl)
    else:
        # Legacy single-amount JE
        elements.append(_kv_grid([
            ["Account", voucher.get("account") or "—"],
            ["Type", (voucher.get("type") or "").upper()],
            ["Amount", f"₹ {float(voucher.get('amount') or 0):,.2f}"],
        ], s))

    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        f"<b>Authorised Signature:</b> {voucher.get('approved_by') or voucher.get('posted_by') or '_______________________'}",
        s["value"]
    ))
    elements.append(Spacer(1, 14))
    elements.append(_footer(s))
    return _build_pdf(elements)


# ────────────────────────────────────────────────────────────────────────────
# Debit / Credit Note (Iter 110)
# ────────────────────────────────────────────────────────────────────────────
def dn_cn_pdf(note: Dict[str, Any], party: Dict[str, Any] | None = None) -> bytes:
    s = _styles()
    elements: List[Any] = []
    elements.append(_header(s))

    kind = (note.get("kind") or "credit_note")  # "credit_note" | "debit_note"
    title = "Credit Note" if kind == "credit_note" else "Debit Note"
    elements.append(Paragraph(title, s["title"]))
    elements.append(Spacer(1, 6))

    elements.append(_kv_grid([
        ["Note #", note.get("note_number") or "—"],
        ["Date", note.get("date") or "—"],
        ["Against", note.get("against_type") or "—"],
        ["Against #", note.get("against_number") or "—"],
        ["Project", note.get("project_id") or note.get("project_code") or "—"],
        ["Reason code", note.get("reason_code") or "—"],
        ["Status", (note.get("status") or "draft").upper()],
        ["Created by", note.get("created_by") or "—"],
    ], s))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph(f"<b>{'Client' if kind == 'credit_note' else 'Vendor'}</b>", s["h2"]))
    elements.append(_kv_grid([
        ["Name", (party or {}).get("name") or note.get("party_name") or "—"],
        ["GST", (party or {}).get("gst") or (party or {}).get("gstin") or "—"],
        ["Address", (party or {}).get("address") or "—"],
    ], s))
    elements.append(Spacer(1, 6))

    if note.get("reason"):
        elements.append(Paragraph(f"<b>Reason:</b> {note.get('reason')}", s["value"]))
        elements.append(Spacer(1, 6))

    money_rows = [
        ["Taxable value", f"₹ {float(note.get('taxable_value') or 0):,.2f}"],
        [f"GST @ {note.get('gst_percent', 18)}%", f"₹ {float(note.get('gst_amount') or 0):,.2f}"],
    ]
    if (note.get("tds_amount") or 0) > 0:
        money_rows.append([f"TDS @ {note.get('tds_percent', 0)}%", f"₹ {float(note.get('tds_amount') or 0):,.2f}"])
    money_rows.append(["Total", f"₹ {float(note.get('total_amount') or 0):,.2f}"])
    elements.append(_kv_grid(money_rows, s))
    elements.append(Spacer(1, 12))
    elements.append(_footer(s))
    return _build_pdf(elements)
