from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, select

from devin_flow.api import canvas as canvas_api
from devin_flow.models import ActionNode, Edge, EventAction


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
    assert canvas["trigger_nodes"][0]["trigger"] == {
        "event_action": None,
        "repository_full_name": None,
    }
    assert canvas["action_nodes"][0]["trigger"] is None


def test_event_action_is_exported() -> None:
    assert EventAction


def test_create_trigger_with_fields_and_patch_independently(
    unit_client: TestClient,
) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/trigger",
        json={
            "position": {"x": 1, "y": 2},
            "trigger": {
                "event_action": "opened",
                "repository_full_name": "octo/repo",
            },
        },
    )
    assert response.status_code == 201
    node_id = response.json()["id"]
    assert response.json()["trigger"] == {
        "event_action": "opened",
        "repository_full_name": "octo/repo",
    }
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        json={"trigger": {"event_action": "closed"}},
    )
    assert response.status_code == 200
    assert response.json()["trigger"] == {
        "event_action": "closed",
        "repository_full_name": "octo/repo",
    }
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        json={"trigger": {"repository_full_name": "octo/other"}},
    )
    assert response.json()["trigger"] == {
        "event_action": "closed",
        "repository_full_name": "octo/other",
    }


def test_patch_trigger_explicit_null_clears_only_one_field(
    unit_client: TestClient,
) -> None:
    node_id = unit_client.post(
        "/api/canvas/nodes/trigger",
        json={
            "position": {"x": 1, "y": 2},
            "trigger": {
                "event_action": "opened",
                "repository_full_name": "octo/repo",
            },
        },
    ).json()["id"]
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        json={"trigger": {"repository_full_name": None}},
    )
    assert response.status_code == 200
    assert response.json()["trigger"] == {
        "event_action": "opened",
        "repository_full_name": None,
    }


def test_position_only_patch_leaves_trigger_fields(
    unit_client: TestClient,
) -> None:
    node_id = unit_client.post(
        "/api/canvas/nodes/trigger",
        json={
            "position": {"x": 1, "y": 2},
            "trigger": {
                "event_action": "opened",
                "repository_full_name": "octo/repo",
            },
        },
    ).json()["id"]
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        json={"position": {"x": 3, "y": 4}},
    )
    assert response.json()["position"] == {"x": 3, "y": 4}
    assert response.json()["trigger"] == {
        "event_action": "opened",
        "repository_full_name": "octo/repo",
    }


@pytest.mark.parametrize("kind", ["action", "outcome"])
def test_trigger_fields_only_apply_to_trigger_nodes(
    unit_client: TestClient, kind: str
) -> None:
    response = unit_client.post(
        f"/api/canvas/nodes/{kind}",
        json={
            "position": {"x": 1, "y": 2},
            "trigger": {"event_action": "opened"},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "trigger fields apply only to trigger nodes"
    node_id = create_node(unit_client, kind)
    response = unit_client.patch(
        f"/api/canvas/nodes/{kind}/{node_id}",
        json={"trigger": {"event_action": "opened"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "trigger fields apply only to trigger nodes"


@pytest.mark.parametrize(
    "repository",
    [
        "octo",
        "octo/",
        "/repo",
        "octo/repo/extra",
        "-octo/repo",
        "octo-/repo",
        "octo/.",
        "octo/..",
        "octo/re po",
        "octo/re;po",
        "Ｏcto/repo",
        "octo/répo",
        "octo//repo",
        r"octo\repo",
        "octo/repo\n",
        "a" * 40 + "/repo",
        "octo/" + "r" * 101,
    ],
)
def test_repository_full_name_rejects_invalid_values(
    unit_client: TestClient, repository: str
) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/trigger",
        json={
            "position": {"x": 1, "y": 2},
            "trigger": {"repository_full_name": repository},
        },
    )
    assert response.status_code == 422
    assert unit_client.get("/api/canvas").json()["trigger_nodes"] == []


@pytest.mark.parametrize(
    "repository",
    ["octo/repo", "octo-org/my.repo_name-1", "a/b", "a" * 39 + "/repo"],
)
def test_repository_full_name_accepts_valid_values(
    unit_client: TestClient, repository: str
) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/trigger",
        json={
            "position": {"x": 1, "y": 2},
            "trigger": {"repository_full_name": repository},
        },
    )
    assert response.status_code == 201


def test_event_action_validation_returns_422(unit_client: TestClient) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/trigger",
        json={
            "position": {"x": 1, "y": 2},
            "trigger": {"event_action": "reopened"},
        },
    )
    assert response.status_code == 422


def test_create_action_node_persists_and_returns_fields(
    unit_client: TestClient,
) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/action",
        json={
            "position": {"x": 1, "y": 2},
            "name": "Triage",
            "playbook_id": "pb-1",
            "prompt": "Use the repository context",
        },
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Triage"
    assert response.json()["playbook_id"] == "pb-1"
    assert response.json()["prompt"] == "Use the repository context"


def test_create_action_node_defaults_fields(unit_client: TestClient) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/action",
        json={"position": {"x": 1, "y": 2}},
    )
    assert response.status_code == 201
    assert response.json()["name"] == ""
    assert response.json()["playbook_id"] is None
    assert response.json()["prompt"] == ""


def test_canvas_action_nodes_include_fields_but_other_nodes_do_not(
    unit_client: TestClient,
) -> None:
    action_id = create_node(unit_client, "action")
    trigger_id = create_node(unit_client, "trigger")
    outcome_id = create_node(unit_client, "outcome")
    canvas = unit_client.get("/api/canvas").json()
    assert set(canvas["action_nodes"][0]) >= {
        "id",
        "kind",
        "position",
        "name",
        "playbook_id",
        "prompt",
    }
    assert action_id == canvas["action_nodes"][0]["id"]
    assert "name" not in canvas["trigger_nodes"][0]
    assert "name" not in canvas["outcome_nodes"][0]
    assert {trigger_id, outcome_id} == {
        canvas["trigger_nodes"][0]["id"],
        canvas["outcome_nodes"][0]["id"],
    }


def test_action_patch_preserves_omitted_fields_and_clears_null(
    unit_client: TestClient,
) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/action",
        json={
            "position": {"x": 1, "y": 2},
            "name": "Triage",
            "playbook_id": "pb-1",
            "prompt": "Keep this",
        },
    )
    node_id = response.json()["id"]
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{node_id}", json={"name": "Updated"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"
    assert response.json()["playbook_id"] == "pb-1"
    assert response.json()["prompt"] == "Keep this"
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{node_id}", json={"name": None}
    )
    assert response.status_code == 200
    assert response.json()["name"] == ""
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{node_id}",
        json={"prompt": None},
    )
    assert response.status_code == 200
    assert response.json()["prompt"] == ""
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{node_id}", json={"playbook_id": None}
    )
    assert response.status_code == 200
    assert response.json()["playbook_id"] is None


