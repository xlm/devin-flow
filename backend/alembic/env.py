from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine
from sqlmodel import SQLModel

import devin_flow.models  # noqa: F401  (populates SQLModel.metadata)
from devin_flow.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # tests pass an open connection via config.attributes to reuse their engine
    connection: Connection | None = config.attributes.get("connection")
    if connection is not None:
        run_migrations_with(connection)
        return
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        run_migrations_with(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
