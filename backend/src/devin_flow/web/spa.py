from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.routing import Match, Route
from starlette.types import Scope


def is_api_path(path: str) -> bool:
    return path == "api" or path.startswith("api/")


class SpaRoute(Route):
    # never match /api/* so unknown api paths fall through to Starlette's 404
    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope = super().matches(scope)
        if match is not Match.NONE and is_api_path(
            child_scope["path_params"]["full_path"]
        ):
            return Match.NONE, {}
        return match, child_scope


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    if not static_dir.is_dir():
        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    if (static_dir / "index.html").is_file():
        root = static_dir.resolve()

        async def spa(request: Request) -> FileResponse:
            full_path: str = request.path_params["full_path"]
            # every file served by the fallback must resolve inside static_dir
            candidate = (root / full_path).resolve()
            if full_path and candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

        app.router.routes.append(
            SpaRoute(
                "/{full_path:path}",
                spa,
                methods=["GET", "HEAD"],
                include_in_schema=False,
            )
        )
