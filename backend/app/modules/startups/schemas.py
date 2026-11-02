from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# --- Startup ---------------------------------------------------------------


class StartupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    website_url: str | None = None
    normalized_domain: str | None = None
    description: str | None = None
    industry: str | None = None
    country: str | None = None
    city: str | None = None
    founding_date: date | None = None
    launch_date: date | None = None
    funding_stage: str | None = None
    status: str
    source_slug: str | None = None
    source_url: str | None = None
    first_discovered_at: datetime
    last_researched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StartupCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website_url: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=150)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=150)
    founding_date: date | None = None
    launch_date: date | None = None
    funding_stage: str | None = Field(default=None, max_length=100)
    status: str = Field(default="unknown", max_length=50)
    source_slug: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=2000)


class StartupUpdateIn(BaseModel):
    website_url: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=150)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=150)
    founding_date: date | None = None
    launch_date: date | None = None
    funding_stage: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=50)


class StartupListOut(BaseModel):
    items: list[StartupOut]
    total: int
    limit: int
    offset: int


# --- Founder ---------------------------------------------------------------


class FounderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    startup_id: uuid.UUID
    name: str
    role: str | None = None
    public_profile_url: str | None = None
    source_id: uuid.UUID | None = None
    created_at: datetime


class FounderCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=150)
    public_profile_url: str | None = Field(default=None, max_length=2000)


# --- Product ---------------------------------------------------------------


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    startup_id: uuid.UUID
    name: str
    description: str | None = None
    product_url: str | None = None
    category: str | None = None
    launch_date: date | None = None
    created_at: datetime
    updated_at: datetime


class ProductCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    product_url: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=150)
    launch_date: date | None = None


# --- Pricing ---------------------------------------------------------------


class PricingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    plan_name: str
    amount: float | None = None
    currency: str | None = None
    billing_period: str | None = None
    pricing_url: str | None = None
    observed_at: datetime


class PricingCreateIn(BaseModel):
    plan_name: str = Field(min_length=1, max_length=150)
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)
    billing_period: str | None = Field(default=None, max_length=30)
    pricing_url: str | None = Field(default=None, max_length=2000)


# --- Revenue ---------------------------------------------------------------


class RevenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    startup_id: uuid.UUID
    amount: float | None = None
    currency: str | None = None
    revenue_period: str | None = None
    classification: str
    methodology: str | None = None
    assumptions: dict = Field(default_factory=dict)
    confidence: float | None = None
    source_url: str | None = None
    reported_at: datetime | None = None
    observed_at: datetime


class RevenueCreateIn(BaseModel):
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)
    revenue_period: str | None = Field(default=None, max_length=30)
    classification: str = Field(default="not_available", max_length=30)
    methodology: str | None = Field(default=None, max_length=5000)
    assumptions: dict = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=100)
    source_url: str | None = Field(default=None, max_length=2000)
    reported_at: datetime | None = None


# --- Competitor ------------------------------------------------------------


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    startup_id: uuid.UUID
    competitor_startup_id: uuid.UUID
    relationship_type: str | None = None
    evidence: dict = Field(default_factory=dict)
    created_at: datetime


class CompetitorCreateIn(BaseModel):
    competitor_startup_id: uuid.UUID
    relationship_type: str | None = Field(default=None, max_length=50)
    evidence: dict = Field(default_factory=dict)


# --- Research --------------------------------------------------------------


class ResearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    startup_id: uuid.UUID
    research_type: str
    summary: str | None = None
    findings: dict = Field(default_factory=dict)
    source_references: dict = Field(default_factory=dict)
    researched_at: datetime


class ResearchCreateIn(BaseModel):
    research_type: str = Field(min_length=1, max_length=100)
    summary: str | None = Field(default=None, max_length=5000)
    findings: dict = Field(default_factory=dict)
    source_references: dict = Field(default_factory=dict)


# --- Watchlist -------------------------------------------------------------


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[StartupOut] = Field(default_factory=list)


class WatchlistCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class WatchlistItemIn(BaseModel):
    startup_id: uuid.UUID


# --- Detail ----------------------------------------------------------------


class StartupDetailOut(StartupOut):
    founders: list[FounderOut] = Field(default_factory=list)
    products: list[ProductOut] = Field(default_factory=list)
    revenue: list[RevenueOut] = Field(default_factory=list)
    competitors: list[CompetitorOut] = Field(default_factory=list)
    research: list[ResearchOut] = Field(default_factory=list)
    watchlists: list[str] = Field(default_factory=list)
