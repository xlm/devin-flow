import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from devin_flow import invocations
from devin_flow.config import Settings
from devin_flow.devin.client import DevinSession, Playbook
from devin_flow.models import ActionNode, Edge, Invocation, TriggerNode
from devin_flow.simulate import github, reset
from devin_flow.simulate.scenario import load_scenario

from .conftest import SCENARIO_PATH


def _valid_client(**kwargs: Any) -> SimpleNamespace:
    defaults = {
        "list_playbooks": lambda: [
            Playbook(
                playbook_id="playbook-1",
                title="Issue triage",
                body="body",
                structured_output_schema={
                    "type": "object",
                    "properties": {"issue_number": {"type": "integer"}},
                },
            )
        ],
        "list_sessions": lambda **session_kwargs: [],
        "terminate_session": lambda session_id: None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _add_connected_action(
    session: Session,
    repository: str,
    automation_id: str,
    *,
    archived_at: datetime | None = None,
    enabled: bool = True,
    event_action: Literal["opened", "closed"] = "opened",
    playbook_id: str | None = "playbook-1",
    sync_status: str = "enabled",
) -> ActionNode:
    trigger = TriggerNode(
        event_action=event_action,
        repository_full_name=repository,
        position_x=0,
        position_y=0,
    )
    action = ActionNode(
        name=f"Action {automation_id}",
        position_x=450,
        position_y=0,
        enabled=enabled,
        sync_status=sync_status,
        automation_id=automation_id,
        playbook_id=playbook_id,
        archived_at=archived_at,
    )
    session.add_all(
        [
            trigger,
            action,
            Edge(
                source_id=trigger.id,
                source_kind="trigger",
                target_id=action.id,
                target_kind="action",
            ),
        ]
    )
    session.commit()
    return action


@pytest.fixture(autouse=True)
def no_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(invocations, "poll_once", lambda *args: None)


def test_reset_cleans_state_and_wipes_connected_flow(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    calls: list[tuple[str, Any]] = []
    tmp_path.mkdir(exist_ok=True)
    reset.repo_dir(tmp_path).mkdir()
    (tmp_path / ".simulate-run.json").write_text("{}")
    trigger_id = uuid4()
    action_id = uuid4()
    unit_session.add_all(
        [
            TriggerNode(
                id=trigger_id,
                event_action="opened",
                repository_full_name=scenario.repository,
                position_x=0,
                position_y=0,
            ),
            ActionNode(
                id=action_id,
                name="Issue triage",
                position_x=450,
                position_y=0,
                enabled=True,
                sync_status="enabled",
                automation_id="seed-automation",
                playbook_id="playbook-1",
            ),
            Edge(
                source_id=trigger_id,
                source_kind="trigger",
                target_id=action_id,
                target_kind="action",
            ),
        ]
    )
    unit_session.add(
        Invocation(
            session_id="seed-session",
            automation_id="seed-automation",
            action_node_id=action_id,
            status="running",
            session_created_at=datetime.now(UTC),
            session_updated_at=datetime.now(UTC),
        )
    )
    unit_session.commit()

    monkeypatch.setattr(
        github, "require_admin", lambda repo: calls.append(("admin", repo))
    )
    monkeypatch.setattr(
        github, "enable_issues", lambda repo: calls.append(("enable", repo))
    )
    monkeypatch.setattr(
        github, "ensure_labels", lambda repo: calls.append(("labels", repo))
    )
    monkeypatch.setattr(github, "list_issue_node_ids", lambda repo: ["issue-1"])
    monkeypatch.setattr(
        github, "delete_issue", lambda repo, node: calls.append(("delete", node))
    )
    monkeypatch.setattr(
        github, "list_open_prs", lambda repo: [github.PullRequest(2, "fix")]
    )
    monkeypatch.setattr(
        github, "close_pr", lambda repo, number: calls.append(("close", number))
    )
    monkeypatch.setattr(
        github, "delete_branch", lambda repo, branch: calls.append(("branch", branch))
    )
    monkeypatch.setattr(reset, "_git_branches", lambda scenario, work_dir: ["fix"])
    git_outputs = {
        "config": "https://github.com/xlm/superset.git",
        "rev-parse": "result-sha",
    }
    git_dirs: list[Path] = []

    def fake_git(work_dir: Path, *args: str) -> str:
        git_dirs.append(work_dir)
        calls.append(("git", args))
        return git_outputs.get(args[0], "")

    monkeypatch.setattr(reset, "_git", fake_git)
    settings = Settings(
        DEVIN_API_TOKEN="token",
        DEVIN_ORG_ID="org",
        seed_repository_full_name="xlm/superset",
    )
    monkeypatch.setattr(reset, "get_settings", lambda: settings)

    poller_events: list[str] = []
    original_get_poller_state = invocations.get_poller_state

    def get_poller_state_spy(session: Session) -> Any:
        poller_events.append("lock")
        return original_get_poller_state(session)

    monkeypatch.setattr(
        invocations,
        "get_poller_state",
        get_poller_state_spy,
    )

    def poll_once(session: Session, client: Any) -> None:
        poller_events.append("poll")
        session.add(
            Invocation(
                session_id="late-session",
                automation_id="seed-automation",
                action_node_id=action_id,
                status="running",
                session_created_at=datetime.now(UTC),
                session_updated_at=datetime.now(UTC),
            )
        )
        session.commit()

    monkeypatch.setattr(invocations, "poll_once", poll_once)

    original_delete = cast(Any, reset).delete

    def delete_spy(model: Any) -> Any:
        if model is Invocation:
            poller_events.append("delete")
        return original_delete(model)

    monkeypatch.setattr(
        cast(Any, reset),
        "delete",
        delete_spy,
    )
    result = reset.reset(
        scenario,
        work_dir=tmp_path,
        session=unit_session,
        devin_client=cast(
            Any,
            _valid_client(
                terminate_session=lambda session_id: calls.append(
                    ("terminate", session_id)
                )
            ),
        ),
    )
    assert result == "result-sha"
    assert (
        json.loads((tmp_path / ".simulate-state.json").read_text())["baseline"]
        == scenario.baseline
    )
    assert ("delete", "issue-1") in calls
    assert ("close", 2) in calls
    assert calls.index(("enable", scenario.repository)) < calls.index(
        ("labels", scenario.repository)
    )
    poller_state = invocations.get_poller_state(unit_session)
    assert poller_state.last_success_at is not None
    assert poller_state.last_success_at > datetime.now()
    assert calls.index(("admin", scenario.repository)) < calls.index(
        ("terminate", "seed-session")
    )
    assert ("terminate", "late-session") in calls
    assert git_dirs
    assert set(git_dirs) == {tmp_path / "repo"}
    assert json.loads((tmp_path / ".simulate-state.json").read_text()) == {
        "repository": scenario.repository,
        "default_branch": scenario.default_branch,
        "baseline": scenario.baseline,
        "reset_sha": "result-sha",
    }
    assert not (tmp_path / ".simulate-run.json").exists()
    reset_index = calls.index(("git", ("reset", "--hard", scenario.baseline)))
    clean_index = calls.index(("git", ("clean", "-fdx")))
    apply_index = calls.index(
        ("git", ("apply", str(scenario.patch_path(scenario.poisons[0]))))
    )
    assert reset_index < clean_index < apply_index
    assert poller_events[:3] == ["poll", "lock", "delete"]


def test_reset_terminates_upstream_sessions(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
    action = _add_connected_action(unit_session, scenario.repository, "automation-1")
    unit_session.add(
        Invocation(
            session_id="mirrored",
            automation_id="automation-1",
            action_node_id=action.id,
            status="running",
            session_created_at=datetime.now(UTC),
            session_updated_at=datetime.now(UTC),
        )
    )
    unit_session.add(
        Invocation(
            session_id="unrelated",
            automation_id="automation-2",
            action_node_id=uuid4(),
            status="running",
            session_created_at=datetime.now(UTC),
            session_updated_at=datetime.now(UTC),
        )
    )
    unit_session.commit()
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
    monkeypatch.setattr(github, "ensure_labels", lambda repo: None)
    monkeypatch.setattr(github, "list_issue_node_ids", lambda repo: [])
    monkeypatch.setattr(github, "list_open_prs", lambda repo: [])
    monkeypatch.setattr(reset, "_git_branches", lambda scenario, work_dir: [])
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: (
            "https://github.com/xlm/superset.git"
            if args[:3] == ("config", "--get", "remote.origin.url")
            else "sha"
        ),
    )
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    terminated: list[str] = []

    class FakeClient:
        def list_playbooks(self) -> list[Playbook]:
            return cast(list[Playbook], _valid_client().list_playbooks())

        def list_sessions(self, **kwargs: Any) -> list[DevinSession]:
            assert kwargs == {
                "automation_ids": ["automation-1"],
                "created_after": None,
                "paginate": True,
            }
            return [
                DevinSession(session_id="mirrored", status="running"),
                DevinSession(session_id="upstream", status="running"),
                DevinSession(session_id="done", status="exit"),
            ]

        def terminate_session(self, session_id: str) -> None:
            terminated.append(session_id)

    reset.reset(
        scenario,
        work_dir=tmp_path,
        session=unit_session,
        devin_client=cast(Any, FakeClient()),
    )
    assert terminated == ["mirrored", "upstream"]
    assert (
        unit_session.exec(
            select(Invocation).where(Invocation.session_id == "unrelated")
        ).first()
        is not None
    )


def test_reset_wipes_two_connected_actions(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
    trigger_id = uuid4()
    action_ids = [uuid4(), uuid4()]
    unit_session.add_all(
        [
            TriggerNode(
                id=trigger_id,
                position_x=100,
                position_y=0,
                event_action="opened",
                repository_full_name=scenario.repository,
            ),
            *[
                ActionNode(
                    id=action_id,
                    name=f"Action {index}",
                    position_x=index * 100,
                    position_y=0,
                    enabled=index == 1,
                    sync_status="enabled",
                    automation_id=f"auto-{index}",
                    playbook_id="playbook-1",
                )
                for index, action_id in enumerate(action_ids, 1)
            ],
            Edge(
                source_id=trigger_id,
                source_kind="trigger",
                target_id=action_ids[0],
                target_kind="action",
            ),
        ]
    )
    for index, automation_id in enumerate(("auto-1", "auto-2"), 1):
        unit_session.add(
            Invocation(
                session_id=f"local-{index}",
                automation_id=automation_id,
                action_node_id=action_ids[index - 1],
                status="running",
                session_created_at=datetime.now(UTC),
                session_updated_at=datetime.now(UTC),
            )
        )
    unit_session.commit()
    second_trigger = TriggerNode(
        event_action="opened",
        repository_full_name=scenario.repository,
        position_x=0,
        position_y=0,
    )
    unit_session.add(second_trigger)
    unit_session.commit()
    unit_session.add(
        Edge(
            source_id=second_trigger.id,
            source_kind="trigger",
            target_id=action_ids[1],
            target_kind="action",
        )
    )
    unit_session.commit()
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
    monkeypatch.setattr(github, "ensure_labels", lambda repo: None)
    monkeypatch.setattr(github, "list_issue_node_ids", lambda repo: [])
    monkeypatch.setattr(github, "list_open_prs", lambda repo: [])
    monkeypatch.setattr(reset, "_git_branches", lambda scenario, work_dir: [])
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: (
            "https://github.com/xlm/superset.git"
            if args[:3] == ("config", "--get", "remote.origin.url")
            else "sha"
        ),
    )
    terminated: list[str] = []

    class FakeClient:
        def list_playbooks(self) -> list[Playbook]:
            return cast(list[Playbook], _valid_client().list_playbooks())

        def list_sessions(self, **kwargs: Any) -> list[DevinSession]:
            assert kwargs["automation_ids"] == ["auto-1", "auto-2"]
            return [
                DevinSession(session_id="upstream-1", status="running"),
                DevinSession(session_id="upstream-2", status="running"),
            ]

        def terminate_session(self, session_id: str) -> None:
            terminated.append(session_id)

    reset.reset(
        scenario,
        work_dir=tmp_path,
        session=unit_session,
        devin_client=cast(Any, FakeClient()),
    )
    assert terminated == ["local-1", "local-2", "upstream-1", "upstream-2"]
    assert unit_session.exec(select(Invocation)).all() == []


def test_reset_rejects_empty_flow(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        github,
        "require_admin",
        lambda repo: pytest.fail("empty Flow must be checked first"),
    )
    with pytest.raises(
        RuntimeError, match="no enabled Action using the Issue triage Playbook"
    ):
        reset.reset(
            load_scenario(SCENARIO_PATH),
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )


def test_reset_ignores_archived_action(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    _add_connected_action(
        unit_session,
        scenario.repository,
        "archived",
        archived_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        github,
        "require_admin",
        lambda repo: pytest.fail("archived Flow must be ignored before reset"),
    )
    with pytest.raises(
        RuntimeError, match="no enabled Action using the Issue triage Playbook"
    ):
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": False},
        {"event_action": "closed"},
        {"playbook_id": "other-playbook"},
        {"sync_status": "pending"},
    ],
)
def test_reset_rejects_ineligible_action(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any],
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    _add_connected_action(
        unit_session,
        scenario.repository,
        "ineligible",
        **overrides,
    )
    monkeypatch.setattr(
        github,
        "require_admin",
        lambda repo: pytest.fail("ineligible Flow must be rejected first"),
    )
    with pytest.raises(
        RuntimeError, match="no enabled Action using the Issue triage Playbook"
    ):
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )


