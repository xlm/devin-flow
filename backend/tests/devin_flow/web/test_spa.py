from pathlib import Path

from fastapi.testclient import TestClient

from devin_flow.app import create_app


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


def test_nested_file_served(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "file.txt").write_text("nested content")
    client = make_client(tmp_path)
    response = client.get("/nested/file.txt")
    assert response.status_code == 200
    assert response.text == "nested content"


def make_escape_client(tmp_path: Path) -> TestClient:
    # guard tests: static dir lives next to a secret it must never serve
    (tmp_path / "secret.txt").write_text("SECRET-DATA")
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>spa</html>")
    return TestClient(create_app(static_dir=static_dir))


def assert_secret_not_served(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code in {200, 404}
    assert "SECRET-DATA" not in response.text


def test_dotdot_traversal_blocked(tmp_path: Path) -> None:
    client = make_escape_client(tmp_path)
    for path in [
        "/../secret.txt",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/assets/../../secret.txt",
        "/nested/../../secret.txt",
    ]:
        assert_secret_not_served(client, path)


def test_symlink_escape_blocked(tmp_path: Path) -> None:
    client = make_escape_client(tmp_path)
    (tmp_path / "dist" / "leak.txt").symlink_to(tmp_path / "secret.txt")
    assert_secret_not_served(client, "/leak.txt")


def test_head_serves_index(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.head("/").status_code == 200


def test_non_get_on_spa_path_is_405(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post("/some/route")
    assert response.status_code == 405
    assert "<html>spa</html>" not in response.text
