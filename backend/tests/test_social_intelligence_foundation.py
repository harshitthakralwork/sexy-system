"""Social & Demand Intelligence Engine — Phase 1 foundation schema.

These tests exercise the additive tables against real PostgreSQL, through a real
signed-in owner so the rows are cleaned up exactly like every other module: the
tracks and runs persist, the CHECK vocabularies reject the wrong values, and a
track's owner scoping holds.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import session_scope
from app.modules.social.models import (
    SocialDiscoveryRun,
    SocialSearchTrack,
)
from tests.conftest import Session


def _create_track(
    owner: uuid.UUID, *, track_type: str = "demand", max_results: int = 50
) -> uuid.UUID:
    async def run() -> uuid.UUID:
        async with session_scope() as session:
            track = SocialSearchTrack(
                owner_user_id=owner,
                name="Web agency demand",
                track_type=track_type,
                keywords=["looking for web developer"],
                platforms=["reddit", "hackernews"],
                max_results_per_run=max_results,
            )
            session.add(track)
            await session.flush()
            return track.id

    return asyncio.run(run())


def _create_run(owner: uuid.UUID, track_id: uuid.UUID, *, status: str = "pending") -> uuid.UUID:
    async def run() -> uuid.UUID:
        async with session_scope() as session:
            record = SocialDiscoveryRun(
                owner_user_id=owner,
                track_id=track_id,
                status=status,
                trigger_type="manual",
            )
            session.add(record)
            await session.flush()
            return record.id

    return asyncio.run(run())


def _load_run(run_id: uuid.UUID) -> dict:
    async def run() -> dict:
        async with session_scope() as session:
            record = await session.get(SocialDiscoveryRun, run_id)
            assert record is not None
            return {"status": record.status, "track_id": str(record.track_id)}

    return asyncio.run(run())


def _count_tracks(owner: uuid.UUID) -> int:
    async def run() -> int:
        async with session_scope() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(SocialSearchTrack)
                    .where(SocialSearchTrack.owner_user_id == owner)
                )
                or 0
            )

    return asyncio.run(run())


def test_track_and_run_roundtrip(session_account: Session) -> None:
    owner = uuid.UUID(session_account.user_id)
    track_id = _create_track(owner)
    run_id = _create_run(owner, track_id)

    record = _load_run(run_id)
    assert record["status"] == "pending"
    assert record["track_id"] == str(track_id)


def test_track_rejects_unknown_type(session_account: Session) -> None:
    owner = uuid.UUID(session_account.user_id)

    async def run() -> None:
        async with session_scope() as session:
            session.add(SocialSearchTrack(owner_user_id=owner, name="bad", track_type="nonsense"))
            await session.flush()

    with pytest.raises(IntegrityError):
        asyncio.run(run())


def test_track_rejects_zero_max_results(session_account: Session) -> None:
    owner = uuid.UUID(session_account.user_id)

    async def run() -> None:
        async with session_scope() as session:
            session.add(
                SocialSearchTrack(
                    owner_user_id=owner, name="bad", track_type="demand", max_results_per_run=0
                )
            )
            await session.flush()

    with pytest.raises(IntegrityError):
        asyncio.run(run())


def test_run_rejects_unknown_status(session_account: Session) -> None:
    owner = uuid.UUID(session_account.user_id)
    track_id = _create_track(owner)

    async def run() -> None:
        async with session_scope() as session:
            session.add(
                SocialDiscoveryRun(owner_user_id=owner, track_id=track_id, status="half_done")
            )
            await session.flush()

    with pytest.raises(IntegrityError):
        asyncio.run(run())


def test_tracks_are_owner_scoped(
    session_account: Session, make_account
) -> None:
    owner = uuid.UUID(session_account.user_id)
    other = uuid.UUID(make_account().user_id)
    _create_track(owner)
    assert _count_tracks(owner) == 1
    assert _count_tracks(other) == 0
