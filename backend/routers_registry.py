"""Centralized router registry.

Single source of truth for the order in which API routers are mounted under
`/api`.  Some routers (e.g. `sales_router`, `payroll_router`, `vendors_router`,
`approvals_router`) MUST be registered BEFORE the generic `crud_router`
because they override CRUD-generic POST/PUT/DELETE paths.  That order is
captured here as a single declarative list — server.py just iterates it.

Side-effect imports (seed helpers, migration helpers, indexes) used by the
startup hooks remain in server.py.  This module is concerned ONLY with
include_router ordering.
"""
from __future__ import annotations

from typing import Iterable, List, Tuple
from fastapi import APIRouter

# ─── Router imports ─────────────────────────────────────────────────────────
from routers.auth_router import router as auth_router
from routers.allocation_router import router as allocation_router
from routers.payroll_router import router as payroll_router
from routers.vendors_router import router as vendors_router
from routers.projects_ops_router import router as projects_ops_router
from routers.resource_requests_router import router as resource_requests_router
from routers.ops_dashboard_router import router as ops_dashboard_router
from routers.ops_reports_router import router as ops_reports_router
from routers.approvals_router import router as approvals_router
from routers.sales_router import router as sales_router
from routers.crud_router import router as crud_router
from routers.files_router import router as files_router
from routers.notifications_router import router as notifications_router
from routers.exports_router import router as exports_router
from routers.dashboard_router import router as dashboard_router
from routers.admin_router import router as admin_router
from routers.billing_defaults_router import router as billing_defaults_router
from routers.quotation_builder_router import router as quotation_builder_router
from routers.ai_quotation_router import router as ai_quotation_router
from routers.project_dashboard_legacy_router import router as project_dashboard_router
from routers.procurement_master_router import router as procurement_master_router
from routers.data_cleanup_router import router as data_cleanup_router
from routers.hr import router as hr_router
from routers.hr_phase1_router import router as hr_phase1_router
from routers.hr_phase2_router import router as hr_phase2_router
from routers.hr_phase3_router import router as hr_phase3_router
from routers.hr_phase4_router import router as hr_phase4_router
from routers.hr_phase5_router import router as hr_phase5_router
from routers.admin_projects_dedupe import router as admin_projects_dedupe_router
from routers.employees_bulk_router import router as employees_bulk_router
from routers.inventory_bulk_router import router as inventory_bulk_router
from routers.resource_plan_bulk_router import router as resource_plan_bulk_router
from routers.attendance_bulk_router import router as attendance_bulk_router
from routers.projects_ops_masters_router import router as projects_ops_masters_router
from routers.projects_ops_workorders_router import router as projects_ops_workorders_router
from routers.projects_ops_phase1_router import router as projects_ops_phase1_router
from routers.projects_ops_phase2_router import router as projects_ops_phase2_router
from routers.projects_ops_phase2r2_router import router as projects_ops_phase2r2_router
from routers.projects_ops_phase3_router import router as projects_ops_phase3_router
from routers.projects_ops_phase3b_router import router as projects_ops_phase3b_router
from routers.projects_ops_phase3c_router import router as projects_ops_phase3c_router
from routers.projects_ops_phase4_router import router as projects_ops_phase4_router
from routers.projects_ops_phase5_router import router as projects_ops_phase5_router
from routers.procurement_extras_router import router as procurement_extras_router
from routers.email_router import router as email_router
from routers.email_actions_router import router as email_actions_router
from routers.role_catalog_router import router as role_catalog_router
from routers.onedrive_router import router as onedrive_router
from routers.linkage_router import router as linkage_router
from routers.advance_router import router as advance_router
from routers.department_master_router import router as department_master_router
from routers.dept_governance_router import router as dept_governance_router
from routers.commercial_router import router as commercial_router
from routers.store_router import router as store_router
from routers.vendor_portal_router import router as vendor_portal_router
from routers.departments_router import router as departments_router
from routers.import_router import router as import_router
from routers.clients_router import router as clients_router
from routers.procurement_router import router as procurement_router
from routers.materials_router import router as materials_router
from routers.bulk_allocation_router import router as bulk_allocation_router
from routers.code_override_router import router as code_override_router
from routers.inventory_intel_router import router as inventory_intel_router
from routers.inventory_master_router import router as inventory_master_router
from routers.inventory_phase2_router import router as inventory_phase2_router
from routers.inventory_phase3_router import router as inventory_phase3_router
from routers.inventory_phase4_router import router as inventory_phase4_router
from routers.inventory_phase5_router import router as inventory_phase5_router
from routers.procurement_intel_router import router as procurement_intel_router
from routers.site_execution_router import router as site_execution_router
from routers.ra_bills_router import router as ra_bills_router
from routers.receivables_router import router as receivables_router

