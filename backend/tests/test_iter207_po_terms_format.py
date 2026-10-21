"""Iteration 207 — Service PO Terms & Conditions: auto numbering AND manual formatting.

Plain "one clause per line" text keeps the automatic 1…n numbering, while a
manually formatted set (headings, paragraphs, bullets, own clause numbers) is
printed exactly as typed — no duplicate or invented numbering — and the PDF lays
it out with proper spacing and page breaks.
"""
import os
import re

import pytest
import requests

import sys
sys.path.insert(0, "/app/backend")
from terms_format import has_manual_numbering, terms_to_html  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}

AUTO_TEXT = "First clause of the order.\nSecond clause of the order.\nThird clause of the order."
MANUAL_TEXT = """**SCOPE OF WORK**
The vendor shall provide monthly transport services as per the agreed schedule.

1. COMMERCIAL TERMS
1.1 The rate shall remain firm for the entire contract period.
1.2 Taxes as applicable shall be paid extra against a valid tax invoice.

2. VEHICLE & MANPOWER
   - All vehicles shall carry valid fitness, insurance and pollution certificates.
   - Drivers shall hold a valid commercial licence.
(a) A replacement vehicle must be of the same or higher specification.
Payment Terms:
Payment shall be released within 30 days of invoice receipt."""


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return s


# ───────────────────────── formatter ─────────────────────────
def test_plain_lines_keep_automatic_numbering():
    html = terms_to_html(AUTO_TEXT)
    assert has_manual_numbering(AUTO_TEXT) is False
    assert [n for n in re.findall(r"tnc-num'>(.*?)<", html)] == ["1.", "2.", "3."]
    assert "tnc-para" not in html


def test_manual_format_is_preserved_without_extra_numbering():
    html = terms_to_html(MANUAL_TEXT)
    assert has_manual_numbering(MANUAL_TEXT) is True
    markers = re.findall(r"tnc-num'>(.*?)<", html)
    # Only the author's own markers — nothing auto-generated.
    assert markers == ["1.1", "1.2", "•", "•", "(a)"]
    # Headings print unnumbered, and a numbered heading keeps its own number inline.
    assert "<div class='tnc-heading'>SCOPE OF WORK</div>" in html
    assert "<div class='tnc-heading'>Payment Terms:</div>" in html
    assert "<div class='tnc-heading'>1. COMMERCIAL TERMS</div>" in html
    assert "<div class='tnc-heading'>2. VEHICLE &amp; MANPOWER</div>" in html
    # Plain paragraphs stay paragraphs instead of becoming clause 1, 2, 3…
    assert html.count("tnc-para") >= 2
    # Sub-clauses and bullets get their own indent classes.
    assert "tnc-sub" in html and "tnc-bullet" in html


def test_no_number_is_duplicated_or_invented():
    html = terms_to_html(MANUAL_TEXT)
    markers = re.findall(r"tnc-num'>(.*?)<", html)
    numeric = [m for m in markers if m[0].isdigit()]
    assert len(numeric) == len(set(numeric)), "a clause number was repeated"
    # Every numeric marker that prints must exist in the source text.
    for m in numeric:
        assert m.rstrip(".") in MANUAL_TEXT


def test_empty_terms_fall_back_to_a_note():
    assert "As mutually agreed" in terms_to_html("")
    assert "As mutually agreed" in terms_to_html("   \n  \n")


# ───────────────────────── preview endpoint ─────────────────────────
@pytest.mark.parametrize("text,manual", [(AUTO_TEXT, False), (MANUAL_TEXT, True)])
def test_preview_endpoint_matches_the_formatter(session, text, manual):
    r = session.post(f"{API}/service-workflow/terms/preview", json={"body": text}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert data["manual_numbering"] is manual
    assert data["html"] == terms_to_html(text)
    assert data["lines"] == len([l for l in text.splitlines() if l.strip()])


# ───────────────────────── rendered PDF ─────────────────────────
def _po(terms):
    return dict(po_no="SPO-TEST-0001", po_date="2026-10-21", project_code="PRJ-TEST",
                project_name="Terms layout check", status="approved", subtotal=100000.0,
                tax_amount=18000.0, total_value=118000.0, tax_pct=18, quantity=1, rate=100000.0,
                terms_conditions=terms, terms_title="Layout Check",
                payment_terms="30 days from invoice",
                line_items=[dict(description="Service", quantity=1, unit="Lot", rate=100000.0,
                                 amount=100000.0, tax_pct=18, tax_amount=18000.0, total=118000.0)])


@pytest.mark.parametrize("terms,expected", [(AUTO_TEXT, "auto"), (MANUAL_TEXT, "manual")])
def test_pdf_renders_both_formats(terms, expected):
    from pdf_generator import render_service_po_pdf
    vendor = dict(name="Test Vendor Pvt Ltd", gst="07AAACT0000A1Z1",
                  addresses=[dict(line1="Plot 1", city="New Delhi", pin="110020", state="Delhi")])
    data = render_service_po_pdf(_po(terms), vendor, {})
    assert data[:5] == b"%PDF-", "not a PDF"
    assert len(data) > 5000

    import pypdfium2 as pdfium
    import io
    doc = pdfium.PdfDocument(io.BytesIO(data))
    assert 1 <= len(doc) <= 3, "terms should not spill into stray pages"
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "Terms & Conditions" in text
    if expected == "auto":
        assert "1. First clause of the order." in text.replace("\r", " ").replace("\n", " ")
    else:
        assert "SCOPE OF WORK" in text
        assert "1.1" in text and "1.2" in text
        # The whole set must be present — nothing cut off at a page break.
        assert "Payment shall be released within 30 days of invoice receipt." in \
               text.replace("\n", " ").replace("  ", " ")
        # The last clause of a numbered block survives the page break.
        assert "replacement vehicle must be of the same or higher specification" in text.replace("\n", " ")
