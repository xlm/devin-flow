from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from devin_flow.api.devin import ErrorResponse
from devin_flow.db import get_session
from devin_flow.models import Edge, Invocation, InvocationOutcome, OutcomeNode
from devin_flow.outcomes import (
    PullRequestLink,
    duplicate_of,
    pull_request_links,
)

router = APIRouter(prefix="/outcome-nodes")
SessionDep = Annotated[Session, Depends(get_session)]


class OutcomeInvocationRead(BaseModel):
    id: UUID
    session_id: str
    title: str | None
    url: str | None
    status: str
    session_created_at: datetime
    pull_requests: list[PullRequestLink]
    duplicate_of: str | None
    archived_at: datetime | None


@router.get(
    "/{node_id}/invocations",
    response_model=list[OutcomeInvocationRead],
    responses={
        404: {"model": ErrorResponse, "description": "Outcome node not found"},
    },
)
def list_outcome_invocations(
    node_id: UUID,
    session: SessionDep,
    action_node_id: UUID | None = None,
) -> list[OutcomeInvocationRead]:
    node = session.get(OutcomeNode, node_id)
    if node is None:
        raise HTTPException(404, "outcome node not found")
    edges = session.exec(
        select(Edge).where(
            col(Edge.target_id) == node_id,
            col(Edge.source_kind) == "action",
        )
    ).all()
    action_ids = [edge.source_id for edge in edges]
    if not action_ids or node.kind is None:
        return []
    if action_node_id is not None:
        if action_node_id not in action_ids:
            return []
        action_ids = [action_node_id]
    invocations = session.exec(
        select(Invocation)
        .join(
            InvocationOutcome,
            col(InvocationOutcome.invocation_id) == col(Invocation.id),
        )
        .where(col(Invocation.action_node_id).in_(action_ids))
        .where(col(InvocationOutcome.kind) == node.kind)
        .order_by(col(Invocation.session_created_at).desc())
    ).all()
    return [
        OutcomeInvocationRead(
            id=invocation.id,
            session_id=invocation.session_id,
            title=invocation.title,
            url=invocation.url,
            status=invocation.status,
            session_created_at=invocation.session_created_at,
            archived_at=invocation.archived_at,
            pull_requests=pull_request_links(invocation),
            duplicate_of=duplicate_of(invocation),
        )
        for invocation in invocations
    ]
