from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.discovery.adapters.base import AdapterCapabilities
from app.modules.sources.models import Source


async def ensure_source(session: AsyncSession, capabilities: AdapterCapabilities) -> uuid.UUID:
    """Register an adapter in the source table, idempotently by slug.

    Every provenance row references `sources`, so a job that runs without a
    registry row cannot record where its data came from. Describing the source
    from the adapter's own capabilities — including its limitations — keeps the
    registry honest instead of hand-maintained and optimistic.
    """
    existing = await session.scalar(select(Source).where(Source.slug == capabilities.slug))
    if existing is not None:
        return existing.id

    source = Source(
        name=capabilities.name,
        slug=capabilities.slug,
        category=capabilities.category,
        adapter_key=capabilities.adapter_key,
        description=(
            f"{capabilities.name} — accepts {', '.join(capabilities.supported_query_types)}. "
            f"{capabilities.geographic_coverage}"
        ),
        capabilities={"available_fields": list(capabilities.available_fields)},
        limitations={
            "rate_limit_notes": capabilities.rate_limit_notes,
            "terms_notes": capabilities.terms_notes,
            "access_requirements": list(capabilities.access_requirements),
            "max_results_per_query": capabilities.max_results_per_query,
        },
        coverage={"geographic_coverage": capabilities.geographic_coverage},
        rate_limit_config={"notes": capabilities.rate_limit_notes},
    )
    session.add(source)
    await session.flush()
    return source.id
