from pathlib import Path

from fastapi import FastAPI

from devin_flow import api, web
from devin_flow.config import Settings

STATIC_DIR = Settings().static_dir


def create_app(static_dir: Path = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="devin-flow")
    app.include_router(api.router)
    web.spa.mount_spa(app, static_dir)
    return app
