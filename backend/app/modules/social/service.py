from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    SourceUnavailableError,
    ValidationFailedError,
)
from app.modules.businesses.models import Business, BusinessSocialProfile
from app.modules.discovery.adapters.base import AdapterError
from app.modules.discovery.public_fetch import fetch_public_page
from app.modules.social.adapters import RedditAdapter, SocialAdapter, SocialResult
from app.modules.social.connectors import (
    BlueskyAdapter,
    FacebookAdapter,
    HackerNewsAdapter,
    InstagramAdapter,
    JustdialAdapter,
    LinkedInAdapter,
    MastodonAdapter,
    RssAtomAdapter,
    SearxngSocialAdapter,
    StackOverflowAdapter,
    XSocialAdapter,
    YouTubeAdapter,
)
from app.modules.social.models import (
    SocialContent,
    SocialPlatform,
    SocialProfile,
    SocialResearchQuery,
)
from app.modules.social.platforms import (
    ENABLED_ADAPTER_KEYS,
    PLATFORM_DEFINITIONS,
    SOCIAL_MVP_PLATFORM_SLUGS,
)
from app.modules.sources.registry import ensure_source
from app.shared.normalization import MAX_URL_LENGTH, sanitize_text


async def ensure_platforms(session: AsyncSession) -> list[SocialPlatform]:
    """Seed the platform catalogue, idempotently by slug.

    The catalogue is data, not code, so an operator can disable a platform or
    edit its limitations without a deploy. Descriptions come from the honest
    definitions in `platforms.py`, never optimistic placeholders.
    """
    existing = {
        row.slug: row
        for row in (await session.scalars(select(SocialPlatform))).all()
    }
    created: list[SocialPlatform] = []
    for definition in PLATFORM_DEFINITIONS:
        row = existing.get(definition["slug"])
        if row is None:
            row = SocialPlatform(
                name=definition["name"],
                slug=definition["slug"],
                adapter_key=definition["adapter_key"],
                capabilities=definition["capabilities"],
                limitations=definition["limitations"],
                is_enabled=definition["slug"] in SOCIAL_MVP_PLATFORM_SLUGS,
            )
            session.add(row)
            created.append(row)
        else:
            row.name = definition["name"]
            row.adapter_key = definition["adapter_key"]
            row.capabilities = definition["capabilities"]
            row.limitations = definition["limitations"]
            row.is_enabled = definition["slug"] in SOCIAL_MVP_PLATFORM_SLUGS
    await session.flush()
    return list(existing.values()) + created


async def list_platforms(session: AsyncSession) -> list[SocialPlatform]:
    await ensure_platforms(session)
    rows = await session.scalars(select(SocialPlatform).order_by(SocialPlatform.name))
    return list(rows)


async def _get_platform_by_slug(session: AsyncSession, slug: str) -> SocialPlatform | None:
    return await session.scalar(select(SocialPlatform).where(SocialPlatform.slug == slug))


async def _get_platform(session: AsyncSession, platform_id: uuid.UUID) -> SocialPlatform | None:
    return await session.scalar(
        select(SocialPlatform).where(SocialPlatform.id == platform_id)
    )


def _build_adapter(settings: Settings, adapter_key: str) -> SocialAdapter:
    if adapter_key == "reddit":
        return RedditAdapter(
            settings.reddit_base_url,
            user_agent=settings.reddit_user_agent,
            timeout_seconds=settings.reddit_timeout_seconds,
            searxng_base_url=settings.searxng_base_url,
        )
    if adapter_key == "hackernews":
        return HackerNewsAdapter(
            settings.hn_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.hn_timeout_seconds,
        )
    if adapter_key == "rss":
        return RssAtomAdapter(
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.rss_timeout_seconds,
            max_entries_per_feed=settings.rss_max_entries_per_feed,
        )
    if adapter_key == "searxng":
        return SearxngSocialAdapter(
            settings.searxng_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.searxng_timeout_seconds,
            results_per_page=settings.searxng_results_per_page,
        )
    if adapter_key == "stackoverflow":
        return StackOverflowAdapter(
            settings.stackoverflow_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.social_timeout_seconds,
        )
    if adapter_key == "bluesky":
        return BlueskyAdapter(
            settings.bluesky_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.social_timeout_seconds,
        )
    if adapter_key == "mastodon":
        return MastodonAdapter(
            settings.mastodon_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.social_timeout_seconds,
        )
    if adapter_key == "linkedin":
        return LinkedInAdapter(
            settings.searxng_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.searxng_timeout_seconds,
            results_per_page=settings.searxng_results_per_page,
        )
    if adapter_key == "instagram":
        return InstagramAdapter(
            settings.searxng_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.searxng_timeout_seconds,
            results_per_page=settings.searxng_results_per_page,
        )
    if adapter_key == "facebook":
        return FacebookAdapter(
            settings.searxng_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.searxng_timeout_seconds,
            results_per_page=settings.searxng_results_per_page,
        )
    if adapter_key == "x":
        return XSocialAdapter(
            settings.searxng_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.searxng_timeout_seconds,
            results_per_page=settings.searxng_results_per_page,
        )
    if adapter_key == "youtube":
        return YouTubeAdapter(
            settings.searxng_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.searxng_timeout_seconds,
            results_per_page=settings.searxng_results_per_page,
        )
    if adapter_key in ("justdial", "directory"):
        return JustdialAdapter(
            settings.searxng_base_url,
            user_agent=settings.social_user_agent,
            timeout_seconds=settings.searxng_timeout_seconds,
            results_per_page=settings.searxng_results_per_page,
        )
    raise SourceUnavailableError(adapter_key, "no adapter is registered for this platform")


