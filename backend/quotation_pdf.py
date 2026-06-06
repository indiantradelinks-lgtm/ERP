"""Reportlab-based PDF renderer for the AI Quotation module.

Single entrypoint: `render_quotation_pdf(quote, company) -> bytes`.
Keeps the layout corporate-clean: header band, client + meta blocks,
service sections with line-item tables, totals block, conditions appendix.
"""
from io import BytesIO
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether,
)

from pdf_watermark import attach_watermark


# Brand palette
SLATE = colors.HexColor("#0f172a")
ACCENT = colors.HexColor("#2563eb")
MUTED = colors.HexColor("#64748b")
BORDER = colors.HexColor("#e2e8f0")
SOFT = colors.HexColor("#f8fafc")


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("Title2", parent=s["Heading1"], fontName="Helvetica-Bold",
                         textColor=SLATE, fontSize=18, leading=22, spaceAfter=2))
    s.add(ParagraphStyle("Eyebrow", parent=s["Normal"], fontName="Helvetica-Bold",
                         textColor=ACCENT, fontSize=8, leading=10, spaceAfter=4,
                         textTransform="uppercase"))
    s.add(ParagraphStyle("Small", parent=s["Normal"], fontName="Helvetica",
                         textColor=MUTED, fontSize=8.5, leading=11))
    s.add(ParagraphStyle("Body", parent=s["Normal"], fontName="Helvetica",
                         textColor=SLATE, fontSize=9.5, leading=13))
    s.add(ParagraphStyle("BodyBold", parent=s["Normal"], fontName="Helvetica-Bold",
                         textColor=SLATE, fontSize=9.5, leading=13))
    s.add(ParagraphStyle("SectionH", parent=s["Heading2"], fontName="Helvetica-Bold",
                         textColor=SLATE, fontSize=11, leading=14, spaceBefore=6, spaceAfter=4))
    s.add(ParagraphStyle("CondTxt", parent=s["Normal"], fontName="Helvetica",
                         textColor=SLATE, fontSize=9, leading=12.5, leftIndent=12))
    return s


def _fmt_inr(amount) -> str:
    try:
        a = float(amount or 0)
    except (TypeError, ValueError):
        a = 0.0
    return "Rs. " + f"{a:,.2f}"


def _header_table(quote: Dict, company: Dict, styles) -> Table:
    from reportlab.platypus import Image as RLImage
    import os
    logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "assets", "itl-logo.jpg")
    if not os.path.exists(logo_path):
        logo_path = "/app/backend/assets/itl-logo.jpg"
    logo_cell = ""
    try:
        if os.path.exists(logo_path):
            logo_cell = RLImage(logo_path, width=24 * mm, height=24 * mm)
    except Exception:
        logo_cell = ""

    company_block = [
        Paragraph(f"<b>{(company.get('name') or 'INDIAN TRADE LINKS').upper()}</b>", styles["Title2"]),
        Paragraph("Industrial Services Pvt. Ltd.", styles["Small"]),
        Paragraph(company.get("address") or "—", styles["Small"]),
        Paragraph(
            f"GSTIN: <b>{company.get('gstin') or '—'}</b>  |  PAN: <b>{company.get('pan') or '—'}</b>",
            styles["Small"]),
        Paragraph(
            f"State: <b>{company.get('state') or '—'}</b>  |  Phone: {company.get('phone') or '—'}",
            styles["Small"]),
        Paragraph(f"Email: {company.get('email') or '—'} | Web: {company.get('website') or '—'}",
                  styles["Small"]),
    ]
    meta_block = [
        Paragraph("QUOTATION", styles["Eyebrow"]),
        Paragraph(f"<b>{quote.get('quote_number') or '—'}</b>", styles["Title2"]),
        Paragraph(f"Date: <b>{quote.get('date') or '—'}</b>", styles["Small"]),
        Paragraph(f"Valid Until: <b>{quote.get('valid_until') or '—'}</b>", styles["Small"]),
        Paragraph(
            f"Revision: <b>R{quote.get('revision_no') or 0}</b>"
            + (f"  |  Ref Enq: <b>{quote['enquiry_no']}</b>" if quote.get("enquiry_no") else ""),
            styles["Small"]),
    ]
    t = Table([[logo_cell, company_block, meta_block]], colWidths=[28 * mm, 82 * mm, 75 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 6),
    ]))
    return t


