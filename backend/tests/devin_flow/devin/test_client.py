from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from devin_flow.config import get_settings
from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import (
    DevinNotConfiguredError,
    DevinSession,
    DevinUpstreamError,
    SessionCreate,
    SessionCreated,
    create_client,
)


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


@pytest.mark.parametrize("token", [None, ""])
def test_create_client_requires_token(token: str | None) -> None:
    settings = get_settings().model_copy(update={"devin_api_token": token})
    with pytest.raises(DevinNotConfiguredError, match="DEVIN_API_TOKEN is not set"):
        create_client(settings)


def test_create_client_configures_base_url_and_authorization() -> None:
    client = create_client(
        get_settings().model_copy(
            update={
                "devin_api_token": "secret",
                "devin_api_base_url": "https://devin.example/v1",
            }
        )
    )
    assert client.http.base_url == httpx.URL("https://devin.example/v1/")
    assert client.http.headers["Authorization"] == "Bearer secret"
    client.http.close()


def make_client(
    handler: httpx.BaseTransport,
) -> DevinClient:
    return DevinClient(
        httpx.Client(transport=handler, base_url="https://devin.example/v1")
    )


def test_list_sessions_parses_response_and_passes_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/sessions"
        assert request.url.params["limit"] == "3"
        return httpx.Response(
            200,
            json={
                "sessions": [
                    {
                        "session_id": "session-1",
                        "status": "working",
                        "title": "Title",
                        "url": "https://devin.example/session-1",
                        "ignored": True,
                    }
                ]
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.list_sessions(limit=3) == [
        DevinSession(
            session_id="session-1",
            status="working",
            title="Title",
            url="https://devin.example/session-1",
        )
    ]
    client.http.close()


def test_create_session_posts_prompt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/sessions"
        assert request.read() == b'{"prompt":"Build it"}'
        return httpx.Response(
            201,
            json={
                "session_id": "session-2",
                "url": "https://devin.example/session-2",
                "is_new_session": True,
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.create_session(SessionCreate(prompt="Build it")) == SessionCreated(
        session_id="session-2",
        url="https://devin.example/session-2",
        is_new_session=True,
    )
    client.http.close()


@pytest.mark.parametrize("status_code", [400, 500])
def test_upstream_http_errors_include_status(status_code: int) -> None:
    client = make_client(
        httpx.MockTransport(
            lambda request: httpx.Response(status_code, text="upstream failed")
        )
    )
    with pytest.raises(DevinUpstreamError) as error:
        client.list_sessions()
    assert error.value.status_code == status_code
    assert error.value.detail == f"devin api returned HTTP {status_code}"
    client.http.close()


def test_create_session_upstream_http_error_includes_status() -> None:
    client = make_client(
        httpx.MockTransport(lambda request: httpx.Response(500, text="upstream failed"))
    )
    with pytest.raises(DevinUpstreamError) as error:
        client.create_session(SessionCreate(prompt="Build it"))
    assert error.value.status_code == 500
    assert error.value.detail == "devin api returned HTTP 500"
    client.http.close()


def test_upstream_transport_error_has_no_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(DevinUpstreamError) as error:
        client.list_sessions()
    assert error.value.status_code is None
    assert error.value.detail == "devin api unreachable"
    client.http.close()


def test_create_session_transport_error_has_no_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(DevinUpstreamError) as error:
        client.create_session(SessionCreate(prompt="Build it"))
    assert error.value.status_code is None
    assert error.value.detail == "devin api unreachable"
    client.http.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"unexpected": []}),
        httpx.Response(200, json={"sessions": [{}]}),
    ],
)
def test_list_sessions_rejects_malformed_success(
    response: httpx.Response,
) -> None:
    client = make_client(httpx.MockTransport(lambda request: response))
    with pytest.raises(DevinUpstreamError) as error:
        client.list_sessions()
    assert error.value.status_code is None
    assert error.value.detail == "malformed devin response"
    client.http.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"unexpected": []}),
    ],
)
def test_create_session_rejects_malformed_success(
    response: httpx.Response,
) -> None:
    client = make_client(httpx.MockTransport(lambda request: response))
    with pytest.raises(DevinUpstreamError) as error:
        client.create_session(SessionCreate(prompt="Build it"))
    assert error.value.status_code is None
    assert error.value.detail == "malformed devin response"
    client.http.close()


def test_get_devin_client_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVIN_API_TOKEN", "secret")
    first = get_devin_client()
    assert first is get_devin_client()
    assert isinstance(first, DevinClient)
    first.http.close()