def test_reset_leaves_other_repository_action_untouched(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    target = _add_connected_action(unit_session, scenario.repository, "target")
    foreign = _add_connected_action(unit_session, "other/repository", "foreign")
    unit_session.add_all(
        [
            Invocation(
                session_id="target",
                automation_id="target",
                action_node_id=target.id,
                status="exit",
                session_created_at=datetime.now(UTC),
                session_updated_at=datetime.now(UTC),
            ),
            Invocation(
                session_id="foreign",
                automation_id="foreign",
                action_node_id=foreign.id,
                status="exit",
                session_created_at=datetime.now(UTC),
                session_updated_at=datetime.now(UTC),
            ),
        ]
    )
    unit_session.commit()
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
    monkeypatch.setattr(github, "ensure_labels", lambda repo: None)
    monkeypatch.setattr(github, "list_issue_node_ids", lambda repo: [])
    monkeypatch.setattr(github, "list_open_prs", lambda repo: [])
    monkeypatch.setattr(reset, "_git_branches", lambda scenario, work_dir: [])
    reset.repo_dir(tmp_path).mkdir()
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: (
            "https://github.com/xlm/superset.git"
            if args[:3] == ("config", "--get", "remote.origin.url")
            else "sha"
        ),
    )
    reset.reset(
        scenario,
        work_dir=tmp_path,
        session=unit_session,
        devin_client=cast(Any, _valid_client()),
    )
    assert unit_session.exec(
        select(Invocation).where(Invocation.session_id == "foreign")
    ).one()
    assert (
        unit_session.exec(
            select(Invocation).where(Invocation.session_id == "target")
        ).first()
        is None
    )


