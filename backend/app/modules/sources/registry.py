from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.discovery.adapters.base import AdapterCapabilities
from app.modules.sources.models import Source


def _described(
    capabilities: AdapterCapabilities, *, repair_name: bool
) -> dict[str, Any]:
    """The columns an adapter is authoritative about.

    Health, the enabled switch and the category are always absent — those are state
    and ownership decisions, not description. `name` is only repaired by the Source
    Manager's own catalogue pass, which knows exactly one adapter per provider; a
    provenance write from inside a run must not rewrite the display name, or the
    first caller would decide what every later reader sees.
    """
    described: dict[str, Any] = {
        "description": (
            f"{capabilities.name} — accepts {', '.join(capabilities.supported_query_types)}. "
            f"{capabilities.geographic_coverage}"
        ),
        "capabilities": {"available_fields": list(capabilities.available_fields)},
        "limitations": {
            "rate_limit_notes": capabilities.rate_limit_notes,
            "terms_notes": capabilities.terms_notes,
            "access_requirements": list(capabilities.access_requirements),
            "max_results_per_query": capabilities.max_results_per_query,
        },
        "coverage": {"geographic_coverage": capabilities.geographic_coverage},
        "rate_limit_config": {"notes": capabilities.rate_limit_notes},
    }
    if repair_name:
        described["name"] = capabilities.name
    return described


async def sync_described(
    session: AsyncSession, capabilities: AdapterCapabilities, *, repair_name: bool = False
) -> Source:
    """Insert a registry row, or refresh the description it is generated from.

    A row that keeps whichever wording created it first will drift: a source's real
    limits change with the code that talks to it, and the manager has to show the
    current ones rather than a stale claim.
    """
    source = await session.scalar(select(Source).where(Source.slug == capabilities.slug))
    described = _described(capabilities, repair_name=repair_name)
    if source is None:
        source = Source(
            slug=capabilities.slug,
            name=capabilities.name,
            category=capabilities.category,
            adapter_key=capabilities.adapter_key,
            **described,
        )
        session.add(source)
        await session.flush()
        return source

    changed = False
    for column, value in described.items():
        if getattr(source, column) != value:
            setattr(source, column, value)
            changed = True
    if changed:
        await session.flush()
    return source


async def ensure_source(session: AsyncSession, capabilities: AdapterCapabilities) -> uuid.UUID:
    """Register an adapter in the source table, idempotently by slug.

    Every provenance row references `sources`, so a job that runs without a
    registry row cannot record where its data came from. Describing the source
    from the adapter's own capabilities — including its limitations — keeps the
    registry honest instead of hand-maintained and optimistic.
    """
    source = await sync_described(session, capabilities)
    return source.id


def adapter_for(settings: Settings, slug: str) -> tuple[str, Any]:
    """Build one adapter by slug, from configuration only.

    The two existing factories are asked in turn, so the Source Manager never
    keeps a third list of providers that can drift from the code that actually
    runs. An unknown slug raises — a source the manager can show but no job can
    use would be a lie in the opposite direction.
    """
    from app.modules.discovery import runner
    from app.modules.social import service as social_service

    if slug in ("overpass", "searxng"):
        built = runner.build_adapters(settings, [slug])
        return built[0]
    adapter = social_service._build_adapter(settings, slug)
    return slug, adapter


def catalogue_slugs(settings: Settings) -> list[str]:
    """Every slug this build can actually run, discovery first.

    SearXNG appears once: the same instance answers both discovery queries and
    social tracks, and two registry rows for one provider would double-count its
    health and its usage.
    """
    from app.modules.discovery import runner
    from app.modules.social.connectors import ADAPTER_REGISTRY

    slugs: list[str] = []
    for slug in runner.AVAILABLE_SOURCE_SLUGS:
        if slug not in slugs:
            slugs.append(slug)
    for key in ADAPTER_REGISTRY:
        if key not in slugs:
            slugs.append(key)
    return slugs


async def ensure_registered_sources(
    session: AsyncSession, settings: Settings
) -> list[Source] | None:
    """Register every runnable adapter so the manager has rows before any run.

    This is the one pass that repairs a row's display name, because it picks exactly
    one adapter per provider — SearXNG counts once, as the discovery provider it is
    for jobs. A source that no longer maps to any adapter is left alone: it may still
    be referenced by provenance rows, and deleting it would delete their history.
    """
    for slug in catalogue_slugs(settings):
        _, adapter = adapter_for(settings, slug)
        try:
            await sync_described(session, adapter.capabilities, repair_name=True)
        finally:
            await adapter.aclose()
    rows = await session.scalars(select(Source).order_by(Source.category, Source.name))
    return list(rows)

