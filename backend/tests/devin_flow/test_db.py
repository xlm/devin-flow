from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, text

from devin_flow import db
from devin_flow.config import get_settings


@pytest.fixture(autouse=True)
def clear_caches() -> Iterator[None]:
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    db.get_engine.cache_clear()


def test_get_engine_uses_settings_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    engine = db.get_engine()
    assert engine.url.render_as_string(hide_password=False) == (
        "postgresql+psycopg://u:p@db:5432/x"
    )
    assert db.get_engine() is engine


def test_get_session_yields_session_on_engine(
    monkeypatch: pytest.MonkeyPatch, unit_engine: Engine
) -> None:
    monkeypatch.setattr(db, "get_engine", lambda: unit_engine)
    sessions = list(db.get_session())
    assert len(sessions) == 1
    session = sessions[0]
    assert isinstance(session, Session)
    assert session.get_bind() is unit_engine


def test_get_session_closes_after_use(
    monkeypatch: pytest.MonkeyPatch, unit_engine: Engine
) -> None:
    monkeypatch.setattr(db, "get_engine", lambda: unit_engine)
    generator = db.get_session()
    session = next(generator)
    assert session.exec(text("select 1")).scalar() == 1  # type: ignore[call-overload]
    with pytest.raises(StopIteration):
        next(generator)
    assert not session.in_transaction()
