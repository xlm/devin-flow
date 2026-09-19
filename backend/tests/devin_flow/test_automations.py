import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from devin_flow.automations import (
    METADATA_KEY,
    actions_to_sync,
    build_automation_payload,
    build_prompt,
    connected_action,
    connected_trigger,
    flow_invalid_reason,
    is_action_complete,
    is_trigger_complete,
    mark_pending,
    retry_syncs,
    sync_action,
)
from devin_flow.devin import DevinClient
from devin_flow.devin.client import (
    Automation,
    AutomationUpdate,
    DevinNotConfiguredError,
)
from devin_flow.models import ActionNode, Edge, TriggerNode


def make_client(handler: httpx.MockTransport) -> DevinClient:
    return DevinClient(
        httpx.Client(
            transport=handler,
            base_url="https://devin.example/v3",
        ),
        "org-test",
    )


def action(*, enabled: bool = True, playbook_id: str | None = "pb-1") -> ActionNode:
    return ActionNode(
        position_x=1,
        position_y=2,
        name="Triage",
        playbook_id=playbook_id,
        prompt="Inspect the issue",
        enabled=enabled,
    )


def trigger(
    *,
    event_action: str | None = "opened",
    repository_full_name: str | None = "octo/repo",
) -> TriggerNode:
    return TriggerNode(
        position_x=3,
        position_y=4,
        event_action=event_action,
        repository_full_name=repository_full_name,
    )


def connect(session: Session, source: TriggerNode, target: ActionNode) -> None:
    session.add(
        Edge(
            source_id=source.id,
            source_kind="trigger",
            target_id=target.id,
            target_kind="action",
        )
    )
    session.commit()


def automation_response(automation_id: str = "auto-1") -> dict[str, object]:
    return {
        "automation_id": automation_id,
        "name": "Triage: octo/repo issue opened",
        "enabled": True,
        "metadata": {METADATA_KEY: "action"},
    }


def test_build_prompt_with_and_without_extra_prompt(unit_session: Session) -> None:
    with_prompt = action()
    no_prompt = action()
    no_prompt.prompt = "  "
    assert build_prompt(with_prompt.prompt, "pb-1") == (
        "Inspect the issue\n\n@playbook:pb-1"
    )
    assert build_prompt(no_prompt.prompt, "pb-1") == "@playbook:pb-1"


def test_completion_and_flow_invalid_reasons(unit_session: Session) -> None:
    complete_action = action()
    incomplete_action = action(playbook_id=None)
    complete_trigger = trigger()
    incomplete_trigger = trigger(event_action=None)
    assert is_action_complete(complete_action)
    assert not is_action_complete(incomplete_action)
    assert is_trigger_complete(complete_trigger)
    assert not is_trigger_complete(incomplete_trigger)
    assert flow_invalid_reason(incomplete_action, complete_trigger) == (
        "Action is incomplete"
    )
    assert flow_invalid_reason(complete_action, None) == "Action has no Trigger"
    assert flow_invalid_reason(complete_action, incomplete_trigger) == (
        "Trigger is incomplete"
    )
    assert flow_invalid_reason(complete_action, complete_trigger) is None


def test_connected_nodes_and_payload(unit_session: Session) -> None:
    node = action()
    source = trigger()
    unit_session.add(node)
    unit_session.add(source)
    unit_session.commit()
    connect(unit_session, source, node)
    assert connected_trigger(unit_session, node.id) == source
    assert connected_action(unit_session, source.id) == node
    node.deleted_at = datetime.now(UTC)
    unit_session.add(node)
    unit_session.commit()
    assert connected_trigger(unit_session, node.id) is None
    payload = build_automation_payload(node, source)
    assert payload.model_dump() == {
        "name": "Triage: octo/repo issue opened",
        "enabled": True,
        "triggers": [
            {
                "event_type": "github:issues",
                "conditions": {
                    "any": [
                        {
                            "all": [
                                {
                                    "field": "action",
                                    "operator": "eq",
                                    "value": "opened",
                                },
                                {
                                    "field": "repository.full_name",
                                    "operator": "eq",
                                    "value": "octo/repo",
                                },
                            ]
                        }
                    ]
                },
            }
        ],
        "actions": [
            {
                "type": "start_session",
                "prompt": "Inspect the issue\n\n@playbook:pb-1",
            }
        ],
        "run_as": {"type": "organization"},
        "metadata": {METADATA_KEY: str(node.id)},
    }


