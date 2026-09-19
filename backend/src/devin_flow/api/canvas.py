import re
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field, FiniteFloat
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select

from devin_flow.api.devin import DevinClientDep, ErrorResponse
from devin_flow.automations import (
    connected_action,
    connected_trigger,
    flow_invalid_reason,
    mark_pending,
    sync_action,
)
from devin_flow.canvas import (
    ConnectError,
    NodeRef,
    check_edge_kinds,
    check_edge_uniqueness,
)
from devin_flow.db import get_session
from devin_flow.devin.client import (
    AutomationUpdate,
    DevinNotConfiguredError,
    DevinUpstreamError,
)
from devin_flow.models import (
    NODE_MODELS,
    ActionNode,
    Edge,
    EventAction,
    Invocation,
    InvocationOutcome,
    NodeBase,
    NodeKind,
    OutcomeKind,
    OutcomeNode,
    SyncStatus,
    TriggerNode,
)

router = APIRouter(prefix="/canvas")
SessionDep = Annotated[Session, Depends(get_session)]


class Position(BaseModel):
    x: FiniteFloat
    y: FiniteFloat


REPOSITORY_FULL_NAME_PATTERN = (
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$"
)


def check_repository_full_name(value: str) -> str:
    if re.fullmatch(REPOSITORY_FULL_NAME_PATTERN, value) is None:
        raise ValueError("must look like owner/repo")
    return value


RepositoryFullName = Annotated[str, AfterValidator(check_repository_full_name)]


class TriggerRead(BaseModel):
    event_action: EventAction | None
    repository_full_name: str | None


class TriggerUpdate(BaseModel):
    event_action: EventAction | None = None
    repository_full_name: RepositoryFullName | None = None


class OutcomeRead(BaseModel):
    kind: OutcomeKind | None


class OutcomeUpdate(BaseModel):
    kind: OutcomeKind | None = None


class NodeRead(BaseModel):
    id: UUID
    kind: NodeKind
    position: Position
    trigger: TriggerRead | None = None
    outcome: OutcomeRead | None = None


class ActionFieldsBase(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    playbook_id: str | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = Field(default=None, max_length=20_000)


class ActionFields(ActionFieldsBase):
    enabled: bool | None = None


class ActionNodeRead(NodeRead):
    name: str
    playbook_id: str | None
    prompt: str
    enabled: bool
    sync_status: SyncStatus
    sync_error: str | None
    automation_id: str | None
    invocation_count: int = 0


class NodeCreate(ActionFieldsBase):
    position: Position
    trigger: TriggerUpdate | None = None
    outcome: OutcomeUpdate | None = None


class NodeUpdate(ActionFields):
    position: Position | None = None
    trigger: TriggerUpdate | None = None
    outcome: OutcomeUpdate | None = None


class EdgeRead(BaseModel):
    id: UUID
    source: NodeRef
    target: NodeRef
    outcome_count: int | None = None


class EdgeCreate(BaseModel):
    source: NodeRef
    target: NodeRef


class CanvasRead(BaseModel):
    trigger_nodes: list[NodeRead]
    action_nodes: list[ActionNodeRead]
    outcome_nodes: list[NodeRead]
    edges: list[EdgeRead]


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Canvas object not found"},
    409: {"model": ErrorResponse, "description": "Canvas conflict"},
}


def node_read(
    node: NodeBase, kind: NodeKind, invocation_count: int = 0
) -> NodeRead | ActionNodeRead:
    fields = {
        "id": node.id,
        "kind": kind,
        "position": Position(x=node.position_x, y=node.position_y),
    }
    if isinstance(node, ActionNode):
        return ActionNodeRead(
            **fields,
            name=node.name,
            playbook_id=node.playbook_id,
            prompt=node.prompt,
            enabled=node.enabled,
            sync_status=node.sync_status,
            sync_error=node.sync_error,
            automation_id=node.automation_id,
            invocation_count=invocation_count,
        )
    return NodeRead(
        trigger=(
            TriggerRead(
                event_action=node.event_action,
                repository_full_name=node.repository_full_name,
            )
            if isinstance(node, TriggerNode)
            else None
        ),
        outcome=(
            OutcomeRead(kind=node.kind) if isinstance(node, OutcomeNode) else None
        ),
        **fields,
    )


def apply_action_fields(node: NodeBase, payload: ActionFieldsBase) -> None:
    fields = payload.model_fields_set & {"name", "playbook_id", "prompt"}
    if isinstance(payload, ActionFields) and "enabled" in payload.model_fields_set:
        fields.add("enabled")
    if not fields:
        return
    if not isinstance(node, ActionNode):
        raise HTTPException(
            422,
            "only action nodes have name, playbook_id, prompt and enabled",
        )
    if "name" in fields:
        node.name = payload.name or ""
    if "playbook_id" in fields:
        node.playbook_id = payload.playbook_id
    if "prompt" in fields:
        node.prompt = payload.prompt or ""
    if "enabled" in fields:
        assert isinstance(payload, ActionFields)
        if payload.enabled is not None:
            node.enabled = payload.enabled


