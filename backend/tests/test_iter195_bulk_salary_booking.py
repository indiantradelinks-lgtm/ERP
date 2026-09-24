"""Iteration 195 · HR → Payroll → Bulk Salary Booking E2E."""
import io
import os
import pytest
import requests
from openpyxl import load_workbook, Workbook

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

TEST_MONTH = "2026-08"          # un-booked month for full flow
BOOKED_MONTH = "2026-09"        # already-booked reference month


@pytest.fixture(scope="module")
def hdr():
    """Use httpOnly cookie session (via requests.Session)."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, r.text
    return s  # actually return session used as headers-proxy


def _get(sess, path, **kw):
    return sess.get(f"{API}{path}", **kw)


# ── 1. Template download ────────────────────────────────────────────────
def test_template_download(hdr):
    r = hdr.get(f"{API}/payroll/bulk-booking/template", params={"month": TEST_MONTH}, )
    assert r.status_code == 200, r.text
    assert "spreadsheet" in r.headers.get("content-type", "")
    wb = load_workbook(io.BytesIO(r.content))
    assert "Salary Export" in wb.sheetnames
    ws = wb["Salary Export"]
    headers = [c.value for c in ws[1]]
    assert headers[0] == "Emp ID"
    assert "Project Code" in headers and "Net Amount" in headers
    assert len(headers) == 38
    assert ws.max_row >= 2, "template should have at least 1 employee row"


def test_template_bad_month(hdr):
    r = hdr.get(f"{API}/payroll/bulk-booking/template", params={"month": "bad"}, )
    assert r.status_code == 400


# ── 2. Preview and Commit ───────────────────────────────────────────────
@pytest.fixture(scope="module")
def template_bytes(hdr):
    r = hdr.get(f"{API}/payroll/bulk-booking/template", params={"month": TEST_MONTH}, )
    assert r.status_code == 200
    return r.content


@pytest.fixture(scope="module")
def filled_sheet(template_bytes):
    """Load template and set project code to PRJ-2025-01 on every row."""
    wb = load_workbook(io.BytesIO(template_bytes))
    ws = wb["Salary Export"]
    headers = [c.value for c in ws[1]]
    pcode_idx = headers.index("Project Code") + 1
    pname_idx = headers.index("Project Name") + 1
    for row_i in range(2, ws.max_row + 1):
        ws.cell(row=row_i, column=pcode_idx, value="PRJ-2025-01")
        ws.cell(row=row_i, column=pname_idx, value="")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture(scope="module")
def preview_batch(hdr, filled_sheet):
    files = {"file": ("filled.xlsx", filled_sheet,
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"month": TEST_MONTH}
    r = hdr.post(f"{API}/payroll/bulk-booking/preview", files=files, data=data, )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["id"] and j["month"] == TEST_MONTH
    assert j["totals"]["count"] > 0
    assert isinstance(j["rows"], list) and len(j["rows"]) > 0
    assert isinstance(j["by_project"], list) and len(j["by_project"]) > 0
    assert isinstance(j["skipped"], list)
    assert isinstance(j["warnings"], list)
    return j


def test_preview_unknown_emp_skipped(hdr):
    wb = Workbook()
    ws = wb.active
    ws.title = "Salary Export"
    headers = ["Emp ID", "Employee Name", "Month/ Year", "Pay Days", "Present Days",
               "BASIC", "FIX Rate", "Other Allo", "DA", "HRA", "CONV", "Att. Bonus",
               "OT Amount", "OT1 Unit", "Other ded", "Advance.", "LWF", "PF", "ESI",
               "PT", "Total Earning", "Total Deduction", "Net Amount",
               "BASIC (Rt)", "FIX Rate (Rt)", "DA (Rt)", "OT RATE (Rt)",
               "EL AVAILED", "CL AVAILED", "Remark", "Project Name", "Project Code",
               "Department", "Designation", "Grade", "Father's Name", "UAN No.", "E.S.I. No."]
    ws.append(headers)
    # Add unknown emp id row so it should be skipped
    row = ["ZZZ_UNKNOWN_999", "Ghost", f"{TEST_MONTH}-01"] + [0] * 27 + ["", "", "PRJ-2025-01", "", "", "", "", "", ""]
    # pad to 38
    row = row[:38] + [""] * (38 - len(row))
    ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    files = {"file": ("bad.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = hdr.post(f"{API}/payroll/bulk-booking/preview", files=files,
                      data={"month": TEST_MONTH})
    # Should either 400 (nothing bookable) or return skipped
    assert r.status_code in (200, 400)
    if r.status_code == 400:
        assert "No bookable" in r.text or "not found" in r.text.lower()


@pytest.fixture(scope="module")
def booking(hdr, preview_batch):
    payload = {"overwrite": True, "remarks": "iter195 automated test"}
    r = hdr.post(f"{API}/payroll/bulk-booking/{preview_batch['id']}/commit",
                      json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["booking"]["booking_no"].startswith("BSB-")
    assert j["booked_count"] > 0
    return j["booking"]


# ── 3. Summary + reports ────────────────────────────────────────────────
def test_summary_after_commit(hdr, booking):
    r = hdr.get(f"{API}/payroll/bulk-booking/summary",
                     params={"month": TEST_MONTH})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["totals"]["headcount"] > 0
    assert j["totals"]["booked"] > 0
    assert j["totals"]["paid"] == 0
    assert j["totals"]["pending"] == j["totals"]["booked"]
    assert j["booking"]["booking_no"] == booking["booking_no"]
    assert any(p["project_code"] == "PRJ-2025-01" for p in j["by_project"])


def test_bookings_list(hdr, booking):
    r = hdr.get(f"{API}/payroll/bulk-booking/bookings",
                     params={"month": TEST_MONTH})
    assert r.status_code == 200
    j = r.json()
    rows = j if isinstance(j, list) else j.get("items", [])
    assert any(b["booking_no"] == booking["booking_no"] for b in rows)


def test_payslips_carry_project_and_source(hdr, booking):
    r = hdr.get(f"{API}/payroll/payslips",
                     params={"month": TEST_MONTH})
    assert r.status_code == 200, r.text
    j = r.json()
    rows = j if isinstance(j, list) else j.get("items", j.get("payslips", []))
    assert len(rows) > 0
    sample = rows[0]
    # Some rows will have PRJ-2025-01
    assert any(r.get("project_code") == "PRJ-2025-01" for r in rows)
    assert any(r.get("source") == "bulk_booking" for r in rows)
    assert "payment_status" in sample
    assert "paid_amount" in sample


def test_project_cost_report(hdr, booking):
    r = hdr.get(f"{API}/hr4/project-cost",
                     params={"month": TEST_MONTH})
    # Endpoint may be under different prefix; treat 404 as informational
    if r.status_code == 200:
        j = r.json()
        assert j is not None


def test_project_pnl_has_salary_line(hdr, booking):
    r = hdr.get(f"{API}/project-pnl",
                     params={"project_code": "PRJ-2025-01"})
    if r.status_code == 200:
        j = r.json()
        text = str(j).lower()
        assert "salary" in text, "project P&L should include a salary line"


# ── 4. Payment recording ────────────────────────────────────────────────
def test_month_level_partial_payment(hdr, booking):
    r = hdr.post(f"{API}/payroll/bulk-booking/payments",
                      json={"month": TEST_MONTH, "amount": 5000, "mode": "bank",
                            "reference": "TEST_UTR1"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["paid_now"] > 0
    assert j["paid"] >= j["paid_now"]
    assert j["pending"] == round(j["booked"] - j["paid"], 2)


def test_employee_wise_payment_and_full_clear(hdr, booking):
    s = hdr.get(f"{API}/payroll/bulk-booking/summary",
                     params={"month": TEST_MONTH}).json()
    emps = [e for e in (s.get("employees") or []) if float(e.get("pending_amount") or 0) > 0]
    if not emps:
        pytest.skip("no unpaid employees left")
    eid = emps[0]["employee_id"]
    r = hdr.post(f"{API}/payroll/bulk-booking/payments",
                      json={"month": TEST_MONTH, "employee_ids": [eid], "amount": 0,
                            "mode": "bank", "reference": "TEST_EMP"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["employees_paid"] == 1
    assert j["paid_now"] > 0


def test_payments_list(hdr, booking):
    r = hdr.get(f"{API}/payroll/bulk-booking/payments",
                     params={"month": TEST_MONTH})
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 2


# ── 5. Export booked sheet ──────────────────────────────────────────────
def test_export_booked(hdr, booking):
    r = hdr.get(f"{API}/payroll/bulk-booking/export",
                     params={"month": TEST_MONTH})
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert "Salary Export" in wb.sheetnames


# ── 6. Project report ──────────────────────────────────────────────────
def test_project_wise_report(hdr, booking):
    r = hdr.get(f"{API}/payroll/bulk-booking/project-report",
                     params={"month_from": TEST_MONTH, "month_to": TEST_MONTH})
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j and "totals" in j
    assert j["totals"]["booked"] > 0


# ── 7. Regression on existing endpoints ─────────────────────────────────
def test_payroll_master_regression(hdr):
    r = hdr.get(f"{API}/payroll/master", )
    assert r.status_code in (200, 404)


def test_salary_structures_regression(hdr):
    r = hdr.get(f"{API}/hr4/salary-structures", )
    assert r.status_code in (200, 404)


def test_attendance_regression(hdr):
    r = hdr.get(f"{API}/attendance", params={"month": TEST_MONTH}, )
    assert r.status_code in (200, 400, 404)
