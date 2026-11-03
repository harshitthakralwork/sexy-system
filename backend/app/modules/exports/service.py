"""Background export jobs: a file on disk and a row that says what it holds.

An export is asked for in one request and produced in another. The row records
what was asked for and what actually came out; the file itself lives in storage
and expires. Nothing here reports a count it did not observe.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.integrations.storage import StorageError, get_storage
from app.modules.exports.csv_export import BUSINESS_COLUMNS
from app.modules.exports.formats import EXPORT_FORMATS, FORMAT_EXTENSIONS, render_export
from app.modules.exports.models import ExportJob, ImportJob
from app.shared.base import utcnow
from app.workers.dispatcher import SynchronousDispatcher, get_dispatcher
from app.workers.tasks import register_task

logger = get_logger(__name__)

EXPORT_TASK_NAME = "sparkxflow.exports.run_export"

# A ceiling on one export. An export is a convenience, not a bulk extract: the
# honest answer past this point is to narrow the filter.
MAX_EXPORT_ROWS = 10_000


@dataclass(frozen=True)
class ExportModule:
    """One thing that can be exported, and the filters it understands."""

    key: str
    label: str
    filter_keys: tuple[str, ...]
    numeric_filters: tuple[str, ...] = ()
    boolean_filters: tuple[str, ...] = ()


EXPORT_MODULES: dict[str, ExportModule] = {
    "leads": ExportModule(
        key="leads",
        label="Leads",
        filter_keys=(
            "query",
            "city",
            "country",
            "category",
            "website_status",
            "has_phone",
            "shortlisted_only",
        ),
        boolean_filters=("has_phone", "shortlisted_only"),
    ),
    "social_content": ExportModule(
        key="social_content",
        label="Collected content",
        filter_keys=("platform", "query", "content_type"),
    ),
    "social_intelligence": ExportModule(
        key="social_intelligence",
        label="Classified demand results",
        filter_keys=(
            "track_type",
            "platform",
            "classification",
            "query",
            "needs_review",
            "saved_only",
            "min_confidence",
        ),
        numeric_filters=("min_confidence",),
        boolean_filters=("needs_review", "saved_only"),
    ),
    "startups": ExportModule(
        key="startups",
        label="Startups",
        filter_keys=("query", "industry", "country", "funding_stage", "status"),
    ),
}

STARTUP_COLUMNS: tuple[str, ...] = (
    "name",
    "website_url",
    "industry",
    "country",
    "city",
    "founding_date",
    "funding_stage",
    "status",
    "description",
    "source_slug",
    "source_url",
    "first_discovered_at",
    "last_researched_at",
)


def columns_for(module: str) -> tuple[str, ...]:
    """The columns a module exports.

    The social column sets live with the module that owns the data, so the
    ad-hoc CSV endpoints and this exporter cannot drift apart.
    """
    if module == "leads":
        return BUSINESS_COLUMNS
    if module == "social_content":
        from app.modules.social.router import SOCIAL_CONTENT_COLUMNS

        return SOCIAL_CONTENT_COLUMNS
    if module == "social_intelligence":
        from app.modules.social.router import INTELLIGENCE_COLUMNS

        return INTELLIGENCE_COLUMNS
    if module == "startups":
        return STARTUP_COLUMNS
    raise ValidationFailedError(
        f"Unknown export module '{module}'", details={"available": sorted(EXPORT_MODULES)}
    )


def resolve_columns(module: str, requested: Sequence[str] | None) -> tuple[str, ...]:
    """Resolve the requested field list, refusing columns the module cannot supply.

    Silently dropping an unknown column would hand the user a file missing the
    field they asked for and no indication of it.
    """
    available = columns_for(module)
    if not requested:
        return available
    unknown = [name for name in requested if name not in available]
    if unknown:
        raise ValidationFailedError(
            f"Unknown export columns: {', '.join(unknown)}",
            details={"available": list(available)},
        )
    return tuple(requested)


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sanitize_filters(module: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the filters this module understands, with their declared types.

    The filter set is a boundary: an unknown key must not reach a query builder,
    and a value that cannot be read as the type the module expects must not be
    passed on as a string.
    """
    spec = EXPORT_MODULES[module]
    clean: dict[str, Any] = {}
    for key in spec.filter_keys:
        if not raw or key not in raw:
            continue
        value = raw[key]
        if value is None:
            continue
        if key in spec.boolean_filters:
            parsed = _as_bool(value)
            if parsed is not None:
                clean[key] = parsed
            continue
        if key in spec.numeric_filters:
            parsed_float = _as_float(value)
            if parsed_float is not None:
                clean[key] = parsed_float
            continue
        text = str(value).strip()
        if text:
            clean[key] = text
    return clean


