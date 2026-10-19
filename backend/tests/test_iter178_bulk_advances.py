"""Iter 178 — Employee Advances: bulk permission fix + Excel/CSV bulk upload.

Covers:
- POST /api/advances/bulk  (PM-scoped custom role manager_o_p allowed; out-of-scope employee blocked)
- Super admin bulk → ONE approval → approve chain → each advance approved + separate payment-queue row
- GET /api/advances/bulk/template  (xlsx headers)
- POST /api/advances/bulk/parse    (xlsx + csv validation, no DB writes)
- Regression: single advance create + approval
"""
import io
import os
import random

import pytest
import requests
from dotenv import dotenv_values
from openpyxl import Workbook, load_workbook

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")

ADMIN = ("admin@erp.com", "Admin@123")
MOP = ("test_mop@erp.com", "Mop@12345")

# employees on PRJ-2025-01 (mop's only project)
EMP_IN_SCOPE = ["1e99e383-7ccc-43f6-85c2-dae9adb52424", "8bd0fbcc-8a9c-404d-b5e1-10d3ad01ca49"]
EMP_CODES_IN_SCOPE = ["E-1001", "E-MOP-01"]
EMP_OUT_OF_SCOPE = "7d2abb4d-3542-4d85-80c5-1bf078dc95be"  # E-1002 Sneha Iyer (no project)

CREATED_BATCHES = []
CREATED_ADV_IDS = []


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {creds[0]}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def mop():
    return _login(MOP)


def _bulk_payload(emp_amounts, atype="Salary Advance"):
    return {
        "employees": [{"employee_id": e, "amount": a} for e, a in emp_amounts],
        "advance_type": atype,
        "reason": "TEST_iter178 automated bulk advance",
        "installments": 1,
        "remarks": "TEST_iter178",
        "documents_not_required": True,
        "documents_not_required_reason": "automated test - no docs",
    }


# ── 1. BUG VERIFY: PM-scoped custom role can raise bulk advances ──────────
class TestPMScopedBulk:
    def test_manager_op_bulk_allowed_for_own_project_employees(self, mop):
        r = mop.post(f"{BASE}/api/advances/bulk",
                     json=_bulk_payload([(EMP_IN_SCOPE[0], 1200), (EMP_IN_SCOPE[1], 1500)]), timeout=60)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"
        d = r.json()
        assert d["batch_no"].startswith("ADB"), d
        assert d["count"] == 2
        assert d["total"] == 2700
        assert len(d["advances"]) == 2
        CREATED_BATCHES.append(d["batch_no"])
        CREATED_ADV_IDS.extend([a["id"] for a in d["advances"]])
        # one approval only
        assert d.get("approval_id")

    def test_manager_op_blocked_for_out_of_scope_employee(self, mop):
        r = mop.post(f"{BASE}/api/advances/bulk",
                     json=_bulk_payload([(EMP_IN_SCOPE[0], 1000), (EMP_OUT_OF_SCOPE, 1000)]), timeout=60)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:400]}"
        assert "your projects" in r.text.lower()


