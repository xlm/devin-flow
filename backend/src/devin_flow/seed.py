from uuid import UUID

from sqlmodel import Session, select

from devin_flow import db
from devin_flow.canvas import (
    NodeRef,
    check_edge_kinds,
    check_edge_uniqueness,
)
from devin_flow.config import get_settings
from devin_flow.models import ActionNode, Edge, OutcomeKind, OutcomeNode, TriggerNode

SEED_TRIGGER_ID = UUID("00000000-0000-0000-0000-000000000001")
SEED_ACTION_ID = UUID("00000000-0000-0000-0000-000000000002")
SEED_OUTCOME_IDS: dict[OutcomeKind, UUID] = {
    "pull_request": UUID("00000000-0000-0000-0000-000000000003"),
    "duplicate": UUID("00000000-0000-0000-0000-000000000004"),
    "not_reproducible": UUID("00000000-0000-0000-0000-000000000005"),
    "not_a_bug": UUID("00000000-0000-0000-0000-000000000006"),
}


def _add_edge(session: Session, source: NodeRef, target: NodeRef) -> None:
    check_edge_kinds(source.kind, target.kind)
    existing = session.exec(select(Edge)).all()
    if any(
        edge.source_id == source.id and edge.target_id == target.id for edge in existing
    ):
        return
    check_edge_uniqueness(existing, source, target)
    session.add(
        Edge(
            source_id=source.id,
            source_kind=source.kind,
            target_id=target.id,
            target_kind=target.kind,
        )
    )


def seed(
    session: Session, *, playbook_id: str | None, repository_full_name: str
) -> None:
    """Bring the database to its seeded state. Safe to run repeatedly or concurrently.

    When a playbook is configured, the Seed Flow is inserted one missing row at
    a time. Existing rows are reused, with a changed Trigger repository or a
    tombstoned Action restored without changing the Action automation.
    Caller work already pending on the session is committed so the seeded
    database is always in a consistent, committed state.
    """
    if playbook_id is not None:
        trigger = session.get(TriggerNode, SEED_TRIGGER_ID)
        trigger_changed = False
        if trigger is None:
            trigger = TriggerNode(
                id=SEED_TRIGGER_ID,
                position_x=100,
                position_y=0,
                event_action="opened",
                repository_full_name=repository_full_name,
            )
            session.add(trigger)
        elif trigger.repository_full_name != repository_full_name:
            trigger.repository_full_name = repository_full_name
            session.add(trigger)
            trigger_changed = True
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
        else:
            if action.deleted_at is not None:
                action.deleted_at = None
                action.enabled = True
                action.sync_status = "pending"
                action.sync_error = None
            if trigger_changed or action.playbook_id != playbook_id:
                action.playbook_id = playbook_id
                action.sync_status = "pending"
            session.add(action)
        for index, (kind, outcome_id) in enumerate(SEED_OUTCOME_IDS.items()):
            if session.get(OutcomeNode, outcome_id) is None:
                session.add(
                    OutcomeNode(
                        id=outcome_id,
                        position_x=800,
                        position_y=index * 150,
                        kind=kind,
                    )
                )
        session.flush()
        _add_edge(
            session,
            NodeRef(id=SEED_TRIGGER_ID, kind="trigger"),
            NodeRef(id=SEED_ACTION_ID, kind="action"),
        )
        for outcome_id in SEED_OUTCOME_IDS.values():
            _add_edge(
                session,
                NodeRef(id=SEED_ACTION_ID, kind="action"),
                NodeRef(id=outcome_id, kind="outcome"),
            )
    session.commit()


def main() -> None:
    settings = get_settings()
    with Session(db.get_engine()) as session:
        seed(
            session,
            playbook_id=settings.seed_playbook_id,
            repository_full_name=settings.seed_repository_full_name,
        )


if __name__ == "__main__":
    main()
