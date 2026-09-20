import sys
from uuid import UUID

from sqlmodel import Session, select

from devin_flow import db
from devin_flow.automations import mark_pending
from devin_flow.canvas import (
    NodeRef,
    check_edge_kinds,
    check_edge_uniqueness,
)
from devin_flow.config import get_settings
from devin_flow.devin.client import DevinClient, Playbook, create_client
from devin_flow.models import ActionNode, Edge, OutcomeKind, OutcomeNode, TriggerNode

SEED_TRIGGER_ID = UUID("00000000-0000-0000-0000-000000000001")
SEED_PLAYBOOK_TITLE = "Issue triage"
SEED_ACTION_ID = UUID("00000000-0000-0000-0000-000000000002")
SEED_OUTCOME_IDS: dict[OutcomeKind, UUID] = {
    "pull_request": UUID("00000000-0000-0000-0000-000000000003"),
    "duplicate": UUID("00000000-0000-0000-0000-000000000004"),
    "not_reproducible": UUID("00000000-0000-0000-0000-000000000005"),
    "not_a_bug": UUID("00000000-0000-0000-0000-000000000006"),
}


def find_seed_playbook(client: DevinClient) -> Playbook | None:
    return next(
        (
            playbook
            for playbook in client.list_playbooks()
            if playbook.title == SEED_PLAYBOOK_TITLE
        ),
        None,
    )


def _add_edge(session: Session, source: NodeRef, target: NodeRef) -> bool:
    check_edge_kinds(source.kind, target.kind)
    existing = session.exec(select(Edge)).all()
    if any(
        edge.source_id == source.id and edge.target_id == target.id for edge in existing
    ):
        return False
    check_edge_uniqueness(existing, source, target)
    session.add(
        Edge(
            source_id=source.id,
            source_kind=source.kind,
            target_id=target.id,
            target_kind=target.kind,
        )
    )
    return True


def seed(
    session: Session, *, playbook_id: str | None, repository_full_name: str
) -> None:
    """Bring the database to its seeded state. Safe to run repeatedly or concurrently.

    When playbook_id is None, the Seed Flow is left unmanaged, neither created
    nor removed. Simulator reset requires a configured playbook.
    When a playbook is configured, the Seed Flow is normalized one row at a
    time. Existing rows are reused, preserving their identity, positions, and
    Action automation, while conflicting Trigger edges are removed.
    Caller work already pending on the session is committed so the seeded
    database is always in a consistent, committed state.
    """
    if playbook_id is not None:
        trigger = session.get(TriggerNode, SEED_TRIGGER_ID)
        if trigger is None:
            trigger = TriggerNode(
                id=SEED_TRIGGER_ID,
                position_x=100,
                position_y=0,
                event_action="opened",
                repository_full_name=repository_full_name,
            )
            session.add(trigger)
            trigger_changed = True
        else:
            trigger_changed = (
                trigger.event_action != "opened"
                or trigger.repository_full_name != repository_full_name
            )
            trigger.event_action = "opened"
            trigger.repository_full_name = repository_full_name
            session.add(trigger)
        action = session.get(ActionNode, SEED_ACTION_ID)
        if action is None:
            action = ActionNode(
                id=SEED_ACTION_ID,
                position_x=450,
                position_y=0,
                name="Seed: Issue triage",
                playbook_id=playbook_id,
                enabled=True,
                sync_status="pending",
            )
            session.add(action)
            action_changed = True
        else:
            action_changed = any(
                (
                    action.name != "Seed: Issue triage",
                    action.playbook_id != playbook_id,
                    action.prompt != "",
                    not action.enabled,
                    action.archived_at is not None,
                )
            )
            action.name = "Seed: Issue triage"
            action.playbook_id = playbook_id
            action.prompt = ""
            action.enabled = True
            action.archived_at = None
            session.add(action)
        for index, (kind, outcome_id) in enumerate(SEED_OUTCOME_IDS.items()):
            outcome = session.get(OutcomeNode, outcome_id)
            if outcome is None:
                session.add(
                    OutcomeNode(
                        id=outcome_id,
                        position_x=800,
                        position_y=index * 150,
                        kind=kind,
                    )
                )
            else:
                outcome.kind = kind
                session.add(outcome)
        if trigger_changed or action_changed:
            mark_pending(action)
            action.sync_error = None
            session.add(action)
        session.flush()
        seed_action = action
        edge_removed = False
        for edge in session.exec(
            select(Edge).where(
                Edge.source_id == SEED_TRIGGER_ID,
                Edge.target_id != SEED_ACTION_ID,
            )
        ).all():
            displaced_action = session.get(ActionNode, edge.target_id)
            if displaced_action is not None:
                mark_pending(displaced_action)
                session.add(displaced_action)
            session.delete(edge)
            edge_removed = True
        for edge in session.exec(
            select(Edge).where(
                Edge.source_id != SEED_TRIGGER_ID,
                Edge.target_id == SEED_ACTION_ID,
            )
        ).all():
            session.delete(edge)
            edge_removed = True
        if edge_removed:
            mark_pending(seed_action)
            session.add(seed_action)
        session.flush()
        trigger_edge_added = _add_edge(
            session,
            NodeRef(id=SEED_TRIGGER_ID, kind="trigger"),
            NodeRef(id=SEED_ACTION_ID, kind="action"),
        )
        if trigger_edge_added:
            mark_pending(seed_action)
            seed_action.sync_error = None
            session.add(seed_action)
        for outcome_id in SEED_OUTCOME_IDS.values():
            _add_edge(
                session,
                NodeRef(id=SEED_ACTION_ID, kind="action"),
                NodeRef(id=outcome_id, kind="outcome"),
            )
    session.commit()


def main() -> None:
    settings = get_settings()
    playbook = find_seed_playbook(create_client(settings))
    if playbook is None:
        print(
            "playbook 'Issue triage' not found in the Devin org, run uv run "
            "sync-playbooks; Seed Flow left unmanaged",
            file=sys.stderr,
        )
    with Session(db.get_engine()) as session:
        seed(
            session,
            playbook_id=playbook.playbook_id if playbook is not None else None,
            repository_full_name=settings.seed_repository_full_name,
        )


if __name__ == "__main__":
    main()
