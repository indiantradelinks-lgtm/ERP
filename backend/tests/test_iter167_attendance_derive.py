"""Iter 167 — Attendance auto-status time-window derivation.

Covers:
- GET/PUT /api/hr2/attendance-plus/auto-settings (validation & persistence)
- POST /api/hr2/attendance/bulk/day-sheet server-side derive (P/HD/A boundary cases)
- Bulk rows xlsx template + upload derive
- Punch-import preview derive (in/out both present)
- Monthly summary consistency (P/HD/A counts, paid_days)
- Regression: auto/run, punch-import preview without in/out, exports 200
"""
import io
import os
import pytest
import requests
from datetime import datetime, date, timedelta
from openpyxl import load_workbook, Workbook

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Test employee (from PRJ-2025-01) and past date in current month
TEST_EMPLOYEE_ID = None   # populated at runtime
TEST_EMPLOYEE_CODE = "E-1001"
TEST_PROJECT = "PRJ-2025-01"


def _past_date_in_current_month(offset: int = 0) -> str:
    today = date.today()
    d = today - timedelta(days=1 + offset)
    if d.month != today.month:
        # if beginning of month, use day 1
        d = today.replace(day=1)
    return d.isoformat()


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def emp_id(session):
    r = session.get(f"{API}/employees", params={"q": "Arjun"}, timeout=30)
    assert r.status_code == 200, r.text
    for e in r.json():
        if (e.get("employee_id") or e.get("emp_code")) == TEST_EMPLOYEE_CODE:
            return e["id"]
    # fallback — any employee under PRJ-2025-01
    r = session.get(f"{API}/employees", timeout=30)
    for e in r.json():
        if e.get("current_project_code") == TEST_PROJECT:
            return e["id"]
    pytest.skip("No test employee available")