def test_build_payload_rejects_incomplete_trigger(unit_session: Session) -> None:
    node = action()
    incomplete = trigger(repository_full_name=None)
    try:
        build_automation_payload(node, incomplete)
    except ValueError as exc:
        assert str(exc) == "action or trigger is incomplete"
    else:
        raise AssertionError("expected incomplete trigger to fail")


def test_sync_creates_and_enables_action(unit_session: Session) -> None:
    node = action()
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            assert request.url.params[f"metadata.{METADATA_KEY}"] == str(node.id)
            return httpx.Response(
                200,
                json={"items": [], "has_next_page": False, "end_cursor": None},
            )
        assert request.method == "POST"
        return httpx.Response(201, json=automation_response())

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    assert [request.method for request in calls] == ["GET", "POST"]
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.automation_id == "auto-1"
    assert stored.sync_status == "enabled"
    assert stored.sync_error is None


def test_sync_patches_existing_action_without_listing(unit_session: Session) -> None:
    node = action()
    node.automation_id = "auto-existing"
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "PATCH"
        body = json.loads(request.read())
        assert body["enabled"] is True
        assert body["name"] == "Triage: octo/repo issue opened"
        assert body["metadata"] == {METADATA_KEY: str(node.id)}
        return httpx.Response(200, json=automation_response("auto-existing"))

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    assert len(calls) == 1
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "enabled"


def test_sync_disables_disconnected_action(unit_session: Session) -> None:
    node = action()
    node.automation_id = "auto-existing"
    unit_session.add(node)
    unit_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert json.loads(request.read()) == {"enabled": False}
        return httpx.Response(200, json=automation_response("auto-existing"))

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "disabled"


def test_sync_disables_incomplete_action(unit_session: Session) -> None:
    node = action()
    node.automation_id = "auto-existing"
    node.playbook_id = None
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert json.loads(request.read()) == {"enabled": False}
        return httpx.Response(200, json=automation_response("auto-existing"))

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "disabled"
    assert stored.sync_error is None


def test_sync_unprovisioned_action_makes_no_request(unit_session: Session) -> None:
    node = action()
    unit_session.add(node)
    unit_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request)

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "unprovisioned"
    assert stored.sync_error is None


def test_sync_reconciles_by_metadata(unit_session: Session) -> None:
    node = action()
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": [automation_response("auto-found")],
                    "has_next_page": False,
                    "end_cursor": None,
                },
            )
        assert request.method == "PATCH"
        return httpx.Response(200, json=automation_response("auto-found"))

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    assert calls == ["GET", "PATCH"]
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.automation_id == "auto-found"


def test_sync_stores_disabled_status_for_disabled_action(unit_session: Session) -> None:
    node = action(enabled=False)
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"items": [], "has_next_page": False, "end_cursor": None},
            )
        return httpx.Response(201, json=automation_response())

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "disabled"


def test_sync_handles_upstream_error_and_preserves_id(unit_session: Session) -> None:
    node = action()
    node.automation_id = "auto-existing"
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    sync_action(unit_session, make_client(httpx.MockTransport(handler)), node.id)
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.automation_id == "auto-existing"
    assert stored.sync_status == "error"
    assert stored.sync_error == "devin api returned HTTP 500"


def test_sync_handles_missing_configuration(unit_session: Session) -> None:
    node = action()
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)

    class NotConfiguredClient(DevinClient):
        def list_automations(
            self, metadata: dict[str, str] | None = None
        ) -> list[Automation]:
            raise DevinNotConfiguredError

    sync_action(unit_session, NotConfiguredClient(httpx.Client(), "org-test"), node.id)
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "error"
    assert stored.sync_error == "devin api not configured"


def test_sync_handles_missing_action_and_pending(unit_session: Session) -> None:
    missing_id = uuid4()
    client = make_client(httpx.MockTransport(lambda request: httpx.Response(500)))
    sync_action(unit_session, client, missing_id)
    node = action()
    unit_session.add(node)
    mark_pending(node)
    assert node.sync_status == "pending"


def test_retry_syncs_errored_action(unit_session: Session) -> None:
    node = action()
    node.automation_id = "auto-1"
    node.sync_status = "error"
    node.sync_error = "boom"
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "PATCH"
        return httpx.Response(200, json=automation_response("auto-1"))

    client = make_client(httpx.MockTransport(handler))
    assert retry_syncs(unit_session, client) == 1
    assert [request.method for request in calls] == ["PATCH"]
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "enabled"
    assert stored.sync_error is None


