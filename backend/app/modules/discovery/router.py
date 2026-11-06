from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.audit import client_ip, record_audit
from app.core.config import get_settings
from app.core.database import AsyncSession, AsyncSessionDep
from app.core.exceptions import (
    NotFoundError,
    SourceUnavailableError,
    TooManyRequestsError,
    ValidationFailedError,
)
from app.core.ratelimit import RateLimitRule, get_rate_limiter
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.businesses.models import Business
from app.modules.businesses.schemas import BulkDeleteIn, BulkDeleteOut
from app.modules.discovery import areas as area_service
from app.modules.discovery import job_service, runner, scan_service
from app.modules.discovery.local_scraper import (
    LocalScrapeRequest,
    LocalScrapeResponse,
    run_local_search_job,
    scrape_google_local,
)
from app.modules.discovery.models import DiscoveryJob, JobLog, Search
from app.modules.discovery.public_fetch import (
    PublicPageFetchRequest,
    PublicPageFetchResult,
    UnsafeUrlError,
    fetch_public_page,
)
from app.modules.discovery.scan_models import LocalScanBusiness, LocalScanRun
from app.modules.discovery.scan_schemas import ScanCreateIn, ScanRunListOut, ScanRunOut
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
# Local Business Finder performs one slow, source-respectful job at a time in
# the UI. It should not inherit the much tighter generic sweep limit, because
# correcting a city or niche would otherwise lock an operator out for minutes.
LOCAL_SEARCH_RULE = RateLimitRule(max_attempts=30, window_seconds=300)
AREA_RULE = RateLimitRule(max_attempts=60, window_seconds=300)
PUBLIC_FETCH_RULE = RateLimitRule(max_attempts=30, window_seconds=300)


@router.get("/public-page-fetch/health")
async def public_page_fetch_health(_user: CurrentUser) -> dict[str, object]:
    return {
        "status": "ok",
        "method": "unauthenticated HTTP GET; schema.org JSON-LD first",
        "limits": {"max_response_bytes": 1_500_000, "max_redirects": 4},
        "access": "public HTML only; no login, cookie, CAPTCHA or access-control bypass",
    }


