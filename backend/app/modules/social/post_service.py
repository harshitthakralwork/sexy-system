from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.modules.discovery.public_fetch import fetch_public_page
from app.modules.social.classification import classify
from app.modules.social.models import (
    SocialContent,
    SocialContentUserAnnotation,
    SocialDiscoveryRun,
    SocialPlatform,
    SocialSearchTrack,
)
from app.modules.social.schemas import (
    LeadsDashboardOut,
    PostAnnotationIn,
    PostAnnotationOut,
    PostBulkActionIn,
    PostListOut,
    PostOut,
)


def _build_post_out(
    content: SocialContent,
    platform_slug: str,
    annotation: SocialContentUserAnnotation | None = None,
) -> PostOut:
    user_ann = PostAnnotationOut(
        lead_status=annotation.lead_status if annotation else "new",
        is_hot=annotation.is_hot if annotation else False,
        follow_up_date=annotation.follow_up_date if annotation else None,
        user_note=annotation.user_note if annotation else None,
        quoted_customer_need=annotation.quoted_customer_need if annotation else None,
        services_to_sell=annotation.services_to_sell if annotation and annotation.services_to_sell else [],
        is_saved=annotation.is_saved if annotation else False,
    )

    # Determine full text vs snippet strictly and truthfully
    full_text = content.content_text if content.retrieval_status in ("full_text", "retrieved", "public_page_retrieved") else None
    snippet = content.snippet or (content.content_text[:600] if content.content_text else None)

    return PostOut(
        id=content.id,
        platform=platform_slug,
        original_url=content.content_url,
        canonical_url=content.canonical_url,
        external_id=content.external_id,
        page_title=content.title,
        search_snippet=snippet,
        extracted_full_text=full_text,
        author_name=content.author_name or content.author_username,
        author_username=content.author_username,
        author_profile_url=content.author_profile_url,
        published_at=content.published_at,
        published_at_source=content.published_at_source,
        first_discovered_at=content.discovered_at,
        last_seen_at=content.last_seen_at,
        retrieval_status=content.retrieval_status or "snippet_only",
        retrieval_error=content.retrieval_error,
        extraction_method=content.extraction_method,
        matched_query=content.matched_query,
        discovery_run_id=content.discovery_run_id,
        duplicate_of_id=content.duplicate_of_id,
        classification_category=content.classification,
        classification_confidence=float(content.confidence_score) if content.confidence_score is not None else None,
        classification_score=content.classification_score,
        matched_phrases=content.matched_terms if isinstance(content.matched_terms, list) else [],
        negative_phrases=list(content.negative_signals.keys()) if isinstance(content.negative_signals, dict) else [],
        service_tags=content.service_tags if isinstance(content.service_tags, list) else [],
        reactions_count=content.reactions_count,
        comments_count=content.comments_count,
        reposts_count=content.reposts_count,
        evidence=content.evidence if isinstance(content.evidence, list) else [],
        raw_metadata=content.raw_metadata if isinstance(content.raw_metadata, dict) else {},
        user_annotation=user_ann,
    )


