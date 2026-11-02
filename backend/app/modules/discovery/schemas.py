from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.discovery.adapters.base import DiscoveryQuery, LocationSpec
from app.shared.geo import (
    Area,
    Circle,
    Polygon,
    Rectangle,
    area_from_payload,
    area_to_payload,
)

MAX_KEYWORDS = 10
MAX_KEYWORD_LENGTH = 100
# Overpass tag keys and values are interpolated into the QL string, so both halves
# of a `key=value` category are held to the same alphabet the adapter enforces —
# anything else is rejected rather than escaped. OSM stores a cafe as
# `amenity=cafe`, so the value half is what makes a category searchable at all.
CATEGORY_PATTERN = r"^[A-Za-z0-9:_-]{1,40}(=[A-Za-z0-9:_-]{1,40})?$"


class DiscoveryJobIn(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)
    category: str | None = Field(default=None, pattern=CATEGORY_PATTERN)
    geometry: AreaGeometryIn | None = None
    area_id: uuid.UUID | None = None
    country: str = Field(default="IN", pattern=r"^[A-Za-z]{2}$")
    max_results: int = Field(default=50, ge=1, le=500)
    sources: list[str] | None = Field(default=None, max_length=5)

    @field_validator("keywords")
    @classmethod
    def _clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip()[:MAX_KEYWORD_LENGTH] for item in value if item.strip()]
        if len(cleaned) != len(value):
            raise ValueError("keywords must be non-empty and free of padding only")
        return cleaned

    @model_validator(mode="after")
    def _something_to_search_for(self) -> DiscoveryJobIn:
        if not self.keywords and self.category is None:
            raise ValueError("a discovery query needs keywords, a category or a location")
        # Two ways of saying "where" would make the job ambiguous about which one
        # it actually ran, and the answer must be re-readable from the stored row.
        if self.geometry is not None and self.area_id is not None:
            raise ValueError("provide either an ad-hoc geometry or a saved area, not both")
        return self

    def to_location(self, area: Area | None) -> LocationSpec | None:
        if area is None:
            return None
        if area.shape_type == "circle" and area.latitude is not None:
            return LocationSpec(
                center=(area.latitude, area.longitude or 0.0),
                radius_km=area.radius_m / 1000 if area.radius_m else None,
            )
        west, south, east, north = area.bbox.as_tuple()
        return LocationSpec(query_bbox=(west, south, east, north))

    def to_query(self, area: Area | None) -> DiscoveryQuery:
        return DiscoveryQuery(
            keywords=tuple(self.keywords),
            category=self.category,
            location=self.to_location(area),
            country=self.country.upper(),
            max_results=self.max_results,
        )

    def to_config(self, area: Area | None) -> dict[str, Any]:
        """JSON-safe form of the request, stored on the `searches` row.

        The resolved geometry is stored alongside the request that produced it, so
        a job re-read next month asks about the same ground even if the saved area
        is edited or deleted in the meantime — and asks it in the same shape.
        """
        config = self.model_dump(mode="json", exclude={"geometry", "area_id"})
        config["geometry"] = self.geometry.model_dump(mode="json") if self.geometry else None
        config["area_id"] = str(self.area_id) if self.area_id else None
        config["resolved_area"] = area_to_payload(area) if area else None
        return config


def query_from_config(config: dict[str, Any]) -> tuple[DiscoveryJobIn, Area | None]:
    """Rebuild the validated request and its geometry from stored config.

    Going through the request model rather than reading the JSON directly means
    a hand-edited or legacy row cannot smuggle past the same bounds a live API
    caller is held to.
    """
    request = DiscoveryJobIn.model_validate(config)
    return request, area_from_payload(config.get("resolved_area"))


class AdminScopeIn(BaseModel):
    """Administrative labels carried alongside a shape for display and re-runs.

    These do not define the search area on their own: a place name is not geometry,
    and resolving one needs a geocoder, which is not wired yet. They arrive with a
    bounding box the user or the map actually selected.
    """

    country: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=150)
    locality: str | None = Field(default=None, max_length=150)


class AreaGeometryIn(BaseModel):
    """The shape a search should run over, in whichever form the user produced it."""

    shape_type: Literal["circle", "rectangle", "polygon", "administrative"]
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=50)
    rectangle: tuple[float, float, float, float] | None = None
    polygon: list[tuple[float, float]] | None = Field(default=None, max_length=200)
    bbox: tuple[float, float, float, float] | None = None
    admin: AdminScopeIn | None = None

    def to_area(self) -> Area:
        if self.shape_type == "circle":
            if self.latitude is None or self.longitude is None or self.radius_km is None:
                raise ValueError("a circle needs latitude, longitude and radius_km")
            return Area.from_circle(Circle(self.latitude, self.longitude, self.radius_km))
        if self.shape_type == "rectangle":
            if self.rectangle is None:
                raise ValueError("a rectangle needs west, south, east and north")
            west, south, east, north = self.rectangle
            return Area.from_rectangle(Rectangle(west, south, east, north))
        if self.shape_type == "polygon":
            if not self.polygon:
                raise ValueError("a polygon needs at least three [lat, lng] vertices")
            vertices = ((float(v[0]), float(v[1])) for v in self.polygon)
            return Area.from_polygon(Polygon(tuple(vertices)))
        if self.bbox is None:
            raise ValueError("an administrative area needs the bounding box it resolved to")
        west, south, east, north = self.bbox
        from app.shared.geo import BoundingBox

        return Area.from_bounding_box(BoundingBox(west, south, east, north))


class SearchAreaIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    module: str = Field(default="leads", max_length=50)
    geometry: AreaGeometryIn
    categories: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("categories")
    @classmethod
    def _clean_categories(cls, value: list[str]) -> list[str]:
        return [item.strip()[:150] for item in value if item.strip()]


class SearchAreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    module: str
    shape_type: str
    area_km2: float
    center_latitude: float | None
    center_longitude: float | None
    radius_m: int | None
    bbox_west: float
    bbox_south: float
    bbox_east: float
    bbox_north: float
    polygon: list | None
    admin_country: str | None
    admin_state: str | None
    admin_city: str | None
    admin_locality: str | None
    categories: list
    last_run_at: datetime | None
    created_at: datetime


class SearchAreaListOut(BaseModel):
    items: list[SearchAreaOut]
    total: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: str
    execution_target: str
    progress_percent: float
    total_records: int
    processed_records: int
    failed_records: int
    area_id: uuid.UUID | None = None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_details: dict[str, Any] | None
    report: dict[str, Any] | None


class JobListOut(BaseModel):
    items: list[JobOut]
    total: int


class TileBatchOut(BaseModel):
    """One unit of geographic work and the state it finished in."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    batch_number: int
    unit_kind: str
    tile_key: str | None
    status: str
    records_expected: int
    records_processed: int
    retry_count: int
    truncated: bool
    bounds: dict[str, float] | None
    error_details: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