# Accounts module (Iter 71)
from routers.accounts_router import router as accounts_router
from routers.billing_router import router as billing_router
from routers.vendor_billing_router import router as vendor_billing_router
from routers.costing_router import router as costing_router
from routers.closing_router import router as closing_router
from routers.statutory_router import router as statutory_router
from routers.finance_phase2_router import router as finance_phase2_router
from routers.finance_phase3_router import router as finance_phase3_router
from routers.finance_phase4_5_router import router as finance_phase4_5_router
from routers.finance_phase6_router import router as finance_phase6_router
from routers.finance_phase7_router import router as finance_phase7_router
from routers.finance_phase8_router import router as finance_phase8_router
from routers.finance_phase9_router import router as finance_phase9_router
from routers.finance_phase10_router import router as finance_phase10_router
from routers.duplicate_audit_router import router as duplicate_audit_router
from routers.enquiry_followup_and_internal_review_router import router as enquiry_internal_review_router
from routers.telemetry_router import router as telemetry_router
from routers.safety_masters_router import router as safety_masters_router
from routers.safety_hira_jsa_router import router as safety_hira_jsa_router
from routers.safety_plans_docs_dashboard_router import router as safety_plans_docs_dashboard_router
from routers.safety_work_permits_router import router as safety_work_permits_router
from routers.safety_phase2_router import router as safety_phase2_router
from routers.safety_inspections_capa_router import router as safety_inspections_capa_router
from routers.safety_incidents_router import router as safety_incidents_router
from routers.safety_phase4_router import router as safety_phase4_router
from routers.safety_phase5_router import router as safety_phase5_router
from routers.logistics_phase1_router import router as logistics_phase1_router
from routers.logistics_phase2_router import router as logistics_phase2_router
from routers.logistics_phase3_router import router as logistics_phase3_router
from routers.logistics_phase4_router import router as logistics_phase4_router
from routers.logistics_phase5_router import router as logistics_phase5_router


