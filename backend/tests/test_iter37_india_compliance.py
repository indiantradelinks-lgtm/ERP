"""Iteration 37 — Indian statutory compliance + employment_type validation.

Covers POST/PUT /api/employees validation for:
  - PAN (regex)
  - Aadhaar (12-digit + Verhoeff checksum)
  - UAN (12 digits)
  - ESIC (10-17 digits)
  - IFSC (regex)
  - employment_type (permanent / daily_wages / contractual)
  - conditional fields (daily_rate negative, contract_end < contract_start)
  - normalisation (PAN/IFSC uppercased)
"""
import os
import pytest
import requests

def _load_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        # Fall back to frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return url.rstrip("/")


BASE_URL = _load_base_url()
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

ADMIN_EMAIL = "admin@erp.com"
ADMIN_PASS = "Admin@123"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if r.status_code != 200:
        pytest.skip(f"Auth failed: {r.status_code} {r.text}")
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# Track created IDs for cleanup
created_ids = []


@pytest.fixture(scope="module", autouse=True)
def cleanup(client):
    yield
    for eid in created_ids:
        try:
            client.delete(f"{BASE_URL}/api/employees/{eid}")
        except Exception:
            pass


def _base_payload(**over):
    p = {
        "name": "TEST_Compliance_" + over.pop("suffix", "x"),
        "phone": "9999999999",
        "employment_type": "permanent",
    }
    p.update(over)
    return p


# -------------------- Negative validation --------------------

class TestNegativeValidation:
    def test_invalid_pan_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(suffix="badpan", pan_number="BAD123"))
        assert r.status_code == 400
        assert "PAN" in r.text

    def test_invalid_aadhaar_checksum_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(suffix="badaad", aadhaar_number="123456789012"))
        assert r.status_code == 400
        assert "checksum" in r.text.lower() or "Aadhaar" in r.text

    def test_invalid_aadhaar_format_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(suffix="badaad2", aadhaar_number="12345"))
        assert r.status_code == 400
        assert "Aadhaar" in r.text

    def test_invalid_ifsc_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(suffix="badifsc", bank_ifsc="BAD"))
        assert r.status_code == 400
        assert "IFSC" in r.text

    def test_negative_daily_rate_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(
            suffix="negrate", employment_type="daily_wages", daily_rate=-50))
        assert r.status_code == 400
        assert "daily_rate" in r.text.lower() or "negative" in r.text.lower()

    def test_contract_end_before_start_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(
            suffix="badct", employment_type="contractual",
            contract_start_date="2026-06-01", contract_end_date="2026-01-01"))
        assert r.status_code == 400
        assert "contract_end_date" in r.text.lower()

    def test_unknown_employment_type_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(suffix="badtype", employment_type="freelancer"))
        assert r.status_code == 400
        assert "employment_type" in r.text.lower()

    def test_invalid_uan_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(suffix="baduan", uan="12345"))
        assert r.status_code == 400
        assert "UAN" in r.text

    def test_invalid_esic_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/employees", json=_base_payload(suffix="badesic", esic_number="12"))
        assert r.status_code == 400
        assert "ESIC" in r.text


# -------------------- Positive validation --------------------

class TestPositiveValidation:
    def test_valid_permanent_full_compliance(self, client):
        payload = _base_payload(
            suffix="perm_ok",
            pan_number="abcde1234f",  # lowercase to test normalisation
            aadhaar_number="999941057058",  # known-valid Verhoeff
            uan="123456789012",
            esic_number="12345678901234567",  # 17 digits
            bank_ifsc="sbin0001234",  # lowercase
            bank_account_no="00112233445566",
            bank_name="SBI",
            employment_type="permanent",
            salary=50000,
        )
        r = client.post(f"{BASE_URL}/api/employees", json=payload)
        assert r.status_code in (200, 201), f"got {r.status_code}: {r.text}"
        body = r.json()
        eid = body["id"]
        created_ids.append(eid)
        # Normalisation checks
        assert body["pan_number"] == "ABCDE1234F", f"PAN not normalised: {body['pan_number']}"
        assert body["bank_ifsc"] == "SBIN0001234", f"IFSC not normalised: {body['bank_ifsc']}"
        assert body["employment_type"] == "permanent"

        # Verify persistence
        g = client.get(f"{BASE_URL}/api/employees/{eid}")
        assert g.status_code == 200
        gb = g.json()
        assert gb["pan_number"] == "ABCDE1234F"
        assert gb["aadhaar_number"] == "999941057058"

    def test_valid_daily_wages(self, client):
        payload = _base_payload(
            suffix="daily_ok",
            employment_type="daily_wages",
            daily_rate=600,
            working_days_per_month=26,
        )
        r = client.post(f"{BASE_URL}/api/employees", json=payload)
        assert r.status_code in (200, 201), f"got {r.status_code}: {r.text}"
        body = r.json()
        created_ids.append(body["id"])
        assert body["employment_type"] == "daily_wages"
        assert float(body["daily_rate"]) == 600

    def test_valid_contractual(self, client):
        payload = _base_payload(
            suffix="contract_ok",
            employment_type="contractual",
            contractor_name="TEST_Contractor",
            contractor_license_no="CLRA/2024/123",
            contract_start_date="2026-01-01",
            contract_end_date="2026-12-31",
        )
        r = client.post(f"{BASE_URL}/api/employees", json=payload)
        assert r.status_code in (200, 201), f"got {r.status_code}: {r.text}"
        body = r.json()
        created_ids.append(body["id"])
        assert body["employment_type"] == "contractual"

    def test_put_validation_runs(self, client):
        # Create then attempt invalid update
        payload = _base_payload(suffix="put_target", employment_type="permanent")
        r = client.post(f"{BASE_URL}/api/employees", json=payload)
        assert r.status_code in (200, 201)
        eid = r.json()["id"]
        created_ids.append(eid)
        # PUT with bad PAN
        u = client.put(f"{BASE_URL}/api/employees/{eid}", json={"pan_number": "BAD123"})
        assert u.status_code == 400
        assert "PAN" in u.text


# -------------------- Regression: other CRUD pages --------------------

class TestRegressionOtherResources:
    def test_vendors_list(self, client):
        r = client.get(f"{BASE_URL}/api/vendors")
        assert r.status_code == 200, f"vendors list failed: {r.status_code}"
        assert isinstance(r.json(), list)

    def test_projects_list(self, client):
        r = client.get(f"{BASE_URL}/api/projects")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_employees_list(self, client):
        r = client.get(f"{BASE_URL}/api/employees")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
