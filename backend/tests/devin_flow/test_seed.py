import pytest
from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import SessionTransaction
from sqlmodel import Session, select

from devin_flow import db, seed
from devin_flow.models import Item


def names(session: Session) -> list[str]:
    return list(session.exec(select(Item.name).order_by(Item.name)))


def test_seed_inserts_all_seed_items(unit_session: Session) -> None:
    seed.seed(unit_session)
    assert names(unit_session) == sorted(seed.SEED_ITEM_NAMES)


def test_seed_is_idempotent(unit_session: Session) -> None:
    unit_session.add(Item(name="beta"))
    unit_session.commit()
    seed.seed(unit_session)
    seed.seed(unit_session)
    assert names(unit_session) == sorted(seed.SEED_ITEM_NAMES)


def test_main_seeds_configured_engine(
    monkeypatch: pytest.MonkeyPatch, unit_engine: Engine
) -> None:
    monkeypatch.setattr(db, "get_engine", lambda: unit_engine)
    seed.main()
    with Session(unit_engine) as session:
        assert names(session) == sorted(seed.SEED_ITEM_NAMES)


def test_seed_retries_when_a_concurrent_seeder_wins(unit_session: Session) -> None:
    real_begin_nested = unit_session.begin_nested

    def rival_inserts_alpha_then_begin_nested() -> SessionTransaction:
        unit_session.begin_nested = real_begin_nested  # type: ignore[method-assign]
        unit_session.exec(insert(Item).values(name="alpha"))
        return real_begin_nested()

    unit_session.begin_nested = rival_inserts_alpha_then_begin_nested  # type: ignore[method-assign]
    seed.seed(unit_session)
    assert names(unit_session) == sorted(seed.SEED_ITEM_NAMES)


def test_seed_surfaces_callers_pending_failure(unit_session: Session) -> None:
    unit_session.add(Item(name="delta"))
    unit_session.commit()
    unit_session.add(Item(name="delta"))
    with pytest.raises(IntegrityError):
        seed.seed(unit_session)
