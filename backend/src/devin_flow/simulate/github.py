import subprocess
from dataclasses import dataclass


class GitHubError(RuntimeError):
    pass


TRIAGE_LABELS: dict[str, tuple[str, str]] = {
    "bug": ("d73a4a", "Something isn't working"),
    "duplicate": ("cfd3d7", "This issue or pull request already exists"),
    "enhancement": ("a2eeef", "New feature or request"),
    "question": ("d876e3", "Further information is requested"),
    "needs-repro": ("e4e669", "Closed pending reproducible steps, reopen with them"),
}


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitHubError(detail or f"gh exited with {result.returncode}")
    return result


def require_admin(repo: str) -> None:
    auth = _run("auth", "status", check=False)
    if auth.returncode:
        raise GitHubError(
            "an admin gh login on the Target repository is a prerequisite"
        )
    permissions = _run("api", f"repos/{repo}", "--jq", ".permissions.admin")
    if permissions.stdout.strip().lower() != "true":
        raise GitHubError(
            "an admin gh login on the Target repository is a prerequisite"
        )


def enable_issues(repo: str) -> None:
    _run("api", "--method", "PATCH", f"repos/{repo}", "-f", "has_issues=true")


def default_branch(repo: str) -> str:
    return _run("api", f"repos/{repo}", "--jq", ".default_branch").stdout.strip()


def ensure_labels(repo: str) -> None:
    for name, (color, description) in TRIAGE_LABELS.items():
        _run(
            "label",
            "create",
            name,
            "--repo",
            repo,
            "--color",
            color,
            "--description",
            description,
            "--force",
        )


def list_issue_node_ids(repo: str) -> list[str]:
    owner, name = repo.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$endCursor:String) { "
        "repository(owner:$owner,name:$name) { issues(first:100,after:$endCursor,"
        "states:[OPEN,CLOSED]) { nodes { id } pageInfo { hasNextPage endCursor } } } }"
    )
    result = _run(
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-f",
        f"owner={owner}",
        "-f",
        f"name={name}",
        "--paginate",
        "--jq",
        ".data.repository.issues.nodes[].id",
    )
    return [line for line in result.stdout.splitlines() if line]


def delete_issue(repo: str, node_id: str) -> None:
    mutation = (
        "mutation($id:ID!) { deleteIssue(input:{issueId:$id}) { clientMutationId } }"
    )
    _run(
        "api",
        "graphql",
        "-f",
        f"query={mutation}",
        "-f",
        f"id={node_id}",
    )


@dataclass(frozen=True)
class PullRequest:
    number: int
    branch: str


def list_open_prs(repo: str) -> list[PullRequest]:
    result = _run(
        "api",
        "--paginate",
        f"repos/{repo}/pulls?state=open",
        "--jq",
        ".[] | [.number, .head.ref] | @tsv",
    )
    return [
        PullRequest(number=int(number), branch=branch)
        for number, branch in (
            line.split("\t", 1) for line in result.stdout.splitlines() if line
        )
    ]


def close_pr(repo: str, number: int) -> None:
    _run("pr", "close", str(number), "--repo", repo)


def delete_branch(repo: str, branch: str) -> None:
    _run("api", "--method", "DELETE", f"repos/{repo}/git/refs/heads/{branch}")


def get_branch_sha(repo: str, branch: str) -> str:
    result = _run("api", f"repos/{repo}/branches/{branch}", "--jq", ".commit.sha")
    return result.stdout.strip()


def create_issue(repo: str, title: str, body: str) -> tuple[int, str]:
    result = _run("issue", "create", "--repo", repo, "--title", title, "--body", body)
    url = result.stdout.strip().splitlines()[-1]
    return int(url.rstrip("/").rsplit("/", 1)[-1]), url
