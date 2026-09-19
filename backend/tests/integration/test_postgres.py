from collections.abc import Iterator

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect
from sqlmodel import Session, SQLModel, text

from devin_flow import db, seed
from devin_flow.config import get_settings

pytestmark = pytest.mark.docker


def test_postgres_major_version(session: Session) -> None:
    version = session.scalar(text("show server_version"))
    assert version.startswith("18.")


def test_migrations_match_models(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, SQLModel.metadata) == []


def test_item_table_is_dropped(postgres_engine: Engine) -> None:
    assert inspect(postgres_engine).get_table_names() == ["alembic_version"]


def test_seeded_session_is_empty_canvas(seeded_session: Session) -> None:
    assert inspect(seeded_session.connection()).get_table_names() == ["alembic_version"]


def test_seed_twice_is_idempotent(seeded_session: Session) -> None:
    seed.seed(seeded_session)
    assert inspect(seeded_session.connection()).get_table_names() == ["alembic_version"]


def test_tests_are_isolated(session: Session) -> None:
    # a temp table created here is rolled back with the test transaction
    session.exec(text("create table scratch (id int)"))  # type: ignore[call-overload]
    assert "scratch" in inspect(session.connection()).get_table_names()


def test_previous_test_scratch_table_is_gone(session: Session) -> None:
    assert "scratch" not in inspect(session.connection()).get_table_names()


@pytest.fixture
def configured_for_container(
    monkeypatch: pytest.MonkeyPatch, postgres_url: str
) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    yield
    db.get_engine().dispose()
    get_settings.cache_clear()
    db.get_engine.cache_clear()


@pytest.mark.usefixtures("configured_for_container")
def test_get_session_connects_to_configured_database() -> None:
    session = next(db.get_session())
    assert session.scalar(text("select 1")) == 1
