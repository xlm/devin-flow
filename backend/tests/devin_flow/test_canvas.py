from typing import cast
from uuid import uuid4

import pytest

from devin_flow.canvas import (
    ConnectError,
    NodeRef,
    check_edge_kinds,
    check_edge_uniqueness,
)
from devin_flow.models import Edge, NodeKind

VALID_KINDS = {
    ("trigger", "action"),
    ("action", "outcome"),
}
ALL_KINDS = ("trigger", "action", "outcome")


@pytest.mark.parametrize(
    ("source_kind", "target_kind"),
    [(source, target) for source in ALL_KINDS for target in ALL_KINDS],
)
def test_check_edge_kinds_matrix(source_kind: str, target_kind: str) -> None:
    if (source_kind, target_kind) in VALID_KINDS:
        check_edge_kinds(source_kind, target_kind)
    else:
        with pytest.raises(ConnectError, match="edges must connect") as error:
            check_edge_kinds(source_kind, target_kind)
        assert error.value.status_code == 409


def node_ref(kind: str) -> NodeRef:
    return NodeRef(id=uuid4(), kind=cast(NodeKind, kind))


def edge(source: NodeRef, target: NodeRef) -> Edge:
    return Edge(
        source_id=source.id,
        source_kind=source.kind,
        target_id=target.id,
        target_kind=target.kind,
    )


def test_check_edge_uniqueness_rejects_duplicate() -> None:
    source = node_ref("trigger")
    target = node_ref("action")
    with pytest.raises(ConnectError, match="already connected"):
        check_edge_uniqueness([edge(source, target)], source, target)


def test_check_edge_uniqueness_rejects_second_trigger_edge() -> None:
    source = node_ref("trigger")
    target = node_ref("action")
    other_target = node_ref("action")
    with pytest.raises(ConnectError, match="one outgoing"):
        check_edge_uniqueness([edge(source, target)], source, other_target)


def test_check_edge_uniqueness_rejects_second_trigger_to_action() -> None:
    source = node_ref("trigger")
    other_source = node_ref("trigger")
    target = node_ref("action")
    with pytest.raises(ConnectError, match="one incoming"):
        check_edge_uniqueness([edge(other_source, target)], source, target)


def test_check_edge_uniqueness_allows_multiple_outcomes() -> None:
    source = node_ref("action")
    first_target = node_ref("outcome")
    second_target = node_ref("outcome")
    check_edge_uniqueness([edge(source, first_target)], source, second_target)


def test_check_edge_uniqueness_allows_trigger_after_action_edge() -> None:
    trigger = node_ref("trigger")
    action = node_ref("action")
    outcome = node_ref("outcome")
    check_edge_uniqueness([edge(action, outcome)], trigger, action)
