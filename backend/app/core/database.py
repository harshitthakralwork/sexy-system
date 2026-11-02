from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def build_engine_and_maker(
    url: str | None = None, *, pooled: bool = True
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create an engine and its session factory.

    `pooled=False` uses NullPool, which is what anything spanning more than one
    event loop must use: a pooled connection belongs to the loop that opened it,
    and reusing it from another loop fails with "Event loop is closed" at the
    most confusing possible moment.
    """
    settings = get_settings()
    if pooled:
        engine = create_async_engine(
            url or settings.database_url,
            echo=settings.database_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
        )
    else:
        # NullPool takes no sizing arguments; passing them raises TypeError.
        engine = create_async_engine(
            url or settings.database_url,
            echo=settings.database_echo,
            poolclass=NullPool,
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request, from the engine that belongs to *this* app.

    The engine lives on `app.state` rather than in a module global. A global
    engine outlives the event loop that created it, which is invisible in
    production (one app, one loop) and fatal in tests and scripts that build
    several clients.
    """
    maker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    session = maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Standalone session for workers and scripts, outside a request.

    Builds a short-lived, unpooled engine so it is safe to call from `asyncio.run`
    anywhere, including inside a test that already has a loop of its own.
    """
    engine, maker = build_engine_and_maker(pooled=False)
    session = maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        await engine.dispose()


async def check_database_connection() -> bool:
    """Health probe. Returns False rather than raising when the database is down."""
    from sqlalchemy import text

    engine: AsyncEngine | None = getattr(_health_probe_state, "engine", None)
    try:
        if engine is None:
            return False
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health probe must not raise
        return False


class _HealthProbeState:
    engine: AsyncEngine | None = None


_health_probe_state = _HealthProbeState()


def register_health_probe_engine(engine: AsyncEngine | None) -> None:
    """Point the readiness probe at the running app's engine.

    Readiness must report on the connection the application actually uses, not
    on a second one that happens to work.
    """
    _health_probe_state.engine = engine
