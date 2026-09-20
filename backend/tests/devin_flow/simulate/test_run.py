import json
from pathlib import Path
from typing import Any, cast

import pytest

from devin_flow.simulate import github, run
from devin_flow.simulate.scenario import load_scenario

from .conftest import SCENARIO_PATH


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
        state={
            "repository": scenario.repository,
            "default_branch": scenario.default_branch,
            "baseline": scenario.baseline,
            "reset_sha": "reset",
        },
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
            state={
                "repository": "xlm/superset",
                "default_branch": "master",
                "baseline": load_scenario(SCENARIO_PATH).baseline,
                "reset_sha": "reset",
            },
            work_dir=tmp_path,
        )


def test_run_refuses_existing_run_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    (tmp_path / ".simulate-run.json").write_text("{}")
    monkeypatch.setattr(
        github,
        "get_branch_sha",
        lambda repo, branch: pytest.fail("existing run must be checked first"),
    )
    with pytest.raises(
        RuntimeError, match="issues already filed for this reset, run reset again"
    ):
        run.run(
            scenario,
            state={
                "repository": scenario.repository,
                "default_branch": scenario.default_branch,
                "baseline": scenario.baseline,
                "reset_sha": "reset",
            },
            work_dir=tmp_path,
        )


def test_run_persists_partial_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    calls = 0

    monkeypatch.setattr(github, "get_branch_sha", lambda repo, branch: "reset")

    def create_issue(repo: str, title: str, body: str) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("create failed")
        return calls, f"https://example/{calls}"

    monkeypatch.setattr(github, "create_issue", create_issue)
    with pytest.raises(RuntimeError, match="create failed"):
        run.run(
            scenario,
            state={
                "repository": scenario.repository,
                "default_branch": scenario.default_branch,
                "baseline": scenario.baseline,
                "reset_sha": "reset",
            },
            work_dir=tmp_path,
            sleep=lambda seconds: None,
            now=lambda: 0,
        )
    partial = json.loads((tmp_path / ".simulate-run.json").read_text())
    assert len(partial["issues"]) == 2


def test_run_rejects_different_or_legacy_state(tmp_path: Path) -> None:
    scenario = load_scenario(SCENARIO_PATH)
    state = {
        "repository": scenario.repository,
        "default_branch": scenario.default_branch,
        "baseline": scenario.baseline,
        "reset_sha": "reset",
    }
    for key in ("repository", "default_branch", "baseline"):
        mismatched = state | {key: "different"}
        with pytest.raises(RuntimeError, match="different Scenario"):
            run.run(scenario, state=mismatched, work_dir=tmp_path)
    with pytest.raises(RuntimeError, match="different Scenario"):
        run.run(scenario, state={"reset_sha": "reset"}, work_dir=tmp_path)
