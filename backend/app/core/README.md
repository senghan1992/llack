# Core Building Blocks

## Overview

The five pieces everything else stands on:

- `config.py` — environment-backed settings, read once per process
- `db.py` — the async engine, the session factory, and the schema bootstrap
- `errors.py` — one error envelope for the whole API
- `ids.py` — prefixed, time-sortable identifiers
- `security.py` — password hashing, JWT issue/verify, and the auth dependencies

There is no migration tool in this project. The schema is created from the
SQLAlchemy metadata on startup, and drift is detected by comparing the live
schema with the models.

## Interface

### Configuration (`config.py`)

- `BACKEND_ROOT` — backend package root (`parents[2]` of this file), used to
  anchor relative paths [backend/app/core/config.py:BACKEND_ROOT]
- `Settings(BaseSettings)` — `model_config = SettingsConfigDict(env_file=".env",
  env_file_encoding="utf-8", extra="ignore")`
  [backend/app/core/config.py:Settings.model_config]
- `Settings.secret_key` — default
  `"llack-dev-secret-key-change-me-before-production"`; env aliases
  `SECRET_KEY` | `LLACK_SECRET_KEY`
  [backend/app/core/config.py:Settings.secret_key]
- `Settings.database_url` — default `"sqlite+aiosqlite:///./llack.db"`; env
  aliases `DATABASE_URL` | `LLACK_DATABASE_URL`
  [backend/app/core/config.py:Settings.database_url]
- `Settings.api_prefix` — `"/api/v1"`
  [backend/app/core/config.py:Settings.api_prefix]
- `Settings.access_token_ttl_seconds` — `1800`
  [backend/app/core/config.py:Settings.access_token_ttl_seconds]
- `Settings.refresh_token_ttl_seconds` — `2592000`
  [backend/app/core/config.py:Settings.refresh_token_ttl_seconds]
- `Settings.jwt_algorithm` — `"HS256"`
  [backend/app/core/config.py:Settings.jwt_algorithm]
- `Settings.cors_origins` — `"*"`
  [backend/app/core/config.py:Settings.cors_origins]
- `Settings.upload_dir` — default `BACKEND_ROOT / "var" / "uploads"`; env
  aliases `UPLOAD_DIR` | `LLACK_UPLOAD_DIR`
  [backend/app/core/config.py:Settings.upload_dir]
- `Settings.max_upload_bytes` — `50 * 1024 * 1024`
  [backend/app/core/config.py:Settings.max_upload_bytes]
- `Settings.workspace_quota_bytes` — `5 * 1024 * 1024 * 1024`
  [backend/app/core/config.py:Settings.workspace_quota_bytes]
- `Settings.orphan_file_hours` — `24`
  [backend/app/core/config.py:Settings.orphan_file_hours]
- `Settings.max_name_length` — `120`
  [backend/app/core/config.py:Settings.max_name_length]
- `Settings.cors_origin_list` — splits `cors_origins` on commas; empty or `*`
  yields `["*"]` [backend/app/core/config.py:Settings.cors_origin_list]
- `Settings.upload_root` — `upload_dir` when absolute, otherwise
  `BACKEND_ROOT / upload_dir` [backend/app/core/config.py:Settings.upload_root]
- `get_settings() -> Settings` — cached with `@lru_cache(maxsize=1)`
  [backend/app/core/config.py:get_settings]

### Database (`db.py`)

- `SchemaMismatch(RuntimeError)` — raised when the live database schema does
  not match the models [backend/app/core/db.py:SchemaMismatch]
- `_resolved_database_url(raw_url)` — rewrites relative SQLite paths as absolute
  under `BACKEND_ROOT` [backend/app/core/db.py:_resolved_database_url]
- `settings` — module-level `Settings` instance
  [backend/app/core/db.py:settings]
- `DATABASE_URL` — the resolved URL handed to the engine
  [backend/app/core/db.py:DATABASE_URL]
- `engine` — `create_async_engine(DATABASE_URL, echo=False, future=True,
  pool_pre_ping=True)` [backend/app/core/db.py:engine]
- `SessionLocal` — `async_sessionmaker(engine, expire_on_commit=False,
  class_=AsyncSession)` [backend/app/core/db.py:SessionLocal]
- `get_session()` — FastAPI dependency yielding a request-scoped session
  [backend/app/core/db.py:get_session]
- `create_all()` — creates every table declared on `Base.metadata`
  [backend/app/core/db.py:create_all]
- `drop_all()` — drops every table declared on `Base.metadata`
  [backend/app/core/db.py:drop_all]
- `ensure_columns()` — idempotent `ALTER TABLE` / `CREATE INDEX` schema growth
  for messages, files, projects, tasks
  [backend/app/core/db.py:ensure_columns]
