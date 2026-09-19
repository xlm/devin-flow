import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from sqlmodel import Session, select

from devin_flow.devin import DevinClient
from devin_flow.devin.client import DevinUpstreamError
from devin_flow.invocations import (
    SAFETY_MARGIN,
    PollResult,
    poll_forever,
    poll_once,
    run_poll_cycle,
)
from devin_flow.models import (
    ActionNode,
    Edge,
    Invocation,
    InvocationOutcome,
    PollerState,
    TriggerNode,
)


def at(epoch: int) -> datetime:
    # sqlite returns naive timestamps, so compare without tzinfo
    return datetime.fromtimestamp(epoch, UTC).replace(tzinfo=None)


def make_client(handler: httpx.BaseTransport) -> DevinClient:
    return DevinClient(
        httpx.Client(transport=handler, base_url="https://devin.example"),
        "org-test",
    )


def add_action(
    session: Session,
    automation_id: str | None,
    *,
    deleted: bool = False,
) -> ActionNode:
    action = ActionNode(
        position_x=0,
        position_y=0,
        name=f"Action {automation_id}",
        automation_id=automation_id,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    session.add(action)
    session.commit()
    return action


def session_payload(
    session_id: str,
    automation_id: str,
    status: str = "running",
    **extra: object,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "status": status,
        "automation_id": automation_id,
        "title": f"Title {session_id}",
        "url": f"https://devin.example/{session_id}",
        "created_at": 1700000000,
        "updated_at": 1700000100,
        **extra,
    }


def outcome_rows(session: Session, invocation_id: UUID) -> set[str]:
    return {
        row.kind
        for row in session.exec(
            select(InvocationOutcome).where(
                InvocationOutcome.invocation_id == invocation_id
            )
        ).all()
    }


def test_first_poll_lists_all_owned_automations(unit_session: Session) -> None:
    live = add_action(unit_session, "auto-1")
    add_action(unit_session, "auto-2")
    tombstoned = add_action(unit_session, "auto-deleted", deleted=True)
    add_action(unit_session, None)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/organizations/org-test/sessions"
        assert request.url.params.get_list("automation_ids") == [
            "auto-1",
            "auto-2",
            "auto-deleted",
        ]
        assert "created_after" not in request.url.params
        return httpx.Response(
            200,
            json={
                "items": [
                    session_payload(
                        "s-1",
                        "auto-1",
                        pull_requests=[
                            {"pr_url": "https://gh.example/1", "pr_state": "open"}
                        ],
                    ),
                    session_payload("s-2", "auto-1", status="exit"),
                    session_payload("s-3", "auto-deleted", status="exit"),
                    session_payload("s-unknown", "auto-gone"),
                ],
                "has_next_page": False,
            },
        )

    result = poll_once(unit_session, make_client(httpx.MockTransport(handler)))

    assert result == PollResult(listed=4, upserted=3, refreshed=0, synced=0)
    assert len(requests) == 1
    invocations = unit_session.exec(
        select(Invocation).order_by(Invocation.session_id)
    ).all()
    assert [(i.session_id, i.action_node_id) for i in invocations] == [
        ("s-1", live.id),
        ("s-2", live.id),
        ("s-3", tombstoned.id),
    ]
    first = invocations[0]
    assert first.automation_id == "auto-1"
    assert first.status == "running"
    assert first.title == "Title s-1"
    assert first.url == "https://devin.example/s-1"
    assert first.pull_requests == [
        {"pr_url": "https://gh.example/1", "pr_state": "open"}
    ]
    assert first.structured_output is None
    assert first.session_created_at == at(1700000000)
    assert first.session_updated_at == at(1700000100)
    assert outcome_rows(unit_session, invocations[0].id) == {"pull_request"}
    assert outcome_rows(unit_session, invocations[1].id) == set()
    assert outcome_rows(unit_session, invocations[2].id) == set()
    state = unit_session.get(PollerState, 1)
    assert state is not None and state.last_success_at is not None


def test_poll_without_automations_skips_listing(unit_session: Session) -> None:
    add_action(unit_session, None)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not call upstream")

    result = poll_once(unit_session, make_client(httpx.MockTransport(handler)))
    assert result == PollResult(listed=0, upserted=0, refreshed=0, synced=0)
    state = unit_session.get(PollerState, 1)
    assert state is not None and state.last_success_at is not None


def test_incremental_poll_uses_margin_and_upserts(unit_session: Session) -> None:
    action = add_action(unit_session, "auto-1")
    last = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    unit_session.add(PollerState(last_success_at=last))
    unit_session.add(
        Invocation(
            session_id="s-1",
            automation_id="auto-1",
            action_node_id=action.id,
            status="exit",
            session_created_at=last,
            session_updated_at=last,
        )
    )
    unit_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["created_after"] == str(
            int((last - SAFETY_MARGIN).timestamp())
        )
        return httpx.Response(
            200,
            json={
                "items": [
                    session_payload(
                        "s-1",
                        "auto-1",
                        status="exit",
                        structured_output={"outcome": "fixed"},
                        updated_at=1700000999,
                    ),
                    session_payload("s-3", "auto-1"),
                ],
                "has_next_page": False,
            },
        )

    result = poll_once(unit_session, make_client(httpx.MockTransport(handler)))

    assert result == PollResult(listed=2, upserted=2, refreshed=0, synced=0)
    invocations = unit_session.exec(
        select(Invocation).order_by(Invocation.session_id)
    ).all()
    assert [i.session_id for i in invocations] == ["s-1", "s-3"]
    assert invocations[0].structured_output == {"outcome": "fixed"}
    assert invocations[0].session_updated_at == at(1700000999)
    state = unit_session.get(PollerState, 1)
    assert state is not None
    assert state.last_success_at is not None
    assert state.last_success_at.replace(tzinfo=UTC) > last


def test_poll_refreshes_non_terminal_invocations(unit_session: Session) -> None:
    action = add_action(unit_session, "auto-1")
    when = datetime.now(UTC) - timedelta(days=1)
    for session_id, status in [("old-run", "running"), ("old-done", "exit")]:
        unit_session.add(
            Invocation(
                session_id=session_id,
                automation_id="auto-1",
                action_node_id=action.id,
                status=status,
                session_created_at=when,
                session_updated_at=when,
            )
        )
    unit_session.add(PollerState(last_success_at=when))
    unit_session.commit()
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/organizations/org-test/sessions":
            return httpx.Response(
                200,
                json={
                    "items": [session_payload("fresh", "auto-1", status="claimed")],
                    "has_next_page": False,
                },
            )
        assert request.url.path == "/organizations/org-test/sessions/old-run"
        return httpx.Response(
            200,
            json={
                "session_id": "old-run",
                "status": "exit",
                "pull_requests": [{"pr_url": "https://gh.example/2"}],
                "structured_output": {"outcome": "duplicate"},
                "updated_at": 1700001000,
            },
        )

    result = poll_once(unit_session, make_client(httpx.MockTransport(handler)))

    assert result == PollResult(listed=1, upserted=1, refreshed=1, synced=0)
    assert paths == [
        "/organizations/org-test/sessions",
        "/organizations/org-test/sessions/old-run",
    ]
    refreshed = unit_session.exec(
        select(Invocation).where(Invocation.session_id == "old-run")
    ).one()
    assert refreshed.status == "exit"
    assert refreshed.pull_requests == [
        {"pr_url": "https://gh.example/2", "pr_state": None}
    ]
    assert refreshed.structured_output == {"outcome": "duplicate"}
    assert refreshed.session_updated_at == at(1700001000)
    assert outcome_rows(unit_session, refreshed.id) == {
        "pull_request",
        "duplicate",
    }


def test_upsert_replaces_stale_outcome_rows(unit_session: Session) -> None:
    action = add_action(unit_session, "auto-1")
    payloads = [
        session_payload(
            "s-1",
            "auto-1",
            pull_requests=[{"pr_url": "https://gh.example/1"}],
        ),
        session_payload(
            "s-1",
            "auto-1",
            status="exit",
            structured_output={"outcome": "duplicate"},
        ),
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [payloads.pop(0)], "has_next_page": False},
        )

    client = make_client(httpx.MockTransport(handler))
    poll_once(unit_session, client)
    invocation = unit_session.exec(
        select(Invocation).where(Invocation.session_id == "s-1")
    ).one()
    assert invocation.action_node_id == action.id
    assert outcome_rows(unit_session, invocation.id) == {"pull_request"}

    poll_once(unit_session, client)
    unit_session.expire_all()
    assert outcome_rows(unit_session, invocation.id) == {"duplicate"}


