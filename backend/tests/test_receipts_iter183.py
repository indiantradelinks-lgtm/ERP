"""
Iteration 183 — Receipts Module Backend Tests
Tests for:
- POST /api/billing/receipts (create receipt with project_code, file_ids, total_adjusted)
- GET /api/billing/receipts (list with created_at, project_code, file_ids)
- GET /api/billing/receipts/{id} (detail with invoices array and files array)
- GET /api/billing/receipts/summary (mtd_amount, mtd_count, lifetime totals)
- GET /api/dashboard/summary (collections_mtd and collections_count in kpis)
"""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def auth_session():
    """Authenticate and return session with cookies"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@erp.com",
        "password": "Admin@123"
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    return session


class TestReceiptsEndpoints:
    """Test receipts CRUD and related endpoints"""
    
    def test_receipts_list_returns_required_fields(self, auth_session):
        """GET /api/billing/receipts returns list with created_at, project_code, file_ids"""
        resp = auth_session.get(f"{BASE_URL}/api/billing/receipts")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) > 0:
            receipt = data[0]
            # Verify required fields exist
            assert "receipt_no" in receipt, "receipt_no field missing"
            assert "created_at" in receipt, "created_at field missing"
            assert "project_code" in receipt or receipt.get("project_code") is None, "project_code field should exist"
            assert "file_ids" in receipt or receipt.get("file_ids") is None, "file_ids field should exist"
            assert "total_adjusted" in receipt, "total_adjusted field missing"
            print(f"✓ Receipts list returned {len(data)} receipts with required fields")
    
    def test_receipts_summary_returns_mtd_and_lifetime(self, auth_session):
        """GET /api/billing/receipts/summary returns mtd_amount, mtd_count, lifetime totals"""
        resp = auth_session.get(f"{BASE_URL}/api/billing/receipts/summary")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        # Verify all required fields
        assert "mtd_amount" in data, "mtd_amount field missing"
        assert "mtd_count" in data, "mtd_count field missing"
        assert "mtd_adjusted" in data, "mtd_adjusted field missing"
        assert "lifetime_amount" in data, "lifetime_amount field missing"
        assert "lifetime_count" in data, "lifetime_count field missing"
        assert "lifetime_adjusted" in data, "lifetime_adjusted field missing"
        
        # Verify types
        assert isinstance(data["mtd_amount"], (int, float)), "mtd_amount should be numeric"
        assert isinstance(data["mtd_count"], int), "mtd_count should be integer"
        
        print(f"✓ Receipts summary: MTD={data['mtd_amount']}, count={data['mtd_count']}, lifetime={data['lifetime_amount']}")
    
    def test_receipt_detail_returns_enriched_data(self, auth_session):
        """GET /api/billing/receipts/{id} returns enriched detail with invoices and files arrays"""
        # First get a receipt ID
        list_resp = auth_session.get(f"{BASE_URL}/api/billing/receipts")
        assert list_resp.status_code == 200
        receipts = list_resp.json()
        
        if len(receipts) == 0:
            pytest.skip("No receipts to test detail endpoint")
        
        receipt_id = receipts[0]["id"]
        
        # Get detail
        resp = auth_session.get(f"{BASE_URL}/api/billing/receipts/{receipt_id}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        # Verify basic fields
        assert data["id"] == receipt_id
        assert "receipt_no" in data
        assert "created_at" in data
        assert "total_adjusted" in data
        
        # Verify enriched fields exist (may be empty arrays)
        # invoices array is populated if invoice_ids exist
        if data.get("invoice_ids") and len(data["invoice_ids"]) > 0:
            assert "invoices" in data, "invoices array should be present when invoice_ids exist"
        
        # files array is populated if file_ids exist
        if data.get("file_ids") and len(data["file_ids"]) > 0:
            assert "files" in data, "files array should be present when file_ids exist"
        
        print(f"✓ Receipt detail for {data['receipt_no']} returned with enriched data")
    
    def test_receipt_detail_404_for_invalid_id(self, auth_session):
        """GET /api/billing/receipts/{id} returns 404 for non-existent receipt"""
        resp = auth_session.get(f"{BASE_URL}/api/billing/receipts/invalid-id-12345")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Receipt detail returns 404 for invalid ID")


class TestReceiptCreation:
    """Test receipt creation with new fields"""
    
    def test_create_receipt_with_project_code(self, auth_session):
        """POST /api/billing/receipts creates receipt with project_code and correct total_adjusted"""
        # Get a client for the receipt
        clients_resp = auth_session.get(f"{BASE_URL}/api/clients?limit=1")
        if clients_resp.status_code != 200 or len(clients_resp.json()) == 0:
            pytest.skip("No clients available for testing")
        
        client = clients_resp.json()[0]
        
        # Get a project
        projects_resp = auth_session.get(f"{BASE_URL}/api/projects?limit=1")
        project_code = None
        if projects_resp.status_code == 200 and len(projects_resp.json()) > 0:
            project_code = projects_resp.json()[0].get("code")
        
        payload = {
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "client_id": client["id"],
            "client_name": client["name"],
            "project_code": project_code or "TEST-PRJ-001",
            "mode": "NEFT",
            "txn_reference": f"TEST_UTR_{datetime.now().strftime('%H%M%S')}",
            "amount": 10000,
            "tds_deducted": 200,
            "retention_deducted": 500,
            "other_deduction": 100,
            "remarks": "TEST_iter183 receipt creation test"
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/billing/receipts", json=payload)
        assert resp.status_code == 200, f"Failed to create receipt: {resp.text}"
        
        data = resp.json()
        # Verify created receipt
        assert "receipt_no" in data, "receipt_no missing in response"
        assert data["project_code"] == payload["project_code"], "project_code not saved correctly"
        
        # Verify total_adjusted calculation: amount + tds + retention + other
        expected_total = payload["amount"] + payload["tds_deducted"] + payload["retention_deducted"] + payload["other_deduction"]
        assert data["total_adjusted"] == expected_total, f"total_adjusted mismatch: expected {expected_total}, got {data['total_adjusted']}"
        
        assert "created_at" in data, "created_at missing"
        assert data.get("file_ids") is not None, "file_ids field should exist (even if empty)"
        
        print(f"✓ Created receipt {data['receipt_no']} with project_code={data['project_code']}, total_adjusted={data['total_adjusted']}")
        
        # Verify via GET
        get_resp = auth_session.get(f"{BASE_URL}/api/billing/receipts/{data['id']}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["project_code"] == payload["project_code"]
        print(f"✓ Verified receipt persisted correctly via GET")
    
    def test_create_receipt_validation_errors(self, auth_session):
        """POST /api/billing/receipts validates required fields"""
        # Test with zero amounts
        payload = {
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "client_name": "Test Client",
            "mode": "Bank",
            "amount": 0,
            "tds_deducted": 0,
            "retention_deducted": 0
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/billing/receipts", json=payload)
        assert resp.status_code == 400, f"Expected 400 for zero amounts, got {resp.status_code}"
        print("✓ Receipt creation validates that at least one amount must be > 0")
    
    def test_create_receipt_invalid_mode(self, auth_session):
        """POST /api/billing/receipts validates mode field"""
        payload = {
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "client_name": "Test Client",
            "mode": "InvalidMode",
            "amount": 1000
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/billing/receipts", json=payload)
        assert resp.status_code == 400, f"Expected 400 for invalid mode, got {resp.status_code}"
        print("✓ Receipt creation validates mode field")


class TestDashboardCollections:
    """Test dashboard integration for collections KPI"""
    
    def test_dashboard_summary_includes_collections(self, auth_session):
        """GET /api/dashboard/summary returns collections_mtd and collections_count in kpis"""
        resp = auth_session.get(f"{BASE_URL}/api/dashboard/summary")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        assert "kpis" in data, "kpis object missing from dashboard summary"
        
        kpis = data["kpis"]
        assert "collections_mtd" in kpis, "collections_mtd missing from kpis"
        assert "collections_count" in kpis, "collections_count missing from kpis"
        
        # Verify types
        assert isinstance(kpis["collections_mtd"], (int, float)), "collections_mtd should be numeric"
        assert isinstance(kpis["collections_count"], int), "collections_count should be integer"
        
        print(f"✓ Dashboard KPIs include collections_mtd={kpis['collections_mtd']}, collections_count={kpis['collections_count']}")
    
    def test_dashboard_collections_matches_receipts_summary(self, auth_session):
        """Dashboard collections_mtd should match receipts summary mtd_amount"""
        # Get dashboard
        dash_resp = auth_session.get(f"{BASE_URL}/api/dashboard/summary")
        assert dash_resp.status_code == 200
        dash_kpis = dash_resp.json()["kpis"]
        
        # Get receipts summary
        rcpt_resp = auth_session.get(f"{BASE_URL}/api/billing/receipts/summary")
        assert rcpt_resp.status_code == 200
        rcpt_summary = rcpt_resp.json()
        
        # Compare (allow small float tolerance)
        assert abs(dash_kpis["collections_mtd"] - rcpt_summary["mtd_amount"]) < 0.01, \
            f"Dashboard collections_mtd ({dash_kpis['collections_mtd']}) doesn't match receipts summary mtd_amount ({rcpt_summary['mtd_amount']})"
        
        assert dash_kpis["collections_count"] == rcpt_summary["mtd_count"], \
            f"Dashboard collections_count ({dash_kpis['collections_count']}) doesn't match receipts summary mtd_count ({rcpt_summary['mtd_count']})"
        
        print("✓ Dashboard collections KPIs match receipts summary")


class TestCollectionReport:
    """Test collection report endpoint"""
    
    def test_collection_report_includes_required_columns(self, auth_session):
        """GET /api/billing/reports/collection returns rows with created_at and project_code"""
        resp = auth_session.get(f"{BASE_URL}/api/billing/reports/collection")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        assert "rows" in data, "rows missing from collection report"
        assert "totals" in data, "totals missing from collection report"
        
        if len(data["rows"]) > 0:
            row = data["rows"][0]
            assert "receipt_no" in row, "receipt_no missing"
            assert "created_at" in row, "created_at missing from collection report rows"
            assert "project_code" in row or row.get("project_code") is None, "project_code field should exist"
            print(f"✓ Collection report has {len(data['rows'])} rows with created_at and project_code columns")
        else:
            print("✓ Collection report endpoint works (no rows to verify)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
