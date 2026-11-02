from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.discovery_doubles import stub_adapters  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _inline_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery jobs run inline, whatever the operator's `.env` says.

    A machine configured for Celery would otherwise pass the job tests having
    proved only that a job can be queued, not that a job runs.
    """
    monkeypatch.setenv("SPARKX_RUN_JOBS_SYNCHRONOUSLY", "true")
    from app.core import config as config_module

    config_module.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """The limiter is process-wide on purpose; tests must not inherit each other's
    counters. Without this, the fifth registration in the suite starts failing and
    the cause looks like a product bug."""
    from app.core.ratelimit import get_rate_limiter

    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


def signed_in_client() -> TestClient:
    """A TestClient with its lifespan running.

    The engine is built during startup, so a client created without the context
    manager has no database to serve requests from.
    """
    from app.main import create_app

    client = TestClient(create_app())
    client.__enter__()
    return client


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """App with lifespan running, for endpoints that need no database."""
    with TestClient(create_app()) as test_client:
        yield test_client


def _database_reachable() -> bool:
    import asyncio

    import asyncpg

    from app.core.config import get_settings

    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")

    async def probe() -> bool:
        try:
            connection = await asyncpg.connect(dsn=dsn, timeout=3)
        except Exception:  # noqa: BLE001 - any failure means "not available"
            return False
        await connection.close()
        return True

    try:
        return asyncio.run(probe())
    except RuntimeError:  # pragma: no cover - no event loop available
        return False


@pytest.fixture(scope="session")
def database_available() -> bool:
    """Probed once per session rather than once per test."""
    return _database_reachable()


@dataclass(frozen=True)
class Session:
    """A signed-in client plus what it needs to make state changes."""

    email: str
    password: str
    user_id: str
    csrf: str
    api: TestClient

    def csrf_headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf}


@pytest.fixture()
def make_account(
    database_available: bool, request: pytest.FixtureRequest
) -> Iterator[Callable[[], Session]]:
    """Register and sign in real accounts against the real database.

    Each account gets its own cookie jar, which is the whole point: cross-owner
    tests are meaningless if both users share one client. Rows are deleted by
    owner id afterwards so the development database stays explainable.
    """
    if not database_available:
        pytest.skip("no reachable PostgreSQL; these tests exercise real persistence")

    import asyncio

    import asyncpg

    from app.core.config import get_settings

    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    created_user_ids: list[str] = []
    open_clients: list[TestClient] = []

    def factory() -> Session:
        email = f"test-{uuid.uuid4()}@sparkxflow.dev"
        password = "correct-horse-battery-staple"

        api = TestClient(create_app())
        api.__enter__()
        open_clients.append(api)
        request.addfinalizer(api.__exit__)

        registered = api.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": "Test User"},
        )
        assert registered.status_code == 201, registered.text
        user_id = registered.json()["id"]

        logged_in = api.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert logged_in.status_code == 200, logged_in.text

        created_user_ids.append(user_id)
        return Session(email, password, user_id, logged_in.json()["csrf_token"], api)

    yield factory

    for api in open_clients:
        with contextlib.suppress(Exception):
            api.__exit__(None, None, None)

    async def cleanup() -> None:
        connection = await asyncpg.connect(dsn=dsn, timeout=10)
        try:
            for raw_id in created_user_ids:
                user_id = uuid.UUID(raw_id)
                await connection.execute(
                    "delete from business_tags where business_id in"
                    " (select id from businesses where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute(
                    "delete from business_contacts where business_id in"
                    " (select id from businesses where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute(
                    "delete from business_notes where owner_user_id = $1", user_id
                )
                await connection.execute(
                    "delete from crm_stage_history where crm_record_id in"
                    " (select id from crm_business_records where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute(
                    "delete from crm_activities where owner_user_id = $1", user_id
                )
                await connection.execute(
                    "delete from crm_business_records where owner_user_id = $1", user_id
                )
                await connection.execute(
                    "delete from crm_stages where pipeline_id in"
                    " (select id from crm_pipelines where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute(
                    "delete from crm_pipelines where owner_user_id = $1", user_id
                )
                await connection.execute(
                    "delete from opportunity_evidence where opportunity_id in"
                    " (select id from business_opportunities where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute(
                    "delete from business_opportunities where owner_user_id = $1", user_id
                )
                await connection.execute(
                    "delete from scoring_rules where service_profile_id in"
                    " (select id from service_profiles where service_id in"
                    " (select id from services where owner_user_id = $1))",
                    user_id,
                )
                await connection.execute(
                    "delete from service_profiles where service_id in"
                    " (select id from services where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute("delete from services where owner_user_id = $1", user_id)
                await connection.execute(
                    "delete from source_record_links where source_record_id in"
                    " (select id from source_records where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute(
                    "delete from source_records where owner_user_id = $1", user_id
                )
                await connection.execute(
                    "delete from job_logs where job_id in"
                    " (select id from discovery_jobs where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute(
                    "delete from discovery_jobs where owner_user_id = $1", user_id
                )
                await connection.execute("delete from searches where owner_user_id = $1", user_id)
                await connection.execute("delete from social_content where owner_user_id = $1", user_id)
                await connection.execute("delete from social_profiles where owner_user_id = $1", user_id)
                await connection.execute(
                    "delete from social_research_queries where owner_user_id = $1", user_id
                )
                await connection.execute(
                    "delete from business_social_profiles where business_id in"
                    " (select id from businesses where owner_user_id = $1)",
                    user_id,
                )
                await connection.execute("delete from businesses where owner_user_id = $1", user_id)
                await connection.execute("delete from tags where owner_user_id = $1", user_id)
                await connection.execute(
                    "delete from startup_watchlists where owner_user_id = $1", user_id
                )
                await connection.execute("delete from startups where owner_user_id = $1", user_id)
                await connection.execute("delete from audit_logs where owner_user_id = $1", user_id)
                await connection.execute("delete from user_sessions where user_id = $1", user_id)
                await connection.execute("delete from user_settings where user_id = $1", user_id)
                await connection.execute("delete from users where id = $1", user_id)
        finally:
            await connection.close()

    asyncio.run(cleanup())


@pytest.fixture()
def session_account(make_account: Callable[[], Session]) -> Session:
    return make_account()