async def create_research_query(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    platform_slug: str,
    query_config: dict[str, Any],
    settings: Settings,
) -> SocialResearchQuery:
    await ensure_platforms(session)
    platform = await _get_platform_by_slug(session, platform_slug)
    if platform is None:
        raise NotFoundError(f"Unknown social platform '{platform_slug}'")
    if not platform.is_enabled:
        raise ConflictError(
            f"{platform.name} is not available: {_first_limitation(platform)}"
        )
    if platform.adapter_key not in ENABLED_ADAPTER_KEYS:
        raise SourceUnavailableError(
            platform.slug, "no permitted collection adapter configured"
        )
    adapter = _build_adapter(settings, platform.adapter_key)
    try:
        await adapter.validate_config(query_config)
    except AdapterError as exc:
        raise ValidationFailedError(exc.message) from exc
    finally:
        await adapter.aclose()

    row = SocialResearchQuery(
        owner_user_id=owner_user_id,
        platform_id=platform.id,
        query_config=query_config,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


def _first_limitation(platform: SocialPlatform) -> str:
    limitations = platform.limitations or {}
    for value in limitations.values():
        if isinstance(value, str) and value:
            return value
    return "restricted access"


async def list_research_queries(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    limit: int | None,
    offset: int,
) -> tuple[list[SocialResearchQuery], int]:
    await ensure_platforms(session)
    base = select(SocialResearchQuery).where(
        SocialResearchQuery.owner_user_id == owner_user_id
    )
    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    rows = await session.scalars(
        base.order_by(SocialResearchQuery.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total


async def _get_query(
    session: AsyncSession, owner_user_id: uuid.UUID, query_id: uuid.UUID
) -> SocialResearchQuery | None:
    return await session.scalar(
        select(SocialResearchQuery).where(
            SocialResearchQuery.id == query_id,
            SocialResearchQuery.owner_user_id == owner_user_id,
        )
    )


async def delete_research_query(
    session: AsyncSession, *, owner_user_id: uuid.UUID, query_id: uuid.UUID
) -> None:
    row = await _get_query(session, owner_user_id, query_id)
    if row is None:
        raise NotFoundError("Research query not found")
    await session.delete(row)


async def run_research_query(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    query_id: uuid.UUID,
    settings: Settings,
) -> dict[str, Any]:
    query = await _get_query(session, owner_user_id, query_id)
    if query is None:
        raise NotFoundError("Research query not found")
    platform = await _get_platform(session, query.platform_id)
    if platform is None:
        raise NotFoundError("Platform for this query no longer exists")
    if not platform.is_enabled:
        raise SourceUnavailableError(platform.slug, _first_limitation(platform))

    adapter = _build_adapter(settings, platform.adapter_key)
    try:
        results = await adapter.search(query.query_config)
    except AdapterError as exc:
        query.last_run_at = datetime.now(UTC)
        query.last_run_status = "failed"
        query.last_run_error = exc.message[:500]
        platform.last_run_at = datetime.now(UTC)
        platform.health_status = "failed"
        platform.last_error = exc.message[:500]
        await session.flush()
        return {
            "query_id": query.id,
            "platform_slug": platform.slug,
            "status": "failed",
            "collected": 0,
            "stored_new": 0,
            "duplicates": 0,
            "error": exc.message,
        }
    finally:
        await adapter.aclose()

    # Indexed search results often omit publication dates. Enrich a bounded
    # number of public URLs before persistence so dates exposed in JSON-LD/meta
    # become available without turning one query into an unbounded crawl.
    results = await _enrich_public_results(results)

    source_id = await ensure_source(session, adapter.capabilities)
    stored_new, duplicates = await _store_results(
        session,
        owner_user_id=owner_user_id,
        platform=platform,
        query_id=query.id,
        source_id=source_id,
        results=results,
    )

    query.last_run_at = datetime.now(UTC)
    query.last_run_status = "completed"
    query.last_run_error = None
    platform.last_run_at = datetime.now(UTC)
    platform.health_status = "working"
    platform.last_error = None
    await session.flush()
    return {
        "query_id": query.id,
        "platform_slug": platform.slug,
        "status": "completed",
        "collected": len(results),
        "stored_new": stored_new,
        "duplicates": duplicates,
        "error": None,
    }


async def _enrich_public_results(results: Sequence[SocialResult]) -> list[SocialResult]:
    """Fill missing publication dates from publicly accessible result pages."""
    max_pages = 25
    candidates = [
        result
        for result in results
        if result.published_at is None
        and result.content_url
        and result.content_url.startswith(("http://", "https://"))
    ][:max_pages]
    if not candidates:
        return list(results)

    enriched: dict[str, SocialResult] = {}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0), follow_redirects=False
    ) as client:
        for result in candidates:
            try:
                fetched = await fetch_public_page(result.content_url or "", client=client)
            except (httpx.HTTPError, ValueError):
                continue
            if fetched.status == "ok" and fetched.published_at is not None:
                enriched[result.external_id] = replace(
                    result, published_at=fetched.published_at
                )

    return [enriched.get(result.external_id, result) for result in results]


async def _store_results(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    platform: SocialPlatform,
    query_id: uuid.UUID,
    source_id: uuid.UUID,
    results: Sequence[SocialResult],
) -> tuple[int, int]:
    """Persist collected results, deduplicating content and reusing profiles.

    Content is unique per (owner, platform, external_id): re-running a search
    must not re-store the same post, and the duplicate count is reported rather
    than hidden. A profile is created once per (owner, platform, author).
    """
    external_ids = [r.external_id for r in results]
    if not external_ids:
        return 0, 0
    existing_content = {
        row.external_id: row
        for row in (
            await session.scalars(
                select(SocialContent).where(
                    SocialContent.owner_user_id == owner_user_id,
                    SocialContent.platform_id == platform.id,
                    SocialContent.external_id.in_(external_ids),
                )
            )
        ).all()
    }

    author_ids = {r.author_external_id for r in results if r.author_external_id}
    existing_profiles: dict[str, SocialProfile] = {}
    if author_ids:
        existing_profiles = {
            row.external_id: row
            for row in (
                await session.scalars(
                    select(SocialProfile).where(
                        SocialProfile.owner_user_id == owner_user_id,
                        SocialProfile.platform_id == platform.id,
                        SocialProfile.external_id.in_(author_ids),
                    )
                )
            ).all()
        }

    stored_new = 0
    duplicates = 0
    now = datetime.now(UTC)
    for result in results:
        if result.external_id in existing_content:
            duplicates += 1
            continue
        profile_id = None
        if result.author_external_id:
            profile = existing_profiles.get(result.author_external_id)
            if profile is None:
                profile = SocialProfile(
                    platform_id=platform.id,
                    owner_user_id=owner_user_id,
                    external_id=result.author_external_id,
                    username=sanitize_text(result.author_username, max_length=255),
                    profile_url=_clip_url(result.author_profile_url),
                    display_name=sanitize_text(result.author_display_name, max_length=255),
                    public_metadata=result.raw_data.get("author") or {},
                    last_researched_at=now,
                )
                session.add(profile)
                await session.flush()
                existing_profiles[result.author_external_id] = profile
            profile_id = profile.id
        session.add(
            SocialContent(
                platform_id=platform.id,
                owner_user_id=owner_user_id,
                research_query_id=query_id,
                profile_id=profile_id,
                external_id=result.external_id,
                content_url=_clip_url(result.content_url),
                content_type=result.content_type,
                content_text=sanitize_text(result.content_text, max_length=4000),
                published_at=result.published_at,
                engagement_data=result.engagement,
                source_id=source_id,
                collected_at=now,
            )
        )
        stored_new += 1
    await session.flush()
    return stored_new, duplicates


def _clip_url(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:MAX_URL_LENGTH]


async def list_content(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    platform_slug: str | None,
    query: str | None,
    content_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[SocialContent, str, str | None, str | None]], int]:
    await ensure_platforms(session)
    stmt = (
        select(
            SocialContent,
            SocialPlatform.slug,
            SocialProfile.username,
            SocialProfile.profile_url,
        )
        .join(SocialPlatform, SocialPlatform.id == SocialContent.platform_id)
        .outerjoin(SocialProfile, SocialProfile.id == SocialContent.profile_id)
        .where(SocialContent.owner_user_id == owner_user_id)
    )
    if platform_slug:
        stmt = stmt.where(SocialPlatform.slug == platform_slug)
    if content_type:
        stmt = stmt.where(SocialContent.content_type == content_type)
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            SocialContent.content_text.ilike(pattern)
            | SocialContent.external_id.ilike(pattern)
        )
    total = await session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0
    rows_stmt = stmt.order_by(SocialContent.collected_at.desc())
    if limit is not None:
        rows_stmt = rows_stmt.limit(limit).offset(offset)
    rows = await session.execute(rows_stmt)
    return [
        (row[0], row[1], row[2], row[3])
        for row in rows.all()
    ], total


