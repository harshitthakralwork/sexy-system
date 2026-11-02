from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    is_active: bool


class ServiceListOut(BaseModel):
    items: list[ServiceOut]
    total: int


class ServiceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_name: str
    signal_key: str
    weight: float
    operator: str
    threshold: Any | None = None
    is_required: bool
    is_active: bool


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    name: str
    qualification_threshold: float
    is_active: bool
    version: int
    rules: list[RuleOut] = Field(default_factory=list)


class ServiceDetailOut(ServiceOut):
    profiles: list[ProfileOut] = Field(default_factory=list)


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evidence_type: str
    description: str
    source_url: str | None = None
    evidence_value: dict[str, Any] | None = None
    score_contribution: float
    confidence: float | None = None
    observed_at: datetime


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    service_id: uuid.UUID
    service_profile_id: uuid.UUID
    score: float
    confidence: float
    status: str
    evidence_summary: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    profile_version: int
    evaluated_at: datetime
    evidence: list[EvidenceOut] = Field(default_factory=list)


class OpportunityListOut(BaseModel):
    items: list[OpportunityOut]
    total: int