# ─── Ordered include list ───────────────────────────────────────────────────
# Order matters: the first 9 routers MUST be registered before `crud_router`
# because they override the generic CRUD POST/PUT/DELETE paths for their
# resources.  Everything after `crud_router` is order-insensitive.
ROUTERS_IN_ORDER: List[Tuple[str, APIRouter]] = [
    # ── MUST PRECEDE crud_router ──
    ("auth", auth_router),
    ("allocation", allocation_router),
    ("payroll", payroll_router),               # literal /payroll/master|runs|run/*
    ("vendors", vendors_router),               # rich /vendors lifecycle
    ("projects_ops", projects_ops_router),     # Iter 60 — handover
    ("resource_requests", resource_requests_router),
    ("ops_dashboard", ops_dashboard_router),
    ("ops_reports", ops_reports_router),
    ("approvals", approvals_router),           # /approvals/my-revisions
    ("sales", sales_router),                   # overrides /quotations

    # ── Generic CRUD ──
    ("crud", crud_router),

    # ── Order-insensitive feature routers (alphabetical-ish for sanity) ──
    ("admin", admin_router),
    ("admin_projects_dedupe", admin_projects_dedupe_router),
    ("advance", advance_router),
    ("ai_quotation", ai_quotation_router),
    ("billing_defaults", billing_defaults_router),
    ("clients", clients_router),
    ("commercial", commercial_router),
    ("dashboard", dashboard_router),
    ("data_cleanup", data_cleanup_router),
    ("department_master", department_master_router),
    ("departments", departments_router),
    ("dept_governance", dept_governance_router),
    ("email", email_router),
    ("email_actions", email_actions_router),
    ("employees_bulk", employees_bulk_router),
    ("exports", exports_router),
    ("files", files_router),
    ("hr", hr_router),
    ("hr_phase1", hr_phase1_router),
    ("hr_phase2", hr_phase2_router),
    ("hr_phase3", hr_phase3_router),
    ("hr_phase4", hr_phase4_router),
    ("hr_phase5", hr_phase5_router),
    ("import", import_router),
    ("inventory_bulk", inventory_bulk_router),
    ("resource_plan_bulk", resource_plan_bulk_router),
    ("attendance_bulk", attendance_bulk_router),
    ("inventory_intel", inventory_intel_router),
    ("inventory_master", inventory_master_router),
    ("inventory_phase2", inventory_phase2_router),
    ("inventory_phase3", inventory_phase3_router),
    ("inventory_phase4", inventory_phase4_router),
    ("inventory_phase5", inventory_phase5_router),
    ("linkage", linkage_router),
    ("materials", materials_router),
    ("bulk_allocation", bulk_allocation_router),
    ("code_override", code_override_router),
    ("notifications", notifications_router),
    ("onedrive", onedrive_router),
    ("procurement", procurement_router),
    ("procurement_extras", procurement_extras_router),
    ("procurement_intel", procurement_intel_router),
    ("procurement_master", procurement_master_router),
    ("project_dashboard", project_dashboard_router),
    ("projects_ops_masters", projects_ops_masters_router),
    ("projects_ops_phase1", projects_ops_phase1_router),
    ("projects_ops_phase2", projects_ops_phase2_router),
    ("projects_ops_phase2r2", projects_ops_phase2r2_router),
    ("projects_ops_phase3", projects_ops_phase3_router),
    ("projects_ops_phase3b", projects_ops_phase3b_router),
    ("projects_ops_phase3c", projects_ops_phase3c_router),
    ("projects_ops_phase4", projects_ops_phase4_router),
    ("projects_ops_phase5", projects_ops_phase5_router),
    ("projects_ops_workorders", projects_ops_workorders_router),
    ("quotation_builder", quotation_builder_router),
    ("ra_bills", ra_bills_router),
    ("receivables", receivables_router),
    ("role_catalog", role_catalog_router),
    ("site_execution", site_execution_router),
    ("store", store_router),
    ("vendor_portal", vendor_portal_router),

    # ── Accounts module (Iter 71) ──
    ("accounts", accounts_router),
    ("billing", billing_router),
    ("vendor_billing", vendor_billing_router),
    ("costing", costing_router),
    ("closing", closing_router),
    ("statutory", statutory_router),
    ("finance_phase2", finance_phase2_router),
    ("finance_phase3", finance_phase3_router),
    ("finance_phase4_5", finance_phase4_5_router),
    ("finance_phase6", finance_phase6_router),
    ("finance_phase7", finance_phase7_router),
    ("finance_phase8", finance_phase8_router),
    ("finance_phase9", finance_phase9_router),
    ("finance_phase10", finance_phase10_router),
    ("duplicate_audit", duplicate_audit_router),
    ("enquiry_internal_review", enquiry_internal_review_router),
    ("telemetry", telemetry_router),
    # Iter 127 — Safety Foundation
    ("safety_masters", safety_masters_router),
    ("safety_hira_jsa", safety_hira_jsa_router),
    ("safety_plans_docs_dashboard", safety_plans_docs_dashboard_router),
    ("safety_work_permits", safety_work_permits_router),
    ("safety_phase2", safety_phase2_router),
    ("safety_inspections_capa", safety_inspections_capa_router),
    ("safety_incidents", safety_incidents_router),
    ("safety_phase4", safety_phase4_router),
    ("safety_phase5", safety_phase5_router),
    ("logistics_phase1", logistics_phase1_router),
    ("logistics_phase2", logistics_phase2_router),
    ("logistics_phase3", logistics_phase3_router),
    ("logistics_phase4", logistics_phase4_router),
    ("logistics_phase5", logistics_phase5_router),
]


def register_all(api: APIRouter) -> int:
    """Mount every router onto `api` in declared order. Returns the count."""
    for _, router in ROUTERS_IN_ORDER:
        api.include_router(router)
    return len(ROUTERS_IN_ORDER)


def iter_router_names() -> Iterable[str]:
    """Used by health-check endpoints / tests."""
    return (name for name, _ in ROUTERS_IN_ORDER)
