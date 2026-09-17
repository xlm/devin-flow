from pathlib import Path

from fastapi.testclient import TestClient

from devin_flow.app import create_app


def test_health(tmp_path: Path) -> None:
    client = TestClient(create_app(static_dir=tmp_path))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
