"""Run one discovery job: against real sources, in bounded units, reporting what was seen.

A job is a queue of units of work. For a point-and-radius or keyword search that is a
single unit; for a drawn region it is the region's tiles. Each unit runs against each
selected source, so the state of *one provider asked about one piece of ground* is
visible on its own — which is the only way a partially completed region can be
described honestly, retried narrowly, or resumed without re-burdening a shared public
endpoint.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.modules.discovery import areas as area_service
from app.modules.discovery import job_service
from app.modules.discovery.adapters.base import (
    DiscoveryAdapter,
    DiscoveryQuery,
    LocationSpec,
)
from app.modules.discovery.adapters.overpass import OverpassAdapter
from app.modules.discovery.adapters.searxng import SearxngAdapter
from app.modules.discovery.models import DiscoveryJob
from app.modules.discovery.pipeline import PipelineReport, run_pipeline
from app.modules.discovery.schemas import query_from_config
from app.modules.discovery.store_sql import SqlBusinessStore
from app.modules.discovery.tiles import Tile, plan_tiles, split_tile
from app.modules.sources.registry import ensure_source
from app.shared.geo import Area, BoundingBox
from app.workers.dispatcher import SynchronousDispatcher, get_dispatcher
from app.workers.tasks import register_task

logger = get_logger(__name__)

RUN_TASK_NAME = "sparkxflow.discovery.run_job"
DEFAULT_SOURCE_SLUGS = ("searxng", "overpass")
AVAILABLE_SOURCE_SLUGS = ("searxng", "overpass")
# Sources are asked one at a time per unit. Overpass throttles by IP and rejects
# concurrent heavy queries, and a queue that fans out both providers on every tile
# multiplies the load on infrastructure nobody here is paying for.
COMMIT_EVERY_UNITS = 5


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


@dataclass
class Unit:
    """One queryable piece of ground. `tile_key` is None for an untiled request."""

    label: str
    query: DiscoveryQuery
    tile_key: str | None = None
    bounds: dict[str, float] | None = None
    depth: int = 0


@dataclass
class UnitOutcome:
    report: PipelineReport
    truncated: bool
    failed: bool
    discovered: int = 0
    stored_new: int = 0
    rejected: int = 0
    survivors: int = 0


@dataclass
class SourceSummary:
    """One source's record for the whole job, aggregated across tiles.

    A job that asked Overpass about 40 tiles has 40 outcomes; the operator needs
    the aggregate — how many tiles it answered, how many refused, and the reason it
    gave — because "completed" over a source that failed on a third of the region is
    not a truthful single word.
    """

    slug: str
    units: int = 0
    items_returned: int = 0
    requests_made: int = 0
    units_failed: int = 0
    units_truncated: int = 0
    last_classification: str | None = None
    last_reason: str | None = None

    @property
    def failed(self) -> bool:
        return self.units_failed > 0


@dataclass
class JobCounters:
    """Accumulated across units. Every number here was observed, never estimated."""

    discovered: int = 0
    processed: int = 0
    rejected: int = 0
    stored_new: int = 0
    review_pairs: int = 0
    units_total: int = 0
    units_done: int = 0
    units_failed: int = 0
    units_truncated: int = 0
    reports: list[dict[str, Any]] = field(default_factory=list)
    sources: dict[str, SourceSummary] = field(default_factory=dict)

    def observe(self, unit: Unit, outcome: UnitOutcome) -> None:
        self.discovered += outcome.discovered
        self.rejected += outcome.rejected
        self.stored_new += outcome.stored_new
        # A record has "reached the end" when it either went into the store or was
        # refused before it could. Nothing still in flight is counted.
        self.processed += outcome.rejected + outcome.survivors
        self.review_pairs += len(outcome.report.review_pairs)
        self.units_done += 1
        if outcome.failed:
            self.units_failed += 1
        if outcome.truncated:
            self.units_truncated += 1

        for source in outcome.report.sources:
            summary = self.sources.setdefault(source.slug, SourceSummary(slug=source.slug))
            summary.units += 1
            summary.items_returned += source.items_returned
            summary.requests_made += max(source.requests_made, 0)
            if source.failed:
                summary.units_failed += 1
                summary.last_classification = source.failure_classification
                summary.last_reason = source.failure_reason
            if source.capped:
                summary.units_truncated += 1

        self.reports.append(
            {
                "unit": unit.label,
                "tile_key": unit.tile_key,
                "discovered": outcome.discovered,
                "stored_new": outcome.stored_new,
                "rejected": outcome.rejected,
                "truncated": outcome.truncated,
                "failed": outcome.failed,
                "sources": [asdict(source) for source in outcome.report.sources],
            }
        )

    def failure_summary(self) -> str:
        failed = [
            f"{summary.slug}: {summary.units_failed} of {summary.units} unit(s) failed "
            f"— {summary.last_classification} — {summary.last_reason}"
            for summary in self.sources.values()
            if summary.failed
        ]
        return "; ".join(failed) if failed else "All sources completed"

    def any_source_failed(self) -> bool:
        return any(summary.failed for summary in self.sources.values())


def plan_units(area: Area | None, request: DiscoveryQuery, settings: Settings) -> list[Unit]:
    """Turn an area (or its absence) into the first batch of units to run.

    An area small enough for one request stays one request. Anything bigger is
    tiled deterministically, and a region that would need more tiles than the limit
    is refused here rather than trimmed later.
    """
    if area is None:
        return [Unit(label="query", query=request)]

    if area.area_km2 <= settings.discovery_tile_target_area_km2:
        return [Unit(label=area.shape_type, query=request)]

    tiles = plan_tiles(
        area,
        target_area_km2=settings.discovery_tile_target_area_km2,
        max_tiles=settings.discovery_max_tiles_per_job,
        plan_label=f"{area.shape_type} of {area.area_km2:,.1f} km²",
    )
    return [unit_for_tile(tile, request) for tile in tiles]


def unit_for_tile(tile: Tile, request: DiscoveryQuery) -> Unit:
    west, south, east, north = tile.bbox.as_tuple()
    query = dataclasses.replace(
        request,
        location=LocationSpec(query_bbox=(west, south, east, north)),
    )
    return Unit(
        label=f"tile {tile.index}",
        query=query,
        tile_key=tile.key,
        bounds=tile.bounds_payload(),
        depth=0,
    )


def next_units(
    unit: Unit,
    outcome: UnitOutcome,
    *,
    request: DiscoveryQuery,
    settings: Settings,
    planned: int,
) -> list[Unit]:
    """Subdivide a tile only when the provider said 'there is more'.

    Truncation is the one signal that a count is wrong rather than small: the source
    returned exactly as many records as were asked for, so the true number is
    unknown. Depth and total-unit limits stop that from becoming an unbounded fan-out.
    """
    if not outcome.truncated or unit.depth >= settings.discovery_max_tile_depth:
        return []
    if not unit.bounds or not unit.tile_key:
        return []

    children: list[Unit] = []
    for child in split_tile(_tile_from_payload(unit.tile_key, unit.bounds)):
        if planned + len(children) >= settings.discovery_max_tiles_per_job:
            break
        child_unit = unit_for_tile(child, request)
        child_unit.depth = unit.depth + 1
        children.append(child_unit)
    return children


def _tile_from_payload(key: str, bounds: dict[str, float]) -> Tile:
    return Tile(key=key, index=0, row=0, column=0, bbox=_bbox_from_payload(bounds))


def _bbox_from_payload(bounds: dict[str, float]) -> BoundingBox:
    return BoundingBox(
        west=float(bounds["west"]),
        south=float(bounds["south"]),
        east=float(bounds["east"]),
        north=float(bounds["north"]),
    )


class JobTracker:
    """Writes observed progress to the job row between units."""

    def __init__(self, session: AsyncSession, job: DiscoveryJob, counters: JobCounters) -> None:
        self._session = session
        self._job = job
        self._counters = counters
        self._cancel_seen = False

    async def publish(self) -> None:
        job = self._job
        job.total_records = self._counters.discovered
        job.processed_records = self._counters.processed
        job.failed_records = self._counters.rejected
        job.progress_percent = (
            round(self._counters.processed / self._counters.discovered * 100, 2)
            if self._counters.discovered
            else 0
        )
        await self._session.commit()
        await self._session.refresh(job)
        self._cancel_seen = job.status == "cancelled"

    async def is_cancelled(self) -> bool:
        return self._cancel_seen


def _unit_outcome(report: PipelineReport, unit: Unit) -> UnitOutcome:
    del unit
    sources = report.sources
    counters = report.counters
    return UnitOutcome(
        report=report,
        truncated=any(source.capped for source in sources),
        failed=bool(sources) and all(source.failed for source in sources),
        discovered=counters.discovered,
        stored_new=counters.stored_new,
        rejected=counters.rejected,
        # What actually reached the store: accepted records minus those folded into
        # another record by deduplication inside this unit.
        survivors=counters.normalized - counters.duplicates_merged,
    )


def report_payload(
    report: PipelineReport, store: SqlBusinessStore, counters: JobCounters, area: Area | None
) -> dict[str, Any]:
    """The pipeline's own numbers, written out rather than summarised away."""
    return {
        "counters": asdict(report.counters),
        "totals": {
            "discovered": counters.discovered,
            "processed": counters.processed,
            "rejected": counters.rejected,
            "stored_new": counters.stored_new,
            "review_pairs": counters.review_pairs,
            "units_total": counters.units_total,
            "units_done": counters.units_done,
            "units_failed": counters.units_failed,
            "units_truncated": counters.units_truncated,
        },
        "area": area_service.describe_area(area) if area else None,
        "sources": [
            {**asdict(summary), "failed": summary.failed} for summary in counters.sources.values()
        ],
        "enrichment": asdict(report.enrichment) if report.enrichment else None,
        "stored_new_rows": store.created,
        "merged_existing": store.merged,
        "known_records_reseen": store.reused_by_source_id,
        "skipped_provenance": store.skipped_provenance,
        "unit_reports": counters.reports,
        "cancelled": report.cancelled,
        "failure_summary": counters.failure_summary(),
    }


