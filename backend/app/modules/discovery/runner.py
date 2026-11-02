from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.modules.discovery import job_service
from app.modules.discovery.adapters.base import DiscoveryAdapter
from app.modules.discovery.adapters.overpass import OverpassAdapter
from app.modules.discovery.adapters.searxng import SearxngAdapter
from app.modules.discovery.models import DiscoveryJob
from app.modules.discovery.pipeline import PipelineReport, StageCounters, run_pipeline
from app.modules.discovery.schemas import query_from_config
from app.modules.discovery.store_sql import SqlBusinessStore
from app.modules.sources.registry import ensure_source
from app.workers.dispatcher import SynchronousDispatcher, get_dispatcher
from app.workers.tasks import register_task

logger = get_logger(__name__)

RUN_TASK_NAME = "sparkxflow.discovery.run_job"
DEFAULT_SOURCE_SLUGS = ("searxng", "overpass")
AVAILABLE_SOURCE_SLUGS = ("searxng", "overpass")

# How often an in-flight job commits its progress and re-reads the cancel flag.
# Checked per unit of work would be one database round trip per record.
CHECKPOINT_EVERY = 25


def build_adapters(settings: Settings, slugs: Sequence[str]) -> list[tuple[str, DiscoveryAdapter]]:
    """Instantiate the sources a job asked for, from configuration only.

    A slug with no adapter is an error, not a silent skip: quietly running a
    "searxng + overpass" job against overpass alone would report provenance the
    run did not actually have.
    """
    built: list[tuple[str, DiscoveryAdapter]] = []
    for slug in slugs:
        if slug == "overpass":
            built.append(
                (
                    slug,
                    OverpassAdapter(
                        settings.overpass_base_url,
                        timeout_seconds=settings.overpass_timeout_seconds,
                    ),
                )
            )
        elif slug == "searxng":
            built.append(
                (
                    slug,
                    SearxngAdapter(
                        settings.searxng_base_url,
                        timeout_seconds=settings.searxng_timeout_seconds,
                        max_pages=settings.searxng_max_pages,
                        results_per_page=settings.searxng_results_per_page,
                    ),
                )
            )
        else:
            raise ValueError(f"No adapter is registered for source '{slug}'")
    return built


class JobTracker:
    """Turns pipeline stage callbacks into observed job progress.

    `processed_records` counts records that have reached the end of the pipeline
    — stored, or rejected before storage. Nothing is counted while it is still
    in flight, so a stalled run shows the stall instead of a hopeful number.
    """

    def __init__(self, session: AsyncSession, job: DiscoveryJob) -> None:
        self._session = session
        self._job = job
        self._stored = 0
        self._since_checkpoint = 0
        self._cancel_seen = False

    async def on_stage(self, stage: str, counters: StageCounters) -> None:
        if stage == "store":
            self._stored += 1

        processed = counters.rejected + self._stored
        total = counters.discovered
        self._job.total_records = total
        self._job.processed_records = processed
        self._job.failed_records = counters.rejected
        self._job.progress_percent = round(processed / total * 100, 2) if total else 0

        self._since_checkpoint += 1
        if self._since_checkpoint >= CHECKPOINT_EVERY:
            await self._checkpoint()

    async def is_cancelled(self) -> bool:
        return self._cancel_seen

    async def _checkpoint(self) -> None:
        self._since_checkpoint = 0
        await self._session.commit()
        await self._session.refresh(self._job)
        self._cancel_seen = self._job.status == "cancelled"


def report_payload(report: PipelineReport, store: SqlBusinessStore) -> dict[str, Any]:
    """The pipeline's own numbers, written out rather than summarised away."""
    return {
        "counters": asdict(report.counters),
        "sources": [asdict(outcome) for outcome in report.sources],
        "enrichment": asdict(report.enrichment) if report.enrichment else None,
        "review_pairs": len(report.review_pairs),
        "stored_new": store.created,
        "merged_existing": store.merged,
        "skipped_provenance": store.skipped_provenance,
        "cancelled": report.cancelled,
        "failure_summary": report.failure_summary(),
    }


