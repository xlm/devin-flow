import json
from pathlib import Path

import httpx
import pytest

from devin_flow.config import Settings, get_settings
from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import (
    DevinNotConfiguredError,
    DevinSession,
    DevinUpstreamError,
    Playbook,
    PlaybookCreate,
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


def test_list_playbooks_follows_cursor() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "after" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "playbook_id": "pb-1",
                            "title": "One",
                            "body": "body-1",
                            "macro": "!one",
                            "ignored": True,
                        }
                    ],
                    "end_cursor": "cursor-1",
                    "has_next_page": True,
                    "total": 2,
                },
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "playbook_id": "pb-2",
                        "title": "Two",
                        "body": "body-2",
                        "structured_output_schema": {"type": "object"},
                    }
                ],
                "end_cursor": None,
                "has_next_page": False,
                "total": 2,
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.list_playbooks() == [
        Playbook(playbook_id="pb-1", title="One", body="body-1", macro="!one"),
        Playbook(
            playbook_id="pb-2",
            title="Two",
            body="body-2",
            structured_output_schema={"type": "object"},
        ),
    ]
    assert "after" not in calls[0].url.params
    assert calls[0].url.params["first"] == "100"
    assert calls[1].url.params["after"] == "cursor-1"
    client.http.close()


def test_list_playbooks_treats_missing_has_next_page_as_done() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [{"playbook_id": "pb-1", "title": "One", "body": "b"}]},
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.list_playbooks() == [
        Playbook(playbook_id="pb-1", title="One", body="b")
    ]
    client.http.close()


def test_create_playbook_posts_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/organizations/org-test/playbooks"
        assert json.loads(request.read()) == {
            "title": "Triage",
            "body": "# Triage\n",
            "macro": None,
            "structured_output_schema": {"type": "object"},
        }
        return httpx.Response(
            200,
            json={
                "playbook_id": "pb-9",
                "title": "Triage",
                "body": "# Triage\n",
                "structured_output_schema": {"type": "object"},
                "ignored": True,
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.create_playbook(
        PlaybookCreate(
            title="Triage",
            body="# Triage\n",
            structured_output_schema={"type": "object"},
        )
    ) == Playbook(
        playbook_id="pb-9",
        title="Triage",
        body="# Triage\n",
        structured_output_schema={"type": "object"},
    )
    client.http.close()


def test_update_playbook_puts_to_playbook_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/organizations/org-test/playbooks/pb-9"
        assert json.loads(request.read())["macro"] == "!triage"
        return httpx.Response(
            200,
            json={"playbook_id": "pb-9", "title": "Triage", "body": "b"},
        )

    client = make_client(httpx.MockTransport(handler))
    playbook = client.update_playbook(
        "pb-9", PlaybookCreate(title="Triage", body="b", macro="!triage")
    )
    assert playbook.playbook_id == "pb-9"
    client.http.close()


@pytest.mark.parametrize("status_code", [400, 500])
def test_list_playbooks_upstream_http_error_includes_status(
    status_code: int,
) -> None:
    client = make_client(
        httpx.MockTransport(
            lambda request: httpx.Response(status_code, text="upstream failed")
        )
    )
    with pytest.raises(DevinUpstreamError) as error:
        client.list_playbooks()
    assert error.value.status_code == status_code
    assert error.value.detail == f"devin api returned HTTP {status_code}"
    client.http.close()


def test_create_playbook_upstream_http_error_includes_status() -> None:
    client = make_client(
        httpx.MockTransport(lambda request: httpx.Response(500, text="upstream failed"))
    )
    with pytest.raises(DevinUpstreamError) as error:
        client.create_playbook(PlaybookCreate(title="t", body="b"))
    assert error.value.status_code == 500
    client.http.close()


def test_update_playbook_upstream_http_error_includes_status() -> None:
    client = make_client(
        httpx.MockTransport(lambda request: httpx.Response(500, text="upstream failed"))
    )
    with pytest.raises(DevinUpstreamError) as error:
        client.update_playbook("pb-1", PlaybookCreate(title="t", body="b"))
    assert error.value.status_code == 500
    client.http.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"unexpected": []}),
        httpx.Response(200, json={"items": [{}]}),
        httpx.Response(200, json={"items": [], "has_next_page": True}),
    ],
)
def test_list_playbooks_rejects_malformed_success(
    response: httpx.Response,
) -> None:
    client = make_client(httpx.MockTransport(lambda request: response))
    with pytest.raises(DevinUpstreamError) as error:
        client.list_playbooks()
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
