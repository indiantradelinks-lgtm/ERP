"""Corporate ERP — FastAPI entrypoint.

Bootstraps environment, MongoDB indexes, sample data, object storage, and
the APScheduler, then registers all module routers under `/api`.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from core import db, client, logger
from rbac import PERMISSIONS  # noqa: F401  (ensures import side effects load early)
from storage import init_storage
from notification_service import email_enabled

from routers.crud_router import router as crud_router, MODULES
from routers.auth_router import router as auth_router
from routers.approvals_router import router as approvals_router, migrate_approvals_chain
from routers.files_router import router as files_router
from routers.notifications_router import router as notifications_router
from routers.exports_router import router as exports_router
from routers.dashboard_router import router as dashboard_router
from routers.admin_router import router as admin_router
from routers.sales_router import router as sales_router
from routers.store_router import router as store_router
from routers.vendor_portal_router import router as vendor_portal_router
from routers.departments_router import router as departments_router
from routers.import_router import router as import_router
from routers.allocation_router import router as allocation_router
from routers.clients_router import router as clients_router
from routers.procurement_router import router as procurement_router
from routers.materials_router import router as materials_router
from routers.inventory_intel_router import router as inventory_intel_router
from routers.procurement_intel_router import router as procurement_intel_router
from routers.site_execution_router import router as site_execution_router
from routers.ra_bills_router import router as ra_bills_router
from routers.receivables_router import router as receivables_router
from routers.commercial_router import router as commercial_router
from routers.billing_defaults_router import router as billing_defaults_router
from routers.quotation_builder_router import router as quotation_builder_router, seed_conditions_if_empty
from routers.ai_quotation_router import router as ai_quotation_router
from routers.admin_router import load_rbac_overrides_on_startup
from routers.project_dashboard_legacy_router import router as project_dashboard_router
from routers.procurement_master_router import router as procurement_master_router, seed_master_if_empty
from routers.data_cleanup_router import router as data_cleanup_router
from routers.hr import router as hr_router, seed_leave_types_if_empty
from routers.email_router import router as email_router, ensure_email_indexes
from routers.email_actions_router import router as email_actions_router
from routers.role_catalog_router import router as role_catalog_router, ensure_role_catalog_seeded
from routers.onedrive_router import router as onedrive_router, run_push_queue, run_db_backup
from routers.linkage_router import router as linkage_router
from routers.advance_router import router as advance_router, seed_advance_types_if_empty
from routers.department_master_router import router as department_master_router, seed_department_master_if_empty
from routers.dept_governance_router import router as dept_governance_router
from routers.payroll_router import router as payroll_router
from routers.vendors_router import router as vendors_router
from routers.projects_ops_router import router as projects_ops_router
from routers.resource_requests_router import router as resource_requests_router
from routers.ops_dashboard_router import router as ops_dashboard_router
from routers.ops_reports_router import router as ops_reports_router

from seed import seed_admin, seed_sample_data
from scheduler import start_scheduler, shutdown_scheduler, scheduler_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Corporate ERP API")
api = APIRouter(prefix="/api")


# Iter 63 — Universal Approval Documents Gate: turn the helper exception
# raised by approval_engine.insert_approval() into a clean 400.
from fastapi import Request as _FRequest
from fastapi.responses import JSONResponse as _JSONResponse
from approval_engine import ApprovalDocumentsRequired as _ADR

@app.exception_handler(_ADR)
async def _approval_docs_required_handler(request: _FRequest, exc: _ADR):
    return _JSONResponse(status_code=400, content={"detail": str(exc)})


@api.get("/")
async def root():
    return {"service": "Corporate ERP API", "version": "1.1.0"}


@api.get("/scheduler/status")
async def get_scheduler_status():
    return scheduler_status()


# Register module routers
api.include_router(auth_router)
api.include_router(allocation_router)
api.include_router(payroll_router)   # MUST be before crud_router — literal /payroll/master|runs|run/* routes
api.include_router(vendors_router)    # MUST be before crud_router — dedicated /vendors with rich lifecycle
api.include_router(projects_ops_router)  # Iter 60 — Projects & Operations Workflow (Sales→PM handover)
api.include_router(resource_requests_router)  # Iter 61 Phase 2 — Resource Requests
api.include_router(ops_dashboard_router)      # Iter 61 Phase 3 — Project ops dashboard + P&L
api.include_router(ops_reports_router)        # Iter 61 Phase 4 — Reports (13 kinds)
api.include_router(approvals_router) # MUST be before crud_router — /approvals/my-revisions etc.
api.include_router(sales_router)     # MUST be before crud_router — overrides /quotations POST/PUT/status
api.include_router(crud_router)
api.include_router(files_router)
api.include_router(notifications_router)
api.include_router(exports_router)
api.include_router(dashboard_router)
api.include_router(admin_router)
api.include_router(billing_defaults_router)
api.include_router(quotation_builder_router)
api.include_router(ai_quotation_router)
api.include_router(project_dashboard_router)
api.include_router(procurement_master_router)
api.include_router(data_cleanup_router)
api.include_router(hr_router)
api.include_router(email_router)
api.include_router(email_actions_router)
api.include_router(role_catalog_router)
api.include_router(onedrive_router)
api.include_router(linkage_router)
api.include_router(advance_router)
api.include_router(department_master_router)
api.include_router(dept_governance_router)
api.include_router(commercial_router)
# sales_router moved above crud_router (registered earlier) so /quotations overrides apply
api.include_router(store_router)
api.include_router(vendor_portal_router)
api.include_router(departments_router)
api.include_router(import_router)
api.include_router(clients_router)
api.include_router(procurement_router)
api.include_router(materials_router)
api.include_router(inventory_intel_router)
api.include_router(procurement_intel_router)
api.include_router(site_execution_router)
api.include_router(ra_bills_router)
api.include_router(receivables_router)


@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.login_attempts.create_index("identifier")
        for _, c in MODULES:
            await db[c].create_index("id", unique=True)
        await db.files.create_index("id", unique=True)
        await db.files.create_index([("parent_type", 1), ("parent_id", 1)])
        await db.audit_logs.create_index("ts")
        await db.audit_logs.create_index([("resource", 1), ("record_id", 1)])
        await db.audit_logs.create_index("actor_id")
        await db.login_activity.create_index("at")
        await db.dropdown_options.create_index([("category", 1), ("order", 1)])
        await db.approval_chains.create_index("type", unique=True)
        await db.enquiries.create_index("id", unique=True)
        await db.enquiries.create_index("enquiry_no")
        await db.orders.create_index("id", unique=True)
        await db.orders.create_index("order_no")
        await db.quotations.create_index([("root_id", 1), ("revision_no", 1)])
        await db.inventory_transactions.create_index("item_id")
        await db.inventory_transactions.create_index("txn_no")
        await db.vendor_invoices.create_index("vendor_id")
        await db.vendor_evaluations.create_index("vendor_id")
        await db.employee_history.create_index([("employee_id", 1), ("at", -1)])
        await db.employees.create_index("employee_id")
        await db.sites.create_index([("client_id", 1), ("site_code", 1)])
        try:
            await db.sites.create_index(
                "gst", unique=True,
                partialFilterExpression={"gst": {"$type": "string", "$gt": ""}},
            )
        except Exception as ie:
            logger.warning(f"sites.gst partial index skipped: {ie}")
        await db.client_contacts.create_index("site_id")
        await db.client_contacts.create_index("client_id")
        # Backfill: legacy clients (seeded before customer_code existed)
        # get a system-generated code so they show up in the tree view.
        legacy = await db.clients.find(
            {"$or": [{"customer_code": {"$exists": False}}, {"customer_code": None}, {"customer_code": ""}]},
            {"_id": 0, "id": 1, "code": 1, "name": 1},
        ).to_list(500)
        if legacy:
            from routers.clients_router import _next_customer_code
            for c in legacy:
                code = c.get("code") or await _next_customer_code()
                await db.clients.update_one(
                    {"id": c["id"]},
                    {"$set": {"customer_code": code, "code": code}},
                )
        # Generic CRUD on /api/clients (collection 'clients') now coexists with the
        # hierarchical /api/clients-tree router. The generic POST/PUT routes are
        # registered first via make_crud — that's fine, our richer router only
        # overrides /clients (POST/PUT/DELETE for parent), /clients/{id}/sites,
        # /sites/{id}, /sites, /sites/{id}/contacts, /contacts/{id}, etc.
        # Backfill: copy legacy single `department` -> `departments[]` array.
        await db.employees.update_many(
            {"department": {"$exists": True, "$nin": [None, ""]},
             "departments": {"$exists": False}},
            [{"$set": {"departments": ["$department"]}}],
        )
        await seed_admin()
        await seed_sample_data()
        await migrate_approvals_chain()
        try:
            n_cond = await seed_conditions_if_empty()
            if n_cond:
                logger.info(f"Seeded {n_cond} quotation condition library entries")
        except Exception as ce:
            logger.warning(f"Condition library seed skipped: {ce}")
        init_storage()
        start_scheduler()
        logger.info(f"ERP backend started. email_enabled={email_enabled()}")
    except Exception as e:
        logger.exception(f"Startup error: {e}")


@app.on_event("startup")
async def seed_quotation_conditions_on_startup():
    """Idempotent — populates the condition library if empty. Runs even if the
    main startup block bailed early on an unrelated index error."""
    try:
        n = await seed_conditions_if_empty()
        if n:
            logger.info(f"[quotation-builder] Seeded {n} condition library entries")
    except Exception as e:
        logger.warning(f"[quotation-builder] Condition seed skipped: {e}")
    try:
        loaded = await load_rbac_overrides_on_startup()
        logger.info(f"[rbac] Loaded {loaded} role-register override entries")
    except Exception as e:
        logger.warning(f"[rbac] Override load skipped: {e}")
    try:
        n_cat = await seed_master_if_empty()
        if n_cat:
            logger.info(f"[procurement-master] Seeded {n_cat} default categories")
    except Exception as e:
        logger.warning(f"[procurement-master] Category seed skipped: {e}")
    try:
        n_lt = await seed_leave_types_if_empty()
        if n_lt:
            logger.info(f"[hr] Seeded {n_lt} default leave types")
    except Exception as e:
        logger.warning(f"[hr] Leave type seed skipped: {e}")
    try:
        await ensure_email_indexes()
        logger.info("[email] Outbox indexes ensured")
    except Exception as e:
        logger.warning(f"[email] Index ensure skipped: {e}")
    try:
        n_roles = await ensure_role_catalog_seeded()
        if n_roles:
            logger.info(f"[role-catalog] Seeded {n_roles} built-in roles")
    except Exception as e:
        logger.warning(f"[role-catalog] Seed skipped: {e}")
    try:
        n_types = await seed_advance_types_if_empty()
        if n_types:
            logger.info(f"[advance-types] Seeded {n_types} default advance types")
    except Exception as e:
        logger.warning(f"[advance-types] Seed skipped: {e}")
    try:
        n_depts = await seed_department_master_if_empty()
        if n_depts:
            logger.info(f"[department-master] Seeded {n_depts} default departments")
    except Exception as e:
        logger.warning(f"[department-master] Seed skipped: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    shutdown_scheduler()
    client.close()


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