async def finalize(
    session: AsyncSession,
    job: DiscoveryJob,
    report: PipelineReport,
    store: SqlBusinessStore,
    counters: JobCounters,
    area: Area | None,
) -> None:
    job.report = report_payload(report, store, counters, area)

    if store.skipped_provenance:
        # Attribution that could not be recorded is reported, never hidden.
        await job_service.add_log(
            session,
            job.id,
            "warning",
            f"{store.skipped_provenance} provenance rows skipped: source not registered",
        )

    for summary in counters.sources.values():
        if summary.failed:
            await job_service.add_log(
                session,
                job.id,
                "warning",
                f"Source {summary.slug} failed on {summary.units_failed} of {summary.units} "
                f"unit(s): {summary.last_reason}",
                metadata={
                    "classification": summary.last_classification,
                    "units_failed": summary.units_failed,
                    "units": summary.units,
                },
            )

    if report.cancelled:
        job.status = "cancelled"
        await job_service.add_log(
            session, job.id, "warning", "Cancelled mid-run; records stored so far are kept"
        )
    elif (
        counters.discovered == 0
        and counters.units_failed
        and counters.units_failed == counters.units_done
    ):
        job.status = "failed"
        job.error_details = {"reason": counters.failure_summary()}
        await job_service.add_log(session, job.id, "error", counters.failure_summary())
    else:
        job.status = "completed"
        job.progress_percent = 100 if job.total_records else 0
        if counters.any_source_failed():
            job.error_details = {
                "partial_failure": counters.failure_summary(),
                "units_failed": counters.units_failed,
            }
        if counters.units_truncated:
            job.error_details = {
                **(job.error_details or {}),
                "truncated_units": counters.units_truncated,
                "note": (
                    "Some units returned the provider's full element allowance, so "
                    "those parts of the area are not completely covered."
                ),
            }
        await job_service.add_log(
            session,
            job.id,
            "info",
            f"Completed {counters.units_done} of {counters.units_total} units: "
            f"{store.created} new, {store.merged} merged, {counters.rejected} rejected",
        )

    job_service.mark_finished(job)
    await session.commit()