def test_reset_rejects_checkout_for_different_repository(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
    _add_connected_action(unit_session, scenario.repository, "auto")
    calls: list[str] = []
    monkeypatch.setattr(github, "require_admin", lambda repo: calls.append("admin"))
    monkeypatch.setattr(
        github,
        "enable_issues",
        lambda repo: pytest.fail("repository mismatch must be checked first"),
    )
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: "https://github.com/other/repository.git",
    )
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    with pytest.raises(RuntimeError, match="xlm/superset.*other/repository"):
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )
    assert calls == []


def test_reset_rejects_scenario_for_different_seed_repository(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    _add_connected_action(unit_session, scenario.repository, "auto")
    calls: list[str] = []
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
            seed_repository_full_name="other/repository",
        ),
    )
    monkeypatch.setattr(
        github,
        "require_admin",
        lambda repo: calls.append("admin"),
    )
    with pytest.raises(
        RuntimeError,
        match=(
            "scenario repository xlm/superset does not match "
            "SEED_REPOSITORY_FULL_NAME other/repository"
        ),
    ):
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )
    assert calls == []


def test_reset_rejects_checkout_without_origin(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
    _add_connected_action(unit_session, scenario.repository, "auto")
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, ["git"])
        ),
    )
    with pytest.raises(RuntimeError, match="expected xlm/superset.*unavailable"):
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )


