from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    position: int
    color: str | None = None
    is_terminal: bool
    is_active: bool


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_default: bool
    stages: list[StageOut] = Field(default_factory=list)


class BoardCardOut(BaseModel):
    """A business as it sits on the board: the card, not the full record."""

    business_id: uuid.UUID
    name: str
    primary_category: str | None = None
    city: str | None = None
    website_status: str
    stage_id: uuid.UUID
    stage_name: str
    next_follow_up_at: datetime | None = None


class BoardOut(BaseModel):
    stages: list[StageOut]
    cards: list[BoardCardOut]


class StageCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=30)
    position: int | None = Field(default=None, ge=1)


class StageUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    activity_type: str
    title: str
    description: str | None = None
    occurred_at: datetime


class ActivityListOut(BaseModel):
    items: list[ActivityOut]
    total: int
    limit: int
    offset: int
