from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables.

    Variable names are the field names below, prefixed with ``SPARKX_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="SPARKX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SparkXFlow Nexus"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://sparkx:sparkx@localhost:5432/sparkxflow"
    database_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    # No-broker development path (docs/RUNBOOK-DOCKER.md section 3.2). Blocks the
    # caller, so it must never be on in production.
    run_jobs_synchronously: bool = False

    log_level: str = "INFO"
    log_json: bool = True

    session_cookie_name: str = "sparkx_session"
    session_ttl_hours: int = 12
    # Used for CSRF-style double-submit tokens. Not used to derive the session token itself.
    signing_secret: str = ""
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # Both loopback spellings, because a browser at http://127.0.0.1:3000 is a
    # different origin from http://localhost:3000 and would otherwise be silently
    # blocked by CORS — which surfaces as a dashboard stuck on "checking".
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    searxng_base_url: str = "http://localhost:8080"
    searxng_timeout_seconds: float = 20.0
    searxng_max_pages: int = 3
    searxng_results_per_page: int = 20

    default_region: str = "IN"
    export_dir: Path = Path("var/exports")
    retention_raw_days: int = 15
    retention_enrichment_days: int = 15

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("cookie_samesite")
    @classmethod
    def _valid_samesite(cls, value: str) -> str:
        allowed = {"strict", "lax", "none"}
        if value.lower() not in allowed:
            raise ValueError(f"cookie_samesite must be one of {sorted(allowed)}")
        return value.lower()

    @field_validator("default_region")
    @classmethod
    def _valid_region(cls, value: str) -> str:
        if len(value) != 2 or not value.isalpha():
            raise ValueError("default_region must be a two-letter ISO 3166-1 alpha-2 code")
        return value.upper()

    @field_validator("searxng_max_pages")
    @classmethod
    def _bounded_pages(cls, value: int) -> int:
        # Each extra page multiplies requests to a proxy that upstream engines
        # will block. The ceiling is configuration-proof on purpose.
        if not 1 <= value <= 10:
            raise ValueError("searxng_max_pages must be between 1 and 10")
        return value

    @field_validator("searxng_results_per_page")
    @classmethod
    def _bounded_results(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("searxng_results_per_page must be between 1 and 50")
        return value

    @field_validator("searxng_timeout_seconds")
    @classmethod
    def _bounded_timeout(cls, value: float) -> float:
        if not 1.0 <= value <= 60.0:
            raise ValueError("searxng_timeout_seconds must be between 1 and 60")
        return value

    @field_validator("session_ttl_hours")
    @classmethod
    def _bounded_ttl(cls, value: int) -> int:
        if not 1 <= value <= 24 * 30:
            raise ValueError("session_ttl_hours must be between 1 and 720")
        return value

    @field_validator("retention_raw_days", "retention_enrichment_days")
    @classmethod
    def _bounded_retention(cls, value: int) -> int:
        if value < 1:
            raise ValueError("retention days must be at least 1")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    def validate_for_startup(self) -> list[str]:
        """Return configuration problems that must be fixed before serving traffic."""
        problems: list[str] = []
        if self.is_production:
            if not self.signing_secret:
                problems.append("SPARKX_SIGNING_SECRET must be set outside development")
            if not self.cookie_secure:
                problems.append("SPARKX_COOKIE_SECURE must be true in production")
            if self.database_url.startswith("sqlite"):
                problems.append("SQLite is not a supported production database")
            if "localhost" in self.database_url:
                problems.append("Database URL still points at localhost")
            if self.run_jobs_synchronously:
                problems.append("SPARKX_RUN_JOBS_SYNCHRONOUSLY must be false in production")
            # The session cookie is sent with credentials. A wildcard origin plus
            # credentialed cookies is cross-origin access to the whole API for any
            # site the operator's browser visits, so it is refused outright.
            if "*" in self.cors_origins:
                problems.append("SPARKX_CORS_ORIGINS must not contain '*' with cookie auth")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