async def _leads_rows(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: dict[str, Any]
) -> list[dict[str, Any]]:
    from app.modules.businesses.repository import BusinessFilters, export_rows

    business_filters = BusinessFilters(
        query=filters.get("query"),
        city=filters.get("city"),
        country=filters.get("country"),
        category=filters.get("category"),
        website_status=filters.get("website_status"),
        has_phone=filters.get("has_phone"),
        shortlisted_only=bool(filters.get("shortlisted_only")),
    )
    return await export_rows(session, owner_user_id, business_filters)


async def _social_content_rows(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: dict[str, Any]
) -> list[dict[str, Any]]:
    from app.modules.social import service

    rows, _ = await service.list_content(
        session,
        owner_user_id=owner_user_id,
        platform_slug=filters.get("platform"),
        query=filters.get("query"),
        content_type=filters.get("content_type"),
        limit=MAX_EXPORT_ROWS,
        offset=0,
    )
    return [
        service.content_export_row(content, slug, username, profile_url)
        for content, slug, username, profile_url in rows
    ]


async def _social_intelligence_rows(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: dict[str, Any]
) -> list[dict[str, Any]]:
    from app.modules.social import service, tracks

    rows, _ = await tracks.list_intelligence(
        session,
        owner_user_id,
        track_type=filters.get("track_type"),
        platform_slug=filters.get("platform"),
        classification=filters.get("classification"),
        min_confidence=_as_float(filters.get("min_confidence")),
        needs_review=_as_bool(filters.get("needs_review")),
        saved_only=_as_bool(filters.get("saved_only")),
        query=filters.get("query"),
        limit=MAX_EXPORT_ROWS,
        offset=0,
    )
    return [
        service.intelligence_export_row(content, slug, username)
        for content, slug, username in rows
    ]


async def _startup_rows(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: dict[str, Any]
) -> list[dict[str, Any]]:
    from app.modules.startups import service as startup_service

    rows, _ = await startup_service.list_startups(
        session,
        owner_user_id=owner_user_id,
        query=filters.get("query"),
        industry=filters.get("industry"),
        country=filters.get("country"),
        funding_stage=filters.get("funding_stage"),
        status=filters.get("status"),
        watchlist_id=None,
        limit=MAX_EXPORT_ROWS,
        offset=0,
    )
    return [
        {
            "name": startup.name,
            "website_url": startup.website_url,
            "industry": startup.industry,
            "country": startup.country,
            "city": startup.city,
            "founding_date": startup.founding_date.isoformat()
            if startup.founding_date
            else "",
            "funding_stage": startup.funding_stage,
            "status": startup.status,
            "description": startup.description,
            "source_slug": startup.source_slug,
            "source_url": startup.source_url,
            "first_discovered_at": startup.first_discovered_at.isoformat()
            if startup.first_discovered_at
            else "",
            "last_researched_at": startup.last_researched_at.isoformat()
            if startup.last_researched_at
            else "",
        }
        for startup in rows
    ]


