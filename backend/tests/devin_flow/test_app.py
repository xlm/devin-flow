import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from devin_flow.app import create_app
from devin_flow.config import DEFAULT_STATIC_DIR, get_settings
from devin_flow.web import spa


def test_static_dir_env_var_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("<html>spa</html>")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    response = TestClient(create_app()).get("/")
    assert response.status_code == 200
    assert response.text == "<html>spa</html>"


def test_static_dir_defaults_to_frontend_dist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STATIC_DIR", raising=False)
    get_settings.cache_clear()
    mounted: list[Path] = []

    def mount_spa(_app: FastAPI, static_dir: Path) -> None:
        mounted.append(static_dir)

    monkeypatch.setattr(spa, "mount_spa", mount_spa)
    create_app()
    assert mounted == [DEFAULT_STATIC_DIR]


def test_root_is_404_without_static_dir(tmp_path: Path) -> None:
    client = TestClient(create_app(static_dir=tmp_path / "missing"))
    response = client.get("/")
    assert response.status_code == 404


def test_no_spa_fallback_without_index_html(tmp_path: Path) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "app.js").write_text("console.log(1)")
    client = TestClient(create_app(static_dir=static_dir))
    assert client.get("/").status_code == 404
    assert client.get("/foo").status_code == 404
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_api_route_is_404(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>spa</html>")
    client = TestClient(create_app(static_dir=tmp_path))
    for method in ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]:
        for path in ["/api/nope", "/api"]:
            response = client.request(method, path)
            assert response.status_code == 404, (method, path)


def test_existing_api_route_keeps_405_for_wrong_method(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>spa</html>")
    client = TestClient(create_app(static_dir=tmp_path))
    assert client.post("/api/health").status_code == 405


def test_lifespan_starts_poller_when_interval_positive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devin_flow import app as app_module

    started: list[float] = []

    async def fake_poll_forever(interval_seconds: float) -> None:
        started.append(interval_seconds)
        await asyncio.Event().wait()

    monkeypatch.setattr(app_module, "poll_forever", fake_poll_forever)
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "5")
    get_settings.cache_clear()
    with TestClient(create_app(static_dir=tmp_path)) as client:
        assert client.get("/api/health").status_code == 200
    assert started == [5]


def test_lifespan_skips_poller_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devin_flow import app as app_module

    def fail(_interval: float) -> None:
        raise AssertionError("poller must not start")

    monkeypatch.setattr(app_module, "poll_forever", fail)
    with TestClient(create_app(static_dir=tmp_path)) as client:
        assert client.get("/api/health").status_code == 200