def test_reset_rejects_missing_playbook_before_destructive_work(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(devin_api_token="token", devin_org_id="org"),
    )
    monkeypatch.setattr(
        github,
        "require_admin",
        lambda repo: calls.append("require_admin"),
    )
    with pytest.raises(RuntimeError, match="playbook 'Issue triage' not found"):
        reset.reset(
            load_scenario(SCENARIO_PATH),
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(
                Any,
                SimpleNamespace(list_playbooks=lambda: []),
            ),
        )
    assert calls == []
    assert not (tmp_path / ".simulate-run.json").exists()


def test_reset_rejects_playbook_without_issue_number(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    monkeypatch.setattr(
        github,
        "require_admin",
        lambda repo: calls.append("require_admin"),
    )
    client = SimpleNamespace(
        list_playbooks=lambda: [
            Playbook(
                playbook_id="playbook-1",
                title="Issue triage",
                body="body",
                structured_output_schema={
                    "type": "object",
                    "properties": {"outcome": {"type": "string"}},
                },
            )
        ]
    )
    with pytest.raises(
        RuntimeError,
        match=(
            "playbook playbook-1 structured output schema lacks issue_number, "
            "run uv run sync-playbooks"
        ),
    ):
        reset.reset(
            load_scenario(SCENARIO_PATH),
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, client),
        )
    assert calls == []


