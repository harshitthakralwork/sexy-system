from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy import select

from app.core.audit import client_ip, record_audit
from app.core.config import get_settings
from app.core.database import AsyncSession, AsyncSessionDep
from app.core.exceptions import TooManyRequestsError, ValidationFailedError
from app.core.ratelimit import RateLimitRule, get_rate_limiter
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.discovery import areas as area_service
from app.modules.discovery import job_service, runner
from app.modules.discovery.models import DiscoveryJob, JobLog, Search
from app.modules.discovery.schemas import (
    DiscoveryJobIn,
    JobListOut,
    JobOut,
    SearchAreaIn,
    SearchAreaListOut,
    SearchAreaOut,
    TileBatchOut,
)
from app.modules.discovery.tiles import TilePlanError
from app.shared.geo import Area

router = APIRouter(prefix="/discovery", tags=["discovery"])

Csrf = Depends(require_csrf_for_state_changes())

# Starting a sweep reaches out to external sources, so it is throttled like any
# other expensive action: generous enough for real work, tight enough that a
# runaway script cannot queue hundreds of concurrent crawls.
JOB_RULE = RateLimitRule(max_attempts=10, window_seconds=300)
AREA_RULE = RateLimitRule(max_attempts=60, window_seconds=300)


def _job_out(job: DiscoveryJob, area_id: uuid.UUID | None = None) -> JobOut:
    out = JobOut.model_validate(job)
    out.area_id = area_id
    return out


async def _area_ids_for(
    session: AsyncSession, jobs: list[DiscoveryJob]
) -> dict[uuid.UUID | None, uuid.UUID]:
    """One query for the area behind each job, rather than one per row.

    Keyed by search id because that is the row that carries the area; a job with no
    search, or a search with no saved area, simply has no entry.
    """
    search_ids = [job.search_id for job in jobs if job.search_id]
    if not search_ids:
        return {}
    rows = await session.execute(
        select(Search.id, Search.area_id).where(
            Search.id.in_(search_ids), Search.area_id.is_not(None)
        )
    )
    return {row.id: row.area_id for row in rows.all() if row.area_id is not None}


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: Request,
    payload: DiscoveryJobIn,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> JobOut:
    """Queue a discovery job, then let the configured runner work on it.

    The area is resolved and the tile plan computed *before* the job is accepted, so
    a region that would need more requests than the limit allows is refused with the
    number it would have produced — instead of being quietly searched in part.
    """
    allowed, retry_after = get_rate_limiter().check("discovery_job", str(user.id), JOB_RULE)
    if not allowed:
        raise TooManyRequestsError(
            "Too many discovery jobs queued. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
            details={"retry_after_seconds": int(retry_after)},
        )

    unknown = sorted(set(payload.sources or []) - set(runner.AVAILABLE_SOURCE_SLUGS))
    if unknown:
        # Refused here rather than deep in a background job: a source with no
        # adapter can never produce results, and queuing it would only create a
        # job row that fails for a reason the caller could have been told.
        raise ValidationFailedError(
            "Unknown discovery source requested",
            details={"unknown_sources": unknown, "available": list(runner.AVAILABLE_SOURCE_SLUGS)},
        )

    settings = get_settings()
    area: Area | None = await area_service.resolve_area_for_job(session, payload, user.id)
    if area is not None:
        try:
            runner.plan_units(area, payload.to_query(area), settings)
        except TilePlanError as exc:
            raise ValidationFailedError(exc.message, details=exc.details) from exc

    job = await job_service.create_job(
        session,
        owner_user_id=user.id,
        config=payload.to_config(area),
        correlation_id=getattr(request.state, "correlation_id", None),
        area_id=payload.area_id,
    )
    dispatch_mode = await runner.dispatch(session, job, background)
    await record_audit(
        session,
        action="discovery.job_created",
        owner_user_id=user.id,
        entity_type="discovery_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={
            "dispatch": dispatch_mode,
            "sources": payload.sources,
            "area_id": str(payload.area_id) if payload.area_id else None,
        },
    )
    return _job_out(job, payload.area_id)


@router.get("/jobs", response_model=JobListOut)
async def list_jobs(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobListOut:
    jobs, total = await job_service.list_jobs(session, user.id, limit=limit, offset=offset)
    area_ids = await _area_ids_for(session, jobs)
    items = [_job_out(job, area_ids.get(job.search_id)) for job in jobs]
    return JobListOut(items=items, total=total)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser) -> JobOut:
    job = await job_service.get_job(session, job_id, user.id)
    area_ids = await _area_ids_for(session, [job])
    return _job_out(job, area_ids.get(job.search_id))


