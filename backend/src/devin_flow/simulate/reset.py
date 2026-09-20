import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, col, delete, select

from devin_flow import invocations
from devin_flow.config import get_settings
from devin_flow.devin import DevinClient
from devin_flow.devin.client import TERMINAL_SESSION_STATUSES
from devin_flow.models import ActionNode, Edge, Invocation, TriggerNode
from devin_flow.seed import find_seed_playbook
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


def target_automation_ids(session: Session, repository: str) -> list[str]:
    trigger_ids = select(TriggerNode.id).where(
        TriggerNode.repository_full_name == repository
    )
    action_ids = select(Edge.target_id).where(
        col(Edge.source_id).in_(trigger_ids),
        Edge.source_kind == "trigger",
        Edge.target_kind == "action",
    )
    actions = session.exec(
        select(ActionNode).where(
            col(ActionNode.id).in_(action_ids),
            col(ActionNode.archived_at).is_(None),
            col(ActionNode.automation_id).is_not(None),
        )
    ).all()
    return sorted(
        {action.automation_id for action in actions if action.automation_id is not None}
    )


def reset(
    scenario: Scenario,
    *,
    work_dir: Path,
    session: Session,
    devin_client: DevinClient,
    wipe_invocations: bool = True,
) -> str:
    settings = get_settings()
    playbook = find_seed_playbook(devin_client)
    if playbook is None:
        raise RuntimeError(
            "playbook 'Issue triage' not found in the Devin org, "
            "run uv run sync-playbooks"
        )
    playbook_id = playbook.playbook_id
    schema = playbook.structured_output_schema
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or "issue_number" not in properties:
        raise RuntimeError(
            f"playbook {playbook_id} structured output schema lacks issue_number, "
            "run uv run sync-playbooks"
        )
    if scenario.repository != settings.seed_repository_full_name:
        raise RuntimeError(
            f"scenario repository {scenario.repository} does not match "
            f"SEED_REPOSITORY_FULL_NAME {settings.seed_repository_full_name}"
        )
    patch_paths = [scenario.patch_path(poison) for poison in scenario.poisons]
    for patch_path in patch_paths:
        if not patch_path.exists():
            raise RuntimeError(f"missing poison patch: {patch_path}")
    automation_ids = target_automation_ids(session, scenario.repository)
    if not automation_ids:
        raise RuntimeError(
            "no enabled Action with an Automation is connected to a Trigger for "
            f"{scenario.repository}, build the Flow on the Canvas first "
            "(or run uv run seed)"
        )
    state_path = work_dir / ".simulate-state.json"
    run_path = work_dir / ".simulate-run.json"
    work_dir.mkdir(parents=True, exist_ok=True)
    checkout_dir = repo_dir(work_dir)
    if checkout_dir.exists():
        try:
            origin_url = _git(checkout_dir, "config", "--get", "remote.origin.url")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "simulator checkout repository mismatch: "
                f"expected {scenario.repository}, got unavailable origin"
            ) from exc
        actual_repository = _normalize_repository(origin_url)
        if actual_repository != scenario.repository:
            raise RuntimeError(
                "simulator checkout repository mismatch: "
                f"expected {scenario.repository}, got {actual_repository}"
            )
    state_path.unlink(missing_ok=True)
    run_path.unlink(missing_ok=True)
    github.require_admin(scenario.repository)
    terminated: set[str] = set()
    for invocation in session.exec(
        select(Invocation).where(
            col(Invocation.automation_id).in_(automation_ids),
        )
    ).all():
        if invocation.status not in TERMINAL_SESSION_STATUSES:
            devin_client.terminate_session(invocation.session_id)
            terminated.add(invocation.session_id)
    for upstream_session in devin_client.list_sessions(
        automation_ids=automation_ids,
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
    github.ensure_labels(scenario.repository)
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
    _git(checkout_dir, "clean", "-fdx")
    for poison, patch in zip(scenario.poisons, patch_paths, strict=True):
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
    if wipe_invocations:
        invocations.poll_once(session, devin_client)
        poller_state = invocations.get_poller_state(session)
        session.exec(
            delete(Invocation).where(
                col(Invocation.automation_id).in_(automation_ids),
            )
        )
        poller_state.last_success_at = datetime.now(UTC) + invocations.SAFETY_MARGIN
        session.add(poller_state)
        session.commit()
    state_path.write_text(
        json.dumps(
            {
                "repository": scenario.repository,
                "default_branch": scenario.default_branch,
                "baseline": scenario.baseline,
                "reset_sha": reset_sha,
            },
            indent=2,
        )
        + "\n"
    )
    return reset_sha


def _normalize_repository(origin_url: str) -> str:
    normalized = origin_url.strip().removesuffix(".git").rstrip("/")
    for marker in ("github.com/", "github.com:"):
        if marker in normalized:
            return normalized.rsplit(marker, 1)[1]
    return normalized


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
