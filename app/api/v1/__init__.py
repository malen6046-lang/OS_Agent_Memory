"""API v1 router composition."""

from fastapi import APIRouter

from .evaluations import router as evaluations_router
from .events import router as events_router
from .forget import router as forget_router
from .health import router as health_router
from .memory import router as memory_router


router = APIRouter()
router.include_router(health_router)
router.include_router(events_router)
router.include_router(memory_router)
router.include_router(forget_router)
router.include_router(evaluations_router)
