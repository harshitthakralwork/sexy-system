from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import from_url

from app.core.config import Settings, get_settings
from app.core.database import check_database_connection

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
    """Probe Redis without letting a dead broker raise through the endpoint."""
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
    ]
    all_ok = all(component.ok for component in components)
    return ReadyResponse(status="ok" if all_ok else "degraded", components=components)
