from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

API_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    if not static_dir.is_dir():
        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    if (static_dir / "index.html").is_file():
        root = static_dir.resolve()

        def api_path_owned(request: Request) -> bool:
            # a sibling route matches the path but not this method -> 405
            for route in request.app.routes:
                if getattr(route, "endpoint", None) is spa:
                    continue
                match, _ = route.matches(request.scope)
                if match is not Match.NONE:
                    return True
            return False

        async def spa(request: Request) -> Response:
            full_path: str = request.path_params["full_path"]
            # keep unknown /api/* paths as 404 instead of index.html
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=405 if api_path_owned(request) else 404)
            if request.method not in {"GET", "HEAD"}:
                raise HTTPException(status_code=405)
            # every file served by the fallback must resolve inside static_dir
            candidate = (root / full_path).resolve()
            if full_path and candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

        # methods=None would default to GET only; list all so /api/* never
        # partial-matches into a 405
        app.add_route(
            "/{full_path:path}",
            spa,
            methods=API_METHODS,
            include_in_schema=False,
        )
