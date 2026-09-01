"""Iter 179 — RETEST of the two iter-178 bugs (bulk employee advances).

Fix 1 (backend): POST /api/advances/bulk inserts the approval FIRST (documents gate
can raise 400) so a rejected request leaves NO orphan employee_advances rows.
Regressions: happy-path bulk (admin), Manager-OP scoped bulk (200), bulk/parse (no writes).
"""
import io
import os

import pytest
import requests
from dotenv import dotenv_values
from openpyxl import Workbook

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")

ADMIN = ("admin@erp.com", "Admin@123")
MOP = ("test_mop@erp.com", "Mop@12345")

EMP_IN_SCOPE = ["1e99e383-7ccc-43f6-85c2-dae9adb52424", "8bd0fbcc-8a9c-404d-b5e1-10d3ad01ca49"]
EMP_CODES_IN_SCOPE = ["E-1001", "E-MOP-01"]

ORPHAN_REASON = "TEST_iter179 orphan gate check"
HAPPY_REASON = "TEST_iter179 happy path bulk"

CREATED_ADV_IDS = []
CREATED_APPROVAL_IDS = []


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


def _payload(emp_amounts, reason):
    return {
        "employees": [{"employee_id": e, "amount": a} for e, a in emp_amounts],
        "advance_type": "Salary Advance",
        "reason": reason,
        "installments": 1,
        "remarks": "TEST_iter179",
        "documents_not_required": True,
        "documents_not_required_reason": "automated retest - no docs needed",
    }


def _all_advances(sess):
    r = sess.get(f"{BASE}/api/advances", timeout=60)
    assert r.status_code == 200, f"GET /api/advances {r.status_code} {r.text[:200]}"
    d = r.json()
    return d if isinstance(d, list) else (d.get("items") or [])


def _approvals(sess):
    r = sess.get(f"{BASE}/api/approvals", timeout=60)
    assert r.status_code == 200, f"GET /api/approvals {r.status_code} {r.text[:200]}"
    d = r.json()
    return d if isinstance(d, list) else (d.get("items") or [])


# ── P0 RETEST: documents-gate 400 must leave no orphan advances ───────────
class TestNoOrphanOnDocsGate:
    def test_docs_gate_400_leaves_no_orphans(self, admin):
        before = _all_advances(admin)
        ap_before = _approvals(admin)

        p = _payload([(EMP_IN_SCOPE[0], 900), (EMP_IN_SCOPE[1], 900)], ORPHAN_REASON)
        p["documents_not_required"] = False
        p["documents_not_required_reason"] = ""
        p["documents"] = []

        r = admin.post(f"{BASE}/api/advances/bulk", json=p, timeout=60)
        assert r.status_code == 400, f"expected docs-gate 400, got {r.status_code}: {r.text[:400]}"

        after = _all_advances(admin)
        orphans = [a for a in after if a.get("reason") == ORPHAN_REASON]
        for a in orphans:
            CREATED_ADV_IDS.append(a["id"])
        assert not orphans, f"orphan advances persisted: {[a.get('advance_no') for a in orphans]}"
        assert len(after) == len(before), f"advance count changed {len(before)} → {len(after)}"

        ap_after = _approvals(admin)
        new_aps = [a for a in ap_after if a.get("id") not in {x.get("id") for x in ap_before}]
        assert not new_aps, f"unexpected new approval docs: {[a.get('title') for a in new_aps]}"


# ── Happy path after the reorder ──────────────────────────────────────────
class TestHappyPathAfterReorder:
    def test_bulk_success_creates_advances_and_matching_approval(self, admin):
        r = admin.post(f"{BASE}/api/advances/bulk",
                       json=_payload([(EMP_IN_SCOPE[0], 1100), (EMP_IN_SCOPE[1], 1300)], HAPPY_REASON),
                       timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["batch_no"].startswith("ADB"), d
        assert d["count"] == 2 and d["total"] == 2400, d
        approval_id = d["approval_id"]
        CREATED_APPROVAL_IDS.append(approval_id)
        adv_ids = [a["id"] for a in d["advances"]]
        CREATED_ADV_IDS.extend(adv_ids)

        # both advances exist and carry the approval_id
        for aid in adv_ids:
            g = admin.get(f"{BASE}/api/advances/{aid}", timeout=30)
            assert g.status_code == 200, g.text[:200]
            adv = g.json()
            assert adv["approval_id"] == approval_id, adv.get("approval_id")
            assert adv["status"] == "submitted", adv["status"]
            assert adv["batch_no"] == d["batch_no"]
            assert "_id" not in adv

        # approval doc exists with matching advance_ids
        matching = [a for a in _approvals(admin) if a.get("id") == approval_id]
        assert len(matching) == 1, f"approval {approval_id} not found"
        assert sorted(matching[0].get("advance_ids") or []) == sorted(adv_ids), matching[0].get("advance_ids")
        assert matching[0].get("batch_no") == d["batch_no"]


# ── Regression: Manager OP scoped bulk still 200 ──────────────────────────
class TestManagerOpRegression:
    def test_mop_bulk_in_scope_employees_ok(self, mop):
        r = mop.post(f"{BASE}/api/advances/bulk",
                     json=_payload([(EMP_IN_SCOPE[0], 1000), (EMP_IN_SCOPE[1], 1200)],
                                   "TEST_iter179 mop scoped bulk"), timeout=60)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"
        d = r.json()
        CREATED_APPROVAL_IDS.append(d["approval_id"])
        CREATED_ADV_IDS.extend([a["id"] for a in d["advances"]])
        assert d["count"] == 2 and d["total"] == 2200


# ── Regression: bulk/parse valid rows, no writes ──────────────────────────
class TestParseRegression:
    @staticmethod
    def _xlsx():
        wb = Workbook()
        ws = wb.active
        ws.append(["Employee Code", "Employee Name", "Amount", "Remarks"])
        ws.append([EMP_CODES_IN_SCOPE[0], "Arjun Reddy", 1000, "ok"])
        ws.append([EMP_CODES_IN_SCOPE[1], "Mop Manager", 2000, "ok"])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_parse_valid_xlsx_no_writes(self, admin):
        before = len(_all_advances(admin))
        r = admin.post(f"{BASE}/api/advances/bulk/parse",
                       files={"file": ("bulk.xlsx", self._xlsx(),
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                       timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["total"] == 2 and d["valid"] == 2 and d["errors"] == 0, d
        assert d["rows"][0]["amount"] == 1000 and d["rows"][0]["error"] == ""
        assert d["rows"][1]["amount"] == 2000 and d["rows"][1]["error"] == ""
        assert len(_all_advances(admin)) == before, "parse wrote rows to DB"


# ── Cleanup ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def cleanup(admin):
    yield
    for aid in set(CREATED_ADV_IDS):
        admin.delete(f"{BASE}/api/advances/{aid}", timeout=30)
    print(f"cleanup: attempted delete of {len(set(CREATED_ADV_IDS))} advances, "
          f"{len(set(CREATED_APPROVAL_IDS))} approvals tracked")
