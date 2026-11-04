from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.businesses.models import Business, BusinessContact
from app.modules.crm.models import BusinessNote, BusinessTag, CrmBusinessRecord, CrmStage, Tag
from app.modules.crm.service import move_stage
from app.modules.exports.csv_export import BUSINESS_COLUMNS

# An export is bounded so a runaway selection cannot turn one request into a
# memory problem. Filters narrow further; this is the ceiling, not the target.
EXPORT_ROW_LIMIT = 10_000

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
    has_phone: bool | None = None
    min_rating: float | None = None
    min_reviews: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    located_only: bool = False
    job_id: uuid.UUID | None = None
    shortlisted_only: bool = False
    sort: str = "first_discovered_at"
    descending: bool = True
    limit: int = 50
    offset: int = 0

    def normalized(self) -> BusinessFilters:
        bbox = self.bbox
        if bbox is not None:
            west, south, east, north = bbox
            # An unordered box is a caller bug, not a search: silently swapping it
            # would return a different region than the one drawn on the map.
            if not (-90 <= south <= north <= 90 and -180 <= west <= east <= 180):
                bbox = None
        return BusinessFilters(
            query=(self.query or "").strip() or None,
            city=(self.city or "").strip() or None,
            country=(self.country or "").strip().upper() or None,
            category=(self.category or "").strip() or None,
            website_status=(self.website_status or "").strip() or None,
            has_phone=self.has_phone,
            min_rating=self.min_rating,
            min_reviews=self.min_reviews,
            bbox=bbox,
            located_only=self.located_only,
            job_id=self.job_id,
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


def _apply_filters(statement: Select, filters: BusinessFilters, owner_user_id: uuid.UUID) -> Select:
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
    if filters.has_phone is True:
        statement = statement.where(Business.normalized_phone.is_not(None))
    elif filters.has_phone is False:
        # "No phone reported" is not "no phone exists", and the UI says which.
        statement = statement.where(Business.normalized_phone.is_(None))
    if filters.min_rating is not None:
        statement = statement.where(Business.rating >= filters.min_rating)
    if filters.min_reviews is not None:
        statement = statement.where(Business.review_count >= filters.min_reviews)
    if filters.bbox:
        west, south, east, north = filters.bbox
        statement = statement.where(
            Business.latitude.is_not(None),
            Business.longitude.is_not(None),
            Business.latitude >= south,
            Business.latitude <= north,
            Business.longitude >= west,
            Business.longitude <= east,
        )
    if filters.located_only:
        statement = statement.where(
            Business.latitude.is_not(None), Business.longitude.is_not(None)
        )
    if filters.job_id:
        # Which records this run produced is recorded in provenance, not denormalised
        # onto the business: a job that merged into an existing lead still owns the
        # sighting, and the lead itself may predate the job.
        from app.modules.discovery.models import SourceRecord, SourceRecordLink

        linked = (
            select(SourceRecordLink.entity_id)
            .join(SourceRecord, SourceRecord.id == SourceRecordLink.source_record_id)
            .where(
                SourceRecord.job_id == filters.job_id,
                SourceRecord.owner_user_id == owner_user_id,
                SourceRecordLink.entity_type == "business",
            )
            .subquery()
        )
        statement = statement.where(Business.id.in_(select(linked.c.entity_id)))
    if filters.shortlisted_only:
        # Shortlisted is a CRM stage, not a column on the business. The filter
        # was accepted by the API and never applied, so a request for the
        # shortlisted list returned every record instead.
        shortlisted = (
            select(CrmBusinessRecord.business_id)
            .join(CrmStage, CrmStage.id == CrmBusinessRecord.stage_id)
            .where(
                CrmBusinessRecord.owner_user_id == owner_user_id,
                func.lower(CrmStage.name) == "shortlisted",
            )
        )
        statement = statement.where(Business.id.in_(shortlisted))
    return statement


async def list_businesses(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: BusinessFilters
) -> tuple[list[Business], int]:
    filters = filters.normalized()
    statement = _apply_filters(_base_statement(owner_user_id), filters, owner_user_id)

    total = await session.scalar(select(func.count()).select_from(statement.subquery()))

    column = SORTABLE[filters.sort]
    ordered = statement.order_by(column.desc() if filters.descending else column.asc())
    rows = (await session.scalars(ordered.limit(filters.limit).offset(filters.offset))).all()
    return list(rows), int(total or 0)


async def list_pins(
    session: AsyncSession, owner_user_id: uuid.UUID, filters: BusinessFilters
) -> tuple[list[dict[str, Any]], int]:
    """Pins for one viewport, with the true count of what is inside it.

    Reads only the columns a marker and its preview need, and always reports
    `total` from the same filtered query as the rows: a map that shows 1500 pins and
    says "1500 found" when 4213 match would be lying about the market.
    """
    filters = filters.normalized()
    statement = _apply_filters(
        _base_statement(owner_user_id),
        dataclasses.replace(filters, located_only=True),
        owner_user_id,
    )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await session.execute(
            statement.with_only_columns(
                Business.id,
                Business.name,
                Business.latitude,
                Business.longitude,
                Business.primary_category,
                Business.website_status,
                Business.normalized_phone.is_not(None),
                Business.rating,
                Business.review_count,
                Business.created_at,
            )
            .order_by(Business.created_at.desc())
            .limit(filters.limit)
        )
    ).all()
    pins = [
        {
            "id": row[0],
            "name": row[1],
            "latitude": float(row[2]),
            "longitude": float(row[3]),
            "primary_category": row[4],
            "website_status": row[5],
            "has_phone": row[6],
            "rating": float(row[7]) if row[7] is not None else None,
            "review_count": row[8],
            "discovered_at": row[9],
        }
        for row in rows
        # The query asks for located records only; re-checking here means a pin is
        # never emitted without a place to put it.
        if row[2] is not None and row[3] is not None
    ]
    return pins, int(total or 0)


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