async def list_posts(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    q: str | None = None,
    intent: str | None = None,
    retrieval_status: str | None = None,
    min_confidence: float | None = None,
    lead_status: str | None = None,
    is_hot: bool | None = None,
    service_tag: str | None = None,
    discovery_run_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    platform: str | None = None,
    sort: str = "discovered_at",
    descending: bool = True,
    limit: int = 25,
    offset: int = 0,
) -> PostListOut:
    """Server-side filtering, searching, and pagination for the Post Explorer."""
    base_query = (
        select(SocialContent, SocialPlatform.slug, SocialContentUserAnnotation)
        .join(SocialPlatform, SocialPlatform.id == SocialContent.platform_id)
        .outerjoin(
            SocialContentUserAnnotation,
            and_(
                SocialContentUserAnnotation.content_id == SocialContent.id,
                SocialContentUserAnnotation.owner_user_id == owner_user_id,
            ),
        )
        .where(SocialContent.owner_user_id == owner_user_id)
    )

    filters = []

    if q and q.strip():
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                SocialContent.title.ilike(term),
                SocialContent.snippet.ilike(term),
                SocialContent.content_text.ilike(term),
                SocialContent.author_name.ilike(term),
                SocialContent.author_username.ilike(term),
            )
        )

    if intent and intent.strip() and intent.lower() != "all":
        filters.append(SocialContent.classification == intent.strip())

    if retrieval_status and retrieval_status.strip() and retrieval_status.lower() != "all":
        filters.append(SocialContent.retrieval_status == retrieval_status.strip())

    if min_confidence is not None and min_confidence > 0:
        filters.append(SocialContent.confidence_score >= min_confidence)

    if lead_status and lead_status.strip() and lead_status.lower() != "all":
        if lead_status == "new":
            filters.append(
                or_(
                    SocialContentUserAnnotation.lead_status == "new",
                    SocialContentUserAnnotation.lead_status.is_(None),
                )
            )
        else:
            filters.append(SocialContentUserAnnotation.lead_status == lead_status.strip())

    if is_hot is not None:
        if is_hot:
            filters.append(SocialContentUserAnnotation.is_hot.is_(True))
        else:
            filters.append(
                or_(
                    SocialContentUserAnnotation.is_hot.is_(False),
                    SocialContentUserAnnotation.is_hot.is_(None),
                )
            )

    if service_tag and service_tag.strip() and service_tag.lower() != "all":
        filters.append(SocialContent.service_tags.contains([service_tag.strip()]))

    if discovery_run_id:
        filters.append(SocialContent.discovery_run_id == discovery_run_id)

    if date_from:
        filters.append(SocialContent.discovered_at >= date_from)

    if date_to:
        filters.append(SocialContent.discovered_at <= date_to)

    if platform and platform.strip() and platform.lower() != "all":
        filters.append(SocialPlatform.slug == platform.strip().lower())

    if filters:
        base_query = base_query.where(and_(*filters))

    # Count total matching rows
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await session.scalar(count_query)) or 0

    # Sorting
    sort_column = SocialContent.discovered_at
    if sort == "published_at":
        sort_column = SocialContent.published_at
    elif sort == "confidence_score":
        sort_column = SocialContent.confidence_score
    elif sort == "classification_score":
        sort_column = SocialContent.classification_score

    order_expr = desc(sort_column) if descending else sort_column
    paginated_query = base_query.order_by(order_expr).limit(limit).offset(offset)

    rows = (await session.execute(paginated_query)).all()
    items = [_build_post_out(content, p_slug, annotation) for content, p_slug, annotation in rows]

    # Calculate summary metrics for the explorer
    summary_query = select(
        func.count(SocialContent.id).label("total"),
        func.count(
            case(
                (
                    SocialContent.classification.in_(
                        ["Service needed", "Freelancer hiring", "Vendor search", "Recommendation request", "Project help"]
                    ),
                    1,
                )
            )
        ).label("demand_count"),
        func.count(case((SocialContent.confidence_score >= 70, 1))).label("high_confidence"),
    ).where(SocialContent.owner_user_id == owner_user_id)
    summary_row = (await session.execute(summary_query)).first()

    hot_count = await session.scalar(
        select(func.count(SocialContentUserAnnotation.id)).where(
            SocialContentUserAnnotation.owner_user_id == owner_user_id,
            SocialContentUserAnnotation.is_hot.is_(True),
        )
    )

    summary = {
        "total_posts": summary_row.total if summary_row else 0,
        "demand_posts": summary_row.demand_count if summary_row else 0,
        "high_confidence": summary_row.high_confidence if summary_row else 0,
        "hot_leads": hot_count or 0,
    }

    return PostListOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        summary=summary,
    )