@router.get("/jobs/{job_id}/batches", response_model=list[TileBatchOut])
async def job_batches(
    job_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> list[TileBatchOut]:
    """Per-tile state, so a partly covered region is visible as partly covered."""
    batches = await job_service.list_batches(session, job_id, user.id)
    return [TileBatchOut.model_validate(batch) for batch in batches]


@router.get("/jobs/{job_id}/logs")
async def job_logs(
    job_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    """What the job actually did, in the order it said it.

    Exposed because "completed" is not an explanation. When a source refused to
    answer, the operator has to see that rather than infer it from a low count.
    """
    job = await job_service.get_job(session, job_id, user.id)
    rows = (
        await session.scalars(
            select(JobLog)
            .where(JobLog.job_id == job.id)
            .order_by(JobLog.created_at.asc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "level": row.level,
            "message": row.message,
            "metadata": row.metadata_,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    request: Request,
    job_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> JobOut:
    job = await job_service.cancel_job(session, job_id, user.id)
    await record_audit(
        session,
        action="discovery.job_cancelled",
        owner_user_id=user.id,
        entity_type="discovery_job",
        entity_id=job.id,
        ip_address=client_ip(request),
    )
    return _job_out(job)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(
    request: Request,
    job_id: uuid.UUID,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> JobOut:
    """Re-queue a failed, blocked or cancelled job.

    A completed job is refused — re-running a sweep that already ran would
    re-query shared infrastructure for nothing. Records stored by the previous
    attempt are kept; the retry merges, it does not un-run history.
    """
    allowed, retry_after = get_rate_limiter().check("discovery_job_retry", str(user.id), JOB_RULE)
    if not allowed:
        raise TooManyRequestsError(
            "Too many retries requested. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
            details={"retry_after_seconds": int(retry_after)},
        )
    job = await job_service.reset_for_retry(session, job_id, user.id)
    dispatch_mode = await runner.dispatch(session, job, background)
    await record_audit(
        session,
        action="discovery.job_retried",
        owner_user_id=user.id,
        entity_type="discovery_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={"dispatch": dispatch_mode, "retry_count": job.retry_count},
    )
    return _job_out(job)


@router.post("/areas", response_model=SearchAreaOut, status_code=status.HTTP_201_CREATED)
async def create_area(
    request: Request,
    payload: SearchAreaIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> SearchAreaOut:
    """Save a shape the user drew or resolved, so it can be re-run later."""
    allowed, retry_after = get_rate_limiter().check("search_area", str(user.id), AREA_RULE)
    if not allowed:
        raise TooManyRequestsError(
            "Too many saved areas created. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
        )
    row = await area_service.create_area(session, owner_user_id=user.id, payload=payload)
    await record_audit(
        session,
        action="area.create",
        owner_user_id=user.id,
        entity_type="search_area",
        entity_id=row.id,
        ip_address=client_ip(request),
        metadata={"shape_type": row.shape_type, "area_km2": float(row.area_km2)},
    )
    return SearchAreaOut.model_validate(row)


@router.get("/areas", response_model=SearchAreaListOut)
async def list_areas(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SearchAreaListOut:
    rows, total = await area_service.list_areas(session, user.id, limit=limit, offset=offset)
    return SearchAreaListOut(
        items=[SearchAreaOut.model_validate(row) for row in rows], total=total
    )


@router.get("/areas/{area_id}", response_model=SearchAreaOut)
async def get_area(
    area_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> SearchAreaOut:
    row = await area_service.get_area(session, area_id, user.id)
    return SearchAreaOut.model_validate(row)


@router.put("/areas/{area_id}", response_model=SearchAreaOut)
async def update_area(
    request: Request,
    area_id: uuid.UUID,
    payload: SearchAreaIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> SearchAreaOut:
    row = await area_service.update_area(session, area_id, user.id, payload)
    await record_audit(
        session,
        action="area.update",
        owner_user_id=user.id,
        entity_type="search_area",
        entity_id=row.id,
        ip_address=client_ip(request),
        metadata={"shape_type": row.shape_type, "area_km2": float(row.area_km2)},
    )
    return SearchAreaOut.model_validate(row)


@router.delete("/areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_area(
    request: Request,
    area_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> None:
    """Soft delete. Past jobs keep their geometry; the area stops being selectable."""
    await area_service.delete_area(session, area_id, user.id)
    await record_audit(
        session,
        action="area.delete",
        owner_user_id=user.id,
        entity_type="search_area",
        entity_id=area_id,
        ip_address=client_ip(request),
    )
