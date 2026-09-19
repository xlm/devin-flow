from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from testcontainers.community.postgres import PostgresContainer

import devin_flow.models  # noqa: F401  (populates SQLModel.metadata)
from devin_flow.app import create_app
from devin_flow.config import get_settings
from devin_flow.db import get_session
from devin_flow.devin import get_devin_client
from devin_flow.seed import seed

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


@pytest.fixture(autouse=True)
def devin_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    # live tests use the real credentials from the environment
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("DEVIN_API_TOKEN", "test-token")
        monkeypatch.setenv("DEVIN_ORG_ID", "org-test")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()
    get_devin_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_devin_client.cache_clear()


def make_client(session: Session, static_dir: Path) -> TestClient:
    app = create_app(static_dir=static_dir)
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


# ---- docker-free path: in-memory sqlite, one fresh database per test ----


@pytest.fixture
def unit_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def unit_session(unit_engine: Engine) -> Iterator[Session]:
    with Session(unit_engine) as session:
        yield session


@pytest.fixture
def unit_client(unit_session: Session, tmp_path: Path) -> TestClient:
    return make_client(unit_session, tmp_path)


# ---- docker path: Postgres 18 via testcontainers, schema from alembic ----
# every fixture below needs a Docker daemon; mark tests using them with
# @pytest.mark.docker (or module-level pytestmark) so `-m "not docker"` skips them


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:18", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def postgres_engine(postgres_url: str) -> Iterator[Engine]:
    engine = create_engine(postgres_url)
    config = Config(ALEMBIC_INI)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(postgres_engine: Engine) -> Iterator[Session]:
    # outer transaction is rolled back after each test; session.commit() only
    # releases a savepoint, so tests stay isolated without truncating tables
    with postgres_engine.connect() as connection, connection.begin() as transaction:
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def seeded_session(session: Session) -> Session:
    seed(session)
    return session


@pytest.fixture
def client(session: Session, tmp_path: Path) -> TestClient:
    return make_client(session, tmp_path)