def edge_read(edge: Edge, outcome_count: int | None = None) -> EdgeRead:
    return EdgeRead(
        id=edge.id,
        source=NodeRef(id=edge.source_id, kind=edge.source_kind),
        target=NodeRef(id=edge.target_id, kind=edge.target_kind),
        outcome_count=outcome_count,
    )


def get_node(
    session: Session, kind: NodeKind, node_id: UUID, *, for_update: bool = False
) -> NodeBase | None:
    if kind == "action":
        query = select(ActionNode).where(
            ActionNode.id == node_id,
            col(ActionNode.deleted_at).is_(None),
        )
        if for_update:
            query = query.with_for_update()
        return session.exec(query).first()
    return session.get(NODE_MODELS[kind], node_id, with_for_update=for_update)


def invocation_count(session: Session, action_id: UUID) -> int:
    return session.exec(
        select(func.count()).where(Invocation.action_node_id == action_id)
    ).one()


@router.get("", response_model=CanvasRead)
def get_canvas(session: SessionDep) -> CanvasRead:
    counts = dict(
        session.exec(
            select(col(Invocation.action_node_id), func.count()).group_by(
                col(Invocation.action_node_id)
            )
        ).all()
    )
    edges = session.exec(select(Edge).order_by(col(Edge.created_at))).all()
    outcome_kind_by_id = {
        node.id: node.kind for node in session.exec(select(OutcomeNode)).all()
    }
    action_ids = [edge.source_id for edge in edges if edge.target_kind == "outcome"]
    outcome_counts = (
        {
            (action_id, kind): count
            for action_id, kind, count in session.exec(
                select(
                    col(Invocation.action_node_id),
                    col(InvocationOutcome.kind),
                    func.count(),
                )
                .join(
                    InvocationOutcome,
                    col(InvocationOutcome.invocation_id) == col(Invocation.id),
                )
                .where(col(Invocation.action_node_id).in_(action_ids))
                .group_by(col(Invocation.action_node_id), col(InvocationOutcome.kind))
            ).all()
        }
        if action_ids
        else {}
    )

    def outcome_count(edge: Edge) -> int | None:
        if edge.target_kind != "outcome":
            return None
        kind = outcome_kind_by_id.get(edge.target_id)
        if kind is None:
            return 0
        return outcome_counts.get((edge.source_id, kind), 0)

    nodes = {
        "trigger": [
            node_read(node, "trigger")
            for node in session.exec(
                select(TriggerNode).order_by(col(TriggerNode.created_at))
            ).all()
        ],
        "action": [
            node_read(node, "action", counts.get(node.id, 0))
            for node in session.exec(
                select(ActionNode)
                .where(col(ActionNode.deleted_at).is_(None))
                .order_by(col(ActionNode.created_at))
            ).all()
        ],
        "outcome": [
            node_read(node, "outcome")
            for node in session.exec(
                select(OutcomeNode).order_by(col(OutcomeNode.created_at))
            ).all()
        ],
    }
    return CanvasRead(
        trigger_nodes=nodes["trigger"],
        action_nodes=nodes["action"],
        outcome_nodes=nodes["outcome"],
        edges=[edge_read(edge, outcome_count(edge)) for edge in edges],
    )


@router.post(
    "/nodes/{kind}",
    response_model=ActionNodeRead | NodeRead,
    status_code=201,
    responses=ERROR_RESPONSES,
)
def create_node(
    kind: NodeKind, payload: NodeCreate, session: SessionDep
) -> NodeRead | ActionNodeRead:
    if payload.trigger is not None and kind != "trigger":
        raise HTTPException(422, "trigger fields apply only to trigger nodes")
    if payload.outcome is not None and kind != "outcome":
        raise HTTPException(422, "outcome fields apply only to outcome nodes")
    node = NODE_MODELS[kind](
        position_x=payload.position.x,
        position_y=payload.position.y,
        **(
            {
                "event_action": payload.trigger.event_action,
                "repository_full_name": payload.trigger.repository_full_name,
            }
            if payload.trigger is not None
            else {}
        ),
        **({"kind": payload.outcome.kind} if payload.outcome is not None else {}),
    )
    apply_action_fields(node, payload)
    session.add(node)
    session.commit()
    session.refresh(node)
    return node_read(node, kind)