def _client_meta_table(quote: Dict, styles) -> Table:
    client_block = [
        Paragraph("CLIENT", styles["Eyebrow"]),
        Paragraph(f"<b>{quote.get('client') or '—'}</b>", styles["BodyBold"]),
        Paragraph(quote.get("site_name") or "", styles["Small"]),
        Paragraph(f"Site / State: {quote.get('client_state') or '—'}", styles["Small"]),
        Paragraph(f"Attn: {quote.get('contact_person') or '—'}", styles["Small"]),
        Paragraph(f"Email: {quote.get('contact_email') or '—'}", styles["Small"]),
    ]
    meta_block = [
        Paragraph("SCOPE / PROJECT", styles["Eyebrow"]),
        Paragraph(quote.get("project") or quote.get("scope_of_work") or "—", styles["Body"]),
        Paragraph(
            "Services: <b>" + ", ".join(quote.get("service_categories") or []) + "</b>",
            styles["Small"]),
        Paragraph(
            "Tax Mode: <b>"
            + ("CGST + SGST (intra-state)" if quote.get("tax_mode") == "intra" else "IGST (inter-state)")
            + "</b>",
            styles["Small"]),
    ]
    t = Table([[client_block, meta_block]], colWidths=[92 * mm, 92 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, BORDER),
    ]))
    return t


def _items_table(section: Dict, styles, tax_mode: str) -> Table:
    items = section.get("items") or []
    rows = [
        ["SN", "Description", "HSN/SAC", "Qty", "Unit", "Rate",
         "Discount %", "Taxable", "GST %", "Total"]
    ]
    for i, it in enumerate(items, start=1):
        desc = (it.get("description") or "") + (
            f"<br/><font size=7 color='#64748b'>{it['specification']}</font>"
            if it.get("specification") else ""
        )
        rows.append([
            str(i),
            Paragraph(desc, styles["Small"]),
            it.get("hsn_sac") or "—",
            f"{float(it.get('quantity') or 0):,.2f}",
            it.get("unit") or "—",
            _fmt_inr(it.get("rate")),
            f"{float(it.get('discount_pct') or 0):.1f}",
            _fmt_inr(it.get("taxable")),
            f"{float(it.get('gst_pct') or 0):.1f}",
            _fmt_inr(it.get("total")),
        ])
    # Subtotal row
    rows.append(["", Paragraph("<b>Section Subtotal</b>", styles["BodyBold"]), "", "", "", "", "",
                 _fmt_inr(section.get("subtotal_taxable")), "", _fmt_inr(section.get("subtotal_total"))])
    t = Table(
        rows,
        colWidths=[8 * mm, 60 * mm, 16 * mm, 14 * mm, 12 * mm, 18 * mm, 14 * mm, 18 * mm, 12 * mm, 22 * mm],
        repeatRows=1,
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SLATE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, SOFT]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e0e7ef")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _totals_block(totals: Dict, tax_mode: str, styles) -> Table:
    rows = [
        ["Basic Amount", _fmt_inr(totals.get("basic"))],
        ["Less: Discount", _fmt_inr(totals.get("discount"))],
        ["Taxable Value", _fmt_inr(totals.get("taxable"))],
    ]
    if tax_mode == "intra":
        rows.append(["CGST", _fmt_inr(totals.get("cgst"))])
        rows.append(["SGST", _fmt_inr(totals.get("sgst"))])
    else:
        rows.append(["IGST", _fmt_inr(totals.get("igst"))])
    rows.append(["Round Off", _fmt_inr(totals.get("round_off"))])
    rows.append(["GRAND TOTAL (INR)", _fmt_inr(totals.get("grand_total"))])
    t = Table(rows, colWidths=[55 * mm, 35 * mm])
    t.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEABOVE", (0, -1), (-1, -1), 1, SLATE),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), SLATE),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
    ]))
    return t


