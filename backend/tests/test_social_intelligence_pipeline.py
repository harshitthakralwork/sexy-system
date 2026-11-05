"""Social & Demand Intelligence Engine — Phase 3 pipeline tests.

Classification is checked as a pure function (a keyword is not a buying signal; a
tutorial is not a demand), and the ingest pipeline is checked against real
PostgreSQL: it normalises, classifies with evidence, deduplicates within a source
and across sources by shared URL, and keeps each owner's intelligence separate.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select

from app.core.database import session_scope
from app.modules.social.adapters import SocialResult
from app.modules.social.classification import classify
from app.modules.social.models import (
    SocialContent,
    SocialSearchTrack,
)
from app.modules.social.pipeline import ingest_results
from app.modules.social.service import ensure_platforms
from tests.conftest import Session

URL_1 = "https://news.ycombinator.com/item?id=hn1"


def _result(external_id: str, text: str, url: str, **extra) -> SocialResult:
    return SocialResult(
        external_id=external_id,
        content_url=url,
        content_type="post",
        content_text=text,
        published_at=None,
        raw_data={"title": text[:40], **extra},
    )


# --- Classification (pure) --------------------------------------------------


def test_demand_intent_with_category_is_confident() -> None:
    outcome = classify("Looking for a web development agency for our launch", "demand")
    assert outcome.category in ("Agency Search", "Service needed")
    assert outcome.confidence >= 50
    assert outcome.evidence
    assert "looking for" in outcome.matched_terms


def test_keyword_without_intent_is_discussion_not_demand() -> None:
    # A bare service keyword is not someone asking for help.
    outcome = classify("We provide web development services in Pune", "demand")
    assert outcome.category in ("General Discussion", "General discussion")
    assert outcome.confidence < 50


def test_negative_context_signal_reduces_confidence() -> None:
    tutorial = classify("Here is a tutorial on how to build a website quickly", "demand")
    assert tutorial.negative_signals
    assert tutorial.confidence <= 40


def test_nothing_matched_is_unclassified_zero() -> None:
    outcome = classify("Weather is nice today", "demand")
    assert outcome.category in ("Unclassified", "Not relevant")
    assert outcome.confidence == 0.0


def test_business_signal_is_classified() -> None:
    outcome = classify(
        "Acme announced a Series A funding round and is now hiring developers", "business"
    )
    assert outcome.category in {
        "Startup",
        "Hiring Signal",
        "Product Launch",
        "Company Expansion",
        "General Company Update",
        "General discussion",
        "Job hiring",
        "Service needed",
    }
    assert outcome.confidence > 0
    assert outcome.method == "rule"


# --- Ingest pipeline (real PostgreSQL) -------------------------------------


def _seed_track(owner: uuid.UUID) -> uuid.UUID:
    async def run() -> uuid.UUID:
        async with session_scope() as session:
            track = SocialSearchTrack(
                owner_user_id=owner,
                name="Web agency demand",
                track_type="demand",
                platforms=["hackernews"],
            )
            session.add(track)
            await session.flush()
            return track.id

    return asyncio.run(run())


def _platform_model():
    from app.modules.social.models import SocialPlatform

    return SocialPlatform


def _ingest_once(
    owner: uuid.UUID, platform_slug: str, track_id: uuid.UUID, results: list[SocialResult]
) -> dict:
    async def run() -> dict:
        async with session_scope() as session:
            await ensure_platforms(session)
            platform = await session.scalar(
                select(_platform_model()).where(_platform_model().slug == platform_slug)
            )
            return await ingest_results(
                session,
                owner_user_id=owner,
                platform=platform,
                track_id=track_id,
                track_type="demand",
                source_id=None,
                results=results,
            )

    return asyncio.run(run())


def _content_for(owner: uuid.UUID, external_id: str) -> dict | None:
    async def run() -> dict | None:
        async with session_scope() as session:
            row = await session.scalar(
                select(SocialContent).where(
                    SocialContent.owner_user_id == owner,
                    SocialContent.external_id == external_id,
                )
            )
            if row is None:
                return None
            return {
                "classification": row.classification,
                "confidence": float(row.confidence_score or 0),
                "evidence": row.evidence,
                "fingerprint": row.dedup_fingerprint,
                "attribution": row.source_attribution,
                "track_type": row.track_type,
            }

    return asyncio.run(run())


def _count_content_for(owner: uuid.UUID) -> int:
    async def run() -> int:
        async with session_scope() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(SocialContent)
                    .where(SocialContent.owner_user_id == owner)
                )
                or 0
            )

    return asyncio.run(run())


def test_ingest_stores_classifies_and_dedups(session_account: Session) -> None:
    owner = uuid.UUID(session_account.user_id)
    track_id = _seed_track(owner)

    results = [
        _result("hn1", "Looking for a web development agency for our launch", URL_1),
        _result("hn2", "A tutorial on how to build a website", URL_1.replace("hn1", "hn2")),
        _result("hn1", "Looking for a web development agency for our launch", URL_1),  # dup
    ]
    outcome = _ingest_once(owner, "hackernews", track_id, results)
    assert outcome["stored_new"] == 2
    assert outcome["duplicates"] == 1

    stored = _content_for(owner, "hn1")
    assert stored is not None
    assert stored["classification"] in ("Agency Search", "Service needed")
    assert stored["confidence"] >= 50
    assert stored["evidence"]
    assert stored["fingerprint"]
    assert stored["track_type"] == "demand"


def test_cross_source_same_url_merges_attribution(session_account: Session) -> None:
    owner = uuid.UUID(session_account.user_id)
    track_id = _seed_track(owner)

    _ingest_once(
        owner, "hackernews", track_id, [_result("hn1", "Need a website built fast", URL_1)]
    )
    # SearXNG finds the same canonical URL under a different external id.
    merged = _ingest_once(
        owner,
        "searxng",
        track_id,
        [_result("sx999", "Need a website built fast", URL_1)],
    )
    assert merged["stored_new"] == 0
    assert merged["duplicates"] == 1

    stored = _content_for(owner, "hn1")
    assert stored is not None
    assert len(stored["attribution"]) == 2  # both sources preserved on the survivor


def test_ingest_is_owner_scoped(session_account: Session, make_account) -> None:
    owner = uuid.UUID(session_account.user_id)
    other_owner = uuid.UUID(make_account().user_id)
    track_id = _seed_track(owner)

    _ingest_once(
        owner, "hackernews", track_id, [_result("hn1", "Need a website built fast", URL_1)]
    )
    assert _count_content_for(owner) == 1
    assert _count_content_for(other_owner) == 0
    assert _content_for(other_owner, "hn1") is None
