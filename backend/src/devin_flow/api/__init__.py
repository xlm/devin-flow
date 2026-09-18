from fastapi import APIRouter

from devin_flow.api import health, items

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(items.router)
