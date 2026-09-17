# AGENTS.md

## Layout

- `backend/` - Python package `devin_flow` (src layout). FastAPI app
  factory in `src/devin_flow/main.py`; serves `frontend/dist` when it
  exists (or `STATIC_DIR`). Unknown `/api/*` paths must stay 404.
- `backend/tests/` - pytest tests; test files mirror `src`.
- `frontend/` - Vite + Vue 3 + TypeScript + Tailwind 4 + shadcn-vue.
  `@/*` maps to `src/*`. Generated shadcn code in `src/components/ui` is
  excluded from lint and formatting.
- `pyproject.toml` - uv workspace root plus shared ruff, mypy (strict,
  pydantic plugin) and pytest config.
- `package.json` / `pnpm-workspace.yaml` - pnpm workspace; root scripts
  delegate with `pnpm --filter frontend`.

## Commands

```sh
uv sync                        # python env + lockfile
pnpm install                   # node deps
uv run pytest                  # backend tests
uv run ruff check .            # python lint
uv run ruff format --check .   # python format check
uv run mypy                    # strict type check
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test
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
