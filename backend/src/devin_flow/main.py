import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC_DIR = Path(
    os.environ.get(
        "STATIC_DIR", Path(__file__).resolve().parents[3] / "frontend" / "dist"
    )
)


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(static_dir: Path = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="devin-flow")
    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    app.include_router(api)

    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        if (static_dir / "index.html").is_file():
            root = static_dir.resolve()

            @app.get("/{full_path:path}", include_in_schema=False)
            def spa(full_path: str) -> FileResponse:
                # keep unknown /api/* paths as 404 instead of index.html
                if full_path == "api" or full_path.startswith("api/"):
                    raise HTTPException(status_code=404)
                # every file served by the fallback must resolve inside static_dir
                candidate = (root / full_path).resolve()
                if full_path and candidate.is_relative_to(root) and candidate.is_file():
                    return FileResponse(candidate)
                return FileResponse(root / "index.html")

    return app


app = create_app()
