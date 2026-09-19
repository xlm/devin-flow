from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

NodeKind = Literal["trigger", "action", "outcome"]
TIMESTAMP = cast(
    "type[Any]", DateTime(timezone=True)
)  # sqlmodel types sa_type as a class but SQLAlchemy accepts a configured instance


class NodeBase(SQLModel):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    position_x: float
    position_y: float
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )


class TriggerNode(NodeBase, table=True):
    __tablename__ = "trigger_node"


class ActionNode(NodeBase, table=True):
    __tablename__ = "action_node"


class OutcomeNode(NodeBase, table=True):
    __tablename__ = "outcome_node"


NODE_MODELS: dict[NodeKind, type[NodeBase]] = {
    "trigger": TriggerNode,
    "action": ActionNode,
    "outcome": OutcomeNode,
}


class Edge(SQLModel, table=True):
    __tablename__ = "edge"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_id: UUID = Field(index=True)
    source_kind: str
    target_id: UUID = Field(index=True)
    target_kind: str
    automation_id: str | None = None
    sync_status: str = "unprovisioned"
    sync_error: str | None = None
    deleted_at: datetime | None = Field(default=None, sa_type=TIMESTAMP, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )
