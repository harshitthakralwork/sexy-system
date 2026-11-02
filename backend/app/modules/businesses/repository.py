from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.businesses.models import Business, BusinessContact
from app.modules.crm.models import CrmBusinessRecord, CrmStage
from app.modules.crm.service import move_stage
from app.modules.exports.csv_export import BUSINESS_COLUMNS

SORTABLE = {
    "name": Business.name,
    "city": Business.city,
    "first_discovered_at": Business.first_discovered_at,
    "primary_category": Business.primary_category,
    "website_status": Business.website_status,
}


@dataclass(frozen=True)
class BusinessFilters:
    """Query parameters accepted by the results table.

    Anything not listed here cannot reach the database, which is what keeps the
    filter surface from becoming an injection surface as it grows.
    """

    query: str | None = None
    city: str | None = None
    country: str | None = None
    category: str | None = None
    website_status: str | None = None
    shortlisted_only: bool = False
    sort: str = "first_discovered_at"
    descending: bool = True
    limit: int = 50
    offset: int = 0

    def normalized(self) -> BusinessFilters:
        return BusinessFilters(
            query=(self.query or "").strip() or None,
            city=(self.city or "").strip() or None,
            country=(self.country or "").strip().upper() or None,
            category=(self.category or "").strip() or None,
            website_status=(self.website_status or "").strip() or None,
            shortlisted_only=self.shortlisted_only,
            sort=self.sort if self.sort in SORTABLE else "first_discovered_at",
            descending=self.descending,
            limit=min(max(self.limit, 1), 500),
            offset=max(self.offset, 0),
        )


def _base_statement(owner_user_id: uuid.UUID) -> Select:
    """Every read starts here.

    The owner predicate is not optional and not defaulted: a statement built
    without it would return every user's businesses, and nothing downstream
    would notice.
    """
    return select(Business).where(
        Business.owner_user_id == owner_user_id,
        Business.deleted_at.is_(None),
    )


def _apply_filters(statement: Select, filters: BusinessFilters) -> Select:
    if filters.query:
        pattern = f"%{filters.query}%"
        statement = statement.where(
            or_(
                Business.name.ilike(pattern),
                Business.normalized_domain.ilike(pattern),
                Business.city.ilike(pattern),
                Business.primary_category.ilike(pattern),
            )
        )
    if filters.city:
        statement = statement.where(func.lower(Business.city) == filters.city.lower())
    if filters.country:
        statement = statement.where(Business.country == filters.country)
    if filters.category:
        statement = statement.where(
            func.lower(Business.primary_category) == filters.category.lower()
        )
    if filters.website_status:
        statement = statement.where(Business.website_status == filters.website_status)
    return statement


async def list_businesses(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: BusinessFilters
) -> tuple[list[Business], int]:
    filters = filters.normalized()
    statement = _apply_filters(_base_statement(owner_user_id), filters)

    total = await session.scalar(select(func.count()).select_from(statement.subquery()))

    column = SORTABLE[filters.sort]
    ordered = statement.order_by(column.desc() if filters.descending else column.asc())
    rows = (await session.scalars(ordered.limit(filters.limit).offset(filters.offset))).all()
    return list(rows), int(total or 0)