def _condition_block(title: str, items: List[str], styles) -> List:
    if not items:
        return []
    elems = [Paragraph(title, styles["Eyebrow"]), Spacer(1, 2)]
    for i, txt in enumerate(items, start=1):
        elems.append(Paragraph(f"{i}.  {txt}", styles["CondTxt"]))
    elems.append(Spacer(1, 6))
    return elems


def render_quotation_pdf(quote: Dict, company: Dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=quote.get("quote_number") or "Quotation",
        author=company.get("name") or "INDIAN TRADE LINKS",
    )
    attach_watermark(doc)
    styles = _styles()
    story = []

    story.append(_header_table(quote, company, styles))
    story.append(Spacer(1, 8))
    story.append(_client_meta_table(quote, styles))
    story.append(Spacer(1, 8))

    tax_mode = quote.get("tax_mode") or "intra"
    for sec in quote.get("sections") or []:
        title = sec.get("title") or f"{sec.get('service', '').replace('_', ' ').title()} — {sec.get('basis', '').replace('_', ' ').title()}"
        story.append(Paragraph(title.upper(), styles["SectionH"]))
        story.append(_items_table(sec, styles, tax_mode))
        story.append(Spacer(1, 6))

    # Totals — right-aligned
    totals_wrap = Table([["", _totals_block(quote.get("totals") or {}, tax_mode, styles)]],
                        colWidths=[95 * mm, 90 * mm])
    totals_wrap.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(totals_wrap)
    story.append(Spacer(1, 10))

    # Conditions appendix
    story.extend(_condition_block("INCLUSIONS", quote.get("inclusions") or [], styles))
    story.extend(_condition_block("EXCLUSIONS", quote.get("exclusions") or [], styles))
    story.extend(_condition_block("TECHNICAL CONDITIONS", quote.get("technical_conditions") or [], styles))
    story.extend(_condition_block("COMMERCIAL CONDITIONS", quote.get("commercial_conditions") or [], styles))

    # Commercial summary block (payment terms, validity, warranty)
    summary_rows = [
        ["Payment Terms", quote.get("payment_terms") or "—"],
        ["Validity (days)", str(quote.get("validity_days") or "—")],
        ["Advance %", f"{quote.get('advance_pct') or 0} %"],
        ["Retention %", f"{quote.get('retention_pct') or 0} %"],
        ["TDS %", f"{quote.get('tds_pct') or 0} %"],
        ["Delivery / Timeline", quote.get("delivery_timeline") or "—"],
        ["Warranty", quote.get("warranty") or "—"],
    ]
    summary = Table(summary_rows, colWidths=[40 * mm, 145 * mm])
    summary.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (0, -1), SOFT),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
    ]))
    story.append(Spacer(1, 4))
    story.append(Paragraph("COMMERCIAL SUMMARY", styles["Eyebrow"]))
    story.append(summary)

    story.append(Spacer(1, 16))
    sig = Table([[
        Paragraph(
            f"For <b>{(company.get('name') or 'INDIAN TRADE LINKS').upper()}</b><br/><br/><br/>"
            f"<b>{company.get('authorized_signatory') or '—'}</b><br/>"
            f"<font color='#64748b'>{company.get('designation') or 'Authorised Signatory'}</font>",
            styles["Body"]),
        Paragraph(
            "<b>Client Acceptance</b><br/><br/><br/>Name &amp; Signature<br/>"
            "<font color='#64748b'>Seal &amp; Date</font>", styles["Body"]),
    ]], colWidths=[92 * mm, 92 * mm])
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 0.5, BORDER),
                             ("TOPPADDING", (0, 0), (-1, -1), 12)]))
    story.append(sig)

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
