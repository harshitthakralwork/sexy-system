"""Saved search areas: validate the shape, store it once, hand it back to jobs.

An area is the *where* of a discovery request, kept separate from the request so it
can be re-run, renamed and compared over time. Everything that decides how much
work a shape implies — the ceiling check, the tile plan — is derived from the stored
geometry rather than trusted from the browser.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.discovery.models import SearchArea
from app.modules.discovery.schemas import AreaGeometryIn, DiscoveryJobIn, SearchAreaIn
from app.shared.geo import Area, BoundingBox, GeometryError


def build_area(geometry: AreaGeometryIn, *, max_area_km2: float) -> Area:
    """Turn a request shape into a validated Area, or explain why it is not usable."""
    try:
        area = geometry.to_area()
    except GeometryError as exc:
        raise ValidationFailedError(exc.message, details={"field": exc.field}) from exc
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc

    if not area.within_ceiling(max_area_km2):
        raise ValidationFailedError(
            f"That area is {area.area_km2:,.1f} km², above the "
            f"{max_area_km2:,.1f} km² limit for one job. Draw a smaller shape or work "
            "it district by district — the area is not shrunk for you, because a "
            "partial search that reports itself as complete would mislead you about "
            "the market.",
            details={
                "area_km2": round(area.area_km2, 2),
                "limit_km2": max_area_km2,
            },
        )
    return area


def _row_from_area(area: Area) -> dict[str, Any]:
    west, south, east, north = area.bbox.as_tuple()
    return {
        "shape_type": area.shape_type,
        "center_latitude": area.latitude,
        "center_longitude": area.longitude,
        "radius_m": area.radius_m,
        "bbox_west": west,
        "bbox_south": south,
        "bbox_east": east,
        "bbox_north": north,
        "polygon": [list(vertex) for vertex in area.polygon] if area.polygon else None,
        "area_km2": round(area.area_km2, 4),
    }


def area_from_row(row: SearchArea) -> Area:
    """Rebuild the geometry a job should run against, exactly as saved.

    The stored bounding box and polygon are authoritative; recomputing them from a
    name or a stale label would let a saved area quietly mean different ground.
    """
    bbox = BoundingBox(
        west=float(row.bbox_west),
        south=float(row.bbox_south),
        east=float(row.bbox_east),
        north=float(row.bbox_north),
    )
    polygon = None
    if row.shape_type == "polygon" and row.polygon:
        polygon = tuple((float(vertex[0]), float(vertex[1])) for vertex in row.polygon)
    return Area(
        shape_type=row.shape_type,
        bbox=bbox,
        area_km2=float(row.area_km2),
        latitude=float(row.center_latitude) if row.center_latitude is not None else None,
        longitude=float(row.center_longitude) if row.center_longitude is not None else None,
        radius_m=row.radius_m,
        polygon=polygon,
    )


async def create_area(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    payload: SearchAreaIn,
    settings: Settings | None = None,
) -> SearchArea:
    active = settings or get_settings()
    area = build_area(payload.geometry, max_area_km2=active.discovery_max_area_km2)
    admin = payload.geometry.admin
    row = SearchArea(
        owner_user_id=owner_user_id,
        module=payload.module,
        name=payload.name.strip(),
        categories=payload.categories,
        geocode=None,
        **_row_from_area(area),
        admin_country=admin.country if admin else None,
        admin_state=admin.state if admin else None,
        admin_city=admin.city if admin else None,
        admin_locality=admin.locality if admin else None,
    )
    session.add(row)
    await session.flush()
    return row


async def get_area(
    session: AsyncSession, area_id: uuid.UUID, owner_user_id: uuid.UUID
) -> SearchArea:
    """Owner-scoped read. Someone else's area is not found, not forbidden."""
    row = await session.scalar(
        select(SearchArea).where(
            SearchArea.id == area_id,
            SearchArea.owner_user_id == owner_user_id,
            SearchArea.deleted_at.is_(None),
        )
    )
    if row is None:
        raise NotFoundError("Search area not found", details={"area_id": str(area_id)})
    return row


async def list_areas(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[SearchArea], int]:
    total = await session.scalar(
        select(func.count()).select_from(SearchArea).where(
            SearchArea.owner_user_id == owner_user_id, SearchArea.deleted_at.is_(None)
        )
    )
    rows = (
        await session.scalars(
            select(SearchArea)
            .where(SearchArea.owner_user_id == owner_user_id, SearchArea.deleted_at.is_(None))
            .order_by(SearchArea.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), int(total or 0)


async def update_area(
    session: AsyncSession,
    area_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: SearchAreaIn,
    *,
    settings: Settings | None = None,
) -> SearchArea:
    active = settings or get_settings()
    row = await get_area(session, area_id, owner_user_id)
    area = build_area(payload.geometry, max_area_km2=active.discovery_max_area_km2)
    admin = payload.geometry.admin
    for field, value in _row_from_area(area).items():
        setattr(row, field, value)
    row.name = payload.name.strip()
    row.module = payload.module
    row.categories = payload.categories
    row.admin_country = admin.country if admin else None
    row.admin_state = admin.state if admin else None
    row.admin_city = admin.city if admin else None
    row.admin_locality = admin.locality if admin else None
    await session.flush()
    return row


async def delete_area(
    session: AsyncSession, area_id: uuid.UUID, owner_user_id: uuid.UUID
) -> SearchArea:
    """Soft delete. Past searches referenced this area; their history stays readable."""
    row = await get_area(session, area_id, owner_user_id)
    row.deleted_at = datetime.now(UTC)
    await session.flush()
    return row


async def mark_run(session: AsyncSession, area_id: uuid.UUID | None) -> None:
    if area_id is None:
        return
    row = await session.get(SearchArea, area_id)
    if row is not None:
        row.last_run_at = datetime.now(UTC)


async def resolve_area_for_job(
    session: AsyncSession, request: DiscoveryJobIn, owner_user_id: uuid.UUID
) -> Area | None:
    """The geometry a job will search, from an ad-hoc shape or a saved area.

    Both paths end up validated against the same ceiling. A saved area is re-read
    rather than re-measured, because a ceiling lowered later must not silently
    permit an old oversized area to run — it must refuse and say so.
    """
    active = get_settings()
    if request.geometry is not None:
        return build_area(request.geometry, max_area_km2=active.discovery_max_area_km2)
    if request.area_id is not None:
        row = await get_area(session, request.area_id, owner_user_id)
        area = area_from_row(row)
        if not area.within_ceiling(active.discovery_max_area_km2):
            raise ValidationFailedError(
                f"Saved area '{row.name}' is {area.area_km2:,.1f} km², above the current "
                f"{active.discovery_max_area_km2:,.1f} km² limit. Draw a smaller area.",
                details={"area_id": str(row.id), "area_km2": round(area.area_km2, 2)},
            )
        return area
    return None


def describe_area(area: Area) -> dict[str, Any]:
    """A compact, honest summary for job reports and logs."""
    west, south, east, north = area.bbox.as_tuple()
    return {
        "shape_type": area.shape_type,
        "area_km2": round(area.area_km2, 3),
        "bbox": [round(west, 7), round(south, 7), round(east, 7), round(north, 7)],
        "radius_m": area.radius_m,
        "vertices": len(area.polygon) if area.polygon else 0,
    }
