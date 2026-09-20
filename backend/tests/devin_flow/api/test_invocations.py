from datetime import UTC, datetime
from typing import cast

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import DevinNotConfiguredError
from devin_flow.models import ActionNode, Invocation, PollerState


def install_upstream(client: TestClient, handler: httpx.BaseTransport) -> None:
    upstream = DevinClient(
        httpx.Client(transport=handler, base_url="https://devin.example"),
        "org-test",
    )
    cast(FastAPI, client.app).dependency_overrides[get_devin_client] = lambda: upstream


def add_action(session: Session, automation_id: str) -> ActionNode:
    action = ActionNode(
        position_x=0, position_y=0, name="Triage", automation_id=automation_id
    )
    session.add(action)
    session.commit()
    return action


def test_refresh_runs_one_cycle_and_returns_counts(
    unit_client: TestClient, unit_session: Session
) -> None:
    action = add_action(unit_session, "auto-1")
    now = datetime.now(UTC)
    unit_session.add(
        Invocation(
            session_id="old",
            automation_id="auto-1",
            action_node_id=action.id,
            status="running",
            session_created_at=now,
            session_updated_at=now,
        )
    )
    unit_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/organizations/org-test/sessions":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "session_id": "new",
                            "status": "running",
                            "automation_id": "auto-1",
                        }
                    ],
                    "has_next_page": False,
                },
            )
        return httpx.Response(200, json={"session_id": "old", "status": "exit"})

    install_upstream(unit_client, httpx.MockTransport(handler))
    response = unit_client.post("/api/invocations/refresh")
    assert response.status_code == 200
    assert response.json() == {
        "listed": 1,
        "upserted": 1,
        "refreshed": 1,
        "synced": 0,
    }
    statuses = {
        i.session_id: i.status for i in unit_session.exec(select(Invocation)).all()
    }
    assert statuses == {"old": "exit", "new": "running"}
    assert (
        unit_client.get("/api/canvas").json()["action_nodes"][0]["invocation_count"]
        == 2
    )


def test_refresh_reports_upstream_failure(
    unit_client: TestClient, unit_session: Session
) -> None:
    add_action(unit_session, "auto-1")
    install_upstream(
        unit_client,
        httpx.MockTransport(lambda _request: httpx.Response(500, text="boom")),
    )
    response = unit_client.post("/api/invocations/refresh")
    assert response.status_code == 502
    assert response.json() == {"detail": "devin api returned HTTP 500"}
    assert unit_session.get(PollerState, 1) is None


def add_invocation(session: Session) -> Invocation:
    action = add_action(session, "auto-1")
    now = datetime.now(UTC)
    invocation = Invocation(
        session_id="session-archive",
        automation_id="auto-1",
        action_node_id=action.id,
        status="running",
        session_created_at=now,
        session_updated_at=now,
    )
    session.add(invocation)
    session.commit()
    session.refresh(invocation)
    return invocation


def test_archive_invocation_returns_no_content_and_updates_row(
    unit_client: TestClient, unit_session: Session
) -> None:
    invocation = add_invocation(unit_session)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/sessions/session-archive/archive")
        return httpx.Response(
            200,
            json={"session_id": "session-archive", "status": "exit"},
        )

    install_upstream(unit_client, httpx.MockTransport(handler))
    response = unit_client.post(f"/api/invocations/{invocation.id}/archive")
    assert response.status_code == 204
    assert response.content == b""
    archived = unit_session.get(Invocation, invocation.id)
    assert archived is not None
    assert archived.archived_at is not None
    assert archived.status == "exit"


def test_archive_invocation_returns_not_found(
    unit_client: TestClient, unit_session: Session
) -> None:
    response = unit_client.post(
        "/api/invocations/00000000-0000-0000-0000-000000000001/archive"
    )
    assert response.status_code == 404


def test_archive_invocation_reports_upstream_failure(
    unit_client: TestClient, unit_session: Session
) -> None:
    invocation = add_invocation(unit_session)
    install_upstream(
        unit_client,
        httpx.MockTransport(lambda _request: httpx.Response(500, text="boom")),
    )
    response = unit_client.post(f"/api/invocations/{invocation.id}/archive")
    assert response.status_code == 502
    assert response.json() == {"detail": "devin api returned HTTP 500"}
    stored = unit_session.get(Invocation, invocation.id)
    assert stored is not None
    assert stored.archived_at is None


def test_archive_invocation_reports_missing_configuration(
    unit_client: TestClient, unit_session: Session
) -> None:
    invocation = add_invocation(unit_session)

    def missing_client() -> DevinClient:
        raise DevinNotConfiguredError("missing")

    cast(FastAPI, unit_client.app).dependency_overrides[get_devin_client] = (
        missing_client
    )
    response = unit_client.post(f"/api/invocations/{invocation.id}/archive")
    assert response.status_code == 503