def content_export_row(
    content: SocialContent,
    platform_slug: str,
    author_username: str | None,
    author_profile_url: str | None,
) -> dict[str, Any]:
    """One collected item as an export row.

    Shared by the ad-hoc CSV endpoint and the background export job so the two
    cannot drift into exporting different columns.
    """
    engagement = content.engagement_data or {}
    return {
        "platform": platform_slug,
        "content_type": content.content_type,
        "content_url": content.content_url,
        "content_text": content.content_text,
        "author_username": author_username,
        "author_profile_url": author_profile_url,
        "published_at": content.published_at.isoformat() if content.published_at else "",
        "collected_at": content.collected_at.isoformat() if content.collected_at else "",
        "engagement_score": engagement.get("score", ""),
        "engagement_comments": engagement.get("num_comments", ""),
        "subreddit": engagement.get("subreddit", ""),
    }


def intelligence_export_row(
    content: SocialContent, platform_slug: str, username: str | None
) -> dict[str, Any]:
    """One classified result as an export row.

    Shared by the ad-hoc CSV endpoint and the background export job.
    """
    return {
        "platform": platform_slug,
        "track_type": content.track_type or "",
        "classification": content.classification or "",
        "confidence_score": (
            float(content.confidence_score) if content.confidence_score is not None else ""
        ),
        "retrieval_status": content.retrieval_status or "",
        "title": content.title or "",
        "content_url": content.content_url or "",
        "content_text": content.content_text or "",
        "matched_terms": ",".join(content.matched_terms or []),
        "published_at": content.published_at.isoformat() if content.published_at else "",
        "discovered_at": content.discovered_at.isoformat() if content.discovered_at else "",
        "author_username": username or "",
        "needs_review": content.needs_review,
    }


