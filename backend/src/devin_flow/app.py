from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from devin_flow import api, web
from devin_flow.config import Settings
from devin_flow.devin.client import DevinNotConfiguredError

STATIC_DIR = Settings().static_dir


def handle_devin_not_configured(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def create_app(static_dir: Path = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="devin-flow")
    app.add_exception_handler(DevinNotConfiguredError, handle_devin_not_configured)
    app.include_router(api.router)
    web.spa.mount_spa(app, static_dir)
    return app
