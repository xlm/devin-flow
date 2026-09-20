from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, col, select

from devin_flow.api.devin import DevinClientDep, ErrorResponse, upstream_error
from devin_flow.db import get_session
from devin_flow.devin.client import DevinUpstreamError
from devin_flow.invocations import (
    PollResult,
    apply_session,
    poll_once,
    record_outcomes,
)
from devin_flow.models import Invocation

router = APIRouter(prefix="/invocations")
SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/refresh",
    response_model=PollResult,
    responses={
        502: {"model": ErrorResponse, "description": "Devin API failure"},
        503: {
            "model": ErrorResponse,
            "description": "Devin API not configured",
        },
    },
)
def refresh_invocations(session: SessionDep, client: DevinClientDep) -> PollResult:
    try:
        return poll_once(session, client)
    except DevinUpstreamError as exc:
        session.rollback()
        raise upstream_error(exc) from exc


@router.post(
    "/{invocation_id}/archive",
    status_code=204,
    responses={
        404: {"model": ErrorResponse, "description": "Invocation not found"},
        502: {"model": ErrorResponse, "description": "Devin API failure"},
        503: {
            "model": ErrorResponse,
            "description": "Devin API not configured",
        },
    },
)
def archive_invocation(
    invocation_id: UUID,
    session: SessionDep,
    client: DevinClientDep,
) -> Response:
    invocation = session.exec(
        select(Invocation).where(col(Invocation.id) == invocation_id)
    ).first()
    if invocation is None:
        raise HTTPException(404, "invocation not found")
    try:
        now = datetime.now(UTC)
        devin_session = client.archive_session(invocation.session_id)
        apply_session(invocation, devin_session, now)
        invocation.archived_at = now
        session.add(invocation)
        record_outcomes(session, invocation)
        session.commit()
    except DevinUpstreamError as exc:
        session.rollback()
        raise upstream_error(exc) from exc
    return Response(status_code=204)
