#!/bin/sh
# Apply migrations before serving. Safe to run on every container start:
# Alembic is idempotent once the schema is at head.
set -eu

echo "llack: applying migrations"
alembic upgrade head

echo "llack: starting $*"
exec "$@"
