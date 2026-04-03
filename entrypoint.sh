#!/bin/sh
set -e

# Run database migrations once, before Uvicorn forks workers.
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

# Hand off to the CMD (uvicorn)
exec "$@"
