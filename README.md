# devin-flow

Monorepo with a FastAPI backend and a Vue 3 (Vite, Tailwind, shadcn-vue)
frontend. The backend serves the built SPA in production.

## Prerequisites

- uv (Python 3.13 is pinned via `.python-version`)
- Node 24 + pnpm (pinned via `.node-version` and `packageManager`)

## Setup

```sh
uv sync
pnpm install
uv run pre-commit install
```

## Development

```sh
# backend on :8000
uv run fastapi dev backend/src/devin_flow/main.py

# frontend on :5173, proxies /api to :8000
pnpm dev
```

## Checks

```sh
# backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest

# frontend
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test
pnpm build

# everything (pre-commit)
uv run pre-commit run --all-files
```

## Docker

```sh
docker build -t devin-flow .
docker run -p 8000:8000 devin-flow
```

The image builds `frontend/dist`, installs the Python deps with
`uv sync --frozen --no-dev --no-editable`, and serves the app on port 8000.

## Layout

```
backend/    FastAPI package (src layout), tests in backend/tests
frontend/   Vite + Vue 3 + Tailwind + shadcn-vue app
pyproject   uv workspace root, shared ruff/mypy/pytest config
```
