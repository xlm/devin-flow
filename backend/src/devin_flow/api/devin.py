from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from devin_flow.devin import DevinClient, get_devin_client
from devin_flow.devin.client import (
    DevinSession,
    DevinUpstreamError,
    Repository,
    SessionCreate,
)

router = APIRouter()

DevinClientDep = Annotated[DevinClient, Depends(get_devin_client)]


class ErrorResponse(BaseModel):
    detail: str


def upstream_error(exc: DevinUpstreamError) -> HTTPException:
    return HTTPException(status_code=502, detail=exc.detail)


@router.get(
    "/devin/sessions",
    response_model=list[DevinSession],
    responses={
        502: {"model": ErrorResponse, "description": "Devin API failure"},
        503: {
            "model": ErrorResponse,
            "description": "Devin API not configured",
        },
    },
)
def list_sessions(
    client: DevinClientDep, limit: int = Query(100, ge=1, le=200)
) -> list[DevinSession]:
    try:
        return client.list_sessions(limit=limit)
    except DevinUpstreamError as exc:
        raise upstream_error(exc) from exc


@router.get(
    "/devin/repositories",
    response_model=list[Repository],
    responses={
        502: {"model": ErrorResponse, "description": "Devin API failure"},
        503: {
            "model": ErrorResponse,
            "description": "Devin API not configured",
        },
    },
)
def list_repositories(client: DevinClientDep) -> list[Repository]:
    try:
        return client.list_repositories()
    except DevinUpstreamError as exc:
        raise upstream_error(exc) from exc


@router.post(
    "/devin/sessions",
    response_model=DevinSession,
    status_code=201,
    responses={
        502: {"model": ErrorResponse, "description": "Devin API failure"},
        503: {
            "model": ErrorResponse,
            "description": "Devin API not configured",
        },
    },
)
def create_session(payload: SessionCreate, client: DevinClientDep) -> DevinSession:
    try:
        return client.create_session(payload)
    except DevinUpstreamError as exc:
        raise upstream_error(exc) from exc
