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
COPY --from=frontend /app/frontend/dist /app/static
ENV STATIC_DIR=/app/static PATH=/app/.venv/bin:$PATH
USER appuser
EXPOSE 8000
CMD ["uvicorn", "devin_flow_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
