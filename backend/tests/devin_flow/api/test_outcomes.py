from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from devin_flow.invocations import record_outcomes
from devin_flow.models import Invocation, OutcomeNode


def create_node(client: TestClient, kind: str, x: float = 1, y: float = 2) -> str:
    response = client.post(
        f"/api/canvas/nodes/{kind}", json={"position": {"x": x, "y": y}}
    )
    assert response.status_code == 201
    return cast(str, response.json()["id"])


def create_edge(
    client: TestClient,
    source_id: str,
    source_kind: str,
    target_id: str,
    target_kind: str,
) -> Response:
    return cast(
        Response,
        client.post(
            "/api/canvas/edges",
            json={
                "source": {"id": source_id, "kind": source_kind},
                "target": {"id": target_id, "kind": target_kind},
            },
        ),
    )


def add_invocation(
    session: Session,
    action_id: UUID,
    *,
    session_id: str,
    age_seconds: int = 0,
    pull_requests: list[dict[str, Any]] | None = None,
    structured_output: dict[str, Any] | None = None,
    archived_at: datetime | None = None,
) -> Invocation:
    now = datetime.now(UTC)
    invocation = Invocation(
        session_id=session_id,
        automation_id="auto-1",
        action_node_id=action_id,
        status="exit",
        pull_requests=pull_requests or [],
        structured_output=structured_output,
        archived_at=archived_at,
        session_created_at=now - timedelta(seconds=age_seconds),
        session_updated_at=now,
    )
    session.add(invocation)
    record_outcomes(session, invocation)
    session.commit()
    return invocation


def test_unknown_outcome_node_is_404(unit_client: TestClient) -> None:
    response = unit_client.get(f"/api/outcome-nodes/{uuid4()}/invocations")
    assert response.status_code == 404
    assert response.json()["detail"] == "outcome node not found"


def test_unconnected_outcome_node_returns_empty(unit_client: TestClient) -> None:
    node_id = create_node(unit_client, "outcome")
    response = unit_client.get(f"/api/outcome-nodes/{node_id}/invocations")
    assert response.status_code == 200
    assert response.json() == []


