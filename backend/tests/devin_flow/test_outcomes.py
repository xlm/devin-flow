from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from devin_flow.models import Invocation
from devin_flow.outcomes import (
    IssueRef,
    bucket_pr_state,
    duplicate_of,
    issue_ref,
    matches,
    outcome_kinds,
    pull_request_links,
    structured_outcome,
)


def invocation(
    *,
    pull_requests: list[dict[str, Any]] | None = None,
    structured_output: dict[str, Any] | None = None,
) -> Invocation:
    now = datetime.now(UTC)
    return Invocation(
        session_id=str(uuid4()),
        automation_id="auto-1",
        action_node_id=uuid4(),
        status="exit",
        pull_requests=pull_requests or [],
        structured_output=structured_output,
        session_created_at=now,
        session_updated_at=now,
    )


def test_bucket_pr_state() -> None:
    assert bucket_pr_state("open") == "open"
    assert bucket_pr_state("merged") == "merged"
    assert bucket_pr_state("closed") == "closed"
    assert bucket_pr_state("MERGED") == "merged"
    assert bucket_pr_state(None) == "other"
    assert bucket_pr_state("draft") == "other"
    assert bucket_pr_state(12) == "other"


def test_pull_request_links_bucketing_and_dedupe() -> None:
    inv = invocation(
        pull_requests=[
            {"pr_url": "https://github.com/a/b/pull/1", "pr_state": "merged"},
            {"pr_url": "https://github.com/a/b/pull/1", "pr_state": "open"},
            {"pr_url": "https://github.com/a/b/pull/2"},
            {"pr_state": "open"},
            {"pr_url": ""},
            {"pr_url": 7},
        ]
    )
    links = pull_request_links(inv)
    assert [link.url for link in links] == [
        "https://github.com/a/b/pull/1",
        "https://github.com/a/b/pull/2",
    ]
    assert links[0].state == "merged"
    assert links[1].state == "other"


def test_structured_outcome_and_duplicate_of() -> None:
    inv = invocation(structured_output={"outcome": "duplicate", "duplicate_of": "s-9"})
    assert structured_outcome(inv) == "duplicate"
    assert duplicate_of(inv) == "s-9"
    inv = invocation()
    assert structured_outcome(inv) is None
    assert duplicate_of(inv) is None


def test_structured_output_not_a_dict_or_not_a_str() -> None:
    inv = invocation(structured_output={"outcome": 42})
    assert structured_outcome(inv) is None
    assert outcome_kinds(inv) == frozenset()
    inv2 = invocation()
    object.__setattr__(inv2, "structured_output", ["not", "a", "dict"])
    assert structured_outcome(inv2) is None
    assert duplicate_of(inv2) is None


def test_fixed_is_not_an_outcome_kind() -> None:
    inv = invocation(structured_output={"outcome": "fixed"})
    assert outcome_kinds(inv) == frozenset()


def test_pull_request_kind() -> None:
    inv = invocation(pull_requests=[{"pr_url": "https://github.com/a/b/pull/1"}])
    assert outcome_kinds(inv) == frozenset({"pull_request"})
    assert matches(inv, "pull_request")
    assert not matches(inv, "duplicate")


@pytest.mark.parametrize("kind", ["duplicate", "not_reproducible", "not_a_bug"])
def test_structured_outcome_kinds(kind: str) -> None:
    inv = invocation(structured_output={"outcome": kind})
    assert outcome_kinds(inv) == frozenset({kind})
    assert matches(inv, kind)  # type: ignore[arg-type]


def test_invocation_matching_both_kinds() -> None:
    inv = invocation(
        pull_requests=[{"pr_url": "https://github.com/a/b/pull/1"}],
        structured_output={"outcome": "duplicate"},
    )
    assert outcome_kinds(inv) == frozenset({"pull_request", "duplicate"})


def test_invocation_matching_neither() -> None:
    inv = invocation()
    assert outcome_kinds(inv) == frozenset()
    assert not matches(inv, "pull_request")


def test_matches_with_none_kind_is_always_false() -> None:
    inv = invocation(
        pull_requests=[{"pr_url": "https://github.com/a/b/pull/1"}],
        structured_output={"outcome": "duplicate"},
    )
    assert not matches(inv, None)


def test_issue_ref_from_structured_output() -> None:
    inv = invocation(
        structured_output={
            "issue_url": "https://github.com/a/b/issues/7",
            "issue_number": 7,
            "issue_title": "Crash on save",
        }
    )
    assert issue_ref(inv, None) == IssueRef(
        url="https://github.com/a/b/issues/7", number=7, title="Crash on save"
    )


def test_issue_ref_structured_output_with_wrong_typed_fields() -> None:
    inv = invocation(
        structured_output={
            "issue_url": "https://github.com/a/b/issues/7",
            "issue_number": "7",
            "issue_title": 12,
        }
    )
    ref = issue_ref(inv, "a/b")
    assert ref == IssueRef(
        url="https://github.com/a/b/issues/7", number=None, title=None
    )


def test_issue_ref_bool_issue_number_is_rejected() -> None:
    inv = invocation(
        structured_output={
            "issue_url": "https://github.com/a/b/issues/7",
            "issue_number": True,
        }
    )
    ref = issue_ref(inv, None)
    assert ref is not None
    assert ref.number is None


def test_issue_ref_empty_or_missing_url_falls_through_to_title() -> None:
    for output in ({"issue_url": ""}, {"issue_url": 5}, {}, None):
        inv = invocation(structured_output=output)
        assert issue_ref(inv, "a/b") is None
        inv = invocation(structured_output=output)
        object.__setattr__(inv, "title", "Triage #3")
        assert issue_ref(inv, "a/b") == IssueRef(
            url="https://github.com/a/b/issues/3", number=3, title=None
        )


def test_issue_ref_title_fallback_without_repository() -> None:
    inv = invocation()
    object.__setattr__(inv, "title", "Triage #3")
    assert issue_ref(inv, None) is None


def test_issue_ref_title_fallback_without_match() -> None:
    inv = invocation()
    object.__setattr__(inv, "title", "No issue here")
    assert issue_ref(inv, "a/b") is None
