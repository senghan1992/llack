"""Application settings, read from the environment (or a local ``.env``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = Field(
        default="llack-dev-secret-key-change-me-before-production",
        validation_alias=AliasChoices("SECRET_KEY", "LLACK_SECRET_KEY"),
    )
    database_url: str = Field(
        default="sqlite+aiosqlite:///./llack.db",
        validation_alias=AliasChoices("DATABASE_URL", "LLACK_DATABASE_URL"),
    )
    api_prefix: str = "/api/v1"
    access_token_ttl_seconds: int = 1800  # 30 minutes
    refresh_token_ttl_seconds: int = 2_592_000  # 30 days
    jwt_algorithm: str = "HS256"
    cors_origins: str = "*"
    upload_dir: Path = Field(
        default_factory=lambda: BACKEND_ROOT / "var" / "uploads",
        validation_alias=AliasChoices("UPLOAD_DIR", "LLACK_UPLOAD_DIR"),
    )
    # Room for real office documents. Raise it with MAX_UPLOAD_BYTES.
    max_upload_bytes: int = 50 * 1024 * 1024
    # How much a workspace may keep in files. Five gigabytes of documents is
    # a lot for one team; the rule is here so it can be argued about in one
    # place.
    workspace_quota_bytes: int = 5 * 1024 * 1024 * 1024
    # An upload that never reaches a message is taken away after this many
    # hours. Zero keeps everything.
    orphan_file_hours: int = 24
    max_name_length: int = 120

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def upload_root(self) -> Path:
        return self.upload_dir if self.upload_dir.is_absolute() else BACKEND_ROOT / self.upload_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
