from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select, text

from devin_flow import db, seed
from devin_flow.models import ActionNode, Edge, OutcomeNode, TriggerNode


def canvas_counts(session: Session) -> list[int]:
    return [
        session.connection().execute(text(f"select count(*) from {table}")).scalar_one()
        for table in ("trigger_node", "action_node", "outcome_node", "edge")
    ]


def test_seeded_session_is_empty_canvas(unit_session: Session) -> None:
    seed.seed(unit_session, playbook_id=None, repository_full_name="xlm/superset")
    assert canvas_counts(unit_session) == [0, 0, 0, 0]


def test_seed_is_idempotent(unit_session: Session) -> None:
    seed.seed(unit_session, playbook_id=None, repository_full_name="xlm/superset")
    seed.seed(unit_session, playbook_id=None, repository_full_name="xlm/superset")
    assert canvas_counts(unit_session) == [0, 0, 0, 0]


def test_main_seeds_configured_engine(
    monkeypatch: pytest.MonkeyPatch, unit_engine: Engine
) -> None:
    monkeypatch.setattr(db, "get_engine", lambda: unit_engine)
    seed.main()
    with Session(unit_engine) as session:
        assert canvas_counts(session) == [0, 0, 0, 0]


def test_seed_inserts_seed_flow_when_playbook_is_configured(
    unit_session: Session,
) -> None:
    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )

    assert canvas_counts(unit_session) == [1, 1, 4, 5]
    action = unit_session.get(ActionNode, seed.SEED_ACTION_ID)
    assert action is not None
    assert action.playbook_id == "playbook-1"
    assert action.sync_status == "pending"
    trigger = unit_session.get(TriggerNode, seed.SEED_TRIGGER_ID)
    assert trigger is not None
    assert str(trigger.event_action) == "opened"
    assert len(unit_session.exec(select(Edge)).all()) == 5


def test_seed_is_idempotent_and_preserves_action_automation(
    unit_session: Session,
) -> None:
    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )
    action = unit_session.get(ActionNode, seed.SEED_ACTION_ID)
    assert action is not None
    action.automation_id = "automation-1"
    action.sync_status = "disabled"
    unit_session.add(action)
    unit_session.commit()

    seed.seed(
        unit_session,
        playbook_id="playbook-2",
        repository_full_name="other/repository",
    )

    action = unit_session.get(ActionNode, seed.SEED_ACTION_ID)
    assert action is not None
    assert action.playbook_id == "playbook-2"
    assert action.automation_id == "automation-1"
    assert action.sync_status == "pending"
    trigger = unit_session.get(TriggerNode, seed.SEED_TRIGGER_ID)
    assert trigger is not None
    assert trigger.repository_full_name == "other/repository"


def test_seed_restores_tombstoned_action(unit_session: Session) -> None:
    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )
    action = unit_session.get(ActionNode, seed.SEED_ACTION_ID)
    assert action is not None
    action.automation_id = "automation-1"
    setattr(action, seed._DELETED_AT_FIELD, datetime.now(UTC))
    action.enabled = False
    action.sync_status = "disabled"
    action.sync_error = "disabled"
    unit_session.add(action)
    unit_session.commit()

    seed.seed(
        unit_session,
        playbook_id="playbook-2",
        repository_full_name="xlm/superset",
    )

    action = unit_session.get(ActionNode, seed.SEED_ACTION_ID)
    assert action is not None
    assert getattr(action, "deleted_at", None) is None
    assert action.enabled
    assert action.sync_status == "pending"
    assert action.sync_error is None
    assert action.automation_id == "automation-1"


