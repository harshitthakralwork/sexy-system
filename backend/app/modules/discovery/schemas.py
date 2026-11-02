from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.discovery.adapters.base import DiscoveryQuery, LocationSpec

MAX_KEYWORDS = 10
MAX_KEYWORD_LENGTH = 100
# Overpass tag keys/values are interpolated into the QL string, so the same
# whitelist the adapter applies is applied here too — a rejected request is
# cheaper than a rejected query at the endpoint.
CATEGORY_PATTERN = r"^[A-Za-z0-9:_-]{1,40}$"


class LocationIn(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=50)
    place_name: str | None = Field(default=None, max_length=150)
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _coherent(self) -> LocationIn:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        if self.radius_km is not None and self.latitude is None:
            raise ValueError("radius_km requires a centre coordinate")
        return self


class DiscoveryJobIn(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)
    category: str | None = Field(default=None, pattern=CATEGORY_PATTERN)
    location: LocationIn | None = None
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
        if not self.keywords and self.category is None and self.location is None:
            raise ValueError("a discovery query needs keywords, a category or a location")
        return self

    def to_query(self) -> DiscoveryQuery:
        location = None
        if self.location is not None:
            location = LocationSpec(
                query_bbox=self.location.bbox,
                center=(self.location.latitude, self.location.longitude)
                if self.location.latitude is not None and self.location.longitude is not None
                else None,
                radius_km=self.location.radius_km,
                place_name=self.location.place_name,
            )
        return DiscoveryQuery(
            keywords=tuple(self.keywords),
            category=self.category,
            location=location,
            country=self.country.upper(),
            max_results=self.max_results,
        )

    def to_config(self) -> dict[str, Any]:
        """JSON-safe form of the request, stored on the `searches` row."""
        return self.model_dump(mode="json")


def query_from_config(config: dict[str, Any]) -> DiscoveryJobIn:
    """Rebuild the validated request from stored config.

    Going through the request model rather than reading the JSON directly means
    a hand-edited or legacy row cannot smuggle past the same bounds a live API
    caller is held to.
    """
    return DiscoveryJobIn.model_validate(config)


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
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_details: dict[str, Any] | None
    report: dict[str, Any] | None


class JobListOut(BaseModel):
    items: list[JobOut]
    total: int
