import json
import subprocess
from pathlib import Path

from sqlmodel import Session, delete, select

from devin_flow.config import get_settings
from devin_flow.devin import DevinClient
from devin_flow.devin.client import TERMINAL_SESSION_STATUSES
from devin_flow.models import Invocation, PollerState
from devin_flow.seed import seed
from devin_flow.simulate import github
from devin_flow.simulate.scenario import Scenario


def _git(work_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=work_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def reset(
    scenario: Scenario,
    *,
    work_dir: Path,
    session: Session,
    devin_client: DevinClient,
    wipe_invocations: bool = True,
) -> str:
    github.require_admin(scenario.repository)
    for invocation in session.exec(select(Invocation)).all():
        if invocation.status not in TERMINAL_SESSION_STATUSES:
            devin_client.terminate_session(invocation.session_id)
    github.enable_issues(scenario.repository)
    for node_id in github.list_issue_node_ids(scenario.repository):
        github.delete_issue(scenario.repository, node_id)
    for pull_request in github.list_open_prs(scenario.repository):
        github.close_pr(scenario.repository, pull_request.number)
    if not work_dir.exists():
        work_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                f"https://github.com/{scenario.repository}.git",
                str(work_dir),
            ],
            check=True,
        )
    for branch in _git_branches(scenario, work_dir):
        github.delete_branch(scenario.repository, branch)
    _git(work_dir, "fetch", "origin")
    _git(work_dir, "checkout", "-B", scenario.default_branch, scenario.baseline)
    for poison in scenario.poisons:
        patch = Path(__file__).resolve().parent / poison.patch
        _git(work_dir, "apply", str(patch))
        _git(work_dir, "add", "-A")
        _git(work_dir, "commit", "-m", f"chore: {poison.id}")
    reset_sha = _git(work_dir, "rev-parse", "HEAD")
    _git(
        work_dir,
        "push",
        "--force",
        "origin",
        f"HEAD:{scenario.default_branch}",
    )
    (work_dir / ".simulate-state.json").write_text(
        json.dumps({"baseline": scenario.baseline, "reset_sha": reset_sha}, indent=2)
        + "\n"
    )
    if wipe_invocations:
        session.exec(delete(Invocation))
        session.exec(delete(PollerState))
        session.commit()
    settings = get_settings()
    seed(
        session,
        playbook_id=settings.seed_playbook_id,
        repository_full_name=settings.seed_repository_full_name,
    )
    return reset_sha


def _git_branches(scenario: Scenario, work_dir: Path) -> list[str]:
    if not work_dir.exists():
        return []
    branches = _git(
        work_dir,
        "ls-remote",
        "--heads",
        "origin",
    )
    return [
        line.rsplit("/", 1)[-1]
        for line in branches.splitlines()
        if line and not line.endswith(f"/{scenario.default_branch}")
    ]
