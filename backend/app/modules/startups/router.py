from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.startups import service
from app.modules.startups.schemas import (
    CompetitorCreateIn,
    CompetitorOut,
    FounderCreateIn,
    FounderOut,
    PricingCreateIn,
    PricingOut,
    ProductCreateIn,
    ProductOut,
    ResearchCreateIn,
    ResearchOut,
    RevenueCreateIn,
    RevenueOut,
    StartupCreateIn,
    StartupDetailOut,
    StartupListOut,
    StartupOut,
    StartupUpdateIn,
    WatchlistCreateIn,
    WatchlistItemIn,
    WatchlistOut,
)

router = APIRouter(prefix="/startups", tags=["startups"])

Csrf = Depends(require_csrf_for_state_changes())


def _detail_out(
    startup: StartupOut,
    founders: list[FounderOut],
    products: list[ProductOut],
    revenue: list[RevenueOut],
    competitors: list[CompetitorOut],
    research: list[ResearchOut],
    watchlists: list[str],
) -> StartupDetailOut:
    return StartupDetailOut(
        **startup.model_dump(),
        founders=founders,
        products=products,
        revenue=revenue,
        competitors=competitors,
        research=research,
        watchlists=watchlists,
    )


@router.get("", response_model=StartupListOut)
async def list_startups(
    session: AsyncSessionDep,
    user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
    industry: str | None = Query(default=None, max_length=150),
    country: str | None = Query(default=None, max_length=100),
    funding_stage: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=50),
    watchlist_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> StartupListOut:
    rows, total = await service.list_startups(
        session,
        owner_user_id=user.id,
        query=query,
        industry=industry,
        country=country,
        funding_stage=funding_stage,
        status=status,
        watchlist_id=watchlist_id,
        limit=limit,
        offset=offset,
    )
    return StartupListOut(
        items=[StartupOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StartupOut, status_code=201, dependencies=[Csrf])
async def create_startup(
    request: Request,
    payload: StartupCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> StartupOut:
    try:
        row = await service.create_startup(
            session,
            owner_user_id=user.id,
            name=payload.name,
            website_url=payload.website_url,
            description=payload.description,
            industry=payload.industry,
            country=payload.country,
            city=payload.city,
            founding_date=payload.founding_date,
            launch_date=payload.launch_date,
            funding_stage=payload.funding_stage,
            status=payload.status,
            source_slug=payload.source_slug,
            source_url=payload.source_url,
        )
    except Exception:
        await session.rollback()
        raise
    await record_audit(
        session,
        action="startup.create",
        owner_user_id=user.id,
        entity_type="startup",
        entity_id=row.id,
        ip_address=client_ip(request),
        metadata={"name": row.name, "source_slug": row.source_slug},
    )
    return StartupOut.model_validate(row)


@router.get("/watchlists", response_model=list[WatchlistOut])
async def list_watchlists(session: AsyncSessionDep, user: CurrentUser) -> list[WatchlistOut]:
    watchlists = await service.list_watchlists(session, owner_user_id=user.id)
    out: list[WatchlistOut] = []
    for watchlist in watchlists:
        items = await service.startups_in_watchlist(
            session, owner_user_id=user.id, watchlist_id=watchlist.id
        )
        out.append(
            WatchlistOut(
                **WatchlistOut.model_validate(watchlist).model_dump(exclude={"items"}),
                items=[StartupOut.model_validate(item) for item in items],
            )
        )
    return out


@router.post("/watchlists", response_model=WatchlistOut, status_code=201, dependencies=[Csrf])
async def create_watchlist(
    request: Request,
    payload: WatchlistCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> WatchlistOut:
    row = await service.create_watchlist(
        session, owner_user_id=user.id, name=payload.name, description=payload.description
    )
    await record_audit(
        session,
        action="startup.watchlist_create",
        owner_user_id=user.id,
        entity_type="startup_watchlist",
        entity_id=row.id,
        ip_address=client_ip(request),
        metadata={"name": row.name},
    )
    return WatchlistOut(**WatchlistOut.model_validate(row).model_dump(exclude={"items"}), items=[])


@router.delete(
    "/watchlists/{watchlist_id}",
    response_model=dict,
    status_code=200,
    dependencies=[Csrf],
)
async def delete_watchlist(
    watchlist_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_watchlist(session, owner_user_id=user.id, watchlist_id=watchlist_id)
    return {"id": str(watchlist_id), "message": "Deleted"}


@router.post(
    "/watchlists/{watchlist_id}/items",
    response_model=dict,
    status_code=201,
    dependencies=[Csrf],
)
async def add_watchlist_item(
    watchlist_id: uuid.UUID,
    payload: WatchlistItemIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.add_watchlist_item(
        session,
        owner_user_id=user.id,
        watchlist_id=watchlist_id,
        startup_id=payload.startup_id,
    )
    return {"watchlist_id": str(watchlist_id), "startup_id": str(payload.startup_id)}


@router.delete(
    "/watchlists/{watchlist_id}/items/{startup_id}",
    response_model=dict,
    status_code=200,
    dependencies=[Csrf],
)
async def remove_watchlist_item(
    watchlist_id: uuid.UUID,
    startup_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.remove_watchlist_item(
        session, owner_user_id=user.id, watchlist_id=watchlist_id, startup_id=startup_id
    )
    return {"watchlist_id": str(watchlist_id), "startup_id": str(startup_id), "message": "Removed"}


@router.get("/{startup_id}", response_model=StartupDetailOut)
async def startup_detail(
    startup_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> StartupDetailOut:
    row = await service._get(session, user.id, startup_id)
    if row is None:
        raise NotFoundError("Startup not found")
    founders = await service.list_founders(session, owner_user_id=user.id, startup_id=startup_id)
    products = await service.list_products(session, owner_user_id=user.id, startup_id=startup_id)
    revenue = await service.list_revenue(session, owner_user_id=user.id, startup_id=startup_id)
    competitors = await service.list_competitors(
        session, owner_user_id=user.id, startup_id=startup_id
    )
    research = await service.list_research(session, owner_user_id=user.id, startup_id=startup_id)
    watchlists = await service.watchlist_names_for_startup(
        session, owner_user_id=user.id, startup_id=startup_id
    )
    return _detail_out(
        StartupOut.model_validate(row),
        [FounderOut.model_validate(f) for f in founders],
        [ProductOut.model_validate(p) for p in products],
        [RevenueOut.model_validate(r) for r in revenue],
        [CompetitorOut.model_validate(c) for c in competitors],
        [ResearchOut.model_validate(r) for r in research],
        watchlists,
    )


@router.patch("/{startup_id}", response_model=StartupOut, dependencies=[Csrf])
async def update_startup(
    startup_id: uuid.UUID,
    payload: StartupUpdateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> StartupOut:
    row = await service.update_startup(
        session,
        owner_user_id=user.id,
        startup_id=startup_id,
        **payload.model_dump(exclude_unset=True),
    )
    return StartupOut.model_validate(row)


@router.delete("/{startup_id}", response_model=dict, status_code=200, dependencies=[Csrf])
async def delete_startup(
    startup_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.soft_delete_startup(session, owner_user_id=user.id, startup_id=startup_id)
    await record_audit(
        session,
        action="startup.delete",
        owner_user_id=user.id,
        entity_type="startup",
        entity_id=startup_id,
    )
    return {"id": str(startup_id), "message": "Deleted"}


# --- Founders -------------------------------------------------------------


@router.post(
    "/{startup_id}/founders", response_model=FounderOut, status_code=201, dependencies=[Csrf]
)
async def add_founder(
    startup_id: uuid.UUID,
    payload: FounderCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> FounderOut:
    row = await service.add_founder(
        session,
        owner_user_id=user.id,
        startup_id=startup_id,
        name=payload.name,
        role=payload.role,
        public_profile_url=payload.public_profile_url,
    )
    return FounderOut.model_validate(row)


@router.delete(
    "/{startup_id}/founders/{founder_id}",
    response_model=dict,
    status_code=200,
    dependencies=[Csrf],
)
async def delete_founder(
    startup_id: uuid.UUID,
    founder_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_founder(session, owner_user_id=user.id, founder_id=founder_id)
    return {"id": str(founder_id), "message": "Deleted"}


# --- Products -------------------------------------------------------------


@router.post(
    "/{startup_id}/products", response_model=ProductOut, status_code=201, dependencies=[Csrf]
)
async def add_product(
    startup_id: uuid.UUID,
    payload: ProductCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> ProductOut:
    row = await service.add_product(
        session,
        owner_user_id=user.id,
        startup_id=startup_id,
        name=payload.name,
        description=payload.description,
        product_url=payload.product_url,
        category=payload.category,
        launch_date=payload.launch_date,
    )
    return ProductOut.model_validate(row)


@router.delete(
    "/{startup_id}/products/{product_id}",
    response_model=dict,
    status_code=200,
    dependencies=[Csrf],
)
async def delete_product(
    startup_id: uuid.UUID,
    product_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_product(session, owner_user_id=user.id, product_id=product_id)
    return {"id": str(product_id), "message": "Deleted"}


@router.post(
    "/{startup_id}/products/{product_id}/pricing",
    response_model=PricingOut,
    status_code=201,
    dependencies=[Csrf],
)
async def add_pricing(
    startup_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: PricingCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> PricingOut:
    row = await service.add_pricing(
        session,
        owner_user_id=user.id,
        product_id=product_id,
        plan_name=payload.plan_name,
        amount=payload.amount,
        currency=payload.currency,
        billing_period=payload.billing_period,
        pricing_url=payload.pricing_url,
    )
    return PricingOut.model_validate(row)


# --- Revenue --------------------------------------------------------------


@router.post(
    "/{startup_id}/revenue", response_model=RevenueOut, status_code=201, dependencies=[Csrf]
)
async def add_revenue(
    startup_id: uuid.UUID,
    payload: RevenueCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> RevenueOut:
    row = await service.add_revenue(
        session,
        owner_user_id=user.id,
        startup_id=startup_id,
        classification=payload.classification,
        amount=payload.amount,
        methodology=payload.methodology,
        currency=payload.currency,
        revenue_period=payload.revenue_period,
        assumptions=payload.assumptions,
        confidence=payload.confidence,
        source_url=payload.source_url,
        reported_at=payload.reported_at,
    )
    return RevenueOut.model_validate(row)


@router.delete(
    "/{startup_id}/revenue/{revenue_id}",
    response_model=dict,
    status_code=200,
    dependencies=[Csrf],
)
async def delete_revenue(
    startup_id: uuid.UUID,
    revenue_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_revenue(session, owner_user_id=user.id, revenue_id=revenue_id)
    return {"id": str(revenue_id), "message": "Deleted"}


# --- Competitors ----------------------------------------------------------


@router.post(
    "/{startup_id}/competitors",
    response_model=CompetitorOut,
    status_code=201,
    dependencies=[Csrf],
)
async def add_competitor(
    startup_id: uuid.UUID,
    payload: CompetitorCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> CompetitorOut:
    row = await service.add_competitor(
        session,
        owner_user_id=user.id,
        startup_id=startup_id,
        competitor_startup_id=payload.competitor_startup_id,
        relationship_type=payload.relationship_type,
        evidence=payload.evidence,
    )
    return CompetitorOut.model_validate(row)


@router.delete(
    "/{startup_id}/competitors/{competitor_id}",
    response_model=dict,
    status_code=200,
    dependencies=[Csrf],
)
async def delete_competitor(
    startup_id: uuid.UUID,
    competitor_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_competitor(session, owner_user_id=user.id, competitor_id=competitor_id)
    return {"id": str(competitor_id), "message": "Deleted"}


# --- Research -------------------------------------------------------------


@router.post(
    "/{startup_id}/research", response_model=ResearchOut, status_code=201, dependencies=[Csrf]
)
async def add_research(
    startup_id: uuid.UUID,
    payload: ResearchCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> ResearchOut:
    row = await service.add_research(
        session,
        owner_user_id=user.id,
        startup_id=startup_id,
        research_type=payload.research_type,
        summary=payload.summary,
        findings=payload.findings,
        source_references=payload.source_references,
    )
    return ResearchOut.model_validate(row)


@router.delete(
    "/{startup_id}/research/{research_id}",
    response_model=dict,
    status_code=200,
    dependencies=[Csrf],
)
async def delete_research(
    startup_id: uuid.UUID,
    research_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> dict:
    await service.delete_research(session, owner_user_id=user.id, research_id=research_id)
    return {"id": str(research_id), "message": "Deleted"}
