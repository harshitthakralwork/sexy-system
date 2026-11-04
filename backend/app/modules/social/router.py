from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from app.core.audit import client_ip, record_audit
from app.core.config import get_settings
from app.core.database import AsyncSessionDep
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.exports.csv_export import to_csv
from app.modules.social import post_service, service, tracks
from app.modules.social.models import SocialContent, SocialResearchQuery
from app.modules.social.schemas import (
    ConvertResultOut,
    DiscoveryRunListOut,
    DiscoveryRunOut,
    IntelligenceListOut,
    IntelligenceResultOut,
    LeadsDashboardOut,
    NotificationOut,
    PostAnnotationIn,
    PostAnnotationOut,
    PostBulkActionIn,
    PostListOut,
    PostOut,
    SavedItemIn,
    SavedItemOut,
    SocialContentListOut,
    SocialContentOut,
    SocialLinkIn,
    SocialLinkOut,
    SocialPlatformOut,
    SocialResearchQueryCreateIn,
    SocialResearchQueryListOut,
    SocialResearchQueryOut,
    SocialRunOut,
    TrackCreateIn,
    TrackListOut,
    TrackOut,
    TrackRunOut,
    TrackUpdateIn,
)

router = APIRouter(prefix="/social", tags=["social"])

Csrf = Depends(require_csrf_for_state_changes())

SOCIAL_CONTENT_COLUMNS = (
    "platform",
    "content_type",
    "content_url",
    "content_text",
    "author_username",
    "author_profile_url",
    "published_at",
    "collected_at",
    "engagement_score",
    "engagement_comments",
    "subreddit",
)


