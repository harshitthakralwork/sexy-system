from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import JobStateError, NotFoundError
from app.modules.discovery.models import DiscoveryJob, JobBatch, JobLog, Search

JOB_TYPE_DISCOVERY = "discovery"
MODULE_LEADS = "leads"
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "blocked"})
# Statuses a worker may transition into `running`. `failed` and `blocked` are here
# so a retry is just a re-dispatch; `paused` is reserved for a future pause control.
RUNNABLE_STATUSES = frozenset({"queued", "blocked", "failed", "paused"})
# A job in these states may be reset and re-run. `completed` is deliberately
# absent: re-running a sweep that already ran would re-query shared infrastructure
# for nothing, so the operator is told to start a new search instead.
RETRYABLE_STATUSES = frozenset({"failed", "blocked", "cancelled"})


async def create_job(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    config: dict[str, Any],
    correlation_id: str | None,
    area_id: uuid.UUID | None = None,
) -> DiscoveryJob:
    """Queue a discovery job and remember the query that produced it.

    The query lives on a `searches` row so a job can always be re-read as "what
    was asked", separate from "what happened". A saved area is referenced by id,
    not copied, while the resolved geometry is copied into the config — so the job
    stays reproducible even if the area is later edited or deleted.
    """
    search = Search(
        owner_user_id=owner_user_id,
        area_id=area_id,
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


async def claim_job(session: AsyncSession, job_id: uuid.UUID) -> DiscoveryJob | None:
    """Atomically move a runnable job into `running`, or return None.

    The guard is the UPDATE itself. Two workers that both see a `queued` job race
    to run it; only one UPDATE matches a row still in a runnable status, so the
    loser gets None and must not execute the work again. Returning None for
    `completed`/`cancelled`/`running` is what makes a duplicate Celery delivery —
    or a re-submitted retry — a no-op instead of a double sweep.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        update(DiscoveryJob)
        .where(DiscoveryJob.id == job_id, DiscoveryJob.status.in_(RUNNABLE_STATUSES))
        .values(status="running", started_at=func.coalesce(DiscoveryJob.started_at, now))
        .returning(DiscoveryJob.id)
    )
    await session.commit()
    if result.scalar_one_or_none() is None:
        return None
    return await session.get(DiscoveryJob, job_id)


async def reset_for_retry(
    session: AsyncSession, job_id: uuid.UUID, owner_user_id: uuid.UUID
) -> DiscoveryJob:
    """Put a terminal job back in the queue, preserving its history.

    Counters and timestamps reset so the retry reports only its own run; the
    previous report is overwritten by the new one, and past runs remain visible
    in the job log and audit trail. Records already stored are kept — a retry
    re-asks the sources and merges, it does not un-run the first attempt.
    """
    job = await get_job(session, job_id, owner_user_id)
    if job.status == "completed":
        raise JobStateError(
            "A completed job has nothing to retry; start a new search instead",
            details={"job_id": str(job_id), "status": job.status},
        )
    if job.status not in RETRYABLE_STATUSES:
        raise JobStateError(
            f"A {job.status} job cannot be retried",
            details={"job_id": str(job_id), "status": job.status},
        )
    job.status = "queued"
    job.retry_count += 1
    job.error_details = None
    job.started_at = None
    job.completed_at = None
    job.celery_task_id = None
    job.progress_percent = 0
    job.total_records = 0
    job.processed_records = 0
    job.failed_records = 0
    await add_log(session, job.id, "info", f"Retry #{job.retry_count} requested")
    await session.flush()
    return job


async def recover_stale_jobs(session: AsyncSession, *, stale_after_seconds: int) -> int:
    """Mark jobs a dead worker left in `running` as failed, so they can be retried.

    Only jobs with a `started_at` older than the window are touched: a sweep that
    is merely long-running keeps its `running` status. The threshold is measured
    from job start, not last progress, so the window must exceed the longest
    legitimate job — the default is hours, not minutes.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    rows = (
        await session.scalars(
            select(DiscoveryJob).where(
                DiscoveryJob.status == "running",
                DiscoveryJob.started_at.is_not(None),
                DiscoveryJob.started_at < cutoff,
            )
        )
    ).all()
    for job in rows:
        job.status = "failed"
        job.error_details = {
            "reason": "Worker lost: no completion observed within the stale window",
            "stale": True,
        }
        mark_finished(job)
        await add_log(session, job.id, "error", "Marked failed: worker lost (stale running job)")
    await session.flush()
    return len(rows)


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


async def open_batch(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    batch_number: int,
    unit_kind: str,
    tile_key: str | None = None,
    source_id: uuid.UUID | None = None,
    bounds: dict[str, Any] | None = None,
) -> JobBatch:
    """Record a unit of work as started, or return the row that already exists.

    Re-opening a completed tile is what a retry is: the same deterministic key,
    the same bounds, the counters reset and the history kept. Inserting a second
    row for the same tile would let one region be counted twice.
    """
    existing = await find_batch(
        session, job_id=job_id, tile_key=tile_key, source_id=source_id
    )
    if existing is not None:
        existing.status = "running"
        existing.started_at = datetime.now(UTC)
        existing.completed_at = None
        existing.retry_count += 1
        existing.records_processed = 0
        await session.flush()
        return existing

    batch = JobBatch(
        job_id=job_id,
        batch_number=batch_number,
        unit_kind=unit_kind,
        tile_key=tile_key,
        source_id=source_id,
        bounds=bounds,
        status="running",
        started_at=datetime.now(UTC),
    )
    session.add(batch)
    await session.flush()
    return batch


async def find_batch(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    tile_key: str | None,
    source_id: uuid.UUID | None,
) -> JobBatch | None:
    if tile_key is None:
        return None
    return await session.scalar(
        select(JobBatch).where(
            JobBatch.job_id == job_id,
            JobBatch.tile_key == tile_key,
            JobBatch.source_id == source_id,
        )
    )


def finish_batch(
    batch: JobBatch,
    *,
    status: str,
    records_expected: int,
    records_processed: int,
    truncated: bool = False,
    error: dict[str, Any] | None = None,
) -> None:
    batch.status = status
    batch.records_expected = records_expected
    batch.records_processed = records_processed
    batch.truncated = truncated
    batch.error_details = error
    batch.completed_at = datetime.now(UTC)


async def list_batches(
    session: AsyncSession, job_id: uuid.UUID, owner_user_id: uuid.UUID
) -> list[JobBatch]:
    """Tile-level state for a job the caller owns."""
    job = await get_job(session, job_id, owner_user_id)
    rows = (
        await session.scalars(
            select(JobBatch).where(JobBatch.job_id == job.id).order_by(JobBatch.batch_number)
        )
    ).all()
    return list(rows)


async def delete_job(
    session: AsyncSession, job_id: uuid.UUID, owner_user_id: uuid.UUID
) -> bool:
    """Delete a single job owned by the user. Child batches and logs cascade."""
    job = await get_job(session, job_id, owner_user_id)
    await session.delete(job)
    await session.flush()
    return True


async def bulk_delete_jobs(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    job_ids: list[uuid.UUID] | None = None,
) -> int:
    """Delete all or selected jobs owned by the user."""
    query = delete(DiscoveryJob).where(DiscoveryJob.owner_user_id == owner_user_id)
    if job_ids is not None:
        if not job_ids:
            return 0
        query = query.where(DiscoveryJob.id.in_(job_ids))
    result = await session.execute(query)
    await session.flush()
    return int(result.rowcount)

