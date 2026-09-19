# AGENTS.md

## Layout

- `backend/` - Python package `devin_flow` (src layout). `main.py` is the
  ASGI entrypoint; the app factory lives in `app.py`, API routes in
  `api/` (under `/api`), and static file serving in `web/spa.py`. Serves
  `frontend/dist` when it exists (or `STATIC_DIR`). Unknown `/api/*`
  paths must stay 404.
  Settings (`DATABASE_URL`, `STATIC_DIR`, `DEVIN_API_TOKEN`, and
  `DEVIN_ORG_ID`, the latter two required) come from `config.py`
  (pydantic-settings, `.env` aware). `db.py` builds the sync SQLModel
  engine lazily and exposes the `get_session` dependency. Table models
  live in `models/` and must be imported from `models/__init__.py` so
  `SQLModel.metadata` is complete. `seed.py` holds the idempotent
  `seed(session)` used by `uv run seed` and by test fixtures.
  `playbooks.py` holds `uv run sync-playbooks`, which upserts the repo's
  `playbooks/` directory to Devin.
- `backend/alembic/` + `backend/alembic.ini` - migrations (target
  metadata is `SQLModel.metadata`, URL from `Settings`). Never
  `create_all` against Postgres; add a migration instead.
- `canvas.py` holds connect rules, `models/canvas.py` holds the node and edge
  tables, and `api/canvas.py` holds the Canvas routes.
- `backend/tests/` - pytest tests; test files mirror `src` under
  `tests/devin_flow/` (pytest runs with `--import-mode=importlib`).
  `conftest.py` provides `unit_session`/`unit_client` (in-memory sqlite,
  no Docker) and `session`/`client`/`seeded_session` (Postgres 18 via
  testcontainers, per-test transaction rollback). Tests using the
  Postgres fixtures must carry `@pytest.mark.docker` (markers are
  strict); they live in `tests/integration/`.
- `docker-compose.yml` - `db` (postgres:18), `migrate` one-shot, `app`, and a
  `seed` one-shot.
- `frontend/` - Vite + Vue 3 + TypeScript + Tailwind 4 + shadcn-vue.
  `@/*` maps to `src/*`. Generated shadcn code in `src/components/ui` is
  excluded from lint and formatting. `src/api/schema.d.ts` is generated
  from the backend OpenAPI schema and also excluded from lint/format.
- `pyproject.toml` - uv workspace root plus shared ruff, mypy (strict,
  pydantic plugin) and pytest config.
- `package.json` / `pnpm-workspace.yaml` - pnpm workspace; root scripts
  delegate with `pnpm --filter frontend`.

## Commands

```sh
uv sync                        # python env + lockfile
pnpm install                   # node deps
uv run pytest                  # full backend suite (needs Docker), 100% coverage gate, what CI runs
uv run pytest -m "not docker" --no-cov   # fast docker-free loop, NOT coverage-complete
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini revision --autogenerate -m "msg"
uv run seed                    # idempotent seed against DATABASE_URL
uv run sync-playbooks          # upsert playbooks/ to the Devin org
docker compose up -d db        # local postgres 18 on :5432
docker compose run --rm seed   # seed the compose database
uv run ruff check .            # python lint
uv run ruff format --check .   # python format check
uv run mypy                    # strict type check
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test
pnpm test:coverage             # frontend tests with 100% coverage gate (CI)
pnpm generate:api              # regenerate openapi.json + schema.d.ts
pnpm build                     # emits frontend/dist
uv run pre-commit run --all-files
docker build -t devin-flow .
```

## Conventions

- Conventional Commits (Angular). Types: feat, fix, docs, style, refactor,
  perf, test, build, ci. Subject <= 50 chars, lowercase, no trailing period.
  Body wrapped at 72. One scope max: `backend`, `frontend`, or none.
  Manifest and lockfile changes go in the same commit.
- Backend tests in `backend/tests/` mirror `src`.
- No em dashes anywhere.