# ── 2. Super admin bulk end-to-end (one approval → payment queue rows) ────
class TestAdminBulkEndToEnd:
    def test_admin_bulk_creates_one_approval_and_reaches_payment_queue(self, admin):
        r = admin.post(f"{BASE}/api/advances/bulk",
                       json=_bulk_payload([(EMP_IN_SCOPE[0], 2000), (EMP_OUT_OF_SCOPE, 2500)]), timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        batch_no = d["batch_no"]
        CREATED_BATCHES.append(batch_no)
        adv_ids = [a["id"] for a in d["advances"]]
        CREATED_ADV_IDS.extend(adv_ids)
        approval_id = d["approval_id"]
        assert len(adv_ids) == 2

        # exactly ONE approval references this batch
        ap = admin.get(f"{BASE}/api/approvals", timeout=60)
        assert ap.status_code == 200
        rows = ap.json() if isinstance(ap.json(), list) else ap.json().get("items", [])
        matching = [a for a in rows if a.get("batch_no") == batch_no]
        assert len(matching) == 1, f"expected 1 approval for {batch_no}, got {len(matching)}"

        # approve through the chain
        status = None
        for _ in range(10):
            act = admin.post(f"{BASE}/api/approvals/{approval_id}/action",
                             json={"action": "approve", "comment": "TEST_iter178 approve"}, timeout=60)
            assert act.status_code == 200, f"approval action failed: {act.status_code} {act.text[:400]}"
            body = act.json()
            status = (body.get("approval") or body).get("status") or body.get("status")
            if status == "approved":
                break
        assert status == "approved", f"chain not fully approved, last status={status}"

        # each advance approved
        for aid in adv_ids:
            g = admin.get(f"{BASE}/api/advances/{aid}", timeout=30)
            assert g.status_code == 200, g.text[:200]
            adv = g.json()
            assert adv["status"] == "approved", f"{aid} status={adv['status']}"
            assert adv["approved_amount"] == adv["requested_amount"]

        # separate payment-queue rows
        pq = admin.get(f"{BASE}/api/accounts/payment-queue", timeout=60)
        assert pq.status_code == 200, pq.text[:300]
        pq_rows = pq.json() if isinstance(pq.json(), list) else (pq.json().get("items") or pq.json().get("rows") or [])
        matched = [q for q in pq_rows if q.get("source_id") in adv_ids or q.get("source_ref") in adv_ids]
        assert len(matched) == 2, f"expected 2 payment-queue rows, got {len(matched)}"
        assert all((q.get("source") or "").lower() == "advance" for q in matched), matched


# ── 3. Template download ─────────────────────────────────────────────────
class TestBulkTemplate:
    def test_template_returns_xlsx_with_expected_headers(self, admin):
        r = admin.get(f"{BASE}/api/advances/bulk/template", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert "spreadsheetml" in r.headers.get("content-type", "")
        wb = load_workbook(io.BytesIO(r.content))
        ws = wb.worksheets[0]
        header = [ws.cell(row=1, column=i).value for i in range(1, 5)]
        assert header == ["Employee Code", "Employee Name", "Amount", "Remarks"], header


# ── 4. Parse validation ──────────────────────────────────────────────────
PARSE_ROWS = [
    [EMP_CODES_IN_SCOPE[0], "Arjun Reddy", 1000, "ok"],
    [EMP_CODES_IN_SCOPE[1], "Mop Manager", 2000, "ok"],
    ["NO-SUCH-CODE-999", "Ghost", 500, "unknown"],
    [EMP_CODES_IN_SCOPE[0], "Arjun Reddy", 700, "dupe"],
    ["E-1003", "Karan", 0, "zero"],
    ["E-1004", "Deepa", "abcd", "nonnumeric"],
]


def _xlsx_bytes():
    wb = Workbook()
    ws = wb.active
    ws.append(["Employee Code", "Employee Name", "Amount", "Remarks"])
    for r in PARSE_ROWS:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv_bytes():
    lines = ["Employee Code,Employee Name,Amount,Remarks"]
    for r in PARSE_ROWS:
        lines.append(",".join(str(c) for c in r))
    return ("\n".join(lines)).encode("utf-8")


class TestBulkParse:
    def _assert_expected(self, data):
        assert data["total"] == 6, data
        assert data["valid"] == 2, data
        assert data["errors"] == 4, data
        by_row = {r["row"]: r for r in data["rows"]}
        assert by_row[2]["amount"] == 1000 and by_row[2]["error"] == ""
        assert by_row[3]["amount"] == 2000 and by_row[3]["error"] == ""
        assert "not found" in by_row[4]["error"].lower(), by_row[4]
        assert "duplicate" in by_row[5]["error"].lower(), by_row[5]
        assert "greater than 0" in by_row[6]["error"].lower(), by_row[6]
        assert "not a number" in by_row[7]["error"].lower(), by_row[7]

    def test_parse_xlsx(self, admin):
        before = None
        r = admin.post(f"{BASE}/api/advances/bulk/parse",
                       files={"file": ("bulk.xlsx", _xlsx_bytes(),
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                       timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        self._assert_expected(r.json())
        assert before is None

    def test_parse_csv(self, admin):
        r = admin.post(f"{BASE}/api/advances/bulk/parse",
                       files={"file": ("bulk.csv", _csv_bytes(), "text/csv")}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        self._assert_expected(r.json())

    def test_parse_no_db_writes(self, admin):
        """Advance count must be unchanged by two parse calls."""
        c1 = len(admin.get(f"{BASE}/api/advances", timeout=60).json())
        admin.post(f"{BASE}/api/advances/bulk/parse",
                   files={"file": ("bulk.csv", _csv_bytes(), "text/csv")}, timeout=60)
        c2 = len(admin.get(f"{BASE}/api/advances", timeout=60).json())
        assert c1 == c2, f"parse created rows: {c1} → {c2}"

    def test_parse_rejects_bad_extension(self, admin):
        r = admin.post(f"{BASE}/api/advances/bulk/parse",
                       files={"file": ("bulk.txt", b"a,b", "text/plain")}, timeout=60)
        assert r.status_code == 400, r.status_code

    def test_parse_missing_columns(self, admin):
        r = admin.post(f"{BASE}/api/advances/bulk/parse",
                       files={"file": ("bad.csv", b"Foo,Bar\n1,2", "text/csv")}, timeout=60)
        assert r.status_code == 400, r.status_code

    def test_parse_pm_scope_flags_out_of_project(self, mop):
        body = b"Employee Code,Employee Name,Amount,Remarks\nE-1001,Arjun,1000,ok\nE-1002,Sneha,1000,out\n"
        r = mop.post(f"{BASE}/api/advances/bulk/parse",
                     files={"file": ("s.csv", body, "text/csv")}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["valid"] == 1 and d["errors"] == 1, d
        assert "your projects" in d["rows"][1]["error"].lower(), d["rows"]


# ── 5. Regression: single advance ─────────────────────────────────────────
class TestSingleAdvanceRegression:
    def test_single_on_behalf_create_and_approve(self, admin):
        payload = {
            "employee_id": EMP_OUT_OF_SCOPE,
            "advance_type": "Travel Advance",
            # Iter 205 blocks an identical live advance — keep each run unique.
            "requested_amount": 1800 + random.randint(1, 899) / 100,
            "reason": "TEST_iter178 single advance regression",
            "installments": 1,
            "documents_not_required": True,
            "documents_not_required_reason": "automated test - no docs",
            "submit": True,
        }
        r = admin.post(f"{BASE}/api/advances", json=payload, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        adv = r.json()
        CREATED_ADV_IDS.append(adv["id"])
        assert adv["status"] == "submitted"
        assert adv["advance_no"].startswith("AD-")
        approval_id = adv["approval_id"]

        status = None
        for _ in range(10):
            act = admin.post(f"{BASE}/api/approvals/{approval_id}/action",
                             json={"action": "approve", "comment": "TEST_iter178"}, timeout=60)
            assert act.status_code == 200, act.text[:300]
            body = act.json()
            status = (body.get("approval") or body).get("status") or body.get("status")
            if status == "approved":
                break
        assert status == "approved", status

        g = admin.get(f"{BASE}/api/advances/{adv['id']}", timeout=30)
        assert g.status_code == 200
        assert g.json()["status"] == "approved"
        assert g.json()["approved_amount"] == payload["requested_amount"]

    def test_bulk_docs_gate_failure_must_not_persist_orphan_advances(self, admin):
        """BUG: bulk inserts advances BEFORE insert_approval(); when the documents
        gate rejects (400) the advances stay in DB as 'submitted' with a dangling
        approval_id → stuck rows in the register, never approvable."""
        p = _bulk_payload([(EMP_IN_SCOPE[0], 999), (EMP_OUT_OF_SCOPE, 999)])
        p["documents_not_required"] = False
        p["documents_not_required_reason"] = ""
        p["reason"] = "TEST_iter178_orphan check"
        before = admin.get(f"{BASE}/api/advances", timeout=60).json()
        r = admin.post(f"{BASE}/api/advances/bulk", json=p, timeout=60)
        assert r.status_code == 400, f"expected docs-gate 400, got {r.status_code}"
        after = admin.get(f"{BASE}/api/advances", timeout=60).json()
        orphans = [a for a in after if a.get("reason") == "TEST_iter178_orphan check"]
        for a in orphans:
            CREATED_ADV_IDS.append(a["id"])
        assert len(after) == len(before), (
            f"docs-gate 400 still persisted {len(after) - len(before)} advance rows "
            f"(orphans: {[a.get('advance_no') for a in orphans]})")

    def test_bulk_requires_two_employees(self, admin):
        r = admin.post(f"{BASE}/api/advances/bulk",
                       json=_bulk_payload([(EMP_IN_SCOPE[0], 1000)]), timeout=60)
        assert r.status_code == 400, r.status_code
        assert "at least 2" in r.text.lower()
