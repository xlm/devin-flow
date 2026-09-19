from fastapi import APIRouter

from devin_flow.api import devin, health

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(devin.router)
