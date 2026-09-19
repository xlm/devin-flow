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


def test_canvas_tables_exist(postgres_engine: Engine) -> None:
    inspector = inspect(postgres_engine)
    assert sorted(inspector.get_table_names()) == [
        "action_node",
        "alembic_version",
        "edge",
        "outcome_node",
        "trigger_node",
    ]
    action_columns = {column["name"] for column in inspector.get_columns("action_node")}
    edge_columns = {column["name"] for column in inspector.get_columns("edge")}
    assert {
        "automation_id",
        "sync_status",
        "sync_error",
        "deleted_at",
    } <= action_columns
    assert (
        not {
            "automation_id",
            "sync_status",
            "sync_error",
            "deleted_at",
        }
        & edge_columns
    )
    assert {index["name"] for index in inspector.get_indexes("edge")} >= {
        "ux_edge_pair",
        "ux_edge_trigger_source",
        "ux_edge_trigger_target",
    }


def test_seeded_session_is_empty_canvas(seeded_session: Session) -> None:
    assert all(
        seeded_session.connection()
        .execute(text(f"select count(*) from {table}"))
        .scalar_one()
        == 0
        for table in ("trigger_node", "action_node", "outcome_node", "edge")
    )


def test_seed_twice_is_idempotent(seeded_session: Session) -> None:
    seed.seed(seeded_session)
    assert all(
        seeded_session.connection()
        .execute(text(f"select count(*) from {table}"))
        .scalar_one()
        == 0
        for table in ("trigger_node", "action_node", "outcome_node", "edge")
    )


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
