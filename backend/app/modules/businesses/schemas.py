from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.discovery.provenance import is_official_website


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    primary_category: str | None = None
    website_url: str | None = None
    website_status: str
    phone: str | None = None
    email: str | None = None
    rating: float | None = None
    review_count: int | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    enrichment: dict[str, Any] = Field(default_factory=dict)
    lifecycle_status: str
    first_discovered_at: datetime | None = None
    last_researched_at: datetime | None = None

    @field_validator("website_url", mode="before")
    @classmethod
    def hide_non_business_website_urls(cls, value: str | None) -> str | None:
        """Prevent historical Maps image/assets from rendering as a website."""
        return value if value is None or is_official_website(str(value)) else None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_type: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    verification_status: str
    verification_date: datetime | None = None
    source_url: str | None = None


class BusinessDetail(BusinessOut):
    contacts: list[ContactOut] = Field(default_factory=list)
    crm_stage: str | None = None
    source_slugs: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class BusinessListOut(BaseModel):
    items: list[BusinessOut]
    total: int
    limit: int
    offset: int


class PinOut(BaseModel):
    """One marker. Carries only what a pin and its preview need."""

    id: uuid.UUID
    name: str
    latitude: float
    longitude: float
    primary_category: str | None = None
    website_status: str
    has_phone: bool
    rating: float | None = None
    review_count: int | None = None
    discovered_at: datetime


class ViewportOut(BaseModel):
    """A viewport read that admits what it left out.

    `total_in_viewport` counts every matching record; `returned` is what was sent.
    When they differ the client must say so rather than let a dense area look sparse.
    """

    items: list[PinOut]
    total_in_viewport: int
    returned: int
    truncated: bool
    bbox: list[float]


class SelectedExportIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class BulkDeleteIn(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    delete_all: bool = False


class BulkDeleteOut(BaseModel):
    deleted: int


class SelectedExportOut(BaseModel):
    rows: int
    skipped: int = Field(
        default=0, description="Requested ids that are not the caller's records or no longer exist"
    )


class ActionOut(BaseModel):
    id: uuid.UUID
    message: str
    crm_stage: str | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    content: str
    created_at: datetime
    updated_at: datetime


class NoteCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str | None = None


class TagAssignIn(BaseModel):
    names: list[str] = Field(max_length=20)
