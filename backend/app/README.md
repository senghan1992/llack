# Llack Backend Application

## Overview

The FastAPI application package. `main.py` builds the app, wires the
middleware and the error handlers, mounts the v1 router, and runs the startup
schema bootstrap. Everything else in the package is organised by concern.

The dependency direction is one-way: `api` and `realtime` call `services`,
`services` call `models` and `core`, and nothing calls back up.

## Interface

- `__version__ = "0.1.0"` [backend/app/__init__.py:__version__]
- `settings = get_settings()` — the process-wide settings singleton
  [backend/app/main.py:settings]
- `lifespan(_: FastAPI) -> AsyncIterator[None]` — the startup context manager:
  create the schema, grow it, verify it, prepare the upload directory, sweep
  orphan files [backend/app/main.py:lifespan]
- `app = FastAPI(title="Atrium", version="0.1.0", description="ArcheAI
  internal workspace & messenger API.", lifespan=lifespan)`
  [backend/app/main.py:app]
- `GET /health` -> `{"status": "ok"}` — health probe outside the API prefix
  [backend/app/main.py:health]
- `GET /api/v1/health` -> `{"status": "ok"}` — health probe inside the API
  prefix [backend/app/main.py:api_health]
- Subdirectory contracts:
  - [api](./api/README.md) — the HTTP transport layer: shared dependencies and
    the v1 routes
  - [core](./core/README.md) — settings, database, errors, ids, security
  - [models](./models/README.md) — the SQLAlchemy ORM tables
  - [realtime](./realtime/README.md) — the WebSocket hub and the event emitters
  - [schemas](./schemas/README.md) — the Pydantic request and response models
  - [services](./services/README.md) — the domain logic shared by HTTP and
    WebSocket

## Invariants

- The schema is created from the SQLAlchemy metadata on startup; there is no
  migration tool in this project
  [backend/app/main.py:lifespan]
- The startup sequence is `create_all()`, then `ensure_columns()`, then
  `ensure_schema()` [backend/app/main.py:lifespan]
- A `SchemaMismatch` from `ensure_schema()` is logged and re-raised, so a
  database from another version of the app fails at startup rather than on the
  first login [backend/app/main.py:lifespan]
- The upload root is created if missing before the app starts serving
  [backend/app/main.py:lifespan]
- The orphan-file sweep runs inside the lifespan, so it happens without anyone
  asking [backend/app/main.py:lifespan]
- CORS is installed with `allow_origins=settings.cors_origin_list`,
  `allow_credentials=True`, and all methods and headers allowed
  [backend/app/main.py:app]
- `register_exception_handlers(app)` is called before the router is mounted, so
  the error envelope applies to every route including `/health`
  [backend/app/main.py:app]
- The v1 router is mounted under `settings.api_prefix`, which defaults to
  `/api/v1` [backend/app/main.py:app]
- `settings = get_settings()` runs at import time, so the settings singleton is
  created once per process [backend/app/main.py:settings]

## Side Effects

- Installs the `CORSMiddleware` [backend/app/main.py:app]
- Registers the exception handlers for the whole app
  [backend/app/main.py:app]
- On startup: issues DDL through `create_all()` and `ensure_columns()`, and
  verifies the live schema through `ensure_schema()`
  [backend/app/main.py:lifespan]
- On startup: creates the upload directory on disk
  [backend/app/main.py:lifespan]
- On startup: runs `purge_orphan_files(session, settings.orphan_file_hours)`
  in its own session and logs how many files were removed
  [backend/app/main.py:lifespan]
- Configures root logging with `logging.basicConfig(level=logging.INFO, ...)`
  at import time [backend/app/main.py:app]
- Logs "llack backend ready (database=%s)" once startup finishes
  [backend/app/main.py:lifespan]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
- Start the API locally: `cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
  (or `make dev` from the repository root)
