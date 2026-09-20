import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, delete, select

from devin_flow import invocations
from devin_flow.config import get_settings
from devin_flow.devin import DevinClient
from devin_flow.devin.client import TERMINAL_SESSION_STATUSES
from devin_flow.models import Invocation
from devin_flow.seed import seed
from devin_flow.simulate import github
from devin_flow.simulate.scenario import Scenario

GIT_CREDENTIAL_ARGS = (
    "-c",
    "credential.helper=",
    "-c",
    "credential.helper=!gh auth git-credential",
)
GIT_IDENTITY_ARGS = (
    "-c",
    "user.name=devin-flow simulator",
    "-c",
    "user.email=simulator@devin-flow.invalid",
)


def repo_dir(work_dir: Path) -> Path:
    return work_dir / "repo"


def _git(work_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *GIT_CREDENTIAL_ARGS, *args],
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
    work_dir.mkdir(parents=True, exist_ok=True)
    checkout_dir = repo_dir(work_dir)
    terminated: set[str] = set()
    for invocation in session.exec(select(Invocation)).all():
        if invocation.status not in TERMINAL_SESSION_STATUSES:
            devin_client.terminate_session(invocation.session_id)
            terminated.add(invocation.session_id)
    owners = invocations.automation_owners(session)
    if owners:
        for upstream_session in devin_client.list_sessions(
            automation_ids=sorted(owners),
            created_after=None,
            paginate=True,
        ):
            if (
                upstream_session.status not in TERMINAL_SESSION_STATUSES
                and upstream_session.session_id not in terminated
            ):
                devin_client.terminate_session(upstream_session.session_id)
                terminated.add(upstream_session.session_id)
    github.enable_issues(scenario.repository)
    for node_id in github.list_issue_node_ids(scenario.repository):
        github.delete_issue(scenario.repository, node_id)
    for pull_request in github.list_open_prs(scenario.repository):
        github.close_pr(scenario.repository, pull_request.number)
    if not checkout_dir.exists():
        subprocess.run(
            [
                "git",
                *GIT_CREDENTIAL_ARGS,
                "clone",
                f"https://github.com/{scenario.repository}.git",
                str(checkout_dir),
            ],
            check=True,
        )
    for branch in _git_branches(scenario, checkout_dir):
        github.delete_branch(scenario.repository, branch)
    _git(checkout_dir, "fetch", "origin")
    _git(checkout_dir, "checkout", "-B", scenario.default_branch, scenario.baseline)
    _git(checkout_dir, "reset", "--hard", scenario.baseline)
    for poison in scenario.poisons:
        patch = Path(__file__).resolve().parent / "patches" / poison.patch
        _git(checkout_dir, "apply", str(patch))
        _git(checkout_dir, "add", "-A")
        _git(
            checkout_dir,
            *GIT_IDENTITY_ARGS,
            "commit",
            "-m",
            f"chore: {poison.id}",
        )
    reset_sha = _git(checkout_dir, "rev-parse", "HEAD")
    _git(
        checkout_dir,
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
        poller_state = invocations.get_poller_state(session)
        poller_state.last_success_at = datetime.now(UTC) + invocations.SAFETY_MARGIN
        session.add(poller_state)
        session.commit()
    settings = get_settings()
    seed(
        session,
        playbook_id=settings.seed_playbook_id,
        repository_full_name=scenario.repository,
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
    result = []
    for line in branches.splitlines():
        if "\t" not in line:
            continue
        _, ref = line.split("\t", 1)
        if not ref.startswith("refs/heads/"):
            continue
        branch = ref.removeprefix("refs/heads/")
        if branch != scenario.default_branch:
            result.append(branch)
    return result
