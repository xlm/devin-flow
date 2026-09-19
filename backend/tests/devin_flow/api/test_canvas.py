from datetime import UTC, datetime
from json import loads
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, select

from devin_flow.api import canvas as canvas_api
from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import (
    Automation,
    AutomationUpdate,
    DevinNotConfiguredError,
)
from devin_flow.models import (
    ActionNode,
    Edge,
    EventAction,
    Invocation,
    OutcomeNode,
    TriggerNode,
)


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


@pytest.fixture
def mock_devin(unit_client: TestClient) -> tuple[DevinClient, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"items": [], "has_next_page": False, "end_cursor": None},
            )
        return httpx.Response(
            200,
            json={
                "automation_id": "auto-1",
                "name": "Triage",
                "enabled": True,
                "metadata": {},
            },
        )

    client = DevinClient(
        httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://devin.example/v3",
        ),
        "org-test",
    )
    cast(FastAPI, unit_client.app).dependency_overrides[get_devin_client] = lambda: (
        client
    )
    return client, calls


def add_flow(
    session: Session,
    *,
    enabled: bool = False,
    automation_id: str | None = None,
) -> tuple[TriggerNode, ActionNode, Edge]:
    trigger = TriggerNode(
        position_x=1,
        position_y=2,
        event_action="opened",
        repository_full_name="octo/repo",
    )
    action = ActionNode(
        position_x=3,
        position_y=4,
        name="Triage",
        playbook_id="pb-1",
        enabled=enabled,
        automation_id=automation_id,
    )
    edge = Edge(
        source_id=trigger.id,
        source_kind="trigger",
        target_id=action.id,
        target_kind="action",
    )
    session.add_all([trigger, action, edge])
    session.commit()
    return trigger, action, edge


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


def test_create_action_node_ignores_enabled_field(
    unit_client: TestClient,
) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/action",
        json={"position": {"x": 1, "y": 2}, "enabled": True},
    )
    assert response.status_code == 201
    assert response.json()["enabled"] is False


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
        == "only action nodes have name, playbook_id, prompt and enabled"
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
        "outcome_count": None,
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


@pytest.mark.parametrize(
    ("name", "playbook_id", "trigger"),
    [
        ("", "pb-1", None),
        ("Triage", None, None),
        ("Triage", "pb-1", "incomplete"),
    ],
)
def test_enable_rejects_invalid_flows(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
    name: str,
    playbook_id: str | None,
    trigger: str | None,
) -> None:
    _, calls = mock_devin
    action = ActionNode(
        position_x=1,
        position_y=2,
        name=name,
        playbook_id=playbook_id,
    )
    unit_session.add(action)
    if trigger is not None:
        source = TriggerNode(position_x=3, position_y=4, event_action="opened")
        unit_session.add(source)
        unit_session.add(
            Edge(
                source_id=source.id,
                source_kind="trigger",
                target_id=action.id,
                target_kind="action",
            )
        )
    unit_session.commit()
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{action.id}",
        json={"enabled": True},
    )
    assert response.status_code == 409
    assert response.json()["detail"].startswith("cannot enable:")
    stored = unit_session.get(ActionNode, action.id)
    assert stored is not None
    assert stored.enabled is False
    assert calls == []


def test_enable_syncs_complete_flow(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
) -> None:
    _, calls = mock_devin
    _, action, _ = add_flow(unit_session)
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{action.id}",
        json={"enabled": True},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["sync_status"] == "enabled"
    assert response.json()["automation_id"] == "auto-1"
    assert [call.method for call in calls] == ["GET", "POST"]


def test_incomplete_action_update_disables_automation(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
) -> None:
    trigger, action, _ = add_flow(
        unit_session,
        enabled=True,
        automation_id="auto-1",
    )
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{action.id}",
        json={"playbook_id": None},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["sync_status"] == "disabled"
    assert response.json()["automation_id"] == "auto-1"
    assert unit_session.get(TriggerNode, trigger.id) is not None
    assert len(mock_devin[1]) == 1
    assert json_body(mock_devin[1][0]) == {"enabled": False}


def test_trigger_update_resyncs_connected_action(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
) -> None:
    _, action, _ = add_flow(unit_session, enabled=True, automation_id="auto-1")
    response = unit_client.patch(
        f"/api/canvas/nodes/trigger/{unit_session.exec(select(TriggerNode)).one().id}",
        json={"trigger": {"event_action": "closed"}},
    )
    assert response.status_code == 200
    assert [call.method for call in mock_devin[1]] == ["PATCH"]


def test_edge_delete_disables_connected_action(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
) -> None:
    _, action, edge = add_flow(unit_session, enabled=True, automation_id="auto-1")
    response = unit_client.delete(f"/api/canvas/edges/{edge.id}")
    assert response.status_code == 204
    assert action.id
    assert json_body(mock_devin[1][0]) == {"enabled": False}


