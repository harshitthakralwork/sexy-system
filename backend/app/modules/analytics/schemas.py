from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsBucket(BaseModel):
    key: str
    count: int


class AnalyticsOut(BaseModel):
    generated_at: datetime
    leads_total: int
    businesses_by_website_status: list[AnalyticsBucket] = Field(default_factory=list)
    businesses_by_lifecycle: list[AnalyticsBucket] = Field(default_factory=list)
    crm_by_stage: list[AnalyticsBucket] = Field(default_factory=list)
    opportunities_by_status: list[AnalyticsBucket] = Field(default_factory=list)
    discovery_jobs_by_status: list[AnalyticsBucket] = Field(default_factory=list)
    social_by_classification: list[AnalyticsBucket] = Field(default_factory=list)
    social_by_platform: list[AnalyticsBucket] = Field(default_factory=list)
    social_by_track_type: list[AnalyticsBucket] = Field(default_factory=list)
    startups_by_funding_stage: list[AnalyticsBucket] = Field(default_factory=list)


class ReportCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    report_type: str = Field(default="analytics")


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    report_type: str
    snapshot: dict = Field(default_factory=dict)
    captured_at: str | None = None
    created_at: datetime
    updated_at: datetime


class ReportListOut(BaseModel):
    items: list[ReportOut]
    total: int
    limit: int
    offset: int
