import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel
from sqlmodel import Session, col, select

from devin_flow.automations import retry_syncs
from devin_flow.db import get_engine
from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import TERMINAL_SESSION_STATUSES, DevinSession
from devin_flow.models import (
    ActionNode,
    Invocation,
    InvocationOutcome,
    PollerState,
)
from devin_flow.outcomes import outcome_kinds

logger = logging.getLogger(__name__)

# re-list a little before the last success so sessions that were created while
# the previous poll ran are not missed
SAFETY_MARGIN = timedelta(minutes=10)


class PollResult(BaseModel):
    listed: int
    upserted: int
    refreshed: int
    synced: int


def _timestamp(value: int | None, fallback: datetime) -> datetime:
    return fallback if value is None else datetime.fromtimestamp(value, UTC)


def apply_session(invocation: Invocation, session: DevinSession, now: datetime) -> None:
    invocation.status = session.status
    invocation.title = session.title
    invocation.url = session.url
    invocation.pull_requests = [pr.model_dump() for pr in session.pull_requests]
    invocation.structured_output = session.structured_output
    invocation.session_updated_at = _timestamp(session.updated_at, now)
    invocation.updated_at = now


def get_poller_state(session: Session) -> PollerState:
    # the row lock serializes overlapping poll cycles (lifespan task, manual
    # refresh, other workers) until this session commits
    state = session.exec(select(PollerState).with_for_update()).first()
    if state is None:
        state = PollerState()
        session.add(state)
    return state


def automation_owners(session: Session) -> dict[str, UUID]:
    # archived Actions keep their automation_id so sessions started before
    # the delete are still mirrored
    actions = session.exec(
        select(ActionNode).where(col(ActionNode.automation_id).is_not(None))
    ).all()
    return {
        action.automation_id: action.id
        for action in actions
        if action.automation_id is not None
    }


def record_outcomes(session: Session, invocation: Invocation) -> None:
    derived = outcome_kinds(invocation)
    rows = session.exec(
        select(InvocationOutcome).where(
            InvocationOutcome.invocation_id == invocation.id
        )
    ).all()
    existing = {row.kind for row in rows}
    for row in rows:
        if row.kind not in derived:
            session.delete(row)
    for kind in derived - existing:
        session.add(InvocationOutcome(invocation_id=invocation.id, kind=kind))


def upsert_invocation(
    session: Session,
    devin_session: DevinSession,
    action_node_id: UUID,
    now: datetime,
) -> Invocation:
    assert devin_session.automation_id is not None
    invocation = session.exec(
        select(Invocation).where(Invocation.session_id == devin_session.session_id)
    ).first()
    if invocation is None:
        invocation = Invocation(
            session_id=devin_session.session_id,
            automation_id=devin_session.automation_id,
            action_node_id=action_node_id,
            status=devin_session.status,
            session_created_at=_timestamp(devin_session.created_at, now),
            session_updated_at=_timestamp(devin_session.updated_at, now),
            created_at=now,
        )
    invocation.action_node_id = action_node_id
    apply_session(invocation, devin_session, now)
    session.add(invocation)
    record_outcomes(session, invocation)
    return invocation


def poll_once(session: Session, client: DevinClient) -> PollResult:
    started = datetime.now(UTC)
    # retry before taking the poller_state row lock so automations created by
    # the retry are already owned in automation_owners below
    synced = retry_syncs(session, client)
    state = get_poller_state(session)
    created_after = (
        None
        if state.last_success_at is None
        else int((state.last_success_at - SAFETY_MARGIN).timestamp())
    )
    owners = automation_owners(session)
    listed = (
        client.list_sessions(
            automation_ids=sorted(owners),
            created_after=created_after,
            paginate=True,
        )
        if owners
        else []
    )
    seen: set[str] = set()
    upserted = 0
    for devin_session in listed:
        action_id = owners.get(devin_session.automation_id or "")
        if action_id is None:
            continue
        upsert_invocation(session, devin_session, action_id, started)
        seen.add(devin_session.session_id)
        upserted += 1
    session.flush()
    stale = session.exec(
        select(Invocation).where(
            col(Invocation.status).not_in(TERMINAL_SESSION_STATUSES),
            col(Invocation.session_id).not_in(seen),
        )
    ).all()
    for invocation in stale:
        apply_session(invocation, client.get_session(invocation.session_id), started)
        session.add(invocation)
        record_outcomes(session, invocation)
    state.last_success_at = started
    session.add(state)
    session.commit()
    return PollResult(
        listed=len(listed), upserted=upserted, refreshed=len(stale), synced=synced
    )


def run_poll_cycle() -> PollResult:
    with Session(get_engine()) as session:
        return poll_once(session, get_devin_client())


async def poll_forever(
    interval_seconds: float,
    run_cycle: Callable[[], PollResult] = run_poll_cycle,
) -> None:
    while True:
        try:
            result = await asyncio.to_thread(run_cycle)
            logger.info("invocation poll: %s", result.model_dump())
        except Exception:
            logger.exception("invocation poll failed")
        await asyncio.sleep(interval_seconds)