async def finalize(
    session: AsyncSession, job: DiscoveryJob, report: PipelineReport, store: SqlBusinessStore
) -> None:
    job.report = report_payload(report, store)

    for outcome in report.sources:
        if outcome.failed:
            await job_service.add_log(
                session,
                job.id,
                "warning",
                f"Source {outcome.slug} failed: {outcome.failure_reason}",
                metadata={"classification": outcome.failure_classification},
            )

    if store.skipped_provenance:
        # Attribution that could not be recorded is reported, never hidden.
        await job_service.add_log(
            session,
            job.id,
            "warning",
            f"{store.skipped_provenance} provenance rows skipped: source not registered",
        )

    if report.cancelled:
        job.status = "cancelled"
        await job_service.add_log(
            session, job.id, "warning", "Cancelled mid-run; records stored so far are kept"
        )
    elif report.counters.discovered == 0 and report.any_source_failed:
        job.status = "failed"
        job.error_details = {"reason": report.failure_summary()}
        await job_service.add_log(session, job.id, "error", report.failure_summary())
    else:
        job.status = "completed"
        job.progress_percent = 100 if job.total_records else 0
        if report.any_source_failed:
            job.error_details = {"partial_failure": report.failure_summary()}
        await job_service.add_log(
            session,
            job.id,
            "info",
            f"Completed: {store.created} new, {store.merged} merged, "
            f"{report.counters.rejected} rejected",
        )

    job_service.mark_finished(job)
    await session.commit()


async def execute(job_id: uuid.UUID, *, settings: Settings | None = None) -> str:
    """Run one discovery job against the real sources and the real database."""
    active = settings or get_settings()
    async with session_scope() as session:
        job = await session.get(DiscoveryJob, job_id)
        if job is None:
            logger.warning("discovery_job_missing", job_id=str(job_id))
            return "missing"
        if job.status == "cancelled":
            return "cancelled"

        config = await job_service.query_config(session, job)
        request = query_from_config(config)
        slugs = tuple(request.sources or DEFAULT_SOURCE_SLUGS)
        adapters = build_adapters(active, slugs)

        for _, adapter in adapters:
            await ensure_source(session, adapter.capabilities)

        job_service.mark_running(job)
        await job_service.add_log(
            session, job.id, "info", f"Started with sources: {', '.join(slugs)}"
        )
        await session.commit()

        store = SqlBusinessStore(session, owner_user_id=job.owner_user_id, job_id=job.id)
        tracker = JobTracker(session, job)
        try:
            report = await run_pipeline(
                adapters,
                [request.to_query()],
                store=store,
                default_region=active.default_region,
                on_stage=tracker.on_stage,
                is_cancelled=tracker.is_cancelled,
            )
        finally:
            for _, adapter in adapters:
                aclose = getattr(adapter, "aclose", None)
                if aclose is not None:
                    await aclose()

        await finalize(session, job, report, store)
        return job.status


@register_task(RUN_TASK_NAME)
async def run_discovery_job(*, job_id: str) -> str:
    try:
        return await execute(uuid.UUID(str(job_id)))
    except Exception as exc:  # noqa: BLE001 - a crashed job must still be reported
        logger.error("discovery_job_crashed", job_id=job_id, error_type=type(exc).__name__)
        await mark_failed(job_id, exc)
        return "failed"


async def mark_failed(job_id: str, exc: Exception) -> None:
    try:
        parsed = uuid.UUID(str(job_id))
    except ValueError:
        return
    async with session_scope() as session:
        job = await session.get(DiscoveryJob, parsed)
        if job is None:
            return
        job.status = "failed"
        job.error_details = {"reason": f"{type(exc).__name__}: {exc}"[:500]}
        job_service.mark_finished(job)
        await job_service.add_log(session, job.id, "error", f"Job crashed: {type(exc).__name__}")
        await session.commit()


async def dispatch(
    session: AsyncSession, job: DiscoveryJob, background_tasks: BackgroundTasks
) -> str:
    """Hand the job to the configured runner and report how it was handed.

    Inline execution is scheduled as a background task, after the response, so
    the job row is committed and visible before anything tries to read it. It
    also means the caller is not told a job finished that is still running.
    """
    dispatcher = get_dispatcher()
    if isinstance(dispatcher, SynchronousDispatcher):
        # Commit first. The job runs after the response, in its own session, and
        # an uncommitted row is invisible to it — the runner would report a job
        # that never existed and the API would still say 201.
        await session.commit()
        background_tasks.add_task(run_discovery_job, job_id=str(job.id))
        return "inline"

    try:
        job.celery_task_id = dispatcher.submit(RUN_TASK_NAME, {"job_id": str(job.id)})
    except Exception as exc:  # noqa: BLE001 - no broker is a reportable state
        job.status = "blocked"
        job.error_details = {
            "reason": f"No worker could accept this job ({type(exc).__name__}). "
            "Set SPARKX_RUN_JOBS_SYNCHRONOUSLY=true to run jobs inline in development."
        }
        await job_service.add_log(session, job.id, "error", "Broker unavailable; job blocked")
        return "blocked"
    return "queued"
