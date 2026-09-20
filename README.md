# devin-flow

Monorepo with a FastAPI backend and a Vue 3 (Vite, Tailwind, shadcn-vue)
frontend. The backend serves the built SPA in production.

## Prerequisites

- uv (Python 3.13 is pinned via `.python-version`)
- Node 24 + pnpm (pinned via `.node-version` and `packageManager`)
- Docker (Postgres 18 for local dev, the full test suite, and browser E2E)
- A Devin GitHub connection whose Automation scope is **All installed
  repos**. By default Devin Automations only fire on private
  repositories, so a Flow whose Trigger points at a public repo would
  never run. A Devin admin sets this once per connection: Settings ->
  Connections -> GitHub, open the connection's menu, set **Automation
  scope** to **All installed repos**. Public-repo triggers carry a higher
  prompt-injection risk, so keep Trigger conditions narrow. See
  https://docs.devin.ai/product-guides/automations#github-triggers.

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

# apply migrations, then seed (idempotent, safe to re-run)
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
`DEVIN_API_TOKEN` is a required server-side service token for the
`/api/devin/*` proxy and is never sent to the frontend. `DEVIN_ORG_ID` is also
required and selects the organization from Settings -> Service Users.
`DEVIN_API_BASE_URL` configures the Devin API v3 endpoint. The backend refuses
to start when either required Devin variable is missing or empty. Live Devin
tests are opt-in with `uv run pytest -m live` and require both Devin
environment variables.

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

Seed data is defined in `backend/src/devin_flow/seed.py`. `seed(session, *,
playbook_id, repository_full_name)` is idempotent, so `uv run seed` (locally) or `docker compose run --rm seed`
(against the compose database) can run any number of times. When
the `Issue triage` Playbook is found by title, it creates the Seed Flow: an
issue-opened Trigger for `SEED_REPOSITORY_FULL_NAME`, the `Seed: Issue triage`
Action, and one Outcome node for each Outcome kind. Existing Seed Flow rows are
reused without changing their Automation. Run `uv run sync-playbooks` first to
sync the Playbook. If it is absent, `uv run seed` leaves the Canvas unmanaged.
Test fixtures pass no playbook and call the same function.

## Issue simulator

The Issue simulator resets the Target repository to the Scenario's pinned
Baseline plus its Poisoned bugs, then files the ordered Simulated issues across
the configured run window so a running Seed Flow can be watched end to end.

Before running it, ensure that:

- `gh auth status` uses an admin login on `xlm/superset`, for example
  `GH_TOKEN` set to a fine-grained PAT with Administration, Contents, Issues,
  and Pull requests read/write permissions on the Target repository.
- Git can push with the same credentials. Run `gh auth setup-git`, or configure
  an equivalent Git credential helper. The simulator also uses `gh`'s Git
  credential helper automatically when `GH_TOKEN` is set.
- The `Issue triage` Playbook is available by title. Run
  `uv run sync-playbooks` before resetting so its structured output schema is
  available.
- `SEED_REPOSITORY_FULL_NAME` is set to the Target repository. Reset rejects
  scenarios for any other repository.
- The Devin GitHub connection's Automation scope is set to **All installed
  repos**, because the Target repository is public.

```sh
uv run simulate-issues reset   # destructively recreate the Target start state
uv run simulate-issues run     # file the Scenario's Simulated issues
uv run simulate-issues report  # wait for terminal Invocations and compare Outcomes
```

Reset is destructive: it wipes issues, pull requests, and non-default branches,
terminates non-terminal sessions, clears simulator state, and force-pushes
`master`. The default work directory is
`~/.cache/devin-flow/superset`; the Git checkout is in its `repo/` child,
while `.simulate-state.json` and `.simulate-run.json` stay directly in the
work directory. `DATABASE_URL` used by reset and `--flow-url` used by report
must point to the same devin-flow deployment. Reset also ensures the triage
labels used by the Playbook exist.

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
pnpm e2e:install         # one-time Chromium install
pnpm e2e                 # browser suite against throwaway postgres:18 and stub Devin
                        # needs Docker and free ports 8000 and 5174
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

The browser E2E suite under `frontend/e2e` starts its own throwaway
`postgres:18` container, a local Devin API stub at
`frontend/e2e/harness/stub-devin.ts`, the backend, and Vite. It strips every
`DEVIN_*` variable and never reaches the real Devin API. CI runs it in the
`e2e` job. Failures upload `playwright-report` and `test-results` artifacts.

## Docker

```sh
docker compose up --build          # postgres 18, migrate, app on :8000
docker compose run --rm seed       # seed the compose database (idempotent)
docker compose down -v             # also drops the pgdata volume
```

Compose passes `DEVIN_API_TOKEN`, `DEVIN_ORG_ID` and `DEVIN_API_BASE_URL`
through from the root `.env` (or the shell). `migrate`, `app` and `seed`
refuse to start without the two credentials, `db` alone does not need them.

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
