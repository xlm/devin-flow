import pytest
from sqlalchemy import Engine
from sqlmodel import Session, text

from devin_flow import db, seed


def canvas_counts(session: Session) -> list[int]:
    return [
        session.connection().execute(text(f"select count(*) from {table}")).scalar_one()
        for table in ("trigger_node", "action_node", "outcome_node", "edge")
    ]


def test_seeded_session_is_empty_canvas(unit_session: Session) -> None:
    seed.seed(unit_session)
    assert canvas_counts(unit_session) == [0, 0, 0, 0]


def test_seed_is_idempotent(unit_session: Session) -> None:
    seed.seed(unit_session)
    seed.seed(unit_session)
    assert canvas_counts(unit_session) == [0, 0, 0, 0]


def test_main_seeds_configured_engine(
    monkeypatch: pytest.MonkeyPatch, unit_engine: Engine
) -> None:
    monkeypatch.setattr(db, "get_engine", lambda: unit_engine)
    seed.main()
    with Session(unit_engine) as session:
        assert canvas_counts(session) == [0, 0, 0, 0]
