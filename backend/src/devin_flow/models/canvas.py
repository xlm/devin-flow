from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, text
from sqlmodel import Field, SQLModel

NodeKind = Literal["trigger", "action", "outcome"]
EventAction = Literal["opened", "closed"]
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
    event_action: EventAction | None = Field(
        default=None, sa_type=cast("type[Any]", String())
    )
    repository_full_name: str | None = None


class ActionNode(NodeBase, table=True):
    __tablename__ = "action_node"
    name: str = ""
    playbook_id: str | None = None
    extra_instructions: str = ""
    automation_id: str | None = None
    sync_status: str = "unprovisioned"
    sync_error: str | None = None
    deleted_at: datetime | None = Field(default=None, sa_type=TIMESTAMP, nullable=True)


class OutcomeNode(NodeBase, table=True):
    __tablename__ = "outcome_node"


NODE_MODELS: dict[NodeKind, type[NodeBase]] = {
    "trigger": TriggerNode,
    "action": ActionNode,
    "outcome": OutcomeNode,
}


class Edge(SQLModel, table=True):
    __tablename__ = "edge"
    __table_args__ = (
        Index(
            "ux_edge_pair",
            "source_id",
            "target_id",
            unique=True,
        ),
        Index(
            "ux_edge_trigger_source",
            "source_id",
            unique=True,
            postgresql_where=text("source_kind = 'trigger'"),
            sqlite_where=text("source_kind = 'trigger'"),
        ),
        Index(
            "ux_edge_trigger_target",
            "target_id",
            unique=True,
            postgresql_where=text("source_kind = 'trigger'"),
            sqlite_where=text("source_kind = 'trigger'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_id: UUID = Field(index=True)
    source_kind: str
    target_id: UUID = Field(index=True)
    target_kind: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )
