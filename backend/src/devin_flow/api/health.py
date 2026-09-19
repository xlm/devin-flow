from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from devin_flow.config import get_settings
from devin_flow.db import get_session
from devin_flow.models import PollerState

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]

# a poller that missed this many intervals in a row is reported stale
STALE_INTERVALS = 3


class PollingStatus(BaseModel):
    enabled: bool
    interval_seconds: float
    last_success_at: datetime | None
    stale: bool


class HealthResponse(BaseModel):
    status: Literal["ok"]
    polling: PollingStatus


def _as_utc(value: datetime) -> datetime:
    # sqlite hands back naive timestamps, which the poller always stores as UTC
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def polling_status(
    last_success_at: datetime | None, interval_seconds: float, now: datetime
) -> PollingStatus:
    enabled = interval_seconds > 0
    stale = enabled and (
        last_success_at is None
        or (now - _as_utc(last_success_at)).total_seconds()
        > STALE_INTERVALS * interval_seconds
    )
    return PollingStatus(
        enabled=enabled,
        interval_seconds=interval_seconds,
        last_success_at=last_success_at,
        stale=stale,
    )


@router.get("/health")
def health(session: SessionDep) -> HealthResponse:
    # a plain read, not the locking get_poller_state, so health never waits on
    # a running poll cycle
    state = session.exec(select(PollerState)).first()
    return HealthResponse(
        status="ok",
        polling=polling_status(
            None if state is None else state.last_success_at,
            get_settings().poll_interval_seconds,
            datetime.now(UTC),
        ),
    )
