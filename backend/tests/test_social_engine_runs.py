"""Social & Demand Intelligence Engine — Phase 4 track run tests.

The connector wire is the only thing faked; the orchestrator, run record, dedup,
classification and persistence run for real against PostgreSQL. These tests prove
the loop the directive demands: a track runs, its sources are attempted one by one,
a refused source is recorded rather than fatal, results are stored and classified,
a re-run deduplicates instead of inflating, and each owner sees only their own.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from app.core.database import session_scope
from app.modules.discovery.adapters.base import (
    AdapterCapabilities,
    AdapterError,
    HealthResult,
)
from app.modules.social import tracks
from app.modules.social.adapters import SocialResult
from app.modules.social.models import (
    SocialContent,
    SocialDiscoveryRun,
    SocialSearchTrack,
)
from app.modules.social.schemas import TrackCreateIn
from tests.conftest import Session

DEMAND_TEXT = "Looking for a web development agency to rebuild our site"
TUTORIAL_TEXT = "A tutorial on how to build a website from scratch"


class FakeAdapter:
    """Stands in for a connector. Hacker News yields; anything else refuses."""

    def __init__(self, key: str) -> None:
        self.key = key

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key=self.key,
            name=f"Fake {self.key}",
            slug=self.key,
            category="social",
            supported_query_types=("keyword",),
            supported_filters=(),
            available_fields=("title",),
            geographic_coverage="test",
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        return None

    async def search(self, config: dict[str, Any]) -> list[SocialResult]:
        if self.key != "hackernews":
            raise AdapterError(f"{self.key} refused", classification="access_denied")
        return [
            SocialResult(
                external_id="hn1",
                content_url="https://news.ycombinator.com/item?id=hn1",
                content_type="post",
                content_text=DEMAND_TEXT,
                published_at=None,
                raw_data={"title": DEMAND_TEXT[:40]},
            ),
            SocialResult(
                external_id="hn2",
                content_url="https://news.ycombinator.com/item?id=hn2",
                content_type="post",
                content_text=TUTORIAL_TEXT,
                published_at=None,
                raw_data={"title": TUTORIAL_TEXT[:40]},
            ),
        ]

    async def health_check(self) -> HealthResult:
        return HealthResult(status="working")

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def fake_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracks, "_build_adapter", lambda settings, key: FakeAdapter(key))


async def _make_track_async(
    owner: uuid.UUID, *, platforms: list[str], freq: dict | None = None
) -> uuid.UUID:
    async with session_scope() as session:
        data = TrackCreateIn(
            name="Agency demand track",
            track_type="demand",
            keywords=["web development agency"],
            platforms=platforms,
            frequency_config=freq,
        )
        track = await tracks.create_track(session, owner, data)
        return track.id


async def _pending_run_async(owner: uuid.UUID, track_id: uuid.UUID) -> uuid.UUID:
    async with session_scope() as session:
        run_row = SocialDiscoveryRun(
            owner_user_id=owner, track_id=track_id, status="pending", trigger_type="manual"
        )
        session.add(run_row)
        await session.flush()
        return run_row.id


async def _run_row_async(run_id: uuid.UUID) -> dict:
    async with session_scope() as session:
        row = await session.get(SocialDiscoveryRun, run_id)
        assert row is not None
        return {
            "status": row.status,
            "stored_new": row.stored_new,
            "duplicates": row.duplicates,
            "results_returned": row.results_returned,
            "classification_counts": row.classification_counts,
            "error_summary": row.error_summary,
            "duration_ms": row.duration_ms,
        }


async def _count_content_async(owner: uuid.UUID) -> int:
    async with session_scope() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(SocialContent)
                .where(SocialContent.owner_user_id == owner)
            )
            or 0
        )


async def _content_async(owner: uuid.UUID, external_id: str) -> dict:
    async with session_scope() as session:
        row = await session.scalar(
            select(SocialContent).where(
                SocialContent.owner_user_id == owner, SocialContent.external_id == external_id
            )
        )
        assert row is not None
        return {
            "classification": row.classification,
            "confidence": float(row.confidence_score or 0),
            "track_type": row.track_type,
            "retrieval_status": row.retrieval_status,
            "attribution": row.source_attribution,
        }


async def _make_due_track_async(owner: uuid.UUID) -> uuid.UUID:
    async with session_scope() as session:
        data = TrackCreateIn(
            name="Scheduled track",
            track_type="demand",
            keywords=["web development agency"],
            platforms=["hackernews"],
            frequency_config={"interval_seconds": 3600},
        )
        track = await tracks.create_track(session, owner, data)
        track.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.flush()
        return track.id


async def _track_state_async(owner: uuid.UUID) -> dict:
    async with session_scope() as session:
        run_row = await session.scalar(
            select(SocialDiscoveryRun).where(
                SocialDiscoveryRun.owner_user_id == owner,
                SocialDiscoveryRun.trigger_type == "scheduled",
            )
        )
        track = await session.scalar(
            select(SocialSearchTrack).where(SocialSearchTrack.owner_user_id == owner)
        )
        assert run_row is not None and track is not None
        return {
            "status": run_row.status,
            "next_run": track.next_run_at,
            "last": track.last_run_at,
        }


# --- Core run: persist + classify ------------------------------------------


def test_run_track_persists_and_classifies(session_account: Session, fake_sources: None) -> None:
    owner = uuid.UUID(session_account.user_id)

    async def scenario() -> tuple[dict, dict, dict]:
        track_id = await _make_track_async(owner, platforms=["hackernews"])
        run_id = await _pending_run_async(owner, track_id)
        status = await tracks.execute_track_run(run_id)
        record = await _run_row_async(run_id)
        hn1 = await _content_async(owner, "hn1")
        hn2 = await _content_async(owner, "hn2")
        return {"status": status} | record, hn1, hn2

    record, hn1, hn2 = asyncio.run(scenario())
    assert record["status"] == "completed"
    assert record["stored_new"] == 2
    assert record["results_returned"] == 2
    assert (
        record["classification_counts"].get("Service needed", 0) >= 1
        or record["classification_counts"].get("Agency Search", 0) >= 1
    )
    assert record["error_summary"] is None
    assert record["duration_ms"] is not None

    assert hn1["classification"] in ("Agency Search", "Service needed")
    assert hn1["confidence"] >= 50
    assert hn1["track_type"] == "demand"
    assert hn2["confidence"] <= 40  # tutorial is not a demand, but is still stored truthfully


def test_re_run_dedups_and_claim_is_idempotent(
    session_account: Session, fake_sources: None
) -> None:
    owner = uuid.UUID(session_account.user_id)

    async def scenario() -> tuple[str, str, dict, int]:
        track_id = await _make_track_async(owner, platforms=["hackernews"])
        run_id = await _pending_run_async(owner, track_id)
        first = await tracks.execute_track_run(run_id)
        again = await tracks.execute_track_run(run_id)  # already past pending → no re-run
        run_id2 = await _pending_run_async(owner, track_id)
        await tracks.execute_track_run(run_id2)
        record2 = await _run_row_async(run_id2)
        count = await _count_content_async(owner)
        return first, again, record2, count

    first, again, record2, count = asyncio.run(scenario())
    assert first == "completed"
    assert again == "completed"
    assert record2["stored_new"] == 0
    assert record2["duplicates"] == 2
    assert count == 2


def test_failing_source_is_a_warning_not_a_crash(
    session_account: Session, fake_sources: None
) -> None:
    owner = uuid.UUID(session_account.user_id)

    async def scenario() -> dict:
        track_id = await _make_track_async(owner, platforms=["hackernews", "rss"])
        run_id = await _pending_run_async(owner, track_id)
        status = await tracks.execute_track_run(run_id)
        record = await _run_row_async(run_id)
        return {"status": status} | record

    record = asyncio.run(scenario())
    assert record["status"] == "completed_with_warnings"
    assert record["stored_new"] == 2  # the working source still stored its results
    assert record["error_summary"] is not None
    assert "rss" in record["error_summary"]


def test_tick_runs_due_tracks(session_account: Session, fake_sources: None) -> None:
    owner = uuid.UUID(session_account.user_id)

    async def scenario() -> tuple[int, dict, int]:
        await _make_due_track_async(owner)
        started = await tracks.run_due_tracks()
        state = await _track_state_async(owner)
        count = await _count_content_async(owner)
        return started, state, count

    started, state, count = asyncio.run(scenario())
    assert started >= 1
    assert count == 2
    assert state["status"] == "completed"
    assert state["last"] is not None
    assert state["next_run"] is not None


# --- HTTP surface -----------------------------------------------------------


def test_track_crud_and_results_over_http(session_account: Session, fake_sources: None) -> None:
    api = session_account.api
    csrf = session_account.csrf_headers()

    created = api.post(
        "/api/v1/social/tracks",
        json={
            "name": "Agency demand",
            "track_type": "demand",
            "keywords": ["web development agency"],
            "platforms": ["hackernews"],
        },
        headers=csrf,
    )
    assert created.status_code == 201, created.text
    track_id = created.json()["id"]

    assert api.get("/api/v1/social/tracks").json()["total"] == 1

    run = api.post(f"/api/v1/social/tracks/{track_id}/run", headers=csrf)
    assert run.status_code == 201, run.text

    runs = api.get(f"/api/v1/social/tracks/{track_id}/runs").json()
    assert runs["total"] == 1
    assert runs["items"][0]["status"] == "completed"

    results = api.get("/api/v1/social/results", params={"track_type": "demand"}).json()
    assert results["total"] == 2
    agency = next(item for item in results["items"] if item["external_id"] == "hn1")
    assert agency["classification"] in ("Agency Search", "Service needed")
    assert agency["confidence_score"] >= 50
    assert agency["evidence"]

    saved = api.post(
        f"/api/v1/social/results/{agency['id']}/save",
        json={"note": "hot lead", "tags": ["priority"]},
        headers=csrf,
    )
    assert saved.status_code == 200, saved.text
    assert api.get("/api/v1/social/saved").json()[0]["note"] == "hot lead"

    export = api.get("/api/v1/social/results/export", params={"track_type": "demand"})
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "Agency Search" in export.text or "Service needed" in export.text


def test_cross_owner_cannot_see_or_run_track(
    session_account: Session, make_account: Callable[[], Session], fake_sources: None
) -> None:
    owner = session_account
    other = make_account()

    created = owner.api.post(
        "/api/v1/social/tracks",
        json={
            "name": "Mine",
            "track_type": "demand",
            "keywords": ["web development agency"],
            "platforms": ["hackernews"],
        },
        headers=owner.csrf_headers(),
    )
    track_id = created.json()["id"]
    owner.api.post(f"/api/v1/social/tracks/{track_id}/run", headers=owner.csrf_headers())

    assert other.api.get("/api/v1/social/tracks").json()["total"] == 0
    assert other.api.get("/api/v1/social/results").json()["total"] == 0
    other_run = other.api.post(
        f"/api/v1/social/tracks/{track_id}/run", headers=other.csrf_headers()
    )
    assert other_run.status_code == 404


def test_run_requires_platforms(session_account: Session) -> None:
    api = session_account.api
    created = api.post(
        "/api/v1/social/tracks",
        json={"name": "No sources", "track_type": "demand", "keywords": ["web agency"]},
        headers=session_account.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    run = api.post(
        f"/api/v1/social/tracks/{created.json()['id']}/run",
        headers=session_account.csrf_headers(),
    )
    assert run.status_code == 409, run.text


# --- Phase 6 integration: alerts, conversion, notifications, JSON export ----


async def _content_id_async(owner: uuid.UUID, external_id: str) -> uuid.UUID:
    async with session_scope() as session:
        row = await session.scalar(
            select(SocialContent).where(
                SocialContent.owner_user_id == owner, SocialContent.external_id == external_id
            )
        )
        assert row is not None
        return row.id


async def _run_demand_track_async(owner: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    track_id = await _make_track_async(owner, platforms=["hackernews"])
    run_id = await _pending_run_async(owner, track_id)
    await tracks.execute_track_run(run_id)
    return track_id, run_id


def test_high_confidence_alert_created_and_deduped(
    session_account: Session, fake_sources: None
) -> None:
    from app.modules.notifications.models import Notification

    owner = uuid.UUID(session_account.user_id)

    async def scenario() -> tuple[int, int, int]:
        await _run_demand_track_async(owner)
        # hn1 classifies Agency Search ~70; threshold 50 alerts it, hn2 (tutorial) not.
        first = await _alerts(owner, 50)
        again = await _alerts(owner, 50)
        async with session_scope() as session:
            count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(
                        Notification.owner_user_id == owner,
                        Notification.notification_type == "social.demand_high_confidence",
                    )
                )
                or 0
            )
        return first, again, count

    first, again, count = asyncio.run(scenario())
    assert first >= 1
    assert again == 0  # dedup: no second alert for the same content
    assert count == first


async def _alerts(owner: uuid.UUID, threshold: float) -> int:
    async with session_scope() as session:
        return await tracks.record_high_confidence_alerts(session, owner, threshold)


def test_convert_creates_business_and_dedups(session_account: Session, fake_sources: None) -> None:
    from app.modules.businesses.models import Business

    owner = uuid.UUID(session_account.user_id)

    async def scenario() -> tuple[uuid.UUID, uuid.UUID, int]:
        await _run_demand_track_async(owner)
        cid = await _content_id_async(owner, "hn1")
        async with session_scope() as session:
            biz1 = await tracks.convert_result_to_lead(session, owner, cid)
        async with session_scope() as session:
            biz2 = await tracks.convert_result_to_lead(session, owner, cid)
        async with session_scope() as session:
            count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Business)
                    .where(Business.owner_user_id == owner, Business.deleted_at.is_(None))
                )
                or 0
            )
        return biz1, biz2, count

    biz1, biz2, count = asyncio.run(scenario())
    assert biz1 == biz2  # domain dedup: no duplicate lead created
    assert count == 1


def test_convert_is_owner_scoped(
    session_account: Session, make_account: Callable[[], Session], fake_sources: None
) -> None:
    from app.core.exceptions import NotFoundError

    owner = uuid.UUID(session_account.user_id)
    other = uuid.UUID(make_account().user_id)

    async def scenario() -> None:
        await _run_demand_track_async(owner)
        cid = await _content_id_async(owner, "hn1")
        async with session_scope() as session:
            with pytest.raises(NotFoundError):
                await tracks.convert_result_to_lead(session, other, cid)

    asyncio.run(scenario())


def test_json_export_and_notifications_over_http(
    session_account: Session, fake_sources: None
) -> None:
    api = session_account.api
    csrf = session_account.csrf_headers()
    created = api.post(
        "/api/v1/social/tracks",
        json={
            "name": "Agency demand",
            "track_type": "demand",
            "keywords": ["web development agency"],
            "platforms": ["hackernews"],
        },
        headers=csrf,
    )
    api.post(f"/api/v1/social/tracks/{created.json()['id']}/run", headers=csrf)

    js = api.get("/api/v1/social/results/export", params={"track_type": "demand", "format": "json"})
    assert js.status_code == 200
    assert js.headers["content-type"].startswith("application/json")
    assert isinstance(js.json(), list)
    assert any(row["platform"] == "hackernews" for row in js.json())

    # Notifications endpoint is reachable and returns the caller's own alerts.
    notes = api.get("/api/v1/social/notifications")
    assert notes.status_code == 200
    assert isinstance(notes.json(), list)
