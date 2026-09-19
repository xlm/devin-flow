from pathlib import Path

import httpx
import pytest

from devin_flow.config import Settings, get_settings
from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import (
    DevinNotConfiguredError,
    DevinSession,
    DevinUpstreamError,
    SessionCreate,
    create_client,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DEVIN_API_BASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    get_devin_client.cache_clear()


def test_create_client_configures_base_url_and_authorization() -> None:
    client = create_client(
        get_settings().model_copy(
            update={
                "devin_api_token": "secret",
                "devin_api_base_url": "https://devin.example/v3",
                "devin_org_id": "org-test",
            }
        )
    )
    assert client.http.base_url == httpx.URL("https://devin.example/v3/")
    assert client.http.headers["Authorization"] == "Bearer secret"
    assert client.org_id == "org-test"
    client.http.close()


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.devin.ai/v3",
        "http://localhost:8099/v3",
        "http://127.0.0.1:8099/v3",
        "http://[::1]:8099/v3",
        "HTTPS://api.devin.ai/v3",
    ],
)
def test_create_client_accepts_tls_or_loopback(base_url: str) -> None:
    settings = Settings(
        devin_api_token="secret",
        devin_api_base_url=base_url,
        devin_org_id="org-test",
    )
    client = create_client(settings)
    assert client.http.base_url.host == httpx.URL(base_url).host
    client.http.close()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.devin.ai/v3",
        "http://localhost.evil.com/v3",
        "http://127.0.0.1.nip.io/v3",
        "ftp://api.devin.ai/v3",
        "ftp://localhost/v3",
        "ws://127.0.0.1:8099/v3",
        "api.devin.ai/v3",
    ],
)
def test_create_client_rejects_non_tls_remote_urls(base_url: str) -> None:
    settings = Settings(
        devin_api_token="secret",
        devin_api_base_url=base_url,
        devin_org_id="org-test",
    )
    with pytest.raises(
        DevinNotConfiguredError, match="DEVIN_API_BASE_URL must use https"
    ):
        create_client(settings)


def make_client(
    handler: httpx.BaseTransport,
) -> DevinClient:
    return DevinClient(
        httpx.Client(transport=handler, base_url="https://devin.example"),
        "org-test",
    )


def test_list_sessions_parses_response_and_passes_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/organizations/org-test/sessions"
        assert request.url.params["first"] == "3"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "session_id": "session-1",
                        "status": "running",
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
            status="running",
            title="Title",
            url="https://devin.example/session-1",
        )
    ]
    client.http.close()


def test_create_session_posts_prompt() -> None:
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

    client = make_client(httpx.MockTransport(handler))
    assert client.create_session(SessionCreate(prompt="Build it")) == DevinSession(
        session_id="session-2",
        url="https://devin.example/session-2",
        status="running",
        title="Title",
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
        httpx.Response(200, json={"items": [{}]}),
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
    monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    first = get_devin_client()
    assert first is get_devin_client()
    assert isinstance(first, DevinClient)
    first.http.close()