def test_unset_kind_returns_empty(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    outcome_id = UUID(create_node(unit_client, "outcome"))
    assert (
        create_edge(
            unit_client, str(action_id), "action", str(outcome_id), "outcome"
        ).status_code
        == 201
    )
    add_invocation(
        unit_session,
        action_id,
        session_id="s-1",
        pull_requests=[{"pr_url": "https://github.com/a/b/pull/1"}],
    )
    assert unit_client.get(f"/api/outcome-nodes/{outcome_id}/invocations").json() == []


def test_lists_matching_invocations_newest_first(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    outcome = OutcomeNode(position_x=1, position_y=2, kind="duplicate")
    unit_session.add(outcome)
    unit_session.commit()
    assert (
        create_edge(
            unit_client, str(action_id), "action", str(outcome.id), "outcome"
        ).status_code
        == 201
    )
    older = add_invocation(
        unit_session,
        action_id,
        session_id="s-old",
        age_seconds=100,
        structured_output={"outcome": "duplicate", "duplicate_of": "s-0"},
    )
    newer = add_invocation(
        unit_session,
        action_id,
        session_id="s-new",
        pull_requests=[
            {"pr_url": "https://github.com/a/b/pull/1", "pr_state": "merged"}
        ],
        structured_output={"outcome": "duplicate"},
    )
    add_invocation(
        unit_session,
        action_id,
        session_id="s-other",
        structured_output={"outcome": "not_a_bug"},
    )
    response = unit_client.get(f"/api/outcome-nodes/{outcome.id}/invocations")
    assert response.status_code == 200
    rows = response.json()
    assert [row["id"] for row in rows] == [str(newer.id), str(older.id)]
    assert rows[0]["session_id"] == "s-new"
    assert rows[0]["pull_requests"] == [
        {"url": "https://github.com/a/b/pull/1", "state": "merged"}
    ]
    assert rows[1]["duplicate_of"] == "s-0"


def test_archived_invocations_are_listed_with_archive_dates(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    outcome = OutcomeNode(position_x=1, position_y=2, kind="duplicate")
    unit_session.add(outcome)
    unit_session.commit()
    assert (
        create_edge(
            unit_client, str(action_id), "action", str(outcome.id), "outcome"
        ).status_code
        == 201
    )
    add_invocation(
        unit_session,
        action_id,
        session_id="s-visible",
        structured_output={"outcome": "duplicate"},
    )
    add_invocation(
        unit_session,
        action_id,
        session_id="s-archived",
        structured_output={"outcome": "duplicate"},
        archived_at=datetime.now(UTC),
    )
    rows = unit_client.get(f"/api/outcome-nodes/{outcome.id}/invocations").json()
    assert [row["session_id"] for row in rows] == ["s-archived", "s-visible"]
    assert rows[0]["archived_at"] is not None
    assert rows[1]["archived_at"] is None


def test_pull_request_outcome_lists_only_pr_invocations(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    outcome = OutcomeNode(position_x=1, position_y=2, kind="pull_request")
    unit_session.add(outcome)
    unit_session.commit()
    assert (
        create_edge(
            unit_client, str(action_id), "action", str(outcome.id), "outcome"
        ).status_code
        == 201
    )
    with_pr = add_invocation(
        unit_session,
        action_id,
        session_id="s-pr",
        pull_requests=[{"pr_url": "https://github.com/a/b/pull/3"}],
        structured_output={"outcome": "duplicate"},
    )
    add_invocation(
        unit_session,
        action_id,
        session_id="s-dup",
        structured_output={"outcome": "duplicate"},
    )
    rows = unit_client.get(f"/api/outcome-nodes/{outcome.id}/invocations").json()
    assert [row["id"] for row in rows] == [str(with_pr.id)]
    assert cast(list[Any], rows[0]["pull_requests"])[0]["url"].endswith("/pull/3")


def test_lists_invocations_from_all_incoming_actions(
    unit_client: TestClient, unit_session: Session
) -> None:
    first_action_id = UUID(create_node(unit_client, "action"))
    second_action_id = UUID(create_node(unit_client, "action"))
    outcome = OutcomeNode(position_x=1, position_y=2, kind="duplicate")
    unit_session.add(outcome)
    unit_session.commit()
    for action_id in (first_action_id, second_action_id):
        assert (
            create_edge(
                unit_client, str(action_id), "action", str(outcome.id), "outcome"
            ).status_code
            == 201
        )
    older = add_invocation(
        unit_session,
        first_action_id,
        session_id="s-1",
        age_seconds=100,
        structured_output={"outcome": "duplicate"},
    )
    add_invocation(
        unit_session,
        first_action_id,
        session_id="s-2",
        structured_output={"outcome": "not_a_bug"},
    )
    newer = add_invocation(
        unit_session,
        second_action_id,
        session_id="s-3",
        structured_output={"outcome": "duplicate"},
    )
    rows = unit_client.get(f"/api/outcome-nodes/{outcome.id}/invocations").json()
    assert [row["id"] for row in rows] == [str(newer.id), str(older.id)]


def test_filters_invocations_by_action_node_id(
    unit_client: TestClient, unit_session: Session
) -> None:
    first_action_id = UUID(create_node(unit_client, "action"))
    second_action_id = UUID(create_node(unit_client, "action"))
    outcome = OutcomeNode(position_x=1, position_y=2, kind="duplicate")
    unit_session.add(outcome)
    unit_session.commit()
    for action_id in (first_action_id, second_action_id):
        assert (
            create_edge(
                unit_client, str(action_id), "action", str(outcome.id), "outcome"
            ).status_code
            == 201
        )
    first_match = add_invocation(
        unit_session,
        first_action_id,
        session_id="s-first",
        structured_output={"outcome": "duplicate"},
    )
    add_invocation(
        unit_session,
        second_action_id,
        session_id="s-second",
        structured_output={"outcome": "duplicate"},
    )
    rows = unit_client.get(
        f"/api/outcome-nodes/{outcome.id}/invocations",
        params={"action_node_id": str(first_action_id)},
    ).json()
    assert [row["id"] for row in rows] == [str(first_match.id)]


def test_filter_by_unconnected_action_returns_empty(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    unconnected_id = uuid4()
    outcome = OutcomeNode(position_x=1, position_y=2, kind="duplicate")
    unit_session.add(outcome)
    unit_session.commit()
    assert (
        create_edge(
            unit_client, str(action_id), "action", str(outcome.id), "outcome"
        ).status_code
        == 201
    )
    add_invocation(
        unit_session,
        action_id,
        session_id="s-1",
        structured_output={"outcome": "duplicate"},
    )
    response = unit_client.get(
        f"/api/outcome-nodes/{outcome.id}/invocations",
        params={"action_node_id": str(unconnected_id)},
    )
    assert response.status_code == 200
    assert response.json() == []
