import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from sqlmodel import Session

from devin_flow.config import Settings
from devin_flow.simulate import cli, github, report, reset, run
from devin_flow.simulate.scenario import Scenario, load_scenario

SCENARIO_PATH = Path("backend/src/devin_flow/simulate/scenario.toml")


def test_packaged_scenario_has_expected_issue_phases() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    assert len(scenario.poisons) == 3
    assert [issue.phase for issue in scenario.issues] == [
        "original",
        "original",
        "original",
        "filler",
        "filler",
        "filler",
        "duplicate",
        "duplicate",
    ]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("baseline", "baseline"),
        ("poisons", "poison ids"),
        ("issues", "issue ids"),
    ],
)
def test_scenario_rejects_invalid_ids(
    field: str, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = load_scenario(SCENARIO_PATH).model_dump()
    if field == "baseline":
        scenario[field] = "not-a-sha"
    elif field == "poisons":
        scenario[field][1]["id"] = scenario[field][0]["id"]
    else:
        scenario[field][1]["id"] = scenario[field][0]["id"]
    with pytest.raises(ValueError, match=message):
        Scenario.model_validate(scenario)


def test_scenario_rejects_phase_and_duplicate_rules() -> None:
    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][0]["phase"] = "filler"
    with pytest.raises(ValueError, match="ordered"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][-1]["duplicate_of"] = "missing"
    with pytest.raises(ValueError, match="reference"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][-1]["duplicate_of"] = None
    with pytest.raises(ValueError, match="require"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][0]["duplicate_of"] = "date-parser-offset"
    with pytest.raises(ValueError, match="only valid"):
        Scenario.model_validate(scenario)

    scenario = load_scenario(SCENARIO_PATH).model_dump()
    scenario["issues"][0]["id"] = "missing-poison"
    scenario["issues"] = scenario["issues"][:6]
    with pytest.raises(ValueError, match="fixed originals"):
        Scenario.model_validate(scenario)


def test_github_wrappers_use_expected_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:2] == ["gh", "auth"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if any("permissions.admin" in arg for arg in args):
            return subprocess.CompletedProcess(args, 0, "true\n", "")
        if args[1:3] == ["issue", "create"]:
            return subprocess.CompletedProcess(
                args, 0, "https://github.com/x/y/issues/7\n", ""
            )
        if args[1:3] == ["pr", "list"]:
            return subprocess.CompletedProcess(
                args, 0, '[{"number": 3, "headRefName": "fix/3"}]', ""
            )
        if args[1:3] == ["api", "graphql"] and "deleteIssue" not in " ".join(args):
            return subprocess.CompletedProcess(args, 0, "node-1\nnode-2\n", "")
        return subprocess.CompletedProcess(args, 0, "abc123\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    github.require_admin("xlm/superset")
    github.enable_issues("xlm/superset")
    assert github.list_issue_node_ids("xlm/superset") == ["node-1", "node-2"]
    github.delete_issue("xlm/superset", "node-1")
    assert github.list_open_prs("xlm/superset")[0].branch == "fix/3"
    github.close_pr("xlm/superset", 3)
    github.delete_branch("xlm/superset", "fix/3")
    assert github.get_branch_sha("xlm/superset", "master") == "abc123"
    assert github.create_issue("xlm/superset", "title", "body")[0] == 7
    assert calls[0] == ["gh", "auth", "status"]
    assert calls[1][:4] == ["gh", "api", "repos/xlm/superset", "--jq"]


def test_github_admin_failure_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        github,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", "no auth"),
    )
    with pytest.raises(github.GitHubError, match="admin gh login"):
        github.require_admin("xlm/superset")


def test_github_admin_requires_repository_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        github,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "false\n", ""),
    )
    with pytest.raises(github.GitHubError, match="admin gh login"):
        github.require_admin("xlm/superset")


def test_github_command_failure_uses_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 1, "stdout detail", "stderr detail"
        ),
    )
    with pytest.raises(github.GitHubError, match="stderr detail"):
        github._run("api", "bad")


def test_run_schedules_and_records_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    calls: list[str] = []
    clock = [0.0]

    monkeypatch.setattr(github, "get_branch_sha", lambda repo, branch: "reset")
    monkeypatch.setattr(
        github,
        "create_issue",
        lambda repo, title, body: (len(calls) + 1, f"https://example/{len(calls) + 1}"),
    )

    class Rng:
        def uniform(self, low: float, high: float) -> float:
            return 0

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    def create(repo: str, title: str, body: str) -> tuple[int, str]:
        calls.append(title)
        return len(calls), f"https://example/{len(calls)}"

    monkeypatch.setattr(github, "create_issue", create)
    result = run.run(
        scenario,
        state={"reset_sha": "reset"},
        work_dir=tmp_path,
        sleep=sleep,
        now=lambda: clock[0],
        rng=cast(Any, Rng()),
    )
    assert len(result["issues"]) == 8
    assert json.loads((tmp_path / ".simulate-run.json").read_text()) == result
    assert len(calls) == 8


def test_run_refuses_changed_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(github, "get_branch_sha", lambda repo, branch: "changed")
    with pytest.raises(RuntimeError, match="changed since Reset"):
        run.run(
            load_scenario(SCENARIO_PATH),
            state={"reset_sha": "reset"},
            work_dir=tmp_path,
        )