async def get_post(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    post_id: uuid.UUID,
) -> PostOut:
    stmt = (
        select(SocialContent, SocialPlatform.slug, SocialContentUserAnnotation)
        .join(SocialPlatform, SocialPlatform.id == SocialContent.platform_id)
        .outerjoin(
            SocialContentUserAnnotation,
            and_(
                SocialContentUserAnnotation.content_id == SocialContent.id,
                SocialContentUserAnnotation.owner_user_id == owner_user_id,
            ),
        )
        .where(
            SocialContent.id == post_id,
            SocialContent.owner_user_id == owner_user_id,
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise NotFoundError(f"Post with id {post_id} not found")

    content, p_slug, annotation = row
    return _build_post_out(content, p_slug, annotation)


async def update_post_annotation(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    post_id: uuid.UUID,
    payload: PostAnnotationIn,
) -> PostAnnotationOut:
    """Updates user-owned annotations without modifying raw crawler data."""
    # Check post ownership
    content = await session.get(SocialContent, post_id)
    if content is None or content.owner_user_id != owner_user_id:
        raise NotFoundError("Post not found")

    stmt = select(SocialContentUserAnnotation).where(
        SocialContentUserAnnotation.content_id == post_id,
        SocialContentUserAnnotation.owner_user_id == owner_user_id,
    )
    annotation = await session.scalar(stmt)

    if annotation is None:
        annotation = SocialContentUserAnnotation(
            id=uuid.uuid4(),
            content_id=post_id,
            owner_user_id=owner_user_id,
        )
        session.add(annotation)

    if payload.lead_status is not None:
        annotation.lead_status = payload.lead_status
    if payload.is_hot is not None:
        annotation.is_hot = payload.is_hot
    if payload.follow_up_date is not None:
        annotation.follow_up_date = payload.follow_up_date
    if payload.user_note is not None:
        annotation.user_note = payload.user_note
    if payload.quoted_customer_need is not None:
        annotation.quoted_customer_need = payload.quoted_customer_need
    if payload.services_to_sell is not None:
        annotation.services_to_sell = payload.services_to_sell
    if payload.is_saved is not None:
        annotation.is_saved = payload.is_saved

    annotation.updated_at = datetime.now(UTC)
    await session.commit()
    return PostAnnotationOut.model_validate(annotation)


async def retry_post_fetch(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    post_id: uuid.UUID,
) -> PostOut:
    """Re-attempts public page retrieval on the post's target URL."""
    stmt = (
        select(SocialContent, SocialPlatform.slug, SocialContentUserAnnotation)
        .join(SocialPlatform, SocialPlatform.id == SocialContent.platform_id)
        .outerjoin(
            SocialContentUserAnnotation,
            and_(
                SocialContentUserAnnotation.content_id == SocialContent.id,
                SocialContentUserAnnotation.owner_user_id == owner_user_id,
            ),
        )
        .where(
            SocialContent.id == post_id,
            SocialContent.owner_user_id == owner_user_id,
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise NotFoundError("Post not found")

    content, p_slug, annotation = row
    target_url = content.canonical_url or content.content_url
    if not target_url:
        content.retrieval_status = "unsupported"
        content.retrieval_error = "No URL available to fetch"
        await session.commit()
        return _build_post_out(content, p_slug, annotation)

    try:
        result = await fetch_public_page(target_url)
        if result.status == "ok":
            body = result.description or result.title or ""
            content.content_text = body[:8000]
            content.title = result.title or content.title
            if result.published_at is not None:
                content.published_at = result.published_at
            content.retrieval_status = "full_text"
            content.retrieval_error = None
            content.extraction_method = result.extraction_method

            # Re-classify with full text
            outcome = classify(content.content_text, "demand")
            content.classification = outcome.category
            content.confidence_score = outcome.confidence
            content.classification_score = outcome.score
            content.service_tags = list(outcome.service_mapping)
            content.evidence = [dict(e) for e in outcome.evidence]
        elif result.status == "blocked":
            content.retrieval_status = "blocked"
            content.retrieval_error = "; ".join(result.notes) or "Authentication wall or access blocked"
        else:
            content.retrieval_status = "unsupported"
            content.retrieval_error = "; ".join(result.notes) or "Unsupported content type"
    except Exception as exc:
        content.retrieval_status = "failed"
        content.retrieval_error = str(exc)[:300]

    content.updated_at = datetime.now(UTC)
    await session.commit()
    return _build_post_out(content, p_slug, annotation)


async def bulk_post_action(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    payload: PostBulkActionIn,
) -> dict[str, Any]:
    """Applies bulk actions across selected post records."""
    if not payload.post_ids:
        return {"updated": 0}

    # Verify posts ownership
    posts = (
        await session.scalars(
            select(SocialContent.id).where(
                SocialContent.id.in_(payload.post_ids),
                SocialContent.owner_user_id == owner_user_id,
            )
        )
    ).all()

    updated = 0
    now = datetime.now(UTC)

    for p_id in posts:
        stmt = select(SocialContentUserAnnotation).where(
            SocialContentUserAnnotation.content_id == p_id,
            SocialContentUserAnnotation.owner_user_id == owner_user_id,
        )
        ann = await session.scalar(stmt)
        if ann is None:
            ann = SocialContentUserAnnotation(
                id=uuid.uuid4(),
                content_id=p_id,
                owner_user_id=owner_user_id,
            )
            session.add(ann)

        if payload.action == "set_hot":
            ann.is_hot = True
            ann.updated_at = now
            updated += 1
        elif payload.action == "unset_hot":
            ann.is_hot = False
            ann.updated_at = now
            updated += 1
        elif payload.action == "set_status" and payload.value:
            ann.lead_status = payload.value
            ann.updated_at = now
            updated += 1
        elif payload.action == "save":
            ann.is_saved = True
            ann.updated_at = now
            updated += 1

    await session.commit()
    return {"updated": updated}


async def get_leads_dashboard(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
) -> LeadsDashboardOut:
    """Aggregates truthful, database-driven metrics for the Leads Dashboard."""
    # 1. Total counts
    demand_categories = ["Service needed", "Freelancer hiring", "Vendor search", "Recommendation request", "Project help"]

    demand_count = await session.scalar(
        select(func.count(SocialContent.id)).where(
            SocialContent.owner_user_id == owner_user_id,
            SocialContent.classification.in_(demand_categories),
        )
    ) or 0

    high_confidence_count = await session.scalar(
        select(func.count(SocialContent.id)).where(
            SocialContent.owner_user_id == owner_user_id,
            SocialContent.confidence_score >= 70,
        )
    ) or 0

    posts_discovered = await session.scalar(
        select(func.count(SocialContent.id)).where(
            SocialContent.owner_user_id == owner_user_id,
        )
    ) or 0

    duplicates_removed = await session.scalar(
        select(func.coalesce(func.sum(SocialDiscoveryRun.duplicates), 0)).where(
            SocialDiscoveryRun.owner_user_id == owner_user_id,
        )
    ) or 0

    scheduled_runs = await session.scalar(
        select(func.count(SocialSearchTrack.id)).where(
            SocialSearchTrack.owner_user_id == owner_user_id,
            SocialSearchTrack.is_enabled.is_(True),
        )
    ) or 0

    # 2. Latest 5 demand posts
    latest_rows = (
        await session.execute(
            select(SocialContent, SocialPlatform.slug, SocialContentUserAnnotation)
            .join(SocialPlatform, SocialPlatform.id == SocialContent.platform_id)
            .outerjoin(
                SocialContentUserAnnotation,
                and_(
                    SocialContentUserAnnotation.content_id == SocialContent.id,
                    SocialContentUserAnnotation.owner_user_id == owner_user_id,
                ),
            )
            .where(
                SocialContent.owner_user_id == owner_user_id,
                SocialContent.classification.in_(demand_categories),
            )
            .order_by(desc(SocialContent.discovered_at))
            .limit(5)
        )
    ).all()
    latest_demand_posts = [_build_post_out(c, slug, ann) for c, slug, ann in latest_rows]

    # 3. Classification distribution
    dist_rows = (
        await session.execute(
            select(SocialContent.classification, func.count(SocialContent.id))
            .where(SocialContent.owner_user_id == owner_user_id)
            .group_by(SocialContent.classification)
        )
    ).all()
    classification_dist = {r[0] or "Unclassified": r[1] for r in dist_rows}

    # 4. Recent runs
    runs_rows = (
        await session.execute(
            select(SocialDiscoveryRun)
            .where(SocialDiscoveryRun.owner_user_id == owner_user_id)
            .order_by(desc(SocialDiscoveryRun.created_at))
            .limit(5)
        )
    ).scalars().all()
    recent_runs = [
        {
            "id": str(r.id),
            "status": r.status,
            "trigger_type": r.trigger_type,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "results_returned": r.results_returned,
            "stored_new": r.stored_new,
            "duplicates": r.duplicates,
            "duration_ms": r.duration_ms,
        }
        for r in runs_rows
    ]

    # 5. Posts discovered per day (last 7 days from real DB timestamps)
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)
    daily_rows = (
        await session.execute(
            select(
                func.date(SocialContent.discovered_at).label("day"),
                func.count(SocialContent.id).label("count"),
            )
            .where(
                SocialContent.owner_user_id == owner_user_id,
                SocialContent.discovered_at >= seven_days_ago,
            )
            .group_by(func.date(SocialContent.discovered_at))
            .order_by(func.date(SocialContent.discovered_at))
        )
    ).all()

    # Fill in any missing days in the last 7 days with honest 0
    daily_map = {str(r[0]): r[1] for r in daily_rows}
    posts_per_day = []
    for i in range(7):
        day_date = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        posts_per_day.append({
            "date": day_date,
            "count": daily_map.get(day_date, 0),
        })

    return LeadsDashboardOut(
        demand_posts_found=demand_count,
        high_confidence_leads=high_confidence_count,
        posts_discovered=posts_discovered,
        duplicates_removed=int(duplicates_removed),
        scheduled_runs=scheduled_runs,
        latest_demand_posts=latest_demand_posts,
        classification_distribution=classification_dist,
        recent_runs=recent_runs,
        posts_per_day=posts_per_day,
    )

