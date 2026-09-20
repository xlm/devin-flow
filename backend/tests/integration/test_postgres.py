import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, bindparam, inspect
from sqlmodel import Session, SQLModel, text

from devin_flow import db, seed
from devin_flow.config import get_settings
from devin_flow.outcomes import derive_outcome_kinds

pytestmark = pytest.mark.docker

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def load_migration(revision: str) -> Any:
    path = next((BACKEND_DIR / "alembic" / "versions").glob(f"{revision}_*.py"))
    spec = importlib.util.spec_from_file_location(revision, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        "invocation",
        "invocation_outcome",
        "outcome_node",
        "poller_state",
        "trigger_node",
    ]
    action_columns = {column["name"] for column in inspector.get_columns("action_node")}
    edge_columns = {column["name"] for column in inspector.get_columns("edge")}
    assert {
        "automation_id",
        "sync_status",
        "sync_error",
        "archived_at",
    } <= action_columns
    assert (
        not {
            "automation_id",
            "sync_status",
            "sync_error",
            "archived_at",
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


def test_invocation_outcome_backfill(postgres_engine: Engine) -> None:
    config = Config(ALEMBIC_INI)
    action_id = uuid4()
    first_id, second_id = uuid4(), uuid4()
    with postgres_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "a1f3e5c7d9b2")
    try:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "insert into action_node "
                    "(id, position_x, position_y, name, prompt, enabled, "
                    "sync_status, created_at, updated_at) "
                    "values (:id, 0, 0, '', '', false, 'unprovisioned', "
                    "now(), now())"
                ),
                {"id": action_id},
            )
            connection.execute(
                text(
                    "insert into invocation "
                    "(id, session_id, automation_id, action_node_id, status, "
                    "pull_requests, structured_output, session_created_at, "
                    "session_updated_at, created_at, updated_at) "
                    "values (:id, :session_id, 'auto-1', :action_id, 'exit', "
                    "cast(:pull_requests as json), "
                    "cast(:structured_output as json), now(), now(), now(), "
                    "now())"
                ),
                [
                    {
                        "id": first_id,
                        "session_id": "s-1",
                        "action_id": action_id,
                        "pull_requests": '[{"pr_url": "https://gh.example/1"}]',
                        "structured_output": '{"outcome": "duplicate"}',
                    },
                    {
                        "id": second_id,
                        "session_id": "s-2",
                        "action_id": action_id,
                        "pull_requests": "[]",
                        "structured_output": None,
                    },
                ],
            )
        with postgres_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with postgres_engine.connect() as connection:
            rows = {
                (invocation_id, kind)
                for invocation_id, kind in connection.execute(
                    text("select invocation_id, kind from invocation_outcome")
                )
            }
        assert rows == {
            (first_id, "duplicate"),
            (first_id, "pull_request"),
        }
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                text("delete from invocation where action_node_id = :id"),
                {"id": action_id},
            )
            connection.execute(
                text("delete from action_node where id = :id"),
                {"id": action_id},
            )


def test_offline_backfill_sql_matches_python(postgres_engine: Engine) -> None:
    module = load_migration("f7a8b9c0d1e2")
    cases: list[tuple[list[dict[str, Any]], dict[str, Any] | list[str] | None]] = [
        (
            [{"pr_url": "https://gh.example/1"}],
            {"outcome": "duplicate"},
        ),
        ([{"pr_url": "https://gh.example/2", "pr_state": "merged"}], None),
        ([], {"outcome": "not_a_bug"}),
        ([{"pr_url": ""}], {"outcome": "fixed"}),
        ([{"pr_url": 7}], None),
        ([], None),
        ([], ["x"]),
        (
            [
                {"pr_url": "https://gh.example/8"},
                {"pr_url": "https://gh.example/8"},
            ],
            None,
        ),
    ]
    ids = [uuid4() for _ in cases]
    action_id = uuid4()
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                text(
                    "insert into action_node "
                    "(id, position_x, position_y, name, prompt, enabled, "
                    "sync_status, created_at, updated_at) "
                    "values (:id, 0, 0, '', '', false, 'unprovisioned', "
                    "now(), now())"
                ),
                {"id": action_id},
            )
            connection.execute(
                text(
                    "insert into invocation "
                    "(id, session_id, automation_id, action_node_id, status, "
                    "pull_requests, structured_output, session_created_at, "
                    "session_updated_at, created_at, updated_at) "
                    "values (:id, :session_id, 'auto-1', :action_id, 'exit', "
                    "cast(:pull_requests as json), "
                    "cast(:structured_output as json), now(), now(), now(), "
                    "now())"
                ),
                [
                    {
                        "id": invocation_id,
                        "session_id": f"s-{index}",
                        "action_id": action_id,
                        "pull_requests": json.dumps(pull_requests),
                        "structured_output": (
                            json.dumps(structured_output)
                            if structured_output is not None
                            else None
                        ),
                    }
                    for index, (invocation_id, (pull_requests, structured_output)) in (
                        enumerate(zip(ids, cases, strict=True))
                    )
                ],
            )
            connection.execute(text(module.OFFLINE_BACKFILL_SQL))
            rows = {
                (invocation_id, kind)
                for invocation_id, kind in connection.execute(
                    text(
                        "select invocation_id, kind from invocation_outcome "
                        "where invocation_id in :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": ids},
                )
            }
            expected = {
                (invocation_id, kind)
                for invocation_id, (pull_requests, structured_output) in zip(
                    ids, cases, strict=True
                )
                for kind in derive_outcome_kinds(pull_requests, structured_output)
            }
            assert rows == expected
        finally:
            transaction.rollback()


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