async def execute(job_id: uuid.UUID, *, settings: Settings | None = None) -> str:
    """Run one discovery job against the real sources and the real database."""
    active = settings or get_settings()
    async with session_scope() as session:
        # Claiming is the idempotency guard: a duplicate delivery of a job that is
        # already running or finished fails to claim and returns without re-running.
        job = await job_service.claim_job(session, job_id)
        if job is None:
            existing = await session.get(DiscoveryJob, job_id)
            if existing is None:
                logger.warning("discovery_job_missing", job_id=str(job_id))
                return "missing"
            logger.info(
                "discovery_job_not_claimable", job_id=str(job_id), status=existing.status
            )
            return "already_running" if existing.status == "running" else existing.status

        config = await job_service.query_config(session, job)
        request_model, area = query_from_config(config)
        slugs = tuple(request_model.sources or DEFAULT_SOURCE_SLUGS)
        adapters = build_adapters(active, slugs)
        source_ids: dict[str, uuid.UUID] = {}
        for slug, adapter in adapters:
            source_ids[slug] = await ensure_source(session, adapter.capabilities)

        base_query = request_model.to_query(area)
        queue = plan_units(area, base_query, active)
        counters = JobCounters(units_total=len(queue))

        await job_service.add_log(
            session,
            job.id,
            "info",
            f"Started: {len(queue)} unit(s) across {len(slugs)} source(s) — "
            f"{area_service.describe_area(area) if area else 'no geometry'}",
        )

        store = SqlBusinessStore(session, owner_user_id=job.owner_user_id, job_id=job.id)
        tracker = JobTracker(session, job, counters)
        last_report = PipelineReport()
        planned = len(queue)
        batch_number = 0
        try:
            while queue:
                if await tracker.is_cancelled():
                    last_report.cancelled = True
                    break
                unit = queue.pop(0)
                batch_number += 1

                for slug, adapter in adapters:
                    batch = await job_service.open_batch(
                        session,
                        job_id=job.id,
                        batch_number=batch_number,
                        unit_kind="tile" if unit.tile_key else "single_query",
                        tile_key=unit.tile_key,
                        source_id=source_ids[slug],
                        bounds=unit.bounds,
                    )
                    last_report = await run_pipeline(
                        [(slug, adapter)],
                        [unit.query],
                        store=store,
                        default_region=active.default_region,
                        is_cancelled=tracker.is_cancelled,
                    )
                    outcome = _unit_outcome(last_report, unit)
                    job_service.finish_batch(
                        batch,
                        status="failed" if outcome.failed else "completed",
                        records_expected=outcome.discovered,
                        records_processed=outcome.discovered,
                        truncated=outcome.truncated,
                        error=(
                            {"reason": last_report.failure_summary()}
                            if outcome.failed
                            else None
                        ),
                    )
                    counters.observe(unit, outcome)
                    children = next_units(
                        unit,
                        outcome,
                        request=base_query,
                        settings=active,
                        planned=planned,
                    )
                    if children:
                        queue = children + queue
                        counters.units_total += len(children)
                        planned += len(children)
                        await job_service.add_log(
                            session,
                            job.id,
                            "warning",
                            f"{unit.label} returned the element cap for {slug}; "
                            f"subdivided into {len(children)} smaller units",
                        )
                    if batch_number % COMMIT_EVERY_UNITS == 0:
                        await tracker.publish()

                await tracker.publish()
        finally:
            for _, adapter in adapters:
                aclose = getattr(adapter, "aclose", None)
                if aclose is not None:
                    await aclose()

        if request_model.area_id is not None:
            await area_service.mark_run(session, request_model.area_id)
        await finalize(session, job, last_report, store, counters, area)
        await session.commit()
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