@router.post(
    "/public-page-fetch",
    response_model=PublicPageFetchResult,
    dependencies=[Csrf],
)
async def public_page_fetch(
    request: Request,
    payload: PublicPageFetchRequest,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> PublicPageFetchResult:
    allowed, retry_after = get_rate_limiter().check(
        "public_page_fetch", str(user.id), PUBLIC_FETCH_RULE
    )
    if not allowed:
        raise TooManyRequestsError(
            "Too many public-page fetches. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
        )
    try:
        result = await fetch_public_page(payload.url)
    except UnsafeUrlError as exc:
        raise ValidationFailedError(
            "Public-page URL was refused", details={"reason": str(exc)}
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceUnavailableError("public_page_fetch", type(exc).__name__) from exc
    await record_audit(
        session,
        action="discovery.public_page_fetch",
        owner_user_id=user.id,
        entity_type="public_page",
        ip_address=client_ip(request),
        metadata={"host": payload.url.split("/", 3)[2], "status": result.status},
    )
    return result


@router.post("/local-search", response_model=LocalScrapeResponse, dependencies=[Csrf])
async def local_search(
    request: Request,
    payload: LocalScrapeRequest,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> LocalScrapeResponse:
    allowed, retry_after = get_rate_limiter().check("local_search", str(user.id), LOCAL_SEARCH_RULE)
    if not allowed:
        raise TooManyRequestsError(
            "Too many local searches. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
        )
    result = await scrape_google_local(session, user.id, payload.niche, payload.city)
    await record_audit(
        session,
        action="discovery.local_search",
        owner_user_id=user.id,
        entity_type="search",
        ip_address=client_ip(request),
        metadata={
            "niche": payload.niche,
            "city": payload.city,
            "found": result.total_found,
            "stored_new": result.stored_new,
        },
    )
    return result


@router.post("/local-search/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_local_search_job(
    request: Request,
    payload: LocalScrapeRequest,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> JobOut:
    """Queue a long local evidence pass rather than tying it to one HTTP request."""
    allowed, retry_after = get_rate_limiter().check("local_search", str(user.id), LOCAL_SEARCH_RULE)
    if not allowed:
        raise TooManyRequestsError(
            "Too many local searches. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
        )
    job = await job_service.create_job(
        session,
        owner_user_id=user.id,
        config={
            "niche": payload.niche.strip(),
            "city": payload.city.strip(),
            "kind": "local_search",
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    job.job_type = "local_search"
    # The worker has its own transaction. Commit before scheduling it so it
    # cannot race an uncommitted job row.
    await session.commit()
    background.add_task(run_local_search_job, job_id=str(job.id))
    await record_audit(
        session,
        action="discovery.local_search",
        owner_user_id=user.id,
        entity_type="discovery_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={"niche": payload.niche, "city": payload.city},
    )
    return _job_out(job)


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
    await job_service.recover_stale_jobs(session, stale_after_seconds=3600)
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


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Csrf])
@router.post("/jobs/{job_id}/delete", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Csrf])
async def delete_job(
    request: Request,
    job_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> None:
    """Delete a discovery job and cascade its batches and logs."""
    await job_service.delete_job(session, job_id, user.id)
    await record_audit(
        session,
        action="discovery.job_deleted",
        owner_user_id=user.id,
        entity_type="discovery_job",
        entity_id=job_id,
        ip_address=client_ip(request),
    )


@router.post("/jobs/bulk-delete", response_model=BulkDeleteOut, dependencies=[Csrf])
@router.delete("/jobs/bulk-delete", response_model=BulkDeleteOut, dependencies=[Csrf])
@router.delete("/jobs", response_model=BulkDeleteOut, dependencies=[Csrf])
async def bulk_delete_jobs(
    request: Request,
    payload: BulkDeleteIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> BulkDeleteOut:
    """Delete selected or all discovery jobs for this user."""
    if payload.delete_all == bool(payload.ids):
        raise ValidationFailedError("Choose either selected job ids or delete_all")
    deleted = await job_service.bulk_delete_jobs(
        session,
        owner_user_id=user.id,
        job_ids=None if payload.delete_all else payload.ids,
    )
    await record_audit(
        session,
        action="discovery.jobs_bulk_deleted",
        owner_user_id=user.id,
        entity_type="discovery_job",
        ip_address=client_ip(request),
        metadata={"deleted": deleted, "delete_all": payload.delete_all},
    )
    return BulkDeleteOut(deleted=deleted)


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
    return SearchAreaListOut(items=[SearchAreaOut.model_validate(row) for row in rows], total=total)


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


# ── Evidence-First Resumable Scan Runs ──────────────────────────────────────


@router.post("/scans", response_model=ScanRunOut, status_code=status.HTTP_201_CREATED)
async def create_scan(
    request: Request,
    payload: ScanCreateIn,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> ScanRunOut:
    """Create a planned, multi-source Local Business Finder scan run."""
    allowed, retry_after = get_rate_limiter().check("local_scan", str(user.id), LOCAL_SEARCH_RULE)
    if not allowed:
        raise TooManyRequestsError(
            "Too many scans created. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
        )

    scan = await scan_service.create_scan_run(
        session,
        owner_user_id=user.id,
        niche=payload.niche,
        city=payload.city,
        country=payload.country,
    )
    background.add_task(scan_service.execute_scan_run, scan_run_id=str(scan.id))
    await record_audit(
        session,
        action="discovery.scan.create",
        owner_user_id=user.id,
        entity_type="local_scan_run",
        entity_id=scan.id,
        ip_address=client_ip(request),
        metadata={"niche": payload.niche, "city": payload.city, "country": payload.country},
    )
    # Reload with units
    stmt = (
        select(LocalScanRun)
        .where(LocalScanRun.id == scan.id)
        .options(selectinload(LocalScanRun.units))
    )
    loaded = await session.scalar(stmt)
    return ScanRunOut.model_validate(loaded)


@router.get("/scans", response_model=ScanRunListOut)
async def list_scans(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ScanRunListOut:
    """List recent scan runs for the authenticated operator."""
    count_stmt = select(func.count(LocalScanRun.id)).where(LocalScanRun.owner_user_id == user.id)
    total = (await session.scalar(count_stmt)) or 0

    stmt = (
        select(LocalScanRun)
        .where(LocalScanRun.owner_user_id == user.id)
        .options(selectinload(LocalScanRun.units))
        .order_by(LocalScanRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.scalars(stmt)).all())
    return ScanRunListOut(items=[ScanRunOut.model_validate(r) for r in rows], total=total)


@router.get("/scans/{scan_id}", response_model=ScanRunOut)
async def get_scan(
    scan_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> ScanRunOut:
    """Poll status, progress, real stage and source coverage for a scan run."""
    stmt = (
        select(LocalScanRun)
        .where(LocalScanRun.id == scan_id, LocalScanRun.owner_user_id == user.id)
        .options(selectinload(LocalScanRun.units))
    )
    scan = await session.scalar(stmt)
    if not scan:
        raise NotFoundError("Scan run not found")
    return ScanRunOut.model_validate(scan)


@router.post("/scans/{scan_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_scan(
    scan_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> dict[str, Any]:
    """Gracefully cancel a scan run; collected evidence is kept."""
    ok = await scan_service.cancel_scan_run(session, scan_id, user.id)
    if not ok:
        raise NotFoundError("Scan run not found or already cancelled")
    return {"status": "cancellation_requested", "scan_id": str(scan_id)}


@router.post("/scans/{scan_id}/resume", response_model=ScanRunOut)
async def resume_scan(
    scan_id: uuid.UUID,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> ScanRunOut:
    """Resume failed or incomplete units of a scan run without repeating completed work."""
    ok = await scan_service.resume_scan_run(session, scan_id, user.id)
    if not ok:
        raise NotFoundError("Scan run not found")
    background.add_task(scan_service.execute_scan_run, scan_run_id=str(scan_id))
    stmt = (
        select(LocalScanRun)
        .where(LocalScanRun.id == scan_id, LocalScanRun.owner_user_id == user.id)
        .options(selectinload(LocalScanRun.units))
    )
    scan = await session.scalar(stmt)
    return ScanRunOut.model_validate(scan)


@router.get("/scans/{scan_id}/export")
async def export_scan_csv(
    scan_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> Response:
    """Export all businesses and evidence URLs discovered in this scan run as a CSV."""
    stmt = select(LocalScanRun).where(
        LocalScanRun.id == scan_id, LocalScanRun.owner_user_id == user.id
    )
    scan = await session.scalar(stmt)
    if not scan:
        raise NotFoundError("Scan run not found")

    biz_stmt = (
        select(Business)
        .join(LocalScanBusiness, LocalScanBusiness.business_id == Business.id)
        .where(
            LocalScanBusiness.scan_run_id == scan_id,
            Business.owner_user_id == user.id,
            Business.deleted_at.is_(None),
        )
        .order_by(Business.name)
    )
    businesses = list((await session.scalars(biz_stmt)).all())
    csv_content = scan_service.generate_scan_csv(businesses)

    filename = f"scan-{scan.niche.replace(' ', '_')}-{scan.city.replace(' ', '_')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
