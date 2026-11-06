from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

SCAN_RUN_STATUSES = (
    "queued",
    "planning",
    "running",
    "paused",
    "completed",
    "cancelled",
    "failed",
)
SCAN_RUN_STAGES = (
    "planning",
    "source_discovery",
    "page_verification",
    "contact_page_checks",
    "deduplication",
    "saving",
    "completed",
)
SCAN_UNIT_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


class LocalScanRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Durable state for a multi-source, resumable Local Business Finder scan run."""

    __tablename__ = "local_scan_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'queued', 'planning', 'running', 'paused', 'completed', 'cancelled', 'failed')",
            name="ck_local_scan_run_status",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_local_scan_run_progress",
        ),
        Index("ix_local_scan_runs_owner_status", "owner_user_id", "status", "created_at"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_local_scan_runs_owner_user_id_users"),
        nullable=False,
        index=True,
    )
    niche: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str] = mapped_column(String(160), nullable=False)
    country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="India", server_default=text("'India'")
    )

    query_variants: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    locality_units: Mapped[list] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", server_default=text("'queued'")
    )
    stage: Mapped[str] = mapped_column(
        String(100), nullable=False, default="planning", server_default=text("'planning'")
    )
    progress_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0.0, server_default=text("0.0")
    )

    retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    accepted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    rejected_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    source_coverage: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    units: Mapped[list[LocalScanUnit]] = relationship(
        back_populates="scan_run", cascade="all, delete-orphan", order_by="LocalScanUnit.created_at"
    )


class LocalScanUnit(Base, UUIDPrimaryKeyMixin):
    """An individual granular unit of work within a LocalScanRun."""

    __tablename__ = "local_scan_units"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_local_scan_unit_status",
        ),
        Index("ix_local_scan_units_run_status", "scan_run_id", "status"),
        Index("ix_local_scan_units_source", "source_name", "status"),
    )

    scan_run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("local_scan_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    unit_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    query_or_url: Mapped[str] = mapped_column(Text, nullable=False)
    locality: Mapped[str | None] = mapped_column(String(150), nullable=True)

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", server_default=text("'queued'")
    )
    candidates_found: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    candidates_accepted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    candidates_duplicate: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_metadata: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan_run: Mapped[LocalScanRun] = relationship(back_populates="units")


class LocalScanBusiness(Base):
    """Association linking a scan run to the businesses discovered/observed in it."""

    __tablename__ = "local_scan_businesses"
    __table_args__ = (
        Index("ix_local_scan_businesses_run", "scan_run_id"),
        Index("ix_local_scan_businesses_biz", "business_id"),
    )

    scan_run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("local_scan_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
