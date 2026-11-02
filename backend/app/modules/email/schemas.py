from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.email.models import EMAIL_PROVIDERS


class EmailAccountCreateIn(BaseModel):
    provider: str = Field(default="smtp", max_length=50)
    email_address: EmailStr
    secret_reference: str | None = Field(default=None, max_length=255)

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        if value not in EMAIL_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{value}'. Supported: {', '.join(EMAIL_PROVIDERS)}"
            )
        return value


class EmailAccountUpdateIn(BaseModel):
    status: Literal["pending", "connected", "failed", "disabled"] | None = None
    secret_reference: str | None = Field(default=None, max_length=255)


class EmailAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    email_address: str
    secret_reference: str | None = None
    status: str
    connected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EmailAccountListOut(BaseModel):
    items: list[EmailAccountOut]
    total: int
    limit: int
    offset: int


class CampaignCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    workflow_id: uuid.UUID | None = None
    settings: dict = Field(default_factory=dict)


class CampaignUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    status: Literal["draft", "active", "paused", "completed", "archived"] | None = None
    settings: dict | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID | None = None
    name: str
    status: str
    settings: dict
    created_at: datetime
    updated_at: datetime


class CampaignListOut(BaseModel):
    items: list[CampaignOut]
    total: int
    limit: int
    offset: int


class EmailMessageCreateIn(BaseModel):
    recipient_email: EmailStr
    subject: str | None = Field(default=None, max_length=500)
    body: str | None = None
    business_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    email_account_id: uuid.UUID | None = None


class EmailMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID | None = None
    email_account_id: uuid.UUID | None = None
    business_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    workflow_execution_id: uuid.UUID | None = None
    recipient_email: str
    subject: str | None = None
    body: str | None = None
    status: str
    provider_message_id: str | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    bounced_at: datetime | None = None
    replied_at: datetime | None = None
    created_at: datetime


class EmailMessageListOut(BaseModel):
    items: list[EmailMessageOut]
    total: int
    limit: int
    offset: int


class EmailEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email_message_id: uuid.UUID
    event_type: str
    provider_event_id: str | None = None
    event_data: dict
    occurred_at: datetime
    created_at: datetime


class SuppressionCreateIn(BaseModel):
    email_address: EmailStr
    reason: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=100)


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email_address: str
    normalized_email: str
    reason: str | None = None
    source: str | None = None
    created_at: datetime


class SuppressionListOut(BaseModel):
    items: list[SuppressionOut]
    total: int
    limit: int
    offset: int


class SendResultOut(BaseModel):
    message_id: uuid.UUID
    status: str
    provider_message_id: str | None = None
    error: str | None = None
