#!/bin/sh
# The schema is created from the SQLAlchemy metadata on startup, so there is no
# migration step to run here.
set -eu

echo "llack: starting $*"
exec "$@"
