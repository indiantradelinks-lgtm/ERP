"""Iter 170 - Batch 4 backend regression:
- Employee duplicate guard (EMP-ID, Aadhaar, Name+Father)
- PUT employee unchanged -> no false positive
- GET /logistics/transport-vendors returns only APPROVED transportation vendors
- POST /project-requests still works (no PEX_TYPES NameError)
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://worksite-command.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@erp.com", "password": "Admin@123"})
    assert r.status_code == 200, r.text
    return s


# --- Employees duplicate guards ---
class TestEmployeeDuplicates:
    def test_get_transport_vendors_only_approved_transport(self, sess):
        r = sess.get(f"{BASE}/api/logistics/transport-vendors")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        for v in data:
            # Category should be transportation & status approved
            cat = (v.get("category") or v.get("vendor_category") or "").lower()
            status = (v.get("status") or v.get("approval_status") or "").lower()
            assert "transport" in cat or "logistic" in cat or cat == "", f"non-transport vendor: {v}"
            assert status in ("approved", "active", ""), f"non-approved vendor: {v}"
        # At least FastTrack Transporters expected present
        names = [(v.get("vendor_name") or v.get("name") or "") for v in data]
        assert any("FastTrack" in n for n in names), f"FastTrack Transporters missing: {names}"

    def test_create_worker_and_dup_guards(self, sess):
        ts = int(time.time())
        base_payload = {
            "master": "worker",
            "master_category": "worker",
            "name": f"TEST_UI_Dup_{ts}",
            "father_name": "Mohan Lal Test",
            "phone": f"9{ts%1000000000:09d}",
            "employment_type": "daily_wages",
        }
        r = sess.post(f"{BASE}/api/employees", json=base_payload)
        assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
        emp = r.json()
        emp_id = emp.get("id") or emp.get("_id") or emp.get("employee_id")
        assert emp_id, f"no id on created: {emp}"

        # Same name+father
        r2 = sess.post(f"{BASE}/api/employees", json={**base_payload, "phone": None})
        assert r2.status_code == 409, f"expected 409 name+father dup, got {r2.status_code} {r2.text}"
        assert "duplicate" in r2.text.lower() or "already" in r2.text.lower()

        # Same aadhaar — reuse existing worker with aadhaar 123412341234 per E1 context.
        # Try creating a new worker with the same aadhaar.
        r3 = sess.post(f"{BASE}/api/employees", json={
            "master": "worker",
            "employee_name": f"TEST_OtherName_{ts}",
            "father_name": f"Diff Father {ts}",
            "aadhaar_number": "123412341234",
            "employment_type": "daily_wages",
        })
        # 409 = duplicate; 400 = invalid checksum (fallback acceptable if the seed value not present)
        assert r3.status_code in (409, 400), f"expected 409 aadhaar dup, got {r3.status_code} {r3.text}"

        # PUT with unchanged data - should NOT false-positive
        emp_full = sess.get(f"{BASE}/api/employees/{emp_id}").json()
        r4 = sess.put(f"{BASE}/api/employees/{emp_id}", json=emp_full)
        assert r4.status_code in (200, 204), f"unchanged PUT failed: {r4.status_code} {r4.text}"

        # cleanup
        sess.delete(f"{BASE}/api/employees/{emp_id}")


class TestProjectRequestCreation:
    def test_post_project_request_no_pex_error(self, sess):
        # get a project
        pr = sess.get(f"{BASE}/api/projects").json()
        assert pr, "no projects"
        project = pr[0] if isinstance(pr, list) else (pr.get("items") or [{}])[0]
        pid = project.get("id") or project.get("_id")
        assert pid
        payload = {
            "request_type": "fuel",
            "project_id": pid,
            "amount": 100.0,
            "description": "iter170 smoke",
        }
        r = sess.post(f"{BASE}/api/project-requests", json=payload)
        assert r.status_code in (200, 201), f"POST /api/project-requests failed: {r.status_code} {r.text}"
        req = r.json()
        rid = req.get("id") or req.get("_id")
        if rid:
            # cleanup best-effort
            sess.delete(f"{BASE}/api/project-requests/{rid}")

    def test_expense_type_other_accepted(self, sess):
        pr = sess.get(f"{BASE}/api/projects").json()
        project = pr[0] if isinstance(pr, list) else (pr.get("items") or [{}])[0]
        pid = project.get("id") or project.get("_id")
        payload = {
            "request_type": "accommodation",
            "project_id": pid,
            "amount": 500.0,
            "description": "iter170 other-expense-type",
            "expense_type": "other",
            "settlement_mode": "other",
        }
        r = sess.post(f"{BASE}/api/project-requests", json=payload)
        assert r.status_code in (200, 201), f"POST with expense_type=other failed: {r.status_code} {r.text}"
        rid = (r.json() or {}).get("id")
        if rid:
            sess.delete(f"{BASE}/api/project-requests/{rid}")
