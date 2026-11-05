from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WebProspectingIn(BaseModel):
    niche: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=160)
    max_candidates: int = Field(default=25, ge=1, le=50)


class VerifiedRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    niche: str
    city: str
    source_kind: str
    max_candidates: int
    status: Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
    stage: str
    progress_percent: int
    candidate_count: int
    saved_count: int
    failed_count: int
    cancellation_requested: bool
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class VerifiedLeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID
    name: str
    city: str
    source_type: str
    source_url: str
    website_url: str | None
    website_status: Literal["has_website", "unknown"]
    public_phone: str | None
    public_email: str | None
    address: str | None
    rating: float | None
    review_count: int | None
    latitude: float | None
    longitude: float | None
    potential_score: int
    score_reasons: list[str]
    evidence: dict
    created_at: datetime


class VerifiedLeadListOut(BaseModel):
    items: list[VerifiedLeadOut]
    total: int