def test_poll_retries_failed_syncs_before_listing(unit_session: Session) -> None:
    # an errored Action with an Automation is re-synced first, and a pending
    # Action without one gets its Automation created, so both are owned by
    # the time sessions are listed in the same cycle
    errored = add_action(unit_session, "auto-1")
    errored.sync_status = "error"
    errored.sync_error = "boom"
    pending = ActionNode(
        position_x=0,
        position_y=0,
        name="Triage",
        playbook_id="pb-1",
        prompt="Inspect the issue",
        enabled=True,
        sync_status="pending",
    )
    trigger = TriggerNode(
        position_x=0,
        position_y=0,
        event_action="opened",
        repository_full_name="octo/repo",
    )
    unit_session.add_all([errored, pending, trigger])
    unit_session.commit()
    unit_session.add(
        Edge(
            source_id=trigger.id,
            source_kind="trigger",
            target_id=pending.id,
            target_kind="action",
        )
    )
    unit_session.commit()
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == "/organizations/org-test/automations/auto-1":
            assert request.method == "PATCH"
            return httpx.Response(
                200,
                json={
                    "automation_id": "auto-1",
                    "name": "auto-1",
                    "enabled": False,
                },
            )
        if path == "/organizations/org-test/automations":
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={"items": [], "has_next_page": False, "end_cursor": None},
                )
            return httpx.Response(
                201,
                json={
                    "automation_id": "auto-new",
                    "name": "auto-new",
                    "enabled": True,
                },
            )
        assert path == "/organizations/org-test/sessions"
        assert request.method == "GET"
        assert request.url.params.get_list("automation_ids") == [
            "auto-1",
            "auto-new",
        ]
        return httpx.Response(200, json={"items": [], "has_next_page": False})

    result = poll_once(unit_session, make_client(httpx.MockTransport(handler)))

    assert result == PollResult(listed=0, upserted=0, refreshed=0, synced=2)
    methods = [method for method, _ in calls]
    assert methods[-1] == "GET"
    assert calls[-1][1] == "/organizations/org-test/sessions"
    assert methods[:3] == ["PATCH", "GET", "POST"]
    stored = unit_session.get(ActionNode, pending.id)
    assert stored is not None
    assert stored.automation_id == "auto-new"
    assert stored.sync_status == "enabled"


