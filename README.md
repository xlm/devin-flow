# devin-flow

Monorepo with a FastAPI backend and a Vue 3 (Vite, Tailwind, shadcn-vue)
frontend. The backend serves the built SPA in production.

## Prerequisites

- uv (Python 3.13 is pinned via `.python-version`)
- Node 24 + pnpm (pinned via `.node-version` and `packageManager`)
- Docker (Postgres 18 for local dev and for the full test suite)

## Setup

```sh
uv sync
pnpm install
uv run pre-commit install
```

## Development

```sh
# postgres 18 on :5432 (user/password/db: devin/devin/devin_flow)
docker compose up -d db

# apply migrations, then seed example rows (idempotent, safe to re-run)
uv run alembic -c backend/alembic.ini upgrade head
uv run seed

# backend on :8000
uv run fastapi dev backend/src/devin_flow/main.py

# frontend on :5173, proxies /api to :8000
pnpm dev
```

The backend reads `DATABASE_URL` (default
`postgresql+psycopg://devin:devin@localhost:5432/devin_flow`) and
`STATIC_DIR` from the environment or a `.env` file in the working
directory, see `backend/src/devin_flow/config.py`. `.env.example` lists
them with their defaults; copy it to `.env` to override locally.

### Database

SQLModel (synchronous, psycopg 3) on Postgres 18. Table models live in
`backend/src/devin_flow/models/`, and the package `__init__` must import
every model so `SQLModel.metadata` is complete for Alembic. Schema
changes go through Alembic, never `create_all`:

```sh
uv run alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini downgrade -1
```

Seed data is defined in `backend/src/devin_flow/seed.py`. `seed(session)`
only inserts rows that are missing, so `uv run seed` (locally) or
`docker compose run --rm seed` (against the compose database) can run
any number of times. Test fixtures call the same function.

## Checks

```sh
# backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest            # full suite, needs Docker, fails under 100% coverage
uv run pytest -m "not docker" --no-cov   # fast loop, no Docker, no coverage gate

# frontend
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test                # fast, no coverage
pnpm test:coverage       # what CI runs, fails under 100%
pnpm build

# everything (pre-commit)
uv run pre-commit run --all-files
```

## API types

The frontend gets its API types from the backend's OpenAPI schema.
`pnpm generate:api` runs `python -m devin_flow.openapi` to dump the
schema to `frontend/openapi.json`, then `openapi-typescript` turns it
into `frontend/src/api/schema.d.ts`, which `src/api/client.ts` consumes
via `openapi-fetch`. Both generated files are committed; CI regenerates
them and fails on drift, so re-run `pnpm generate:api` whenever backend
routes or response models change.

### Tests and Docker

Tests that need a real database are marked `@pytest.mark.docker` and run
against a throwaway `postgres:18` container started by testcontainers,
migrated with `alembic upgrade head`. Each test runs inside a transaction
that is rolled back afterwards. The plain `uv run pytest` runs everything
and enforces 100% coverage, which is what CI does (`ubuntu-latest`
provides Docker, so no extra services are configured). Any environment
expected to pass the coverage gate, CI or a Devin session, needs a
running Docker daemon.

`uv run pytest -m "not docker" --no-cov` skips the container-backed tests
and the coverage gate for fast iteration without Docker. It is not
coverage-complete on its own, only the full run is.

## Docker

```sh
docker compose up --build          # postgres 18, migrate, app on :8000
docker compose run --rm seed       # seed the compose database (idempotent)
docker compose down -v             # also drops the pgdata volume
```

The image builds `frontend/dist`, installs the Python deps with
`uv sync --frozen --no-dev --no-editable`, and its entrypoint runs
`alembic upgrade head` against `DATABASE_URL` before starting uvicorn on
port 8000. To run the image alone:

```sh
docker build -t devin-flow .
docker run -p 8000:8000 -e DATABASE_URL=postgresql+psycopg://... devin-flow
```

## Layout

```
backend/    FastAPI package (src layout), tests in backend/tests,
            alembic migrations in backend/alembic
frontend/   Vite + Vue 3 + Tailwind + shadcn-vue app
pyproject   uv workspace root, shared ruff/mypy/pytest config
```
