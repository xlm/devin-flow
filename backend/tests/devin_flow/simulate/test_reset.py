import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlmodel import Session

from devin_flow import invocations
from devin_flow.config import Settings
from devin_flow.devin.client import DevinSession
from devin_flow.simulate import github, reset
from devin_flow.simulate.scenario import load_scenario

from .conftest import SCENARIO_PATH


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
        seed_repository_full_name="wrong/repository",
    )
    monkeypatch.setattr(reset, "get_settings", lambda: settings)
    monkeypatch.setattr(
        reset, "seed", lambda session, **kwargs: calls.append(("seed", kwargs))
    )
    result = reset.reset(
        scenario,
        work_dir=tmp_path,
        session=unit_session,
        devin_client=cast(Any, SimpleNamespace()),
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
    assert git_dirs
    assert set(git_dirs) == {tmp_path / "repo"}
    assert json.loads((tmp_path / ".simulate-state.json").read_text()) == {
        "repository": scenario.repository,
        "default_branch": scenario.default_branch,
        "baseline": scenario.baseline,
        "reset_sha": "result-sha",
    }
    assert not (tmp_path / ".simulate-run.json").exists()


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
            name="action",
            position_x=0,
            position_y=0,
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
            devin_client=cast(Any, SimpleNamespace()),
        )
    assert calls == ["admin"]


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
            devin_client=cast(Any, SimpleNamespace()),
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
            devin_client=cast(Any, SimpleNamespace()),
        )
    assert not state_path.exists()
    assert not (tmp_path / ".simulate-run.json").exists()


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
            devin_client=cast(Any, SimpleNamespace()),
        )
    assert calls == []
    assert not (tmp_path / ".simulate-run.json").exists()


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
    monkeypatch.setattr(reset, "seed", lambda session, **kwargs: None)
    reset.reset(
        scenario,
        work_dir=work_dir,
        session=unit_session,
        devin_client=cast(Any, SimpleNamespace()),
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
    monkeypatch.setattr(reset, "seed", lambda session, **kwargs: None)
    client = SimpleNamespace(
        terminate_session=lambda session_id: terminated.append(session_id)
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
