from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from devin_flow.api.devin import DevinClientDep, ErrorResponse, upstream_error
from devin_flow.db import get_session
from devin_flow.devin.client import DevinUpstreamError
from devin_flow.invocations import PollResult, poll_once

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
