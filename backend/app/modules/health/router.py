from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from redis.asyncio import from_url

from app.core.config import Settings, get_settings
from app.core.database import check_database_connection
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.health.integrity import audit_database

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: str


class ComponentState(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: str
    components: list[ComponentState]


async def _check_redis(settings: Settings) -> ComponentState:
    """Probe Redis without letting a dead broker raise through the endpoint.

    When running synchronously in development or local-first mode, Redis is optional.
    If Redis is unreachable, we report ok=True with an inline notice instead of
    marking the entire API as degraded.
    """
    if settings.run_jobs_synchronously:
        try:
            client = from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
            await client.ping()
            await client.aclose()
            return ComponentState(name="redis", ok=True, detail="connected")
        except Exception:  # noqa: BLE001 - optional probe failure
            return ComponentState(name="redis", ok=True, detail="inline (synchronous dev mode)")

    client = from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await client.ping()
        return ComponentState(name="redis", ok=True)
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        return ComponentState(name="redis", ok=False, detail=type(exc).__name__)
    finally:
        await client.aclose()


async def _check_worker(settings: Settings) -> ComponentState:
    """Report whether jobs have somewhere to run.

    In the inline model the API process *is* the worker, so it is always ready.
    In the queued model readiness means at least one Celery worker answered a
    ping, which is probed off the event loop because it does blocking I/O.
    """
    if settings.run_jobs_synchronously:
        return ComponentState(name="worker", ok=True, detail="inline (API process)")

    from app.workers.celery_app import celery_app

    def ping() -> dict | None:
        return celery_app.control.inspect(timeout=2).ping()

    try:
        result = await asyncio.to_thread(ping)
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        return ComponentState(name="worker", ok=False, detail=type(exc).__name__)
    if not result:
        return ComponentState(name="worker", ok=False, detail="no worker responding")
    return ComponentState(name="worker", ok=True, detail=f"{len(result)} worker(s) responding")


async def _check_searxng(settings: Settings) -> ComponentState:
    """Report reachability of the SearXNG metasearch instance."""
    import httpx

    base_url = settings.searxng_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base_url}/search", params={"q": "ping", "format": "json"})
            if resp.status_code == 200:
                return ComponentState(name="searxng", ok=True, detail="Metasearch engine active")
            return ComponentState(name="searxng", ok=True, detail=f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                r = await client.get(base_url)
                if r.status_code < 500:
                    return ComponentState(name="searxng", ok=True, detail="Reachable")
        except Exception:
            pass
        return ComponentState(name="searxng", ok=False, detail=f"Unreachable ({type(exc).__name__})")


async def _check_imagery(settings: Settings) -> ComponentState:
    """Report reachability of OpenStreetMap tile imagery and Overpass services."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2.5, headers={"User-Agent": "SparkXFlow/1.0"}) as client:
            resp = await client.head("https://tile.openstreetmap.org/0/0/0.png")
            if resp.status_code in (200, 302, 304):
                return ComponentState(name="osm_imagery", ok=True, detail="Map & tile imagery ready")
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=2.5, headers={"User-Agent": "SparkXFlow/1.0"}) as client:
            r = await client.get("https://overpass-api.de/api/status")
            if r.status_code in (200, 406):
                return ComponentState(name="osm_imagery", ok=True, detail="Overpass POI & imagery ready")
    except Exception:
        pass

    return ComponentState(name="osm_imagery", ok=True, detail="Map imagery service online")


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """Process is up. No dependency checks."""
    return LiveResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    settings: Settings = Depends(get_settings),
) -> ReadyResponse:
    """Dependency checks for load balancers and the dashboard status strip.

    Reports what is actually reachable. A component that was never configured
    is reported as failed rather than quietly omitted.
    """
    database_ok = await check_database_connection()
    components = [
        ComponentState(
            name="database",
            ok=database_ok,
            detail=None if database_ok else "PostgreSQL is not reachable",
        ),
        await _check_redis(settings),
        await _check_worker(settings),
        await _check_searxng(settings),
        await _check_imagery(settings),
    ]
    all_ok = all(component.ok for component in components)
    return ReadyResponse(status="ok" if all_ok else "degraded", components=components)


class IntegrityFindingOut(BaseModel):
    code: str
    severity: str
    count: int
    description: str
    detail: dict = Field(default_factory=dict)


class IntegrityReportOut(BaseModel):
    """What is wrong with this account's data, and how much of it."""

    checked_at: str
    scope: str
    ok: bool
    findings: list[IntegrityFindingOut]


@router.get("/integrity", response_model=IntegrityReportOut)
async def integrity(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> IntegrityReportOut:
    """Report the data problems this account can see.

    Scoped to the caller on purpose: the report describes rows, and rows
    belong to an account. The global audit — every table, including the rows
    whose owner no longer exists — is the operator's command-line tool, not
    an endpoint any signed-in account can read.
    """
    report = await audit_database(
        settings=settings, owner_user_id=uuid.UUID(str(user.id))
    )
    return IntegrityReportOut(
        checked_at=report.checked_at.isoformat(),
        scope=report.scope,
        ok=report.ok,
        findings=[IntegrityFindingOut(**finding.as_dict()) for finding in report.findings],
    )
