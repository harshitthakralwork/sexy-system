from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

EMAIL_ACCOUNT_STATUSES = ("pending", "connected", "failed", "disabled")
EMAIL_PROVIDERS = ("smtp", "gmail_oauth")
CAMPAIGN_STATUSES = ("draft", "active", "paused", "completed", "archived")
MESSAGE_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "rejected",
    "sending",
    "sent",
    "delivered",
    "bounced",
    "failed",
    "replied",
    "suppressed",
    "cancelled",
)
EVENT_TYPES = (
    "sent",
    "delivered",
    "bounced",
    "opened",
    "clicked",
    "replied",
    "unsubscribed",
    "failed",
    "complained",
)


class EmailAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A sending identity. Holds a `secret_reference`, never the secret itself.

    `database-schema.md` §16.1 also lists `encrypted_credentials BYTEA`; that column
    is deliberately not modelled — the spec itself says to prefer an external secret
    manager, and a secret stored in the application database is a secret that can leak
    with the backup.
    """

    __tablename__ = "email_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','connected','failed','disabled')",
            name="ck_email_account_status",
        ),
        CheckConstraint(
            "provider IN ('smtp','gmail_oauth')",
            name="ck_email_account_provider",
        ),
        Index("ix_email_account_owner_address", "owner_user_id", "email_address", unique=True),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_email_accounts_owner_user_id_users"),
        nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="smtp", server_default=text("'smtp'")
    )
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    secret_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Campaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named outreach campaign, optionally tied to a workflow."""

    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','paused','completed','archived')",
            name="ck_campaign_status",
        ),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_campaigns_owner_user_id_users"),
        nullable=False, index=True,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", server_default=text("'draft'")
    )
    settings: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class EmailMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One outbound message and its full lifecycle, from draft to reply."""

    __tablename__ = "email_messages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','pending_approval','approved','rejected','sending','sent',"
            "'delivered','bounced','failed','replied','suppressed','cancelled')",
            name="ck_email_message_status",
        ),
        Index("ix_email_message_status", "owner_user_id", "status"),
    )

    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    email_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("email_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("business_contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_email_messages_owner_user_id_users"),
        nullable=False, index=True,
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", server_default=text("'draft'")
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Provider- or system-reported lifecycle event for one message."""

    __tablename__ = "email_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('sent','delivered','bounced','opened','clicked','replied',"
            "'unsubscribed','failed','complained')",
            name="ck_email_event_type",
        ),
    )

    email_message_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("email_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SuppressionEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An address that must never be emailed, with a reason and source."""

    __tablename__ = "suppression_list"
    __table_args__ = (
        Index("ix_suppression_owner_email", "owner_user_id", "normalized_email", unique=True),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_suppression_list_owner_user_id_users"),
        nullable=False, index=True,
    )
    email_address: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