async def soft_delete_many(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_ids: Sequence[uuid.UUID] | None = None,
) -> int:
    """Soft-delete selected rows, or every active row owned by the caller."""
    statement = select(Business).where(
        Business.owner_user_id == owner_user_id,
        Business.deleted_at.is_(None),
    )
    if business_ids is not None:
        statement = statement.where(Business.id.in_(list(business_ids)))
    rows = list((await session.scalars(statement)).all())
    if not rows:
        return 0
    from datetime import UTC, datetime

    deleted_at = datetime.now(UTC)
    for business in rows:
        business.deleted_at = deleted_at
        business.lifecycle_status = "deleted"
    await session.flush()
    return len(rows)


async def list_notes(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> list[BusinessNote]:
    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")
    rows = await session.scalars(
        select(BusinessNote)
        .where(BusinessNote.business_id == business_id, BusinessNote.owner_user_id == owner_user_id)
        .order_by(BusinessNote.created_at.desc())
    )
    return list(rows)


async def create_note(
    session: AsyncSession, *, owner_user_id: uuid.UUID, business_id: uuid.UUID, content: str
) -> BusinessNote:
    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")
    note = BusinessNote(business_id=business_id, owner_user_id=owner_user_id, content=content)
    session.add(note)
    await session.flush()
    return note


async def tags_on_business(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> list[Tag]:
    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")
    rows = await session.scalars(
        select(Tag)
        .join(BusinessTag, BusinessTag.tag_id == Tag.id)
        .where(BusinessTag.business_id == business_id, Tag.owner_user_id == owner_user_id)
        .order_by(Tag.name)
    )
    return list(rows)


async def all_tags(session: AsyncSession, owner_user_id: uuid.UUID) -> list[Tag]:
    rows = await session.scalars(
        select(Tag).where(Tag.owner_user_id == owner_user_id).order_by(Tag.name)
    )
    return list(rows)


async def set_tags(
    session: AsyncSession, *, owner_user_id: uuid.UUID, business_id: uuid.UUID, names: list[str]
) -> list[Tag]:
    """Replace a business's tags with exactly `names`, creating missing tags.

    Tags are owned, so a name that already exists for this owner is reused; a new
    name creates a new tag rather than aliasing someone else's.
    """
    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")

    cleaned = sorted({name.strip() for name in names if name.strip()})
    existing = {
        tag.name: tag
        for tag in (
            await session.scalars(
                select(Tag).where(Tag.owner_user_id == owner_user_id, Tag.name.in_(cleaned))
            )
        ).all()
    }
    tags: list[Tag] = []
    for name in cleaned:
        tag = existing.get(name)
        if tag is None:
            tag = Tag(owner_user_id=owner_user_id, name=name)
            session.add(tag)
            await session.flush()
            existing[name] = tag
        tags.append(tag)

    await session.execute(
        delete(BusinessTag).where(BusinessTag.business_id == business_id)
    )
    for tag in tags:
        session.add(BusinessTag(business_id=business_id, tag_id=tag.id))
    await session.flush()
    return tags


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
    """Build CSV-ready rows for a filter, including provenance and verification state."""
    filters = filters.normalized()
    statement = _apply_filters(_base_statement(owner_user_id), filters, owner_user_id).order_by(
        Business.first_discovered_at.desc()
    )
    rows = (await session.scalars(statement.limit(EXPORT_ROW_LIMIT))).all()
    return await _build_export_rows(session, owner_user_id, list(rows))


async def export_rows_by_ids(
    session: AsyncSession, owner_user_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> tuple[list[dict[str, Any]], int]:
    """Export exactly the records selected on the map or in the table.

    Ids are resolved through the same owner-scoped statement as every other read, so
    another user's id simply is not found — and the count of those is returned rather
    than swallowed, because a selection that silently exports fewer rows than the user
    picked needs to say so out loud.
    """
    statement = (
        _base_statement(owner_user_id)
        .where(Business.id.in_(list(ids)))
        .order_by(Business.first_discovered_at.desc())
        .limit(EXPORT_ROW_LIMIT)
    )
    rows = (await session.scalars(statement)).all()
    found = {row.id for row in rows}
    skipped = len(set(ids)) - len(found)
    return await _build_export_rows(session, owner_user_id, list(rows)), max(skipped, 0)


async def _build_export_rows(
    session: AsyncSession, owner_user_id: uuid.UUID, businesses: list[Business]
) -> list[dict[str, Any]]:
    business_ids = [business.id for business in businesses]
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
    for business in businesses:
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
    "soft_delete_many",
]
