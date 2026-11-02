from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.automation.models import STEP_TYPES


class WorkflowStep(BaseModel):
    """One step in a workflow definition, validated against the engine's vocabulary."""

    key: str = Field(min_length=1, max_length=100)
    type: str
    config: dict = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in STEP_TYPES:
            raise ValueError(f"Unsupported step type '{value}'. Supported: {', '.join(STEP_TYPES)}")
        return value

    @field_validator("key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Step key must be alphanumeric with hyphens or underscores")
        return value


class WorkflowCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    module: str = Field(default="leads", max_length=50)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=20)

    @field_validator("steps")
    @classmethod
    def _unique_keys(cls, value: list[WorkflowStep]) -> list[WorkflowStep]:
        keys = [step.key for step in value]
        if len(keys) != len(set(keys)):
            raise ValueError("Step keys must be unique within a workflow")
        return value


class WorkflowUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    module: str | None = Field(default=None, max_length=50)
    status: Literal["draft", "active", "paused", "archived"] | None = None
    steps: list[WorkflowStep] | None = Field(default=None, max_length=20)

    @field_validator("steps")
    @classmethod
    def _unique_keys(cls, value: list[WorkflowStep] | None) -> list[WorkflowStep] | None:
        if value is None:
            return value
        keys = [step.key for step in value]
        if len(keys) != len(set(keys)):
            raise ValueError("Step keys must be unique within a workflow")
        return value


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    module: str
    workflow_definition: dict
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class WorkflowListOut(BaseModel):
    items: list[WorkflowOut]
    total: int
    limit: int
    offset: int


def _validate_recurrence(value: dict) -> dict:
    has_interval = "interval_seconds" in value
    has_cron = "cron" in value
    if has_interval == has_cron:
        raise ValueError(
            "recurrence_config must contain exactly one of 'interval_seconds' or 'cron'"
        )
    if has_interval:
        seconds = value["interval_seconds"]
        if not isinstance(seconds, int) or seconds < 60:
            raise ValueError("interval_seconds must be an integer >= 60")
    else:
        cron = value["cron"]
        if not isinstance(cron, str) or len(cron.split()) != 5:
            raise ValueError("cron must be a five-field cron expression")
    return value


class ScheduleCreateIn(BaseModel):
    workflow_id: uuid.UUID
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    recurrence_config: dict = Field(default_factory=dict)
    start_at: datetime
    end_at: datetime | None = None
    is_enabled: bool = True

    @field_validator("recurrence_config")
    @classmethod
    def _valid_recurrence(cls, value: dict) -> dict:
        return _validate_recurrence(value)


class ScheduleUpdateIn(BaseModel):
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    recurrence_config: dict | None = None
    end_at: datetime | None = None
    is_enabled: bool | None = None

    @field_validator("recurrence_config")
    @classmethod
    def _valid_recurrence(cls, value: dict | None) -> dict | None:
        if value is None:
            return value
        return _validate_recurrence(value)


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    timezone: str
    recurrence_config: dict
    start_at: datetime
    end_at: datetime | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class ScheduleListOut(BaseModel):
    items: list[ScheduleOut]
    total: int
    limit: int
    offset: int


class ExecutionRunIn(BaseModel):
    input_data: dict = Field(default_factory=dict)


class StepExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    step_key: str
    step_type: str
    status: str
    input_data: dict
    output_data: dict
    retry_count: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: dict | None = None


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    trigger_type: str
    status: str
    input_data: dict
    output_data: dict
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: dict | None = None
    created_at: datetime
    steps: list[StepExecutionOut] | None = None


class ExecutionListOut(BaseModel):
    items: list[ExecutionOut]
    total: int
    limit: int
    offset: int


class WorkflowRunOut(BaseModel):
    execution_id: uuid.UUID
    status: str


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    step_execution_id: uuid.UUID | None = None
    approval_type: str
    status: str
    original_content: dict
    approved_content: dict | None = None
    reviewed_by_user_id: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ApprovalListOut(BaseModel):
    items: list[ApprovalOut]
    total: int
    limit: int
    offset: int


class ApprovalReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    content: dict | None = None
