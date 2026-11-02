from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.businesses import repository
from app.modules.businesses.schemas import (
    ActionOut,
    BusinessDetail,
    BusinessListOut,
    BusinessOut,
    ContactOut,
)
from app.modules.crm.service import ensure_default_pipeline, stage_by_name
from app.modules.exports.csv_export import to_csv

router = APIRouter(prefix="/businesses", tags=["businesses"])

Csrf = Depends(require_csrf_for_state_changes())


@router.get("", response_model=BusinessListOut)
async def list_businesses(
    session: AsyncSessionDep,
    user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
    city: str | None = Query(default=None, max_length=150),
    country: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=150),
    website_status: str | None = Query(default=None, max_length=30),
    shortlisted_only: bool = Query(default=False),
    sort: str = Query(default="first_discovered_at"),
    descending: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> BusinessListOut:
    """The results table. Scoped to the caller's own records by the repository."""
    filters = repository.BusinessFilters(
        query=query,
        city=city,
        country=country,
        category=category,
        website_status=website_status,
        shortlisted_only=shortlisted_only,
        sort=sort,
        descending=descending,
        limit=limit,
        offset=offset,
    )
    rows, total = await repository.list_businesses(session, user.id, filters)
    return BusinessListOut(
        items=[BusinessOut.model_validate(row) for row in rows],
        total=total,
        limit=filters.normalized().limit,
        offset=filters.normalized().offset,
    )


@router.get("/export", response_class=Response)
async def export_csv(
    request: Request,
    session: AsyncSessionDep,
    user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
    city: str | None = Query(default=None, max_length=150),
    country: str | None = Query(default=None, max_length=100),
    website_status: str | None = Query(default=None, max_length=30),
) -> Response:
    """CSV download of the current filter.

    A GET, not a POST: it changes nothing, and making it unsafe would demand a
    CSRF token for an action that cannot harm anyone.
    """
    filters = repository.BusinessFilters(
        query=query, city=city, country=country, website_status=website_status
    )
    rows = await repository.export_rows(session, user.id, filters)
    await record_audit(
        session,
        action="export.create",
        owner_user_id=user.id,
        entity_type="export_job",
        ip_address=client_ip(request),
        metadata={"format": "csv", "record_count": len(rows)},
    )
    body = to_csv(rows)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sparkxflow-leads.csv"'},
    )


@router.get("/{business_id}", response_model=BusinessDetail)
async def business_detail(
    business_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> BusinessDetail:
    business = await repository.get_business(session, user.id, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    contacts = await repository.contacts_for(session, user.id, business_id)
    stage = await repository.stage_name(session, user.id, business_id)
    provenance = await repository.provenance_map(session, user.id, [business_id])
    slugs, urls = provenance.get(business_id, ([], []))
    return BusinessDetail(
        **BusinessOut.model_validate(business).model_dump(),
        contacts=[ContactOut.model_validate(contact) for contact in contacts],
        crm_stage=stage,
        source_slugs=slugs,
        source_urls=urls,
        signals=dict((business.enrichment or {}).get("signals", {})),
    )


@router.post("/{business_id}/shortlist", response_model=ActionOut, dependencies=[Csrf])
async def shortlist(
    business_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ActionOut:
    try:
        await repository.shortlist(session, owner_user_id=user.id, business_id=business_id)
    except LookupError as exc:
        raise NotFoundError("Business not found") from exc
    await record_audit(
        session,
        action="business.shortlist",
        owner_user_id=user.id,
        entity_type="business",
        entity_id=business_id,
    )
    stage = await repository.stage_name(session, user.id, business_id)
    return ActionOut(id=business_id, message="Shortlisted", crm_stage=stage)


@router.post("/{business_id}/archive", response_model=ActionOut, dependencies=[Csrf])
async def archive(business_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser) -> ActionOut:
    try:
        await repository.archive(session, owner_user_id=user.id, business_id=business_id)
    except LookupError as exc:
        raise NotFoundError("Business not found") from exc
    await record_audit(
        session,
        action="business.archive",
        owner_user_id=user.id,
        entity_type="business",
        entity_id=business_id,
    )
    return ActionOut(id=business_id, message="Archived", crm_stage="Archived")


@router.delete(
    "/{business_id}", response_model=ActionOut, status_code=status.HTTP_200_OK, dependencies=[Csrf]
)
async def delete_business(
    business_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ActionOut:
    """Soft delete. Outreach history and provenance survive a removal today so
    they can be produced later; hard deletion belongs to the retention worker."""
    try:
        await repository.soft_delete(session, owner_user_id=user.id, business_id=business_id)
    except LookupError as exc:
        raise NotFoundError("Business not found") from exc
    await record_audit(
        session,
        action="business.delete",
        owner_user_id=user.id,
        entity_type="business",
        entity_id=business_id,
    )
    return ActionOut(id=business_id, message="Deleted", crm_stage=None)


@router.get("/{business_id}/stage", response_model=ActionOut)
async def current_stage(
    business_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ActionOut:
    business = await repository.get_business(session, user.id, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    stage = await repository.stage_name(session, user.id, business_id)
    return ActionOut(id=business_id, message="ok", crm_stage=stage)


@router.post("/{business_id}/stage/{stage_name}", response_model=ActionOut, dependencies=[Csrf])
async def change_stage(
    business_id: uuid.UUID,
    stage_name: str,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> ActionOut:
    business = await repository.get_business(session, user.id, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    from app.modules.crm.service import move_stage

    pipeline = await ensure_default_pipeline(session, user.id)
    if await stage_by_name(session, pipeline.id, stage_name) is None:
        raise NotFoundError(f"Unknown stage '{stage_name}'")
    await move_stage(session, owner_user_id=user.id, business_id=business_id, stage_name=stage_name)
    await record_audit(
        session,
        action="crm.stage_change",
        owner_user_id=user.id,
        entity_type="business",
        entity_id=business_id,
        metadata={"stage": stage_name},
    )
    return ActionOut(id=business_id, message=f"Moved to {stage_name}", crm_stage=stage_name)