def test_reset_rejects_missing_poison_patch_before_destructive_work(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    scenario.patch_dir = tmp_path / "patches"
    _add_connected_action(unit_session, scenario.repository, "auto")
    calls: list[str] = []
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    monkeypatch.setattr(
        github,
        "require_admin",
        lambda repo: calls.append("require_admin"),
    )
    with pytest.raises(
        RuntimeError,
        match=r"missing poison patch: .*patches/date-parser-offset\.patch",
    ):
        reset.reset(
            scenario,
            work_dir=tmp_path / "work",
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )
    assert calls == []


def test_git_and_branch_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    completed = subprocess.CompletedProcess(
        ["git"],
        0,
        "sha-fix\trefs/heads/devin/123-fix\nsha-master\trefs/heads/master\n",
        "",
    )
    calls: list[Any] = []

    def record_git(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return completed

    monkeypatch.setattr(
        subprocess,
        "run",
        record_git,
    )
    assert (
        reset._git(tmp_path, "status")
        == "sha-fix\trefs/heads/devin/123-fix\nsha-master\trefs/heads/master"
    )
    scenario = load_scenario(SCENARIO_PATH)
    assert reset._git_branches(scenario, tmp_path) == ["devin/123-fix"]
    assert calls[0][0] == ["git", *reset.GIT_CREDENTIAL_ARGS, "status"]


def test_git_branches_ignores_malformed_refs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: (
            "malformed\nsha-tag\trefs/tags/v1\n"
            "sha-fix\trefs/heads/devin/123-fix\nsha-master\trefs/heads/master"
        ),
    )
    assert reset._git_branches(load_scenario(SCENARIO_PATH), tmp_path) == [
        "devin/123-fix"
    ]
    assert reset._normalize_repository("local/repository") == "local/repository"


def test_reset_clones_missing_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unit_session: Session
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    work_dir = tmp_path / "clone"
    clone_calls: list[Any] = []
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
    monkeypatch.setattr(github, "ensure_labels", lambda repo: None)
    monkeypatch.setattr(github, "list_issue_node_ids", lambda repo: [])
    monkeypatch.setattr(github, "list_open_prs", lambda repo: [])
    monkeypatch.setattr(reset, "_git_branches", lambda scenario, work_dir: [])
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: (
            "https://github.com/xlm/superset.git"
            if args[:3] == ("config", "--get", "remote.origin.url")
            else "sha"
        ),
    )

    def record_clone(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        Path(args[-1]).mkdir()
        clone_calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", record_clone)
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    _add_connected_action(unit_session, scenario.repository, "auto-1")
    reset.reset(
        scenario,
        work_dir=work_dir,
        session=unit_session,
        devin_client=cast(Any, _valid_client()),
    )
    assert clone_calls[0][0][0] == "git"
    assert clone_calls[0][0][1 : 1 + len(reset.GIT_CREDENTIAL_ARGS)] == list(
        reset.GIT_CREDENTIAL_ARGS
    )
    assert clone_calls[0][0][1 + len(reset.GIT_CREDENTIAL_ARGS)] == "clone"
    assert Path(clone_calls[0][0][-1]) == work_dir / "repo"


def test_reset_handles_session_termination_without_wiping(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    from devin_flow.models import Invocation

    reset.repo_dir(tmp_path).mkdir(parents=True)
    action = _add_connected_action(unit_session, scenario.repository, "auto")
    unit_session.add(
        Invocation(
            session_id="running",
            automation_id="auto",
            action_node_id=action.id,
            status="running",
            session_created_at=datetime.now(),
            session_updated_at=datetime.now(),
        )
    )
    unit_session.commit()
    terminated: list[str] = []
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
    monkeypatch.setattr(github, "ensure_labels", lambda repo: None)
    monkeypatch.setattr(github, "list_issue_node_ids", lambda repo: [])
    monkeypatch.setattr(github, "list_open_prs", lambda repo: [])
    monkeypatch.setattr(reset, "_git_branches", lambda scenario, work_dir: [])
    monkeypatch.setattr(
        reset,
        "_git",
        lambda work_dir, *args: (
            "https://github.com/xlm/superset.git"
            if args[:3] == ("config", "--get", "remote.origin.url")
            else "sha"
        ),
    )
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
        ),
    )
    unit_session.commit()
    client = _valid_client(
        list_sessions=lambda **kwargs: [],
        terminate_session=lambda session_id: terminated.append(session_id),
    )
    assert (
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, client),
            wipe_invocations=False,
        )
        == "sha"
    )
    assert terminated == ["running"]


def test_reset_git_branches_ignores_missing_worktree(tmp_path: Path) -> None:
    assert reset._git_branches(load_scenario(SCENARIO_PATH), tmp_path / "missing") == []