@router.patch(
    "/nodes/{kind}/{node_id}",
    response_model=ActionNodeRead | NodeRead,
    responses=ERROR_RESPONSES,
)
def update_node(
    kind: NodeKind,
    node_id: UUID,
    payload: NodeUpdate,
    session: SessionDep,
    client: DevinClientDep,
) -> NodeRead | ActionNodeRead:
    node = get_node(session, kind, node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    if payload.trigger is not None and kind != "trigger":
        raise HTTPException(422, "trigger fields apply only to trigger nodes")
    if payload.outcome is not None and kind != "outcome":
        raise HTTPException(422, "outcome fields apply only to outcome nodes")
    if payload.position is not None:
        node.position_x = payload.position.x
        node.position_y = payload.position.y
    if payload.trigger is not None and isinstance(node, TriggerNode):
        fields_set = payload.trigger.model_fields_set
        if "event_action" in fields_set:
            node.event_action = payload.trigger.event_action
        if "repository_full_name" in fields_set:
            node.repository_full_name = payload.trigger.repository_full_name
    if (
        payload.outcome is not None
        and isinstance(node, OutcomeNode)
        and "kind" in payload.outcome.model_fields_set
    ):
        node.kind = payload.outcome.kind
    apply_action_fields(node, payload)
    action_fields = payload.model_fields_set & {
        "name",
        "playbook_id",
        "prompt",
        "enabled",
    }
    if isinstance(node, ActionNode) and payload.enabled is True:
        reason = flow_invalid_reason(node, connected_trigger(session, node.id))
        if reason is not None:
            session.rollback()
            raise HTTPException(409, f"cannot enable: {reason}")
    node.updated_at = datetime.now(UTC)
    session.add(node)
    session.commit()
    if isinstance(node, ActionNode) and action_fields:
        mark_pending(node)
        session.add(node)
        session.commit()
        sync_action(session, client, node.id)
    elif isinstance(node, TriggerNode) and payload.trigger is not None:
        action = connected_action(session, node.id)
        if action is not None:
            mark_pending(action)
            session.add(action)
            session.commit()
            sync_action(session, client, action.id)
    session.refresh(node)
    return node_read(node, kind, invocation_count(session, node.id))


@router.delete("/nodes/{kind}/{node_id}", status_code=204, responses=ERROR_RESPONSES)
def delete_node(
    kind: NodeKind,
    node_id: UUID,
    session: SessionDep,
    client: DevinClientDep,
) -> Response:
    node = get_node(session, kind, node_id, for_update=True)
    if node is None:
        raise HTTPException(404, "node not found")
    action = (
        connected_action(session, node.id) if isinstance(node, TriggerNode) else None
    )
    if isinstance(node, ActionNode) and node.automation_id is not None:
        disable_error: str | None = None
        try:
            client.update_automation(
                node.automation_id,
                AutomationUpdate(enabled=False),
            )
        except DevinUpstreamError as exc:
            disable_error = exc.detail
        except DevinNotConfiguredError:
            disable_error = "devin api not configured"
        session.exec(
            delete(Edge).where(
                (col(Edge.source_id) == node_id) | (col(Edge.target_id) == node_id)
            )
        )
        node.enabled = False
        node.sync_status = "error" if disable_error is not None else "disabled"
        node.sync_error = disable_error
        node.deleted_at = datetime.now(UTC)
        session.add(node)
        session.commit()
        return Response(status_code=204)
    session.exec(
        delete(Edge).where(
            (col(Edge.source_id) == node_id) | (col(Edge.target_id) == node_id)
        )
    )
    session.delete(node)
    session.commit()
    if action is not None:
        mark_pending(action)
        session.add(action)
        session.commit()
        sync_action(session, client, action.id)
    return Response(status_code=204)


@router.post(
    "/edges",
    response_model=EdgeRead,
    status_code=201,
    responses=ERROR_RESPONSES,
)
def create_edge(
    payload: EdgeCreate, session: SessionDep, client: DevinClientDep
) -> EdgeRead:
    try:
        check_edge_kinds(payload.source.kind, payload.target.kind)
    except ConnectError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    if (
        get_node(session, payload.source.kind, payload.source.id, for_update=True)
        is None
    ):
        raise HTTPException(404, "source node not found")
    if (
        get_node(session, payload.target.kind, payload.target.id, for_update=True)
        is None
    ):
        raise HTTPException(404, "target node not found")
    existing = session.exec(select(Edge)).all()
    try:
        check_edge_uniqueness(existing, payload.source, payload.target)
    except ConnectError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    edge = Edge(
        source_id=payload.source.id,
        source_kind=payload.source.kind,
        target_id=payload.target.id,
        target_kind=payload.target.kind,
    )
    try:
        session.add(edge)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "edge conflicts with an existing edge") from exc
    session.refresh(edge)
    if edge.source_kind == "trigger":
        action = session.get(ActionNode, edge.target_id)
        if action is not None:
            mark_pending(action)
            session.add(action)
            session.commit()
            sync_action(session, client, action.id)
    return edge_read(edge)


@router.delete("/edges/{edge_id}", status_code=204, responses=ERROR_RESPONSES)
def delete_edge(edge_id: UUID, session: SessionDep, client: DevinClientDep) -> Response:
    edge = session.get(Edge, edge_id)
    if edge is None:
        raise HTTPException(404, "edge not found")
    action_id = edge.target_id if edge.source_kind == "trigger" else None
    session.delete(edge)
    session.commit()
    if action_id is not None:
        action = session.get(ActionNode, action_id)
        if action is not None:
            mark_pending(action)
            session.add(action)
            session.commit()
            sync_action(session, client, action.id)
    return Response(status_code=204)
