from collections.abc import Iterator

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, select, text

from devin_flow import db, seed
from devin_flow.config import get_settings
from devin_flow.models import Item

pytestmark = pytest.mark.docker


def test_postgres_major_version(session: Session) -> None:
    version = session.scalar(text("show server_version"))
    assert version.startswith("18.")


def test_migrations_match_models(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, SQLModel.metadata) == []


def test_items_endpoints(client: TestClient) -> None:
    assert client.get("/api/items").json() == []
    created = client.post("/api/items", json={"name": "widget"})
    assert created.status_code == 201
    assert client.get("/api/items").json() == [created.json()]
    assert client.post("/api/items", json={"name": "widget"}).status_code == 409


def test_seeded_session_has_seed_items(seeded_session: Session) -> None:
    stored = seeded_session.exec(select(Item.name).order_by(Item.name)).all()
    assert list(stored) == sorted(seed.SEED_ITEM_NAMES)


def test_seed_twice_does_not_duplicate(seeded_session: Session) -> None:
    seed.seed(seeded_session)
    assert len(seeded_session.exec(select(Item)).all()) == len(seed.SEED_ITEM_NAMES)


def test_tests_are_isolated(session: Session) -> None:
    # rows committed by the previous tests were rolled back with their transaction
    assert session.exec(select(Item)).all() == []


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
    assert session.exec(select(Item)).all() == []
