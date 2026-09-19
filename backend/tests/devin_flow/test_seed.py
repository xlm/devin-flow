import pytest
from sqlalchemy import Engine, inspect
from sqlmodel import Session

from devin_flow import db, seed


def table_names(session: Session) -> list[str]:
    return inspect(session.connection()).get_table_names()


def test_seed_leaves_empty_database_empty(unit_session: Session) -> None:
    seed.seed(unit_session)
    assert table_names(unit_session) == []


def test_seed_is_idempotent(unit_session: Session) -> None:
    seed.seed(unit_session)
    seed.seed(unit_session)
    assert table_names(unit_session) == []


def test_main_seeds_configured_engine(
    monkeypatch: pytest.MonkeyPatch, unit_engine: Engine
) -> None:
    monkeypatch.setattr(db, "get_engine", lambda: unit_engine)
    seed.main()
    with Session(unit_engine) as session:
        assert table_names(session) == []
