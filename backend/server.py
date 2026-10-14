"""Corporate ERP — FastAPI entrypoint.

Bootstraps environment, MongoDB indexes, sample data, object storage, and
the APScheduler, then mounts all module routers via `routers_registry`.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
import os
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from core import db, client, logger
from rbac import PERMISSIONS  # noqa: F401  (ensures import side effects load early)
from storage import init_storage
from notification_service import email_enabled

# Router mount table (single source of truth for include_router order)
from routers_registry import register_all, ROUTERS_IN_ORDER  # noqa: F401

# Side-effect imports only — these are NOT registered here, the registry
# handles router mounting.  We import the seed/migration/index helpers that
# the on_startup hooks need to call explicitly.
from routers.crud_router import MODULES
from routers.approvals_router import migrate_approvals_chain
from routers.quotation_builder_router import seed_conditions_if_empty, ensure_standard_conditions
from routers.employees_bulk_router import migrate_legacy_bank_fields
from routers.admin_router import load_rbac_overrides_on_startup
from routers.procurement_master_router import seed_master_if_empty
from routers.hr import seed_leave_types_if_empty
from routers.email_router import ensure_email_indexes
from routers.role_catalog_router import ensure_role_catalog_seeded
from routers.onedrive_router import run_push_queue, run_db_backup  # noqa: F401  (used by scheduler)
from routers.advance_router import seed_advance_types_if_empty
from routers.department_master_router import seed_department_master_if_empty
from routers.project_requests_router import backfill_manpower_recruitment, migrate_legacy_resource_requests

from seed import seed_admin, seed_sample_data
from scheduler import start_scheduler, shutdown_scheduler, scheduler_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Corporate ERP API")

# Phase 5.1 — convert PeriodLockedError → 400
from accounting_service import PeriodLockedError as _PLE  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

@app.exception_handler(_PLE)
async def _period_locked_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
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


# Register every router declared in routers_registry.ROUTERS_IN_ORDER.
_registered = register_all(api)
logger.info(f"[routers] Registered {_registered} module routers")


@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.login_attempts.create_index("identifier")
        for _, c in MODULES:
            await db[c].create_index("id", unique=True)
            await db[c].create_index([("created_at", -1)])
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
        try:
            from indexes import ensure_indexes
            await ensure_indexes()
        except Exception as ie:
            logger.warning(f"[indexes] bootstrap skipped: {ie}")
        # Logistics Phase 4 indexes
        try:
            from routers.logistics_phase4_router import _ensure_indexes as _logistics_p4_indexes
            await _logistics_p4_indexes()
        except Exception:
            pass
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
        # Iter 71 — Seed Chart of Accounts (idempotent)
        try:
            from accounting_service import ensure_coa_seeded
            n_coa = await ensure_coa_seeded()
            if n_coa:
                logger.info(f"[accounting] Seeded {n_coa} chart-of-accounts rows")
            await db.chart_of_accounts.create_index("code", unique=True)
            await db.journal_entries.create_index([("source_module", 1), ("source_id", 1), ("source_event", 1)])
            await db.journal_entries.create_index([("date", 1)])
            await db.journal_entries.create_index([("project_id", 1)])
        except Exception as ce:
            logger.warning(f"[accounting] Startup setup skipped: {ce}")
        logger.info(f"ERP backend started. email_enabled={email_enabled()}")
    except Exception as e:
        logger.exception(f"Startup error: {e}")


@app.on_event("startup")
async def backfill_project_managers_on_startup():
    """Idempotent self-heal — syncs PM assignments/names from handovers onto projects."""
    try:
        from routers.projects_ops_router import backfill_project_manager_assignments
        await backfill_project_manager_assignments()
    except Exception as e:
        logger.warning(f"PM assignment backfill failed: {e}")


@app.on_event("startup")
async def seed_quotation_conditions_on_startup():
    """Idempotent — populates the condition library if empty. Runs even if the
    main startup block bailed early on an unrelated index error."""
    try:
        n = await seed_conditions_if_empty()
        if n:
            logger.info(f"[quotation-builder] Seeded {n} condition library entries")
        m = await ensure_standard_conditions()
        if m:
            logger.info(f"[quotation-builder] Added {m} standard technical conditions to library")
        b = await migrate_legacy_bank_fields()
        if b:
            logger.info(f"[employees] Migrated legacy bank fields on {b} employee records")
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
    try:
        from approval_policy import clear_removed_service_approvals, reroute_pending_fuel_requests, ensure_fuel_approver_permissions
        await clear_removed_service_approvals()
        await reroute_pending_fuel_requests()
        await ensure_fuel_approver_permissions()
    except Exception as e:
        logger.warning(f"[approval-policy] Cleanup skipped: {e}")
    try:
        from head_office_project import ensure_head_office_project
        if await ensure_head_office_project():
            logger.info("[head-office] Seeded 'Head Office – Delhi' internal project (HEAD-OFFICE)")
    except Exception as e:
        logger.warning(f"[head-office] Seed skipped: {e}")
    try:
        n_mig = await migrate_legacy_resource_requests()
        if n_mig:
            logger.info(f"[legacy-rr-migration] Migrated {n_mig} legacy resource request(s) to Project Requests")
    except Exception as e:
        logger.warning(f"[legacy-rr-migration] skipped: {e}")
    try:
        n_bf = await backfill_manpower_recruitment()
        if n_bf:
            logger.info(f"[recruitment-backfill] Raised recruitment for {n_bf} approved manpower request(s)")
    except Exception as e:
        logger.warning(f"[recruitment-backfill] skipped: {e}")
    try:
        from routers.safety_masters_router import seed_safety_masters
        result = await seed_safety_masters()
        if any(result.values()):
            logger.info(f"[safety-masters] Seeded {result}")
    except Exception as e:
        logger.warning(f"[safety-masters] Seed skipped: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    shutdown_scheduler()
    client.close()


app.include_router(api)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