- `ensure_schema()` — compares live columns to `Base.metadata` and raises
  `SchemaMismatch` on drift [backend/app/core/db.py:ensure_schema]

### Errors (`errors.py`)

- Error codes: `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`,
  `VALIDATION_ERROR`, `RATE_LIMITED`, `INTERNAL`
  [backend/app/core/errors.py:UNAUTHORIZED]
- `_STATUS_CODES` — HTTP status to error code map (400, 401, 403, 404, 409,
  413, 415, 422, 429) [backend/app/core/errors.py:_STATUS_CODES]
- `ErrorBody(BaseModel)` — `code: str`, `message: str`, `field: str | None = None`
  [backend/app/core/errors.py:ErrorBody]
- `ErrorEnvelope(BaseModel)` — `error: ErrorBody`
  [backend/app/core/errors.py:ErrorEnvelope]
- `AppError(Exception)` — carries `code`, `message`, `status_code`, `field` plus
  `to_response() -> JSONResponse` [backend/app/core/errors.py:AppError]
- Factory helpers: `unauthorized` (401), `forbidden` (403), `not_found` (404),
  `conflict` (409), `validation_error` (422), `rate_limited` (429), `internal`
  (500) [backend/app/core/errors.py:unauthorized]
- `_envelope(code, message, field=None)` — builds the
  `{"error": {"code", "message", "field"}}` body
  [backend/app/core/errors.py:_envelope]
- `register_exception_handlers(app)` — attaches handlers for `AppError`,
  `RequestValidationError`, `StarletteHTTPException` and generic `Exception`
  [backend/app/core/errors.py:register_exception_handlers]

### Identifiers (`ids.py`)

- `_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"` — Crockford base32 without
  I, L, O, U [backend/app/core/ids.py:_ALPHABET]
- Entity prefixes: `USER_PREFIX "usr_"`, `WORKSPACE_PREFIX "wsp_"`,
  `CHANNEL_PREFIX "chl_"`, `MESSAGE_PREFIX "msg_"`, `FILE_PREFIX "fil_"`,
  `MEMBER_PREFIX "mem_"`, `CHANNEL_MEMBER_PREFIX "cm_"`,
  `REACTION_PREFIX "rx_"`, `READ_STATE_PREFIX "rs_"`, `INVITE_PREFIX "inv_"`,
  `EVENT_PREFIX "evt_"`, `ATTENDEE_PREFIX "att_"`, `PROJECT_PREFIX "prj_"`,
  `ROADMAP_PREFIX "rm_"`, `PROJECT_MEMBER_PREFIX "pm_"`,
  `TASK_PREFIX "tsk_"`, `TASK_COMMENT_PREFIX "tc_"`,
  `MILESTONE_PREFIX "mst_"`, `ORG_UNIT_PREFIX "org_"`,
  `ORG_MEMBER_PREFIX "om_"`, `ORG_MANAGER_PREFIX "ogm_"`
  [backend/app/core/ids.py:USER_PREFIX]
- `_encode(value, length)` — 5-bit base32 encoder
  [backend/app/core/ids.py:_encode]
- `ulid(now=None) -> str` — 26-character lexicographically sortable ULID
  [backend/app/core/ids.py:ulid]
- `new_id(prefix) -> str` — prefixed identifier, e.g. `new_id("usr_")`
  [backend/app/core/ids.py:new_id]

### Security (`security.py`)

- `_password_hash = PasswordHash.recommended()` (Argon2)
  [backend/app/core/security.py:_password_hash]
- `_bearer = HTTPBearer(auto_error=False)`
  [backend/app/core/security.py:_bearer]
- `ACCESS_TOKEN = "access"`, `REFRESH_TOKEN = "refresh"`
  [backend/app/core/security.py:ACCESS_TOKEN]
- `hash_password(raw_password) -> str`
  [backend/app/core/security.py:hash_password]
- `verify_password(raw_password, password_hash) -> bool` — returns `False` on
  any exception [backend/app/core/security.py:verify_password]
- `_encode(user_id, token_type, ttl_seconds) -> str` — builds the JWT payload
  and signs it [backend/app/core/security.py:_encode]
- `create_access_token(user_id) -> str`
  [backend/app/core/security.py:create_access_token]
- `create_refresh_token(user_id) -> str`
  [backend/app/core/security.py:create_refresh_token]
- `decode_token(token, expected_type) -> str` — returns the `sub` user id,
  raises `ValueError` otherwise
  [backend/app/core/security.py:decode_token]
- `load_user(session, user_id) -> User | None`
  [backend/app/core/security.py:load_user]
