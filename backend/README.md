# Llack Backend Blueprint

## System Overview

The Llack backend is a single FastAPI service: an internal workspace and
messenger API. Python 3.12, FastAPI with async SQLAlchemy 2.0. SQLite is the
development database (one file, `llack.db`); Postgres is the production
deployment target, reached by changing one setting.

The package is layered one way:

```
app/main.py            FastAPI app, lifespan, middleware, error handlers
app/api/               HTTP transport: deps.py + v1/ routes
app/realtime/          WebSocket hub + event emitters
app/services/          domain logic shared by HTTP and WebSocket
app/models/            SQLAlchemy ORM tables (the DDL source of truth)
app/schemas/           Pydantic request/response models (the wire contract)
app/core/              settings, database, errors, ids, security
scripts/seed.py        demo workspace seeder
```

There is no migration tool. The schema is created from the SQLAlchemy metadata
on startup and drift is detected by comparing the live schema with the models.

## Local Interface & Invariants

`backend/` itself holds no Python source — only the build manifest, the test
configuration, and the container definition.

- `pyproject.toml` — package `llack-backend` 0.1.0, `requires-python >= 3.12`;
  runtime dependencies `fastapi>=0.115`, `uvicorn[standard]>=0.32`,
  `pydantic>=2.9`, `pydantic-settings>=2.6`, `sqlalchemy[asyncio]>=2.0.36`,
  `aiosqlite>=0.20`, `asyncpg>=0.30`, `greenlet>=3.1`, `pwdlib[argon2]>=0.2`,
  `pyjwt>=2.10`, `python-multipart>=0.0.17`, `email-validator>=2.2`; dev extras
  `pytest>=8.3`, `pytest-asyncio>=0.24`, `asgi-lifespan>=2.1`, `httpx>=0.28`,
  `websockets>=13.0`, `ruff>=0.8`
  [backend/pyproject.toml:project]
- `[tool.setuptools.packages.find] include = ["app*"]` — only the `app`
  package ships in the wheel [backend/pyproject.toml:tool.setuptools.packages.find]
- `[tool.ruff]` — `line-length = 100`, `target-version = "py312"`
  [backend/pyproject.toml:tool.ruff]
- `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`,
  `asyncio_default_fixture_loop_scope = "function"`, `testpaths = ["tests"]`,
  `filterwarnings = ["ignore::DeprecationWarning"]`
  [backend/pyproject.toml:tool.pytest.ini_options]
- `pytest.ini` — the same four settings, in the standalone ini file
  [backend/pytest.ini:pytest]
- `Dockerfile` — a two-stage build (`python:3.12-slim` builder, then a slim
  runtime) that installs the project from the wheels it just built
  [backend/Dockerfile:Dockerfile]
- The runtime image runs as the non-root user `llack` (uid/gid 10001) and
  writes only to `/app/var` [backend/Dockerfile:Dockerfile]
- `docker-entrypoint.sh` — `set -eu`, echoes the command, then `exec "$@"`; it
  runs no migration step because the schema is created on startup
  [backend/docker-entrypoint.sh:docker-entrypoint.sh]
- `.dockerignore` — excludes `.venv/`, `var/`, `__pycache__/`, `*.pyc`,
  `.pytest_cache/`, `.ruff_cache/`, `*.db`, `*.db-wal`, `*.db-shm`, `.env` and
  `tests/` [backend/.dockerignore:.dockerignore]
- `.env.example` — the documented environment surface: `SECRET_KEY`,
  `DATABASE_URL`, `API_PREFIX`, `CORS_ORIGINS`, `UPLOAD_DIR`
  [backend/.env.example:.env.example]

## Subdirectories & System Boundaries

- [app](./app/README.md) — the FastAPI application: `main.py` plus the
  layered `api`, `realtime`, `services`, `models`, `schemas` and `core`
  packages
- [scripts](./scripts/README.md) — the demo workspace seeder behind
  `make seed`

## Global Invariants

- One uvicorn worker, on purpose: the realtime hub keeps the open sockets in
  this process's memory, so with several workers a message posted to one worker
  would never reach a client connected to another. Scale out with a broker
  behind the hub before raising `--workers`
  [backend/Dockerfile:Dockerfile]
- `--proxy-headers` is set so `client_ip()` can trust `X-Forwarded-For` behind
  a reverse proxy; `--forwarded-allow-ips` must be narrowed to the proxy in
  production [backend/Dockerfile:Dockerfile]
- The container exposes port 8000 and runs `uvicorn app.main:app`
  [backend/Dockerfile:Dockerfile]
- The relative SQLite URL `sqlite+aiosqlite:///./llack.db` is resolved to an
  absolute path under `backend/`, so the database file location never depends
  on the process working directory
  [backend/app/core/db.py:_resolved_database_url]
- `DATABASE_URL` selects the dialect; `postgresql+asyncpg://…` is the
  production form [backend/.env.example:.env.example]
- `UPLOAD_DIR=var/uploads` is resolved relative to `backend/`
  [backend/.env.example:.env.example]

## Global Side Effects

- The application creates and alters database tables at startup from the
  SQLAlchemy metadata [backend/app/main.py:lifespan]
- Uploaded files are written under `UPLOAD_DIR` and swept when they were never
  attached to a message [backend/app/main.py:lifespan]
- The demo seeder writes users, workspaces, channels, messages, calendar events,
  projects and org units into the configured database
  [backend/scripts/seed.py:main]
- The container build downloads and installs the project's dependencies
  [backend/Dockerfile:Dockerfile]

## System Verification

- Run: `cd backend && .venv/bin/pytest -q`
  (the repository-root `make test` target)
- Lint: `cd backend && .venv/bin/ruff check app tests scripts` and
  `cd backend && .venv/bin/ruff format --check .`
  (the repository-root `make lint` target)
- Seed the demo workspace: `cd backend && .venv/bin/python scripts/seed.py`
  (the repository-root `make seed` target)
