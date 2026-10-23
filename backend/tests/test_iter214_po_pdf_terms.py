"""Iter 214 — Material PO PDF: no default T&C, only Payment/Delivery/Special terms, project name."""
import sys
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pdf_generator import render_po_pdf  # noqa: E402

PO = {
    "po_number": "PO-TEST-0001", "po_date": "2026-06-24", "pr_number": "PR-TEST-1",
    "project_code": "PRJ-2024-09", "project_name": "ONGC Roof Sheeting",
    "vendor_name": "RK TRADERS", "gst_type": "igst", "gst_pct": 18,
    "items": [{"name": "MS Sheet", "quantity": 10, "unit": "Nos", "rate": 100, "hsn_sac": "7208"}],
    "payment_terms": "30% advance along with the purchase order\n70% within 30 days of GRN acceptance",
    "delivery_terms": "Delivery within 15 days\nFreight to vendor scope",
    "special_terms": "Loading at dispatch is in the supplier scope",
    "other_terms": "Loading in the presence of the purchaser representative",
    # the default clause library must NOT be printed any more
    "terms_structured": [{"title": "Force Majeure", "body": "DEFAULT CLAUSE SHOULD NOT PRINT", "selected": True}],
    "terms": "LEGACY FALLBACK SHOULD NOT PRINT",
}


def _text(po):
    r = PdfReader(__import__("io").BytesIO(render_po_pdf(po, {"name": "RK TRADERS"})))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def test_default_terms_and_conditions_removed():
    t = _text(PO)
    assert "DEFAULT CLAUSE SHOULD NOT PRINT" not in t
    assert "LEGACY FALLBACK SHOULD NOT PRINT" not in t
    assert "Force Majeure" not in t


def test_only_the_three_term_sections_print():
    t = _text(PO)
    assert "Payment Terms" in t
    assert "Delivery Terms" in t
    assert "Special Terms & Conditions" in t
    assert "Other Terms" not in t


def test_serial_numbering_per_section():
    t = _text(PO).replace("\n", " ")
    assert "1. 30% advance along with the purchase order" in t
    assert "2. 70% within 30 days of GRN acceptance" in t
    assert "1. Delivery within 15 days" in t
    assert "2. Freight to vendor scope" in t
    # other_terms content continues the special clause numbering, nothing is dropped
    assert "1. Loading at dispatch is in the supplier scope" in t
    assert "2. Loading in the presence of the purchaser representative" in t


def test_project_name_printed():
    t = _text(PO)
    assert "ONGC Roof Sheeting" in t
    assert "PRJ-2024-09" in t


def test_placeholders_when_terms_blank():
    t = _text({**PO, "payment_terms": "", "delivery_terms": "", "special_terms": "", "other_terms": ""})
    assert "As mutually agreed." in t
    assert "As per the agreed delivery schedule." in t
    assert "Special Terms & Conditions" not in t


def test_manual_numbering_is_not_doubled():
    t = _text({**PO, "payment_terms": "1. Advance 30%\n2. Balance on delivery"}).replace("\n", " ")
    assert "1. Advance 30%" in t and "2. Balance on delivery" in t
    assert "1. 1. Advance 30%" not in t
