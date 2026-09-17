import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import devin_flow.app
from devin_flow.app import create_app


@pytest.fixture
def reload_app_module() -> Iterator[None]:
    yield
    importlib.reload(devin_flow.app)


@pytest.mark.usefixtures("reload_app_module")
def test_static_dir_env_var_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    module = importlib.reload(devin_flow.app)
    assert tmp_path == module.STATIC_DIR


@pytest.mark.usefixtures("reload_app_module")
def test_static_dir_defaults_to_frontend_dist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STATIC_DIR", raising=False)
    module = importlib.reload(devin_flow.app)
    assert module.STATIC_DIR.parts[-2:] == ("frontend", "dist")


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