- `current_user(request, credentials, session) -> User` — FastAPI dependency
  [backend/app/core/security.py:current_user]
- `authenticate_query_token(session, token) -> User | None` — resolves a
  `?token=` query parameter [backend/app/core/security.py:authenticate_query_token]
- `current_user_or_token(request, credentials, token, session) -> User` — bearer
  header or query token [backend/app/core/security.py:current_user_or_token]

## Invariants

- `get_settings()` is cached with `@lru_cache(maxsize=1)`, so the `Settings`
  object is a process-wide singleton and environment changes after the first
  call are not observed [backend/app/core/config.py:get_settings]
- `secret_key`, `database_url` and `upload_dir` accept two environment names
  each (unprefixed and `LLACK_`-prefixed); all other settings read only their
  exact field name [backend/app/core/config.py:Settings.secret_key]
- Relative SQLite database paths are rewritten to absolute paths under
  `BACKEND_ROOT`, so the DB file location never depends on the process working
  directory; `:memory:` URLs are left unchanged
  [backend/app/core/db.py:_resolved_database_url]
- Only URLs starting with `sqlite+aiosqlite:///` are rewritten; every other
  dialect string is returned verbatim
  [backend/app/core/db.py:_resolved_database_url]
- The engine is created with `echo=False`, `future=True` and
  `pool_pre_ping=True` [backend/app/core/db.py:engine]
- `SessionLocal` is created with `expire_on_commit=False`, so ORM attributes
  remain readable after the transaction commits
  [backend/app/core/db.py:SessionLocal]
- `ensure_columns()` is idempotent and safe to run on every start: each
  statement is guarded by an `inspect()` of the existing columns and indexes
  [backend/app/core/db.py:ensure_columns]
- The `messages.inline` boolean column is added with a dialect-specific
  default: `'false'` on postgresql, `'0'` on every other dialect
  [backend/app/core/db.py:ensure_columns]
- `messages.reply_to_id`, `files.workspace_id`, `tasks.roadmap_id` and
  `tasks.milestone_id` are `VARCHAR(40)`, matching the 4-character prefix plus
  26-character ULID id width [backend/app/core/db.py:ensure_columns]
- `projects.description` is added `NOT NULL DEFAULT ''` and then back-filled
  from `projects.purpose` [backend/app/core/db.py:ensure_columns]
- `ensure_schema()` raises `SchemaMismatch` listing "table: missing columns"
  before the app can fail on its first query
  [backend/app/core/db.py:ensure_schema]
- `ensure_schema()` treats a missing table (`NoSuchTableError`) as an empty
  column set, so every expected column is listed as missing
  [backend/app/core/db.py:ensure_schema]
- There is no migration tool: drift is repaired by deleting and recreating the
  SQLite file (`make db-reset`) or by creating a fresh Postgres schema
  [backend/app/core/db.py:ensure_schema]
- Every error response uses the envelope
  `{"error": {"code", "message", "field"}}`; `field` is null unless a field name
  is supplied [backend/app/core/errors.py:ErrorEnvelope]
- Error code to HTTP status mapping: unauthorized 401, forbidden 403,
  not_found 404, conflict 409, validation_error 422, rate_limited 429, internal
  500 [backend/app/core/errors.py:AppError]
- HTTP status to error code mapping for `StarletteHTTPException`:
  400/413/415/422 to `validation_error`, 401 to `unauthorized`, 403 to
  `forbidden`, 404 to `not_found`, 409 to `conflict`, 429 to `rate_limited`, any
  other status to `internal` [backend/app/core/errors.py:_STATUS_CODES]
- `RequestValidationError` always answers 422 and reports only the first error,
  with the location joined by `.` and the `body` segment removed
  [backend/app/core/errors.py:register_exception_handlers]
- Unhandled exceptions are logged with method and path and returned as a
  generic 500 "internal server error" envelope with no detail leaked
  [backend/app/core/errors.py:register_exception_handlers]
- `cors_origin_list` returns `["*"]` for an empty or `*` value; otherwise it
  splits on commas and drops blank entries
  [backend/app/core/config.py:Settings.cors_origin_list]
- `upload_root` resolves a relative `upload_dir` against `BACKEND_ROOT` so
  uploads never depend on the working directory
  [backend/app/core/config.py:Settings.upload_root]
- Access token TTL is 1800 seconds (30 minutes); refresh token TTL is 2592000
  seconds (30 days) [backend/app/core/config.py:Settings.access_token_ttl_seconds]
- Tokens are signed with HS256 using `settings.secret_key`
  [backend/app/core/config.py:Settings.jwt_algorithm]
