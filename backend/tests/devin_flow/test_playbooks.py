import json
from pathlib import Path

import httpx
import pytest

from devin_flow import playbooks
from devin_flow.config import DEFAULT_PLAYBOOKS_DIR, Settings
from devin_flow.devin.client import DevinClient
from devin_flow.outcomes import STRUCTURED_OUTCOMES
from devin_flow.playbooks import (
    load_playbook,
    main,
    sync_playbooks,
)


def make_client(
    handler: httpx.BaseTransport,
) -> DevinClient:
    return DevinClient(
        httpx.Client(transport=handler, base_url="https://devin.example"),
        "org-test",
    )


def test_load_playbook_reads_title_body_and_schema(tmp_path: Path) -> None:
    path = tmp_path / "triage.md"
    path.write_text("# Triage\n\ndo it\n")
    path.with_suffix(".schema.json").write_text('{"type": "object"}')

    playbook = load_playbook(path)
    assert playbook.path == path
    assert playbook.title == "Triage"
    assert playbook.body == "# Triage\n\ndo it\n"
    assert playbook.structured_output_schema == {"type": "object"}


def test_load_playbook_without_schema_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "triage.md"
    path.write_text("## Sub heading first\n# Triage\n")

    assert load_playbook(path).structured_output_schema is None
    assert load_playbook(path).title == "Sub heading first"


def test_load_playbook_without_heading_raises(tmp_path: Path) -> None:
    path = tmp_path / "plain.md"
    path.write_text("no heading here\n")

    with pytest.raises(ValueError, match="no markdown heading"):
        load_playbook(path)


def test_sync_playbooks_creates_missing_playbook(tmp_path: Path) -> None:
    (tmp_path / "new.md").write_text("# New\n\nbody\n")
    (tmp_path / "new.schema.json").write_text('{"title": "NewOutcome"}')
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"items": [], "end_cursor": None, "has_next_page": False}
            )
        return httpx.Response(
            200,
            json={"playbook_id": "pb-1", "title": "New", "body": "# New\n\nbody\n"},
        )

    client = make_client(httpx.MockTransport(handler))
    assert list(sync_playbooks(client, tmp_path)) == [(tmp_path / "new.md", "created")]
    assert [request.method for request in requests] == ["GET", "POST"]
    assert json.loads(requests[1].read()) == {
        "title": "New",
        "body": "# New\n\nbody\n",
        "macro": None,
        "structured_output_schema": {"title": "NewOutcome"},
    }
    client.http.close()


def test_sync_playbooks_updates_existing_and_preserves_macro(
    tmp_path: Path,
) -> None:
    (tmp_path / "triage.md").write_text("# Triage\n\nnew body\n")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "playbook_id": "pb-7",
                            "title": "Triage",
                            "body": "old",
                            "macro": "!triage",
                        }
                    ],
                    "has_next_page": False,
                },
            )
        return httpx.Response(
            200, json={"playbook_id": "pb-7", "title": "Triage", "body": "new body"}
        )

    client = make_client(httpx.MockTransport(handler))
    assert list(sync_playbooks(client, tmp_path)) == [
        (tmp_path / "triage.md", "updated")
    ]
    assert [request.method for request in requests] == ["GET", "PUT"]
    assert requests[1].url.path == "/organizations/org-test/playbooks/pb-7"
    assert json.loads(requests[1].read())["macro"] == "!triage"
    client.http.close()


def test_sync_playbooks_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    store: dict[str, dict[str, object]] = {}
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": list(store.values()),
                    "end_cursor": None,
                    "has_next_page": False,
                },
            )
        payload = json.loads(request.read())
        if request.method == "POST":
            playbook_id = f"pb-{len(store) + 1}"
            store[playbook_id] = {
                "playbook_id": playbook_id,
                "title": payload["title"],
                "body": payload["body"],
            }
            return httpx.Response(200, json=store[playbook_id])
        playbook_id = request.url.path.rsplit("/", 1)[-1]
        store[playbook_id]["body"] = payload["body"]
        return httpx.Response(200, json=store[playbook_id])

    client = make_client(httpx.MockTransport(handler))
    assert [action for _, action in sync_playbooks(client, tmp_path)] == ["created"]
    assert [action for _, action in sync_playbooks(client, tmp_path)] == ["updated"]
    assert calls == ["GET", "POST", "GET", "PUT"]
    assert len(store) == 1
    client.http.close()


