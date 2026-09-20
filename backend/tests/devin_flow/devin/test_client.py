import json
from pathlib import Path

import httpx
import pytest

from devin_flow.config import Settings, get_settings
from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import (
    Automation,
    AutomationAction,
    AutomationCondition,
    AutomationConditionGroup,
    AutomationConditions,
    AutomationCreate,
    AutomationRunAs,
    AutomationTrigger,
    AutomationUpdate,
    DevinNotConfiguredError,
    DevinSession,
    DevinUpstreamError,
    Playbook,
    PlaybookCreate,
    Repository,
    SessionCreate,
    SessionPullRequest,
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


def test_list_sessions_sends_flat_filters_and_follows_cursor() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.params.get_list("automation_ids") == ["auto-1", "auto-2"]
        assert request.url.params["created_after"] == "1700000000"
        if "after" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "session_id": "session-1",
                            "status": "running",
                            "automation_id": "auto-1",
                            "pull_requests": [
                                {"pr_url": "https://gh.example/1", "pr_state": "open"}
                            ],
                            "created_at": 1700000100,
                            "updated_at": 1700000200,
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
                "items": [{"session_id": "session-2", "status": "exit"}],
                "has_next_page": False,
                "end_cursor": None,
            },
        )

    client = make_client(httpx.MockTransport(handler))
    sessions = client.list_sessions(
        automation_ids=["auto-1", "auto-2"],
        created_after=1700000000,
        paginate=True,
    )
    assert [s.session_id for s in sessions] == ["session-1", "session-2"]
    assert sessions[0].pull_requests == [
        SessionPullRequest(pr_url="https://gh.example/1", pr_state="open")
    ]
    assert sessions[0].created_at == 1700000100
    assert len(calls) == 2
    client.http.close()