def _query_out(row: SocialResearchQuery, platform_slug: str) -> SocialResearchQueryOut:
    return SocialResearchQueryOut(
        id=row.id,
        platform_id=row.platform_id,
        platform_slug=platform_slug,
        query_config=row.query_config,
        last_run_at=row.last_run_at,
        last_run_status=row.last_run_status,
        last_run_error=row.last_run_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/platforms", response_model=list[SocialPlatformOut])
async def list_platforms(session: AsyncSessionDep) -> list[SocialPlatformOut]:
    rows = await service.list_platforms(session)
    return [SocialPlatformOut.model_validate(row) for row in rows]


@router.get("/research-queries", response_model=SocialResearchQueryListOut)
async def list_research_queries(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SocialResearchQueryListOut:
    rows, total = await service.list_research_queries(
        session, owner_user_id=user.id, limit=limit, offset=offset
    )
    platforms = {row.id: row for row in await service.list_platforms(session)}
    return SocialResearchQueryListOut(
        items=[
            _query_out(
                row,
                platforms[row.platform_id].slug if row.platform_id in platforms else "unknown",
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/research-queries",
    response_model=SocialResearchQueryOut,
    status_code=201,
    dependencies=[Csrf],
)
async def create_research_query(
    payload: SocialResearchQueryCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> SocialResearchQueryOut:
    row = await service.create_research_query(
        session,
        owner_user_id=user.id,
        platform_slug=payload.platform_slug,
        query_config=payload.query_config,
        settings=get_settings(),
    )
    return _query_out(row, payload.platform_slug)


@router.delete("/research-queries/{query_id}", response_model=dict, dependencies=[Csrf])
async def delete_research_query(
    query_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_research_query(session, owner_user_id=user.id, query_id=query_id)
    return {"id": str(query_id), "message": "Deleted"}


@router.post("/research-queries/{query_id}/run", response_model=SocialRunOut, dependencies=[Csrf])
async def run_research_query(
    request: Request,
    query_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> SocialRunOut:
    result = await service.run_research_query(
        session, owner_user_id=user.id, query_id=query_id, settings=get_settings()
    )
    await record_audit(
        session,
        action="social.research_run",
        owner_user_id=user.id,
        entity_type="social_research_query",
        entity_id=query_id,
        ip_address=client_ip(request),
        metadata={"status": result["status"], "collected": result["collected"]},
    )
    return SocialRunOut(**result)


@router.get("/content", response_model=SocialContentListOut)
async def list_content(
    session: AsyncSessionDep,
    user: CurrentUser,
    platform_slug: str | None = Query(default=None, max_length=100),
    query: str | None = Query(default=None, max_length=200),
    content_type: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    all_results: bool = Query(default=False),
) -> SocialContentListOut:
    rows, total = await service.list_content(
        session,
        owner_user_id=user.id,
        platform_slug=platform_slug,
        query=query,
        content_type=content_type,
        limit=None if all_results else limit,
        offset=0 if all_results else offset,
    )
    return SocialContentListOut(
        items=[
            SocialContentOut(
                id=content.id,
                platform_id=content.platform_id,
                platform_slug=slug,
                research_query_id=content.research_query_id,
                profile_id=content.profile_id,
                external_id=content.external_id,
                content_url=content.content_url,
                content_type=content.content_type,
                content_text=content.content_text,
                published_at=content.published_at,
                engagement_data=content.engagement_data or {},
                author_username=author_username,
                author_profile_url=author_profile_url,
                collected_at=content.collected_at,
            )
            for content, slug, author_username, author_profile_url in rows
        ],
        total=total,
        limit=total if all_results else limit,
        offset=0 if all_results else offset,
    )


@router.get("/content/export", response_class=Response)
async def export_content(
    request: Request,
    session: AsyncSessionDep,
    user: CurrentUser,
    platform_slug: str | None = Query(default=None, max_length=100),
    content_type: str | None = Query(default=None, max_length=50),
    query: str | None = Query(default=None, max_length=200),
) -> Response:
    rows, _ = await service.list_content(
        session,
        owner_user_id=user.id,
        platform_slug=platform_slug,
        query=query,
        content_type=content_type,
        limit=500,
        offset=0,
    )
    export_rows = []
    for content, slug, author_username, author_profile_url in rows:
        export_rows.append(
            service.content_export_row(content, slug, author_username, author_profile_url)
        )
    await record_audit(
        session,
        action="export.create",
        owner_user_id=user.id,
        entity_type="export_job",
        ip_address=client_ip(request),
        metadata={"format": "csv", "module": "social", "record_count": len(export_rows)},
    )
    body = to_csv(export_rows, columns=SOCIAL_CONTENT_COLUMNS)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sparkxflow-social.csv"'},
    )


@router.delete("/content", response_model=dict, dependencies=[Csrf])
async def delete_all_content(
    request: Request,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    deleted = await service.delete_all_content(session, owner_user_id=user.id)
    await record_audit(
        session,
        action="social.content_delete_all",
        owner_user_id=user.id,
        entity_type="social_content",
        ip_address=client_ip(request),
        metadata={"deleted": deleted},
    )
    return {"deleted": deleted, "message": "All collected content deleted"}


@router.delete("/content/{content_id}", response_model=dict, dependencies=[Csrf])
async def delete_content(
    content_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_content(session, owner_user_id=user.id, content_id=content_id)
    return {"id": str(content_id), "message": "Deleted"}


@router.post(
    "/content/{content_id}/link",
    response_model=SocialLinkOut,
    dependencies=[Csrf],
)
async def link_content(
    request: Request,
    content_id: uuid.UUID,
    payload: SocialLinkIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> SocialLinkOut:
    link = await service.link_content_to_business(
        session,
        owner_user_id=user.id,
        content_id=content_id,
        business_id=payload.business_id,
    )
    await record_audit(
        session,
        action="social.link",
        owner_user_id=user.id,
        entity_type="business_social_profile",
        entity_id=link.id,
        ip_address=client_ip(request),
        metadata={"business_id": str(payload.business_id), "platform": link.platform},
    )
    return SocialLinkOut(
        business_id=payload.business_id, platform=link.platform, profile_url=link.profile_url
    )


# --- Intelligence tracks, runs, results, saved items (engine) ---------------


INTELLIGENCE_COLUMNS = (
    "platform",
    "track_type",
    "classification",
    "confidence_score",
    "retrieval_status",
    "title",
    "content_url",
    "content_text",
    "matched_terms",
    "published_at",
    "discovered_at",
    "author_username",
    "needs_review",
)


def _intelligence_out(
    content: SocialContent, slug: str, username: str | None
) -> IntelligenceResultOut:
    return IntelligenceResultOut(
        id=content.id,
        platform_id=content.platform_id,
        platform_slug=slug,
        external_id=content.external_id,
        content_type=content.content_type,
        title=content.title,
        snippet=content.snippet,
        content_text=content.content_text,
        content_url=content.content_url,
        canonical_url=content.canonical_url,
        published_at=content.published_at,
        discovered_at=content.discovered_at,
        retrieval_status=content.retrieval_status,
        track_type=content.track_type,
        classification=content.classification,
        confidence_score=(
            float(content.confidence_score) if content.confidence_score is not None else None
        ),
        classification_method=content.classification_method,
        matched_terms=content.matched_terms or [],
        evidence=content.evidence or [],
        needs_review=content.needs_review,
        source_attribution=content.source_attribution or [],
        author_username=username,
        collected_at=content.collected_at,
    )


@router.get("/tracks", response_model=TrackListOut)
async def list_tracks(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TrackListOut:
    rows, total = await tracks.list_tracks(session, user.id, limit=limit, offset=offset)
    return TrackListOut(
        items=[TrackOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/tracks", response_model=TrackOut, status_code=201, dependencies=[Csrf])
async def create_track(
    payload: TrackCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> TrackOut:
    track = await tracks.create_track(session, user.id, payload)
    await record_audit(
        session,
        action="social.track_created",
        owner_user_id=user.id,
        entity_type="social_search_track",
        entity_id=track.id,
        ip_address=client_ip(request),
        metadata={"track_type": track.track_type, "platforms": track.platforms},
    )
    return TrackOut.model_validate(track)


@router.get("/tracks/{track_id}", response_model=TrackOut)
async def get_track(
    track_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> TrackOut:
    from app.core.exceptions import NotFoundError

    track = await tracks.get_track(session, user.id, track_id)
    if track is None:
        raise NotFoundError("Track not found")
    return TrackOut.model_validate(track)


@router.patch("/tracks/{track_id}", response_model=TrackOut, dependencies=[Csrf])
async def update_track(
    track_id: uuid.UUID,
    payload: TrackUpdateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> TrackOut:
    track = await tracks.update_track(session, user.id, track_id, payload)
    await record_audit(
        session,
        action="social.track_updated",
        owner_user_id=user.id,
        entity_type="social_search_track",
        entity_id=track.id,
        ip_address=client_ip(request),
    )
    return TrackOut.model_validate(track)


@router.delete("/tracks/{track_id}", status_code=204, dependencies=[Csrf])
async def delete_track(
    track_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> None:
    await tracks.delete_track(session, user.id, track_id)
    await record_audit(
        session,
        action="social.track_deleted",
        owner_user_id=user.id,
        entity_type="social_search_track",
        entity_id=track_id,
        ip_address=client_ip(request),
    )


@router.post(
    "/tracks/{track_id}/run", response_model=TrackRunOut, status_code=201, dependencies=[Csrf]
)
async def run_track(
    track_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
    background: BackgroundTasks,
) -> TrackRunOut:
    run = await tracks.start_track_run(
        session, owner_user_id=user.id, track_id=track_id, trigger_type="manual"
    )
    mode = await tracks.dispatch_run(session, run, background)
    await record_audit(
        session,
        action="social.track_run",
        owner_user_id=user.id,
        entity_type="social_search_track",
        entity_id=track_id,
        ip_address=client_ip(request),
        metadata={"run_id": str(run.id), "dispatch": mode},
    )
    return TrackRunOut(run_id=run.id, status=run.status)


@router.get("/tracks/{track_id}/runs", response_model=DiscoveryRunListOut)
async def list_track_runs(
    track_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DiscoveryRunListOut:
    rows, total = await tracks.list_runs(
        session, user.id, track_id=track_id, limit=limit, offset=offset
    )
    return DiscoveryRunListOut(
        items=[DiscoveryRunOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/results", response_model=IntelligenceListOut)
async def list_results(
    session: AsyncSessionDep,
    user: CurrentUser,
    track_type: str | None = Query(default=None, max_length=20),
    platform_slug: str | None = Query(default=None, max_length=100),
    classification: str | None = Query(default=None, max_length=100),
    min_confidence: float | None = Query(default=None, ge=0, le=100),
    retrieval_status: str | None = Query(default=None, max_length=50),
    needs_review: bool | None = Query(default=None),
    saved_only: bool | None = Query(default=None),
    query: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IntelligenceListOut:
    rows, total = await tracks.list_intelligence(
        session,
        user.id,
        track_type=track_type,
        platform_slug=platform_slug,
        classification=classification,
        min_confidence=min_confidence,
        retrieval_status=retrieval_status,
        needs_review=needs_review,
        saved_only=saved_only,
        query=query,
        limit=limit,
        offset=offset,
    )
    return IntelligenceListOut(
        items=[_intelligence_out(content, slug, username) for content, slug, username in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/results/export", response_class=Response)
async def export_results(
    request: Request,
    session: AsyncSessionDep,
    user: CurrentUser,
    track_type: str | None = Query(default=None, max_length=20),
    classification: str | None = Query(default=None, max_length=100),
    min_confidence: float | None = Query(default=None, ge=0, le=100),
    saved_only: bool | None = Query(default=None),
    format: str = Query(default="csv", pattern="^(csv|json)$"),
) -> Response:
    rows, _ = await tracks.list_intelligence(
        session,
        user.id,
        track_type=track_type,
        classification=classification,
        min_confidence=min_confidence,
        saved_only=saved_only,
        limit=500,
        offset=0,
    )
    export_rows = []
    for content, slug, username in rows:
        export_rows.append(service.intelligence_export_row(content, slug, username))
    await record_audit(
        session,
        action="export.create",
        owner_user_id=user.id,
        entity_type="export_job",
        ip_address=client_ip(request),
        metadata={
            "format": format,
            "module": "social_intelligence",
            "record_count": len(export_rows),
        },
    )
    if format == "json":
        return JSONResponse(content=export_rows)
    body = to_csv(export_rows, columns=INTELLIGENCE_COLUMNS)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sparkxflow-intelligence.csv"'},
    )


@router.post("/results/{content_id}/convert", response_model=ConvertResultOut, dependencies=[Csrf])
async def convert_result(
    content_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> ConvertResultOut:
    business_id = await tracks.convert_result_to_lead(session, user.id, content_id)
    await record_audit(
        session,
        action="social.item_converted",
        owner_user_id=user.id,
        entity_type="business",
        entity_id=business_id,
        ip_address=client_ip(request),
        metadata={"from": "social_intelligence", "content_id": str(content_id)},
    )
    return ConvertResultOut(
        content_id=content_id,
        business_id=business_id,
        message="Converted to a Leads business (an existing match was reused if found).",
    )


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[NotificationOut]:
    rows, _ = await tracks.list_notifications(session, user.id, limit=limit, offset=offset)
    return [NotificationOut.model_validate(row) for row in rows]


@router.post("/notifications/{notification_id}/read", status_code=204, dependencies=[Csrf])
async def mark_notification_read(
    notification_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> None:
    await tracks.mark_notification_read(session, user.id, notification_id)


@router.post("/results/{content_id}/save", response_model=SavedItemOut, dependencies=[Csrf])
async def save_result(
    content_id: uuid.UUID,
    payload: SavedItemIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> SavedItemOut:
    item = await tracks.save_item(
        session, user.id, content_id, note=payload.note, tags=payload.tags
    )
    await record_audit(
        session,
        action="social.item_saved",
        owner_user_id=user.id,
        entity_type="social_content",
        entity_id=content_id,
        ip_address=client_ip(request),
    )
    return SavedItemOut.model_validate(item)


@router.delete("/results/{content_id}/save", status_code=204, dependencies=[Csrf])
async def unsave_result(
    content_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> None:
    await tracks.unsave_item(session, user.id, content_id)
    await record_audit(
        session,
        action="social.item_unsaved",
        owner_user_id=user.id,
        entity_type="social_content",
        entity_id=content_id,
        ip_address=client_ip(request),
    )


@router.get("/saved", response_model=list[SavedItemOut])
async def list_saved(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SavedItemOut]:
    rows, _ = await tracks.list_saved(session, user.id, limit=limit, offset=offset)
    return [SavedItemOut.model_validate(row) for row in rows]


# --- Post & Lead Intelligence Endpoints ------------------------------------


@router.get("/posts", response_model=PostListOut)
async def list_posts(
    session: AsyncSessionDep,
    user: CurrentUser,
    q: str | None = Query(default=None, max_length=200),
    intent: str | None = Query(default=None, max_length=100),
    retrieval_status: str | None = Query(default=None, max_length=50),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    lead_status: str | None = Query(default=None, max_length=50),
    is_hot: bool | None = Query(default=None),
    service_tag: str | None = Query(default=None, max_length=100),
    discovery_run_id: uuid.UUID | None = Query(default=None),
    platform: str | None = Query(default=None, max_length=50),
    sort_by: str = Query(default="discovered_at", max_length=50),
    sort_desc: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PostListOut:
    return await post_service.list_posts(
        session,
        user.id,
        q=q,
        intent=intent,
        retrieval_status=retrieval_status,
        min_confidence=min_confidence,
        lead_status=lead_status,
        is_hot=is_hot,
        service_tag=service_tag,
        discovery_run_id=discovery_run_id,
        platform=platform,
        sort=sort_by,
        descending=sort_desc,
        limit=limit,
        offset=offset,
    )


@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> PostOut:
    return await post_service.get_post(session, user.id, post_id)


@router.patch("/posts/{post_id}/annotation", response_model=PostAnnotationOut, dependencies=[Csrf])
async def update_post_annotation(
    post_id: uuid.UUID,
    payload: PostAnnotationIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> PostOut:
    post = await post_service.update_post_annotation(session, user.id, post_id, payload)
    await record_audit(
        session,
        action="social.post_annotated",
        owner_user_id=user.id,
        entity_type="social_content",
        entity_id=post_id,
        ip_address=client_ip(request),
        metadata={"lead_status": payload.lead_status, "is_hot": payload.is_hot},
    )
    return post


@router.post("/posts/{post_id}/retry-fetch", response_model=PostOut, dependencies=[Csrf])
async def retry_post_fetch(
    post_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> PostOut:
    post = await post_service.retry_post_fetch(session, user.id, post_id)
    await record_audit(
        session,
        action="social.post_retry_fetch",
        owner_user_id=user.id,
        entity_type="social_content",
        entity_id=post_id,
        ip_address=client_ip(request),
    )
    return post


@router.post("/posts/bulk-action", response_model=dict, dependencies=[Csrf])
async def bulk_post_action(
    payload: PostBulkActionIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> dict:
    result = await post_service.bulk_post_action(session, user.id, payload)
    await record_audit(
        session,
        action="social.posts_bulk_action",
        owner_user_id=user.id,
        entity_type="social_content",
        ip_address=client_ip(request),
        metadata={"action": payload.action, "count": len(payload.post_ids)},
    )
    return result


@router.get("/leads-dashboard", response_model=LeadsDashboardOut)
async def get_leads_dashboard(
    session: AsyncSessionDep,
    user: CurrentUser,
) -> LeadsDashboardOut:
    return await post_service.get_leads_dashboard(session, user.id)

