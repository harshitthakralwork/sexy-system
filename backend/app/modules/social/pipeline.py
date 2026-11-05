"""Social & Demand Intelligence Engine — ingestion pipeline (Phase 3).

Takes the raw ``SocialResult`` items a connector produced and turns them into
owned, classified, deduplicated ``social_content`` rows. Normalisation never
invents a field the source did not carry; deduplication merges only on an exact
identity (external id, or a shared canonical URL / content fingerprint across
sources) and preserves every source attribution; classification is the
deterministic engine's, and its method/version/evidence are recorded so a call is
explainable and re-runnable.

Discovered ≠ retrieved ≠ stored ≠ classified ≠ qualified. This module reports the
first four as separate counts; "qualified" is a downstream lead decision, not here.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.social.adapters import SocialResult
from app.modules.social.classification import classify
from app.modules.social.models import SocialContent, SocialContentUserAnnotation, SocialPlatform, SocialProfile
from app.shared.normalization import MAX_URL_LENGTH, canonical_hash, sanitize_text


def _clip_url(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned[:MAX_URL_LENGTH] if cleaned else None


def _retrieval_status(platform: SocialPlatform, result: SocialResult) -> str:
    # A connector that already told us how much it got wins; RSS records the same
    # truth in engagement; everything else is judged by whether it carried a body.
    hint = result.raw_data.get("retrieval_hint")
    if isinstance(hint, str):
        return hint
    if platform.slug == "rss":
        return "retrieved" if result.engagement.get("has_full_content") else "snippet_only"
    return "retrieved" if (result.content_text or "").strip() else "snippet_only"


def _fingerprint(result: SocialResult, canonical_url: str | None) -> str:
    if canonical_url:
        return canonical_hash("url", canonical_url)
    body = sanitize_text(result.content_text, max_length=4000) or ""
    return canonical_hash("body", body[:1000])


async def _upsert_profile(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    platform: SocialPlatform,
    result: SocialResult,
    cache: dict[str, SocialProfile],
    now: datetime,
) -> uuid.UUID | None:
    if not result.author_external_id:
        return None
    existing = cache.get(result.author_external_id)
    if existing is not None:
        return existing.id
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
    cache[result.author_external_id] = profile
    return profile.id


async def ingest_results(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    platform: SocialPlatform,
    track_id: uuid.UUID | None,
    track_type: str,
    source_id: uuid.UUID | None,
    results: Sequence[SocialResult],
) -> dict[str, Any]:
    """Persist + classify a batch, deduplicating within and across sources.

    Returns counts that stay honest about what happened: ``stored_new`` counts only
    genuinely new rows, ``duplicates`` counts rows merged into an existing record,
    and ``classification_counts`` breaks the new rows down by category.
    """
    if not results:
        return {"stored_new": 0, "duplicates": 0, "review_flagged": 0, "classification_counts": {}}

    now = datetime.now(UTC)

    # Within-source identity: the unique (owner, platform, external_id) index.
    external_ids = [r.external_id for r in results]
    same_platform = {
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

    # Cross-source identity: the same URL/body seen on another platform merges here.
    fingerprints = [_fingerprint(r, _clip_url(r.content_url)) for r in results]
    by_fingerprint = {
        row.dedup_fingerprint: row
        for row in (
            await session.scalars(
                select(SocialContent).where(
                    SocialContent.owner_user_id == owner_user_id,
                    SocialContent.dedup_fingerprint.in_(fingerprints),
                )
            )
        ).all()
    }

    profiles: dict[str, SocialProfile] = {}
    stored_new = 0
    duplicates = 0
    classification_counts: dict[str, int] = {}
    # Identity seen within this batch, so two results carrying the same external id
    # or URL in a single run merge rather than collide on the unique index.
    batch_map: dict[str, SocialContent] = {}

    for result, fingerprint in zip(results, fingerprints, strict=True):
        attribution = {
            "platform": platform.slug,
            "external_id": result.external_id,
            "url": _clip_url(result.content_url),
            "observed_at": now.isoformat(),
            "source_id": str(source_id) if source_id else None,
        }

        existing = (
            same_platform.get(result.external_id)
            or by_fingerprint.get(fingerprint)
            or batch_map.get(result.external_id)
            or batch_map.get(fingerprint)
        )
        if existing is not None:
            existing.source_attribution = [*existing.source_attribution, attribution]
            if existing.retrieval_status in (None, "snippet_only", "indexed_snippet") and (
                _retrieval_status(platform, result) == "retrieved"
            ):
                existing.retrieval_status = "retrieved"
            duplicates += 1
            continue

        outcome = classify(result.content_text or "", track_type)
        profile_id = await _upsert_profile(
            session,
            owner_user_id=owner_user_id,
            platform=platform,
            result=result,
            cache=profiles,
            now=now,
        )
        # Extract nullable engagement without inventing fake 0s
        eng = result.engagement if isinstance(result.engagement, dict) else {}
        reactions = eng.get("reactions") if "reactions" in eng else eng.get("score") if "score" in eng else None
        comments = eng.get("comments") if "comments" in eng else eng.get("num_comments") if "num_comments" in eng else None
        reposts = eng.get("reposts") if "reposts" in eng else eng.get("shares") if "shares" in eng else None

        row = SocialContent(
            platform_id=platform.id,
            owner_user_id=owner_user_id,
            track_id=track_id,
            track_type=track_type,
            research_query_id=None,
            profile_id=profile_id,
            external_id=result.external_id,
            content_url=_clip_url(result.content_url),
            canonical_url=_clip_url(result.content_url),
            content_type=result.content_type,
            content_text=sanitize_text(result.content_text, max_length=8000),
            title=sanitize_text(result.raw_data.get("title"), max_length=255),
            snippet=sanitize_text(result.raw_data.get("snippet") or result.content_text, max_length=1000),
            retrieval_status=_retrieval_status(platform, result),
            published_at=result.published_at,
            published_at_source=result.published_at.isoformat() if result.published_at else None,
            last_seen_at=now,
            author_name=result.author_display_name or result.author_username or result.raw_data.get("author"),
            author_username=result.author_username,
            author_profile_url=result.author_profile_url,
            extraction_method=result.raw_data.get("extraction_method") or "searxng_public",
            matched_query=result.raw_data.get("matched_query"),
            classification_score=outcome.score,
            service_tags=list(outcome.service_mapping),
            reactions_count=reactions,
            comments_count=comments,
            reposts_count=reposts,
            raw_metadata={k: v for k, v in result.raw_data.items() if len(str(v)) < 10000} if isinstance(result.raw_data, dict) else {},
            discovered_at=now,
            engagement_data=result.engagement,
            source_id=source_id,
            collected_at=now,
            classification=outcome.category,
            confidence_score=outcome.confidence,
            classification_method=outcome.method,
            classification_version=outcome.version,
            matched_terms=list(outcome.matched_terms),
            evidence=[dict(e) for e in outcome.evidence],
            positive_signals=dict(outcome.positive_signals),
            negative_signals=dict(outcome.negative_signals),
            dedup_fingerprint=fingerprint,
            source_attribution=[attribution],
        )
        session.add(row)
        await session.flush()

        # Seed isolated user annotation so re-enrichment never overwrites CRM state
        annotation = SocialContentUserAnnotation(
            content_id=row.id,
            owner_user_id=owner_user_id,
            lead_status="new",
            is_hot=outcome.score >= 70,
            is_saved=False,
            services_to_sell=list(outcome.service_mapping),
        )
        session.add(annotation)
        batch_map[result.external_id] = row
        batch_map[fingerprint] = row
        stored_new += 1
        classification_counts[outcome.category] = (
            classification_counts.get(outcome.category, 0) + 1
        )

    await session.flush()
    return {
        "stored_new": stored_new,
        "duplicates": duplicates,
        "review_flagged": 0,
        "classification_counts": classification_counts,
    }
