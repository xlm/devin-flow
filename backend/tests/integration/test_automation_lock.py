import httpx
import pytest
from sqlmodel import Session

from devin_flow.automations import sync_action
from devin_flow.devin import DevinClient
from devin_flow.models import ActionNode, Edge, TriggerNode

pytestmark = pytest.mark.docker


def test_sync_action_uses_postgres_row_lock(session: Session) -> None:
    action = ActionNode(
        position_x=1,
        position_y=2,
        name="Triage",
        playbook_id="pb-1",
        prompt="Inspect the issue",
    )
    trigger = TriggerNode(
        position_x=3,
        position_y=4,
        event_action="opened",
        repository_full_name="octo/repo",
    )
    session.add_all([action, trigger])
    session.commit()
    session.add(
        Edge(
            source_id=trigger.id,
            source_kind="trigger",
            target_id=action.id,
            target_kind="action",
        )
    )
    session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"items": [], "has_next_page": False, "end_cursor": None},
            )
        return httpx.Response(
            201,
            json={
                "automation_id": "auto-postgres",
                "name": "Triage: octo/repo issue opened",
                "enabled": False,
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
    sync_action(session, client, action.id)
    stored = session.get(ActionNode, action.id)
    assert stored is not None
    assert stored.automation_id == "auto-postgres"
    client.http.close()
