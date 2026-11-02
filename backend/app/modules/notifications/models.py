from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

ENTITY_REGISTRY = (
    "business",
    "business_contact",
    "startup",
    "social_profile",
    "discovery_job",
    "crm_record",
    "export_job",
    "opportunity",
)

PROTECTED_DATA_CATEGORIES = ("shortlisted_lead", "outreach_history")


class Notification(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_owner_read", "owner_user_id", "is_read", "created_at"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Deep link target. Validated against ENTITY_REGISTRY, not trusted as free text.
    related_entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    # Structured detail only. Secrets, tokens and free personal data do not belong here.
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class RetentionPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Row-driven retention so cleanup rules are data, not code constants.

    Categories in ``PROTECTED_DATA_CATEGORIES`` are never eligible for
    temporary-data deletion, whatever the retention worker finds.
    """

    __tablename__ = "retention_policies"
    __table_args__ = (Index("ix_retention_category_active", "data_category", "is_active"),)

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True, index=True)
    data_category: Mapped[str] = mapped_column(String(100), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
