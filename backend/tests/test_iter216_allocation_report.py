"""Iter 216 — Material / Asset Allocations project-wise export (xlsx / csv / pdf)."""
import io
import os

import pytest
import requests
from openpyxl import load_workbook

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def allocations(s):
    rows = s.get(f"{API}/allocations", timeout=90).json()
    assert isinstance(rows, list) and rows, "no allocations to report on"
    return rows


def _xlsx(s, **params):
    r = s.get(f"{API}/allocations/export", params={"fmt": "xlsx", **params}, timeout=120)
    assert r.status_code == 200, r.text
    return load_workbook(io.BytesIO(r.content))


def test_excel_has_the_project_wise_sheets(s):
    wb = _xlsx(s)
    assert wb.sheetnames == ["Project-wise Allocations", "Project Summary", "Allocation Detail", "Filters"]
    hdr = list(next(wb["Project-wise Allocations"].iter_rows(values_only=True)))
    assert hdr == ["Project Name", "Project Code", "Material / Asset Name", "Kind", "Unit",
                   "Quantity Issued", "Quantity Returned", "Net Issued", "Allocations"]


def test_quantities_tally_with_the_api(s, allocations):
    wb = _xlsx(s)
    rows = list(wb["Project Summary"].iter_rows(values_only=True))[1:]
    grand = rows[-1]
    assert grand[0] == "Grand Total"
    assert grand[3] == pytest.approx(round(sum(float(a.get("quantity") or 0) for a in allocations), 3))
    assert grand[4] == pytest.approx(round(sum(float(a.get("returned_qty") or 0) for a in allocations), 3))
    assert grand[5] == pytest.approx(round(grand[3] - grand[4], 3))


def test_every_project_has_a_total_row(s):
    wb = _xlsx(s)
    rows = list(wb["Project-wise Allocations"].iter_rows(values_only=True))[1:-1]
    totals = {r[0][8:]: r for r in rows if str(r[0]).startswith("Total — ")}
    assert totals, "expected per-project total rows"
    for name, total in totals.items():
        items = [r for r in rows if r[0] == name]
        assert items, name
        assert total[5] == pytest.approx(round(sum(i[5] for i in items), 3))
        assert total[7] == pytest.approx(round(sum(i[7] for i in items), 3))


def test_project_names_are_resolved_not_just_codes(s, allocations):
    wb = _xlsx(s)
    detail = list(wb["Allocation Detail"].iter_rows(values_only=True))[1:]
    assert len(detail) == len(allocations)
    named = [d for d in detail if d[3] and d[2] and d[2] != d[3]]
    assert named, "expected at least one allocation showing the project NAME next to its code"


def test_status_filter_applies_to_the_export(s, allocations):
    issued = [a for a in allocations if a.get("status") == "issued"]
    if not issued:
        pytest.skip("no issued allocations")
    wb = _xlsx(s, status="issued")
    detail = list(wb["Allocation Detail"].iter_rows(values_only=True))[1:]
    assert len(detail) == len(issued)
    assert {d[10] for d in detail} == {"Issued"}


def test_search_filter_applies_to_the_export(s, allocations):
    needle = allocations[0]["item_name"]
    wb = _xlsx(s, q=needle)
    detail = list(wb["Allocation Detail"].iter_rows(values_only=True))[1:]
    assert detail and all(needle.lower() in str(d[5]).lower() for d in detail)
    filters = {r[0]: r[1] for r in wb["Filters"].iter_rows(values_only=True)}
    assert filters["Search"] == needle


def test_csv_export(s):
    r = s.get(f"{API}/allocations/export", params={"fmt": "csv"}, timeout=120)
    assert r.status_code == 200
    lines = r.text.splitlines()
    assert lines[0].startswith("Material / Asset Allocations")
    assert lines[3].startswith("Project Name,Project Code,Material / Asset Name")
    assert lines[-1].startswith("Grand Total")


def test_pdf_export(s):
    r = s.get(f"{API}/allocations/export", params={"fmt": "pdf"}, timeout=180)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF" and len(r.content) > 5000


def test_bad_format_is_rejected(s):
    r = s.get(f"{API}/allocations/export", params={"fmt": "docx"}, timeout=60)
    assert r.status_code == 400
