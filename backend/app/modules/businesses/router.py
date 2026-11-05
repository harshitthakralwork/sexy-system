from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.businesses import repository
from app.modules.businesses.schemas import (
    ActionOut,
    BulkDeleteIn,
    BulkDeleteOut,
    BusinessDetail,
    BusinessListOut,
    BusinessOut,
    ContactOut,
    NoteCreateIn,
    NoteOut,
    PinOut,
    SelectedExportIn,
    TagAssignIn,
    TagOut,
    ViewportOut,
)
from app.modules.crm.service import ensure_default_pipeline, stage_by_name
from app.modules.exports.csv_export import to_csv
from app.shared.geo import BoundingBox, GeometryError

router = APIRouter(prefix="/businesses", tags=["businesses"])

Csrf = Depends(require_csrf_for_state_changes())

MAX_SELECTED_EXPORT = 500


def _parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse and validate `west,south,east,north`.

    An unusable box raises rather than degrades: if the ordering were wrong and the
    filter simply dropped, the response would be every located record the user owns —
    an unbounded read dressed up as a viewport.
    """
    if not value:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        raise ValidationFailedError(
            "A bounding box is west,south,east,north in decimal degrees",
            details={"example": "77.5,28.5,77.7,28.7"},
        )
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError:
        raise ValidationFailedError(
            "A bounding box must be four decimal numbers", details={"value": value}
        ) from None
    try:
        BoundingBox(west=west, south=south, east=east, north=north)
    except GeometryError as exc:
        raise ValidationFailedError(exc.message, details={"field": exc.field}) from exc
    return (west, south, east, north)


@router.get("", response_model=BusinessListOut)
async def list_businesses(
    session: AsyncSessionDep,
    user: CurrentUser,
    query: str | None = Query(default=None, max_length=200),
    city: str | None = Query(default=None, max_length=150),
    country: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=150),
    website_status: str | None = Query(default=None, max_length=30),
    has_phone: bool | None = Query(default=None),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    min_reviews: int | None = Query(default=None, ge=0),
    job_id: uuid.UUID | None = Query(default=None),
    bbox: str | None = Query(default=None, max_length=64, description="west,south,east,north"),
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
        has_phone=has_phone,
        min_rating=min_rating,
        min_reviews=min_reviews,
        job_id=job_id,
        bbox=_parse_bbox(bbox),
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


@router.get("/viewport", response_model=ViewportOut)
async def viewport_pins(
    session: AsyncSessionDep,
    user: CurrentUser,
    bbox: str = Query(description="west,south,east,north in decimal degrees"),
    category: str | None = Query(default=None, max_length=150),
    website_status: str | None = Query(default=None, max_length=30),
    has_phone: bool | None = Query(default=None),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    min_reviews: int | None = Query(default=None, ge=0),
    job_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> ViewportOut:
    """Pins for the visible map area, plus the honest count of what is in it.

    Bounded on purpose. The response says how many records match and how many were
    sent, so a dense district is visibly a partial render rather than a smaller
    market. Records without coordinates are excluded here and still counted in the
    table, because the map cannot draw what the source never located.
    """
    bounds = _parse_bbox(bbox)
    if bounds is None:
        raise ValidationFailedError(
            "A viewport needs a bounding box as west,south,east,north",
            details={"example": "77.5,-85.3,77.7,28.7"},
        )
    filters = repository.BusinessFilters(
        bbox=bounds,
        category=category,
        website_status=website_status,
        has_phone=has_phone,
        min_rating=min_rating,
        min_reviews=min_reviews,
        job_id=job_id,
        limit=limit,
    )
    pins, total = await repository.list_pins(session, user.id, filters)
    return ViewportOut(
        items=[PinOut(**pin) for pin in pins],
        total_in_viewport=total,
        returned=len(pins),
        truncated=total > len(pins),
        bbox=list(bounds),
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


@router.post("/export/selected", response_class=Response)
async def export_selected(
    request: Request,
    payload: SelectedExportIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    _csrf: None = Csrf,
) -> Response:
    """CSV of exactly the records selected, whether picked on the map or in the table.

    Ids that are not the caller's are not exported and are reported as skipped. The
    response still downloads — a partial selection is useful — but the count is also
    logged, because a silent shortfall is how a lead list starts lying about itself.
    """
    rows, skipped = await repository.export_rows_by_ids(session, user.id, payload.ids)
    await record_audit(
        session,
        action="export.create",
        owner_user_id=user.id,
        entity_type="export_job",
        ip_address=client_ip(request),
        metadata={"format": "csv", "record_count": len(rows), "requested": len(payload.ids)},
    )
    body = to_csv(rows)
    headers = {
        "Content-Disposition": 'attachment; filename="sparkxflow-selection.csv"',
        "X-Exported-Records": str(len(rows)),
        "X-Export-Skipped": str(skipped),
    }
    return Response(content=body, media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/tags", response_model=list[TagOut])
async def list_tags(session: AsyncSessionDep, user: CurrentUser) -> list[TagOut]:
    tags = await repository.all_tags(session, user.id)
    return [TagOut.model_validate(tag) for tag in tags]


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


@router.post("/bulk-delete", response_model=BulkDeleteOut, dependencies=[Csrf])
@router.delete("/bulk-delete", response_model=BulkDeleteOut, dependencies=[Csrf])
@router.delete("", response_model=BulkDeleteOut, dependencies=[Csrf])
async def bulk_delete_businesses(
    payload: BulkDeleteIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> BulkDeleteOut:
    if payload.delete_all == bool(payload.ids):
        raise ValidationFailedError("Choose either selected business ids or delete_all")
    deleted = await repository.soft_delete_many(
        session,
        owner_user_id=user.id,
        business_ids=None if payload.delete_all else payload.ids,
    )
    await record_audit(
        session,
        action="business.bulk_update",
        owner_user_id=user.id,
        entity_type="business",
        metadata={"operation": "soft_delete", "deleted": deleted},
    )
    return BulkDeleteOut(deleted=deleted)


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


@router.get("/{business_id}/notes", response_model=list[NoteOut])
async def list_notes(
    business_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> list[NoteOut]:
    try:
        notes = await repository.list_notes(session, user.id, business_id)
    except LookupError as exc:
        raise NotFoundError("Business not found") from exc
    return [NoteOut.model_validate(note) for note in notes]


@router.post("/{business_id}/notes", response_model=NoteOut, status_code=201, dependencies=[Csrf])
async def create_note(
    business_id: uuid.UUID,
    payload: NoteCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> NoteOut:
    try:
        note = await repository.create_note(
            session, owner_user_id=user.id, business_id=business_id, content=payload.content
        )
    except LookupError as exc:
        raise NotFoundError("Business not found") from exc
    return NoteOut.model_validate(note)


@router.get("/{business_id}/tags", response_model=list[TagOut])
async def list_business_tags(
    business_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> list[TagOut]:
    try:
        tags = await repository.tags_on_business(session, user.id, business_id)
    except LookupError as exc:
        raise NotFoundError("Business not found") from exc
    return [TagOut.model_validate(tag) for tag in tags]


@router.put("/{business_id}/tags", response_model=list[TagOut], dependencies=[Csrf])
async def set_tags(
    business_id: uuid.UUID,
    payload: TagAssignIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> list[TagOut]:
    try:
        tags = await repository.set_tags(
            session, owner_user_id=user.id, business_id=business_id, names=payload.names
        )
    except LookupError as exc:
        raise NotFoundError("Business not found") from exc
    return [TagOut.model_validate(tag) for tag in tags]
