import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from devin_flow import automations, invocations
from devin_flow.config import Settings
from devin_flow.devin.client import Automation, DevinSession, Playbook
from devin_flow.models import ActionNode, Edge, Invocation, TriggerNode
from devin_flow.seed import SEED_ACTION_ID, SEED_TRIGGER_ID
from devin_flow.simulate import github, reset
from devin_flow.simulate.scenario import load_scenario

from .conftest import SCENARIO_PATH

REAL_SYNC_ACTION = automations.sync_action


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


def _seed_enabled_action(session: Session, **kwargs: Any) -> None:
    session.add(
        ActionNode(
            id=SEED_ACTION_ID,
            name="Seed: Issue triage",
            position_x=450,
            position_y=0,
            enabled=True,
            sync_status="enabled",
            automation_id="seed-automation",
        )
    )
    session.commit()


@pytest.fixture(autouse=True)
def no_seed_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(automations, "sync_action", lambda *args: None)


def test_reset_cleans_state_and_seeds(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    calls: list[tuple[str, Any]] = []
    tmp_path.mkdir(exist_ok=True)
    reset.repo_dir(tmp_path).mkdir()
    (tmp_path / ".simulate-run.json").write_text("{}")
    unit_session.add(
        Invocation(
            session_id="seed-session",
            automation_id="seed-automation",
            action_node_id=SEED_ACTION_ID,
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
        seed_playbook_id="playbook-1",
        seed_repository_full_name="xlm/superset",
    )
    monkeypatch.setattr(reset, "get_settings", lambda: settings)

    def fake_seed(session: Session, **kwargs: Any) -> None:
        calls.append(("seed", kwargs))
        session.add(
            ActionNode(
                id=SEED_ACTION_ID,
                name="Seed: Issue triage",
                position_x=450,
                position_y=0,
                enabled=True,
                sync_status="pending",
                automation_id="seed-automation",
            )
        )
        session.commit()

    monkeypatch.setattr(reset, "seed", fake_seed)
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
    sync_calls: list[Any] = []

    def fake_sync(session: Session, client: Any, action_id: Any) -> None:
        sync_calls.append(action_id)
        action = session.get(ActionNode, action_id)
        assert action is not None
        action.sync_status = "enabled"
        action.automation_id = "seed-automation"
        session.add(action)
        session.commit()

    monkeypatch.setattr(
        automations,
        "sync_action",
        fake_sync,
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
    poller_state = invocations.get_poller_state(unit_session)
    assert poller_state.last_success_at is not None
    assert poller_state.last_success_at > datetime.now()
    assert (
        "seed",
        {"playbook_id": "playbook-1", "repository_full_name": scenario.repository},
    ) in calls
    seed_index = next(index for index, call in enumerate(calls) if call[0] == "seed")
    assert (
        seed_index
        < calls.index(("admin", scenario.repository))
        < calls.index(("terminate", "seed-session"))
    )
    assert git_dirs
    assert set(git_dirs) == {tmp_path / "repo"}
    assert json.loads((tmp_path / ".simulate-state.json").read_text()) == {
        "repository": scenario.repository,
        "default_branch": scenario.default_branch,
        "baseline": scenario.baseline,
        "reset_sha": "result-sha",
    }
    assert not (tmp_path / ".simulate-run.json").exists()
    assert sync_calls == [SEED_ACTION_ID]
    assert poller_events[:2] == ["lock", "delete"]


def test_reset_terminates_upstream_sessions(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    from devin_flow.models import ActionNode, Invocation

    reset.repo_dir(tmp_path).mkdir(parents=True)
    unit_session.add(
        ActionNode(
            id=SEED_ACTION_ID,
            name="Seed: Issue triage",
            position_x=0,
            position_y=0,
            enabled=True,
            sync_status="enabled",
            automation_id="automation-1",
        )
    )
    unit_session.add(
        Invocation(
            session_id="mirrored",
            automation_id="automation-1",
            action_node_id=uuid4(),
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
            seed_playbook_id="playbook-1",
        ),
    )
    monkeypatch.setattr(reset, "seed", lambda session, **kwargs: None)
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


def test_reset_syncs_displaced_action(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
    unit_session.add_all(
        [
            TriggerNode(
                id=SEED_TRIGGER_ID,
                position_x=100,
                position_y=0,
                event_action="opened",
                repository_full_name=scenario.repository,
            ),
            ActionNode(
                id=SEED_ACTION_ID,
                name="Seed: Issue triage",
                position_x=450,
                position_y=0,
                enabled=True,
                sync_status="enabled",
                automation_id="seed-automation",
                playbook_id="playbook-1",
            ),
            ActionNode(
                name="Displaced",
                position_x=0,
                position_y=0,
                enabled=True,
                sync_status="enabled",
                automation_id="displaced-automation",
                playbook_id="playbook-1",
            ),
        ]
    )
    unit_session.commit()
    displaced = unit_session.exec(
        select(ActionNode).where(ActionNode.name == "Displaced")
    ).one()
    unit_session.add(
        Edge(
            source_id=SEED_TRIGGER_ID,
            source_kind="trigger",
            target_id=displaced.id,
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
            seed_playbook_id="playbook-1",
        ),
    )
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
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
    monkeypatch.setattr(automations, "sync_action", REAL_SYNC_ACTION)
    updates: list[tuple[str, bool | None]] = []

    class FakeClient:
        def list_playbooks(self) -> list[Playbook]:
            return cast(list[Playbook], _valid_client().list_playbooks())

        def list_sessions(self, **kwargs: Any) -> list[DevinSession]:
            return []

        def update_automation(self, automation_id: str, update: Any) -> Automation:
            updates.append((automation_id, update.enabled))
            return Automation(
                automation_id=automation_id,
                name="seed",
                enabled=bool(update.enabled),
            )

    reset.reset(
        scenario,
        work_dir=tmp_path,
        session=unit_session,
        devin_client=cast(Any, FakeClient()),
    )
    assert ("displaced-automation", False) in updates


def test_reset_rejects_checkout_for_different_repository(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
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
            seed_playbook_id="playbook-1",
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
    calls: list[str] = []
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
            seed_playbook_id="playbook-1",
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
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
            seed_playbook_id="playbook-1",
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


def test_reset_deletes_state_before_failing_seed(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
    state_path = tmp_path / ".simulate-state.json"
    state_path.write_text("{}")
    (tmp_path / ".simulate-run.json").write_text("{}")
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
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
            seed_playbook_id="playbook-1",
        ),
    )

    def fail_seed(session: Session, **kwargs: Any) -> None:
        raise RuntimeError("seed failed")

    monkeypatch.setattr(reset, "seed", fail_seed)
    with pytest.raises(RuntimeError, match="seed failed"):
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )
    assert state_path.exists()
    assert (tmp_path / ".simulate-run.json").exists()


def test_reset_fails_when_seed_action_sync_is_not_enabled(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    reset.repo_dir(tmp_path).mkdir(parents=True)
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
            seed_playbook_id="playbook-1",
        ),
    )
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
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

    def seed_disabled_action(session: Session, **kwargs: Any) -> None:
        session.add(
            ActionNode(
                id=SEED_ACTION_ID,
                name="Seed: Issue triage",
                position_x=450,
                position_y=0,
                enabled=False,
                sync_status="pending",
                sync_error="upstream rejected",
            )
        )
        session.commit()

    monkeypatch.setattr(reset, "seed", seed_disabled_action)
    sync_calls: list[Any] = []
    monkeypatch.setattr(
        automations,
        "sync_action",
        lambda session, client, action_id: sync_calls.append(action_id),
    )
    with pytest.raises(
        RuntimeError, match="seed action sync failed: upstream rejected"
    ):
        reset.reset(
            scenario,
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
        )
    assert sync_calls == [SEED_ACTION_ID]
    assert not (tmp_path / ".simulate-state.json").exists()


def test_reset_requires_playbook_before_destructive_work(
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
    with pytest.raises(RuntimeError, match="SEED_PLAYBOOK_ID is required"):
        reset.reset(
            load_scenario(SCENARIO_PATH),
            work_dir=tmp_path,
            session=unit_session,
            devin_client=cast(Any, _valid_client()),
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
            seed_playbook_id="playbook-1",
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
    calls: list[str] = []
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(
            devin_api_token="token",
            devin_org_id="org",
            seed_playbook_id="playbook-1",
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
            seed_playbook_id="playbook-1",
        ),
    )
    monkeypatch.setattr(reset, "seed", _seed_enabled_action)
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
    unit_session.add(
        Invocation(
            session_id="running",
            automation_id="auto",
            action_node_id=uuid4(),
            status="running",
            session_created_at=datetime.now(),
            session_updated_at=datetime.now(),
        )
    )
    unit_session.commit()
    terminated: list[str] = []
    monkeypatch.setattr(github, "require_admin", lambda repo: None)
    monkeypatch.setattr(github, "enable_issues", lambda repo: None)
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
            seed_playbook_id="playbook-1",
        ),
    )
    unit_session.add(
        ActionNode(
            id=SEED_ACTION_ID,
            name="Seed: Issue triage",
            position_x=450,
            position_y=0,
            enabled=True,
            sync_status="enabled",
            automation_id="auto",
        )
    )
    unit_session.commit()
    monkeypatch.setattr(reset, "seed", lambda session, **kwargs: None)
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
