"""Iteration 11 — Operations Pulse endpoint tests.

Verifies GET /api/dashboard/operations-pulse:
  * 7 cards, expected keys, valid tones, non-negative integer values
  * Accessible to any authenticated user (super_admin AND site_engineer)
  * Counter semantics match DB queries used by the router
  * Unauthenticated request is rejected
"""
import os
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@erp.com", "password": "Admin@123"}
SITE_ENG = {"email": "test_site_engineer@erp.com", "password": "TestPass@123"}

EXPECTED_KEYS = {
    "pending_approvals",
    "material_issue_holds",
    "open_ptws",
    "low_stock",
    "ppe_due",
    "open_enquiries",
    "open_safety",
}
ALLOWED_TONES = {"primary", "success", "warning", "danger", "info", "neutral"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def engineer_session(admin_session):
    # Try login; if missing, create then login.
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=SITE_ENG, timeout=20)
    if r.status_code != 200:
        admin_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": SITE_ENG["email"],
                "password": SITE_ENG["password"],
                "full_name": "TEST Site Engineer",
                "role": "site_engineer",
            },
            timeout=20,
        )
        r = s.post(f"{BASE_URL}/api/auth/login", json=SITE_ENG, timeout=20)
        assert r.status_code == 200, f"engineer login failed after register: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def mongo_db():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL / DB_NAME not set in env — semantic checks skipped")
    return MongoClient(mongo_url)[db_name]


# --- pulse endpoint contract ---
class TestOperationsPulseShape:
    def test_unauthenticated_rejected(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/operations-pulse", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_admin_returns_pulse(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dashboard/operations-pulse", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "as_of" in body and "cards" in body
        # ISO timestamp parses
        datetime.fromisoformat(body["as_of"].replace("Z", "+00:00"))
        assert isinstance(body["cards"], list)
        assert len(body["cards"]) == 7

    def test_card_keys_and_shape(self, admin_session):
        body = admin_session.get(f"{BASE_URL}/api/dashboard/operations-pulse", timeout=20).json()
        keys = {c["key"] for c in body["cards"]}
        assert keys == EXPECTED_KEYS, f"unexpected keys: {keys ^ EXPECTED_KEYS}"
        for c in body["cards"]:
            assert set(c.keys()) >= {"key", "label", "value", "tone", "deeplink"}
            assert isinstance(c["value"], int) and c["value"] >= 0
            assert c["tone"] in ALLOWED_TONES, f"tone {c['tone']} not allowed"
            assert isinstance(c["deeplink"], str) and c["deeplink"].startswith("/app/")
            assert isinstance(c["label"], str) and c["label"].strip()

    def test_site_engineer_can_access(self, engineer_session):
        r = engineer_session.get(f"{BASE_URL}/api/dashboard/operations-pulse", timeout=20)
        assert r.status_code == 200, f"non-admin should access pulse, got {r.status_code}: {r.text}"
        body = r.json()
        assert len(body["cards"]) == 7


# --- semantic correctness vs raw DB queries ---
class TestOperationsPulseSemantics:
    def _cards_map(self, session):
        body = session.get(f"{BASE_URL}/api/dashboard/operations-pulse", timeout=20).json()
        return {c["key"]: c for c in body["cards"]}

    def test_pending_approvals_count(self, admin_session, mongo_db):
        cards = self._cards_map(admin_session)
        expected = mongo_db.approvals.count_documents({"status": {"$in": ["pending", "in_progress"]}})
        assert cards["pending_approvals"]["value"] == expected

    def test_material_issue_holds_count(self, admin_session, mongo_db):
        cards = self._cards_map(admin_session)
        expected = mongo_db.inventory_transactions.count_documents({"status": "awaiting_approval"})
        assert cards["material_issue_holds"]["value"] == expected

    def test_open_ptws_count(self, admin_session, mongo_db):
        cards = self._cards_map(admin_session)
        expected = mongo_db.ptws.count_documents({"status": "open"})
        assert cards["open_ptws"]["value"] == expected

    def test_low_stock_count(self, admin_session, mongo_db):
        cards = self._cards_map(admin_session)
        expected = mongo_db.inventory.count_documents({"$expr": {"$lt": ["$quantity", "$min_stock"]}})
        assert cards["low_stock"]["value"] == expected

    def test_ppe_due_count(self, admin_session, mongo_db):
        cards = self._cards_map(admin_session)
        cutoff = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
        expected = mongo_db.ppe_issuance.count_documents({"expiry_date": {"$ne": None, "$lte": cutoff}})
        assert cards["ppe_due"]["value"] == expected

    def test_open_enquiries_count(self, admin_session, mongo_db):
        cards = self._cards_map(admin_session)
        expected = mongo_db.enquiries.count_documents(
            {"status": {"$in": ["open", "under_review", "submitted", "negotiation"]}}
        )
        assert cards["open_enquiries"]["value"] == expected

    def test_open_safety_count(self, admin_session, mongo_db):
        cards = self._cards_map(admin_session)
        expected = mongo_db.safety_reports.count_documents({"status": {"$nin": ["closed", "resolved"]}})
        assert cards["open_safety"]["value"] == expected

    def test_deeplinks_match_spec(self, admin_session):
        cards = self._cards_map(admin_session)
        expected = {
            "pending_approvals": "/app/approvals",
            "material_issue_holds": "/app/store-transactions",
            "open_ptws": "/app/ptws",
            "low_stock": "/app/inventory",
            "ppe_due": "/app/ppe",
            "open_enquiries": "/app/enquiries",
            "open_safety": "/app/safety",
        }
        for k, dl in expected.items():
            assert cards[k]["deeplink"] == dl
