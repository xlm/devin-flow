from fastapi import APIRouter

from devin_flow.api import health

router = APIRouter(prefix="/api")
router.include_router(health.router)
