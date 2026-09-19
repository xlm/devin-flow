from fastapi import APIRouter

from devin_flow.api import action_nodes, canvas, devin, health, invocations, outcomes

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(devin.router)
router.include_router(canvas.router)
router.include_router(invocations.router)
router.include_router(outcomes.router)
router.include_router(action_nodes.router)
