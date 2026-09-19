"""Derive Canvas outcomes from an Invocation's recorded fields.

Pure functions over a single Invocation: no database access. An
invocation counts toward an Outcome node's kind when a matching signal is
present: a recorded pull request, or a structured output verdict.
"""

from typing import Literal, cast

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


def pull_request_links(invocation: Invocation) -> list[PullRequestLink]:
    links: list[PullRequestLink] = []
    seen: set[str] = set()
    for entry in invocation.pull_requests:
        url = entry.get("pr_url")
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        links.append(
            PullRequestLink(url=url, state=bucket_pr_state(entry.get("pr_state")))
        )
    return links


def structured_outcome(invocation: Invocation) -> str | None:
    output = invocation.structured_output
    if not isinstance(output, dict):
        return None
    outcome = output.get("outcome")
    return outcome if isinstance(outcome, str) else None


def duplicate_of(invocation: Invocation) -> str | None:
    output = invocation.structured_output
    if not isinstance(output, dict):
        return None
    value = output.get("duplicate_of")
    return value if isinstance(value, str) else None


def outcome_kinds(invocation: Invocation) -> frozenset[OutcomeKind]:
    kinds: set[OutcomeKind] = set()
    if pull_request_links(invocation):
        kinds.add("pull_request")
    structured = structured_outcome(invocation)
    if structured in STRUCTURED_OUTCOMES:
        kinds.add(cast("OutcomeKind", structured))
    return frozenset(kinds)


def matches(invocation: Invocation, kind: OutcomeKind | None) -> bool:
    if kind is None:
        return False
    return kind in outcome_kinds(invocation)
