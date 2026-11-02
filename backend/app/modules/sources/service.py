"""Source Manager service (master plan #28).

The registry rows already existed but nothing could read or change them, so the
screen had no power over anything. This service gives the operator the three things
the PRD asks for — status, configuration, and the ability to turn a source off — and
each one is honoured by the code that actually runs jobs, so a disabled source cannot
be used by a discovery run or a track.

Health and usage are recorded, not inferred: a `working` badge appears only after an
adapter answered, and the usage figures are the counters a real run observed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.discovery.adapters.base import AdapterError, HealthResult
from app.modules.sources import registry
from app.modules.sources.models import (
    Source,
    SourceConfiguration,
    SourceHealthCheck,
    SourceUsageRecord,
)


async def get_by_slug(session: AsyncSession, slug: str) -> Source | None:
    return await session.scalar(select(Source).where(Source.slug == slug))


async def registered_sources(session: AsyncSession, settings: Settings) -> list[Source]:
    return await registry.ensure_registered_sources(session, settings) or []


async def _configuration_for(
    session: AsyncSession, owner_user_id: uuid.UUID, source_ids: list[uuid.UUID]
) -> dict[uuid.UUID, SourceConfiguration]:
    if not source_ids:
        return {}
    rows = await session.scalars(
        select(SourceConfiguration).where(
            SourceConfiguration.owner_user_id == owner_user_id,
            SourceConfiguration.source_id.in_(source_ids),
        )
    )
    return {row.source_id: row for row in rows}


async def _latest_health(session: AsyncSession) -> dict[uuid.UUID, SourceHealthCheck]:
    """Newest probe per source.

    A grouped subquery rather than DISTINCT ON, so the read does not depend on a
    Postgres-only spelling of the same idea.
    """
    newest = (
        select(
            SourceHealthCheck.source_id.label("source_id"),
            func.max(SourceHealthCheck.checked_at).label("checked_at"),
        )
        .group_by(SourceHealthCheck.source_id)
        .subquery()
    )
    rows = await session.scalars(
        select(SourceHealthCheck).join(
            newest,
            and_(
                SourceHealthCheck.source_id == newest.c.source_id,
                SourceHealthCheck.checked_at == newest.c.checked_at,
            ),
        )
    )
    latest: dict[uuid.UUID, SourceHealthCheck] = {}
    for row in rows:
        latest.setdefault(row.source_id, row)
    return latest


async def _usage_by_source(
    session: AsyncSession,
) -> dict[uuid.UUID, dict[str, Any]]:
    rows = await session.execute(
        select(
            SourceUsageRecord.source_id,
            func.count(),
            func.sum(SourceUsageRecord.requests_count),
            func.sum(SourceUsageRecord.records_returned),
            func.sum(SourceUsageRecord.records_accepted),
            # Counts only the non-null ones: the gap against `runs` is what tells
            # this function that at least one run could not report the number.
            func.count(SourceUsageRecord.records_accepted),
            func.max(SourceUsageRecord.measured_at),
        ).group_by(SourceUsageRecord.source_id)
    )
    return {
        source_id: {
            "runs_recorded": int(runs),
            "requests_count": int(requests or 0),
            "records_returned": int(returned or 0),
            # A partial picture is reported as unknown, never as a smaller total:
            # "we were not told" is not the same claim as "none were accepted".
            "records_accepted": None if accepted_seen < runs else int(accepted_total or 0),
            "last_run_at": last_run_at,
        }
        for (
            source_id,
            runs,
            requests,
            returned,
            accepted_total,
            accepted_seen,
            last_run_at,
        ) in rows
    }


async def list_sources(
    session: AsyncSession, owner_user_id: uuid.UUID, settings: Settings
) -> list[dict]:
    sources = await registered_sources(session, settings)
    configs = await _configuration_for(session, owner_user_id, [row.id for row in sources])
    health = await _latest_health(session)
    usage = await _usage_by_source(session)

    out: list[dict] = []
    for row in sources:
        config = configs.get(row.id)
        last_check = health.get(row.id)
        counts = usage.get(row.id, {})
        out.append(
            {
                "id": row.id,
                "slug": row.slug,
                "name": row.name,
                "category": row.category,
                "adapter_key": row.adapter_key,
                "description": row.description,
                "globally_enabled": row.is_enabled,
                "enabled_for_user": True if config is None else config.is_enabled,
                "configured_at": config.updated_at if config else None,
                "configuration": config.configuration if config else {},
                "secret_reference": config.secret_reference if config else None,
                "health_status": row.health_status,
                "last_error": row.last_error,
                "last_check_at": last_check.checked_at if last_check else None,
                "last_check_response_ms": last_check.response_time_ms if last_check else None,
                "last_check_detail": (
                    (last_check.metadata_ or {}).get("detail") if last_check else None
                ),
                "last_successful_run_at": counts.get("last_run_at"),
                "runs_recorded": counts.get("runs_recorded", 0),
                "requests_count": counts.get("requests_count", 0),
                "records_returned": counts.get("records_returned", 0),
                "records_accepted": counts.get("records_accepted"),
                "capabilities": row.capabilities,
                "limitations": row.limitations,
                "coverage": row.coverage,
                "rate_limit_config": row.rate_limit_config,
            }
        )
    return out


async def _source_or_404(session: AsyncSession, slug: str) -> Source:
    row = await get_by_slug(session, slug)
    if row is None:
        raise NotFoundError(f"Source '{slug}' is not registered")
    return row


async def set_enabled(
    session: AsyncSession, owner_user_id: uuid.UUID, slug: str, enabled: bool
) -> SourceConfiguration:
    """Turn a source on or off for this account only.

    `sources.is_enabled` stays the operator-wide switch and `source_configurations`
    is per-user, so one account cannot silently change what another one collects.
    """
    source = await _source_or_404(session, slug)
    config = await session.scalar(
        select(SourceConfiguration).where(
            SourceConfiguration.source_id == source.id,
            SourceConfiguration.owner_user_id == owner_user_id,
        )
    )
    if config is None:
        config = SourceConfiguration(
            source_id=source.id,
            owner_user_id=owner_user_id,
            configuration={},
            is_enabled=enabled,
        )
        session.add(config)
    else:
        config.is_enabled = enabled
    await session.flush()
    await session.refresh(config)
    return config


async def configure(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    slug: str,
    settings: Settings,
    configuration: dict[str, Any],
    secret_reference: str | None,
    enabled: bool | None = None,
) -> SourceConfiguration:
    """Store per-account source settings, validated by the adapter that reads them.

    Validation runs through the real adapter, so a typo in a feed URL is refused
    here rather than surfacing weeks later as an empty run.
    """
    source = await _source_or_404(session, slug)
    cleaned: dict[str, Any] = {}
    if "feed_urls" in configuration:
        cleaned["feed_urls"] = [
            str(url).strip() for url in configuration["feed_urls"] if str(url).strip()
        ]
    if "note" in configuration:
        cleaned["note"] = str(configuration["note"]).strip()[:500]

    if cleaned.get("feed_urls"):
        if source.adapter_key != "rss":
            raise ValidationFailedError(
                "Feed URLs apply only to the RSS/Atom source; other providers take no "
                "per-account connection settings."
            )
        _, adapter = registry.adapter_for(settings, slug)
        try:
            await adapter.validate_config({"feed_urls": cleaned["feed_urls"]})
        except AdapterError as exc:
            raise ValidationFailedError(exc.message) from exc
        finally:
            await adapter.aclose()

    config = await session.scalar(
        select(SourceConfiguration).where(
            SourceConfiguration.source_id == source.id,
            SourceConfiguration.owner_user_id == owner_user_id,
        )
    )
    if config is None:
        config = SourceConfiguration(
            source_id=source.id,
            owner_user_id=owner_user_id,
            configuration=cleaned,
            is_enabled=True if enabled is None else enabled,
        )
        session.add(config)
    else:
        # A blank submission means "clear what I set", not "keep the old value".
        config.configuration = cleaned
        if enabled is not None:
            config.is_enabled = enabled
    if secret_reference is not None:
        config.secret_reference = secret_reference.strip() or None
    await session.flush()
    await session.refresh(config)
    return config


async def owner_feed_urls(
    session: AsyncSession, owner_user_id: uuid.UUID, slug: str
) -> list[str]:
    """The feeds this account configured for a source, if any.

    Read by the track runner, which is what makes "Configure" more than a form.
    """
    row = await session.execute(
        select(SourceConfiguration.configuration)
        .join(Source, Source.id == SourceConfiguration.source_id)
        .where(
            Source.slug == slug,
            SourceConfiguration.owner_user_id == owner_user_id,
        )
    )
    for (configuration,) in row:
        feeds = (configuration or {}).get("feed_urls")
        if isinstance(feeds, list) and feeds:
            return [str(feed) for feed in feeds]
    return []


async def disabled_slugs(
    session: AsyncSession, owner_user_id: uuid.UUID, slugs: list[str]
) -> dict[str, str]:
    """Which of these slugs this account may not use, and why."""
    if not slugs:
        return {}
    rows = await session.scalars(select(Source).where(Source.slug.in_(slugs)))
    by_slug = {row.slug: row for row in rows}
    configs = await _configuration_for(session, owner_user_id, [row.id for row in by_slug.values()])

    blocked: dict[str, str] = {}
    for slug in slugs:
        source = by_slug.get(slug)
        # An unregistered slug is not blocked here: the runner has no adapter for
        # it and reports that itself. Silence would be the wrong fix.
        if source is None:
            continue
        if not source.is_enabled:
            blocked[slug] = "disabled for every account"
            continue
        config = configs.get(source.id)
        if config is not None and not config.is_enabled:
            blocked[slug] = "disabled for your account"
    return blocked


async def record_usage(
    session: AsyncSession,
    source_id: uuid.UUID,
    *,
    job_id: uuid.UUID | None,
    requests_count: int,
    records_returned: int,
    records_accepted: int | None,
    measured_at: datetime,
) -> None:
    """One row per source per run, from counters the run actually observed."""
    session.add(
        SourceUsageRecord(
            source_id=source_id,
            job_id=job_id,
            requests_count=requests_count,
            records_returned=records_returned,
            records_accepted=records_accepted,
            measured_at=measured_at,
        )
    )
    await session.flush()


async def record_health(
    session: AsyncSession,
    source: Source,
    result: HealthResult,
    *,
    detail_extra: dict[str, Any] | None = None,
) -> SourceHealthCheck:
    """Persist a probe and let it change the registry status it describes."""
    check = SourceHealthCheck(
        source_id=source.id,
        status=result.status,
        checked_at=datetime.now(UTC),
        response_time_ms=result.response_time_ms,
        error_message=result.detail if not result.ok else None,
        metadata_=dict(detail_extra or {}),
    )
    session.add(check)
    source.health_status = result.status
    source.last_error = None if result.ok else result.detail
    await session.flush()
    await session.refresh(check)
    return check


async def test_connection(
    session: AsyncSession, slug: str, settings: Settings
) -> dict[str, Any]:
    """Ask the adapter itself whether the provider answers right now."""
    source = await _source_or_404(session, slug)
    _, adapter = registry.adapter_for(settings, slug)
    try:
        result = await adapter.health_check()
    except AdapterError as exc:
        result = HealthResult(status="failed", detail=exc.message[:500])
    except Exception as exc:  # noqa: BLE001 - a probe must never break the request
        result = HealthResult(status="failed", detail=type(exc).__name__)
    finally:
        await adapter.aclose()

    check = await record_health(session, source, result)
    return {
        "slug": slug,
        "status": result.status,
        "detail": result.detail,
        "response_time_ms": result.response_time_ms,
        "checked_at": check.checked_at,
    }


async def source_history(
    session: AsyncSession, slug: str, *, limit: int
) -> dict[str, Any]:
    """Recent probes and recent per-source run counters, newest first."""
    source = await _source_or_404(session, slug)
    checks = list(
        await session.scalars(
            select(SourceHealthCheck)
            .where(SourceHealthCheck.source_id == source.id)
            .order_by(SourceHealthCheck.checked_at.desc())
            .limit(limit)
        )
    )
    runs = list(
        await session.scalars(
            select(SourceUsageRecord)
            .where(SourceUsageRecord.source_id == source.id)
            .order_by(SourceUsageRecord.measured_at.desc())
            .limit(limit)
        )
    )
    return {"checks": checks, "runs": runs}
