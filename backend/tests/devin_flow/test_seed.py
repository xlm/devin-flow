import pytest
from sqlalchemy import Engine
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