async def get_business(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> Business | None:
    """Return None for a row that exists but belongs to someone else.

    The router turns both cases into 404. Distinguishing them would confirm to a
    caller that an id is real, which is an information leak dressed up as a
    helpful error.
    """
    return await session.scalar(
        select(Business).where(
            Business.id == business_id,
            Business.owner_user_id == owner_user_id,
            Business.deleted_at.is_(None),
        )
    )


async def contacts_for(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> list[BusinessContact]:
    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        return []
    rows = await session.scalars(
        select(BusinessContact).where(BusinessContact.business_id == business_id)
    )
    return list(rows)


async def shortlist(
    session: AsyncSession, *, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> Business:
    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")
    await move_stage(
        session,
        owner_user_id=owner_user_id,
        business_id=business_id,
        stage_name="Shortlisted",
        reason="Shortlisted from results",
    )
    return business


async def archive(
    session: AsyncSession, *, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> None:
    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")
    business.lifecycle_status = "archived"
    await move_stage(
        session,
        owner_user_id=owner_user_id,
        business_id=business_id,
        stage_name="Archived",
        reason="Archived from results",
    )


async def soft_delete(
    session: AsyncSession, *, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> None:
    """Mark deleted rather than remove.

    Shortlisted records carry outreach history and provenance that the retention
    rules protect; a hard delete here would be irreversible by the time anyone
    noticed.
    """
    from datetime import UTC, datetime

    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")
    business.deleted_at = datetime.now(UTC)
    business.lifecycle_status = "deleted"


async def stage_name(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> str | None:
    record = await session.scalar(
        select(CrmBusinessRecord).where(
            CrmBusinessRecord.business_id == business_id,
            CrmBusinessRecord.owner_user_id == owner_user_id,
        )
    )
    if record is None:
        return None
    stage = await session.get(CrmStage, record.stage_id)
    return stage.name if stage else None


async def provenance_map(
    session: AsyncSession, owner_user_id: uuid.UUID, business_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[list[str], list[str]]]:
    """Source slugs and URLs behind each business, in one query.

    An export whose `source_slugs` column is empty is a lead list nobody can
    re-verify, opt out against, or trust a month later.
    """
    if not business_ids:
        return {}

    from app.modules.discovery.models import SourceRecord, SourceRecordLink
    from app.modules.sources.models import Source

    rows = await session.execute(
        select(
            SourceRecordLink.entity_id,
            Source.slug,
            SourceRecord.source_url,
        )
        .join(SourceRecord, SourceRecord.id == SourceRecordLink.source_record_id)
        .join(Source, Source.id == SourceRecord.source_id)
        .where(
            SourceRecordLink.entity_type == "business",
            SourceRecordLink.entity_id.in_(business_ids),
            SourceRecord.owner_user_id == owner_user_id,
        )
    )
    collected: dict[uuid.UUID, tuple[list[str], list[str]]] = {
        business_id: ([], []) for business_id in business_ids
    }
    for entity_id, slug, source_url in rows:
        slugs, urls = collected.setdefault(entity_id, ([], []))
        if slug and slug not in slugs:
            slugs.append(slug)
        if source_url and source_url not in urls:
            urls.append(source_url)
    return collected


async def export_rows(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: BusinessFilters
) -> list[dict[str, Any]]:
    """Build CSV-ready rows, including provenance and verification state."""
    filters = filters.normalized()
    statement = _apply_filters(_base_statement(owner_user_id), filters).order_by(
        Business.first_discovered_at.desc()
    )
    rows = (await session.scalars(statement.limit(10_000))).all()
    business_ids = [business.id for business in rows]
    provenance = await provenance_map(session, owner_user_id, business_ids)

    stage_rows = await session.execute(
        select(CrmBusinessRecord.business_id, CrmStage.name)
        .join(CrmStage, CrmStage.id == CrmBusinessRecord.stage_id)
        .where(CrmBusinessRecord.owner_user_id == owner_user_id)
        .where(CrmBusinessRecord.business_id.in_(business_ids))
    )
    # `.all()` first: a Result is iterable but not mapping-convertible, and
    # `dict(result)` raises rather than degrading.
    stages = dict(stage_rows.all())

    output: list[dict[str, Any]] = []
    for business in rows:
        contacts = list(
            await session.scalars(
                select(BusinessContact).where(BusinessContact.business_id == business.id)
            )
        )
        slugs, urls = provenance.get(business.id, ([], []))
        output.append(
            {
                "name": business.name,
                "primary_category": business.primary_category,
                "phone": business.phone,
                "email": business.email,
                "email_verification_status": next(
                    (c.verification_status for c in contacts if c.normalized_email), "unknown"
                ),
                "website_url": business.website_url,
                "website_status": business.website_status,
                "address": business.address,
                "city": business.city,
                "state": business.state,
                "country": business.country,
                "latitude": float(business.latitude) if business.latitude is not None else None,
                "longitude": float(business.longitude) if business.longitude is not None else None,
                "opportunity_score": None,
                "opportunity_confidence": None,
                "qualification_status": None,
                "evidence_summary": None,
                "source_slugs": slugs,
                "source_urls": urls,
                "first_discovered_at": business.first_discovered_at,
                "last_researched_at": business.last_researched_at,
                "crm_stage": stages.get(business.id),
            }
        )
    return output


__all__ = [
    "BUSINESS_COLUMNS",
    "archive",
    "contacts_for",
    "export_rows",
    "get_business",
    "list_businesses",
    "shortlist",
    "soft_delete",
]
