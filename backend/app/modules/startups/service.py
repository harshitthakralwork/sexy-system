from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.startups.models import (
    REVENUE_CLASSIFICATIONS,
    STARTUP_STATUSES,
    Startup,
    StartupCompetitor,
    StartupFounder,
    StartupPricing,
    StartupProduct,
    StartupResearchRecord,
    StartupRevenueRecord,
    StartupWatchlist,
    StartupWatchlistItem,
)
from app.shared.normalization import normalize_domain, normalize_name


async def _get(session: AsyncSession, owner_id: uuid.UUID, startup_id: uuid.UUID) -> Startup | None:
    return await session.scalar(
        select(Startup).where(
            Startup.id == startup_id,
            Startup.owner_user_id == owner_id,
            Startup.deleted_at.is_(None),
        )
    )


async def _require(session: AsyncSession, owner_id: uuid.UUID, startup_id: uuid.UUID) -> Startup:
    startup = await _get(session, owner_id, startup_id)
    if startup is None:
        raise NotFoundError("Startup not found")
    return startup


async def create_startup(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    name: str,
    website_url: str | None,
    description: str | None,
    industry: str | None,
    country: str | None,
    city: str | None,
    founding_date: date | None,
    launch_date: date | None,
    funding_stage: str | None,
    status: str,
    source_slug: str | None,
    source_url: str | None,
) -> Startup:
    if status not in STARTUP_STATUSES:
        raise ValidationFailedError(
            f"Unknown startup status '{status}'", details={"allowed": list(STARTUP_STATUSES)}
        )
    domain = normalize_domain(website_url)
    if domain:
        existing = await session.scalar(
            select(Startup).where(
                Startup.owner_user_id == owner_user_id,
                Startup.normalized_domain == domain,
                Startup.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise ConflictError(
                "A startup with this domain already exists",
                details={"existing_id": str(existing.id)},
            )
    startup = Startup(
        owner_user_id=owner_user_id,
        name=name,
        normalized_name=normalize_name(name) or name.lower(),
        website_url=website_url,
        normalized_domain=domain,
        description=description,
        industry=industry,
        country=country,
        city=city,
        founding_date=founding_date,
        launch_date=launch_date,
        funding_stage=funding_stage,
        status=status,
        source_slug=source_slug,
        source_url=source_url,
    )
    session.add(startup)
    await session.flush()
    await session.refresh(startup)
    return startup


async def list_startups(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    query: str | None,
    industry: str | None,
    country: str | None,
    funding_stage: str | None,
    status: str | None,
    watchlist_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Startup], int]:
    conditions = [Startup.owner_user_id == owner_user_id, Startup.deleted_at.is_(None)]
    if query:
        pattern = f"%{query.strip().lower()}%"
        conditions.append(
            Startup.normalized_name.like(pattern)
            | Startup.description.ilike(pattern)
            | Startup.normalized_domain.ilike(pattern)
        )
    if industry:
        conditions.append(Startup.industry == industry)
    if country:
        conditions.append(Startup.country == country)
    if funding_stage:
        conditions.append(Startup.funding_stage == funding_stage)
    if status:
        conditions.append(Startup.status == status)
    if watchlist_id is not None:
        conditions.append(
            Startup.id.in_(
                select(StartupWatchlistItem.startup_id).where(
                    StartupWatchlistItem.watchlist_id == watchlist_id
                )
            )
        )

    total = await session.scalar(select(func.count()).select_from(Startup).where(*conditions)) or 0
    rows = list(
        await session.scalars(
            select(Startup)
            .where(*conditions)
            .order_by(Startup.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return rows, total


async def update_startup(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    startup_id: uuid.UUID,
    **changes: Any,
) -> Startup:
    startup = await _require(session, owner_user_id, startup_id)
    if changes.get("status") is not None and changes["status"] not in STARTUP_STATUSES:
        raise ValidationFailedError(
            f"Unknown startup status '{changes['status']}'",
            details={"allowed": list(STARTUP_STATUSES)},
        )
    if changes.get("website_url") is not None:
        domain = normalize_domain(changes["website_url"])
        if domain:
            existing = await session.scalar(
                select(Startup).where(
                    Startup.owner_user_id == owner_user_id,
                    Startup.normalized_domain == domain,
                    Startup.deleted_at.is_(None),
                    Startup.id != startup_id,
                )
            )
            if existing is not None:
                raise ConflictError(
                    "A startup with this domain already exists",
                    details={"existing_id": str(existing.id)},
                )
        changes["normalized_domain"] = domain
    for field, value in changes.items():
        setattr(startup, field, value)
    await session.flush()
    await session.refresh(startup)
    return startup


async def soft_delete_startup(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID
) -> None:
    startup = await _require(session, owner_user_id, startup_id)
    from app.shared.base import utcnow

    startup.deleted_at = utcnow()
    await session.flush()


# --- Founders -------------------------------------------------------------


async def add_founder(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    startup_id: uuid.UUID,
    name: str,
    role: str | None,
    public_profile_url: str | None,
) -> StartupFounder:
    await _require(session, owner_user_id, startup_id)
    founder = StartupFounder(
        startup_id=startup_id,
        name=name,
        role=role,
        public_profile_url=public_profile_url,
    )
    session.add(founder)
    await session.flush()
    await session.refresh(founder)
    return founder


async def list_founders(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID
) -> list[StartupFounder]:
    await _require(session, owner_user_id, startup_id)
    return list(
        await session.scalars(
            select(StartupFounder)
            .where(StartupFounder.startup_id == startup_id)
            .order_by(StartupFounder.created_at)
        )
    )


async def delete_founder(
    session: AsyncSession, *, owner_user_id: uuid.UUID, founder_id: uuid.UUID
) -> None:
    founder = await session.scalar(
        select(StartupFounder).where(StartupFounder.id == founder_id)
    )
    if founder is None:
        raise NotFoundError("Founder not found")
    await _require(session, owner_user_id, founder.startup_id)
    await session.delete(founder)
    await session.flush()


# --- Products -------------------------------------------------------------


async def add_product(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID, **fields: Any
) -> StartupProduct:
    await _require(session, owner_user_id, startup_id)
    product = StartupProduct(startup_id=startup_id, **fields)
    session.add(product)
    await session.flush()
    await session.refresh(product)
    return product


async def list_products(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID
) -> list[StartupProduct]:
    await _require(session, owner_user_id, startup_id)
    return list(
        await session.scalars(
            select(StartupProduct)
            .where(StartupProduct.startup_id == startup_id)
            .order_by(StartupProduct.created_at)
        )
    )


async def delete_product(
    session: AsyncSession, *, owner_user_id: uuid.UUID, product_id: uuid.UUID
) -> None:
    product = await session.scalar(select(StartupProduct).where(StartupProduct.id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    await _require(session, owner_user_id, product.startup_id)
    await session.delete(product)
    await session.flush()


# --- Pricing --------------------------------------------------------------


async def add_pricing(
    session: AsyncSession, *, owner_user_id: uuid.UUID, product_id: uuid.UUID, **fields: Any
) -> StartupPricing:
    product = await session.scalar(select(StartupProduct).where(StartupProduct.id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    await _require(session, owner_user_id, product.startup_id)
    pricing = StartupPricing(product_id=product_id, **fields)
    session.add(pricing)
    await session.flush()
    await session.refresh(pricing)
    return pricing


async def list_pricing(
    session: AsyncSession, *, owner_user_id: uuid.UUID, product_id: uuid.UUID
) -> list[StartupPricing]:
    product = await session.scalar(select(StartupProduct).where(StartupProduct.id == product_id))
    if product is None:
        raise NotFoundError("Product not found")
    await _require(session, owner_user_id, product.startup_id)
    return list(
        await session.scalars(
            select(StartupPricing)
            .where(StartupPricing.product_id == product_id)
            .order_by(StartupPricing.observed_at.desc())
        )
    )


async def delete_pricing(
    session: AsyncSession, *, owner_user_id: uuid.UUID, pricing_id: uuid.UUID
) -> None:
    pricing = await session.scalar(select(StartupPricing).where(StartupPricing.id == pricing_id))
    if pricing is None:
        raise NotFoundError("Pricing record not found")
    product = await session.scalar(
        select(StartupProduct).where(StartupProduct.id == pricing.product_id)
    )
    if product is None:
        raise NotFoundError("Product not found")
    await _require(session, owner_user_id, product.startup_id)
    await session.delete(pricing)
    await session.flush()


# --- Revenue --------------------------------------------------------------


def _validate_revenue(classification: str, amount: float | None, methodology: str | None) -> None:
    if classification not in REVENUE_CLASSIFICATIONS:
        raise ValidationFailedError(
            f"Unknown revenue classification '{classification}'",
            details={"allowed": list(REVENUE_CLASSIFICATIONS)},
        )
    if classification == "not_available" and amount is not None:
        raise ValidationFailedError(
            "A 'not_available' revenue record must not carry an amount",
            details={"classification": classification},
        )
    if classification == "estimated" and not (methodology or "").strip():
        raise ValidationFailedError(
            "An 'estimated' revenue record must state its methodology"
        )


async def add_revenue(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    startup_id: uuid.UUID,
    classification: str,
    amount: float | None,
    methodology: str | None,
    **fields: Any,
) -> StartupRevenueRecord:
    await _require(session, owner_user_id, startup_id)
    _validate_revenue(classification, amount, methodology)
    record = StartupRevenueRecord(
        startup_id=startup_id,
        classification=classification,
        amount=amount,
        methodology=methodology,
        **fields,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def list_revenue(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID
) -> list[StartupRevenueRecord]:
    await _require(session, owner_user_id, startup_id)
    return list(
        await session.scalars(
            select(StartupRevenueRecord)
            .where(StartupRevenueRecord.startup_id == startup_id)
            .order_by(StartupRevenueRecord.observed_at.desc())
        )
    )


async def delete_revenue(
    session: AsyncSession, *, owner_user_id: uuid.UUID, revenue_id: uuid.UUID
) -> None:
    record = await session.scalar(
        select(StartupRevenueRecord).where(StartupRevenueRecord.id == revenue_id)
    )
    if record is None:
        raise NotFoundError("Revenue record not found")
    await _require(session, owner_user_id, record.startup_id)
    await session.delete(record)
    await session.flush()


# --- Competitors ----------------------------------------------------------


async def add_competitor(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    startup_id: uuid.UUID,
    competitor_startup_id: uuid.UUID,
    relationship_type: str | None,
    evidence: dict,
) -> StartupCompetitor:
    await _require(session, owner_user_id, startup_id)
    if competitor_startup_id == startup_id:
        raise ValidationFailedError("A startup cannot be its own competitor")
    await _require(session, owner_user_id, competitor_startup_id)
    existing = await session.scalar(
        select(StartupCompetitor).where(
            StartupCompetitor.startup_id == startup_id,
            StartupCompetitor.competitor_startup_id == competitor_startup_id,
        )
    )
    if existing is not None:
        raise ConflictError("This competitor relationship already exists")
    edge = StartupCompetitor(
        startup_id=startup_id,
        competitor_startup_id=competitor_startup_id,
        relationship_type=relationship_type,
        evidence=evidence,
    )
    session.add(edge)
    await session.flush()
    await session.refresh(edge)
    return edge


async def list_competitors(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID
) -> list[StartupCompetitor]:
    await _require(session, owner_user_id, startup_id)
    return list(
        await session.scalars(
            select(StartupCompetitor)
            .where(StartupCompetitor.startup_id == startup_id)
            .order_by(StartupCompetitor.created_at)
        )
    )


async def delete_competitor(
    session: AsyncSession, *, owner_user_id: uuid.UUID, competitor_id: uuid.UUID
) -> None:
    edge = await session.scalar(
        select(StartupCompetitor).where(StartupCompetitor.id == competitor_id)
    )
    if edge is None:
        raise NotFoundError("Competitor relationship not found")
    await _require(session, owner_user_id, edge.startup_id)
    await session.delete(edge)
    await session.flush()


# --- Research -------------------------------------------------------------


async def add_research(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID, **fields: Any
) -> StartupResearchRecord:
    startup = await _require(session, owner_user_id, startup_id)
    record = StartupResearchRecord(startup_id=startup_id, **fields)
    session.add(record)
    from app.shared.base import utcnow

    startup.last_researched_at = utcnow()
    await session.flush()
    await session.refresh(record)
    return record


async def list_research(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID
) -> list[StartupResearchRecord]:
    await _require(session, owner_user_id, startup_id)
    return list(
        await session.scalars(
            select(StartupResearchRecord)
            .where(StartupResearchRecord.startup_id == startup_id)
            .order_by(StartupResearchRecord.researched_at.desc())
        )
    )


async def delete_research(
    session: AsyncSession, *, owner_user_id: uuid.UUID, research_id: uuid.UUID
) -> None:
    record = await session.scalar(
        select(StartupResearchRecord).where(StartupResearchRecord.id == research_id)
    )
    if record is None:
        raise NotFoundError("Research record not found")
    await _require(session, owner_user_id, record.startup_id)
    await session.delete(record)
    await session.flush()


# --- Watchlists -----------------------------------------------------------


async def create_watchlist(
    session: AsyncSession, *, owner_user_id: uuid.UUID, name: str, description: str | None
) -> StartupWatchlist:
    watchlist = StartupWatchlist(owner_user_id=owner_user_id, name=name, description=description)
    session.add(watchlist)
    await session.flush()
    await session.refresh(watchlist)
    return watchlist


async def list_watchlists(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[StartupWatchlist]:
    return list(
        await session.scalars(
            select(StartupWatchlist)
            .where(StartupWatchlist.owner_user_id == owner_user_id)
            .order_by(StartupWatchlist.created_at)
        )
    )


async def get_watchlist(
    session: AsyncSession, *, owner_user_id: uuid.UUID, watchlist_id: uuid.UUID
) -> StartupWatchlist:
    watchlist = await session.scalar(
        select(StartupWatchlist).where(
            StartupWatchlist.id == watchlist_id,
            StartupWatchlist.owner_user_id == owner_user_id,
        )
    )
    if watchlist is None:
        raise NotFoundError("Watchlist not found")
    return watchlist


async def delete_watchlist(
    session: AsyncSession, *, owner_user_id: uuid.UUID, watchlist_id: uuid.UUID
) -> None:
    watchlist = await get_watchlist(session, owner_user_id=owner_user_id, watchlist_id=watchlist_id)
    await session.delete(watchlist)
    await session.flush()


async def add_watchlist_item(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    watchlist_id: uuid.UUID,
    startup_id: uuid.UUID,
) -> StartupWatchlistItem:
    await get_watchlist(session, owner_user_id=owner_user_id, watchlist_id=watchlist_id)
    await _require(session, owner_user_id, startup_id)
    existing = await session.scalar(
        select(StartupWatchlistItem).where(
            StartupWatchlistItem.watchlist_id == watchlist_id,
            StartupWatchlistItem.startup_id == startup_id,
        )
    )
    if existing is not None:
        raise ConflictError("This startup is already on the watchlist")
    item = StartupWatchlistItem(watchlist_id=watchlist_id, startup_id=startup_id)
    session.add(item)
    await session.flush()
    return item


async def remove_watchlist_item(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    watchlist_id: uuid.UUID,
    startup_id: uuid.UUID,
) -> None:
    await get_watchlist(session, owner_user_id=owner_user_id, watchlist_id=watchlist_id)
    await session.execute(
        delete(StartupWatchlistItem).where(
            StartupWatchlistItem.watchlist_id == watchlist_id,
            StartupWatchlistItem.startup_id == startup_id,
        )
    )
    await session.flush()


async def watchlist_names_for_startup(
    session: AsyncSession, *, owner_user_id: uuid.UUID, startup_id: uuid.UUID
) -> list[str]:
    rows = await session.execute(
        select(StartupWatchlist.name)
        .join(StartupWatchlistItem, StartupWatchlistItem.watchlist_id == StartupWatchlist.id)
        .where(
            StartupWatchlist.owner_user_id == owner_user_id,
            StartupWatchlistItem.startup_id == startup_id,
        )
        .order_by(StartupWatchlist.name)
    )
    return list(rows.scalars())


async def startups_in_watchlist(
    session: AsyncSession, *, owner_user_id: uuid.UUID, watchlist_id: uuid.UUID
) -> list[Startup]:
    await get_watchlist(session, owner_user_id=owner_user_id, watchlist_id=watchlist_id)
    return list(
        await session.scalars(
            select(Startup)
            .join(StartupWatchlistItem, StartupWatchlistItem.startup_id == Startup.id)
            .where(
                StartupWatchlistItem.watchlist_id == watchlist_id,
                Startup.owner_user_id == owner_user_id,
                Startup.deleted_at.is_(None),
            )
            .order_by(StartupWatchlistItem.added_at.desc())
        )
    )
