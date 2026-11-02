from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    category: str
    adapter_key: str
    description: str | None = None
    globally_enabled: bool
    enabled_for_user: bool
    configured_at: datetime | None = None
    configuration: dict = Field(default_factory=dict)
    secret_reference: str | None = None
    health_status: str
    last_error: str | None = None
    last_check_at: datetime | None = None
    last_check_response_ms: int | None = None
    last_check_detail: str | None = None
    last_successful_run_at: datetime | None = None
    runs_recorded: int = 0
    requests_count: int = 0
    records_returned: int = 0
    records_accepted: int | None = None
    capabilities: dict = Field(default_factory=dict)
    limitations: dict = Field(default_factory=dict)
    coverage: dict = Field(default_factory=dict)
    rate_limit_config: dict = Field(default_factory=dict)


class SourceGroupOut(BaseModel):
    category: str
    items: list[SourceOut]


class SourceListOut(BaseModel):
    groups: list[SourceGroupOut]
    total: int


class SourceConfigIn(BaseModel):
    feed_urls: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    secret_reference: str | None = Field(default=None, max_length=255)


class SourceConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    configuration: dict = Field(default_factory=dict)
    secret_reference: str | None = None
    is_enabled: bool
    updated_at: datetime


class SourceEnableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    enabled_for_user: bool


class SourceTestOut(BaseModel):
    slug: str
    status: str
    detail: str | None = None
    response_time_ms: int | None = None
    checked_at: datetime


class HealthCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    checked_at: datetime
    response_time_ms: int | None = None
    error_message: str | None = None


class UsageRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID | None = None
    requests_count: int
    records_returned: int
    records_accepted: int | None = None
    measured_at: datetime


class SourceHistoryOut(BaseModel):
    slug: str
    checks: list[HealthCheckOut]
    runs: list[UsageRecordOut]