def test_action_patch_without_position_updates_fields_and_timestamp(
    unit_client: TestClient, unit_session: Session
) -> None:
    node_id = create_node(unit_client, "action")
    before = (
        unit_session.exec(select(ActionNode).where(ActionNode.id == UUID(node_id)))
        .one()
        .updated_at
    )
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{node_id}",
        json={"name": "Updated", "prompt": "Notes"},
    )
    assert response.status_code == 200
    assert response.json()["position"] == {"x": 1, "y": 2}
    assert response.json()["name"] == "Updated"
    after = (
        unit_session.exec(select(ActionNode).where(ActionNode.id == UUID(node_id)))
        .one()
        .updated_at
    )
    assert after >= before


def test_action_fields_on_trigger_are_rejected(unit_client: TestClient) -> None:
    node_id = create_node(unit_client, "trigger")
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}", json={"name": "Not allowed"}
    )
    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "only action nodes have name, playbook_id and prompt"
    )


def test_position_only_patch_on_trigger_still_works(unit_client: TestClient) -> None:
    node_id = create_node(unit_client, "trigger")
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        json={"position": {"x": 4, "y": 5}},
    )
    assert response.status_code == 200
    assert response.json()["position"] == {"x": 4, "y": 5}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("playbook_id", ""),
        ("name", "x" * 201),
        ("prompt", "x" * 20_001),
    ],
)
def test_action_field_validation(
    unit_client: TestClient, field: str, value: str
) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/action",
        json={"position": {"x": 1, "y": 2}, field: value},
    )
    assert response.status_code == 422


def test_action_node_defaults_sync_status(unit_session: Session) -> None:
    node = ActionNode(position_x=1, position_y=2)
    unit_session.add(node)
    unit_session.commit()
    assert node.sync_status == "unprovisioned"
    assert node.automation_id is None
    assert node.sync_error is None
    assert node.deleted_at is None


def test_unknown_node_kind_is_unprocessable(unit_client: TestClient) -> None:
    assert (
        unit_client.post(
            "/api/canvas/nodes/unknown", json={"position": {"x": 0, "y": 0}}
        ).status_code
        == 422
    )


def test_update_node_updates_position(unit_client: TestClient) -> None:
    node_id = create_node(unit_client, "trigger")
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        json={"position": {"x": 4, "y": 5}},
    )
    assert response.status_code == 200
    assert response.json()["position"] == {"x": 4, "y": 5}


def test_non_finite_create_position_is_rejected(unit_client: TestClient) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/trigger",
        content='{"position":{"x":1e400,"y":0}}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert unit_client.get("/api/canvas").json()["trigger_nodes"] == []


def test_non_finite_update_position_is_rejected(unit_client: TestClient) -> None:
    node_id = create_node(unit_client, "trigger")
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{node_id}",
        content='{"position":{"x":1e400,"y":0}}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert unit_client.get("/api/canvas").json()["trigger_nodes"][0]["position"] == {
        "x": 1,
        "y": 2,
    }


def test_update_and_delete_missing_or_wrong_kind_are_not_found(
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


def test_delete_edge_is_hard_delete(unit_client: TestClient) -> None:
    trigger_id = create_node(unit_client, "trigger")
    action_id = create_node(unit_client, "action")
    edge_id = create_edge(
        unit_client, trigger_id, "trigger", action_id, "action"
    ).json()["id"]
    assert unit_client.delete(f"/api/canvas/edges/{edge_id}").status_code == 204
    assert unit_client.delete(f"/api/canvas/edges/{edge_id}").status_code == 404
