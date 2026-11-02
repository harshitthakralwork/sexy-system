from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy import select

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import TooManyRequestsError, ValidationFailedError
from app.core.ratelimit import RateLimitRule, get_rate_limiter
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.discovery import job_service, runner
from app.modules.discovery.models import JobLog
from app.modules.discovery.schemas import DiscoveryJobIn, JobListOut, JobOut

router = APIRouter(prefix="/discovery", tags=["discovery"])

Csrf = Depends(require_csrf_for_state_changes())

# Starting a sweep reaches out to external sources, so it is throttled like any
# other expensive action: generous enough for real work, tight enough that a
# runaway script cannot queue hundreds of concurrent crawls.
JOB_RULE = RateLimitRule(max_attempts=10, window_seconds=300)


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: Request,
    payload: DiscoveryJobIn,
    background: BackgroundTasks,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> JobOut:
    """Queue a discovery job, then let the configured runner work on it."""
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

    job = await job_service.create_job(
        session,
        owner_user_id=user.id,
        config=payload.to_config(),
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    dispatch_mode = await runner.dispatch(session, job, background)
    await record_audit(
        session,
        action="discovery.job_created",
        owner_user_id=user.id,
        entity_type="discovery_job",
        entity_id=job.id,
        ip_address=client_ip(request),
        metadata={"dispatch": dispatch_mode, "sources": payload.sources},
    )
    return JobOut.model_validate(job)


@router.get("/jobs", response_model=JobListOut)
async def list_jobs(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobListOut:
    jobs, total = await job_service.list_jobs(session, user.id, limit=limit, offset=offset)
    return JobListOut(items=[JobOut.model_validate(job) for job in jobs], total=total)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser) -> JobOut:
    job = await job_service.get_job(session, job_id, user.id)
    return JobOut.model_validate(job)


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
    return JobOut.model_validate(job)
