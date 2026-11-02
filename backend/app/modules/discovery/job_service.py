from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import JobStateError, NotFoundError
from app.modules.discovery.models import DiscoveryJob, JobLog, Search

JOB_TYPE_DISCOVERY = "discovery"
MODULE_LEADS = "leads"
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "blocked"})


async def create_job(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    config: dict[str, Any],
    correlation_id: str | None,
) -> DiscoveryJob:
    """Queue a discovery job and remember the query that produced it.

    The query lives on a `searches` row so a job can always be re-read as "what
    was asked", separate from "what happened".
    """
    search = Search(
        owner_user_id=owner_user_id,
        module=MODULE_LEADS,
        query_config=config,
        execution_status="queued",
    )
    session.add(search)
    await session.flush()

    job = DiscoveryJob(
        search_id=search.id,
        owner_user_id=owner_user_id,
        job_type=JOB_TYPE_DISCOVERY,
        status="queued",
        correlation_id=correlation_id,
    )
    session.add(job)
    await session.flush()
    return job


async def get_job(
    session: AsyncSession, job_id: uuid.UUID, owner_user_id: uuid.UUID
) -> DiscoveryJob:
    """Fetch a job owned by the caller. Another user's job does not exist here."""
    job = await session.scalar(
        select(DiscoveryJob).where(
            DiscoveryJob.id == job_id, DiscoveryJob.owner_user_id == owner_user_id
        )
    )
    if job is None:
        raise NotFoundError("Discovery job not found", details={"job_id": str(job_id)})
    return job


async def list_jobs(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[DiscoveryJob], int]:
    total = await session.scalar(
        select(func.count()).select_from(DiscoveryJob).where(
            DiscoveryJob.owner_user_id == owner_user_id
        )
    )
    rows = (
        await session.scalars(
            select(DiscoveryJob)
            .where(DiscoveryJob.owner_user_id == owner_user_id)
            .order_by(DiscoveryJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), int(total or 0)


async def query_config(session: AsyncSession, job: DiscoveryJob) -> dict[str, Any]:
    """The stored request behind a job, for the runner to rebuild the query."""
    if job.search_id is None:
        return {}
    search = await session.get(Search, job.search_id)
    return dict(search.query_config) if search is not None else {}


async def add_log(
    session: AsyncSession,
    job_id: uuid.UUID,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(JobLog(job_id=job_id, level=level, message=message, metadata_=metadata or {}))


def mark_running(job: DiscoveryJob) -> None:
    job.status = "running"
    job.started_at = job.started_at or datetime.now(UTC)


def mark_finished(job: DiscoveryJob) -> None:
    job.completed_at = datetime.now(UTC)


async def cancel_job(
    session: AsyncSession, job_id: uuid.UUID, owner_user_id: uuid.UUID
) -> DiscoveryJob:
    """Mark a job cancelled; the runner notices between units of work.

    Refused once a job has finished — pretending to un-run a completed sweep
    would leave the record claiming something that is not true.
    """
    job = await get_job(session, job_id, owner_user_id)
    if job.status in TERMINAL_STATUSES:
        raise JobStateError(
            f"Job is already {job.status}",
            details={"job_id": str(job_id), "status": job.status},
        )
    job.status = "cancelled"
    mark_finished(job)
    await add_log(session, job.id, "warning", "Cancellation requested")
    await session.flush()
    return job
