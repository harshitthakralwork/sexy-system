from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[Path, ...]:
    """Absolute candidate paths for the environment file.

    A relative `env_file=".env"` resolves against the *current working
    directory*, so the backend silently ran on defaults whenever it was started
    from anywhere other than the repo root — pytest from `backend/` included.
    Configuration that loads sometimes is worse than configuration that is
    missing, because it looks applied.
    """
    here = Path(__file__).resolve()
    backend_dir = here.parents[2]  # .../sparkxflow-nexus/backend
    repo_root = backend_dir.parent  # .../sparkxflow-nexus
    return (repo_root / ".env", backend_dir / ".env")


class Settings(BaseSettings):
    """Application settings, loaded from environment variables.

    Variable names are the field names below, prefixed with ``SPARKX_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="SPARKX_",
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SparkXFlow Nexus"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"

    # 127.0.0.1 rather than `localhost`: Windows may resolve that name to ::1
    # first, and a server bound to the IPv4 loopback is then "unreachable" with
    # nothing actually wrong.
    database_url: str = "postgresql+asyncpg://sparkx:sparkx@127.0.0.1:5432/sparkxflow"
    database_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"
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

    csrf_cookie_name: str = "sparkx_csrf"
    csrf_header_name: str = "X-CSRF-Token"

    password_min_length: int = 12
    allow_registration: bool = True

    login_max_attempts: int = 10
    login_window_seconds: int = 300
    register_max_attempts: int = 5
    register_window_seconds: int = 3600

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

    overpass_base_url: str = "https://overpass-api.de"
    overpass_timeout_seconds: float = 90.0

    reddit_base_url: str = "https://www.reddit.com"
    reddit_user_agent: str = "sparkxflow-nexus/0.1 (local research tool)"
    reddit_timeout_seconds: float = 20.0

    # Social & Demand Intelligence Engine — keyless sources. Hacker News and
    # RSS/Atom need no credentials; SearXNG (above) is reused for publicly
    # indexed-snippet search. Each is bounded independently of configuration.
    hn_base_url: str = "https://hn.algolia.com"
    hn_timeout_seconds: float = 20.0
    rss_timeout_seconds: float = 20.0
    rss_max_entries_per_feed: int = 100
    social_max_query_terms: int = 10
    social_user_agent: str = "sparkxflow-nexus/0.1 (local research tool)"

    # Email sending (Automation Engine). SMTP is the first adapter because it is
    # testable without credentials; Gmail OAuth stays credential-gated. Secrets
    # live in the environment, referenced by `secret_reference` in the database.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_from_email: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    # Geographic discovery ceilings. Set from the D4 measurements in
    # PROJECT_STATUS.md section 9: a 78.5 km² circle took 36-45 s on the public
    # interpreter, and smaller/faster units are what keep a job from timing out —
    # but more units is exactly what a saturated endpoint cannot absorb, so tiles
    # stay modest and the per-job request budget stays tight on purpose.
    discovery_max_area_km2: float = 2500.0
    discovery_tile_target_area_km2: float = 25.0
    discovery_max_tiles_per_job: int = 40
    # One level of subdivision. Deep recursion multiplies requests against shared
    # infrastructure that is already refusing queries.
    discovery_max_tile_depth: int = 1
    discovery_max_results_per_job: int = 20_000
    map_max_features_per_viewport: int = 1500

    default_region: str = "IN"
    export_dir: Path = Path("var/exports")
    retention_raw_days: int = 15
    retention_enrichment_days: int = 15
    # A job whose worker died mid-run leaves a row stuck in `running`. The
    # maintenance pass marks such rows failed after this long without completion,
    # so they can be retried instead of looking busy forever. Generous on purpose:
    # a legitimate tiled sweep can run for well over an hour.
    stale_job_after_seconds: int = 6 * 3600

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

    @field_validator("overpass_timeout_seconds")
    @classmethod
    def _bounded_overpass_timeout(cls, value: float) -> float:
        # D4 measured a 5 km / 50-element query completing in 37 seconds on the
        # public interpreter under load. A 60-second ceiling would time out on
        # work that was succeeding; the ceiling is still hard, because an
        # unbounded wait against shared infrastructure is a self-inflicted DoS.
        if not 1.0 <= value <= 120.0:
            raise ValueError("overpass_timeout_seconds must be between 1 and 120")
        return value

    @field_validator("reddit_timeout_seconds")
    @classmethod
    def _bounded_reddit_timeout(cls, value: float) -> float:
        if not 1.0 <= value <= 60.0:
            raise ValueError("reddit_timeout_seconds must be between 1 and 60")
        return value

    @field_validator("hn_timeout_seconds", "rss_timeout_seconds")
    @classmethod
    def _bounded_social_timeout(cls, value: float) -> float:
        if not 1.0 <= value <= 60.0:
            raise ValueError("social source timeout must be between 1 and 60")
        return value

    @field_validator("rss_max_entries_per_feed")
    @classmethod
    def _bounded_rss_entries(cls, value: int) -> int:
        if not 1 <= value <= 500:
            raise ValueError("rss_max_entries_per_feed must be between 1 and 500")
        return value

    @field_validator("social_max_query_terms")
    @classmethod
    def _bounded_social_terms(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("social_max_query_terms must be between 1 and 50")
        return value

    @field_validator("smtp_port")
    @classmethod
    def _bounded_smtp_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("smtp_port must be between 1 and 65535")
        return value

    @field_validator("discovery_max_tiles_per_job")
    @classmethod
    def _bounded_tiles(cls, value: int) -> int:
        # Each tile is a request against shared public infrastructure. A number
        # this high is already aggressive; the ceiling exists to be argued down
        # from measurement, never up for convenience.
        if not 1 <= value <= 400:
            raise ValueError("discovery_max_tiles_per_job must be between 1 and 400")
        return value

    @field_validator("discovery_max_area_km2", "discovery_tile_target_area_km2")
    @classmethod
    def _bounded_area_settings(cls, value: float) -> float:
        if not 0.01 <= value <= 10_000.0:
            raise ValueError("area settings must be between 0.01 and 10000 km2")
        return value

    @field_validator("discovery_max_tile_depth")
    @classmethod
    def _bounded_depth(cls, value: int) -> int:
        if not 0 <= value <= 4:
            raise ValueError("discovery_max_tile_depth must be between 0 and 4")
        return value

    @field_validator("map_max_features_per_viewport", "discovery_max_results_per_job")
    @classmethod
    def _bounded_feature_counts(cls, value: int) -> int:
        if not 1 <= value <= 50_000:
            raise ValueError("map and job result counts must be between 1 and 50000")
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

    @field_validator("stale_job_after_seconds")
    @classmethod
    def _bounded_stale_window(cls, value: int) -> int:
        if not 300 <= value <= 7 * 24 * 3600:
            raise ValueError("stale_job_after_seconds must be between 300 and 604800")
        return value

    @field_validator("password_min_length")
    @classmethod
    def _valid_password_length(cls, value: int) -> int:
        if value < 10:
            raise ValueError("password_min_length must be at least 10")
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
            # Open registration turns a private tool into a hosted one. Deliberate,
            # never accidental.
            if self.allow_registration:
                problems.append(
                    "SPARKX_ALLOW_REGISTRATION must be false unless multi-user signup is intended"
                )
            # CSRF tokens are HMAC-signed. Development falls back to a fixed,
            # documented key; in production that fallback is a predictable token,
            # which is worse than having no check at all.
            if not self.signing_secret:
                problems.append(
                    "SPARKX_SIGNING_SECRET is required for CSRF protection in production"
                )
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
