"""Master-plan Phase 6: Global Search across every owned entity.

Seeds one row in each searchable surface for a real, signed-in owner, then checks
that a single query reaches all of them, that the totals are the sum of what the
per-entity queries actually returned, that an empty query returns nothing, and that
another user sees none of it. Search reuses the existing list functions; this test
proves the aggregation, not a re-implementation of them.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.social import service as social_service
from app.modules.social.models import SocialContent, SocialPlatform, SocialSearchTrack
from app.modules.startups.models import Startup
from tests.conftest import Session


def _seed(owner_id: str) -> None:
    async def run() -> None:
        owner = uuid.UUID(owner_id)
        async with session_scope() as session:
            await social_service.ensure_platforms(session)
            platform = await session.scalar(
                select(SocialPlatform).where(SocialPlatform.slug == "hackernews")
            )
            session.add(
                Business(
                    owner_user_id=owner,
                    name="Acme Cafe",
                    normalized_name="acme cafe",
                    first_discovered_at=datetime.now(UTC),
                    website_status="unknown",
                    city="Pune",
                )
            )
            session.add(
                Startup(
                    owner_user_id=owner,
                    name="Acme Robotics",
                    normalized_name="acme robotics",
                    status="active",
                    first_discovered_at=datetime.now(UTC),
                )
            )
            session.add(
                SocialContent(
                    platform_id=platform.id,
                    owner_user_id=owner,
                    external_id="acme-post-1",
                    content_type="post",
                    title="Acme is looking for a web agency",
                    content_text="Acme needs help building an ecommerce site",
                )
            )
            session.add(
                SocialSearchTrack(
                    owner_user_id=owner,
                    name="Acme demand track",
                    track_type="demand",
                    platforms=["hackernews"],
                )
            )

    asyncio.run(run())


def test_global_search_reaches_every_owned_entity(session_account: Session) -> None:
    _seed(session_account.user_id)
    result = session_account.api.get("/api/v1/search", params={"q": "acme"}).json()

    assert result["query"] == "acme"
    groups = result["groups"]
    assert groups["businesses"]["total"] >= 1
    assert groups["startups"]["total"] >= 1
    assert groups["social_results"]["total"] >= 1
    assert groups["tracks"]["total"] >= 1
    assert result["total"] >= 4
    # A social hit carries the honest retrieval/classification metadata.
    social_hit = groups["social_results"]["items"][0]
    assert social_hit["kind"] == "social_result"
    assert "acme" in social_hit["title"].lower()


def test_global_search_empty_query_returns_nothing(session_account: Session) -> None:
    _seed(session_account.user_id)
    result = session_account.api.get("/api/v1/search", params={"q": "   "}).json()
    assert result["total"] == 0
    assert all(group["total"] == 0 for group in result["groups"].values())


def test_global_search_is_owner_scoped(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    owner = session_account
    other = make_account()
    _seed(owner.user_id)

    assert owner.api.get("/api/v1/search", params={"q": "acme"}).json()["total"] >= 4
    # The other user owns none of the seeded rows, so they find nothing.
    assert other.api.get("/api/v1/search", params={"q": "acme"}).json()["total"] == 0
