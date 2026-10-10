"""Payment Verification Report — branded Excel + PDF (Accounts · Payment Processing).

Date-wise listing of every payment verified by Accounts, with beneficiary / bank
details, purpose, amounts and an editable Remarks column for management review.
"""
import io
import os
from typing import Any, Dict, List

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import fmt_ist
from exports import BRAND_LOGO_PATH, BRAND_NAME
from pdf_watermark import attach_watermark

COLS = [
    ("s_no", "S. No.", 8, 12),
    ("request_no", "Req No.", 26, 18),
    ("beneficiary_name", "Beneficiary Name", 54, 34),
    ("bank_details", "Bank A/c · IFSC", 44, 26),
    ("purpose", "Payment Purpose", 46, 30),
    ("project", "Project", 32, 20),
    ("verified_amount", "Verified Amt", 22, 14),
    ("tds_amount", "TDS", 16, 10),
    ("net_amount", "Net Amt", 22, 14),
    ("verified_on", "Verification Date", 30, 20),
    ("verified_by", "Verified By", 28, 18),
    ("remarks", "Remarks", 44, 28),
]
NUM_KEYS = {"verified_amount", "tds_amount", "net_amount"}


def _money(v) -> str:
    try:
        return f"{float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def report_xlsx(rows: List[Dict[str, Any]], title: str, subtitle: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Payment Report"
    ncol = len(COLS)
    last = get_column_letter(ncol)

    ws.merge_cells(f"A1:{last}2")
    hdr = ws["A1"]
    hdr.value = f"{BRAND_NAME}\n{title}"
    hdr.font = Font(bold=True, size=14, color="FFFFFF")
    hdr.fill = PatternFill("solid", fgColor="0F172A")
    hdr.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 22
    try:
        if os.path.exists(BRAND_LOGO_PATH):
            img = XLImage(BRAND_LOGO_PATH)
            img.height, img.width = 38, 112
            ws.add_image(img, "A1")
    except Exception:
        pass

    ws.merge_cells(f"A3:{last}3")
    sub = ws["A3"]
    sub.value = f"{subtitle} · {len(rows)} payment(s) · Generated {fmt_ist(fmt='%d-%m-%Y %I:%M %p IST')}"
    sub.font = Font(size=9, color="334155")
    sub.alignment = Alignment(horizontal="center")

    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for i, (_, label, w, _p) in enumerate(COLS, start=1):
        c = ws.cell(row=5, column=i, value=label)
        c.font = Font(bold=True, size=9, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1D4ED8")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
        ws.column_dimensions[get_column_letter(i)].width = w / 2.2
    ws.row_dimensions[5].height = 26

    r = 6
    for row in rows:
        for i, (key, _l, _w, _p) in enumerate(COLS, start=1):
            val = row.get(key)
            if key in NUM_KEYS:
                c = ws.cell(row=r, column=i, value=float(val or 0))
                c.number_format = "#,##0.00"
                c.alignment = Alignment(horizontal="right")
            else:
                c = ws.cell(row=r, column=i, value="" if val is None else str(val))
                c.alignment = Alignment(vertical="top", wrap_text=key in ("beneficiary_name", "purpose", "remarks"))
            c.font = Font(size=9)
            c.border = border
        r += 1

    tot_col = {k: sum(float(x.get(k) or 0) for x in rows) for k in NUM_KEYS}
    ws.cell(row=r, column=1, value="TOTAL").font = Font(bold=True, size=9)
    for i, (key, _l, _w, _p) in enumerate(COLS, start=1):
        c = ws.cell(row=r, column=i)
        c.fill = PatternFill("solid", fgColor="E2E8F0")
        c.border = border
        if key in NUM_KEYS:
            c.value = tot_col[key]
            c.number_format = "#,##0.00"
            c.font = Font(bold=True, size=9)
            c.alignment = Alignment(horizontal="right")

    ws.cell(row=r + 3, column=2, value="Prepared By (Accounts)").font = Font(size=9, bold=True)
    ws.cell(row=r + 3, column=5, value="Verified By (Manager — Accounts)").font = Font(size=9, bold=True)
    ws.cell(row=r + 3, column=9, value="Approved By (Management)").font = Font(size=9, bold=True)
    ws.freeze_panes = "A6"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def report_pdf(rows: List[Dict[str, Any]], title: str, subtitle: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=12 * mm, title=title)
    attach_watermark(doc, width_mm=180.0)
    styles = getSampleStyleSheet()
    t_style = ParagraphStyle("t", parent=styles["Heading1"], fontSize=14, spaceAfter=2,
                             textColor=colors.HexColor("#0f172a"))
    s_style = ParagraphStyle("s", parent=styles["Normal"], fontSize=8.5,
                             textColor=colors.HexColor("#475569"))
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7, leading=8.6)
    cell_r = ParagraphStyle("cr", parent=cell, alignment=2)
    head = ParagraphStyle("h", parent=styles["Normal"], fontSize=7, leading=8.6,
                          textColor=colors.white, fontName="Helvetica-Bold")

    logo = ""
    try:
        if os.path.exists(BRAND_LOGO_PATH):
            logo = RLImage(BRAND_LOGO_PATH, width=33 * mm, height=11.1 * mm)
    except Exception:
        logo = ""
    band = Table([[logo, [Paragraph(f"<b>{BRAND_NAME}</b>", t_style),
                          Paragraph(title, s_style),
                          Paragraph(f"{subtitle} · {len(rows)} payment(s) · Generated "
                                    f"{fmt_ist(fmt='%d-%m-%Y %I:%M %p IST')}", s_style)]]],
                 colWidths=[37 * mm, 240 * mm])
    band.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#0f172a")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [band, Spacer(1, 4 * mm)]

    data = [[Paragraph(label, head) for _k, label, _w, _p in COLS]]
    for row in rows:
        line = []
        for key, _l, _w, _p in COLS:
            v = row.get(key)
            if key in NUM_KEYS:
                line.append(Paragraph(_money(v), cell_r))
            else:
                line.append(Paragraph(str(v if v is not None else ""), cell))
        data.append(line)
    totals = {k: sum(float(x.get(k) or 0) for x in rows) for k in NUM_KEYS}
    data.append([Paragraph("", cell)] * len(COLS))
    data[-1][2] = Paragraph("<b>TOTAL</b>", cell)
    for i, (key, _l, _w, _p) in enumerate(COLS):
        if key in NUM_KEYS:
            data[-1][i] = Paragraph(f"<b>{_money(totals[key])}</b>", cell_r)

    t = Table(data, repeatRows=1, colWidths=[c[3] * mm for c in COLS])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#94a3b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(Spacer(1, 12 * mm))
    sign = Table([[Paragraph("Prepared By<br/><br/>_____________________<br/>Accounts", cell),
                   Paragraph("Verified By<br/><br/>_____________________<br/>Manager — Accounts", cell),
                   Paragraph("Approved By<br/><br/>_____________________<br/>Management", cell)]],
                 colWidths=[92 * mm, 92 * mm, 92 * mm])
    sign.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(sign)
    doc.build(story)
    return buf.getvalue()