def test_sync_playbooks_skips_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Playbooks\n")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"items": [], "end_cursor": None, "has_next_page": False}
        )

    client = make_client(httpx.MockTransport(handler))
    assert list(sync_playbooks(client, tmp_path)) == []
    assert [request.method for request in requests] == ["GET"]
    client.http.close()


def test_sync_playbooks_fails_on_missing_directory(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": []})

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="playbooks directory not found"):
        list(sync_playbooks(client, tmp_path / "missing"))
    assert requests == []
    client.http.close()


def test_sync_playbooks_fails_on_duplicate_titles(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# Same\n\na\n")
    (tmp_path / "b.md").write_text("# Same\n\nb\n")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": []})

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="duplicate playbook title 'Same': a.md, b.md"):
        list(sync_playbooks(client, tmp_path))
    assert requests == []
    client.http.close()


def test_sync_playbooks_fails_on_bad_file_before_requests(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text("no heading\n")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": []})

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="no markdown heading"):
        list(sync_playbooks(client, tmp_path))
    assert requests == []
    client.http.close()


def test_main_prints_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.md").write_text("# A\n\nbody\n")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": [], "has_next_page": False})
        return httpx.Response(
            200, json={"playbook_id": "pb-1", "title": "A", "body": "body"}
        )

    client = make_client(httpx.MockTransport(handler))
    monkeypatch.setattr(
        playbooks,
        "get_settings",
        lambda: Settings(
            devin_api_token="test-token",
            devin_org_id="org-test",
            playbooks_dir=tmp_path,
        ),
    )
    monkeypatch.setattr(playbooks, "get_devin_client", lambda: client)
    main()
    assert capsys.readouterr().out == "created a.md\n"
    client.http.close()


def test_main_exits_on_upstream_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    client = make_client(
        httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
    )
    monkeypatch.setattr(
        playbooks,
        "get_settings",
        lambda: Settings(
            devin_api_token="test-token",
            devin_org_id="org-test",
            playbooks_dir=tmp_path,
        ),
    )
    monkeypatch.setattr(playbooks, "get_devin_client", lambda: client)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert "sync-playbooks failed" in captured.err
    client.http.close()


def test_main_wraps_load_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.md").write_text("no heading\n")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no requests expected")

    client = make_client(httpx.MockTransport(handler))
    monkeypatch.setattr(
        playbooks,
        "get_settings",
        lambda: Settings(
            devin_api_token="test-token",
            devin_org_id="org-test",
            playbooks_dir=tmp_path,
        ),
    )
    monkeypatch.setattr(playbooks, "get_devin_client", lambda: client)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "no markdown heading" in capsys.readouterr().err


def test_repo_playbooks_load() -> None:
    playbook = load_playbook(DEFAULT_PLAYBOOKS_DIR / "issue-triage.md")
    assert playbook.title == "Issue triage"
    assert playbook.structured_output_schema is not None
    assert playbook.structured_output_schema["title"] == "IssueTriageOutcome"


def test_issue_triage_schema_matches_outcome_readers() -> None:
    schema = load_playbook(
        DEFAULT_PLAYBOOKS_DIR / "issue-triage.md"
    ).structured_output_schema
    assert schema is not None
    properties = schema["properties"]
    assert set(properties["outcome"]["enum"]) == STRUCTURED_OUTCOMES | {"fixed"}
    assert {
        "outcome",
        "duplicate_of",
        "issue_url",
        "issue_number",
        "issue_title",
    } <= set(properties)
    assert {"issue_url", "issue_number", "issue_title"} <= set(schema["required"])
    assert properties["issue_number"]["type"] == "integer"
    assert properties["issue_title"]["type"] == "string"