def test_reset_cleans_state_and_seeds(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    calls: list[tuple[str, Any]] = []
    tmp_path.mkdir(exist_ok=True)

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
    git_outputs = {"rev-parse": "result-sha"}

    def fake_git(work_dir: Path, *args: str) -> str:
        calls.append(("git", args))
        return git_outputs.get(args[0], "")

    monkeypatch.setattr(reset, "_git", fake_git)
    settings = Settings(DEVIN_API_TOKEN="token", DEVIN_ORG_ID="org")
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


def test_report_maps_structured_and_title_outcomes(tmp_path: Path) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps(
            {
                "issues": [
                    {"number": 1, "expected_outcome": "fixed"},
                    {"number": 2, "expected_outcome": "duplicate"},
                ]
            }
        )
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[
                {
                    "status": "exit",
                    "title": "Triage issue #2",
                    "structured_output": {"issue_number": 2, "outcome": "duplicate"},
                    "pull_requests": [],
                    "url": "session-2",
                },
                {
                    "status": "error",
                    "title": "Fix issue #1",
                    "structured_output": None,
                    "pull_requests": [{"pr_url": "pr-1"}],
                    "url": "session-1",
                },
            ],
        )
    )
    with httpx.Client(transport=transport, base_url="http://flow") as client:
        assert report.report(work_dir=tmp_path, http=client) == 0


def test_report_times_out(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps({"issues": [{"number": 1}]})
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    with httpx.Client(transport=transport, base_url="http://flow") as client:
        assert report.report(work_dir=tmp_path, timeout=0, http=client) == 1
    assert "timed out" in capsys.readouterr().out


def test_report_waits_and_closes_owned_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".simulate-run.json").write_text(
        json.dumps({"issues": [{"number": 1, "expected_outcome": "fixed"}]})
    )
    clock = [0.0]

    class FakeClient:
        def get(self, path: str) -> httpx.Response:
            return httpx.Response(
                200,
                json=[],
                request=httpx.Request("GET", "http://flow/api/invocations"),
            )

        def close(self) -> None:
            closed.append(True)

    closed: list[bool] = []
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: FakeClient())

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    assert (
        report.report(
            work_dir=tmp_path,
            timeout=1,
            sleep=sleep,
            now=lambda: clock[0],
        )
        == 1
    )
    assert closed == [True]
    assert report._issue_number({"title": "no issue"}) is None


def test_git_and_branch_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    completed = subprocess.CompletedProcess(
        ["git"], 0, "refs/heads/fix\nrefs/heads/master\n", ""
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
    assert reset._git(tmp_path, "status") == "refs/heads/fix\nrefs/heads/master"
    scenario = load_scenario(SCENARIO_PATH)
    assert reset._git_branches(scenario, tmp_path) == ["fix"]


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
    monkeypatch.setattr(reset, "_git", lambda work_dir, *args: "sha")

    def record_clone(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        work_dir.mkdir()
        clone_calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", record_clone)
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(devin_api_token="token", devin_org_id="org"),
    )
    monkeypatch.setattr(reset, "seed", lambda session, **kwargs: None)
    reset.reset(
        scenario,
        work_dir=work_dir,
        session=unit_session,
        devin_client=cast(Any, SimpleNamespace()),
    )
    assert clone_calls[0][0][:2] == ["git", "clone"]


def test_reset_handles_session_termination_without_wiping(
    tmp_path: Path,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    from devin_flow.models import Invocation

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
    monkeypatch.setattr(reset, "_git", lambda work_dir, *args: "sha")
    monkeypatch.setattr(
        reset,
        "get_settings",
        lambda: Settings(devin_api_token="token", devin_org_id="org"),
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


def test_cli_parser_and_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["--work-dir", str(tmp_path), "report", "--timeout", "1"])
    assert args.command == "report"
    assert (
        parser.parse_args(["report", "--work-dir", str(tmp_path)]).work_dir == tmp_path
    )
    scenario = load_scenario(SCENARIO_PATH)
    monkeypatch.setattr(cli, "load_scenario", lambda path: scenario)
    monkeypatch.setattr(cli, "report", SimpleNamespace(report=lambda **kwargs: 0))
    monkeypatch.setattr(
        sys, "argv", ["simulate-issues", "--work-dir", str(tmp_path), "report"]
    )
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 0


def test_cli_dispatches_run_and_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    monkeypatch.setattr(cli, "load_scenario", lambda path: scenario)
    (tmp_path / ".simulate-state.json").write_text(json.dumps({"reset_sha": "sha"}))
    run_calls: list[Any] = []
    monkeypatch.setattr(
        cast(Any, cli).run,
        "run",
        lambda scenario, **kwargs: run_calls.append((scenario, kwargs)),
    )
    monkeypatch.setattr(
        sys, "argv", ["simulate-issues", "run", "--work-dir", str(tmp_path)]
    )
    cli.main()
    assert run_calls

    monkeypatch.setattr(cli, "report", SimpleNamespace(report=lambda **kwargs: 0))
    monkeypatch.setattr(
        sys,
        "argv",
        ["simulate-issues", "run", "--report", "--work-dir", str(tmp_path)],
    )
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 0

    class FakeSession:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(cli, "Session", lambda engine: FakeSession())
    monkeypatch.setattr(cast(Any, cli).db, "get_engine", lambda: object())
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(devin_api_token="token", devin_org_id="org"),
    )
    monkeypatch.setattr(cli, "create_client", lambda settings: object())
    reset_calls: list[Any] = []
    monkeypatch.setattr(
        cast(Any, cli).reset,
        "reset",
        lambda scenario, **kwargs: reset_calls.append((scenario, kwargs)),
    )
    monkeypatch.setattr(
        sys, "argv", ["simulate-issues", "reset", "--work-dir", str(tmp_path)]
    )
    cli.main()
    assert reset_calls