_BUILDERS = {
    "leads": _leads_rows,
    "social_content": _social_content_rows,
    "social_intelligence": _social_intelligence_rows,
    "startups": _startup_rows,
}


async def build_rows(
    session: AsyncSession, owner_user_id: uuid.UUID, module: str, filters: dict[str, Any]
) -> list[dict[str, Any]]:
    """The rows an export will contain."""
    builder = _BUILDERS.get(module)
    if builder is None:
        raise ValidationFailedError(
            f"Unknown export module '{module}'", details={"available": sorted(EXPORT_MODULES)}
        )
    return await builder(session, owner_user_id, filters)


async def create_export_job(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    module: str,
    export_format: str,
    filters: dict[str, Any] | None = None,
    selected_fields: Sequence[str] | None = None,
) -> ExportJob:
    """Record what was asked for. The file is produced by the background run."""
    if module not in EXPORT_MODULES:
        raise ValidationFailedError(
            f"Unknown export module '{module}'", details={"available": sorted(EXPORT_MODULES)}
        )
    if export_format not in EXPORT_FORMATS:
        raise ValidationFailedError(
            f"Unsupported export format '{export_format}'",
            details={"available": list(EXPORT_FORMATS)},
        )
    columns = resolve_columns(module, selected_fields)
    job = ExportJob(
        owner_user_id=owner_user_id,
        module=module,
        export_format=export_format,
        filters=sanitize_filters(module, filters),
        selected_fields=list(columns),
        status="queued",
    )
    session.add(job)
    await session.flush()
    await session.refresh(job)
    return job


def storage_key_for(job: ExportJob) -> str:
    """Where the file lives.

    Scoped by owner so one account's key can never address another's file, even
    if a key were guessed.
    """
    extension = FORMAT_EXTENSIONS.get(job.export_format, "csv")
    return f"exports/{job.owner_user_id}/{job.id}.{extension}"