def test_trigger_delete_disables_connected_action(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
) -> None:
    trigger, action, _ = add_flow(
        unit_session,
        enabled=True,
        automation_id="auto-1",
    )
    response = unit_client.delete(f"/api/canvas/nodes/trigger/{trigger.id}")
    assert response.status_code == 204
    assert unit_session.get(ActionNode, action.id) is not None
    assert json_body(mock_devin[1][0]) == {"enabled": False}


def test_action_delete_tombstones_on_upstream_failure(
    unit_client: TestClient,
    unit_session: Session,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    client = DevinClient(
        httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://devin.example/v3",
        ),
        "org-test",
    )
    cast(FastAPI, unit_client.app).dependency_overrides[get_devin_client] = lambda: (
        client
    )
    action = ActionNode(
        position_x=1,
        position_y=2,
        automation_id="auto-1",
    )
    trigger = TriggerNode(position_x=3, position_y=4)
    unit_session.add_all(
        [
            action,
            trigger,
            Edge(
                source_id=trigger.id,
                source_kind="trigger",
                target_id=action.id,
                target_kind="action",
            ),
        ]
    )
    unit_session.commit()
    response = unit_client.delete(f"/api/canvas/nodes/action/{action.id}")
    assert response.status_code == 204
    assert len(calls) == 1
    stored = unit_session.get(ActionNode, action.id)
    assert stored is not None
    assert stored.deleted_at is not None
    assert stored.automation_id == "auto-1"
    assert stored.enabled is False
    assert stored.sync_status == "error"
    assert stored.sync_error == "devin api returned HTTP 500"
    assert unit_client.get("/api/canvas").json()["action_nodes"] == []
    assert unit_client.get("/api/canvas").json()["edges"] == []
    assert (
        unit_client.patch(
            f"/api/canvas/nodes/action/{action.id}",
            json={"enabled": False},
        ).status_code
        == 404
    )
    client.http.close()


def test_action_delete_tombstones_after_upstream_success(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
) -> None:
    action = ActionNode(
        position_x=1,
        position_y=2,
        automation_id="auto-1",
    )
    unit_session.add(action)
    unit_session.commit()
    response = unit_client.delete(f"/api/canvas/nodes/action/{action.id}")
    assert response.status_code == 204
    stored = unit_session.get(ActionNode, action.id)
    assert stored is not None
    assert stored.deleted_at is not None
    assert stored.automation_id == "auto-1"
    assert stored.enabled is False
    assert stored.sync_status == "disabled"
    assert stored.sync_error is None
    assert json_body(mock_devin[1][0]) == {"enabled": False}


def test_action_delete_tombstones_when_devin_is_not_configured(
    unit_client: TestClient,
    unit_session: Session,
) -> None:
    class NotConfiguredClient(DevinClient):
        def update_automation(
            self,
            automation_id: str,
            payload: AutomationUpdate,
        ) -> Automation:
            raise DevinNotConfiguredError

    client = NotConfiguredClient(httpx.Client(), "org-test")
    cast(FastAPI, unit_client.app).dependency_overrides[get_devin_client] = lambda: (
        client
    )
    action = ActionNode(
        position_x=1,
        position_y=2,
        automation_id="auto-1",
    )
    unit_session.add(action)
    unit_session.commit()
    response = unit_client.delete(f"/api/canvas/nodes/action/{action.id}")
    assert response.status_code == 204
    stored = unit_session.get(ActionNode, action.id)
    assert stored is not None
    assert stored.deleted_at is not None
    assert stored.sync_status == "error"
    assert stored.sync_error == "devin api not configured"
    client.http.close()


def test_position_only_action_patch_does_not_sync(
    unit_client: TestClient,
    unit_session: Session,
    mock_devin: tuple[DevinClient, list[httpx.Request]],
) -> None:
    action = ActionNode(
        position_x=1,
        position_y=2,
        automation_id="auto-1",
    )
    unit_session.add(action)
    unit_session.commit()
    response = unit_client.patch(
        f"/api/canvas/nodes/action/{action.id}",
        json={"position": {"x": 5, "y": 6}},
    )
    assert response.status_code == 200
    assert mock_devin[1] == []


def json_body(request: httpx.Request) -> dict[str, object]:
    return cast(dict[str, object], loads(request.read()))


