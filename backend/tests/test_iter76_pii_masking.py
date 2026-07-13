"""Iter 76 — DPDP Act 2023 PII masking + duplicate-route removal.

Pure unit tests for:
  · exports._mask_value() / _redact_row()
  · exports_router._should_mask_pii()  (role-based gating)
  · Legacy CRUD removal: journal-entries and vendor-invoices must NOT be in MODULES
"""
from __future__ import annotations


def test_mask_email_partial():
    from exports import _mask_value
    assert _mask_value("email", "amit@itl.com") == "a***@itl.com"
    assert _mask_value("email", "") == ""
    assert _mask_value("email", None) is None


def test_mask_phone_last_four():
    from exports import _mask_value
    assert _mask_value("phone", "+91 98765 43210") == "XXXXXXXX3210"
    assert _mask_value("phone", "9876543210") == "XXXXXX3210"
    assert _mask_value("contact", "0000000001") == "XXXXXX0001"


def test_mask_identity_documents():
    from exports import _mask_value
    assert _mask_value("aadhaar", "123456789012") == "XXXX-XXXX-9012"
    assert _mask_value("pan", "ABCDE1234F") == "XXXXX1234X"
    assert _mask_value("gst", "07AABCT1234A1Z5") == "07***5"


def test_mask_banking():
    from exports import _mask_value
    assert _mask_value("bank_account", "123456789012") == "XXXXXXXX9012"
    assert _mask_value("ifsc", "HDFC0001234") == "HDFC*****"


def test_mask_dob_keeps_year_only():
    from exports import _mask_value
    assert _mask_value("dob", "1990-05-21") == "1990-XX-XX"
    assert _mask_value("date_of_birth", "1985-12-01") == "1985-XX-XX"


def test_mask_salary_fully_redacted():
    from exports import _mask_value
    assert _mask_value("salary", 75000) == "***"
    assert _mask_value("ctc", "12,00,000") == "***"


def test_redact_row_only_touches_pii_columns():
    from exports import _redact_row
    row = {
        "emp_code": "EMP-001", "name": "Amit Sharma", "role": "engineer",
        "department": "Ops", "phone": "9876543210", "email": "amit@itl.com",
        "salary": 60000, "pan": "ABCDE1234F",
    }
    out = _redact_row("employees", row)
    # Non-PII columns preserved verbatim
    assert out["emp_code"] == "EMP-001"
    assert out["name"] == "Amit Sharma"
    assert out["role"] == "engineer"
    assert out["department"] == "Ops"
    # PII columns masked
    assert out["phone"] == "XXXXXX3210"
    assert out["email"] == "a***@itl.com"
    assert out["salary"] == "***"
    assert out["pan"] == "XXXXX1234X"


def test_redact_row_unknown_resource_is_passthrough():
    from exports import _redact_row
    row = {"a": 1, "phone": "9876543210"}
    # 'projects' is not in PII_FIELDS → no masking even though 'phone' key exists
    assert _redact_row("projects", row) == row


def test_role_gating_for_employees():
    from routers.exports_router import _should_mask_pii
    # Privileged roles: super_admin, director, GM, HR, dept_head
    for r in ("super_admin", "director", "general_manager", "hr_executive", "dept_head"):
        assert not _should_mask_pii(r, "employees"), f"{r} should see raw PII"
    # Everyone else gets masked
    for r in ("project_manager", "site_engineer", "supervisor", "store_incharge",
              "purchase_officer", "vendor", "client_rep", None):
        assert _should_mask_pii(r, "employees"), f"{r} must be masked"


def test_role_gating_for_vendors():
    from routers.exports_router import _should_mask_pii
    assert not _should_mask_pii("purchase_officer", "vendors")
    assert not _should_mask_pii("accounts_executive", "vendors")
    assert _should_mask_pii("project_manager", "vendors")
    assert _should_mask_pii("hr_executive", "vendors")


def test_role_gating_for_payroll():
    from routers.exports_router import _should_mask_pii
    assert not _should_mask_pii("hr_executive", "payroll")
    assert not _should_mask_pii("accounts_executive", "payroll")
    assert _should_mask_pii("project_manager", "payroll")


def test_resource_without_pii_never_masks():
    from routers.exports_router import _should_mask_pii
    # Resources without declared PII columns (e.g. projects, assets) are always exposed
    for resource in ("projects", "assets", "inventory", "approvals", "safety_reports",
                      "purchase_orders", "quotations", "journal_entries", "vehicles"):
        assert not _should_mask_pii("supervisor", resource)


def test_legacy_journal_entries_crud_removed():
    """Phase 1 (accounts_router) owns journal-entries with double-entry validation.
    The generic /api/journal-entries CRUD must NOT be registered anywhere."""
    from routers.crud_router import MODULES
    slugs = {slug for slug, _ in MODULES}
    assert "journal-entries" not in slugs, "Legacy journal-entries CRUD must be removed"


def test_legacy_vendor_invoices_crud_removed():
    """Phase 3 (vendor_billing_router) owns vendor bills with lifecycle + JE posting.
    The generic /api/vendor-invoices CRUD must NOT be registered anywhere."""
    from routers.crud_router import MODULES
    slugs = {slug for slug, _ in MODULES}
    assert "vendor-invoices" not in slugs, "Legacy vendor-invoices CRUD must be removed"


def test_pii_fields_coverage():
    """Every resource that exposes a phone/email/pan/aadhaar/salary/bank field
    in COLUMNS must also list it in PII_FIELDS — guards against future regressions."""
    from exports import COLUMNS, PII_FIELDS
    SENSITIVE = {"phone", "email", "pan", "aadhaar", "aadhar", "salary",
                 "bank_account", "bank_account_no", "ifsc", "gst", "gstin",
                 "dob", "date_of_birth"}
    for resource, cols in COLUMNS.items():
        if resource not in PII_FIELDS:
            continue
        column_keys = {c["key"] for c in cols}
        sensitive_in_cols = column_keys & SENSITIVE
        # Every sensitive column visible in this resource must be marked PII
        missing = sensitive_in_cols - PII_FIELDS[resource]
        assert not missing, f"{resource}: PII columns not declared: {missing}"
