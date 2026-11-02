from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# --- Platform --------------------------------------------------------------


class SocialPlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    adapter_key: str
    capabilities: dict = Field(default_factory=dict)
    limitations: dict = Field(default_factory=dict)
    is_enabled: bool
    health_status: str
    last_run_at: datetime | None = None
    last_error: str | None = None


# --- Research queries -------------------------------------------------------


class SocialResearchQueryCreateIn(BaseModel):
    platform_slug: str = Field(min_length=1, max_length=100)
    query_config: dict = Field(default_factory=dict)


class SocialResearchQueryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_id: uuid.UUID
    platform_slug: str
    query_config: dict
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    last_run_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SocialResearchQueryListOut(BaseModel):
    items: list[SocialResearchQueryOut]
    total: int
    limit: int
    offset: int


# --- Content ---------------------------------------------------------------


class SocialContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_id: uuid.UUID
    platform_slug: str
    research_query_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    external_id: str
    content_url: str | None = None
    content_type: str
    content_text: str | None = None
    published_at: datetime | None = None
    engagement_data: dict = Field(default_factory=dict)
    author_username: str | None = None
    author_profile_url: str | None = None
    collected_at: datetime


class SocialContentListOut(BaseModel):
    items: list[SocialContentOut]
    total: int
    limit: int
    offset: int


class SocialRunOut(BaseModel):
    query_id: uuid.UUID
    platform_slug: str
    status: str
    collected: int
    stored_new: int
    duplicates: int
    error: str | None = None


class SocialLinkIn(BaseModel):
    business_id: uuid.UUID


class SocialLinkOut(BaseModel):
    business_id: uuid.UUID
    platform: str
    profile_url: str
