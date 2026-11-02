from __future__ import annotations

import pytest

from app.core.config import Settings


def test_defaults_are_local_development_friendly() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.default_region == "IN"
    assert settings.retention_raw_days == 15


def test_production_requires_a_signing_secret() -> None:
    settings = Settings(_env_file=None, app_env="production", cookie_secure=True)
    problems = settings.validate_for_startup()
    assert any("SIGNING_SECRET" in problem for problem in problems)


def test_production_requires_secure_cookies() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        signing_secret="x" * 32,
        cookie_secure=False,
        database_url="postgresql+asyncpg://u:p@db.internal:5432/sparkxflow",
    )
    assert any("COOKIE_SECURE" in problem for problem in settings.validate_for_startup())


def test_production_rejects_a_localhost_database() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        signing_secret="x" * 32,
        cookie_secure=True,
        database_url="postgresql+asyncpg://u:p@localhost:5432/sparkxflow",
    )
    assert any("localhost" in problem for problem in settings.validate_for_startup())


def test_development_is_allowed_to_start_without_secrets() -> None:
    assert Settings(_env_file=None).validate_for_startup() == []


def test_invalid_samesite_is_rejected_at_load_time() -> None:
    with pytest.raises(ValueError, match="cookie_samesite"):
        Settings(_env_file=None, cookie_samesite="no-cors")


def test_region_must_be_iso_alpha2() -> None:
    with pytest.raises(ValueError, match="ISO 3166"):
        Settings(_env_file=None, default_region="INDIA")
    assert Settings(_env_file=None, default_region="us").default_region == "US"


def test_log_level_is_normalised() -> None:
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"
