FROM node:24-slim AS frontend
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile
COPY frontend/ frontend/
RUN pnpm --filter frontend build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/ backend/
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
RUN useradd --create-home appuser
WORKDIR /app
COPY --from=backend /app/.venv /app/.venv
COPY --from=backend /app/backend/alembic.ini /app/backend/alembic.ini
COPY --from=backend /app/backend/alembic /app/backend/alembic
COPY --from=backend /app/backend/entrypoint.sh /app/backend/entrypoint.sh
COPY --from=frontend /app/frontend/dist /app/static
ENV STATIC_DIR=/app/static PATH=/app/.venv/bin:$PATH
USER appuser
EXPOSE 8000
# DATABASE_URL must point at a reachable Postgres; migrations run on start
ENTRYPOINT ["/app/backend/entrypoint.sh"]
