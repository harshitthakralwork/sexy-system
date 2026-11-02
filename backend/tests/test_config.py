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


def test_env_file_is_found_regardless_of_working_directory() -> None:
    """Regression: `env_file=".env"` resolved against the cwd, so the backend ran
    on defaults whenever it was started from anywhere but the repo root —
    including pytest. Configuration that loads sometimes looks applied and is not."""
    from app.core.config import _env_files

    candidates = _env_files()
    assert candidates, "no environment file candidates configured"
    for candidate in candidates:
        assert candidate.is_absolute(), f"{candidate} is relative and cwd-dependent"
    # The repo root copy is the canonical location for this project.
    assert (candidates[0].parent.name == "sparkxflow-nexus"), candidates


def test_default_hosts_are_literal_loopback_addresses() -> None:
    """`localhost` may resolve to ::1 on Windows while the development server is
    bound to 127.0.0.1, producing a timeout that looks like an outage."""
    settings = Settings(_env_file=None)
    assert "127.0.0.1" in settings.database_url
    assert "localhost" not in settings.database_url
    assert "127.0.0.1" in settings.redis_url