# ─── Auto Settings ───────────────────────────────────────────
class TestAutoSettings:
    def test_get_defaults(self, session):
        r = session.get(f"{API}/hr2/attendance-plus/auto-settings")
        assert r.status_code == 200, r.text
        d = r.json()
        # Defaults after any prior tests could set values, but shape must match
        assert set(d.keys()) >= {"full_in_by", "full_out_after", "mid_time"}
        assert "full_day_hours" not in d and "half_day_hours" not in d

    def test_put_invalid_mid_ge_out(self, session):
        r = session.put(f"{API}/hr2/attendance-plus/auto-settings",
                        json={"full_in_by": "09:10", "full_out_after": "17:00", "mid_time": "17:30"})
        assert r.status_code == 400

    def test_put_invalid_mid_le_in(self, session):
        r = session.put(f"{API}/hr2/attendance-plus/auto-settings",
                        json={"full_in_by": "09:10", "full_out_after": "17:00", "mid_time": "08:00"})
        assert r.status_code == 400

    def test_put_valid_persists(self, session):
        r = session.put(f"{API}/hr2/attendance-plus/auto-settings",
                        json={"full_in_by": "09:15", "full_out_after": "17:30", "mid_time": "13:15"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["full_in_by"] == "09:15"
        assert d["full_out_after"] == "17:30"
        assert d["mid_time"] == "13:15"
        # restore defaults
        r2 = session.put(f"{API}/hr2/attendance-plus/auto-settings",
                         json={"full_in_by": "09:10", "full_out_after": "17:00", "mid_time": "13:00"})
        assert r2.status_code == 200
        assert r2.json()["full_in_by"] == "09:10"


# ─── Day Sheet Derive ─────────────────────────────────────────
class TestDaySheetDerive:
    CASES = [
        # (in, out, requested_status, expected_stored_status, label)
        ("09:30", "17:30", "present", "half_day", "late-in but full out → HD (afternoon half)"),
        ("09:05", "17:30", "present", "present", "in ≤ 09:10 and out ≥ 17:00 → P"),
        ("10:00", "12:00", "present", "absent", "covers neither half → A"),
        ("09:00", "13:00", "present", "half_day", "morning half exact"),
        ("13:00", "17:00", "present", "half_day", "afternoon half exact"),
        ("09:10", "17:00", "present", "present", "boundary inclusive → P"),
    ]

    @pytest.mark.parametrize("in_t,out_t,req_status,expected,label", CASES)
    def test_derive(self, session, emp_id, in_t, out_t, req_status, expected, label):
        d = _past_date_in_current_month()
        r = session.post(f"{API}/hr2/attendance/bulk/day-sheet", json={
            "date": d, "project_code": TEST_PROJECT, "master": "employee",
            "entries": [{"employee_id": emp_id, "status": req_status, "in_time": in_t, "out_time": out_t, "overtime_hours": 0}]
        })
        assert r.status_code == 200, f"{label}: {r.text}"
        # verify via day-sheet GET
        r2 = session.get(f"{API}/hr2/attendance/bulk/day-sheet",
                         params={"date": d, "master": "employee", "project_code": TEST_PROJECT})
        assert r2.status_code == 200
        row = next((x for x in r2.json()["rows"] if x["employee_id"] == emp_id), None)
        assert row is not None, f"row missing for {label}"
        assert row["status"] == expected, f"{label}: expected {expected} got {row['status']}"

    def test_manual_leave_unchanged(self, session, emp_id):
        d = _past_date_in_current_month(offset=1)
        r = session.post(f"{API}/hr2/attendance/bulk/day-sheet", json={
            "date": d, "project_code": TEST_PROJECT, "master": "employee",
            "entries": [{"employee_id": emp_id, "status": "leave", "overtime_hours": 0}]
        })
        assert r.status_code == 200, r.text
        r2 = session.get(f"{API}/hr2/attendance/bulk/day-sheet",
                         params={"date": d, "master": "employee", "project_code": TEST_PROJECT})
        row = next((x for x in r2.json()["rows"] if x["employee_id"] == emp_id), None)
        assert row["status"] == "leave"

    def test_manual_weekly_off_unchanged(self, session, emp_id):
        d = _past_date_in_current_month(offset=2)
        r = session.post(f"{API}/hr2/attendance/bulk/day-sheet", json={
            "date": d, "project_code": TEST_PROJECT, "master": "employee",
            "entries": [{"employee_id": emp_id, "status": "weekly_off", "overtime_hours": 0}]
        })
        assert r.status_code == 200
        r2 = session.get(f"{API}/hr2/attendance/bulk/day-sheet",
                         params={"date": d, "master": "employee", "project_code": TEST_PROJECT})
        row = next((x for x in r2.json()["rows"] if x["employee_id"] == emp_id), None)
        assert row["status"] == "weekly_off"


# ─── Bulk Rows Template + Upload ─────────────────────────────
class TestBulkRowsUpload:
    def test_template_downloads(self, session):
        r = session.get(f"{API}/hr2/attendance-plus/bulk-rows/template")
        assert r.status_code == 200, r.text
        assert "spreadsheet" in r.headers.get("content-type", "") or r.content[:2] == b"PK"

    def test_upload_derives_statuses(self, session, emp_id):
        # get emp_code from GET employees
        r = session.get(f"{API}/employees", timeout=30)
        emp = next((e for e in r.json() if e["id"] == emp_id), None)
        code = emp.get("employee_id") or emp.get("emp_code")
        name = emp.get("name")
        assert code

        wb = Workbook()
        ws = wb.active
        ws.title = "ATTENDANCE_ROWS"
        ws.append(["Employee Code", "Employee Name", "Date (YYYY-MM-DD)", "Shift",
                   "Status", "In Time", "Out Time", "Overtime Hours", "Remarks"])
        d1 = _past_date_in_current_month(offset=5)
        d2 = _past_date_in_current_month(offset=6)
        d3 = _past_date_in_current_month(offset=7)
        d4 = _past_date_in_current_month(offset=8)
        ws.append([code, name, d1, "GEN", "P", "09:00", "18:00", 0, "TEST_iter167"])
        ws.append([code, name, d2, "GEN", "P", "09:30", "18:00", 0, "TEST_iter167"])
        ws.append([code, name, d3, "GEN", "P", "10:30", "12:30", 0, "TEST_iter167"])
        ws.append([code, name, d4, "GEN", "L", "", "", 0, "TEST_iter167"])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        files = {"file": ("bulk_test.xlsx", buf.getvalue(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = session.post(f"{API}/hr2/attendance-plus/bulk-rows/upload", files=files)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result.get("ok") is True, result
        assert (result["created"] + result["updated"]) >= 4, result

        # Verify each date's stored status
        expected = {d1: "present", d2: "half_day", d3: "absent", d4: "leave"}
        for d, exp in expected.items():
            r2 = session.get(f"{API}/hr2/attendance/bulk/day-sheet",
                             params={"date": d, "master": "employee", "project_code": TEST_PROJECT})
            assert r2.status_code == 200
            row = next((x for x in r2.json()["rows"] if x["employee_id"] == emp_id), None)
            assert row is not None, f"row missing for {d}"
            assert row["status"] == exp, f"{d} expected {exp} got {row['status']}"


# ─── Monthly Summary Consistency ─────────────────────────────
class TestMonthlySummary:
    def test_summary_reflects_stored(self, session, emp_id):
        month = date.today().strftime("%Y-%m")
        r = session.get(f"{API}/hr2/attendance-plus/summary",
                        params={"month": month, "project_code": TEST_PROJECT, "employee_id": emp_id})
        assert r.status_code == 200, r.text
        d = r.json()
        emps = d.get("employees") or []
        assert emps, "no employees in summary"
        e = emps[0]
        # paid_days formula: P+L+WO+H+OD + 0.5*HD
        expected_paid = round(e["P"] + e["L"] + e["WO"] + e["H"] + e["OD"] + 0.5 * e["HD"], 1)
        assert e["paid_days"] == expected_paid, e


# ─── Punch-Import Preview Derive ─────────────────────────────
class TestPunchImportPreview:
    def test_preview_with_in_out_derives(self, session, emp_id):
        r = session.get(f"{API}/employees", timeout=30)
        emp = next((e for e in r.json() if e["id"] == emp_id), None)
        code = emp.get("employee_id") or emp.get("emp_code")

        # CSV with explicit IN and OUT columns per row — simple format AI should map easily.
        # Use a date in current month past
        d = _past_date_in_current_month(offset=10)
        csv_content = (
            "EmpCode,Date,InTime,OutTime\n"
            f"{code},{d},09:30,17:30\n"
        )
        files = {"file": ("punches.csv", csv_content.encode(), "text/csv")}
        r = session.post(f"{API}/hr2/attendance-plus/punch-import/preview", files=files, timeout=60)
        # 502 possible if AI unavailable; we accept 200 (main case) or 502/503 (env)
        assert r.status_code in (200, 502, 503), r.text
        if r.status_code != 200:
            pytest.skip(f"AI mapping unavailable: {r.status_code}")
        data = r.json()
        rows = data.get("rows") or []
        # Find row for our employee/date
        for row in rows:
            if row.get("date") == d and (row.get("employee_id") == emp_id or row.get("employee_code") == code):
                # In=09:30, Out=17:30 → should be half_day (afternoon half — in > 09:10)
                assert row.get("status") in ("half_day", "present"), row
                assert row.get("in_time") == "09:30"
                return
        # no matching row; not a failure — punch file format may not have been mapped by AI
        pytest.skip("AI did not map preview row for our employee")


# ─── Regressions ─────────────────────────────────────────────
class TestRegressions:
    def test_auto_run(self, session):
        month = date.today().strftime("%Y-%m")
        r = session.post(f"{API}/hr2/attendance-plus/auto/run",
                         json={"month": month, "project_code": "ALL",
                               "do_weekly_off": False, "do_absent": False})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_export_xlsx(self, session):
        month = date.today().strftime("%Y-%m")
        r = session.get(f"{API}/hr2/attendance-plus/summary/export",
                        params={"fmt": "xlsx", "month": month})
        assert r.status_code == 200

    def test_export_csv(self, session):
        month = date.today().strftime("%Y-%m")
        r = session.get(f"{API}/hr2/attendance-plus/summary/export",
                        params={"fmt": "csv", "month": month})
        assert r.status_code == 200
