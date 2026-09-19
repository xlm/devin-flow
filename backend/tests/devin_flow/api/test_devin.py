from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from devin_flow.app import create_app
from devin_flow.config import get_settings
from devin_flow.devin import get_devin_client
from devin_flow.devin.client import DevinClient


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DEVIN_API_BASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    get_devin_client.cache_clear()


def make_client(
    tmp_path: Path,
    handler: httpx.BaseTransport,
) -> tuple[TestClient, DevinClient]:
    upstream = DevinClient(
        httpx.Client(transport=handler, base_url="https://devin.example"),
        "org-test",
    )
    app = create_app(static_dir=tmp_path)
    app.dependency_overrides[get_devin_client] = lambda: upstream
    return TestClient(app), upstream


def test_list_sessions_proxies_response_and_limit(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/organizations/org-test/sessions"
        assert request.url.params["first"] == "4"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "session_id": "session-1",
                        "status": "running",
                        "title": "Title",
                    }
                ]
            },
        )

    client, upstream = make_client(tmp_path, httpx.MockTransport(handler))
    response = client.get("/api/devin/sessions?limit=4")
    assert response.status_code == 200
    assert response.json() == [
        {
            "session_id": "session-1",
            "status": "running",
            "title": "Title",
            "url": None,
            "automation_id": None,
            "pull_requests": [],
            "structured_output": None,
            "created_at": None,
            "updated_at": None,
        }
    ]
    upstream.http.close()


def test_list_playbooks_maps_two_pages(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/organizations/org-test/playbooks"
        if len(requests) == 1:
            assert request.url.params["first"] == "100"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "playbook_id": "pb-1",
                            "title": "Triage",
                            "body": "body",
                        }
                    ],
                    "has_next_page": True,
                    "end_cursor": "cursor-1",
                },
            )
        assert request.url.params["after"] == "cursor-1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "playbook_id": "pb-2",
                        "title": "Deploy",
                        "body": "body",
                    }
                ],
                "has_next_page": False,
            },
        )

    client, upstream = make_client(tmp_path, httpx.MockTransport(handler))
    response = client.get("/api/devin/playbooks")
    assert response.status_code == 200
    assert response.json() == [
        {"id": "pb-1", "title": "Triage"},
        {"id": "pb-2", "title": "Deploy"},
    ]
    upstream.http.close()


def test_list_playbooks_maps_upstream_failure_without_secret(
    tmp_path: Path,
) -> None:
    secret = "secret-string"
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(
            lambda request: httpx.Response(
                500, text=f"Authorization: Bearer test-token {secret}"
            )
        ),
    )
    response = client.get("/api/devin/playbooks")
    assert response.status_code == 502
    assert response.json() == {"detail": "devin api returned HTTP 500"}
    assert "test-token" not in response.text
    assert secret not in response.text
    upstream.http.close()


def test_list_playbooks_maps_unreachable_upstream(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client, upstream = make_client(tmp_path, httpx.MockTransport(handler))
    response = client.get("/api/devin/playbooks")
    assert response.status_code == 502
    assert response.json() == {"detail": "devin api unreachable"}
    upstream.http.close()


def test_create_session_proxies_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/organizations/org-test/sessions"
        assert request.read() == b'{"prompt":"Build it"}'
        return httpx.Response(
            200,
            json={
                "session_id": "session-2",
                "url": "https://devin.example/session-2",
                "status": "running",
                "title": "Title",
            },
        )

    client, upstream = make_client(tmp_path, httpx.MockTransport(handler))
    response = client.post("/api/devin/sessions", json={"prompt": "Build it"})
    assert response.status_code == 201
    assert response.json() == {
        "session_id": "session-2",
        "url": "https://devin.example/session-2",
        "status": "running",
        "title": "Title",
        "automation_id": None,
        "pull_requests": [],
        "structured_output": None,
        "created_at": None,
        "updated_at": None,
    }
    upstream.http.close()


def test_list_sessions_maps_upstream_failure_to_502(tmp_path: Path) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(500, text="server error")),
    )
    response = client.get("/api/devin/sessions")
    assert response.status_code == 502
    assert response.json() == {"detail": "devin api returned HTTP 500"}
    upstream.http.close()


def test_list_repositories_proxies_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3beta1/organizations/org-test/repositories"
        return httpx.Response(
            200,
            json={"items": [{"repo_path": "octo/repo", "repo_name": "repo"}]},
        )

    client, upstream = make_client(tmp_path, httpx.MockTransport(handler))
    response = client.get("/api/devin/repositories")
    assert response.status_code == 200
    assert response.json() == [{"repo_path": "octo/repo", "repo_name": "repo"}]
    upstream.http.close()


def test_list_repositories_maps_upstream_failure_to_502(tmp_path: Path) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(500, text="server error")),
    )
    response = client.get("/api/devin/repositories")
    assert response.status_code == 502
    assert response.json() == {"detail": "devin api returned HTTP 500"}
    upstream.http.close()


def test_create_session_maps_upstream_failure_to_502(tmp_path: Path) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized")),
    )
    response = client.post("/api/devin/sessions", json={"prompt": "Build it"})
    assert response.status_code == 502
    assert response.json() == {"detail": "devin api returned HTTP 401"}
    upstream.http.close()


def test_upstream_failure_does_not_expose_token(tmp_path: Path) -> None:
    token = "secret-token"
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(
            lambda request: httpx.Response(500, text=f"Authorization: Bearer {token}")
        ),
    )
    response = client.get("/api/devin/sessions")
    assert response.status_code == 502
    assert token not in response.text
    assert response.json() == {"detail": "devin api returned HTTP 500"}
    upstream.http.close()


def test_repository_upstream_failure_does_not_expose_token(tmp_path: Path) -> None:
    token = "secret-token"
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(
            lambda request: httpx.Response(500, text=f"Authorization: Bearer {token}")
        ),
    )
    response = client.get("/api/devin/repositories")
    assert response.status_code == 502
    assert token not in response.text
    assert response.json() == {"detail": "devin api returned HTTP 500"}
    upstream.http.close()


def test_non_tls_remote_base_url_returns_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVIN_API_TOKEN", "secret")
    monkeypatch.setenv("DEVIN_API_BASE_URL", "http://api.devin.ai/v3")
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    response = TestClient(create_app(static_dir=tmp_path)).get("/api/devin/sessions")
    assert response.status_code == 503
    assert response.json() == {"detail": "DEVIN_API_BASE_URL must use https"}


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_validation_returns_422(tmp_path: Path, limit: int) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(200, json={"items": []})),
    )
    response = client.get(f"/api/devin/sessions?limit={limit}")
    assert response.status_code == 422
    upstream.http.close()


def test_oversized_prompt_returns_422(tmp_path: Path) -> None:
    client, upstream = make_client(
        tmp_path,
        httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    response = client.post(
        "/api/devin/sessions",
        json={"prompt": "x" * 20_001},
    )
    assert response.status_code == 422
    upstream.http.close()
