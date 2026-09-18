from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from devin_flow.app import create_app
from devin_flow.config import get_settings
from devin_flow.devin import get_devin_client
from devin_flow.devin.client import DevinClient


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.delenv("DEVIN_API_TOKEN", raising=False)
    monkeypatch.delenv("DEVIN_API_BASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    get_devin_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_devin_client.cache_clear()


def make_client(
    tmp_path: Path,
    handler: httpx.BaseTransport,
) -> tuple[TestClient, DevinClient]:
    upstream = DevinClient(
        httpx.Client(transport=handler, base_url="https://devin.example/v1")
    )
    app = create_app(static_dir=tmp_path)
    app.dependency_overrides[get_devin_client] = lambda: upstream
    return TestClient(app), upstream


def test_list_sessions_proxies_response_and_limit(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/sessions"
        assert request.url.params["limit"] == "4"
        return httpx.Response(
            200,
            json={
                "sessions": [
                    {
                        "session_id": "session-1",
                        "status": "working",
                        "title": "Title",
                    }
                ]
            },
        )

    client, upstream = make_client(tmp_path, httpx.MockTransport(handler))
    response = client.get("/api/devin/sessions?limit=4")
    assert response.status_code == 200
    assert response.json() == [
        {"session_id": "session-1", "status": "working", "title": "Title", "url": None}
    ]
    upstream.http.close()


def test_create_session_proxies_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/sessions"
        assert request.read() == b'{"prompt":"Build it"}'
        return httpx.Response(
            200,
            json={"session_id": "session-2", "status": "queued"},
        )

    client, upstream = make_client(tmp_path, httpx.MockTransport(handler))
    response = client.post("/api/devin/sessions", json={"prompt": "Build it"})
    assert response.status_code == 201
    assert response.json() == {
        "session_id": "session-2",
        "status": "queued",
        "title": None,
        "url": None,
    }
    upstream.http.close()


def test_list_sessions_maps_upstream_failure_to_502(tmp_path: Path) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(500, text="server error")),
    )
    response = client.get("/api/devin/sessions")
    assert response.status_code == 502
    assert response.json() == {"detail": "server error"}
    upstream.http.close()


def test_create_session_maps_upstream_failure_to_502(tmp_path: Path) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized")),
    )
    response = client.post("/api/devin/sessions", json={"prompt": "Build it"})
    assert response.status_code == 502
    assert response.json() == {"detail": "unauthorized"}
    upstream.http.close()


def test_missing_token_returns_503(tmp_path: Path) -> None:
    response = TestClient(create_app(static_dir=tmp_path)).get("/api/devin/sessions")
    assert response.status_code == 503
    assert response.json() == {"detail": "DEVIN_API_TOKEN is not set"}


@pytest.mark.parametrize("limit", [0, 101])
def test_limit_validation_returns_422(tmp_path: Path, limit: int) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(200, json={"sessions": []})),
    )
    response = client.get(f"/api/devin/sessions?limit={limit}")
    assert response.status_code == 422
    upstream.http.close()
