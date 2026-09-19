from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from devin_flow.api import canvas as canvas_api
from devin_flow.models import Edge


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


def test_empty_canvas(unit_client: TestClient) -> None:
    assert unit_client.get("/api/canvas").json() == {
        "trigger_nodes": [],
        "action_nodes": [],
        "outcome_nodes": [],
        "edges": [],
    }


def test_create_nodes_in_kind_lists(unit_client: TestClient) -> None:
    for kind in ("trigger", "action", "outcome"):
        create_node(unit_client, kind)
    canvas = unit_client.get("/api/canvas").json()
    assert [
        len(canvas[f"{kind}_nodes"]) for kind in ("trigger", "action", "outcome")
    ] == [
        1,
        1,
        1,
    ]
    assert canvas["trigger_nodes"][0]["position"] == {"x": 1, "y": 2}


def test_unknown_node_kind_is_unprocessable(unit_client: TestClient) -> None:
    assert (
        unit_client.post(
            "/api/canvas/nodes/unknown", json={"position": {"x": 0, "y": 0}}
        ).status_code
        == 422
    )


def test_move_node_updates_position(unit_client: TestClient) -> None:
    node_id = create_node(unit_client, "trigger")
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        json={"position": {"x": 4, "y": 5}},
    )
    assert response.status_code == 200
    assert response.json()["position"] == {"x": 4, "y": 5}


def test_move_and_delete_missing_or_wrong_kind_are_not_found(
    unit_client: TestClient,
) -> None:
    node_id = create_node(unit_client, "trigger")
    for path in (
        f"/api/canvas/nodes/trigger/{uuid4()}",
        f"/api/canvas/nodes/action/{node_id}",
    ):
        assert (
            unit_client.patch(path, json={"position": {"x": 0, "y": 0}}).status_code
            == 404
        )
        assert unit_client.delete(path).status_code == 404


def test_delete_node_cascades_edges_as_source_and_target(
    unit_client: TestClient,
) -> None:
    trigger_id = create_node(unit_client, "trigger")
    action_id = create_node(unit_client, "action")
    outcome_id = create_node(unit_client, "outcome")
    assert (
        create_edge(unit_client, trigger_id, "trigger", action_id, "action").status_code
        == 201
    )
    assert (
        create_edge(unit_client, action_id, "action", outcome_id, "outcome").status_code
        == 201
    )
    assert (
        unit_client.delete(f"/api/canvas/nodes/action/{action_id}").status_code == 204
    )
    assert unit_client.get("/api/canvas").json()["edges"] == []


def test_create_edges_returns_full_shape(unit_client: TestClient) -> None:
    trigger_id = create_node(unit_client, "trigger")
    action_id = create_node(unit_client, "action")
    response = create_edge(unit_client, trigger_id, "trigger", action_id, "action")
    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "source": {"id": trigger_id, "kind": "trigger"},
        "target": {"id": action_id, "kind": "action"},
        "automation_id": None,
        "sync_status": "unprovisioned",
        "sync_error": None,
    }


def test_create_edge_forbidden_pair_is_conflict(unit_client: TestClient) -> None:
    source_id = create_node(unit_client, "action")
    target_id = create_node(unit_client, "trigger")
    response = create_edge(unit_client, source_id, "action", target_id, "trigger")
    assert response.status_code == 409
    assert "edges must connect" in response.json()["detail"]


def test_create_edge_missing_endpoints(unit_client: TestClient) -> None:
    action_id = create_node(unit_client, "action")
    response = create_edge(unit_client, str(uuid4()), "trigger", action_id, "action")
    assert response.status_code == 404
    assert response.json()["detail"] == "source node not found"
    response = create_edge(
        unit_client,
        create_node(unit_client, "trigger"),
        "trigger",
        str(uuid4()),
        "action",
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "target node not found"


def test_create_edge_conflicts(unit_client: TestClient) -> None:
    trigger_id = create_node(unit_client, "trigger")
    first_action_id = create_node(unit_client, "action")
    second_action_id = create_node(unit_client, "action")
    assert (
        create_edge(
            unit_client, trigger_id, "trigger", first_action_id, "action"
        ).status_code
        == 201
    )
    duplicate = create_edge(
        unit_client, trigger_id, "trigger", first_action_id, "action"
    )
    assert duplicate.status_code == 409
    outgoing = create_edge(
        unit_client, trigger_id, "trigger", second_action_id, "action"
    )
    assert outgoing.status_code == 409
    second_trigger = create_node(unit_client, "trigger")
    incoming = create_edge(
        unit_client, second_trigger, "trigger", first_action_id, "action"
    )
    assert incoming.status_code == 409


def test_create_edge_allowed_independent_rules(unit_client: TestClient) -> None:
    trigger_id = create_node(unit_client, "trigger")
    action_id = create_node(unit_client, "action")
    first_outcome_id = create_node(unit_client, "outcome")
    second_outcome_id = create_node(unit_client, "outcome")
    assert (
        create_edge(
            unit_client, action_id, "action", first_outcome_id, "outcome"
        ).status_code
        == 201
    )
    assert (
        create_edge(
            unit_client, action_id, "action", second_outcome_id, "outcome"
        ).status_code
        == 201
    )
    assert (
        create_edge(unit_client, trigger_id, "trigger", action_id, "action").status_code
        == 201
    )


def test_create_edge_database_conflict(
    unit_client: TestClient,
    unit_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trigger_id = create_node(unit_client, "trigger")
    action_id = create_node(unit_client, "action")
    unit_session.add(
        Edge(
            source_id=UUID(trigger_id),
            source_kind="trigger",
            target_id=UUID(action_id),
            target_kind="action",
        )
    )
    unit_session.commit()
    monkeypatch.setattr(canvas_api, "check_edge_uniqueness", lambda *_args: None)
    response = create_edge(unit_client, trigger_id, "trigger", action_id, "action")
    assert response.status_code == 409
    assert response.json()["detail"] == "edge conflicts with an existing edge"


def test_get_canvas_excludes_soft_deleted_edge(
    unit_client: TestClient, unit_session: Session
) -> None:
    trigger_id = create_node(unit_client, "trigger")
    action_id = create_node(unit_client, "action")
    edge_id = create_edge(
        unit_client, trigger_id, "trigger", action_id, "action"
    ).json()["id"]
    edge = unit_session.get(Edge, UUID(edge_id))
    assert edge is not None
    edge.deleted_at = datetime.now(UTC)
    unit_session.add(edge)
    unit_session.commit()
    assert unit_client.get("/api/canvas").json()["edges"] == []
    assert unit_client.delete(f"/api/canvas/edges/{edge_id}").status_code == 404


def test_delete_edge_is_hard_delete(unit_client: TestClient) -> None:
    trigger_id = create_node(unit_client, "trigger")
    action_id = create_node(unit_client, "action")
    edge_id = create_edge(
        unit_client, trigger_id, "trigger", action_id, "action"
    ).json()["id"]
    assert unit_client.delete(f"/api/canvas/edges/{edge_id}").status_code == 204
    assert unit_client.delete(f"/api/canvas/edges/{edge_id}").status_code == 404
