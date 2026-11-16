"""운영 설정의 가드 — 잘못된 설정으로 서버가 뜨지 않게 한다."""

from __future__ import annotations

import pytest

from app.core.config import (
    DEFAULT_DEV_SECRET_KEY,
    InsecureSettings,
    Settings,
    validate_production_settings,
)


def test_development_settings_pass_the_guard() -> None:
    validate_production_settings(Settings())


def test_a_production_server_with_the_development_key_is_refused() -> None:
    settings = Settings(APP_ENV="production", SECRET_KEY=DEFAULT_DEV_SECRET_KEY)
    with pytest.raises(InsecureSettings) as failure:
        validate_production_settings(settings)
    message = str(failure.value)
    assert "SECRET_KEY" in message
    assert DEFAULT_DEV_SECRET_KEY not in message


def test_a_production_server_that_opens_every_origin_is_refused() -> None:
    settings = Settings(APP_ENV="production", SECRET_KEY="a-real-random-key")
    with pytest.raises(InsecureSettings) as failure:
        validate_production_settings(settings)
    assert "CORS_ORIGINS" in str(failure.value)


def test_a_properly_set_up_production_server_passes() -> None:
    settings = Settings(
        APP_ENV="production",
        SECRET_KEY="a-real-random-key",
        CORS_ORIGINS="https://atrium.example.com",
    )
    validate_production_settings(settings)


def test_staging_is_not_production() -> None:
    settings = Settings(APP_ENV="staging")
    assert settings.is_production is False
    validate_production_settings(settings)
