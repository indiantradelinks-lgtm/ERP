"""Iter 165 — Attendance Plus (Summary, AI punch import, row bulk, day-sheet in/out).

Tests:
  A) GET /hr2/attendance-plus/summary + exports (xlsx/csv/pdf)
  B) GET /hr2/attendance-plus/bulk-rows/template
  C) AI punch-import lifecycle (preview → commit(overwrite) → history → rollback)
  D) Row-based bulk upload (1 valid + 1 invalid)
  E) Day-sheet with in_time/out_time → hours + auto-OT
"""
import io
import os
from datetime import date, timedelta

import openpyxl
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
MONTH = "2026-08"
DATE_1 = "2026-08-02"  # a Sunday? doesn't matter - not future
DATE_ROWBULK = "2026-08-03"
DATE_DAYSHEET = "2026-08-04"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ── (A) Summary + exports ────────────────────────────────────────
class TestSummary:
    def test_summary_shape(self, client):
        r = client.get(f"{BASE_URL}/api/hr2/attendance-plus/summary", params={"month": MONTH}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("month", "totals", "employees", "by_date", "by_department", "by_project", "by_shift"):
            assert k in j, f"missing key {k}"
        assert j["month"] == MONTH
        assert isinstance(j["employees"], list)
        assert "P" in j["totals"] and "employees" in j["totals"]

    def test_summary_bad_month(self, client):
        r = client.get(f"{BASE_URL}/api/hr2/attendance-plus/summary", params={"month": "2026-13"}, timeout=15)
        assert r.status_code == 400

    @pytest.mark.parametrize("fmt,mime", [("xlsx", "spreadsheetml"), ("csv", "text/csv"), ("pdf", "pdf")])
    def test_export(self, client, fmt, mime):
        r = client.get(f"{BASE_URL}/api/hr2/attendance-plus/summary/export",
                       params={"fmt": fmt, "month": MONTH}, timeout=45)
        assert r.status_code == 200, r.text[:200]
        assert mime in r.headers.get("content-type", "").lower()
        assert len(r.content) > 100


# ── (B) Row-based template ──────────────────────────────────────
class TestBulkRowsTemplate:
    def test_template(self, client):
        r = client.get(f"{BASE_URL}/api/hr2/attendance-plus/bulk-rows/template", timeout=20)
        assert r.status_code == 200, r.text
        wb = openpyxl.load_workbook(io.BytesIO(r.content), data_only=True)
        assert "ATTENDANCE_ROWS" in wb.sheetnames
        header = [c.value for c in wb["ATTENDANCE_ROWS"][1]]
        assert "Employee Code" in header


# ── (C) AI punch-import lifecycle ───────────────────────────────
def _synthetic_punch_txt() -> bytes:
    """Tab-delimited: emp_code<TAB>name<TAB>datetime<TAB>direction."""
    lines = [
        "EmpCode\tName\tDateTime\tDirection",
        "E-1001\tArjun Reddy\t2026-08-02 09:05:00\tIN",
        "E-1001\tArjun Reddy\t2026-08-02 18:35:00\tOUT",
        "E-1002\tSneha Iyer\t2026-08-02 09:15:00\tIN",
        "E-1002\tSneha Iyer\t2026-08-02 19:05:00\tOUT",
        "E-9999\tUnknown Person\t2026-08-02 09:00:00\tIN",
        "E-9999\tUnknown Person\t2026-08-02 18:00:00\tOUT",
    ]
    return ("\n".join(lines)).encode("utf-8")


@pytest.fixture(scope="module")
def punch_batch_id(client):
    files = {"file": ("punches.txt", _synthetic_punch_txt(), "text/plain")}
    r = client.post(f"{BASE_URL}/api/hr2/attendance-plus/punch-import/preview",
                    files=files, timeout=90)
    assert r.status_code == 200, f"Preview failed: {r.status_code} {r.text[:400]}"
    j = r.json()
    assert j.get("ok") is True
    assert j.get("batch_id")
    # E-9999 unmatched
    flags_all = [f for row in j["rows"] for f in row.get("flags", [])]
    assert "unmatched_employee" in flags_all, f"expected unmatched_employee flag; rows={j['rows']}"
    return j["batch_id"]


class TestPunchImport:
    def test_commit(self, client, punch_batch_id):
        r = client.post(f"{BASE_URL}/api/hr2/attendance-plus/punch-import/{punch_batch_id}/commit",
                        json={"overwrite": True}, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["created"] + j["updated"] >= 2  # E-1001 + E-1002

    def test_history_has_batch(self, client, punch_batch_id):
        r = client.get(f"{BASE_URL}/api/hr2/attendance-plus/punch-imports", timeout=20)
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()]
        assert punch_batch_id in ids

    def test_summary_reflects_commit(self, client):
        r = client.get(f"{BASE_URL}/api/hr2/attendance-plus/summary", params={"month": MONTH}, timeout=30)
        assert r.status_code == 200
        emps = r.json()["employees"]
        codes = {e["employee_code"] for e in emps}
        assert "E-1001" in codes or "E-1002" in codes, f"expected imported emps in summary; got {codes}"

    def test_rollback(self, client, punch_batch_id):
        r = client.post(f"{BASE_URL}/api/hr2/attendance-plus/punch-import/{punch_batch_id}/rollback", timeout=30)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # rollback twice → 400
        r2 = client.post(f"{BASE_URL}/api/hr2/attendance-plus/punch-import/{punch_batch_id}/rollback", timeout=15)
        assert r2.status_code == 400


# ── (D) Row-based bulk upload ────────────────────────────────────
def _build_bulk_xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ATTENDANCE_ROWS"
    ws.append(["Employee Code", "Employee Name", "Date (YYYY-MM-DD)", "Shift",
               "Status (P/A/HD/L/WO/OD/H)", "In Time (HH:MM)", "Out Time (HH:MM)",
               "Overtime Hours", "Remarks"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestBulkRowsUpload:
    def test_upload_valid_and_invalid(self, client):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        content = _build_bulk_xlsx([
            ["E-1001", "Arjun Reddy", yesterday, "GEN", "P", "09:00", "18:30", 0.0, "iter165 test"],
            ["E-1002", "Sneha Iyer", yesterday, "GEN", "XX", "09:00", "18:00", 0.0, "invalid status"],
        ])
        files = {"file": ("rows.xlsx", content,
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = client.post(f"{BASE_URL}/api/hr2/attendance-plus/bulk-rows/upload", files=files, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert (j["created"] + j["updated"]) >= 1
        assert j["error_count"] >= 1
        # error message about invalid status
        assert any("Invalid status" in e.get("error", "") for e in j["errors"]), j["errors"]


# ── (E) Day-sheet with in/out → hours + OT ──────────────────────
class TestDaySheetInOut:
    def test_save_with_in_out(self, client):
        payload = {
            "date": DATE_DAYSHEET,
            "project_code": "HEAD-OFFICE",
            "master": "employee",
            "entries": [{
                "employee_id": None,  # filled below
                "status": "present",
                "overtime_hours": 0,
                "in_time": "09:00",
                "out_time": "19:00",
                "remarks": "iter165 in/out",
            }],
        }
        # get an employee id
        r = client.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                       params={"date": DATE_DAYSHEET, "master": "employee", "project_code": "HEAD-OFFICE"},
                       timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert rows, "no employees returned"
        # pick Arjun/Sneha
        emp = next((x for x in rows if x.get("code") in ("E-1001", "E-1002")), rows[0])
        payload["entries"][0]["employee_id"] = emp["employee_id"]

        r2 = client.post(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet", json=payload, timeout=20)
        assert r2.status_code == 200, r2.text
        assert r2.json()["ok"] is True

        # verify prefill returns in/out/remarks/total_hours=10 and OT=2
        r3 = client.get(f"{BASE_URL}/api/hr2/attendance/bulk/day-sheet",
                        params={"date": DATE_DAYSHEET, "master": "employee", "project_code": "HEAD-OFFICE"},
                        timeout=20)
        assert r3.status_code == 200
        row = next(x for x in r3.json()["rows"] if x["employee_id"] == emp["employee_id"])
        assert row["in_time"] == "09:00"
        assert row["out_time"] == "19:00"
        assert float(row["total_hours"] or 0) == 10.0
        assert float(row["overtime_hours"] or 0) == 2.0
        assert row["remarks"] == "iter165 in/out"
