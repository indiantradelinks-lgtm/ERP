"""Faint, centered INDIAN TRADE LINKS watermark for every PDF document.

Usage:
    from pdf_watermark import attach_watermark
    doc = SimpleDocTemplate(...)
    attach_watermark(doc)         # registers onPage callbacks
    doc.build(story)
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

WATERMARK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "itl-watermark.png")


def _draw_watermark(canvas, doc, *, width_mm: float = 140.0):
    """Draw the watermark centered on the current page."""
    if not os.path.exists(WATERMARK_PATH):
        return
    try:
        page_w, page_h = canvas._pagesize
    except AttributeError:
        page_w, page_h = A4
    # Preserve aspect (logo is ~2.18:1). Width is configurable.
    img_w = width_mm * mm
    img_h = img_w * (265 / 577)
    x = (page_w - img_w) / 2.0
    y = (page_h - img_h) / 2.0
    canvas.saveState()
    try:
        canvas.drawImage(
            WATERMARK_PATH,
            x, y,
            width=img_w, height=img_h,
            mask="auto",
            preserveAspectRatio=True,
        )
    except Exception:
        # Watermark must never break document generation
        pass
    canvas.restoreState()


def attach_watermark(doc, *, width_mm: float = 140.0):
    """Wire watermark to both first-page and later-page callbacks of a
    SimpleDocTemplate. Preserves any pre-existing onPage callbacks set by the
    caller (rare in this codebase — but safe to chain)."""
    prev_first = getattr(doc, "onFirstPage", None)
    prev_later = getattr(doc, "onLaterPages", None)

    def _first(canvas, _doc):
        _draw_watermark(canvas, _doc, width_mm=width_mm)
        if callable(prev_first):
            prev_first(canvas, _doc)

    def _later(canvas, _doc):
        _draw_watermark(canvas, _doc, width_mm=width_mm)
        if callable(prev_later):
            prev_later(canvas, _doc)

    doc.onFirstPage = _first
    doc.onLaterPages = _later
    return doc