def test_seed_normalizes_existing_rows(unit_session: Session) -> None:
    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )
    trigger = unit_session.get(TriggerNode, seed.SEED_TRIGGER_ID)
    action = unit_session.get(ActionNode, seed.SEED_ACTION_ID)
    outcome = unit_session.get(OutcomeNode, seed.SEED_OUTCOME_IDS["pull_request"])
    assert trigger is not None
    assert action is not None
    assert outcome is not None
    trigger.event_action = "closed"
    trigger.repository_full_name = "other/repository"
    action.name = "Wrong name"
    action.playbook_id = "playbook-old"
    action.prompt = "Wrong prompt"
    action.enabled = False
    setattr(action, seed._DELETED_AT_FIELD, datetime.now(UTC))
    action.automation_id = "automation-1"
    action.sync_status = "disabled"
    action.sync_error = "old error"
    outcome.kind = "not_a_bug"
    unit_session.add_all([trigger, action, outcome])
    unit_session.commit()

    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )

    unit_session.refresh(trigger)
    unit_session.refresh(action)
    unit_session.refresh(outcome)
    assert str(trigger.event_action) == "opened"
    assert trigger.repository_full_name == "xlm/superset"
    assert action.name == "Seed: Issue triage"
    assert action.playbook_id == "playbook-1"
    assert action.prompt == ""
    assert action.enabled
    assert getattr(action, "deleted_at", None) is None
    assert action.sync_status == "pending"
    assert action.sync_error is None
    assert action.automation_id == "automation-1"
    assert outcome.kind == "pull_request"

    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )
    unit_session.refresh(action)
    assert action.sync_status == "pending"


def test_seed_removes_conflicting_trigger_edge(unit_session: Session) -> None:
    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )
    unit_session.exec(delete(Edge).where(col(Edge.source_id) == seed.SEED_TRIGGER_ID))
    conflicting = ActionNode(
        name="Other action",
        position_x=450,
        position_y=0,
        sync_status="disabled",
    )
    unit_session.add(conflicting)
    unit_session.flush()
    unit_session.add(
        Edge(
            source_id=seed.SEED_TRIGGER_ID,
            source_kind="trigger",
            target_id=conflicting.id,
            target_kind="action",
        )
    )
    unit_session.commit()

    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )

    edge = unit_session.exec(
        select(Edge).where(
            Edge.source_id == seed.SEED_TRIGGER_ID,
            Edge.target_id == conflicting.id,
        )
    ).first()
    assert edge is None
    assert conflicting.sync_status == "pending"
    assert (
        unit_session.exec(
            select(Edge).where(
                Edge.source_id == seed.SEED_TRIGGER_ID,
                Edge.target_id == seed.SEED_ACTION_ID,
            )
        ).first()
        is not None
    )


def test_seed_removes_foreign_trigger_edge_to_action(unit_session: Session) -> None:
    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )
    action = unit_session.get(ActionNode, seed.SEED_ACTION_ID)
    assert action is not None
    action.sync_status = "disabled"
    unit_session.exec(
        delete(Edge).where(
            col(Edge.source_id) == seed.SEED_TRIGGER_ID,
            col(Edge.target_id) == seed.SEED_ACTION_ID,
        )
    )
    foreign_trigger = TriggerNode(
        event_action="opened",
        repository_full_name="other/repository",
        position_x=100,
        position_y=150,
    )
    unit_session.add(foreign_trigger)
    unit_session.flush()
    unit_session.add(
        Edge(
            source_id=foreign_trigger.id,
            source_kind="trigger",
            target_id=seed.SEED_ACTION_ID,
            target_kind="action",
        )
    )
    unit_session.commit()

    seed.seed(
        unit_session,
        playbook_id="playbook-1",
        repository_full_name="xlm/superset",
    )

    assert (
        unit_session.exec(
            select(Edge).where(
                col(Edge.source_id) == foreign_trigger.id,
                col(Edge.target_id) == seed.SEED_ACTION_ID,
            )
        ).first()
        is None
    )
    assert action.sync_status == "pending"


def test_seed_playbook_none_inserts_nothing(unit_session: Session) -> None:
    seed.seed(
        unit_session,
        playbook_id=None,
        repository_full_name="xlm/superset",
    )
    assert unit_session.exec(select(OutcomeNode)).all() == []
