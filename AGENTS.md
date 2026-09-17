# AGENTS.md

## Layout

- `backend/` - Python package `devin_flow` (src layout). `main.py` is the
  ASGI entrypoint; the app factory lives in `app.py`, API routes in
  `api/` (under `/api`), and static file serving in `web/spa.py`. Serves
  `frontend/dist` when it exists (or `STATIC_DIR`). Unknown `/api/*`
  paths must stay 404.
- `backend/tests/` - pytest tests; test files mirror `src` under
  `tests/devin_flow/` (pytest runs with `--import-mode=importlib`).
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
uv run pytest                  # backend tests, fails under 100% coverage
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
