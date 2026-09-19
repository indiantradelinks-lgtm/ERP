"""Central index bootstrap — idempotent, safe to run on every startup."""
from core import db, logger

# collection -> list of index specs (str = single asc field, list = compound)
INDEXES = {
    # High-volume system collections
    "notifications": [[("user_id", 1), ("at", -1)], [("user_id", 1), ("read", 1)], "id"],
    "audit_logs": [[("ts", -1)], [("resource", 1), ("ts", -1)], [("action", 1), ("ts", -1)], "actor_name", "record_id"],
    "login_activity": [[("at", -1)], "user_id", "email"],
    "module_visits": [[("ts", -1)]],
    "safety_audit_log": [[("at", -1)], [("record_kind", 1), ("record_id", 1)]],
    "logistics_audit_log": [[("at", -1)], [("record_kind", 1), ("record_id", 1)]],
    "employee_history": [[("at", -1)]],
    # Attachments + OneDrive sync
    "files": [[("is_deleted", 1), ("created_at", -1)], [("folder", 1), ("is_deleted", 1), ("created_at", -1)],
              [("parent_type", 1), ("parent_id", 1), ("is_deleted", 1)], "sha256", "uploaded_by_id"],
    "onedrive_queue": ["id", "file_id", [("status", 1), ("attempts", 1), ("next_attempt_at", 1), ("created_at", 1)],
                       [("status", 1), ("updated_at", 1)], [("created_at", -1)]],
    "onedrive_backups": [[("at", -1)]],
    # Workflow collections
    "approvals": [[("status", 1), ("created_at", -1)], [("type", 1), ("created_at", -1)], "chain.role",
                  "created_by", "requested_by", "requested_by_id", "record_id", [("updated_at", -1)]],
    "approval_versions": [[("approval_id", 1), ("saved_at", -1)]],
    "project_requests": [[("status", 1), ("created_at", -1)], [("project_id", 1), ("created_at", -1)],
                         "request_no", "created_by_id", "request_type"],
    "project_expenses": ["id", [("project_id", 1), ("created_at", -1)], "status", "expense_no"],
    "cost_centers": ["id", "code", [("project_id", 1), ("active", 1)], "category_id"],
    "sequences": [[("prefix", 1), ("year", 1)]],
    # Masters commonly filtered
    "employees": ["status", "department", "master_category", "current_project_code", "aadhaar_number", "emp_code"],
    "projects": ["code", "status", "client_id", "priority"],
    "clients": ["customer_code", "name", "status"],
    "vendors": ["vendor_code", "name", "status", "category"],
    "attendance": [[("employee_id", 1), ("date", -1)], [("date", -1)], "status", "project_code"],
    "inventory": ["code", "category", "status", "project_code"],
    "inventory_transactions": [[("created_at", -1)], [("item_id", 1), ("created_at", -1)]],
    "purchase_orders": ["po_number", "status", "vendor_id", "project_id", "pr_id"],
    "purchase_requisitions": ["id", "pr_number", "status", "project_id", [("created_at", -1)]],
    "rfqs": ["id", "status", "pr_id", [("created_at", -1)]],
    "grns": ["id", "po_id", "status", [("created_at", -1)]],
    "quotations": ["status", "enquiry_id", "client_id", "quote_no"],
    "enquiries": ["status", "client_id", [("created_at", -1)]],
    "orders": ["status", "enquiry_id", [("created_at", -1)]],
    "safety_reports": ["status", "type", "project_code", "incident_no"],
    "ptws": ["status", "ptw_no", "project_code"],
    "assets": ["code", "status", "category", "project_code"],
    "payroll": ["employee_id", "month", "status"],
    "vehicles": ["reg_no", "status"],
    "documents": ["expiry", "category", "is_deleted"],
    "deployments": ["employee_id", "status", "project", "deployment_no"],
    "recruitment_requests": ["status", "req_no", "source_request_id"],
    "candidates": ["status", "candidate_no", "recruitment_request_id"],
    "overtime": ["employee_id", "status", "ot_no"],
    "leave_requests": ["id", "employee_id", "status", [("created_at", -1)]],
    "employee_advances": ["id", "employee_id", "status", [("created_at", -1)]],
    "hr_letters": ["id", "employee_id", [("created_at", -1)]],
    "salary_structures": ["id", [("employee_id", 1), ("effective_from", -1)], "status"],
    "journal_entries": ["voucher_no", "status", [("created_at", -1)]],
    "vendor_invoices": ["status", "po_id", [("created_at", -1)]],
    "ra_bills": ["id", "project_id", "status", [("created_at", -1)]],
    "payments_in": ["id", "client_id", [("date", -1)], [("created_at", -1)]],
    "payments_out": ["id", "vendor_id", [("date", -1)], [("created_at", -1)]],
    "dprs": ["id", [("project_id", 1), ("date", -1)], [("created_at", -1)]],
    "measurements": ["id", "project_id", [("created_at", -1)]],
    "sites": ["id", "status"],
    "users": ["role", "department", "is_active"],
    "table_views": ["id", [("user_id", 1), ("table", 1), ("kind", 1)]],
    "email_outbox": ["status", [("created_at", -1)]],
}


async def ensure_indexes() -> int:
    created = 0
    for coll, specs in INDEXES.items():
        for spec in specs:
            try:
                await db[coll].create_index(spec)
                created += 1
            except Exception as e:  # noqa: BLE001 — never block startup on an index
                logger.warning(f"[indexes] {coll} {spec}: {e}")
    logger.info(f"[indexes] ensured {created} indexes across {len(INDEXES)} collections")
    return created
