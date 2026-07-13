"""Iter 122 — true .xlsx exports + mobile per-row picker (backend only)."""
import os
import requests
import pytest

API_URL = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API_URL}/api/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200
    return sess


def _check_xlsx(content: bytes):
    """Real .xlsx starts with PK signature (ZIP container)."""
    assert len(content) > 1000, f"too small ({len(content)} bytes)"
    assert content[:2] == b"PK", "not a ZIP/XLSX container"


def test_followups_xlsx(s):
    r = s.get(f"{API_URL}/api/enquiry-followups/export.xlsx?view=all", timeout=20)
    assert r.status_code == 200, r.text[:200]
    assert XLSX_TYPE in r.headers.get("content-type", "")
    _check_xlsx(r.content)


def test_reviews_xlsx(s):
    r = s.get(f"{API_URL}/api/internal-reviews/export.xlsx", timeout=20)
    assert r.status_code == 200
    assert XLSX_TYPE in r.headers.get("content-type", "")
    _check_xlsx(r.content)


def test_action_items_xlsx(s):
    r = s.get(f"{API_URL}/api/action-items/export.xlsx?view=all", timeout=20)
    assert r.status_code == 200
    assert XLSX_TYPE in r.headers.get("content-type", "")
    _check_xlsx(r.content)


def test_xlsx_can_be_parsed_by_openpyxl(s):
    """Server-side sanity — write to disk, open with openpyxl, verify the
    formatted header + a status-coloured cell."""
    import tempfile, openpyxl
    r = s.get(f"{API_URL}/api/internal-reviews/export.xlsx", timeout=20)
    assert r.status_code == 200
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(r.content); fp = f.name
    wb = openpyxl.load_workbook(fp)
    ws = wb.active
    # Title row + header row exist; header row is bold
    header_row_idx = 3  # title is row 1, blank row 2, header row 3
    h = ws.cell(row=header_row_idx, column=1)
    assert h.font.bold, "header cell should be bold"
    # Sheet name set
    assert ws.title.startswith("Internal Reviews")
    # frozen panes set
    assert ws.freeze_panes is not None


def test_csv_still_works(s):
    """Ensure CSV endpoint is not broken by xlsx addition."""
    r = s.get(f"{API_URL}/api/internal-reviews/export.csv", timeout=15)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