def test_canvas_counts_invocations_per_action(
    unit_client: TestClient, unit_session: Session
) -> None:
    counted_id = UUID(create_node(unit_client, "action"))
    empty_id = UUID(create_node(unit_client, "action"))
    now = datetime.now(UTC)
    for session_id in ["s-1", "s-2"]:
        unit_session.add(
            Invocation(
                session_id=session_id,
                automation_id="auto-1",
                action_node_id=counted_id,
                status="exit",
                session_created_at=now,
                session_updated_at=now,
            )
        )
    unit_session.commit()
    canvas = unit_client.get("/api/canvas").json()
    counts = {
        UUID(node["id"]): node["invocation_count"] for node in canvas["action_nodes"]
    }
    assert counts == {counted_id: 2, empty_id: 0}
    created = unit_client.post(
        "/api/canvas/nodes/action", json={"position": {"x": 0, "y": 0}}
    )
    assert created.json()["invocation_count"] == 0
    moved = unit_client.patch(
        f"/api/canvas/nodes/action/{counted_id}", json={"position": {"x": 1, "y": 1}}
    )
    assert moved.json()["invocation_count"] == 2


def add_invocation(
    session: Session,
    action_id: UUID,
    session_id: str,
    *,
    pull_requests: list[dict[str, object]] | None = None,
    structured_output: dict[str, object] | None = None,
) -> Invocation:
    now = datetime.now(UTC)
    invocation = Invocation(
        session_id=session_id,
        automation_id="auto-1",
        action_node_id=action_id,
        status="exit",
        pull_requests=pull_requests or [],
        structured_output=structured_output,
        session_created_at=now,
        session_updated_at=now,
    )
    session.add(invocation)
    session.commit()
    return invocation


def test_create_outcome_node_with_kind(unit_client: TestClient) -> None:
    response = unit_client.post(
        "/api/canvas/nodes/outcome",
        json={"position": {"x": 1, "y": 2}, "outcome": {"kind": "duplicate"}},
    )
    assert response.status_code == 201
    assert response.json()["outcome"] == {"kind": "duplicate"}


def test_patch_outcome_kind_and_clear(unit_client: TestClient) -> None:
    node_id = create_node(unit_client, "outcome")
    response = unit_client.patch(
        f"/api/canvas/nodes/outcome/{node_id}",
        json={"outcome": {"kind": "not_a_bug"}},
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == {"kind": "not_a_bug"}
    response = unit_client.patch(
        f"/api/canvas/nodes/outcome/{node_id}",
        json={"outcome": {"kind": None}},
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == {"kind": None}


@pytest.mark.parametrize("kind", ["trigger", "action"])
def test_outcome_fields_only_apply_to_outcome_nodes(
    unit_client: TestClient, kind: str
) -> None:
    response = unit_client.post(
        f"/api/canvas/nodes/{kind}",
        json={"position": {"x": 1, "y": 2}, "outcome": {"kind": "duplicate"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "outcome fields apply only to outcome nodes"
    node_id = create_node(unit_client, kind)
    response = unit_client.patch(
        f"/api/canvas/nodes/{kind}/{node_id}",
        json={"outcome": {"kind": "duplicate"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "outcome fields apply only to outcome nodes"


def test_canvas_edges_report_outcome_counts(
    unit_client: TestClient, unit_session: Session
) -> None:
    action_id = UUID(create_node(unit_client, "action"))
    dup_outcome = OutcomeNode(position_x=5, position_y=6, kind="duplicate")
    pr_outcome = OutcomeNode(position_x=7, position_y=8, kind="pull_request")
    unset_outcome = OutcomeNode(position_x=9, position_y=10)
    unit_session.add_all([dup_outcome, pr_outcome, unset_outcome])
    unit_session.commit()
    add_invocation(
        unit_session,
        action_id,
        "s-1",
        pull_requests=[{"pr_url": "https://github.com/a/b/pull/1"}],
        structured_output={"outcome": "duplicate"},
    )
    add_invocation(
        unit_session,
        action_id,
        "s-2",
        pull_requests=[{"pr_url": "https://github.com/a/b/pull/2"}],
    )
    add_invocation(unit_session, action_id, "s-3")
    trigger_id = create_node(unit_client, "trigger")
    edges = {
        edge["target"]["id"]: edge
        for edge in [
            create_edge(
                unit_client, str(action_id), "action", str(node.id), "outcome"
            ).json()
            for node in (dup_outcome, pr_outcome, unset_outcome)
        ]
    }
    assert (
        create_edge(
            unit_client, trigger_id, "trigger", str(action_id), "action"
        ).status_code
        == 201
    )
    canvas_edges = unit_client.get("/api/canvas").json()["edges"]
    by_target = {edge["target"]["id"]: edge for edge in canvas_edges}
    assert by_target[str(dup_outcome.id)]["outcome_count"] == 1
    assert by_target[str(pr_outcome.id)]["outcome_count"] == 2
    assert by_target[str(unset_outcome.id)]["outcome_count"] == 0
    assert by_target[str(action_id)]["outcome_count"] is None
    assert {e["id"] for e in canvas_edges} >= {e["id"] for e in edges.values()}
