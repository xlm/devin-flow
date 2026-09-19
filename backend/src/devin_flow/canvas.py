from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel

from devin_flow.models.canvas import Edge, NodeKind

ALLOWED_EDGE_KINDS: frozenset[tuple[str, str]] = frozenset(
    {("trigger", "action"), ("action", "outcome")}
)


class ConnectError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class NodeRef(BaseModel):
    id: UUID
    kind: NodeKind


def check_edge_kinds(source_kind: str, target_kind: str) -> None:
    if (source_kind, target_kind) not in ALLOWED_EDGE_KINDS:
        raise ConnectError(
            422,
            "edges must connect a Trigger to an Action or an Action to an Outcome",
        )


def check_edge_uniqueness(
    existing: Sequence[Edge], source: NodeRef, target: NodeRef
) -> None:
    for edge in existing:
        if edge.source_id == source.id and edge.target_id == target.id:
            raise ConnectError(409, "these nodes are already connected")
        if source.kind == "trigger" and edge.source_id == source.id:
            raise ConnectError(409, "a Trigger can have only one outgoing edge")
        if (
            target.kind == "action"
            and edge.target_id == target.id
            and edge.source_kind == "trigger"
        ):
            raise ConnectError(409, "an Action can have only one incoming Trigger edge")
