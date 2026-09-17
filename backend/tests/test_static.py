from pathlib import Path

from fastapi.testclient import TestClient

from devin_flow_backend.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return TestClient(create_app(static_dir=tmp_path))


def test_index_served_at_root(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/").text == "<html>spa</html>"


def test_spa_fallback_serves_index(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/some/route").text == "<html>spa</html>"


def test_assets_served(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert response.text == "console.log(1)"


def test_unknown_api_route_is_404(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/api/nope").status_code == 404
