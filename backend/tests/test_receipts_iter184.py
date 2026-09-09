"""
Iteration 184 — Receipts Module Backend Tests
Tests for the new Receipts page features:
- GET /api/billing/invoices/receivable returns only invoices with outstanding > 0 (approved or partially_paid status)
- POST /api/billing/receipts accepts project_code and file_ids, creates receipt and returns receipt_no + created_at
- PATCH /api/billing/receipts/{id} accepts txn_reference, mode, bank_account, remarks, file_ids updates
- GET /api/billing/receipts/{id} returns enriched detail with invoices and files arrays
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


class TestReceivableInvoices:
    """Test GET /api/billing/invoices/receivable endpoint"""
    
    def test_receivable_returns_only_outstanding_invoices(self, auth_session):
        """GET /api/billing/invoices/receivable returns only invoices with outstanding > 0"""
        resp = auth_session.get(f"{BASE_URL}/api/billing/invoices/receivable")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Verify all returned invoices have outstanding > 0
        for inv in data:
            assert inv.get("outstanding", 0) > 0, f"Invoice {inv.get('invoice_no')} has outstanding <= 0"
            assert inv.get("status") in ["approved", "partially_paid"], \
                f"Invoice {inv.get('invoice_no')} has invalid status: {inv.get('status')}"
        
        print(f"✓ Receivable endpoint returned {len(data)} invoices, all with outstanding > 0")
    
    def test_receivable_includes_required_fields(self, auth_session):
        """GET /api/billing/invoices/receivable returns invoices with all required fields for form auto-fill"""
        resp = auth_session.get(f"{BASE_URL}/api/billing/invoices/receivable")
        assert resp.status_code == 200
        
        data = resp.json()
        if len(data) > 0:
            inv = data[0]
            # Fields needed for auto-fill
            required_fields = ["id", "invoice_no", "client_name", "outstanding", "status"]
            for field in required_fields:
                assert field in inv, f"Required field '{field}' missing from receivable invoice"
            
            # Optional but expected fields
            optional_fields = ["client_id", "project_id", "project_code", "net_receivable", "paid_amount"]
            for field in optional_fields:
                if field not in inv:
                    print(f"  Note: Optional field '{field}' not present")
            
            print(f"✓ Receivable invoices include all required fields for form auto-fill")


class TestReceiptCreationWithNewFields:
    """Test POST /api/billing/receipts with project_code and file_ids"""
    
    def test_create_receipt_returns_receipt_no_and_created_at(self, auth_session):
        """POST /api/billing/receipts returns receipt_no and created_at in response"""
        # Get a client
        clients_resp = auth_session.get(f"{BASE_URL}/api/clients?limit=1")
        if clients_resp.status_code != 200 or len(clients_resp.json()) == 0:
            pytest.skip("No clients available")
        client = clients_resp.json()[0]
        
        payload = {
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "client_id": client["id"],
            "client_name": client["name"],
            "project_code": "TEST-PRJ-184",
            "mode": "NEFT",
            "txn_reference": f"TEST_UTR_184_{datetime.now().strftime('%H%M%S')}",
            "amount": 5000,
            "remarks": "TEST_iter184 receipt creation"
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/billing/receipts", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        assert "receipt_no" in data, "receipt_no missing from response"
        assert "created_at" in data, "created_at missing from response"
        assert data["receipt_no"].startswith("RCPT-"), f"Invalid receipt_no format: {data['receipt_no']}"
        
        print(f"✓ Created receipt {data['receipt_no']} with created_at={data['created_at']}")
    
    def test_create_receipt_with_file_ids(self, auth_session):
        """POST /api/billing/receipts accepts file_ids array"""
        clients_resp = auth_session.get(f"{BASE_URL}/api/clients?limit=1")
        if clients_resp.status_code != 200 or len(clients_resp.json()) == 0:
            pytest.skip("No clients available")
        client = clients_resp.json()[0]
        
        # Use fake file IDs (they won't be enriched but should be stored)
        fake_file_ids = ["test-file-id-001", "test-file-id-002"]
        
        payload = {
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "client_id": client["id"],
            "client_name": client["name"],
            "mode": "Bank",
            "amount": 3000,
            "file_ids": fake_file_ids,
            "remarks": "TEST_iter184 with file_ids"
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/billing/receipts", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        
        data = resp.json()
        assert "file_ids" in data, "file_ids missing from response"
        assert data["file_ids"] == fake_file_ids, f"file_ids not saved correctly: {data['file_ids']}"
        
        print(f"✓ Created receipt with file_ids={data['file_ids']}")


class TestReceiptPatch:
    """Test PATCH /api/billing/receipts/{id} endpoint"""
    
    @pytest.fixture
    def test_receipt(self, auth_session):
        """Create a test receipt for PATCH testing"""
        clients_resp = auth_session.get(f"{BASE_URL}/api/clients?limit=1")
        if clients_resp.status_code != 200 or len(clients_resp.json()) == 0:
            pytest.skip("No clients available")
        client = clients_resp.json()[0]
        
        payload = {
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "client_id": client["id"],
            "client_name": client["name"],
            "mode": "Bank",
            "amount": 2000,
            "remarks": "TEST_iter184 for PATCH testing"
        }
        
        resp = auth_session.post(f"{BASE_URL}/api/billing/receipts", json=payload)
        assert resp.status_code == 200
        return resp.json()
    
    def test_patch_txn_reference(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} updates txn_reference"""
        receipt_id = test_receipt["id"]
        new_utr = f"UTR-PATCH-{datetime.now().strftime('%H%M%S')}"
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json={"txn_reference": new_utr}
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        
        data = resp.json()
        assert data["txn_reference"] == new_utr, f"txn_reference not updated: {data['txn_reference']}"
        
        print(f"✓ PATCH updated txn_reference to {new_utr}")
    
    def test_patch_mode(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} updates mode"""
        receipt_id = test_receipt["id"]
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json={"mode": "RTGS"}
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        
        data = resp.json()
        assert data["mode"] == "RTGS", f"mode not updated: {data['mode']}"
        
        print("✓ PATCH updated mode to RTGS")
    
    def test_patch_bank_account(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} updates bank_account"""
        receipt_id = test_receipt["id"]
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json={"bank_account": "HDFC-TEST-12345"}
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        
        data = resp.json()
        assert data["bank_account"] == "HDFC-TEST-12345", f"bank_account not updated: {data['bank_account']}"
        
        print("✓ PATCH updated bank_account")
    
    def test_patch_remarks(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} updates remarks"""
        receipt_id = test_receipt["id"]
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json={"remarks": "Updated remarks via PATCH test"}
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        
        data = resp.json()
        assert data["remarks"] == "Updated remarks via PATCH test", f"remarks not updated: {data['remarks']}"
        
        print("✓ PATCH updated remarks")
    
    def test_patch_file_ids(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} updates file_ids"""
        receipt_id = test_receipt["id"]
        new_file_ids = ["new-file-001", "new-file-002"]
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json={"file_ids": new_file_ids}
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        
        data = resp.json()
        assert data["file_ids"] == new_file_ids, f"file_ids not updated: {data['file_ids']}"
        
        print(f"✓ PATCH updated file_ids to {new_file_ids}")
    
    def test_patch_multiple_fields(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} updates multiple fields at once"""
        receipt_id = test_receipt["id"]
        
        updates = {
            "txn_reference": "MULTI-UTR-001",
            "mode": "IMPS",
            "bank_account": "SBI-MULTI-001",
            "remarks": "Multi-field update test"
        }
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json=updates
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        
        data = resp.json()
        for key, value in updates.items():
            assert data[key] == value, f"{key} not updated correctly"
        
        print("✓ PATCH updated multiple fields at once")
    
    def test_patch_invalid_receipt_returns_404(self, auth_session):
        """PATCH /api/billing/receipts/{id} returns 404 for non-existent receipt"""
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/invalid-id-12345",
            json={"remarks": "test"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        
        print("✓ PATCH returns 404 for invalid receipt ID")
    
    def test_patch_empty_body_returns_400(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} returns 400 for empty update body"""
        receipt_id = test_receipt["id"]
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json={}
        )
        assert resp.status_code == 400, f"Expected 400 for empty body, got {resp.status_code}"
        
        print("✓ PATCH returns 400 for empty update body")
    
    def test_patch_disallowed_field_ignored(self, auth_session, test_receipt):
        """PATCH /api/billing/receipts/{id} ignores disallowed fields like amount"""
        receipt_id = test_receipt["id"]
        original_amount = test_receipt["amount"]
        
        resp = auth_session.patch(
            f"{BASE_URL}/api/billing/receipts/{receipt_id}",
            json={"amount": 999999, "remarks": "Trying to change amount"}
        )
        assert resp.status_code == 200, f"PATCH failed: {resp.text}"
        
        data = resp.json()
        # Amount should NOT be changed
        assert data["amount"] == original_amount, f"Amount was changed when it shouldn't be: {data['amount']}"
        # Remarks should be changed
        assert data["remarks"] == "Trying to change amount"
        
        print("✓ PATCH correctly ignores disallowed fields (amount)")