def test_list_sessions_without_paginate_stops_after_first_page() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert "automation_ids" not in request.url.params
        return httpx.Response(
            200,
            json={"items": [], "has_next_page": True, "end_cursor": "cursor-1"},
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.list_sessions() == []
    assert len(calls) == 1
    client.http.close()


def test_get_session_fetches_one_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/organizations/org-test/sessions/session-9"
        return httpx.Response(
            200,
            json={
                "session_id": "session-9",
                "status": "exit",
                "structured_output": {"outcome": "duplicate"},
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.get_session("session-9") == DevinSession(
        session_id="session-9",
        status="exit",
        structured_output={"outcome": "duplicate"},
    )
    client.http.close()


def test_get_session_upstream_error_includes_status() -> None:
    client = make_client(httpx.MockTransport(lambda request: httpx.Response(404)))
    with pytest.raises(DevinUpstreamError) as error:
        client.get_session("missing")
    assert error.value.status_code == 404
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


def test_archive_session_posts_to_archive_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/organizations/org-test/sessions/session-9/archive"
        return httpx.Response(
            200,
            json={
                "session_id": "session-9",
                "status": "exit",
                "title": "Archived",
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.archive_session("session-9") == DevinSession(
        session_id="session-9",
        status="exit",
        title="Archived",
    )
    client.http.close()


def test_archive_session_rejects_malformed_success() -> None:
    client = make_client(httpx.MockTransport(lambda _: httpx.Response(200, text="bad")))
    with pytest.raises(DevinUpstreamError) as error:
        client.archive_session("session-9")
    assert error.value.detail == "malformed devin response"
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


@pytest.mark.parametrize(
    "base_url", ["https://devin.example/v3", "https://devin.example"]
)
def test_list_repositories_uses_beta_path_and_authorization(base_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3beta1/organizations/org-test/repositories"
        assert request.headers["Authorization"] == "Bearer secret"
        assert request.url.params["first"] == "100"
        assert request.url.params["load_indexing_status"] == "false"
        return httpx.Response(
            200,
            json={"items": [{"repo_path": "octo/repo", "repo_name": "repo"}]},
        )

    client = DevinClient(
        httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url=base_url,
            headers={"Authorization": "Bearer secret"},
        ),
        "org-test",
    )
    assert client.list_repositories() == [
        Repository(repo_path="octo/repo", repo_name="repo")
    ]
    client.http.close()


def test_list_repositories_follows_cursor() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "after" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "items": [{"repo_path": "octo/one", "repo_name": "one"}],
                    "end_cursor": "cursor-1",
                    "has_next_page": True,
                },
            )
        return httpx.Response(
            200,
            json={
                "items": [{"repo_path": "octo/two", "repo_name": "two"}],
                "has_next_page": False,
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.list_repositories() == [
        Repository(repo_path="octo/one", repo_name="one"),
        Repository(repo_path="octo/two", repo_name="two"),
    ]
    assert calls[1].url.params["after"] == "cursor-1"
    client.http.close()


@pytest.mark.parametrize("status_code", [400, 500])
def test_list_repositories_upstream_http_error_includes_status(
    status_code: int,
) -> None:
    client = make_client(
        httpx.MockTransport(
            lambda request: httpx.Response(status_code, text="upstream failed")
        )
    )
    with pytest.raises(DevinUpstreamError) as error:
        client.list_repositories()
    assert error.value.status_code == status_code
    assert error.value.detail == f"devin api returned HTTP {status_code}"
    client.http.close()


def test_list_repositories_transport_error_has_no_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(DevinUpstreamError) as error:
        client.list_repositories()
    assert error.value.status_code is None
    assert error.value.detail == "devin api unreachable"
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
def test_list_repositories_rejects_malformed_success(
    response: httpx.Response,
) -> None:
    client = make_client(httpx.MockTransport(lambda request: response))
    with pytest.raises(DevinUpstreamError) as error:
        client.list_repositories()
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


def automation_payload() -> AutomationCreate:
    return AutomationCreate(
        name="Triage",
        enabled=True,
        triggers=[
            AutomationTrigger(
                event_type="github:issues",
                conditions=AutomationConditions(
                    any=[
                        AutomationConditionGroup(
                            all=[
                                AutomationCondition(field="action", value="opened"),
                                AutomationCondition(
                                    field="repository.full_name", value="octo/repo"
                                ),
                            ]
                        )
                    ]
                ),
            )
        ],
        actions=[AutomationAction(prompt="@playbook:pb-1")],
        run_as=AutomationRunAs(),
        metadata={"devin_flow_action_id": "action-id"},
    )


def test_list_automations_filters_metadata_and_follows_cursor() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            assert request.url.params["first"] == "100"
            assert request.url.params["metadata.devin_flow_action_id"] == "action-id"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "automation_id": "auto-1",
                            "name": "One",
                            "enabled": True,
                            "metadata": {},
                            "ignored": True,
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
                        "automation_id": "auto-2",
                        "name": "Two",
                        "enabled": False,
                    }
                ],
                "has_next_page": False,
                "end_cursor": None,
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.list_automations({"devin_flow_action_id": "action-id"}) == [
        Automation(
            automation_id="auto-1",
            name="One",
            enabled=True,
            metadata={},
        ),
        Automation(automation_id="auto-2", name="Two", enabled=False),
    ]
    client.http.close()


def test_create_and_update_automation_use_json_payloads() -> None:
    payload = automation_payload()
    calls: list[httpx.Request] = []
    update = AutomationUpdate(
        name=payload.name,
        enabled=False,
        triggers=payload.triggers,
        actions=payload.actions,
        metadata=payload.metadata,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            assert request.url.path == "/organizations/org-test/automations"
            assert json.loads(request.read()) == payload.model_dump()
        else:
            assert request.method == "PATCH"
            assert request.url.path.endswith("/automations/auto-1")
            body = json.loads(request.read())
            assert body == update.model_dump()
            assert all(
                condition["operator"] == "eq"
                for group in body["triggers"][0]["conditions"]["any"]
                for condition in group["all"]
            )
            assert body["actions"][0]["type"] == "start_session"
            assert "run_as" not in body
        return httpx.Response(
            201 if request.method == "POST" else 200,
            json={
                "automation_id": "auto-1",
                "name": "Triage",
                "enabled": request.method == "POST",
                "metadata": {"devin_flow_action_id": "action-id"},
            },
        )

    client = make_client(httpx.MockTransport(handler))
    assert client.create_automation(payload).automation_id == "auto-1"
    assert client.update_automation("auto-1", update).enabled is False
    assert [call.method for call in calls] == ["POST", "PATCH"]
    client.http.close()
