"""Derive Canvas outcomes from an Invocation's recorded fields.

Pure functions over a single Invocation: no database access. An
invocation counts toward an Outcome node's kind when a matching signal is
present: a recorded pull request, or a structured output verdict.
"""

from typing import Any, Literal, cast

from pydantic import BaseModel

from devin_flow.models import Invocation, OutcomeKind

PrState = Literal["open", "merged", "closed", "other"]

STRUCTURED_OUTCOMES: frozenset[str] = frozenset(
    {"duplicate", "not_reproducible", "not_a_bug"}
)


class PullRequestLink(BaseModel):
    url: str
    state: PrState


def bucket_pr_state(state: object) -> PrState:
    lowered = state.lower() if isinstance(state, str) else ""
    if lowered in ("open", "merged", "closed"):
        return cast("PrState", lowered)
    return "other"


def _links(pull_requests: list[dict[str, Any]]) -> list[PullRequestLink]:
    links: list[PullRequestLink] = []
    seen: set[str] = set()
    for entry in pull_requests:
        url = entry.get("pr_url")
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        links.append(
            PullRequestLink(url=url, state=bucket_pr_state(entry.get("pr_state")))
        )
    return links


def pull_request_links(invocation: Invocation) -> list[PullRequestLink]:
    return _links(invocation.pull_requests)


def _structured_outcome(output: object) -> str | None:
    if not isinstance(output, dict):
        return None
    outcome = output.get("outcome")
    return outcome if isinstance(outcome, str) else None


def structured_outcome(invocation: Invocation) -> str | None:
    return _structured_outcome(invocation.structured_output)


def _duplicate_of(output: object) -> str | None:
    if not isinstance(output, dict):
        return None
    value = output.get("duplicate_of")
    return value if isinstance(value, str) else None


def duplicate_of(invocation: Invocation) -> str | None:
    return _duplicate_of(invocation.structured_output)


def derive_outcome_kinds(
    pull_requests: list[dict[str, Any]], structured_output: object
) -> frozenset[OutcomeKind]:
    kinds: set[OutcomeKind] = set()
    if _links(pull_requests):
        kinds.add("pull_request")
    structured = _structured_outcome(structured_output)
    if structured in STRUCTURED_OUTCOMES:
        kinds.add(cast("OutcomeKind", structured))
    return frozenset(kinds)


def outcome_kinds(invocation: Invocation) -> frozenset[OutcomeKind]:
    return derive_outcome_kinds(invocation.pull_requests, invocation.structured_output)


def matches(invocation: Invocation, kind: OutcomeKind | None) -> bool:
    if kind is None:
        return False
    return kind in outcome_kinds(invocation)
