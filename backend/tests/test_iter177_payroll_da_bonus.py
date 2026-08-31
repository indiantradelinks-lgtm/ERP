"""Iter 177 — Payroll Salary Structure: DA + Attendance Bonus + Bulk Upload (validate/import).

Covers:
  - GET  /api/payroll/master/bulk/template   (header includes DA + Attendance Bonus cols)
  - POST /api/payroll/master/bulk/validate   (dry-run preview, no DB writes)
  - POST /api/payroll/master/bulk/import     (upsert, no duplicates, error rows skipped)
  - PUT  /api/payroll/master/{employee_id}   (da / attendance_bonus_* persisted)
  - POST /api/payroll/run/preview            (da prorated, Attendance Bonus only when lop_days==0)
  - HR4  /api/hr4/salary-structures + approve  → syncs da/bonus into payroll_master
"""
import io
import os

import pytest
import requests
from dotenv import dotenv_values
from openpyxl import Workbook, load_workbook

fenv = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or fenv.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
MONTH = "2026-07"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        sess.headers.update({"Authorization": f"Bearer {tok}"})
    return sess


@pytest.fixture(scope="module")
def employees(s):
    r = s.get(f"{API}/employees", timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    rows = data if isinstance(data, list) else data.get("items") or data.get("employees") or []
    assert rows, "no employees returned"
    return rows


@pytest.fixture(scope="module")
def template_bytes(s):
    r = s.get(f"{API}/payroll/master/bulk/template", timeout=120)
    assert r.status_code == 200, r.text[:300]
    assert XLSX_MIME in r.headers.get("content-type", "")
    return r.content


def _header(content):
    ws = load_workbook(io.BytesIO(content), data_only=True).worksheets[0]
    return [str(c.value or "").strip() for c in ws[1]]


def _build(rows, header):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append([r.get(h, "") for h in header])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _post_file(s, path, content, name="payroll-master-template.xlsx"):
    return s.post(f"{API}{path}", files={"file": (name, content, XLSX_MIME)}, timeout=180)


def _masters(s):
    r = s.get(f"{API}/payroll/master", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    return d if isinstance(d, list) else d.get("rows") or d.get("items") or []


# ── 1. Template ────────────────────────────────────────────────────────────
class TestTemplate:
    def test_template_header_has_new_columns(self, template_bytes):
        header = _header(template_bytes)
        for col in ("DA", "Attendance Bonus (Y/N)", "Attendance Bonus Amount"):
            assert col in header, f"missing column {col}; header={header}"

    def test_template_prefilled_rows(self, template_bytes, employees):
        ws = load_workbook(io.BytesIO(template_bytes), data_only=True).worksheets[0]
        data_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
        assert len(data_rows) >= 1
        codes = {str(r[0]).strip() for r in data_rows}
        assert "E-1001" in codes, f"E-1001 not prefilled; sample={list(codes)[:5]}"


# ── 2. Validate (dry run) ─────────────────────────────────────────────────
class TestBulkValidate:
    def test_validate_preview_and_no_db_writes(self, s, template_bytes):
        header = _header(template_bytes)
        before = _masters(s)
        da_val = 4000 + (int(__import__("time").time()) % 97)  # ensure a real diff each run
        rows = [
            {"Employee Code": "E-1001", "Employee Name": "x", "Basic": 30000, "HRA": 6000, "DA": da_val,
             "Special Allowance": 0, "Site Allowance": 0, "Conveyance": 0, "Medical": 0,
             "Attendance Bonus (Y/N)": "Y", "Attendance Bonus Amount": 1500,
             "PF Applicable (Y/N)": "Y", "ESI Applicable (Y/N)": "N", "PT State": "GJ"},
            {"Employee Code": "E-1002", "Basic": 20000, "DA": "abc",
             "Attendance Bonus (Y/N)": "N", "Attendance Bonus Amount": 0, "PT State": "GJ"},
            {"Employee Code": "TEST_UNKNOWN_CODE", "Basic": 10000, "PT State": "GJ"},
            {"Employee Code": "E-1003", "Basic": 15000, "DA": 1000,
             "Attendance Bonus (Y/N)": "Y", "Attendance Bonus Amount": 0, "PT State": "GJ"},
        ]
        r = _post_file(s, "/payroll/master/bulk/validate", _build(rows, header))
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        counts = d["counts"]
        assert counts["error"] == 3, f"expected 3 error rows, got {counts}"
        assert d["ok"] is False
        by_code = {x["employee"]: x for x in d["rows"]}
        r1 = by_code["E-1001"]
        assert r1["action"] in ("update", "create"), r1
        assert r1["da"] == da_val
        assert "1,500" in (r1["attendance_bonus"] or ""), r1["attendance_bonus"]
        assert r1["gross"] == 36000 + da_val, r1["gross"]
        assert "da" in r1["changed_fields"], r1
        assert "must be a number" in by_code["E-1002"]["error"]
        assert "not found" in by_code["TEST_UNKNOWN_CODE"]["error"]
        assert "bonus amount is 0" in by_code["E-1003"]["error"]
        # NO DB writes during validate
        after = _masters(s)
        assert len(after) == len(before), "validate changed payroll_master row count"
        assert after == before, "validate mutated payroll_master documents"

    def test_validate_rejects_non_template(self, s):
        wb = Workbook()
        wb.active.append(["Random", "Header"])
        buf = io.BytesIO()
        wb.save(buf)
        r = _post_file(s, "/payroll/master/bulk/validate", buf.getvalue())
        assert r.status_code == 400, r.status_code

    def test_validate_rejects_non_xlsx(self, s):
        r = _post_file(s, "/payroll/master/bulk/validate", b"hello", name="notes.txt")
        assert r.status_code == 400


# ── 3. Import (upsert, no duplicates) ────────────────────────────────────
class TestBulkImport:
    def test_import_updates_without_duplicates(self, s, template_bytes):
        header = _header(template_bytes)
        rows = [
            {"Employee Code": "E-1001", "Basic": 30000, "HRA": 6000, "DA": 4000,
             "Attendance Bonus (Y/N)": "Y", "Attendance Bonus Amount": 1500,
             "PF Applicable (Y/N)": "Y", "ESI Applicable (Y/N)": "N", "PT State": "GJ"},
            {"Employee Code": "E-1004", "Basic": 30000, "DA": 2000,
             "Attendance Bonus (Y/N)": "N", "Attendance Bonus Amount": 0,
             "PF Applicable (Y/N)": "Y", "PT State": "GJ"},
            {"Employee Code": "TEST_UNKNOWN_CODE", "Basic": 10000, "PT State": "GJ"},
        ]
        content = _build(rows, header)
        r1 = _post_file(s, "/payroll/master/bulk/import", content)
        assert r1.status_code == 200, r1.text[:400]
        d1 = r1.json()
        assert d1["error_count"] == 1, d1
        assert d1["created"] + d1["updated"] == 2, d1

        # re-import the same file → must be updates only, no new docs
        masters_mid = _masters(s)
        r2 = _post_file(s, "/payroll/master/bulk/import", content)
        assert r2.status_code == 200, r2.text[:400]
        d2 = r2.json()
        assert d2["created"] == 0, f"re-import created duplicates: {d2}"
        masters_after = _masters(s)
        assert len(masters_after) == len(masters_mid), "row count grew on re-import"

        # duplicate detection for the employees touched by this import
        touched = {m["employee_id"] for m in masters_after}
        ids = [m["employee_id"] for m in masters_after]
        emp_r = s.get(f"{API}/employees", timeout=60).json()
        emp_rows = emp_r if isinstance(emp_r, list) else emp_r.get("items", [])
        mine = {e["id"] for e in emp_rows if (e.get("emp_code") or e.get("employee_id")) in ("E-1001", "E-1004")}
        dupes = {i for i in (touched & mine) if ids.count(i) > 1}
        assert not dupes, f"bulk import created duplicate payroll_master rows: {dupes}"

    def test_no_duplicate_master_rows_in_collection(self, s):
        """DATA INTEGRITY: payroll_master must have exactly one doc per employee_id."""
        rows = _masters(s)
        ids = [m["employee_id"] for m in rows]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        assert not dupes, f"duplicate payroll_master rows per employee_id (pre-existing data): {dupes}"

    def test_imported_values_persisted(self, s, employees):
        emp = next(e for e in employees if (e.get("emp_code") or e.get("employee_id")) == "E-1001")
        r = s.get(f"{API}/payroll/master/{emp['id']}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        m = r.json()
        assert m["da"] == 4000, m.get("da")
        assert m["attendance_bonus_applicable"] is True
        assert m["attendance_bonus_amount"] == 1500
        assert "_id" not in m


# ── 4. PUT master ────────────────────────────────────────────────────────
class TestMasterPut:
    def test_put_persists_da_and_bonus(self, s, employees):
        emp = next(e for e in employees if (e.get("emp_code") or e.get("employee_id")) == "E-1004")
        payload = {"employee_id": emp["id"], "basic": 30000, "hra": 5000, "da": 3500,
                   "attendance_bonus_applicable": True, "attendance_bonus_amount": 1200,
                   "pf_applicable": True, "pt_state": "GJ"}
        r = s.put(f"{API}/payroll/master/{emp['id']}", json=payload, timeout=60)
        assert r.status_code == 200, r.text[:400]
        out = r.json()
        assert out["da"] == 3500 and out["attendance_bonus_amount"] == 1200
        g = s.get(f"{API}/payroll/master/{emp['id']}", timeout=60).json()
        assert g["da"] == 3500
        assert g["attendance_bonus_applicable"] is True
        assert g["attendance_bonus_amount"] == 1200


# ── 5. Payroll run preview ───────────────────────────────────────────────
class TestRunPreview:
    @pytest.fixture(scope="class")
    def preview(self, s, employees):
        ids = [e["id"] for e in employees
               if (e.get("emp_code") or e.get("employee_id")) in ("E-1001", "E-1004")]
        r = s.post(f"{API}/payroll/run/preview",
                   json={"month": MONTH, "skip_attendance_check": True, "employee_ids": ids},
                   timeout=240)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert not d.get("preflight_failed"), d
        return d

    def test_da_in_earnings(self, preview):
        slips = preview["payslips"]
        assert slips, preview
        for sl in slips:
            assert "da" in sl["earnings"], f"da missing for {sl.get('employee_name')}: {sl['earnings']}"
            assert sl["earnings"]["da"] > 0

    def test_attendance_bonus_rules(self, preview):
        for sl in preview["payslips"]:
            labels = [e["label"] for e in sl.get("extra_earnings", [])]
            lop = float(sl.get("lop_days") or 0)
            if lop <= 0:
                assert "Attendance Bonus" in labels, f"{sl.get('employee_name')} lop={lop} labels={labels}"
                amt = next(e["amount"] for e in sl["extra_earnings"] if e["label"] == "Attendance Bonus")
                assert amt > 0
            else:
                assert "Attendance Bonus" not in labels, f"bonus paid with lop={lop}"

    def test_da_prorated_when_lop(self, s, employees):
        """LOP employee: DA prorated by paid_days/total_days and no attendance bonus."""
        emp = next((e for e in employees if (e.get("emp_code") or e.get("employee_id")) == "E-1005"), None)
        if not emp:
            pytest.skip("E-1005 not present")
        payload = {"employee_id": emp["id"], "basic": 31000, "da": 3100,
                   "attendance_bonus_applicable": True, "attendance_bonus_amount": 1000,
                   "pf_applicable": True, "pt_state": "GJ"}
        assert s.put(f"{API}/payroll/master/{emp['id']}", json=payload, timeout=60).status_code == 200
        r = s.post(f"{API}/payroll/run/preview",
                   json={"month": MONTH, "skip_attendance_check": True, "employee_ids": [emp["id"]]},
                   timeout=240)
        assert r.status_code == 200, r.text[:300]
        slips = r.json()["payslips"]
        assert slips
        sl = slips[0]
        paid, total = float(sl["paid_days"]), float(sl["total_days"])
        expected_da = round(3100 * (paid / total), 2)
        assert abs(sl["earnings"]["da"] - expected_da) < 1, (sl["earnings"]["da"], expected_da, paid, total)
        labels = [e["label"] for e in sl.get("extra_earnings", [])]
        if float(sl.get("lop_days") or 0) > 0:
            assert "Attendance Bonus" not in labels

    def test_legacy_master_without_da_has_no_da_key(self, s, employees):
        """Existing rows without DA must not get a forced 'da' earning."""
        emp = next((e for e in employees if (e.get("emp_code") or e.get("employee_id")) == "E-1006"), None)
        if not emp:
            pytest.skip("E-1006 not present")
        payload = {"employee_id": emp["id"], "basic": 25000, "pf_applicable": True, "pt_state": "GJ"}
        assert s.put(f"{API}/payroll/master/{emp['id']}", json=payload, timeout=60).status_code == 200
        r = s.post(f"{API}/payroll/run/preview",
                   json={"month": MONTH, "skip_attendance_check": True, "employee_ids": [emp["id"]]},
                   timeout=240)
        assert r.status_code == 200
        slips = r.json()["payslips"]
        assert slips
        assert "da" not in slips[0]["earnings"], slips[0]["earnings"]


# ── 6. Payslips regression ───────────────────────────────────────────────
class TestPayslipsRegression:
    def test_list_payslips(self, s):
        r = s.get(f"{API}/payroll/payslips?month={MONTH}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        rows = d if isinstance(d, list) else d.get("payslips") or d.get("rows") or []
        assert isinstance(rows, list)
        self.__class__._slips = rows

    def test_payslip_pdf(self, s):
        rows = getattr(self.__class__, "_slips", [])
        if not rows:
            pytest.skip("no committed payslips for month")
        sl = rows[0]
        r = s.get(f"{API}/payroll/payslips/{sl['employee_id']}/{sl['month']}/pdf", timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.content[:4] == b"%PDF", r.content[:20]


# ── 7. HR4 salary structure → payroll master sync ────────────────────────
class TestHr4StructureSync:
    def test_create_approve_syncs_da_and_bonus(self, s, employees):
        emp = next((e for e in employees if (e.get("emp_code") or e.get("employee_id")) == "E-1007"), None)
        if not emp:
            pytest.skip("E-1007 not present")
        body = {"employee_id": emp["id"], "wage_type": "monthly", "basic": 28000, "hra": 5600,
                "da": 2800, "attendance_bonus_applicable": True, "attendance_bonus_amount": 900,
                "effective_from": f"{MONTH}-01"}
        r = s.post(f"{API}/hr4/salary-structures", json=body, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        sid = r.json().get("id") or r.json().get("structure", {}).get("id")
        assert sid, r.json()
        a = s.post(f"{API}/hr4/salary-structures/{sid}/approve", json={"decision": "approve"}, timeout=60)
        assert a.status_code == 200, a.text[:400]
        m = s.get(f"{API}/payroll/master/{emp['id']}", timeout=60)
        assert m.status_code == 200, m.text[:300]
        md = m.json()
        assert md["da"] == 2800, md.get("da")
        assert md["attendance_bonus_applicable"] is True
        assert md["attendance_bonus_amount"] == 900


# ── 8. Payslip PDF labels (unit-level, no DB writes) ─────────────────────
class TestPayslipPdfLabels:
    def test_da_and_bonus_labels_in_payslip_body(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from pdf_generator import _payslip_body
        slip = {
            "employee_name": "TEST Emp", "employee_code": "E-9999", "month": MONTH,
            "paid_days": 31, "total_days": 31, "lop_days": 0,
            "earnings": {"basic": 30000, "hra": 6000, "da": 4000},
            "extra_earnings": [{"label": "Attendance Bonus", "amount": 1500}],
            "statutory_deductions": {"pf": 1800},
            "total_earnings": 41500, "total_deductions": 1800, "net_pay": 39700,
        }
        html = _payslip_body(slip)
        assert "DA (Dearness Allowance)" in html
        assert "Attendance Bonus" in html
