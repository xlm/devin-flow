from fastapi import APIRouter

from devin_flow.api import canvas, devin, health, invocations

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(devin.router)
router.include_router(canvas.router)
router.include_router(invocations.router)
