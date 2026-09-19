from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, FiniteFloat, StringConstraints
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select

from devin_flow.api.devin import ErrorResponse
from devin_flow.canvas import (
    ConnectError,
    NodeRef,
    check_edge_kinds,
    check_edge_uniqueness,
)
from devin_flow.db import get_session
from devin_flow.models import (
    NODE_MODELS,
    Edge,
    EventAction,
    NodeBase,
    NodeKind,
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
RepositoryFullName = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/"
            r"(?:[A-Za-z0-9_-]|"
            r"(?:[A-Za-z0-9_-][A-Za-z0-9._-]|\.[A-Za-z0-9_-])|"
            r"[A-Za-z0-9._-]{3,100})$"
        )
    ),
]


class TriggerRead(BaseModel):
    event_action: EventAction | None
    repository_full_name: str | None


class TriggerUpdate(BaseModel):
    event_action: EventAction | None = None
    repository_full_name: RepositoryFullName | None = None


class NodeRead(BaseModel):
    id: UUID
    kind: NodeKind
    position: Position
    trigger: TriggerRead | None = None


class NodeCreate(BaseModel):
    position: Position
    trigger: TriggerUpdate | None = None


class NodeUpdate(BaseModel):
    position: Position | None = None
    trigger: TriggerUpdate | None = None


class EdgeRead(BaseModel):
    id: UUID
    source: NodeRef
    target: NodeRef


class EdgeCreate(BaseModel):
    source: NodeRef
    target: NodeRef


class CanvasRead(BaseModel):
    trigger_nodes: list[NodeRead]
    action_nodes: list[NodeRead]
    outcome_nodes: list[NodeRead]
    edges: list[EdgeRead]


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Canvas object not found"},
    409: {"model": ErrorResponse, "description": "Canvas conflict"},
}


def node_read(node: NodeBase, kind: NodeKind) -> NodeRead:
    return NodeRead(
        id=node.id,
        kind=kind,
        position=Position(x=node.position_x, y=node.position_y),
        trigger=(
            TriggerRead(
                event_action=node.event_action,
                repository_full_name=node.repository_full_name,
            )
            if isinstance(node, TriggerNode)
            else None
        ),
    )


def edge_read(edge: Edge) -> EdgeRead:
    return EdgeRead(
        id=edge.id,
        source=NodeRef(id=edge.source_id, kind=edge.source_kind),
        target=NodeRef(id=edge.target_id, kind=edge.target_kind),
    )


def get_node(
    session: Session, kind: NodeKind, node_id: UUID, *, for_update: bool = False
) -> NodeBase | None:
    return session.get(NODE_MODELS[kind], node_id, with_for_update=for_update)


@router.get("", response_model=CanvasRead)
def get_canvas(session: SessionDep) -> CanvasRead:
    nodes = {
        kind: [
            node_read(node, kind)
            for node in session.exec(
                select(model).order_by(col(model.created_at))
            ).all()
        ]
        for kind, model in NODE_MODELS.items()
    }
    edges = session.exec(select(Edge).order_by(col(Edge.created_at))).all()
    return CanvasRead(
        trigger_nodes=nodes["trigger"],
        action_nodes=nodes["action"],
        outcome_nodes=nodes["outcome"],
        edges=[edge_read(edge) for edge in edges],
    )


@router.post(
    "/nodes/{kind}",
    response_model=NodeRead,
    status_code=201,
    responses=ERROR_RESPONSES,
)
def create_node(kind: NodeKind, payload: NodeCreate, session: SessionDep) -> NodeRead:
    if payload.trigger is not None and kind != "trigger":
        raise HTTPException(422, "trigger fields apply only to trigger nodes")
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
    )
    session.add(node)
    session.commit()
    session.refresh(node)
    return node_read(node, kind)


@router.patch(
    "/nodes/{kind}/{node_id}",
    response_model=NodeRead,
    responses=ERROR_RESPONSES,
)
def update_node(
    kind: NodeKind, node_id: UUID, payload: NodeUpdate, session: SessionDep
) -> NodeRead:
    node = get_node(session, kind, node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    if payload.trigger is not None and kind != "trigger":
        raise HTTPException(422, "trigger fields apply only to trigger nodes")
    if payload.position is not None:
        node.position_x = payload.position.x
        node.position_y = payload.position.y
    if payload.trigger is not None and isinstance(node, TriggerNode):
        fields_set = payload.trigger.model_fields_set
        if "event_action" in fields_set:
            node.event_action = payload.trigger.event_action
        if "repository_full_name" in fields_set:
            node.repository_full_name = payload.trigger.repository_full_name
    node.updated_at = datetime.now(UTC)
    session.add(node)
    session.commit()
    session.refresh(node)
    return node_read(node, kind)


@router.delete("/nodes/{kind}/{node_id}", status_code=204, responses=ERROR_RESPONSES)
def delete_node(kind: NodeKind, node_id: UUID, session: SessionDep) -> Response:
    node = get_node(session, kind, node_id, for_update=True)
    if node is None:
        raise HTTPException(404, "node not found")
    session.exec(
        delete(Edge).where(
            (col(Edge.source_id) == node_id) | (col(Edge.target_id) == node_id)
        )
    )
    session.delete(node)
    session.commit()
    return Response(status_code=204)


@router.post(
    "/edges",
    response_model=EdgeRead,
    status_code=201,
    responses=ERROR_RESPONSES,
)
def create_edge(payload: EdgeCreate, session: SessionDep) -> EdgeRead:
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
    return edge_read(edge)


@router.delete("/edges/{edge_id}", status_code=204, responses=ERROR_RESPONSES)
def delete_edge(edge_id: UUID, session: SessionDep) -> Response:
    edge = session.get(Edge, edge_id)
    if edge is None:
        raise HTTPException(404, "edge not found")
    session.delete(edge)
    session.commit()
    return Response(status_code=204)