async def get_content(
    session: AsyncSession, *, owner_user_id: uuid.UUID, content_id: uuid.UUID
) -> SocialContent | None:
    return await session.scalar(
        select(SocialContent).where(
            SocialContent.id == content_id,
            SocialContent.owner_user_id == owner_user_id,
        )
    )


async def link_content_to_business(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    content_id: uuid.UUID,
    business_id: uuid.UUID,
) -> BusinessSocialProfile:
    content = await get_content(session, owner_user_id=owner_user_id, content_id=content_id)
    if content is None:
        raise NotFoundError("Content not found")
    business = await session.scalar(
        select(Business).where(
            Business.id == business_id,
            Business.owner_user_id == owner_user_id,
        )
    )
    if business is None:
        raise NotFoundError("Business not found")
    if not content.content_url:
        raise ValidationFailedError("This content has no URL to link to a business")

    platform = await _get_platform(session, content.platform_id)
    platform_slug = platform.slug if platform else "unknown"
    username = None
    if content.profile_id:
        profile = await session.scalar(
            select(SocialProfile).where(SocialProfile.id == content.profile_id)
        )
        if profile is not None:
            username = profile.username
    existing = await session.scalar(
        select(BusinessSocialProfile).where(
            BusinessSocialProfile.business_id == business_id,
            BusinessSocialProfile.platform == platform_slug,
        )
    )
    if existing is not None:
        existing.profile_url = content.content_url
        existing.username = username
        existing.last_verified_at = datetime.now(UTC)
        await session.flush()
        return existing

    link = BusinessSocialProfile(
        business_id=business_id,
        platform=platform_slug,
        profile_url=content.content_url,
        username=username,
        source_id=content.source_id,
        last_verified_at=datetime.now(UTC),
    )
    session.add(link)
    await session.flush()
    return link


async def delete_content(
    session: AsyncSession, *, owner_user_id: uuid.UUID, content_id: uuid.UUID
) -> None:
    content = await get_content(session, owner_user_id=owner_user_id, content_id=content_id)
    if content is None:
        raise NotFoundError("Content not found")
    await session.delete(content)


async def delete_all_content(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> int:
    """Delete only the current owner's collected social content."""
    result = await session.execute(
        delete(SocialContent).where(SocialContent.owner_user_id == owner_user_id)
    )
    return int(result.rowcount or 0)