def test_upstream_failure_leaves_state_untouched(unit_session: Session) -> None:
    add_action(unit_session, "auto-1")

    client = make_client(
        httpx.MockTransport(lambda _request: httpx.Response(500, text="boom"))
    )
    with pytest.raises(DevinUpstreamError):
        poll_once(unit_session, client)
    unit_session.rollback()
    assert unit_session.get(PollerState, 1) is None
    assert unit_session.exec(select(Invocation)).all() == []


def test_run_poll_cycle_uses_engine_and_client(
    monkeypatch: pytest.MonkeyPatch, unit_session: Session
) -> None:
    from devin_flow import invocations

    calls: list[tuple[Session, DevinClient]] = []
    client = make_client(httpx.MockTransport(lambda _r: httpx.Response(500)))

    def fake_poll_once(session: Session, devin: DevinClient) -> PollResult:
        calls.append((session, devin))
        return PollResult(listed=0, upserted=0, refreshed=0, synced=0)

    monkeypatch.setattr(invocations, "poll_once", fake_poll_once)
    monkeypatch.setattr(invocations, "get_engine", lambda: unit_session.get_bind())
    monkeypatch.setattr(invocations, "get_devin_client", lambda: client)

    assert run_poll_cycle() == PollResult(listed=0, upserted=0, refreshed=0, synced=0)
    assert len(calls) == 1
    assert calls[0][1] is client


def test_poll_forever_logs_failures_and_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0

    def run_cycle() -> PollResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("upstream down")
        return PollResult(listed=1, upserted=1, refreshed=0, synced=0)

    async def run() -> None:
        task = asyncio.create_task(poll_forever(0.01, run_cycle))
        while attempts < 3:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with caplog.at_level(logging.INFO, logger="devin_flow.invocations"):
        asyncio.run(run())

    assert attempts >= 3
    assert "invocation poll failed" in caplog.text
    assert "'listed': 1" in caplog.text
