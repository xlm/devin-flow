from math import isfinite
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from devin_flow import api, web
from devin_flow.config import get_settings
from devin_flow.devin.client import DevinNotConfiguredError


def handle_devin_not_configured(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def handle_request_validation(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = []
    for error in exc.errors():
        value = error.get("input")
        if isinstance(value, float) and not isfinite(value):
            error = {**error, "input": str(value)}
        context = error.get("ctx")
        if isinstance(context, dict):
            error = {
                **error,
                "ctx": {
                    key: str(value) if isinstance(value, Exception) else value
                    for key, value in context.items()
                },
            }
        details.append(error)
    return JSONResponse(status_code=422, content={"detail": details})


def create_app(static_dir: Path | None = None) -> FastAPI:
    if static_dir is None:
        static_dir = get_settings().static_dir
    app = FastAPI(title="devin-flow")
    app.add_exception_handler(DevinNotConfiguredError, handle_devin_not_configured)
    app.add_exception_handler(RequestValidationError, handle_request_validation)
    app.include_router(api.router)
    web.spa.mount_spa(app, static_dir)
    return app
