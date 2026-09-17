from pathlib import Path

from fastapi.testclient import TestClient

from devin_flow.app import create_app


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
    assert client.get("/api/nope").status_code == 404
