from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScanCreateIn(BaseModel):
    niche: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=160)
    country: str = Field(default="India", max_length=100)


class ScanUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_name: str
    unit_kind: str
    query_or_url: str
    locality: str | None = None
    status: str
    candidates_found: int = 0
    candidates_accepted: int = 0
    candidates_duplicate: int = 0
    retry_count: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ScanRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    niche: str
    city: str
    country: str
    query_variants: list[str] = Field(default_factory=list)
    locality_units: list[str] = Field(default_factory=list)
    status: str
    stage: str
    progress_percent: float
    candidate_count: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    retries: int = 0
    source_coverage: dict[str, Any] = Field(default_factory=dict)
    cancellation_requested: bool = False
    error_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    units: list[ScanUnitOut] = Field(default_factory=list)


class ScanRunListOut(BaseModel):
    items: list[ScanRunOut]
    total: int
