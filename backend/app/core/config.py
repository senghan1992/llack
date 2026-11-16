"""Application settings, read from the environment (or a local ``.env``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]

ENV_DEVELOPMENT = "development"
ENV_STAGING = "staging"
ENV_PRODUCTION = "production"

# 개발용 기본값. 이 키로 서명된 토큰은 누구나 만들 수 있으므로 운영에서는
# 절대 쓰지 않습니다 — `validate_production_settings` 가 기동을 막습니다.
DEFAULT_DEV_SECRET_KEY = "llack-dev-secret-key-change-me-before-production"


class InsecureSettings(RuntimeError):
    """운영에서 그대로 쓰면 안 되는 설정입니다."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 이 서버가 어디에서 도는가. "production" 이면 아래의 운영 가드가 돕니다.
    env: Literal["development", "staging", "production"] = Field(
        default=ENV_DEVELOPMENT,
        validation_alias=AliasChoices("APP_ENV", "LLACK_APP_ENV"),
    )
    secret_key: str = Field(
        default=DEFAULT_DEV_SECRET_KEY,
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

    # 레이트 리밋. 각 항목은 "한 창(period)에 몇 번까지" 입니다.
    # 사내망에서는 여러 사람이 주소를 공유할 수 있으므로, 값이 너무 작으면
    # 동료가 같이 막힙니다 — 필요한 만큼 키우세요.
    rate_limit_enabled: bool = True
    rate_limit_signup: int = 60  # 시간당, 주소당
    rate_limit_login: int = 30  # 분당, 주소당
    rate_limit_login_account: int = 10  # 분당, 계정당
    rate_limit_refresh: int = 30  # 분당, 주소당
    rate_limit_message: int = 60  # 분당, 사람당
    rate_limit_upload: int = 30  # 분당, 사람당
    rate_limit_search: int = 60  # 분당, 사람당

    # 이 주소들에서 오는 요청만 `X-Forwarded-For` 를 믿습니다. 리버스
    # 프록시(nginx)가 앞에 있을 때가 그 경우입니다. 사내망에서 오는
    # 요청도 신뢰하려면 여기 사내망 네트워크를 적으세요.
    trusted_proxy_networks: str = "127.0.0.1,::1"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def upload_root(self) -> Path:
        return self.upload_dir if self.upload_dir.is_absolute() else BACKEND_ROOT / self.upload_dir

    @property
    def is_production(self) -> bool:
        return self.env == ENV_PRODUCTION

    @property
    def trusted_proxy_networks_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_networks.split(",") if item.strip()]

    def rate_limit_capacity(self, scope: str) -> int:
        """어떤 동작의 한도가 몇 번인지. 모르는 이름이면 제한이 없습니다."""
        value = getattr(self, f"rate_limit_{scope.replace('-', '_')}", None)
        return int(value) if value is not None else 0


def validate_production_settings(settings: Settings) -> None:
    """운영 서버가 개발용 기본값으로 뜨지 않게 막습니다.

    두 가지가 위험합니다. 개발용 시크릿 키로 서명된 토큰은 누구나 만들어
    만들 수 있고(그 토큰이면 누구인지도 속일 수 있습니다), CORS 가 ``*``
    면 브라우저 어디서든 이 API 를 부를 수 있습니다. 둘 다 운영에서
    조용히 잘못된 상태로 떠 있으면 그때 알아차리게 됩니다.
    """
    if not settings.is_production:
        return

    problems: list[str] = []
    if settings.secret_key == DEFAULT_DEV_SECRET_KEY:
        problems.append(
            "SECRET_KEY 가 개발용 기본값입니다 — "
            'python3 -c "import secrets; print(secrets.token_urlsafe(48))" 로 새로 뽑으세요.'
        )
    if settings.cors_origins.strip() in ("", "*"):
        problems.append(
            'CORS_ORIGINS 가 "*" 입니다 — 이 서버를 여는 주소를 적으세요 '
            "(예: https://atrium.example.com)."
        )
    if problems:
        raise InsecureSettings(
            "운영 설정을 확인하세요.\n" + "\n".join(f"  · {problem}" for problem in problems)
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
