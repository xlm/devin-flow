from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select, text

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
    assert trigger.event_action == "opened"
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
    action.deleted_at = datetime.now(UTC)
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
    assert action.deleted_at is None
    assert action.enabled
    assert action.sync_status == "pending"
    assert action.sync_error is None
    assert action.automation_id == "automation-1"


def test_seed_playbook_none_inserts_nothing(unit_session: Session) -> None:
    seed.seed(
        unit_session,
        playbook_id=None,
        repository_full_name="xlm/superset",
    )
    assert unit_session.exec(select(OutcomeNode)).all() == []
