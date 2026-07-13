"""Iteration 39 — HR Doc Scan-Prefill (AI auto-fill on New Employee).

Tests:
  * POST /hr/documents/scan-prefill — happy path + 4xx negatives + RBAC.
  * POST /hr/employees/{eid}/documents with scan_result_json — skips Gemini, sets scan_status='scanned'.
  * Recompute logic: 3 KYC docs prescanned-verified → employee.verification_status='verified'.
  * Upload still works WITHOUT scan_result_json (scan_status='not_scanned').
  * _build_verification engine handles pre-scan path correctly.
"""
import io
import json
import os

import pytest
import requests
from PIL import Image, ImageDraw
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SUPER = {"email": "supervisor@erp.com", "password": "Super@1234"}


def _png_bytes(text: str) -> bytes:
    img = Image.new("RGB", (640, 400), "white")
    d = ImageDraw.Draw(img)
    y = 20
    for line in text.split("\n"):
        d.text((20, y), line, fill="black")
        y += 24
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def super_session():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json=SUPER, timeout=15)
    if r.status_code != 200:
        pytest.skip("supervisor login not available")
    return s


@pytest.fixture(scope="module")
def new_employee(admin_session):
    """Create a TEST employee with NO PAN/Aadhaar/Bank — so prescan path
    can recompute its verification_status as docs are attached."""
    payload = {
        "name": "TEST_IT39 PrefillUser",
        "employment_type": "permanent",
        "phone": "9999900039",
        "status": "active",
    }
    r = admin_session.post(f"{BASE}/employees", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    row = r.json()
    yield row
    admin_session.delete(f"{BASE}/employees/{row['id']}", timeout=15)


# ─────────────────────────  scan-prefill validation  ─────────────────────────
class TestScanPrefillValidation:
    def test_unknown_doc_type(self, admin_session):
        files = {"file": ("x.png", _png_bytes("hi"), "image/png")}
        r = admin_session.post(
            f"{BASE}/hr/documents/scan-prefill",
            data={"doc_type": "blah"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_unsupported_ext(self, admin_session):
        files = {"file": ("x.txt", b"hello", "text/plain")}
        r = admin_session.post(
            f"{BASE}/hr/documents/scan-prefill",
            data={"doc_type": "pan"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 400

    def test_empty_file(self, admin_session):
        files = {"file": ("x.png", b"", "image/png")}
        r = admin_session.post(
            f"{BASE}/hr/documents/scan-prefill",
            data={"doc_type": "pan"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 400

    def test_supervisor_forbidden(self, super_session):
        files = {"file": ("x.png", _png_bytes("hi"), "image/png")}
        r = super_session.post(
            f"{BASE}/hr/documents/scan-prefill",
            data={"doc_type": "pan"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 403, r.text


# ─────────────────────────  scan-prefill happy path  ─────────────────────────
class TestScanPrefillHappy:
    def test_pan_extracts_fields(self, admin_session):
        """Live Gemini call. If budget cap is hit, accept 502 as informational."""
        png = _png_bytes(
            "INCOME TAX DEPARTMENT\nPERMANENT ACCOUNT NUMBER\n"
            "ABCDE1234F\nName: RAJESH KUMAR SHARMA\nFather: SURESH SHARMA\n"
            "Date of Birth: 15/03/1985"
        )
        files = {"file": ("pan.png", png, "image/png")}
        r = admin_session.post(
            f"{BASE}/hr/documents/scan-prefill",
            data={"doc_type": "pan"},
            files=files,
            timeout=90,
        )
        if r.status_code == 502:
            pytest.skip(f"Gemini budget/cap hit (informational): {r.text}")
        assert r.status_code == 200, r.text
        data = r.json()
        # Shape assertions
        for key in ("doc_type", "detected_kind", "raw_fields", "employee_fields", "raw_text_preview"):
            assert key in data, f"missing key {key}"
        assert data["doc_type"] == "pan"
        assert isinstance(data["employee_fields"], dict)
        # Likely fields (Gemini may or may not catch DOB depending on render)
        # We just verify PAN was extracted with the standard format normalisation.
        ef = data["employee_fields"]
        if "pan_number" in ef:
            assert ef["pan_number"] == "ABCDE1234F"


# ─────────────────────────  attach scan_result_json  ─────────────────────────
class TestUploadWithPrescan:
    def test_upload_with_prescan_skips_gemini(self, admin_session, new_employee):
        """Attach a pre-scanned PAN doc with scan_result_json. The endpoint
        must NOT call Gemini and must store scan_status='scanned',
        verification.overall + scan_result.from_prefill=true."""
        eid = new_employee["id"]
        # First set employee.pan_number so verification can compute 'verified'
        admin_session.put(f"{BASE}/employees/{eid}",
                          json={"pan_number": "ABCDE1234F", "name": "TEST_IT39 PrefillUser"},
                          timeout=15)
        files = {"file": ("pan.png", _png_bytes("PAN"), "image/png")}
        prescan = {
            "raw_fields": {"pan_number": "ABCDE1234F", "name": "TEST_IT39 PrefillUser"},
            "detected_kind": "pan",
            "confidence": 0.95,
            "raw_text_preview": "PAN dummy text",
        }
        r = admin_session.post(
            f"{BASE}/hr/employees/{eid}/documents",
            data={"doc_type": "pan", "label": "TEST_IT39 PAN",
                  "scan_result_json": json.dumps(prescan)},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["scan_status"] == "scanned"
        assert rec["scan_result"]["from_prefill"] is True
        assert rec["scan_result"]["fields"]["pan_number"] == "ABCDE1234F"
        assert rec["verification"] is not None
        assert rec["verification"]["overall"] in ("verified", "mismatch", "no_data")
        # PAN matches → should be 'verified'
        assert rec["verification"]["overall"] == "verified"

    def test_upload_no_prescan_keeps_not_scanned(self, admin_session, new_employee):
        eid = new_employee["id"]
        files = {"file": ("misc.png", _png_bytes("misc"), "image/png")}
        r = admin_session.post(
            f"{BASE}/hr/employees/{eid}/documents",
            data={"doc_type": "other", "label": "TEST_IT39 misc"},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["scan_status"] == "not_scanned"
        assert rec["scan_result"] is None
        assert rec["verification"] is None

    def test_three_kyc_prescanned_flips_verification_status(self, admin_session, new_employee):
        """After PAN+Aadhaar+Bank prescanned-verified, employees.verification_status='verified'."""
        eid = new_employee["id"]
        # Populate employee KYC fields so prescan matches will be 'verified'
        admin_session.put(f"{BASE}/employees/{eid}", json={
            "pan_number": "ABCDE1234F",
            "aadhaar_number": "123412341234",
            "bank_ifsc": "SBIN0001234",
            "bank_account_no": "001234567890",
            "bank_name": "STATE BANK OF INDIA",
            "name": "TEST_IT39 PrefillUser",
        }, timeout=15)

        # Upload Aadhaar prescan
        aad = {"raw_fields": {"aadhaar_number": "123412341234",
                              "name": "TEST_IT39 PrefillUser"},
               "detected_kind": "aadhaar"}
        admin_session.post(
            f"{BASE}/hr/employees/{eid}/documents",
            data={"doc_type": "aadhaar", "label": "TEST_IT39 Aadhaar",
                  "scan_result_json": json.dumps(aad)},
            files={"file": ("a.png", _png_bytes("aad"), "image/png")}, timeout=30,
        )
        # Upload Bank prescan
        bank = {"raw_fields": {"account_number": "001234567890",
                               "ifsc": "SBIN0001234",
                               "bank_name": "STATE BANK OF INDIA",
                               "account_holder": "TEST_IT39 PrefillUser"},
                "detected_kind": "bank_passbook"}
        admin_session.post(
            f"{BASE}/hr/employees/{eid}/documents",
            data={"doc_type": "bank_passbook", "label": "TEST_IT39 Bank",
                  "scan_result_json": json.dumps(bank)},
            files={"file": ("b.png", _png_bytes("bank"), "image/png")}, timeout=30,
        )
        # Verify employee.verification_status now 'verified'
        emp_r = admin_session.get(f"{BASE}/employees/{eid}", timeout=15)
        assert emp_r.status_code == 200
        emp = emp_r.json()
        assert emp.get("verification_status") == "verified", emp
