import json
import time
from collections.abc import Callable
from pathlib import Path
from random import Random
from typing import Any

from devin_flow.simulate import github
from devin_flow.simulate.scenario import Scenario


def run(
    scenario: Scenario,
    *,
    state: dict[str, Any],
    work_dir: Path,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    rng: Random | None = None,
) -> dict[str, Any]:
    expected_sha = state["reset_sha"]
    actual_sha = github.get_branch_sha(scenario.repository, scenario.default_branch)
    if actual_sha != expected_sha:
        raise RuntimeError(
            "Target branch changed since Reset: "
            f"expected {expected_sha}, got {actual_sha}"
        )
    random = rng or Random()
    started = now()
    filed: list[dict[str, Any]] = []
    groups = [
        [issue for issue in scenario.issues if issue.phase == phase]
        for phase in ("original", "filler", "duplicate")
    ]
    phase_seconds = scenario.window_seconds / 3
    for phase_index, issues in enumerate(groups):
        for index, issue in enumerate(issues):
            offset = phase_index * phase_seconds
            if issues:
                offset += (index + 1) * phase_seconds / (len(issues) + 1)
            offset += random.uniform(-1, 1)
            delay = max(0, offset - (now() - started))
            sleep(delay)
            number, url = github.create_issue(
                scenario.repository, issue.title, issue.body
            )
            filed.append(
                {
                    "number": number,
                    "scenario_id": issue.id,
                    "expected_outcome": issue.expected_outcome,
                    "url": url,
                }
            )
            print(f"{now() - started:7.1f}s issue #{number} {issue.id}: {url}")
    result = {"reset_sha": expected_sha, "issues": filed}
    (work_dir / ".simulate-run.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