async def execute_export(job_id: uuid.UUID, *, settings: Settings | None = None) -> str:
    """Produce the file and record what it holds."""
    active = settings or get_settings()
    async with session_scope() as session:
        job = await session.get(ExportJob, job_id)
        if job is None:
            logger.warning("export_job_missing", job_id=str(job_id))
            return "missing"
        if job.status != "queued":
            # A duplicate delivery must not produce a second file.
            return job.status
        job.status = "running"
        await session.commit()

    try:
        async with session_scope() as session:
            job = await session.get(ExportJob, job_id)
            if job is None:
                return "missing"
            rows = await build_rows(
                session, job.owner_user_id, job.module, dict(job.filters or {})
            )
            columns = resolve_columns(job.module, list(job.selected_fields or []))
            export_format = job.export_format
            key = storage_key_for(job)

        data = render_export(rows, columns, export_format)
        get_storage(active).save(key, data)

        async with session_scope() as session:
            job = await session.get(ExportJob, job_id)
            if job is not None:
                job.status = "completed"
                job.storage_key = key
                job.total_records = len(rows)
                job.completed_at = utcnow()
                job.expires_at = utcnow() + timedelta(hours=active.export_retention_hours)
                await session.commit()
        logger.info("export_job_completed", job_id=str(job_id), records=len(rows))
        return "completed"
    except Exception as exc:  # noqa: BLE001 - a crashed export must be reported
        async with session_scope() as session:
            job = await session.get(ExportJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error_details = {"reason": f"{type(exc).__name__}: {exc}"[:500]}
                job.completed_at = utcnow()
                await session.commit()
        logger.error("export_job_failed", job_id=str(job_id), error_type=type(exc).__name__)
        return "failed"


@register_task(EXPORT_TASK_NAME)
async def run_export_task(*, job_id: str) -> str:
    """Inline/synchronous entry point under the same name the worker uses."""
    try:
        return await execute_export(uuid.UUID(str(job_id)))
    except ValueError:
        logger.warning("export_job_id_invalid", job_id=job_id)
        return "missing"


async def dispatch_export(
    session: AsyncSession, job: ExportJob, background_tasks: BackgroundTasks
) -> str:
    """Hand the export to the configured runner and report how it was handed.

    Inline execution is scheduled as a background task, after the response, so
    the job row is committed and visible before anything tries to read it.
    """
    dispatcher = get_dispatcher()
    if isinstance(dispatcher, SynchronousDispatcher):
        await session.commit()
        background_tasks.add_task(run_export_task, job_id=str(job.id))
        return "inline"

    try:
        dispatcher.submit(EXPORT_TASK_NAME, {"job_id": str(job.id)})
    except Exception as exc:  # noqa: BLE001 - no broker is a reportable state
        job.status = "blocked"
        job.error_details = {
            "reason": f"No worker could accept this export ({type(exc).__name__}). "
            "Set SPARKX_RUN_JOBS_SYNCHRONOUSLY=true to run jobs inline in development."
        }
        await session.commit()
        return "blocked"
    return "queued"


async def list_export_jobs(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int = 50
) -> list[ExportJob]:
    rows = await session.scalars(
        select(ExportJob)
        .where(ExportJob.owner_user_id == owner_user_id)
        .order_by(ExportJob.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def get_export_job(
    session: AsyncSession, owner_user_id: uuid.UUID, job_id: uuid.UUID
) -> ExportJob:
    """Return None for a row that exists but belongs to someone else.

    The router turns both cases into 404. Distinguishing them would confirm to
    a caller that an id is real.
    """
    job = await session.scalar(
        select(ExportJob).where(
            ExportJob.id == job_id, ExportJob.owner_user_id == owner_user_id
        )
    )
    if job is None:
        raise NotFoundError("Export job not found")
    return job


def read_export_file(job: ExportJob, *, settings: Settings | None = None) -> bytes:
    """The bytes of a finished export."""
    active = settings or get_settings()
    if not job.storage_key:
        raise NotFoundError("This export has no file")
    storage = get_storage(active)
    if not storage.exists(job.storage_key):
        raise NotFoundError("This export's file has expired")
    return storage.read(job.storage_key)


async def purge_expired_files(*, settings: Settings | None = None) -> int:
    """Delete files past their retention window and clear the rows that named them.

    Idempotent: a file that is already gone is not an error, and a row whose
    file has expired keeps its history and loses its pointer.
    """
    active = settings or get_settings()
    storage = get_storage(active)
    now = utcnow()
    removed = 0

    async with session_scope() as session:
        expired = await session.scalars(
            select(ExportJob).where(
                ExportJob.expires_at.is_not(None), ExportJob.expires_at < now
            )
        )
        for job in expired:
            if job.storage_key:
                try:
                    storage.delete(job.storage_key)
                except StorageError as exc:
                    logger.warning(
                        "export_file_purge_failed",
                        job_id=str(job.id),
                        error_type=type(exc).__name__,
                    )
                else:
                    removed += 1
            job.storage_key = None
        await session.commit()

    # A file whose row was deleted would otherwise stay on disk forever, so the
    # age-based sweep stays as a backstop for orphans.
    removed += storage.purge_older_than(
        now - timedelta(hours=active.export_retention_hours), prefix="exports"
    )
    removed += storage.purge_older_than(
        now - timedelta(hours=active.import_retention_hours), prefix="imports"
    )

    async with session_scope() as session:
        import_jobs = await session.scalars(select(ImportJob))
        for import_job in import_jobs:
            if import_job.storage_key and not storage.exists(import_job.storage_key):
                import_job.storage_key = ""
        await session.commit()

    if removed:
        logger.info("export_files_purged", removed=removed)
    return removed


PURGE_TASK_NAME = "sparkxflow.exports.purge_expired"


@register_task(PURGE_TASK_NAME)
async def run_purge_expired() -> int:
    """Inline/synchronous entry point for the scheduled expiry pass."""
    return await purge_expired_files()
