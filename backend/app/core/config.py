"""Application settings, loaded from environment / .env with the LLACK_ prefix."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLACK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────────────
    env: Literal["development", "staging", "production"] = "development"
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    api_prefix: str = "/api/v1"

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./llack.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Redis ───────────────────────────────────────────────────────────
    # Empty means "single-node in-process fan-out" — fine for dev, not for
    # more than one uvicorn worker.
    redis_url: str = ""

    # ── Tokens ──────────────────────────────────────────────────────────
    access_token_ttl_seconds: int = 900          # 15 min
    refresh_token_ttl_seconds: int = 2_592_000   # 30 days
    jwt_algorithm: str = "HS256"

    # ── Storage ─────────────────────────────────────────────────────────
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: Path = Path("./var/uploads")
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "ap-northeast-2"
    max_upload_bytes: int = 104_857_600  # 100 MiB

    # ── Realtime ────────────────────────────────────────────────────────
    ws_heartbeat_seconds: int = 25
    presence_ttl_seconds: int = 60

    # ── CORS ────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:1420",
        "http://localhost:5173",
        "tauri://localhost",
    ]

    # ── Mini-app platform ───────────────────────────────────────────────
    # Mini-app iframes get their own CSP; these are the hosts they may be
    # loaded from. "*" allows any (development only).
    app_allowed_hosts: list[str] = ["*"]

    @field_validator("cors_origins", "app_allowed_hosts", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
