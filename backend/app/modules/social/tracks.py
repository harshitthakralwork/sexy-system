"""Social & Demand Intelligence Engine — track orchestration (Phase 4).

Runs a track across its configured sources, one auditable ``social_discovery_runs``
per execution, with per-source failure isolation: a source that refuses (blocked,
rate-limited, unreachable) is recorded and skipped, and the other sources still
complete. It reuses the existing dispatcher and task registry rather than a second
job system, and the automation engine's recurrence maths rather than a copy of it.

A manual "run now" claims a pending run and executes inline in development (via the
background task) or on Celery in production; the periodic tick runs scheduled tracks.
Nothing is reported as completed that did not run.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.modules.automation.service import compute_next_run
from app.modules.businesses.models import Business, BusinessSocialProfile
from app.modules.discovery.adapters.base import AdapterError, HealthResult
from app.modules.notifications.models import Notification
from app.modules.social.adapters import SocialResult
from app.modules.social.models import (
    SocialContent,
    SocialDiscoveryRun,
    SocialPlatform,
    SocialProfile,
    SocialSavedItem,
    SocialSearchTrack,
)
from app.modules.social.pipeline import ingest_results
from app.modules.social.schemas import TrackCreateIn, TrackUpdateIn
from app.modules.social.service import _build_adapter, ensure_platforms
from app.modules.sources import service as source_service
from app.modules.sources.models import Source
from app.modules.sources.registry import ensure_source
from app.shared.normalization import normalize_domain, normalize_name
from app.workers.dispatcher import SynchronousDispatcher, get_dispatcher
from app.workers.tasks import register_task

RUN_TASK_NAME = "sparkxflow.social.run_track"
TICK_TASK_NAME = "sparkxflow.social.tick_tracks"

logger = get_logger(__name__)


# --- Track CRUD -------------------------------------------------------------


async def list_tracks(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[SocialSearchTrack], int]:
    where = SocialSearchTrack.owner_user_id == owner_user_id
    total = await session.scalar(select(func.count()).select_from(SocialSearchTrack).where(where))
    rows = await session.scalars(
        select(SocialSearchTrack)
        .where(where)
        .order_by(SocialSearchTrack.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def get_track(
    session: AsyncSession, owner_user_id: uuid.UUID, track_id: uuid.UUID
) -> SocialSearchTrack | None:
    return await session.scalar(
        select(SocialSearchTrack).where(
            SocialSearchTrack.id == track_id, SocialSearchTrack.owner_user_id == owner_user_id
        )
    )


def _next_run_for(track: SocialSearchTrack, *, now: datetime) -> datetime | None:
    if not track.frequency_config:
        return None
    return compute_next_run(
        track.frequency_config,
        start_at=track.created_at or now,
        last_run_at=track.last_run_at,
        now=now,
    )


async def create_track(
    session: AsyncSession, owner_user_id: uuid.UUID, data: TrackCreateIn
) -> SocialSearchTrack:
    if not (data.keywords or data.exact_phrases or data.hashtags or data.source_config):
        raise ValidationFailedError(
            "A track needs at least one keyword, phrase, hashtag or feed"
        )
    now = datetime.now(UTC)
    track = SocialSearchTrack(
        owner_user_id=owner_user_id,
        name=data.name,
        track_type=data.track_type,
        keywords=data.keywords,
        exact_phrases=data.exact_phrases,
        excluded_terms=data.excluded_terms,
        hashtags=data.hashtags,
        platforms=data.platforms,
        language=data.language,
        geography=data.geography,
        date_from=data.date_from,
        date_to=data.date_to,
        source_config=data.source_config,
        frequency_config=data.frequency_config,
        max_results_per_run=data.max_results_per_run,
        is_enabled=data.is_enabled,
        is_paused=False,
        next_run_at=None,
    )
    session.add(track)
    await session.flush()
    track.next_run_at = _next_run_for(track, now=now)
    await session.flush()
    await session.refresh(track)
    return track


async def update_track(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    track_id: uuid.UUID,
    data: TrackUpdateIn,
) -> SocialSearchTrack:
    track = await get_track(session, owner_user_id, track_id)
    if track is None:
        raise NotFoundError("Track not found")
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(track, field, value)
    track.next_run_at = _next_run_for(track, now=datetime.now(UTC))
    await session.flush()
    await session.refresh(track)
    return track


async def delete_track(
    session: AsyncSession, owner_user_id: uuid.UUID, track_id: uuid.UUID
) -> None:
    track = await get_track(session, owner_user_id, track_id)
    if track is None:
        raise NotFoundError("Track not found")
    await session.delete(track)
    await session.flush()


# --- Query construction -----------------------------------------------------


def _primary_query_text(track: SocialSearchTrack) -> str:
    if track.exact_phrases:
        return track.exact_phrases[0]
    parts = list(track.keywords)
    parts += [f"#{h.lstrip('#')}" for h in track.hashtags]
    return " ".join(parts)


def build_query(
    track: SocialSearchTrack, platform_slug: str, feed_urls: list[str] | None = None
) -> dict[str, Any]:
    """Turn a track into the config one platform's adapter expects.

    A platform whose adapter cannot answer this track (e.g. RSS with no feed URLs)
    raises so the orchestrator records an honest skip rather than a fake empty run.
    `feed_urls` is the account's Source Manager default, used only where a track
    leaves its feeds unset.
    """
    text = _primary_query_text(track)
    limit = min(track.max_results_per_run, 100)
    if platform_slug == "reddit":
        subreddit = track.source_config.get("subreddit")
        if subreddit:
            return {
                "kind": "subreddit",
                "subreddit": subreddit,
                "q": text,
                "sort": "new",
                "limit": limit,
            }
        if not text:
            raise AdapterError(
                "Reddit track needs a keyword or subreddit", classification="unsupported_query"
            )
        return {"kind": "search", "q": text, "sort": "new", "limit": limit}
    if platform_slug == "hackernews":
        kind = track.source_config.get("hn_kind", "search")
        if kind in ("front_page", "ask_hn", "show_hn"):
            return {"kind": kind, "limit": limit}
        if kind == "user":
            author = track.source_config.get("author")
            if not author:
                raise AdapterError(
                    "Hacker News user track needs an author", classification="unsupported_query"
                )
            return {"kind": "user", "author": author, "limit": limit}
        if not text:
            raise AdapterError(
                "Hacker News track needs a keyword", classification="unsupported_query"
            )
        return {"kind": "search", "q": text, "limit": limit}
    if platform_slug == "searxng":
        if not text:
            raise AdapterError(
                "SearXNG track needs a keyword", classification="unsupported_query"
            )
        cfg: dict[str, Any] = {"q": text}
        if track.language:
            cfg["language"] = track.language
        for key in ("time_range", "categories"):
            if track.source_config.get(key):
                cfg[key] = track.source_config[key]
        return cfg
    if platform_slug == "rss":
        feeds = track.source_config.get("feed_urls") or feed_urls
        if not isinstance(feeds, Sequence) or not feeds:
            raise AdapterError(
                "RSS track needs feed URLs (set them on the track or in the Source Manager)",
                classification="unsupported_query",
            )
        return {"feed_urls": list(feeds)}
    if platform_slug in (
        "stackoverflow",
        "bluesky",
        "mastodon",
        "linkedin",
        "instagram",
        "facebook",
        "x",
        "youtube",
    ):
        if not text:
            raise AdapterError(
                f"{platform_slug} track needs a keyword", classification="unsupported_query"
            )
        cfg = {"q": text, "limit": limit}
        if platform_slug == "stackoverflow":
            cfg["sort"] = track.source_config.get("sort", "creation")
            if track.source_config.get("tagged"):
                cfg["tagged"] = track.source_config["tagged"]
        elif platform_slug in ("linkedin", "instagram", "facebook", "x", "youtube"):
            cfg["kind"] = "search"
        return cfg
    raise AdapterError(
        f"No query builder for platform '{platform_slug}'", classification="unsupported_query"
    )


def _apply_exclusions(
    results: list[SocialResult], excluded: list[str]
) -> list[SocialResult]:
    if not excluded:
        return results
    lowered = [e.lower() for e in excluded]
    return [
        result
        for result in results
        if not any(term in (result.content_text or "").lower() for term in lowered)
    ]


# --- Run orchestration ------------------------------------------------------


async def start_track_run(
    session: AsyncSession, *, owner_user_id: uuid.UUID, track_id: uuid.UUID, trigger_type: str
) -> SocialDiscoveryRun:
    track = await get_track(session, owner_user_id, track_id)
    if track is None:
        raise NotFoundError("Track not found")
    if not track.platforms:
        raise ConflictError("A track must select at least one source before it can run")
    run = SocialDiscoveryRun(
        owner_user_id=owner_user_id,
        track_id=track.id,
        status="pending",
        trigger_type=trigger_type,
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    return run


async def execute_track_run(run_id: uuid.UUID, *, settings: Settings | None = None) -> str:
    """Run one pending track execution across its sources, recording each outcome."""
    active = settings or get_settings()
    async with session_scope() as session:
        run = await session.get(SocialDiscoveryRun, run_id)
        if run is None:
            logger.warning("social_run_missing", run_id=str(run_id))
            return "missing"
        if run.status != "pending":
            return run.status  # idempotent claim

        track = await session.get(SocialSearchTrack, run.track_id)
        if track is None or track.owner_user_id != run.owner_user_id:
            run.status = "failed"
            run.error_summary = json.dumps({"reason": "Track was deleted before the run"})
            run.finished_at = datetime.now(UTC)
            await session.commit()
            return "failed"

        await ensure_platforms(session)
        now = datetime.now(UTC)
        run.status = "running"
        run.started_at = now
        run.sources_attempted = []
        await session.commit()

        results_returned = 0
        stored_new = 0
        duplicates = 0
        review_flagged = 0
        classification_counts: dict[str, int] = {}
        errors: dict[str, str] = {}
        ok_sources: list[str] = []
        attempted: list[str] = []
        # A source the operator turned off in the Source Manager is skipped here,
        # and the skip is recorded on the run rather than quietly dropped.
        blocked = await source_service.disabled_slugs(
            session, run.owner_user_id, list(track.platforms)
        )

        for slug in track.platforms:
            attempted.append(slug)
            run.sources_attempted = list(attempted)
            run.queries_attempted = len(attempted)
            if slug in blocked:
                errors[slug] = blocked[slug]
                run.error_summary = json.dumps(errors)
                await session.commit()
                continue
            platform = await session.scalar(
                select(SocialPlatform).where(SocialPlatform.slug == slug)
            )
            if platform is None or not platform.is_enabled:
                errors[slug] = "platform unavailable or disabled"
                run.error_summary = json.dumps(errors) if errors else None
                await session.commit()
                continue

            adapter = _build_adapter(active, platform.adapter_key)
            try:
                configured_feeds = await source_service.owner_feed_urls(
                    session, run.owner_user_id, slug
                )
                config = build_query(track, slug, feed_urls=configured_feeds)
                raw_results = await adapter.search(config)
            except AdapterError as exc:
                errors[slug] = exc.message[:400]
                platform.health_status = "failed"
                platform.last_error = exc.message[:500]
                platform.last_run_at = datetime.now(UTC)
                failed_source = await session.scalar(
                    select(Source).where(Source.slug == slug)
                )
                if failed_source is not None:
                    await source_service.record_health(
                        session,
                        failed_source,
                        HealthResult(status="failed", detail=exc.message[:500]),
                        detail_extra={"origin": "track_run", "run_id": str(run.id)},
                    )
                run.error_summary = json.dumps(errors)
                await session.commit()
                await adapter.aclose()
                continue

            kept = _apply_exclusions(raw_results, list(track.excluded_terms))
            source_id = await ensure_source(session, adapter.capabilities)
            outcome = await ingest_results(
                session,
                owner_user_id=run.owner_user_id,
                platform=platform,
                track_id=track.id,
                track_type=track.track_type,
                source_id=source_id,
                results=kept,
            )
            platform.health_status = "working"
            platform.last_error = None
            platform.last_run_at = datetime.now(UTC)
            finished_source = datetime.now(UTC)
            await source_service.record_usage(
                session,
                source_id,
                job_id=None,
                requests_count=int(getattr(adapter, "requests_made", 0) or 0),
                records_returned=len(raw_results),
                records_accepted=int(outcome["stored_new"]),
                measured_at=finished_source,
            )
            source_row = await session.get(Source, source_id)
            if source_row is not None:
                await source_service.record_health(
                    session,
                    source_row,
                    HealthResult(status="working", detail=f"{len(raw_results)} result(s)"),
                    detail_extra={"origin": "track_run", "run_id": str(run.id)},
                )
            results_returned += len(raw_results)
            stored_new += outcome["stored_new"]
            duplicates += outcome["duplicates"]
            review_flagged += outcome["review_flagged"]
            for category, count in outcome["classification_counts"].items():
                classification_counts[category] = classification_counts.get(category, 0) + count
            ok_sources.append(slug)
            run.error_summary = json.dumps(errors) if errors else None
            await session.commit()
            await adapter.aclose()

        finished = datetime.now(UTC)
        if not ok_sources:
            run.status = "failed"
        elif errors:
            run.status = "completed_with_warnings"
        else:
            run.status = "completed"
        run.results_returned = results_returned
        run.stored_new = stored_new
        run.duplicates = duplicates
        run.review_flagged = review_flagged
        run.classification_counts = classification_counts
        run.finished_at = finished
        run.duration_ms = int((finished - (run.started_at or finished)).total_seconds() * 1000)

        track.last_run_at = finished
        track.next_run_at = _next_run_for(track, now=finished)
        await record_high_confidence_alerts(
            session, run.owner_user_id, float(active.social_alert_confidence_threshold)
        )
        await session.commit()
        return run.status


async def list_runs(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    track_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[SocialDiscoveryRun], int]:
    where = SocialDiscoveryRun.owner_user_id == owner_user_id
    if track_id is not None:
        where = where & (SocialDiscoveryRun.track_id == track_id)
    total = await session.scalar(select(func.count()).select_from(SocialDiscoveryRun).where(where))
    rows = await session.scalars(
        select(SocialDiscoveryRun)
        .where(where)
        .order_by(SocialDiscoveryRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def dispatch_run(
    session: AsyncSession, run: SocialDiscoveryRun, background: BackgroundTasks
) -> str:
    """Hand a freshly created run to the configured runner; report how it was handed."""
    dispatcher = get_dispatcher()
    if isinstance(dispatcher, SynchronousDispatcher):
        await session.commit()
        background.add_task(execute_track_run_task, run_id=str(run.id))
        return "inline"
    try:
        dispatcher.submit(RUN_TASK_NAME, {"run_id": str(run.id)})
    except Exception as exc:  # noqa: BLE001 - a missing broker is a reportable state
        run.status = "failed"
        run.error_summary = json.dumps(
            {
                "reason": f"No worker could accept this run ({type(exc).__name__}). "
                "Set SPARKX_RUN_JOBS_SYNCHRONOUSLY=true to run inline in development."
            }
        )
        await session.flush()
        return "blocked"
    return "queued"


@register_task(RUN_TASK_NAME)
async def execute_track_run_task(*, run_id: str) -> str:
    return await execute_track_run(uuid.UUID(run_id))


@register_task(TICK_TASK_NAME)
async def run_due_tracks(*, settings: Settings | None = None) -> int:
    """Start and run every enabled, unpaused track whose next_run_at has passed."""
    active = settings or get_settings()
    now = datetime.now(UTC)
    run_ids: list[uuid.UUID] = []
    async with session_scope() as session:
        due = list(
            await session.scalars(
                select(SocialSearchTrack).where(
                    SocialSearchTrack.is_enabled.is_(True),
                    SocialSearchTrack.is_paused.is_(False),
                    SocialSearchTrack.next_run_at.is_not(None),
                    SocialSearchTrack.next_run_at <= now,
                )
            )
        )
        for track in due:
            if not track.platforms:
                continue
            run = SocialDiscoveryRun(
                owner_user_id=track.owner_user_id,
                track_id=track.id,
                status="pending",
                trigger_type="scheduled",
            )
            session.add(run)
            await session.flush()
            track.next_run_at = _next_run_for(track, now=now)
            run_ids.append(run.id)
        await session.commit()
    for run_id in run_ids:
        await execute_track_run(run_id, settings=active)
    return len(run_ids)


# --- Intelligence listing (Demand / Business results) -----------------------


async def list_intelligence(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    track_type: str | None = None,
    platform_slug: str | None = None,
    classification: str | None = None,
    min_confidence: float | None = None,
    retrieval_status: str | None = None,
    needs_review: bool | None = None,
    saved_only: bool | None = None,
    query: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[tuple], int]:
    conds: list[Any] = [SocialContent.owner_user_id == owner_user_id]
    if track_type:
        conds.append(SocialContent.track_type == track_type)
    if classification:
        conds.append(SocialContent.classification == classification)
    if min_confidence is not None:
        conds.append(SocialContent.confidence_score >= min_confidence)
    if retrieval_status:
        conds.append(SocialContent.retrieval_status == retrieval_status)
    if needs_review is not None:
        conds.append(SocialContent.needs_review.is_(needs_review))
    if platform_slug:
        conds.append(
            SocialContent.platform_id.in_(
                select(SocialPlatform.id).where(SocialPlatform.slug == platform_slug)
            )
        )
    if saved_only is not None:
        saved_ids = select(SocialSavedItem.content_id).where(
            SocialSavedItem.owner_user_id == owner_user_id
        )
        if saved_only:
            conds.append(SocialContent.id.in_(saved_ids))
        else:
            conds.append(~SocialContent.id.in_(saved_ids))
    if query:
        pattern = f"%{query}%"
        conds.append(
            SocialContent.content_text.ilike(pattern) | SocialContent.title.ilike(pattern)
        )

    total = await session.scalar(
        select(func.count()).select_from(SocialContent).where(*conds)
    )
    rows = (
        await session.execute(
            select(SocialContent, SocialPlatform.slug, SocialProfile.username)
            .join(SocialPlatform, SocialContent.platform_id == SocialPlatform.id)
            .outerjoin(SocialProfile, SocialContent.profile_id == SocialProfile.id)
            .where(*conds)
            .order_by(SocialContent.discovered_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), int(total or 0)


# --- Saved items ------------------------------------------------------------


async def save_item(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    content_id: uuid.UUID,
    *,
    note: str | None,
    tags: list[str],
) -> SocialSavedItem:
    content = await session.scalar(
        select(SocialContent).where(
            SocialContent.id == content_id, SocialContent.owner_user_id == owner_user_id
        )
    )
    if content is None:
        raise NotFoundError("Content not found")
    item = await session.scalar(
        select(SocialSavedItem).where(
            SocialSavedItem.content_id == content_id,
            SocialSavedItem.owner_user_id == owner_user_id,
        )
    )
    if item is None:
        item = SocialSavedItem(
            owner_user_id=owner_user_id, content_id=content_id, note=note, tags=tags
        )
        session.add(item)
    else:
        item.note = note
        item.tags = tags
    await session.flush()
    await session.refresh(item)
    return item


async def unsave_item(
    session: AsyncSession, owner_user_id: uuid.UUID, content_id: uuid.UUID
) -> None:
    item = await session.scalar(
        select(SocialSavedItem).where(
            SocialSavedItem.content_id == content_id,
            SocialSavedItem.owner_user_id == owner_user_id,
        )
    )
    if item is None:
        raise NotFoundError("Saved item not found")
    await session.delete(item)
    await session.flush()


async def list_saved(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[SocialSavedItem], int]:
    where = SocialSavedItem.owner_user_id == owner_user_id
    total = await session.scalar(select(func.count()).select_from(SocialSavedItem).where(where))
    rows = await session.scalars(
        select(SocialSavedItem)
        .where(where)
        .order_by(SocialSavedItem.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


# --- Integration: alerts, notifications, lead conversion --------------------


async def record_high_confidence_alerts(
    session: AsyncSession, owner_user_id: uuid.UUID, threshold: float
) -> int:
    """Create one in-app notification per new high-confidence demand result.

    Deduplicated against notifications already raised for the same content, so a
    re-run does not spam. No email is sent; this is the in-app-first alert.
    """
    rows = list(
        await session.scalars(
            select(SocialContent).where(
                SocialContent.owner_user_id == owner_user_id,
                SocialContent.track_type == "demand",
                SocialContent.confidence_score.is_not(None),
                SocialContent.confidence_score >= threshold,
            )
        )
    )
    created = 0
    for content in rows:
        already = await session.scalar(
            select(Notification.id).where(
                Notification.owner_user_id == owner_user_id,
                Notification.notification_type == "social.demand_high_confidence",
                Notification.related_entity_type == "social_content",
                Notification.related_entity_id == content.id,
            )
        )
        if already is not None:
            continue
        session.add(
            Notification(
                owner_user_id=owner_user_id,
                notification_type="social.demand_high_confidence",
                title=f"Demand signal: {content.classification}",
                message=(
                    (content.title or content.snippet or "")[:280]
                    or "A high-confidence demand post was found."
                ),
                related_entity_type="social_content",
                related_entity_id=content.id,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created


async def list_notifications(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Notification], int]:
    where = Notification.owner_user_id == owner_user_id
    total = await session.scalar(select(func.count()).select_from(Notification).where(where))
    rows = await session.scalars(
        select(Notification)
        .where(where)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def mark_notification_read(
    session: AsyncSession, owner_user_id: uuid.UUID, notification_id: uuid.UUID
) -> None:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.owner_user_id != owner_user_id:
        raise NotFoundError("Notification not found")
    notification.is_read = True
    await session.flush()


async def convert_result_to_lead(
    session: AsyncSession, owner_user_id: uuid.UUID, content_id: uuid.UUID
) -> uuid.UUID:
    """Turn an eligible intelligence result into a Leads Intelligence business.

    Dedups on owner + normalised domain so it can never mint a duplicate business,
    and links the original social post as provenance. It refuses rather than
    inventing a business when the record has no real entity to anchor.
    """
    content = await session.scalar(
        select(SocialContent).where(
            SocialContent.id == content_id, SocialContent.owner_user_id == owner_user_id
        )
    )
    if content is None:
        raise NotFoundError("Result not found")
    anchor_url = content.canonical_url or content.content_url
    if not anchor_url:
        raise ConflictError("This result has no source URL to anchor a business entity")

    domain = normalize_domain(anchor_url)
    name = (content.title or "").strip() or (domain or "").split(".")[0]
    if not name:
        raise ConflictError("This result has no identifiable business name")

    business: Business | None = None
    if domain:
        business = await session.scalar(
            select(Business).where(
                Business.owner_user_id == owner_user_id,
                Business.normalized_domain == domain,
                Business.deleted_at.is_(None),
            )
        )
    if business is None:
        business = await session.scalar(
            select(Business).where(
                Business.owner_user_id == owner_user_id,
                Business.name == name,
                Business.deleted_at.is_(None),
            )
        )
    if business is None:
        business = Business(
            owner_user_id=owner_user_id,
            name=name,
            normalized_name=normalize_name(name) or name.lower(),
            first_discovered_at=datetime.now(UTC),
            website_status="unknown",
            normalized_domain=domain,
            website_url=anchor_url if domain else None,
        )
        session.add(business)
        await session.flush()

    platform = await session.get(SocialPlatform, content.platform_id)
    link_exists = await session.scalar(
        select(BusinessSocialProfile.id).where(
            BusinessSocialProfile.business_id == business.id,
            BusinessSocialProfile.profile_url == anchor_url,
        )
    )
    if link_exists is None:
        session.add(
            BusinessSocialProfile(
                business_id=business.id,
                platform=(platform.slug if platform else "social"),
                profile_url=anchor_url,
                username=None,
            )
        )

    saved = await session.scalar(
        select(SocialSavedItem).where(
            SocialSavedItem.owner_user_id == owner_user_id,
            SocialSavedItem.content_id == content_id,
        )
    )
    if saved is not None:
        saved.converted_business_id = business.id
    await session.flush()
    return business.id
