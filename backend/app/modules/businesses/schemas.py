from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    primary_category: str | None = None
    website_url: str | None = None
    website_status: str
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    lifecycle_status: str
    first_discovered_at: datetime | None = None
    last_researched_at: datetime | None = None


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


class ActionOut(BaseModel):
    id: uuid.UUID
    message: str
    crm_stage: str | None = None
