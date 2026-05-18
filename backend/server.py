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

from seed import seed_admin, seed_sample_data
from scheduler import start_scheduler, shutdown_scheduler, scheduler_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Corporate ERP API")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "Corporate ERP API", "version": "1.1.0"}


@api.get("/scheduler/status")
async def get_scheduler_status():
    return scheduler_status()


# Register module routers
api.include_router(auth_router)
api.include_router(crud_router)
api.include_router(approvals_router)
api.include_router(files_router)
api.include_router(notifications_router)
api.include_router(exports_router)
api.include_router(dashboard_router)


@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.login_attempts.create_index("identifier")
        for _, c in MODULES:
            await db[c].create_index("id", unique=True)
        await db.files.create_index("id", unique=True)
        await db.files.create_index([("parent_type", 1), ("parent_id", 1)])
        await seed_admin()
        await seed_sample_data()
        await migrate_approvals_chain()
        init_storage()
        start_scheduler()
        logger.info(f"ERP backend started. email_enabled={email_enabled()}")
    except Exception as e:
        logger.exception(f"Startup error: {e}")


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
