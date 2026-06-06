"""HR module — aggregates the 5 sub-routers under /api/hr."""
from fastapi import APIRouter

from .onboarding import router as onboarding_router
from .employee360 import router as employee360_router
from .leave import router as leave_router, seed_leave_types_if_empty
from .letters import router as letters_router
from .exit_fnf import router as exit_router
from .documents import router as documents_router

router = APIRouter(prefix="/hr", tags=["hr"])
router.include_router(onboarding_router)
router.include_router(employee360_router)
router.include_router(leave_router)
router.include_router(letters_router)
router.include_router(exit_router)
router.include_router(documents_router)

__all__ = ["router", "seed_leave_types_if_empty"]
