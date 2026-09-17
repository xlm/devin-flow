import os
from pathlib import Path

from fastapi import FastAPI

from devin_flow import api, web

STATIC_DIR = Path(
    os.environ.get(
        "STATIC_DIR", Path(__file__).resolve().parents[3] / "frontend" / "dist"
    )
)


def create_app(static_dir: Path = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="devin-flow")
    app.include_router(api.router)
    web.spa.mount_spa(app, static_dir)
    return app
