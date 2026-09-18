from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import devin_flow.models  # noqa: F401  (populates SQLModel.metadata)
from devin_flow.app import create_app
from devin_flow.db import get_session


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