def test_retry_syncs_tombstoned_action_disables(unit_session: Session) -> None:
    node = action()
    node.automation_id = "auto-1"
    node.sync_status = "error"
    node.deleted_at = datetime.now(UTC)
    unit_session.add(node)
    unit_session.commit()
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "PATCH"
        assert json.loads(request.read()) == {"enabled": False}
        return httpx.Response(200, json=automation_response("auto-1"))

    client = make_client(httpx.MockTransport(handler))
    assert retry_syncs(unit_session, client) == 1
    assert len(calls) == 1
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "disabled"


def test_retry_syncs_keeps_error_on_upstream_failure(
    unit_session: Session,
) -> None:
    node = action()
    node.automation_id = "auto-1"
    node.sync_status = "error"
    node.sync_error = "old boom"
    unit_session.add(node)
    unit_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    client = make_client(httpx.MockTransport(handler))
    assert retry_syncs(unit_session, client) == 1
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "error"
    assert stored.sync_error == "devin api returned HTTP 502"


def test_retry_syncs_picks_up_pending_action(unit_session: Session) -> None:
    node = action()
    node.sync_status = "pending"
    unit_session.add(node)
    unit_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request)

    client = make_client(httpx.MockTransport(handler))
    assert retry_syncs(unit_session, client) == 1
    stored = unit_session.get(ActionNode, node.id)
    assert stored is not None
    assert stored.sync_status == "unprovisioned"


def test_actions_to_sync_skips_settled_statuses(unit_session: Session) -> None:
    for status in ["enabled", "disabled", "unprovisioned"]:
        node = action()
        node.sync_status = status
        unit_session.add(node)
    tombstoned = action()
    tombstoned.deleted_at = datetime.now(UTC)
    tombstoned.sync_status = "error"
    unit_session.add(tombstoned)
    unit_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request)

    client = make_client(httpx.MockTransport(handler))
    assert actions_to_sync(unit_session) == []
    assert retry_syncs(unit_session, client) == 0


def test_retry_syncs_one_failure_does_not_stop_others(
    unit_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    nodes = []
    for _ in range(2):
        node = action()
        node.automation_id = "auto-1"
        node.sync_status = "error"
        unit_session.add(node)
        nodes.append(node)
    unit_session.commit()
    attempted: list[str] = []

    class FailingClient(DevinClient):
        def update_automation(
            self, automation_id: str, update: AutomationUpdate
        ) -> Automation:
            attempted.append(automation_id)
            raise RuntimeError("client exploded")

    client = FailingClient(httpx.Client(), "org-test")
    with caplog.at_level(logging.ERROR, logger="devin_flow.automations"):
        assert retry_syncs(unit_session, client) == 2
    assert attempted == ["auto-1", "auto-1"]
    assert caplog.text.count("sync of action") == 2
    assert "client exploded" in caplog.text


def test_sync_uses_fresh_fields_after_lock(
    unit_session: Session, unit_engine: Engine
) -> None:
    node = action()
    node.prompt = "Old"
    node.automation_id = "auto-1"
    node.sync_status = "error"
    source = trigger()
    unit_session.add_all([node, source])
    unit_session.commit()
    connect(unit_session, source, node)
    # populate the identity map so the lock must refresh stale fields
    assert actions_to_sync(unit_session)[0].id == node.id
    with Session(unit_engine) as other:
        other_node = other.get(ActionNode, node.id)
        other_trigger = other.get(TriggerNode, source.id)
        assert other_node is not None and other_trigger is not None
        other_node.prompt = "New"
        other_trigger.event_action = "closed"
        other.add_all([other_node, other_trigger])
        other.commit()

    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        bodies.append(json.loads(request.read()))
        return httpx.Response(200, json=automation_response("auto-1"))

    client = make_client(httpx.MockTransport(handler))
    assert retry_syncs(unit_session, client) == 1
    assert len(bodies) == 1
    actions = bodies[0]["actions"]
    assert isinstance(actions, list)
    assert str(actions[0]["prompt"]).startswith("New")
    triggers = bodies[0]["triggers"]
    assert isinstance(triggers, list)
    conditions = triggers[0]["conditions"]["any"][0]["all"]
    assert {c["field"]: c["value"] for c in conditions} == {
        "action": "closed",
        "repository.full_name": "octo/repo",
    }