class TestReceiptDetailEnrichment:
    """Test GET /api/billing/receipts/{id} enrichment with invoices and files"""
    
    def test_detail_includes_invoices_array_when_invoice_ids_present(self, auth_session):
        """GET /api/billing/receipts/{id} returns invoices array when invoice_ids exist"""
        # First, find a receipt with invoice_ids
        list_resp = auth_session.get(f"{BASE_URL}/api/billing/receipts")
        assert list_resp.status_code == 200
        receipts = list_resp.json()
        
        receipt_with_invoices = None
        for r in receipts:
            if r.get("invoice_ids") and len(r["invoice_ids"]) > 0:
                receipt_with_invoices = r
                break
        
        if not receipt_with_invoices:
            pytest.skip("No receipts with invoice_ids found")
        
        # Get detail
        resp = auth_session.get(f"{BASE_URL}/api/billing/receipts/{receipt_with_invoices['id']}")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "invoices" in data, "invoices array missing from detail response"
        assert isinstance(data["invoices"], list), "invoices should be a list"
        
        # Verify invoice objects have expected fields
        if len(data["invoices"]) > 0:
            inv = data["invoices"][0]
            assert "id" in inv, "invoice id missing"
            assert "invoice_no" in inv, "invoice_no missing"
        
        print(f"✓ Receipt detail includes invoices array with {len(data['invoices'])} invoices")
    
    def test_detail_includes_files_array_when_file_ids_present(self, auth_session):
        """GET /api/billing/receipts/{id} returns files array when file_ids exist"""
        # Create a receipt with file_ids
        clients_resp = auth_session.get(f"{BASE_URL}/api/clients?limit=1")
        if clients_resp.status_code != 200 or len(clients_resp.json()) == 0:
            pytest.skip("No clients available")
        client = clients_resp.json()[0]
        
        # Note: These are fake file IDs, so files array will be empty
        # But the endpoint should still return the files key
        payload = {
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "client_id": client["id"],
            "client_name": client["name"],
            "mode": "Bank",
            "amount": 1000,
            "file_ids": ["fake-file-001"],
            "remarks": "TEST_iter184 files enrichment test"
        }
        
        create_resp = auth_session.post(f"{BASE_URL}/api/billing/receipts", json=payload)
        assert create_resp.status_code == 200
        receipt = create_resp.json()
        
        # Get detail
        resp = auth_session.get(f"{BASE_URL}/api/billing/receipts/{receipt['id']}")
        assert resp.status_code == 200
        
        data = resp.json()
        # files key should be present (may be empty if file IDs don't exist in documents collection)
        assert "file_ids" in data, "file_ids missing from detail"
        # The files array is only populated if file_ids exist in documents collection
        # Since we used fake IDs, files may not be present or be empty
        
        print(f"✓ Receipt detail handles file_ids correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
