from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from devin_flow.api.devin import ErrorResponse
from devin_flow.api.outcomes import OutcomeInvocationRead, SessionDep
from devin_flow.models import ActionNode, Edge, Invocation, TriggerNode
from devin_flow.outcomes import IssueRef, duplicate_of, issue_ref, pull_request_links

router = APIRouter(prefix="/action-nodes")


class ActionInvocationRead(OutcomeInvocationRead):
    issue: IssueRef | None


@router.get(
    "/{node_id}/invocations",
    response_model=list[ActionInvocationRead],
    responses={
        404: {"model": ErrorResponse, "description": "Action node not found"},
    },
)
def list_action_invocations(
    node_id: UUID,
    session: SessionDep,
) -> list[ActionInvocationRead]:
    node = session.get(ActionNode, node_id)
    if node is None:
        raise HTTPException(404, "action node not found")
    trigger_edge = session.exec(
        select(Edge).where(
            col(Edge.target_id) == node_id,
            col(Edge.source_kind) == "trigger",
        )
    ).first()
    repository_full_name = None
    if trigger_edge is not None:
        trigger = session.get(TriggerNode, trigger_edge.source_id)
        if trigger is not None:
            repository_full_name = trigger.repository_full_name
    invocations = session.exec(
        select(Invocation)
        .where(col(Invocation.action_node_id) == node_id)
        .order_by(col(Invocation.session_created_at).desc())
    ).all()
    return [
        ActionInvocationRead(
            id=invocation.id,
            session_id=invocation.session_id,
            title=invocation.title,
            url=invocation.url,
            status=invocation.status,
            session_created_at=invocation.session_created_at,
            pull_requests=pull_request_links(invocation),
            duplicate_of=duplicate_of(invocation),
            issue=issue_ref(invocation, repository_full_name),
        )
        for invocation in invocations
    ]
