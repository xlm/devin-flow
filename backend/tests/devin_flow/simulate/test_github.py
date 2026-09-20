import subprocess
from typing import Any

import pytest

from devin_flow.simulate import github


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
        if args[1:3] == ["api", "--paginate"]:
            return subprocess.CompletedProcess(args, 0, "3\tfix/3\n", "")
        if args[1:3] == ["api", "graphql"] and "deleteIssue" not in " ".join(args):
            return subprocess.CompletedProcess(args, 0, "node-1\nnode-2\n", "")
        return subprocess.CompletedProcess(args, 0, "abc123\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    github.require_admin("xlm/superset")
    github.enable_issues("xlm/superset")
    assert github.default_branch("xlm/superset") == "abc123"
    github.ensure_labels("xlm/superset")
    assert github.list_issue_node_ids("xlm/superset") == ["node-1", "node-2"]
    github.delete_issue("xlm/superset", "node-1")
    assert github.list_open_prs("xlm/superset")[0].branch == "fix/3"
    github.close_pr("xlm/superset", 3)
    github.delete_branch("xlm/superset", "fix/3")
    assert github.get_branch_sha("xlm/superset", "master") == "abc123"
    assert github.create_issue("xlm/superset", "title", "body")[0] == 7
    assert calls[0] == ["gh", "auth", "status"]
    assert calls[1][:4] == ["gh", "api", "repos/xlm/superset", "--jq"]
    assert [
        "gh",
        "api",
        "repos/xlm/superset",
        "--jq",
        ".default_branch",
    ] in calls
    assert [
        "gh",
        "api",
        "--paginate",
        "repos/xlm/superset/pulls?state=open",
        "--jq",
        ".[] | [.number, .head.ref] | @tsv",
    ] in calls
    assert [
        "gh",
        "label",
        "create",
        "bug",
        "--repo",
        "xlm/superset",
        "--color",
        "d73a4a",
        "--description",
        "Something isn't working",
        "--force",
    ] in calls


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
