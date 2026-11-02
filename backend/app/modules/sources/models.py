from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

HEALTH_STATUSES = ("working", "degraded", "failed", "unknown")


class Source(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Registry entry for a discovery provider.

    ``capabilities``, ``limitations`` and ``coverage`` exist so the UI can tell
    the user what a source can and cannot do instead of implying parity.
    """

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    health_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown", server_default=text("'unknown'")
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    limitations: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    coverage: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    rate_limit_config: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class SourceConfiguration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source_configurations"
    __table_args__ = (
        # One row per account per source: enable/disable and configuration are
        # meaningless if two rows can disagree about them.
        UniqueConstraint("source_id", "owner_user_id", name="uq_source_config_owner"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, nullable=False, index=True)
    configuration: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Reference into the secret store, never the secret itself.
    secret_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class SourceHealthCheck(Base):
    __tablename__ = "source_health_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class SourceUsageRecord(Base):
    """Per-job source consumption. ``quota_remaining`` stays null when a
    provider does not expose quota information.

    ``records_accepted`` is null when the run only counted what it stored for the
    job as a whole — a discovery run knows how many rows each source *returned*,
    not how many each one got past deduplication. Zero would claim the source
    contributed nothing.
    """

    __tablename__ = "source_usage_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True, index=True)
    requests_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_accepted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quota_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