- The JWT payload always carries `sub`, `typ`, `iat`, `exp` and a uuid4-hex
  `jti` [backend/app/core/security.py:_encode]
- `decode_token` rejects a token whose `typ` does not equal `expected_type`, and
  requires a non-empty string `sub`
  [backend/app/core/security.py:decode_token]
- Only access-type tokens are accepted as credentials: `current_user` and
  `authenticate_query_token` decode with `ACCESS_TOKEN`, so a refresh token
  cannot authenticate a request
  [backend/app/core/security.py:current_user]
- `current_user` sets `request.state.user_id` to the resolved user id;
  `current_user_or_token` does the same on the query-token path
  [backend/app/core/security.py:current_user]
- `verify_password` never raises: any exception inside the hash verification is
  swallowed and returns `False`
  [backend/app/core/security.py:verify_password]
- Ids are a 4-character prefix followed by a 26-character ULID (30 characters
  total), e.g. `usr_01J...` [backend/app/core/ids.py:new_id]
- The ULID alphabet is Crockford base32 and excludes the letters I, L, O and U
  [backend/app/core/ids.py:_ALPHABET]
- A ULID is 10 characters of millisecond timestamp plus 16 characters of 80
  random bits, so ids sort lexicographically by creation time
  [backend/app/core/ids.py:ulid]
- Each entity kind owns a distinct prefix constant, so ids of different kinds
  never collide [backend/app/core/ids.py:USER_PREFIX]
- File limits are fixed by settings: `max_upload_bytes` 50 MiB,
  `workspace_quota_bytes` 5 GiB, `orphan_file_hours` 24, `max_name_length` 120
  [backend/app/core/config.py:Settings.max_upload_bytes]
- `orphan_file_hours` of 0 means uploads are never reclaimed
  [backend/app/core/config.py:Settings.orphan_file_hours]

## Side Effects

- Reads a `.env` file (utf-8) from the process working directory whenever
  `Settings` is constructed [backend/app/core/config.py:Settings.model_config]
- Instantiates the cached `Settings` singleton at import time of the db module
  [backend/app/core/db.py:settings]
- Creates the async SQLAlchemy engine and its connection pool at import time
  [backend/app/core/db.py:engine]
- Opens an `AsyncSession` per request through `SessionLocal` and closes it when
  the dependency generator ends [backend/app/core/db.py:get_session]
- DDL: `create_all()` issues `CREATE TABLE` for every table in `Base.metadata`
  inside an engine transaction [backend/app/core/db.py:create_all]
- DDL: `drop_all()` issues `DROP TABLE` for every table in `Base.metadata`
  [backend/app/core/db.py:drop_all]
- DDL: `ensure_columns()` issues `ALTER TABLE messages ADD COLUMN reply_to_id /
  inline / deleted_body`, `ALTER TABLE files ADD COLUMN workspace_id`,
  `ALTER TABLE projects ADD COLUMN description`, `ALTER TABLE tasks ADD COLUMN
  roadmap_id / milestone_id` [backend/app/core/db.py:ensure_columns]
- DML: `ensure_columns()` back-fills `projects.description` from
  `projects.purpose` [backend/app/core/db.py:ensure_columns]
- DDL: `ensure_columns()` creates indexes `ix_tasks_roadmap_id` and
  `ix_tasks_milestone_id` [backend/app/core/db.py:ensure_columns]
- Reads live schema metadata via
  `inspect(sync_connection).get_columns()` and `get_indexes()`
  [backend/app/core/db.py:ensure_columns]
- `ensure_schema()` raises `SchemaMismatch` and aborts startup when the live
  schema drifts from `Base.metadata` [backend/app/core/db.py:ensure_schema]
- Logs unhandled exceptions with
  `logger.exception('unhandled error on %s %s', request.method, request.url.path)`
  [backend/app/core/errors.py:register_exception_handlers]
- Hashes passwords with `PasswordHash.recommended()`
  [backend/app/core/security.py:hash_password]
- Verifies password hashes against stored digests
  [backend/app/core/security.py:verify_password]
- Issues JWTs via `jwt.encode` signed with `settings.secret_key` and
  `settings.jwt_algorithm` [backend/app/core/security.py:_encode]
- Generates a random per-token `jti` with `uuid.uuid4().hex`
  [backend/app/core/security.py:_encode]
- Verifies and decodes JWTs via `jwt.decode` with
  `algorithms=[settings.jwt_algorithm]`
  [backend/app/core/security.py:decode_token]
- Reads the `User` row from the database via `session.get(User, user_id)`
  [backend/app/core/security.py:load_user]
- Mutates the request-scoped attribute `request.state.user_id`
  [backend/app/core/security.py:current_user]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
