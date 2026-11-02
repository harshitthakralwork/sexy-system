from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import client_ip, record_audit
from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.sources import service
from app.modules.sources.schemas import (
    HealthCheckOut,
    SourceConfigIn,
    SourceConfigOut,
    SourceEnableOut,
    SourceGroupOut,
    SourceHistoryOut,
    SourceListOut,
    SourceOut,
    SourceTestOut,
    UsageRecordOut,
)

router = APIRouter(prefix="/sources", tags=["sources"])

Csrf = Depends(require_csrf_for_state_changes())


@router.get("", response_model=SourceListOut)
async def list_sources(
    session: AsyncSessionDep, user: CurrentUser, settings: Settings = Depends(get_settings)
) -> SourceListOut:
    """The registry grouped by discovery category, with this account's state on each."""
    rows = await service.list_sources(session, user.id, settings)
    by_category: dict[str, list[SourceOut]] = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(SourceOut(**row))
    groups = [
        SourceGroupOut(category=category, items=items)
        for category, items in by_category.items()
    ]
    return SourceListOut(groups=groups, total=len(rows))


@router.get("/{slug}", response_model=SourceOut)
async def get_source(
    slug: str,
    session: AsyncSessionDep,
    user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> SourceOut:
    for row in await service.list_sources(session, user.id, settings):
        if row["slug"] == slug:
            return SourceOut(**row)
    raise NotFoundError(f"Source '{slug}' is not registered")


@router.post("/{slug}/enable", response_model=SourceEnableOut, dependencies=[Csrf])
async def enable_source(
    slug: str, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> SourceEnableOut:
    config = await service.set_enabled(session, user.id, slug, True)
    await record_audit(
        session,
        action="source.enable",
        owner_user_id=user.id,
        entity_type="source",
        entity_id=config.source_id,
        ip_address=client_ip(request),
    )
    return SourceEnableOut(slug=slug, enabled_for_user=config.is_enabled)


@router.post("/{slug}/disable", response_model=SourceEnableOut, dependencies=[Csrf])
async def disable_source(
    slug: str, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> SourceEnableOut:
    config = await service.set_enabled(session, user.id, slug, False)
    await record_audit(
        session,
        action="source.disable",
        owner_user_id=user.id,
        entity_type="source",
        entity_id=config.source_id,
        ip_address=client_ip(request),
    )
    return SourceEnableOut(slug=slug, enabled_for_user=config.is_enabled)


@router.put("/{slug}/config", response_model=SourceConfigOut, dependencies=[Csrf])
async def configure_source(
    payload: SourceConfigIn,
    slug: str,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SourceConfigOut:
    configuration: dict = {}
    if payload.feed_urls:
        configuration["feed_urls"] = payload.feed_urls
    if payload.note:
        configuration["note"] = payload.note
    config = await service.configure(
        session,
        user.id,
        slug,
        settings,
        configuration,
        payload.secret_reference,
        payload.enabled,
    )
    await record_audit(
        session,
        action="source.configure",
        owner_user_id=user.id,
        entity_type="source",
        entity_id=config.source_id,
        ip_address=client_ip(request),
        # The keys, never the values: a feed list can carry a signed URL.
        metadata={"source_slug": slug, "keys": sorted(configuration)},
    )
    return SourceConfigOut.model_validate(config)


@router.post("/{slug}/test", response_model=SourceTestOut, dependencies=[Csrf])
async def test_source(
    slug: str,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SourceTestOut:
    """Probe the provider now and record what it answered."""
    result = await service.test_connection(session, slug, settings)
    source = await service.get_by_slug(session, slug)
    if source is not None:
        await record_audit(
            session,
            action="source.test",
            owner_user_id=user.id,
            entity_type="source",
            entity_id=source.id,
            ip_address=client_ip(request),
            metadata={"source_slug": slug, "status": result["status"]},
        )
    return SourceTestOut(**result)


@router.get("/{slug}/history", response_model=SourceHistoryOut)
async def source_history(
    slug: str,
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> SourceHistoryOut:
    history = await service.source_history(session, slug, limit=limit)
    return SourceHistoryOut(
        slug=slug,
        checks=[HealthCheckOut.model_validate(check) for check in history["checks"]],
        runs=[UsageRecordOut.model_validate(run) for run in history["runs"]],
    )
