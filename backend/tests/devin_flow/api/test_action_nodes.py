from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from devin_flow.models import Invocation, TriggerNode


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
) -> None:
    response = client.post(
        "/api/canvas/edges",
        json={
            "source": {"id": source_id, "kind": source_kind},
            "target": {"id": target_id, "kind": target_kind},
        },
    )
    assert response.status_code == 201


def add_invocation(
    session: Session,
    action_id: UUID,
    *,
    session_id: str,
    age_seconds: int = 0,
    title: str | None = None,
    structured_output: dict[str, Any] | None = None,
) -> Invocation:
    now = datetime.now(UTC)
    invocation = Invocation(
        session_id=session_id,
        automation_id="auto-1",
        action_node_id=action_id,
        status="exit",
        title=title,
        pull_requests=[],
        structured_output=structured_output,
        session_created_at=now - timedelta(seconds=age_seconds),
        session_updated_at=now,
    )
    session.add(invocation)
    session.commit()
    return invocation


def test_unknown_action_node_is_404(unit_client: TestClient) -> None:
    response = unit_client.get(f"/api/action-nodes/{uuid4()}/invocations")
    assert response.status_code == 404
    assert response.json()["detail"] == "action node not found"


def test_action_node_without_invocations_returns_empty(
    unit_client: TestClient,
) -> None:
    node_id = create_node(unit_client, "action")
    response = unit_client.get(f"/api/action-nodes/{node_id}/invocations")
    assert response.status_code == 200
    assert response.json() == []


def test_lists_invocations_newest_first(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    other_id = UUID(create_node(unit_client, "action"))
    older = add_invocation(unit_session, action_id, session_id="s-old", age_seconds=100)
    newer = add_invocation(unit_session, action_id, session_id="s-new")
    add_invocation(unit_session, other_id, session_id="s-other")
    response = unit_client.get(f"/api/action-nodes/{action_id}/invocations")
    assert response.status_code == 200
    rows = response.json()
    assert [row["id"] for row in rows] == [str(newer.id), str(older.id)]
    assert rows[0]["issue"] is None


def test_issue_from_structured_output(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    add_invocation(
        unit_session,
        action_id,
        session_id="s-1",
        structured_output={
            "issue_url": "https://github.com/a/b/issues/9",
            "issue_number": 9,
            "issue_title": "Boom",
        },
    )
    rows = unit_client.get(f"/api/action-nodes/{action_id}/invocations").json()
    assert rows[0]["issue"] == {
        "url": "https://github.com/a/b/issues/9",
        "number": 9,
        "title": "Boom",
    }


def test_issue_from_title_via_trigger_repository(
    unit_client: TestClient, unit_session: Session
) -> None:
    trigger = TriggerNode(
        position_x=0,
        position_y=0,
        repository_full_name="a/b",
    )
    unit_session.add(trigger)
    unit_session.commit()
    action_id = UUID(create_node(unit_client, "action"))
    create_edge(unit_client, str(trigger.id), "trigger", str(action_id), "action")
    add_invocation(unit_session, action_id, session_id="s-1", title="Triage #42")
    rows = unit_client.get(f"/api/action-nodes/{action_id}/invocations").json()
    assert rows[0]["issue"] == {
        "url": "https://github.com/a/b/issues/42",
        "number": 42,
        "title": None,
    }


def test_issue_none_without_trigger(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    add_invocation(unit_session, action_id, session_id="s-1", title="Triage #42")
    rows = unit_client.get(f"/api/action-nodes/{action_id}/invocations").json()
    assert rows[0]["issue"] is None
