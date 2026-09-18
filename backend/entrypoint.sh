#!/bin/sh
set -eu
alembic -c /app/backend/alembic.ini upgrade head
exec uvicorn devin_flow.main:app --host 0.0.0.0 --port 8000
