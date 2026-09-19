from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

from devin_flow.models.canvas import TIMESTAMP

JSON_TYPE = cast("type[Any]", JSON())


class Invocation(SQLModel, table=True):
    __tablename__ = "invocation"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: str = Field(unique=True)
    automation_id: str = Field(index=True)
    action_node_id: UUID = Field(foreign_key="action_node.id", index=True)
    status: str
    title: str | None = None
    url: str | None = None
    pull_requests: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON_TYPE)
    structured_output: dict[str, Any] | None = Field(
        default=None, sa_type=JSON_TYPE, nullable=True
    )
    session_created_at: datetime = Field(sa_type=TIMESTAMP)
    session_updated_at: datetime = Field(sa_type=TIMESTAMP)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TIMESTAMP,
    )


class PollerState(SQLModel, table=True):
    """Single row (id = 1) remembering the last successful session poll."""

    __tablename__ = "poller_state"

    id: int = Field(default=1, primary_key=True)
    last_success_at: datetime | None = Field(
        default=None, sa_type=TIMESTAMP, nullable=True
    )
